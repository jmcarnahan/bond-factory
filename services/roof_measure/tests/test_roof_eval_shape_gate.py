"""The shape gate (plan 3.5): mean two-sided facet IoU on high, medium and all labels; gates on all; fails loudly when
high and medium differ by more than 0.15; FAILS (never silently passes) below 10 labelled houses. Invented numbers only."""

import json
from pathlib import Path

import pytest
import roof_eval_helpers as H
from shapely.geometry import Polygon
from test_roof_eval_run import cfg_for

from tools.roof_eval import gates, m_truth, runner, score

GATES_DIR = Path(__file__).resolve().parents[1] / "tools" / "roof_eval" / "gates"


def shape_gate(split="tuning", **over):
    spec = json.loads((GATES_DIR / f"{split}.json").read_text())
    g = next(g for g in spec["gates"] if g["agg"] == "t2_shape")
    return {**g, **over}


def rec(i, iou, conf):
    """A per-house record as the runner writes it, with only what the gate reads."""
    return {"id": f"h-{i:08x}", "row": {"tiers": ["T2"]}, "automation_ok": True,
            "truth": {"T2": {"facet_iou.mean_iou": iou}}, "t2_confidence": conf}


def run_gate(g, recs):
    (res,) = gates.evaluate({"gates": [g]}, recs)
    return res


def test_passes_and_reports_three_numbers():
    recs = [rec(i, 0.8, "high") for i in range(6)] + [rec(10 + i, 0.75, "medium") for i in range(6)]
    r = run_gate(shape_gate(), recs)
    s = r["shape"]
    assert r["passed"] and not r["skipped"]
    assert s["iou_high"] == pytest.approx(0.8) and s["iou_medium"] == pytest.approx(0.75)
    assert s["iou_all"] == pytest.approx(0.775) and r["value"] == pytest.approx(0.775)
    assert (s["n_high"], s["n_medium"], s["n_all"]) == (6, 6, 12)
    assert "high 0.800 (n=6)" in r["note"] and "medium 0.750 (n=6)" in r["note"] and "all 0.775 (n=12)" in r["note"]


def test_gates_on_all_not_on_high():
    recs = [rec(i, 0.9, "high") for i in range(4)] + [rec(10 + i, 0.5, "medium") for i in range(8)]
    r = run_gate(shape_gate(max_conf_gap=1.0), recs)  # gap check off: the mean of all is (3.6 + 4.0) / 12 = 0.633
    assert r["passed"] and r["value"] == pytest.approx(7.6 / 12)
    low = [rec(i, 0.9, "high") for i in range(2)] + [rec(10 + i, 0.5, "medium") for i in range(10)]
    r = run_gate(shape_gate(max_conf_gap=1.0), low)  # high is great, all is 0.567: fails
    assert not r["passed"] and r["shape"]["iou_all"] == pytest.approx((1.8 + 5.0) / 12)


def test_boundary_of_the_all_mean_is_inclusive():
    recs = [rec(i, 0.625, "high") for i in range(5)] + [rec(10 + i, 0.625, "medium") for i in range(5)]
    assert run_gate(shape_gate(value=0.625), recs)["passed"]
    assert not run_gate(shape_gate(value=0.6251), recs)["passed"]


def test_high_medium_gap_fails_loudly_even_when_the_mean_is_fine():
    recs = [rec(i, 0.95, "high") for i in range(5)] + [rec(10 + i, 0.65, "medium") for i in range(5)]
    r = run_gate(shape_gate(), recs)
    assert r["shape"]["iou_all"] == pytest.approx(0.8)  # well above 0.6 ...
    assert not r["passed"] and r["shape"]["loud"]  # ... and still a failure
    assert "LOUD FAILURE" in r["note"] and "0.300" in r["note"]


def test_gap_boundary_uses_a_strict_greater_than():
    recs = [rec(i, 0.75, "high") for i in range(5)] + [rec(10 + i, 0.625, "medium") for i in range(5)]  # gap 0.125, exact
    assert run_gate(shape_gate(max_conf_gap=0.125), recs)["passed"]
    r = run_gate(shape_gate(max_conf_gap=0.124), recs)
    assert not r["passed"] and r["shape"]["loud"]


