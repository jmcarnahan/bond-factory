"""One coded error for every refusal. ``code`` is the wire contract (REST detail code and sync verdict message)."""

#: code -> (HTTP status, default message)
CODES: dict[str, tuple[int, str]] = {
    "notice_not_found": (404, "Notice not found."),
    "not_notice_owner": (403, "That notice belongs to someone else."),
    "invalid_cursor": (422, "That page cursor is not valid."),
}


class NoticeError(Exception):
    """``NoticeError(code, message=None, status=None)``; message and status default from the code table."""

    def __init__(self, code: str, message: str | None = None, status: int | None = None) -> None:
        known_status, known_message = CODES.get(code, (422, code.replace("_", " ")))
        self.code = code
        self.message = message or known_message
        self.status = status or known_status
        super().__init__(f"{code}: {self.message}")
