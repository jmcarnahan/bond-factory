"""Things standing on the roof (chimneys, flues, a roof lantern): returns well above the plane of the facet under them.

``find_objects`` reads the wide cloud (``context``: x, y, z, ASPRS class, the world frame in metres the engine returns
its facets in), the facets and the roof outline. Steps: (1) candidates are non-ground returns more than ``obj_hag_m``
above the local ground within ``obj_reach_m`` of the outline; (2) each gets its residual to the plane of the facet under
it (the nearest facet, continued, outside every polygon); (3) returns more than ``obj_above_plane_m`` above their plane
link into blobs (a point graph: two returns closer than the link radius, which follows the roof's own point density);
(4) each blob of at least ``obj_min_points`` returns is classed: tree (not listed), planar blob over
``obj_mislabel_area_m2`` (a roof part the facets left out: returned apart, not listed), chimney, lantern or unknown.

There is no raster: the blobs come from point distances, so the result does not depend on where the frame's origin is
(a roof translated by any offset gives the same objects). Skylights are flush with the roof and cannot be seen: not tried.

Returns ``(objects, mislabelled)``. ``objects``: dicts ``id`` ("o1", ... ordered by x then y), ``kind``
("chimney" | "lantern" | "unknown"), ``center`` [x, y], ``size_ft`` [long, short], ``polygon`` (closed ring of [x, y]: the
rectangle of the blob's returns, grown by 0.15 of the mean return spacing: aligned with the walls unless a free
angle fits much better), ``height_ft`` (95th percentile above the plane),
``facet`` (id of the facet under the centre), ``returns`` (count); x, y in feet like the model's facets. ``mislabelled``:
the same keys without ``id`` and ``kind``, plus ``area_sqft`` (the footprint), for a later quality reason.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import shapely
from scipy.sparse import coo_array
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint
from shapely.geometry.polygon import orient

from .params import DEFAULT, EngineParams
from .points import local_ground
from .types import Facet, Outline

FT = 1 / 0.3048
SQFT = FT * FT
MIN_DENSITY = 2.0  # pts/m2: floor of the density estimate (a sparse roof still gets a finite link radius)


def _residuals(xyz: np.ndarray, facets: list[Facet]) -> np.ndarray:
    """Height of each return above the plane of the facet under it. Returns outside every polygon use the
    nearest facet's plane continued."""
    n = len(xyz)
    fi = np.full(n, -1)
    for j, f in enumerate(facets):
        fi[(fi < 0) & shapely.contains_xy(f.polygon, xyz[:, 0], xyz[:, 1])] = j
    rest = np.flatnonzero(fi < 0)
    if len(rest) and facets:
        pts = shapely.points(xyz[rest, 0], xyz[rest, 1])
        d = np.stack([shapely.distance(f.polygon, pts) for f in facets])
        fi[rest] = np.argmin(d, axis=0)
    planes = np.array([f.plane for f in facets]) if facets else np.zeros((1, 3))
    pl = planes[np.maximum(fi, 0)]
    return xyz[:, 2] - (pl[:, 0] * xyz[:, 0] + pl[:, 1] * xyz[:, 1] + pl[:, 2])


def _candidates(ctx: np.ndarray, outline: Outline, ground_z: float, p: EngineParams) -> np.ndarray:
    """Non-ground returns more than ``obj_hag_m`` above the local ground within ``obj_reach_m`` of the outline."""
    reach = outline.drawn.buffer(p.obj_reach_m)
    x0, y0, x1, y1 = reach.bounds
    ctx = ctx[(ctx[:, 0] >= x0 - 8) & (ctx[:, 0] <= x1 + 8) & (ctx[:, 1] >= y0 - 8) & (ctx[:, 1] <= y1 + 8)]
    gr = ctx[ctx[:, 3] == 2]
    ng = ctx[ctx[:, 3] != 2]
    ng = ng[shapely.contains_xy(reach, ng[:, 0], ng[:, 1])]
    tree = cKDTree(gr[:, :2]) if len(gr) >= 3 else None
    hag = ng[:, 2] - local_ground(tree, gr[:, 2], ng[:, :2], ground_z)
    return ng[hag > p.obj_hag_m, :3]


