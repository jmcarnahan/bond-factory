"""Best-effort calendar mirror: a dated, open task appears as an event in its target person's calendar.

The service only calls ``mark_mirror`` (sets ``pending`` or ``skipped``). The app runs ``sync_mirror`` after commit
as a background task. It reloads the task, never raises and records the outcome on the row:

    mirrored   the event exists in the target mailbox (provider, event id, mailbox and etag stored)
    skipped    nothing to do, or the person has no live connection (or it needs reconnecting)
    failed     the provider refused; the next edit retries

The mailbox is the assignee, else the owner. A reassign deletes the event in the old mailbox, then creates one in the
new. Updates send ``If-Match`` with the stored etag; a stale etag re-reads the event and updates once more.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import UTC as _UTC
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import update

from bond_tasks_py.models import MirrorStatus, TaskStatus
from bond_tasks_py.protocols import MirrorDraft, MirrorPointer, MirrorProviders
from bond_tasks_py.timeutil import local_to_utc, parse_hhmm

LOGGER = logging.getLogger(__name__)
EVENT_MINUTES = 30


def mirror_eligible(task: Any) -> bool:
    return bool(task.mirror_enabled and task.due_date and task.status == TaskStatus.OPEN.value)


def mark_mirror(task: Any) -> None:
    """``pending`` when the task belongs on a calendar or must come off one; else ``skipped``."""
    wanted = mirror_eligible(task) or bool(task.external_event_id)
    task.mirror_status = (MirrorStatus.PENDING if wanted else MirrorStatus.SKIPPED).value


def mailbox_of(task: Any) -> str:
    return task.assigned_user_id or task.owner_user_id


def pointer_of(task: Any) -> MirrorPointer | None:
    if not task.external_event_id:
        return None
    return MirrorPointer(task.external_account_user_id or mailbox_of(task), task.external_provider, task.external_event_id)


# -- error classification (by class name, so no sibling import is needed) ---------------------------------------------


def _names(exc: BaseException) -> set[str]:
    return {cls.__name__ for cls in type(exc).__mro__}


def classify(exc: BaseException) -> str:
    """``not_found``, ``etag``, ``reconnect`` or ``other``."""
    names, status = _names(exc), getattr(exc, "status", None)
    if "NotFound" in names or status in (404, 410):
        return "not_found"
    if "EtagMismatch" in names or status == 412:
        return "etag"
    if "ReconnectRequired" in names or status == 401:
        return "reconnect"
    return "other"


# -- the event a task becomes ------------------------------------------------------------------------------------------


def build_draft(title: str, notes: str | None, due_date: date, due_time: str | None, remind_minutes: int, tz: str) -> MirrorDraft:
    reminder = remind_minutes if remind_minutes >= 0 else None
    if due_time:
        start = local_to_utc(due_date, parse_hhmm(due_time), tz).replace(tzinfo=_UTC)
        end = start + timedelta(minutes=EVENT_MINUTES)
        return MirrorDraft(title, start, end, False, notes or "", reminder_minutes=reminder)
    start = datetime.combine(due_date, time(0, 0), tzinfo=_UTC)
    return MirrorDraft(title, start, start + timedelta(days=1), True, notes or "", reminder_minutes=reminder)


@dataclass(frozen=True)
class _Snap:
    mailbox: str
    eligible: bool
    event_id: str | None
    event_user: str | None
    etag: str | None
    draft: MirrorDraft | None


def _snapshot(task: Any, tz: str) -> _Snap:
    eligible = mirror_eligible(task)
    draft = None
    if eligible:
        draft = build_draft(task.title, task.notes, task.due_date, task.due_time, task.remind_minutes_before, tz)
    return _Snap(mailbox_of(task), eligible, task.external_event_id, task.external_account_user_id, task.external_etag, draft)


def _finish(session_factory: Any, task_model: Any, task_id: str, **fields: Any) -> None:
    with session_factory() as session:
        task = session.get(task_model, task_id)
        if task is None:
            return
        for key, value in fields.items():
            setattr(task, key, value)
        session.commit()


def _failure_status(exc: BaseException) -> str:
    return (MirrorStatus.SKIPPED if classify(exc) == "reconnect" else MirrorStatus.FAILED).value


def _lookup(session_factory: Any, providers: MirrorProviders, user_id: str):
    with session_factory() as session:
        return providers.for_user(session, user_id)


def _delete_remote(session_factory: Any, providers: MirrorProviders, user_id: str, event_id: str) -> str | None:
    """None when the event is gone or cannot be reached (drop the pointer); else the failure status to record."""
    found = _lookup(session_factory, providers, user_id)
    if found is None:
        return None  # no live connection in that mailbox: retrying would dead-end forever
    try:
        found[1].delete_event(event_id)
    except Exception as exc:  # noqa: BLE001
        kind = classify(exc)
        if kind == "not_found":
            return None
        if kind == "reconnect":
            LOGGER.warning("task-mirror: old mailbox %s needs reconnecting; dropping the event pointer", user_id)
            return None
        LOGGER.warning("task-mirror: delete of event %s failed: %s", event_id, exc)
        return _failure_status(exc)
    return None


def _upsert(mirror: Any, draft: MirrorDraft, event_id: str | None, etag: str | None) -> Any:
    if not event_id:
        return mirror.create_event(draft)
    patch = asdict(draft)
    try:
        return mirror.update_event(event_id, patch, etag=etag)
    except Exception as exc:
        kind = classify(exc)
        if kind == "not_found":
            return mirror.create_event(draft)
        if kind != "etag":
            raise
    try:
        fresh = mirror.get_event(event_id)
        return mirror.update_event(event_id, patch, etag=fresh.etag)
    except Exception as exc:
        if classify(exc) == "not_found":
            return mirror.create_event(draft)
        raise


def sync_mirror(session_factory: Any, task_model: Any, task_id: str, providers: MirrorProviders, *, tz: str = "UTC") -> None:
    """Reconcile the task's external event with its row. Never raises."""
    try:
        _sync(session_factory, task_model, task_id, providers, tz)
    except Exception:
        LOGGER.warning("task-mirror-degraded: sync of task %s failed", task_id, exc_info=True)


