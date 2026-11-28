"""Roof-edge finder: where the roof really ends along each side of the outline ring. Metres, building frame.

Strips 0.9 m wide cross every ring side from 2.7 m inside to 3.0 m outside. In each strip the LiDAR returns are
compared with the roof plane just inside the edge; walking outward, the edge is where the continuous run of returns on
that plane stops (a gap scaled to the strip's own point spacing, so a sparse roof is not cut short). Strips that do not
show an edge are rejected: on-plane returns to the end of the window (a cover continuing the roof, a neighbour) or
returns standing above the plane just past the edge with no ground or wall seen (a tree over the eave). A side takes the
median of its strips, split in two where the strips form two runs (an eave jog the wall line lacks). The per-side
offsets of a first pass also solve for a rigid shift of the whole ring (a displaced county outline); the second pass
measures from the shifted ring. Nothing is anchored to the frame origin: strips hang off the ring sides (centred on each
side), the support cells off the median roof point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from shapely import affinity
from shapely.geometry import Polygon

from .params import EngineParams


@dataclass
class EdgeResult:
    """The finder's answer: ``polygon`` is ``ring`` with ``offsets`` applied (filled, clamped)."""

    polygon: Polygon
    ring: Polygon  # the regularised ring, shifted by ``shift`` and with sides split at steps, CCW
    measured: list[float | None]  # per ring side: measured offset (m, + outward), None when no strip held
    offsets: list[float]  # per ring side: measured, else filled from the sides facing the same way (unclamped)
    sources: list[str]  # per ring side: ok (clear strips), tree (strips under a crown) or fill
    shift: tuple[float, float]  # m: rigid shift applied to the input ring (registration)
    rejected: dict[str, int] = field(default_factory=dict)  # strips by reason (``ok`` = kept)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Cloud:
    cand: np.ndarray  # (n, 3) returns that may be roof: not ground, above the local ground
    q: np.ndarray  # (m, 3) roof points assigned to a plane
    qlab: np.ndarray  # (m,) their plane labels
    planes: np.ndarray  # (k, 3) plane a, b, c
    tree: cKDTree | None = None  # of cand (x, y)
    qtree: cKDTree | None = None  # of q (x, y)

    def __post_init__(self) -> None:
        self.tree = cKDTree(self.cand[:, :2]) if len(self.cand) else None
        self.qtree = cKDTree(self.q[:, :2]) if len(self.q) else None

    def near(self, a: np.ndarray, b: np.ndarray, reach: float) -> tuple[np.ndarray, np.ndarray]:
        """Indices of cand and of q within ``reach`` of the segment a-b's bounding circle (a cheap pre-selection)."""
        mid, r = (a + b) / 2, float(np.hypot(*(b - a))) / 2 + reach
        ci = np.array(self.tree.query_ball_point(mid, r), int) if self.tree is not None else np.zeros(0, int)
        qi = np.array(self.qtree.query_ball_point(mid, r), int) if self.qtree is not None else np.zeros(0, int)
        return np.sort(ci), np.sort(qi)


def candidates(context: np.ndarray | None, roof_xyz: np.ndarray, ring: Polygon, p: EngineParams) -> np.ndarray:
    """Non-ground returns more than ``edge_hag_m`` above the local ground (median z of the ``edge_ground_k`` nearest
    ground returns) within reach of the ring. Without a usable wide cloud the roof points themselves (already chosen
    by height) stand in."""
    reach = ring.buffer(p.edge_out_m + p.edge_extend_m + p.edge_shift_max_m + p.edge_half_m)
    if context is None or int((context[:, 3] == 2).sum()) < p.edge_ground_k:
        return roof_xyz[shapely.contains_xy(reach, roof_xyz[:, 0], roof_xyz[:, 1])][:, :3]
    g = context[context[:, 3] == 2]
    ng = context[context[:, 3] != 2]
    ng = ng[shapely.contains_xy(reach, ng[:, 0], ng[:, 1])]
    if not len(ng):
        return np.zeros((0, 3))
    _, i = cKDTree(g[:, :2]).query(ng[:, :2], k=p.edge_ground_k)
    hag = ng[:, 2] - np.median(g[np.atleast_2d(i.reshape(len(ng), -1)), 2], axis=1)
    return ng[hag > p.edge_hag_m][:, :3]


