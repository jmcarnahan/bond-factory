"""Pending tests for review rev-e1 (N1, S1, S3, S5). Copy into F/services/roof_measure/tests/ after the unfreeze."""

import numpy as np
import pytest
from shapely.geometry import box

from roof_measure.engine import measure_roof
from roof_measure.engine.cleanup import clean_facets
from roof_measure.engine.errors import Ctx
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.params import DEFAULT


@pytest.mark.parametrize("gap", [0.021, 0.025, 0.029])
def test_a_sliver_next_to_a_facet_with_a_small_gap_does_not_crash(gap):
    """N1: a sliver and its neighbour 2-3 cm apart union to a MultiPolygon; _exact(...).exterior used to raise."""
    items = [[0, box(0, 0, 10, 8)], [1, box(10 + gap, 0, 10.4 + gap, 8)]]  # the second is a 0.4 m wide sliver
    out = clean_facets(items, box(-1, -1, 12, 9), Ctx(DEFAULT, None))
    assert out and all(g.geom_type == "Polygon" and g.is_valid for _, g in out)


def test_the_params_hash_does_not_depend_on_int_versus_float():
    """S1: 1 and 1.0 are the same parameter."""
    assert DEFAULT.replace(overhang_scale=1).stable_hash() == DEFAULT.replace(overhang_scale=1.0).stable_hash()


@pytest.mark.parametrize("field,value", [("overhang_scale", float("nan")), ("density_refuse", -1.0), ("knn_k", 0)])
def test_nonsense_params_are_rejected(field, value):
    with pytest.raises(ValueError):
        DEFAULT.replace(**{field: value})


def test_a_failed_priced_clip_is_reported_not_good(monkeypatch):
    """S3: a result that prices the drawn area must say so (reason priced_fallback) and must not be labelled ok."""
    from roof_measure.engine import priced
    from roof_measure.engine.synth_points import gable

    def boom(*a, **k):
        raise RuntimeError("clip failed")

    monkeypatch.setattr(priced, "scaled_outline", boom)
    roof = gable()
    pts = __import__("roof_measure.engine.synth_points", fromlist=["simulate"]).simulate(roof, density=8, seed=1)
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res = measure_roof(rp, wall, outline_source="county", parcel_match="given", context=pts)
    assert "priced_fallback" in res.quality.reasons and res.quality.verdict != "ok"


def test_a_wrong_shaped_context_is_ignored_not_crashing():
    """S5: context must be (m, 4); anything else is dropped."""
    from roof_measure.engine.synth_points import gable, simulate

    roof = gable()
    pts = simulate(roof, density=8, seed=1)
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res = measure_roof(rp, wall, outline_source="county", parcel_match="given", context=np.zeros((5, 2)))
    assert res.facets
