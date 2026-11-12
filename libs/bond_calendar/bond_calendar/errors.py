"""Typed calendar failures. The caller decides what each one means for its own connection or task."""

from __future__ import annotations


class CalendarError(Exception):
    """Any calendar failure: the HTTP status (0 for none), a short machine code and a readable message."""

    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


class NotFound(CalendarError):
    def __init__(self, message: str = "The event does not exist.", status: int = 404, code: str = "not_found") -> None:
        super().__init__(status, code, message)


class EtagMismatch(CalendarError):
    """The event changed since it was read (HTTP 412). Re-read, merge, retry."""

    def __init__(self, message: str = "The event changed since it was read.", status: int = 412,
                 code: str = "etag_mismatch") -> None:
        super().__init__(status, code, message)


class ReconnectRequired(CalendarError):
    """The provider refused the token (HTTP 401). The caller marks the connection as needing a reconnect."""

    def __init__(self, message: str = "The calendar connection must be re-authorised.", status: int = 401,
                 code: str = "reconnect_required") -> None:
        super().__init__(status, code, message)


class Forbidden(CalendarError):
    """The provider refused the action (HTTP 403): missing scope, a read-only calendar or a policy block.

    ``.code`` keeps the provider's own code (for example ``insufficientPermissions`` or ``ErrorAccessDenied``)."""

    def __init__(self, message: str = "The calendar provider refused the request.", status: int = 403,
                 code: str = "forbidden") -> None:
        super().__init__(status, code, message)


class Unavailable(CalendarError):
    """A 5xx, 429, timeout or transport failure: transient, retry later. A Google 403 that is a throttle
    (``rateLimitExceeded`` and the like) is this too: status 403, ``.code`` is the reason."""

    def __init__(self, message: str = "The calendar service is unavailable.", status: int = 503,
                 code: str = "unavailable") -> None:
        super().__init__(status, code, message)
