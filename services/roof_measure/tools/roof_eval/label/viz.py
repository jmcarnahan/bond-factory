"""roofviz: rendering + measuring helpers for roof truth labelling.

Independent of the product pipeline: uses only numpy/scipy/shapely/matplotlib.
All coordinates are the house's LOCAL frame in METRES (x east, y north); z absolute metres.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
import numpy as np
from scipy import ndimage as ndi
from scipy.interpolate import griddata
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely import wkt as _wkt
from shapely.geometry import LineString, Polygon

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap, hsv_to_rgb

M2FT = 1 / 0.3048
SQM2SQFT = M2FT * M2FT
PAD = 8.0
RES = 0.1  # metres per pixel of every raster
FLAT_RISE = 2.0  # < 2/12 = flat


# ----------------------------------------------------------------------------- loading
class House:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.meta = json.loads((self.folder / "meta.json").read_text())
        self.house_id = (
            self.folder.name
        )  # an opaque id chosen by the caller; nothing here reads or writes an address
        self.fp = _wkt.loads(self.meta["footprint_local_m_wkt"])
        w = np.load(self.folder / "points_wide.npy").astype(np.float64)
        # privacy: remove the absolute elevation (whole metres) before anything is rendered or measured; restored in the written truth
        self.z0 = float(math.floor(np.percentile(w[:, 2], 1)))
        w[:, 2] -= self.z0
        self.w = w
        x0, y0, x1, y1 = self.fp.bounds
        # snap bbox to whole metres so the grid labels are clean
        self.bbox = (math.floor(x0 - PAD), math.floor(y0 - PAD), math.ceil(x1 + PAD), math.ceil(y1 + PAD))
        self.nx = round((self.bbox[2] - self.bbox[0]) / RES)
        self.ny = round((self.bbox[3] - self.bbox[1]) / RES)
        g = w[w[:, 3] == 2]
        self.ground = g
        self._gtree = cKDTree(g[:, :2]) if len(g) else None
        hag = w[:, 2] - self.ground_z(w[:, 0], w[:, 1])
        self.hag = hag
        self.ng = w[(w[:, 3] != 2) & (hag > 1.0)]  # non-ground returns above 1 m
        self.ng_hag = hag[(w[:, 3] != 2) & (hag > 1.0)]
        self._rasters = None

    def ground_z(self, x, y):
        """Local ground height: median of the 8 nearest ground returns."""
        x = np.atleast_1d(np.asarray(x, float))
        y = np.atleast_1d(np.asarray(y, float))
        if self._gtree is None:
            return np.full(x.shape, float(np.percentile(self.w[:, 2], 2)))
        k = min(8, len(self.ground))
        _, idx = self._gtree.query(np.c_[x, y], k=k)
        return np.median(self.ground[idx, 2].reshape(len(x), -1), axis=1)

    # ------------------------------------------------------------------------- rasters
    def rasters(self):
        """Per-pixel (0.1 m) local plane fit of the top surface: z, slope (rise/12), aspect (deg), rms; plus DSM, HAG."""
        if self._rasters is not None:
            return self._rasters
        bx0, by0, bx1, by1 = self.bbox
        w = self.w
        # --- DSM at 0.25 m: highest return per cell, linear interpolation, resampled to 0.1 m
        c = 0.25
        nx, ny = int((bx1 - bx0) / c), int((by1 - by0) / c)
        ix = ((w[:, 0] - bx0) / c).astype(int)
        iy = ((w[:, 1] - by0) / c).astype(int)
        ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
        top = np.full((ny, nx), -np.inf)
        np.maximum.at(top, (iy[ok], ix[ok]), w[ok, 2])
        have = np.isfinite(top)
        cy, cx = np.nonzero(have)
        gx, gy = np.meshgrid(bx0 + (np.arange(self.nx) + 0.5) * RES, by0 + (np.arange(self.ny) + 0.5) * RES)
        pts = np.c_[bx0 + (cx + 0.5) * c, by0 + (cy + 0.5) * c]
        dsm = griddata(pts, top[have], (gx, gy), method="linear")
        nn = griddata(pts, top[have], (gx, gy), method="nearest")
        dsm = np.where(np.isfinite(dsm), dsm, nn)
        gz = self.ground_z(gx.ravel(), gy.ravel()).reshape(gx.shape)
        # --- local plane fit at 0.2 m, radius 0.6 m, top surface only
        s = 0.2
        mx, my = round((bx1 - bx0) / s), round((by1 - by0) / s)
        qx, qy = np.meshgrid(bx0 + (np.arange(mx) + 0.5) * s, by0 + (np.arange(my) + 0.5) * s)
        tree = cKDTree(w[:, :2])
        nbrs = tree.query_ball_point(np.c_[qx.ravel(), qy.ravel()], r=0.45)
        A = np.full(qx.size, np.nan)
        B = A.copy()
        R = A.copy()
        Z = A.copy()
        for i, nb in enumerate(nbrs):
            if len(nb) < 5:
                continue
            p = w[nb, :3]
            keep = p[:, 2] > np.percentile(p[:, 2], 95) - 1.5
            p = p[keep]
            if len(p) < 5:
                continue
            X = np.c_[p[:, 0] - qx.flat[i], p[:, 1] - qy.flat[i], np.ones(len(p))]
            co, *_ = np.linalg.lstsq(X, p[:, 2], rcond=None)
            r = p[:, 2] - X @ co
            mad = np.median(np.abs(r - np.median(r))) * 1.4826 + 0.02
            k2 = np.abs(r) < 2.5 * mad
            if k2.sum() >= 5 and k2.sum() < len(p):
                co, *_ = np.linalg.lstsq(X[k2], p[k2, 2], rcond=None)
                r = p[k2, 2] - X[k2] @ co
            A[i], B[i], Z[i], R[i] = co[0], co[1], co[2], math.sqrt(float(np.mean(r * r)))
        up = lambda a: np.kron(a.reshape(my, mx), np.ones((2, 2)))[: self.ny, : self.nx]
        a, b, rms, zfit = up(A), up(B), up(R), up(Z)
        slope = 12.0 * np.hypot(a, b)
        aspect = (np.degrees(np.arctan2(-a, -b)) + 360.0) % 360.0  # downslope, 0 = N, 90 = E
        self._rasters = {
            "dsm": dsm,
            "hag": dsm - gz,
            "slope": slope,
            "aspect": aspect,
            "rms": rms,
            "zfit": zfit,
            "a": a,
            "b": b,
        }
        return self._rasters

    # ------------------------------------------------------------------------- measuring
    def roof_points_in(self, poly: Polygon, shrink=0.0, min_hag=1.0):
        q = poly.buffer(-shrink) if shrink else poly
        if q.is_empty:
            q = poly
        p = self.ng[self.ng_hag > min_hag]
        m = contains_xy(q, p[:, 0], p[:, 1])
        return p[m, :3]

    def fit_plane(self, polygon, shrink=0.25):
        """Robust plane through the LiDAR returns inside a hand-drawn polygon (local metres)."""
        poly = Polygon(polygon)
        if not poly.is_valid:
            poly = poly.buffer(0)
        plan = poly.area
        p = self.roof_points_in(poly, shrink)
        for sh in (0.12, 0.0):  # small facet: use returns closer to its edges
            if len(p) >= 15:
                break
            p = self.roof_points_in(poly, sh)
        out = {"plan_area_sqft": round(plan * SQM2SQFT, 1), "points": len(p)}
        if len(p) < 6:
            out.update(error="fewer than 6 LiDAR returns inside the polygon", plane=None)
            return out
        X = np.c_[p[:, 0], p[:, 1], np.ones(len(p))]
        best = None
        rng = np.random.default_rng(7)
        for _ in range(200):  # small RANSAC: dominant plane
            s = rng.choice(len(p), 3, replace=False)
            try:
                co = np.linalg.solve(X[s], p[s, 2])
            except np.linalg.LinAlgError:
                continue
            inl = np.abs(p[:, 2] - X @ co) < 0.10
            if best is None or inl.sum() > best.sum():
                best = inl
        if best is None or best.sum() < 6:
            best = np.ones(len(p), bool)
        co, *_ = np.linalg.lstsq(X[best], p[best, 2], rcond=None)
        r = p[:, 2] - X @ co
        inl = np.abs(r) < 0.12
        if inl.sum() >= 6:
            co, *_ = np.linalg.lstsq(X[inl], p[inl, 2], rcond=None)
            r = p[:, 2] - X @ co
            inl = np.abs(r) < 0.12
        a, b, c = map(float, co)
        rise = 12.0 * math.hypot(a, b)
        out.update(
            plane=[round(a, 5), round(b, 5), round(c, 4)],
            pitch_rise=round(rise, 2),
            aspect_deg=round((math.degrees(math.atan2(-a, -b)) + 360) % 360, 1),
            roof_type="flat" if rise < FLAT_RISE else "pitched",
            rms_m=round(float(np.sqrt(np.mean(r[inl] ** 2))), 3) if inl.any() else None,
            inlier_fraction=round(float(inl.mean()), 3),
            above_plane_fraction=round(float((r > 0.12).mean()), 3),
            below_plane_fraction=round(float((r < -0.12).mean()), 3),
            area_sqft=round(plan * math.sqrt(1 + a * a + b * b) * SQM2SQFT, 1),
            mean_height_above_ground_m=round(
                float(np.mean(p[inl, 2]) - float(self.ground_z(*poly.centroid.coords[0])[0])), 2
            ),
        )
        return out

    def intersect_planes(self, poly_a, poly_b):
        """Line where the two fitted planes meet (candidate ridge / hip / valley), clipped to the polygons' joint bbox."""
        fa, fb = self.fit_plane(poly_a), self.fit_plane(poly_b)
        if not fa.get("plane") or not fb.get("plane"):
            return {"error": "plane fit failed", "a": fa, "b": fb}
        a1, b1, c1 = fa["plane"]
        a2, b2, c2 = fb["plane"]
        da, db, dc = a1 - a2, b1 - b2, c1 - c2
        if math.hypot(da, db) < 1e-3:
            return {"error": "planes are parallel", "a": fa, "b": fb}
        U = Polygon(poly_a).union(Polygon(poly_b)).envelope.buffer(1.0).envelope
        x0, y0, x1, y1 = U.bounds
        if abs(db) > abs(da):
            ln = LineString([(x0 - 5, -(da * (x0 - 5) + dc) / db), (x1 + 5, -(da * (x1 + 5) + dc) / db)])
        else:
            ln = LineString([(-(db * (y0 - 5) + dc) / da, y0 - 5), (-(db * (y1 + 5) + dc) / da, y1 + 5)])
        seg = ln.intersection(U)
        if seg.is_empty:
            return {"error": "intersection lies outside the polygons", "a": fa, "b": fb}
        (xa, ya), (xb, yb) = next(iter(seg.coords)), list(seg.coords)[-1]
        za, zb = a1 * xa + b1 * ya + c1, a1 * xb + b1 * yb + c1
        return {
            "line": [[round(xa, 2), round(ya, 2), round(za, 2)], [round(xb, 2), round(yb, 2), round(zb, 2)]],
            "slope_along_line_rise_per_12": round(
                12 * abs(zb - za) / max(1e-6, math.hypot(xb - xa, yb - ya)), 2
            ),
            "note": "the true edge is the part of this line where both facets exist; trim it by eye",
            "a": {k: fa[k] for k in ("pitch_rise", "aspect_deg", "rms_m")},
            "b": {k: fb[k] for k in ("pitch_rise", "aspect_deg", "rms_m")},
        }

    def profile(self, p0, p1, half_width=0.4):
        p0 = np.array(p0, float)
        p1 = np.array(p1, float)
        d = p1 - p0
        L = float(np.hypot(*d))
        u = d / L
        n = np.array([-u[1], u[0]])
        q = self.w[:, :2] - p0
        t = q @ u
        off = q @ n
        m = (t >= 0) & (t <= L) & (np.abs(off) <= half_width)
        return t[m], self.w[m, 2], self.w[m, 3], L

    def profile_table(self, p0, p1, step=0.5):
        """Median top-surface height above ground every `step` metres along a line (text version of a profile cut)."""
        t, z, _cls, L = self.profile(p0, p1)
        g = float(np.median(self.ground_z([p0[0], p1[0]], [p0[1], p1[1]])))
        rows = []
        for s in np.arange(0, L, step):
            m = (t >= s) & (t < s + step)
            if m.sum() == 0:
                rows.append([round(float(s + step / 2), 2), None])
                continue
            zz = z[m]
            top = zz[zz > np.percentile(zz, 90) - 0.5]
            rows.append([round(float(s + step / 2), 2), round(float(np.median(top)) - g, 2)])
        return {"length_m": round(L, 2), "ground_z_m": round(g, 2), "distance_m__height_above_ground_m": rows}


