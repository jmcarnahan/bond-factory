"""engine.objects.find_objects on synthetic roofs: expected numbers come from the geometry of what is built.

Detectable minimum (measured with 4 seeds each, a flat-topped box 1.2 m high on a gable slope): a footprint side of
1.0 m is found at 8, 13 and 20 returns per m2; 0.7 m is found at 13 and 20 (not reliably at 8); 0.3 m is never a
chimney. Skylights are flush with the roof and are not detectable at all.
"""

from __future__ import annotations

import dataclasses
import math
from functools import cache

import numpy as np
import pytest
import shapely
from shapely.affinity import translate
from shapely.geometry import Polygon, box

from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.measure import measure_stages
from roof_measure.engine.objects import find_objects
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.synth_points import add_box, cases, gable, hip, simulate
from roof_measure.engine.types import Facet, Outline

FT = 1 / 0.3048
KEYS = {"id", "kind", "center", "size_ft", "polygon", "height_ft", "facet", "returns"}


def _measure(roof, pts):
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res, _ = measure_stages(rp, wall, params=DEFAULT, deadline=None, outline_source="county", parcel_match="given",
                            context=pts)
    return res, rp.ground_z


@cache
def _gable_with_box(density, seed, size, height, rotation=0.0, dx=1.5):
    """(objects, mislabelled, box centre in feet, facet ids) for a gable with a box on its slope."""
    roof = gable(rotation_deg=rotation)
    c = roof.roof_polygon().centroid
    centre = (c.x + dx * math.cos(math.radians(rotation)), c.y + dx * math.sin(math.radians(rotation)))
    pts = simulate(roof, density=density, seed=seed)
    pts = add_box(pts, roof, centre, (size, size), height, rotation_deg=rotation, density=density, seed=seed + 20)
    res, gz = _measure(roof, pts)
    objs, mis = find_objects(pts, res.facets, res.outline, gz)
    return objs, mis, (centre[0] * FT, centre[1] * FT), [f.id for f in res.facets]


def _angle_mod90(poly):
    (x0, y0), (x1, y1) = poly[0], poly[1]
    return math.degrees(math.atan2(y1 - y0, x1 - x0)) % 90


@pytest.mark.parametrize("rotation", [0.0, 30.0])
def test_chimney_on_a_slope_is_one_chimney_with_its_place_size_and_height(rotation):
    objs, mis, centre, facet_ids = _gable_with_box(13, 1, 1.0, 1.5, rotation)
    assert mis == []
    assert len(objs) == 1
    o = objs[0]
    assert set(o) == KEYS and o["id"] == "o1" and o["kind"] == "chimney"
    assert math.dist(o["center"], centre) < 0.3 * FT  # centre within 0.3 m
    assert all(abs(side - 1.0 * FT) < 0.4 * FT for side in o["size_ft"])  # each side within 0.4 m of 1 m
    assert o["size_ft"][0] >= o["size_ft"][1]  # long side first
    assert 1.2 * FT < o["height_ft"] < 1.9 * FT  # 1.5 m above the plane at its centre, 0.25 m either way on a 6/12 slope
    assert o["facet"] in facet_ids and o["returns"] >= 4
    poly = o["polygon"]
    assert poly[0] == poly[-1] and len(poly) == 5  # a closed rectangle, in feet
    assert abs(Polygon(poly).area - o["size_ft"][0] * o["size_ft"][1]) < 0.05 * o["size_ft"][0] * o["size_ft"][1]
    a = _angle_mod90(poly)
    assert min(abs(a - rotation % 90), 90 - abs(a - rotation % 90)) < 8.0  # the footprint turns with the roof


@pytest.mark.parametrize("density", [8, 13, 20])
def test_a_one_metre_chimney_is_found_at_every_density(density):
    for seed in (1, 2):
        objs, mis, _, _ = _gable_with_box(density, seed, 1.0, 1.2)
        assert [o["kind"] for o in objs] == ["chimney"] and mis == []


