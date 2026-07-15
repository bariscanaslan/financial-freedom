"""
Portfolyo katmani konfigurasyonu.

Fee/slippage varsayilanlari K3 geregi SIFIR DEGILDIR: simulasyona islem
maliyeti eklenmezse sonuc sistematik olarak iyimser cikar ve kullaniciyi
yaniltir. Varsayilanlar konfigure edilebilir ama makul bir tabandan baslar.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Event log kaliciligi. Dizin import aninda DEGIL, ilk save'de olusturulur
# (bkz. store.EventStore.save) -- test/import yan etkisi birakmasin.
PORTFOLIO_DIR = PROJECT_ROOT / "portfolio_data"
EVENT_LOG_DIR = PORTFOLIO_DIR / "events"

# ---- Para birimi ve benchmark -----------------------------------------
BASE_CURRENCY = "USD"
BENCHMARK_TICKER = "SPY"   # K4: getiri tek basina anlamsiz, benchmark zorunlu

# ---- Islem maliyeti (K3) ----------------------------------------------
# Slippage: fill fiyati BUY'da yukari, SELL'de asagi kayar (bps = 1/10000).
DEFAULT_SLIPPAGE_BPS = 5.0
# Komisyon: notional uzerinden bps + islem basi sabit.
DEFAULT_COMMISSION_BPS = 1.0
DEFAULT_COMMISSION_FLAT = 0.0

# ---- Degerleme / metrik -----------------------------------------------
PRICE_COL = "adj_close"        # K6: split+temettu duzeltilmis; getiri tutarli
TRADING_DAYS_PER_YEAR = 252    # yillik olcekleme (vol, Sharpe, ann return)
RISK_FREE_RATE = 0.0           # basit Sharpe icin gunluk risksiz getiri = 0
