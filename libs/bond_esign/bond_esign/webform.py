"""The inline signing panel: an escaped HTML fragment, the asset helpers and the form parser.

No template engine: every interpolated value goes through ``_e`` (``html.escape(..., quote=True)``).
The fragment has no inline script, style or event handler, so it works under a strict CSP.
"""

from __future__ import annotations

import base64
import binascii
import html
import importlib.resources
import math
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass

from . import errors
from .errors import EsignError
from .types import SigningView

_ASSETS = ("LICENSE-signature_pad", "bond-esign.css", "bond-esign.js", "signature_pad.umd.min.js")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_PREFIX = "data:image/png;base64,"
_TRUE = ("1", "on", "true")


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


@dataclass(frozen=True)
class PanelLabels:
    """Every visible string of the panel. ``signing_as`` may contain ``{name}``."""

    heading: str = "Sign this document"
    signing_as: str = "Signing as {name}"
    name_label: str = "Your full name"
    consent_label: str = "I have read the above and I agree to sign this document electronically."
    mode_label: str = "How do you want to sign?"
    draw_tab: str = "Draw"
    type_tab: str = "Type"
    canvas_label: str = "Draw your signature in the box"
    clear: str = "Clear"
    submit: str = "Sign and accept"
    typed_preview_label: str = "Your signature will look like this"
    signed_message: str = "Thank you. This document is signed."
    not_available_expired: str = "This signing link has expired. Please ask for a new one."
    not_available_not_open: str = "This document is not ready to sign yet."
    not_available_generic: str = "This document cannot be signed right now."
    code_needed: str = "Please enter the code we sent you before signing."
    noscript_hint: str = "Without JavaScript you can sign by typing your full name."
    noscript_draw_only: str = "JavaScript is needed to draw your signature. Please turn it on and reload this page."

    @classmethod
    def spanish(cls) -> PanelLabels:
        return cls(
            heading="Firme este documento",
            signing_as="Firmando como {name}",
            name_label="Su nombre completo",
            consent_label="He leído lo anterior y acepto firmar este documento electrónicamente.",
            mode_label="¿Cómo desea firmar?",
            draw_tab="Dibujar",
            type_tab="Escribir",
            canvas_label="Dibuje su firma en el recuadro",
            clear="Borrar",
            submit="Firmar y aceptar",
            typed_preview_label="Su firma se verá así",
            signed_message="Gracias. Este documento está firmado.",
            not_available_expired="Este enlace de firma ha vencido. Pida uno nuevo.",
            not_available_not_open="Este documento aún no está listo para firmar.",
            not_available_generic="Este documento no se puede firmar en este momento.",
            code_needed="Ingrese el código que le enviamos antes de firmar.",
            noscript_hint="Sin JavaScript puede firmar escribiendo su nombre completo.",
            noscript_draw_only=(
                "Se necesita JavaScript para dibujar su firma. Actívelo y vuelva a cargar esta página."
            ),
        )


@dataclass(frozen=True)
class Submission:
    consent_version: str
    consent_accepted: bool
    typed_name: str | None
    drawn_png: bytes | None


def asset_names() -> tuple[str, ...]:
    return _ASSETS


def asset_path(name: str) -> pathlib.Path:
    """Path of a shipped web asset. Only the exact shipped names are accepted (the app serves by URL name)."""
    if name not in _ASSETS:
        raise ValueError(f"unknown bond_esign asset: {name!r}")
    return pathlib.Path(str(importlib.resources.files("bond_esign") / "web" / name))


def asset_tags(base_url: str) -> str:
    base = _e(base_url.rstrip("/"))
    return (
        f'<link rel="stylesheet" href="{base}/bond-esign.css">\n'
        f'<script defer src="{base}/signature_pad.umd.min.js"></script>\n'
        f'<script defer src="{base}/bond-esign.js"></script>'
    )


def _closed(message: str) -> str:
    return f'<div class="bond-esign bond-esign--closed" role="status"><p>{_e(message)}</p></div>'