def _run_end(s: np.ndarray, r: np.ndarray, p: EngineParams) -> tuple[float, np.ndarray, bool] | None:
    """(last roof return of the continuous run, sorted roof positions, ended by a gap) or None with too few returns."""
    roof = np.abs(r) < p.edge_tol_m
    rs = np.sort(s[roof & (s >= -p.edge_inner_from_m)])
    if len(rs) < p.edge_min_roof_pts:
        return None
    lam_in = float(((rs > -p.edge_inner_from_m) & (rs < -p.edge_inner_to_m)).sum()) / (p.edge_inner_from_m - p.edge_inner_to_m)
    lam_back = (np.arange(1, len(rs) + 1) - np.searchsorted(rs, rs - p.edge_knee_m, side="right")) / p.edge_knee_m
    lam = np.maximum(np.minimum(lam_in, lam_back[:-1]), p.edge_gap_lam_floor)
    gap = np.maximum(p.edge_gap_m, p.edge_gap_k / lam)  # long against the spacing inside and just before it (banding)
    br = np.nonzero(np.diff(rs) > gap)[0]
    return float(rs[br[0]] if len(br) else rs[-1]), rs[: br[0] + 1] if len(br) else rs, bool(len(br))


def _strip_edge(s: np.ndarray, r: np.ndarray, p: EngineParams, end: float) -> tuple[float | None, str]:
    """Edge position along the outward normal in one strip (``s`` positions, ``r`` residuals to the local plane; the
    window ends at ``end``)."""
    keep = s < end
    s, r = s[keep], r[keep]
    run = _run_end(s, r, p)
    if run is None:
        return None, "noroof"
    last, rs, gapped = run
    if not gapped and last > end - p.edge_end_margin_m:
        return None, "end"  # on-plane returns to the end of the window: a cover, a canopy at roof height, a neighbour
    lam_end = float(((rs > last - p.edge_knee_m) & (rs <= last)).sum()) / p.edge_knee_m
    edge = last + p.edge_allow / max(lam_end, p.edge_lam_min)
    beyond = s > last
    n_up = int((beyond & (r > p.edge_up_m) & (s < last + p.edge_up_win_m)).sum())
    n_dn = int((beyond & (r < -p.edge_dn_m) & (s < last + p.edge_dn_win_m)).sum())
    if end > p.edge_out_m:  # past the first window only a visible drop (wall, fascia) makes it an edge, not a cover
        drop = int((beyond & (r < -p.edge_dn_m) & (s < last + p.edge_up_win_m)).sum())
        return (edge, "ok") if drop >= p.edge_extend_dn_min else (None, "end")  # a lip or parapet at the drop is no tree
    if n_dn < p.edge_dn_min and n_up > p.edge_up_max:
        return edge, "tree"  # something stands over the edge and neither ground nor wall is seen below it (kept as a fallback)
    return edge, "ok"


def _strip_centres(length: float, p: EngineParams) -> np.ndarray:
    """Strip centres along a side, centred on it (symmetric, so the same side gives the same strips both ways)."""
    if length < p.edge_min_side_m:
        return np.zeros(0)
    if length < 2 * p.edge_half_m + p.edge_end_margin_m:
        return np.array([length / 2])
    k = int((length - 2 * p.edge_half_m) / p.edge_step_m + 1e-9) + 1
    return (length - (k - 1) * p.edge_step_m) / 2 + np.arange(k) * p.edge_step_m


