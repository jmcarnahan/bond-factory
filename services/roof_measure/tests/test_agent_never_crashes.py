"""The agent method never crashes after the agent has finished.

The real failure (a house measured through ``lidar_agent``): the agent's gable passed ``Workspace.finalize`` as drawn,
``complete_tiling`` then clipped it to the footprint and its neighbours, and ``build_model`` raised
``ValueError: gable edges cannot be extended on this outline`` from ``block_geometry``, after the agent's turn, so the
whole measurement failed. The shape is rebuilt here by hand: a wrapper around ``complete_tiling`` turns the agent's
gable into a trapezoid whose sides converge on the gable ends (the clipped shape), invented 40 x 24 ft frame.

Three defences, one test group each: the agent hears about it and corrects itself; at its last round the gable is
drawn as a hip; and the pipeline answers with the rule result, then the planes only, rather than raising.
Scripted fake client, no key, no network.
"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest
from quality_helpers import hip_rectangle
from shapely.geometry import Polygon

from roof_measure import agent as agent_mod
from roof_measure import agent_repair, pipeline
from roof_measure.agent import run_agent
from roof_measure.classify import RoofBlock
from roof_measure.envelope import WARNING_CODES
from roof_measure.model import ModelError, build_model, validate
from roof_measure.skeleton import block_geometry

CODE = "agent_failed_fell_back"
TRAPEZOID = [(0.0, 0.0), (40.0, 0.0), (32.0, 24.0), (8.0, 24.0)]  # edges 0 and 2 are the gable ends; sides converge
PITCH = 4.0  # the LiDAR blocks' pitch, so the agent may cite it


class Client:
    """Scripted client: each reply is a list of ``(tool name, input)``; the last one repeats."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0
        self.results: list[list[dict]] = []  # tool results the harness sent back, one list per request
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        last = kw["messages"][-1]
        if isinstance(last["content"], list):
            got = [c for c in last["content"] if c["type"] == "tool_result"]
            if got:
                self.results.append(got)
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        blocks = [NS(type="tool_use", id=f"t{self.calls}_{i}", name=n, input=a) for i, (n, a) in enumerate(reply)]
        return NS(content=blocks, stop_reason="tool_use", usage=NS(input_tokens=1, output_tokens=1))


def finalize(form: str, **extra):
    blk = {"polygon_id": "footprint", "form": form, "pitch_rise": PITCH, "confidence": "high", "evidence": ["x"], **extra}
    return [("finalize", {"blocks": [blk]})]


GABLE = finalize("gable", gable_edges=[0, 2])
HIP = finalize("hip")


@pytest.fixture
def agent_wins(monkeypatch):
    """The agent is never worse than the rules here (the comparison itself is tested in test_agent_pick.py)."""
    monkeypatch.setattr(pipeline.agent_pick, "rules_if_not_worse", lambda *a, **k: None)


@pytest.fixture
def clipped(monkeypatch):
    """After the real ``complete_tiling``, every gable has the converging trapezoid outline (what clipping produced)
    and no ridge fallback (a block that arrives without the flag), so the skeleton refuses it."""
    real = agent_mod.complete_tiling

    def tile(blocks, bs, *a, **k):
        done, pct, notes = real(blocks, bs, *a, **k)
        for b in done:
            if b.form == "gable":
                b.polygon, b.gable_edges, b.ridge_gable = list(TRAPEZOID), [0, 2], False  # no ridge fallback
        return done, pct, notes

    monkeypatch.setattr(agent_mod, "complete_tiling", tile)
    monkeypatch.setattr(agent_mod, "tidy_tiling", lambda done, bs: [])  # the tidy pass would reshape the trapezoid


def test_the_trapezoid_really_cannot_be_built():
    with pytest.raises(ValueError, match="gable edges cannot be extended"):
        block_geometry("gable", TRAPEZOID, PITCH, [0, 2], None)


def test_the_check_is_exactly_the_builders_call():
    rb = RoofBlock(id="b1", form="gable", polygon=list(TRAPEZOID), pitch_rise=PITCH, gable_edges=[0, 2])
    ok = RoofBlock(id="b2", form="hip", polygon=list(TRAPEZOID), pitch_rise=PITCH)
    flat = RoofBlock(id="b3", form="flat", polygon=list(TRAPEZOID))
    assert [b.id for b, _ in agent_repair.unbuildable([rb, ok, flat])] == ["b1"]


