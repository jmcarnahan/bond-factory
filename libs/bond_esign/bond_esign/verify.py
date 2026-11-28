"""Cross-check the stored rows against the hashed events: the chain alone covers only the event rows."""

from sqlalchemy import select

from bond_esign import events
from bond_esign._rows import COMPLETED, SIGNED, iso
from bond_esign.pdf_read import sha256_hex
from bond_esign.types import EvidenceCheck, Tables


def _created(rows, request, problems: list[str]) -> None:
    created = next((e for e in rows if e.kind == events.CREATED), None)
    if created is None:
        problems.append("no created event")
        return
    data = created.data or {}
    for column in ("document_sha256", "title", "consent_version", "consent_sha256"):
        if getattr(request, column) != data.get(column):
            problems.append(f"request: {column} differs from the created event")
    if sha256_hex((request.consent_text or "").encode("utf-8")) != request.consent_sha256:
        problems.append("request: consent_text does not match consent_sha256")


def _signers(rows, signer_rows, problems: list[str]) -> None:
    created = next((e for e in rows if e.kind == events.CREATED), None)
    if created is None:
        return
    expected = {s.get("id"): s for s in (created.data or {}).get("signers", [])}
    stored = {s.id: s for s in signer_rows}
    if set(expected) != set(stored):
        problems.append("signers: the rows differ from the created event")
    for sid, row in stored.items():
        want = expected.get(sid)
        if want is None:
            continue
        for column in ("position", "name", "email", "role", "key"):
            if getattr(row, column) != want.get(column):
                problems.append(f"signer {sid[:8]}: {column} differs from the created event")


def _signed(rows, signer_rows, problems: list[str]) -> None:
    by_signer = {e.signer_id: e for e in rows if e.kind == events.SIGNED}
    for s in signer_rows:
        who = f"signer {s.id[:8]}"
        ev = by_signer.get(s.id)
        if s.status != SIGNED:
            if ev is not None:
                problems.append(f"{who}: has a signed event but is not signed")
            continue
        if ev is None:
            problems.append(f"{who}: is signed but has no signed event")
            continue
        data = ev.data or {}
        if s.signature_sha256 != data.get("signature_sha256"):
            problems.append(f"{who}: signature_sha256 differs from the signed event")
        body = s.signature_png if s.signature_kind == "drawn" else (s.typed_name or "").encode("utf-8")
        if not body or sha256_hex(body) != s.signature_sha256:
            problems.append(f"{who}: the stored signature does not match its signature_sha256")
        for column, key in (("signature_kind", "kind"), ("method", "method"), ("typed_name", "typed_name"),
                            ("name", "name")):
            if getattr(s, column) != data.get(key):
                problems.append(f"{who}: {column} differs from the signed event")
        if iso(s.signed_at) != iso(ev.at):
            problems.append(f"{who}: signed_at differs from the signed event")


def _built(rows, request, problems: list[str]) -> None:
    if request.status != COMPLETED:
        return
    built = next((e for e in rows if e.kind == events.DOCUMENT_BUILT), None)
    if built is None:
        problems.append("request: completed but has no document_built event")
        return
    data = built.data or {}
    if request.signed_sha256 != data.get("sha256"):
        problems.append("request: signed_sha256 differs from the document_built event")
    for column in ("sealed", "timestamped"):
        if bool(getattr(request, column)) != bool(data.get(column)):
            problems.append(f"request: {column} differs from the document_built event")


def verify_evidence(session, t: Tables, request) -> EvidenceCheck:
    """The hash chain, plus request and signer rows checked against what the events recorded.

    ``problems`` holds one short sentence per mismatch. Tampering that also rewrites the chain is not
    detectable here: compare the head printed on the certificate.
    """
    chain = events.verify_chain(session, t, request)
    rows = events.chain(session, t, request)
    signer_rows = list(
        session.execute(select(t.signer).where(t.signer.request_id == request.id).order_by(t.signer.position))
        .scalars()
    )
    problems: list[str] = []
    if not chain.ok:
        problems.append(f"event chain broken at seq {chain.broken_seq}")
    _created(rows, request, problems)
    _signers(rows, signer_rows, problems)
    _signed(rows, signer_rows, problems)
    _built(rows, request, problems)
    return EvidenceCheck(ok=not problems, chain=chain, problems=tuple(problems))
