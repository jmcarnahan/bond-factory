"""Snapping must survive noisy LiDAR: seeded jittered copies of the fixtures all give planes that satisfy every invariant."""

from __future__ import annotations

import logging

import pytest
from quality_helpers import SITE1, SITE1_HANDMADE, TWO_LEVEL, hip_rectangle, invariant_problems, jittered

from roof_measure import planes_gaps, planes_tidy
from roof_measure.classify import BlockSet
from roof_measure.planes import snap_planes, snap_with_stats

SEEDS = 15  # 50 for a full sweep by hand: `SEEDS = 50`; 15 keeps the committed test under 30 s
FIXTURES = {"site1": SITE1, "two_level": TWO_LEVEL, "handmade": SITE1_HANDMADE}


@pytest.mark.parametrize("sigma", [0.1, 0.3])
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_jittered_copies_all_snap_and_keep_the_invariants(name, sigma, caplog):
    bs = BlockSet.load(FIXTURES[name])
    problems = {}
    with caplog.at_level(logging.WARNING, logger="roof_measure.planes"):
        for seed in range(SEEDS):
            j = jittered(bs, sigma, seed)
            res = snap_with_stats(j, clip_to_footprint=True)
            bad = ["snapping failed"] if res.failed else invariant_problems(j, res.planes)
            if bad:
                problems[seed] = bad[:2]
    assert not problems, problems
    assert not caplog.records, [r.message for r in caplog.records][:3]  # no swallowed error, no fallback used


@pytest.mark.parametrize("name", ["two_level", "handmade"])
def test_heavy_jitter_keeps_overlap_and_coverage(name):
    bs = BlockSet.load(FIXTURES[name])
    for seed in range(20):
        j = jittered(bs, 0.5, seed)
        res = snap_with_stats(j, clip_to_footprint=True)
        assert not res.failed and not [p for p in invariant_problems(j, res.planes) if "overlap" in p or "union" in p]


def test_a_gap_split_that_raises_falls_back_to_the_longest_border_plane(monkeypatch, caplog):
    from shapely.errors import GEOSException

    def boom(*a, **k):
        raise GEOSException("TopologyException: side location conflict")

    monkeypatch.setattr(planes_gaps, "_split_by_nearest", boom)
    bs = hip_rectangle()  # the eave strip all round is a gap shared by four planes: the split path
    with caplog.at_level(logging.WARNING, logger="roof_measure.planes"):
        planes = snap_planes(bs, clip_to_footprint=True)
    assert len(planes) == 4 and not invariant_problems(bs, planes)
    assert any("gap split failed" in r.message for r in caplog.records)


def test_a_gap_that_cannot_be_assigned_stays_uncovered_and_the_rest_survives(monkeypatch, caplog):
    from shapely.errors import GEOSException

    real = planes_gaps._pieces_for
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GEOSException("TopologyException")
        return real(*a, **k)

    monkeypatch.setattr(planes_gaps, "_pieces_for", flaky)
    with caplog.at_level(logging.WARNING, logger="roof_measure.planes"):
        res = snap_with_stats(hip_rectangle(), clip_to_footprint=True)
    assert not res.failed and len(res.planes) == 4
    assert any("could not be assigned" in r.message for r in caplog.records)


def test_a_weld_that_fails_keeps_the_plane_unwelded_and_says_so(monkeypatch, caplog):
    real = planes_tidy._drop_spikes
    state = {"first": True}

    def kill_first(pts):
        if state["first"]:
            state["first"] = False
            return []  # the welded ring of the first plane collapses
        return real(pts)

    monkeypatch.setattr(planes_tidy, "_drop_spikes", kill_first)
    bs = hip_rectangle()
    with caplog.at_level(logging.WARNING, logger="roof_measure.planes"):
        planes = snap_planes(bs, clip_to_footprint=True)
    assert len(planes) == 4 and all(p.shape().is_valid for p in planes)
    assert any("kept unwelded" in r.message for r in caplog.records)
    assert max(p.shape().intersection(q.shape()).area for p in planes for q in planes if p is not q) <= 0.5


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_jittered_copies_with_the_envelope_partition_on_keep_a_valid_tiling(name):
    """The default path (planes_envelope may replace the straightened planes): no exception, planes tile, none overlap."""
    bs = BlockSet.load(FIXTURES[name])
    for seed in range(5):
        j = jittered(bs, 0.2, seed)
        res = snap_with_stats(j, clip_to_footprint=True)
        assert not res.failed and res.planes
        assert not [p for p in invariant_problems(j, res.planes) if "overlap" in p or "union" in p or "valid" in p]


def test_a_gap_is_split_between_planes_even_when_one_plane_is_in_two_pieces():
    """A cluster with a bare patch can reach the gap splitter as a MultiPolygon: it used to raise AttributeError."""
    from shapely.geometry import MultiPolygon, Polygon

    from roof_measure import planes_gaps

    left = MultiPolygon([Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]), Polygon([(0, 6), (4, 6), (4, 10), (0, 10)])])
    right = Polygon([(6, 0), (10, 0), (10, 10), (6, 10)])
    gap = Polygon([(4, 0), (6, 0), (6, 10), (4, 10)])
    out = planes_gaps._split_by_nearest(gap, [left, right], [0, 1])
    assert set(out) == {0, 1} and abs(sum(g.area for g in out.values()) - gap.area) < 0.5
