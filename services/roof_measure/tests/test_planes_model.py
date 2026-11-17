"""A model built straight from the measured planes: edge types and closed-form lengths on synthetic roofs.

Invented frames only. Planes are ``planes.Plane``-shaped objects (polygon, pitch, aspect, height at the centroid,
optional ``plane_eq``); the helpers derive heights from the roof geometry so shared edges agree.
"""

from __future__ import annotations

import math
from types import SimpleNamespace as NS

import pytest
from quality_helpers import TWO_LEVEL, hip_rectangle
from shapely.geometry import Polygon

from roof_measure import pipeline, planes_model
from roof_measure.classify import BlockSet
from roof_measure.model import validate
from roof_measure.planes_model import model_from_planes, planes_model_ok
from roof_measure.skeleton import hip_roof_edges


def plane(pid, ring, pitch, aspect, z_at):
    """A plane over ``ring``; ``z_at(x, y)`` gives the surface height there (taken at the centroid)."""
    poly = Polygon(ring)
    c = poly.centroid
    sf = math.sqrt(1 + (pitch / 12) ** 2)
    return NS(id=pid, polygon=[list(p) for p in ring], pitch_rise=pitch, aspect_deg=aspect, height_ft=z_at(c.x, c.y),
              plan_area_sqft=poly.area, surface_area_sqft=poly.area * sf, plane_eq=None)


def build(planes, fp):
    m = model_from_planes(planes, Polygon(fp), {"method": "lidar_skeleton"})
    validate(m)
    return m


def lengths(m):
    return {k: v for k, v in m["totals"]["lengths_ft"].items() if v}


def counts(m):
    out = {}
    for e in m["edges"]:
        out[e["type"]] = out.get(e["type"], 0) + 1
    return out


def test_a_gable_from_two_planes():
    fp = [(0, 0), (40, 0), (40, 24), (0, 24)]
    s = 6 / 12
    south = plane("a", [(0, 0), (40, 0), (40, 12), (0, 12)], 6, 180.0, lambda x, y: s * y)
    north = plane("b", [(0, 12), (40, 12), (40, 24), (0, 24)], 6, 0.0, lambda x, y: s * (24 - y))
    m = build([south, north], fp)
    assert len(m["facets"]) == 2 and counts(m) == {"ridge": 1, "eave": 2, "rake": 4}
    t = m["totals"]["lengths_ft"]
    assert t["ridge"] == pytest.approx(40.0) and t["eave"] == pytest.approx(80.0)
    assert t["rake"] == pytest.approx(4 * math.hypot(12.0, 6.0), rel=1e-3)
    assert m["source"]["from_planes"] is True and all(b["form"] == "shed" for b in m["blocks"])
    ok, why = planes_model_ok(m, [south, north], Polygon(fp))
    assert ok, why


def test_a_hip_from_four_planes_matches_the_skeleton():
    ring = [(0.0, 0.0), (40.0, 0.0), (40.0, 24.0), (0.0, 24.0)]
    sk = hip_roof_edges(ring, 6.0)
    planes = []
    for i, f in enumerate(sk["facets"]):
        c0, c1, c2 = f["plane"]
        p = plane(f"k{i}", f["polygon_xy"], 6, f["aspect_deg"], lambda x, y, c=(c0, c1, c2): c[0] + c[1] * x + c[2] * y)
        p.plane_eq = [c1, c2, c0]
        planes.append(p)
    m = build(planes, ring)
    want, got = sk["totals"], m["totals"]["lengths_ft"]
    for ours, theirs in (("eave", "eaves_ft"), ("hip", "hips_ft"), ("ridge", "ridges_ft")):
        assert got[ours] == pytest.approx(want[theirs], rel=0.01), ours
    assert counts(m) == {"eave": 4, "hip": 4, "ridge": 1}
    assert m["totals"]["total_area_sqft"] == pytest.approx(want["facet_area_sqft"], rel=0.01)