def test_gap_is_not_computed_with_one_group_and_untagged_labels_count_in_all_only():
    recs = [rec(i, 0.9, "high") for i in range(5)] + [rec(10 + i, 0.4, None) for i in range(5)]
    r = run_gate(shape_gate(), recs)
    s = r["shape"]
    assert s["gap"] is None and not s["loud"] and s["iou_medium"] is None and s["n_all"] == 10
    assert s["iou_all"] == pytest.approx(0.65) and r["passed"]
    assert "medium n/a (n=0)" in r["note"]


def test_fewer_than_ten_labelled_houses_fail_on_tuning_too():
    for split in ("tuning", "heldout"):
        r = run_gate(shape_gate(split), [rec(i, 0.9, "high") for i in range(9)])
        assert not r["skipped"] and not r["passed"] and "insufficient" in r["note"]
    assert run_gate(shape_gate("tuning"), [rec(i, 0.9, "high") for i in range(10)])["passed"]


def test_fewer_than_ten_labelled_houses_fail_on_heldout():
    r = run_gate(shape_gate("heldout"), [rec(i, 0.9, "high") for i in range(9)])
    assert not r["skipped"] and not r["passed"] and "insufficient" in r["note"]
    assert run_gate(shape_gate("heldout"), [rec(i, 0.9, "high") for i in range(10)])["passed"]


def test_houses_that_failed_automation_are_not_counted():
    recs = [rec(i, 0.9, "high") for i in range(9)]
    bad = rec(99, 0.9, "high")
    bad["automation_ok"] = False
    assert not run_gate(shape_gate("tuning"), recs + [bad])["passed"]  # still 9: fails


def test_gate_files_carry_the_gate_with_the_right_insufficient_rule():
    t, h = shape_gate("tuning"), shape_gate("heldout")
    for g in (t, h):
        assert g["metric"] == "truth.T2.facet_iou.mean_iou" and g["op"] == ">=" and g["value"] == 0.6
        assert g["min_n"] == 10 and g["max_conf_gap"] == 0.15 and g["where"] == ["tiers=T2"]
    assert "on_insufficient" not in t and h["on_insufficient"] == "fail"  # absent = fail
    for split in ("tuning", "heldout"):
        names = [g["name"] for g in json.loads((GATES_DIR / f"{split}.json").read_text())["gates"]]
        assert sum(n.startswith("6 ") for n in names) == 1 and len(names) == 23


def _scored(res, conf, i):
    truth = {**H.truth_for(H.gable_result(), confidence=conf), "tier": "T2"}
    r = score.score_house(res, H.gable_points(), Polygon(H.footprint()), [truth])
    return {"id": f"h-{i:08x}", "row": {"tiers": ["T2"]}, **r}


def test_one_big_facet_fails_the_gate_and_the_right_result_passes():
    """The deliberately wrong result (one facet over the whole roof, IoU 0.25 against two) must fail; the right one passes."""
    wrong = [_scored(H.one_big_facet(H.gable_result()), "high" if i % 2 else "medium", i) for i in range(10)]
    r = run_gate(shape_gate(), wrong)
    assert r["shape"]["iou_all"] == pytest.approx(0.25, abs=0.01) and not r["passed"]
    right = [_scored(H.gable_result(), "high" if i % 2 else "medium", i) for i in range(10)]
    r = run_gate(shape_gate(), right)
    assert r["shape"]["iou_all"] == pytest.approx(1.0) and r["passed"]


def test_t2_confidence_of_a_house():
    f = [{"tier": "T2", "confidence": "high"}, {"tier": "T2", "confidence": "medium"}]
    assert m_truth.t2_confidence(f) == "medium"
    assert m_truth.t2_confidence(f[:1]) == "high"
    assert m_truth.t2_confidence([{"tier": "T2", "confidence": "low"}, {"tier": "T3", "confidence": "high"}]) is None
    assert m_truth.t2_confidence([]) is None


def test_too_few_houses_fail_the_run_on_both_splits(tmp_path):
    root = tmp_path / "data"
    H.build_root(root, n=4)  # 4 T2 houses: under the 10 the gate needs
    for i, split in enumerate(("tuning", "heldout")):
        out = tmp_path / f"gates{i}.json"
        out.write_text(json.dumps({"gates": [shape_gate(split)]}))
        s = runner.evaluate(cfg_for(root, tmp_path, "perfect", f"run{i}", gates_file=out))
        assert not s["ok"] and not s["gates"][0]["passed"] and not s["gates"][0]["skipped"]
