"""Label agreement (plan D4): accepted when the two runs agree (area <= 8 %, two-sided facet IoU >= 0.6); the 85 %
of-returns-within-12-cm figure is a confidence tag (high / medium), never a pass/fail. Invented numbers only."""

import csv
import json

import pytest

from tools.roof_eval.label import compare
from tools.roof_eval.label.compare import ACCEPTED, decide, decide_status, metrics, rebuild


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


HALVES = [rect(0, 0, 12, 4), rect(0, 4, 12, 8)]
ONE = [rect(0, 0, 12, 8)]


def truth(polys=HALVES, area=1000.0, fit=90.0, nofacet=2.0, conf="medium", cost=1.5):
    return {
        "area_sqft": area,
        "facet_count": len(polys),
        "flat_area_sqft": 0.0,
        "confidence": conf,
        "lengths_ft": {"hip": 0.0, "valley": 0.0, "ridge": 40.0},
        "label_check": {"in_facet_within_12cm_pct": fit, "in_no_facet_pct": nofacet},
        "facets": [{"id": f"f{i}", "polygon": p} for i, p in enumerate(polys)],
        "api_run": {"cost_usd": cost, "submissions": 2},
        "run_tag": "x",
    }


# ---- the rule on the four numbers, every boundary ----
@pytest.mark.parametrize(
    "area,iou,f1,f2,status",
    [
        (0.0, 1.0, 95, 95, "accepted_high"),
        (8.0, 0.6, 85.0, 85.0, "accepted_high"),  # every boundary exactly on the line: accepted, high
        (8.0, 0.6, 84.99, 90, "accepted_medium"),  # one run just under 85: medium
        (8.0, 0.6, 90, 84.99, "accepted_medium"),
        (3.0, 0.9, 50, 40, "accepted_medium"),  # a poor point fit is a tag, not a failure
        (3.0, 0.9, 0, 0, "accepted_medium"),
        (8.0000001, 0.9, 95, 95, "rejected_disagree"),  # area just over 8 %
        (7.99, 0.5999, 95, 95, "rejected_disagree"),  # IoU just under 0.6
        (30.0, 0.9, 95, 95, "rejected_disagree"),  # a house whose two runs differ by 30 % in area
        (9.0, 0.3, 95, 95, "rejected_disagree"),
    ],
)
def test_decide_status_branches_and_boundaries(area, iou, f1, f2, status):
    assert decide_status(area, iou, f1, f2)[0] == status


def test_why_names_what_failed():
    assert "area differs 9.5%" in decide_status(9.5, 0.9, 95, 95)[1]
    assert "facet IoU 0.400" in decide_status(1.0, 0.4, 95, 95)[1]
    both = decide_status(20.0, 0.1, 95, 95)[1]
    assert "area" in both and "IoU" in both
    assert decide_status(1.0, 0.9, 95, 95)[1] == ""


def test_nan_numbers_never_pass():
    assert decide_status(float("nan"), 0.9, 95, 95)[0] == "rejected_disagree"
    assert decide_status(float("inf"), 0.9, 95, 95)[0] == "rejected_disagree"


def test_area_difference_is_relative_to_the_mean():
    assert compare.area_diff_pct(9600.0, 10400.0) == 8.0
    assert compare.area_diff_pct(100.0, 100.0) == 0.0
    assert compare.area_diff_pct(0.0, 0.0) == float("inf")


# ---- the metrics on two label files ----
def test_identical_runs_agree_perfectly():
    m = metrics(truth(), truth())
    assert (
        m["area_diff_pct"] == 0.0
        and m["facet_iou_two_sided"] == pytest.approx(1.0)
        and m["outline_iou"] == pytest.approx(1.0)
    )


def test_one_run_with_a_single_facet_gives_a_two_sided_iou_of_0_375():
    m = metrics(truth(HALVES), truth(ONE))
    assert m["facet_iou_two_sided"] == pytest.approx(
        0.375
    )  # matched 0.5 over 2 facets and over 1 facet, averaged
    assert decide_status(m["area_diff_pct"], m["facet_iou_two_sided"], 90, 90)[0] == "rejected_disagree"


# ---- end to end on a work folder ----
def put(work, hid, tag, t):
    d = work / "truth" / hid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"truth.llm_vision.{tag}.json").write_text(json.dumps(t))
    r = work / "runs" / hid / tag
    r.mkdir(parents=True, exist_ok=True)
    (r / "run.json").write_text("{}")


