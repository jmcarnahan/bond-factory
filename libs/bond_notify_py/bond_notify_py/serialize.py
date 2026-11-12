"""The ``Notice`` wire shape (fixture ``../../fixtures/notify/notice.json``)."""

from typing import Any

from bond_notify_py.timeutil import iso_z

#: Top-level keys of a ``Notice`` on the wire, in order.
NOTICE_KEYS = ("id", "user_id", "kind", "title", "body", "data", "created_at", "read_at", "dismissed_at")
#: Keys of the ``data`` object, in order.
DATA_KEYS = ("task_id", "stage", "seq", "due_at", "priority", "route", "actions", "last")


def due_key(value: Any) -> str | None:
    """A ``due_at`` (datetime, ISO string or None) as the ISO Z string the inbox stores, for comparison."""
    if value is None or value == "":
        return None
    return iso_z(value) if hasattr(value, "isoformat") else str(value)


def notice_item(row: Any) -> dict:
    """One notice row as the JSON a client reads. ``data`` is rebuilt, so the row is never mutated; a key the
    row's ``data`` lacks comes out null (``actions`` as an empty list, ``last`` as false). A ``due_at`` stored as a
    datetime is written as ISO Z; a string is passed through. ``source_id`` is server-only, not on the wire."""
    stored = dict(row.data or {})
    data = {key: stored.get(key) for key in DATA_KEYS}
    data["actions"] = list(stored.get("actions") or [])
    data["last"] = bool(stored.get("last", False))
    if hasattr(data["due_at"], "isoformat"):
        data["due_at"] = iso_z(data["due_at"])
    return {
        "id": row.id,
        "user_id": row.user_id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "data": data,
        "created_at": iso_z(row.created_at),
        "read_at": iso_z(row.read_at),
        "dismissed_at": iso_z(row.dismissed_at),
    }
