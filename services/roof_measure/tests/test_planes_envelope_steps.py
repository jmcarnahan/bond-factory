"""Wall steps between roof sections (planes_envelope_steps): walls are square, follow the slopes they bound, and every
border between two planes is found even where a roof line ends on a step (a T).

Same synthetic method as test_planes_envelope.py (true facets by hand, shrunk and jittered clusters, production gap
fill as input, the roof turned and moved to an invented place). Where a test needs the gap fill to draw a diagonal,
part of a cluster is dropped (LiDAR saw nothing there).
"""

from __future__ import annotations

import dataclasses
import math

from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from test_planes_envelope import local_plane, roof, to_local, to_world

from roof_measure.planes_envelope import envelope_detail


def _segs(res, a: str, b: str) -> list[LineString]:
    return [to_local(LineString(x["segment"])) for x in res.borders if {x["a"], x["b"]} == {a, b}]


def _along(lines: list[LineString], axis: str, at: float, tol: float) -> bool:
    k = 1 if axis == "x" else 0
    return bool(lines) and all(abs(q[k] - at) < tol for ln in lines for q in ln.coords)


def with_tiles(built, tiles: dict[str, list[tuple[float, float]]]):
    """``roof(...)`` with the input tiling replaced by hand-drawn tiles (local feet): the arbitrary gap fill drawn
    the way it came out on a real roof."""
    planes, raw, fp = built
    out = []
    for p in planes:
        g = orient(to_world(Polygon(tiles[p.id])), 1.0)
        out.append(dataclasses.replace(p, polygon=[[x, y] for x, y in list(g.exterior.coords)[:-1]], holes=[],
                                       plan_area_sqft=g.area))
    return out, raw, fp


def ringed_flat():
    """A flat roof (12 ft) ringed on three sides by slopes rising to a curb 1.8 ft above it (west, north, east;
    hips where they meet); LiDAR missed the north-east corner, so the gap fill gave the ring that corner as a
    diagonal: the flat's border with the ring turns three corners (as on a real roof, where one step line or one L
    cannot follow it)."""
    s, curb = 4.0 / 12.0, 13.8
    outline = [(0, 0), (46, 0), (46, 36), (0, 36)]
    facets = {"f": ([(5, 0), (40, 0), (40, 30), (5, 30)], (0.0, 0.0, 12.0)),
              "w": ([(0, 0), (5, 0), (5, 30), (0, 35)], (s, 0.0, curb - 5 * s)),  # west-facing
              "n": ([(0, 35), (5, 30), (40, 30), (46, 36), (0, 36)], (0.0, -s, curb + 30 * s)),  # north-facing
              "e": ([(40, 0), (46, 0), (46, 36), (40, 30)], (-s, 0.0, curb + 40 * s))}  # east-facing
    drop = {"f": Polygon([(33, 22), (41, 22), (41, 31), (33, 31)]),
            "e": Polygon([(39, 21), (47, 21), (47, 37), (39, 37)]),
            "n": Polygon([(31, 29), (47, 29), (47, 37), (31, 37)])}
    tiles = {"f": [(5, 0), (40, 0), (40, 22), (32, 30), (5, 30)], "w": [(0, 0), (5, 0), (5, 30), (0, 35)],
             "n": [(0, 35), (5, 30), (32, 30), (40, 22), (40, 30), (46, 36), (0, 36)],
             "e": [(40, 0), (46, 0), (46, 36), (40, 30), (40, 22)]}
    return with_tiles(roof(outline, facets, drop=drop), tiles)


def test_a_flat_roof_ringed_by_slopes_has_square_steps_along_each_slope():
    res = envelope_detail(*ringed_flat())
    assert res.gate_failure is None, res.gate_failure
    assert abs(local_plane(res, "f").area - 35 * 30) < 60.0
    assert _along(_segs(res, "f", "e"), "y", 40.0, 0.8)  # the east slope's top edge: a wall along y
    assert _along(_segs(res, "f", "n"), "x", 30.0, 0.8)  # the north slope's: along x
    assert _along(_segs(res, "f", "w"), "y", 5.0, 0.8)
    for b in res.borders:
        if b["kind"] == "step":
            (x0, y0), (x1, y1) = to_local(LineString(b["segment"])).coords[0], to_local(LineString(b["segment"])).coords[-1]
            assert min(abs(x1 - x0), abs(y1 - y0)) < 0.3, b  # no diagonal step


