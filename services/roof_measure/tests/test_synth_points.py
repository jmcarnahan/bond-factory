"""Synthetic roofs: closed-form truth, tiling, edge geometry, rotation invariance and the LiDAR simulator."""

import math
from collections import Counter

import numpy as np
import pytest
import shapely

from roof_measure.engine import synth_points as sp
from roof_measure.engine.synth_shapes import M2FT, SQM2SQFT

SHAPE_NAMES = list(sp.SHAPES)
_ROOFS = {n: f() for n, f in sp.SHAPES.items()}


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def types(roof):
    return Counter(e.type for e in roof.edges)


# ---- closed forms ----------------------------------------------------------------------------

def test_hip_35x26_at_4_12_matches_hand_numbers():
    t = sp.hip(35, 26, 4, overhang_m=0).totals
    s = 4 / 12
    hips = 4 * 13 * math.sqrt(2 + s * s)
    assert rel(t["eave_ft"], 122.0) < 1e-3 and rel(t["perimeter_ft"], 122.0) < 1e-3
    assert rel(t["ridge_ft"], 9.0) < 1e-3
    assert rel(t["hip_ft"], 75.55) < 1e-3 and rel(t["hip_ft"], hips) < 1e-6
    assert rel(t["area_sqft"], 959.22) < 1e-3
    assert rel(t["plan_area_sqft"], 910.0) < 1e-6
    assert t["valley_ft"] == 0 and t["facet_count"] == 4


@pytest.mark.parametrize("ovh", [0.0, 0.3, 0.6])
def test_gable_closed_form(ovh):
    length, width, pitch = 40.0, 26.0, 6.0
    o, s = ovh * M2FT, pitch / 12
    k = math.sqrt(1 + s * s)
    t = sp.gable(length, width, pitch, overhang_m=ovh).totals
    assert rel(t["ridge_ft"], length + 2 * o) < 1e-6
    assert rel(t["eave_ft"], 2 * (length + 2 * o)) < 1e-6
    assert rel(t["rake_ft"], 4 * (width / 2 + o) * k) < 1e-6
    assert rel(t["area_sqft"], (length + 2 * o) * (width + 2 * o) * k) < 1e-6
    assert rel(t["perimeter_ft"], t["eave_ft"] + t["rake_ft"]) < 1e-9


@pytest.mark.parametrize("ovh", [0.0, 0.45])
def test_hip_closed_form_with_overhang(ovh):
    length, width, pitch = 35.0, 26.0, 4.0
    o, s = ovh * M2FT, pitch / 12
    t = sp.hip(length, width, pitch, overhang_m=ovh).totals
    assert rel(t["eave_ft"], 2 * (length + width + 4 * o)) < 1e-6
    assert rel(t["ridge_ft"], length - width) < 1e-6
    assert rel(t["hip_ft"], 4 * (width / 2 + o) * math.sqrt(2 + s * s)) < 1e-6
    assert rel(t["area_sqft"], (length + 2 * o) * (width + 2 * o) * math.sqrt(1 + s * s)) < 1e-6


def test_valley_and_ridge_counts_of_the_compound_shapes():
    assert types(_ROOFS["l_shape"])["valley"] == 1 and types(sp.l_shape(corner="gable"))["valley"] == 2
    assert types(_ROOFS["t_shape"])["valley"] == 2 and types(_ROOFS["cross_gable"])["valley"] == 4
    for name in ("gable", "hip", "t_shape", "cross_gable", "shed", "flat", "two_level"):
        assert "level_change" not in types(_ROOFS[name]) or name == "two_level"
    assert types(_ROOFS["shed"])["eave"] == 1 and "ridge" not in types(_ROOFS["shed"]) and types(_ROOFS["flat"])["flat_edge"] == 4


def test_dutch_gable_has_vertical_walls_not_valleys():
    roof = sp.dutch_gable(overhang_m=0)
    c = types(roof)
    assert c["level_change"] == 4 and c["hip"] == 4 and c["valley"] == 0 and len(roof.facets) == 4
    assert rel(roof.totals["ridge_ft"], 40 - 2 * 6) < 1e-6  # the gable ridge runs past the hips
    wall = [e for e in roof.edges if e.type == "level_change"]
    assert all(rel(e.jump_ft, (13 - 6) * 0.5 / 2) < 1e-6 for e in wall)  # mean of 0 and the 3.5 ft apex step


