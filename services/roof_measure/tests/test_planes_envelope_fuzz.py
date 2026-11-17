"""Robustness of the envelope partition: random variations of the synthetic roofs (turn, place, cluster shrink and
jitter, bare roof, missing small planes, a broken input) never raise out of ``envelope_planes``, and whatever passes
the gate is a valid tiling of the outline (no overlap, no gap) in reasonable time.
"""

from __future__ import annotations

import math
import random
import time

import pytest
import test_planes_envelope as base
import test_planes_envelope_pins as pins
import test_planes_envelope_steps as steps
from shapely.geometry import Polygon

from roof_measure.planes_envelope import envelope_detail, envelope_planes


def _gable():
    outline, _, facets = base.gable(p1=4.0, p2=6.0)
    return base.roof(outline, facets)


def _hip():
    s, h0 = 0.5, 10.0
    facets = {"s": ([(0, 0), (40, 0), (28, 12), (12, 12)], (0.0, s, h0)),
              "e": ([(40, 0), (40, 24), (28, 12)], (-s, 0.0, h0 + 40 * s)),
              "n": ([(40, 24), (0, 24), (12, 12), (28, 12)], (0.0, -s, h0 + 24 * s)),
              "w": ([(0, 24), (0, 0), (12, 12)], (s, 0.0, h0))}
    return base.roof([(0, 0), (40, 0), (40, 24), (0, 24)], facets)


BUILDERS = [(_gable, base), (_hip, base), (pins.house_like, pins), (pins.commercial_like, pins),
            (steps.two_level_diagonal, steps), (steps.flat_under_a_cross_gable, steps), (steps.angled_wing, steps)]


def _max_shrink(facets) -> float:
    """The largest shrink that leaves every facet a cluster."""
    out = 2.2
    for ring, _ in facets.values():
        g = Polygon(ring)
        while out > 0.3 and g.buffer(-out, join_style=2).area < 3.0:
            out -= 0.2
    return out


def variant(k: int):
    """Case k: a builder with a random turn, place, shrink, jitter, bare patch and maybe a missing plane."""
    rnd = random.Random(1000 + k)
    build, mod = BUILDERS[k % len(BUILDERS)]
    angle, origin = rnd.uniform(0.0, 360.0), (rnd.uniform(-900, 900), rnd.uniform(-900, 900))
    shrink, amp = rnd.uniform(0.4, 2.2), rnd.uniform(0.05, 0.8)
    real_roof, real_jitter = base.roof, base.jitter
    hole = None
    if rnd.random() < 0.5:
        x, y = rnd.uniform(0, 30), rnd.uniform(0, 20)
        hole = Polygon([(x, y), (x + rnd.uniform(4, 14), y), (x + rnd.uniform(4, 14), y + rnd.uniform(4, 12)),
                        (x, y + rnd.uniform(4, 12))]).convex_hull
    missing = rnd.random() < 0.3

    def roof(outline, facets, shrink_=None, drop=None, **kw):
        drop = dict(drop or {})
        if hole is not None:
            for pid in facets:
                drop[pid] = drop[pid].union(hole) if pid in drop else hole
        if missing:  # LiDAR found almost nothing of the smallest plane (a 2 ft patch)
            small = min(facets, key=lambda p: Polygon(facets[p][0]).area)
            g = Polygon(facets[small][0])
            c = g.representative_point()
            drop[small] = g.buffer(5.0).difference(c.buffer(1.0, cap_style=3))
        for pid, (ring, _) in facets.items():  # every plane keeps some cluster (the generator needs one)
            if pid in drop and Polygon(ring).buffer(-shrink, join_style=2).difference(drop[pid]).area < 3.0:
                c = Polygon(ring).representative_point()
                drop[pid] = drop[pid].difference(c.buffer(1.0, cap_style=3))
        return real_roof(outline, facets, shrink=min(shrink, _max_shrink(facets)), drop=drop)

    saved = (base.ANGLE, base.ORIGIN)
    base.ANGLE, base.ORIGIN = angle, origin
    base.jitter = lambda poly, seed, amp_=amp: real_jitter(poly, seed + 7919 * k, amp_)
    mod.roof = roof
    try:
        return build()
    finally:
        base.ANGLE, base.ORIGIN = saved
        base.jitter = real_jitter
        mod.roof = real_roof


def check(planes, raw, fp) -> float:
    t0 = time.perf_counter()
    got = envelope_planes(planes, raw, fp)  # must never raise
    took = time.perf_counter() - t0
    if got is not None:
        out, borders = got
        shapes = [Polygon(p.polygon, p.holes) for p in out]
        assert all(g.is_valid and not g.is_empty for g in shapes)
        assert abs(sum(g.area for g in shapes) - fp.area) <= 0.01 * fp.area
        for i, a in enumerate(shapes):
            for b in shapes[i + 1:]:
                assert a.intersection(b).area <= 0.5
        assert all(math.isfinite(b["length_ft"]) for b in borders)
    return took


@pytest.mark.parametrize("k", range(35))
def test_random_variants_never_raise_and_any_pass_is_a_tiling(k):
    planes, raw, fp = variant(k)
    assert check(planes, raw, fp) < 5.0


def test_an_internal_error_returns_none_instead_of_raising(monkeypatch):
    import roof_measure.planes_envelope as pe

    planes, raw, fp = _gable()

    def boom(*a, **k):
        raise RuntimeError("an error nobody expected")

    monkeypatch.setattr(pe, "section_regions", boom)
    assert envelope_planes(planes, raw, fp) is None
    assert envelope_detail(planes, raw, fp).gate_failure == "an error"


def test_garbage_inputs_return_none():
    planes, raw, fp = _gable()
    assert envelope_planes(planes, {p.id: Polygon() for p in planes}, Polygon()) is None
    broken = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])  # a bow tie
    for args in ((planes[:1], raw, fp), (planes, {p.id: broken for p in planes}, broken), (planes, None, fp)):
        got = envelope_planes(*args)  # whatever the gate says: no exception
        assert got is None or isinstance(got, tuple)
