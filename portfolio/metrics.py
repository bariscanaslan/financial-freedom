"""
Portfolyo performans metrikleri. HEPSI NET-OF-FEES: fee'ler zaten event'lerin
nakit etkisine (cash_delta) girdigi icin deger serisi otomatik olarak fee
dusulmus haldedir.

K7 (dis akis): getiri hesabi dis para akisini DISLAR. "%12 kazandim" ile
"%12 para yatirdim" karismasin diye TIME-WEIGHTED RETURN (TWR) kullanilir.
Gunluk getiri: r_t = (V_t - F_t) / V_{t-1} - 1  (F_t = o gunku dis akis).
DIVIDEND dis akis DEGILDIR (events.external_flow), dolayisiyla getiriye dahildir.

Money-weighted (IRR) v1 kapsami disi -- ihtiyac olursa ayrica eklenir.

K4: getiri tek basina anlamsiz. Rapor katmani (report.py) her metrigi buy-and-hold
benchmark ile yan yana verir; alpha/beta bu katmandaki fonksiyonlarla hesaplanir.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import RISK_FREE_RATE, TRADING_DAYS_PER_YEAR


def daily_returns(total_value: pd.Series, external_flow: pd.Series) -> pd.Series:
    """
    Dis akistan arindirilmis gunluk getiri (TWR bileseni).

    Dis akisin o gunun SONUNDA gerceklestigi varsayilir: V_t akisi icerir,
    getiriyi bulmak icin cikaririz. V_{t-1} = 0 (henuz fonlanmamis) gunler
    tanimsizdir ve atlanir.
    """
    v = pd.Series(total_value, dtype="float64")
    f = pd.Series(external_flow, dtype="float64").reindex(v.index).fillna(0.0)
    prev = v.shift(1)
    r = (v - f) / prev - 1.0
    r = r[prev.notna() & (prev.abs() > 1e-12) & v.notna()]
    return r.dropna()


def growth_index(returns: pd.Series) -> pd.Series:
    """Gunluk getirilerden 1.0 baslangicli buyume egrisi (dis akistan bagimsiz)."""
    return (1.0 + returns).cumprod()


def twr(returns: pd.Series) -> float:
    """Toplam time-weighted getiri: prod(1+r) - 1."""
    if len(returns) == 0:
        return 0.0
    return float((1.0 + returns).prod() - 1.0)


def annualized_return(returns: pd.Series) -> float:
    if len(returns) == 0:
        return 0.0
    total = (1.0 + returns).prod()
    if total <= 0:
        return float("nan")
    return float(total ** (TRADING_DAYS_PER_YEAR / len(returns)) - 1.0)


def annualized_vol(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe(returns: pd.Series, rf_daily: float = RISK_FREE_RATE) -> float:
    if len(returns) < 2:
        return float("nan")
    sd = returns.std(ddof=1)
    if sd < 1e-12:
        return float("nan")
    return float((returns.mean() - rf_daily) / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(returns: pd.Series) -> float:
    """
    En buyuk tepe-dip dususu. Ham deger uzerinde DEGIL, buyume egrisi uzerinde
    hesaplanir -- boylece para yatirma/cekme dususu taklit etmez.
    Doner: <= 0 (ornek: -0.23 = %23 dusus).
    """
    if len(returns) == 0:
        return 0.0
    g = growth_index(returns)
    dd = g / g.cummax() - 1.0
    return float(dd.min())


def beta_alpha(
    returns: pd.Series,
    benchmark_returns: pd.Series,
) -> tuple[float, float]:
    """
    Basit beta/alpha: portfolyo gunluk getirisini benchmark'a regresle.
    beta = cov / var(benchmark),  alpha_gunluk = mean_p - beta*mean_b.
    Doner: (beta, alpha_yillik). Ortak tarihlerde hizalanir.
    """
    df = pd.concat([returns.rename("p"), benchmark_returns.rename("b")], axis=1).dropna()
    if len(df) < 2:
        return float("nan"), float("nan")
    var_b = df["b"].var(ddof=1)
    if var_b < 1e-18:
        return float("nan"), float("nan")
    beta = float(df["p"].cov(df["b"]) / var_b)
    alpha_daily = float(df["p"].mean() - beta * df["b"].mean())
    return beta, alpha_daily * TRADING_DAYS_PER_YEAR


@dataclass
class Performance:
    """Bir deger serisinin ozet performansi. Hepsi net-of-fees."""
    label: str
    n_days: int
    total_return: float      # TWR
    ann_return: float
    ann_vol: float
    sharpe: float
    max_drawdown: float
    beta: float = float("nan")
    alpha: float = float("nan")

    def to_row(self) -> dict:
        return {
            "portfolio": self.label,
            "days": self.n_days,
            "total_return": self.total_return,
            "ann_return": self.ann_return,
            "ann_vol": self.ann_vol,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "beta": self.beta,
            "alpha": self.alpha,
        }


def performance(
    values: pd.DataFrame,
    label: str,
    *,
    benchmark_returns: pd.Series | None = None,
) -> Performance:
    """
    valuation.value_series ciktisi -> Performance.

    values: [cash, position_value, total_value, external_flow] kolonlari.
    benchmark_returns verilirse beta/alpha da hesaplanir.
    """
    r = daily_returns(values["total_value"], values["external_flow"])
    beta = alpha = float("nan")
    if benchmark_returns is not None:
        beta, alpha = beta_alpha(r, benchmark_returns)
    return Performance(
        label=label,
        n_days=len(r),
        total_return=twr(r),
        ann_return=annualized_return(r),
        ann_vol=annualized_vol(r),
        sharpe=sharpe(r),
        max_drawdown=max_drawdown(r),
        beta=beta,
        alpha=alpha,
    )
