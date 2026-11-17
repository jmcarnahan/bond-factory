"""The agent loop with the REAL SDK block types a thinking model returns (thinking, redacted_thinking, text, tool_use).

Offline: a scripted client; no key, no network. The old loop raised AgentError("unexpected content block type
'thinking'") on the first reply, which the NS-only fake in test_model_agent.py could never show.
"""

import dataclasses
import json
from types import SimpleNamespace as NS

import pytest
from anthropic.types import RedactedThinkingBlock, TextBlock, ThinkingBlock, ToolUseBlock

from roof_measure import agent as agent_mod
from roof_measure.agent import AgentError, run_agent
from roof_measure.classify import BlockSet

FLAT_FINAL = {"blocks": [{"polygon_id": "footprint", "form": "flat", "confidence": "low", "evidence": ["x"]}]}
THINK1 = {"type": "thinking", "thinking": "look at the azimuths", "signature": "SIG-ONE=="}
REDACTED = {"type": "redacted_thinking", "data": "ENC-DATA-123"}


class Scripted:
    """A client that replays full replies (lists of SDK block objects) and records every request it gets."""

    def __init__(self, replies, stop="tool_use"):
        self.replies = list(replies)
        self.messages = NS(create=self._create)
        self.requests = []
        self.stop = stop

    def _create(self, **kw):
        # snapshot: the loop mutates its message list afterwards
        self.requests.append({"kw": {k: v for k, v in kw.items() if k != "messages"},
                              "messages": json.loads(json.dumps(kw["messages"]))})
        n = len(self.requests)
        reply = self.replies[n - 1]
        blocks, stop = (reply if isinstance(reply, tuple) else (reply, self.stop))
        return NS(content=blocks, stop_reason=stop, usage=NS(input_tokens=100 * n, output_tokens=10 * n))


def thinking_block(d=THINK1):
    return ThinkingBlock(type="thinking", thinking=d["thinking"], signature=d["signature"])


def tool(i, name, args):
    return ToolUseBlock(type="tool_use", id=f"tu{i}", name=name, input=args)


@pytest.fixture(scope="module")
def blockset(site1_blocks_path):
    return BlockSet.load(site1_blocks_path)


@pytest.fixture
def cgal_stub(monkeypatch):
    """No native CGAL call can happen in this process: a regression of the guard must fail an assertion, never
    kill the test run. The stub records the ring it is handed and raises a ValueError the loop turns into an error."""
    import roof_measure.skeleton as sk

    rings = []

    def stub(ring3, *a, **k):
        rings.append([(p[0], p[1]) for p in ring3])
        raise ValueError("stub: CGAL is not called in this test")

    monkeypatch.setattr(sk, "interior_straight_skeleton", stub)
    return rings


def trapezoid_set(bs):
    return dataclasses.replace(bs, footprint_ft=[(0.0, 0.0), (40.0, 0.0), (43.0, 24.0), (-3.0, 24.0)], blocks=[])


def test_loop_finishes_with_thinking_blocks_and_echoes_them_unchanged(blockset):
    client = Scripted([
        [thinking_block(), tool(1, "measure", {"polygon_id": "footprint"})],
        [thinking_block(), RedactedThinkingBlock(type="redacted_thinking", data=REDACTED["data"]),
         TextBlock(type="text", text="Flat is safest."), tool(2, "finalize", FLAT_FINAL)],
    ])
    res = run_agent(blockset, kind="lidar", client=client)
    assert res.api_calls == 2 and res.blocks
    assert res.usage == {"input_tokens": 100 + 200, "output_tokens": 10 + 20}
    echoed = client.requests[1]["messages"][1]
    assert echoed["role"] == "assistant"
    assert echoed["content"][0] == THINK1  # byte-for-byte: thinking text and signature, in front of the tool_use
    assert json.dumps(echoed["content"][0], sort_keys=True) == json.dumps(THINK1, sort_keys=True)
    assert echoed["content"][1]["type"] == "tool_use" and echoed["content"][1]["name"] == "measure"