def _paragraphs(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "".join(f"<p>{_e(ln)}</p>" for ln in lines if ln)


def _tabs(p: str, labels: PanelLabels, drawn_first: bool) -> str:
    def tab(mode: str, text: str, selected: bool) -> str:
        return (
            f'<button type="button" role="tab" class="bond-esign__tab" id="{p}-tab-{mode}" '
            f'data-mode="{mode}" aria-controls="{p}-panel-{mode}" '
            f'aria-selected="{"true" if selected else "false"}" tabindex="{0 if selected else -1}">'
            f"{_e(text)}</button>"
        )

    return (
        f'<div class="bond-esign__tabs" role="tablist" aria-label="{_e(labels.mode_label)}" hidden>'
        f"{tab('drawn', labels.draw_tab, drawn_first)}{tab('typed', labels.type_tab, not drawn_first)}</div>"
    )


def render_panel(
    view: SigningView,
    *,
    action_url: str,
    labels: PanelLabels = PanelLabels(),  # noqa: B008 (frozen dataclass default)
    hidden: Mapping[str, str] | None = None,
    error: str | None = None,
    id_prefix: str = "bond-esign",
) -> str:
    """The signing panel as an HTML fragment, or a one-sentence closed notice when signing is not possible."""
    if not view.can_sign:
        if view.signer_status == "signed":
            return _closed(labels.signed_message)
        by_reason = {errors.EXPIRED: labels.not_available_expired, errors.NOT_OPEN: labels.not_available_not_open}
        return _closed(by_reason.get(view.reason or "", labels.not_available_generic))
    if view.needs_code and not view.code_verified:
        return _closed(labels.code_needed)
    if not (view.allow_typed or view.allow_drawn):
        return _closed(labels.not_available_generic)

    p = _e(id_prefix)
    both = view.allow_typed and view.allow_drawn
    typed_ok, drawn_ok = view.allow_typed, view.allow_drawn
    initial_mode = "typed" if typed_ok else "drawn"
    form_open = (
        f'<form class="bond-esign" method="post" action="{_e(action_url)}" data-bond-esign '
        f'data-allow-typed="{int(typed_ok)}" data-allow-drawn="{int(drawn_ok)}">'
    )
    parts = [form_open]
    for name, value in (hidden or {}).items():
        parts.append(f'<input type="hidden" name="{_e(name)}" value="{_e(value)}">')
    parts.append(f'<input type="hidden" name="consent_version" value="{_e(view.consent.version)}">')
    parts.append(f'<input type="hidden" name="mode" value="{initial_mode}" data-bond-esign-mode>')
    parts.append('<input type="hidden" name="drawn_png" value="" data-bond-esign-png>')
    parts.append(f'<h2 class="bond-esign__heading">{_e(labels.heading)}</h2>')
    if view.title:
        parts.append(f'<p class="bond-esign__doc">{_e(view.title)}</p>')
    if view.signer_name:
        who = _e(labels.signing_as).replace("{name}", _e(view.signer_name))
        parts.append(f'<p class="bond-esign__who">{who}</p>')
    parts.append(f'<div class="bond-esign__consent-text">{_paragraphs(view.consent.text)}</div>')
    parts.append(
        '<div class="bond-esign__consent"><input type="checkbox" name="consent_accepted" value="1" '
        f'id="{p}-consent" class="bond-esign__check"><label for="{p}-consent">{_e(labels.consent_label)}'
        "</label></div>"
    )
    required = " required" if typed_ok else ""
    parts.append(
        f'<div class="bond-esign__field"><label for="{p}-name">{_e(labels.name_label)}</label>'
        f'<input type="text" name="typed_name" id="{p}-name" autocomplete="name" maxlength="120" '
        f'value=""{required}></div>'
    )
    if both:
        parts.append(_tabs(p, labels, drawn_first=False))
    if drawn_ok:
        parts.append(
            f'<div class="bond-esign__draw" id="{p}-panel-drawn" role="tabpanel" hidden>'
            f'<canvas class="bond-esign__canvas" id="{p}-canvas" aria-label="{_e(labels.canvas_label)}" '
            f'tabindex="0"></canvas><button type="button" class="bond-esign__clear">{_e(labels.clear)}</button>'
            "</div>"
        )
    if typed_ok:
        parts.append(
            f'<div class="bond-esign__type" id="{p}-panel-typed" role="tabpanel">'
            f'<p class="bond-esign__preview-label">{_e(labels.typed_preview_label)}</p>'
            '<p class="bond-esign__preview" aria-live="polite" data-bond-esign-preview></p></div>'
        )
    parts.append(f'<p class="bond-esign__error" role="alert" id="{p}-error">{_e(error or "")}</p>')
    parts.append(f'<button type="submit" class="bond-esign__submit">{_e(labels.submit)}</button>')
    hint = labels.noscript_hint if view.allow_typed else labels.noscript_draw_only
    parts.append(f'<noscript><p class="bond-esign__hint">{_e(hint)}</p></noscript>')
    parts.append("</form>")
    return "\n".join(parts)


def _text(form: Mapping[str, object], key: str) -> str:
    value = form.get(key)
    return value if isinstance(value, str) else ""


def parse_submission(form: Mapping[str, str], *, max_signature_bytes: int) -> Submission:
    """Read the panel's post. Missing consent is not an error here: ``sign()`` owns that rule."""
    accepted = _text(form, "consent_accepted").strip().lower() in _TRUE
    typed = _text(form, "typed_name").strip() or None
    png: bytes | None = None
    raw = _text(form, "drawn_png").strip()
    if _text(form, "mode") == "drawn" and raw:
        if not raw.startswith(_PNG_PREFIX):
            raise EsignError(errors.SIGNATURE_INVALID, "The drawn signature is not a PNG image.")
        b64 = raw[len(_PNG_PREFIX) :]
        if len(b64) > math.ceil(max_signature_bytes / 3) * 4 + 4:
            raise EsignError(errors.SIGNATURE_INVALID, "The drawn signature is too large. Please draw it again.")
        try:
            png = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise EsignError(errors.SIGNATURE_INVALID, "The drawn signature could not be read.") from None
        if not png.startswith(_PNG_MAGIC):
            raise EsignError(errors.SIGNATURE_INVALID, "The drawn signature is not a PNG image.")
        if len(png) > max_signature_bytes:
            raise EsignError(errors.SIGNATURE_INVALID, "The drawn signature is too large. Please draw it again.")
    return Submission(
        consent_version=_text(form, "consent_version").strip(),
        consent_accepted=accepted,
        typed_name=typed,
        drawn_png=png,
    )
