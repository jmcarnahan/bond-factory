import calendar
import json
from datetime import datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from bond_push_py import APNS_HOST_PRODUCTION, APNS_HOST_SANDBOX, ApnsSender, PushMessage, PushResult

T0 = datetime(2026, 11, 12, 15, 0, 0)
TOKEN = "ab" * 32


def epoch(moment):
    return calendar.timegm(moment.timetuple())


@pytest.fixture(scope="module")
def keys():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return pem, key.public_key()


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


class Apple:
    """A mock transport that records requests and replays a list of (status, json) answers."""

    def __init__(self, *answers):
        self.answers = list(answers) or [(200, None)]
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        status, body = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(body, Exception):
            raise body
        return httpx.Response(status, json=body)


def make(keys, *answers, clock=None):
    apple = Apple(*answers)
    client = httpx.Client(transport=httpx.MockTransport(apple))
    sender = ApnsSender(keys[0], "KEYID12345", "TEAMID6789", client=client, now=clock or Clock())
    return sender, apple


def msg(**kw):
    base = {"token": TOKEN, "environment": "sandbox", "topic": "com.example.app", "title": "Due", "body": "Now"}
    base.update(kw)
    return PushMessage(**base)


def test_full_message_headers_and_body(keys):
    sender, apple = make(keys)
    m = msg(collapse_id="n" * 32, data={"notice_id": "n1", "task_id": "t1", "route": "/tasks/t1"},
            expires_at=datetime(2026, 11, 12, 15, 10, 0), priority=5, thread_id="t1", category="bond.task")
    assert sender.send([m]) == [PushResult(ok=True)]
    (req,) = apple.requests
    assert req.method == "POST"
    assert str(req.url) == f"{APNS_HOST_SANDBOX}/3/device/{TOKEN}"
    h = req.headers
    assert h["apns-topic"] == "com.example.app"
    assert h["apns-push-type"] == "alert"
    assert h["apns-priority"] == "5"
    assert h["apns-expiration"] == str(epoch(datetime(2026, 11, 12, 15, 10, 0)))
    assert h["apns-collapse-id"] == "n" * 32
    scheme, _, token = h["authorization"].partition(" ")
    assert scheme == "bearer"
    assert jwt.get_unverified_header(token) == {"alg": "ES256", "kid": "KEYID12345", "typ": "JWT"}
    claims = jwt.decode(token, keys[1], algorithms=["ES256"], options={"verify_iat": False})
    assert claims == {"iss": "TEAMID6789", "iat": epoch(T0)}
    assert json.loads(req.content) == {
        "aps": {"alert": {"title": "Due", "body": "Now"}, "sound": "default", "thread-id": "t1",
                "category": "bond.task"},
        "notice_id": "n1", "task_id": "t1", "route": "/tasks/t1",
    }


def test_minimal_message_has_no_optional_fields(keys):
    sender, apple = make(keys)
    sender.send([msg()])
    req = apple.requests[0]
    assert req.headers["apns-expiration"] == "0"
    assert "apns-collapse-id" not in req.headers
    assert json.loads(req.content) == {"aps": {"alert": {"title": "Due", "body": "Now"}, "sound": "default"}}


def test_category_only_when_given(keys):
    sender, apple = make(keys)
    sender.send([msg(), msg(category="bond.task")])
    first, second = (json.loads(r.content)["aps"] for r in apple.requests)
    assert "category" not in first and second["category"] == "bond.task"


def test_data_cannot_replace_aps(keys):
    sender, apple = make(keys)
    sender.send([msg(data={"aps": {"evil": 1}, "x": 1})])
    body = json.loads(apple.requests[0].content)
    assert body["aps"]["alert"]["title"] == "Due" and body["x"] == 1


def test_host_follows_environment(keys):
    sender, apple = make(keys)
    sender.send([msg(environment="sandbox"), msg(environment="production")])
    assert str(apple.requests[0].url).startswith(APNS_HOST_SANDBOX)
    assert str(apple.requests[1].url).startswith(APNS_HOST_PRODUCTION)


def test_provider_token_is_reused_then_refreshed_after_50_minutes(keys):
    clock = Clock()
    sender, apple = make(keys, clock=clock)
    sender.send([msg()])
    clock.t = T0 + timedelta(minutes=49, seconds=59)
    sender.send([msg()])
    clock.t = T0 + timedelta(minutes=50)
    sender.send([msg()])
    tokens = [r.headers["authorization"] for r in apple.requests]
    assert tokens[0] == tokens[1] != tokens[2]
    iat = jwt.decode(tokens[2].split()[1], keys[1], algorithms=["ES256"], options={"verify_iat": False})["iat"]
    assert iat == epoch(T0 + timedelta(minutes=50))


