"""The host's own signing page for the native provider (kept minimal): the panel from bond_esign, nothing else.

`GET|POST /estimates/{id}/sign?sign=1&t=<token>` and the panel's assets under `/esign/static/`. The token is the
one `NativeProvider.recipient_view_url` put in the link.
"""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs, urlencode

import bond_esign as be
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .deps import clock_now
from .esign_models import CONSENT, TABLES, EsignEnvelope
from .esign_native import NativeProvider
from .esign_seam import envelope_status
from .wire import legacy_envelope

router = APIRouter()
STATIC = "/esign/static"
MAX_FORM_BYTES = 400_000  # a drawn signature is capped at 200 KB, then base64 and the form fields
#: Messages for the codes a post can fail with; a fixed table, so the query string is never echoed.
MESSAGES = {
    "not_open": "This document can no longer be signed.",
    "expired": "This signing request has expired. Please ask for a new one.",
    "consent_required": "Please tick the box to agree to sign electronically.",
    "consent_stale": "The agreement text changed. Please reload the page and read it again.",
    "code_required": "Please enter the code we emailed you before signing.",
    "signature_required": "Please type your name or draw your signature to sign.",
    "signature_invalid": "The signature could not be read. Please try again.",
    "typed_not_allowed": "Typed signatures are not accepted for this document.",
    "drawn_not_allowed": "Drawn signatures are not accepted for this document.",
    "name_not_renderable": "That name has characters that cannot be used. Please retype it.",
    "document_mismatch": "The document changed after this signing request was made.",
}


def _page(title: str, body: str) -> HTMLResponse:
    head = f"<title>{escape(title)}</title>\n{be.asset_tags(STATIC)}"
    return HTMLResponse(f"<!doctype html><html><head><meta charset=\"utf-8\">{head}</head><body>"
                        f"<h1>{escape(title)}</h1>{body}</body></html>", headers={"Cache-Control": "no-store"})


def _signer(request: Request, session, estimate_id: str):
    token = request.query_params.get("t", "")
    signer = be.find_signer_by_token(session, TABLES, token, now=clock_now(request))
    owner = None if signer is None else session.get(TABLES.request, signer.request_id)
    if owner is None or owner.subject_id != estimate_id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "This link does not work."})
    return signer, owner


def _ctx(request: Request) -> be.RequestContext:
    return be.RequestContext(ip=request.client.host if request.client else None,
                             user_agent=request.headers.get("user-agent"))


def _action(estimate_id: str, request: Request) -> str:
    """The form's own URL, built from the path and the token only (nothing from the query is copied)."""
    return f"/estimates/{estimate_id}/sign?{urlencode({'sign': 1, 't': request.query_params.get('t', '')})}"


def _show(request: Request, estimate_id: str, session, signer, owner, error: str | None, *, ctx=True):
    view = be.signing_view(session, TABLES, signer, ctx=_ctx(request) if ctx else None, now=clock_now(request))
    session.commit()
    panel = be.render_panel(view, action_url=_action(estimate_id, request), error=MESSAGES.get(error or ""))
    return _page(owner.title, panel)


@router.get("/estimates/{estimate_id}/sign")
def sign_page(estimate_id: str, request: Request, error: str | None = None):
    with request.app.state.session_factory() as session:
        signer, owner = _signer(request, session, estimate_id)
        return _show(request, estimate_id, session, signer, owner, error)


async def _form(request: Request) -> dict[str, str]:
    if not (request.headers.get("content-type") or "").startswith("application/x-www-form-urlencoded"):
        raise HTTPException(status_code=415, detail={"code": "unsupported_media_type", "message": "Send a form."})
    raw = b""
    async for chunk in request.stream():  # stop reading once the cap is passed
        raw += chunk
        if len(raw) > MAX_FORM_BYTES:
            raise HTTPException(status_code=413, detail={"code": "too_large", "message": "That form is too large."})
    try:
        fields = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True, max_num_fields=20)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "invalid_form", "message": "Unreadable form."}) from None
    return {k: v[0] for k, v in fields.items()}


@router.post("/estimates/{estimate_id}/sign")
async def sign_post(estimate_id: str, request: Request):
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_FORM_BYTES:
        raise HTTPException(status_code=413, detail={"code": "too_large", "message": "That form is too large."})
    form = await _form(request)
    store = request.app.state.esign_store
    with request.app.state.session_factory() as session:
        signer, owner = _signer(request, session, estimate_id)
        try:
            sub = be.parse_submission(form, max_signature_bytes=be.policy_of(owner).max_signature_bytes)
            be.sign(session, TABLES, signer, pdf=store.get(f"esign/{owner.id}/original.pdf"),
                    consent_version=sub.consent_version, consent_accepted=sub.consent_accepted,
                    typed_name=sub.typed_name, drawn_png=sub.drawn_png, ctx=_ctx(request), now=clock_now(request))
        except be.EsignError as exc:
            session.rollback()
            signer, owner = _signer(request, session, estimate_id)
            return _show(request, estimate_id, session, signer, owner, exc.code, ctx=False)
        session.commit()
    return RedirectResponse(_action(estimate_id, request), status_code=303)


@router.get("/estimates/{estimate_id}/envelopes")
def envelopes(estimate_id: str, request: Request):
    """The estimate's envelopes in the app's wire shape, the same keys whichever provider made each one."""
    now = clock_now(request)
    with request.app.state.session_factory() as session:
        native = NativeProvider(session, TABLES, CONSENT, lambda: now, request.app.state.esign_store)
        rows = session.query(EsignEnvelope).filter_by(estimate_id=estimate_id).order_by(EsignEnvelope.id).all()
        for row in rows:
            if row.provider == "native":  # the vendor's own rows are shown as stored
                envelope_status(session, {"native": native}, row, now=now)
        return [legacy_envelope(row) for row in rows]


@router.get(STATIC + "/{name}")
def asset(name: str):
    if name not in be.asset_names():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such file."})
    return FileResponse(be.asset_path(name))
