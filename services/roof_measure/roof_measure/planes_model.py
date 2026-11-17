"""A roof model built straight from the measured planes: one facet per plane, edges typed from geometry.

The straight-skeleton blocks cannot draw a house whose ridges are off-centre or whose sections differ in height. The
measured planes can: each plane is one facet; every boundary piece is either on the outline (eave, rake, or the
high side of a single plane) or shared with a neighbour, and a shared piece is typed from the heights and slopes of
the two planes (ridge, hip, valley, step or wall flashing). The result is the ordinary ``bond.roof_model/0.1``.

Blocks: the schema wants blocks that tile into facets, so each plane is its own ``shed`` block (polygon = the plane,
its pitch, ``ridge_azimuth_deg`` null). ``source.from_planes`` is true; nothing else about the shape changes.

``planes_model_ok`` is the gate: coverage, overlap, facet shape, classified edges and area. A model that fails it is
never returned (the pipeline keeps what it had).
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from typing import Any

from shapely.geometry import LineString, MultiLineString, MultiPoint, Point, Polygon
from shapely.ops import snap, unary_union

from .classify import BlockSet
from .model import SCHEMA, ModelError, _cleanup_edges, _totals, validate

log = logging.getLogger("roof_measure.planes_model")

SNAP_FT = 0.5  # vertices of different planes closer than this are one vertex
TAPER_STEP_FT = 1.5
ENVELOPE_KINDS = ("ridge", "hip", "valley", "step", "seam")  # bf-planes' in-place borders say intersection/step: ignored
SNAP_LINE_FT = 0.4
OWN_FT = 0.2  # a noded piece belongs to every plane whose outline passes this close
SHARE_FT = 0.25  # boundary pieces this close are the same border
STEP_FT = 1.5  # a height difference across a shared edge above this is a wall step
SLOPE_COS = 0.3  # |outward normal . downslope| above this: the edge faces down or up the slope
HORIZONTAL = 0.1  # rise over run of an edge under this counts as horizontal (a ridge, not a hip)
MIN_PIECE_FT = 0.3
FLAT_RISE = 0.5
OUTER_ROUND = 5


def _sub_rad(plane: Any) -> tuple[float, float]:
    a = math.radians(plane.aspect_deg or 0.0)
    return math.sin(a), math.cos(a)


class _P:
    """A plane prepared for edge work: polygon, downslope unit vector, slope, and the height function."""

    def __init__(self, idx: int, plane: Any, ring: list[tuple[float, float]]) -> None:
        self.idx, self.src, self.ring = idx, plane, ring
        whole = Polygon(ring).buffer(0)  # snapping can pinch a narrow neck shut: keep the largest part
        parts = [g for g in getattr(whole, "geoms", [whole]) if g.geom_type == "Polygon" and not g.is_empty]
        self.poly = max(parts, key=lambda g: g.area) if parts else Polygon()
        eq = getattr(plane, "plane_eq", None)
        c = self.poly.centroid
        grad = math.hypot(eq[0], eq[1]) if eq else 0.0
        if eq and grad > 1e-9:  # the common-datum equation decides slope and facing (down = against the gradient)
            self.s, self.d = grad, (-eq[0] / grad, -eq[1] / grad)
            self.flat = grad * 12.0 < FLAT_RISE
        else:
            self.flat = plane.aspect_deg is None or plane.pitch_rise < FLAT_RISE
            self.s = 0.0 if self.flat else plane.pitch_rise / 12.0
            self.d = (0.0, 0.0) if self.flat else _sub_rad(plane)
        if self.flat:
            self.s, self.d = 0.0, (0.0, 0.0)
        self._eq = list(eq) if eq else None
        self._h0 = (plane.height_ft, c.x, c.y)

    def z(self, x: float, y: float) -> float:
        if self._eq is not None:
            return self._eq[0] * x + self._eq[1] * y + self._eq[2]
        h, cx, cy = self._h0
        return h - self.s * ((x - cx) * self.d[0] + (y - cy) * self.d[1])


def _snap(rings: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Move vertices of different planes that are within ``SNAP_FT`` of each other onto one shared vertex."""
    reps: list[tuple[float, float]] = []
    out = []
    for ring in rings:
        new = []
        for x, y in ring:
            hit = next((r for r in reps if math.dist(r, (x, y)) <= SNAP_FT), None)
            if hit is None:
                reps.append((x, y))
                hit = (x, y)
            if not new or math.dist(new[-1], hit) > 1e-9:
                new.append(hit)
        if len(new) > 1 and math.dist(new[0], new[-1]) < 1e-9:
            new.pop()
        out.append(new)
    return out