def test_redacted_thinking_is_echoed_with_its_data(blockset):
    client = Scripted([
        [RedactedThinkingBlock(type="redacted_thinking", data=REDACTED["data"]), tool(1, "measure", {"polygon_id": "footprint"})],
        [tool(2, "finalize", FLAT_FINAL)],
    ])
    run_agent(blockset, kind="lidar", client=client)
    assert client.requests[1]["messages"][1]["content"][0] == REDACTED


def test_every_request_sends_the_explicit_thinking_setting(blockset):
    client = Scripted([[tool(1, "finalize", FLAT_FINAL)]])
    run_agent(blockset, kind="lidar", client=client)
    kw = client.requests[0]["kw"]
    assert kw["thinking"] == {"type": "between_tools"}  # the same setting the verifier sends
    assert kw["max_tokens"] == agent_mod.MAX_TOKENS >= 12000  # room for thinking plus the tool call


def test_stop_reason_max_tokens_is_a_clear_agent_error(blockset):
    client = Scripted([([thinking_block()], "max_tokens")])
    with pytest.raises(AgentError, match="ran out of output tokens"):
        run_agent(blockset, kind="lidar", client=client)
    assert len(client.requests) == 1  # no nudge round wasted on a truncated turn


def test_stop_reason_refusal_is_a_clear_agent_error(blockset):
    client = Scripted([([TextBlock(type="text", text="no")], "refusal")])
    with pytest.raises(AgentError, match="declined"):
        run_agent(blockset, kind="lidar", client=client)


def test_transcript_records_thinking_and_survives_json(blockset):
    client = Scripted([
        [thinking_block(), RedactedThinkingBlock(type="redacted_thinking", data="X"),
         TextBlock(type="text", text="hi"), tool(1, "finalize", FLAT_FINAL)],
    ])
    res = run_agent(blockset, kind="lidar", client=client)
    entry = res.transcript[1]
    assert entry["thinking"] == ["look at the azimuths"] and entry["redacted_thinking_blocks"] == 1
    assert entry["text"] == "hi"
    assert "SIG-ONE" not in json.dumps(res.transcript)  # the signature is not debug material
    json.dumps(res.transcript, default=str)


def test_unknown_block_types_are_kept_not_rejected(blockset):
    odd = NS(type="server_tool_use", id="s1", name="web", input={"q": 1})
    client = Scripted([
        [odd, tool(1, "measure", {"polygon_id": "footprint"})],
        [tool(2, "finalize", FLAT_FINAL)],
    ])
    res = run_agent(blockset, kind="lidar", client=client)
    assert res.api_calls == 2
    assert client.requests[1]["messages"][1]["content"][0]["type"] == "server_tool_use"


def test_plain_dict_and_missing_usage_are_tolerated(blockset):
    class NoUsage(Scripted):
        def _create(self, **kw):
            r = super()._create(**kw)
            r.usage = None
            return r

    client = NoUsage([[dict(THINK1), tool(1, "finalize", FLAT_FINAL)]])
    res = run_agent(blockset, kind="lidar", client=client)
    assert res.usage == {"input_tokens": 0, "output_tokens": 0}


# ----------------------------------------------------------------------------- tool errors the model can read
def results_of(client, request_index):
    last = client.requests[request_index]["messages"][-1]
    return [(json.loads(c["content"]), c["is_error"]) for c in last["content"] if c["type"] == "tool_result"]


def test_self_crossing_polygon_is_a_tool_error_not_a_crash(blockset, cgal_stub):
    bow = dataclasses.replace(blockset, footprint_ft=[(0.0, 100.0), (10.0, 100.0), (20.0, 0.0), (31.0, 0.0)], blocks=[])
    client = Scripted([
        [tool(1, "hip_roof_edges", {"polygon_id": "footprint", "pitch_rise": 6.0, "gable_edges": [0, 2]})],
        [tool(2, "finalize", FLAT_FINAL)],
    ])
    run_agent(bow, kind="lidar", client=client)
    (out, is_err), = results_of(client, 1)
    assert is_err and "outline" in out["error"] and "rect_fit" in out["error"]
    assert cgal_stub == []  # the bad ring was refused before the native call