def test_an_l_shaped_hip_has_a_valley():
    ring = [(0.0, 0.0), (40.0, 0.0), (40.0, 16.0), (16.0, 16.0), (16.0, 40.0), (0.0, 40.0)]
    sk = hip_roof_edges(ring, 6.0)
    planes = []
    for i, f in enumerate(sk["facets"]):
        c0, c1, c2 = f["plane"]
        p = plane(f"k{i}", f["polygon_xy"], 6, f["aspect_deg"], lambda x, y, c=(c0, c1, c2): c[0] + c[1] * x + c[2] * y)
        p.plane_eq = [c1, c2, c0]
        planes.append(p)
    m = build(planes, ring)
    got, want = m["totals"]["lengths_ft"], sk["totals"]
    assert got["valley"] > 5 and got["valley"] == pytest.approx(want["valleys_ft"], rel=0.02)
    assert got["hip"] == pytest.approx(want["hips_ft"], rel=0.02) and got["ridge"] == pytest.approx(want["ridges_ft"], rel=0.02)


def test_a_two_level_house_has_a_wall_and_a_step():
    """Low plane in front (south), a plane 5 ft higher behind it, and a plane 5 ft higher beside it: wall + step."""
    s = 4.8 / 12
    fp = [(0, 0), (20, 0), (20, 20), (0, 20)]
    low = plane("low", [(0, 0), (10, 0), (10, 10), (0, 10)], 4.8, 180.0, lambda x, y: s * y)
    behind = plane("behind", [(0, 10), (10, 10), (10, 20), (0, 20)], 4.8, 180.0, lambda x, y: 9 + s * (y - 10))
    beside = plane("beside", [(10, 0), (20, 0), (20, 10), (10, 10)], 4.8, 180.0, lambda x, y: 5 + s * y)
    m = build([low, behind, beside], [(0, 0), (20, 0), (20, 20), (0, 20)][:4] if False else fp)
    t = m["totals"]["lengths_ft"]
    assert t["wall_flashing"] == pytest.approx(10.0)  # the low plane's top against the higher plane behind it
    assert t["step_flashing"] == pytest.approx(math.hypot(10.0, s * 10), rel=1e-3)  # along the low plane's slope


def test_an_off_centre_ridge_with_unequal_pitches():
    """The case the skeleton cannot draw: ridge at y = 10 on a 25 ft deep roof, 4.8/12 south and 3.2/12 north."""
    fp = [(0, 0), (40, 0), (40, 25), (0, 25)]
    south = plane("s", [(0, 0), (40, 0), (40, 10), (0, 10)], 4.8, 180.0, lambda x, y: 0.4 * y)
    north = plane("n", [(0, 10), (40, 10), (40, 25), (0, 25)], 3.2, 0.0, lambda x, y: (4 / 15) * (25 - y))
    m = build([south, north], fp)
    t = m["totals"]["lengths_ft"]
    assert counts(m) == {"ridge": 1, "eave": 2, "rake": 4}
    assert t["ridge"] == pytest.approx(40.0) and t["eave"] == pytest.approx(80.0)
    assert t["rake"] == pytest.approx(2 * math.hypot(10, 4) + 2 * math.hypot(15, 4), rel=1e-3)
    ridge = next(e for e in m["edges"] if e["type"] == "ridge")
    assert {round(p[1], 3) for p in ridge["points"]} == {10.0}
    assert m["totals"]["total_area_sqft"] == pytest.approx(400 * math.hypot(1, 0.4) + 600 * math.hypot(1, 4 / 15), rel=1e-6)


def test_a_valley_between_planes_that_fall_toward_each_other():
    fp = [(0, 0), (40, 0), (40, 20), (0, 20)]
    west = plane("w", [(0, 0), (20, 0), (20, 20), (0, 20)], 6, 90.0, lambda x, y: 0.5 * (20 - x))  # falls east
    east = plane("e", [(20, 0), (40, 0), (40, 20), (20, 20)], 6, 270.0, lambda x, y: 0.5 * (x - 20))  # falls west
    m = build([west, east], fp)
    assert counts(m)["valley"] == 1 and m["totals"]["lengths_ft"]["valley"] == pytest.approx(20.0)


# ----------------------------------------------------------------------------- the gate
def gable_planes():
    s = 0.5
    return ([plane("a", [(0, 0), (40, 0), (40, 12), (0, 12)], 6, 180.0, lambda x, y: s * y),
             plane("b", [(0, 12), (40, 12), (40, 24), (0, 24)], 6, 0.0, lambda x, y: s * (24 - y))],
            [(0, 0), (40, 0), (40, 24), (0, 24)])


