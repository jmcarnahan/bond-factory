"""Golden interface files: one small JSON per stage boundary of the engine, for synthetic roofs only.

These are the contract between the engine's stages (planes -> outline -> partition -> facets/edges): a builder who
changes one stage must still produce what the next stage expects. ``views`` extracts the four files from a run,
``compare`` checks a run against stored ones with tolerances (GEOS and BLAS differ a little between machines).
Regenerate with ``python -m roof_measure.engine.golden write`` (after a deliberate behaviour change, and say why).
Metres in the building frame (``frame_deg`` rotates it to the world), feet for lengths and areas; no geographic data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

from .load import roof_points_from_arrays
from .measure import measure_stages
from .params import DEFAULT, EngineParams
from .plane_math import aspect_deg, pitch_rise, pres
from .state import Stages
from .types import EngineResult

GOLDEN_CASES = ("gable_d8", "l_shape_d8", "flat_pitched_d8")
FILES = ("planes", "outline", "partition_summary", "facets_edges")
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "tests" / "data" / "engine_golden"


def run_case(name: str, params: EngineParams = DEFAULT) -> tuple[EngineResult, Stages]:
    """Simulate synthetic case ``name`` and run the engine on it (county-style outline: the wall line)."""
    from .synth_points import cases

    case = {c.name: c for c in cases()}[name]
    pts = case.points()
    wall = case.roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    return measure_stages(rp, wall, params=params, deadline=None, outline_source="county", parcel_match="given",
                          context=pts)


def _ring(poly: Polygon) -> list[list[float]]:
    return [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords]


def _planes_view(res: EngineResult, st: Stages) -> dict[str, Any]:
    crop, plab = st.crop, st.plab
    planes = []
    for i, pl in enumerate(st.planes):
        m = plab == i
        rms = float(pres(pl, crop[m]).std()) if m.sum() > 1 else 0.0
        planes.append({"a": round(float(pl[0]), 4), "b": round(float(pl[1]), 4), "c": round(float(pl[2]), 3),
                       "n_points": int(m.sum()), "pitch_rise": round(pitch_rise(pl), 2),
                       "aspect_deg": round(aspect_deg(pl), 1), "rms_m": round(rms, 3)})
    return {"frame_deg": round(st.frame_deg, 2), "theta_deg": round(st.theta, 2), "n_crop_points": len(crop),
            "assigned_pct": res.diagnostics.get("assigned_pct"), "planes": planes}


def _outline_view(res: EngineResult, st: Stages) -> dict[str, Any]:
    d = res.diagnostics
    return {"ring": _ring(st.outline), "area_m2": round(st.outline.area, 2), "source": d.get("outline_source"),
            "overhang_measured_m": d.get("overhang_measured_m"), "overhang_applied_m": d.get("overhang_applied_m"),
            "support_area_m2": d.get("support_area_m2"), "extra_parts": d.get("extra_parts"),
            "scale_used": d.get("overhang_scale_used")}


def _facets_edges_view(res: EngineResult, st: Stages) -> dict[str, Any]:
    facets = [{"id": f.id, "plane": [round(v, 4) for v in f.plane], "pitch_rise": round(f.pitch_rise, 2),
               "aspect_deg": round(f.aspect_deg, 1), "roof_type": f.roof_type, "area_sqft": round(f.area_sqft, 1),
               "points": f.points, "polygon": _ring(f.polygon)} for f in st.facets]
    edges = [{"type": e.type, "length_ft": round(e.length_ft, 1), "facets": list(e.facets),
              "p0": [round(v, 2) for v in e.p0], "p1": [round(v, 2) for v in e.p1]} for e in st.edges]
    keys = ("area_sqft", "planes_pitch_weighted", "eave_rake_ft", "ridge_hip_ft", "roofing_pitched_sqft", "roofing_flat_sqft")
    return {"facets": facets, "edges": edges, "totals": {k: res.totals.get(k) for k in keys},
            "verdict": res.quality.verdict}


def views(res: EngineResult, st: Stages) -> dict[str, dict[str, Any]]:
    """The four golden views of one run, keyed by file stem."""
    return {"planes": _planes_view(res, st), "outline": _outline_view(res, st),
            "partition_summary": st.run_summary(), "facets_edges": _facets_edges_view(res, st)}


def _num(a, b, atol: float, rtol: float, what: str, out: list[str]) -> None:
    if a is None or b is None:
        if a != b:
            out.append(f"{what}: {a} vs {b}")
    elif abs(a - b) > max(atol, rtol * max(abs(a), abs(b))):
        out.append(f"{what}: {a} vs {b}")


def _poly_iou(a: list, b: list) -> float:
    pa, pb = Polygon(a).buffer(0), Polygon(b).buffer(0)
    u = pa.union(pb).area
    return pa.intersection(pb).area / u if u else 0.0


def _match_planes(got: list, want: list, out: list[str]) -> None:
    if len(got) != len(want):
        out.append(f"planes: {len(got)} vs {len(want)}")
        return
    left = list(want)
    for g in got:
        j = min(range(len(left)), key=lambda k: abs(left[k]["a"] - g["a"]) + abs(left[k]["b"] - g["b"]))
        w = left.pop(j)
        for k, atol in (("a", 0.01), ("b", 0.01), ("c", 0.05)):
            _num(g[k], w[k], atol, 0.0, f"plane {k}", out)
        _num(g["n_points"], w["n_points"], 3, 0.1, "plane n_points", out)


def _compare_facets_edges(got: dict, want: dict, out: list[str]) -> None:
    if len(got["facets"]) != len(want["facets"]):
        out.append(f"facets: {len(got['facets'])} vs {len(want['facets'])}")
        return
    left = list(want["facets"])
    for g in got["facets"]:
        j = max(range(len(left)), key=lambda k: _poly_iou(g["polygon"], left[k]["polygon"]))
        w = left.pop(j)
        if _poly_iou(g["polygon"], w["polygon"]) < 0.97:
            out.append(f"facet {g['id']}: polygon differs from the golden one")
        if g["roof_type"] != w["roof_type"]:
            out.append(f"facet {g['id']}: roof_type {g['roof_type']} vs {w['roof_type']}")
        _num(g["pitch_rise"], w["pitch_rise"], 0.3, 0.0, f"facet {g['id']} pitch", out)
        _num(g["area_sqft"], w["area_sqft"], 5.0, 0.02, f"facet {g['id']} area", out)
    by_type = lambda d: {t: sum(e["length_ft"] for e in d["edges"] if e["type"] == t) for t in {e["type"] for e in d["edges"]}}
    gt, wt = by_type(got), by_type(want)
    for t in sorted(set(gt) | set(wt)):
        _num(gt.get(t, 0.0), wt.get(t, 0.0), 1.0, 0.03, f"edge length {t}", out)
    for k, v in want["totals"].items():
        if isinstance(v, (int, float)):
            _num(got["totals"].get(k), v, 1.0, 0.02, f"totals {k}", out)
    if got["verdict"] != want["verdict"]:
        out.append(f"verdict {got['verdict']} vs {want['verdict']}")


def compare(name: str, got: dict, want: dict) -> list[str]:
    """Mismatches of one golden view against the stored one (empty = reproduces it within tolerance)."""
    out: list[str] = []
    if name == "planes":
        _num(got["frame_deg"], want["frame_deg"], 0.5, 0.0, "frame_deg", out)
        _match_planes(got["planes"], want["planes"], out)
    elif name == "outline":
        _num(got["area_m2"], want["area_m2"], 0.5, 0.02, "outline area", out)
        _num(got["support_area_m2"], want["support_area_m2"], 1.0, 0.03, "support area", out)
        if _poly_iou(got["ring"], want["ring"]) < 0.97:
            out.append("outline ring differs from the golden one")
        if len(got["overhang_applied_m"] or []) != len(want["overhang_applied_m"] or []):
            out.append("overhang_applied_m: different number of sides")
    elif name == "partition_summary":
        if got["grid"] != want["grid"]:
            out.append(f"grid {got['grid']} vs {want['grid']}")
        if len(got["labels"]) != len(want["labels"]):
            out.append(f"labels {len(got['labels'])} vs {len(want['labels'])}")
        gc = sorted(v["cells"] for v in got["labels"].values())
        wc = sorted(v["cells"] for v in want["labels"].values())
        for a, b in zip(gc, wc, strict=False):
            _num(a, b, 20, 0.05, "label cells", out)
    elif name == "facets_edges":
        _compare_facets_edges(got, want, out)
    return out


def write(directory: Path = DEFAULT_DIR, names: tuple[str, ...] = GOLDEN_CASES) -> list[Path]:
    """Regenerate the golden files of ``names`` under ``directory`` (one folder per case)."""
    written = []
    for name in names:
        res, st = run_case(name)
        for stem, view in views(res, st).items():
            path = directory / name / f"{stem}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(view, indent=1) + "\n")
            written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "write":
        print("usage: python -m roof_measure.engine.golden write [dir]", file=sys.stderr)
        return 2
    for p in write(Path(args[1]) if len(args) > 1 else DEFAULT_DIR):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
