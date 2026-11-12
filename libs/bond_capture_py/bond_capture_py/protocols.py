"""The seams the host fills. Text is never logged by any of them."""

from typing import Protocol


class LlmClient(Protocol):
    def complete_json(self, system: str, user: str, schema: dict, timeout_s: float) -> dict:
        """Return the parsed JSON object the model answered. Raise ``LlmUnavailable`` on timeout or outage."""
        ...


class EntityResolver(Protocol):
    def resolve(self, user_id: str, name: str, kind: str) -> list[dict]:
        """Candidates for a name as written, ``[{id, label}]``, best first. The user's own data only."""
        ...


class CaptureGuard(Protocol):
    def check(self, user_id: str, text: str) -> None:
        """Raise ``CaptureDenied`` to refuse the call (spend or rate limit); the app owns the policy."""
        ...
