"""Engine improvements (phase 2b), each pinned on synthetic roofs with exact answers: roof-edge position independent of
point density, low-slope roofs, junction nodes, flat-roof junk, multi-level flat roofs, tree crowns, thin clouds."""

import pytest
from engine_improve_cases import cases, drawn_area, length, run, truth
from shapely.ops import unary_union

from roof_measure.engine import measure_roof
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.params import DEFAULT

M2FT = 3.280839895013123


def _area_err(name: str) -> float:
    return drawn_area(run(name, DEFAULT)) / sum(f.area_sqft for f in truth(name).facets) - 1


@pytest.mark.parametrize("name", [f"{s}_d{d}" for s in ("gable", "hip", "l_shape", "t_shape", "shed", "flat", "two_level") for d in (16, 8)])
def test_area_within_the_gate_at_16_and_8_points(name):
    """Plan gate 9: area within 2% (the roof edge is measured, not assumed; was -4..-9% / +2..3% at the port)."""
    assert abs(_area_err(name)) <= 0.02


@pytest.mark.parametrize("name", ["gable_d16", "gable_d8", "hip_d16", "hip_d8", "l_shape_d16"])
def test_measured_overhang_does_not_depend_on_density(name):
    """The true overhang is 0.3 m. The support boundary moves inward as returns thin out; the spacing correction undoes it."""
    got = [v for v in run(name, DEFAULT).outline.overhang_measured_m if v is not None]
    assert got and all(abs(v - 0.3) <= 0.12 for v in got), got


@pytest.mark.parametrize("name", ["gable_p25_d8", "gable_p30_d8", "hip_p30_d8", "cross_gable_p30_d16", "gable_p25_d8_rot17"])
def test_low_slope_roofs_keep_their_planes(name):
    """2.5/12 and 3/12 roofs are pitched, not shattered and not merged into one plane: facet count matches the truth."""
    res = run(name)
    assert len(res.facets) == len(truth(name).facets)
    assert {f.roof_type for f in res.facets} == {"pitched"}
    assert all(abs(f.pitch_rise - float(name.split("_p")[1][:2]) / 10) <= 0.6 for f in res.facets)


@pytest.mark.parametrize("name", ["gable_p25_d8_noisy", "hip_p30_d8_noisy", "l_shape_p30_d8_noisy"])
def test_low_slope_with_realistic_noise(name):
    """7 cm of vertical noise on a 2.5-3/12 roof (the real LiDAR scatter) keeps the facet count and the area."""
    res = run(name, DEFAULT)
    assert len(res.facets) == len(truth(name).facets)
    assert abs(drawn_area(res) / sum(f.area_sqft for f in truth(name).facets) - 1) <= 0.03


def test_two_level_flat_roof_is_two_facets_with_the_measured_step():
    res = run("two_level_flat_d16", DEFAULT)
    assert len(res.facets) == 2 and {f.roof_type for f in res.facets} == {"flat"}
    steps = [e for e in res.edges if e.type == "level_change"]
    assert steps and abs(sum(e.length_ft for e in steps) - truth("two_level_flat_d16").totals["level_change_ft"]) <= 1.5
    assert all(abs(e.jump_ft - 1.0 * M2FT) <= 0.7 for e in steps)


@pytest.mark.parametrize("name", ["flat_equipment_d16", "flat_equipment_d8", "flat_equipment_d8_noisy"])
def test_rooftop_units_and_a_bulkhead_are_part_of_the_flat_roof(name):
    """Equipment under 6 m2 is absorbed: one flat facet, no pitched patch, the main roof's area."""
    res = run(name, DEFAULT)
    assert len(res.facets) == 1 and res.facets[0].roof_type == "flat"
    assert abs(_area_err(name)) <= 0.03  # the units' plan area belongs to the one flat facet


@pytest.mark.parametrize("name", [pytest.param("flat_parapet_d16", marks=pytest.mark.xfail(
    strict=True, reason="three flat facets, two expected: the edge finder ends the roof at the parapet's inner face on one side, so "
                        "the parapet strip splits in two arms and absorb._parapet skips the wedge-shaped one (inscribed radius 0.81 m "
                        "over parapet_radius_m 0.6). All facets stay flat; area -5.5%. Parked: parapet edge rule")), "flat_parapet_d8"])
