"""``GET /d/{token}``: the recipient-facing download of a shared document.

The only unauthenticated route that serves stored bytes, so the rules are narrow: no auth and no prompt, one byte-identical
410 for every failure (unknown, revoked, expired, used up, or the file is gone), a download counted only after the grant is
claimed, and a 503 text answer for storage trouble.
"""

import logging
from collections.abc import Callable, Collection
from typing import Any, Literal

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


def gone(body: str = GONE_BODY) -> Response:
    """The ONE failure answer, byte-identical for every reason."""
    return Response(body, status_code=410, media_type="text/html; charset=utf-8", headers=dict(NO_STORE))


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


_default_client_ip = client_ip


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
                         after_download: Callable[[Session, DocumentLike], None] | None = None,
                         delivery: Literal["stream", "redirect"] = "stream", presign_seconds: int = 60,
                         on_claim: Callable[[Session, Any, str], None] | None = None,
                         gone_body: str | Callable[[Request], str] = GONE_BODY,
                         enabled: Callable[[], bool] | None = None,
                         client_ip: Callable[[Request], str] | None = None,
                         enforce_cap: bool = True) -> APIRouter:
    """The router with ``GET /d/{token}``.

    ``rate_limit(token_key, ip)`` returns False to refuse; ``token_key`` is the HASHED token, so nothing raw reaches a
    limiter or a log. A refusal answers 429. Documents open inline only when their content type is a picture or PDF and
    their ``kind`` is not in ``attachment_kinds``; everything else downloads. ``after_download(session, document)`` runs
    once the bytes are in hand, before the commit (for example to discard a one-time export).

    ``delivery="redirect"`` answers 302 to a signed URL valid for ``presign_seconds`` instead of sending the bytes. It
    checks the object exists, signs the URL, claims the download, then redirects (a signing fault answers 503 and
    leaves the download unclaimed); a backend without presigned URLs (the local one)
    streams as before. The bytes never pass through this process, so ``after_download`` cannot run: the two together
    raise ``ValueError``. ``on_claim(session, grant, ip)`` runs in the same transaction as the claim (its writes and
    the claim commit together; if it raises, both roll back and the request fails). ``gone_body`` is the 410 HTML (or
    a callable taking the request, which must not vary by failure reason). ``enabled()`` is checked per request; false
    answers 404 (with the no-store headers). ``client_ip(request)`` replaces the default proxy-aware lookup. ``enforce_cap=False`` ignores
    ``max_downloads``.
    """
    if delivery not in ("stream", "redirect"):
        raise ValueError("delivery must be 'stream' or 'redirect'")
    if delivery == "redirect" and after_download is not None:
        raise ValueError("after_download needs the bytes in this process; it cannot be used with delivery='redirect'")
    router = APIRouter(tags=["downloads"])
    ip_of = client_ip or _default_client_ip

    def refuse_gone(request: Request) -> Response:
        return gone(gone_body(request) if callable(gone_body) else gone_body)

    def storage_trouble() -> Response:
        return Response("Temporarily unavailable. Please try again shortly.", status_code=503,
                        media_type="text/plain; charset=utf-8", headers=dict(NO_STORE))

    def settle(session: Session, grant: Any, ip: str) -> bool:
        """Claim the download. With ``on_claim`` the hook runs before the single commit."""
        if on_claim is None:
            return grants.claim(session, grant, ip, enforce_cap=enforce_cap)
        try:
            if not grants.claim(session, grant, ip, enforce_cap=enforce_cap, commit=False):
                session.rollback()
                return False
            on_claim(session, grant, ip)
            session.commit()
        except BaseException:
            session.rollback()
            raise
        return True

    @router.get("/d/{token}", include_in_schema=False)
    def download_by_token(request: Request, token: str) -> Response:
        if enabled is not None and not enabled():
            return Response('{"detail":"Not Found"}', status_code=404, media_type="application/json",
                            headers=dict(NO_STORE))
        ip = (ip_of(request) or "")[:MAX_IP_TEXT]  # a custom client_ip is cut once, before the limiter and on_claim
        if rate_limit is not None and not rate_limit(grants.hash_token(token), ip):
            return Response('{"detail": {"code": "rate_limited", "message": "Too many requests"}}', status_code=429,
                            media_type="application/json", headers={**NO_STORE, "Retry-After": "60"})
        session = session_factory()
        try:
            try:
                grant, document = grants.resolve(session, token, grant_model=grant_model, document_loader=document_loader,
                                                 enforce_cap=enforce_cap)
            except grants.GrantUnavailable:
                return refuse_gone(request)
            redirect = delivery == "redirect" and storage.supports_presigned
            media_type = document.content_type or "application/octet-stream"
            disposition = _disposition(document, attachment_kinds)
            # Fetch (or check) BEFORE claiming: a missing object or a transient storage fault must not burn a download.
            content = b""
            url = ""
            try:
                if redirect:
                    if not storage.exists(document.storage_key):
                        raise FileNotFoundError(document.storage_key)
                    # Sign BEFORE claiming too: a signing fault must not burn a single-use download.
                    # The signed URL cannot say "inline", so it forces a download name only when the page would download.
                    forced = disposition.startswith("attachment;")
                    url = storage.get_url(document.storage_key, presign_seconds,
                                          download_filename=document.filename if forced else None,
                                          content_type=document.content_type)
                else:
                    content = storage.download_bytes(document.storage_key)
            except FileNotFoundError:
                LOGGER.warning("Shared document is missing from storage: %s", document.storage_key)
                return refuse_gone(request)
            except Exception as exc:  # noqa: BLE001 - any storage fault is a retryable 503, never a 500 with a trace
                LOGGER.error("Storage unavailable for %s: %s", document.storage_key, exc)
                return storage_trouble()
            if not settle(session, grant, ip):
                return refuse_gone(request)  # another request used the last download between resolve and here
            if redirect:
                return Response(status_code=302, headers={**NO_STORE, "Location": url})
            if after_download is not None:
                after_download(session, document)
            session.commit()
            return Response(content, media_type=media_type,
                            headers={**NO_STORE, "Content-Disposition": disposition})
        finally:
            session.close()

    return router
