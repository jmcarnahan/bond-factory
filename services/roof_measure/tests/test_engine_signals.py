"""signals.quality at its thresholds: each verdict condition just below, at and just above
the limit (plan 3.9 / 3.7a values, read from EngineParams)."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import box

from roof_measure.engine.params import DEFAULT as P
from roof_measure.engine.signals import quality
from roof_measure.engine.types import Facet

WALL = box(0, 0, 10, 10)  # 100 m2, sqrt = 10
PLANE = (0.0, 0.0, 3.0)


def facet(fid="f1", area=1000.0) -> Facet:
    return Facet(id=fid, polygon=WALL, plane=PLANE, label=0, pitch_rise=0.0, aspect_deg=0.0, roof_type="flat",
                 plan_area_sqft=area, area_sqft=area, points=0, rms_m=0.0)


def cloud(n: int, off_plane: int = 0, dx: float = 0.0, lift: float = -1.0) -> np.ndarray:
    """n points over the wall (a grid, mean at the centre), the first ``off_plane`` of them ``lift`` m off the plane
    (below it by default: a miss; above it by more than 0.5 m is canopy)."""
    k = int(np.ceil(np.sqrt(n)))
    g = (np.arange(k) + 0.5) / k * 10
    xy = np.array([(x, y) for x in g for y in g])[:n]
    xy = xy - xy.mean(0) + 5.0  # exactly centred
    z = np.full(n, 3.0)
    z[:off_plane] = 3.0 + lift
    return np.c_[xy[:, 0] + dx, xy[:, 1], z]


def q(n=1000, off=0, dx=0.0, support=100.0, supported=100.0, match="exact", params=P, lift=-1.0):
    return quality([facet()], cloud(n, off, dx, lift), WALL, WALL, match, "lacounty", supported, support, 
                   None, None, params)


# ----------------------------------------------------------------------------- density
@pytest.mark.parametrize("pts, reasons", [(399, ["lidar_too_sparse"]), (400, ["low_density"]), (599, ["low_density"]),
                                          (600, []), (601, [])])
def test_density_refusal_at_4_and_low_density_under_6(pts, reasons):
    got = [r for r in q(n=pts).reasons if r in ("lidar_too_sparse", "low_density")]
    assert got == reasons
    assert q(n=pts).density == pytest.approx(pts / 100, abs=0.06)


def test_verdict_is_the_most_serious_reason_and_ok_when_none():
    assert q().verdict == "ok" and q().reasons == []
    assert q(n=500, support=50.0).reasons == ["low_density", "outline_mismatch"] and q(n=500, support=50.0).verdict == "outline_mismatch"


# ----------------------------------------------------------------------------- outline mismatch
@pytest.mark.parametrize("support, mismatch", [(69.0, True), (70.0, False), (71.0, False), (129.0, False), (130.0, False),
                                               (131.0, True)])
def test_outline_mismatch_by_support_ratio(support, mismatch):
    assert ("outline_mismatch" in q(support=support).reasons) is mismatch


@pytest.mark.parametrize("dx, mismatch", [(1.0, False), (1.69, False), (1.71, True), (2.5, True)])
def test_outline_mismatch_by_shift_0_17(dx, mismatch):
    got = q(n=2000, dx=dx)
    assert ("outline_mismatch" in got.reasons) is mismatch
    assert got.outline_shift == pytest.approx(dx / 10, abs=0.002)


def test_the_thresholds_come_from_the_params():
    tight = P.replace(mismatch_lo=0.9)
    assert "outline_mismatch" in q(support=85.0, params=tight).reasons and "outline_mismatch" not in q(support=85.0).reasons


# ----------------------------------------------------------------------------- poor fit
@pytest.mark.parametrize("off, poor", [(440, False), (450, False), (451, True), (460, True)])
def test_poor_fit_at_fit_all_0_55(off, poor):
    got = q(n=1000, off=off)  # fit_all = (1000 - off) / 1000
    assert ("poor_fit" in got.reasons) is poor and got.fit_all == pytest.approx((1000 - off) / 1000)
    assert got.fit_covered == got.fit_all  # every point is inside the facet


@pytest.mark.parametrize("supported, poor", [(69.9, True), (70.0, False), (70.1, False), (None, False)])
def test_poor_fit_at_supported_70(supported, poor):
    assert ("poor_fit" in q(supported=supported).reasons) is poor


# ----------------------------------------------------------------------------- parcel
@pytest.mark.parametrize("match, flagged", [("street", True), ("nearest", True), ("exact", False), ("given", False),
                                            (None, False)])
def test_not_exact_parcel(match, flagged):
    got = q(match=match)
    assert ("not_exact_parcel" in got.reasons) is flagged and got.parcel_match == match


# ----------------------------------------------------------------------------- canopy: reported, never in the verdict
def test_canopy_is_reported_but_the_verdict_still_tests_fit_all():
    below = q(n=1000, off=100, lift=-1.0)  # a tenth of the returns 1 m under the surface
    above = q(n=1000, off=100, lift=+1.0)  # a tenth over it: trees
    assert below.fit_clear == below.fit_all == 0.9 and below.tree_cover_pct == 0.0
    assert above.fit_all == 0.9 and above.fit_clear == 1.0 and above.tree_cover_pct == 10.0
    assert above.to_dict()["tree_cover_pct"] == 10.0 and above.to_dict()["fit_clear"] == 1.0


@pytest.mark.parametrize("lift", [-1.0, +1.0, +3.0])
def test_a_wrong_surface_is_poor_fit_whether_the_returns_lie_below_or_above_it(lift):
    """Half the returns off the drawn surface: poor_fit by fit_all, however high above it they are (a flat drawn over a
    slope puts the real roof 'above' the surface: it must not pass as canopy)."""
    got = q(n=1000, off=500, lift=lift)
    assert got.fit_all == 0.5 and "poor_fit" in got.reasons and got.verdict == "poor_fit"


@pytest.mark.parametrize("lift, canopy", [(0.45, False), (0.55, True)])
def test_canopy_starts_half_a_metre_above_the_surface(lift, canopy):
    got = q(n=1000, off=100, lift=lift)
    assert (got.tree_cover_pct == 10.0) is canopy


def test_a_lot_of_canopy_alone_is_not_a_poor_fit():
    got = q(n=1000, off=400, lift=+1.0)  # fit_all 0.6 (above the floor), 40% canopy
    assert got.fit_all == 0.6 and got.tree_cover_pct == 40.0 and "poor_fit" not in got.reasons


# ----------------------------------------------------------------------------- the fit is over THIS roof
def test_returns_beyond_the_drawn_outline_do_not_count_against_the_fit():
    """1000 returns on the roof plane, plus 500 on a neighbour 2 m beyond the outline and 1 m lower: over all returns
    fit_all would be 1000 / 1500 = 0.67; over the drawn roof (+ fit_outline_margin_m) it is 1.0."""
    roof = cloud(1000)
    nb = cloud(500)
    nb[:, 0] += 12.0  # x 12..22: beyond the 10 m roof by 2 m and more
    nb[:, 2] -= 1.0
    res = quality([facet()], np.vstack([roof, nb]), WALL, WALL, "exact", "lacounty", 100.0, 100.0, None, None, P)
    assert res.fit_all == 1.0 and res.coverage == pytest.approx(1000 / 1500, abs=0.001)


def test_a_miss_inside_the_margin_still_counts():
    """A return 0.2 m outside the outline (inside the 0.3 m margin) and 1 m below the plane is a miss of this roof."""
    pts = np.vstack([cloud(999), [[10.2, 5.0, 2.0]]])
    res = quality([facet()], pts, WALL, WALL, "exact", "lacounty", 100.0, 100.0, None, None, P)
    assert res.fit_all == pytest.approx(0.999, abs=0.0005)


# ----------------------------------------------------------------------------- reasons from the edge finder
@pytest.mark.parametrize("share, flagged", [(0.19, False), (0.20, True), (0.32, True)])
def test_outline_no_evidence_at_its_share(share, flagged):
    res = quality([facet()], cloud(1000), WALL, WALL, "exact", "lacounty", 100.0, 100.0, None, None, P,
                  diag={"edge_no_evidence_share": share})
    assert ("outline_no_evidence" in res.reasons) is flagged and (res.verdict == "ok") is not flagged


@pytest.mark.parametrize("share, flagged", [(0.03, False), (0.10, True)])
def test_roof_continues_at_its_share(share, flagged):
    res = quality([facet()], cloud(1000), WALL, WALL, "exact", "lacounty", 100.0, 100.0, None, None, P,
                  diag={"edge_end_share": share})
    assert ("roof_continues" in res.reasons) is flagged


def test_roof_part_missed_from_the_objects_figure():
    from roof_measure.engine.signals import part_missed_reason

    assert part_missed_reason(0.0, P) is None and part_missed_reason(32.2, P) is None
    assert part_missed_reason(32.3, P) == "roof_part_missed"


# ----------------------------------------------------------------------------- the verdict is the most serious reason
def test_a_serious_reason_promotes_a_soft_verdict():
    """A low density used to hide a wrong outline: [low_density, outline_no_evidence] reads outline_no_evidence."""
    res = quality([facet()], cloud(500), WALL, WALL, "exact", "lacounty", 100.0, 100.0, None, None, P,
                  diag={"edge_no_evidence_share": 0.5})
    assert res.reasons == ["low_density", "outline_no_evidence"] and res.verdict == "outline_no_evidence"


def test_roof_part_missed_outranks_not_exact_parcel_and_no_reason_is_added_twice():
    from roof_measure.engine.signals import add_reason

    res = q(match="nearest")
    assert res.verdict == "not_exact_parcel"
    add_reason(res, "roof_part_missed")
    add_reason(res, "roof_part_missed")
    assert res.reasons == ["not_exact_parcel", "roof_part_missed"] and res.verdict == "roof_part_missed"


def test_the_verdict_order_is_the_closed_list():
    from roof_measure.engine.signals import REASONS, SOFT, verdict_of

    assert verdict_of([]) == "ok" and verdict_of(["not_exact_parcel", "low_density"]) == "low_density"
    assert verdict_of(["low_density", "planes_not_found"]) == "poor_fit"  # the word a reader knows for no planes
    assert verdict_of(["roof_part_missed", "outline_mismatch"]) == "outline_mismatch"
    assert set(SOFT) - {"ok"} <= set(REASONS) and REASONS.index("low_density") > REASONS.index("roof_part_missed")
