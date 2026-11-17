"""Draw the measured roof planes of a blocks file (or an envelope) as one PNG.

    .venv/bin/python tools/planes_png.py <blocks.json|envelope.json> out.png [--raw] [--no-straighten]

Each plane is filled, with its id, pitch, a facing arrow (downslope) and plan area; the footprint outline is drawn on
top. For a blocks file the planes are snapped here (``planes.snap_with_stats``); for an envelope the ``model.planes``
are drawn as they are and the footprint is read from the envelope when it carries one. ``--raw`` also draws the raw
LiDAR cluster outlines (thin dashed). Needs matplotlib (the ``render`` extra). Developer tool, not part of the library.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.path import Path as MplPath
from shapely.geometry import Polygon

PALETTE = ("#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2", "#edc948", "#9c755f", "#bab0ac")


def _planes_from_blocks(path: Path, straighten: bool) -> tuple[list[dict], list[list[float]], list[list[list[float]]]]:
    from roof_measure.classify import BlockSet
    from roof_measure.planes import snap_with_stats

    bs = BlockSet.load(path)
    kwargs = {} if straighten else {"straighten": False}
    res = snap_with_stats(bs, clip_to_footprint=True, **kwargs)
    planes = [p.to_dict() for p in res.planes]
    return planes, [list(p) for p in bs.footprint_ft], [[list(p) for p in b.polygon_ft] for b in bs.blocks]


def _planes_from_envelope(path: Path) -> tuple[list[dict], list[list[float]], list[list[list[float]]]]:
    env = json.loads(path.read_text())
    model = env.get("model", env)
    fp = (model.get("outline") or {}).get("polygon") or model.get("footprint_ft") or []
    return list(model.get("planes", [])), [list(p) for p in fp], []


def draw(planes: list[dict], footprint: list[list[float]], raw: list[list[list[float]]], out: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 9), dpi=110)
    for r in raw:
        ax.add_patch(MplPolygon(r, closed=True, fill=False, ls=":", lw=0.7, ec="#555"))
    for i, p in enumerate(planes):
        rings = [p["polygon"], *p.get("holes", [])]
        verts, codes = [], []
        for ring in rings:
            pts = [*ring, ring[0]]
            verts += pts
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(pts) - 2) + [MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(verts, codes), fc=PALETTE[i % len(PALETTE)], alpha=0.55, ec="#111", lw=1.2))
        rp = Polygon(p["polygon"]).buffer(0).representative_point()
        cx, cy = rp.x, rp.y
        asp = p.get("aspect_deg")
        if asp is not None:
            a = math.radians(asp)  # downslope compass bearing: 0 = north (+y), 90 = east
            ax.annotate("", xy=(cx + 3.2 * math.sin(a), cy + 3.2 * math.cos(a)), xytext=(cx, cy),
                        arrowprops={"arrowstyle": "-|>", "color": "#111", "lw": 1.5})
        flag = "" if "straightened" not in p else (" S" if p["straightened"] else " raw")
        ax.text(cx, cy - 1.2, f"{p['id']} {p['pitch_rise']:.1f}/12\n{p['plan_area_sqft']:.0f} sf, {len(p['polygon'])}v{flag}",
                ha="center", va="top", fontsize=8, color="#000")
    if footprint:
        ring = [*footprint, footprint[0]]
        ax.plot([q[0] for q in ring], [q[1] for q in ring], color="k", lw=2.2, ls="--")
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.set_title(title, fontsize=11)
    ax.grid(alpha=0.2)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--raw", action="store_true", help="also draw the raw LiDAR cluster outlines")
    ap.add_argument("--no-straighten", action="store_true", help="blocks files only: the planes as before straightening")
    ap.add_argument("--title", default="")
    a = ap.parse_args(argv)
    src = Path(a.source)
    doc = json.loads(src.read_text())
    if doc.get("schema", "").startswith("bond.roof_blocks"):
        planes, fp, raw = _planes_from_blocks(src, not a.no_straighten)
    else:
        planes, fp, raw = _planes_from_envelope(src)
    title = a.title or f"{src.stem}: {len(planes)} planes, {sum(len(p['polygon']) for p in planes)} vertices"
    draw(planes, fp, raw if a.raw else [], Path(a.out), title)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