def _segments(geom: Any) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    lines = [geom] if geom.geom_type == "LineString" else [g for g in getattr(geom, "geoms", [])
                                                           if g.geom_type == "LineString"]
    out = []
    for ln in lines:
        c = list(ln.coords)
        out.extend(((c[i][0], c[i][1]), (c[i + 1][0], c[i + 1][1])) for i in range(len(c) - 1)
                   if math.dist(c[i], c[i + 1]) >= MIN_PIECE_FT)
    return out


def _runs_along(boundary: Any, a: tuple[float, float], b: tuple[float, float]) -> bool:
    """True when segment a-b lies along ``boundary`` (both ends within the share tolerance, direction within 20 deg)."""
    line = LineString([a, b])
    if boundary.distance(Point(a)) > SHARE_FT or boundary.distance(Point(b)) > SHARE_FT:
        return False
    mid = line.interpolate(0.5, normalized=True)
    c = list(boundary.coords) if boundary.geom_type == "LineString" else [pt for g in boundary.geoms for pt in g.coords]
    best = min(range(len(c) - 1), key=lambda k: LineString([c[k], c[k + 1]]).distance(mid))
    ang = abs(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]) - math.atan2(c[best + 1][1] - c[best][1],
                                                                           c[best + 1][0] - c[best][0]))) % 180.0
    return min(ang, 180.0 - ang) <= 20.0


def _is_seam(seams: list[Any], a: tuple[float, float], b: tuple[float, float]) -> bool:
    mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return any(sm.distance(mid) < 0.15 for sm in seams)


def _border_kind(borders: list[Any], ia: Any, ib: Any, mid: Point, a: tuple[float, float],
                 b: tuple[float, float]) -> str | None:
    """The envelope border kind of the edge a-b between planes ``ia`` and ``ib`` (nearest parallel record), or None.

    A ``hip`` whose median height step is ``TAPER_STEP_FT`` or more is a tapering step (0 ft at one end, several at the
    other), not a hip: it comes back as ``transition``, which adds to no flashing or cap total."""
    best = None
    for rec, line in borders:
        if rec.get("kind") not in ENVELOPE_KINDS or {rec.get("a"), rec.get("b")} != {ia, ib} or line.distance(mid) > 0.15:
            continue
        c = list(line.coords)
        ang = abs(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]) - math.atan2(c[-1][1] - c[0][1], c[-1][0] - c[0][0]))) % 180.0
        if min(ang, 180.0 - ang) <= 15.0 and (best is None or line.distance(mid) < best[0]):
            kind = rec.get("kind")
            if kind == "hip" and abs(rec.get("step_ft") or 0.0) >= TAPER_STEP_FT:
                kind = "transition"
            best = (line.distance(mid), kind)
    return None if best is None else best[1]


def _step_type(p: _P, q: _P, a: tuple[float, float], b: tuple[float, float]) -> str:
    """Step flashing along the LOWER plane's slope (within 30 deg), wall flashing across it at the lower plane's high side."""
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    low = p if p.z(*mid) < q.z(*mid) else q
    if low.flat:
        return "wall_flashing"
    length = _plan_len(a, b)
    u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    along = abs(u[0] * low.d[0] + u[1] * low.d[1])
    if math.degrees(math.acos(min(1.0, along))) <= 30.0:
        return "step_flashing"
    n = _outward(low, a, b)  # from the lower plane toward the higher one
    return "wall_flashing" if n[0] * low.d[0] + n[1] * low.d[1] < -SLOPE_COS else "step_flashing"


