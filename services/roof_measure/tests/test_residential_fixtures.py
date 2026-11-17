"""Ordinary invented houses (an adopter's dev mock needs roofs that score good) and one honest limitation."""

from __future__ import annotations

import pytest
from quality_helpers import HERE

from roof_measure.library import measure

pytestmark = pytest.mark.usefixtures("no_planes_model")  # these tests pin the block model, see conftest

FIX = HERE / "fixtures"


def envelope(tmp_path, name):
    return measure("", lat=1.0, lng=1.0, method="lidar_skeleton", verify=False, isolate=False,
                   cache_dir=tmp_path / "c", blocks_path=FIX / f"{name}_blocks.json")


@pytest.mark.parametrize("name, planes, facets", [("simple_hip_house", 4, 4), ("plain_gable_house", 2, 2)])
def test_a_plain_house_scores_good(tmp_path, name, planes, facets):
    q = envelope(tmp_path, name)["model"]["quality"]
    assert q["planes_lidar"] == planes and q["facets_model"] == facets
    assert q["plane_mismatch_pct"] < 10.0 and q["outline_covered_pct"] > 90.0 and q["reasons"] == []


def test_the_hip_house_model_matches_its_planes_in_area_and_pitch(tmp_path):
    e = envelope(tmp_path, "simple_hip_house")
    assert e["totals"]["area_sqft"] == pytest.approx(e["totals"]["planes_surface_area_sqft"], rel=0.01)
    assert e["totals"]["predominant_pitch"] == 5.0 and e["totals"]["planes_pitch_weighted"] == 5.0


def test_known_limitation_a_gable_house_with_a_lower_attached_gable_is_merged_into_one_block(tmp_path):
    """Pins today's rule behaviour (see the CHANGELOG): two connected gables on different levels (6/12 and 4/12) are
    fitted as ONE gable block at the weighted pitch, so the model has 2 facets for 4 planes, the wrong extent (the
    attached bay is not drawn) and a mismatch on the lower planes. Not good, and the metric only sees pitch and
    direction, not the lost extent. Revisit this test when the rules separate levels."""
    e = envelope(tmp_path, "simple_gable_house")
    q = e["model"]["quality"]
    assert q["planes_lidar"] == 4 and q["facets_model"] == 2
    assert 10.0 < q["plane_mismatch_pct"] < 20.0 and q["outline_covered_pct"] > 90.0
    assert [b["form"] for b in e["model"]["blocks"]] == ["gable"]
    assert 4.0 < e["model"]["blocks"][0]["pitch_rise"] < 6.0
    assert e["totals"]["area_sqft"] < 0.95 * e["totals"]["planes_surface_area_sqft"]


def _extent(tmp_path, name):
    q = envelope(tmp_path, name)["model"]["quality"]
    return q["model_uncovered_pct"], q["level_spread_ft"], q["reasons"]


@pytest.mark.parametrize("name", ["simple_hip_house", "plain_gable_house"])
def test_a_plain_house_loses_no_extent(tmp_path, name):
    uncovered, spread, reasons = _extent(tmp_path, name)
    assert uncovered < 3.0 and spread == 0.0 and "model_misses_roof_area" not in reasons


def test_the_attached_bay_that_the_model_does_not_draw_is_measured(tmp_path):
    """The model block (one rectangle) leaves 18.8% of the plane area outside it, on two levels 5 ft apart."""
    uncovered, spread, reasons = _extent(tmp_path, "simple_gable_house")
    assert uncovered >= 5.0 and uncovered == pytest.approx(18.8, abs=0.3) and spread == pytest.approx(5.0, abs=0.1)
    assert reasons == ["model_misses_roof_area"]


def test_extent_values_of_the_other_fixtures_are_pinned(tmp_path):
    from quality_helpers import SITE1, SITE1_HANDMADE, TWO_LEVEL

    for path, uncovered, spread in [(TWO_LEVEL, 26.1, 4.5), (SITE1, 5.3, 9.3), (SITE1_HANDMADE, 0.0, 0.3)]:
        q = measure("", lat=1.0, lng=1.0, method="lidar_skeleton", verify=False, isolate=False,
                    cache_dir=tmp_path / "c", blocks_path=path)["model"]["quality"]
        assert q["model_uncovered_pct"] == pytest.approx(uncovered, abs=0.3), path.name
        assert q["level_spread_ft"] == pytest.approx(spread, abs=0.2), path.name
