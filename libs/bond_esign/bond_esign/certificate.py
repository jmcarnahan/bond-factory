"""The "Signature certificate" pages appended to the signed PDF (Letter, deterministic, standard fonts)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bond_esign.certificate_draw import Flow
from bond_esign.labels import CertificateLabels
from bond_esign.types import Brand, CertificateData, CertificateSigner

_UA_MAX = 120


def _times(moment: datetime, zone: str, labels: CertificateLabels) -> str:
    utc = labels.format_datetime(moment, labels.zone_label)
    if zone in ("", "UTC"):
        return utc
    try:
        local = moment.replace(tzinfo=UTC).astimezone(ZoneInfo(zone))
    except (ZoneInfoNotFoundError, ValueError):
        return utc
    return f"{utc}  ({labels.format_datetime(local.replace(tzinfo=None), local.strftime('%Z') or zone)}, {zone})"


def _header(f: Flow, data: CertificateData) -> None:
    labels, brand = f.labels, f.brand
    if brand and brand.logo_png:
        try:
            top = f.y
            f.image(brand.logo_png, 110, 36, indent=0)
            f.y = top - 40
        except Exception:  # noqa: BLE001, S110  an unreadable logo must not stop the certificate
            pass
    if brand and brand.name:
        f.lines(brand.name, size=9, color=(0.35, 0.38, 0.42))
        f.gap(2)
    f.heading(labels.title, 20)
    f.rule(f.accent)
    f.gap(4)
    f.field(labels.document, data.title, name=True)
    f.field(labels.request_id, data.request_id, mono=True)
    f.field(labels.document_sha256, data.document_sha256, mono=True)
    f.field(labels.pages, str(data.page_count))


def _signer(f: Flow, s: CertificateSigner, data: CertificateData) -> None:
    labels = f.labels
    f.gap(6)
    f.ensure(110)
    f.lines(f"{s.name}  -  {labels.status_label(s.status)}", font=f.font(True, True), size=10.5, name=True)
    f.field(labels.email, s.email, indent=8)
    f.field(labels.role, s.role, indent=8)
    f.field(labels.method, labels.method_label(s.method), indent=8)
    f.field(labels.witness, s.witness, name=True, indent=8)
    if s.signed_at:
        f.field(labels.signed_at, _times(s.signed_at, data.zone, labels), indent=8)
    f.field(labels.ip, s.ip, indent=8)
    f.field(labels.user_agent, (s.user_agent or "")[:_UA_MAX], indent=8)
    if s.signed_at:
        f.field(labels.consent, f"{data.consent_version} ({data.consent_language})", indent=8)
        f.field(labels.consent_sha256, data.consent_sha256, mono=True, indent=8)
    if s.signature_kind == "drawn" and s.signature_png:
        f.field(labels.signature, labels.drawn_signature, indent=8)
        try:
            f.image(s.signature_png, 180, 56, indent=120)
        except Exception:  # noqa: BLE001  an unreadable image must not stop the certificate
            f.field("", "?", indent=8)
    elif s.signature_kind == "typed" or (s.signed_at and s.typed_name):
        f.field(labels.signature, labels.typed_signature, indent=8)
        font = f.name_font or "Times-Italic"
        f.lines(s.typed_name or "", font=font, size=18, indent=120, name=True)
    if s.signature_sha256:
        f.field(labels.signature_sha256, s.signature_sha256, mono=True, indent=8)
    f.gap(4)
    f.rule()


def _timeline(f: Flow, data: CertificateData) -> None:
    labels = f.labels
    local = data.zone not in ("", "UTC")
    f.gap(6)
    f.heading(labels.timeline_heading)
    cols = [(0, labels.col_seq), (22, labels.col_time), (140, labels.col_event)]
    if local:
        cols = [(0, labels.col_seq), (22, labels.col_time), (130, f"({data.zone})"), (250, labels.col_event)]
    signer_x = 380 if local else 290
    cols.append((signer_x, labels.col_signer))
    f.row(cols, font="Helvetica-Bold")
    for ev in data.events:
        cells = [(0, str(ev.seq)), (22, f"{ev.at:%Y-%m-%d %H:%M:%S}")]
        if local:
            try:
                z = ev.at.replace(tzinfo=UTC).astimezone(ZoneInfo(data.zone))
                cells.append((130, f"{z:%Y-%m-%d %H:%M:%S}"))
            except (ZoneInfoNotFoundError, ValueError):
                cells.append((130, ""))
        cells.append((250 if local else 140, labels.event_label(ev.kind)))
        cells.append((signer_x, (ev.signer_name or "")[:30]))
        f.row(cells)


def _render(data: CertificateData, labels: CertificateLabels, brand: Brand | None, total: int | None):
    f = Flow(labels, brand, total)
    _header(f, data)
    f.gap(6)
    f.heading(labels.signers_heading)
    for s in data.signers:
        _signer(f, s, data)
    _timeline(f, data)
    f.gap(8)
    f.heading(labels.consent_heading)
    f.lines(data.consent_text, size=8.5, limit=None)
    f.gap(8)
    f.heading(labels.verify_heading)
    f.lines(labels.verify_text.format(head=data.chain_head), size=9, limit=None)
    return f.finish()


def certificate_pages(data: CertificateData, *, labels: CertificateLabels, brand: Brand | None = None) -> bytes:
    """Render the certificate; two passes so every page can say "Certificate page n of m"."""
    _, pages = _render(data, labels, brand, None)
    pdf, _ = _render(data, labels, brand, pages)
    return pdf