# ----------------------------------------------------------------------------- (a) the agent hears about it
def test_the_agent_is_told_at_commit_time_and_corrects_itself(clipped):
    client = Client(GABLE, HIP)
    res = run_agent(hip_rectangle(), kind="lidar", client=client)
    assert client.calls == 2 and [b.form for b in res.blocks] == ["hip"]
    err = json.loads(client.results[0][0]["content"])["error"]
    assert client.results[0][0]["is_error"] is True
    assert "polygon footprint" in err and "gable edges 0,2" in err
    assert "choose other gable_edges" in err and "rect_fit" in err and "make it a hip" in err
    first_turn = res.transcript[1]["tool_results"][0]
    assert first_turn["name"] == "finalize" and "error" in first_turn["result"]  # the transcript says so too
    assert not any("could not be used" in n for n in res.notes + res.warnings)  # nothing was repaired


# ----------------------------------------------------------------------------- (b) per-block repair
def test_on_the_last_round_a_gable_that_cannot_be_built_becomes_a_hip(clipped):
    client = Client(GABLE)
    res = run_agent(hip_rectangle(), kind="lidar", client=client, max_rounds=1)
    hips = [b for b in res.blocks if b.form == "hip"]
    assert len(hips) == 1 and hips[0].gable_edges == [] and hips[0].confidence == "low"
    assert any("drawn as a hip" in n for n in hips[0].notes)
    assert any("drawn as a hip" in n for n in res.warnings) and any("drawn as a hip" in n for n in res.notes)
    assert agent_repair.unbuildable(res.blocks) == []
    assert hips[0].ridge_azimuth_deg is not None


def test_a_repaired_agent_result_builds_a_valid_model(clipped):
    res = run_agent(hip_rectangle(), kind="lidar", client=Client(GABLE), max_rounds=1)
    validate(build_model(hip_rectangle(), res.blocks, {"method": "lidar_agent"}))


def test_a_block_that_stays_unbuildable_raises_model_error_for_the_pipeline(clipped):
    sliver = RoofBlock(id="b1", form="hip", polygon=[(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)], pitch_rise=PITCH)
    with pytest.raises(ModelError, match="block b1"):
        agent_repair.repair_blocks([sliver])


# ----------------------------------------------------------------------------- (c) the pipeline's rungs
def blocks_path(tmp_path):
    p = tmp_path / "blocks.json"
    hip_rectangle().save(p)
    return p


def run(tmp_path, client, **kw):
    return pipeline.run_pipeline("100 Example Ave, Sampletown, CA 90000", tmp_path / "out", "lidar_agent",
                                 blocks_path=blocks_path(tmp_path), client=client, verify=False, render=False, **kw)


def test_the_code_is_a_known_warning_code():
    assert CODE in WARNING_CODES


def test_rung_1_repair_keeps_the_agent_result_and_says_so(tmp_path, clipped, agent_wins, no_planes_model):
    res = run(tmp_path, Client(GABLE), max_rounds=1)
    assert res.method_used == "lidar_agent" and res.model["source"]["method"] == "lidar_agent"
    notes = res.model["confidence"]["notes"]
    assert any("drawn as a hip" in n for n in notes)
    assert CODE not in res.envelope["warning_codes"]  # the agent's answer stands, with a note, not a fallback


def test_rung_2_a_repair_that_fails_gives_the_rule_result(tmp_path, clipped, monkeypatch):
    rules = pipeline.run_pipeline("x", tmp_path / "rules", "lidar_skeleton", blocks_path=blocks_path(tmp_path),
                                  verify=False, render=False)

    def refuse(blocks):
        raise ModelError("block b1: still cannot be built")

    monkeypatch.setattr(agent_mod, "repair_blocks", refuse)
    res = run(tmp_path, Client(GABLE), max_rounds=1)
    assert res.method_used == "lidar_skeleton" and CODE in res.envelope["warning_codes"]
    assert res.envelope["totals"] == rules.envelope["totals"]
    assert "still cannot be built" in res.envelope["warnings"][res.envelope["warning_codes"].index(CODE)]


