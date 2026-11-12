"""Task models and services: the due instant, the day view, links, per-user settings, the three-stage notice
sweep with its ledger and outbox, and the calendar mirror.

Imports only sqlalchemy, pydantic and the standard library. Everything the host supplies enters through the
Protocols in ``protocols.py`` and ``notify_protocols.py``.
"""

from bond_tasks_py import service
from bond_tasks_py.compose import default_compose
from bond_tasks_py.dialect import dialect_insert, ensure_savepoint_safe, sqlite_savepoint_setup
from bond_tasks_py.due import (
    backfill_due_at,
    compute_due_at,
    end_of_day_due,
    is_overdue,
    local_day_bounds,
    next_local_time,
    recompute_day_due,
    valid_zone,
)
from bond_tasks_py.errors import CODES, TaskError
from bond_tasks_py.hostcols import apply_extras
from bond_tasks_py.ledger import TASK_NOTICE_LEDGER_COLUMNS, NoticeLedgerMixin
from bond_tasks_py.lifecycle import apply_notice_action
from bond_tasks_py.link_index import (
    TASK_LINK_INDEX_COLUMNS,
    TaskLinkIndexMixin,
    make_link_hook,
    reindex_links,
)
from bond_tasks_py.links import remove_links, retarget_links
from bond_tasks_py.mirror import (
    classify,
    mark_mirror,
    mirror_eligible,
    remove_event,
    sync_mirror,
)
from bond_tasks_py.models import (
    TASK_COLUMNS,
    USE_DEFAULT_REMINDER,
    MirrorStatus,
    TasksMixin,
    TaskStatus,
)
from bond_tasks_py.notify_protocols import (
    NOTICE_ACTIONS,
    NOTICE_CATEGORY,
    STAGES,
    Compose,
    Notice,
    Notifier,
    Recipients,
    TransactionalNotifier,
)
from bond_tasks_py.outbox import (
    TASK_NOTICE_OUTBOX_COLUMNS,
    DeliverResult,
    NoticeOutboxMixin,
    deliver_pending,
)
from bond_tasks_py.permissions import DefaultPermissions
from bond_tasks_py.protocols import (
    LINK_KIND_CONTACT,
    AfterWrite,
    CalendarMirror,
    LinkResolver,
    MirrorDraft,
    MirroredEvent,
    MirrorPointer,
    MirrorProviders,
    Permissions,
    Preferences,
    UserPrefs,
)
from bond_tasks_py.queries import TaskFilters, list_tasks, summary, viewer_today
from bond_tasks_py.quiet import in_quiet_hours, next_work_start, sendable
from bond_tasks_py.retention import prune_ledger
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
from bond_tasks_py.settings_schema import SettingsUpdate, settings_item
from bond_tasks_py.stages import (
    MAX_LEAD_MINUTES,
    StageTime,
    current_stage,
    deadline_token,
    effective_zone,
    fnv1a31,
    notice_id,
    stage_times,
)
from bond_tasks_py.sweep import SweepResult, default_recipients, notice_recipients, sweep_due
from bond_tasks_py.sync_routes import TaskRoute, sync_routes, verdict_for
from bond_tasks_py.today import TodayResult, today
from bond_tasks_py.usersettings import (
    TASK_USER_SETTINGS_COLUMNS,
    StoredPreferences,
    TaskUserSettingsMixin,
    get_settings,
    settings_overridden,
    update_settings,
)

__version__ = "0.2.0"

__all__ = [
    "CODES", "ITEM_KEYS", "LINK_KIND_CONTACT", "MAX_LEAD_MINUTES", "NOTICE_ACTIONS", "NOTICE_CATEGORY", "STAGES",
    "TASK_COLUMNS", "TASK_LINK_INDEX_COLUMNS", "TASK_NOTICE_LEDGER_COLUMNS", "TASK_NOTICE_OUTBOX_COLUMNS",
    "TASK_USER_SETTINGS_COLUMNS", "USE_DEFAULT_REMINDER", "AfterWrite", "CalendarMirror", "ChecklistInput",
    "Compose", "DefaultPermissions", "DeliverResult", "LinkInput", "LinkResolver", "MirrorDraft", "MirrorPointer",
    "MirrorProviders", "MirrorStatus", "MirroredEvent", "Notice", "NoticeLedgerMixin", "NoticeOutboxMixin",
    "Notifier", "Permissions", "Preferences", "Recipients", "SettingsUpdate", "StageTime",
    "StoredPreferences", "SweepResult", "TaskCreate", "TaskError", "TaskFilters", "TaskLinkIndexMixin",
    "TaskRoute", "TaskStatus", "TaskUpdate", "TaskUserSettingsMixin", "TasksMixin", "TodayResult",
    "TransactionalNotifier", "UserPrefs", "apply_extras", "apply_notice_action", "backfill_due_at", "cancel",
    "classify", "complete", "compute_due_at", "create", "current_stage",
    "deadline_token", "default_compose", "default_recipients", "delete", "deliver_pending", "dialect_insert",
    "effective_zone", "end_of_day_due", "ensure_savepoint_safe", "fnv1a31", "get", "get_settings", "in_quiet_hours", "is_overdue",
    "list_tasks", "local_day_bounds", "make_link_hook", "mark_mirror", "mirror_eligible", "next_local_time",
    "next_work_start", "notice_id", "notice_recipients", "prune_ledger", "recompute_day_due", "reindex_links", "remove_event",
    "remove_links", "reopen", "retarget_links", "sendable", "service", "set_checklist_item", "settings_item", "settings_overridden", "sqlite_savepoint_setup",
    "stage_times", "summary", "sweep_due", "sync_mirror", "sync_routes", "task_item", "task_items", "today",
    "update", "update_settings", "valid_zone", "verdict_for", "viewer_today",
]