@pytest.mark.parametrize("density", [13, 20])
def test_a_70_cm_chimney_is_found_at_13_and_20_per_m2(density):
    kinds = [[o["kind"] for o in _gable_with_box(density, s, 0.7, 1.2)[0]] for s in (1, 2)]
    assert kinds == [["chimney"], ["chimney"]]


@pytest.mark.parametrize("density", [8, 13, 20])
def test_a_30_cm_flue_is_never_a_chimney(density):
    for seed in (1, 2, 3, 4):
        objs, mis, _, _ = _gable_with_box(density, seed, 0.3, 1.2)
        assert [o for o in objs if o["kind"] == "chimney"] == [] and mis == []


def test_a_box_on_the_ridge_of_a_hip_roof_is_a_lantern():
    roof = hip()
    c = roof.roof_polygon().centroid  # on the ridge: the ridge runs along x at mid width
    for density in (8, 13, 20):
        pts = simulate(roof, density=density, seed=1)
        pts = add_box(pts, roof, (c.x, c.y), (1.6, 1.6), 0.5, density=density, seed=5)
        res, gz = _measure(roof, pts)
        objs, mis = find_objects(pts, res.facets, res.outline, gz)
        assert mis == [] and [o["kind"] for o in objs] == ["lantern"]
        o = objs[0]
        assert math.dist(o["center"], (c.x * FT, c.y * FT)) < 0.3 * FT
        assert all(abs(side - 1.6 * FT) < 0.4 * FT for side in o["size_ft"])
        # 0.5 m above the ridge; the slope falls away 0.27 m under the box's far sides (4/12 over 0.8 m)
        assert 0.4 * FT < o["height_ft"] < 0.85 * FT


def test_ids_run_by_x_then_y():
    roof = gable()
    c = roof.roof_polygon().centroid
    pts = simulate(roof, density=16, seed=3)
    pts = add_box(pts, roof, (c.x + 2.0, c.y), (1.0, 1.0), 1.5, density=16, seed=4)
    pts = add_box(pts, roof, (c.x - 2.0, c.y - 0.5), (1.0, 1.0), 1.5, density=16, seed=5)
    res, gz = _measure(roof, pts)
    objs, _ = find_objects(pts, res.facets, res.outline, gz)
    assert [o["id"] for o in objs] == ["o1", "o2"]
    assert objs[0]["center"][0] < objs[1]["center"][0]


def test_a_tree_crown_over_a_corner_lists_nothing():
    for name in ("gable_d8_trees", "hip_d8_trees", "l_shape_d8_trees"):
        case = next(c for c in cases() if c.name == name)
        pts = case.points()
        res, gz = _measure(case.roof, pts)
        assert find_objects(pts, res.facets, res.outline, gz) == ([], []), name


def test_bare_roofs_have_no_objects():
    bad = {}
    for case in cases():
        pts = case.points()
        res, gz = _measure(case.roof, pts)
        out = find_objects(pts, res.facets, res.outline, gz)
        if out != ([], []):
            bad[case.name] = out
    assert bad == {}


def _flat_roof_with_upper_patch(patch_w, patch_h, rise=1.2, density=13, seed=1):
    """A 10 x 8 m flat roof at z = 3 m (one facet, the engine's own types) with a planar upper patch ``rise`` above it."""
    rng = np.random.default_rng(seed)
    ring = box(0, 0, 10, 8)
    facet = Facet(id="f1", polygon=ring, plane=(0.0, 0.0, 3.0), label=0, pitch_rise=0.0, aspect_deg=0.0,
                  roof_type="flat", plan_area_sqft=80 * 10.7639, area_sqft=80 * 10.7639, points=1000, rms_m=0.02)
    outline = Outline(drawn=ring, priced=ring, source="county", county=True, scale_drawn=1.0)
    s = 1 / math.sqrt(density)
    gx, gy = np.meshgrid(np.arange(-8, 18, s), np.arange(-8, 16, s))
    x, y = gx.ravel() + rng.uniform(0, s, gx.size), gy.ravel() + rng.uniform(0, s, gx.size)
    on = shapely.contains_xy(ring, x, y)
    patch = shapely.contains_xy(box(3, 2, 3 + patch_w, 2 + patch_h), x, y)
    z = np.where(patch, 3.0 + rise, 3.0) + rng.normal(0, 0.02, x.size)
    cls = np.where(on, 1.0, 2.0)
    z = np.where(on, z, rng.normal(0, 0.02, x.size))
    return np.column_stack([x, y, z, cls]), [facet], outline


