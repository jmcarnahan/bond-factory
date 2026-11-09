"""``GET /d/{token}``: the recipient-facing download of a shared document.

The only unauthenticated route that serves stored bytes, so the rules are narrow: no auth and no prompt, one byte-identical
410 for every failure (unknown, revoked, expired, used up, or the file is gone), a download counted only after the grant is
claimed, and a 503 text answer for storage trouble.
"""

import logging
from collections.abc import Callable, Collection
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from . import grants
from .grants import DocumentLike
from .service import StorageService, attachment_disposition

LOGGER = logging.getLogger(__name__)

GONE_BODY = (
    '<!doctype html><html><head><meta charset="utf-8"><title>Link expired</title></head><body>'
    "<h1>This link is no longer available</h1>"
    "<p>Links expire after a while. Ask the person who sent it to share the file again.</p></body></html>"
)
NO_STORE = {"Cache-Control": "no-store, max-age=0", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow"}
MAX_IP_TEXT = 45
_INLINE_TYPES =frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"})


def gone() -> Response:
    """The ONE failure answer, byte-identical for every reason."""
    return Response(GONE_BODY, status_code=410, media_type="text/html; charset=utf-8", headers=dict(NO_STORE))


def client_ip(request: Request) -> str:
    """The LAST hop of ``X-Forwarded-For`` (the one the nearest proxy appended; everything before it is client-controlled),
    truncated to 45 characters (the longest IPv6 text), else the socket peer."""
    forwarded = (request.headers.get("x-forwarded-for", "") or "").strip()
    if forwarded:
        hop = forwarded.split(",")[-1].strip()
        if hop:
            return hop[:MAX_IP_TEXT]
    direct = (request.client.host if request.client else "") or ""
    return direct[:MAX_IP_TEXT]


def _disposition(document: DocumentLike, attachment_kinds: Collection[str]) -> str:
    base = (document.content_type or "").split(";", 1)[0].strip().lower()
    if document.kind in attachment_kinds or base not in _INLINE_TYPES:
        return attachment_disposition(document.filename)
    return attachment_disposition(document.filename).replace("attachment;", "inline;", 1)


def make_download_router(*, storage: StorageService, grant_model: Any,
                         document_loader: Callable[[Session, str], DocumentLike | None],
                         session_factory: Callable[[], Session],
                         rate_limit: Callable[[str, str], bool] | None = None,
                         attachment_kinds: Collection[str] = (),
                         after_download: Callable[[Session, DocumentLike], None] | None = None) -> APIRouter:
    """The router with ``GET /d/{token}``.

    ``rate_limit(token_key, ip)`` returns False to refuse; ``token_key`` is the HASHED token, so nothing raw reaches a
    limiter or a log. A refusal answers 429. Documents open inline only when their content type is a picture or PDF and
    their ``kind`` is not in ``attachment_kinds``; everything else downloads. ``after_download(session, document)`` runs
    once the bytes are in hand, before the commit (for example to discard a one-time export).
    """
    router = APIRouter(tags=["downloads"])

    @router.get("/d/{token}", include_in_schema=False)
    def download_by_token(request: Request, token: str) -> Response:
        ip = client_ip(request)
        if rate_limit is not None and not rate_limit(grants.hash_token(token), ip):
            return Response('{"detail": {"code": "rate_limited", "message": "Too many requests"}}', status_code=429,
                            media_type="application/json", headers={**NO_STORE, "Retry-After": "60"})
        session = session_factory()
        try:
            try:
                grant, document = grants.resolve(session, token, grant_model=grant_model, document_loader=document_loader)
            except grants.GrantUnavailable:
                return gone()
            # Fetch BEFORE claiming: a missing object or a transient storage fault must not burn a download.
            try:
                content = storage.download_bytes(document.storage_key)
            except FileNotFoundError:
                LOGGER.warning("Shared document is missing from storage: %s", document.storage_key)
                return gone()
            except Exception as exc:  # noqa: BLE001 - any storage fault is a retryable 503, never a 500 with a trace
                LOGGER.error("Storage unavailable for %s: %s", document.storage_key, exc)
                return Response("Temporarily unavailable. Please try again shortly.", status_code=503,
                                media_type="text/plain; charset=utf-8", headers=dict(NO_STORE))
            if not grants.claim(session, grant, ip):
                return gone()  # another request used the last download between resolve and here
            if after_download is not None:
                after_download(session, document)
            session.commit()
            media_type = document.content_type or "application/octet-stream"
            return Response(content, media_type=media_type,
                            headers={**NO_STORE, "Content-Disposition": _disposition(document, attachment_kinds)})
        finally:
            session.close()

    return router
