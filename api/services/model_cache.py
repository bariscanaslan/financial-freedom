"""
Model cache: registry uzerine lazy + cache'li yukleme.

GUIDE §5: model bir kez yuklenir, request basina YENIDEN YUKLENMEZ. Ard arda
model yukleme torch 2.13+xpu'da kaynak sizdirir; sunucuda bu olumcul. Ayrica
her request'te diskten okuma gereksiz I/O'dur.

Dosya yolu DISARIDAN GELMEZ: ticker verilir, registry'de en yeni model cozulur.
"""
from __future__ import annotations

from pathlib import Path

from model import registry

from api.errors import NotFound


class ModelCache:
    def __init__(self, models_dir: str | Path, device: str | None = None):
        self._dir = Path(models_dir)
        self._device = device
        self._models: dict[str, object] = {}   # cozulmus yol -> TrainedModel

    # -- ticker -> en yeni model dizini --
    def resolve_path(self, ticker: str) -> Path:
        ticker = ticker.upper()
        rows = [m for m in registry.list_models(self._dir) if m.get("ticker") == ticker]
        if not rows:
            raise NotFound(f"'{ticker}' icin kayitli model yok")
        # list_models yeniden eskiye sirali -> ilki en yeni
        return Path(rows[0]["path"])

    def get(self, ticker: str):
        """TrainedModel'i getirir (yalnizca ilk cagride diskten yuklenir)."""
        path = self.resolve_path(ticker)
        key = str(path)
        if key not in self._models:
            self._models[key] = registry.load(path, device=self._device)
        return self._models[key]

    def meta(self, ticker: str) -> dict:
        return registry.load_meta(self.resolve_path(ticker))

    # -- listeleme (A2: skill_score, coverage) --
    def summaries(self) -> list[dict]:
        out = []
        for m in registry.list_models(self._dir):
            try:
                meta = registry.load_meta(m["path"])
            except Exception:  # noqa: BLE001 -- bozuk meta listeyi patlatmasin
                continue
            tm = meta.get("test_metrics") or {}
            out.append({
                "ticker": meta.get("ticker"),
                "saved_at": meta.get("saved_at"),
                "skill_score": tm.get("skill_score"),
                "coverage": tm.get("coverage"),
                "nominal_cov": tm.get("nominal_cov"),
            })
        return out

    def loaded_tickers(self) -> list[str]:
        return sorted(self._models.keys())
