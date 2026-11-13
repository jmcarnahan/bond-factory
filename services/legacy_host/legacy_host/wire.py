"""The legacy wire: what installed clients read. Bond's keys stay, the app's keys are added, timestamps lose the
zone suffix and gain microseconds, and an error answers `{"detail": {"error_code", "code", "message"}}`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bond_tasks_py import TaskError

#: bond key -> the task attribute that holds the instant (rewritten as naive ISO with microseconds)
TIMESTAMPS = {"completed_at": "completed_at", "created_at": "created_at", "updated_at": "updated_at",
              "due_at": "due_at"}


def naive_iso(value: datetime | None) -> str | None:
    """`2026-11-08T10:00:00.000000`: naive UTC, six fractional digits, no zone suffix."""
    return None if value is None else value.strftime("%Y-%m-%dT%H:%M:%S.%f")


def legacy_item(item: dict, task: Any, *, client_name: str | None = None, case_label: str | None = None) -> dict:
    """Bond's item dict with the legacy keys added and the four instants rewritten."""
    out = dict(item)
    for key, attr in TIMESTAMPS.items():
        out[key] = naive_iso(getattr(task, attr))
    out.update({
        "sync_to_calendar": bool(task.mirror_enabled),
        "calendar_event_id": task.external_event_id,
        "client_ref": task.client_ref,
        "case_ref": task.case_ref,
        "client_name": client_name,
        "case_label": case_label,
    })
    return out


def legacy_body(code: str, message: str) -> dict[str, Any]:
    return {"detail": {"error_code": code.upper(), "code": code, "message": message}}


def legacy_error(exc: TaskError) -> tuple[int, dict[str, Any]]:
    return exc.status, legacy_body(exc.code, exc.message)