# ----------------------------------------------------------------------------- drawing
def _axes(h: House, title, px_per_m=30):
    bx0, by0, bx1, by1 = h.bbox
    wpx, hpx = (bx1 - bx0) * px_per_m + 170, (by1 - by0) * px_per_m + 150
    fig = plt.figure(figsize=(wpx / 100, hpx / 100), dpi=100)
    ax = fig.add_axes([70 / wpx, 60 / hpx, (bx1 - bx0) * px_per_m / wpx, (by1 - by0) * px_per_m / hpx])
    ax.set_xlim(bx0, bx1)
    ax.set_ylim(by0, by1)
    ax.set_aspect("equal")
    ax.set_xticks(np.arange(bx0, bx1 + 1, 2))
    ax.set_yticks(np.arange(by0, by1 + 1, 2))
    ax.set_xticks(np.arange(bx0, bx1 + 1, 1), minor=True)
    ax.set_yticks(np.arange(by0, by1 + 1, 1), minor=True)
    ax.tick_params(labelsize=8, top=True, right=True, labeltop=True, labelright=True)
    ax.set_xlabel("x east (m, local frame)", fontsize=8)
    ax.set_ylabel("y north (m)", fontsize=8)
    fig.text(0.5, 1 - 14 / hpx, title, ha="center", va="top", fontsize=10)
    return fig, ax


