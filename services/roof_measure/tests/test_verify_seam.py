"""verify(): verdicts, D1 degradation, determinism."""

import json

import anthropic
import httpx
import pytest
from test_verify_llm import Fake, finalize
from test_verify_merge import STRAIGHT, hip, split_edge, stretch

from roof_measure import verify as verify_mod
from roof_measure import verify_tools
from roof_measure.deadline import Deadline
from roof_measure.verify import verify
from roof_measure.verify_merge import merge_collinear


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_no_key_is_unverified_with_reason_and_keeps_model():
    r = verify(hip())
    v = r.verification
    assert v["verdict"] == "unverified" and v["model"] is None and v["rounds"] == 0
    assert set(v) == {"verdict", "notes", "adjustments", "original_totals", "model", "rounds", "usage"}
    assert any("ANTHROPIC_API_KEY" in n for n in v["notes"]) and len(v["original_totals"]) == 14


def test_pass_with_fake_client():
    r = verify(hip(), client=Fake([finalize("pass", [])]))
    assert r.verification["verdict"] == "pass" and r.verification["model"] == "claude-sonnet-5-5"
    assert r.verification["rounds"] == 1 and r.verification["adjustments"] == []


def test_zigzag_unverified_without_key_adjusted_with_client():
    m = split_edge(hip(), "e1", [[14.0, 0.0], [15.5, 0.06], [17.0, 0.0], [18.5, 0.04]])
    assert verify(m).verification["verdict"] == "unverified"
    r = verify(m, client=Fake([finalize("adjusted", [])]))
    v = r.verification
    assert v["verdict"] == "adjusted" and v["adjustments"] and r.model["totals"]["lengths_ft"]["eave"] < m["totals"]["lengths_ft"]["eave"] + 1e-9
    assert v["original_totals"]["eave_ft"] == pytest.approx(122.0, abs=0.2)


def test_straight_split_merges_but_totals_unmoved_is_pass():
    r = verify(hip() and split_edge(hip(), "e1", STRAIGHT), client=Fake([finalize("pass", [])]))
    assert r.verification["adjustments"] and r.verification["verdict"] == "pass"
    assert len(r.model["edges"]) == 9


def test_area_delta_over_five_percent_is_fail(monkeypatch):
    def distort(model, a, b, check=None):
        import copy
        m = copy.deepcopy(model)
        for f in m["facets"]:
            f["area_sqft"] *= 0.9
        m["totals"]["total_area_sqft"] *= 0.9
        return m, [{"op": "merge_collinear", "edge_ids": ["e1", "e2"], "edge_type": "eave", "length_before_ft": 1.0,
                    "length_after_ft": 1.0, "angle_tol_deg": a, "min_len_ft": b}]
    monkeypatch.setattr(verify_mod, "merge_collinear", distort)
    monkeypatch.setattr(verify_mod, "checker_for", lambda m: None)
    r = verify(hip(), client=Fake([finalize("pass", [])]))
    assert r.verification["verdict"] == "fail"
    assert any("overridden from pass to fail" in n for n in r.verification["notes"])
    assert r.model["totals"]["total_area_sqft"] == pytest.approx(hip()["totals"]["total_area_sqft"] * 0.9)


def test_edge_type_delta_over_ten_percent_is_fail(monkeypatch):
    def distort(model, a, b, check=None):
        import copy
        m = copy.deepcopy(model)
        m["totals"]["lengths_ft"]["eave"] *= 0.8
        return m, [{"op": "merge_collinear", "edge_ids": ["e1", "e2"], "edge_type": "eave", "length_before_ft": 1.0,
                    "length_after_ft": 1.0, "angle_tol_deg": a, "min_len_ft": b}]
    monkeypatch.setattr(verify_mod, "merge_collinear", distort)
    monkeypatch.setattr(verify_mod, "checker_for", lambda m: None)
    assert verify(hip(), client=Fake([finalize("adjusted", [])])).verification["verdict"] == "fail"


def test_never_finalizes_is_unverified_after_six_rounds():
    c = Fake([lambda c: [("recompute_totals", {})]])
    r = verify(hip(), client=c)
    assert c.calls == 6 and r.verification["verdict"] == "unverified" and r.verification["rounds"] == 6
    assert any("6 rounds" in n for n in r.verification["notes"])


def test_api_error_is_unverified_without_stack_or_secret():
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    r = verify(hip(), client=Fake([err]), api_key="sk-ant-secret")
    v = r.verification
    assert v["verdict"] == "unverified" and "sk-ant" not in json.dumps(v) and "Traceback" not in json.dumps(v)


def test_expired_deadline_makes_no_call():
    c = Fake([finalize()])
    r = verify(hip(), client=c, deadline=Deadline.after(0))
    assert c.calls == 0 and r.verification["verdict"] == "unverified"
    assert any("time" in n for n in r.verification["notes"])