def work_with(tmp_path, ids):
    (tmp_path / "houses.tsv").write_text(
        "id\tfolder\tsplit\tstrata\n" + "".join(f"{i}\t/x/{i}\ttuning\ts\n" for i in ids)
    )
    return tmp_path


def test_agreeing_runs_write_a_merged_truth_with_confidence_and_fit(tmp_path):
    work = work_with(tmp_path, ["h-0000000a"])
    put(work, "h-0000000a", "r1", truth(fit=90.0, nofacet=2.0, conf="high"))
    put(work, "h-0000000a", "r2", truth(fit=92.0, nofacet=1.0, conf="medium", area=1050.0))
    out = decide(work, "h-0000000a")
    assert (
        out["status"] == "accepted_high" and out["confidence"] == "high" and out["merged_from"] == "r2"
    )  # better fit x coverage
    merged = json.loads((work / "truth" / "h-0000000a" / "truth.llm_vision.json").read_text())
    assert merged["confidence"] == "high" and merged["fit12_pct"] == [90.0, 92.0]
    assert merged["labeller_confidence"] == {"r1": "high", "r2": "medium"} and merged["area_sqft"] == 1050.0
    assert "run_tag" not in merged and merged["merged"]["chosen"] == "r2"


def test_a_poor_fit_is_accepted_as_medium(tmp_path):
    work = work_with(tmp_path, ["h-0000000a"])
    put(work, "h-0000000a", "r1", truth(fit=70.0))
    put(work, "h-0000000a", "r2", truth(fit=95.0))
    out = decide(work, "h-0000000a")
    assert out["status"] == "accepted_medium"
    assert (
        json.loads((work / "truth" / "h-0000000a" / "truth.llm_vision.json").read_text())["confidence"]
        == "medium"
    )


def test_disagreeing_runs_are_rejected_and_a_stale_merged_file_is_removed(tmp_path):
    work = work_with(tmp_path, ["h-0000000b"])
    put(work, "h-0000000b", "r1", truth(area=1000.0))
    put(work, "h-0000000b", "r2", truth(area=1300.0))
    stale = work / "truth" / "h-0000000b" / "truth.llm_vision.json"
    stale.write_text("{}")
    out = decide(work, "h-0000000b")
    assert out["status"] == "rejected_disagree" and "area differs" in out["why"] and not stale.exists()
    assert (
        work / "truth" / "h-0000000b" / "truth.llm_vision.r1.json"
    ).exists()  # the runs themselves are never deleted


def test_one_run_only_and_not_run(tmp_path):
    work = work_with(tmp_path, ["h-0000000c", "h-0000000d"])
    put(work, "h-0000000c", "r1", truth())
    assert decide(work, "h-0000000c")["status"] == "one_run_only"
    assert decide(work, "h-0000000d")["status"] == "not_run"


def test_rebuild_writes_labels_tsv_with_every_state(tmp_path):
    ids = ["h-00000001", "h-00000002", "h-00000003", "h-00000004", "h-00000005"]
    work = work_with(tmp_path, ids)
    put(work, ids[0], "r1", truth(fit=90))
    put(work, ids[0], "r2", truth(fit=90))
    put(work, ids[1], "r1", truth(fit=60))
    put(work, ids[1], "r2", truth(fit=90))
    put(work, ids[2], "r1", truth(area=1000.0))
    put(work, ids[2], "r2", truth(area=2000.0))
    (work / "runs" / ids[3] / "r1").mkdir(parents=True)  # started, not finished
    rebuild(work)
    with open(work / "labels.tsv") as fh:
        rows = {r["id"]: r for r in csv.DictReader(fh, delimiter="\t")}
    assert [rows[i]["status"] for i in ids] == [
        "accepted_high",
        "accepted_medium",
        "rejected_disagree",
        "running",
        "not_run",
    ]
    assert (
        rows[ids[0]]["confidence"] == "high"
        and rows[ids[1]]["confidence"] == "medium"
        and rows[ids[2]]["confidence"] == ""
    )
    assert rows[ids[0]]["split"] == "tuning"
    assert {r["status"] for r in rows.values() if r["status"] in ACCEPTED} == {
        "accepted_high",
        "accepted_medium",
    }
