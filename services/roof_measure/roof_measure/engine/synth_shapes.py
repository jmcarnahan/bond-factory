"""Exact synthetic roofs: wings -> facets with plane equations, typed edges, totals.

A roof is a list of `Wing`s (a rectangle whose sloping sides give planes; the wing surface is the
minimum of its planes) and the roof surface is the maximum over all wings covering a point. That
one rule yields gables, hips, valleys, steps and dutch gables exactly. Facets are the plan regions
where one plane wins; edges are typed from the facet pairs that share them. Everything is in a
local metric frame (metres, z up, ground at z=0); no geographic coordinates anywhere.
Edge `facets` convention: continuous edges lie on every listed facet's plane; a `level_change`
lists (lower, upper) and its endpoints lie on the lower facet's plane.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

M2FT = 3.280839895013123
SQM2SQFT = M2FT * M2FT
FLAT_BELOW = 2.0  # rise per 12 below which a facet is flat (owner decision D2)
_TOL = 1e-5  # metres: planes/edges that agree within this are the same
_BUF = 1e-6  # boundary matching buffer, metres
_MIN_AREA = 1e-6  # m2: smaller regions are numerical slivers
_MIN_EDGE = 1e-3  # m: shorter edge pieces are numerical stubs


@dataclass(frozen=True)
class Facet:
    id: int
    xy: tuple  # exterior ring, metres, counter-clockwise, no closing repeat
    plane: tuple  # (a, b, c): z = a*x + b*y + c, metres
    pitch: float  # rise per 12
    aspect_deg: float  # downslope compass direction (0 = +y, clockwise); 0 for flat
    roof_type: str  # flat | pitched (pitch >= 2/12)
    area_sqft: float  # surface
    plan_area_sqft: float

    def polygon(self) -> Polygon:
        return Polygon(self.xy)

    def z(self, x: float, y: float) -> float:
        a, b, c = self.plane
        return a * x + b * y + c


@dataclass(frozen=True)
class Edge:
    type: str  # eave|rake|ridge|hip|valley|flat_edge|level_change|transition
    p0: tuple  # (x, y, z) metres
    p1: tuple
    length_ft: float  # exact 3D length
    facets: tuple  # facet ids (see module docstring for level_change)
    jump_ft: float = 0.0  # level_change: mean vertical step along the edge
    exterior: bool = False  # on the roof outline
    high_edge: bool = False  # a level outline edge at the top of a slope (shed): typed rake, takes rake metal


@dataclass(frozen=True)
class SynthRoof:
    name: str
    facets: tuple
    edges: tuple
    totals: dict
    wall_outline: tuple  # ring, metres
    roof_outline: tuple  # ring, metres (wall outline plus overhang)
    params: dict

    def facet_polygons(self) -> list[Polygon]:
        return [f.polygon() for f in self.facets]

    def roof_polygon(self) -> Polygon:
        return Polygon(self.roof_outline)

    def wall_polygon(self) -> Polygon:
        return Polygon(self.wall_outline)

    def translated(self, dx: float, dy: float) -> SynthRoof:
        return _xform(self, 0.0, (0.0, 0.0), (dx, dy))


@dataclass(frozen=True)
class Wing:
    rect: tuple  # wall rectangle x0, y0, x1, y1 (metres)
    sides: str  # sloping sides among "WSEN": the wing height is rise/12 times the distance to the nearest
    rise: float  # rise per 12
    eave_z: float  # height of the eave line, metres
    ovh: tuple = (0.0, 0.0, 0.0, 0.0)  # overhang per side W, S, E, N, metres

    def expanded(self) -> tuple:
        x0, y0, x1, y1 = self.rect
        w, s, e, n = self.ovh
        return (x0 - w, y0 - s, x1 + e, y1 + n)

    def planes(self) -> list[tuple]:
        x0, y0, x1, y1 = self.rect
        t, z = self.rise / 12.0, self.eave_z
        table = {"S": (0.0, t, z - t * y0), "N": (0.0, -t, z + t * y1),
                 "W": (t, 0.0, z - t * x0), "E": (-t, 0.0, z + t * x1)}
        return [table[s] for s in self.sides] or [(0.0, 0.0, z)]


def _half(a: float, b: float, c: float, big: float = 1e4) -> Polygon:
    """The half-plane a*x + b*y + c >= 0 as a big polygon (a=b=0: everything or nothing)."""
    n = math.hypot(a, b)
    if n < 1e-12:
        return box(-big, -big, big, big) if c >= -1e-9 else Polygon()
    a, b, c = a / n, b / n, c / n
    px, py = -a * c, -b * c
    dx, dy = -b * big, a * big
    return Polygon([(px - dx, py - dy), (px + dx, py + dy), (px + dx + a * big, py + dy + b * big),
                    (px - dx + a * big, py - dy + b * big)])


def _diff_half(p: tuple, q: tuple) -> Polygon:  # where plane p is at or above plane q
    return _half(p[0] - q[0], p[1] - q[1], p[2] - q[2])


def _wing_regions(wings: list[Wing]) -> list[tuple]:
    """(plane, region polygon) for every plane of every wing where it is the roof surface."""
    out = []
    for i, wing in enumerate(wings):
        pls = wing.planes()
        for k, pk in enumerate(pls):
            reg = box(*wing.expanded())
            for m, pm in enumerate(pls):
                if m != k:
                    reg = reg.intersection(_diff_half(pm, pk))
            for j, other in enumerate(wings):
                if j == i or reg.is_empty:
                    continue
                wins = unary_union([_diff_half(pk, pm) for pm in other.planes()])
                reg = reg.difference(box(*other.expanded()).difference(wins))
            out.append((pk, shapely.set_precision(reg, 1e-9)))  # also drops zero-width spikes
    return out


def _make_facets(wings: list[Wing]) -> list[tuple]:
    """Disjoint (plane, polygon) pairs, coplanar neighbours merged, in a stable order."""
    taken = Polygon()
    groups: dict = {}
    for plane, reg in _wing_regions(wings):
        reg = reg.difference(taken)
        if reg.is_empty:
            continue
        taken = taken.union(reg)
        groups.setdefault(tuple(round(v, 6) for v in plane), [plane, []])[1].append(reg)
    out = []
    for plane, regs in groups.values():
        for poly in shapely.get_parts(unary_union(regs)):
            if poly.geom_type != "Polygon" or poly.area <= _MIN_AREA:
                continue
            if list(poly.interiors):
                raise ValueError("a facet with a hole: not representable")
            out.append((plane, orient(poly.simplify(1e-7), 1.0)))
    out.sort(key=lambda fp: (round(fp[1].centroid.x, 5), round(fp[1].centroid.y, 5), fp[0]))
    return out


def _facet(i: int, plane: tuple, poly: Polygon) -> Facet:
    a, b, _ = plane
    grad = math.hypot(a, b)
    pitch = grad * 12.0
    aspect = math.degrees(math.atan2(-a, -b)) % 360.0 if grad > 1e-9 else 0.0
    plan = poly.area * SQM2SQFT
    return Facet(i, tuple(poly.exterior.coords)[:-1], plane, pitch, aspect,
                 "pitched" if pitch >= FLAT_BELOW - 1e-9 else "flat",
                 plan * math.sqrt(1 + grad * grad), plan)


def _lines(geom):
    for g in shapely.get_parts(geom):
        if g.geom_type == "LineString":
            yield g
        elif g.geom_type == "GeometryCollection":
            yield from _lines(g)


def _runs(geom, verts) -> list[tuple]:
    """Straight pieces ((x0, y0), (x1, y1)) of the line parts of geom, stubs dropped, ends snapped to facet vertices."""

    def snap(p):
        near = min(verts, key=lambda v: math.dist(v, p))
        return near if math.dist(near, p) < 1e-5 else p

    out = []
    for line in _lines(geom):
        c = list(line.coords)
        k = 0
        while k < len(c) - 1:
            e = k + 1
            while e + 1 < len(c) and all(
                    LineString([c[k], c[e + 1]]).distance(Point(p)) < _TOL for p in c[k + 1:e + 1]):
                e += 1
            if math.dist(c[k], c[e]) >= _MIN_EDGE:
                out.append((snap(c[k]), snap(c[e])))
            k = e
    return out


def _shared_edge(i: int, j: int, f: list[Facet], seg: tuple) -> Edge:
    (x0, y0), (x1, y1) = seg
    fi, fj = f[i], f[j]
    d0, d1 = abs(fi.z(x0, y0) - fj.z(x0, y0)), abs(fi.z(x1, y1) - fj.z(x1, y1))
    if max(d0, d1) > _TOL:  # a vertical step between the two surfaces
        lo, hi = (fi, fj) if fi.z((x0 + x1) / 2, (y0 + y1) / 2) < fj.z((x0 + x1) / 2, (y0 + y1) / 2) else (fj, fi)
        p0, p1 = (x0, y0, lo.z(x0, y0)), (x1, y1, lo.z(x1, y1))
        return Edge("level_change", p0, p1, math.dist(p0, p1) * M2FT, (lo.id, hi.id), (d0 + d1) / 2 * M2FT)
    p0, p1 = (x0, y0, fi.z(x0, y0)), (x1, y1, fi.z(x1, y1))
    if fi.roof_type != fj.roof_type:
        kind = "transition"
    else:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ln = math.dist((x0, y0), (x1, y1))
        nx, ny = -(y1 - y0) / ln * 1e-4, (x1 - x0) / ln * 1e-4
        if not fi.polygon().contains(Point(mx + nx, my + ny)):
            nx, ny = -nx, -ny
        convex = fi.z(mx + nx, my + ny) < fj.z(mx + nx, my + ny)
        kind = ("ridge" if abs(p0[2] - p1[2]) < _TOL else "hip") if convex else "valley"
    return Edge(kind, p0, p1, math.dist(p0, p1) * M2FT, (i, j))


def _exterior_edge(i: int, f: list[Facet], seg: tuple) -> Edge:
    (x0, y0), (x1, y1) = seg
    fi = f[i]
    p0, p1 = (x0, y0, fi.z(x0, y0)), (x1, y1, fi.z(x1, y1))
    if fi.roof_type == "flat":
        kind = "flat_edge"
    elif abs(p0[2] - p1[2]) > _TOL:
        kind = "rake"
    else:
        ln = math.dist((x0, y0), (x1, y1))
        nx, ny = (y1 - y0) / ln, -(x1 - x0) / ln  # right-hand normal; outward for a CCW ring
        high = fi.plane[0] * nx + fi.plane[1] * ny > 0  # the roof rises toward this edge
        kind = "rake" if high else "eave"
        return Edge(kind, p0, p1, math.dist(p0, p1) * M2FT, (i,), 0.0, True, high)
    return Edge(kind, p0, p1, math.dist(p0, p1) * M2FT, (i,), 0.0, True)


def _edges(facets: list[Facet]) -> list[Edge]:
    polys = [f.polygon() for f in facets]
    rings = [p.exterior for p in polys]
    bufs = [r.buffer(_BUF) for r in rings]
    verts = [p for f in facets for p in f.xy]
    out = []
    for i in range(len(facets)):
        for j in range(i + 1, len(facets)):
            if polys[i].distance(polys[j]) < _BUF:
                out += [_shared_edge(i, j, facets, s) for s in _runs(rings[i].intersection(bufs[j]), verts)]
    for i in range(len(facets)):
        near = [bufs[j] for j in range(len(facets)) if j != i and polys[i].distance(polys[j]) < _BUF]
        rest = rings[i].difference(unary_union(near)) if near else LineString(rings[i].coords)
        out += [_exterior_edge(i, facets, s) for s in _runs(rest, verts)]
    out.sort(key=lambda e: (e.type, round(e.p0[0], 4), round(e.p0[1], 4), round(e.p1[0], 4), round(e.p1[1], 4)))
    return out


def totals_of(facets, edges) -> dict:
    def ft(*kinds):
        return sum(e.length_ft for e in edges if e.type in kinds)
    area = sum(f.area_sqft for f in facets)
    return {
        "area_sqft": area, "plan_area_sqft": sum(f.plan_area_sqft for f in facets),
        "perimeter_ft": sum(e.length_ft for e in edges if e.exterior),
        "ridge_ft": ft("ridge"),
        "hip_ft": ft("hip"), "valley_ft": ft("valley"), "eave_ft": ft("eave"), "rake_ft": ft("rake"),
        "flat_edge_ft": ft("flat_edge"), "level_change_ft": ft("level_change"), "transition_ft": ft("transition"),
        "wall_cap_ft": sum(e.length_ft for e in edges if e.high_edge),
        "flat_sqft": sum(f.area_sqft for f in facets if f.roof_type == "flat"),
        "pitched_sqft": sum(f.area_sqft for f in facets if f.roof_type == "pitched"),
        "facet_count": len(facets)}


def _xform(roof: SynthRoof, theta: float, center: tuple, shift: tuple) -> SynthRoof:
    """p' = center + R(theta)(p - center) + shift, applied to the whole roof."""
    ct, st = math.cos(theta), math.sin(theta)
    qx, qy = center

    def pt(x, y):
        return (qx + ct * (x - qx) - st * (y - qy) + shift[0], qy + st * (x - qx) + ct * (y - qy) + shift[1])

    facets = []
    for f in roof.facets:
        a, b, c = f.plane
        a2, b2 = ct * a - st * b, st * a + ct * b
        c2 = c + a * qx + b * qy - a2 * (qx + shift[0]) - b2 * (qy + shift[1])
        facets.append(Facet(f.id, tuple(pt(*p) for p in f.xy), (a2, b2, c2), f.pitch, (f.aspect_deg - math.degrees(theta)) % 360.0
                            if f.pitch > 1e-9 else 0.0, f.roof_type, f.area_sqft, f.plan_area_sqft))
    edges = [Edge(e.type, (*pt(*e.p0[:2]), e.p0[2]), (*pt(*e.p1[:2]), e.p1[2]), e.length_ft, e.facets,
                  e.jump_ft, e.exterior, e.high_edge) for e in roof.edges]
    return SynthRoof(roof.name, tuple(facets), tuple(edges), roof.totals,
                     tuple(pt(*p) for p in roof.wall_outline), tuple(pt(*p) for p in roof.roof_outline), roof.params)


def build(name: str, wings: list[Wing], params: dict | None = None, rotation_deg: float = 0.0) -> SynthRoof:
    """Exact roof from wings; rotated about the wall-outline centroid afterwards."""
    parts = _make_facets(wings)
    facets = [_facet(i, pl, po) for i, (pl, po) in enumerate(parts)]
    edges = _edges(facets)
    wall = unary_union([box(*w.rect) for w in wings])
    roof_poly = unary_union([box(*w.expanded()) for w in wings])
    roof = SynthRoof(name, tuple(facets), tuple(edges), totals_of(facets, edges),
                     tuple(orient(wall, 1.0).exterior.coords)[:-1], tuple(orient(roof_poly, 1.0).exterior.coords)[:-1],
                     dict(params or {}, rotation_deg=rotation_deg))
    if rotation_deg:
        roof = _xform(roof, math.radians(rotation_deg), (wall.centroid.x, wall.centroid.y), (0.0, 0.0))
    return roof
