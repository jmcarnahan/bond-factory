"""Side-by-side SVG for ``eval_blocks``: the model's facets on the left, the snapped LiDAR planes on the right.

Hand-written SVG, no dependency beyond shapely. North is up; each polygon is labelled "pitch/12 direction sq ft".
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

from shapely.geometry import Polygon

PALETTE = ("#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2", "#edc948", "#9c755f", "#bab0ac")
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
PANEL_PX = 520
PAD_PX = 28


def direction(aspect_deg: float | None) -> str:
    """Compass name of the downslope direction ("flat" when there is none)."""
    return "flat" if aspect_deg is None else COMPASS[int(((aspect_deg % 360) + 22.5) // 45) % 8]


def label(pitch_rise: float, aspect_deg: float | None, sqft: float) -> str:
    """``4/12 S 224 sq ft`` (a flat plane reads ``flat 224 sq ft``)."""
    if aspect_deg is None:
        return f"flat {sqft:,.0f} sq ft"
    return f"{pitch_rise:.1f}".rstrip("0").rstrip(".") + f"/12 {direction(aspect_deg)} {sqft:,.0f} sq ft"


def _panel(items: list[tuple[Polygon, str]], footprint: Polygon, bounds: tuple[float, float, float, float],
           scale: float, x_off: float, title: str) -> str:
    minx, _, _, maxy = bounds

    def pt(x: float, y: float) -> str:
        return f"{x_off + PAD_PX + (x - minx) * scale:.1f},{PAD_PX + 20 + (maxy - y) * scale:.1f}"

    def path(poly: Polygon) -> str:
        rings = [poly.exterior, *poly.interiors]
        return " ".join("M" + " L".join(pt(x, y) for x, y in r.coords) + " Z" for r in rings)

    out = [(f'<text x="{x_off + PAD_PX}" y="18" font-size="14" font-family="sans-serif" font-weight="bold">'
            f"{escape(title)}</text>")]
    for i, (poly, text) in enumerate(items):
        out.append(f'<path d="{path(poly)}" fill="{PALETTE[i % len(PALETTE)]}" fill-opacity="0.55" stroke="#222" '
                   'stroke-width="1" fill-rule="evenodd"/>')
    out.append(f'<path d="{path(footprint)}" fill="none" stroke="#000" stroke-width="1.5" stroke-dasharray="6 4"/>')
    for poly, text in items:
        p = poly.representative_point()
        x, y = pt(p.x, p.y).split(",")
        out.append(f'<text x="{x}" y="{y}" font-size="10" font-family="sans-serif" text-anchor="middle" '
                   f'fill="#111">{escape(text)}</text>')
    return "".join(out)


def side_by_side(envelope: dict[str, Any], footprint_ft: list[Any], title: str) -> str:
    """The SVG text: model facets (left) and snapped planes (right) in one frame."""
    model = envelope["model"]
    fp = Polygon(footprint_ft).buffer(0)
    left = [(Polygon(f["polygon"]).buffer(0), label(f["pitch_rise"], f.get("aspect_deg"), f["area_sqft"]))
            for f in model["facets"]]
    right = [(Polygon(p["polygon"], p.get("holes") or []).buffer(0),
              label(p["pitch_rise"], p["aspect_deg"], p["surface_area_sqft"])) for p in model.get("planes", [])]
    minx, miny, maxx, maxy = fp.bounds
    scale = (PANEL_PX - 2 * PAD_PX) / max(maxx - minx, maxy - miny, 1.0)
    height = int((maxy - miny) * scale + 2 * PAD_PX + 60)
    width = 2 * PANEL_PX
    q = model.get("quality") or {}
    note = (f"mismatch {q.get('plane_mismatch_pct')}%  covered {q.get('outline_covered_pct')}%  "
            f"reasons: {', '.join(q.get('reasons') or []) or 'none'}")
    body = _panel(left, fp, fp.bounds, scale, 0, f"{title}: model, {len(left)} facets")
    body += _panel(right, fp, fp.bounds, scale, PANEL_PX, f"snapped LiDAR planes, {len(right)}")
    body += (f'<text x="{PAD_PX}" y="{height - 12}" font-size="12" font-family="sans-serif">{escape(note)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#fff"/>{body}</svg>\n')
