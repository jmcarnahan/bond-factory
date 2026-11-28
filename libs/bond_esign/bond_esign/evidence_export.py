"""The full evidence of a request as one JSON-serialisable dict (schema ``bond.esign_evidence/0.1``)."""

import base64
from datetime import datetime

from sqlalchemy import select

from bond_esign import events
from bond_esign._rows import iso
from bond_esign.types import Tables
from bond_esign.verify import verify_evidence

SCHEMA = "bond.esign_evidence/0.1"
_REQUEST_SKIP = {"meta"}  # app-owned
_SIGNER_SKIP = {"signature_png", "code_sha256", "token_sha256"}  # the last two are credentials


def _value(value):
    return iso(value) if isinstance(value, datetime) else value


def _columns(row, skip: set[str]) -> dict:
    return {c.name: _value(getattr(row, c.name)) for c in row.__table__.columns if c.name not in skip}


def evidence(session, t: Tables, request) -> dict:
    signers = session.execute(
        select(t.signer).where(t.signer.request_id == request.id).order_by(t.signer.position)
    ).scalars().all()
    signer_dicts = []
    for signer in signers:
        item = _columns(signer, _SIGNER_SKIP)
        png = signer.signature_png
        item["signature_png_base64"] = base64.b64encode(png).decode("ascii") if png else None
        signer_dicts.append(item)
    rows = events.chain(session, t, request)
    check = verify_evidence(session, t, request)
    return {
        "schema": SCHEMA,
        "request": _columns(request, _REQUEST_SKIP),
        "signers": signer_dicts,
        "events": [
            {
                "seq": e.seq, "signer_id": e.signer_id, "kind": e.kind, "at": iso(e.at), "ip": e.ip,
                "user_agent": e.user_agent, "actor": e.actor, "data": e.data, "prev_hash": e.prev_hash,
                "row_hash": e.row_hash,
            }
            for e in rows
        ],
        "chain": {"ok": check.chain.ok, "count": check.chain.count, "head": rows[-1].row_hash if rows else None},
        "check": {"ok": check.ok, "problems": list(check.problems)},
    }