def _decor(h: House, ax, color="k", grid_color="k"):
    bx0, by0, bx1, by1 = h.bbox
    ax.grid(True, which="major", color=grid_color, lw=0.5, alpha=0.55)
    ax.grid(True, which="minor", color=grid_color, lw=0.3, alpha=0.3)
    x, y = h.fp.exterior.xy
    ax.plot(x, y, color=color, lw=1.6, ls="--", label="county outline")
    ax.plot(x, y, color="w", lw=0.6, ls="--")
    ax.annotate(
        "N",
        xy=(bx1 - 1.2, by1 - 0.6),
        xytext=(bx1 - 1.2, by1 - 3.2),
        ha="center",
        va="center",
        fontsize=12,
        color=color,
        fontweight="bold",
        arrowprops={"arrowstyle": "-|>", "color": color, "lw": 2},
        bbox={"boxstyle": "round", "fc": "w", "ec": "none", "alpha": 0.7},
    )
    ax.plot([bx0 + 1, bx0 + 6], [by0 + 0.8, by0 + 0.8], color=color, lw=4, solid_capstyle="butt")
    ax.text(
        bx0 + 3.5,
        by0 + 1.1,
        "5 m (16.4 ft)",
        ha="center",
        va="bottom",
        fontsize=8,
        color=color,
        bbox={"boxstyle": "round", "fc": "w", "ec": "none", "alpha": 0.7},
    )