def _outward(p: _P, a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """Outward unit normal of segment a-b of plane ``p`` (probe the side that is not inside the polygon)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = dy / length, -dx / length
    mid = Point((a[0] + b[0]) / 2 + nx * 0.05, (a[1] + b[1]) / 2 + ny * 0.05)
    return (nx, ny) if not p.poly.contains(mid) else (-nx, -ny)


def _plan_len(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.dist(a, b)


def _classify_outer(p: _P, a: tuple[float, float], b: tuple[float, float]) -> str:
    if p.flat:
        return "parapet"
    n = _outward(p, a, b)
    dot = n[0] * p.d[0] + n[1] * p.d[1]
    return "eave" if dot > math.cos(math.radians(45)) else "ridge" if dot < -math.cos(math.radians(45)) else "rake"


def _classify_shared(p: _P, q: _P, a: tuple[float, float], b: tuple[float, float]) -> tuple[str, float]:
    """``(type, 3D length)`` of the edge a-b between planes p and q."""
    plan = _plan_len(a, b)
    za = (p.z(*a) + q.z(*a)) / 2
    zb = (p.z(*b) + q.z(*b)) / 2
    length = math.hypot(plan, zb - za)
    dz = max(abs(p.z(*a) - q.z(*a)), abs(p.z(*b) - q.z(*b)))
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if dz > STEP_FT:
        low = p if p.z(*mid) < q.z(*mid) else q
        if low.flat:
            return "wall_flashing", length
        n = _outward(low, a, b)  # points from the lower plane toward the higher one
        up = n[0] * low.d[0] + n[1] * low.d[1]
        return ("wall_flashing" if up < -SLOPE_COS else "step_flashing"), length
    np_, nq = _outward(p, a, b), _outward(q, a, b)
    away_p = -(np_[0] * p.d[0] + np_[1] * p.d[1])  # > 0: p falls away from the edge
    away_q = -(nq[0] * q.d[0] + nq[1] * q.d[1])
    horizontal = abs(zb - za) <= HORIZONTAL * plan
    if away_p > SLOPE_COS and away_q > SLOPE_COS:
        return ("ridge" if horizontal else "hip"), length
    if away_p < -SLOPE_COS and away_q < -SLOPE_COS:
        return "valley", length
    if (away_p > SLOPE_COS and away_q < -SLOPE_COS) or (away_p < -SLOPE_COS and away_q > SLOPE_COS):
        return "transition", length  # the slope carries on across the edge
    total = away_p + away_q  # one side runs along the edge: it follows the other
    if abs(total) <= 0.1:  # both run along the edge: one surface split by a line down its slope
        return "transition", length
    if total > 0:
        return ("ridge" if horizontal else "hip"), length
    return "valley", length


def model_from_planes(planes: list[Any], footprint: Polygon | list[Any], source: dict[str, Any] | None = None,
                      base: BlockSet | None = None, notes: list[str] | None = None,
                      borders: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The 0.1 model of ``planes`` (``planes.Plane`` objects). Raises :class:`ModelError` when it cannot be built.

    ``borders`` (planes_envelope's) mark seams: two planes of one face cut in two draw no edge there.
    ``base`` supplies address, origin and provenance (optional). The model is validated before it is returned.
    """
    if not planes:
        raise ModelError("no planes to build a model from")
    fp = footprint if isinstance(footprint, Polygon) else Polygon(footprint)
    rings = _snap([[tuple(pt) for pt in p.polygon] for p in planes])
    ps = [_P(i, pl, r) for i, (pl, r) in enumerate(zip(planes, rings, strict=True)) if len(r) >= 3]
    ps = [p for p in ps if not p.poly.is_empty and p.poly.area > 0.5]
    if not ps:
        raise ModelError("the planes have no usable polygon")
    facets, blocks = [], []
    for k, p in enumerate(ps, start=1):
        ring = list(p.poly.exterior.coords)[:-1]
        if sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
               for i in range(len(ring))) < 0:
            ring = ring[::-1]
        pitch = 0.0 if p.flat else float(p.src.pitch_rise)
        area = p.poly.area
        facets.append({"id": f"f{k}", "block": f"b{k}", "kind": "flat" if p.flat else "sloped",
                       "polygon": [[x, y] for x, y in ring], "pitch_rise": pitch,
                       "aspect_deg": None if p.flat else float(p.src.aspect_deg),
                       "plan_area_sqft": area, "area_sqft": area * math.sqrt(1 + (pitch / 12) ** 2)})
        blocks.append({"id": f"b{k}", "form": "flat" if p.flat else "shed", "polygon": [[x, y] for x, y in ring],
                       "pitch_rise": pitch, "ridge_azimuth_deg": None, "gable_edges": [],
                       "eave_height_ft": float(p.src.height_ft), "plan_area_sqft": area,
                       **({} if p.flat else {"aspect_deg": float(p.src.aspect_deg)})})
    edges: list[dict[str, Any]] = []
    fid = {p.idx: f"f{k}" for k, p in enumerate(ps, start=1)}
    border_list = [(b, LineString(b["segment"])) for b in (borders or []) if b.get("segment")]
    interior_len = disagree_len = 0.0
    verts = MultiPoint([pt for p in ps for pt in p.poly.exterior.coords])
    # snap every outline onto every vertex first: a vertex of one plane lying on the side of another splits that side,
    # and two outlines that run along the same border become the same segments (one edge per segment)
    noded = unary_union([snap(p.poly.boundary, verts, SNAP_LINE_FT) for p in ps])
    lines = list(noded.geoms) if hasattr(noded, "geoms") else [noded]
    for a, b in _segments(MultiLineString(lines)):  # one piece per segment, split at every vertex of any plane
        mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        owners = [p for p in ps if p.poly.boundary.distance(mid) < OWN_FT]
        if len(owners) == 1:
            p = owners[0]
            typ = _classify_outer(p, a, b)
            length = math.hypot(_plan_len(a, b), p.z(*b) - p.z(*a)) if not p.flat else _plan_len(a, b)
            edges.append({"type": typ, "points": [a, b], "length_ft": length, "facets": [fid[p.idx]]})
            continue
        if len(owners) < 2:
            continue
        p, q = owners[0], owners[1]
        own, length = _classify_shared(p, q, a, b)
        kind = _border_kind(border_list, getattr(p.src, "id", None), getattr(q.src, "id", None), mid, a, b)
        interior_len += length
        typ = own
        if kind is not None:
            if kind == "seam":
                if own not in ("transition", "ridge", "hip", "valley"):
                    disagree_len += length
                continue  # one face cut in two: not a roof line
            typ = _step_type(p, q, a, b) if kind == "step" else kind
            if kind == "transition":
                if own not in ("hip", "transition", "step_flashing", "wall_flashing"):
                    disagree_len += length
            elif (kind == "step") != (own in ("step_flashing", "wall_flashing")) or (kind != "step" and kind != own):
                disagree_len += length
        edges.append({"type": typ, "points": [a, b], "length_ft": length, "facets": [fid[p.idx], fid[q.idx]]})
    edges = _cleanup_edges(edges)
    meta = (base.footprint_meta if base else {}) or {}
    lidar = (base.lidar if base else {}) or {}
    src = dict(source or {})
    model: dict[str, Any] = {
        "schema": SCHEMA, "generated_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "address": dict(base.address) if base else {}, "origin": dict(base.origin) if base else {},
        "north_deg": 0, "units": "ft",
        "source": {"method": src.get("method", "lidar_skeleton"),
                   "footprint": {"provider": meta.get("provider"), "id": str(meta["id"]) if meta.get("id") is not None else None,
                                 "area_sqft": meta.get("area_sqft", fp.area)},
                   "lidar": ({k: lidar.get(k) for k in ("project", "acquired", "points_on_roof", "density_per_m2")}
                             if lidar else None),
                   "solar": src.get("solar"), "from_planes": True},
        "blocks": blocks, "facets": facets,
        "edges": [{"id": f"e{n}", "type": e["type"], "points": [list(e["points"][0]), list(e["points"][1])],
                   "length_ft": e["length_ft"], "facets": e["facets"]} for n, e in enumerate(edges, start=1)],
        "holes": [], "totals": _totals(facets, edges),
        "confidence": {"overall": "medium", "notes": [
            "Built directly from the measured roof planes: one facet per plane, edges typed from plane heights and slopes.",
            *(notes or [])]},
        "warnings": [], "debug": {}}
    model["debug"]["typing_disagreement"] = disagree_len / interior_len if interior_len > 0 else 0.0
    model["debug"]["plane_ids"] = [getattr(p.src, "id", None) for p in ps]  # facet f{k} is plane_ids[k - 1]
    if src.get("agent"):
        model["debug"]["agent"] = src["agent"]
    validate(model)
    return model


