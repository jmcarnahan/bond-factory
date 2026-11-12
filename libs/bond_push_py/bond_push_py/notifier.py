"""``PushNotifier``: the after-commit notifier for the push channel."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from bond_push_py.devices import devices_for
from bond_push_py.messages import PushMessage
from bond_push_py.protocols import PushSender
from bond_push_py.timeutil import to_naive_utc, utcnow


class PushNotifier:
    """Satisfies the tasks lib's ``Notifier`` by shape: ``send(session, notice) -> "ok" | "retryable" |
    "unregistered" | "failed"``.

    Loads the recipient's live devices (``notice.user_id``), builds one ``PushMessage`` each
    (``collapse_id = notice.notice_id``, ``thread_id = notice.task_id``, ``data = {notice_id, task_id, route}``,
    ``expires_at = notice.created_at + expires_in`` seconds, or now plus ``expires_in`` if that is already past),
    sends, and disables tokens reported unregistered (``disabled_at``). Result, in this order: "retryable" if any
    device was retryable (the notice is sent again later to every live device; Apple's collapse id makes the
    repeat replace the first on a device that already has it); "ok" if any device accepted, or there is no live
    device (by design: a device registered a minute later does not get this notice); "unregistered" if every
    device was unregistered (they are now disabled); otherwise "failed" (a permanent error such as a bad topic
    or an unconfigured sender). Flushes, never commits.

    Only rows whose platform is "ios" are sent to; a user with only web or android rows counts as having no live
    device ("ok"), and those rows are left alone (not disabled). Times are normalised to naive UTC.

    No Apple ``category`` is sent unless ``category`` is given: the phone plugin cannot report which action
    button of a remote notification was pressed, so a tap just opens the task.

    An app that has no real sender must not list the push channel in the sweep's channels: with ``NullSender``
    every send would be "failed".
    """

    def __init__(self, device_model: Any, sender: PushSender, *, expires_in: int = 600,
                 category: str | None = None, now: Callable[[], datetime] = utcnow) -> None:
        self.device_model = device_model
        self.sender = sender
        self.expires_in = expires_in
        self.category = category
        self._now = now

    def send(self, session: Any, notice: Any) -> str:
        devices = devices_for(session, self.device_model, notice.user_id)
        if not devices:
            return "ok"
        now = to_naive_utc(self._now())
        lifetime = timedelta(seconds=self.expires_in)
        expires_at = to_naive_utc(notice.created_at) + lifetime
        if expires_at <= now:
            expires_at = now + lifetime
        data = {"notice_id": notice.notice_id, "task_id": notice.task_id, "route": notice.route}
        messages = [
            PushMessage(
                token=d.token, environment=d.environment, topic=d.topic, title=notice.title, body=notice.body,
                collapse_id=notice.notice_id, data=dict(data), expires_at=expires_at,
                thread_id=notice.task_id, category=self.category,
            )
            for d in devices
        ]
        results = self.sender.send(messages)
        for device, result in zip(devices, results, strict=True):
            if result.unregistered:
                device.disabled_at = now
        session.flush()
        if any(r.retryable for r in results):
            return "retryable"
        if any(r.ok for r in results):
            return "ok"
        if all(r.unregistered for r in results):
            return "unregistered"
        return "failed"