def test_the_gate_names_a_missing_plane_an_overlap_and_a_wrong_area():
    planes, fp = gable_planes()
    full = build(planes, fp)
    gap = build(planes[:1], fp)
    assert "coverage" in " ".join(planes_model_ok(gap, planes[:1], Polygon(fp))[1])
    over = [planes[0], plane("b", [(0, 10), (40, 10), (40, 24), (0, 24)], 6, 0.0, lambda x, y: 0.5 * (24 - y))]
    assert any("overlap" in r for r in planes_model_ok(build(over, fp), over, Polygon(fp))[1])
    assert any("area" in r for r in planes_model_ok(full, [NS(surface_area_sqft=1.0)], Polygon(fp))[1])


# ----------------------------------------------------------------------------- the pipeline
@pytest.fixture
def partition(monkeypatch):
    """The snapped planes carry ``straighten_method`` 'envelope' and a section (what planes_envelope sets)."""
    from roof_measure import planes

    real = planes.snap_with_stats

    def snap(*a, **k):
        res = real(*a, **k)
        for p in res.planes:
            p.straighten_method, p.section = "envelope", 0
        return res

    monkeypatch.setattr(planes, "snap_with_stats", snap)


def run(tmp_path, path, **kw):
    return pipeline.run_pipeline("x", tmp_path / "out", "lidar_skeleton", blocks_path=path, verify=False, render=False, **kw)


def test_two_level_l_under_the_new_rules(tmp_path, partition):
    """mismatch 37 and uncovered 26 on the block model: replaced when its planes come from the partition and pass both gates."""
    res = run(tmp_path, TWO_LEVEL)
    m = res.model
    if m["source"].get("from_planes"):
        q = m["quality"]
        assert q["reasons"][0] == "from_planes" and q["block_model_mismatch_pct"] == pytest.approx(38.8, abs=0.2)  # was 37.4: the planes the block model is compared with changed (partition planes)
        assert q["block_model_uncovered_pct"] == pytest.approx(26.1, abs=0.2) and q["plane_mismatch_pct"] < 5
        assert res.envelope["verification"]["verdict"] == "unverified" and res.method_used == "lidar_skeleton"
        i = next(i for i, w in enumerate(res.envelope["warnings"]) if "built from the measured roof planes" in w)
        assert res.envelope["warning_codes"][i] in (planes_model.CODE, "other")
    else:  # the replacement gate refused it: the block model stays untouched
        assert m["quality"]["plane_mismatch_pct"] > 15


def test_planes_without_the_partition_never_replace_a_block_model(tmp_path, monkeypatch):
    from roof_measure import planes_envelope

    monkeypatch.setattr(planes_envelope, "envelope_planes", lambda *a, **k: None)  # its gate failed: fallback planes
    res = run(tmp_path, TWO_LEVEL)  # planes straightened in place (no straighten_method)
    assert "from_planes" not in res.model["source"] and res.model["quality"]["plane_mismatch_pct"] > 15


def test_a_good_block_model_is_left_alone(tmp_path, partition):
    p = tmp_path / "b.json"
    hip_rectangle().save(p)
    res = run(tmp_path, p)
    assert "from_planes" not in res.model["source"] and "from_planes" not in res.model["quality"]["reasons"]


def _fake(monkeypatch, mismatch, uncovered, method="envelope"):
    """replace_if_bad on the rectangle's planes with the block model's metrics faked."""
    from roof_measure import quality

    monkeypatch.setattr(quality, "plane_metrics", lambda *a, **k: {"plane_mismatch_pct": mismatch, "model_uncovered_pct": uncovered})
    bs = hip_rectangle()
    from roof_measure import planes

    real = planes.snap_with_stats

    def snap(*a, **k):
        res = real(*a, **k)
        for p in res.planes:
            p.straighten_method, p.section = method, 0
        return res

    monkeypatch.setattr(planes, "snap_with_stats", snap)
    return bs


@pytest.mark.parametrize("mismatch, uncovered, replaced", [(10.0, 5.0, False), (14.9, 9.9, False), (15.0, 5.0, True), (5.0, 10.0, True)])
def test_the_thresholds_are_15_mismatch_or_10_uncovered(monkeypatch, mismatch, uncovered, replaced):
    bs = _fake(monkeypatch, mismatch, uncovered)
    out = planes_model.replace_if_bad(bs, {"facets": []}, {}, False, [])
    assert (out is not None) is replaced
    if replaced:
        assert out[1] == {"block_model_mismatch_pct": mismatch, "block_model_uncovered_pct": uncovered}


