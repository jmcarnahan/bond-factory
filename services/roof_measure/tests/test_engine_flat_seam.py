"""The flat/flat seam rule (0.5.1): two flat facets are separated by a ``level_change`` only when their FITTED planes are at
least 0.3 m apart at 70% of the stations along the seam (``jump_ft`` is the median offset); otherwise the seam is a
``flat_seam``: drawn, never priced, in no total. Synthetic data only."""

from __future__ import annotations

import numpy as np
import pytest
from test_engine_edges import CTX, M2FT, facet, points_on

from roof_measure.engine import measure_roof, synth_points
from roof_measure.engine.edge_measure import seam_is_level, seam_offsets
from roof_measure.engine.edges import build_edges, totals_of
from roof_measure.engine.load import roof_points_from_arrays

LEFT = [(0, 0), (20, 0), (20, 5), (0, 5)]  # a 20 m long seam at y = 5 between two flat decks
RIGHT = [(0, 5), (20, 5), (20, 10), (0, 10)]


def two_decks(upper_plane, lower_plane=(0.0, 0.0, 3.0), upper_pts=None, lower_pts=None, noise=0.0, seed=1):
    """Two flat facets (``upper_plane`` on the far side of the seam) and points that lie on their planes unless
    ``upper_pts`` / ``lower_pts`` name other planes (the points then disagree with the fitted planes)."""
    a, b = facet("f1", LEFT, lower_plane), facet("f2", RIGHT, upper_plane)
    assert a.roof_type == "flat" and b.roof_type == "flat"
    pa = facet("p1", LEFT, lower_pts or lower_plane)
    pb = facet("p2", RIGHT, upper_pts or upper_plane)
    q = np.vstack([points_on(pa, 1600, 1), points_on(pb, 1600, 2)])
    if noise:
        q = q + np.random.default_rng(seed).normal(0, noise, q.shape) * [0, 0, 1]
    return [a, b], q


def seam_edges(facets, q):
    return [e for e in build_edges(facets, q, CTX) if len(e.facets) == 2]


def seam_types(facets, q):
    return [e.type for e in seam_edges(facets, q)]


def test_a_constant_five_foot_step_stays_a_level_change_with_the_plane_offset_as_its_jump():
    facets, q = two_decks((0.0, 0.0, 3.0 + 1.5))
    edges = seam_edges(facets, q)
    assert [e.type for e in edges] == ["level_change"]
    assert edges[0].jump_ft == pytest.approx(1.5 * M2FT, abs=0.05)


def test_a_seven_foot_step_with_a_little_noise_stays_a_level_change():
    facets, q = two_decks((0.0, 0.0, 3.0 + 2.26), noise=0.03, seed=3)
    edges = seam_edges(facets, q)
    assert [e.type for e in edges] == ["level_change"]
    assert edges[0].jump_ft == pytest.approx(2.26 * M2FT, abs=0.1)


def test_a_five_foot_step_between_tilted_flat_decks_with_noisy_points_stays_a_level_change():
    # both decks tilt (under 2/12): the planes are 1.0 m apart at one end of the seam and 3.0 m at the other
    facets, q = two_decks((0.05, 0.0, 3.0 + 1.0), (-0.05, 0.0, 3.0), noise=0.08, seed=5)
    assert seam_types(facets, q) == ["level_change"]


def test_a_three_and_a_half_metre_step_with_very_noisy_edge_returns_is_a_level_change():
    # the sampled jump swings (0.6 to 2.7 m on real roofs) but the fitted planes are 3.5 m apart everywhere
    facets, q = two_decks((0.0, 0.0, 3.0 + 3.5), noise=0.5, seed=9)
    assert seam_types(facets, q) == ["level_change"]


def test_a_constant_two_foot_parapet_like_step_with_a_tight_spread_stays_a_level_change():
    facets, q = two_decks((0.0, 0.0, 3.0 + 0.6), noise=0.02, seed=6)
    assert seam_types(facets, q) == ["level_change"]


