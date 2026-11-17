"""Pins for the two real roofs the envelope partition already draws right, rebuilt synthetically (closed form).

HOUSE-like: a higher front section (main ridge along x, a cross gable with its own ridge along y and a 45-degree valley
against the main south slope, a tapering step where the cross gable's west slope runs under the main north slope)
meeting a lower rear gable in a long valley, the rear slopes split in two by seams. COMMERCIAL-like: large flat roofs
at different heights separated by straight steps, one hip block and a small shed awning on the south wall.

Same synthetic method as test_planes_envelope.py (true facets by hand, shrunk and jittered clusters, production gap
fill as input, the roof turned and moved to an invented place). These must hold before and after any change to the
partition of complex roofs.
"""

from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from test_planes_envelope import borders_of, local_plane, roof, to_local

from roof_measure.planes_envelope import envelope_detail

S_MAIN = 4.0 / 12.0  # front section slopes
S_REAR = 2.5 / 12.0  # rear gable slopes
Y_RIDGE, Y_VALLEY, Y_REAR = 16.0, 30.0, 39.0
X_CROSS = 21.6  # the cross gable's ridge
Z_RIDGE = 7.0 + S_MAIN * (Y_VALLEY - Y_RIDGE)  # the main ridge's height: the long valley sits at 7 ft


def house_like():
    """(planes, raw, outline) of the HOUSE-like roof (local feet; see the module docstring)."""
    front = Polygon([(6, 2), (42, 2), (42, 30), (6, 30)])
    rear = Polygon([(0, 30), (38, 30), (38, 52), (0, 52)])
    outline = list(unary_union([front, rear]).exterior.coords)[:-1]
    zr = 7.0 + S_REAR * (Y_REAR - Y_VALLEY)  # the rear ridge
    facets = {
        "k0": ([(6, Y_RIDGE), (42, Y_RIDGE), (42, 30), (6, 30)], (0.0, -S_MAIN, Z_RIDGE + S_MAIN * Y_RIDGE)),  # north
        "k2": ([(X_CROSS, Y_RIDGE), (42, Y_RIDGE), (42, 2), (X_CROSS + 14.0, 2)],
               (0.0, S_MAIN, Z_RIDGE - S_MAIN * Y_RIDGE)),  # south, main
        "k3": ([(6, 2), (X_CROSS, 2), (X_CROSS, Y_RIDGE), (6, Y_RIDGE)],
               (S_MAIN, 0.0, Z_RIDGE - S_MAIN * X_CROSS)),  # the cross gable's west slope
        "k6": ([(X_CROSS, 2), (X_CROSS + 14.0, 2), (X_CROSS, Y_RIDGE)],
               (-S_MAIN, 0.0, Z_RIDGE + S_MAIN * X_CROSS)),  # its east slope, a 45-degree valley against k2
        "k4": ([(0, 30), (24, 30), (24, Y_REAR), (0, Y_REAR)], (0.0, S_REAR, 7.0 - S_REAR * 30)),  # rear south, two
        "k5": ([(24, 30), (38, 30), (38, Y_REAR), (24, Y_REAR)], (0.0, S_REAR, 7.0 - S_REAR * 30)),  # parts (seam)
        "k1": ([(0, Y_REAR), (31.8, Y_REAR), (31.8, 52), (0, 52)], (0.0, -S_REAR, zr + S_REAR * Y_REAR)),  # rear north
        "k7": ([(31.8, Y_REAR), (38, Y_REAR), (38, 52), (31.8, 52)], (0.0, -S_REAR, zr + S_REAR * Y_REAR + 0.1)),
    }
    return roof(outline, facets)


FLAT_Z = {"f0": 14.0, "f1": 20.0, "f2": 11.0}


def commercial_like():
    """(planes, raw, outline) of the COMMERCIAL-like roof: three flats, a hip block, an awning (local feet)."""
    s = 4.0 / 12.0
    parts = [Polygon([(0, 0), (110, 0), (110, 38), (0, 38)]), Polygon([(0, 38), (40, 38), (40, 60), (0, 60)]),
             Polygon([(113, 30), (150, 30), (150, 60), (113, 60)]), Polygon([(110, -4), (160, -4), (160, 30), (110, 30)]),
             Polygon([(55, -9), (64, -9), (64, 0), (55, 0)])]
    outline = list(unary_union(parts).exterior.coords)[:-1]
    eave = 17.0  # the hip block's eaves, 3 ft above the flat next to it
    facets = {
        "f0": (list(parts[0].exterior.coords)[:-1], (0.0, 0.0, FLAT_Z["f0"])),
        "hs": ([(0, 38), (40, 38), (29, 49), (11, 49)], (0.0, s, eave - s * 38)),
        "he": ([(40, 38), (40, 60), (29, 49)], (-s, 0.0, eave + s * 40)),
        "hn": ([(40, 60), (0, 60), (11, 49), (29, 49)], (0.0, -s, eave + s * 60)),
        "hw": ([(0, 60), (0, 38), (11, 49)], (s, 0.0, eave)),
        "f1": (list(parts[2].exterior.coords)[:-1], (0.0, 0.0, FLAT_Z["f1"])),
        "f2": (list(parts[3].exterior.coords)[:-1], (0.0, 0.0, FLAT_Z["f2"])),
        "aw": (list(parts[4].exterior.coords)[:-1], (0.0, 3.0 / 12.0, 10.0 + 9 * 3.0 / 12.0)),  # a shed falling south
    }
    return roof(outline, facets)


