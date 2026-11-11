"""More synthetic cases: a flat roof with chimney curbs, a hip with a bowed eave, a Solar response.

Everything is placeholder data around origin 0/0 (see ``synth.py``); nothing here is a real building.
The curbs model is assembled by hand on top of ``build_model`` because the pipeline never emits holes.
"""

from __future__ import annotations

import copy
import itertools
import json
import math
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import Polygon

from .model import _totals, build_model
from .synth import FIXTURES, SITE1_FRAME, synthetic_flat_parapet, synthetic_hip

FIXED_TIME = "2026-11-10T00:00:00Z"
PLACEHOLDER_ADDRESS = {"line1": "100 Example Ave", "city": "Sampletown", "state": "CA", "zip": "90000",
                       "formatted": "100 Example Ave, Sampletown, CA 90000"}
M_PER_FT = 0.3048


def labelled(model: dict[str, Any]) -> dict[str, Any]:
    """Fixed time and the placeholder address, so regenerated fixtures are byte-identical."""
    model["generated_at"] = FIXED_TIME
    model["address"] = dict(PLACEHOLDER_ADDRESS)
    return model


def _retotal(model: dict[str, Any]) -> None:
    model["totals"] = _totals(model["facets"], model["edges"])


def _edge(i: int, kind: str, a: list[float], b: list[float], facet: str, slope: float = 1.0) -> dict[str, Any]:
    return {"id": f"e{i}", "type": kind, "points": [list(a), list(b)], "length_ft": math.dist(a, b) * slope,
            "facets": [facet]}