def test_parapet_strips_do_not_become_pitched_facets(name):
    res = run(name, DEFAULT)
    assert {f.roof_type for f in res.facets} == {"flat"} and len(res.facets) <= 2


def test_low_slope_l_shape_junction_is_where_the_planes_meet():
    """The ridge, valley and hip meet at one node; the raster put it 0.6-1.0 m off at 2.5/12 and cut the valley by 11%."""
    res = run("l_shape_p25_d16", DEFAULT)
    want = truth("l_shape_p25_d16").totals
    assert abs(length(res, "valley") / want["valley_ft"] - 1) <= 0.05
    assert abs(length(res, "hip") / want["hip_ft"] - 1) <= 0.05


def test_a_short_chain_with_a_real_corner_is_not_straightened():
    """Dutch gable: the vertical gable wall plus the hip are one 5 m chain; straightening it dropped one of four hips."""
    res = run("dutch_gable_d8", DEFAULT)
    assert abs(length(res, "hip") / truth("dutch_gable_d8").totals["hip_ft"] - 1) <= 0.06  # +5.1% since the hip reaches the corner


@pytest.mark.parametrize("name", ["gable_d8_trees", "hip_d8_trees", "l_shape_d8_trees"])
def test_tree_crowns_do_not_create_facets_or_bend_planes(name):
    res = run(name, DEFAULT)
    assert len(res.facets) == len(truth(name).facets)
    pitch = truth(name).facets[0].pitch
    assert all(abs(f.pitch_rise - pitch) <= 0.8 for f in res.facets)
    assert abs(_area_err(name)) <= 0.05
    polys = [f.polygon for f in res.facets]
    assert unary_union(polys).area >= 0.97 * sum(p.area for p in polys)


@pytest.mark.parametrize("name", ["gable_d4", "hip_d4", "l_shape_d4"])
def test_thin_clouds_are_refused_or_measured_within_ten_percent(name):
    res = run(name, DEFAULT)
    if res.refused:
        assert res.quality.verdict == "lidar_too_sparse"
    else:
        assert res.quality.verdict in ("low_density", "ok")
        assert abs(_area_err(name)) <= 0.10


@pytest.mark.parametrize("name", ["gable_d2", "flat_d2", "hip_d2"])
def test_two_points_per_square_metre_is_refused(name):
    res = run(name)
    assert res.refused and res.quality.verdict == "lidar_too_sparse" and not res.facets


@pytest.mark.parametrize("name", ["gable_p25_d8_noisy", "flat_equipment_d8", "l_shape_d8_trees"])
def test_two_runs_are_identical(name):
    c = cases()[name]
    pts = c.points()
    wall = c.roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    again = measure_roof(rp, wall, outline_source="county", parcel_match="given", context=pts)
    assert again.to_result_json("x") == run(name).to_result_json("x")


@pytest.mark.parametrize("pitch", [6.0, 7.0, 9.0, 12.0])
def test_porch_faces_are_kept_at_any_roof_pitch(pitch):
    """A small porch hip face on the roof edge is a facet because it has its own level eave and normal point density, at
    6, 7, 9 and 12/12 alike (the old rule dropped any narrow outline strip steeper than 6.0, which cost a 6.06/12 face)."""
    from engine_improve_cases import measure_roof_for

    from roof_measure.engine import synth_points

    roof = synth_points.complex_hip(pitch=pitch)
    res = measure_roof_for(roof, 16)
    assert len(res.facets) >= 21  # the 22nd (a small end whose two faces merge) is a known partition limit, same at 6/12
    assert sum(1 for f in res.facets if f.area_sqft < 80) >= 8  # the small porch / bay faces are all there
    assert abs(sum(f.area_sqft for f in res.facets) / sum(f.area_sqft for f in roof.facets) - 1) <= 0.03


