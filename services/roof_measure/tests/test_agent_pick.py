"""The agent is never worse than the rules: the pipeline returns whichever roof matches the measured planes better.

Lower plane mismatch wins; a tie goes to the rule result. Synthetic 40 x 24 ft hip (``quality_helpers.hip_rectangle``).
Scripted agent, offline, no key.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

from quality_helpers import hip_rectangle

from roof_measure import agent_pick, pipeline
from roof_measure.classify import Classification, RoofBlock

CODE = "agent_failed_fell_back"
RECT = [(0.0, 0.0), (40.0, 0.0), (40.0, 24.0), (0.0, 24.0)]
HIP = [("finalize", {"blocks": [{"polygon_id": "footprint", "form": "hip", "pitch_rise": 4.0, "confidence": "high",
                                 "evidence": []}]})]
FLAT = [("finalize", {"blocks": [{"polygon_id": "footprint", "form": "flat", "confidence": "low", "evidence": []}]})]


class Client:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.calls += 1
        blocks = [NS(type="tool_use", id=f"t{self.calls}_{i}", name=n, input=a) for i, (n, a) in enumerate(self.reply)]
        return NS(content=blocks, stop_reason="tool_use", usage=NS(input_tokens=1, output_tokens=1))


def run(tmp_path, reply):
    p = tmp_path / "blocks.json"
    hip_rectangle().save(p)
    return pipeline.run_pipeline("x", tmp_path / "out", "lidar_agent", blocks_path=p, client=Client(reply),
                                 verify=False, render=False)


def flat_rules(monkeypatch):
    """The rule method answers one flat block (so any sloped agent answer matches the hip planes better)."""
    def flat(bs, **kw):
        return Classification(blocks=[RoofBlock(id="b1", form="flat", polygon=RECT)])

    monkeypatch.setattr(agent_pick, "classify_blocks", flat)


def test_a_worse_agent_roof_gives_the_rule_result_and_says_so(tmp_path):
    res = run(tmp_path, FLAT)  # the rules draw the hip, the agent a flat roof
    assert res.method_used == "lidar_skeleton" and res.model["source"]["method"] == "lidar_skeleton"
    codes, warns = res.envelope["warning_codes"], res.envelope["warnings"]
    assert CODE in codes and "was not used" in warns[codes.index(CODE)] and "worse" in warns[codes.index(CODE)]
    assert "agent" not in res.model["debug"] and res.agent_transcript is not None  # the transcript is kept
    assert [b["form"] for b in res.model["blocks"]] == ["hip"]


def test_a_tie_goes_to_the_rule_result(tmp_path):
    res = run(tmp_path, HIP)  # both draw the same hip: equal mismatch
    assert res.method_used == "lidar_skeleton" and CODE in res.envelope["warning_codes"]


def test_a_better_agent_roof_is_kept(tmp_path, monkeypatch):
    flat_rules(monkeypatch)
    res = run(tmp_path, HIP)
    assert res.method_used == "lidar_agent" and CODE not in res.envelope["warning_codes"]
    assert [b["form"] for b in res.model["blocks"]] == ["hip"] and res.model["debug"]["agent"]["api_calls"] == 1


def test_the_agent_stands_when_the_rule_roof_cannot_be_built(tmp_path, monkeypatch):
    def boom(bs, **kw):
        raise ValueError("no skeleton")

    monkeypatch.setattr(agent_pick, "classify_blocks", boom)
    res = run(tmp_path, FLAT)
    assert res.method_used == "lidar_agent" and CODE not in res.envelope["warning_codes"]


def test_without_planes_there_is_nothing_to_compare():
    bs = hip_rectangle()
    bs.blocks = []
    assert agent_pick.rules_if_not_worse(bs, {"facets": []}, []) is None


def test_the_comparison_never_changes_a_rule_method(tmp_path):
    p = tmp_path / "blocks.json"
    hip_rectangle().save(p)
    res = pipeline.run_pipeline("x", tmp_path / "out", "lidar_skeleton", blocks_path=p, verify=False, render=False)
    assert res.method_used == "lidar_skeleton" and CODE not in res.envelope["warning_codes"]
