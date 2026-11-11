"""LiDAR hull footprint from synthetic point clouds: the building, a tree, two near buildings, vegetation."""

import numpy as np
import pytest
from pyproj import Transformer

from roof_measure import footprint_hull as fh
from roof_measure.footprint_types import AmbiguousBuilding, FootprintError
from roof_measure.lidar import PointCloud

EPSG, E0, N0 = 32611, 500000.0, 3700000.0
LNG, LAT = Transformer.from_crs(EPSG, 4326, always_xy=True).transform(E0, N0)


def cloud(buildings=(), trees=(), seed=1, ground_class=2):
    rng = np.random.default_rng(seed)
    X = [rng.uniform(-45, 45, 30000)]
    Y = [rng.uniform(-45, 45, 30000)]
    Z = [rng.normal(0, 0.05, 30000)]
    C = [np.full(30000, ground_class)]
    for x0, y0, x1, y1, h in buildings:
        n = int((x1 - x0) * (y1 - y0) * 12)
        X.append(rng.uniform(x0, x1, n))
        Y.append(rng.uniform(y0, y1, n))
        Z.append(h + rng.normal(0, 0.04, n))
        C.append(np.full(n, 6))
    for cx, cy, r, top, cls in trees:
        X.append(cx + rng.normal(0, r / 2, 3000))
        Y.append(cy + rng.normal(0, r / 2, 3000))
        Z.append(rng.uniform(2, top, 3000))
        C.append(np.full(3000, cls))
    x, y, z, c = (np.concatenate(a) for a in (X, Y, Z, C))
    return PointCloud(x + E0, y + N0, z, c, np.zeros(len(x)), {"epsg": EPSG})


def test_hull_is_the_building_with_roughly_its_area():
    fp = fh.hull_from_points(cloud([(-6, -5, 6, 5, 6.0)], [(15, 10, 3, 8, 5)]), LAT, LNG)
    assert fp.source == "lidar_hull" and fp.provider == "lidar_hull"
    assert fp.area_sqft == pytest.approx(12 * 10 * 10.7639, rel=0.1)
    assert fp.height_ft == pytest.approx(6.0 / 0.3048, rel=0.1)
    assert fp.polygon_wgs84.contains(__import__("shapely.geometry", fromlist=["Point"]).Point(LNG, LAT))
    assert fp.warning_codes == ["footprint_lidar_hull"] and len(fp.warnings) == 1


def test_an_l_shaped_building_is_not_filled_in():
    fp = fh.hull_from_points(cloud([(-10, -5, 4, 3, 5.0), (-10, 3, -2, 12, 5.0)]), LAT, LNG)
    full = 14 * 8 + 8 * 9
    assert fp.area_sqft == pytest.approx(full * 10.7639, rel=0.12)
    assert fp.area_sqft < (14 * 17) * 10.7639 * 0.8  # a convex hull would be about 0.9 of the box


def test_vegetation_only_is_rejected():
    for cls in (3, 4, 5):
        with pytest.raises(FootprintError, match="no smooth roof|No roof-height"):
            fh.hull_from_points(cloud([], [(0, 0, 3, 8, cls)]), LAT, LNG)


def test_unclassified_tree_is_rejected_as_rough():
    with pytest.raises(FootprintError):
        fh.hull_from_points(cloud([], [(0, 0, 4, 9, 1)]), LAT, LNG)


def test_two_similar_buildings_close_together_are_ambiguous():
    with pytest.raises(AmbiguousBuilding):
        fh.hull_from_points(cloud([(-6, -5, 6, 5, 6.0), (10, -5, 22, 5, 6.0)]), LAT, LNG)


def test_a_much_smaller_neighbour_is_not_ambiguous():
    fp = fh.hull_from_points(cloud([(-6, -5, 6, 5, 6.0), (10, -3, 15, 1, 4.0)]), LAT, LNG)
    assert fp.area_sqft > 1000


def test_far_apart_buildings_pick_the_nearest():
    fp = fh.hull_from_points(cloud([(-6, -5, 6, 5, 6.0), (30, -5, 42, 5, 6.0)]), LAT, LNG)
    assert fp.polygon_wgs84.centroid.x < LNG + 0.00005


def test_nothing_near_the_point_is_an_error():
    with pytest.raises(FootprintError):
        fh.hull_from_points(cloud([(30, 30, 42, 40, 6.0)]), LAT, LNG)


def test_flat_terrain_alone_is_an_error():
    with pytest.raises(FootprintError):
        fh.hull_from_points(cloud(), LAT, LNG)


def test_fetch_hull_uses_lidar_without_a_footprint(monkeypatch):
    calls = {}

    def fake(lat, lng, half, epsg, min_points=2000, footprint_m=None):
        calls.update(footprint_m=footprint_m, min_points=min_points)
        return cloud([(-6, -5, 6, 5, 6.0)])

    monkeypatch.setattr(fh.lidar, "fetch_best_points", fake)
    assert fh.fetch_hull(LAT, LNG).source == "lidar_hull"
    assert calls["footprint_m"] is None and calls["min_points"] >= 1000


def test_fetch_hull_turns_lidar_errors_into_footprint_errors(monkeypatch):
    def boom(*a, **k):
        raise fh.lidar.LidarError("No USGS 3DEP LiDAR project covers this address.")

    monkeypatch.setattr(fh.lidar, "fetch_best_points", boom)
    with pytest.raises(FootprintError, match="No LiDAR"):
        fh.fetch_hull(LAT, LNG)


def test_fetch_hull_respects_an_expired_deadline():
    from roof_measure.deadline import Deadline, DeadlineExceeded

    with pytest.raises(DeadlineExceeded):
        fh.fetch_hull(LAT, LNG, Deadline.after(0))
