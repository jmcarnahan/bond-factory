"""Queue runner: two independent label runs (r1, r2) per house, two runs at a time, spend-gated.

SPENDS MONEY through make_truth. Reached only from ``python -m tools.roof_eval.label run`` which requires --spend-cap and
--confirm-spend. The cap is a total over the whole spend ledger (work/spend.tsv, one row per finished run, so earlier
runs count). A run is not started when spent + per-run reserve x (runs in flight + 1) would pass the cap.
Children get a minimal environment (PATH, HOME, the API key from the parent's environment) and never print the key.
Houses are opaque ids from work/houses.tsv (columns id, folder); nothing here parses an id.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import compare

PKG_ROOT = (
    Path(__file__).resolve().parents[3]
)  # services/roof_measure: where `python -m tools.roof_eval...` resolves


@dataclass
class Gate:
    """The spend gate: one lock, the ledger and the cap."""

    work: Path
    spend_cap: float
    reserve: float = 5.5  # the most one run may cost (make_truth --max-cost)
    inflight: int = 0
    ledger_path: Path | None = None  # default work/spend.tsv
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def ledger(self) -> Path:
        return self.ledger_path or self.work / "spend.tsv"

    def spent(self) -> float:
        if not self.ledger.exists():
            return 0.0
        with open(self.ledger) as fh:
            return sum(float(r["usd_estimate"]) for r in csv.DictReader(fh, delimiter="\t"))

    def may_start(self, runs: int = 1) -> bool:
        """True when ``runs`` more runs fit under the cap (call with the lock held)."""
        s = self.spent()
        return s < self.spend_cap and s + self.reserve * (self.inflight + runs) <= self.spend_cap


def log(work: Path, *a) -> None:
    (work / "logs").mkdir(exist_ok=True)
    with open(work / "logs" / "driver.log", "a") as fh:
        fh.write(time.strftime("%H:%M:%S ") + " ".join(map(str, a)) + "\n")


def child_env() -> dict[str, str]:
    return {k: os.environ[k] for k in ("PATH", "HOME", "ANTHROPIC_API_KEY") if k in os.environ}


def one(g: Gate, hid: str, folder: str, tag: str) -> None:
    work = g.work
    out = work / "runs" / hid / tag
    done = work / "truth" / hid / f"truth.llm_vision.{tag}.json"
    for attempt in (1, 2):
        if done.exists():
            return
        with g.lock:
            if not g.may_start():
                log(work, "BUDGET: not starting", hid, tag, f"spent {g.spent():.2f} inflight {g.inflight}")
                return
            g.inflight += 1
        try:
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "run.log", "a") as lf:
                subprocess.run(  # noqa: PLW1510 - the exit status is read from run.json, not from the process
                    [
                        sys.executable,
                        "-m",
                        "tools.roof_eval.label",
                        "one",
                        folder,
                        "--out",
                        str(out),
                        "--truth-root",
                        str(work / "truth"),
                        "--tag",
                        tag,
                        "--spend",
                        str(g.ledger),
                        "--max-cost",
                        str(g.reserve),
                        "--spend-cap",
                        str(g.spend_cap),
                        "--confirm-spend",
                    ],
                    cwd=PKG_ROOT,
                    env=child_env(),
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    timeout=3600,
                )
        except Exception as e:  # noqa: BLE001 - the queue keeps going; the failure is logged
            log(work, "run failed", hid, tag, type(e).__name__)
        finally:
            with g.lock:
                g.inflight -= 1
        rj = out / "run.json"
        info = json.loads(rj.read_text()) if rj.exists() else {}
        log(
            work,
            "done",
            hid,
            tag,
            info.get("stop"),
            info.get("turns"),
            info.get("cost_usd"),
            f"total {g.spent():.2f}",
        )
        if info.get("stop") == "usage_limit":
            log(work, "ACCOUNT USAGE LIMIT: stopping the queue")
            os._exit(3)
        retry = str(info.get("stop", "crash")).startswith(
            ("api_error", "connection", "rate_limited", "crash")
        )
        if not retry or info.get("cost_usd", 0) > 1.5:
            return
        if attempt == 1 and rj.exists():
            rj.rename(out / "run.attempt1.json")


def house(g: Gate, h: dict[str, str]) -> None:
    work = g.work
    with g.lock:
        need = sum(
            not (work / "truth" / h["id"] / f"truth.llm_vision.{t}.json").exists() for t in ("r1", "r2")
        )
        if need and not g.may_start(need):
            log(work, "BUDGET: skipping house", h["id"], f"spent {g.spent():.2f}")
            return
    ts = [threading.Thread(target=one, args=(g, h["id"], h["folder"], t)) for t in ("r1", "r2")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    try:
        compare.rebuild(work)
    except Exception as e:  # noqa: BLE001 - the queue keeps going; the failure is logged
        log(work, "compare failed", h["id"], repr(e)[:200])


def run_queue(
    work: Path, spend_cap: float, start: int | None = None, stop: int | None = None, reserve: float = 5.5
) -> None:
    g = Gate(work, spend_cap, reserve)
    houses = compare.read_houses(work)
    if start is not None and stop is not None:
        houses = houses[start:stop]
    sem = threading.Semaphore(1)  # one house at a time = two conversations at once

    def guarded(h):
        with sem:
            house(g, h)

    ths = []
    for h in houses:
        t = threading.Thread(target=guarded, args=(h,))
        t.start()
        ths.append(t)
        time.sleep(20)
    for t in ths:
        t.join()
    log(work, "QUEUE FINISHED", f"total {g.spent():.2f}")
