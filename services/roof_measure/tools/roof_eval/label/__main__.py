"""python -m tools.roof_eval.label <run|one|compare|relax> ...

run and one SPEND MONEY (Anthropic API). They refuse to start unless BOTH --spend-cap USD (a total over the spend
ledger) and --confirm-spend are given, and the key is read only from the environment variable ANTHROPIC_API_KEY.
compare and relax never call the network. ``one --render-only`` and ``one --dump-request`` do not spend and need neither.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def need_spend(a: argparse.Namespace) -> None:
    """Exit 2 unless the person has said how much may be spent and has confirmed it; the key must be in the environment."""
    problems = []
    if a.spend_cap is None or a.spend_cap <= 0:
        problems.append("--spend-cap USD (a positive total across the spend ledger) is required")
    if not a.confirm_spend:
        problems.append("--confirm-spend is required")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY is not set in the environment")
    if problems:
        sys.exit("refusing to spend: " + "; ".join(problems))


def need_budget(a: argparse.Namespace) -> None:
    """For ``one``: a ledger is required, and the cap is enforced against it (ledger total + this run's max cost <= cap)."""
    if not a.spend:
        sys.exit("refusing to spend: --spend LEDGER.tsv is required so the cap can be checked against earlier spend")
    from . import driver

    ledger = Path(a.spend)
    gate = driver.Gate(ledger.parent, a.spend_cap, a.max_cost, ledger_path=ledger)
    if not gate.may_start():
        sys.exit(f"refusing to spend: ledger total {gate.spent():.2f} + up to {a.max_cost:.2f} for this run passes --spend-cap {a.spend_cap:.2f}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tools.roof_eval.label", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def spend_args(q):
        q.add_argument(
            "--spend-cap", type=float, help="USD: total allowed in the spend ledger, earlier runs included"
        )
        q.add_argument("--confirm-spend", action="store_true", help="say that real API money may be spent")

    r = sub.add_parser("run", help="SPENDS: label every house in work/houses.tsv twice, then compare")
    r.add_argument("--work-dir", required=True, type=Path)
    r.add_argument("--start", type=int)
    r.add_argument("--stop", type=int)
    r.add_argument("--max-cost", type=float, default=5.5, help="most one run may cost")
    spend_args(r)
    o = sub.add_parser(
        "one", help="SPENDS (unless --render-only/--dump-request): one run on one house folder"
    )
    o.add_argument("house_folder", type=Path)
    o.add_argument("--out", type=Path, required=True)
    o.add_argument("--truth-root", type=Path)
    o.add_argument("--tag", default="r1")
    o.add_argument("--max-turns", type=int, default=40)
    o.add_argument("--effort", default="high")
    o.add_argument("--max-cost", type=float, default=5.5)
    o.add_argument("--spend", help="spend ledger (tsv) to append to")
    o.add_argument("--render-only", action="store_true")
    o.add_argument("--dump-request", action="store_true")
    spend_args(o)
    c = sub.add_parser(
        "compare", help="decide every house from the finished runs and rewrite labels.tsv (no network)"
    )
    c.add_argument("--work-dir", required=True, type=Path)
    x = sub.add_parser("relax", help="add the relaxed-fit confidence columns to labels.tsv (no network)")
    x.add_argument("--work-dir", required=True, type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if a.cmd == "compare":
        from . import compare

        for r in compare.rebuild(a.work_dir):
            print(
                r["id"], r["status"], r.get("area_diff_pct"), r.get("facet_iou_two_sided"), r.get("why", "")
            )
    elif a.cmd == "relax":
        from . import relax

        for hid, old, new in relax.main(a.work_dir):
            print(hid, old, "->", new)
    elif a.cmd == "one":
        if not (a.render_only or a.dump_request):
            need_spend(a)
            need_budget(a)
        from . import make_truth

        make_truth.run(
            a.house_folder,
            a.out,
            a.truth_root,
            a.max_turns,
            a.effort,
            a.render_only,
            a.tag,
            a.max_cost,
            a.spend,
            a.dump_request,
            confirm_spend=a.confirm_spend,
        )
    else:
        need_spend(a)
        from . import driver

        driver.run_queue(a.work_dir, a.spend_cap, a.start, a.stop, a.max_cost)
    return 0


if __name__ == "__main__":
    sys.exit(main())