def planes_model_ok(model: dict[str, Any], planes: list[Any], footprint: Polygon | list[Any]) -> tuple[bool, list[str]]:
    """``(ok, reasons)``: coverage >= 95% of the outline, overlap <= 1%, 3-12 vertices a facet, every shared edge
    classified, total area within 3% of the planes' surface area. ``reasons`` names each failed check."""
    fp = footprint if isinstance(footprint, Polygon) else Polygon(footprint)
    reasons: list[str] = []
    polys = [Polygon(f["polygon"]).buffer(0) for f in model["facets"]]
    if not polys:
        return False, ["no_facets"]
    union = unary_union(polys)
    cover = union.intersection(fp).area / fp.area if fp.area > 0 else 0.0
    if cover < 0.95:
        reasons.append(f"coverage {100 * cover:.0f}% under 95%")
    overlap = (sum(p.area for p in polys) - union.area) / max(union.area, 1e-9)
    if overlap > 0.01:
        reasons.append(f"overlap {100 * overlap:.1f}% over 1%")
    if any(not 3 <= len(f["polygon"]) <= 12 for f in model["facets"]):
        reasons.append("a facet has under 3 or over 12 vertices")
    if any(e["type"] == "unspecified" and e["length_ft"] > 1.0 for e in model["edges"]):
        reasons.append("an edge could not be classified")
    want = sum(p.surface_area_sqft for p in planes)
    got = model["totals"]["total_area_sqft"]
    if want > 0 and abs(got - want) / want > 0.03:
        reasons.append(f"area {got:.0f} differs from the planes' {want:.0f} by over 3%")
    try:
        validate(model)
    except ModelError as exc:  # includes spikes under 10 degrees
        reasons.append(f"invalid: {exc}")
    return not reasons, reasons


