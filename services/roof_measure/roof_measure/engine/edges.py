"""The one edge typer of the engine: interior creases (ridge, hip, valley, level_change, transition) and the roof
edge (eave, rake, flat_edge). Lengths in feet (3D), geometry in metres, in the frame the facets are in.

Rules (plan 3.1 / contract 0.4):
  * a pitched facet's outline edge is an ``eave`` where it faces down the slope, a ``rake`` along the slope, and a
    ``rake`` with ``high_edge=True`` where it is the level high side (a shed or lean-to wall line): never a ridge;
  * a flat facet's outline edge is a ``flat_edge``;
  * a seam shared by two facets is a STEP when the height jump measured from the points on both sides (robustly: returns far
    off a side's own plane are left out) is 0.3 m or more and, between two pitched facets, their fitted planes are apart too;
    a step is named by how its line meets the lower roof's slope (``steps``: ``step_flashing`` down the slope, ``wall_flashing``
    across it or onto a low-slope roof, ``level_change`` between two low-slope facets), carries ``jump_ft`` and the id of the
    higher facet (``upper``). Else a ``transition`` where pitched meets flat at one height, else a ridge, hip or valley from the
    two planes (a ridge when the line where they meet is level); coplanar facets (flat membrane included) share no edge
    (``coplanar_seams`` lists them: those facets should have been merged);
  * a piece of a seam that reads as no edge or as clutter but touches a line of the same two facets is the end of that line
    and keeps its type (``ends``);
  * a ``level_change`` between two FLAT facets must also hold along the seam (``edge_measure.seam_is_level``: the
    two facets' fitted planes are at least 0.3 m apart at 70% of the stations along the seam, and ``jump_ft`` is their median offset); otherwise it is a ``flat_seam``: drawn,
    never priced, in no total (0.5.1);
  * collinear pieces of one type between the same facets are one edge.
"""

from __future__ import annotations

import math

import numpy as np
from shapely.ops import unary_union

from .edge_measure import crease_slope, into, measured_jump, ridge_check, seam_is_level, seg_split
from .ends import adopt_end_pieces, resolve_steps
from .errors import Ctx
from .params import EngineParams
from .plane_math import zat
from .steps import step_type
from .types import Edge, Facet

M2F = 1 / 0.3048
SHARE_TOL_M = 1e-3  # facets of one partition share vertices exactly: boundaries this close are the same line


def _crease(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, p: EngineParams) -> str:
    """ridge / hip / valley / transition from the slopes of the two planes across the segment: both fall away from it
    (a ridge when the line where the two planes meet is level, else a hip: that line does not depend on where the partition
    drew the boundary), both rise towards it (valley), else one slope carries on across it."""
    n = into(fa, p0, p1)
    eps = 0.5 * p.seam_gdiff
    sa = fa.plane[0] * n[0] + fa.plane[1] * n[1]  # slope going into A
    sb = -(fb.plane[0] * n[0] + fb.plane[1] * n[1])  # slope going into B
    if sa < -eps and sb < -eps:
        return "ridge" if crease_slope(fa.plane, fb.plane) < p.ridge_slope else "hip"
    if sa > eps and sb > eps:
        return "valley"
    return "transition"


def _planes_agree_pitched(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, p: EngineParams) -> bool:
    """Two PITCHED facets whose fitted planes meet (differ by less than ``level_change_m`` at both ends and the middle of the
    segment) are one roof folded, whatever the points near the seam say: a step needs the planes apart too."""
    if fa.roof_type != "pitched" or fb.roof_type != "pitched":
        return False
    # at both ends and the middle: planes crossing the seam diagonally can agree at the middle while a real step exists at the ends
    return all(abs(zat(fa.plane, *pt) - zat(fb.plane, *pt)) < p.level_change_m for pt in (p0, (p0 + p1) / 2, p1))


def seg_type_interior(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, q: np.ndarray | None, p: EngineParams,
                      big_flat: set[str] | None = None) -> tuple[str | None, float, str]:
    """(type or None, jump m, why) of a segment shared by two facets; ``why`` says why there is no edge (``seam``:
    coplanar or two flat facets with no verified jump, they should be one facet; ``kink``: the slope carries on;
    ``small_flat``: a flat facet too small for a transition, planes near-coplanar).

    ``level_change`` only when the points show a jump of 0.3 m or more. ``transition`` only where a pitched facet meets a
    flat facet of real size (``big_flat`` ids; None = every flat facet counts); otherwise the planes decide (ridge, hip,
    valley) or the line is dropped."""
    pa, pb = fa.plane, fb.plane
    jump = measured_jump(fa, fb, p0, p1, q, p)
    flat_a, flat_b = fa.roof_type == "flat", fb.roof_type == "flat"
    if jump >= p.level_change_m and not _planes_agree_pitched(fa, fb, p0, p1, p):
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


STEPS = ("level_change", "step_flashing", "wall_flashing")  # a step between two roofs, by name
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
    """(type, a, b, facet-index tuple) for every boundary piece: shared ones typed by seg_type_interior; a piece that is no
    edge but ends a line of the same two facets takes that line's type (``ends.adopt_end_pieces``). Pieces that stay no edge are
    appended to ``seams`` as (facet ids, length m, why, a, b, facet-index pair) when it is given."""
    big = real_flats(facets, p)
    dropped: list = []
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
                    else:
                        dropped.append(((fa.id, fb.id), float(np.hypot(*(b - a))), why, a, b, (i, j)))
        ext = bd.difference(unary_union(others)) if others else bd
        for a, b in seg_split(ext):
            raw.append((seg_type_exterior(fa, a, b), a, b, (i,)))
    added, dropped = adopt_end_pieces(raw, dropped, p)
    if seams is not None:
        seams.extend(dropped)
    return raw + added


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


