"""``ApnsSender``: Apple push over HTTP/2 with a cached ES256 provider token.

Importing this module needs neither ``h2`` nor a network: the HTTP client is built lazily in ``send``,
and a test passes ``client`` (an ``httpx.Client`` with a mock transport).
"""

from collections.abc import Sequence
from typing import Any

from bond_push_py.messages import PushMessage, PushResult

APNS_HOST_PRODUCTION = "https://api.push.apple.com"
APNS_HOST_SANDBOX = "https://api.sandbox.push.apple.com"


class ApnsSender:
    """``ApnsSender(key_pem, key_id, team_id, *, client=None)``, a ``PushSender``.

    Intended behaviour: one provider JWT (ES256, ``iss`` team id, ``kid`` key id) cached about 50 minutes, refreshed before
    Apple's 60-minute limit; POST ``/3/device/<token>`` to the host that matches ``message.environment``;
    headers ``apns-topic``, ``apns-collapse-id``, ``apns-priority``, ``apns-expiration``, ``apns-push-type:
    alert``; body ``{"aps": {"alert": {title, body}, "category", "thread-id", "sound": "default"}, **data}``.
    410 and ``BadDeviceToken`` / ``Unregistered`` give ``unregistered``; 429 and 5xx give ``retryable``.
    """

    def __init__(self, key_pem: str, key_id: str, team_id: str, *, client: Any = None) -> None:
        self.key_pem = key_pem
        self.key_id = key_id
        self.team_id = team_id
        self.client = client

    def send(self, messages: Sequence[PushMessage]) -> list[PushResult]:
        raise NotImplementedError("apns.ApnsSender.send is not implemented yet")
