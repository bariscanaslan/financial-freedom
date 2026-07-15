"""
Tahmin: kaydedilmis model + guncel OHLCV -> {p10, p50, p90}

API katmani (ileride) bu dosyayi cagiracak. Bu yuzden burada egitim
kodu, dataset kurulumu ya da scaler fit'i YOKTUR -- olamaz da.
Scaler diskten gelir; yeniden fit edilirse leakage arka kapidan girer.

Cikti HEM getiri HEM fiyat olarak verilir:
    getiri : modelin gercekte tahmin ettigi sey (log getiri)
    fiyat  : P = son_kapanis * exp(r)   -- kullaniciya gosterilecek olan

Fiyat sadece bir SUNUM cevirisidir; kalite yargisi hep getiri uzayindadir.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.dataset import log_returns

from .registry import TrainedModel, load


@dataclass
class Forecast:
    ticker: str
    as_of: pd.Timestamp       # tahminin dayandigi son islem gunu
    target_date: pd.Timestamp | None  # hedef gun (bir sonraki islem gunu; takvim gerekir)
    anchor_price: float       # as_of gununun kapanisi

    quantiles: tuple[float, ...]
    returns: dict[str, float]  # {"p10": ..., "p50": ..., "p90": ...} log getiri
    prices: dict[str, float]   # ayni quantile'lar, fiyat cinsinden
    periods: dict[str, dict]   # daily/weekly/monthly cok adimli tahminler

    @property
    def uncertainty(self) -> float:
        """
        RISK SINYALI: en dis quantile ciftinin FIYAT cinsinden genisligi.
        Genis = model bilmiyor. Ileride sentiment risk katmani bunun
        USTUNE oturacak, yerine degil.
        """
        keys = list(self.prices)
        return self.prices[keys[-1]] - self.prices[keys[0]]

    @property
    def uncertainty_pct(self) -> float:
        """Aralik genisligi / cipa fiyati. Tickerlar arasi kiyaslanabilir."""
        return self.uncertainty / self.anchor_price

    def __str__(self) -> str:
        p = "  ".join(f"{k}={v:.2f}" for k, v in self.prices.items())
        r = "  ".join(f"{k}={v:+.4%}" for k, v in self.returns.items())
        return (
            f"{self.ticker}  as_of={self.as_of.date()}  anchor={self.anchor_price:.2f}\n"
            f"  getiri : {r}\n"
            f"  fiyat  : {p}\n"
            f"  belirsizlik: {self.uncertainty:.2f} ({self.uncertainty_pct:.2%} of anchor)"
        )

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "as_of": self.as_of.isoformat(),
            "anchor_price": self.anchor_price,
            "quantiles": list(self.quantiles),
            "returns": self.returns,
            "prices": self.prices,
            "uncertainty": self.uncertainty,
            "uncertainty_pct": self.uncertainty_pct,
            "periods": self.periods,
        }


def aggregate_quantile_path(steps: np.ndarray, median_idx: int) -> np.ndarray:
    """Günlük log-getiri quantile yolunu bağımsız hata varsayımıyla toplar."""
    path = np.asarray(steps, dtype=np.float64)
    medians = path[:, median_idx]
    center = float(medians.sum())
    cumulative = np.empty(path.shape[1], dtype=np.float64)
    for index in range(path.shape[1]):
        if index == median_idx:
            cumulative[index] = center
        else:
            distance = float(np.sqrt(np.sum((path[:, index] - medians) ** 2)))
            cumulative[index] = center - distance if index < median_idx else center + distance
    return cumulative


def _qname(q: float) -> str:
    """0.1 -> 'p10',  0.5 -> 'p50',  0.975 -> 'p97.5'"""
    v = q * 100
    return f"p{int(v)}" if float(v).is_integer() else f"p{v:g}"


def predict(
    model_path: str | Path | TrainedModel,
    recent_df: pd.DataFrame,
    *,
    market_df: pd.DataFrame | None = None,
    price_col: str = "adj_close",
    ticker: str | None = None,
) -> Forecast:
    """
    Args:
        model_path: registry.save() ile yazilmis dizin (ya da hazir TrainedModel)
        recent_df:  data/loader.fetch() formatinda OHLCV.
                    Tek degiskenli model icin en az seq_len + 1 bar.
                    Cok degiskenli model icin DAHA FAZLA gerekir: rolling
                    ozellikler (rv_21, mom_21, vol_z) 21 gunluk gecmis ister.
                    Guvenli taban: seq_len + 40 bar.
        market_df:  model piyasa faktoru (mkt_r vb.) kullaniyorsa ZORUNLU.
                    recent_df ile ayni tarih araligini kapsamali.

    Doner: Forecast
    """
    model = model_path if isinstance(model_path, TrainedModel) else load(model_path)

    seq_len = model.cfg.seq_len
    quantiles = tuple(model.cfg.quantiles)
    names = list(model.cfg.feature_names)

    if price_col not in recent_df.columns:
        raise ValueError(f"'{price_col}' kolonu yok: {list(recent_df.columns)}")

    price = recent_df[price_col].dropna()
    if len(price) < seq_len + 1:
        raise ValueError(
            f"yetersiz veri: {len(price)} bar var, seq_len+1 = {seq_len + 1} gerekli"
        )

    if model.cfg.input_dim == 1:
        # --- tek degiskenli: sadece log getiri ---
        r = log_returns(price).dropna()
        if len(r) < seq_len:
            raise ValueError(f"yetersiz getiri: {len(r)} < {seq_len}")
        window = r.iloc[-seq_len:]
        # Egitimdeki scaler. YENIDEN FIT EDILMEZ.
        z = model.scaler.transform(window.values).astype(np.float32)
        X = z.reshape(1, seq_len, 1)
        as_of = window.index[-1]
    else:
        # --- cok degiskenli: egitimdekiyle AYNI ozellikler, AYNI sirada ---
        # Import burada: features.py surekli yuklenmesin, tek degiskenli
        # yol saf kalsin.
        from .features import build_features

        needs_market = any(n.startswith(("mkt_", "rel_")) for n in names)
        if needs_market and market_df is None:
            raise ValueError(
                f"model piyasa ozellikleri kullaniyor {[n for n in names if n.startswith(('mkt_','rel_'))]}"
                " -- market_df vermelisin"
            )

        feat = build_features(recent_df, market_df=market_df, price_col=price_col)
        missing = [n for n in names if n not in feat.columns]
        if missing:
            raise ValueError(f"ozellik uretilemedi: {missing}")

        feat = feat[names]  # SIRA egitimdekiyle ayni -- kritik
        if len(feat) < seq_len:
            raise ValueError(
                f"yetersiz ozellik satiri: {len(feat)} < seq_len={seq_len}. "
                f"Daha fazla gecmis bar ver (rolling pencereler icin ~40 ekstra)."
            )

        if model.feature_scalers is None or len(model.feature_scalers) != len(names):
            raise ValueError("feature_scalers eksik -- model dogru kaydedilmemis")

        window = feat.iloc[-seq_len:]
        z = np.column_stack([
            sc.transform(window[c].values)
            for sc, c in zip(model.feature_scalers, names)
        ]).astype(np.float32)
        X = z.reshape(1, seq_len, len(names))
        as_of = window.index[-1]

    pred = model.predict(X)                          # (1, horizon, Q) -- log getiri
    steps = pred[0]                                  # (horizon, Q)
    step0 = steps[0]

    anchor = float(price.loc[as_of])                 # as_of gununun kapanisi
    prices = anchor * np.exp(step0)                  # P = anchor * exp(r)

    names = [_qname(q) for q in quantiles]
    periods = {}
    from model.config import FORECAST_PERIODS
    for key, label, days in FORECAST_PERIODS:
        if len(steps) < days:
            continue
        # Medyan log getiriler toplanır; belirsizlik doğrusal değil RSS ile
        # büyür. Böylece aynı günlük uç senaryonun 504 kez gerçekleştiğini
        # varsayan ve uzun vadede fiyatları patlatan komonotonik yol önlenir.
        cumulative = aggregate_quantile_path(steps[:days], quantiles.index(0.5))
        period_prices = anchor * np.exp(cumulative)
        ret = {n: float(v) for n, v in zip(names, cumulative)}
        px = {n: float(v) for n, v in zip(names, period_prices)}
        periods[key] = {
            "label": label,
            "trading_days": days,
            "returns": ret,
            "prices": px,
            "uncertainty": float(period_prices[-1] - period_prices[0]),
            "uncertainty_pct": float((period_prices[-1] - period_prices[0]) / anchor),
            "aggregation": "root_sum_square",
        }
    return Forecast(
        ticker=(ticker or "?").upper(),
        as_of=pd.Timestamp(as_of),
        target_date=None,  # bir sonraki islem gunu -- data/calendar.py ile doldurulabilir
        anchor_price=anchor,
        quantiles=quantiles,
        returns={n: float(v) for n, v in zip(names, step0)},
        prices={n: float(v) for n, v in zip(names, prices)},
        periods=periods,
    )


def predict_many(
    model_paths: dict[str, str | Path],
    frames: dict[str, pd.DataFrame],
    *,
    price_col: str = "adj_close",
) -> dict[str, Forecast]:
    """Portfolyo icin: ticker -> Forecast. Basarisizlari atlar ve raporlar."""
    out: dict[str, Forecast] = {}
    for t, p in model_paths.items():
        df = frames.get(t)
        if df is None:
            continue
        out[t] = predict(p, df, price_col=price_col, ticker=t)
    return out
