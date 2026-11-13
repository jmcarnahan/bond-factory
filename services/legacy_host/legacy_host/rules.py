"""The app's own rules for a task: who may relink it, what a case implies, and who counts as an editor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bond_tasks_py import DefaultPermissions, TaskError

from .models import HOST_COLUMNS, Case, User


def is_admin(session: Any, user_id: str | None) -> bool:
    row = session.get(User, user_id) if user_id else None
    return bool(row is not None and row.is_admin)


class LegacyPermissions(DefaultPermissions):
    """Owner and assignee edit (the lib default); an admin edits, completes and owns any task."""

    def __init__(self, admin: Callable[[str | None], bool]) -> None:
        self._admin = admin

    def can_edit(self, task: Any, user_id: str | None) -> bool:
        return self._admin(user_id) or super().can_edit(task, user_id)

    def can_own(self, task: Any, user_id: str | None) -> bool:
        return self._admin(user_id) or super().can_own(task, user_id)


def permissions_for(session: Any) -> LegacyPermissions:
    return LegacyPermissions(lambda user_id: is_admin(session, user_id))


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def prepare(session: Any, task: Any | None, actor_user_id: str, extras: dict) -> dict:
    """The lib's `prepare` hook. (a) A blank link is NULL. (b) Changing `client_ref` or `case_ref` on a stored task
    needs the owner or an admin; the same value sent again is not a change. (c) A case implies its client."""
    out = {name: _blank_to_none(extras[name]) for name in HOST_COLUMNS if name in extras}
    case_id = out.get("case_ref")
    if case_id and out.get("client_ref") is None and (task is None or case_id != task.case_ref):
        case = session.get(Case, case_id)
        if case is not None and case.client_id:
            out["client_ref"] = case.client_id
    if task is not None:
        changed = [name for name, value in out.items() if value != getattr(task, name)]
        if changed and task.owner_user_id != actor_user_id and not is_admin(session, actor_user_id):
            raise TaskError("not_task_owner", "Only the owner can link a task to a client or case.", 403)
        out = {name: out[name] for name in changed}
    return out
