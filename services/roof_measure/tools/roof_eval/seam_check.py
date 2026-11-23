"""Independent check of a flat/flat seam from the reference points alone (never from the engine's own rule).

STRIP MEDIANS: at 12 stations along the seam (15 % to 85 % of its length), take the median z of the raw reference
returns that lie inside each facet's polygon, within 0.6 m along the seam of the station and between 0.4 m and 2.5 m
from the seam line. A station with fewer than 4 returns on either side is skipped; a seam with fewer than 4 usable
stations (or shorter than 1 m) is NOT EVALUABLE (None) and counts in no numerator. Otherwise the seam is a real step
when the two medians differ by at least 0.3 m at 70 % or more of the usable stations.
"""

from __future__ import annotations

import numpy as np
import shapely

STATIONS = 12
STATION_LO, STATION_HI = 0.15, 0.85
ALONG_M = 0.6
NEAR_M, FAR_M = 0.4, 2.5
MIN_RETURNS = 4
MIN_STATIONS = 4
STEP_M = 0.3
STEP_SHARE = 0.7
MIN_SEAM_M = 1.0


def strip_step(ref: np.ndarray, poly_a, poly_b, p0, p1) -> bool | None:
    """True = a real step, False = no step, None = not evaluable (see the module doc)."""
    a0, a1 = np.array(p0[:2], float), np.array(p1[:2], float)
    ln = float(np.hypot(*(a1 - a0)))
    if ln < MIN_SEAM_M or ref is None or len(ref) == 0:
        return None
    t = (a1 - a0) / ln
    n = np.array([-t[1], t[0]])
    in_a = shapely.contains_xy(poly_a, ref[:, 0], ref[:, 1])
    in_b = shapely.contains_xy(poly_b, ref[:, 0], ref[:, 1])
    jumps = []
    for s in np.linspace(STATION_LO * ln, STATION_HI * ln, STATIONS):
        d = ref[:, :2] - (a0 + t * s)
        near_station = np.abs(d @ t) < ALONG_M
        dist = np.abs(d @ n)
        strip = near_station & (dist > NEAR_M) & (dist < FAR_M)
        za, zb = ref[strip & in_a, 2], ref[strip & in_b, 2]
        if len(za) >= MIN_RETURNS and len(zb) >= MIN_RETURNS:
            jumps.append(abs(float(np.median(za) - np.median(zb))))
    if len(jumps) < MIN_STATIONS:
        return None
    return bool(np.mean(np.array(jumps) >= STEP_M) >= STEP_SHARE)
