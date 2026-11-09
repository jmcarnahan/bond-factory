from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from bond_service_kit import (
    Clock,
    RateLimiter,
    install_error_handlers,
    limiters,
    parse_rate,
    rate_limit_dependency,
)

LA = ZoneInfo("America/Los_Angeles")


def test_freeze_now_today_and_unfreeze():
    c = Clock()
    c.freeze(datetime(2027, 1, 5, 23, 30, tzinfo=LA))
    assert c.frozen and c.now() == datetime(2027, 1, 6, 7, 30, tzinfo=UTC)
    assert c.today(LA).isoformat() == "2027-01-05" and c.today("UTC").isoformat() == "2027-01-06"
    assert c.now() == c.now()
    c.unfreeze()
    assert not c.frozen and abs((c.now() - datetime.now(UTC)).total_seconds()) < 5


def test_naive_freeze_read_in_tz_and_utcnow_naive():
    c = Clock()
    c.freeze(datetime(2027, 1, 5, 9, 0), "America/Los_Angeles")
    assert c.now() == datetime(2027, 1, 5, 17, 0, tzinfo=UTC)
    assert c.utcnow_naive() == datetime(2027, 1, 5, 17, 0) and c.utcnow_naive().tzinfo is None


def test_advance_and_real_now_unaffected():
    c = Clock()
    c.freeze(datetime(2030, 1, 1, tzinfo=UTC))
    c.advance(timedelta(hours=2))
    assert c.now() == datetime(2030, 1, 1, 2, tzinfo=UTC)
    assert abs((c.real_now() - datetime.now(UTC)).total_seconds()) < 5
    c.unfreeze()
    c.advance(timedelta(days=1))  # a running clock freezes at now + delta
    assert c.frozen and c.now() > datetime.now(UTC) + timedelta(hours=23)


def test_source_feeds_now_but_not_real_now():
    c = Clock(source=lambda: datetime(2031, 5, 5, 12, 0))  # naive source is read as UTC
    assert c.now() == datetime(2031, 5, 5, 12, 0, tzinfo=UTC)
    assert c.real_now().year != 2031


@pytest.mark.parametrize("text,expected", [
    ("20/minute", (20, 60.0)), ("1/second", (1, 1.0)), ("3/hours", (3, 3600.0)), ("5/10 minutes", (5, 600.0)),
    ("2 / day", (2, 86400.0)),
])
def test_parse_rate(text, expected):
    assert parse_rate(text) == expected


@pytest.mark.parametrize("bad", ["", "minute", "0/minute", "5/week", "a/minute"])
def test_parse_rate_rejects(bad):
    with pytest.raises(ValueError):
        parse_rate(bad)


class TickClock(Clock):
    """A clock whose REAL time is under the test's control (the limiter stamps with ``real_now``)."""

    def __init__(self):
        super().__init__()
        self.t = datetime(2030, 1, 1, tzinfo=UTC)

    def real_now(self):
        return self.t

    def tick(self, **delta):
        self.t += timedelta(**delta)


def test_windows_slide_on_real_time():
    clk = TickClock()
    rl = RateLimiter("2/minute", clock=clk)
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a")
    assert rl.allow("b")  # keys are independent
    assert rl.retry_after("a") == 60
    clk.tick(seconds=59)
    assert not rl.allow("a") and rl.retry_after("a") == 1
    clk.tick(seconds=1)
    assert rl.allow("a")


def test_a_frozen_or_advanced_clock_does_not_move_the_windows():
    clk = Clock()
    clk.freeze(datetime(2030, 1, 1, tzinfo=UTC))
    rl = RateLimiter("1/minute", clock=clk)
    assert rl.allow("a") and not rl.allow("a")
    clk.advance(timedelta(hours=5))  # the demo or test clock jumps; real time has not
    assert not rl.allow("a")
    clk.unfreeze()
    assert not rl.allow("a")


def test_zero_multiple_is_rejected():
    for bad in ("5/0 minutes", "5/00 hour"):
        with pytest.raises(ValueError, match="at least 1"):
            parse_rate(bad)
    assert parse_rate("5/1 minute") == (5, 60.0)


def test_disabled_and_reset():
    rl = RateLimiter("1/minute", enabled=False)
    assert all(rl.allow("a") for _ in range(5))
    rl2 = RateLimiter("1/minute")
    rl2.allow("a")
    rl2.reset()
    assert rl2.allow("a")


def test_dependency_answers_429():
    limiters.clear()
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/x", dependencies=[Depends(rate_limit_dependency("x", rate="2/minute"))])
    def x():
        return {"ok": True}

    c = TestClient(app)
    assert c.get("/x").status_code == 200 and c.get("/x").status_code == 200
    r = c.get("/x")
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    limiters.reset()
    assert c.get("/x").status_code == 200
    limiters.enabled = False
    try:
        assert all(c.get("/x").status_code == 200 for _ in range(4))
    finally:
        limiters.enabled = True
        limiters.clear()


def test_unknown_limiter_name_is_a_clear_error():
    limiters.clear()
    with pytest.raises(KeyError, match="register"):
        limiters.get("nope")
