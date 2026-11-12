"""One coded error for every refusal. ``code`` is the wire contract (REST detail code and sync verdict message)."""

#: code -> (HTTP status, default message)
CODES: dict[str, tuple[int, str]] = {
    "invalid_platform": (422, "Platform must be ios, android or web."),
    "invalid_environment": (422, "Environment must be sandbox or production."),
    "token_required": (422, "A device token is required."),
    "device_id_required": (422, "A device id is required."),
    "push_not_configured": (503, "Push is not configured."),
    "token_too_long": (422, "The device token is too long."),
    "device_id_too_long": (422, "The device id is too long."),
    "invalid_topic": (422, "The topic must be text."),
    "topic_too_long": (422, "The topic is too long."),
    "device_not_found": (404, "No such device."),
    "not_device_owner": (403, "That device belongs to another user."),
    "device_conflict": (409, "That device id is already in use."),
}


class PushError(Exception):
    """``PushError(code, message=None, status=None)``; message and status default from the code table."""

    def __init__(self, code: str, message: str | None = None, status: int | None = None) -> None:
        known_status, known_message = CODES.get(code, (422, code.replace("_", " ")))
        self.code = code
        self.message = message or known_message
        self.status = status or known_status
        super().__init__(f"{code}: {self.message}")
