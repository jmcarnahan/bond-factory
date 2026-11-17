"""Draw the envelope partition of a blocks file next to the snapped planes it replaces, as one PNG.

    .venv/bin/python tools/envelope_png.py <blocks.json> out.png [--title T] [--print]

Left: the planes as ``planes.snap_with_stats`` gives them without the envelope step. Right: ``planes_envelope``'s
planes (filled, id, pitch, facing arrow, plan area, section and method), the raw LiDAR clusters dotted, the footprint
dashed and the shared borders coloured by kind (ridge green, hip purple, valley red, step dashed brown, seam dotted grey). The title says
whether the gate passed. ``--print`` also prints the per-plane table. Needs matplotlib (the ``render`` extra).
Developer tool, not part of the library.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import Polygon

PALETTE = ("#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2", "#edc948", "#9c755f", "#bab0ac")
KIND = {"ridge": ("#1a9641", "-"), "hip": ("#7b3294", "-"), "valley": ("#d7191c", "-"), "step": ("#8c510a", "--"), "seam": ("#999999", ":")}


def inputs(path: Path) -> tuple[list[Any], dict[str, Any], Polygon]:
    """The snapped planes (no envelope step), the raw clusters by id and the outline, as ``planes._snap`` has them."""
    import roof_measure.planes_envelope as pe
    from roof_measure.classify import BlockSet, clean_polygon, polygons_of
    from roof_measure.planes import snap_with_stats
    from roof_measure.planes_gaps import _grid, _resolve_overlaps, _valid

    bs = BlockSet.load(path)
    keep = pe.envelope_planes
    pe.envelope_planes = lambda *a, **k: None  # the planes as they were before the envelope step (planes._snap's hook)
    try:
        res = snap_with_stats(bs, clip_to_footprint=True)
    finally:
        pe.envelope_planes = keep
    fp = _valid(_grid(max(polygons_of(_valid(bs.footprint)), key=lambda p: p.area)))
    blocks = [b for b in bs.blocks if b.kind in ("flat", "sloped") and b.poly.area > 0]
    cleaned = [_valid(clean_polygon(b.poly)) for b in blocks]
    cleaned = [max(polygons_of(c), key=lambda p: p.area) if polygons_of(c) else Polygon() for c in cleaned]
    raw = _resolve_overlaps(cleaned, fp, True)
    return res.planes, {b.id: r for b, r in zip(blocks, raw, strict=True) if r is not None}, fp


def _panel(ax: Any, planes: list[Any], raw: dict[str, Any], fp: Polygon, borders: list[dict], title: str) -> None:
    for i, p in enumerate(planes):
        ax.add_patch(MplPolygon(p.polygon, closed=True, fc=PALETTE[i % len(PALETTE)], alpha=0.5, ec="#333", lw=0.8))
        g = Polygon(p.polygon).buffer(0)
        rp = g.representative_point()
        if p.aspect_deg is not None:
            a = math.radians(p.aspect_deg)
            ax.annotate("", xy=(rp.x + 3 * math.sin(a), rp.y + 3 * math.cos(a)), xytext=(rp.x, rp.y),
                        arrowprops={"arrowstyle": "-|>", "color": "#111", "lw": 1.4})
        sec = getattr(p, "section", None)
        meth = getattr(p, "straighten_method", None)
        tag = "" if sec is None else f"\ns{sec} {meth[:3] if meth else ''}"
        ax.text(rp.x, rp.y - 1.0, f"{p.id} {p.pitch_rise:.1f}/12\n{p.plan_area_sqft:.0f} sf {len(p.polygon)}v{tag}",
                ha="center", va="top", fontsize=7)
    for r in raw.values():
        for part in getattr(r, "geoms", [r]):
            if part.geom_type == "Polygon":
                ax.add_patch(MplPolygon(list(part.exterior.coords), closed=True, fill=False, ls=":", lw=0.7, ec="#444"))
    for b in borders:
        col, ls = KIND.get(b["kind"], ("#000", "-."))
        xs, ys = zip(*b["segment"], strict=True)
        ax.plot(xs, ys, color=col, ls=ls, lw=2.6)
    ring = list(fp.exterior.coords)
    ax.plot([q[0] for q in ring], [q[1] for q in ring], color="k", lw=1.8, ls="--")
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.grid(alpha=0.2)
    ax.set_title(title, fontsize=9)


def clean_picture(planes: list[Any], borders: list[dict], fp: Polygon, out: str, title: str) -> None:
    """One panel for people: filled planes with pitch and area, borders coloured by kind, a legend; no construction."""
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(9, 9), dpi=120)
    for i, p in enumerate(planes):
        ax.add_patch(MplPolygon(p.polygon, closed=True, fc=PALETTE[i % len(PALETTE)], alpha=0.45, ec="#666", lw=0.6))
        rp = Polygon(p.polygon).buffer(0).representative_point()
        if p.aspect_deg is not None:
            a = math.radians(p.aspect_deg)
            ax.annotate("", xy=(rp.x + 2.5 * math.sin(a), rp.y + 2.5 * math.cos(a)), xytext=(rp.x, rp.y),
                        arrowprops={"arrowstyle": "-|>", "color": "#333", "lw": 1.2})
        pitch = "flat" if not p.pitch_rise else f"{p.pitch_rise:.1f}/12"
        ax.text(rp.x, rp.y - 0.8, f"{pitch}\n{p.plan_area_sqft:.0f} sq ft", ha="center", va="top", fontsize=8)
    for b in borders:
        if b["kind"] == "seam":
            continue
        col, ls = KIND.get(b["kind"], ("#000", "-."))
        xs, ys = zip(*b["segment"], strict=True)
        ax.plot(xs, ys, color=col, ls=ls, lw=2.8)
    ring = list(fp.exterior.coords)
    ax.plot([q[0] for q in ring], [q[1] for q in ring], color="#111", lw=1.6)
    kinds = [k for k in ("ridge", "hip", "valley", "step") if any(b["kind"] == k for b in borders)]
    ax.legend([Line2D([0], [0], color=KIND[k][0], ls=KIND[k][1], lw=2.8) for k in kinds], kinds, loc="upper left",
              bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=9)
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.axis("off")
    ax.set_title(title, fontsize=11)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    from roof_measure.planes_envelope import envelope_detail

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("blocks")
    ap.add_argument("out")
    ap.add_argument("--title", default="")
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--clean", default="", help="also write a clean one-panel picture (no construction lines) here")
    a = ap.parse_args(argv)
    planes, raw, fp = inputs(Path(a.blocks))
    res = envelope_detail(planes, raw, fp)
    x0, y0, x1, y1 = fp.bounds
    wide = (x1 - x0) > 1.5 * (y1 - y0)  # a long building: the two panels one above the other, larger
    fig, axes = plt.subplots(2, 1, figsize=(18, 16), dpi=100) if wide else plt.subplots(1, 2, figsize=(17, 9), dpi=100)
    nv = sum(len(p.polygon) for p in planes)
    _panel(axes[0], planes, raw, fp, [], f"before (snap + straighten): {len(planes)} planes, {nv} vertices")
    secs = "; ".join(f"s{s['section']} {s['method']} {','.join(s['planes'])}" for s in res.sections)
    gate = "GATE PASSED" if res.gate_failure is None else f"GATE FAILED: {res.gate_failure}"
    if getattr(res, "steps", "square") != "square":
        gate += f" ({res.steps} steps; square ones refused: {res.refused})"
    nv2 = sum(len(p.polygon) for p in res.planes)
    _panel(axes[1], res.planes, raw, fp, res.borders, f"envelope: {len(res.planes)} planes, {nv2} vertices, {gate}\n{secs}")
    from shapely.geometry import LineString

    for rec in res.lines:  # the roof lines tried (thin; dotted when they do not separate the two clusters)
        for (px, py), (dx, dy) in rec["lines"]:
            seg = LineString([(px - 300 * dx, py - 300 * dy), (px + 300 * dx, py + 300 * dy)]).intersection(fp)
            for part in getattr(seg, "geoms", [seg]):
                if part.geom_type == "LineString":
                    xs, ys = zip(*part.coords, strict=True)
                    axes[1].plot(xs, ys, color="#888", lw=0.6, ls="-" if rec["separates"] else ":")
        if a.print:
            fa, fb = rec.get("faces", ([rec["a"]], [rec["b"]]))
            print(f"  line {'+'.join(planes[k].id for k in fa)}-{'+'.join(planes[k].id for k in fb)} {rec['kind']} "
                  f"separates={rec['separates']} touch={rec.get('touch_pts')} measured_shift={rec.get('measured_shift_ft')} "
                  f"aligned={rec.get('aligned')} computed={[(tuple(round(v, 1) for v in p), round(math.degrees(math.atan2(d[1], d[0])) % 180, 1)) for p, d in rec.get('computed', [])]} used="
                  f"{[(tuple(round(v, 1) for v in p), round(math.degrees(math.atan2(d[1], d[0])) % 180, 1)) for p, d in rec['lines']]}")
    fig.suptitle(a.title or Path(a.blocks).stem, fontsize=11)
    if a.clean:
        clean_picture(res.planes if res.gate_failure is None else planes, res.borders if res.gate_failure is None else [],
                      fp, a.clean, a.title or "Roof planes")
    fig.savefig(a.out, bbox_inches="tight")
    plt.close(fig)
    if a.print:
        from roof_measure.planes_envelope_gate import expected_areas

        grown = expected_areas([p.id for p in planes], [raw[p.id].intersection(fp) if p.id in raw else Polygon()
                                                         for p in planes], fp)
        for p in res.planes:
            exp = grown.get(p.id, 0.0)
            mv = res.moves.get(p.id, {})
            print(f"{p.id}: s{getattr(p, 'section', '?')} {getattr(p, 'straighten_method', '?')} {len(p.polygon)}v "
                  f"area {p.plan_area_sqft:.0f} expected {exp:.0f} ({100 * (p.plan_area_sqft - exp) / exp if exp else 0:+.0f}%) "
                  f"turn {mv.get('turn_deg', 0)} deg dz {mv.get('max_dz_ft', 0)} ft")
        for b in res.borders:
            print(f"  {b['a']}-{b['b']} {b['kind']} {b['length_ft']} ft step {b['step_ft']}")
        print("sections:", res.sections)
        print("merged_small:", res.merged_small, "gate:", res.gate_failure)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
