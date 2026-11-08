"""Agent loop with a scripted fake client (always runs) and a live run (only with ANTHROPIC_API_KEY)."""

import os
from types import SimpleNamespace as NS

import pytest

from roof_measure.agent import AgentError, run_agent
from roof_measure.classify import BlockSet
from roof_measure.model import build_model, validate
from roof_measure.solar import load_fixture, segments_to_evidence


class FakeClient:
    """Plays back scripted assistant turns; each turn is a list of (tool name, input-builder)."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.messages = NS(create=self._create)
        self.calls = 0
        self.last_results = []

    def _create(self, **kw):
        # remember the tool results the harness sent back so builders can read them
        last = kw["messages"][-1]
        if isinstance(last["content"], list):
            self.last_results = [__import__("json").loads(c["content"]) for c in last["content"] if c["type"] == "tool_result"]
        turn = self.turns[self.calls](self)
        self.calls += 1
        blocks = [NS(type="tool_use", id=f"t{self.calls}_{i}", name=n, input=a) for i, (n, a) in enumerate(turn)]
        return NS(content=blocks, stop_reason="tool_use", usage=NS(input_tokens=1, output_tokens=1))


@pytest.fixture(scope="module")
def solar_setup(site1_blocks_path, solar_fixture_path):
    bs = BlockSet.load(site1_blocks_path)
    ev = segments_to_evidence(load_fixture(solar_fixture_path), bs.frame, bs.footprint_ft)
    return bs, ev


def _script():
    hip_ids = ["s0", "s1", "s2", "s3"]

    def t1(c):
        return [("region_from_segments", {"segment_ids": hip_ids}), ("pitch_rise_from_segments", {"segment_ids": hip_ids}),
                ("region_from_segments", {"segment_ids": ["s4"]})]

    def t2(c):
        return [("rect_fit", {"polygon_id": c.last_results[0]["parts"][0]["polygon_id"]})]

    def t3(c):
        rid = c.last_results[0]["polygon_id"]
        return [("hip_roof_edges", {"polygon_id": rid, "pitch_rise": 4.61})]

    def t4(c):
        pid = "p3"  # two regions (p1, p2) then the rectangle (p3)
        return [("finalize", {"blocks": [{"polygon_id": pid, "form": "hip", "pitch_rise": 4.61, "confidence": "high",
                                          "evidence": ["4 azimuths 90 deg apart"]}], "warnings": []})]

    return [t1, t2, t3, t4]


def test_fake_agent_produces_hip_for_the_west_end(solar_setup):
    bs, ev = solar_setup
    client = FakeClient(_script())
    res = run_agent(bs, ev, kind="solar", client=client)
    hips = [b for b in res.blocks if b.form == "hip"]
    assert len(hips) == 1 and hips[0].poly.centroid.x < 40
    assert any(b.form == "flat" for b in res.blocks)  # harness added the remainder
    assert res.api_calls == 4
    model = build_model(bs, res.blocks, {"method": "solar_agent"})
    validate(model)


def test_agent_rejects_invented_pitch_then_accepts(solar_setup):
    bs, ev = solar_setup
    bad = [lambda c: [("region_from_segments", {"segment_ids": ["s0", "s1", "s2", "s3"]})],
           lambda c: [("finalize", {"blocks": [{"polygon_id": "p1", "form": "hip", "pitch_rise": 7.77,
                                                "confidence": "low", "evidence": []}]})],
           lambda c: [("finalize", {"blocks": [{"polygon_id": "p1", "form": "hip", "pitch_rise": 4.61,
                                                "confidence": "low", "evidence": []}]})]]
    client = FakeClient(bad)
    res = run_agent(bs, ev, kind="solar", client=client)
    assert client.calls == 3 and res.blocks[0].pitch_rise == pytest.approx(4.61, abs=0.01)


def test_api_error_becomes_agent_error(solar_setup):
    import anthropic
    import httpx

    class Boom:
        def __init__(self):
            self.messages = NS(create=self.create)

        def create(self, **kw):
            req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError("credit balance is too low", response=httpx.Response(400, request=req),
                                            body=None)

    bs, ev = solar_setup
    with pytest.raises(AgentError, match="credit balance is too low"):
        run_agent(bs, ev, kind="solar", client=Boom())


def test_agent_round_cap(solar_setup):
    bs, ev = solar_setup
    client = FakeClient([lambda c: [("measure", {"polygon_id": "footprint"})]] * 3)
    with pytest.raises(AgentError, match="within 3 rounds"):
        run_agent(bs, ev, kind="solar", client=client, max_rounds=3)
    assert client.calls == 3


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="live agent test needs ANTHROPIC_API_KEY")
def test_live_agent_finds_hip_at_west_end(solar_setup):
    bs, ev = solar_setup
    res = run_agent(bs, ev, kind="solar", max_rounds=8)
    hips = [b for b in res.blocks if b.form == "hip"]
    assert hips and hips[0].poly.centroid.x < 45
    validate(build_model(bs, res.blocks, {"method": "solar_agent"}))
