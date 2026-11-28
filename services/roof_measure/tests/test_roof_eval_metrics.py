"""Every scorer metric: a correct result passes it and a deliberately wrong one fails it. Synthetic roofs only."""

from pathlib import Path

import numpy as np
import pytest
import roof_eval_helpers as H
from shapely.geometry import Polygon

from tools.roof_eval import m_fit, m_shape, m_truth, price, score
from tools.roof_eval.geom import load_roof

REF = H.gable_points()
FOOT = Polygon(H.footprint())
GOOD = H.gable_result()


def sc(res, truths=(), ref=REF, rules=None):
    return score.score_house(res, ref, FOOT, list(truths), rules)


def M(res, **kw):
    return sc(res, **kw)["m"]


def tru(res, **extra):
    return {**H.truth_for(res, **extra), "tier": "T2"}


def test_perfect_result_scores_clean():
    m = M(GOOD)
    assert m["fit_all"] == 1.0 and m["fit_covered"] == 1.0 and m["coverage"] == 1.0
    assert m["overlap_sqft"] == 0 and m["tiling_gap_sqft"] == pytest.approx(0, abs=1e-6)
    assert m["facets"] == 2 and m["facets_lt_30sqft"] == 0 and m["edges_lt_3ft"] == 0
    assert m["axis_share_7deg"] > 0.45  # rakes run at ~63 deg to the x axis: they are the off-axis share
    assert m["false_level_change_share"] == 0
    assert m["flat_sqft"] == 0


def test_areas_and_lengths_closed_form():
    m = M(GOOD)
    surface = 12 * 8 * 10.7639 * (1 + 0.25) ** 0.5  # plan sqft times sqrt(1 + 0.5^2)
    assert m["area_sqft"] == pytest.approx(surface, rel=1e-3)
    assert m["pitch_weighted"] == pytest.approx(6.0, rel=1e-6)
    assert m["lengths"]["ridge"] == pytest.approx(12 / 0.3048, rel=1e-3)
    assert m["lengths"]["eave"] == pytest.approx(24 / 0.3048, rel=1e-3)
    assert m["lengths"]["rake"] == pytest.approx(4 * (4 ** 2 + 2 ** 2) ** 0.5 / 0.3048, rel=1e-3)
    assert m["perimeter_ft"] == pytest.approx(m["lengths"]["eave"] + m["lengths"]["rake"])
    assert m["ridge_hip_ft"] == pytest.approx(m["lengths"]["ridge"])


def test_one_big_facet_fails_fit_and_iou():
    res = H.one_big_facet(GOOD)
    m = M(res)
    assert m["fit_all"] < 0.4
    iou = m_shape.facet_iou(load_roof(res), H.truth_for(GOOD)["facets"])
    assert iou["mean_iou"] == pytest.approx(0.25, abs=0.01)  # two-sided: 0.5 matched over max(1, 2) facets


def test_shrunken_coverage_fails_coverage_and_fit_all_not_fit_covered():
    m = M(H.shrunk(GOOD, 1.5))
    assert m["coverage"] < 0.6
    assert m["fit_all"] < 0.6
    assert m["fit_covered"] == 1.0  # the covered points still fit: the two metrics differ by design


def test_over_segmentation_fails_facet_count_and_iou():
    res = H.split_four(GOOD)
    m = M(res)
    assert m["facets"] == 8 and m["fit_all"] == 1.0
    iou = m_shape.facet_iou(load_roof(res), H.truth_for(GOOD)["facets"])
    assert iou["mean_iou"] < 0.2
    t = sc(res, [tru(GOOD, facet_count=2)])["truth"]["T2"]
    assert t["facet_count.abs_diff"] == 6