@pytest.mark.parametrize("pitch", [6.0, 12.0])
def test_wall_returns_below_an_eave_do_not_become_a_facet(pitch):
    """Vertical returns along the south wall (a wall, not a roof) must not add a facet or bend the roof."""
    import numpy as np
    from engine_improve_cases import measure_roof_for

    from roof_measure.engine import synth_points

    def wall(roof):
        minx, miny, maxx, _ = roof.wall_polygon().bounds
        gx, gz = np.meshgrid(np.arange(minx, maxx, 0.25), np.arange(0.4, 3.0, 0.25))
        rng = np.random.default_rng(3)
        return np.c_[gx.ravel(), miny + rng.normal(0, 0.03, gx.size), gz.ravel(), np.ones(gx.size)]

    roof = synth_points.gable(pitch=pitch)
    res = measure_roof_for(roof, 16, extra=wall)
    assert len(res.facets) == 2
    assert abs(sum(f.area_sqft for f in res.facets) / sum(f.area_sqft for f in roof.facets) - 1) <= 0.03


def test_a_crease_chain_ends_on_the_eave_corner():
    """Dutch gable: the hip ran to a raster node 0.6 m short of the corner and the stub went to the wrong facet."""
    res = run("dutch_gable_d8", DEFAULT)
    assert length(res, "rake") == 0.0


@pytest.mark.parametrize("shape", ["gable", "cross_gable", "hip"])
@pytest.mark.parametrize("pitch", [8.0, 10.0, 12.0, 14.0, 16.0])
@pytest.mark.parametrize("density", [8, 16])
def test_steep_roofs_are_pitched_not_flat(shape, pitch, density):
    """A pitched roof is never drawn flat: 8..16/12 at 8 and 16 pts/m2 keep their facets (the plane pitch cap at 14/12 used to
    drop whole 14-16/12 roofs and the fallback drew one flat facet)."""
    from engine_improve_cases import measure_roof_for

    from roof_measure.engine import synth_points

    roof = getattr(synth_points, shape)(pitch=pitch)
    res = measure_roof_for(roof, density)
    assert {f.roof_type for f in res.facets} == {"pitched"}
    assert len(res.facets) >= len(roof.facets) - (1 if shape == "hip" and pitch >= 16 else 0)
    assert all(abs(f.pitch_rise - pitch) <= 1.0 for f in res.facets)


def test_a_roof_with_no_planes_is_never_labelled_ok(monkeypatch):
    from engine_improve_cases import measure_roof_for

    from roof_measure.engine import detect, measure, synth_points

    monkeypatch.setattr(measure, "detect_planes", lambda crop, wall, th, ctx: ([], __import__("numpy").full(len(crop), -1)))
    assert detect  # the module exists
    res = measure_roof_for(synth_points.gable(), 16)
    assert "planes_not_found" in res.quality.reasons and res.quality.verdict == "poor_fit"


@pytest.mark.parametrize("shape,width", [("gable", 0.5), ("hip", 0.5), ("cross_gable", 0.3)])  # a 1 m flat top at a cross-gable junction (width 2 m) is no longer a strip: it cost a real low-slope double-gable roof its south slope
def test_a_rounded_ridge_is_not_a_flat_facet(shape, width):
    """LiDAR rounds ridges: returns within `width` of the ridge sit on a flat top. That strip is not a facet."""
    import numpy as np
    import shapely
    from shapely.geometry import LineString

    from roof_measure.engine import measure_roof, synth_points
    from roof_measure.engine.load import roof_points_from_arrays

    roof = getattr(synth_points, shape)()
    pts = synth_points.simulate(roof, density=16, seed=1)
    for e in (e for e in roof.edges if e.type == "ridge"):
        ln = LineString([e.p0[:2], e.p1[:2]])
        near = (shapely.distance(ln, shapely.points(pts[:, 0], pts[:, 1])) < width) & (pts[:, 3] == 1)
        pts[near, 2] = e.p0[2] - (roof.params.get("pitch", 6) / 12.0) * width
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res = measure_roof(rp, wall, params=DEFAULT, outline_source="county", parcel_match="given", context=pts)
    assert {f.roof_type for f in res.facets} == {"pitched"}
    assert len(res.facets) <= len(roof.facets)
    assert np.isfinite(sum(f.area_sqft for f in res.facets))


def test_a_small_flat_porch_roof_on_the_outline_is_kept():
    """A real small flat roof reaches the roof outline: it is not an enclosed hole."""
    from engine_improve_cases import measure_roof_for

    from roof_measure.engine import synth_points

    res = measure_roof_for(synth_points.flat_pitched(flat_ft=10.0), 16)
    assert {f.roof_type for f in res.facets} == {"flat", "pitched"}


