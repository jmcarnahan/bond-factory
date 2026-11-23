"""Wilson interval, bootstrap median interval and the small stats helpers against known values."""

import math

import pytest

from tools.roof_eval import stats


def test_wilson_known_values():
    lo, hi = stats.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    lo, hi = stats.wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo, hi = stats.wilson(10, 10)
    assert hi == 1.0 and lo == pytest.approx(0.7225, abs=1e-4)
    lo, hi = stats.wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-4) and hi == pytest.approx(0.5962, abs=1e-4)


def test_wilson_empty_and_symmetry():
    assert stats.wilson(0, 0) == (0.0, 1.0)
    lo, hi = stats.wilson(3, 20)
    lo2, hi2 = stats.wilson(17, 20)
    assert math.isclose(lo, 1 - hi2) and math.isclose(hi, 1 - lo2)


def test_bootstrap_median_ci_constant_and_deterministic():
    assert stats.bootstrap_median_ci([1.1] * 12) == (1.1, 1.1, 1.1)
    xs = [0.9, 1.0, 1.05, 1.1, 1.2, 0.95, 1.15, 1.0, 1.08, 1.12]
    a, b = stats.bootstrap_median_ci(xs), stats.bootstrap_median_ci(xs)
    assert a == b and a[1] <= a[0] <= a[2]
    assert a[0] == pytest.approx(1.065)
    assert stats.bootstrap_median_ci([]) is None


def test_bootstrap_interval_narrows_with_more_data():
    base = [0.8, 0.9, 1.0, 1.1, 1.2]
    small = stats.bootstrap_median_ci(base)
    big = stats.bootstrap_median_ci(base * 20)
    assert (big[2] - big[1]) < (small[2] - small[1])


def test_median_mean_ignore_none():
    assert stats.median([1, None, 3, float("nan")]) == 2.0
    assert stats.mean([None]) is None
    assert stats.percentile([1, 2, 3, 4], 50) == 2.5