def _side_strips(C: _Cloud, a: np.ndarray, b: np.ndarray, p: EngineParams) -> list[tuple[float, float | None, str]]:
    """(position along the side, edge offset or None, reason) per strip of side a-b (outward normal on the right)."""
    length = float(np.hypot(*(b - a)))
    us = _strip_centres(length, p)
    if not len(us):
        return []
    t = (b - a) / length
    n = np.array([t[1], -t[0]])
    reach = p.edge_half_m + p.edge_plane_pad_m
    far = p.edge_out_m + p.edge_extend_m
    ci, qi = C.near(a, b, math.hypot(max(p.edge_in_m, far), reach))
    d = C.cand[ci, :2] - a
    u, s = d @ t, d @ n
    band = (u > us[0] - p.edge_half_m) & (u < us[-1] + p.edge_half_m) & (s > -p.edge_in_m) & (s < far)
    X, u, s = C.cand[ci[band]], u[band], s[band]
    qd = C.q[qi, :2] - a
    qu, qs = qd @ t, qd @ n
    keep = (qs > -p.edge_in_m) & (qs < -p.edge_inner_to_m) & (qu > us[0] - reach) & (qu < us[-1] + reach)
    qi, qu, qs = qi[keep], qu[keep], qs[keep]
    out: list[tuple[float, float | None, str]] = []
    for c in us:
        m = np.abs(u - c) < p.edge_half_m
        if (m & (s < p.edge_out_m)).sum() < p.edge_min_strip_pts:
            out.append((float(c), None, "few"))
            continue
        near = np.abs(qu - c) < reach
        qk, qsk = qi[near], qs[near]
        if len(qk) < p.edge_min_plane_pts:
            out.append((float(c), None, "noplane"))
            continue
        lab = C.qlab[qk]
        win = qsk > -p.edge_inner_from_m  # the planes of this strip: those holding a fair share of its inner window
        if win.sum() >= p.edge_min_plane_pts:
            labs, cnt = np.unique(lab[win], return_counts=True)
            qk = qk[np.isin(lab, labs[(cnt >= p.edge_plane_share * win.sum()) | (cnt == cnt.max())])]
        Xk = X[m]
        _, j = cKDTree(C.q[qk, :2]).query(Xk[:, :2])
        pl = C.planes[C.qlab[qk[j]]]  # the plane of the nearest such roof point inside the edge
        rk = Xk[:, 2] - (pl[:, 0] * Xk[:, 0] + pl[:, 1] * Xk[:, 1] + pl[:, 2])
        sk = s[m]
        inner = (sk > -p.edge_inner_from_m) & (sk < -p.edge_inner_to_m) & (np.abs(rk) < 2 * p.edge_tol_m)
        if inner.sum() >= p.edge_warp_min_pts:
            rk = rk - np.median(rk[inner])  # the plane's local height here (a warped or sagging deck)
        e, why = _strip_edge(sk, rk, p, p.edge_out_m)
        if why == "end":  # the run reaches the window end: look once further out (a ring well inside the roof edge)
            e, why = _strip_edge(sk, rk, p, far)
        out.append((float(c), e, why))
    return out


def _consensus(vals: list[float], p: EngineParams) -> list[bool]:
    """Strips that agree with the side: within max(edge_dev_m, 3 MAD) of the median (all kept under 3 strips)."""
    if len(vals) < 3:
        return [True] * len(vals)
    v = np.array(vals)
    med = float(np.median(v))
    lim = max(p.edge_dev_m, 3 * 1.4826 * float(np.median(np.abs(v - med))))
    return [bool(abs(x - med) <= lim) for x in v]


def _step_split(us: list[float], es: list[float], p: EngineParams) -> int | None:
    """Index k when the kept strips (in order along the side) form two runs, es[:k] and es[k:], each of at least
    ``edge_split_min_strips`` with most strips near their own median and medians more than ``edge_split_m`` apart.
    Among such splits the one whose runs fit their medians best (least absolute deviation)."""
    m = p.edge_split_min_strips
    best, best_cost = None, math.inf
    for k in range(m, len(es) - m + 1):
        left, right = np.array(es[:k]), np.array(es[k:])
        ml, mr = float(np.median(left)), float(np.median(right))
        if abs(ml - mr) <= p.edge_split_m:
            continue
        if (np.abs(left - ml) <= p.edge_dev_m).mean() < p.edge_split_share or \
                (np.abs(right - mr) <= p.edge_dev_m).mean() < p.edge_split_share:
            continue
        cost = float(np.abs(left - ml).sum() + np.abs(right - mr).sum())
        if cost < best_cost - 1e-12:
            best, best_cost = k, cost
    return best


def _side_offset(rows: list[tuple[float, float | None, str]], p: EngineParams) -> tuple[float | None, int, list, str]:
    """(median offset, strips kept, rows with consensus outliers marked ``dev``, source). A side without enough clear
    strips takes the run measured under a tree crown (source ``tree``): occlusion can only end that run early, never
    carry it past the returns."""
    rows = list(rows)
    for kind in ("ok", "tree"):
        idx = [i for i, (_, _, w) in enumerate(rows) if w == kind]
        keep = _consensus([rows[i][1] for i in idx], p)
        if kind == "ok":
            for i, kp in zip(idx, keep, strict=True):
                if not kp:
                    rows[i] = (rows[i][0], rows[i][1], "dev")
        kept = [rows[i][1] for i, kp in zip(idx, keep, strict=True) if kp]
        if len(kept) >= p.edge_min_strips:
            return float(np.median(kept)), (len(kept) if kind == "ok" else 0), rows, kind
    return None, 0, rows, ""