def _blobs(xy: np.ndarray, radius: float) -> np.ndarray:
    """Component label of each point when points closer than ``radius`` are linked."""
    pairs = cKDTree(xy).query_pairs(radius, output_type="ndarray")
    n = len(xy)
    g = coo_array((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(g, directed=False)[1]


def _plane_rms(pts: np.ndarray) -> float:
    """Rms distance of the points to their least-squares plane."""
    c = pts - pts.mean(0)
    return float(np.linalg.svd(c, compute_uv=False)[-1] / math.sqrt(len(pts)))


def _kind(h95: float, area: float, p: EngineParams) -> str:
    if h95 < p.obj_lantern_max_h_m and area >= p.obj_lantern_min_area_m2:
        return "lantern"
    if h95 >= p.obj_lantern_max_h_m and area <= p.obj_chimney_max_area_m2:
        return "chimney"
    return "unknown"


def _axis_deg(outline: Outline) -> float:
    """The outline's dominant wall direction (degrees, mod 90): the length-weighted circular mean of its edge angles."""
    c = np.array(outline.drawn.exterior.coords)
    d = np.diff(c, axis=0)
    ang = 4.0 * np.arctan2(d[:, 1], d[:, 0])
    w = np.hypot(d[:, 0], d[:, 1])
    return float(np.degrees(np.arctan2((w * np.sin(ang)).sum(), (w * np.cos(ang)).sum())) / 4.0)


def _footprint(xy: np.ndarray, axis_deg: float, pad: float, p: EngineParams):
    """The rectangle of the returns grown by ``pad`` on every side: aligned with the walls, unless the minimum rotated
    rectangle is much smaller (``obj_align_ratio``): a few returns fit a free rectangle too well, so a free angle must
    earn its place."""
    pts = MultiPoint(xy)
    free = pts.minimum_rotated_rectangle
    aligned = shapely.affinity.rotate(shapely.affinity.rotate(pts, -axis_deg, origin=(0, 0)).envelope, axis_deg,
                                      origin=(0, 0))
    if aligned.geom_type != "Polygon":  # returns on one line: a thin box round them
        aligned = pts.convex_hull.buffer(max(pad, 0.05), cap_style="square").minimum_rotated_rectangle
    rect = free if free.geom_type == "Polygon" and aligned.area > p.obj_align_ratio * free.area else aligned
    return orient(rect.buffer(pad, join_style="mitre"), 1.0)


def find_objects(context: np.ndarray, facets: list[Facet], outline: Outline, ground_z: float,
                 params: EngineParams = DEFAULT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Objects standing on the roof and the planar blobs that are really roof parts. See the module docstring.

    ``context``: (n, 4) x, y, z, class (world frame, metres); ``facets`` and ``outline`` as the engine returns them;
    ``ground_z``: site ground height (m), the fallback when the cloud has no class-2 returns near the roof.
    """
    p = params
    ctx = np.asarray(context, float).reshape(-1, 4)
    if not facets or outline is None or len(ctx) == 0:
        return [], []
    cand = _candidates(ctx[np.isfinite(ctx).all(1)], outline, ground_z, p)
    if len(cand) < p.obj_min_points:
        return [], []
    r = _residuals(cand, facets)
    inside = shapely.contains_xy(outline.drawn, cand[:, 0], cand[:, 1])
    density = max(MIN_DENSITY, float(inside.sum()) / outline.drawn.area)
    spacing = 1.0 / math.sqrt(density)
    up = np.flatnonzero(r > p.obj_above_plane_m)
    if len(up) < p.obj_min_points:
        return [], []
    axis = _axis_deg(outline)
    lab = _blobs(cand[up, :2], max(p.obj_link_min_m, p.obj_link_spacings * spacing))
    pt_tree = cKDTree(cand[:, :2])
    edge = outline.drawn.exterior
    blobs = []
    for k in np.unique(lab):
        sel = up[lab == k]
        if len(sel) < p.obj_min_points:
            continue
        foot = _footprint(cand[sel, :2], axis, p.obj_pad_spacings * spacing, p)
        h95 = float(np.percentile(r[sel], 95))
        # canopy: roof returns seen through it, at the same place, with a wide height spread
        c0 = foot.centroid
        idx = np.array(pt_tree.query_ball_point([c0.x, c0.y], c0.distance(shapely.get_point(foot.exterior, 0)) + 1e-6),
                       int)
        near = idx[shapely.contains_xy(foot, cand[idx, 0], cand[idx, 1])]
        on_roof = float((np.abs(r[near]) < p.obj_on_plane_m).sum()) / max(len(near), 1)
        tree = ((1.0 - float(inside[sel].mean())) > p.obj_tree_outside_share or h95 > p.obj_tree_h95_m
                or (on_roof > p.obj_layered_share and float(np.std(r[sel])) > p.obj_layered_spread_m))
        blobs.append((sel, foot, h95, tree))
    crowns = [foot for _, foot, _, tree in blobs if tree]
    objects: list[dict[str, Any]] = []
    mislabelled: list[dict[str, Any]] = []
    for sel, foot, h95, tree in blobs:
        area = foot.area
        ring = np.array(foot.exterior.coords)
        sides = sorted((float(np.hypot(*(ring[i + 1] - ring[i]))) for i in (0, 1)), reverse=True)
        if tree or area < p.obj_min_area_m2 or sides[1] < p.obj_min_side_m:
            continue
        if foot.distance(edge) < p.obj_edge_m:
            continue  # a parapet, a gutter or a wall along the roof edge
        if any(foot.distance(c) < p.obj_tree_reach_m for c in crowns):
            continue  # a blob beside a crown is the same tree: its edge over the roof
        big = area > p.obj_mislabel_area_m2
        if big and _plane_rms(cand[sel]) > p.obj_planar_rms_m:
            continue  # a large, uneven mass that is not a tree by the rules above: not an object, not a roof part
        c = foot.centroid
        under = [i for i, f in enumerate(facets) if f.polygon.contains(c)]
        j = under[0] if under else int(np.argmin([f.polygon.distance(c) for f in facets]))
        d: dict[str, Any] = {
            "center": [round(c.x * FT, 3), round(c.y * FT, 3)],
            "size_ft": [round(sides[0] * FT, 2), round(sides[1] * FT, 2)],
            "polygon": [[round(x * FT, 3), round(y * FT, 3)] for x, y in ring],
            "height_ft": round(h95 * FT, 2), "facet": facets[j].id, "returns": len(sel)}
        if big:
            d["area_sqft"] = round(area * SQFT, 1)
            mislabelled.append(d)
        else:
            objects.append({"kind": _kind(h95, area, p), **d})
    objects.sort(key=lambda o: (o["center"][0], o["center"][1]))
    mislabelled.sort(key=lambda o: (o["center"][0], o["center"][1]))
    return [{"id": f"o{n}", **o} for n, o in enumerate(objects, 1)], mislabelled
