"""The public signing page of the e-signing demo. The link token in the path is the only credential.

    GET  /esign/sign/{token}               the page: document link, then the library's panel (or why not)
    POST /esign/sign/{token}               the panel's form post (urlencoded); 303 back to the page
    POST /esign/decline/{token}            the panel's decline form (urlencoded); 303 back to the page
    GET  /esign/sign/{token}/original.pdf  the document being signed
    GET  /esign/sign/{token}/signed.pdf    404 until completed; records `downloaded`

The page has no inline script or style and sends a strict Content-Security-Policy, so the panel provably works
under one. A failed post redirects to `?error=<code>`; the page shows a message from a fixed table, never the query.
"""

from __future__ import annotations

import hashlib
import html
from urllib.parse import parse_qs

from bond_esign import (
    EsignError,
    asset_tags,
    decline,
    find_signer_by_token,
    parse_decline,
    parse_submission,
    policy_of,
    record_download,
    render_panel,
    sign,
    signing_view,
)
from bond_service_kit import ApiError
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..db import session_scope
from ..esign_wiring import PDF, TABLES, enqueue_completion, load_original, load_signed, request_context

CSP = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'"
MAX_FORM_BYTES = 400_000  # a drawn signature is capped at 200 KB, then base64 and the form fields
#: The lib's plain messages for the codes a post can fail with: a fixed table, so the query string is never echoed.
MESSAGES = {
    "not_open": "This document can no longer be signed.",
    "expired": "This signing request has expired. Please ask for a new one.",
    "consent_required": "Please tick the box to agree to sign electronically.",
    "consent_stale": "The agreement text changed. Please reload the page and read it again.",
    "code_required": "Please enter the code we emailed you before signing.",
    "signature_required": "Please type your name or draw your signature to sign.",
    "signature_invalid": "The signature could not be read. Please try again.",
    "typed_not_allowed": "Typed signatures are not accepted for this document. Please draw your signature.",
    "drawn_not_allowed": "Drawn signatures are not accepted for this document. Please type your name.",
    "name_not_renderable": "That name has characters that cannot be used. Please retype it.",
    "document_mismatch": "The document changed after this signing request was made.",
}


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    text = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<link rel="icon" href="data:,">'
            f"<title>{html.escape(title)}</title>\n{asset_tags('/esign/static')}</head>"
            f"<body><main><h1>{html.escape(title)}</h1>\n{body}</main></body></html>")
    return HTMLResponse(text, status_code=status, headers={"Content-Security-Policy": CSP, "Cache-Control": "no-store"})


def _not_found() -> HTMLResponse:
    return _page("Link not found", "<p>This signing link was not found. Please ask for a new one.</p>", 404)


def _show(request: Request, token: str, error: str | None) -> HTMLResponse:
    now = request.app.state.clock.utcnow_naive()
    with session_scope(request.app.state.session_factory) as session:
        signer = find_signer_by_token(session, TABLES, token, now=now)
        if signer is None:
            return _not_found()
        row = session.get(TABLES.request, signer.request_id)
        view = signing_view(session, TABLES, signer, ctx=request_context(request), now=now)
        panel = render_panel(view, action_url=f"/esign/sign/{token}", error=MESSAGES.get(error or ""),
                             decline_url=f"/esign/decline/{token}")
        after = ""
        if view.signer_status == "signed":
            if row.status == "completed":
                after = f'<p><a href="/esign/sign/{token}/signed.pdf">Download signed copy</a></p>'
            else:
                after = "<p>Your signed copy is being prepared.</p>"
        link = f'<p><a href="/esign/sign/{token}/original.pdf">View the document (PDF)</a></p>'
        return _page(row.title, f"{link}\n{panel}\n{after}")


