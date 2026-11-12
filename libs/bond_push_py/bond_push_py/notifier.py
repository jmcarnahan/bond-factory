"""``PushNotifier``: the after-commit notifier for the push channel."""

from typing import Any

from bond_push_py.protocols import PushSender


class PushNotifier:
    """Satisfies the tasks lib's ``Notifier`` by shape: ``send(session, notice) -> "ok" | "retryable" |
    "unregistered" | "failed"``.

    Intended behaviour: load the recipient's live devices (``notice.user_id``), build one ``PushMessage`` each
    (``collapse_id = notice.notice_id``, ``category = "bond.task"``, ``data = {notice_id, task_id, route}``,
    ``expires_at = notice.created_at + expires_in`` seconds), send, disable tokens reported unregistered
    (``disabled_at``). Result: "ok" if any device accepted, or there is no live device; "unregistered" if every
    device was unregistered (they are now disabled); "retryable" if any device was retryable and none accepted;
    otherwise "failed" (a permanent error such as a bad topic or an unconfigured sender). Flushes, never commits.

    An app that has no real sender must not list the push channel in the sweep's channels: with ``NullSender``
    every send would be "failed".
    """

    def __init__(self, device_model: Any, sender: PushSender, *, expires_in: int = 600) -> None:
        self.device_model = device_model
        self.sender = sender
        self.expires_in = expires_in

    def send(self, session: Any, notice: Any) -> str:
        raise NotImplementedError("notifier.PushNotifier.send is not implemented yet")
