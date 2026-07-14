"""
Model kayit defteri: kaydet / yukle.

KRITIK KURAL: SCALER MODELLE BIRLIKTE KAYDEDILIR.

Notebook'ta scaler bellekte yasiyordu. Bir API surecinde model .pt'den
yuklenip scaler yeniden fit edilirse (ya da hic edilmezse) ag dogru,
olcek yanlis olur. Cikti PATLAMAZ -- sadece sessizce yanlis sayilar uretir.
Sessiz yanlis, gurultulu hatadan cok daha tehlikelidir.

Ayrica denetlenebilirlik icin kaydedilenler: ticker, seq_len, horizon,
quantiles, train tarih araligi (scaler.fitted_on icinde), git commit,
test metrikleri, torch surumu, kayit zamani.

Disk duzeni:
    models/AAPL_20260714_101500/
        model.pt     -- sadece state_dict (pickle'lanmis sinif degil)
        meta.json    -- geri kalan HER SEY, insan okuyabilir
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import torch

from data.dataset import Scaler

from .config import MODEL_DIR, ModelConfig
from .nets import QuantileLSTM
from .train import TrainedModel

SCHEMA_VERSION = 1


# --------------------------------------------------------------------- git
def _git_commit() -> str | None:
    """Repo yoksa/git yoksa sessizce None. Kayit bu yuzden basarisiz olmamali."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True, timeout=5, check=False,
        )
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


# -------------------------------------------------------------------- save
def save(
    model: TrainedModel,
    *,
    ticker: str,
    metrics: dict | None = None,
    train_range: tuple[str, str] | None = None,
    path: str | Path | None = None,
    tag: str | None = None,
) -> Path:
    """
    Modeli + scaler'i + cfg'yi + metrikleri tek dizine yazar.

    Args:
        metrics: test metrikleri (evaluate.py ciktisi). Kaydedilir ki
                 uretimdeki bir modelin ne kadar iyi oldugunu sonradan
                 sorabilelim -- yeniden degerlendirmeden.
        path:    verilmezse models/<TICKER>_<zaman> uretilir.

    Doner: yazilan dizin.
    """
    if path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{tag}" if tag else ""
        path = MODEL_DIR / f"{ticker.upper()}_{stamp}{suffix}"
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # 1) agirliklar -- state_dict, tum nesne degil.
    #    Pickle'lanmis nn.Module, sinif imzasi degisince yuklenmez olur.
    torch.save(model.net.state_dict(), path / "model.pt")

    # 2) geri kalan her sey -- okunabilir, denetlenebilir
    meta = {
        "schema_version": SCHEMA_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "ticker": ticker.upper(),

        # --- MODELIN CALISMASI ICIN ZORUNLU ---
        "scaler": model.scaler.to_dict(),   # <-- OLMAZSA OLMAZ (hedef/0. kanal)
        "feature_scalers": (
            [s.to_dict() for s in model.feature_scalers]
            if model.feature_scalers else None
        ),
        "config": model.cfg.to_dict(),

        # --- veri sekli (predict.py bunlara uyacak) ---
        "seq_len": model.cfg.seq_len,
        "horizon": model.cfg.horizon,
        "quantiles": list(model.cfg.quantiles),
        "input_dim": model.cfg.input_dim,
        "feature_names": list(model.cfg.feature_names),

        # --- denetlenebilirlik ---
        "train_range": list(train_range) if train_range else None,
        "scaler_fitted_on": model.scaler.fitted_on,
        "git_commit": _git_commit(),
        "torch_version": torch.__version__,
        "best_epoch": model.best_epoch,
        "best_val_loss": model.best_val_loss,
        "test_metrics": metrics,
    }
    (path / "meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    return path


# -------------------------------------------------------------------- load
def load(path: str | Path, device: str | None = None) -> TrainedModel:
    """
    Dizinden TrainedModel'i AYNEN geri getirir: ag + scaler + cfg birlikte.

    Scaler burada meta.json'dan gelir -- yeniden fit EDILMEZ. Yeniden fit
    etmek, uretim verisine fit etmek demektir; bu da tam olarak data/
    katmaninda engellenen leakage'in arka kapidan geri girmesidir.
    """
    path = Path(path)
    meta_path = path / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json yok: {path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    if meta.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"uyumsuz schema_version: {meta.get('schema_version')} "
            f"(beklenen {SCHEMA_VERSION})"
        )

    cfg = ModelConfig.from_dict(meta["config"])
    if device is not None:
        cfg.device = device

    scaler = Scaler.from_dict(meta["scaler"])

    net = QuantileLSTM(
        quantiles=cfg.quantiles,
        input_dim=cfg.input_dim,
        hidden_dim=cfg.hidden_dim,
        num_layers=cfg.num_layers,
        horizon=cfg.horizon,
        dropout=cfg.dropout,
    )
    state = torch.load(path / "model.pt", map_location="cpu", weights_only=True)
    net.load_state_dict(state)
    net.eval()

    fs = meta.get("feature_scalers")
    feature_scalers = [Scaler.from_dict(d) for d in fs] if fs else None

    model = TrainedModel(
        net=net,
        scaler=scaler,
        cfg=cfg,
        feature_scalers=feature_scalers,
        best_epoch=meta.get("best_epoch", -1),
        best_val_loss=meta.get("best_val_loss", float("inf")),
    )
    return model


def load_meta(path: str | Path) -> dict:
    """Agirliklari yuklemeden sadece meta'ya bakmak icin (listeleme, denetim)."""
    return json.loads((Path(path) / "meta.json").read_text(encoding="utf-8"))


def list_models(root: str | Path = MODEL_DIR) -> list[dict]:
    """Kayitli modelleri meta ozetiyle listeler (yeniden eskiye)."""
    root = Path(root)
    out = []
    for d in sorted(root.glob("*/"), reverse=True):
        if (d / "meta.json").exists():
            m = load_meta(d)
            out.append({
                "path": str(d),
                "ticker": m.get("ticker"),
                "saved_at": m.get("saved_at"),
                "skill_score": (m.get("test_metrics") or {}).get("skill_score"),
            })
    return out