def _post(request: Request, token: str, form: dict[str, str]) -> RedirectResponse:
    now = request.app.state.clock.utcnow_naive()
    back = f"/esign/sign/{token}"
    with session_scope(request.app.state.session_factory) as session:
        signer = find_signer_by_token(session, TABLES, token, now=now)
        if signer is None:
            raise ApiError("not_found", "Not found.", status=404)
        row = session.get(TABLES.request, signer.request_id)
        try:
            submission = parse_submission(form, max_signature_bytes=policy_of(row).max_signature_bytes)
            outcome = sign(session, TABLES, signer, pdf=load_original(request.app, row.id),
                           consent_version=submission.consent_version, consent_accepted=submission.consent_accepted,
                           typed_name=submission.typed_name, drawn_png=submission.drawn_png,
                           ctx=request_context(request), now=now)
        except EsignError as exc:  # nothing was written for a refused post (an expiry the check noticed is kept)
            return RedirectResponse(f"{back}?error={exc.code}", status_code=303)
        if outcome.all_signed and not outcome.replay:
            enqueue_completion(session, row.id, now)
    return RedirectResponse(back, status_code=303)


def _decline(request: Request, token: str, form: dict[str, str]) -> RedirectResponse:
    now = request.app.state.clock.utcnow_naive()
    back = f"/esign/sign/{token}"
    with session_scope(request.app.state.session_factory) as session:
        signer = find_signer_by_token(session, TABLES, token, now=now)
        if signer is None:
            raise ApiError("not_found", "Not found.", status=404)
        try:
            decline(session, TABLES, signer, reason=parse_decline(form), ctx=request_context(request), now=now)
        except EsignError as exc:  # refused: nothing was written (an expiry the check noticed is kept)
            return RedirectResponse(f"{back}?error={exc.code}", status_code=303)
    return RedirectResponse(back, status_code=303)


def _pdf(request: Request, token: str, *, signed: bool) -> Response:
    now = request.app.state.clock.utcnow_naive()
    with session_scope(request.app.state.session_factory) as session:
        signer = find_signer_by_token(session, TABLES, token, now=now)
        row = None if signer is None else session.get(TABLES.request, signer.request_id)
        if row is None or (signed and row.status != "completed"):
            raise ApiError("not_found", "Not found.", status=404)
        name = "signed.pdf" if signed else "original.pdf"
        data = load_signed(request.app, row.id) if signed else load_original(request.app, row.id)
        if signed:
            if hashlib.sha256(data).hexdigest() != row.signed_sha256:  # never serve a copy the record does not vouch for
                raise ApiError("not_found", "Not found.", status=404)
            record_download(session, TABLES, row, signer=signer, ctx=request_context(request), now=now)
    return Response(data, media_type=PDF, headers={"Content-Disposition": f'inline; filename="{name}"',
                                                   "Cache-Control": "no-store", "Content-Security-Policy": CSP})


async def _read_form(request: Request) -> dict[str, str]:
    if not (request.headers.get("content-type") or "").startswith("application/x-www-form-urlencoded"):
        raise ApiError("unsupported_media_type", "Send the form as application/x-www-form-urlencoded.", status=415)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_FORM_BYTES:
        raise ApiError("too_large", "That form is too large.", status=413)
    raw = b""
    async for chunk in request.stream():  # a chunked body is cut off as soon as it passes the cap
        raw += chunk
        if len(raw) > MAX_FORM_BYTES:
            raise ApiError("too_large", "That form is too large.", status=413)
    try:
        fields = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True, max_num_fields=20)
    except ValueError:
        raise ApiError("invalid_form", "That form could not be read.", status=400) from None
    return {key: values[0] for key, values in fields.items()}


def register(app: FastAPI) -> None:
    @app.get("/esign/sign/{token}")
    def sign_page(token: str, request: Request, error: str | None = None) -> HTMLResponse:
        return _show(request, token, error)

    @app.post("/esign/sign/{token}")
    async def sign_post(token: str, request: Request) -> RedirectResponse:
        return await run_in_threadpool(_post, request, token, await _read_form(request))

    @app.post("/esign/decline/{token}")
    async def decline_post(token: str, request: Request) -> RedirectResponse:
        return await run_in_threadpool(_decline, request, token, await _read_form(request))

    @app.get("/esign/sign/{token}/original.pdf")
    def original_pdf(token: str, request: Request) -> Response:
        return _pdf(request, token, signed=False)

    @app.get("/esign/sign/{token}/signed.pdf")
    def signed_pdf(token: str, request: Request) -> Response:
        return _pdf(request, token, signed=True)
