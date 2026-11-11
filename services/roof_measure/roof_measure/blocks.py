"""Segment a roof into height-continuous BLOCKS from LiDAR + footprint.

WHY blocks and not planes: a flat roof with parapets, awnings and a hip section is easier to
recover as regions that are continuous in absolute height and share a surface class than by
fitting planes globally. This module only SEGMENTS (separate blocks, borders, outline
lengths); `skeleton`/`classify` in svc-model merge blocks and decide hip/gable/parapet.

Method (ported from the research prototype that worked on the site 1 sample):
1. Robust 0.25 m height raster inside the footprint (lower-half median of non-ground points
   within 0.3 m; cells whose z spread exceeds 0.5 m are trees/edges and dropped).
2. Each cell is flat (<4 deg, from a 5x5-smoothed gradient) or sloped, keyed by 45-degree
   aspect sector.
3. Connected components of equal key with height step < 0.12 m between neighbours.
   Absolute z is used because the ground falls ~3 m across the site, so height above
   ground would split flat roofs.
4. Polygonise, fit a plane per block (pitch, aspect, rms), compute shared borders and the
   outline length each block has on the footprint.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely import affinity, contains_xy
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .frame import FT_PER_M, M_PER_FT, Frame
from .lidar import MIN_ROOF_DENSITY, LidarTooSparse, PointCloud, acquired_range

log = logging.getLogger(__name__)

SCHEMA = "bond.roof_blocks/0.1"
FLAT_PITCH_MAX = 0.5  # contract section 1: pitch_rise <= 0.5 is flat
STEP_BASE_M = 0.08  # height step allowed between neighbours on a level plane, on top of cell*tan(tilt)
MAX_TILT_DEG = 60.0
MERGE_PITCH = 0.6  # coplanar merge: max pitch difference (rise per 12)
MERGE_ASPECT_DEG = 20.0
MERGE_GAP_M = 0.15  # coplanar merge: max plane-to-plane height gap along the shared border
MIN_BLOCK_M2 = 1.5  # keeps the 3-4 m2 south awnings alive, but only at the outline
SMALL_BLOCK_M2 = 3.5  # below this a block must touch the footprint outline to survive
EDGE_TOUCH_M = 0.6
OVERHANG_M = 0.6  # upper bound; blocks may extend this far beyond the footprint outline (real overhangs are 1-2 ft)
MAX_SPREAD_M = 0.5
MIN_HAG_M = 1.5
PLANE_RADIUS_M = 0.6  # neighbourhood for the per-cell plane fit
PLANE_RMS_M = 0.05  # a cell is planar when the local fit rms is below this


class BlocksError(ValueError):
    """The roof could not be segmented (too few points or no block survived)."""


# ---------------------------------------------------------------- plane helpers
def fit_plane(p: np.ndarray) -> np.ndarray:
    """Least-squares plane z = a x + b y + c."""
    a = np.column_stack([p[:, 0], p[:, 1], np.ones(len(p))])
    sol, *_ = np.linalg.lstsq(a, p[:, 2], rcond=None)
    return sol


def plane_props(pl: np.ndarray) -> tuple[float, float, float | None]:
    """(tilt deg, pitch rise per 12, downslope compass bearing or None when level)."""
    g = float(np.hypot(pl[0], pl[1]))
    if g < 1e-6:
        return 0.0, 0.0, None
    return (float(np.degrees(np.arctan(g))), g * 12.0,
            float(np.degrees(np.arctan2(-pl[0], -pl[1])) % 360.0))


# ---------------------------------------------------------------- result types
@dataclass
class Block:
    id: str
    kind: str
    polygon_m: Polygon  # frame-local metres (origin = frame origin)
    plan_area_sqft: float
    plan_area_in_footprint_sqft: float
    mean_z_m: float
    height_above_ground_ft: float
    pitch_rise: float
    aspect_deg: float | None
    rms_ft: float
    n_cells: int

    def polygon_ft(self) -> list[list[float]]:
        return _ring_ft(self.polygon_m)


def _bbox_size_ft(poly: Polygon) -> tuple[float, float]:
    minx, miny, maxx, maxy = poly.bounds
    return (maxx - minx) * FT_PER_M, (maxy - miny) * FT_PER_M


def _ring_ft(poly: Polygon) -> list[list[float]]:
    p = orient(poly, 1.0)
    return [[round(x * FT_PER_M, 2), round(y * FT_PER_M, 2)] for x, y in p.exterior.coords]


@dataclass
class BlockSet:
    frame: Frame
    footprint_m: Polygon  # frame-local metres
    blocks: list[Block]
    borders: list[dict]
    outline_edges: list[dict]
    lidar: dict
    address: dict = field(default_factory=dict)
    footprint_meta: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    _debug: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "address": self.address,
            "origin": {"lat": round(self.frame.origin_lat, 7), "lng": round(self.frame.origin_lng, 7)},
            "frame": {"epsg": self.frame.epsg, "x0_m": round(self.frame.x0_m, 3),
                      "y0_m": round(self.frame.y0_m, 3)},
            "footprint_ft": _ring_ft(self.footprint_m),
            "footprint_meta": self.footprint_meta,
            "lidar": self.lidar,
            "blocks": [{
                "id": b.id, "kind": b.kind, "polygon_ft": b.polygon_ft(),
                "plan_area_sqft": round(b.plan_area_sqft, 1),
                "plan_area_in_footprint_sqft": round(b.plan_area_in_footprint_sqft, 1),
                "mean_z_ft": round(b.mean_z_m * FT_PER_M, 2),
                "height_above_ground_ft": round(b.height_above_ground_ft, 2),
                "pitch_rise": round(b.pitch_rise, 2), "aspect_deg": None if b.aspect_deg is None
                else round(b.aspect_deg, 1) % 360,
                "rms_ft": round(b.rms_ft, 3), "n_cells": b.n_cells} for b in self.blocks],
            "borders": self.borders,
            "outline_edges": self.outline_edges,
            "extra": self.extra,
        }

    def to_json(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=1))

    def save_debug_png(self, path: str | Path) -> None:
        """Points by z, block polygons labelled with id/area/kind/pitch, borders in red/orange."""
        import matplotlib  # lazy: the `render` extra

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fw, fh = _bbox_size_ft(self.footprint_m)
        fig, ax = plt.subplots(figsize=(14, min(10.0, max(4.0, 14 * fh / max(fw, 1.0) + 2.0))))
        pts = self._debug.get("points")
        if pts is not None and len(pts):
            sc = ax.scatter(pts[:, 0] * FT_PER_M, pts[:, 1] * FT_PER_M, c=pts[:, 2], s=1.5, cmap="viridis")
            fig.colorbar(sc, ax=ax, label="z (m, absolute)", shrink=0.7)
        for b in self.blocks:
            geoms = b.polygon_m.geoms if hasattr(b.polygon_m, "geoms") else [b.polygon_m]
            for g in geoms:
                xs, ys = zip(*_ring_ft(g), strict=True)
                ax.fill(xs, ys, color="tab:orange" if b.kind == "sloped" else "tab:blue", alpha=0.25,
                        ec="k", lw=0.8)
            c = b.polygon_m.representative_point()
            pitch = f"{b.pitch_rise:.1f}/12" if b.kind == "sloped" else "flat"
            ax.text(c.x * FT_PER_M, c.y * FT_PER_M, f"{b.id}\n{b.plan_area_sqft:.0f} sf\n{b.kind} {pitch}",
                    ha="center", va="center", fontsize=7)
        for line in self._debug.get("border_lines", []):
            xs, ys = zip(*[(x * FT_PER_M, y * FT_PER_M) for x, y in line["xy"]], strict=True)
            ax.plot(xs, ys, color="red" if line["step_m"] > 0.3 else "orange", lw=2.5)
        fx, fy = zip(*_ring_ft(self.footprint_m), strict=True)
        ax.plot(fx, fy, "k-", lw=1.2)
        ax.set_aspect("equal")
        ax.set_xlabel("x east (ft)")
        ax.set_ylabel("y north (ft)")
        ax.set_title(f"Roof blocks ({len(self.blocks)}); red border = step > 0.3 m")
        fig.tight_layout()
        fig.savefig(path, dpi=70)
        plt.close(fig)


# ---------------------------------------------------------------- segmentation
def _fit_trimmed(p3: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Plane through cell heights, refit four times without outliers (parapet rims, edge cells)."""
    pl = fit_plane(p3)
    for _ in range(4):
        r = np.abs(p3[:, 2] - (pl[0] * p3[:, 0] + pl[1] * p3[:, 1] + pl[2]))
        keep = r < max(0.08, 2 * np.median(r))
        if keep.sum() > 10:
            pl = fit_plane(p3[keep])
    r = np.abs(p3[:, 2] - (pl[0] * p3[:, 0] + pl[1] * p3[:, 1] + pl[2]))
    return pl, r


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _merge_coplanar(lab: np.ndarray, flab: np.ndarray, val: np.ndarray, gx_: np.ndarray, gy_: np.ndarray,
                    cell: float) -> None:
    """Merge adjacent components that are one plane, in place on `lab` and `flab`.

    WHY: height-continuity growth splits a face at a dropped crease cell or a vent. Two components merge
    when they are the same kind, within 0.6/12 pitch and 20 degrees aspect, and their fitted planes
    agree within 0.15 m along the shared border. The best pair merges first, planes are refit, repeat.
    """
    planes: dict[int, tuple[np.ndarray, float, float | None]] = {}

    def plane_for(i: int) -> tuple[np.ndarray, float, float | None]:
        m = (lab == i) & np.isfinite(val)
        p3 = np.column_stack([gx_[m], gy_[m], val[m]])
        pl, _ = _fit_trimmed(p3)
        _, pitch, aspect = plane_props(pl)
        return pl, pitch, aspect

    for i in (int(v) for v in np.unique(lab[lab >= 0])):
        planes[i] = plane_for(i)
    while True:
        border: dict[tuple[int, int], list[np.ndarray]] = {}
        for a, b, ox, oy in ((flab[:, :-1], flab[:, 1:], cell / 2, 0.0), (flab[:-1, :], flab[1:, :], 0.0, cell / 2)):
            m = (a >= 0) & (b >= 0) & (a != b)
            jj, ii = np.nonzero(m)
            for j, i in zip(jj, ii, strict=True):
                pair = (min(int(a[j, i]), int(b[j, i])), max(int(a[j, i]), int(b[j, i])))
                border.setdefault(pair, []).append(np.array([gx_[j, i] + ox, gy_[j, i] + oy]))
        best: tuple[float, int, int] | None = None
        for (p, q), pts in border.items():
            if len(pts) < 3 or p not in planes or q not in planes:
                continue
            (pa, pitch_a, asp_a), (pb, pitch_b, asp_b) = planes[p], planes[q]
            flat_a, flat_b = pitch_a <= FLAT_PITCH_MAX, pitch_b <= FLAT_PITCH_MAX
            if flat_a != flat_b or abs(pitch_a - pitch_b) >= MERGE_PITCH:
                continue
            if not flat_a and (asp_a is None or asp_b is None or _angle_diff(asp_a, asp_b) >= MERGE_ASPECT_DEG):
                continue
            xy = np.array(pts)
            za = pa[0] * xy[:, 0] + pa[1] * xy[:, 1] + pa[2]
            zb = pb[0] * xy[:, 0] + pb[1] * xy[:, 1] + pb[2]
            gap = float(np.mean(np.abs(za - zb)))
            if gap < MERGE_GAP_M and (best is None or gap < best[0]):
                best = (gap, p, q)
        if best is None:
            return
        _, p, q = best
        lab[lab == q] = p
        flab[flab == q] = p
        del planes[q]
        planes[p] = plane_for(p)


