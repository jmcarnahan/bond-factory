"""The claim half of the sweep: one set-based insert per batch, then the notifiers and the outbox rows."""

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select

from bond_tasks_py.dialect import dialect_insert
from bond_tasks_py.notify_protocols import Notice, TransactionalNotifier
from bond_tasks_py.timeutil import iso_z, parse_iso

LOG = logging.getLogger("bond_tasks_py.sweep")
ID_CHUNK = 500
OUTBOX_CHUNK = 100  # outbox entries per insert: eight columns each, under 900 bind parameters
BATCH = 80  # rows per statement: ten columns each, under SQLite's oldest bind limit of 999


def table_of(model: Any) -> Any:
    return getattr(model, "__table__", model)


def make_notice(row: dict, attempt: int = 1) -> Notice:
    """The notice a ledger row stands for (the same shape from the claim and from the outbox)."""
    payload = row["payload"]
    return Notice(
        notice_id=row["id"], task_id=row["task_id"], user_id=row["user_id"], stage=row["stage"], seq=row["seq"],
        kind=payload["kind"], title=payload["title"], body=payload["body"],
        due_at=parse_iso(payload["due_at"]) if payload.get("due_at") else None, priority=payload.get("priority"),
        route=payload.get("route"), created_at=row["claimed_at"], actions=tuple(payload.get("actions", ())),
        last=bool(payload.get("last", False)), attempt=attempt)


def payload_of(*, title: str, body: str, due_at: datetime | None, priority: int | None, route: str,
               actions: tuple[str, ...], last: bool) -> dict:
    return {"kind": "task_due", "title": title, "body": body, "due_at": iso_z(due_at), "priority": priority,
            "route": route, "actions": list(actions), "last": last}


def _claim(session: Any, ledger: Any, outbox: Any, rows: list[dict], transactional: Sequence[TransactionalNotifier],
           channels: Sequence[str], now: datetime) -> tuple[int, int, int]:
    """Claim ``rows`` in a savepoint. Returns (claimed, skipped, queued) for the rows this call won."""
    with session.begin_nested():
        table = table_of(ledger)
        won = {r[0] for r in session.execute(
            dialect_insert(session, table).values(rows).on_conflict_do_nothing().returning(table.c.id))}
        mine = [r for r in rows if r["id"] in won]
        sent = [r for r in mine if r["status"] == "claimed"]
        notices = [make_notice(r) for r in sent]
        if notices:
            for notifier in transactional:
                notifier.write(session, notices)
        queued = 0
        if sent and channels and outbox is not None:
            out = table_of(outbox)
            entries = [{"ledger_id": r["id"], "channel": c, "delivered_at": None, "failed_at": None,
                        "attempts": 0, "last_error": None, "lease_until": None, "created_at": now}
                       for r in sent for c in channels]
            for start in range(0, len(entries), OUTBOX_CHUNK):
                session.execute(dialect_insert(session, out).values(entries[start:start + OUTBOX_CHUNK])
                                .on_conflict_do_nothing())
            queued = len(entries)
    return len(sent), len(mine) - len(sent), queued


def existing_ids(session: Any, ledger: Any, ids: list[str]) -> set[str]:
    """The notice ids already in the ledger (asked in chunks, under SQLite's bind limit). An idle sweep inserts
    nothing; the insert keeps its ON CONFLICT DO NOTHING, which stays the arbiter when another worker claims in
    between."""
    table = table_of(ledger)
    have: set[str] = set()
    for start in range(0, len(ids), ID_CHUNK):
        have.update(session.scalars(select(table.c.id).where(table.c.id.in_(ids[start:start + ID_CHUNK]))))
    return have


def claim_rows(session: Any, ledger: Any, outbox: Any, rows: list[dict], transactional: Sequence[TransactionalNotifier],
               channels: Sequence[str], now: datetime) -> tuple[int, int, int, int]:
    """Claim the rows in order, in batches. Returns (claimed, skipped, queued, errors).

    A batch that raises (a notifier refused it) is rolled back and its rows are retried one by one, each in its
    own savepoint. A row that still fails leaves NOTHING behind (no ledger row), is logged once with its notice id
    and the exception class, and is counted in ``errors``: the next sweep tries it again while its stage is
    current."""
    claimed = skipped = queued = errors = 0
    for start in range(0, len(rows), BATCH):
        batch = rows[start:start + BATCH]
        try:
            got = _claim(session, ledger, outbox, batch, transactional, channels, now)
        except Exception:  # noqa: BLE001 - any failure of the batch is isolated row by row
            got = (0, 0, 0)
            for row in batch:
                try:
                    one = _claim(session, ledger, outbox, [row], transactional, channels, now)
                except Exception as exc:  # noqa: BLE001
                    LOG.warning("notice %s was not claimed: %s", row["id"], type(exc).__name__)
                    errors += 1
                    continue
                got = (got[0] + one[0], got[1] + one[1], got[2] + one[2])
        claimed, skipped, queued = claimed + got[0], skipped + got[1], queued + got[2]
    return claimed, skipped, queued, errors