def _save(fig, path):
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return str(path)


def aspect_rgb(aspect, slope, hag=None):
    hsv = np.zeros(aspect.shape + (3,))
    hsv[..., 0] = np.nan_to_num(aspect) / 360.0
    hsv[..., 1] = np.clip(np.nan_to_num(slope) / 4.0, 0.35, 1)  # full colour from 4/12 up
    hsv[..., 2] = 1.0
    rgb = hsv_to_rgb(hsv)
    flat = np.nan_to_num(slope) < FLAT_RISE
    rgb[flat] = 0.72 * 0.8 + 0.2 * rgb[flat]  # flat = grey with a hint of the hue
    rgb[np.nan_to_num(slope) > 24] = 0.25  # walls / tree edges = dark
    rgb[~np.isfinite(slope)] = 1.0
    if hag is not None:
        low = np.nan_to_num(hag) < 1.5
        rgb[low] = rgb[low] * 0.25 + 0.75 * np.array([1, 1, 1.0]) * 0.92  # wash out the ground
    return rgb


def render_all(h: House, outdir, profiles=None):
    """Write the model-input images. Returns {name: path}."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    r = h.rasters()
    ext = (h.bbox[0], h.bbox[2], h.bbox[1], h.bbox[3])
    out = {}
    # (a) height above ground, colour range fitted to the building; contours every 0.25 m
    near = contains_xy(
        h.fp.buffer(1.5),
        *np.meshgrid(h.bbox[0] + (np.arange(h.nx) + 0.5) * RES, h.bbox[1] + (np.arange(h.ny) + 0.5) * RES),
    )
    hv = r["hag"][near & (r["hag"] > 1.5)]
    vmax = float(np.percentile(hv, 99.5)) + 0.3 if hv.size else 8.0
    fig, ax = _axes(
        h,
        f"(a) HEIGHT above ground (m); thin contours every 0.25 m, bold every 1 m; colours clipped at {vmax:.1f} m (taller = trees)",
    )
    im = ax.imshow(
        np.clip(r["hag"], 0, None),
        origin="lower",
        extent=ext,
        cmap="turbo",
        vmin=0,
        vmax=vmax,
        interpolation="nearest",
    )
    xs = h.bbox[0] + (np.arange(h.nx) + 0.5) * RES
    ys = h.bbox[1] + (np.arange(h.ny) + 0.5) * RES
    sm_ = ndi.gaussian_filter(r["hag"], 1.5)
    ax.contour(xs, ys, sm_, levels=np.arange(1.5, vmax, 0.25), colors="k", linewidths=0.35, alpha=0.6)
    ax.contour(xs, ys, sm_, levels=np.arange(2, vmax, 1.0), colors="k", linewidths=1.0, alpha=0.8)
    cax = fig.add_axes([0.93, 0.25, 0.012, 0.5])
    fig.colorbar(im, cax=cax)
    cax.tick_params(labelsize=7)
    _decor(h, ax, "w")
    out["height"] = _save(fig, outdir / "a_height.png")
    # (b) hillshade
    d = ndi.gaussian_filter(r["dsm"], 1.0)
    gy, gx = np.gradient(d, RES)
    az, alt = math.radians(315), math.radians(45)
    sl = np.arctan(np.hypot(gx, gy))
    asp = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(sl) + np.cos(alt) * np.sin(sl) * np.cos(az - asp)
    fig, ax = _axes(h, "(b) HILLSHADE of the LiDAR surface (light from the north-west)")
    ax.imshow(hs, origin="lower", extent=ext, cmap="gray", vmin=-0.2, vmax=1, interpolation="bilinear")
    _decor(h, ax, "yellow", "c")
    out["hillshade"] = _save(fig, outdir / "b_hillshade.png")
    # (c) aspect
    fig, ax = _axes(
        h,
        "(c) ASPECT: hue = DOWNSLOPE direction (see wheel), grey = flat (<2/12), dark = wall/tree edge, pale = ground",
    )
    ax.imshow(
        aspect_rgb(r["aspect"], r["slope"], r["hag"]), origin="lower", extent=ext, interpolation="nearest"
    )
    _decor(h, ax, "k")
    wax = fig.add_axes(
        [0.905, 0.06, 0.09, 0.09 * fig.get_figwidth() / fig.get_figheight()], projection="polar"
    )
    th = np.linspace(0, 2 * np.pi, 361)
    wax.set_theta_zero_location("N")
    wax.set_theta_direction(-1)
    wax.bar(
        th,
        np.ones_like(th),
        width=2 * np.pi / 360,
        color=hsv_to_rgb(np.c_[th / (2 * np.pi), np.ones_like(th), np.ones_like(th)]),
    )
    wax.set_yticks([])
    wax.set_xticks(np.radians([0, 90, 180, 270]))
    wax.set_xticklabels(["N", "E", "S", "W"], fontsize=7)
    wax.set_title("faces / drains to", fontsize=7)
    out["aspect"] = _save(fig, outdir / "c_aspect.png")
    # (d) slope classes
    bounds = [0, 2, 3, 4, 5, 6, 8, 10, 12, 24, 1e9]
    cols = [
        "#9ecae1",
        "#ffffb2",
        "#fed976",
        "#feb24c",
        "#fd8d3c",
        "#fc4e2a",
        "#e31a1c",
        "#b10026",
        "#6a3d9a",
        "#222222",
    ]
    fig, ax = _axes(
        h, "(d) SLOPE in rise per 12. BLUE = FLAT (< 2/12); heavy blue line = the 2/12 threshold on the roof"
    )
    sm = np.where(np.nan_to_num(r["hag"]) < 1.5, np.nan, r["slope"])
    im = ax.imshow(
        sm,
        origin="lower",
        extent=ext,
        cmap=ListedColormap(cols),
        norm=BoundaryNorm(bounds, len(cols)),
        interpolation="nearest",
    )
    ax.contour(
        np.linspace(ext[0], ext[1], h.nx),
        np.linspace(ext[2], ext[3], h.ny),
        np.nan_to_num(ndi.median_filter(np.nan_to_num(sm, nan=99), 5), nan=99),
        levels=[2.0],
        colors="#08306b",
        linewidths=1.2,
    )
    cax = fig.add_axes([0.93, 0.25, 0.012, 0.5])
    cb = fig.colorbar(im, cax=cax, ticks=bounds[:-1])
    cax.tick_params(labelsize=7)
    cb.ax.set_yticklabels(["0", "2", "3", "4", "5", "6", "8", "10", "12", "24+"])
    _decor(h, ax, "k")
    out["slope"] = _save(fig, outdir / "d_slope.png")
    # (e) local-fit residual: ridges / hips / valleys / steps light up
    fig, ax = _axes(
        h,
        "(e) CREASE map: local plane-fit residual (m). Bright lines = ridges, hips, valleys, steps, roof edges",
    )
    im = ax.imshow(
        np.where(np.nan_to_num(r["hag"]) < 1.5, np.nan, r["rms"]),
        origin="lower",
        extent=ext,
        cmap="magma",
        vmin=0,
        vmax=0.25,
        interpolation="nearest",
    )
    cax = fig.add_axes([0.93, 0.25, 0.012, 0.5])
    fig.colorbar(im, cax=cax)
    cax.tick_params(labelsize=7)
    _decor(h, ax, "c", "w")
    out["crease"] = _save(fig, outdir / "e_crease.png")
    # (f) raw returns coloured by height (no interpolation: shows true edge of the roof incl. overhang)
    fig, ax = _axes(
        h, "(f) RAW LiDAR returns higher than 1.5 m above ground, coloured by height above ground (m)"
    )
    m = (h.w[:, 3] != 2) & (h.hag > 1.5)
    sc = ax.scatter(
        h.w[m, 0],
        h.w[m, 1],
        c=h.hag[m],
        s=5,
        cmap="turbo",
        vmin=1.5,
        vmax=max(6.0, float(np.percentile(h.hag[m], 99))) if m.any() else 6,
        linewidths=0,
    )
    cax = fig.add_axes([0.93, 0.25, 0.012, 0.5])
    fig.colorbar(sc, cax=cax)
    cax.tick_params(labelsize=7)
    _decor(h, ax, "k")
    out["returns"] = _save(fig, outdir / "f_returns.png")
    # profiles
    if profiles is None:
        cx, cy = h.fp.centroid.coords[0]
        bx0, by0, bx1, by1 = h.bbox
        fx0, fy0, fx1, fy1 = h.fp.bounds
        profiles = [
            ("P1 west-east through centroid", (bx0 + 2, cy), (bx1 - 2, cy)),
            ("P2 south-north through centroid", (cx, by0 + 2), (cx, by1 - 2)),
            (
                "P3 west-east, north third",
                (bx0 + 2, fy0 + 0.75 * (fy1 - fy0)),
                (bx1 - 2, fy0 + 0.75 * (fy1 - fy0)),
            ),
            (
                "P4 west-east, south third",
                (bx0 + 2, fy0 + 0.25 * (fy1 - fy0)),
                (bx1 - 2, fy0 + 0.25 * (fy1 - fy0)),
            ),
            (
                "P5 south-north, west third",
                (fx0 + 0.25 * (fx1 - fx0), by0 + 2),
                (fx0 + 0.25 * (fx1 - fx0), by1 - 2),
            ),
            (
                "P6 south-north, east third",
                (fx0 + 0.75 * (fx1 - fx0), by0 + 2),
                (fx0 + 0.75 * (fx1 - fx0), by1 - 2),
            ),
        ]
    fig, axs = plt.subplots(len(profiles), 1, figsize=(11, 2.3 * len(profiles)), dpi=100)
    for axp, (name, p0, p1) in zip(np.atleast_1d(axs), profiles):
        t, z, cls, L = h.profile(p0, p1)
        g = float(np.median(h.ground_z([p0[0], p1[0]], [p0[1], p1[1]])))
        axp.scatter(t[cls == 2], z[cls == 2] - g, s=4, c="#8c6d31")
        axp.scatter(t[cls != 2], z[cls != 2] - g, s=4, c="#1f77b4")
        axp.set_title(
            f"{name}: from ({p0[0]:.1f},{p0[1]:.1f}) to ({p1[0]:.1f},{p1[1]:.1f}); 0.8 m wide strip; brown = ground",
            fontsize=8,
        )
        axp.set_aspect("equal")
        axp.grid(True, lw=0.3)
        axp.set_xlim(0, L)
        axp.set_ylabel("height (m)", fontsize=7)
        axp.set_xticks(np.arange(0, L + 0.01, 1))
        axp.tick_params(labelsize=6)
    fig.tight_layout()
    out["profiles"] = _save(fig, outdir / "g_profiles.png")
    h.profiles_used = profiles
    return out