def test_only_the_partition_may_replace_but_planes_only_takes_any_planes(monkeypatch):
    from roof_measure import planes_envelope

    monkeypatch.setattr(planes_envelope, "envelope_planes", lambda *a, **k: None)
    bs = _fake(monkeypatch, 90.0, 50.0, method=None)
    assert planes_model.replace_if_bad(bs, {"facets": []}, {}, False, []) is None
    out = planes_model.replace_if_bad(bs, {"facets": []}, {}, True, [])  # the planes-only exception
    assert out is not None and out[1] == {"block_model_mismatch_pct": None, "block_model_uncovered_pct": None}


def _model(edges, disagreement=0.0):
    return {"edges": [{"type": t, "length_ft": n, "facets": f} for t, n, f in edges],
            "debug": {"typing_disagreement": disagreement}}


def test_the_replacement_gate_rules():
    gate = planes_model.replacement_gate
    ok = [("ridge", 20, ["f1", "f2"]), ("eave", 20, ["f1"])]
    assert gate(_model(ok), []) == []
    assert any("unspecified" in w for w in gate(_model(ok + [("unspecified", 1, ["f1", "f2"])]), []))
    assert any("transition" in w for w in gate(_model(ok + [("transition", 5, ["f1", "f2"])]), []))  # 5 of 25
    assert gate(_model(ok + [("transition", 1, ["f1", "f2"])]), []) == []  # 1 of 21
    assert gate(_model(ok + [("transition", 3, ["f1", "f2"])]), []) == []  # 3 of 23: one tapering step on a small house
    assert any("no ridge" in w for w in gate(_model([("eave", 20, ["f1"]), ("valley", 5, ["f1", "f2"])]), []))
    assert gate(_model(ok, disagreement=0.15), []) == []
    assert any("disagrees" in w for w in gate(_model(ok, disagreement=0.16), []))


# ----------------------------------------------------------------------------- one edge per segment, kinds from the envelope
def three_planes_one_valley():
    """Two south-facing planes side by side (a seam between them) above one north-facing plane: ONE valley along y = 20."""
    fp = [(0, 0), (40, 0), (40, 40), (0, 40)]
    s = 0.5
    low = plane("low", [(0, 0), (40, 0), (40, 20), (0, 20)], 6, 0.0, lambda x, y: s * (20 - y) + 0.0)  # falls north
    low.plane_eq = [0.0, -s, s * 20]
    w = plane("w", [(0, 20), (20, 20), (20, 40), (0, 40)], 6, 180.0, lambda x, y: s * (y - 20))  # falls south to y=20
    w.plane_eq = [0.0, s, -s * 20]
    e = plane("e", [(20, 20), (40, 20), (40, 40), (20, 40)], 6, 180.0, lambda x, y: s * (y - 20))
    e.plane_eq = [0.0, s, -s * 20]
    return [low, w, e], fp


def test_a_long_valley_is_one_edge_per_segment_even_with_a_seam_in_the_upper_planes():
    planes, fp = three_planes_one_valley()
    borders = [{"a": "w", "b": "e", "segment": [[20, 20], [20, 40]], "kind": "seam"},
               {"a": "low", "b": "w", "segment": [[0, 20], [20, 20]], "kind": "valley"},
               {"a": "low", "b": "e", "segment": [[20, 20], [40, 20]], "kind": "valley"}]
    m = model_from_planes(planes, Polygon(fp), {"method": "lidar_skeleton"}, borders=borders)
    validate(m)
    valleys = [e for e in m["edges"] if e["type"] == "valley"]
    assert sum(e["length_ft"] for e in valleys) == pytest.approx(40.0)  # once, not twice
    assert not any(e["type"] in ("ridge", "transition") for e in m["edges"] if len(e["facets"]) == 2)  # the seam draws nothing
    assert m["debug"]["typing_disagreement"] == 0.0
    # no segment of the interior is emitted twice
    segs = sorted((tuple(sorted(map(tuple, e["points"]))), e["type"]) for e in m["edges"])
    assert len(segs) == len(set(segs))
    # without borders the same geometry gives the same valley from heights alone
    m2 = model_from_planes(planes, Polygon(fp), {"method": "lidar_skeleton"})
    assert m2["totals"]["lengths_ft"]["valley"] == pytest.approx(40.0)


