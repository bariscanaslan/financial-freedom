"""
Istisna -> temiz HTTP. Ic detay (stack trace, dosya yolu, model ic yapisi)
CLIENT'A DONMEZ. Tam detay sunucu log'unda kalir.

Bu dis yuzeyin ilk kurali: hata mesaji bir bilgi sizintisi kanalidir.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("api")


class ApiError(Exception):
    """Kontrollu API hatasi. message client'a gider; code makine-okunur."""
    status_code = 400
    code = "error"

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class BadRequest(ApiError):
    status_code = 400
    code = "bad_request"


def _payload(message: str, code: str) -> dict:
    return {"detail": message, "code": code}


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):  # noqa: ANN202
        log.warning("api hatasi %s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status_code, content=_payload(exc.message, exc.code))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):  # noqa: ANN202
        # Beklenmeyen istisna: tam detay LOG'a, client'a GENERIC mesaj.
        log.exception("beklenmeyen hata: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_payload("internal server error", "internal"),
        )