CODE = "model_from_planes"
WARNING = "The diagram was built from the measured roof planes."
REASON = "from_planes"
NOT_VERIFIED = "The diagram was built from the measured roof planes, so it was not verified."
BAD_MISMATCH_PCT = 15.0
BAD_UNCOVERED_PCT = 10.0
PARTITION_METHODS = ("envelope", "arrangement")  # planes_envelope's partition: planes that tile the outline
MAX_TRANSITION_SHARE = 0.20  # one tapering step beside a cross gable is about 12% on a small house
MAX_DISAGREEMENT = 0.15  # share of interior edge length where our own typing and the envelope's kind differ


_LEVELS = ("low", "medium", "high")
_BLOCK_NOTES = ("Wall flashing is not derivable", "Parapet assigned by rule", "Awnings are small")  # about block edges


def _inherit(new: dict[str, Any], old: dict[str, Any], planes_only: bool) -> None:
    """What the replaced model knew that the planes model keeps (additive): ``source.lidar.fitted_area_sqft``, its
    coverage and density notes, and a confidence never above the replaced one's: at most "medium", "low" when the
    replaced result was planes-only."""
    lid_old = ((old.get("source") or {}).get("lidar") or {}) if isinstance(old, dict) else {}
    lid_new = (new.get("source") or {}).get("lidar")
    if isinstance(lid_new, dict) and lid_old.get("fitted_area_sqft") is not None:
        lid_new["fitted_area_sqft"] = lid_old["fitted_area_sqft"]
    conf_old = (old.get("confidence") or {}) if isinstance(old, dict) else {}
    level = "medium"
    if planes_only:
        level = "low"
    elif conf_old.get("overall") in _LEVELS:
        level = min(conf_old["overall"], "medium", key=_LEVELS.index)
    notes = new["confidence"]["notes"]
    carried = [n for n in conf_old.get("notes", []) if isinstance(n, str) and not n.startswith(_BLOCK_NOTES)
               and n not in notes]
    new["confidence"] = {"overall": level, "notes": [*notes, *carried]}


