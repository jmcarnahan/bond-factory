"""One coded error for every refusal. ``code`` is the wire contract (REST detail code and sync verdict message)."""

#: code -> (HTTP status, default message)
CODES: dict[str, tuple[int, str]] = {
    "not_task_editor": (403, "Only the owner or the assignee can change this task."),
    "not_task_owner": (403, "Only the owner can do that."),
    "task_not_found": (404, "Task not found."),
    "checklist_item_not_found": (404, "Checklist item not found."),
    "unknown_assignee": (422, "That user does not exist."),
    "title_required": (422, "A title is required."),
    "due_time_requires_date": (422, "A due time needs a due date."),
    "id_taken": (409, "That id is already in use."),
    "invalid_time_zone": (422, "That time zone is not known."),
    "invalid_priority": (422, "Priority is 1 (low), 2 (normal) or 3 (high)."),
}


class TaskError(Exception):
    """``TaskError(code, message=None, status=None)``; message and status default from the code table."""

    def __init__(self, code: str, message: str | None = None, status: int | None = None) -> None:
        known_status, known_message = CODES.get(code, (422, code.replace("_", " ")))
        self.code = code
        self.message = message or known_message
        self.status = status or known_status
        super().__init__(f"{code}: {self.message}")
