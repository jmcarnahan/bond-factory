"""CGAL crash guard: rings that used to segfault or hang now raise ValueError; rectangles are unchanged.

Every test that can reach CGAL with a non-rectangle runs in a SUBPROCESS with a 30 s timeout, so a regression is a
failed assertion and never a dead test run.
"""

import json
import math
import subprocess
import sys
import textwrap

import pytest

from roof_measure.skeleton import hip_roof_edges
from roof_measure.skeleton_guard import check_ring, safe_extension

TRAPEZOID = [(0, 0), (40, 0), (43, 24), (-3, 24)]
BOWTIE = [(0.0, 100.0), (10.0, 100.0), (20.0, 0.0), (31.0, 0.0)]
DUP_VERTEX = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0), (5, 5)]  # touches itself
THREE_POINTS_ON_A_LINE = [(0, 0), (5, 0), (10, 0)]
TIMEOUT_S = 30

_RUNNER = textwrap.dedent("""
    import faulthandler, json, sys
    faulthandler.enable()
    from roof_measure.skeleton import hip_roof_edges
    ring, rise, gable = json.loads(sys.argv[1])
    try:
        r = hip_roof_edges([tuple(p) for p in ring], rise, set(gable))
        print(json.dumps({"ok": r["totals"], "notes": r["notes"]}))
    except ValueError as exc:
        print(json.dumps({"value_error": str(exc)}))
""")