def test_steps_and_transitions():
    same, step = _ROOFS["flat_pitched"], _ROOFS["flat_pitched_step"]
    assert types(same)["transition"] == 1 and "level_change" not in types(same)
    assert types(step)["level_change"] == 1 and "transition" not in types(step)
    lc = next(e for e in step.edges if e.type == "level_change")
    assert rel(lc.jump_ft, 0.6 * M2FT) < 1e-6 and rel(lc.length_ft, (40 + 2 * 0.3 * M2FT)) < 1e-6
    two = [e for e in _ROOFS["two_level"].edges if e.type == "level_change"]
    assert len(two) == 2 and all(rel(e.jump_ft, 1.2 * M2FT) < 1e-6 for e in two)


def test_complex_hip_has_22_small_real_facets():
    roof = _ROOFS["complex_hip"]
    assert len(roof.facets) == 22
    assert min(f.plan_area_sqft for f in roof.facets) < 30 and min(f.plan_area_sqft for f in roof.facets) > 20
    assert roof.totals["hip_ft"] > 150 and roof.totals["valley_ft"] > 100


# ---- geometry invariants -----------------------------------------------------------------------

@pytest.mark.parametrize("name", SHAPE_NAMES)
def test_facets_tile_the_roof_outline_without_overlap(name):
    roof = _ROOFS[name]
    polys = roof.facet_polygons()
    outline = roof.roof_polygon()
    assert rel(sum(p.area for p in polys), outline.area) < 1e-6
    assert rel(shapely.union_all(polys).area, outline.area) < 1e-6
    overlap = sum(polys[i].intersection(polys[j]).area for i in range(len(polys)) for j in range(i + 1, len(polys)))
    assert overlap < 1e-6 * outline.area
    assert rel(roof.totals["plan_area_sqft"], outline.area * SQM2SQFT) < 1e-6
    assert shapely.Polygon(roof.wall_outline).within(outline.buffer(1e-6))


@pytest.mark.parametrize("name", SHAPE_NAMES)
def test_every_edge_lies_on_its_facets_planes(name):
    roof = _ROOFS[name]
    for e in roof.edges:
        on = e.facets[:1] if e.type == "level_change" else e.facets
        for fid in on:
            for p in (e.p0, e.p1):
                assert abs(roof.facets[fid].z(p[0], p[1]) - p[2]) < 1e-6
        assert rel(e.length_ft, math.dist(e.p0, e.p1) * M2FT) < 1e-9 and e.length_ft > 0.003 * M2FT


@pytest.mark.parametrize("name", ["gable", "hip", "l_shape", "t_shape", "dutch_gable", "flat_pitched_step", "complex_hip"])
@pytest.mark.parametrize("rot", [17.0, 45.0])
def test_totals_are_rotation_invariant(name, rot):
    base = _ROOFS[name].totals
    turned = sp.SHAPES[name](rotation_deg=rot)
    for key, val in base.items():
        assert rel(turned.totals[key], val) < 1e-6 if val else abs(turned.totals[key]) < 1e-6, key
    assert [e.type for e in sorted(turned.edges, key=lambda e: (e.type, e.length_ft))] == \
           [e.type for e in sorted(_ROOFS[name].edges, key=lambda e: (e.type, e.length_ft))]
    for e in turned.edges:
        on = e.facets[:1] if e.type == "level_change" else e.facets
        assert all(abs(turned.facets[i].z(p[0], p[1]) - p[2]) < 1e-6 for i in on for p in (e.p0, e.p1))


def test_flat_pitched_split_at_two_in_twelve():
    assert sp.gable(pitch=1.99).totals["pitched_sqft"] == 0
    assert sp.gable(pitch=1.99).totals["flat_sqft"] > 0
    assert sp.gable(pitch=2.0).totals["flat_sqft"] == 0
    assert all(f.roof_type == "pitched" for f in sp.gable(pitch=2.0).facets)
    mixed = _ROOFS["flat_pitched"]
    flat_area = sum(f.area_sqft for f in mixed.facets if f.pitch < 2.0)
    assert mixed.totals["flat_sqft"] > 0 and rel(mixed.totals["flat_sqft"], flat_area) < 1e-9
    assert rel(mixed.totals["flat_sqft"] + mixed.totals["pitched_sqft"], mixed.totals["area_sqft"]) < 1e-9
    assert all(f.pitch == 0 and f.aspect_deg == 0 for f in _ROOFS["flat"].facets)


