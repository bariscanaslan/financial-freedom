"""
model/predict.py'nin Forecast'ini PORTFOLYO duzeyine toplar.

Portfolyo katmani tahmin URETMEZ, TUKETIR. predict.py bir ticker icin
{p10, p50, p90} getiri + fiyat dondurur; burada bunlar pozisyonlara gore
toplanip portfolyonun 1-gunluk getiri dagilimina cevrilir.

KORELASYON IHMAL EDILIR -- ve bu YANLISTIR. Pozisyonlar bagimsiz degildir
(ayni piyasa faktoru hepsini birden hareket ettirir). Burada her ticker'in
ayni anda kendi quantile'ina gittigi (KOMONOTON, mukemmel korelasyon)
varsayilir. Bu, gercek cesitlendirmeyi yok saydigi icin araligi oldugundan
GENIS/muhafazakar verir. Cikti bir TAVSIYE degil, tanimlayici bir gorunumdur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from .portfolio import PositionState

if TYPE_CHECKING:
    # Yalnizca tip ipucu icin. Calisma aninda kullanilmaz -- boylece portfolyo
    # katmani (ve muhasebe cekirdegi) torch'a bagimli olmaz.
    from model.predict import Forecast

_WARNING = (
    "Correlation ignored (comonotonic assumption): positions were not treated "
    "as independent; all were moved to their own quantile at once. Real "
    "diversification NARROWS the range, so this range is conservative/wide. "
    "This is a descriptive output, NOT an action recommendation."
)


@dataclass
class PortfolioForecast:
    as_of: str
    current_value: float          # nakit + pozisyonlarin cari degeri
    cash: float
    quantiles: tuple[float, ...]
    values: dict[str, float]      # portfolyo DEGERI cinsinden {p10,p50,p90}
    returns: dict[str, float]     # portfolyo cari degerine gore basit getiri
    warning: str = _WARNING
    method: str = "comonotonic"
    correlation: dict[str, dict[str, float]] | None = None
    periods: dict[str, dict] = field(default_factory=dict)

    def __str__(self) -> str:
        v = "  ".join(f"{k}={x:.2f}" for k, x in self.values.items())
        r = "  ".join(f"{k}={x:+.4%}" for k, x in self.returns.items())
        return (
            f"portfolyo 1-gunluk dagilim  as_of={self.as_of}\n"
            f"  cari deger : {self.current_value:.2f}  (nakit {self.cash:.2f})\n"
            f"  deger      : {v}\n"
            f"  getiri     : {r}\n"
            f"  UYARI: {self.warning}"
        )


def portfolio_forecast(
    state: PositionState,
    forecasts: dict[str, Forecast],
    correlation: pd.DataFrame | None = None,
) -> PortfolioForecast:
    """
    Args:
        state: portfolio.replay() ciktisi (holdings + cash).
        forecasts: ticker -> model.predict.Forecast. Her acik pozisyon icin
                   bir tahmin bulunmali; eksikse hata verilir (sessizce
                   pozisyon dusurmek riski oldugundan kucuk gosterir).

    KOMONOTON toplama: her quantile icin portfolyo degeri =
        nakit + Σ_ticker adet * ticker_fiyat_quantile
    Nakit risksizdir; her quantile'da aynidir.
    """
    holdings = state.holdings
    missing = [t for t in holdings if t not in forecasts]
    if missing:
        raise ValueError(f"no forecast for these positions: {missing}")

    # quantile isimleri ilk tahminden alinir; hepsi ayni olmali
    if holdings:
        any_fc = forecasts[next(iter(holdings))]
        qnames = list(any_fc.prices.keys())
        quantiles = tuple(any_fc.quantiles)
    else:
        qnames, quantiles = ["p10", "p50", "p90"], (0.1, 0.5, 0.9)

    cash = state.cash
    current_value = cash
    values = {q: cash for q in qnames}
    for t, qty in holdings.items():
        fc = forecasts[t]
        current_value += qty * fc.anchor_price
        for q in qnames:
            values[q] += qty * fc.prices[q]

    returns = {
        q: (values[q] / current_value - 1.0) if current_value else float("nan")
        for q in qnames
    }
    if correlation is not None and len(holdings) > 1:
        tickers = list(holdings)
        corr = correlation.reindex(index=tickers, columns=tickers)
        if not corr.isna().any().any():
            z = 1.2815515655446004
            exposures = np.array([
                holdings[t] * forecasts[t].anchor_price for t in tickers
            ], dtype=float)
            medians = np.array([forecasts[t].returns["p50"] for t in tickers])
            sigmas = np.array([
                (forecasts[t].returns["p90"] - forecasts[t].returns["p10"]) / (2 * z)
                for t in tickers
            ])
            mean_change = float(np.sum(exposures * medians))
            risk_dollars = exposures * sigmas
            variance = float(risk_dollars @ corr.to_numpy() @ risk_dollars)
            std_change = float(np.sqrt(max(variance, 0.0)))
            values = {
                "p10": current_value + mean_change - z * std_change,
                "p50": current_value + mean_change,
                "p90": current_value + mean_change + z * std_change,
            }
            returns = {q: values[q] / current_value - 1.0 for q in qnames}
            return PortfolioForecast(
                as_of=str(state.as_of.date()) if state.as_of is not None else "?",
                current_value=current_value, cash=cash, quantiles=quantiles,
                values=values, returns=returns,
                warning=("Pozisyonlar arası korelasyon geçmiş günlük getirilerden "
                         "tahmin edilerek risk hesabına katıldı. Geçmiş korelasyon "
                         "gelecekte değişebilir; sonuç yatırım tavsiyesi değildir."),
                method="historical_correlation",
                correlation=corr.to_dict(),
                periods=_build_periods(state, forecasts, corr),
            )

    return PortfolioForecast(
        as_of=str(state.as_of.date()) if state.as_of is not None else "?",
        current_value=current_value,
        cash=cash,
        quantiles=quantiles,
        values=values,
        returns=returns,
        periods=_build_periods(state, forecasts, None),
    )


def _build_periods(state, forecasts, correlation: pd.DataFrame | None) -> dict[str, dict]:
    """Pozisyon tahminlerini günlük/haftalık/aylık portföy riskine toplar."""
    if not state.holdings:
        return {}
    periods = {}
    for key, label, days in (("daily", "Günlük", 1), ("weekly", "Haftalık", 5),
                             ("monthly", "Aylık", 21)):
        source = {}
        for ticker in state.holdings:
            forecast = forecasts[ticker]
            if key == "daily":
                source[ticker] = {"returns": forecast.returns, "prices": forecast.prices}
            elif key in forecast.periods:
                source[ticker] = forecast.periods[key]
            else:
                break
        if len(source) != len(state.holdings):
            continue

        tickers = list(state.holdings)
        current = state.cash + sum(state.holdings[t] * forecasts[t].anchor_price for t in tickers)
        values = {q: state.cash + sum(state.holdings[t] * source[t]["prices"][q] for t in tickers)
                  for q in ("p10", "p50", "p90")}
        method = "comonotonic"
        if correlation is not None and len(tickers) > 1:
            corr = correlation.reindex(index=tickers, columns=tickers)
            z = 1.2815515655446004
            exposures = np.array([state.holdings[t] * forecasts[t].anchor_price for t in tickers])
            medians = np.array([source[t]["returns"]["p50"] for t in tickers])
            sigmas = np.array([(source[t]["returns"]["p90"] - source[t]["returns"]["p10"]) / (2 * z)
                               for t in tickers])
            mean = float(np.sum(exposures * medians))
            risk = exposures * sigmas
            std = float(np.sqrt(max(float(risk @ corr.to_numpy() @ risk), 0.0)))
            values = {"p10": current + mean - z * std, "p50": current + mean,
                      "p90": current + mean + z * std}
            method = "historical_correlation"
        returns = {q: values[q] / current - 1.0 for q in values}
        periods[key] = {"label": label, "trading_days": days, "values": values,
                        "returns": returns, "uncertainty": values["p90"] - values["p10"],
                        "uncertainty_pct": returns["p90"] - returns["p10"], "method": method}
    return periods


def return_correlation(
    price_frames: dict[str, pd.DataFrame],
    *,
    price_col: str = "adj_close",
    min_observations: int = 30,
) -> pd.DataFrame | None:
    """Ortak geçmiş günlük getirilerden korelasyon matrisi üretir."""
    if len(price_frames) < 2:
        return None
    returns = pd.concat(
        {ticker: frame[price_col].pct_change(fill_method=None) for ticker, frame in price_frames.items()},
        axis=1,
        join="inner",
    ).dropna()
    if len(returns) < min_observations:
        return None
    corr = returns.tail(252).corr()
    return None if corr.isna().any().any() else corr