def test_small_facets_and_short_edges_counted():
    res = H.split_four(GOOD)
    res["facets"] += [H.facet("s1", H.rect(14, 0, 14.8, 0.8), (0, 0.5, 3.0)), H.facet("s2", H.rect(11, 7, 12, 8), (0, -0.5, 7.0))]
    m = M(res)
    assert m["facets_lt_30sqft"] == 2 and m["edges_lt_3ft"] >= 4  # edges are recomputed from the facets: a 0.8 m facet has four of 2.6 ft
    assert m["edges_lt_3ft_share"] > 0


def test_ridge_shifted_one_metre_fails_fit_and_iou():
    res = H.ridge_shifted(GOOD, 1.0)
    assert M(res)["fit_all"] < 0.85
    assert m_shape.facet_iou(load_roof(res), H.truth_for(GOOD)["facets"])["mean_iou"] < 0.9
    assert M(res)["coverage"] == 1.0  # shape right, heights wrong: only the fit metric sees it


def test_overlapping_facets_fail_overlap():
    assert M(H.overlapping(GOOD))["overlap_sqft"] == pytest.approx(6 * 2 * 10.7639, rel=1e-3)
    assert M(GOOD)["overlap_sqft"] == 0


def test_tiling_gap_sees_sliver_between_facets():
    res = H.gable_result()
    res["facets"][1]["polygon"] = H.rect(0, 4.15, H.W, H.D)  # a 0.15 m slit along the ridge
    assert M(res)["tiling_gap_sqft"] == pytest.approx(0.15 * 12 * 10.7639, rel=0.02)


def test_swapped_flat_pitched_fails_agreement_and_totals():
    res = H.all_flat(GOOD)
    m = M(res)
    assert m["pitched_sqft"] == 0 and m["flat_sqft"] > 0 and m["pitch_weighted"] is None
    ag = m_shape.flat_pitched_agreement(load_roof(res), H.truth_for(GOOD)["facets"])
    assert ag == 0.0
    assert m_shape.flat_pitched_agreement(load_roof(GOOD), H.truth_for(GOOD)["facets"]) == 1.0


def test_flat_pitched_band_is_indeterminate_not_wrong():
    res = H.gable_result()
    for f in res["facets"]:
        f["plane"][1] = (1.8 / 12) * (1 if f["plane"][1] > 0 else -1)  # 1.8/12: flat by the cut, inside the band
    truth = [{"polygon": f["polygon"], "pitch_rise": 2.2} for f in res["facets"]]
    assert m_shape.flat_pitched_agreement(load_roof(res), truth) == 1.0
    truth = [{"polygon": f["polygon"], "pitch_rise": 6.0} for f in res["facets"]]
    assert m_shape.flat_pitched_agreement(load_roof(res), truth) == 1.0  # result 1.8 is within +-0.5 of 2.0
    for f in res["facets"]:
        f["plane"][1] = (1.0 / 12) * (1 if f["plane"][1] > 0 else -1)
    assert m_shape.flat_pitched_agreement(load_roof(res), truth) == 0.0


def test_false_level_change_flagged_on_continuous_roof_not_on_real_step():
    res = H.with_level_change(GOOD)
    m = M(res)
    assert m["false_level_change_count"] == 1 and m["false_level_change_share"] > 0.05
    # a real 1 m step at x = 6 is not false
    real, pts = H.pitched_step(1.0)
    m = M(real, ref=pts)
    assert m["false_level_change_count"] == 0 and m["level_change_edges"] == 1
    # the same edge on a 0.2 m step is false
    real, pts = H.pitched_step(0.2)
    m = M(real, ref=pts)
    assert m["false_level_change_count"] == 1


def test_level_change_without_points_is_unverified_not_false():
    res = H.gable_result()
    res["edges"].append(H.edge("level_change", (50, 0, 3), (50, 4, 3), ["f1"]))
    m = M(res)
    assert m["level_change_unverified"] == 1 and m["false_level_change_count"] == 0


def test_axis_share_drops_for_skewed_edges():
    res = H.gable_result()
    res["edges"] = [H.edge("ridge", (0, 0, 3), (10, 6, 5), ["f1"]), H.edge("eave", (0, 0, 3), (12, 0, 3), ["f1"])]
    full = m_shape.axis_aligned_share(load_roof(res), FOOT)
    assert full == pytest.approx(12 / (12 + np.hypot(10, 6)), rel=1e-3)


