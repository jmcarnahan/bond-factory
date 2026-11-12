"""``InboxNotifier``: the transactional notifier that writes the stored inbox inside the sweep's claim."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select

from bond_notify_py.dialect import dialect_insert
from bond_notify_py.serialize import due_key
from bond_notify_py.timeutil import iso_z, to_naive_utc

TITLE_LIMIT = 255


def _row(notice: Any) -> dict:
    due_at = notice.due_at
    return {
        "id": notice.notice_id,
        "user_id": notice.user_id,
        "kind": notice.kind,
        "title": (notice.title or "")[:TITLE_LIMIT],
        "body": notice.body,
        "data": {
            "task_id": notice.task_id,
            "stage": notice.stage,
            "seq": notice.seq,
            "due_at": iso_z(due_at) if hasattr(due_at, "isoformat") else due_at,
            "priority": notice.priority,
            "route": notice.route,
            "actions": list(notice.actions or ()),
            "last": bool(notice.last),
        },
        "source_id": notice.task_id,
        "created_at": to_naive_utc(notice.created_at),
        "read_at": None,
        "dismissed_at": None,
    }


class InboxNotifier:
    """Satisfies the tasks lib's ``TransactionalNotifier`` by shape: ``write(session, notices)``.

    One executemany insert of the notices with a target-less ``ON CONFLICT DO NOTHING``, so a replayed claim is
    harmless and a notice already stored is left as it is (a read or dismissed row stays so). It runs inside the
    caller's savepoint: it never commits and never opens a transaction; raising cancels the batch.
    """

    def __init__(self, notice_model: Any) -> None:
        self.notice_model = notice_model

    def write(self, session: Any, notices: Sequence[Any]) -> None:
        rows = [_row(notice) for notice in notices]
        if not rows:
            return
        session.execute(dialect_insert(session, self.notice_model.__table__).on_conflict_do_nothing(), rows)
        self._put_away_stale(session, rows)

    def _put_away_stale(self, session: Any, rows: list[dict]) -> None:
        """A notice for a new due instant replaces the live ones made for an old instant of the same task and
        user (a postponed task must not keep its "overdue" notices). Compared in Python: portable JSON."""
        model = self.notice_model
        groups: dict[tuple, tuple[set, Any]] = {}
        for row in rows:
            due, stamp = groups.get((row["user_id"], row["source_id"]), (set(), row["created_at"]))
            due.add(due_key(row["data"]["due_at"]))
            groups[(row["user_id"], row["source_id"])] = (due, max(stamp, row["created_at"]))
        for (user_id, source_id), (current, stamp) in groups.items():
            live = session.execute(
                select(model).where(model.user_id == user_id, model.source_id == source_id,
                                    model.dismissed_at.is_(None))
            ).scalars()
            for row in live:
                if due_key((row.data or {}).get("due_at")) not in current:
                    row.dismissed_at = stamp
                    if row.read_at is None:
                        row.read_at = stamp
        session.flush()