def test_expired_provider_token_refreshes_once_and_retries(keys):
    sender, apple = make(keys, (403, {"reason": "ExpiredProviderToken"}), (200, None))
    assert sender.send([msg()]) == [PushResult(ok=True)]
    assert len(apple.requests) == 2
    assert apple.requests[0].headers["authorization"] != apple.requests[1].headers["authorization"]


def test_expired_token_is_retried_only_once(keys):
    sender, apple = make(keys, (403, {"reason": "ExpiredProviderToken"}))
    result = sender.send([msg()])[0]
    assert len(apple.requests) == 2
    assert result == PushResult(ok=False, retryable=True, error="ExpiredProviderToken")


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, None, PushResult(ok=True)),
        (410, {"reason": "Unregistered"}, PushResult(ok=False, unregistered=True, error="Unregistered")),
        (410, None, PushResult(ok=False, unregistered=True, error="Unregistered")),
        (400, {"reason": "BadDeviceToken"}, PushResult(ok=False, unregistered=True, error="BadDeviceToken")),
        (400, {"reason": "DeviceTokenNotForTopic"},
         PushResult(ok=False, unregistered=True, error="DeviceTokenNotForTopic")),
        (400, {"reason": "Unregistered"}, PushResult(ok=False, unregistered=True, error="Unregistered")),
        (429, {"reason": "TooManyRequests"}, PushResult(ok=False, retryable=True, error="TooManyRequests")),
        (500, {"reason": "InternalServerError"},
         PushResult(ok=False, retryable=True, error="InternalServerError")),
        (503, {"reason": "ServiceUnavailable"}, PushResult(ok=False, retryable=True, error="ServiceUnavailable")),
        (400, {"reason": "PayloadEmpty"}, PushResult(ok=False, error="PayloadEmpty")),
        (403, {"reason": "InvalidProviderToken"},
         PushResult(ok=False, retryable=True, error="InvalidProviderToken")),
        (403, {"reason": "BadCertificate"}, PushResult(ok=False, retryable=True, error="BadCertificate")),
        (403, None, PushResult(ok=False, retryable=True, error="403")),
        (408, None, PushResult(ok=False, retryable=True, error="408")),
        (502, None, PushResult(ok=False, retryable=True, error="502")),
        (504, None, PushResult(ok=False, retryable=True, error="504")),
        (413, None, PushResult(ok=False, error="payload_too_large")),
        (413, {"reason": "PayloadTooLarge"}, PushResult(ok=False, error="payload_too_large")),
    ],
)
def test_status_mapping(keys, status, body, expected):
    sender, _ = make(keys, (status, body))
    assert sender.send([msg()]) == [expected]


def test_missing_topic_sends_no_request(keys):
    sender, apple = make(keys)
    assert sender.send([msg(topic=None)]) == [PushResult(ok=False, error="topic_required")]
    assert apple.requests == []


def test_long_collapse_id_and_bad_environment_send_no_request(keys):
    sender, apple = make(keys)
    results = sender.send([msg(collapse_id="x" * 65), msg(environment="staging")])
    assert [r.error for r in results] == ["collapse_id_too_long", "invalid_environment"]
    assert apple.requests == []


def test_transport_errors_are_retryable_and_leak_no_token(keys):
    sender, _ = make(keys, (0, httpx.ConnectTimeout(f"timed out for {TOKEN}")))
    (result,) = sender.send([msg()])
    assert result.ok is False and result.retryable is True
    assert TOKEN not in (result.error or "")


def test_one_failure_does_not_stop_the_batch(keys):
    sender, _ = make(keys, (500, None), (200, None))
    assert [r.ok for r in sender.send([msg(token="a"), msg(token="b")])] == [False, True]


def test_bad_key_is_a_result_not_an_exception():
    client = httpx.Client(transport=httpx.MockTransport(Apple()))
    sender = ApnsSender("not a key", "K", "T", client=client)
    assert sender.send([msg()]) == [PushResult(ok=False, error="provider_token_error")]


def test_client_is_built_lazily_with_http2(keys, monkeypatch):
    made = {}

    class Fake(httpx.Client):
        def __init__(self, **kw):
            made.update(kw)
            super().__init__(transport=httpx.MockTransport(Apple()))

    monkeypatch.setattr(httpx, "Client", Fake)
    sender = ApnsSender(keys[0], "K", "T")
    assert made == {}
    sender.send([msg()])
    assert made["http2"] is True and made["timeout"] == 10.0