def test_a_sloped_lower_deck_cut_in_pieces_is_no_step_even_when_the_points_beside_the_seam_are_far_off_their_planes():
    # the fitted planes meet at the seam (y = 5); the points beside it lie 0.6 m over their facet's plane: roughness (a return
    # that far off its own plane is not measured), not a step. Before slice B the jump (0.6 m) was measured and the seam drawn as
    # a flat_seam; now nothing is measured there and the two pieces of one deck share no line (``mergeable``).
    facets, q = two_decks((0.0, 0.03, 3.0 - 0.15), (0.0, 0.0, 3.0), upper_pts=(0.0, 0.03, 3.0 + 0.45))
    types = seam_types(facets, q)
    assert types == [], types


def test_planes_that_are_apart_on_under_70_percent_of_the_seam_make_a_flat_seam():
    # offset 0.02 m per metre along the seam: at least 0.3 m only for x >= 15 (25% of the stations)
    facets, q = two_decks((0.02, 0.0, 3.0), upper_pts=(0.0, 0.0, 3.5))
    assert seam_types(facets, q) == ["flat_seam"]


def test_a_flat_seam_is_in_no_total():
    facets, q = two_decks((0.02, 0.0, 3.0), upper_pts=(0.0, 0.0, 3.5))
    edges = build_edges(facets, q, CTX)
    assert any(e.type == "flat_seam" and e.jump_ft is None for e in edges)
    lengths = totals_of(facets, edges)["lengths_ft"]
    assert "flat_seam" not in lengths and lengths["level_change"] == 0.0


def test_the_stations_are_at_least_twelve_and_never_more_than_half_a_metre_apart():
    a, b = facet("f1", LEFT, (0, 0, 3.0)), facet("f2", RIGHT, (0, 0, 4.0))
    assert len(seam_offsets(a, b, np.array([0.0, 5.0]), np.array([4.0, 5.0]))) == 12
    assert len(seam_offsets(a, b, np.array([0.0, 5.0]), np.array([20.0, 5.0]))) == 41
    assert len(seam_offsets(a, b, np.array([0.0, 5.0]), np.array([0.8, 5.0]))) == 12
    level, med = seam_is_level(a, b, np.array([0.0, 5.0]), np.array([20.0, 5.0]))
    assert level and med == pytest.approx(1.0)


@pytest.mark.parametrize("make,name", [(synth_points.flat_two_level, "flat_two_level"), (synth_points.flat_step, "flat_step")])
def test_the_synthetic_flat_twins_have_exactly_one_real_level_change(make, name):
    roof = make()
    case = synth_points.SynthCase(name, roof, {"density": 8, "seed": 1})
    pts = case.points()
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res = measure_roof(rp, wall, outline_source="county", parcel_match="given", context=pts)
    types = [e.type for e in res.edges if len(e.facets) == 2]
    assert types.count("level_change") == 1 and "flat_seam" not in types
    assert res.quality.flat_share == pytest.approx(1.0)
    assert res.totals["level_change_ft"] > 0
    assert all(f.roof_type == "flat" for f in res.facets)


def test_flat_share_is_the_flat_part_of_the_priced_area():
    from engine_cases import run

    assert run("flat_d8").quality.flat_share == pytest.approx(1.0)
    assert run("gable_d8").quality.flat_share == pytest.approx(0.0)
    mixed = run("flat_pitched_d8")
    flat, pitched = mixed.totals["roofing_flat_sqft"], mixed.totals["roofing_pitched_sqft"]
    assert 0.1 < mixed.quality.flat_share < 0.9
    assert mixed.quality.flat_share == pytest.approx(flat / (flat + pitched), abs=1e-12)  # from the priced totals
    assert "flat_share" in mixed.quality.to_dict()
    assert mixed.quality.flat_share == flat / (flat + pitched)  # UNROUNDED (round(0.8996, 3) would read 0.9)


