"""
Veri kalite kontrolleri.

Model egitmeden ONCE calistir. Sessiz bozuk veri, sessiz bozuk model demektir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Report:
    ticker: str
    n_bars: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        status = "OK " if self.ok else "FAIL"
        lines = [f"[{status}] {self.ticker}  {self.n_bars} bar  "
                 f"{self.start.date() if self.start is not None else '?'} "
                 f"-> {self.end.date() if self.end is not None else '?'}"]
        lines += [f"   ERR  {e}" for e in self.errors]
        lines += [f"   WARN {w}" for w in self.warnings]
        return "\n".join(lines)


def validate(df: pd.DataFrame, ticker: str = "?") -> Report:
    rep = Report(
        ticker=ticker,
        n_bars=len(df),
        start=df.index.min() if len(df) else None,
        end=df.index.max() if len(df) else None,
    )

    if df.empty:
        rep.errors.append("veri bos")
        return rep

    # --- Yapisal ---
    if not df.index.is_monotonic_increasing:
        rep.errors.append("index sirali degil")
    if df.index.has_duplicates:
        rep.errors.append(f"{df.index.duplicated().sum()} tekrarli tarih")

    # --- NaN ---
    nans = df.isna().sum()
    for col, n in nans[nans > 0].items():
        pct = 100 * n / len(df)
        (rep.errors if pct > 5 else rep.warnings).append(
            f"{col}: {n} NaN (%{pct:.1f})"
        )

    # --- Deger mantigi ---
    price_cols = ["open", "high", "low", "close", "adj_close"]
    for c in price_cols:
        if (df[c] <= 0).any():
            rep.errors.append(f"{c}: pozitif olmayan fiyat var")

    if (df["high"] < df["low"]).any():
        rep.errors.append("high < low olan bar var")
    if (df["high"] < df[["open", "close"]].max(axis=1)).any():
        rep.warnings.append("high, open/close'un altinda kalan bar var")
    if (df["low"] > df[["open", "close"]].min(axis=1)).any():
        rep.warnings.append("low, open/close'un ustunde kalan bar var")

    if (df["volume"] < 0).any():
        rep.errors.append("negatif hacim")
    zero_vol = (df["volume"] == 0).sum()
    if zero_vol:
        rep.warnings.append(f"{zero_vol} gun sifir hacim (halt/likidite yok?)")

    # --- Ucuk hareketler (split hatasi tespiti) ---
    # adj_close kullaniyoruz: gercek split zaten duzeltilmis olmali.
    # Yine de %50+ gunluk hareket varsa veri hatasi suphesi vardir.
    ret = df["adj_close"].pct_change()
    extreme = ret[ret.abs() > 0.5]
    if len(extreme):
        rep.warnings.append(
            f"{len(extreme)} gun |getiri| > %50 -> duzeltilmemis split olabilir: "
            f"{[str(d.date()) for d in extreme.index[:3]]}"
        )

    # --- Donuk seri ---
    flat = (ret == 0).sum()
    if flat > 0.2 * len(df):
        rep.warnings.append(f"barlarin %{100*flat/len(df):.0f}'i degisimsiz (likidite dusuk)")

    # --- Bosluklar ---
    gaps = df.index.to_series().diff().dt.days
    long_gaps = gaps[gaps > 7]
    if len(long_gaps):
        rep.warnings.append(f"{len(long_gaps)} adet 7+ gunluk veri boslugu")

    return rep


def validate_many(frames: dict[str, pd.DataFrame]) -> dict[str, Report]:
    return {t: validate(df, t) for t, df in frames.items()}
