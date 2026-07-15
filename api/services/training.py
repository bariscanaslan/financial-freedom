"""Tek kullanıcılı uygulama için arka plan model eğitim işleri."""
from __future__ import annotations

import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from api.errors import BadRequest, NotFound


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class TrainingManager:
    def __init__(self, models_dir: str | Path, device: str | None, prices, redis_backend=None):
        self._models_dir = Path(models_dir)
        self._device = device
        self._prices = prices
        self._redis = redis_backend
        self._lock_tokens: dict[str, str] = {}
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-training")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def device(self) -> str:
        if self._device:
            return self._device
        from model.device import best_device
        return best_device().spec

    def start(self, ticker: str, horizon: int = 21) -> dict:
        with self._lock:
            if any(j["status"] in {"queued", "preparing", "training", "evaluating"}
                   for j in self._jobs.values()):
                raise BadRequest("Başka bir model eğitimi devam ediyor.")
            token = self._redis.acquire("training", 6 * 60 * 60) if self._redis else "memory"
            if token is None:
                raise BadRequest("Başka bir instance üzerinde model eğitimi devam ediyor.")
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id,
                "ticker": ticker,
                "horizon": horizon,
                "status": "queued",
                "stage": "Eğitim kuyruğa alındı.",
                "device": self.device(),
                "created_at": _now(),
                "started_at": None,
                "finished_at": None,
                "config": {},
                "progress": None,
                "history": [],
                "metrics": None,
                "model_path": None,
                "error": None,
            }
            self._jobs[job_id] = job
            self._lock_tokens[job_id] = token
        self._persist(job_id)
        self._executor.submit(self._run, job_id)
        return self.get(job_id)

    def get(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                cached = self._redis.get_json(f"job:training:{job_id}") if self._redis else None
                if cached is None:
                    raise NotFound("Eğitim işi bulunamadı.")
                return cached
            job = self._jobs[job_id]
            return {**job, "history": [dict(row) for row in job["history"]]}

    def _update(self, job_id: str, **values) -> None:
        with self._lock:
            self._jobs[job_id].update(values)
        self._persist(job_id)

    def _persist(self, job_id: str) -> None:
        if not self._redis:
            return
        with self._lock:
            job = dict(self._jobs[job_id])
            job["history"] = [dict(row) for row in job["history"]]
        self._redis.set_json(f"job:training:{job_id}", job)
        self._redis.publish(f"progress:training:{job_id}", job)

    def _on_progress(self, job_id: str, update: dict) -> None:
        if update["event"] == "started":
            self._update(
                job_id,
                status="training",
                stage="Model eğitiliyor.",
                progress=0.0,
                parameters=update["parameters"],
                train_samples=update["train_samples"],
                val_samples=update["val_samples"],
                test_samples=update["test_samples"],
            )
        elif update["event"] == "epoch":
            row = {k: _clean(v) for k, v in update.items() if k != "event"}
            with self._lock:
                job = self._jobs[job_id]
                job["history"].append(row)
                job["progress"] = update["epoch"] / update["max_epochs"]
                job["stage"] = f"Epoch {update['epoch']} / {update['max_epochs']}"
            self._persist(job_id)
        elif update["event"] == "early_stopping":
            self._update(job_id, stage=f"Erken durdurma: epoch {update['epoch']}")

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        ticker, horizon = job["ticker"], job["horizon"]
        self._update(job_id, status="preparing", stage="Piyasa verisi hazırlanıyor.", started_at=_now())
        try:
            from data.dataset import build_dataset
            from data.validate import validate
            from model.config import ModelConfig
            from model.evaluate import evaluate, evaluate_milestones
            from model.registry import save
            from model.train import train

            frame = self._prices.recent(ticker)
            report = validate(frame, ticker)
            if not report.ok:
                raise ValueError("Piyasa verisi eğitim koşullarını karşılamıyor: " + "; ".join(report.errors))

            cfg = ModelConfig(device=self.device(), horizon=horizon)
            dataset = build_dataset(frame, ticker, seq_len=cfg.seq_len, horizon=cfg.horizon)
            self._update(job_id, config=cfg.to_dict(), stage="Veri seti hazırlandı.")

            trained = train(
                dataset,
                cfg,
                verbose=False,
                progress=lambda event: self._on_progress(job_id, event),
            )
            self._update(job_id, status="evaluating", stage="Test metrikleri hesaplanıyor.")
            scores = evaluate(dataset, trained, verbose=False)
            row = scores.loc[scores["model"] == trained.name].iloc[0].to_dict()
            metrics = {key: _clean(value) for key, value in row.items()}
            metrics["horizon_metrics"] = evaluate_milestones(dataset, trained)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = save(
                trained,
                ticker=ticker,
                metrics=metrics,
                path=self._models_dir / f"{ticker}_{stamp}",
            )
            self._update(
                job_id,
                status="completed",
                stage="Eğitim tamamlandı ve model kaydedildi.",
                progress=1.0,
                metrics=metrics,
                model_path=str(path.relative_to(self._models_dir.parent)),
                best_epoch=trained.best_epoch,
                best_val_loss=_clean(trained.best_val_loss),
                finished_at=_now(),
            )
        except Exception as exc:  # noqa: BLE001
            self._update(
                job_id,
                status="failed",
                stage="Eğitim tamamlanamadı.",
                error=str(exc),
                finished_at=_now(),
            )
        finally:
            token = self._lock_tokens.pop(job_id, None)
            if self._redis:
                self._redis.release("training", token)