def test_rung_3_when_the_rules_fail_too_the_planes_only_envelope_answers(tmp_path, clipped, monkeypatch, no_planes_model):
    def refuse(blocks):
        raise ModelError("block b1: still cannot be built")

    real_build = pipeline.build_model
    seen = []

    def build(bs, rbs, source, cls):
        seen.append(len(rbs))
        if rbs:
            raise ValueError("gable edges cannot be extended on this outline")  # a plain ValueError, not ModelError
        return real_build(bs, rbs, source, cls)

    monkeypatch.setattr(agent_mod, "repair_blocks", refuse)
    monkeypatch.setattr(pipeline, "build_model", build)
    res = run(tmp_path, Client(GABLE), max_rounds=1)
    assert res.model["source"].get("planes_only") is True and CODE in res.envelope["warning_codes"]
    assert "model_failed" in res.envelope["model"]["quality"]["reasons"]
    validate(res.model)


def test_a_plain_value_error_from_build_model_no_longer_escapes(tmp_path, monkeypatch):
    """The original crash: a plain ValueError (not a ModelError) from the builder after the agent finished."""
    real = pipeline.build_model
    calls = []

    def build(bs, rbs, source, cls):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("gable edges cannot be extended on this outline (the sides next to a gable end converge)")
        return real(bs, rbs, source, cls)

    monkeypatch.setattr(pipeline, "build_model", build)
    res = run(tmp_path, Client(HIP))
    assert len(calls) == 2 and res.method_used == "lidar_skeleton" and CODE in res.envelope["warning_codes"]


def test_the_scripted_agent_without_trouble_is_untouched(tmp_path, agent_wins):
    res = run(tmp_path, Client(HIP))
    assert res.method_used == "lidar_agent" and CODE not in res.envelope["warning_codes"]
    assert [b["form"] for b in res.model["blocks"]] == ["hip"]


# ----------------------------------------------------------------------------- the ridge-line gable (the cure)
def test_the_ridge_gable_builds_the_outline_the_skeleton_refuses():
    geom = block_geometry("gable", TRAPEZOID, PITCH, [0, 2], None, ridge_fallback=True)
    assert len(geom["facets"]) == 2 and geom["notes"] and "ridge line" in geom["notes"][0]
    assert sum(f["plan_area"] for f in geom["facets"]) == pytest.approx(Polygon(TRAPEZOID).area, rel=1e-6)
    kinds = {e["type"] for e in geom["edges"]}
    assert kinds == {"eave", "rake", "ridge"}
    assert {round(f["aspect_deg"]) % 360 for f in geom["facets"]} == {90, 270}  # edges 0 and 2 are the gable ends (south, north): the ridge runs N-S


def test_the_ridge_gable_is_off_unless_asked():
    with pytest.raises(ValueError, match="gable edges cannot be extended"):
        block_geometry("gable", TRAPEZOID, PITCH, [0, 2], None)


def test_the_ridge_gable_matches_the_skeleton_gable_on_a_rectangle():
    """Where the skeleton works, the two constructions agree: same ridge, rakes, eaves and roof area."""
    rect = [(0.0, 0.0), (40.0, 0.0), (40.0, 24.0), (0.0, 24.0)]
    from roof_measure.skeleton import hip_roof_edges
    from roof_measure.skeleton_gable import ridge_gable

    a = hip_roof_edges(rect, PITCH, {1, 3})["totals"]
    b = ridge_gable(rect, PITCH, {1, 3})["totals"]
    for k in ("eaves_ft", "rakes_ft", "ridges_ft", "hips_ft", "valleys_ft", "facet_area_sqft", "plan_area_sqft"):
        assert b[k] == pytest.approx(a[k], rel=1e-6), k


def test_a_jagged_outline_with_a_gable_builds_through_the_whole_model():
    ring = [(0.0, 0.0), (40.0, 0.0), (40.5, 12.0), (38.0, 12.2), (38.2, 24.0), (1.0, 23.0), (0.0, 12.0)]
    rb = RoofBlock(id="b1", form="gable", polygon=ring, pitch_rise=PITCH, gable_edges=[1, 4, 5, 6], ridge_gable=True)
    assert agent_repair.unbuildable([rb]) == []