def _is_stub(p0: np.ndarray, p1: np.ndarray, jm: float, p: EngineParams) -> bool:
    """A step or flat seam too short (or short and low) to be a real line: clutter."""
    plan_m = float(np.hypot(*(p1 - p0)))
    return plan_m < p.stub_min_len_m or (jm < p.stub_jump_m and plan_m < p.stub_len_m)


def _jump_m(facets: list[Facet], fs: tuple, p0: np.ndarray, p1: np.ndarray, q: np.ndarray | None, p: EngineParams) -> float | None:
    """The measured height jump (m) of a two-facet chain, rounded; None for an outline chain."""
    if len(fs) != 2:
        return None
    try:
        return round(float(measured_jump(facets[fs[0]], facets[fs[1]], p0, p1, q, p)), 3)
    except (ValueError, IndexError):
        return None


def build_edges(facets: list[Facet], q: np.ndarray | None, ctx: Ctx, absorbed: list | None = None) -> list[Edge]:
    """All typed edges of the facet partition. ``q`` are the points jumps and ridge checks are measured from.
    A level change that is clutter (shorter than ``stub_min_len_m``, or under ``stub_jump_m`` and shorter than
    ``stub_len_m``) is not an edge: the neighbouring chains carry on; it is appended to ``absorbed`` when given. Unless it
    touches a line of the same two facets: then it is the end of that line and takes its type (``ends.resolve_steps``, which also
    keeps a jog of the boundary between two creases of the same facets a crease)."""
    ctx.check()
    p = ctx.p
    chains = _chains(_raw_segments(facets, q, p), p)
    jumps = [_jump_m(facets, fs, p0, p1, q, p) for _t, fs, p0, p1 in chains]
    stubs = [t == "level_change" and _is_stub(p0, p1, jm or 0.0, p) for (t, _fs, p0, p1), jm in zip(chains, jumps, strict=True)]
    resolved = resolve_steps(chains, jumps, stubs, p)
    edges = []
    for k, (t, fs, p0, p1) in enumerate(chains):
        jm, continued = jumps[k], resolved[k] is not None
        if resolved[k] is not None:
            t = resolved[k][0]
            jm = resolved[k][1] if t == "level_change" else jm  # the end of a step is as high as the step
        z0, z1 = _end_heights(t, facets, fs, p0, p1)  # (heights of the typer's first answer: kept as they were before 0.5.1)
        t = _refine_step(t, facets, fs, p0, p1, q)
        upper = None
        if t == "level_change" and len(fs) == 2:  # a step: sidewall, headwall or (two low-slope facets) a level change
            t, upper = step_type(facets[fs[0]], facets[fs[1]], p0, p1, p)
        if t == "level_change" and len(fs) == 2 and facets[fs[0]].roof_type == "flat" and facets[fs[1]].roof_type == "flat":
            level, plane_gap = seam_is_level(facets[fs[0]], facets[fs[1]], p0, p1, ctx.p.level_change_m)
            if level:
                jm = round(plane_gap, 3)  # a flat/flat level change: its height is the median offset of the two fitted planes
            else:
                t, upper = "flat_seam", None  # two flat pieces of one deck: a drawn line, never priced (the fitted planes nearly meet)
        high = t == HIGH_EDGE
        t = "rake" if high else t
        length = math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (z1 - z0) ** 2) * M2F
        if t in (*STEPS, "flat_seam") and not continued and _is_stub(p0, p1, jm or 0.0, p):
            if absorbed is not None:
                absorbed.append({"type": t, "facets": [facets[i].id for i in fs], "length_ft": round(length, 1),
                                 "jump_ft": None if jm is None else round(jm / 0.3048, 2)})
            continue
        edges.append(Edge(type=t, p0=(float(p0[0]), float(p0[1]), float(z0)), p1=(float(p1[0]), float(p1[1]), float(z1)),
                          length_ft=float(length), facets=tuple(facets[i].id for i in fs), jump_m=jm,
                          jump_ft=round(jm / 0.3048, 2) if t in STEPS and jm is not None else None,
                          high_edge=high, upper=upper))
    return edges


def edge_diagnostics(facets: list[Facet], p: EngineParams, q: np.ndarray | None = None) -> dict[str, list[dict]]:
    """What the typer left out, for ``model.debug``: ``mergeable`` (neighbouring facets with no line between them:
    coplanar, or two flat facets with no verified jump: they should be one facet), ``kinks`` (a slope that carries on),
    ``small_flat`` (a boundary beside a flat facet too small for a transition) and ``absorbed_level_changes``
    (clutter stubs). Pairs are summed; shared lengths under 0.3 m are left out. Without ``q`` heights come from the planes."""
    seams: list = []
    _raw_segments(facets, q, p, seams)
    by: dict[tuple[str, tuple[str, str]], float] = {}
    for ids, length_m, why, *_ in seams:
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
