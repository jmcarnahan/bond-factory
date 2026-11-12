import os
import signal
import threading

import pytest

from bond_jobs import Every, run_cli, run_schedule
from bond_jobs import interval as interval_mod


class Sim:
    def __init__(self):
        self.t = 0.0

    def clock(self):
        return self.t

    def wait(self, d):
        self.t += d


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_every_rejects_non_finite_seconds_and_jitter(value):
    with pytest.raises(ValueError):
        Every(value, lambda: None)
    with pytest.raises(ValueError):
        Every(1, lambda: None, jitter=value)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_cli_rejects_non_finite_interval_with_stderr_text(value, capsys):
    assert run_cli(["--interval", value], [Every(60, lambda: None)]) == 2
    out = capsys.readouterr()
    assert "--interval" in out.err and out.out == ""


def test_cli_passes_keywords_to_run_schedule(monkeypatch):
    seen = {}
    monkeypatch.setattr(interval_mod, "run_schedule", lambda entries, **kw: seen.update(kw))
    stop, guard, on_result = threading.Event(), (lambda e: True), (lambda *a: None)
    assert run_cli([], [Every(60, lambda: None)], guard=guard, on_result=on_result, stop=stop, install_signals=False) == 0
    assert seen == {"stop": stop, "install_signals": False, "on_result": on_result, "guard": guard}


def test_once_honours_guard_and_on_result_and_ignores_interval():
    ran, results = [], []

    def boom():
        raise RuntimeError("x")

    entries = [Every(60, lambda: ran.append("a"), name="a"), Every(60, lambda: ran.append("b"), name="b"),
               Every(60, boom, name="boom")]
    code = run_cli(["--once", "--interval", "0.5"], entries, guard=lambda e: e.name != "b",
                   on_result=lambda e, r, err: results.append((e.name, err is None)))
    assert code == 1 and ran == ["a"]
    assert results == [("a", True), ("boom", False)]  # b was skipped, not reported
    assert run_cli(["--once"], entries[:2], guard=lambda e: e.name != "b") == 0  # a skipped entry is not a failure


def test_once_guard_that_raises_skips_without_failing():
    def bad_guard(entry):
        raise RuntimeError("lock")

    assert run_cli(["--once"], [Every(60, lambda: 1 / 0)], guard=bad_guard) == 0


def test_a_huge_period_is_waited_in_capped_pieces():
    sim, stop, waits = Sim(), threading.Event(), []

    def wait(d):
        waits.append(d)
        sim.wait(d)
        if len(waits) == 3:
            stop.set()

    run_schedule([Every(1e30, lambda: None, run_first=False)], stop=stop, install_signals=False, clock=sim.clock, wait=wait)
    assert max(waits) <= threading.TIMEOUT_MAX


def test_none_previous_handler_is_not_restored(monkeypatch):
    calls = []
    real = signal.signal
    monkeypatch.setattr(interval_mod.signal, "signal",
                        lambda sig, h: calls.append((sig, h)) or (None if len(calls) <= 2 else real(sig, h)))
    stop = threading.Event()
    run_schedule([Every(1, stop.set)], stop=stop, clock=Sim().clock, wait=lambda d: None)
    assert len(calls) == 2  # installed twice; nothing "restored" with None


def test_first_signal_restores_previous_handlers_at_once():
    seen = []
    before_int = signal.signal(signal.SIGINT, lambda *a: seen.append("prev"))
    try:
        def job():
            os.kill(os.getpid(), signal.SIGINT)  # first signal: stop is set, handlers come back
            os.kill(os.getpid(), signal.SIGINT)  # second signal reaches the previous handler during the "stuck" job
            assert seen == ["prev"]

        run_schedule([Every(1, job)], clock=Sim().clock, wait=lambda d: None)
    finally:
        signal.signal(signal.SIGINT, before_int)


@pytest.mark.parametrize("exc", [SystemExit(3), KeyboardInterrupt()])
def test_base_exception_ends_the_schedule_restores_handlers_and_skips_on_result(exc):
    before = signal.getsignal(signal.SIGTERM)
    seen = []

    def die():
        raise exc

    with pytest.raises(type(exc)):
        run_schedule([Every(1, die)], on_result=lambda *a: seen.append(a), clock=Sim().clock, wait=lambda d: None)
    assert seen == [] and signal.getsignal(signal.SIGTERM) is before
