"""The one edge typer of the engine: interior creases (ridge, hip, valley, level_change, transition) and the roof
edge (eave, rake, flat_edge). Lengths in feet (3D), geometry in metres, in the frame the facets are in.

Rules (plan 3.1 / contract 0.4):
  * a pitched facet's outline edge is an ``eave`` where it faces down the slope, a ``rake`` along the slope, and a
    ``rake`` with ``high_edge=True`` where it is the level high side (a shed or lean-to wall line): never a ridge;
  * a flat facet's outline edge is a ``flat_edge``;
  * a seam shared by two facets is a ``level_change`` (with ``jump_ft``) when the height jump measured from the points
    on both sides is 0.3 m or more, a ``transition`` where pitched meets flat at one height, else a ridge, hip or
    valley from the two planes; coplanar facets (flat membrane included) share no edge (``coplanar_seams`` lists them:
    those facets should have been merged);
  * a ``level_change`` between two FLAT facets must also hold along the seam (``edge_measure.seam_is_level``: the
    two facets' fitted planes are at least 0.3 m apart at 70% of the stations along the seam, and ``jump_ft`` is their median offset); otherwise it is a ``flat_seam``: drawn,
    never priced, in no total (0.5.1);
  * collinear pieces of one type between the same facets are one edge.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.ops import unary_union

from .edge_measure import measured_jump, ridge_check, seam_is_level, seg_split
from .errors import Ctx
from .params import EngineParams
from .plane_math import zat
from .types import Edge, Facet

M2F = 1 / 0.3048
SHARE_TOL_M = 1e-3  # facets of one partition share vertices exactly: boundaries this close are the same line


def _into(f: Facet, p0: np.ndarray, p1: np.ndarray) -> np.ndarray:
    """Unit plan normal of the segment p0-p1 pointing into facet ``f`` (probed just beside the segment, so it is right
    for a concave facet whose far parts lie on both sides of the segment's line)."""
    d = p1 - p0
    n = np.array([-d[1], d[0]]) / max(float(np.hypot(*d)), 1e-12)
    mid = (p0 + p1) / 2
    for step in (0.05, 0.15, 0.4):
        if f.polygon.contains(shapely.Point(*(mid + step * n))):
            return n
        if f.polygon.contains(shapely.Point(*(mid - step * n))):
            return -n
    c = np.array(f.polygon.representative_point().coords[0])
    return n if float(np.dot(c - mid, n)) >= 0 else -n


def _crease(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, p: EngineParams) -> str:
    """ridge / hip / valley / transition from the slopes of the two planes across the segment: both fall away from it
    (ridge when it is level, else hip), both rise towards it (valley), else one slope carries on across it."""
    n = _into(fa, p0, p1)
    eps = 0.5 * p.seam_gdiff
    sa = fa.plane[0] * n[0] + fa.plane[1] * n[1]  # slope going into A
    sb = -(fb.plane[0] * n[0] + fb.plane[1] * n[1])  # slope going into B
    if sa < -eps and sb < -eps:
        length = float(np.hypot(*(p1 - p0)))
        dz = zat(fa.plane, *p1) - zat(fa.plane, *p0)
        return "ridge" if abs(dz) / max(length, 1e-6) < p.ridge_slope else "hip"
    if sa > eps and sb > eps:
        return "valley"
    return "transition"


def seg_type_interior(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, q: np.ndarray | None, p: EngineParams,
                      big_flat: set[str] | None = None) -> tuple[str | None, float, str]:
    """(type or None, jump m, why) of a segment shared by two facets; ``why`` says why there is no edge (``seam``:
    coplanar or two flat facets with no verified jump, they should be one facet; ``kink``: the slope carries on;
    ``small_flat``: a flat facet too small for a transition, planes near-coplanar).

    ``level_change`` only when the points show a jump of 0.3 m or more. ``transition`` only where a pitched facet meets a
    flat facet of real size (``big_flat`` ids; None = every flat facet counts); otherwise the planes decide (ridge, hip,
    valley) or the line is dropped."""
    pa, pb = fa.plane, fb.plane
    jump = measured_jump(fa, fb, p0, p1, q)
    flat_a, flat_b = fa.roof_type == "flat", fb.roof_type == "flat"
    if jump >= p.level_change_m:
        return "level_change", jump, ""
    if flat_a and flat_b:
        return None, jump, "seam"  # one membrane in two pieces: no line on the roof
    coplanar = float(np.hypot(pa[0] - pb[0], pa[1] - pb[1])) < p.seam_gdiff
    if flat_a != flat_b:
        flat = fa if flat_a else fb
        if big_flat is None or flat.id in big_flat:
            return "transition", jump, ""
        if coplanar:
            return None, jump, "small_flat"
        c = _crease(fa, fb, p0, p1, p)
        return (None, jump, "small_flat") if c == "transition" else (c, jump, "")
    if coplanar:
        return None, jump, "seam"
    c = _crease(fa, fb, p0, p1, p)
    return (None, jump, "kink") if c == "transition" else (c, jump, "")


def real_flats(facets: list[Facet], p: EngineParams) -> set[str]:
    """Ids of the flat facets big enough for a transition: at least ``transition_min_flat_m2`` and that share of the roof."""
    total = sum(f.polygon.area for f in facets) or 1.0
    return {f.id for f in facets if f.roof_type == "flat" and f.polygon.area >= p.transition_min_flat_m2
            and f.polygon.area >= p.transition_min_flat_share * total}


HIGH_EDGE = "rake_high"  # inside this module only: a rake that is the level high side of a pitched facet


def seg_type_exterior(f: Facet, p0: np.ndarray, p1: np.ndarray) -> str:
    """Type of a segment on the roof edge: flat_edge, eave (faces down-slope), rake, or ``HIGH_EDGE`` (a rake)."""
    if f.roof_type == "flat":
        return "flat_edge"
    d = p1 - p0
    length = float(np.hypot(*d))
    if length < 1e-6:
        return "eave"
    u = d / length
    n = np.array([u[1], -u[0]]) if f.polygon.exterior.is_ccw else np.array([-u[1], u[0]])  # outward normal
    r = math.radians(f.aspect_deg)
    c = float(np.dot(n, np.array([math.sin(r), math.cos(r)])))
    if c > 0.5:
        return "eave"
    if c < -0.5:
        return HIGH_EDGE  # the high edge of a pitched facet on the outline: a rake (wall cap), never a ridge
    return "rake"


def _raw_segments(facets: list[Facet], q: np.ndarray | None, p: EngineParams, seams: list | None = None) -> list:
    """(type, a, b, facet-index tuple) for every boundary piece: shared ones typed by seg_type_interior. Pieces that
    are no edge are appended to ``seams`` as (facet ids, length m, why) when it is given."""
    big = real_flats(facets, p)
    polys = [f.polygon for f in facets]
    bufs = [g.buffer(SHARE_TOL_M) for g in polys]
    raw = []
    for i, fa in enumerate(facets):
        bd = polys[i].boundary
        others = []
        for j, fb in enumerate(facets):
            if j == i or not bufs[j].intersects(bd):
                continue
            others.append(bufs[j])
            if j > i:
                for a, b in seg_split(bd.intersection(bufs[j])):
                    tt, _, why = seg_type_interior(fa, fb, a, b, q, p, big)
                    if tt is not None:
                        raw.append((tt, a, b, (i, j)))
                    elif seams is not None:
                        seams.append(((fa.id, fb.id), float(np.hypot(*(b - a))), why))
        ext = bd.difference(unary_union(others)) if others else bd
        for a, b in seg_split(ext):
            raw.append((seg_type_exterior(fa, a, b), a, b, (i,)))
    return raw


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.hypot(*v) + 1e-12)


