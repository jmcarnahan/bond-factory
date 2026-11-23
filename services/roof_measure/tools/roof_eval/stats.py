"""Small statistics helpers: Wilson interval, bootstrap median interval, robust medians."""

from __future__ import annotations

import math

import numpy as np

Z95 = 1.959963984540054
BOOT_SEED = 20261122
BOOT_N = 2000


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial share k/n (95% by default). n == 0 gives (0.0, 1.0)."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)
    return (0.0 if k == 0 else lo), (1.0 if k == n else hi)


def median(xs) -> float | None:
    """Median ignoring None and NaN; None when nothing is left."""
    v = [float(x) for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.median(v)) if v else None


def mean(xs) -> float | None:
    """Mean ignoring None and NaN; None when nothing is left."""
    v = [float(x) for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.mean(v)) if v else None


def percentile(xs, q: float) -> float | None:
    """q-th percentile (0-100) ignoring None and NaN."""
    v = [float(x) for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.percentile(v, q)) if v else None


def bootstrap_median_ci(values, level: float = 0.90, n_boot: int = BOOT_N,
                        seed: int = BOOT_SEED) -> tuple[float, float, float] | None:
    """(median, lo, hi): the median of ``values`` and its percentile-bootstrap interval at ``level``.

    Deterministic: a fresh ``default_rng(seed)`` on every call. None when ``values`` is empty.
    """
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if len(v) == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    meds = np.median(v[idx], axis=1)
    a = (1 - level) / 2 * 100
    return float(np.median(v)), float(np.percentile(meds, a)), float(np.percentile(meds, 100 - a))
