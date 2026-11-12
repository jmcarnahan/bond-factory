"""Coded errors. ``code`` is the wire contract (REST detail code)."""

#: code -> (HTTP status, default message)
CODES: dict[str, tuple[int, str]] = {
    "capture_denied": (429, "Too many requests. Try again later."),
    "text_required": (422, "Some text is required."),
    "text_too_long": (422, "The text is too long."),
    "model_unavailable": (503, "The model is unavailable."),
    "invalid_output": (502, "The model's answer could not be used."),
}


class CaptureError(Exception):
    """``CaptureError(code, message=None, status=None)``; message and status default from the code table."""

    default_code = "invalid_output"

    def __init__(self, code: str | None = None, message: str | None = None, status: int | None = None) -> None:
        code = code or self.default_code
        known_status, known_message = CODES.get(code, (422, code.replace("_", " ")))
        self.code = code
        self.message = message or known_message
        self.status = status or known_status
        super().__init__(f"{code}: {self.message}")


class LlmUnavailable(CaptureError):
    """Timeout, outage or no client: the caller returns a degraded draft with reason ``model_unavailable``."""

    default_code = "model_unavailable"


class LlmInvalid(CaptureError):
    """The answer broke the schema: degraded draft with reason ``invalid_output``."""

    default_code = "invalid_output"


class CaptureDenied(CaptureError):
    """Raised by a ``CaptureGuard``; the route answers 429."""

    default_code = "capture_denied"