def _measure(ring: Polygon, C: _Cloud, p: EngineParams, split: bool) -> tuple[list[dict], dict[str, int]]:
    """One pass over the ring sides: per side its ends, normal, length, offset (or None) and kept strip count. With
    ``split`` a side whose strips step is returned as two sides."""
    c = np.array(ring.exterior.coords)[:-1]
    sides: list[dict] = []
    reasons: dict[str, int] = {}
    for i in range(len(c)):
        a, b = c[i], c[(i + 1) % len(c)]
        length = float(np.hypot(*(b - a)))
        if length < 1e-9:
            continue
        t = (b - a) / length
        rows = _side_strips(C, a, b, p)
        parts = [(a, b, rows)]
        if split:
            okr = [(u, e) for u, e, w in rows if w == "ok"]
            k = _step_split([u for u, _ in okr], [e for _, e in okr], p)
            if k is not None:
                cut = (okr[k - 1][0] + okr[k][0]) / 2
                m = a + t * cut
                parts = [(a, m, [r for r in rows if r[0] < cut]), (m, b, [r for r in rows if r[0] > cut])]
        for pa, pb, prow in parts:
            off, kept, prow, src = _side_offset(prow, p)
            for _, _, w in prow:
                reasons[w] = reasons.get(w, 0) + 1
            sides.append({"a": pa, "b": pb, "n": np.array([t[1], -t[0]]), "L": float(np.hypot(*(pb - pa))),
                          "off": off, "k": kept, "src": src, "why": [w for _, _, w in prow]})
    cos_same = math.cos(math.radians(p.edge_same_facing_deg))
    allm = [d["off"] for d in sides if d["off"] is not None]
    for d in sides:  # a side without strips: the sides facing the same way, else the whole house
        if d["off"] is None:
            same = [x["off"] for x in sides if x["off"] is not None and float(x["n"] @ d["n"]) >= cos_same]
            d["fill"] = float(np.median(same)) if same else (float(np.median(allm)) if allm else 0.0)
    return sides, reasons


def _register(sides: list[dict], p: EngineParams) -> tuple[float, float, float]:
    """Least-squares common overhang o and rigid shift d from off_i = o + n_i . d (weights length x strips). An axis
    with measured sides facing only one way cannot separate the shift from the overhang: its shift stays 0."""
    use = [d for d in sides if d["off"] is not None and d["k"] > 0]
    if len(use) < 3:
        return 0.0, 0.0, 0.0
    nrm = np.array([d["n"] for d in use])
    cos_same = math.cos(math.radians(p.edge_same_facing_deg))
    cols = [0] + [ax + 1 for ax in (0, 1) if (nrm[:, ax] >= cos_same).any() and (nrm[:, ax] <= -cos_same).any()]
    A = np.c_[np.ones(len(use)), nrm][:, cols]
    y = np.array([d["off"] for d in use])
    w = np.sqrt(np.array([d["L"] * d["k"] for d in use]))
    sol = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)[0]
    full = np.zeros(3)
    full[cols] = sol
    return float(full[0]), float(full[1]), float(full[2])


def clamp_offsets(offsets: list[float], county: bool, sources: list[str], p: EngineParams) -> list[float]:
    """The offsets to apply. A side measured from clear strips (source ``ok``)
    keeps its measurement; a side filled or seen only under a tree is clamped: inward at most ``edge_clamp_lo_m``,
    outward at most ``edge_clamp_hi_m``, or ``edge_clamp_hi_roofedge_m`` for a non-county outline (OpenStreetMap,
    LiDAR hull), which already lies near the roof edge."""
    hi = p.edge_clamp_hi_m if county else p.edge_clamp_hi_roofedge_m
    out = []
    for v, src in zip(offsets, sources, strict=True):
        out.append(v if src == "ok" else min(hi, max(-p.edge_clamp_lo_m, v)))
    return out


def offset_polygon(ring: Polygon, dist: list[float], p: EngineParams) -> Polygon:
    """Polygon with per-side outward offsets ``dist[i]`` (ring CCW); consecutive offset lines are intersected. Two
    consecutive collinear sides (a side split at a step) get a jog between their offsets."""
    c = np.array(ring.exterior.coords)[:-1]
    n = len(c)
    lines = []
    for i in range(n):
        a, b = c[i], c[(i + 1) % n]
        u = (b - a) / np.hypot(*(b - a))
        nrm = np.array([u[1], -u[0]])
        lines.append((a + nrm * dist[i], u, nrm))
    verts = []
    for i in range(n):
        p1, u1, n1 = lines[i - 1]
        p2, u2, n2 = lines[i]
        a = np.array([u1, -u2]).T
        if abs(np.linalg.det(a)) < p.offset_parallel_det:
            if float(u1 @ u2) > 0 and abs(dist[i - 1] - dist[i]) > 1e-6:
                verts += [c[i] + n1 * dist[i - 1], c[i] + n2 * dist[i]]
            else:
                verts.append(c[i] + (n1 * dist[i - 1] + n2 * dist[i]) / 2)
            continue
        t = np.linalg.solve(a, p2 - p1)
        v = p1 + t[0] * u1
        if np.hypot(*(v - c[i])) > p.offset_corner_max_m:
            v = c[i] + (n1 * dist[i - 1] + n2 * dist[i]) / 2
        verts.append(v)
    out = Polygon(verts)
    if not out.is_valid:
        out = out.buffer(0)
        if out.geom_type == "MultiPolygon":
            out = max(out.geoms, key=lambda g: g.area)
    return out


