"""One roof, one set of totals (contract 0.6 keys): every total is the sum of its drawn facets, edges and objects, recomputed here independently.

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
from roof_measure.model import TOTALS_KEYS

SQM = 10.763910416709722  # square feet per square metre
FT = 1 / 0.3048
AREA_TOL = 0.5  # sq ft
LEN_TOL = 0.05  # ft



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
    t = roof_totals([a, b], edges, set())
    assert tuple(t) == TOTALS_KEYS
    surface = 100.0 * SQM * math.sqrt(1.25)  # 100 m2 of plan at 6/12
    assert t["area_sqft"] == pytest.approx(surface, abs=AREA_TOL)
    assert t["area_sqft_roof_edge"] == t["area_sqft"] and t["roofing_pitched_sqft"] == pytest.approx(surface, abs=AREA_TOL)
    assert t["roofing_flat_sqft"] == 0 and t["squares"] == pytest.approx(surface / 100, abs=0.005)
    assert t["planes_pitch_weighted"] == 6.0 and t["plane_count"] == 2
    assert t["ridge_ft"] == pytest.approx(10 * FT, abs=LEN_TOL) and t["eave_ft"] == pytest.approx(20 * FT, abs=LEN_TOL)
    assert t["rake_ft"] == pytest.approx(4 * rake * FT, abs=LEN_TOL)
    assert t["eave_rake_ft"] == pytest.approx((20 + 4 * rake) * FT, abs=LEN_TOL)  # nothing exposed
    assert t["ridge_hip_ft"] == pytest.approx(10 * FT, abs=LEN_TOL)
    for k in ("hip_ft", "valley_ft", "flat_edge_ft", "level_change_ft", "step_flashing_ft", "wall_flashing_ft", "transition_ft",
              "exposed_edge_ft", "chimney_count", "chimney_perimeter_ft", "lantern_count", "low_slope_confirm_sqft"):
        assert t[k] == 0, k


# ----------------------------------------------------------------------------- a pitched wing beside a flat deck
def test_pitched_and_flat_split_and_the_edges_that_count_toward_no_total():
    pitched = facet("p", box(0, 0, 6, 10), 6.0, "pitched")  # 60 m2 plan
    flat1, flat2 = facet("d1", box(6, 0, 10, 5), 0.0, "flat"), facet("d2", box(6, 5, 10, 10), 0.0, "flat")  # 20 + 20 m2
    edges = [edge("transition", 10.0, ("p", "d1")), edge("flat_seam", 4.0, ("d1", "d2")),  # the seam is in no total
             edge("ridge", 4.0, ("d1", "d2")), edge("ridge", 6.0, ("p",)),
             edge("flat_edge", 4.0, ("d1",)), edge("flat_edge", 4.0, ("d2",)), edge("eave", 6.0, ("p",)),
             edge("level_change", 3.0, ("d1", "d2")), edge("step_flashing", 2.0, ("p", "d2")),
             edge("wall_flashing", 1.5, ("p", "d1"))]
    t = roof_totals([pitched, flat1, flat2], edges, {"d1"})
    pitched_sqft, flat_sqft = 60 * SQM * math.sqrt(1.25), 40 * SQM
    assert t["roofing_pitched_sqft"] == pytest.approx(pitched_sqft, abs=0.1) and t["roofing_flat_sqft"] == pytest.approx(flat_sqft, abs=0.1)
    assert t["area_sqft"] == pytest.approx(pitched_sqft + flat_sqft, abs=0.1)  # the sum of the two rounded parts
    assert t["low_slope_confirm_sqft"] == pytest.approx(20 * SQM, abs=0.1)  # d1 only
    assert t["transition_ft"] == pytest.approx(10 * FT, abs=LEN_TOL)
    assert t["ridge_ft"] == pytest.approx(10 * FT, abs=LEN_TOL) and t["ridge_hip_ft"] == t["ridge_ft"]  # the plain sum
    assert t["flat_edge_ft"] == pytest.approx(8 * FT, abs=LEN_TOL) and t["level_change_ft"] == pytest.approx(3 * FT, abs=LEN_TOL)
    assert t["step_flashing_ft"] == pytest.approx(2 * FT, abs=LEN_TOL) and t["wall_flashing_ft"] == pytest.approx(1.5 * FT, abs=LEN_TOL)
    assert t["exposed_edge_ft"] == pytest.approx(3.5 * FT, abs=LEN_TOL)  # the two step types
    assert t["eave_rake_ft"] == pytest.approx((6 + 0 + 8 + 3.5) * FT, abs=LEN_TOL)  # eave + rake + flat_edge + exposed
    assert t["planes_pitch_weighted"] == 6.0  # the flat facets do not pull it down


# ----------------------------------------------------------------------------- objects: a lantern and a chimney
def test_a_lantern_and_a_chimney_add_their_perimeters_by_kind():
    a = facet("f1", box(0, 0, 10, 10), 6.0, "pitched")
    objs = [{"kind": "chimney", "size_ft": [4.0, 3.0]}, {"kind": "chimney", "size_ft": [2.5, 2.0]},
            {"kind": "lantern", "size_ft": [6.0, 5.0]}, {"kind": "unknown", "size_ft": [9.0, 9.0]}]
    t = roof_totals([a], [edge("eave", 10.0, ("f1",)), edge("ridge", 10.0, ("f1",))], set(), objs)
    assert t["chimney_count"] == 2 and t["lantern_count"] == 1  # an unknown object is counted nowhere
    assert t["chimney_perimeter_ft"] == pytest.approx(2 * (4 + 3) + 2 * (2.5 + 2), abs=LEN_TOL)
    assert t["exposed_edge_ft"] == pytest.approx(2 * (6 + 5), abs=LEN_TOL)  # the sides of the lantern only
    assert t["eave_rake_ft"] == pytest.approx(10 * FT + 22, abs=LEN_TOL)
    assert t["ridge_hip_ft"] == pytest.approx(10 * FT, abs=LEN_TOL)  # a lantern's hips are glass: not added


def test_the_removed_keys_are_not_written():
    removed = {"planes_surface_area_sqft", "area_sqft_wall_line", "squares_wall_line", "outline_perimeter_ft",
               "outline_perimeter_wall_ft", "overhang_ft_median", "roof_edge_perimeter_geom_ft", "drip_edge_eave_ft",
               "drip_edge_eave_rake_ft", "ridge_cap_ridge_ft", "ridge_cap_ridge_hip_ft", "predominant_pitch",
               "roofing_pitched_squares", "roofing_flat_squares", "area_sqft_measured_edge", "squares_measured_edge",
               "perimeter_measured_edge_ft", "pitched_area_sqft", "flat_area_sqft", "facet_count", "lengths_ft", "complexity",
               "high_edge_ft"}
    t = roof_totals([facet("f1", box(0, 0, 5, 5), 6.0, "pitched")], [], set())
    assert not removed & set(t) and set(t) == set(TOTALS_KEYS)


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
        assert tuple(t) == TOTALS_KEYS, name
        area = sum(f.polygon.area * SQM * math.sqrt(1 + (f.pitch_rise / 12) ** 2) for f in res.facets)
        flat = sum(f.polygon.area * SQM * math.sqrt(1 + (f.pitch_rise / 12) ** 2) for f in res.facets if f.roof_type == "flat")
        assert t["area_sqft"] == pytest.approx(area, abs=AREA_TOL) and t["area_sqft_roof_edge"] == t["area_sqft"], name
        assert t["squares"] * 100 == pytest.approx(area, abs=AREA_TOL), name
        assert t["roofing_flat_sqft"] == pytest.approx(flat, abs=AREA_TOL), name
        assert t["roofing_pitched_sqft"] == pytest.approx(area - flat, abs=AREA_TOL), name
        assert t["roofing_pitched_sqft"] + t["roofing_flat_sqft"] == pytest.approx(t["area_sqft"], abs=0.11), name
        assert t["plane_count"] == len(res.facets), name
        by_type: dict[str, float] = {}
        for e in res.edges:
            if e.type != "flat_seam":
                by_type[e.type] = by_type.get(e.type, 0.0) + e.length_ft
        for kind in ("eave", "rake", "flat_edge", "ridge", "hip", "valley", "step_flashing", "wall_flashing", "transition",
                     "level_change"):
            assert t[f"{kind}_ft"] == pytest.approx(by_type.get(kind, 0.0), abs=LEN_TOL), (name, kind)
        assert set(by_type) <= {"eave", "rake", "flat_edge", "ridge", "hip", "valley", "step_flashing", "wall_flashing",
                                "transition", "level_change"}, name
        lanterns = sum(2 * (o["size_ft"][0] + o["size_ft"][1]) for o in res.objects if o["kind"] == "lantern")
        exposed = by_type.get("step_flashing", 0.0) + by_type.get("wall_flashing", 0.0) + lanterns
        assert t["exposed_edge_ft"] == pytest.approx(exposed, abs=LEN_TOL), name
        assert t["eave_rake_ft"] == pytest.approx(sum(by_type.get(k, 0.0) for k in ("eave", "rake", "flat_edge")) + exposed,
                                                  abs=LEN_TOL), name
        assert t["ridge_hip_ft"] == pytest.approx(by_type.get("ridge", 0.0) + by_type.get("hip", 0.0), abs=LEN_TOL), name
        assert t["chimney_count"] == sum(o["kind"] == "chimney" for o in res.objects), name
        assert t["lantern_count"] == sum(o["kind"] == "lantern" for o in res.objects), name
        assert t["chimney_perimeter_ft"] == pytest.approx(
            sum(2 * (o["size_ft"][0] + o["size_ft"][1]) for o in res.objects if o["kind"] == "chimney"), abs=LEN_TOL), name
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
