"""Task models, services and reminder scheduling.

Imports only sqlalchemy, pydantic and the standard library. The queue and the calendar enter through the
``Scheduler``, ``CalendarMirror`` and ``MirrorProviders`` Protocols.
"""

from bond_tasks_py import service
from bond_tasks_py.errors import CODES, TaskError
from bond_tasks_py.mirror import (
    classify,
    mark_mirror,
    mirror_eligible,
    remove_event,
    sync_mirror,
)
from bond_tasks_py.models import TASK_COLUMNS, MirrorStatus, TasksMixin, TaskStatus
from bond_tasks_py.protocols import (
    CalendarMirror,
    MirrorDraft,
    MirroredEvent,
    MirrorPointer,
    MirrorProviders,
    Scheduler,
)
from bond_tasks_py.queries import TaskFilters, list_tasks, summary
from bond_tasks_py.reminders import (
    JOB_TYPE,
    cancel_reminder,
    compute_remind_at,
    dedupe_key,
    fire_reminder,
    schedule_reminder,
)
from bond_tasks_py.schema import ChecklistInput, LinkInput, TaskCreate, TaskUpdate
from bond_tasks_py.serialize import ITEM_KEYS, task_item, task_items
from bond_tasks_py.service import (
    cancel,
    complete,
    create,
    delete,
    get,
    reopen,
    set_checklist_item,
    update,
)
from bond_tasks_py.sync_routes import TaskRoute, sync_routes, verdict_for

__version__ = "0.1.0"

__all__ = [
    "CODES", "ITEM_KEYS", "JOB_TYPE", "TASK_COLUMNS", "CalendarMirror", "ChecklistInput", "LinkInput", "MirrorDraft",
    "MirrorPointer", "MirrorProviders", "MirrorStatus", "MirroredEvent", "Scheduler", "TaskCreate", "TaskError",
    "TaskFilters", "TaskRoute", "TaskStatus", "TaskUpdate", "TasksMixin", "cancel", "cancel_reminder", "classify",
    "complete", "compute_remind_at", "create", "dedupe_key", "delete", "fire_reminder", "get", "list_tasks",
    "mark_mirror", "mirror_eligible", "remove_event", "reopen", "schedule_reminder", "service",
    "set_checklist_item", "summary", "sync_mirror", "sync_routes", "task_item", "task_items", "update",
    "verdict_for",
]