def _sync(session_factory: Any, task_model: Any, task_id: str, providers: MirrorProviders, tz: str) -> None:
    with session_factory() as session:
        task = session.get(task_model, task_id)
        if task is None:
            return
        snap = _snapshot(task, tz)
        session.rollback()  # no transaction is held while the provider answers

    old_event, old_user = snap.event_id, snap.event_user or snap.mailbox
    if old_event and (not snap.eligible or old_user != snap.mailbox):
        failed = _delete_remote(session_factory, providers, old_user, old_event)
        if failed:
            _finish(session_factory, task_model, task_id, mirror_status=failed)  # pointer kept: the next sync retries
            return
        _finish(session_factory, task_model, task_id, external_event_id=None, external_account_user_id=None,
                external_provider=None, external_etag=None)
        old_event = None
    if not snap.eligible:
        _finish(session_factory, task_model, task_id, mirror_status=MirrorStatus.SKIPPED.value)
        return

    found = _lookup(session_factory, providers, snap.mailbox)
    if found is None:
        _finish(session_factory, task_model, task_id, mirror_status=MirrorStatus.SKIPPED.value)
        return
    provider_name, mirror = found
    try:
        event = _upsert(mirror, snap.draft, old_event, snap.etag if old_event else None)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("task-mirror-degraded: write for task %s failed: %s", task_id, exc)
        _finish(session_factory, task_model, task_id, mirror_status=_failure_status(exc))
        return

    # Race guard: the task may have been completed, deleted or reassigned while the provider answered.
    with session_factory() as session:
        task = session.get(task_model, task_id)
        stale = task is None or not mirror_eligible(task) or mailbox_of(task) != snap.mailbox
        pending = task is not None and mirror_eligible(task)
    if stale:
        try:
            mirror.delete_event(event.id)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("task-mirror-degraded: undo of event %s failed: %s", event.id, exc)
        _finish(session_factory, task_model, task_id, external_event_id=None, external_account_user_id=None,
                external_provider=None, external_etag=None,
                mirror_status=(MirrorStatus.PENDING if pending else MirrorStatus.SKIPPED).value)
        return
    fields = {"external_provider": provider_name, "external_event_id": event.id, "external_account_user_id": snap.mailbox,
              "external_etag": getattr(event, "etag", None), "mirror_status": MirrorStatus.MIRRORED.value}
    if _claim_pointer(session_factory, task_model, task_id, old_event, fields) or event.id == old_event:
        return
    # Another sync recorded a different event first (two quick edits both saw no event): ours is the stray one.
    try:
        mirror.delete_event(event.id)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("task-mirror-degraded: removal of duplicate event %s failed: %s", event.id, exc)


def _claim_pointer(session_factory: Any, task_model: Any, task_id: str, expected_event: str | None,
                   fields: dict) -> bool:
    """Record the event only if the row still holds the pointer this pass started from (compare-and-set)."""
    held = task_model.external_event_id == expected_event if expected_event else task_model.external_event_id.is_(None)
    with session_factory() as session:
        changed = session.execute(update(task_model).where(task_model.id == task_id, held).values(**fields)).rowcount
        session.commit()
    return changed == 1


def remove_event(session_factory: Any, providers: MirrorProviders, pointer: MirrorPointer) -> None:
    """Delete one external event (after a hard delete of its task); never raises."""
    try:
        _delete_remote(session_factory, providers, pointer.user_id, pointer.event_id)
    except Exception:
        LOGGER.warning("task-mirror-degraded: removal of event %s failed", pointer.event_id, exc_info=True)
