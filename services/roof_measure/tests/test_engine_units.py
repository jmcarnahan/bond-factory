"""Small pieces of the engine on tiny hand-made inputs (synthetic): raster tracing, graph cut, ring fitting, planes."""

import math
import subprocess
import sys

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon, box

from roof_measure.engine.errors import Ctx
from roof_measure.engine.graphcut import graphcut_swap
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.plane_math import aspect_deg, fit_plane, pdist, pitch_rise
from roof_measure.engine.raster import trace_polys
from roof_measure.engine.ringfit import regularise_ring


def test_trace_polys_gives_lattice_polygons_with_the_right_area():
    mask = np.zeros((6, 8), bool)
    mask[1:4, 1:6] = True
    mask[2:3, 2:4] = False  # a hole
    mask[4:6, 7:8] = True
    polys = sorted(trace_polys(mask, 10.0, 20.0, 0.5), key=lambda p: p.area)
    assert len(polys) == 2
    assert math.isclose(sum(p.area for p in polys), mask.sum() * 0.25)
    assert any(len(p.interiors) == 1 for p in polys)
    assert all(abs((x - 10.0) / 0.5 - round((x - 10.0) / 0.5)) < 1e-9 for p in polys for x, _ in p.exterior.coords)


def test_two_diagonal_cells_share_their_corner_but_keep_their_own_edges():
    mask = np.zeros((2, 2), bool)
    mask[0, 0] = mask[1, 1] = True
    (poly,) = trace_polys(mask, 0.0, 0.0, 1.0)  # one ring pinched at the shared corner (the right-turn rule)
    assert math.isclose(poly.area, 2.0) and len(poly.exterior.coords) == 9


def test_graph_cut_splits_a_strip_where_the_data_changes_and_removes_a_lone_outlier():
    n = 40
    cost = np.zeros((n, 2))
    cost[:, 0] = np.where(np.arange(n) < 20, 0.0, 1.0)
    cost[:, 1] = 1.0 - cost[:, 0]
    cost[7] = [1.0, 0.0]  # one cell that disagrees with its neighbours
    edges = np.c_[np.arange(n - 1), np.arange(1, n)]
    lab = graphcut_swap(cost, edges, np.full(n - 1, 0.9), cost.argmin(1).copy(), Ctx(DEFAULT))
    assert list(lab) == [0] * 20 + [1] * 20


def test_regularise_ring_squares_up_a_noisy_rotated_rectangle():
    rect = affinity.rotate(box(0, 0, 12, 8), 20, origin=(0, 0))
    noisy = Polygon([(x + 0.05 * math.sin(7 * i), y + 0.05 * math.cos(5 * i)) for i, (x, y) in enumerate(rect.exterior.coords[:-1])])
    out = regularise_ring(noisy, 20.0, snap_deg=15.0, min_edge=0.6, tol=0.12)
    assert out is not None and abs(out.area / rect.area - 1) < 0.02
    assert len(out.exterior.coords) == 5


def test_regularise_ring_drops_a_tiny_jog():
    jog = Polygon([(0, 0), (6, 0), (6, 0.3), (12, 0.3), (12, 8), (0, 8)])
    out = regularise_ring(jog, 0.0, snap_deg=15.0, min_edge=0.6, tol=0.05)
    assert out is not None and len(out.exterior.coords) <= 6 and out.area > 0.97 * jog.area


def test_plane_helpers_agree_on_a_slope_to_the_south():
    xy = np.random.default_rng(0).uniform(0, 10, (200, 2))
    pts = np.c_[xy, 3.0 + 0.5 * xy[:, 1]]  # rises to the north: faces south
    pl = fit_plane(pts)
    assert np.allclose(pl, [0, 0.5, 3.0], atol=1e-9)
    assert math.isclose(pitch_rise(pl), 6.0) and math.isclose(aspect_deg(pl), 180.0)
    assert pdist(pl, pts).max() < 1e-9


def test_import_engine_stays_numpy_free():
    code = "import sys, roof_measure.engine; print(sorted(m for m in ('numpy', 'scipy', 'shapely') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=False)
    assert out.returncode == 0 and out.stdout.strip() == "[]", out.stderr[-500:]