def test_the_envelope_kind_wins_and_a_disagreement_is_measured():
    planes, fp = three_planes_one_valley()
    borders = [{"a": "low", "b": "w", "segment": [[0, 20], [20, 20]], "kind": "ridge"},  # wrong on purpose
               {"a": "low", "b": "e", "segment": [[20, 20], [40, 20]], "kind": "valley"}]
    m = model_from_planes(planes, Polygon(fp), {"method": "lidar_skeleton"}, borders=borders)
    inner = {t: sum(e["length_ft"] for e in m["edges"] if len(e["facets"]) == 2 and e["type"] == t) for t in ("ridge", "valley")}
    assert inner == {"ridge": pytest.approx(20.0), "valley": pytest.approx(20.0)}  # the envelope's word is drawn
    assert m["debug"]["typing_disagreement"] == pytest.approx(20.0 / (40.0 + math.hypot(20.0, 10.0)), rel=1e-3)  # 20 ft of the interior (incl. the seam) disagree


def test_a_notch_on_the_low_side_of_a_plane_is_an_eave():
    """A north-facing plane whose northern outline has a notch: every outer edge on that side faces down the slope."""
    s = 0.5
    ring = [(0, 0), (40, 0), (40, 30), (28, 30), (28, 27), (10, 27), (10, 30), (0, 30)]
    pl = plane("a", ring, 6, 0.0, lambda x, y: s * (30 - y) + 0.0)
    pl.plane_eq = [0.0, -s, s * 30]  # falls north
    m = model_from_planes([pl], Polygon(ring), {"method": "lidar_skeleton"})
    by = {}
    for e in m["edges"]:
        (_x1, y1), (_x2, y2) = e["points"]
        if abs(y1 - y2) < 1e-6 and y1 >= 27:
            by[round(y1)] = by.get(round(y1), 0) + 1
            assert e["type"] == "eave", e
    assert by == {30: 2, 27: 1}  # both y=30 stubs and the notch floor are eaves
    assert m["totals"]["lengths_ft"]["ridge"] == pytest.approx(40.0)  # the high (south) edge of a single plane


def test_step_flashing_along_the_lower_slope_and_wall_flashing_across_it():
    s = 0.4
    fp = [(0, 0), (20, 0), (20, 20), (0, 20)]
    low = plane("low", [(0, 0), (10, 0), (10, 10), (0, 10)], 4.8, 180.0, lambda x, y: s * y)
    low.plane_eq = [0.0, s, 0.0]
    behind = plane("behind", [(0, 10), (10, 10), (10, 20), (0, 20)], 4.8, 180.0, lambda x, y: 9 + s * (y - 10))
    behind.plane_eq = [0.0, s, 5.0]
    beside = plane("beside", [(10, 0), (20, 0), (20, 10), (10, 10)], 4.8, 180.0, lambda x, y: 5 + s * y)
    beside.plane_eq = [0.0, s, 5.0]
    borders = [{"a": "low", "b": "behind", "segment": [[0, 10], [10, 10]], "kind": "step"},
               {"a": "low", "b": "beside", "segment": [[10, 0], [10, 10]], "kind": "step"}]
    m = model_from_planes([low, behind, beside], Polygon(fp), {"method": "lidar_skeleton"}, borders=borders)
    t = m["totals"]["lengths_ft"]
    assert t["wall_flashing"] == pytest.approx(10.0)  # across the low plane's slope, at its high side
    assert t["step_flashing"] == pytest.approx(math.hypot(10.0, s * 10), rel=1e-3)  # along it


def test_a_planes_model_error_leaves_the_block_model_as_it_was(tmp_path, monkeypatch, partition):
    def boom(*a, **k):
        raise ValueError("no")

    monkeypatch.setattr(planes_model, "model_from_planes", boom)
    res = run(tmp_path, TWO_LEVEL)
    assert "from_planes" not in res.model["source"]


def test_without_blocks_there_is_no_planes_model():
    bs = BlockSet.load(TWO_LEVEL)
    bs.blocks = []
    assert planes_model.replace_if_bad(bs, {"facets": []}, {}, True, []) is None