def test_dominant_axes_rectangle():
    a, b = m_shape.dominant_axes(FOOT)
    assert {round(a), round(b)} == {0, 90}


def test_hungarian_unmatched_facets_score_zero_both_sides():
    roof = load_roof(GOOD)
    one = H.truth_for(GOOD)["facets"][:1]
    assert m_shape.facet_iou(roof, one)["mean_iou"] == pytest.approx(0.5)  # 1 matched of max(2, 1)
    assert m_shape.facet_iou(roof, H.truth_for(GOOD)["facets"])["mean_iou"] == pytest.approx(1.0)
    far = [{"polygon": H.rect(100, 100, 110, 110), "pitch_rise": 6.0}]
    assert m_shape.facet_iou(roof, far)["mean_iou"] == 0.0


def test_empty_result_scores_as_no_facets():
    r = sc({"facets": [], "edges": []})
    assert r["automation"] is False and r["status"] == "empty"
    assert sc(None)["status"] == "no_result"


def test_verdict_decides_automation_ok():
    res = H.gable_result()
    res["diagnostics"]["quality"]["verdict"] = "poor_fit"
    r = sc(res)
    assert r["automation"] is True and r["automation_ok"] is False
    del res["diagnostics"]
    assert sc(res)["automation_ok"] is True


def test_missing_plane_scores_as_misses():
    res = H.gable_result()
    del res["facets"][0]["plane"]
    m = M(res)
    assert m["invalid_facets"] == 1 and m["fit_all"] < 0.6


def test_fit_covered_vs_fit_all_split():
    roof = load_roof(H.shrunk(GOOD, 1.5))
    assert m_fit.fit_covered(roof, REF) == 1.0 and m_fit.fit_all(roof, REF) < 0.6


def test_area_error_against_each_truth_tier():
    true_sq = M(GOOD)["squares"]
    t1 = {**H.truth_for(GOOD, squares=true_sq * 1.10), "source": "vendor_report", "tier": "T1"}
    t3 = {"source": "contractor_squares", "confidence": "medium", "squares": 12.0, "tier": "T3"}
    r = sc(GOOD, [t1, t3, tru(GOOD, squares=true_sq)])
    assert r["truth"]["T1"]["squares.err_pct"] == pytest.approx(-100 * 0.10 / 1.10, rel=1e-6)
    assert r["truth"]["T2"]["squares.err_pct"] == pytest.approx(0, abs=1e-9)
    assert r["truth"]["T3"]["squares.ratio"] == pytest.approx(true_sq / 12.0)


def test_length_errors_vs_truth_and_perimeter():
    m = M(GOOD)
    t = {"source": "vendor_report", "tier": "T1", "lengths_ft": {"eave": m["lengths"]["eave"] * 0.9, "rake": m["lengths"]["rake"],
                                                                "ridge": m["lengths"]["ridge"], "hip": 0.0}}
    r = sc(GOOD, [t])["truth"]["T1"]
    assert r["lengths.eave.err_pct"] == pytest.approx(100 * (1 / 0.9 - 1), rel=1e-6)
    assert r["lengths.ridge.err_pct"] == pytest.approx(0, abs=1e-9)
    assert r["lengths.perimeter.err_pct"] > 0 and "lengths.ridge_hip.err_pct" in r


def test_t3_aggregate_median_and_interval():
    rows = [{"truth_files": [{"tier": "T3", "confidence": "medium", "squares": {"ratio": x}}]}
            for x in (0.9, 0.95, 1.0, 1.05, 1.1, 1.0, 0.98)]
    rows.append({"truth_files": [{"tier": "T3", "confidence": "low", "squares": {"ratio": 5.0}}]})  # low confidence: ignored
    agg = m_truth.t3_aggregate(rows)
    assert agg["n"] == 7 and agg["median_ratio"] == pytest.approx(1.0)
    assert agg["lo90"] <= 1.0 <= agg["hi90"] and agg == m_truth.t3_aggregate(rows)
    assert m_truth.t3_aggregate([]) is None