# ----------------------------------------------------------------------------- flat roof with curbs
def synthetic_flat_curbs() -> dict[str, Any]:
    """60 x 40 ft flat roof, parapet, 17 chimney curbs (2-4 ft) as holes, one 10 ft wall against the roof.

    Hole areas come off the facet and its block; each curb outline is a ``wall_flashing`` edge and
    10 ft of the north parapet run is ``step_flashing`` where the wall meets the roof. Curb outlines
    sit inside the facet, so ``model.validate`` (edges on facet boundaries) does not apply to this one.
    """
    bs, rbs = synthetic_flat_parapet()
    m = labelled(build_model(bs, rbs, {"method": "fixture"}))
    north = next(e for e in m["edges"] if e["points"][0] == [60.0, 40.0])
    a, b = north["points"]
    north.update(points=[a, [50.0, 40.0]], length_ft=10.0, type="step_flashing")
    m["edges"].insert(m["edges"].index(north) + 1,
                      {"id": "x", "type": "parapet", "points": [[50.0, 40.0], b], "length_ft": 50.0, "facets": ["f1"]})
    holes: list[dict[str, Any]] = []
    k = 0
    for row in range(3):
        for col in range(6):
            if (row, col) == (2, 5):
                continue  # 18 grid cells, 17 curbs
            w, h = 2.0 + k % 3, 2.0 + (k // 3) % 3
            x, y = 6.0 + 9.0 * col, 8.0 + 10.0 * row
            ring = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            holes.append({"id": f"h{k + 1}", "kind": "chimney", "polygon": ring, "area_sqft": w * h})
            k += 1
    m["holes"] = holes
    taken = sum(h["area_sqft"] for h in holes)
    f, blk = m["facets"][0], m["blocks"][0]
    for d, keys in ((f, ("plan_area_sqft", "area_sqft")), (blk, ("plan_area_sqft",))):
        for key in keys:
            d[key] -= taken
    for h in holes:
        r = h["polygon"]
        for i in range(4):
            m["edges"].append({"id": "x", "type": "wall_flashing", "points": [r[i], r[(i + 1) % 4]],
                               "length_ft": math.dist(r[i], r[(i + 1) % 4]), "facets": ["f1"]})
    for i, e in enumerate(m["edges"], start=1):
        e["id"] = f"e{i}"
    _retotal(m)
    m["confidence"]["notes"] = ["Synthetic flat roof with 17 chimney curbs: curb outlines are wall flashing, "
                                + "holes are excluded from the area."]
    return m


# ----------------------------------------------------------------------------- hip with a bowed eave
BOW_X = [13.0, 14.8, 16.6, 18.4, 20.2, 22.0]
BOW_Y = [0.0, 0.08, 0.16, 0.16, 0.08, 0.0]  # every turn <= 2.6 deg, segments 1.8 ft, offset <= 0.16 ft


def synthetic_hip_zigzag() -> dict[str, Any]:
    """The synthetic hip with 5 short, nearly collinear segments in its south eave (verifier input).

    Seven south eave edges: 13 ft, five of 1.8 ft, 13 ft, every turn and every segment within 3 deg of
    the whole line, so the deterministic merge collapses all seven into one 35 ft eave (area moves ~0.9 sq ft).
    """
    bs, rbs = synthetic_hip()
    m = labelled(build_model(bs, rbs, {"method": "fixture"}))
    bow = [[x, y] for x, y in zip(BOW_X, BOW_Y, strict=True)]
    ring = [[0.0, 0.0], *bow, [35.0, 0.0]]  # south edge, west to east
    south = [[a, b] for a, b in itertools.pairwise(ring)]
    slope = math.sqrt(1 + (4 / 12) ** 2)
    f1 = next(f for f in m["facets"] if [0.0, 0.0] in f["polygon"] and [35.0, 0.0] in f["polygon"])
    poly = f1["polygon"]
    i = poly.index([0.0, 0.0])
    f1["polygon"] = poly[: i + 1] + ring[1:-1] + poly[i + 1:]
    f1["plan_area_sqft"] = Polygon(f1["polygon"]).area
    f1["area_sqft"] = f1["plan_area_sqft"] * slope
    blk = m["blocks"][0]
    j = blk["polygon"].index([0.0, 0.0])
    blk["polygon"] = blk["polygon"][: j + 1] + ring[1:-1] + blk["polygon"][j + 1:]
    blk["plan_area_sqft"] = Polygon(blk["polygon"]).area
    old = next(e for e in m["edges"] if e["points"] == [[0.0, 0.0], [35.0, 0.0]])
    at = m["edges"].index(old)
    m["edges"][at:at + 1] = [_edge(0, "eave", a, b, f1["id"]) for a, b in south]
    for n, e in enumerate(m["edges"], start=1):
        e["id"] = f"e{n}"
    _retotal(m)
    return m


# ----------------------------------------------------------------------------- Solar response
def synthetic_solar_response() -> dict[str, Any]:
    """A ``buildingInsights`` document shaped like Google's, placed on the site1 blocks fixture.

    Segment s0-s3 are the four hip faces (21 deg, azimuths from the blocks), s4-s5 the sloped
    outliers, s6-s8 the flat blocks. Coordinates are WGS84 near 0/0 derived from the blocks frame.
    """
    src = json.loads((FIXTURES / "site1_blocks.json").read_text())
    fr = src["frame"]
    tf = Transformer.from_crs(int(fr["epsg"]), 4326, always_xy=True)

    def ll(x_ft: float, y_ft: float) -> dict[str, float]:
        lng, lat = tf.transform(fr["x0_m"] + x_ft * M_PER_FT, fr["y0_m"] + y_ft * M_PER_FT)
        return {"latitude": round(lat, 8), "longitude": round(lng, 8)}

    by = {b["id"]: b for b in src["blocks"]}
    order = [("k3", 21.0), ("k4", 21.0), ("k5", 21.0), ("k6", 21.0), ("k7", 12.0), ("k8", 12.0),
             ("k0", 0.5), ("k1", 0.5), ("k2", 0.5)]
    segs = []
    for bid, deg in order:
        b = by[bid]
        poly = Polygon(b["polygon_ft"])
        x0, y0, x1, y1 = poly.bounds
        ground = b["plan_area_sqft"] * 0.09290304
        segs.append({
            "pitchDegrees": deg, "azimuthDegrees": b["aspect_deg"] if b["aspect_deg"] is not None else 180.0,
            "stats": {"areaMeters2": round(ground / math.cos(math.radians(deg)), 2), "sunshineQuantiles": [],
                      "groundAreaMeters2": round(ground, 2)},
            "center": ll(poly.centroid.x, poly.centroid.y),
            "boundingBox": {"sw": ll(x0, y0), "ne": ll(x1, y1)},
            "planeHeightAtCenterMeters": round(b["mean_z_ft"] * M_PER_FT, 2)})
    return {"_SYNTHETIC": True,
            "_note": "SYNTHETIC buildingInsights-shaped document built by roof_measure.synth_extra; not a Google response.",
            "name": "buildings/SYNTHETIC-0", "center": ll(*Polygon(src["footprint_ft"]).centroid.coords[0]),
            "postalCode": "90000", "regionCode": "US", "imageryDate": {"year": 2023, "month": 6, "day": 15},
            "imageryQuality": "HIGH",
            "solarPotential": {"wholeRoofStats": {"areaMeters2": round(sum(s["stats"]["areaMeters2"] for s in segs), 2),
                                                  "groundAreaMeters2": round(sum(s["stats"]["groundAreaMeters2"] for s in segs), 2)},
                               "roofSegmentStats": segs}}


def deep(model: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(model)


def write_json(path: Path, obj: Any) -> None:
    from .model import _round

    path.write_text(json.dumps(_round(obj), indent=1) + "\n")


def write_raw(path: Path, obj: Any) -> None:
    """Like ``write_json`` without the 5 decimal rounding (the Solar response keeps 8 decimal degrees)."""
    path.write_text(json.dumps(obj, indent=1) + "\n")


__all__ = ["SITE1_FRAME", "synthetic_flat_curbs", "synthetic_hip_zigzag", "synthetic_solar_response"]