def test_a_planar_upper_roof_the_facets_missed_is_mislabelled_not_an_object():
    pts, facets, outline = _flat_roof_with_upper_patch(2.4, 2.5)  # 6 m2
    objs, mis = find_objects(pts, facets, outline, 0.0)
    assert objs == []
    assert len(mis) == 1
    m = mis[0]
    assert "id" not in m and "kind" not in m
    assert abs(m["area_sqft"] - 6.0 * 10.7639) < 0.2 * 6.0 * 10.7639
    assert abs(m["height_ft"] - 1.2 * FT) < 0.15 * FT
    assert math.dist(m["center"], ((3 + 1.2) * FT, (2 + 1.25) * FT)) < 0.3 * FT


def test_a_small_planar_part_is_an_object_not_mislabelled():
    pts, facets, outline = _flat_roof_with_upper_patch(1.2, 1.2)  # 1.4 m2, 1.2 m high
    objs, mis = find_objects(pts, facets, outline, 0.0)
    assert mis == [] and [o["kind"] for o in objs] == ["chimney"]


def test_an_object_gives_the_same_result_translated_by_any_offset():
    roof = gable()
    c = roof.roof_polygon().centroid
    pts = add_box(simulate(roof, density=13, seed=2), roof, (c.x + 1.5, c.y), (1.0, 1.0), 1.5, density=13, seed=3)
    res, gz = _measure(roof, pts)
    base, _ = find_objects(pts, res.facets, res.outline, gz)
    assert len(base) == 1
    for dx, dy in [(0.07, 0.13), (0.125, 0.0625), (123456.789, -98765.4321)]:
        moved = pts.copy()
        moved[:, 0] += dx
        moved[:, 1] += dy
        facets = [dataclasses.replace(f, polygon=translate(f.polygon, dx, dy),
                                      plane=(f.plane[0], f.plane[1], f.plane[2] - f.plane[0] * dx - f.plane[1] * dy))
                  for f in res.facets]
        outline = dataclasses.replace(res.outline, drawn=translate(res.outline.drawn, dx, dy),
                                      priced=translate(res.outline.priced, dx, dy))
        got, _ = find_objects(moved, facets, outline, gz)
        assert [(o["kind"], o["size_ft"], o["height_ft"], o["returns"], o["facet"]) for o in got] == \
               [(o["kind"], o["size_ft"], o["height_ft"], o["returns"], o["facet"]) for o in base], (dx, dy)
        assert math.dist(got[0]["center"], [base[0]["center"][0] + dx * FT, base[0]["center"][1] + dy * FT]) < 0.02


def test_no_side_effects_and_nothing_to_find_returns_empty():
    roof = gable()
    pts = add_box(simulate(roof, density=13, seed=2), roof, (5.0, 4.0), (1.0, 1.0), 1.5, density=13, seed=3)
    res, gz = _measure(roof, pts)
    before = pts.copy()
    a = find_objects(pts, res.facets, res.outline, gz)
    assert np.array_equal(pts, before) and a == find_objects(pts, res.facets, res.outline, gz)
    assert find_objects(np.zeros((0, 4)), res.facets, res.outline, gz) == ([], [])
    assert find_objects(pts, [], res.outline, gz) == ([], [])
