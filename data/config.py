"""Data layer configuration."""
from pathlib import Path

# ---- Paths -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
RAW_DIR = CACHE_DIR / "raw"          # ham OHLCV, parquet
META_DIR = CACHE_DIR / "meta"        # ticker metadata

for _d in (RAW_DIR, META_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---- Market ------------------------------------------------------------
EXCHANGE = "NASDAQ"
MARKET_TZ = "America/New_York"
DEFAULT_START = "2015-01-01"

# ---- Data --------------------------------------------------------------
OHLCV_COLS = ["open", "high", "low", "close", "adj_close", "volume"]

# Cache'i kaç saat sonra bayat sayalım (gün içi tekrar indirmeyi önler)
CACHE_TTL_HOURS = 12

# Bir ticker'ın kullanılabilir sayılması için gereken minimum bar sayısı
MIN_BARS = 250
