"""Senders that need no network: ``NullSender`` (not configured) and ``MockSender`` (tests and demos)."""

from collections.abc import Sequence

from bond_push_py.messages import PushMessage, PushResult


class NullSender:
    """Used when no Apple key is configured: every message fails as ``push_not_configured`` (not retryable)."""

    def send(self, messages: Sequence[PushMessage]) -> list[PushResult]:
        return [PushResult(ok=False, error="push_not_configured") for _ in messages]


class MockSender:
    """Records every message in ``sent``. ``fail`` (a ``PushResult``) is returned for every message while set;
    ``fail_tokens`` maps a token to the ``PushResult`` returned for that token only."""

    def __init__(self, fail: PushResult | None = None, fail_tokens: dict[str, PushResult] | None = None) -> None:
        self.sent: list[PushMessage] = []
        self.fail = fail
        self.fail_tokens: dict[str, PushResult] = dict(fail_tokens or {})

    def send(self, messages: Sequence[PushMessage]) -> list[PushResult]:
        results = []
        for message in messages:
            self.sent.append(message)
            if message.token in self.fail_tokens:
                results.append(self.fail_tokens[message.token])
            elif self.fail is not None:
                results.append(self.fail)
            else:
                results.append(PushResult(ok=True))
        return results
