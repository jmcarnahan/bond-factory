import os
import signal
import threading

from bond_jobs import main, start_inline


def test_main_once_prints_one_line_per_job_and_returns_zero(capsys):
    calls = []

    def step():
        calls.append(1)
        return [{"status": "done", "job_type": "send", "summary": "sent 2"},
                {"status": "pending", "job_type": "retry"}]

    assert main(["--once"], step=step) == 0
    assert calls == [1]
    assert capsys.readouterr().out.splitlines() == ["done    send  sent 2", "pending retry  "]


def test_main_polls_until_sigterm_and_restores_handlers():
    old = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    calls = []

    def step():
        calls.append(1)
        if len(calls) == 2:
            os.kill(os.getpid(), signal.SIGTERM)  # the handler main installed sets the stop flag
        return []

    try:
        assert main([], step=step, interval=0.001) == 0
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)
    assert len(calls) >= 2


def test_start_inline_runs_on_a_daemon_thread_and_stops():
    ran = threading.Event()

    def step():
        ran.set()
        return []

    thread, loop = start_inline(step, interval=0.001, name="test-worker")
    try:
        assert ran.wait(2)
        assert thread.daemon and thread.name == "test-worker" and thread.is_alive()
    finally:
        loop.stop.set()
        thread.join(2)
    assert not thread.is_alive()