def _local_ground(ground_tree: cKDTree | None, ground_z: np.ndarray, xy: np.ndarray, fallback: float) -> np.ndarray:
    """Median z of the 8 nearest class-2 points; the fallback when there is no ground at all."""
    if ground_tree is None:
        return np.full(len(xy), fallback)
    k = min(8, len(ground_z))
    _, ii = ground_tree.query(xy, k=k)
    return np.median(ground_z[np.atleast_2d(ii.reshape(len(xy), -1))], axis=1)


def _snap_to_outline(poly, outline: Polygon, tol: float):
    """Move vertices within `tol` of the outline onto it; vertices farther away stay (overhangs)."""
    ext = outline.exterior

    def fix(ring) -> list[tuple[float, float]]:
        out = []
        for px, py in ring.coords:
            p = shapely.Point(px, py)
            if ext.distance(p) <= tol:
                n = ext.interpolate(ext.project(p))
                out.append((n.x, n.y))
            else:
                out.append((px, py))
        return out

    if isinstance(poly, MultiPolygon):
        return MultiPolygon([_snap_to_outline(g, outline, tol) for g in poly.geoms])
    if not isinstance(poly, Polygon) or poly.is_empty:
        return poly
    return Polygon(fix(poly.exterior), [fix(r) for r in poly.interiors])