def _grow(chain: list, segs: list, used: list[bool], forward: bool, cos_tol: float) -> None:
    """Extend the chain at one end with unused collinear segments whose end meets it (within 5 cm)."""
    grew = True
    while grew:
        grew = False
        for k, (a, b) in enumerate(segs):
            if used[k]:
                continue
            end = chain[-1] if forward else chain[0]
            d0 = _unit(chain[-1] - chain[-2] if forward else chain[0] - chain[1])
            for u, v in ((a, b), (b, a)):
                if np.hypot(*(u - end)) < 0.05 and abs(np.dot(d0, _unit(v - u))) > cos_tol:
                    chain.append(v) if forward else chain.insert(0, v)
                    used[k] = True
                    grew = True
                    break
            if grew:
                break


def _chains(raw: list, p: EngineParams) -> list:
    """Collinear, same-type, same-facets segments merged into chains: [(type, facet-index tuple, p0, p1)]."""
    groups: dict = {}
    for t, a, b, fs in raw:
        if np.hypot(*(b - a)) < p.edge_min_seg_m:
            continue
        groups.setdefault((t, fs), []).append((a, b))
    cos_tol = math.cos(math.radians(p.chain_angle_deg))
    out = []
    for (t, fs), segs in groups.items():
        used = [False] * len(segs)
        for s0 in range(len(segs)):
            if used[s0]:
                continue
            used[s0] = True
            chain = [segs[s0][0], segs[s0][1]]
            _grow(chain, segs, used, True, cos_tol)
            _grow(chain, segs, used, False, cos_tol)
            out.append((t, fs, chain[0], chain[-1]))
    return out


