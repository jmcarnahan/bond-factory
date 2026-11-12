import dataclasses
import re
from datetime import datetime

import pytest
from conftest import PushDevice, fixture

from bond_push_py import (
    APNS_HOST_PRODUCTION,
    APNS_HOST_SANDBOX,
    ApnsSender,
    MockSender,
    NullSender,
    PushError,
    PushMessage,
    PushNotifier,
    PushResult,
    device_routes,
    devices_for,
    register_device,
    unregister_device,
)

NOW = datetime(2026, 11, 12, 15, 0, 0)


def message(token="t1", **kw) -> PushMessage:
    return PushMessage(token=token, environment="sandbox", topic="com.example.app", title="Due", body="Now", **kw)


def test_message_defaults_and_frozen():
    m = message(collapse_id="n1", category="bond.task")
    assert m.priority == 10 and m.data == {} and m.thread_id is None and m.expires_at is None
    assert m.category == "bond.task"
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.title = "x"
    assert [f.name for f in dataclasses.fields(PushMessage)] == [
        "token", "environment", "topic", "title", "body", "collapse_id", "data", "expires_at", "priority",
        "thread_id", "category",
    ]
    assert [f.name for f in dataclasses.fields(PushResult)] == ["ok", "unregistered", "retryable", "error"]


def test_null_sender_fails_every_message_as_not_configured():
    results = NullSender().send([message("a"), message("b")])
    assert results == [PushResult(ok=False, error="push_not_configured")] * 2
    assert NullSender().send([]) == []


def test_mock_sender_records_and_can_fail():
    sender = MockSender()
    assert sender.send([message("a")]) == [PushResult(ok=True)]
    sender.fail = PushResult(ok=False, retryable=True, error="503")
    assert sender.send([message("b")])[0].retryable is True
    sender.fail = None
    sender.fail_tokens["c"] = PushResult(ok=False, unregistered=True, error="BadDeviceToken")
    results = sender.send([message("c"), message("d")])
    assert [r.ok for r in results] == [False, True] and results[0].unregistered
    assert [m.token for m in sender.sent] == ["a", "b", "c", "d"]


def test_apns_hosts_and_constructor_need_no_network():
    assert APNS_HOST_PRODUCTION == "https://api.push.apple.com"
    assert APNS_HOST_SANDBOX == "https://api.sandbox.push.apple.com"
    sender = ApnsSender("pem", "KEYID", "TEAMID")
    assert sender.client is None


def test_device_fixture_shape():
    item = fixture("device_register.json")
    assert re.fullmatch(r"[0-9a-f]{64}", item["token"])
    assert set(item) == {"token", "platform", "environment", "topic", "device_id"}
    assert item["platform"] == "ios" and item["environment"] == "sandbox"


def test_stubs_raise_not_implemented():
    calls = [
        lambda: ApnsSender("pem", "k", "t").send([message()]),
        lambda: PushNotifier(PushDevice, MockSender()).send(None, object()),
        lambda: register_device(None, PushDevice, user_id="u", device_id="d", token="t", platform="ios",
                                environment="sandbox", topic=None, now=NOW),
        lambda: unregister_device(None, PushDevice, user_id="u", device_id="d"),
        lambda: devices_for(None, PushDevice, "u"),
        lambda: device_routes(PushDevice),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError):
            call()


def test_notifier_defaults_and_error_codes():
    assert PushNotifier(PushDevice, MockSender()).expires_in == 600
    assert PushError("invalid_environment").status == 422