def test_pitch_and_aspect_of_a_gable():
    f = sorted(sp.gable(pitch=6, overhang_m=0).facets, key=lambda f: f.aspect_deg)
    assert [round(x.pitch, 6) for x in f] == [6.0, 6.0]
    assert [round(x.aspect_deg, 6) for x in f] == [0.0, 180.0]  # south slope faces away from the ridge: 180 = down toward -y
    turned = sp.gable(pitch=6, overhang_m=0, rotation_deg=90).facets
    assert sorted(round(x.aspect_deg, 6) for x in turned) == [90.0, 270.0]


# ---- LiDAR simulation ---------------------------------------------------------------------------

def test_simulation_is_deterministic_per_seed():
    roof = _ROOFS["hip"]
    a = sp.simulate(roof, density=8, seed=7, trees=1, banding=True)
    assert a.tobytes() == sp.simulate(roof, density=8, seed=7, trees=1, banding=True).tobytes()
    assert a.tobytes() != sp.simulate(roof, density=8, seed=8, trees=1, banding=True).tobytes()
    assert a.shape[1] == 4 and set(np.unique(a[:, 3])) == {1.0, 2.0} and a.dtype == np.float64


@pytest.mark.parametrize("density", sp.DENSITIES)
@pytest.mark.parametrize("name", SHAPE_NAMES)
def test_roof_density_is_within_ten_percent_of_requested(name, density):
    roof = _ROOFS[name]
    pts = sp.simulate(roof, density=density, seed=11)
    got = (pts[:, 3] == 1).sum() / (roof.totals["plan_area_sqft"] / SQM2SQFT)
    assert abs(got / density - 1) < 0.10


def test_roof_returns_follow_the_planes_with_the_requested_noise():
    roof = _ROOFS["l_shape"]
    pts = sp.simulate(roof, density=16, noise_sigma_m=0.03, seed=3)
    roofpts = pts[pts[:, 3] == 1]
    resid = np.full(len(roofpts), np.nan)
    for f in roof.facets:
        m = shapely.contains_xy(f.polygon(), roofpts[:, 0], roofpts[:, 1])
        resid[m] = roofpts[m, 2] - (f.plane[0] * roofpts[m, 0] + f.plane[1] * roofpts[m, 1] + f.plane[2])
    assert not np.isnan(resid).any() and abs(resid.std() - 0.03) < 0.003 and abs(resid.mean()) < 0.003
    ground = pts[pts[:, 3] == 2]
    assert len(ground) > 100 and abs(ground[:, 2].mean()) < 0.01
    assert not shapely.contains_xy(roof.roof_polygon(), ground[:, 0], ground[:, 1]).any()
    assert sp.simulate(roof, density=8, seed=3, ground=False)[:, 3].min() == 1.0
    exact = sp.simulate(roof, density=8, seed=3, noise_sigma_m=0.0)
    assert np.abs(exact[exact[:, 3] == 2][:, 2]).max() == 0.0


def test_trees_are_nonplanar_class_one_clusters_at_the_eaves():
    roof = _ROOFS["gable"]
    plain = sp.simulate(roof, density=8, seed=2)
    treed = sp.simulate(roof, density=8, seed=2, trees=2)
    outside = ~shapely.contains_xy(roof.roof_polygon(), treed[:, 0], treed[:, 1])
    canopy = treed[outside & (treed[:, 3] == 1) & (treed[:, 2] > sp.EAVE_M + 0.3)]
    assert len(canopy) > 80 and (plain[:, 3] == 1).sum() > 0
    assert (treed[:, 3] == 1).sum() > (plain[:, 3] == 1).sum() * 0.9  # canopy returns replace hidden roof returns
    assert canopy[:, 2].std() > 0.2


def test_banding_alternates_dense_and_sparse_strips():
    roof = _ROOFS["hip"]

    def cv(pts):
        h = np.histogram(pts[pts[:, 3] == 2][:, 0], bins=np.arange(-8, 20, 2.0))[0]
        return h.std() / h.mean()

    assert cv(sp.simulate(roof, density=8, seed=5, banding=True)) > 0.35 > cv(sp.simulate(roof, density=8, seed=5))
    banded, plain = sp.simulate(roof, density=8, seed=5, banding=True), sp.simulate(roof, density=8, seed=5)
    assert abs(len(banded) / len(plain) - 1) < 0.15  # the mean density is kept; only its spread changes


