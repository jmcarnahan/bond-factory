"""The shared vertex graph of the planes and the moves on it: border chains, simplification, turning (internal).

Used by ``planes_straight``. A ``_Net`` holds every vertex once, so a vertex that two planes share moves (or goes) for
both; ``simplify_chains`` picks the vertices to drop from each border between planes; ``turn`` turns near-axis borders
onto a dominant direction; ``drop_collinear`` removes vertices that lie on the line through their neighbours.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .classify import polygons_of

KEY = 1e-5  # vertices closer than this are one vertex when the shared graph is built


COLLINEAR_FT = 0.15  # a vertex this near the line through its neighbours is removed


RELAX_PASSES = 40


MAX_MOVE_FT = 0.5  # turning borders onto a direction never moves a vertex further than this


SNAP_DEG = 5.0  # a border within this angle of a dominant direction is turned onto it


MIN_SNAP_FT = 2.5  # shorter borders are left as they are


MIN_GRADIENT_DIFF = 0.12  # slope difference below which the intersection line of two planes is too uncertain to use


MAX_PLANE_DRIFT = 0.10  # a plane's plan area may change by at most this share (and see MIN_DRIFT_SQFT)


MIN_DRIFT_SQFT = 3.0  # ... or by this many sq ft, whichever is larger (a 30 sq ft plane may move 3)


MIN_ANGLE_DEG = 10.0  # a vertex sharper than this is a spike tip (the snapped planes have none)


CHAIN_TOLS_FT = (2.5, 2.0, 1.5, 1.1, 0.8, 0.5, 0.3)  # per border: the largest of these its two planes can afford


def _key(p: tuple[float, float]) -> tuple[int, int]:
    return round(p[0] / KEY), round(p[1] / KEY)


def _diff_deg(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _rings(p: Polygon) -> list[list[tuple[float, float]]]:
    return [[(c[0], c[1]) for c in r.coords[:-1]] for r in (p.exterior, *p.interiors)]


class _Net:
    """The vertices shared by a set of polygons, so a vertex moves once for every polygon that has it."""

    def __init__(self, polys: list[Polygon], outline: BaseGeometry) -> None:
        self.index: dict[tuple[int, int], int] = {}
        self.pos: list[list[float]] = []
        self.rings: list[list[list[int]]] = []
        for p in polys:
            rr = []
            for ring in _rings(p):
                ids = []
                for c in ring:
                    k = _key(c)
                    if k not in self.index:
                        self.index[k] = len(self.pos)
                        self.pos.append([c[0], c[1]])
                    ids.append(self.index[k])
                rr.append(ids)
            self.rings.append(rr)
        self.segs: set[tuple[int, int]] = set()
        self._segs_from_rings()
        # outline rings as lists of coordinates; a vertex on a corner is fixed, one on a side slides along it
        self.sides: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for part in polygons_of(outline):
            for r in (part.exterior, *part.interiors):
                cs = list(r.coords)
                self.sides += [(cs[i], cs[i + 1]) for i in range(len(cs) - 1)]
        self.fixed: set[int] = set()
        self.slide: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}
        for i, (x, y) in enumerate(self.pos):
            for a, b in self.sides:
                if math.dist((x, y), a) < 10 * KEY or math.dist((x, y), b) < 10 * KEY:
                    self.fixed.add(i)
                    break
                if _dist_to_side((x, y), a, b) < 10 * KEY:
                    self.slide[i] = (a, b)
                    break

    def _segs_from_rings(self) -> None:
        self.segs = set()
        for rr in self.rings:
            for ids in rr:
                for i, a in enumerate(ids):
                    b = ids[(i + 1) % len(ids)]
                    if a != b:
                        self.segs.add((min(a, b), max(a, b)))

    def drop(self, gone: set[int]) -> None:
        """Remove the vertices ``gone`` from every ring (the same ones for every polygon that has them)."""
        self.rings = [[[v for v in ids if v not in gone] for ids in rr] for rr in self.rings]
        self._segs_from_rings()

    def ring_area(self, n: int) -> float:
        """Area of polygon ``n`` (exterior minus holes) with the current vertices."""
        total = 0.0
        for k, ids in enumerate(self.rings[n]):
            if len(ids) < 3:
                return 0.0 if k == 0 else total
            a = abs(sum(self.pos[ids[i]][0] * self.pos[ids[(i + 1) % len(ids)]][1]
                        - self.pos[ids[(i + 1) % len(ids)]][0] * self.pos[ids[i]][1] for i in range(len(ids)))) / 2
            total += a if k == 0 else -a
        return total

    def has_spike(self, n: int) -> bool:
        """True when polygon ``n`` has a vertex sharper than MIN_ANGLE_DEG that is not an outline corner."""
        for ids in self.rings[n]:
            m = len(ids)
            for k, v in enumerate(ids):
                a, c = ids[k - 1], ids[(k + 1) % m]
                v1 = (self.pos[a][0] - self.pos[v][0], self.pos[a][1] - self.pos[v][1])
                v2 = (self.pos[c][0] - self.pos[v][0], self.pos[c][1] - self.pos[v][1])
                n1, n2 = math.hypot(*v1), math.hypot(*v2)
                if n1 == 0 or n2 == 0:
                    continue
                ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
                if ang < MIN_ANGLE_DEG and not (self.on_outline(a, v) and self.on_outline(v, c)):
                    return True
        return False

    def on_outline(self, i: int, j: int) -> bool:
        if not ({i, j} <= (self.fixed | set(self.slide))):
            return False
        m = Point((self.pos[i][0] + self.pos[j][0]) / 2, (self.pos[i][1] + self.pos[j][1]) / 2)
        return any(_dist_to_side((m.x, m.y), a, b) < 10 * KEY for a, b in self.sides)

    def polygons(self) -> list[Polygon]:
        out = []
        for rr in self.rings:
            rings = [_dedupe([tuple(self.pos[i]) for i in ids]) for ids in rr]
            out.append(Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3]) if len(rings[0]) >= 3 else Polygon())
        return out


def _dist_to_side(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _project(p: list[float], a: tuple[float, float], b: tuple[float, float]) -> list[float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return [a[0] + t * dx, a[1] + t * dy]


def _dedupe(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for q in pts:
        if not out or math.dist(out[-1], q) > 1e-9:
            out.append(q)
    while len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-9:
        out.pop()
    return out


def _turn(net: _Net, borders: dict[tuple[int, int], set[int]], dirs: list[float], grads: dict[int, Any]) -> bool:
    """Turn every border that runs within SNAP_DEG of a dominant direction onto it (vertices move; outline corners
    never, outline side points only along their side). Returns True when anything was targeted."""
    targets: list[tuple[int, int, float]] = []
    for (i, j) in sorted(net.segs):
        if net.on_outline(i, j):
            continue
        (x1, y1), (x2, y2) = net.pos[i], net.pos[j]
        length = math.hypot(x2 - x1, y2 - y1)
        if length < MIN_SNAP_FT:
            continue
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
        cands = list(dirs)
        owners = sorted(borders.get((i, j), ()))
        if len(owners) == 2 and grads.get(owners[0]) and grads.get(owners[1]):
            (ax, ay), (bx, by) = grads[owners[0]], grads[owners[1]]
            gx, gy = ax - bx, ay - by
            if math.hypot(gx, gy) >= MIN_GRADIENT_DIFF:  # a hip, ridge or valley: the line where the heights agree
                cands.append(math.degrees(math.atan2(gx, -gy)) % 180.0)
        best = min(cands, key=lambda d: _diff_deg(ang, d))
        if _diff_deg(ang, best) <= SNAP_DEG:
            targets.append((i, j, best))
    if not targets:
        return False
    origin = [list(p) for p in net.pos]
    degree: dict[int, int] = {}
    for i, j in net.segs:
        degree[i] = degree.get(i, 0) + 1
        degree[j] = degree.get(j, 0) + 1
    heavy = {v for v, d in degree.items() if d >= 3}  # a junction of three or more borders resists: its neighbours give
    for _ in range(RELAX_PASSES):
        acc: dict[int, list[float]] = {}
        for i, j, phi in targets:
            (x1, y1), (x2, y2) = net.pos[i], net.pos[j]
            mx, my, length = (x1 + x2) / 2, (y1 + y2) / 2, math.hypot(x2 - x1, y2 - y1)
            dx, dy = math.cos(math.radians(phi)), math.sin(math.radians(phi))
            if dx * (x2 - x1) + dy * (y2 - y1) < 0:
                dx, dy = -dx, -dy
            for v, nx, ny in ((i, mx - dx * length / 2, my - dy * length / 2), (j, mx + dx * length / 2, my + dy * length / 2)):
                a = acc.setdefault(v, [0.0, 0.0, 0.0])
                k = 0.1 if v in heavy else 1.0
                a[0] += k * (nx - net.pos[v][0])
                a[1] += k * (ny - net.pos[v][1])
                a[2] += 1
        for v, (sx, sy, n) in acc.items():
            if v in net.fixed:
                continue
            p = [net.pos[v][0] + 0.5 * sx / n, net.pos[v][1] + 0.5 * sy / n]
            if v in net.slide:
                p = _project(p, *net.slide[v])
            d = math.dist(p, origin[v])
            if d > MAX_MOVE_FT:  # (on a slide the clamp stays on the side: it is a point of the same line)
                p = [origin[v][0] + (p[0] - origin[v][0]) * MAX_MOVE_FT / d, origin[v][1] + (p[1] - origin[v][1]) * MAX_MOVE_FT / d]
                if v in net.slide:
                    p = _project(p, *net.slide[v])
            net.pos[v] = p
    return True


def _drop_collinear(net: _Net) -> None:
    """Remove every vertex that lies on the line through its two neighbours in EVERY ring that has it (so a corner of
    one plane that sits on the side of another stays, and shared borders stay shared). Outline points only when the
    line is exact."""
    changed = True
    while changed:
        changed = False
        seen: dict[int, list[float]] = {}
        for rr in net.rings:
            for ids in rr:
                n = len(ids)
                if n < 4:
                    continue
                for i, v in enumerate(ids):
                    d = _dist_to_side(tuple(net.pos[v]), tuple(net.pos[ids[i - 1]]), tuple(net.pos[ids[(i + 1) % n]]))
                    seen.setdefault(v, []).append(d)
        gone = set()
        for v, ds in seen.items():
            count = sum(1 for rr in net.rings for ids in rr if v in ids)
            limit = 1e-6 if (v in net.fixed or v in net.slide) else COLLINEAR_FT
            if len(ds) == count and max(ds) <= limit and v not in net.fixed:
                gone.add(v)
                break  # one at a time: removing a vertex changes its neighbours' lines
        if gone:
            net.drop(gone)
            changed = True


def _chains(net: _Net) -> list[list[int]]:
    """The borders between planes as vertex chains: paths of non-outline sides from one junction (or outline point)
    to the next; a closed loop (a plane inside another) is one chain that starts and ends at its first vertex."""
    inner = [(i, j) for (i, j) in sorted(net.segs) if not net.on_outline(i, j)]
    nbr: dict[int, list[int]] = {}
    for i, j in inner:
        nbr.setdefault(i, []).append(j)
        nbr.setdefault(j, []).append(i)
    node = {v for v, ns in nbr.items() if len(ns) != 2 or v in net.fixed or v in net.slide}
    seen: set[tuple[int, int]] = set()
    chains: list[list[int]] = []

    def walk(start: int, nxt: int) -> list[int]:
        path = [start, nxt]
        seen.add((min(start, nxt), max(start, nxt)))
        while path[-1] not in node:
            cur, prev = path[-1], path[-2]
            step = [w for w in nbr[cur] if w != prev] or [prev]
            w = step[0]
            seen.add((min(cur, w), max(cur, w)))
            path.append(w)
            if w == path[0]:
                break
        return path

    for v in sorted(node):
        for w in nbr.get(v, []):
            if (min(v, w), max(v, w)) not in seen:
                chains.append(walk(v, w))
    for v in sorted(nbr):  # loops with no junction
        for w in nbr[v]:
            if (min(v, w), max(v, w)) not in seen:
                chains.append(walk(v, w))
    return chains


def _drop_for(net: _Net, chain: list[int], tol: float) -> set[int]:
    """The interior vertices of ``chain`` a Douglas-Peucker pass at ``tol`` removes (its ends are always kept)."""
    pts = [tuple(net.pos[v]) for v in chain]
    if len(pts) < 3 or chain[0] == chain[-1] and len(pts) < 5:
        return set()
    kept = LineString(pts).simplify(tol, preserve_topology=False).coords
    keep = {_key(c) for c in kept}
    return {v for v in chain[1:-1] if _key(tuple(net.pos[v])) not in keep}


def _simplify_chains(net: _Net, nplanes: int, scale: float) -> set[int]:
    """Choose the vertices to drop: each border gets the coarsest tolerance whose area change both neighbours can
    afford (budget: ``scale`` x the allowed drift of each plane, shared out over the borders in order of length)."""
    base = [net.ring_area(n) for n in range(len(net.rings))]
    budget = [scale * max(MAX_PLANE_DRIFT * a, MIN_DRIFT_SQFT) for a in base]
    owners: dict[tuple[int, int], list[int]] = {}
    for n, rr in enumerate(net.rings):
        for ids in rr:
            for i, a in enumerate(ids):
                b = ids[(i + 1) % len(ids)]
                owners.setdefault((min(a, b), max(a, b)), []).append(n)
    chains = _chains(net)
    chains.sort(key=lambda c: -sum(math.dist(net.pos[c[i]], net.pos[c[i + 1]]) for i in range(len(c) - 1)))
    gone: set[int] = set()
    full = [list(map(list, rr)) for rr in net.rings]
    for chain in chains:
        adj = sorted(set(owners.get((min(chain[0], chain[1]), max(chain[0], chain[1])), [])))
        for tol in CHAIN_TOLS_FT:
            cand = _drop_for(net, chain, tol)
            if not cand:
                continue
            net.rings = [[[v for v in ids if v not in gone | cand] for ids in rr] for rr in full]
            if all(abs(net.ring_area(n) - base[n]) <= budget[n] and not net.has_spike(n) for n in adj):
                gone |= cand
                break
    net.rings = full
    return gone