def test_a_model_with_a_flat_seam_validates_and_keeps_it_out_of_the_totals():
    from roof_measure.blockset import BlockSet
    from roof_measure.engine.adapter import engine_model

    roof = synth_points.flat_two_level()
    pts = synth_points.SynthCase("x", roof, {"density": 8, "seed": 1}).points()
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res = measure_roof(rp, wall, outline_source="county", parcel_match="given", context=pts)
    # turn the step into a flat seam by hand: the model must still validate and the totals must not count it
    for e in res.edges:
        if e.type == "level_change":
            e.type = "flat_seam"
            e.jump_ft = None
    base = BlockSet(address={"formatted": "x"}, origin={"lat": 0.0, "lng": 0.0}, frame={}, footprint_ft=[],
                    footprint_meta={"provider": "county", "id": "x", "area_sqft": 1000.0})
    model = engine_model(res, base, float(rp.ground_z))
    assert any(e["type"] == "flat_seam" and "jump_ft" not in e for e in model["edges"])
    assert model["debug"]["edge_diagnostics"]["seam_points_only"] == 1
    assert "flat_seam" not in model["totals"]["lengths_ft"]
    assert model["totals"]["lengths_ft"]["level_change"] == 0.0


SEAM0, SEAM1 = np.array([0.0, 5.0]), np.array([20.0, 5.0])  # 41 stations, x = 0, 0.5, ... 20


@pytest.mark.parametrize("plane_b,level,median", [
    ((0.0, 0.0, 3.29), False, 0.29),
    ((0.0, 0.0, 3.30), True, 0.30),
    ((0.0, 0.0, 3.31), True, 0.31),
    ((0.04, 0.0, 3.07), True, None),   # offset >= 0.3 m on exactly 29 of 41 stations (0.707 >= 0.70)
    ((0.04, 0.0, 3.05), False, None),  # on exactly 28 of 41 (0.683 < 0.70)
])
def test_the_thresholds_hold_at_the_line(plane_b, level, median):
    a, b = facet("f1", LEFT, (0.0, 0.0, 3.0)), facet("f2", RIGHT, plane_b)
    got, med = seam_is_level(a, b, SEAM0, SEAM1)
    assert got is level
    if median is not None:
        assert med == pytest.approx(median, abs=1e-6)


def test_the_typer_applies_the_line_to_real_chains():
    for gap, kind in ((0.29, "flat_seam"), (0.31, "level_change")):
        facets, q = two_decks((0.0, 0.0, 3.0 + gap), upper_pts=(0.0, 0.0, 3.5))  # the points show 0.5 m either way
        assert seam_types(facets, q) == [kind], gap


def test_a_non_finite_plane_never_gives_a_nan_jump():
    a, b = facet("f1", LEFT, (0.0, 0.0, 3.0)), facet("f2", RIGHT, (0.0, 0.0, 4.0))
    bad = b.__class__(**{**b.__dict__, "plane": (0.0, 0.0, float("nan"))})
    assert seam_is_level(a, bad, SEAM0, SEAM1) == (False, 0.0)
    assert seam_is_level(a, b, SEAM0, SEAM1)[1] == pytest.approx(1.0)


def test_the_priced_pass_repeats_the_drawn_verdict_on_a_ramping_offset():
    # plane offset 0.6 m at x = 0 falling to 0 at x = 28.4 (>= 0.3 m up to x = 14.2: 71% of a 20 m seam)
    upper = (-0.6 / 28.4, 0.0, 3.0 + 0.6)

    def decks(x0):
        a = facet("f1", [(x0, 0), (20, 0), (20, 5), (x0, 5)], (0.0, 0.0, 3.0))
        b = facet("f2", [(x0, 5), (20, 5), (20, 10), (x0, 10)], upper)
        return [a, b]

    drawn = decks(0.0)
    q = np.vstack([points_on(facet("p1", LEFT, (0, 0, 3.0)), 1600, 1), points_on(facet("p2", RIGHT, (0, 0, 3.5)), 1600, 2)])
    ctx = type(CTX)(CTX.p)
    assert [e.type for e in build_edges(drawn, q, ctx) if len(e.facets) == 2] == ["level_change"]
    clipped = decks(3.0)  # the priced clip loses the high-offset end: 66% of its stations are >= 0.3 m
    alone = [e.type for e in build_edges(clipped, q, type(CTX)(CTX.p)) if len(e.facets) == 2]
    assert alone == ["flat_seam"]  # judged afresh it would differ ...
    again = [e.type for e in build_edges(clipped, q, ctx, reuse_verdicts=True) if len(e.facets) == 2]
    assert again == ["level_change"]  # ... the priced pass re-uses the drawn verdict
