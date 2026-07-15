"""Portföy taslağı üretimini izlenebilir arka plan işi olarak çalıştırır."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from api.errors import BadRequest, NotFound


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PortfolioDraftManager:
    def __init__(self, cache, prices, db, redis_backend=None):
        self._cache, self._prices, self._db = cache, prices, db
        self._redis = redis_backend
        self._lock_tokens: dict[str, str] = {}
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="portfolio-draft")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def start(self, body) -> dict:
        with self._lock:
            if any(job["status"] in {"queued", "running"} for job in self._jobs.values()):
                raise BadRequest("Başka bir portföy taslağı hazırlanıyor.")
            token = self._redis.acquire("portfolio-draft", 30 * 60) if self._redis else "memory"
            if token is None:
                raise BadRequest("Başka bir instance üzerinde portföy taslağı hazırlanıyor.")
            job_id = uuid.uuid4().hex
            self._jobs[job_id] = {"id": job_id, "status": "queued", "stage": "Taslak kuyruğa alındı.",
                "progress": 0.0, "processed_models": 0, "total_models": 0,
                "created_at": _now(), "finished_at": None, "draft": None, "error": None}
            self._jobs[job_id]["events"] = []
            self._lock_tokens[job_id] = token
        self._persist(job_id)
        self._executor.submit(self._run, job_id, body)
        return self.get(job_id)

    def get(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                cached = self._redis.get_json(f"job:portfolio-draft:{job_id}") if self._redis else None
                if cached is None:
                    raise NotFound("Portföy taslağı işi bulunamadı.")
                return cached
            return dict(self._jobs[job_id])

    def _update(self, job_id: str, **values) -> None:
        with self._lock:
            self._jobs[job_id].update(values)
        self._persist(job_id)

    def _persist(self, job_id: str) -> None:
        if not self._redis:
            return
        with self._lock:
            job = dict(self._jobs[job_id])
            job["events"] = list(job["events"])
        self._redis.set_json(f"job:portfolio-draft:{job_id}", job)
        self._redis.publish(f"progress:portfolio-draft:{job_id}", job)

    def _run(self, job_id: str, body) -> None:
        from api.routers.portfolio_drafts import _generate
        self._update(job_id, status="running", stage="Eğitilmiş modeller listeleniyor.", progress=0.05)
        try:
            def progress(processed: int, total: int, stage: str) -> None:
                with self._lock:
                    job = self._jobs[job_id]
                    job.update(processed_models=processed, total_models=total,
                        progress=0.1 + (0.75 * processed / max(total, 1)), stage=stage)
                    job["events"] = [*job["events"], stage][-50:]
                self._persist(job_id)
            payload = _generate(body, self._cache, self._prices, self._db, progress)
            self._update(job_id, stage="Taslak kaydediliyor.", progress=0.9)
            draft = self._db.save_portfolio_draft(payload)
            self._update(job_id, status="completed", stage="Portföy taslağı hazır.",
                progress=1.0, draft=draft, finished_at=_now())
        except Exception as exc:  # kontrollü hata UI'a kısa mesajla aktarılır
            self._update(job_id, status="failed", stage="Taslak oluşturulamadı.",
                error=str(exc), finished_at=_now())
        finally:
            token = self._lock_tokens.pop(job_id, None)
            if self._redis:
                self._redis.release("portfolio-draft", token)
