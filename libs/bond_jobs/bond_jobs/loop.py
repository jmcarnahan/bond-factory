"""The poll loop: on a thread inside the API process, or in the foreground of a worker process."""

import logging
import signal
import sys
import threading
from collections.abc import Callable

from bond_jobs.constants import POLL_SECONDS

LOGGER = logging.getLogger(__name__)

Step = Callable[[], list[dict]]


class Loop:
    """Calls ``step`` every ``interval`` seconds until ``stop`` is set. A failing pass is logged, never fatal."""

    def __init__(self, interval: float = POLL_SECONDS, step: Step | None = None, name: str = "worker"):
        self.interval = interval
        self.step = step
        self.name = name
        self.stop = threading.Event()

    def run(self) -> None:
        if self.step is None:
            raise RuntimeError("Loop has no step to run")
        LOGGER.info("%s started", self.name)
        while not self.stop.is_set():
            try:
                self.step()
            except Exception:
                LOGGER.exception("%s pass failed", self.name)
            self.stop.wait(self.interval)
        LOGGER.info("%s stopped", self.name)


def start_inline(
    step: Step, *, interval: float = POLL_SECONDS, name: str = "bond-worker"
) -> tuple[threading.Thread, Loop]:
    """Run the loop on a daemon thread. Call ``loop.stop.set()`` at shutdown."""
    loop = Loop(interval, step, name)
    thread = threading.Thread(target=loop.run, name=name, daemon=True)
    thread.start()
    return thread, loop


def main(argv: list[str] | None = None, *, step: Step, interval: float = POLL_SECONDS) -> int:
    """Worker entry point. ``--once`` runs one pass and prints a line per job; otherwise poll until SIGINT/SIGTERM."""
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s")
    if "--once" in argv:
        for row in step():
            print(f"{row['status']:7} {row['job_type']}  {row.get('summary') or ''}")
        return 0
    loop = Loop(interval, step)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: loop.stop.set())
    loop.run()
    return 0