def _ring_extras(kind: str, off: float):
    import numpy as np

    def f(roof):
        minx, miny, maxx, maxy = roof.roof_polygon().bounds
        rng = np.random.default_rng(5)
        out = []
        if "wall" in kind:  # a neighbour's wall parallel to the south eave, `off` m beyond it, up to 6 m high
            gx, gz = np.meshgrid(np.arange(minx, maxx, 0.25), np.arange(0.5, 6.0, 0.25))
            out.append(np.c_[gx.ravel(), np.full(gx.size, miny - off) + rng.normal(0, 0.03, gx.size), gz.ravel(),
                             np.ones(gx.size)])
        if "tree" in kind:  # a crown at the north eave, centre `off` m beyond the roof edge
            r, m = 1.6, 300
            rho = r * np.sqrt(rng.uniform(size=m))
            a = rng.uniform(0, 2 * np.pi, m)
            z = 4.0 + 1.5 * np.sqrt(np.clip(1 - (rho / r) ** 2, 0, 1)) * rng.uniform(-0.4, 1, m)
            out.append(np.c_[(minx + maxx) / 2 + rho * np.cos(a), maxy + off + rho * np.sin(a), z, np.ones(m)])
        return np.vstack(out)

    return f


@pytest.mark.parametrize("shape", ["gable", "hip"])
@pytest.mark.parametrize("kind", ["wall", "tree", "wall+tree"])
@pytest.mark.parametrize("off", [0.8, 1.0, 1.2])
def test_a_tree_and_a_neighbour_wall_beyond_the_eave_change_nothing(shape, kind, off):
    """150-300 stray returns 0.8-1.2 m beyond the eave (a crown, a wall) must give the same roof as without them."""
    from engine_improve_cases import measure_roof_for

    from roof_measure.engine import synth_points

    roof = getattr(synth_points, shape)()
    base = measure_roof_for(roof, 16)
    res = measure_roof_for(roof, 16, extra=_ring_extras(kind, off))
    assert len(res.facets) == len(base.facets) and res.quality.verdict == base.quality.verdict == "ok"
    assert {f.roof_type for f in res.facets} == {"pitched"}
    assert abs(sum(f.area_sqft for f in res.facets) / sum(f.area_sqft for f in base.facets) - 1) <= 0.02


def _double_gable_result(density: int, rounded_m: float):
    import shapely
    from shapely.geometry import LineString

    from roof_measure.engine import measure_roof, synth_extra, synth_points
    from roof_measure.engine.load import roof_points_from_arrays

    roof = synth_extra.double_gable()
    pts = synth_points.simulate(roof, density=density, seed=1)
    for e in (e for e in roof.edges if e.type == "ridge"):
        ln = LineString([e.p0[:2], e.p1[:2]])
        near = (shapely.distance(ln, shapely.points(pts[:, 0], pts[:, 1])) < rounded_m) & (pts[:, 3] == 1)
        pts[near, 2] = e.p0[2] - roof.facets[e.facets[0]].pitch / 12.0 * rounded_m  # a flat top, as LiDAR rounds a ridge
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    return roof, measure_roof(rp, wall, params=DEFAULT, outline_source="county", parcel_match="given", context=pts)


@pytest.mark.parametrize("density", [8, 16])
@pytest.mark.parametrize("rounded", [0.0, 0.3, 0.5])
def test_low_slope_double_gable_keeps_all_four_planes_and_both_ridges(density, rounded):
    """Two parallel gables at 2.2/12 and 3.7/12 (opposing normals 25-35 degrees apart), clean and with a rounded ridge: four
    pitched facets, ridge and valley within 5%. A ridge-strip rule once gave a whole south slope to the north one (seen on a real low-slope double-gable roof)."""
    roof, res = _double_gable_result(density, rounded)
    assert len(res.facets) == 4 and {f.roof_type for f in res.facets} == {"pitched"}
    assert len({round(f.aspect_deg / 90) % 4 for f in res.facets}) >= 2  # both slope directions are present
    for kind in ("ridge", "valley"):
        assert abs(length(res, kind) / roof.totals[f"{kind}_ft"] - 1) <= 0.05, kind