def test_trapezoid_gable_call_hands_cgal_only_a_valid_ring(blockset, cgal_stub):
    from shapely.geometry import Polygon

    client = Scripted([
        [tool(1, "hip_roof_edges", {"polygon_id": "footprint", "pitch_rise": 6.0, "gable_edges": [0, 2]})],
        [tool(2, "finalize", FLAT_FINAL)],
    ])
    run_agent(trapezoid_set(blockset), kind="lidar", client=client)
    (out, is_err), = results_of(client, 1)
    assert is_err and "stub" in out["error"]  # reached the (stubbed) native call, so the guard let the ring through
    assert len(cgal_stub) == 1 and Polygon(cgal_stub[0]).is_valid and Polygon(cgal_stub[0]).exterior.is_simple


def test_shapely_error_from_a_tool_is_a_tool_error(blockset, monkeypatch):
    from shapely.errors import GEOSException

    def boom(self, polygon_id, line_ft):
        raise GEOSException("TopologyException: found non-noded intersection")

    monkeypatch.setattr(agent_mod.Workspace, "propose_split", boom)
    client = Scripted([
        [tool(1, "propose_split", {"polygon_id": "footprint", "line_ft": [[0, 0], [1, 1]]})],
        [tool(2, "finalize", FLAT_FINAL)],
    ])
    res = run_agent(blockset, kind="lidar", client=client)
    (out, is_err), = results_of(client, 1)
    assert res.blocks and is_err and out["error"].startswith("GEOSException") and "check" in out["error"]


def test_attribute_error_from_wrong_json_types_is_a_tool_error(blockset):
    client = Scripted([
        [tool(1, "finalize", {"blocks": ["footprint", "p1"]})],  # entries are strings, not objects
        [tool(2, "finalize", FLAT_FINAL)],
    ])
    res = run_agent(blockset, kind="lidar", client=client)
    (out, is_err), = results_of(client, 1)
    assert is_err and "error" in out and res.blocks


def test_tool_arguments_of_the_wrong_json_type_are_tool_errors(blockset):
    client = Scripted([
        [tool(1, "measure", {"polygon_id": ["footprint"]}), tool(3, "propose_split", {"polygon_id": "footprint",
                                                                                       "line_ft": "x"})],
        [tool(2, "finalize", FLAT_FINAL)],
    ])
    run_agent(blockset, kind="lidar", client=client)
    got = results_of(client, 1)
    assert len(got) == 2 and all(is_err and "error" in out for out, is_err in got)


def test_zero_division_and_index_errors_are_tool_errors(blockset, monkeypatch):
    def boom(self, polygon_id):
        return 1 / 0

    monkeypatch.setattr(agent_mod.Workspace, "measure", boom)
    client = Scripted([[tool(1, "measure", {"polygon_id": "footprint"})], [tool(2, "finalize", FLAT_FINAL)]])
    run_agent(blockset, kind="lidar", client=client)
    (out, is_err), = results_of(client, 1)
    assert is_err and out["error"].startswith("ZeroDivisionError")


# ----------------------------------------------------------------------------- key problems are not agent failures
def sdk_error(cls, status):
    import httpx

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("invalid x-api-key", response=httpx.Response(status, request=req), body=None)


@pytest.mark.parametrize("cls, status", [(__import__("anthropic").AuthenticationError, 401),
                                         (__import__("anthropic").PermissionDeniedError, 403)])