def edge_polygon(ring: Polygon, offsets: list[float], county: bool, sources: list[str], p: EngineParams) -> Polygon:
    """The ring with clamped offsets; a plain buffer by the median offset when that polygon collapses. No upper bound:
    a measured side may lie up to edge_out_m + edge_extend_m out (a ring far inside the roof)."""
    dist = clamp_offsets(offsets, county, sources, p)
    out = offset_polygon(ring, dist, p)
    if out.is_empty or out.geom_type != "Polygon" or out.area < p.offset_area_lo * ring.area:  # collapsed
        out = ring.buffer(float(np.median(dist)) if dist else 0.0, join_style=2)
    return out


def support_area(q: np.ndarray, wall: Polygon, p: EngineParams) -> float:
    """Area (m2) the roof points cover within the wall line grown by ``support_buffer_m``: cells sized to the point
    spacing (so a sparse roof is not under-counted), anchored to the median roof point, closed once."""
    if len(q) < 3:
        return 0.0
    q = q[shapely.contains_xy(wall.buffer(p.support_buffer_m), q[:, 0], q[:, 1])]
    if len(q) < 3:
        return 0.0
    dens = int(shapely.contains_xy(wall, q[:, 0], q[:, 1]).sum()) / max(wall.area, 1.0)
    h = min(p.support_cell_max_m, max(p.support_cell_m, p.support_cell_k / math.sqrt(max(dens, 1e-6))))
    ij = np.floor((q[:, :2] - np.median(q[:, :2], axis=0)) / h).astype(np.int64)
    ij -= ij.min(0) - 2
    grid = np.zeros(tuple(ij.max(0) + 3), bool)
    grid[ij[:, 0], ij[:, 1]] = True
    return float(ndi.binary_closing(grid).sum() + 0.0) * h * h


def find_roof_edge(context: np.ndarray | None, roof_xyz: np.ndarray, q: np.ndarray, qlab: np.ndarray, planes: list,
                   ring: Polygon, county: bool, p: EngineParams) -> EdgeResult:
    """The roof edge round the CCW ``ring`` (building frame). ``context`` is the wide cloud (x, y, z, class) in the
    building frame or None, ``roof_xyz`` the roof points (the stand-in without a wide cloud), ``q``/``qlab`` the roof
    points assigned to ``planes``."""
    C = _Cloud(candidates(context, roof_xyz, ring, p), q[:, :3], np.asarray(qlab, int),
               np.array([np.asarray(pl, float)[:3] for pl in planes]).reshape(-1, 3))
    first, _ = _measure(ring, C, p, split=False)
    o, dx, dy = _register(first, p)
    shifted = math.hypot(dx, dy) <= p.edge_shift_max_m
    if not shifted:
        dx = dy = 0.0
    ring2 = affinity.translate(ring, dx, dy)
    sides, reasons = _measure(ring2, C, p, split=True)
    ring_out = Polygon([d["a"] for d in sides])
    measured = [d["off"] for d in sides]
    offsets = [d["off"] if d["off"] is not None else d["fill"] for d in sides]
    sources = [d["src"] or "fill" for d in sides]
    poly = edge_polygon(ring_out, offsets, county, sources, p)
    per = sum(d["L"] for d in sides) or 1.0
    blind = sum(d["L"] for d in sides if d["why"] and set(d["why"]) <= {"few", "noroof", "noplane"}) / per
    carry = sum(d["L"] for d in sides if d["src"] != "ok" and d["why"] and 2 * d["why"].count("end") >= len(d["why"])) / per
    diag = {"edge_no_evidence_share": round(blind, 3), "edge_end_share": round(carry, 3), "edge_shift_m": [round(dx, 3), round(dy, 3)], "edge_common_m": round(o, 3),
            "edge_shift_refused": not shifted, "edge_split_sides": len(sides) - len(first),
            "edge_candidates": len(C.cand), "edge_side_source": sources}
    return EdgeResult(poly, ring_out, measured, offsets, sources, (dx, dy), reasons, diag)
