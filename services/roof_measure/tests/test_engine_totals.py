"""One roof, one set of totals: every total is the sum of its drawn facets and edges, recomputed here independently.

Two hand-built roofs (exact numbers from their geometry) and every synthetic roof of ``synth_points.cases()`` run through
the engine. Synthetic data only."""

from __future__ import annotations

import math

import pytest
from shapely.geometry import box

from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.measure import measure_stages
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.synth_points import cases
from roof_measure.engine.totals import roof_totals
from roof_measure.engine.types import Edge, Facet

SQM = 10.763910416709722  # square feet per square metre
FT = 1 / 0.3048
AREA_TOL = 0.5  # sq ft
LEN_TOL = 0.05  # ft
OUTER = ("eave", "rake", "flat_edge")


def facet(fid: str, poly, rise: float, roof_type: str) -> Facet:
    plan = poly.area * SQM
    return Facet(id=fid, polygon=poly, plane=(0.0, 0.0, 3.0), label=0, pitch_rise=rise, aspect_deg=0.0, roof_type=roof_type,
                 plan_area_sqft=plan, area_sqft=plan * math.sqrt(1 + (rise / 12) ** 2), points=10, rms_m=0.0)


def edge(kind: str, metres: float, facets: tuple[str, ...], high_edge: bool = False) -> Edge:
    return Edge(kind, (0, 0, 0), (metres, 0, 0), metres * FT, facets, high_edge=high_edge)


# ----------------------------------------------------------------------------- a hand-built gable: 2 x 5 m by 10 m, 6/12
def test_a_hand_built_gable_has_the_totals_its_geometry_gives():
    a, b = facet("f1", box(0, 0, 5, 10), 6.0, "pitched"), facet("f2", box(5, 0, 10, 10), 6.0, "pitched")
    rake = math.hypot(5.0, 2.5)  # a rake edge runs along the slope: 5 m of run, 2.5 m of rise
    edges = [edge("ridge", 10.0, ("f1", "f2")), edge("eave", 10.0, ("f1",)), edge("eave", 10.0, ("f2",)),
             *[edge("rake", rake, (f,)) for f in ("f1", "f1", "f2", "f2")]]
    t = roof_totals([a, b], edges, set(), DEFAULT)
    surface = 100.0 * SQM * math.sqrt(1.25)  # 100 m2 of plan at 6/12
    assert t["area_sqft"] == pytest.approx(surface, abs=AREA_TOL)
    for twin in ("planes_surface_area_sqft", "area_sqft_roof_edge", "area_sqft_measured_edge", "roofing_pitched_sqft",
                 "pitched_area_sqft"):
        assert t[twin] == pytest.approx(surface, abs=AREA_TOL), twin
    assert t["roofing_flat_sqft"] == 0 and t["flat_area_sqft"] == 0 and t["squares"] == pytest.approx(surface / 100, abs=0.005)
    assert t["planes_pitch_weighted"] == 6.0 and t["predominant_pitch"] == 6.0
    assert t["lengths_ft"]["ridge"] == pytest.approx(10 * FT, abs=LEN_TOL)
    assert t["lengths_ft"]["eave"] == pytest.approx(20 * FT, abs=LEN_TOL)
    assert t["lengths_ft"]["rake"] == pytest.approx(4 * rake * FT, abs=LEN_TOL)
    perimeter = (20 + 4 * rake) * FT
    assert t["outline_perimeter_ft"] == pytest.approx(perimeter, abs=LEN_TOL)
    assert t["perimeter_measured_edge_ft"] == t["outline_perimeter_ft"]
    assert t["ridge_cap_ridge_hip_ft"] == pytest.approx(10 * FT, abs=LEN_TOL)
    assert t["flat_edge_ft"] == 0 and t["level_change_ft"] == 0 and t["high_edge_ft"] == 0
    assert t["complexity"] == {"facets": 2, "hip_valley_ft_per_square": 0.0, "hint": "simple"}


