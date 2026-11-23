"""Adapter ``library``: convert a house's stored library envelope (bond.roof_model, local FEET) to a result.json (METRES).

Usage: python -m tools.roof_eval.adapter_library <house_dir> <out_json> [--datum shift|ground]
The envelope's heights are feet above a roof-wide ground datum that it does not store. Each facet's relative plane is:
  1. its ``plane_eq`` (on the facet, else on the model plane that overlaps the facet by at least half its area); else
  2. its slope (pitch, aspect) anchored so its lowest polygon vertex sits at the envelope's own eave height for the
     facet's block, else at the median eave height of the other blocks (3 m when none is known).
Nothing is refitted per facet (that flatters the library). The one unknown, the building's absolute datum, is ONE
constant per building: ``shift`` (default) = the median of z - relative plane over the library's roof points, or
``ground`` = the median ground return in a ring 1.5-8 m around the footprint (no roof points used).
The envelope has no verdict: the result states ``ok`` when it has facets, ``refused`` otherwise.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .data import load_json, parse_polygon

FT = 0.3048
EDGE_MAP = {"parapet": "flat_edge"}


def _poly(ring) -> Polygon:
    p = Polygon([(x * FT, y * FT) for x, y in ring])
    return p if p.is_valid else p.buffer(0)


def _find_plane(planes: list[dict[str, Any]], poly: Polygon) -> dict[str, Any] | None:
    """The model plane whose polygon covers at least half of ``poly`` (most overlap wins)."""
    best, best_a = None, 0.5 * poly.area
    for p in planes:
        if not p.get("plane_eq") or not p.get("polygon"):
            continue
        a = poly.intersection(_poly(p["polygon"])).area
        if a >= best_a:
            best, best_a = p, a
    return best


def slope_plane(f: dict[str, Any]) -> tuple[float, float]:
    """(a, b) of z = a x + b y + c from pitch_rise and aspect_deg (downslope bearing, 0 = N, 90 = E)."""
    pitch, az = float(f.get("pitch_rise") or 0.0), f.get("aspect_deg")
    if pitch < 1e-6 or az is None:
        return 0.0, 0.0
    s = pitch / 12.0
    return -s * math.sin(math.radians(az)), -s * math.cos(math.radians(az))


def ground_datum(w: np.ndarray, foot: Polygon) -> float | None:
    """Median class-2 return in the ring 1.5-8 m around the footprint; None with fewer than 6."""
    g = w[w[:, 3] == 2]
    if len(g) == 0 or foot.is_empty:
        return None
    ring = foot.buffer(8.0).difference(foot.buffer(1.5))
    near = g[shapely.intersects_xy(ring, g[:, 0], g[:, 1])]
    return float(np.median(near[:, 2])) if len(near) >= 6 else None


def convert(hdir: Path, datum: str = "shift") -> dict[str, Any]:
    env = load_json(hdir / "envelope.json") or {}
    m = env.get("model") or {}
    out: dict[str, Any] = {"slug": hdir.name, "method": "library", "version": str(env.get("pipeline_version", "")),
                           "roof_outline": [], "facets": [], "edges": [], "totals": {}, "diagnostics": {}}
    if not m.get("facets"):
        out["diagnostics"] = {"quality": {"verdict": "refused"}, "note": "no facets in the stored envelope"}
        return out
    w = np.load(hdir / "points_wide.npy").astype(float)
    foot = parse_polygon(load_json(hdir / "footprint.json"))
    pts = np.load(hdir / "points.npy").astype(float)
    planes = m.get("planes") or []
    eaves = {b["id"]: b.get("eave_height_ft") for b in m.get("blocks") or [] if b.get("id")}
    known = [FT * float(e) for e in eaves.values() if e is not None]
    default_eave = float(np.median(known)) if known else 3.0
    facets = []
    for f in m["facets"]:
        poly = _poly(f["polygon"])
        pl = _find_plane(planes, _poly(f["polygon"]))
        eq = f.get("plane_eq") or (pl or {}).get("plane_eq")
        if eq:
            a, b, c, kind = float(eq[0]), float(eq[1]), FT * float(eq[2]), "plane_eq"
        else:
            a, b = slope_plane(f)
            e = eaves.get(f.get("block"))
            low = FT * float(e) if e is not None else default_eave
            c = low - min(a * x + b * y for x, y in poly.exterior.coords)
            kind = "eave_height" if e is not None else "default_eave"
        pitch = 12.0 * math.hypot(a, b)
        facets.append({"id": f["id"], "polygon": [list(p) for p in poly.exterior.coords][:-1], "plane": [a, b, c],
                       "pitch_rise": pitch, "roof_type": "flat" if pitch < 2.0 else "pitched", "datum": kind})
    shift = ground_datum(w, foot) if datum == "ground" else None
    if shift is None:  # one constant per building from the library's own roof points
        res = []
        for f in facets:
            ins = shapely.contains_xy(Polygon(f["polygon"]), pts[:, 0], pts[:, 1]) if len(pts) else np.zeros(0, bool)
            if ins.any():
                q = pts[ins]
                res.extend(q[:, 2] - f["plane"][0] * q[:, 0] - f["plane"][1] * q[:, 1] - f["plane"][2])
        shift = float(np.median(res)) if res else float(np.percentile(w[:, 2], 5))
    for f in facets:
        f["plane"][2] += shift
    by_id = {f["id"]: f for f in facets}
    edges = []
    for e in m.get("edges") or []:
        pts_e = e.get("points") or []
        fs = [by_id[i] for i in e.get("facets", []) if i in by_id]
        z = [[pl["plane"][0] * x * FT + pl["plane"][1] * y * FT + pl["plane"][2] for pl in fs] for x, y in pts_e]
        for k in range(len(pts_e) - 1):
            p = [[pts_e[j][0] * FT, pts_e[j][1] * FT, float(np.mean(z[j])) if z[j] else shift] for j in (k, k + 1)]
            edges.append({"type": EDGE_MAP.get(e["type"], e["type"]), "p0": p[0], "p1": p[1],
                          "length_ft": float(np.linalg.norm(np.subtract(p[1], p[0])) / FT), "facets": e.get("facets", [])})
    blocks = unary_union([_poly(b["polygon"]) for b in m.get("blocks") or [] if b.get("polygon")] or [Polygon()])
    rings = [[list(c) for c in g.exterior.coords][:-1] for g in getattr(blocks, "geoms", [blocks]) if not g.is_empty]
    tot = env.get("totals") or m.get("totals") or {}
    out.update(facets=facets, edges=edges, roof_outline=rings[0] if len(rings) == 1 else rings,
               totals={"area_sqft": tot.get("area_sqft")},
               diagnostics={"quality": {"verdict": "ok"}, "warning_codes": env.get("warning_codes"),
                            "datum": sorted({f["datum"] for f in facets}), "building_shift_m": round(shift, 3)})
    return out


def main(argv=None) -> int:
    a = sys.argv[1:] if argv is None else list(argv)
    datum = "shift"
    if "--datum" in a:
        i = a.index("--datum")
        datum = a[i + 1]
        del a[i : i + 2]
    if len(a) != 2 or datum not in ("shift", "ground"):
        print(__doc__)
        return 2
    if not (Path(a[0]) / "envelope.json").is_file():  # derived houses (thinned, shifted) have no stored envelope
        print(f"no envelope.json in {a[0]}", file=sys.stderr)
        return 3
    Path(a[1]).write_text(json.dumps(convert(Path(a[0]), datum)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