def replacement_gate(model: dict[str, Any], planes: list[Any]) -> list[str]:
    """Extra checks before a planes model REPLACES a block model (not for the planes-only exception); reasons or []."""
    why: list[str] = []
    edges = model["edges"]
    if any(e["type"] == "unspecified" for e in edges):
        why.append("an unspecified edge")
    interior = [e for e in edges if len(e["facets"]) == 2]
    total = sum(e["length_ft"] for e in interior)
    if total > 0 and sum(e["length_ft"] for e in interior if e["type"] == "transition") >= MAX_TRANSITION_SHARE * total:
        why.append("transition edges are 20% or more of the interior edges")
    if not any(e["type"] in ("ridge", "hip") for e in edges):
        why.append("no ridge or hip")
    if model.get("debug", {}).get("typing_disagreement", 0.0) > MAX_DISAGREEMENT:
        why.append("the height-based edge typing disagrees with the envelope's kinds on over 15% of the interior edges")
    return why


def replace_if_bad(base: BlockSet, model: dict[str, Any], source: dict[str, Any], planes_only: bool,
                   warning_codes: list[str]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """``(planes model, metrics of the model it replaces)``, or ``None`` when the block model stays.

    Replace only when the current result is planes-only (any planes will do: a typed diagram beats none), or its
    ``plane_mismatch_pct`` is 15 or more, or ``model_uncovered_pct`` 10 or more AND every plane comes from the partition
    (``straighten_method`` envelope or arrangement) AND the planes model passes both gates (``replacement_gate`` too).
    Never raises: any failure leaves the caller's model as it was.
    """
    from .planes import snap_with_stats
    from .quality import plane_metrics

    if not base.blocks:
        return None
    try:
        snap = snap_with_stats(base, clip_to_footprint="parcel_street_match" not in warning_codes)
        if snap.failed or not snap.planes:
            return None
        # the model is built from exactly the planes snapping publishes (quality._assess snaps the same base the
        # same way into model.planes): no second partition here, whose planes would never be published
        planes, borders = snap.planes, getattr(snap, "borders", None)
        old: dict[str, Any] = {"block_model_mismatch_pct": None, "block_model_uncovered_pct": None}
        if not planes_only:
            if any(getattr(p, "straighten_method", None) not in PARTITION_METHODS for p in planes):
                return None
            q = plane_metrics(planes, model, covered_pct=snap.covered_pct, warning_codes=warning_codes)
            if (q["plane_mismatch_pct"] or 0.0) < BAD_MISMATCH_PCT and (q["model_uncovered_pct"] or 0.0) < BAD_UNCOVERED_PCT:
                return None
            old = {"block_model_mismatch_pct": q["plane_mismatch_pct"], "block_model_uncovered_pct": q["model_uncovered_pct"]}
        planes_model = model_from_planes(planes, base.footprint, source, base, borders=borders)
        _inherit(planes_model, model, planes_only)
        ok, _reasons = planes_model_ok(planes_model, planes, base.footprint)
        if ok and not planes_only and replacement_gate(planes_model, planes):
            ok = False
    except Exception as exc:  # the block model (or planes-only result) stays: this step may only improve a roof
        log.info("planes model not used: %s", type(exc).__name__, exc_info=True)
        return None
    return (planes_model, old) if ok else None
