"""LLM loop with a scripted fake client: request shape, finalize rejection, no-finalize, errors, token cap."""

import json
from types import SimpleNamespace as NS

import anthropic
import httpx
from test_verify_merge import STRAIGHT, hip, split_edge

from roof_measure.deadline import Deadline
from roof_measure.envelope import totals_from_model
from roof_measure.model import ModelError
from roof_measure.verify_llm import request_kwargs, run_loop
from roof_measure.verify_tools import Workspace, verdict_from_delta


class Fake:
    """Plays scripted turns; each turn is a callable(client) -> list of (tool, input) or an Exception."""

    def __init__(self, turns):
        self.turns, self.calls, self.kwargs, self.results = list(turns), 0, [], []
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.kwargs.append(kw)
        last = kw["messages"][-1]
        if isinstance(last["content"], list):
            self.results = [json.loads(c["content"]) for c in last["content"] if c["type"] == "tool_result"]
        turn = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        if isinstance(turn, Exception):
            raise turn
        out = turn(self)
        blocks = [NS(type="tool_use", id=f"t{self.calls}_{i}", name=n, input=a) for i, (n, a) in enumerate(out)]
        return NS(content=blocks, usage=NS(input_tokens=100, output_tokens=10))


def ws_for(model=None):
    m = model or hip()
    return Workspace(m, [], totals_from_model(m))


def finalize(verdict="pass", notes=()):
    return lambda c: [("finalize_verdict", {"verdict": verdict, "notes": list(notes), "adjustments": []})]


def test_request_kwargs_shape():
    kw = request_kwargs([{"role": "user", "content": "x"}], Deadline.after(60))
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] == 2000
    assert kw["tool_choice"] == {"type": "auto"} and "budget_tokens" not in json.dumps(kw["thinking"])
    assert kw["thinking"] == {"type": "between_tools"} and kw["output_config"] == {"effort": "low"}
    assert kw["timeout"] <= 30 and len(kw["tools"]) == 4


def test_finalize_first_round():
    c = Fake([finalize("pass", ["Edge table adds up to 122 ft of eave."])])
    res = run_loop(ws_for(), c, Deadline.after(60))
    assert res.final["verdict"] == "pass" and res.rounds == 1 and res.error is None
    assert res.usage == {"input_tokens": 100, "output_tokens": 10}


def test_unknown_number_is_error_then_retry_succeeds():
    bad = finalize("pass", ["Eave is 999.5 ft."])
    good = finalize("pass", ["Eave is 122.0 ft."])
    c = Fake([bad, good])
    res = run_loop(ws_for(), c, Deadline.after(60))
    assert c.calls == 2 and res.rounds == 2 and res.final is not None
    assert "error" in res.transcript[0]["tool_results"][0]["result"]
    assert c.kwargs[1]["messages"][2]["content"][0]["is_error"] is True


def test_wrong_verdict_is_overridden_by_delta():
    m = hip()
    ws = ws_for(m)
    ws.model = json.loads(json.dumps(m))
    ws.model["totals"]["total_area_sqft"] *= 0.8
    c = Fake([finalize("pass")])
    res = run_loop(ws, c, Deadline.after(60))
    assert res.final["verdict"] == "fail" and any("overridden from pass to fail" in n for n in res.final["notes"])


def test_never_finalizes_stops_after_six_rounds():
    c = Fake([lambda c: [("recompute_totals", {})]])
    res = run_loop(ws_for(), c, Deadline.after(60), max_rounds=6)
    assert c.calls == 6 and res.final is None and "6 rounds" in res.error


def test_api_error_is_captured_without_raising():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIConnectionError(request=req)
    res = run_loop(ws_for(), Fake([err]), Deadline.after(60))
    assert res.final is None and res.error.startswith("Anthropic API error")


def test_expired_deadline_makes_no_call():
    c = Fake([finalize()])
    res = run_loop(ws_for(), c, Deadline.after(0))
    assert c.calls == 0 and "time" in res.error


def test_token_cap_aborts():
    c = Fake([lambda c: [("recompute_totals", {})]])
    res = run_loop(ws_for(), c, Deadline.after(60), token_cap=150)
    assert c.calls == 1 and "token cap" in res.error


def test_merge_tool_is_bounded():
    c = Fake([lambda c: [("merge_collinear", {"angle_tol_deg": 9, "min_len_ft": 2})], finalize()])
    res = run_loop(ws_for(), c, Deadline.after(60))
    assert "error" in res.transcript[0]["tool_results"][0]["result"] and res.final is not None


def test_prompt_has_no_address():
    m = hip()
    m["address"] = "100 Example Ave, Sampletown, CA 90000"
    c = Fake([finalize()])
    run_loop(ws_for(m), c, Deadline.after(60))
    assert "Example Ave" not in json.dumps(c.kwargs[0]["messages"])


def test_finalize_in_the_response_that_crosses_the_cap_is_kept():
    res = run_loop(ws_for(), Fake([finalize("pass")]), Deadline.after(60), token_cap=50)
    assert res.final is not None and res.error is None


def test_llm_merge_that_breaks_validate_is_rejected_and_reverted():
    m = split_edge(hip(), "e1", STRAIGHT)
    ws = ws_for(m)
    n = len(ws.model["edges"])

    def refuse(model):
        raise ModelError("facets do not tile the block polygon")

    ws.check = refuse
    out = ws.call("merge_collinear", {"angle_tol_deg": 5, "min_len_ft": 3})
    assert "error" in out and "hint" in out and len(ws.model["edges"]) == n and ws.adjustments == []


def test_is_known_loopholes_are_closed():
    ws = ws_for()
    ws.allowed.extend([4.0, 4000.0, 122.0])
    bad = lambda t: ws.unknown_in_text(t)
    assert bad("area moved 9%") == [9.0] and bad("area 5 squares") == [5.0]
    assert bad("4,000 ft") == [] and bad("1,234 ft") == [1234.0] and bad("1e3") == [1000.0]
    assert bad("ft1500") == [1500.0] and bad("sf9999") == [9999.0]
    assert bad("edge e12 and f3 in b1") == [] and bad("3 segments") == []
    assert bad("pitch 4/12") == [] and bad("moved -122.0 ft") == []
    assert bad("pitch 7/12") == [] and bad("7 segments") == []  # 7/12 is a pitch; a bare 7 is a small integer
    assert bad("pitch 11/12") == [11.0]  # 11 is neither small nor known


def test_every_edge_type_counts_for_fail():
    cur = totals_from_model(hip())
    assert verdict_from_delta(cur, cur) == "pass"
    ol = {"parapet": 20.0, "eave": 100.0}
    assert verdict_from_delta(cur, cur, ol, {"parapet": 10.0, "eave": 100.0}) == "fail"
    assert verdict_from_delta(cur, cur, ol, {"parapet": 19.0, "eave": 100.0}) == "pass"
    assert verdict_from_delta(cur, cur, {"parapet": 8.0}, {"parapet": 1.0}) == "pass"  # under 10 ft: ignored


def test_notes_are_capped():
    ws = ws_for()
    notes = ["x" * 400] * 12
    assert ws.finalize({"verdict": "pass", "notes": notes, "adjustments": []})["status"] == "accepted"
    out = ws.final["notes"]
    assert len(out) <= 10 and all(len(n) <= 300 for n in out) and "truncated" in out[-1]
