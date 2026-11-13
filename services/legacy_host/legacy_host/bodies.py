"""Request bodies in both vocabularies. The legacy keys (`sync_to_calendar`, `client_ref`, `case_ref`) and bond's
keys are read; a key neither knows is ignored, never a 422."""

from __future__ import annotations

from typing import Any

from bond_tasks_py import TaskCreate, TaskError, TaskUpdate
from pydantic import ValidationError

from .models import HOST_COLUMNS

#: bond fields that refuse null: a legacy client that sends null means "not sent"
NOT_NULLABLE = ("checklist", "links", "remind_minutes_before", "mirror_enabled")


def split(body: dict[str, Any], model: type[TaskCreate | TaskUpdate]) -> tuple[Any, dict[str, Any]]:
    """`(TaskCreate or TaskUpdate, extras)` from a request body of either vocabulary."""
    fields = {k: v for k, v in body.items() if k in model.model_fields}
    # Both vocabularies in one body (the SDK client echoes what it read): bond's key wins. The response-only keys
    # `calendar_event_id`, `client_name`, `case_label` (and `sync_to_calendar` beside `mirror_enabled`) are never written.
    if "sync_to_calendar" in body and "mirror_enabled" not in body:
        fields["mirror_enabled"] = body["sync_to_calendar"]
    for name in NOT_NULLABLE:
        if name in fields and fields[name] is None:
            del fields[name]
    if "mirror_enabled" in fields:
        fields["mirror_enabled"] = bool(fields["mirror_enabled"])
    if model is TaskCreate and fields.get("source") is None:
        fields.pop("source", None)
    try:
        data = model(**fields)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        raise TaskError("invalid_request", f"{where}: {first.get('msg', 'not valid')}", 422) from None
    return data, {name: body[name] for name in HOST_COLUMNS if name in body}