RULES = price.load_rules(Path(__file__).resolve().parents[1] / "tools" / "roof_eval" / "price_rules.example.json")


def test_price_delta_zero_for_matching_and_signed_for_over_measure():
    m = M(GOOD)
    ln = m["lengths"]
    truth = {"source": "vendor_report", "tier": "T1", "squares": m["squares"], "predominant_pitch": 6.0,
             "lengths_ft": {"eave": ln["eave"], "rake": ln["rake"], "ridge": ln["ridge"], "hip": 0.0, "valley": 0.0}}
    same = sc(GOOD, [truth], rules=RULES)["truth"]["T1"]
    assert same["price.total.delta"] == pytest.approx(0, abs=1e-6)
    over = sc(GOOD, [{**truth, "squares": m["squares"] / 1.1}], rules=RULES)["truth"]["T1"]
    assert over["price.total.pct"] == pytest.approx(over["price.material.pct"] * (over["price.material.truth"] / over["price.total.truth"]), rel=1e-6)
    assert over["price.total.delta"] > 0


def test_price_delta_none_when_truth_is_silent():
    truth = {"source": "contractor_squares", "tier": "T3", "squares": 10.0, "confidence": "medium"}
    r = sc(GOOD, [truth], rules=RULES)
    assert r["truth_files"][0]["price"]["total"] is None and r["truth_files"][0]["price"]["drip_edge"] is None


def test_price_rules_waste_switches_to_cut_up():
    assert price.waste_pct(RULES, 6, 20.0, 20.0) == 8.0
    assert price.waste_pct(RULES, 20, 20.0, 20.0) == 12.0
    assert price.waste_pct(RULES, 6, 400.0, 20.0) == 12.0


def test_truth_flat_edge_counts_in_perimeter_from_extra_block():
    m = M(GOOD)
    ln = m["lengths"]
    t = {"source": "llm_vision", "tier": "T2", "lengths_ft": {"eave": ln["eave"], "rake": ln["rake"]},
         "lengths_ft_extra": {"flat_edge": 50.0}}
    r = sc(GOOD, [t])["truth"]["T2"]
    assert r["lengths.perimeter.truth"] == pytest.approx(ln["eave"] + ln["rake"] + 50.0)
    assert r["lengths.perimeter.err_pct"] < 0


def test_level_change_threshold_is_the_contract_03_m():
    for jump, false in ((0.4, 0), (0.2, 1), (0.35, 0)):  # 0.4 m step: a real level change; 0.2 m: false
        real, pts = H.pitched_step(jump)
        assert M(real, ref=pts)["false_level_change_count"] == false, jump


def test_price_delta_for_flat_only_and_mixed_roofs():
    flat_truth = {"source": "vendor_report", "tier": "T1", "squares": 10.0, "flat_area_sqft": 1000.0, "predominant_pitch": None,
                  "lengths_ft": {"eave": 0.0, "rake": 0.0, "ridge": 0.0, "hip": 0.0}, "lengths_ft_extra": {"flat_edge": 2 * (12 + 8) / 0.3048}}
    flat_res = H.all_flat(GOOD)  # the flat roof's perimeter is recomputed from its facets: 40 m
    r = sc(flat_res, [flat_truth], rules=RULES)["truth_files"][0]["price"]
    assert r["total"] is not None and r["material"] is not None and r["drip_edge"]["delta"] == pytest.approx(0, abs=0.5)
    assert r["material"]["engine"] == pytest.approx(r["material"]["truth"] * (m_area_sq(flat_res) / 10.0), rel=1e-6)


def m_area_sq(res):
    return M(res)["squares"]