def _largest_ring(g) -> Polygon | None:
    if g.is_empty:
        return None
    if isinstance(g, MultiPolygon):
        g = max(g.geoms, key=lambda p: p.area)
    if not isinstance(g, Polygon):
        parts = [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]
        if not parts:
            return None
        g = max(parts, key=lambda p: p.area)
    return Polygon(g.exterior)


def segment_blocks(points: PointCloud, footprint_m: Polygon, frame: Frame, *, cell_m: float = 0.25,
                   address: dict | None = None, footprint_meta: dict | None = None) -> BlockSet:
    """Segment the roof under `footprint_m` (metres in `frame.epsg`) into blocks."""
    cell = cell_m
    fpl = orient(affinity.translate(footprint_m, -frame.x0_m, -frame.y0_m), 1.0)
    x = np.asarray(points.x) - frame.x0_m
    y = np.asarray(points.y) - frame.y0_m
    z = np.asarray(points.z)
    cls = np.asarray(points.classification)
    is_ground = cls == 2

    # ---- ground and height above ground
    g_xy = np.column_stack([x[is_ground], y[is_ground]])
    g_z = z[is_ground]
    gtree = cKDTree(g_xy) if len(g_xy) >= 3 else None
    ring = contains_xy(fpl.buffer(8.0), x[is_ground], y[is_ground]) & ~contains_xy(fpl.buffer(0.5), x[is_ground], y[is_ground])
    ground_z_site = float(np.median(g_z[ring])) if ring.any() else float(np.median(g_z) if len(g_z) else np.percentile(z, 2))
    # a fixed 0.6 m would add 50% to an 8 m2 shed; scale the overhang with the building, capped at 0.6 m
    overhang = min(OVERHANG_M, 0.08 * float(np.sqrt(fpl.area)))
    reach0 = fpl.buffer(overhang)
    # points beyond the clip distance still feed the per-cell plane fits of cells at the clip edge
    near = contains_xy(fpl.buffer(overhang + PLANE_RADIUS_M), x, y)
    hag = np.full(len(z), np.nan)
    if near.any():
        hag[near] = z[near] - _local_ground(gtree, g_z, np.column_stack([x[near], y[near]]), ground_z_site)
    sel = near & ~is_ground & (hag > MIN_HAG_M)
    pp = np.column_stack([x[sel], y[sel], z[sel]])
    if len(pp) < 30:
        raise BlocksError("Too few LiDAR roof points inside the footprint to segment.")
    roof_mask = contains_xy(reach0, x, y) & ~is_ground & (hag > MIN_HAG_M)  # nan hag compares False
    inside_pts = int((contains_xy(fpl, x, y) & ~is_ground & (hag > MIN_HAG_M)).sum())
    roof_density = inside_pts / fpl.area if fpl.area else 0.0
    if roof_density < MIN_ROOF_DENSITY:
        raise LidarTooSparse(points.meta.get("project"), points.meta.get("year"), roof_density, MIN_ROOF_DENSITY)
    points_on_roof = int(roof_mask.sum())

    # ---- 1. robust raster
    minx, miny, maxx, maxy = reach0.bounds
    nx, ny = int(np.ceil((maxx - minx) / cell)), int(np.ceil((maxy - miny) / cell))
    xs = minx + (np.arange(nx) + 0.5) * cell
    ys = miny + (np.arange(ny) + 0.5) * cell
    gx_, gy_ = np.meshgrid(xs, ys)
    reach = reach0  # roofs overhang the county wall line by a foot or two
    inside = contains_xy(reach, gx_, gy_)
    tree = cKDTree(pp[:, :2])
    # Never invent area: a cell belongs to the roof only if a roof return lies within a few point
    # spacings (1.2/sqrt(density), at least 0.15 m). Without this the 0.3/0.6 m fit windows grow every
    # block by half a window, which is +50% on an 8 m2 shed.
    near_m = max(0.15, 1.4 / np.sqrt(roof_density))
    cj0, ci0 = np.nonzero(inside)
    d_pt, _ = tree.query(np.column_stack([gx_[cj0, ci0], gy_[cj0, ci0]]))
    inside[cj0[d_pt > near_m], ci0[d_pt > near_m]] = False
    val = np.full(gx_.shape, np.nan)
    spread = np.full(gx_.shape, np.nan)
    jj, ii = np.nonzero(inside)
    nbrs = tree.query_ball_point(np.column_stack([gx_[jj, ii], gy_[jj, ii]]), 0.30)
    for j, i, nb in zip(jj, ii, nbrs, strict=True):
        if len(nb) < 3:
            continue
        zz = np.sort(pp[nb, 2])
        k = max(2, int(0.5 * len(zz)))
        val[j, i] = np.median(zz[:k])
        spread[j, i] = zz[-1] - zz[0]
    ok = np.isfinite(val)

    # ---- 2. surface class per cell from a LOCAL plane fit on the raw points. A smoothed raster
    # blurs 1 m wide awnings and hip creases into mixed aspects; a plane fit with a residual test
    # classifies planar cells exactly and drops crease/edge cells (the 1 m fill below reclaims them).
    tilt = np.full(gx_.shape, np.nan)
    asp = np.full(gx_.shape, np.nan)
    planar = np.zeros(gx_.shape, bool)
    cj_, ci_ = np.nonzero(ok)
    nb2 = tree.query_ball_point(np.column_stack([gx_[cj_, ci_], gy_[cj_, ci_]]), PLANE_RADIUS_M)
    for j, i, nb in zip(cj_, ci_, nb2, strict=True):
        if len(nb) < 8:
            continue
        q = pp[nb]
        q0 = q - q.mean(axis=0)
        a = np.column_stack([q0[:, 0], q0[:, 1], np.ones(len(q0))])
        sol, *_ = np.linalg.lstsq(a, q0[:, 2], rcond=None)
        res = q0[:, 2] - a @ sol
        if np.sqrt(np.mean(res**2)) > PLANE_RMS_M:
            continue
        planar[j, i] = True
        tilt[j, i] = np.degrees(np.arctan(np.hypot(sol[0], sol[1])))
        asp[j, i] = np.degrees(np.arctan2(-sol[0], -sol[1])) % 360
    # Tree filter: a cell's z spread must stay under 0.5 m, plus what its own slope explains over the
    # 0.6 m window (a 9/12 plane spans 0.45 m by itself). Non-planar cells get no slope allowance.
    allow = MAX_SPREAD_M + 2 * 0.3 * np.tan(np.radians(np.where(planar, np.minimum(tilt, MAX_TILT_DEG), 0.0)))
    good = ok & (spread <= allow)
    key = np.full(gx_.shape, -9)
    flatc = planar & (tilt < 4.0)
    slopec = planar & (tilt >= 4.0) & (tilt <= MAX_TILT_DEG)
    key[flatc] = -1
    key[slopec] = np.round(asp[slopec] / 45.0).astype(int) % 8
    tilt_rad = np.radians(np.nan_to_num(tilt))

    # ---- 3. components
    edge_dist = shapely.distance(fpl.exterior, shapely.points(gx_, gy_))
    lab = np.full(gx_.shape, -1)
    seen = np.zeros(gx_.shape, bool)
    nid = 0
    for j0, i0 in np.argwhere(good & (key > -9)):
        if seen[j0, i0]:
            continue
        k0 = key[j0, i0]
        stack = [(j0, i0)]
        seen[j0, i0] = True
        cells = []
        while stack:
            j, i = stack.pop()
            cells.append((j, i))
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jn, in_ = j + dj, i + di
                if (0 <= jn < ny and 0 <= in_ < nx and good[jn, in_] and not seen[jn, in_]
                        and key[jn, in_] == k0
                        and abs(val[jn, in_] - val[j, i]) < cell * np.tan(tilt_rad[j, i]) + STEP_BASE_M):
                    seen[jn, in_] = True
                    stack.append((jn, in_))
        area = len(cells) * cell**2
        # Small blocks only count at the outline (awnings, canopies); small interior ones are
        # crease or clutter fragments, left to the 1 m fill to merge into their neighbours.
        at_edge = min(edge_dist[j, i] for j, i in cells) <= EDGE_TOUCH_M
        if area >= SMALL_BLOCK_M2 or (area >= MIN_BLOCK_M2 and at_edge):
            for j, i in cells:
                lab[j, i] = nid
            nid += 1
    # fill tree-dropped / edge cells within 1 m to the nearest block
    dist, (fj, fi) = ndimage.distance_transform_edt(lab < 0, return_indices=True)
    flab = lab.copy()
    m = inside & (lab < 0) & (dist * cell <= 1.0)
    # only cells with roof returns nearby: an empty margin is not roof (keeps coverage near 100%)
    mj, mi = np.nonzero(m)
    has_pts = tree.query_ball_point(np.column_stack([gx_[mj, mi], gy_[mj, mi]]), 0.5, return_length=True) > 0
    m[mj[~has_pts], mi[~has_pts]] = False
    flab[m] = lab[fj[m], fi[m]]
    _merge_coplanar(lab, flab, val, gx_, gy_, cell)

    # ---- 4. polygons + planes
    raw: list[dict] = []
    for b in sorted(int(v) for v in np.unique(lab[lab >= 0])):
        js, is_ = np.nonzero(flab == b)
        poly = unary_union([box(minx + i * cell, miny + j * cell, minx + (i + 1) * cell, miny + (j + 1) * cell)
                            for j, i in zip(js, is_, strict=True)])
        poly = poly.buffer(0.2).buffer(-0.2).intersection(reach).simplify(0.15)
        poly = _snap_to_outline(poly, fpl, 0.5)
        if not poly.is_valid:
            poly = poly.buffer(0)
        poly = _largest_ring(poly.intersection(reach))
        if poly is None or poly.area < 0.5:
            continue
        core = lab == b
        p3 = np.column_stack([gx_[core], gy_[core], val[core]])
        pl, r = _fit_trimmed(p3)
        _, pitch, aspect = plane_props(pl)
        raw.append({"old": b, "poly": poly, "pitch": pitch, "aspect": aspect, "mean_z": float(p3[:, 2].mean()),
                    "rms_ft": float(np.sqrt(np.mean(r**2))) * FT_PER_M, "n": int(core.sum())})
    raw.sort(key=lambda d: d["poly"].area, reverse=True)
    relab = np.full(flab.shape, -1)
    relab_core = np.full(lab.shape, -1)
    blocks: list[Block] = []
    for n, d in enumerate(raw):
        relab[flab == d["old"]] = n
        relab_core[lab == d["old"]] = n
        poly = d["poly"]
        rim = poly.buffer(6.0).difference(fpl.buffer(0.5))
        gm = contains_xy(rim, g_xy[:, 0], g_xy[:, 1]) if len(g_xy) else np.zeros(0, bool)
        gz = float(np.median(g_z[gm])) if gm.sum() >= 5 else ground_z_site
        flat = d["pitch"] <= FLAT_PITCH_MAX
        blocks.append(Block(
            id=f"k{n}", kind="flat" if flat else "sloped", polygon_m=poly,
            plan_area_sqft=poly.area * FT_PER_M**2,
            plan_area_in_footprint_sqft=poly.intersection(fpl).area * FT_PER_M**2, mean_z_m=d["mean_z"],
            height_above_ground_ft=(d["mean_z"] - gz) * FT_PER_M, pitch_rise=d["pitch"],
            aspect_deg=None if flat else d["aspect"], rms_ft=d["rms_ft"], n_cells=d["n"]))

    # ---- 5. borders and outline
    borders: list[dict] = []
    border_lines: list[dict] = []
    signed: dict[str, float] = {}
    for a in range(len(blocks)):
        for b in range(a + 1, len(blocks)):
            ln = blocks[a].polygon_m.boundary.intersection(blocks[b].polygon_m.buffer(0.4))
            if ln.is_empty or ln.length < 1.0:
                continue
            zone = ln.buffer(1.0)
            near_zone = contains_xy(zone, gx_, gy_)
            ma, mb = (relab_core == a) & near_zone, (relab_core == b) & near_zone
            if ma.sum() < 3 or mb.sum() < 3:
                continue
            step = float(np.median(val[mb]) - np.median(val[ma]))
            borders.append({"a": blocks[a].id, "b": blocks[b].id, "length_ft": round(ln.length * FT_PER_M, 1),
                            "step_ft": round(abs(step) * FT_PER_M, 2)})
            signed[f"{blocks[a].id}|{blocks[b].id}"] = round(step * FT_PER_M, 2)
            segs = ln.geoms if hasattr(ln, "geoms") else [ln]
            for s in segs:
                border_lines.append({"xy": list(s.coords), "step_m": abs(step)})
    outline_edges = []
    rim_zone = fpl.exterior.buffer(0.5)
    for blk in blocks:
        ln = blk.polygon_m.boundary.intersection(rim_zone)
        outline_edges.append({"block": blk.id, "length_ft": round(ln.length * FT_PER_M, 1)})

    if not blocks:
        raise BlocksError("No roof block survived segmentation (roof density "
                          f"{roof_density:.1f} points/m2); the LiDAR may be too thin or the footprint wrong.")
    fp_area_m2 = fpl.area
    acq = acquired_range(np.asarray(points.gps_time)[roof_mask]) or points.meta.get("acquired")
    lidar = {"project": points.meta.get("project"), "acquired": acq, "year": points.meta.get("year"),
             "points_on_roof": points_on_roof, "density_per_m2": round(points_on_roof / fp_area_m2, 1),
             "ground_z_m": round(ground_z_site, 2), "epsg": frame.epsg}
    bs = BlockSet(frame=frame, footprint_m=fpl, blocks=blocks, borders=borders, outline_edges=outline_edges,
                  lidar=lidar, address=address or {}, footprint_meta=footprint_meta or {},
                  extra={"border_signed_step_ft": signed,
                         "border_lines_ft": [{"xy": [[round(px * FT_PER_M, 2), round(py * FT_PER_M, 2)]
                                                      for px, py in ln["xy"]]} for ln in border_lines],
                         "lidar_meta": {k: points.meta.get(k) for k in ("fallback_used", "skipped", "box_m", "warnings", "z_scale")},
                         "cell_m": cell, "overhang_m": round(overhang, 3), "cells_dropped_spread": int((ok & (spread > MAX_SPREAD_M)).sum())})
    bs._debug = {"points": pp, "border_lines": border_lines}
    log.info("segmented %d blocks, %d borders", len(blocks), len(borders))
    return bs


__all__ = ["M_PER_FT", "Block", "BlockSet", "segment_blocks"]