def run_hip(ring, rise, gable):
    """Run hip_roof_edges in a child interpreter; returns (returncode, parsed last stdout line or None, stderr)."""
    try:
        p = subprocess.run([sys.executable, "-c", _RUNNER, json.dumps([ring, rise, sorted(gable)])],
                           capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail(f"hip_roof_edges hung for {TIMEOUT_S} s (CGAL loop) on {ring}")
    out = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else None
    return p.returncode, out, p.stderr


def assert_safe_value_error(ring, gable):
    rc, out, err = run_hip(ring, 6.0, gable)
    assert rc == 0, f"child died with code {rc}: {err[-300:]}"
    assert out is not None and "value_error" in out, out
    return out["value_error"]


def test_trapezoid_with_gable_ends_no_longer_crashes():
    # before the guard the pushed-out gable edges crossed and CGAL segfaulted (rc -11)
    rc, out, err = run_hip(TRAPEZOID, 6.0, {0, 2})
    assert rc == 0, f"child died with code {rc}: {err[-300:]}"
    assert out is not None
    if "ok" in out:  # the extension shrank until the ring was valid
        t = out["ok"]
        assert t["rakes_ft"] > 0 and t["facet_area_sqft"] > 0
    else:
        assert "gable" in out["value_error"]


def test_trapezoid_result_is_stable_and_sensible():
    rc, out, _ = run_hip(TRAPEZOID, 6.0, {0, 2})
    assert rc == 0 and "ok" in out
    t = out["ok"]
    assert t["eaves_ft"] == pytest.approx(48.4, abs=0.2)  # the research sweep: eaves 48.4 / rakes 96.0 / area 1153.8
    assert t["facet_area_sqft"] == pytest.approx(1153.8, abs=1.0)


def test_literal_bowtie_ring_is_refused():
    msg = assert_safe_value_error(BOWTIE, set())
    assert "crosses or touches itself" in msg


def test_ring_with_a_duplicated_vertex_is_refused():
    msg = assert_safe_value_error(DUP_VERTEX, set())
    assert "touches itself" in msg or "repeated" in msg


def test_three_point_degenerate_ring_is_refused():
    rc, out, err = run_hip(THREE_POINTS_ON_A_LINE, 6.0, set())
    assert rc == 0, err[-300:]
    assert out is not None and "value_error" in out


def test_two_point_ring_is_refused_in_process():
    with pytest.raises(ValueError, match="at least 3"):
        hip_roof_edges([(0, 0), (1, 1)], 4.0)


@pytest.mark.parametrize("ring, msg", [
    (BOWTIE, "crosses or touches itself"),
    (DUP_VERTEX, "touches itself"),
    ([(0, 0), (10, 0), (10, 0), (10, 10)], "repeated"),
    ([(0, 0), (10, 0), (0, 0)], "at least 3 distinct"),
    ([(0, 0), (5, 0), (10, 0)], "crosses or touches"),  # zero area is not a valid ring
    ([(0, 0), (0, 10), (10, 10), (10, 0)], "clockwise"),
    ([(0, 0), (10, 0), (10, 0.000001), (0, 10)], "shorter than"),
    ([(0, 0), (10, 0), (10, float("nan")), (0, 10)], "non-finite"),
])
def test_check_ring_rejects(ring, msg):
    with pytest.raises(ValueError, match=msg):
        check_ring(ring)


def test_check_ring_accepts_rectangles_collinear_points_and_concave_rings():
    check_ring([(0, 0), (40, 0), (40, 24), (0, 24)])
    check_ring([(0, 0), (20, 0), (40, 0), (40, 24), (0, 24)])  # collinear vertex is fine
    check_ring([(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)])  # an L


def test_safe_extension_shrinks_until_valid():
    calls = []

    def fake(poly, gable, d):
        calls.append(d)
        return [(0, 0), (10, 0), (10, 10), (0, 10)] if d <= 50 else BOWTIE

    ring, used = safe_extension([(0, 0), (10, 0), (10, 10), (0, 10)], {0}, 400.0, fake)
    assert ring == [(0, 0), (10, 0), (10, 10), (0, 10)] and calls == [400.0, 200.0, 100.0, 50.0] and used == 50.0


def test_safe_extension_gives_up_with_the_agent_message():
    with pytest.raises(ValueError, match="gable edges cannot be extended on this outline.*rect_fit"):
        safe_extension([(0, 0), (10, 0), (10, 10), (0, 10)], {0}, 400.0, lambda p, g, d: BOWTIE)


def test_rectangle_numbers_are_unchanged():
    """The closed forms from test_model_skeleton, repeated here so this file pins the regression on its own."""
    rect = [(0, 0), (40, 0), (40, 24), (0, 24)]
    sf = math.sqrt(1 + 0.25)
    gable = hip_roof_edges(rect, 6, gable_edges={1, 3})["totals"]
    assert gable["eaves_ft"] == pytest.approx(80.0, abs=1e-6)
    assert gable["ridges_ft"] == pytest.approx(40.0, abs=1e-6)
    assert gable["rakes_ft"] == pytest.approx(4 * 12 * sf, abs=1e-6)
    assert gable["facet_area_sqft"] == pytest.approx(40 * 24 * sf, abs=1e-6)
    hip = hip_roof_edges([(0, 0), (35, 0), (35, 26), (0, 26)], 4)["totals"]
    s = 4 / 12
    assert hip["hips_ft"] == pytest.approx(4 * math.hypot(math.hypot(13, 13), s * 13), abs=1e-6)
    assert hip["facet_area_sqft"] == pytest.approx(35 * 26 * math.sqrt(1 + s * s), abs=1e-6)


def test_clockwise_rectangle_with_gable_edges_matches_ccw():
    ccw = hip_roof_edges([(0, 0), (40, 0), (40, 24), (0, 24)], 6, gable_edges={1, 3})["totals"]
    cw_ring = [(0, 0), (0, 24), (40, 24), (40, 0)]
    cw = hip_roof_edges(cw_ring, 6, gable_edges={0, 2})["totals"]  # edges 0 and 2 of the CW ring are the short ends
    assert cw["rakes_ft"] == pytest.approx(ccw["rakes_ft"], abs=1e-6)
    assert cw["ridges_ft"] == pytest.approx(ccw["ridges_ft"], abs=1e-6)


def test_check_ring_rejects_tiny_area_ring():
    with pytest.raises(ValueError, match="area under"):
        check_ring([(0, 0), (0.0005, 0), (0.0005, 0.0005), (0, 0.0005)])  # edges pass, area 2.5e-7 sqft does not


def test_short_edges_that_head_handled_are_still_accepted():
    check_ring([(0, 0), (40, 0), (40, 23.96), (39.96, 24), (0, 24)])  # a 0.057 ft clipped corner
    check_ring([(0, 0), (40, 0), (40, 23.99998), (39.99998, 24), (0, 24)])  # 0.00003 ft: HEAD still took it


def test_shortened_gable_extension_is_noted_on_the_result():
    """The ring converges: the first (long) extension is not simple, a shorter one is. The result says so."""
    rc, out, err = run_hip(TRAPEZOID, 6.0, {0, 2})
    assert rc == 0, err[-300:]
    assert out is not None and "ok" in out
    assert out["notes"] and "instead of" in out["notes"][0] and "rakes" in out["notes"][0]


def test_a_rectangle_gets_no_note():
    rc, out, _err = run_hip([(0, 0), (40, 0), (40, 24), (0, 24)], 6.0, {1, 3})
    assert rc == 0 and out["notes"] == []


def test_valid_rings_head_handled_give_the_same_numbers():
    """32 valid non-rectangular rings (L, T, trapezoid, convex, jogs, 0.04 ft edges) and the totals HEAD gave."""
    from skeleton_valid_cases import CASES

    payload = [[ring, rise] for _, ring, rise, _ in CASES]
    script = textwrap.dedent("""
        import json, sys, faulthandler
        faulthandler.enable()
        from roof_measure.skeleton import hip_roof_edges
        out = []
        for ring, rise in json.loads(sys.argv[1]):
            t = hip_roof_edges([tuple(p) for p in ring], rise)["totals"]
            out.append(t)
        print(json.dumps(out))
    """)
    try:
        p = subprocess.run([sys.executable, "-c", script, json.dumps(payload)], capture_output=True, text=True,
                           timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail("hip_roof_edges hung on a valid ring")
    assert p.returncode == 0, p.stderr[-400:]
    got = json.loads(p.stdout.strip().splitlines()[-1])
    assert len(got) == len(CASES) >= 30
    for (kind, _ring, _rise, exp), t in zip(CASES, got, strict=True):
        for k, v in exp.items():
            assert t[k] == pytest.approx(v, abs=1e-6), (kind, k)


def test_rectangle_with_a_0_03_ft_jog_is_measured_not_rejected():
    """Adversary case: HEAD measured it fine, so the guard must too (no minimum edge of 0.05 ft)."""
    ring = [(0, 0), (20, 0), (20, 0.03), (32, 0.03), (32, 0), (40, 0), (40, 24), (0, 24)]
    rc, out, err = run_hip(ring, 5.0, set())
    assert rc == 0, err[-300:]
    assert out is not None and "ok" in out, out
    assert out["ok"]["facet_area_sqft"] == pytest.approx(40 * 24 * math.sqrt(1 + (5 / 12) ** 2), rel=1e-3)