# ----------------------------------------------------------------------------- a pitched wing beside a flat deck
def test_pitched_and_flat_split_and_the_edges_that_count_toward_no_total():
    pitched = facet("p", box(0, 0, 6, 10), 6.0, "pitched")  # 60 m2 plan
    flat1, flat2 = facet("d1", box(6, 0, 10, 5), 0.0, "flat"), facet("d2", box(6, 5, 10, 10), 0.0, "flat")  # 20 + 20 m2
    edges = [edge("transition", 10.0, ("p", "d1")), edge("flat_seam", 4.0, ("d1", "d2")),  # the seam is in no total
             edge("ridge", 4.0, ("d1", "d2")),  # a crease between two low-slope facets takes no cap
             edge("ridge", 6.0, ("p",)),  # a ridge of one facet: the high edge, kept
             edge("flat_edge", 4.0, ("d1",)), edge("flat_edge", 4.0, ("d2",)), edge("eave", 6.0, ("p",)),
             edge("level_change", 3.0, ("d1", "d2"))]
    t = roof_totals([pitched, flat1, flat2], edges, {"d1"}, DEFAULT)
    pitched_sqft, flat_sqft = 60 * SQM * math.sqrt(1.25), 40 * SQM
    assert t["roofing_pitched_sqft"] == pytest.approx(pitched_sqft, abs=0.1) and t["roofing_flat_sqft"] == pytest.approx(flat_sqft, abs=0.1)
    assert t["area_sqft"] == pytest.approx(pitched_sqft + flat_sqft, abs=0.1)  # the sum of the two rounded parts
    assert t["low_slope_confirm_sqft"] == pytest.approx(20 * SQM, abs=0.1)  # d1 only
    assert "flat_seam" not in t["lengths_ft"]
    assert t["lengths_ft"]["transition"] == pytest.approx(10 * FT, abs=LEN_TOL)
    assert t["lengths_ft"]["ridge"] == pytest.approx(10 * FT, abs=LEN_TOL)  # both ridge edges are lengths ...
    assert t["ridge_cap_ridge_hip_ft"] == pytest.approx(6 * FT, abs=LEN_TOL)  # ... the flat/flat one takes no cap
    assert t["outline_perimeter_ft"] == pytest.approx((4 + 4 + 6) * FT, abs=LEN_TOL)  # two flat edges and the eave
    assert t["flat_edge_ft"] == pytest.approx(8 * FT, abs=LEN_TOL) and t["level_change_ft"] == pytest.approx(3 * FT, abs=LEN_TOL)
    assert t["planes_pitch_weighted"] == 6.0  # the flat facets do not pull it down


# ----------------------------------------------------------------------------- every synthetic roof
@pytest.fixture(scope="module")
def measured():
    out = {}
    for c in cases():
        pts = c.points()
        wall = c.roof.wall_polygon()
        rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
        res, _ = measure_stages(rp, wall, params=DEFAULT, deadline=None, outline_source="county", parcel_match="given", context=pts)
        out[c.name] = (c, res)
    return out


def test_every_total_is_the_sum_of_its_drawn_facets_and_edges_on_every_synthetic_roof(measured):
    checked = 0
    for name, (_c, res) in measured.items():
        if res.refused:
            continue
        checked += 1
        t = res.totals
        area = sum(f.polygon.area * SQM * math.sqrt(1 + (f.pitch_rise / 12) ** 2) for f in res.facets)
        flat = sum(f.polygon.area * SQM * math.sqrt(1 + (f.pitch_rise / 12) ** 2) for f in res.facets if f.roof_type == "flat")
        for k in ("area_sqft", "planes_surface_area_sqft", "area_sqft_roof_edge", "area_sqft_measured_edge"):
            assert t[k] == pytest.approx(area, abs=AREA_TOL), (name, k)
        assert t["squares"] * 100 == pytest.approx(area, abs=AREA_TOL), name
        assert t["roofing_flat_sqft"] == pytest.approx(flat, abs=AREA_TOL), name
        assert t["roofing_pitched_sqft"] == pytest.approx(area - flat, abs=AREA_TOL), name
        assert t["roofing_pitched_sqft"] + t["roofing_flat_sqft"] == pytest.approx(t["area_sqft"], abs=0.11), name
        by_type: dict[str, float] = {}
        for e in res.edges:
            if e.type != "flat_seam":
                by_type[e.type] = by_type.get(e.type, 0.0) + e.length_ft
        for kind, got in t["lengths_ft"].items():
            assert got == pytest.approx(by_type.get(kind, 0.0), abs=LEN_TOL), (name, kind)
        assert set(by_type) <= set(t["lengths_ft"]), name
        perimeter = sum(e.length_ft for e in res.edges if len(e.facets) == 1 and e.type in OUTER)
        assert t["outline_perimeter_ft"] == pytest.approx(perimeter, abs=LEN_TOL), name
        assert t["perimeter_measured_edge_ft"] == t["outline_perimeter_ft"], name
        flat_ids = {f.id for f in res.facets if f.roof_type == "flat"}
        cap = sum(e.length_ft for e in res.edges if e.type in ("ridge", "hip") and not (len(e.facets) == 2 and set(e.facets) <= flat_ids))
        assert t["ridge_cap_ridge_hip_ft"] == pytest.approx(cap, abs=LEN_TOL), name
        assert t["flat_edge_ft"] == pytest.approx(by_type.get("flat_edge", 0.0), abs=LEN_TOL), name
        assert t["level_change_ft"] == pytest.approx(by_type.get("level_change", 0.0), abs=LEN_TOL), name
        assert t["facet_count"] == len(res.facets) == t["complexity"]["facets"], name
    assert checked >= 40  # most of the 67 cases are measured; the rest are refused for density or tree cover


def test_the_reported_area_is_within_the_error_the_drawn_roof_always_had(measured):
    """The reported area is the drawn roof's: within 4.5% of the exact surface on every measured synthetic roof (the drawn
    roof's worst case is -3.9%, +4.1%); the clipped roof it replaces was 4.3-9.2% low."""
    worst = 0.0
    for name, (c, res) in measured.items():
        if res.refused:
            continue
        err = res.totals["area_sqft"] / c.roof.totals["area_sqft"] - 1
        worst = max(worst, abs(err))
        assert abs(err) <= 0.045, (name, err)
    assert worst > 0.0
