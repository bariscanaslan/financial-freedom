"""Opsiyonel Redis: geçici cache, job state, kilit ve progress yayınları."""
from __future__ import annotations

import json
import logging
import uuid

log = logging.getLogger("api.redis")


class RedisBackend:
    def __init__(self, url: str | None, prefix: str, *, job_ttl: int = 86_400,
                 market_ttl: int = 720):
        self.prefix, self.job_ttl, self.market_ttl = prefix, job_ttl, market_ttl
        self._client = None
        if not url:
            return
        try:
            import redis
            client = redis.Redis.from_url(url, decode_responses=True,
                                          socket_connect_timeout=1, socket_timeout=2)
            client.ping()
            self._client = client
            log.info("Redis geçici state için etkin.")
        except Exception as exc:  # Redis uygulamanın açılmasını engellemez
            log.warning("Redis kullanılamıyor; bellek/Parquet fallback etkin (%s)", exc)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def get_json(self, key: str):
        if self._client is None:
            return None
        try:
            value = self._client.get(self._key(key))
            return json.loads(value) if value else None
        except Exception:
            return None

    def set_json(self, key: str, value, ttl: int | None = None) -> None:
        if self._client is None:
            return
        try:
            self._client.set(self._key(key), json.dumps(value, ensure_ascii=False, default=str),
                             ex=ttl or self.job_ttl)
        except Exception as exc:
            log.warning("Redis yazımı başarısız: %s", exc)

    def publish(self, channel: str, value) -> None:
        if self._client is None:
            return
        try:
            self._client.publish(self._key(channel), json.dumps(value, ensure_ascii=False, default=str))
        except Exception:
            pass

    def acquire(self, name: str, ttl: int) -> str | None:
        if self._client is None:
            return "memory"
        token = uuid.uuid4().hex
        try:
            return token if self._client.set(self._key(f"lock:{name}"), token, nx=True, ex=ttl) else None
        except Exception:
            return "memory"

    def release(self, name: str, token: str | None) -> None:
        if self._client is None or token in {None, "memory"}:
            return
        script = "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
        try:
            self._client.eval(script, 1, self._key(f"lock:{name}"), token)
        except Exception:
            pass
