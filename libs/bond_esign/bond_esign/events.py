"""The append-only, hash-chained event log of a request.

Each row's ``row_hash`` is sha256(prev_hash + canonical JSON of the row's facts), so changing, reordering or
removing a row in the middle of the log breaks every hash after it. Nothing in this library updates or deletes
an event row. Removing the newest rows cannot be seen from the log alone: the certificate prints the chain head.
"""

import hashlib
import json

from sqlalchemy import func, select

from bond_esign._rows import ISO, clean_ctx, lock, utc
from bond_esign.types import ChainCheck, RequestContext, Tables

CREATED = "created"
TOKEN_ISSUED = "token_issued"
VIEWED = "viewed"
CODE_SENT = "code_sent"
CODE_VERIFIED = "code_verified"
CODE_FAILED = "code_failed"
CONSENT_GIVEN = "consent_given"
SIGNED = "signed"
DECLINED = "declined"
VOIDED = "voided"
EXPIRED = "expired"
DOCUMENT_BUILT = "document_built"
COMPLETED = "completed"
COPY_DELIVERED = "copy_delivered"
DOWNLOADED = "downloaded"

KINDS = (
    CREATED, TOKEN_ISSUED, VIEWED, CODE_SENT, CODE_VERIFIED, CODE_FAILED, CONSENT_GIVEN, SIGNED,
    DECLINED, VOIDED, EXPIRED, DOCUMENT_BUILT, COMPLETED, COPY_DELIVERED, DOWNLOADED,
)
ZERO_HASH = "0" * 64


def canonical(payload: dict) -> bytes:
    """The exact bytes that are hashed: sorted keys, no spaces, UTF-8 (pinned by docs/contracts/esign.md)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def row_hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256(prev_hash.encode("ascii") + canonical(payload)).hexdigest()


def _payload(request_id, seq, signer_id, kind, at, ip, user_agent, actor, data) -> dict:
    return {
        "request_id": request_id,
        "seq": seq,
        "signer_id": signer_id,
        "kind": kind,
        "at": utc(at).strftime(ISO),
        "ip": ip,
        "user_agent": user_agent,
        "actor": actor,
        "data": data,
    }


def _check_data(value, path="data") -> None:
    """Only str, int, bool, None and lists/dicts of those survive SQLite and Postgres round trips unchanged."""
    if value is None or isinstance(value, str | int | bool):
        return
    if isinstance(value, list | tuple):
        for i, item in enumerate(value):
            _check_data(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} has a non-string key {key!r}")
            _check_data(item, f"{path}.{key}")
        return
    raise TypeError(f"{path} holds a {type(value).__name__}; only str, int, bool, None, list and dict are allowed")


def append(session, t: Tables, request, kind: str, *, signer=None, ctx: RequestContext | None = None,
           data: dict | None = None, now):
    """Add the next event of ``request`` (locks the request row first) and flush it. Returns the row."""
    if kind not in KINDS:
        raise ValueError(f"unknown event kind {kind!r}")
    data = {} if data is None else data
    _check_data(data)
    data = json.loads(json.dumps(data))  # the exact value that will come back from the database
    ctx = clean_ctx(ctx)  # what is stored is what is hashed
    at = utc(now)
    lock(session, t, request)
    last = session.execute(
        select(t.event.seq, t.event.row_hash)
        .where(t.event.request_id == request.id)
        .order_by(t.event.seq.desc())
        .limit(1)
    ).first()
    seq, prev = (1, ZERO_HASH) if last is None else (last.seq + 1, last.row_hash)
    signer_id = signer.id if signer is not None else None
    payload = _payload(request.id, seq, signer_id, kind, at, ctx.ip, ctx.user_agent, ctx.actor, data)
    event = t.event(
        request_id=request.id, seq=seq, signer_id=signer_id, kind=kind, at=at, ip=ctx.ip,
        user_agent=ctx.user_agent, actor=ctx.actor, data=data, prev_hash=prev, row_hash=row_hash(prev, payload),
    )
    session.add(event)
    session.flush()
    return event


def chain(session, t: Tables, request) -> list:
    """Every event row of the request in seq order."""
    return list(
        session.execute(select(t.event).where(t.event.request_id == request.id).order_by(t.event.seq)).scalars()
    )


def verify_chain(session, t: Tables, request) -> ChainCheck:
    """Recompute every row from its stored columns. ``broken_seq`` is the first seq that does not check out."""
    rows = chain(session, t, request)
    prev = ZERO_HASH
    for index, row in enumerate(rows, start=1):
        payload = _payload(row.request_id, row.seq, row.signer_id, row.kind, row.at, row.ip, row.user_agent,
                           row.actor, row.data)
        good = (
            row.seq == index
            and row.request_id == request.id
            and row.prev_hash == prev
            and row.row_hash == row_hash(prev, payload)
        )
        if not good:
            return ChainCheck(ok=False, count=len(rows), broken_seq=index)
        prev = row.row_hash
    return ChainCheck(ok=True, count=len(rows), broken_seq=None)


def head(session, t: Tables, request) -> str | None:
    """The row_hash of the newest event, or None when there is none."""
    return session.execute(
        select(t.event.row_hash).where(t.event.request_id == request.id).order_by(t.event.seq.desc()).limit(1)
    ).scalar()


def count(session, t: Tables, request) -> int:
    return session.execute(select(func.count()).select_from(t.event).where(t.event.request_id == request.id)).scalar()
