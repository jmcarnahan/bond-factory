"""The ported label geometry on a synthetic gable: a hand label becomes measured facets, typed edges and a coverage check."""

import json

import pytest
from test_roof_label_spend import make_house

from tools.roof_eval.label import build, make_truth, relax, viz

X0 = 8.0  # make_house puts the 12 x 8 m gable at (8, 8)
LABEL = {
    "vertices": {
        "a": [X0, X0],
        "b": [X0 + 12, X0],
        "c": [X0 + 12, X0 + 4],
        "d": [X0, X0 + 4],
        "e": [X0 + 12, X0 + 8],
        "f": [X0, X0 + 8],
    },
    "facets": [{"id": "f1", "ring": ["a", "b", "c", "d"]}, {"id": "f2", "ring": ["d", "c", "e", "f"]}],
    "confidence": "high",
}


@pytest.fixture(scope="module")
def house(tmp_path_factory):
    return viz.House(make_house(tmp_path_factory.mktemp("w") / "h-00000001"))


def test_facets_edges_and_totals_of_a_gable(house):
    truth, facets, edges, _ = build.build(house, LABEL)
    assert truth["house_id"] == "h-00000001" and "slug" not in truth
    assert [round(f["pitch_rise"]) for f in facets] == [6, 6] and {f["roof_type"] for f in facets} == {
        "pitched"
    }
    assert truth["area_sqft"] == pytest.approx(12 * 8 * 10.7639 * 1.25**0.5, rel=0.03)
    by = {}
    for e in edges:
        by.setdefault(e["type"], []).append(e["length_ft"])
    assert sorted(by) == ["eave", "rake", "ridge"] and len(by["eave"]) == 2 and len(by["rake"]) == 4
    assert by["ridge"][0] == pytest.approx(12 / 0.3048, rel=0.02)
    assert truth["lengths_ft"]["ridge"] == pytest.approx(12 / 0.3048, rel=0.02)


def test_overlay_check_says_the_label_explains_the_returns(house, tmp_path):
    truth, facets, edges, polys = build.build(house, LABEL)
    truth["_vertices"] = LABEL["vertices"]
    paths, stats = build.overlay(house, truth, facets, edges, polys, tmp_path / "o.png", title="t")
    assert len(paths) == 2 and all(p.endswith(".png") for p in paths)
    assert stats["in_facet_within_12cm_pct"] > 95 and stats["in_no_facet_pct"] < 5


def test_finalize_writes_schema_r2_and_restores_the_datum(house):
    truth, *_ = build.build(house, LABEL)
    out = make_truth.finalize(truth, house.z0, "r1")
    assert "level_change" in out["lengths_ft"] and "step" not in out["lengths_ft"] and out["run_tag"] == "r1"
    assert all(f["borderline"] is False for f in out["facets"]) and out["borderline_area_sqft"] == 0
    assert json.dumps(out)  # serialisable


def test_relaxed_fit_reproduces_the_stored_fit(house):
    assert relax.fit(house, LABEL, 0.12) > 95 and relax.fit(house, LABEL, 0.20) >= relax.fit(
        house, LABEL, 0.12
    )


def test_cost_arithmetic():
    u = {"input": 1_000_000, "output": 100_000, "cache_read": 2_000_000, "cache_write": 100_000}
    assert make_truth.cost_of(u) == pytest.approx(8.0 + 4.0 + 0.4 + 1.0)