def test_pitch_multiplier_rows_apply_at_7_and_10():
    kw = {"pitched_squares": 10.0, "flat_squares": 0.0, "perimeter_ft": 0.0, "ridge_hip_ft": 0.0, "facets": 4, "hip_valley_ft": 0.0}
    base = price.sheet(RULES, pitch=6.9, **kw)["material"]
    assert base == pytest.approx(10 * 400 * 1.0 * 1.08)
    assert price.sheet(RULES, pitch=7.0, **kw)["material"] == pytest.approx(10 * 400 * 1.1 * 1.08)
    assert price.sheet(RULES, pitch=9.9, **kw)["material"] == pytest.approx(10 * 400 * 1.1 * 1.08)
    assert price.sheet(RULES, pitch=10.0, **kw)["material"] == pytest.approx(10 * 400 * 1.25 * 1.08)
    assert price.sheet(RULES, pitch=None, **kw)["material"] is None  # pitched squares with no pitch stay unknown
    assert price.sheet(RULES, pitch=None, **{**kw, "pitched_squares": 0.0, "flat_squares": 5.0})["material"] == pytest.approx(5 * 650 * 1.08)


def test_t3_aggregate_counts_one_ratio_per_house():
    two_files = {"truth_files": [{"tier": "T3", "confidence": "medium", "squares": {"ratio": 1.0}},
                                 {"tier": "T3", "confidence": "high", "squares": {"ratio": 1.2}}]}
    one = {"truth_files": [{"tier": "T3", "confidence": "medium", "squares": {"ratio": 2.0}}]}
    assert m_truth.t3_aggregate([two_files, one])["n"] == 2


def with_totals(**totals):
    r = H.gable_result()
    r["totals"] = totals
    return r


def test_the_engine_totals_are_not_read_the_drawn_roof_is_the_only_basis():
    """0.6.0 retired the priced-versus-drawn split: whatever the totals say, the numbers come from the facets and edges."""
    drawn = M(GOOD)
    odd = M(with_totals(area_sqft=1000.0, eave_ft=1.0, ridge_hip_ft=999.0, planes_surface_area_sqft=5.0))
    for k in ("area_sqft", "perimeter_ft", "ridge_hip_ft"):
        assert odd[k] == pytest.approx(drawn[k]), k
    assert "priced" not in odd and "priced_consistent" not in odd


def test_truth_comparison_uses_the_drawn_roof_for_every_tier():
    drawn_sq = M(GOOD)["squares"]
    res = with_totals(area_sqft=drawn_sq * 90)
    t = {"source": "vendor_report", "tier": "T1", "squares": drawn_sq * 0.9, "lengths_ft": {"eave": 50.0, "rake": 50.0, "ridge": 39.0, "hip": 0.0}}
    r = sc(res, [t])["truth"]["T1"]
    assert r["squares.result"] == pytest.approx(drawn_sq) and r["squares.err_pct"] == pytest.approx(100 / 0.9 - 100, rel=1e-6)
    assert "squares.err_pct_drawn" not in r and "squares.priced_ratio" not in r and "lengths.perimeter.result_drawn" not in r
    t3 = {"source": "contractor_squares", "tier": "T3", "confidence": "medium", "squares": drawn_sq * 0.9}
    assert sc(res, [t3])["truth"]["T3"]["squares.ratio"] == pytest.approx(1 / 0.9)
    assert sc(res)["m"]["fit_all"] == 1.0  # shape metrics use the drawn geometry, as before


def test_price_delta_uses_the_drawn_inputs():
    m = M(GOOD)
    ln = m["lengths"]
    t = {"source": "vendor_report", "tier": "T1", "squares": m["squares"], "predominant_pitch": 6.0,
         "lengths_ft": {"eave": ln["eave"], "rake": ln["rake"], "ridge": ln["ridge"], "hip": 0.0, "valley": 0.0}}
    assert sc(GOOD, [t], rules=RULES)["truth"]["T1"]["price.total.delta"] == pytest.approx(0, abs=1e-6)