def test_planes_only_is_replaced_by_any_planes_and_keeps_model_failed(tmp_path, monkeypatch):
    """The relay: planes-only stays planes-only when the gate fails; when it passes (any planes) the model has facets,
    is flagged from_planes, is not verified, and the warning model_failed is kept beside model_from_planes."""
    import spike_cases

    from roof_measure.classify import Classification

    rb = spike_cases.roof_block(spike_cases.UNFIXABLE)
    monkeypatch.setattr(pipeline, "classify_blocks", lambda bs, **kw: Classification(blocks=[rb]))
    p = tmp_path / "b.json"
    hip_rectangle().save(p)
    with monkeypatch.context() as m:
        m.setattr(planes_model, "planes_model_ok", lambda *a, **k: (False, ["coverage 50% under 95%"]))
        res = run(tmp_path / "a", p)
    assert res.model["source"].get("planes_only") is True and "from_planes" not in res.model["source"]
    assert "model_failed" in res.envelope["warning_codes"]
    res = run(tmp_path / "b", p)
    assert res.model["source"].get("from_planes") is True and not res.model["source"].get("planes_only") and res.model["facets"]
    assert "model_failed" in res.envelope["warning_codes"]  # kept
    assert res.model["quality"]["reasons"][0] == "from_planes"
    assert res.envelope["verification"]["verdict"] == "unverified"


def test_a_tapering_height_step_that_the_envelope_calls_a_hip_is_a_transition():
    """0 ft at one end of the border and 3 ft at the other: median 1.5 ft or more, so not a hip (no cap, no flashing)."""
    fp = [(0, 0), (40, 0), (40, 20), (0, 20)]
    a = plane("a", [(0, 0), (20, 0), (20, 20), (0, 20)], 6, 180.0, lambda x, y: 0.5 * y)
    a.plane_eq = [0.0, 0.5, 0.0]
    b = plane("b", [(20, 0), (40, 0), (40, 20), (20, 20)], 6, 180.0, lambda x, y: 0.5 * y + 0.15 * (40 - x) * 0 + 1.5)
    b.plane_eq = [0.0, 0.5, 1.5]
    for kind, step, want in (("hip", 1.7, "transition"), ("hip", 1.4, "hip"), ("hip", -1.7, "transition")):
        border = [{"a": "a", "b": "b", "segment": [[20, 0], [20, 20]], "kind": kind, "step_ft": step}]
        planes = [a, b]
        a.id, b.id = "a", "b"
        m = model_from_planes(planes, Polygon(fp), {"method": "lidar_skeleton"}, borders=border)
        t = m["totals"]["lengths_ft"]
        assert (t["transition"] > 0, t["hip"] > 0) == (want == "transition", want == "hip"), (step, t)
        if want == "transition":
            assert t["step_flashing"] == 0 and t["wall_flashing"] == 0 and t["hip"] == 0


def test_a_scripted_agent_roof_at_15_2_mismatch_is_replaced_by_the_planes_model(tmp_path, monkeypatch):
    """The owner's HOUSE case: the agent's roof scored 15.2, the partition planes tile the roof: the planes model answers."""
    from types import SimpleNamespace as NS

    from roof_measure import agent_pick, quality

    monkeypatch.setattr(agent_pick, "rules_if_not_worse", lambda *a, **k: None)  # the agent wins over the rules
    real = quality.plane_metrics
    monkeypatch.setattr(quality, "plane_metrics", lambda *a, **k: {**real(*a, **k), "plane_mismatch_pct": 15.2})

    class Client:
        def __init__(self):
            self.messages = NS(create=self._create)

        def _create(self, **kw):
            blk = {"polygon_id": "footprint", "form": "hip", "pitch_rise": 4.0, "confidence": "high", "evidence": []}
            return NS(content=[NS(type="tool_use", id="t1", name="finalize", input={"blocks": [blk]})],
                      stop_reason="tool_use", usage=NS(input_tokens=1, output_tokens=1))

    p = tmp_path / "b.json"
    hip_rectangle().save(p)
    res = pipeline.run_pipeline("x", tmp_path / "out", "lidar_agent", blocks_path=p, client=Client(), verify=False, render=False)
    assert res.model["source"].get("from_planes") is True and res.method_used == "lidar_agent"
    assert res.model["quality"]["reasons"][0] == "from_planes"


# ----------------------------------------------------------------------------- review fixes (bf-complex)
HOURGLASS = [(0, 0), (10, 0), (5.2, 5), (10, 10), (0, 10), (4.8, 5)]  # valid; snapping pinches its 0.4 ft neck shut


