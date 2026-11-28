"""roof-synth (plan tier T6, gate 9): run an engine over the synthetic roofs of ``roof_measure.engine.synth_points``.

For every case a temporary house dir in the harness layout is built (points_wide from ``simulate``, wall outline as
footprint.json, reference points by the usual rule, truth.synthetic.json from the exact ``SynthRoof`` incl. facets), the
engine is run, and each result is scored and checked against gate 9:
  density >= 8 (16, 8 and the tree / banding / rotation / offset variants): automatic result with verdict ok, area within
    area_pct, ridge, hip, valley and perimeter within length_pct (errors of at most length_floor_ft feet count as zero);
  density 4: within thin_area_pct / thin_length_pct OR a verdict that is not ok;
  density >= 8 also needs two-sided facet IoU >= min_iou, facet count within facet_count_tol of the truth (facet_count_tol_complex
    for the 22-facet case) and flat/pitched agreement >= min_flat_pitched;
  below 4: the engine ran (exit ok), returned NO facets and the verdict is ``lidar_too_sparse`` (a crash, timeout or missing
    result fails; ``low_density`` is the 4-6 band verdict and does not count).
The tolerances are data: the ``synth_gates`` block of a gates.json (``--gates``), defaults below, printed at the top of synth.md.
The exact answer is ``SynthRoof.totals`` (one source). A shed's high edge is typed rake by the generator, not ridge, and
the truth ridge is ``totals.ridge_ft`` (0).
Also ``python -m tools.roof_eval.synth <house_dir> <out_json>``: the ``oracle`` engine, which returns the exact roof.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

from . import runner

NAME_RE = re.compile(r"^(.+?)_d(\d+)(?:_(.+))?$")
LEN_KEYS = ("ridge", "hip", "valley", "perimeter")
DEFAULT_TOL = {"area_pct": 2.0, "length_pct": 5.0, "thin_area_pct": 10.0, "thin_length_pct": 10.0, "length_floor_ft": 1.0,
               "dense_density": 8, "thin_density": 4, "min_iou": 0.90, "facet_count_tol": 1, "facet_count_tol_complex": 2,
               "min_flat_pitched": 0.95}


def tolerances(gates_file) -> dict[str, float]:
    """Gate-9 tolerances: the defaults overridden by the ``synth_gates`` block of a gates.json."""
    t = dict(DEFAULT_TOL)
    if gates_file:
        t.update(json.loads(Path(gates_file).read_text()).get("synth_gates") or {})
    return t


def _cases():
    from roof_measure.engine import synth_points

    return {c.name: c for c in synth_points.cases()}


def exact_roof(case):
    """The exact SynthRoof matching the simulated points (shifted back for an outline-offset case)."""
    dx, dy = case.kwargs.get("outline_offset_m", (0.0, 0.0))
    return case.roof.translated(-dx, -dy) if (dx or dy) else case.roof


def result_dict(roof, slug: str) -> dict[str, Any]:
    """CONTRACT-1 result of an exact SynthRoof (the oracle)."""
    fs = [{"id": f"f{f.id}", "polygon": [list(p) for p in f.xy], "plane": list(f.plane), "pitch_rise": f.pitch,
           "aspect_deg": f.aspect_deg, "roof_type": f.roof_type} for f in roof.facets]
    es = [{"type": e.type, "p0": list(e.p0), "p1": list(e.p1), "length_ft": e.length_ft,
           "facets": [f"f{i}" for i in e.facets], **({"jump_m": e.jump_ft * 0.3048} if e.type == "level_change" else {})}
          for e in roof.edges]
    return {"slug": slug, "method": "oracle", "roof_outline": [list(p) for p in roof.roof_outline], "facets": fs, "edges": es,
            "totals": dict(roof.totals), "diagnostics": {"quality": {"verdict": "ok"}}}


def truth_dict(roof, slug: str) -> dict[str, Any]:
    """truth.v2 from ``SynthRoof.totals`` (the one exact answer) plus the exact facets."""
    t = roof.totals
    pa = t["pitched_sqft"]
    pitched = [f for f in roof.facets if f.roof_type == "pitched"]
    return {"id": slug, "schema": "truth.v2", "source": "synthetic", "confidence": "high", "squares": t["area_sqft"] / 100.0,
            "area_sqft": t["area_sqft"], "flat_area_sqft": t["flat_sqft"], "pitched_area_sqft": pa,
            "predominant_pitch": sum(f.pitch * f.area_sqft for f in pitched) / pa if pa else None,
            "facet_count": len(roof.facets),
            "lengths_ft": {"eave": t["eave_ft"], "rake": t["rake_ft"], "ridge": t["ridge_ft"], "hip": t["hip_ft"],
                           "valley": t["valley_ft"], "level_change": t["level_change_ft"]},
            "lengths_ft_extra": {"flat_edge": t["flat_edge_ft"]},
            "facets": [{"id": f"f{f.id}", "polygon": [list(p) for p in f.xy], "pitch_rise": f.pitch,
                        "roof_type": f.roof_type} for f in roof.facets]}


def build_root(root: Path, names: list[str] | None = None) -> list[str]:
    """Write houses/<case>/ and truth/<case>/ for each case under ``root`` plus manifest.json; returns the names."""
    cs = _cases()
    names = sorted(n for n in cs if not names or any(s in n for s in names))
    rows = []
    for n in names:
        c = cs[n]
        hd = root / "houses" / n
        hd.mkdir(parents=True, exist_ok=True)
        pts = c.points()
        np.save(hd / "points_wide.npy", pts.astype(np.float32))
        np.save(hd / "points.npy", pts[pts[:, 3] == 1][:, :3].astype(np.float32))
        (hd / "footprint.json").write_text(json.dumps({"polygon": [list(p) for p in c.roof.wall_outline]}))
        m = NAME_RE.match(n)
        (hd / "meta.json").write_text(json.dumps({"parcel_match": "exact", "density": c.kwargs.get("density"),
                                                  "outline_source": "county"}))  # the synthetic wall outline IS a wall line
        td = root / "truth" / n
        td.mkdir(parents=True, exist_ok=True)
        (td / "truth.synthetic.json").write_text(json.dumps(truth_dict(exact_roof(c), n)))
        rows.append({"id": n, "split": "synthetic", "roof_class": m.group(1) if m else n,
                     "density_band": m.group(2) if m else None, "complexity": "simple", "flags": [m.group(3)] if m and m.group(3) else []})
    (root / "manifest.json").write_text(json.dumps(rows))
    return names


def gate9(name: str, density: float, rec: dict[str, Any], tol: dict[str, float] | None = None) -> dict[str, Any]:
    """Gate-9 verdict for one scored case: {pass, why, area_err_pct, len_err_pct, worst_len_pct, ...}."""
    tol = {**DEFAULT_TOL, **(tol or {})}
    t = (rec.get("truth") or {}).get("T6", {})
    ok = bool(rec.get("automation_ok"))
    out: dict[str, Any] = {"case": name, "density": density, "verdict": rec.get("verdict"), "has_result": bool(rec.get("automation")),
                           "area_err_pct": t.get("squares.err_pct")}
    errs, worst = {}, 0.0
    for k in LEN_KEYS:
        tr, ab = t.get(f"lengths.{k}.truth"), t.get(f"lengths.{k}.abs_diff")
        if tr is None or ab is None:
            continue
        errs[k] = 100 * ab / tr if tr > 1e-6 else None
        if abs(ab) > tol["length_floor_ft"]:
            worst = max(worst, abs(ab) / max(tr, 1e-9) * 100)
    out["len_err_pct"], out["worst_len_pct"] = errs, worst
    area = abs(out["area_err_pct"]) if out["area_err_pct"] is not None else 1e9

    def within(a_tol: float, l_tol: float) -> bool:
        return area <= a_tol and worst <= l_tol

    iou, agree = t.get("facet_iou.mean_iou"), t.get("flat_pitched_agreement")
    fc = t.get("facet_count.abs_diff")
    fc_tol = tol["facet_count_tol_complex"] if name.startswith("complex_hip") else tol["facet_count_tol"]
    out["iou"], out["facet_count_diff"], out["flat_pitched"] = iou, fc, agree
    if density >= tol["dense_density"]:
        shape_ok = (iou is not None and iou >= tol["min_iou"] and fc is not None and fc <= fc_tol
                    and agree is not None and agree >= tol["min_flat_pitched"])
        out["pass"] = ok and within(tol["area_pct"], tol["length_pct"]) and shape_ok
        out["why"] = (f"ok verdict, area {tol['area_pct']}%, lengths {tol['length_pct']}%, IoU >= {tol['min_iou']}, "
                      f"facet count within {fc_tol}, flat/pitched agreement >= {tol['min_flat_pitched']}")
    elif density >= tol["thin_density"]:
        out["pass"] = (ok and within(tol["thin_area_pct"], tol["thin_length_pct"])) or not ok
        out["why"] = f"within {tol['thin_area_pct']}% or not labelled ok"
    else:
        ran = (rec.get("engine") or {}).get("status") == "ok"
        out["pass"] = ran and not rec.get("automation") and rec.get("verdict") == "lidar_too_sparse"
        out["why"] = "engine ran, no facets, verdict lidar_too_sparse"
    return out


def tables(recs: list[dict[str, Any]], gates: list[dict[str, Any]], tol: dict[str, float] | None = None) -> str:
    """Markdown: shape x density grid (area % / worst length %, PASS or FAIL) and the details of variants and failures."""
    shapes, dens, cell = [], [], {}
    for g in gates:
        m = NAME_RE.match(g["case"])
        if not m or m.group(3):
            continue
        s, d = m.group(1), int(m.group(2))
        shapes.append(s) if s not in shapes else None
        dens.append(d) if d not in dens else None
        a = g["area_err_pct"]
        cell[(s, d)] = f"{'PASS' if g['pass'] else 'FAIL'} {'-' if a is None else f'{a:+.1f}%'} / {g['worst_len_pct']:.0f}%" if g["has_result"] \
            else f"{'PASS' if g['pass'] else 'FAIL'} none"
    dens.sort(reverse=True)
    tol = {**DEFAULT_TOL, **(tol or {})}
    lines = ["gate-9 tolerances (data, from gates.json synth_gates): " + ", ".join(f"{k}={v}" for k, v in tol.items()), "",
             "| shape | " + " | ".join(f"{d}/m2" for d in dens) + " |", "|---|" + "---|" * len(dens)]
    lines += [f"| {s} | " + " | ".join(cell.get((s, d), "") for d in dens) + " |" for s in shapes]
    lines += ["", "cell = gate 9 result, area error, worst of ridge/hip/valley/perimeter error beyond the length floor", "",
              "| case | pass | verdict | area % | fit_all | fit_covered | IoU | flat/pitched | false lvl |", "|---|---|---|---|---|---|---|---|---|"]
    byid = {r["id"]: r for r in recs}
    for g in gates:
        if NAME_RE.match(g["case"]).group(3) or not g["pass"]:
            r = byid[g["case"]]
            m, t = r.get("m") or {}, (r.get("truth") or {}).get("T6", {})
            f = lambda x, n=2: "-" if x is None else f"{x:.{n}f}"
            lines.append(f"| {g['case']} | {'PASS' if g['pass'] else 'FAIL'} | {g['verdict']} | {f(g['area_err_pct'], 1)} | "
                         f"{f(m.get('fit_all'))} | {f(m.get('fit_covered'))} | {f(t.get('facet_iou.mean_iou'))} | "
                         f"{f(t.get('flat_pitched_agreement'))} | {f(m.get('false_level_change_share'), 3)} |")
    return "\n".join(lines) + "\n"


def run(cfg: runner.Config, only: list[str] | None = None) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the cases, run the engine, score, apply gate 9, write synth.md and gates.json; (all passed, recs, gates)."""
    root = cfg.out_dir / "data"
    names = build_root(root, only)
    tol = tolerances(cfg.gates_file)
    cfg = runner.Config(**{**cfg.__dict__, "root": root, "split": "all", "where": [], "gates_file": None, "baseline": None})
    summary = runner.evaluate(cfg)
    recs = [json.loads(ln) for ln in (cfg.out_dir / "per_house.jsonl").read_text().splitlines()]
    cs = _cases()
    gates = [gate9(r["id"], cs[r["id"]].kwargs["density"], r, tol) for r in recs]
    (cfg.out_dir / "synth.md").write_text(tables(recs, gates, tol))
    (cfg.out_dir / "gates.json").write_text(json.dumps(gates, indent=1, default=float))
    summary["cases"] = len(names)
    return all(g["pass"] for g in gates), recs, gates


def selftest_ok(gates: list[dict[str, Any]]) -> bool:
    """The oracle self-test: every case at 4 pts/m2 and above passes gate 9 and every case below 4 fails it (the oracle
    never refuses)."""
    return all(g["pass"] == (g["density"] >= DEFAULT_TOL["thin_density"]) for g in gates)


def main(argv=None) -> int:
    """The oracle engine: ``synth <house_dir> <out_json>``."""
    a = sys.argv[1:] if argv is None else argv
    name = Path(a[0]).name
    c = _cases()[name]
    Path(a[1]).write_text(json.dumps(result_dict(exact_roof(c), name)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