def two_level_diagonal():
    """A high south-facing slope (north) and a lower flat porch (south) along y = 12; the porch was seen only in
    its west half and the slope only in its east half, so the gap fill's border between them runs diagonally."""
    outline = [(0, 0), (40, 0), (40, 30), (0, 30)]
    facets = {"slope": ([(0, 12), (40, 12), (40, 30), (0, 30)], (0.0, -3.0 / 12.0, 16.0 + 12 * 3.0 / 12.0)),
              "porch": ([(0, 0), (40, 0), (40, 12), (0, 12)], (0.0, 0.0, 9.0))}
    drop = {"porch": Polygon([(18, -1), (41, -1), (41, 13), (18, 13)]),
            "slope": Polygon([(-1, 11), (16, 11), (16, 31), (-1, 31)])}
    return roof(outline, facets, drop=drop)


def test_a_step_the_gap_fill_drew_diagonally_is_a_square_wall():
    res = envelope_detail(*two_level_diagonal())
    assert res.gate_failure is None, res.gate_failure
    assert len({p.section for p in res.planes}) == 2
    steps = _segs(res, "slope", "porch")
    assert _along(steps, "x", 12.0, 1.0), [list(s.coords) for s in steps]
    assert abs(sum(s.length for s in steps) - 40.0) < 1.5


def angled_wing():
    """A main gable (ridge along x) whose east end is cut by a wall at 120 degrees, and a lower wing built square to
    that wall (its ridge at 30 degrees, its planes facing 30 degrees off the building axes): the wall between them is
    a real angled wall and both clusters run along it for 12 ft."""
    s, zw = 4.0 / 12.0, 8.0
    c, sn = math.cos(math.radians(120.0)), math.sin(math.radians(120.0))
    p0, p1 = (40.0, 0.0), (40.0 + 14 * c, 14 * sn)  # the angled wall, 14 ft
    a = (math.cos(math.radians(30.0)), math.sin(math.radians(30.0)))  # the wing's long axis
    p0f, p1f = (p0[0] + 20 * a[0], p0[1] + 20 * a[1]), (p1[0] + 20 * a[0], p1[1] + 20 * a[1])
    mid, midf = (p0[0] + 7 * c, p0[1] + 7 * sn), (p0f[0] + 7 * c, p0f[1] + 7 * sn)
    x12 = 40.0 + 12.0 / math.tan(math.radians(120.0))  # where the wall crosses the ridge line y = 12
    outline = [(0, 0), p0, p0f, p1f, p1, (p1[0], 24), (0, 24)]

    def wing_eq(sign: float) -> tuple[float, float, float]:
        ga, gb = sign * s * c, sign * s * sn  # rising toward the wing's ridge (the wall's middle)
        base = zw if sign > 0 else zw + 14 * s
        return ga, gb, base - ga * p0[0] - gb * p0[1]

    facets = {"ms": ([(0, 0), p0, (x12, 12), (0, 12)], (0.0, s, 12.0)),
              "mn": ([(0, 12), (x12, 12), p1, (p1[0], 24), (0, 24)], (0.0, -s, 12.0 + 24 * s)),
              "w1": ([p0, p0f, midf, mid], wing_eq(1.0)), "w2": ([mid, midf, p1f, p1], wing_eq(-1.0))}
    return roof(outline, facets)


def test_a_real_angled_wall_between_sections_stays_angled():
    res = envelope_detail(*angled_wing())
    assert res.gate_failure is None, res.gate_failure
    steps = [b for b in res.borders if b["kind"] == "step" and {b["a"], b["b"]} & {"w1", "w2"}]
    assert steps
    for b in steps:
        ln = to_local(LineString(b["segment"]))
        if ln.length > 4.0:
            (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
            assert abs(math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0 - 120.0) < 6.0  # the wing's short side


def flat_under_a_cross_gable():
    """A flat roof (south) against a gable section (north) whose ridge runs north-south and ends on the step:
    the ridge ends in a T on the flat's border."""
    s = 4.0 / 12.0
    outline = [(0, 0), (40, 0), (40, 40), (0, 40)]
    facets = {"f": ([(0, 0), (40, 0), (40, 18), (0, 18)], (0.0, 0.0, 10.0)),
              "w": ([(0, 18), (20, 18), (20, 40), (0, 40)], (s, 0.0, 13.0)),
              "e": ([(20, 18), (40, 18), (40, 40), (20, 40)], (-s, 0.0, 13.0 + 40 * s))}
    return roof(outline, facets)


def test_borders_are_found_where_a_roof_line_ends_on_a_step():
    res = envelope_detail(*flat_under_a_cross_gable())
    assert res.gate_failure is None, res.gate_failure
    fw, fe = _segs(res, "f", "w"), _segs(res, "f", "e")
    assert fw and fe  # both, though the w/e ridge ends in a T on the flat's single long edge
    assert abs(sum(s.length for s in fw + fe) - 40.0) < 1.5
    assert all(b["kind"] == "step" for b in res.borders if "f" in (b["a"], b["b"]))