def _hourglass_plane():
    from roof_measure.planes import Plane

    poly = Polygon(HOURGLASS)
    return Plane(id="hg", polygon=[list(p) for p in HOURGLASS], pitch_rise=6.0, aspect_deg=180.0,
                 plan_area_sqft=poly.area, surface_area_sqft=poly.area * math.hypot(1, 0.5), height_ft=2.5, rms_ft=0.1,
                 filled_pct=0.0, raw_plan_area_sqft=poly.area, plane_eq=[0.0, 0.5, 0.0])


def test_a_plane_pinched_into_two_parts_builds_from_its_largest_part():
    m = model_from_planes([_hourglass_plane()], Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]))
    assert len(m["facets"]) == 1 and 20.0 < m["facets"][0]["plan_area_sqft"] <= Polygon(HOURGLASS).area


@pytest.fixture
def hourglass_snap(monkeypatch):
    """Snapping returns the hourglass plane (as the planes-only branch accepts any planes)."""
    from roof_measure import planes

    real = planes.snap_with_stats

    def snap(*a, **k):
        res = real(*a, **k)
        res.planes = [_hourglass_plane()]
        return res

    monkeypatch.setattr(planes, "snap_with_stats", snap)


def test_replace_if_bad_never_raises(monkeypatch, hourglass_snap):
    bs = hip_rectangle()
    planes_model.replace_if_bad(bs, {"facets": []}, {}, True, [])  # the pinched plane: no AttributeError
    monkeypatch.setattr(planes_model, "model_from_planes", lambda *a, **k: (_ for _ in ()).throw(AttributeError("x")))
    assert planes_model.replace_if_bad(bs, {"facets": []}, {}, True, []) is None


def test_a_pinched_plane_never_fails_the_pipeline(tmp_path, monkeypatch, hourglass_snap):
    import spike_cases

    from roof_measure.classify import Classification

    monkeypatch.setattr(pipeline, "classify_blocks",
                        lambda bs, **kw: Classification(blocks=[spike_cases.roof_block(spike_cases.UNFIXABLE)]))
    p = tmp_path / "b.json"
    hip_rectangle().save(p)
    res = run(tmp_path, p)  # planes-only path, then replace_if_bad on the pinched plane
    assert res.envelope["model"]["planes"]


def test_the_model_is_built_from_the_published_planes(tmp_path, partition):
    res = run(tmp_path, TWO_LEVEL)
    m = res.model
    if not m["source"].get("from_planes"):
        pytest.skip("the replacement gate refused this roof")
    assert m["debug"]["plane_ids"] == [p["id"] for p in m["planes"]]
    for f, p in zip(m["facets"], m["planes"], strict=True):
        assert f["plan_area_sqft"] == pytest.approx(p["plan_area_sqft"], abs=1.0)


@pytest.mark.parametrize("name", ["simple_gable_house_blocks.json", "two_level_l_blocks.json"])
def test_a_replaced_model_keeps_fitted_area_and_notes_and_never_gains_confidence(tmp_path, name):
    from quality_helpers import HERE

    res = run(tmp_path, HERE / "fixtures" / name)
    m = res.model
    assert m["source"].get("from_planes")  # both are replaced (poor block models)
    assert m["source"]["lidar"]["fitted_area_sqft"] > 0
    assert m["confidence"]["overall"] in ("low", "medium")
    assert res.envelope["confidence"] <= 0.5  # what 0.3.1 gave these roofs
    assert any("no LiDAR-fitted block" in n for n in m["confidence"]["notes"])


def test_inherit_caps_confidence():
    new = {"source": {"lidar": {}}, "confidence": {"overall": "medium", "notes": ["a"]}}
    planes_model._inherit(new, {"confidence": {"overall": "high", "notes": ["b", "Wall flashing is not derivable x"]}},
                          False)
    assert new["confidence"] == {"overall": "medium", "notes": ["a", "b"]}
    planes_model._inherit(new, {"confidence": {"overall": "low"}}, False)
    assert new["confidence"]["overall"] == "low"
    new["confidence"]["overall"] = "medium"
    planes_model._inherit(new, {"confidence": {"overall": "high"}}, True)
    assert new["confidence"]["overall"] == "low"
