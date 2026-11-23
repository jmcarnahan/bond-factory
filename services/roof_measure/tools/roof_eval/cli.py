"""Command line: python -m tools.roof_eval {eval,baseline,blind,blind-score,sweep} (see the roof-* Makefile targets)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import baseline, blind, blind_score, data, runner, sweep, synth

GATES_DIR = Path(__file__).resolve().parent / "gates"


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--data", help="data root (default $ROOF_EVAL_DATA)")
    p.add_argument("--engine", help="library | results-dir:<dir> | '<cmd> {house_dir} {out_json}' (default $ROOF_EVAL_ENGINE)")
    p.add_argument("--jobs", type=int, default=int(os.environ.get("JOBS") or 4))
    p.add_argument("--out", help="run directory (default out/roof-eval/<engine>-<split>)")
    p.add_argument("--price-rules", help="price rules JSON (see price_rules.example.json)")
    p.add_argument("--timeout", type=int, default=runner.engines.DEFAULT_TIMEOUT_S)
    p.add_argument("--limit", type=int)
    p.add_argument("--where", action="append", default=[], help="manifest filter key=a,b or key!=a (repeatable)")


def _cfg(a, split: str, root: Path | None) -> runner.Config:
    name = (a.engine or os.environ.get("ROOF_EVAL_ENGINE", "engine")).split(":")[0].split()[0].rsplit("/", 1)[-1]
    out = Path(a.out) if a.out else Path(os.environ.get("ROOF_EVAL_OUT", "out/roof-eval")) / f"{name}-{split}"
    return runner.Config(root=root or Path("."), out_dir=out, engine=a.engine, split=split, where=a.where, jobs=a.jobs,
                         baseline=getattr(a, "baseline", None), gates_file=Path(a.gates) if getattr(a, "gates", None) else None,
                         price_rules=Path(a.price_rules) if a.price_rules else None, timeout_s=a.timeout, limit=a.limit,
                         baselines_dir=Path(a.baselines_dir) if getattr(a, "baselines_dir", None) else None)


def _latest(base: Path) -> Path:
    runs = sorted((p.parent for p in base.glob("*/summary.json")), key=lambda p: (p / "summary.json").stat().st_mtime)
    if not runs:
        raise SystemExit(f"no run found under {base}")
    return runs[-1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roof_eval", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eval", help="run an engine over a split, score, compare, gate")
    _common(e)
    e.add_argument("--split", default="tuning", help="tuning | demo | heldout | negative | all")
    e.add_argument("--baseline", help="baseline name under <data>/baselines")
    e.add_argument("--baselines-dir")
    e.add_argument("--gates", help="gates.json (default: tools/roof_eval/gates/<split>.json when it exists)")
    e.add_argument("--no-gates", action="store_true", help="run without gates (NO_GATES=1); otherwise no gates file exits 3")
    e.add_argument("--twice", action="store_true", help="run twice and require identical digests")
    b = sub.add_parser("baseline", help="freeze a run as baselines/<name> (needs --confirm)")
    b.add_argument("--data")
    b.add_argument("--name", required=True)
    b.add_argument("--run", help="run directory (default: the newest under out/roof-eval)")
    b.add_argument("--confirm", action="store_true")
    b.add_argument("--baselines-dir")
    k = sub.add_parser("blind", help="stratified draw and anonymous PNGs; the key goes elsewhere")
    k.add_argument("--data")
    k.add_argument("--split", default="heldout")
    k.add_argument("--n", type=int, default=20)
    k.add_argument("--seed", type=int, default=1)
    k.add_argument("--cand", action="append", default=[], help="label=<dir of <id>.json | baseline:NAME> (2 or 3)")
    k.add_argument("--out", required=True)
    k.add_argument("--key-out", required=True)
    k.add_argument("--where", action="append", default=[])
    s = sub.add_parser("blind-score", help="grades.tsv + key -> A/B/C counts with Wilson intervals")
    s.add_argument("--grades", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--graders", help="comma list to include")
    s.add_argument("--out", help="write summary JSON here")
    w = sub.add_parser("sweep", help="truth-free run over a list of house dirs")
    _common(w)
    w.add_argument("--houses", required=True)
    r = sub.add_parser("reference", help="check or rebuild the frozen reference points under the data root")
    r.add_argument("--data")
    r.add_argument("--rebuild", action="store_true")
    y = sub.add_parser("synth", help="gate 9: run an engine over the synthetic roofs")
    _common(y)
    y.add_argument("--selftest", action="store_true", help="oracle self-test: exit 0 iff only the sparse cases fail")
    y.add_argument("--gates", help="gates.json whose synth_gates block sets the gate-9 tolerances")
    y.add_argument("--only", action="append", default=[], help="case-name substring (repeatable)")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "eval":
            cfg = _cfg(a, a.split, data.data_root(a.data))
            if cfg.gates_file is None and not a.no_gates:
                default = GATES_DIR / f"{a.split}.json"
                cfg.gates_file = default if default.is_file() else None
            if cfg.gates_file is None and not a.no_gates:
                print(f"NO GATES EVALUATED: no gates file for split {a.split!r}; pass --gates or NO_GATES=1", file=sys.stderr)
                return 3
            if a.twice:
                same, d1, d2, passed = runner.check_twice(cfg)
                print(f"twice: {'IDENTICAL' if same else 'DIFFERENT'} {d1[:16]} {d2[:16]}; gates {'PASS' if passed else 'FAIL'}")
                return 0 if (same and passed) else 1
            s_ = runner.evaluate(cfg)
            print((cfg.out_dir / "tables.md").read_text())
            if cfg.gates_file is None:
                print("NO GATES EVALUATED (NO_GATES=1)")
            print(f"{'OK' if s_['ok'] else 'FAIL'}: results in {cfg.out_dir}")
            return 0 if s_["ok"] else 1
        if a.cmd == "baseline":
            root = data.data_root(a.data)
            run = Path(a.run) if a.run else _latest(Path(os.environ.get("ROOF_EVAL_OUT", "out/roof-eval")))
            bdir = (Path(a.baselines_dir) if a.baselines_dir else root / "baselines") / a.name
            print(baseline.freeze(run, bdir, a.confirm, root / "manifest.json"))
            return 0
        if a.cmd == "blind":
            root = data.data_root(a.data)
            rows = data.select_rows(data.load_manifest(root), a.split, a.where)
            key = blind.make(root, rows, a.cand, a.n, a.seed, Path(a.out), Path(a.key_out))
            print(f"{len(key['houses'])} sheets in {a.out}; key at {a.key_out} (do not give it to the grader)")
            return 0
        if a.cmd == "blind-score":
            res = blind_score.score(blind_score.read_grades(Path(a.grades)), json.loads(Path(a.key).read_text()),
                                    a.graders.split(",") if a.graders else None)
            if a.out:
                Path(a.out).write_text(json.dumps(res, indent=1))
            print(blind_score.render(res))
            return 0
        if a.cmd == "reference":
            root = data.data_root(a.data)
            if a.rebuild:
                print(f"rule {data.REF_RULE} hash {data.REF_HASH}: {data.rebuild_references(root)}")
                return 0
            ids = sorted(p.name for p in (root / "houses").iterdir() if p.is_dir())
            stale = data.check_references(root, ids)
            print(f"rule {data.REF_RULE} hash {data.REF_HASH}: {len(stale)} of {len(ids)} houses stale")
            return 1 if stale else 0
        if a.cmd == "synth":
            cfg = _cfg(a, "synth", Path("."))
            cfg.gates_file = Path(a.gates) if a.gates else GATES_DIR / "synth.json"
            ok, _, gates = synth.run(cfg, a.only)
            print((cfg.out_dir / "synth.md").read_text())
            print(f"{'OK' if ok else 'FAIL'}: {sum(g['pass'] for g in gates)}/{len(gates)} cases pass gate 9; results in {cfg.out_dir}")
            return 0 if (synth.selftest_ok(gates) if a.selftest else ok) else 1
        if a.cmd == "sweep":
            cfg = _cfg(a, "sweep", Path("."))
            s_ = sweep.sweep(cfg, Path(a.houses), a.limit)
            print((cfg.out_dir / "tables.md").read_text())
            return 0
    except (data.DataError, SystemExit) as exc:
        if isinstance(exc, SystemExit) and not isinstance(exc.code, str):
            raise
        print(f"error: {exc.code if isinstance(exc, SystemExit) else exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