def test_a_rejected_key_is_an_auth_error_not_an_agent_error(blockset, cls, status):
    class Boom:
        messages = NS(create=lambda **kw: (_ for _ in ()).throw(sdk_error(cls, status)))

    with pytest.raises(agent_mod.AgentAuthError, match="API key was rejected") as e:
        run_agent(blockset, kind="lidar", client=Boom())
    assert not isinstance(e.value, AgentError)  # so the pipeline does not fall back on it


def test_other_api_errors_stay_agent_errors(blockset):
    import anthropic

    class Boom:
        messages = NS(create=lambda **kw: (_ for _ in ()).throw(sdk_error(anthropic.BadRequestError, 400)))

    with pytest.raises(AgentError, match="invalid x-api-key"):
        run_agent(blockset, kind="lidar", client=Boom())


def test_a_shortened_gable_extension_is_noted_on_the_accepted_block(blockset, monkeypatch):
    """finalize copies the skeleton's notes onto the block, so the model shows them."""
    import roof_measure.agent_tools as tools

    real = tools.block_geometry
    note = "Gable ends were extended by 40 ft instead of 160 ft because the sides next to them converge; check the rakes."

    def with_note(*a, **k):
        return {**real(*a, **k), "notes": [note]}

    monkeypatch.setattr(tools, "block_geometry", with_note)
    client = Scripted([[tool(1, "finalize", FLAT_FINAL)]])
    res = run_agent(blockset, kind="lidar", client=client)
    assert any(note in b.notes for b in res.blocks)


# ----------------------------------------------------------------------------- non-finite and arithmetic failures
def test_infinite_gable_edge_is_a_tool_error_not_a_dead_job(blockset):
    """The adversary's input: finalize with gable_edges [1e999, 0] (JSON 1e999 parses to infinity)."""
    bad = json.loads('{"blocks": [{"polygon_id": "footprint", "form": "gable", "pitch_rise": 4.0, '
                     '"gable_edges": [1e999, 0], "confidence": "low", "evidence": []}]}')
    client = Scripted([[tool(1, "finalize", bad)], [tool(2, "finalize", FLAT_FINAL)]])
    res = run_agent(blockset, kind="lidar", client=client)
    (out, is_err), = results_of(client, 1)
    assert res.blocks and is_err and "not finite" in out["error"]


@pytest.mark.parametrize("args", [
    {"polygon_id": "footprint", "pitch_rise": float("nan")},
    {"polygon_id": "footprint", "pitch_rise": 4.0, "gable_edges": [float("inf")]},
    {"polygon_id": "footprint", "pitch_rise": 10 ** 400},
])
def test_non_finite_tool_numbers_are_refused_before_any_geometry(blockset, args):
    client = Scripted([[tool(1, "hip_roof_edges", args)], [tool(2, "finalize", FLAT_FINAL)]])
    run_agent(blockset, kind="lidar", client=client)
    (out, is_err), = results_of(client, 1)
    assert is_err and "not finite" in out["error"]


def test_overflow_and_runtime_errors_from_a_tool_are_tool_errors(blockset, monkeypatch):
    def overflow(self, polygon_id):
        raise OverflowError("cannot convert float infinity to integer")

    def runtime(self, polygon_id, pitch_rise, gable_edges=None):
        raise RuntimeError("native wrapper failed")

    monkeypatch.setattr(agent_mod.Workspace, "measure", overflow)
    monkeypatch.setattr(agent_mod.Workspace, "hip_roof_edges", runtime)
    client = Scripted([[tool(1, "measure", {"polygon_id": "footprint"}),
                        tool(3, "hip_roof_edges", {"polygon_id": "footprint", "pitch_rise": 4.0})],
                       [tool(2, "finalize", FLAT_FINAL)]])
    run_agent(blockset, kind="lidar", client=client)
    got = results_of(client, 1)
    assert len(got) == 2 and all(is_err for _, is_err in got)
    assert got[0][0]["error"].startswith("OverflowError") and got[1][0]["error"].startswith("RuntimeError")
