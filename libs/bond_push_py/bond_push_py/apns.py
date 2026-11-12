"""``ApnsSender``: Apple push over HTTP/2 with a cached ES256 provider token.

Importing this module needs no ``h2`` and no network: the HTTP/2 client is built lazily in ``send``, and a test
passes ``client`` (an ``httpx.Client`` with a mock transport). Neither the device token nor the key is ever
logged or put in an error string.
"""

import calendar
import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any, Self

import httpx
import jwt

from bond_push_py.messages import PushMessage, PushResult
from bond_push_py.timeutil import to_naive_utc, utcnow

APNS_HOST_PRODUCTION = "https://api.push.apple.com"
APNS_HOST_SANDBOX = "https://api.sandbox.push.apple.com"

#: Apple rejects a provider token older than 60 minutes; this one is reused for 50.
TOKEN_REUSE = timedelta(minutes=50)
TIMEOUT_SECONDS = 10.0
#: Reasons that mean this token is dead for this topic and host (status 400 or 410).
DEAD_TOKEN_REASONS = {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
#: Apple refuses a provider-token refresh more often than every 20 minutes.
FORCED_REFRESH_GAP = timedelta(minutes=20)
MAX_PAYLOAD_BYTES = 4096


def _epoch(moment: datetime) -> int:
    return calendar.timegm(to_naive_utc(moment).timetuple())


def _reason(response: Any) -> str | None:
    try:
        reason = response.json().get("reason")
    except (ValueError, AttributeError):
        return None
    return reason if isinstance(reason, str) else None


class ApnsSender:
    """``ApnsSender(key_pem, key_id, team_id, *, client=None, now=None)``, a ``PushSender``.

    One provider JWT (ES256, ``iss`` team id, ``kid`` key id) is cached 50 minutes; a 403 ``ExpiredProviderToken``
    mints a new one and retries that message once. Each message is a POST to ``/3/device/<token>`` on the host
    that matches its environment. 200 is ok; 410, and 400 with ``BadDeviceToken`` / ``DeviceTokenNotForTopic`` /
    ``Unregistered``, are ``unregistered``. Retryable (the notice is tried again later): 408, 429, 500, 502, 503,
    504, transport errors, a missing HTTP/2 library, and every 403 (a bad or expired key, a wrong key id: a
    deployment mistake must not burn notices for good, so they retry until the sweep's attempt limit while the
    operator fixes it). 413 and an oversize payload (over 4096 bytes, never sent) are permanent
    ``payload_too_large``; any other status is ``ok=False`` with Apple's reason. A forced provider-token refresh
    happens at most once per 20 minutes (Apple's limit); a second ``ExpiredProviderToken`` inside that window is
    retryable without a new token. ``now`` is a callable returning UTC (tests inject it).

    Use one sender per process: it owns the token cache and the HTTP/2 connection. ``close()`` (or ``with``)
    closes a client the sender built; a ``client`` passed in stays the caller's.
    """

    def __init__(self, key_pem: str, key_id: str, team_id: str, *, client: Any = None,
                 now: Callable[[], datetime] | None = None) -> None:
        self.key_pem = key_pem
        self.key_id = key_id
        self.team_id = team_id
        self.client = client
        self._owns_client = False
        self._now = now or utcnow
        self._jwt: str | None = None
        self._jwt_at: datetime | None = None
        self._forced_at: datetime | None = None

    def close(self) -> None:
        """Close the HTTP client this sender built (a client given to the constructor is not touched)."""
        if self._owns_client and self.client is not None:
            self.client.close()
            self.client = None
            self._owns_client = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _provider_token(self, *, force: bool = False) -> str:
        moment = to_naive_utc(self._now())
        if force or self._jwt is None or self._jwt_at is None or moment - self._jwt_at >= TOKEN_REUSE:
            self._jwt = jwt.encode({"iss": self.team_id, "iat": _epoch(moment)}, self.key_pem,
                                   algorithm="ES256", headers={"kid": self.key_id})
            self._jwt_at = moment
        return self._jwt

    def _http(self) -> Any:
        if self.client is None:
            self.client = httpx.Client(http2=True, timeout=TIMEOUT_SECONDS)  # h2 loads here, not at import
            self._owns_client = True
        return self.client

    def send(self, messages: Sequence[PushMessage]) -> list[PushResult]:
        results = []
        for message in messages:
            try:
                results.append(self._send_one(message))
            except httpx.HTTPError as exc:  # the class name carries no token; its text might
                results.append(PushResult(ok=False, retryable=True, error=type(exc).__name__))
            except ImportError:  # no h2: a deployment mistake, so keep the notice for a retry
                results.append(PushResult(ok=False, retryable=True, error="http2_unavailable"))
            except Exception as exc:  # noqa: BLE001 - never raise for one message
                results.append(PushResult(ok=False, error=f"send_error_{type(exc).__name__}"))
        return results

    @staticmethod
    def _headers(message: PushMessage, provider_token: str) -> dict[str, str]:
        headers = {
            "authorization": f"bearer {provider_token}",
            "apns-topic": message.topic or "",
            "apns-push-type": "alert",
            "apns-priority": str(message.priority),
            "apns-expiration": str(_epoch(message.expires_at)) if message.expires_at else "0",
        }
        if message.collapse_id:
            headers["apns-collapse-id"] = message.collapse_id
        return headers

    @staticmethod
    def _body(message: PushMessage) -> dict:
        aps: dict[str, Any] = {"alert": {"title": message.title, "body": message.body}, "sound": "default"}
        if message.thread_id:
            aps["thread-id"] = message.thread_id
        if message.category:
            aps["category"] = message.category
        body: dict[str, Any] = {k: v for k, v in message.data.items() if k != "aps"}
        body["aps"] = aps
        return body

    def _post(self, message: PushMessage, content: bytes, provider_token: str) -> Any:
        host = APNS_HOST_SANDBOX if message.environment == "sandbox" else APNS_HOST_PRODUCTION
        return self._http().post(
            f"{host}/3/device/{message.token}",
            headers=self._headers(message, provider_token),
            content=content,
            timeout=TIMEOUT_SECONDS,
        )

    def _send_one(self, message: PushMessage) -> PushResult:
        if not message.topic:
            return PushResult(ok=False, error="topic_required")
        if message.environment not in ("sandbox", "production"):
            return PushResult(ok=False, error="invalid_environment")
        if message.collapse_id and len(message.collapse_id.encode()) > 64:
            return PushResult(ok=False, error="collapse_id_too_long")
        content = json.dumps(self._body(message), separators=(",", ":")).encode()
        if len(content) > MAX_PAYLOAD_BYTES:
            return PushResult(ok=False, error="payload_too_large")
        try:
            provider_token = self._provider_token()
        except Exception:  # noqa: BLE001 - a malformed key; the key must not leak into the error
            return PushResult(ok=False, error="provider_token_error")
        response = self._post(message, content, provider_token)
        if response.status_code == 403 and _reason(response) == "ExpiredProviderToken":
            moment = to_naive_utc(self._now())
            if self._forced_at is None or moment - self._forced_at >= FORCED_REFRESH_GAP:
                self._forced_at = moment
                response = self._post(message, content, self._provider_token(force=True))
        return self._result(response)

    @staticmethod
    def _result(response: Any) -> PushResult:
        status = response.status_code
        if status == 200:
            return PushResult(ok=True)
        reason = _reason(response)
        if status == 413:
            return PushResult(ok=False, error="payload_too_large")
        if status == 410 or reason in DEAD_TOKEN_REASONS:
            return PushResult(ok=False, unregistered=True, error=reason or "Unregistered")
        if status == 403 or status in RETRYABLE_STATUS:  # 403: key or provider token trouble, the operator fixes it
            return PushResult(ok=False, retryable=True, error=reason or str(status))
        return PushResult(ok=False, error=reason or str(status))