def _straight_along(line, axis: str, at: float, tol: float = 0.3) -> bool:
    k = 1 if axis == "x" else 0  # a line along x has constant y
    return all(abs(q[k] - at) < tol for q in line.coords)


def test_house_like_is_one_section_with_the_rear_valley_and_the_main_ridge_straight():
    res = envelope_detail(*house_like())
    assert res.gate_failure is None, res.gate_failure
    assert not res.merged_small
    assert len(res.sections) == 1 and res.sections[0]["method"] == "envelope"
    valleys = [v for v in borders_of(res, "valley") if _straight_along(v, "x", Y_VALLEY)]
    assert sum(v.length for v in valleys) > 28.0  # the long valley between the front and rear sections, along x
    main = [r for r in borders_of(res, "ridge") if _straight_along(r, "x", Y_RIDGE)]
    assert sum(r.length for r in main) > 18.0
    rear = [r for r in borders_of(res, "ridge") if _straight_along(r, "x", Y_REAR, 0.5)]
    assert sum(r.length for r in rear) > 30.0  # one straight rear ridge across the k1/k7 seam


def test_house_like_cross_gable_ridge_and_its_45_degree_valley():
    res = envelope_detail(*house_like())
    assert res.gate_failure is None
    cross = [r for r in borders_of(res, "ridge") if _straight_along(r, "y", X_CROSS, 0.4)]
    assert sum(r.length for r in cross) > 11.0  # along y, the k3/k6 ridge
    k2k6 = [b for b in res.borders if {b["a"], b["b"]} == {"k2", "k6"}]
    assert [b["kind"] for b in k2k6] == ["valley"]
    valley = next(v for v in borders_of(res, "valley") if v.length > 10.0 and not _straight_along(v, "x", Y_VALLEY))
    (a, b), (c, d) = valley.coords[0], valley.coords[-1]
    assert abs(abs(math.degrees(math.atan2(d - b, c - a))) % 90.0 - 45.0) < 1.0


def test_house_like_tapering_step_continues_the_main_ridge_and_seams_split_the_rear():
    res = envelope_detail(*house_like())
    assert res.gate_failure is None
    k0k3 = [b for b in res.borders if {b["a"], b["b"]} == {"k0", "k3"}]
    assert k0k3
    for b in k0k3:
        assert _straight_along(to_local(LineString(b["segment"])), "x", Y_RIDGE, 0.4)  # no notch at the junction
    seams = {frozenset((b["a"], b["b"])) for b in res.borders if b["kind"] == "seam"}
    assert seams == {frozenset(("k4", "k5")), frozenset(("k1", "k7"))}
    assert abs(sum(local_plane(res, k).area for k in ("k1", "k7")) - 38.0 * 13.0) < 25.0


def test_commercial_like_flats_are_sections_split_by_straight_steps():
    res = envelope_detail(*commercial_like())
    assert res.gate_failure is None, res.gate_failure
    assert not res.merged_small
    sec = {p.id: p.section for p in res.planes}
    assert len({sec["f0"], sec["f1"], sec["f2"], sec["aw"], sec["hs"]}) == 5
    assert len({sec[k] for k in ("hs", "he", "hn", "hw")}) == 1
    f1f2 = [b for b in res.borders if {b["a"], b["b"]} == {"f1", "f2"}]
    assert f1f2 and all(b["kind"] == "step" and _straight_along(to_local(LineString(b["segment"])), "x", 30.0)
                        for b in f1f2)
    f0f2 = [b for b in res.borders if {b["a"], b["b"]} == {"f0", "f2"}]
    assert f0f2 and all(b["kind"] == "step" and _straight_along(to_local(LineString(b["segment"])), "y", 110.0)
                        for b in f0f2)
    assert abs(sum(b["length_ft"] for b in f0f2) - 30.0) < 1.0  # one straight wall the whole way
    assert abs(local_plane(res, "f1").area - 37 * 30) < 50.0 and abs(local_plane(res, "f2").area - 1700.0) < 75.0
    assert abs(local_plane(res, "f0").area - 110 * 38) < 60.0


def test_commercial_like_hip_block_and_boxed_awning():
    res = envelope_detail(*commercial_like())
    assert res.gate_failure is None
    hips = [h for h in borders_of(res, "hip") if h.length > 8.0]
    assert len(hips) == 4
    (ridge,) = [r for r in borders_of(res, "ridge") if r.length > 5.0]
    assert _straight_along(ridge, "x", 49.0) and abs(ridge.length - 18.0) < 1.0
    aw = local_plane(res, "aw")
    box = Polygon([(55, -9), (64, -9), (64, 0), (55, 0)])
    assert aw.intersection(box).area > 0.8 * box.area and aw.area < 1.4 * box.area  # boxed, not grown into the flat
    assert {b["kind"] for b in res.borders if "aw" in (b["a"], b["b"])} == {"step"}