def test_outline_offset_shifts_the_points_against_the_outline():
    roof = _ROOFS["gable"]
    a = sp.simulate(roof, density=8, seed=4)
    b = sp.simulate(roof, density=8, seed=4, outline_offset_m=(0.8, -0.5))
    assert np.allclose(b[:, 0] + 0.8, a[:, 0]) and np.allclose(b[:, 1] - 0.5, a[:, 1]) and np.array_equal(a[:, 2:], b[:, 2:])
    moved = roof.translated(-0.8, 0.5)  # exact answers in the shifted frame
    r = [p for p in b[b[:, 3] == 1]][:50]
    for x, y, z, _ in r:
        f = next(f for f in moved.facets if f.polygon().buffer(0.2).contains(shapely.Point(x, y)))
        assert abs(f.z(x, y) - z) < 0.2
    assert rel(moved.totals["area_sqft"], roof.totals["area_sqft"]) < 1e-12


def test_cases_registry_covers_every_shape_and_density():
    cs = sp.cases()
    names = [c.name for c in cs]
    assert len(set(names)) == len(names) >= 60
    for shape in sp.SHAPES:
        for d in sp.DENSITIES:
            assert f"{shape}_d{d}" in names
    assert any("rot17" in n for n in names) and any("rot45" in n for n in names)
    assert any(c.kwargs.get("trees") for c in cs) and any(c.kwargs.get("banding") for c in cs)
    assert any(c.kwargs.get("outline_offset_m") for c in cs)
    pts = next(c for c in cs if c.name == "t_shape_d4").points()
    assert pts.shape[1] == 4 and len(pts) > 500


def test_shed_closed_form_and_high_edge_is_rake_metal():
    length, width, pitch, o = 30.0, 20.0, 3.0, 0.3 * M2FT
    s, k = pitch / 12, math.sqrt(1 + (pitch / 12) ** 2)
    roof = sp.shed(length, width, pitch)
    t = roof.totals
    assert rel(t["area_sqft"], (length + 2 * o) * (width + 2 * o) * k) < 1e-6
    assert rel(t["eave_ft"], length + 2 * o) < 1e-6 and t["ridge_ft"] == 0
    assert rel(t["rake_ft"], 2 * (width + 2 * o) * k + (length + 2 * o)) < 1e-6  # two sloped rakes plus the high edge
    assert rel(t["wall_cap_ft"], length + 2 * o) < 1e-6 and sum(e.high_edge for e in roof.edges) == 1
    assert rel(t["perimeter_ft"], t["eave_ft"] + t["rake_ft"]) < 1e-9 and s > 0


def test_flat_closed_form():
    t = sp.flat(40, 30).totals
    o = 0.3 * M2FT
    assert rel(t["area_sqft"], (40 + 2 * o) * (30 + 2 * o)) < 1e-6 and t["pitched_sqft"] == 0
    assert rel(t["flat_edge_ft"], 2 * (70 + 4 * o)) < 1e-6 and rel(t["perimeter_ft"], t["flat_edge_ft"]) < 1e-9
    assert t["ridge_ft"] == t["hip_ft"] == t["valley_ft"] == 0


def test_two_level_closed_form():
    length, width, o, step = 26.0, 24.0, 0.3 * M2FT, 1.2 * M2FT
    k = math.sqrt(1.25)
    t = sp.two_level(length, width, 1.2, 6).totals
    total_len = 2 * length - 4 + 2 * o  # wall at x=length, no overhang there
    assert rel(t["area_sqft"], (total_len) * (width + 2 * o) * k) < 1e-6
    assert rel(t["ridge_ft"], total_len) < 1e-6 and rel(t["level_change_ft"], 2 * (width / 2 + o) * k) < 1e-6
    assert rel(t["eave_ft"], 2 * total_len) < 1e-6 and t["valley_ft"] == 0 and step > 0


@pytest.mark.parametrize("case", sp.cases(), ids=lambda c: c.name)
def test_totals_equal_the_sums_over_typed_edges(case):
    r = case.roof
    def ft(*kinds):
        return sum(e.length_ft for e in r.edges if e.type in kinds)
    t = r.totals
    assert t["ridge_ft"] == pytest.approx(ft("ridge")) and t["hip_ft"] == pytest.approx(ft("hip"))
    assert t["valley_ft"] == pytest.approx(ft("valley"))
    assert t["perimeter_ft"] == pytest.approx(ft("eave", "rake", "flat_edge"))
    assert all(e.exterior == (e.type in ("eave", "rake", "flat_edge")) for e in r.edges)
