"""``DefaultPermissions``: today's rules. Editors are the owner and the assignee; the owner alone deletes, cancels
and reassigns; whoever can edit can complete. A missing user id (None or "") can do nothing, even on a task
that has no assignee."""

from typing import Any


class DefaultPermissions:
    def can_edit(self, task: Any, user_id: str | None) -> bool:
        return bool(user_id) and user_id in (task.owner_user_id, task.assigned_user_id)

    def can_own(self, task: Any, user_id: str | None) -> bool:
        return bool(user_id) and user_id == task.owner_user_id

    def can_complete(self, task: Any, user_id: str | None) -> bool:
        return self.can_edit(task, user_id)