def test_unknown_number_rejected_then_retry():
    c = Fake([finalize("pass", ["Eave is 999.5 ft."]), finalize("pass", ["Eave is 122.0 ft."])])
    r = verify(hip(), client=c)
    assert r.verification["verdict"] == "pass" and r.verification["rounds"] == 2


def test_deterministic_output_is_byte_identical():
    m = split_edge(hip(), "e1", STRAIGHT)
    a, b = verify(m), verify(m)
    assert json.dumps([a.model, a.verification], sort_keys=True) == json.dumps([b.model, b.verification], sort_keys=True)


def test_no_key_never_fails_even_when_delta_would(monkeypatch):
    def distort(model, a, b, check=None):
        import copy
        m = copy.deepcopy(model)
        m["totals"]["total_area_sqft"] *= 0.9
        return m, [{"op": "merge_collinear", "edge_ids": ["e1", "e2"], "edge_type": "eave", "length_before_ft": 1.0,
                    "length_after_ft": 1.0, "angle_tol_deg": a, "min_len_ft": b}]
    monkeypatch.setattr(verify_mod, "merge_collinear", distort)
    monkeypatch.setattr(verify_mod, "checker_for", lambda m: None)
    v = verify(hip()).verification
    assert v["verdict"] == "unverified" and v["adjustments"]
    assert any("would fail" in n and "area" in n for n in v["notes"])


def test_malformed_edge_skips_merge_with_note_and_does_not_raise():
    m = hip()
    del m["edges"][0]["facets"]
    v = verify(m).verification
    assert v["verdict"] == "unverified" and any("Deterministic merge skipped" in n for n in v["notes"])
    m = hip()
    m["edges"][1]["points"].append([1.0, 1.0])  # a 3-point edge
    v = verify(m, client=Fake([finalize("pass", [])])).verification
    assert any("Deterministic merge skipped" in n for n in v["notes"])


def test_deterministic_merge_is_chain_by_chain_in_verify():
    m = stretch(hip(), 3.0)
    m = split_edge(m, "e1", [[51.5, 2.61], [53.5, 2.61]])  # bulge chain, off the chord by 2.6 ft
    r = verify(m)
    assert all(len(a["edge_ids"]) == 2 for a in r.verification["adjustments"])  # no 3-chain: chord cap holds


def test_final_revalidation_failure_falls_back_to_the_deterministic_model(monkeypatch):
    m = split_edge(hip(), "e1", STRAIGHT)
    state = {"finalizing": False}

    def check(model):  # passes while the tools run, fails once the model finalizes
        if state["finalizing"]:
            raise verify_tools.ModelError("late failure")

    monkeypatch.setattr(verify_mod, "checker_for", lambda model: check)
    monkeypatch.setattr(verify_tools, "checker_for", lambda model: check)

    def go_final(c):
        state["finalizing"] = True
        return finalize("pass", [])(c)

    c = Fake([lambda c: [("merge_collinear", {"angle_tol_deg": 5, "min_len_ft": 3})], go_final])
    r = verify(m, client=c, angle_tol_deg=0.5, min_len_ft=0.5)  # tight: the deterministic step leaves chains
    det, det_adj = merge_collinear(m, 0.5, 0.5)
    assert len(det["edges"]) == 11 and len(r.model["edges"]) == 11  # the LLM merge (down to 9) was discarded
    assert r.verification["adjustments"] == det_adj
    assert any("Review changes discarded" in n for n in r.verification["notes"])
    assert r.verification["verdict"] in ("pass", "adjusted")


def test_no_key_note_covers_a_parapet_only_move(monkeypatch):
    def distort(model, a, b, check=None):
        import copy
        m = copy.deepcopy(model)
        m["totals"]["lengths_ft"]["parapet"] = 10.0
        return m, [{"op": "merge_collinear", "edge_ids": ["e1", "e2"], "edge_type": "parapet",
                    "length_before_ft": 20.0, "length_after_ft": 10.0, "angle_tol_deg": a, "min_len_ft": b}]
    monkeypatch.setattr(verify_mod, "merge_collinear", distort)
    monkeypatch.setattr(verify_mod, "checker_for", lambda m: None)
    m = hip()
    m["totals"]["lengths_ft"]["parapet"] = 20.0
    v = verify(m).verification
    assert v["verdict"] == "unverified" and any("edge totals (would fail)" in n for n in v["notes"])


def test_client_has_no_sdk_retries_and_result_carries_the_transcript(monkeypatch):
    made = {}
    fake = Fake([lambda c: [("recompute_totals", {})], finalize("pass", [])])

    def factory(**kw):
        made.update(kw)
        return fake

    monkeypatch.setattr(anthropic, "Anthropic", factory)
    r = verify(hip(), api_key="sk-test")
    assert made["max_retries"] == 0 and made["api_key"] == "sk-test"
    assert [t["round"] for t in r.transcript] == [1, 2] and r.transcript[1]["tool_calls"][0]["name"] == "finalize_verdict"
    assert verify(hip()).transcript == []
