"""Input models and JSON shapes: the ``checklist`` item ``{id, text, done_at|None}`` and the ``links`` item
``{kind, id, label}``. ``TaskCreate`` / ``TaskUpdate`` use ``model_fields_set``: an omitted field is unchanged, an
explicit ``None`` clears ``due_date``, ``due_time``, ``priority``, ``assigned_user_id`` and ``notes``."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from bond_tasks_py.timeutil import iso_z, parse_iso, to_naive_utc

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
MAX_REMIND_MINUTES = 60 * 24 * 365  # what old clients may send; the lead in use is capped at stages.MAX_LEAD_MINUTES
MIN_REMIND_MINUTES = -3  # -3 use my default, -2 none, -1 the morning of the due date

def _no_nul(value: str) -> str:
    """Postgres text cannot hold NUL: refuse it here (422) instead of failing at commit (500)."""
    if "\x00" in value:
        raise ValueError("NUL characters are not allowed")
    return value


Text = Annotated[str, AfterValidator(_no_nul)]
TaskId = Annotated[str, StringConstraints(pattern=ID_PATTERN)]
DueTime = Annotated[str, StringConstraints(pattern=TIME_PATTERN)]
Priority = Annotated[int, Field(ge=1, le=3)]


class ChecklistInput(BaseModel):
    """What a client sends for one checklist item. ``done`` wins over ``done_at`` when both are given."""

    model_config = ConfigDict(extra="forbid")

    id: Text | None = Field(default=None, min_length=1, max_length=64)
    text: Text = Field(max_length=500)
    done: bool | None = None
    done_at: datetime | None = None

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("a checklist item needs text")
        return value


class LinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Text = Field(min_length=1, max_length=32)
    id: Text = Field(min_length=1, max_length=128)
    label: Text | None = Field(default=None, max_length=255)


class _TaskFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: Text | None = None
    due_date: date | None = None
    due_time: DueTime | None = None
    priority: Priority | None = None  # 1 low, 2 normal, 3 high; an explicit null clears it on update
    due_at: datetime | None = None  # a hint for a timed task only; the server recomputes (never rejected)
    time_zone: Text | None = Field(default=None, max_length=64)  # IANA name, write-only, never stored on the task
    assigned_user_id: Text | None = None
    checklist: list[ChecklistInput] = Field(default_factory=list, max_length=200)
    links: list[LinkInput] = Field(default_factory=list, max_length=50)
    remind_minutes_before: int = Field(default=-2, ge=MIN_REMIND_MINUTES, le=MAX_REMIND_MINUTES)
    mirror_enabled: bool = True


class TaskCreate(_TaskFields):
    id: TaskId | None = None
    title: Text | None = None  # a missing or blank title is the coded error title_required
    source: Text = Field(default="manual", min_length=1, max_length=32)


class TaskUpdate(_TaskFields):
    """Every field optional; check ``model_fields_set`` for what was sent. Only ``due_date``, ``due_time``,
    ``priority``, ``assigned_user_id`` and ``notes`` accept an explicit null (``due_at`` and ``time_zone`` are hints
    and a null is ignored); ``checklist``, ``links``, ``remind_minutes_before`` and
    ``mirror_enabled`` refuse it (422), and a null ``title`` is ``title_required``."""

    title: Text | None = None


def new_item_id() -> str:
    return uuid.uuid4().hex[:12]


def checklist_item(item_id: str, text: str, done_at: datetime | None) -> dict:
    return {"id": item_id, "text": text, "done_at": iso_z(done_at)}


def normalize_checklist(items: list[ChecklistInput], *, existing: list[dict] | None, now: datetime) -> list[dict]:
    """Stored items for a client's list. An item keeps its ``done_at`` by id unless ``done`` or ``done_at`` says
    otherwise; ``done: true`` stamps ``now``; ids missing or repeated within the list are minted fresh."""
    previous = {entry["id"]: entry for entry in (existing or [])}
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        item_id = item.id if item.id and item.id not in seen else new_item_id()
        seen.add(item_id)
        before = previous.get(item_id, {}).get("done_at")
        if item.done is True:
            done_at = parse_iso(before) if before else to_naive_utc(now)
        elif item.done is False:
            done_at = None
        elif item.done_at is not None:
            done_at = to_naive_utc(item.done_at)
        else:
            done_at = parse_iso(before) if before else None
        out.append(checklist_item(item_id, item.text, done_at))
    return out


def normalize_links(items: list[LinkInput]) -> list[dict]:
    """Stored links; a repeated (kind, id) pair keeps its first entry (the link index key is task, kind, ref)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for item in items:
        if (item.kind, item.id) not in seen:
            seen.add((item.kind, item.id))
            out.append({"kind": item.kind, "id": item.id, "label": item.label})
    return out
