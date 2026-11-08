"""Closed-form checks of the straight-skeleton port (research values, 35 x 26 ft and 40 x 24 ft)."""

import math

import pytest

from roof_measure.skeleton import (
    block_geometry,
    hip_roof_edges,
    measure,
    rect_fit,
    shed_roof_edges,
    split_footprint,
)

RECT = [(0, 0), (35, 0), (35, 26), (0, 26)]


@pytest.mark.parametrize("rise, hips, area", [(3, 74.68, 938.0), (4, 75.55, 959.2), (5, 76.66, 985.8)])
def test_hip_matches_closed_form(rise, hips, area):
    t = hip_roof_edges(RECT, rise)["totals"]
    assert t["eaves_ft"] == pytest.approx(122.0, abs=0.01)
    assert t["ridges_ft"] == pytest.approx(9.0, abs=0.01)
    assert t["hips_ft"] == pytest.approx(hips, abs=0.01)
    assert t["facet_area_sqft"] == pytest.approx(area, abs=0.1)
    assert t["valleys_ft"] == 0 and t["rakes_ft"] == 0


def test_hip_closed_form_exact():
    rise = 4.0
    s = rise / 12
    plan_hip = math.hypot(13, 13)
    expect_hip = 4 * math.hypot(plan_hip, s * 13)
    t = hip_roof_edges(RECT, rise)["totals"]
    assert t["hips_ft"] == pytest.approx(expect_hip, abs=1e-6)
    assert t["facet_area_sqft"] == pytest.approx(35 * 26 * math.sqrt(1 + s * s), abs=1e-6)


def test_gable_ends_are_rakes():
    t = hip_roof_edges([(0, 0), (40, 0), (40, 24), (0, 24)], 6, gable_edges={1, 3})["totals"]
    sf = math.sqrt(1 + 0.25)
    assert t["eaves_ft"] == pytest.approx(80.0, abs=0.01)
    assert t["ridges_ft"] == pytest.approx(40.0, abs=0.01)
    assert t["rakes_ft"] == pytest.approx(4 * 12 * sf, abs=0.01)
    assert t["facet_area_sqft"] == pytest.approx(40 * 24 * sf, abs=0.1)


def test_clockwise_input_gives_same_totals():
    a = hip_roof_edges(RECT, 4)["totals"]
    b = hip_roof_edges(RECT[::-1], 4)["totals"]
    assert a["hips_ft"] == pytest.approx(b["hips_ft"], abs=1e-6)


def test_shed_edges_by_orientation():
    t = shed_roof_edges([(0, 0), (10, 0), (10, 8), (0, 8)], 4, 180)["totals"]
    assert t["eaves_ft"] == pytest.approx(10.0) and t["ridges_ft"] == pytest.approx(10.0)
    assert t["rakes_ft"] == pytest.approx(2 * 8 * math.sqrt(1 + (4 / 12) ** 2), abs=1e-6)


def test_block_geometry_flat_has_outline_edges():
    g = block_geometry("flat", RECT, 0.0)
    assert len(g["facets"]) == 1 and {e["type"] for e in g["edges"]} == {"outline"}


def test_tools_measure_split_rect():
    m = measure(RECT)
    assert m["area_sqft"] == 910 and [e["outward_bearing_deg"] for e in m["edges"]] == [180, 90, 0, 270]
    parts = split_footprint(RECT, [(10, -5), (10, 30)])
    assert sorted(round(p["area_sqft"]) for p in parts) == [260, 650]
    _, short, long_, area = rect_fit([(0, 0), (35, 1), (35, 26), (0, 26)])
    assert short < long_ and area > 880


def test_repeated_vertices_are_ignored():
    t = hip_roof_edges([(0, 0), (10, 0), (10, 0), (10, 10), (0, 10)], 4)["totals"]
    assert t["facet_area_sqft"] == pytest.approx(100 * math.sqrt(1 + (4 / 12) ** 2), abs=1e-6)
    assert hip_roof_edges([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], 4)["totals"]["eaves_ft"] == pytest.approx(40)
