"""One PNG: the model's facets beside the snapped LiDAR planes, from a ``*_model.json`` the CLI wrote.

    .venv/bin/python tools/eval_png.py <model.json> <blocks.json> out.png [title]

Left: the model's facets (pitch, facing, plan area), with the model's block outlines in bold. Right: the snapped
planes (``model.planes``) with their height above ground. The footprint outline is dashed on both. Reads the numbers
the CLI already put in the model (``quality``, ``totals``); needs matplotlib (the ``render`` extra). Developer tool.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import Polygon

PALETTE = ("#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2", "#edc948", "#9c755f", "#bab0ac")
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _dir(aspect: float | None) -> str:
    return "flat" if aspect is None else COMPASS[int(((aspect % 360) + 22.5) // 45) % 8]


def _draw(ax, items, footprint, title, bold=()):
    for i, (poly, text) in enumerate(items):
        ax.add_patch(MplPolygon(list(poly.exterior.coords), closed=True, fc=PALETTE[i % len(PALETTE)], alpha=0.55,
                                ec="#222", lw=0.8))
        p = poly.representative_point()
        ax.text(p.x, p.y, text, ha="center", va="center", fontsize=6.5)
    for poly in bold:
        ax.add_patch(MplPolygon(list(poly.exterior.coords), closed=True, fc="none", ec="#000", lw=2.0))
    ax.add_patch(MplPolygon(list(footprint.exterior.coords), closed=True, fc="none", ec="#000", lw=1.2, ls="--"))
    minx, miny, maxx, maxy = footprint.bounds
    ax.set_xlim(minx - 3, maxx + 3)
    ax.set_ylim(miny - 3, maxy + 3)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)
    ax.tick_params(labelsize=7)


def main(argv: list[str]) -> int:
    model_path, blocks_path, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
    title = argv[4] if len(argv) > 4 else model_path.stem
    model = json.loads(model_path.read_text())
    blocks = json.loads(blocks_path.read_text())
    fp = Polygon(blocks["footprint_ft"]).buffer(0)
    facets = [(Polygon(f["polygon"]).buffer(0), f"{f['pitch_rise']:.1f}/12 {_dir(f.get('aspect_deg'))}\n{f['area_sqft']:,.0f}")
              for f in model["facets"]]
    planes = [(Polygon(p["polygon"], p.get("holes") or []).buffer(0),
               f"{p['id']} {p['pitch_rise']:.1f}/12 {_dir(p.get('aspect_deg'))}\n{p['surface_area_sqft']:,.0f}"
               + f" h{p.get('height_ft', 0):.1f}") for p in model.get("planes", [])]
    outlines = [Polygon(b["polygon"]).buffer(0) for b in model.get("blocks", [])]
    q, t = model.get("quality") or {}, model["totals"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 6.4))
    _draw(a, facets, fp, f"{title}: model, {len(model['blocks'])} blocks, {len(facets)} facets", outlines)
    _draw(b, planes, fp, f"snapped LiDAR planes, {len(planes)}")
    fig.suptitle(f"mismatch {q.get('plane_mismatch_pct')}%  uncovered {q.get('model_uncovered_pct')}%  "
                 f"model {t.get('total_area_sqft', 0):,.0f} sq ft  planes {(model.get('planes') and sum(p['surface_area_sqft'] for p in model['planes'])) or 0:,.0f} sq ft"
                 f"  method {model['source']['method']}", fontsize=9)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
