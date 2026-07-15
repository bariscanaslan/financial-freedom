"""
API ayarlari (pydantic-settings). Ortam degiskeni onek: SPP_API_.

Yollar burada model.config'ten DEGIL, dogrudan PROJECT_ROOT'tan turer -- boylece
api.config import etmek torch'u yuklemez (model.config torch'a bagimlidir).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPP_API_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8089

    # Kayitli modellerin kok dizini (registry). Request'ten ASLA dosya yolu
    # alinmaz; ticker -> bu dizinde cozulur.
    models_dir: Path = PROJECT_ROOT / "models"

    # Cihaz: None -> model/device.py calisma aninda cozer. Sunucuda "cpu"
    # zorlamak icin SPP_API_DEVICE=cpu (guide §5 xpu kaynak sizintisi).
    device: str | None = None

    # SQLite veritabani: portfolyo kaydi + event log + kullanilan ticker'lar.
    db_path: Path = PROJECT_ROOT / "portfolio_data" / "app.db"

    # Geçici cache, job state ve dağıtık kilit. Bağlantı kurulamazsa mevcut
    # bellek/Parquet fallback'leri çalışmaya devam eder. Kapatmak için boş bırakın.
    redis_url: str | None = "redis://127.0.0.1:6389/0"
    redis_prefix: str = "financial-freedom"
    redis_job_ttl_seconds: int = 86_400
    redis_market_ttl_seconds: int = 720
    notification_interval_seconds: int = 900

    # --- sinirlar (yeni dis yuzey) ---
    max_events_per_request: int = 100
    max_value_days: int = 3650
    max_quantity: float = 1e9
    max_cash: float = 1e12
    max_price: float = 1e7

    price_col: str = "adj_close"
    benchmark_ticker: str = "SPY"

    # Tarayici UI'inin (Next dev) API'yi cagirabilmesi icin CORS. Yalnizca
    # bilinen kaynaklara izin verilir (wildcard degil). Uretimde env ile daralt.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
