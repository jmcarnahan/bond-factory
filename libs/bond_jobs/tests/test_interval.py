import os
import signal
import threading
import time

import pytest

from bond_jobs import Every, run_cli, run_every, run_schedule
from bond_jobs import interval as interval_mod


class Fake:
    """A clock that only moves when the schedule waits (or a function spends time)."""

    def __init__(self):
        self.t = 100.0
        self.waits = []
        self.stop = threading.Event()
        self.limit = None

    def clock(self):
        return self.t

    def wait(self, seconds):
        self.waits.append(seconds)
        self.t += seconds

    def spend(self, seconds):
        self.t += seconds


def go(fake, entries, stop_after=None, **kw):
    """Run until ``stop_after`` fake seconds have passed since the start."""
    start = fake.t
    inner = fake.wait

    def wait(seconds):
        inner(seconds)
        if stop_after is not None and fake.t - start >= stop_after:
            fake.stop.set()

    run_schedule(entries, stop=fake.stop, install_signals=False, clock=fake.clock, wait=wait, **kw)


def test_runs_first_then_by_interval():
    fake, ran = Fake(), []
    go(fake, [Every(10, lambda: ran.append(fake.t - 100))], stop_after=25)
    assert ran == [0, 10, 20]


def test_run_first_false_waits_one_period():
    fake, ran = Fake(), []
    go(fake, [Every(10, lambda: ran.append(fake.t - 100), run_first=False)], stop_after=25)
    assert ran == [10, 20]


def test_fixed_rate_does_not_drift():
    fake, ran = Fake(), []

    def slow():
        ran.append(fake.t - 100)
        fake.spend(3)  # takes 3 of the 10 seconds

    go(fake, [Every(10, slow)], stop_after=45)
    assert ran == [0, 10, 20, 30, 40]


def test_missed_periods_run_once_and_realign():
    fake, ran = Fake(), []

    def stall():
        ran.append(fake.t - 100)
        if len(ran) == 1:
            fake.spend(35)  # misses periods at 10, 20, 30

    go(fake, [Every(10, stall)], stop_after=65)
    assert ran == [0, 40, 50, 60]


def test_exception_does_not_stop_other_entries():
    fake, good, results = Fake(), [], []

    def boom():
        raise RuntimeError("no")

    go(fake, [Every(10, boom, name="boom"), Every(10, lambda: good.append(1) or "ok", name="good")],
       stop_after=25, on_result=lambda e, r, err: results.append((e.name, r, type(err).__name__ if err else None)))
    assert len(good) == 3
    assert ("boom", None, "RuntimeError") in results and ("good", "ok", None) in results


def test_two_entries_interleave():
    fake, order = Fake(), []
    go(fake, [Every(10, lambda: order.append(("a", fake.t - 100)), name="a"),
              Every(15, lambda: order.append(("b", fake.t - 100)), name="b")], stop_after=31)
    assert order == [("a", 0), ("b", 0), ("a", 10), ("b", 15), ("a", 20), ("a", 30), ("b", 30)]


def test_stop_ends_the_wait_at_once():
    stop = threading.Event()
    done = []
    thread = threading.Thread(target=lambda: (run_schedule([Every(3600, lambda: None, run_first=False)],
                                                           stop=stop, install_signals=False), done.append(1)))
    thread.start()
    time.sleep(0.05)
    stop.set()
    thread.join(2)
    assert done == [1]


def test_sigterm_sets_stop_and_handlers_are_restored():
    before = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    stop = threading.Event()
    seen = []

    def fn():
        seen.append(1)
        os.kill(os.getpid(), signal.SIGTERM)

    run_schedule([Every(3600, fn)], stop=stop)
    assert seen == [1] and stop.is_set()
    assert {s: signal.getsignal(s) for s in before} == before


def test_jitter_stays_within_bounds():
    fake, ran = Fake(), []
    go(fake, [Every(10, lambda: ran.append(fake.t - 100), jitter=3)], stop_after=200)
    assert len(ran) >= 15
    for n, at in enumerate(ran):
        assert 10 * n <= at <= 10 * n + 3
    assert any(at != 10 * n for n, at in enumerate(ran))


def test_jitter_uses_random_uniform(monkeypatch):
    monkeypatch.setattr(interval_mod.random, "uniform", lambda a, b: b)
    fake, ran = Fake(), []
    go(fake, [Every(10, lambda: ran.append(fake.t - 100), jitter=2)], stop_after=25)
    assert ran == [2, 12, 22]


def test_guard_false_skips_the_run():
    fake, ran, asked = Fake(), [], []

    def guard(entry):
        asked.append(entry.name)
        return len(asked) != 2

    go(fake, [Every(10, lambda: ran.append(fake.t - 100), name="x")], stop_after=25, guard=guard)
    assert ran == [0, 20] and asked == ["x", "x", "x"]


def test_interval_floor():
    with pytest.raises(ValueError):
        Every(0.001, lambda: None)
    with pytest.raises(ValueError):
        run_every(lambda: None, 0)
    with pytest.raises(ValueError):
        Every(5, lambda: None, jitter=-1)
    with pytest.raises(ValueError):
        run_schedule([], install_signals=False)


def test_run_every_passes_keywords():
    fake, ran = Fake(), []
    run_every(lambda: ran.append(1), 10, run_first=False, stop=fake.stop, install_signals=False,
              clock=fake.clock, wait=lambda s: (fake.wait(s), fake.stop.set() if fake.t > 125 else None))
    assert len(ran) == 2


def test_default_name_is_the_function_name():
    def my_job():
        pass

    assert Every(5, my_job).name == "my_job"


def test_cli_once_exit_zero_when_all_succeed():
    ran = []
    assert run_cli(["--once"], [Every(60, lambda: ran.append("a")), Every(60, lambda: ran.append("b"))]) == 0
    assert ran == ["a", "b"]


def test_cli_once_exit_one_when_any_raises_and_others_still_run():
    ran = []

    def boom():
        raise RuntimeError("x")

    assert run_cli(["--once"], [Every(60, boom), Every(60, lambda: ran.append("b"))]) == 1
    assert ran == ["b"]


def test_cli_watch_interval_overrides_period(monkeypatch):
    seen = []
    monkeypatch.setattr(interval_mod, "run_schedule", lambda entries, **kw: seen.append([e.seconds for e in entries]))
    assert run_cli(["--watch", "--interval", "7"], [Every(60, lambda: None), Every(5, lambda: None)]) == 0
    assert seen == [[7.0, 7.0]]


def test_cli_rejects_bad_interval_and_conflicting_modes():
    assert run_cli(["--interval", "0"], [Every(60, lambda: None)]) == 2
    assert run_cli(["--once", "--watch"], [Every(60, lambda: None)]) == 2
