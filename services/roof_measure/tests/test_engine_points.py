"""``engine.points.roof_points``: the roof-point selection moved out of ``blocks.segment_blocks`` (identical numbers)."""

import numpy as np
from shapely import contains_xy
from shapely.geometry import box

from roof_measure.engine.points import roof_points

FP = box(0, 0, 10, 10)  # 100 m2
OVERHANG, MIN_H = 0.5, 1.5


def _grid(x0, x1, y0, y1, step, z, cls):
    xs, ys = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    return np.column_stack([xs.ravel(), ys.ravel(), np.full(xs.size, z), np.full(xs.size, cls)])


def cloud():
    return np.vstack([
        _grid(-12, 22, -12, 22, 2.0, 0.0, 2),          # ground, 2 m grid, the whole site
        _grid(0.25, 10, 0.25, 10, 0.5, 6.0, 1),        # 20 x 20 = 400 roof returns, strictly inside
        _grid(-0.3, -0.2, 0.25, 10, 0.5, 6.0, 1),      # 20 returns on the overhang (inside the 0.5 m reach)
        _grid(-0.9, -0.8, 0.25, 10, 0.5, 6.0, 1),      # 20 returns beyond the reach, inside overhang + plane radius
        _grid(-3.0, -2.9, 0.25, 10, 0.5, 6.0, 1),      # 20 returns of a neighbour's tree: not near at all
        _grid(0.25, 5, 0.25, 5, 1.0, 1.0, 1),          # 25 low returns (1 m: a car or a bush), under the 1.5 m cut
    ])


def test_counts_and_ground_on_a_known_cloud():
    pts = cloud()
    rp = roof_points(pts, FP, overhang_m=OVERHANG, min_height_m=MIN_H)
    assert rp.n_inside == 400 and rp.n_on_roof == 420 and len(rp) == 440
    assert rp.density == 4.0 and rp.ground_z == 0.0
    assert int(rp.on_roof.sum()) == 420 and rp.on_roof.shape == (len(pts),)
    assert (rp.xyz[:, 2] == 6.0).all() and rp.xyz.shape == (440, 3)
    assert (rp.ground_xyz[:, 2] == 0.0).all() and len(rp.ground_xyz) == int((pts[:, 3] == 2).sum())


def test_height_is_above_the_local_ground_not_the_site_ground():
    pts = cloud()
    pts[pts[:, 3] == 2, 2] = pts[pts[:, 3] == 2, 0] * 0.2  # the ground rises 0.2 per m eastwards
    rp = roof_points(pts, FP, overhang_m=OVERHANG, min_height_m=MIN_H)
    assert rp.xyz[:, 2].min() == 6.0 and 0.0 < rp.ground_z < 2.0
    assert roof_points(pts, FP, overhang_m=OVERHANG, min_height_m=3.5).n_inside == 400  # ground <= ~2.2 m under it
    mid = roof_points(pts, FP, overhang_m=OVERHANG, min_height_m=5.0).n_inside
    assert 0 < mid < 400  # the east end stands only ~4 m above its own ground: a site-wide ground would keep all 400


def test_no_ground_falls_back_to_the_lowest_two_percent():
    pts = cloud()
    pts = pts[pts[:, 3] != 2]
    rp = roof_points(pts, FP, overhang_m=OVERHANG, min_height_m=MIN_H)
    assert rp.ground_z == np.percentile(pts[:, 2], 2) and len(rp.ground_xyz) == 0
    assert rp.n_inside == 400  # 1 m returns are within 1.5 m of the 2nd percentile (1.0): still dropped


def test_same_numbers_as_the_inline_code_it_replaced():
    """The original lines from blocks.segment_blocks, kept here as the reference."""
    from scipy.spatial import cKDTree

    from roof_measure.engine.points import local_ground

    rng = np.random.default_rng(7)
    pts = np.vstack([cloud(), np.column_stack([rng.uniform(-6, 16, 300), rng.uniform(-6, 16, 300),
                                               rng.uniform(0, 9, 300), rng.choice([1, 2, 5], 300)])])
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    is_ground = pts[:, 3] == 2
    g_xy, g_z = np.column_stack([x[is_ground], y[is_ground]]), z[is_ground]
    gtree = cKDTree(g_xy) if len(g_xy) >= 3 else None
    ring = contains_xy(FP.buffer(8.0), x[is_ground], y[is_ground]) & ~contains_xy(FP.buffer(0.5), x[is_ground],
                                                                                  y[is_ground])
    site = float(np.median(g_z[ring])) if ring.any() else float(np.median(g_z) if len(g_z) else np.percentile(z, 2))
    reach0 = FP.buffer(OVERHANG)
    near = contains_xy(FP.buffer(OVERHANG + 0.6), x, y)
    hag = np.full(len(z), np.nan)
    hag[near] = z[near] - local_ground(gtree, g_z, np.column_stack([x[near], y[near]]), site)
    sel = near & ~is_ground & (hag > MIN_H)
    roof_mask = contains_xy(reach0, x, y) & ~is_ground & (hag > MIN_H)
    inside = int((contains_xy(FP, x, y) & ~is_ground & (hag > MIN_H)).sum())

    rp = roof_points(pts, FP, overhang_m=OVERHANG, min_height_m=MIN_H)
    assert np.array_equal(rp.xyz, np.column_stack([x[sel], y[sel], z[sel]])) and rp.ground_z == site
    assert rp.n_on_roof == int(roof_mask.sum()) and np.array_equal(rp.on_roof, roof_mask)
    assert rp.n_inside == inside and rp.density == inside / FP.area
