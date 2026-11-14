from datetime import datetime, timedelta, timezone

import httpx
from test_apns import T0, TOKEN, Apple, Clock, epoch, keys, make, msg  # noqa: F401

from bond_push_py import ApnsSender, PushResult

EXPIRED = (403, {"reason": "ExpiredProviderToken"})


def test_forced_refresh_happens_at_most_once_per_20_minutes(keys):  # noqa: F811
    clock = Clock()
    sender, apple = make(keys, EXPIRED, clock=clock)  # Apple keeps answering ExpiredProviderToken
    first = sender.send([msg()])[0]
    assert len(apple.requests) == 2  # first request, then one forced refresh and one retry
    assert first == PushResult(ok=False, retryable=True, error="ExpiredProviderToken")
    token_after_refresh = apple.requests[1].headers["authorization"]

    clock.t = T0 + timedelta(minutes=19, seconds=59)
    second = sender.send([msg()])[0]
    assert len(apple.requests) == 3  # no second refresh and no retry inside the window
    assert apple.requests[2].headers["authorization"] == token_after_refresh
    assert second == PushResult(ok=False, retryable=True, error="ExpiredProviderToken")

    clock.t = T0 + timedelta(minutes=20)
    sender.send([msg()])
    assert len(apple.requests) == 5  # the window is over: refresh and retry again
    assert apple.requests[4].headers["authorization"] != token_after_refresh


def test_payload_over_4096_bytes_is_permanent_and_never_sent(keys):  # noqa: F811
    sender, apple = make(keys)
    big = msg(data={"blob": "x" * 4100})
    assert sender.send([big]) == [PushResult(ok=False, error="payload_too_large")]
    assert apple.requests == []
    ok = msg(data={"blob": "x" * 3000})
    assert sender.send([ok]) == [PushResult(ok=True)]


def test_a_missing_http2_library_is_retryable(keys, monkeypatch):  # noqa: F811
    def no_h2(**kw):
        raise ImportError("Using http2=True, but the 'h2' package is not installed.")

    monkeypatch.setattr(httpx, "Client", no_h2)
    sender = ApnsSender(keys[0], "K", "T")
    assert sender.send([msg()]) == [PushResult(ok=False, retryable=True, error="http2_unavailable")]


class Closable(httpx.Client):
    closed = 0

    def close(self):
        type(self).closed += 1
        super().close()


def test_close_closes_a_client_the_sender_built(keys, monkeypatch):  # noqa: F811
    Closable.closed = 0
    built = []

    def factory(**kw):
        client = Closable(transport=httpx.MockTransport(Apple()))
        built.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", factory)
    sender = ApnsSender(keys[0], "K", "T")
    sender.close()  # nothing built yet: harmless
    assert Closable.closed == 0
    sender.send([msg()])
    sender.close()
    assert Closable.closed == 1 and sender.client is None
    sender.close()  # idempotent
    assert Closable.closed == 1


def test_a_client_passed_in_is_not_closed_and_the_context_manager_closes_only_owned_ones(keys, monkeypatch):  # noqa: F811
    Closable.closed = 0
    mine = Closable(transport=httpx.MockTransport(Apple()))
    with ApnsSender(keys[0], "K", "T", client=mine) as sender:
        sender.send([msg()])
    assert Closable.closed == 0 and sender.client is mine

    monkeypatch.setattr(httpx, "Client", lambda **kw: Closable(transport=httpx.MockTransport(Apple())))
    with ApnsSender(keys[0], "K", "T") as owner:
        owner.send([msg()])
    assert Closable.closed == 1


def test_aware_times_are_converted_to_utc(keys):  # noqa: F811
    plus5 = timezone(timedelta(hours=5))
    sender, apple = make(keys, clock=lambda: datetime(2026, 11, 12, 20, 0, 0, tzinfo=plus5))  # 15:00 UTC
    sender.send([msg(expires_at=datetime(2026, 11, 12, 20, 10, 0, tzinfo=plus5))])
    assert apple.requests[0].headers["apns-expiration"] == str(epoch(datetime(2026, 11, 12, 15, 10, 0)))


def test_bad_badge_or_interruption_level_is_coded_and_not_sent(keys):  # noqa: F811
    sender, apple = make(keys)
    for badge in (-1, True, "3", 1.5):
        result = sender.send([msg(badge=badge)])[0]
        assert result == PushResult(ok=False, error="invalid_badge")
        assert not result.retryable
    for level in ("urgent", "", ["active"], 1):
        result = sender.send([msg(interruption_level=level)])[0]
        assert result == PushResult(ok=False, error="invalid_interruption_level")
        assert not result.retryable
    assert apple.requests == []