def _end_heights(t: str, facets: list[Facet], fs: tuple, p0: np.ndarray, p1: np.ndarray) -> tuple[float, float]:
    fa = facets[fs[0]]
    if t in ("ridge", "hip", "valley") and len(fs) == 2:
        fb = facets[fs[1]]
        return ((zat(fa.plane, *p0) + zat(fb.plane, *p0)) / 2, (zat(fa.plane, *p1) + zat(fb.plane, *p1)) / 2)
    if t == "level_change" and len(fs) == 2:  # a vertical step: its line runs at the LOWER roof's height
        fb = facets[fs[1]]
        mid = (p0 + p1) / 2
        lo = fa if zat(fa.plane, *mid) <= zat(fb.plane, *mid) else fb
        return zat(lo.plane, *p0), zat(lo.plane, *p1)
    return zat(fa.plane, *p0), zat(fa.plane, *p1)


def _refine_step(t: str, facets: list[Facet], fs: tuple, p0: np.ndarray, p1: np.ndarray, q: np.ndarray | None) -> str:
    """A level change between two opposed pitched facets with a small height gap may really be a ridge or valley."""
    if t != "level_change" or len(fs) != 2 or q is None:
        return t
    fa, fb = facets[fs[0]], facets[fs[1]]
    if fa.roof_type == "pitched" and fb.roof_type == "pitched":
        da = abs(((fa.aspect_deg - fb.aspect_deg) + 180) % 360 - 180)
        mid = (p0 + p1) / 2
        gp = abs(zat(fa.plane, *mid) - zat(fb.plane, *mid))
        if da > 130 and gp < 1.0:
            rc = ridge_check(p0, p1, q)
            if rc in ("ridge", "valley"):
                return rc
    return t


def _seam_verdict(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, ctx: Ctx, reuse: bool) -> tuple[bool, float]:
    """``seam_is_level`` for one flat/flat chain, remembered per facet-id pair (drawn pass) or looked up there (priced pass:
    the drawn chain of the same pair within 0.5 m of this chain's middle; none: judged afresh)."""
    key = (fa.id, fb.id)
    mid = (p0 + p1) / 2
    if reuse:
        best = None
        for a, b, verdict in ctx.seam_memo.get(key, ()):
            d = shapely.distance(shapely.LineString([a, b]), shapely.Point(*mid))
            if d <= 0.5 and (best is None or d < best[0]):
                best = (d, verdict)
        if best is not None:
            return best[1]
    verdict = seam_is_level(fa, fb, p0, p1, ctx.p.level_change_m)
    if not reuse:
        ctx.seam_memo.setdefault(key, []).append((p0.copy(), p1.copy(), verdict))
    return verdict


def build_edges(facets: list[Facet], q: np.ndarray | None, ctx: Ctx, absorbed: list | None = None,
                reuse_verdicts: bool = False) -> list[Edge]:
    """All typed edges of the facet partition. ``q`` are the points jumps and ridge checks are measured from.
    A level change that is clutter (shorter than ``stub_min_len_m``, or under ``stub_jump_m`` and shorter than
    ``stub_len_m``) is not an edge: the neighbouring chains carry on; it is appended to ``absorbed`` when given.
    Flat/flat seam verdicts are remembered in ``ctx.seam_memo``; the priced pass (``reuse_verdicts``) re-uses the drawn
    pass's verdict for the same facet pair at the same place, so a seam cannot be a level change in the drawing and a
    flat seam in the priced totals."""
    ctx.check()
    edges = []
    for t, fs, p0, p1 in _chains(_raw_segments(facets, q, ctx.p), ctx.p):
        z0, z1 = _end_heights(t, facets, fs, p0, p1)  # (heights of the typer's first answer: kept as they were before 0.5.1)
        t = _refine_step(t, facets, fs, p0, p1, q)
        plane_gap = None
        if t == "level_change" and len(fs) == 2 and facets[fs[0]].roof_type == "flat" and facets[fs[1]].roof_type == "flat":
            level, plane_gap = _seam_verdict(facets[fs[0]], facets[fs[1]], p0, p1, ctx, reuse_verdicts)
            if not level:
                t = "flat_seam"  # two flat pieces of one deck: a drawn line, never priced (the fitted planes nearly meet)
                plane_gap = None
        high = t == HIGH_EDGE
        t = "rake" if high else t
        length = math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (z1 - z0) ** 2) * M2F
        jm = None
        if len(fs) == 2:
            try:
                jm = round(float(measured_jump(facets[fs[0]], facets[fs[1]], p0, p1, q)), 3)
            except (ValueError, IndexError):
                jm = None
        if plane_gap is not None:
            jm = round(plane_gap, 3)  # a flat/flat level change: its height is the median offset of the two fitted planes
        plan_m = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if t in ("level_change", "flat_seam") and (plan_m < ctx.p.stub_min_len_m or ((jm or 0.0) < ctx.p.stub_jump_m and plan_m < ctx.p.stub_len_m)):
            if absorbed is not None:
                absorbed.append({"type": t, "facets": [facets[k].id for k in fs], "length_ft": round(length, 1),
                                 "jump_ft": None if jm is None else round(jm / 0.3048, 2)})
            continue
        edges.append(Edge(type=t, p0=(float(p0[0]), float(p0[1]), float(z0)), p1=(float(p1[0]), float(p1[1]), float(z1)),
                          length_ft=float(length), facets=tuple(facets[k].id for k in fs), jump_m=jm,
                          jump_ft=round(jm / 0.3048, 2) if t == "level_change" and jm is not None else None,
                          high_edge=high))
    return edges


