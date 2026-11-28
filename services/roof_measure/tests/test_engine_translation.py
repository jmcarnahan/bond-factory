"""Points and wall moved together change nothing (slice c).

Written before the first run: a synthetic roof and its wall polygon translated by sub-cell offsets (0.03/0.07, 0.11/0.19 and
0.19/0.03 m in x/y) give the same number of planes, the same number of facets and every typed edge length within 0.5 ft.
The label raster hangs on ``anchor.anchor_of`` (the median of the inlier points), so it cannot see the offset. PARKED: ring.py's
cell lattice, measure._crop's voxel key and detect.support_area still bin on an absolute lattice; on the synthetic roofs below that
changes nothing, but on real houses it does (one house 8 or 9 planes, another 6-8 facets under a pure translation). Anchoring them
changed 23 of 151 houses of the tuning set against lib-0.5.1 (thresholds were tuned on the old phase), so it is parked until a
threshold re-tune; add a real-house case here when that lands."""

from __future__ import annotations

import numpy as np
import pytest
from shapely import affinity

from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.measure import measure_stages
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.synth_points import cases

OFFSETS = [(0.03, 0.07), (0.11, 0.19), (0.19, 0.03)]
TOL_FT = 0.5
KNOWN = {}
ROOFS = [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=KNOWN[n])) if n in KNOWN else n
         for n in ["gable_d8", "hip_d8", "l_shape_d8", "t_shape_d8", "complex_hip_d8", "hip_d8_trees", "hip_d8_rot17"]]


def _run(name: str, dx: float, dy: float):
    c = {c.name: c for c in cases()}[name]
    pts = c.points().copy()
    wall = c.roof.wall_polygon()
    pts[:, 0] += dx
    pts[:, 1] += dy
    wall = affinity.translate(wall, dx, dy)
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res, st = measure_stages(rp, wall, params=DEFAULT, deadline=None, outline_source="county", parcel_match="given", context=pts)
    lengths = {}
    for e in res.edges:
        lengths[e.type] = lengths.get(e.type, 0.0) + e.length_ft
    return len(st.planes), len(res.facets), lengths


@pytest.mark.parametrize("name", ROOFS)
def test_moving_points_and_wall_together_changes_nothing(name):
    planes0, facets0, len0 = _run(name, 0.0, 0.0)
    for dx, dy in OFFSETS:
        planes, facets, lens = _run(name, dx, dy)
        assert (planes, facets) == (planes0, facets0), (dx, dy)
        for t in set(len0) | set(lens):
            assert np.isclose(lens.get(t, 0.0), len0.get(t, 0.0), atol=TOL_FT), (dx, dy, t, lens.get(t), len0.get(t))