def edge_diagnostics(facets: list[Facet], p: EngineParams, q: np.ndarray | None = None) -> dict[str, list[dict]]:
    """What the typer left out, for ``model.debug``: ``mergeable`` (neighbouring facets with no line between them:
    coplanar, or two flat facets with no verified jump: they should be one facet), ``kinks`` (a slope that carries on),
    ``small_flat`` (a boundary beside a flat facet too small for a transition) and ``absorbed_level_changes``
    (clutter stubs). Pairs are summed; shared lengths under 0.3 m are left out. Without ``q`` heights come from the planes."""
    seams: list = []
    _raw_segments(facets, q, p, seams)
    by: dict[tuple[str, tuple[str, str]], float] = {}
    for ids, length_m, why in seams:
        by[(why, ids)] = by.get((why, ids), 0.0) + length_m
    out: dict[str, list[dict]] = {"mergeable": [], "kinks": [], "small_flat": []}
    key = {"seam": "mergeable", "kink": "kinks", "small_flat": "small_flat"}
    for (why, ids), m in sorted(by.items()):
        if m >= 0.3:
            out[key[why]].append({"facets": list(ids), "length_ft": round(m * M2F, 1)})
    absorbed: list = []
    build_edges(facets, q, Ctx(p, None), absorbed)
    out["absorbed_level_changes"] = absorbed
    return out


def coplanar_seams(facets: list[Facet], p: EngineParams) -> list[dict]:
    """Neighbouring facets that share a boundary but no edge and should be one facet (``edge_diagnostics`` ``mergeable``)."""
    return edge_diagnostics(facets, p)["mergeable"]


def totals_of(facets: list[Facet], edges: list[Edge]) -> dict:
    """Area and length totals of a facet / edge set (priced or drawn)."""
    tot = {"area_sqft": 0.0, "pitched_area_sqft": 0.0, "flat_area_sqft": 0.0}
    pitch_w: dict[float, float] = {}
    for f in facets:
        tot["area_sqft"] += f.area_sqft
        if f.roof_type == "flat":
            tot["flat_area_sqft"] += f.area_sqft
        else:
            tot["pitched_area_sqft"] += f.area_sqft
            key = round(f.pitch_rise * 2) / 2
            pitch_w[key] = pitch_w.get(key, 0) + f.area_sqft
    tot["squares"] = tot["area_sqft"] / 100.0
    tot["predominant_pitch"] = float(max(pitch_w, key=pitch_w.get)) if pitch_w else 0.0
    tot["facet_count"] = len(facets)
    lengths = {k: 0.0 for k in ("eave", "rake", "ridge", "hip", "valley", "level_change", "flat_edge", "transition")}
    for e in edges:
        if e.type != "flat_seam":  # drawn, never priced: in no total
            lengths[e.type] = lengths.get(e.type, 0.0) + e.length_ft
    tot["lengths_ft"] = {k: round(v, 1) for k, v in lengths.items()}
    for k in ("area_sqft", "pitched_area_sqft", "flat_area_sqft", "squares"):
        tot[k] = round(tot[k], 1)
    return tot
