"""One renderer for every candidate and the shared reference panels of a blind sheet.

Panels: reference points by height; an aspect map from a 0.25 m surface model of points_wide (hue = downslope direction);
an optional orthophoto.png from the house dir; then up to three candidates drawn identically (facet hue = downslope
direction and saturation = pitch, flat facets grey and hatched, typed edges, outline). No method names anywhere.
"""

from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import hsv_to_rgb
from matplotlib.patches import Polygon as MPoly
from scipy import ndimage

from .data import ground_function
from .geom import FLAT_RISE, load_roof, rings_of

EDGE_STYLE = {"ridge": ("#d62728", "-"), "hip": ("#ff7f0e", "-"), "valley": ("#1f77b4", "-"), "eave": ("#111111", "-"),
              "rake": ("#2ca02c", "-"), "step_flashing": ("#e377c2", "--"), "wall_flashing": ("#e377c2", "--"),
              "level_change": ("#8c564b", "--"), "flat_edge": ("#7f7f7f", "-"), "transition": ("#9467bd", "--"),
              "parapet": ("#7f7f7f", "-")}
CELL_M = 0.25
MAX_CELLS = 1600


def aspect_map(w: np.ndarray, bounds: tuple[float, float, float, float]) -> np.ndarray:
    """RGB aspect map of the surface model: hue = downslope bearing, saturation = slope, dark = ground or low."""
    x0, y0, x1, y1 = bounds
    nx, ny = min(int((x1 - x0) / CELL_M) + 1, MAX_CELLS), min(int((y1 - y0) / CELL_M) + 1, MAX_CELLS)
    cx, cy = (x1 - x0) / nx, (y1 - y0) / ny
    m = (w[:, 0] >= x0) & (w[:, 0] < x1) & (w[:, 1] >= y0) & (w[:, 1] < y1) & (w[:, 3] != 7)
    p = w[m]
    z = np.full((ny, nx), np.nan)
    order = np.argsort(p[:, 2])
    z[((p[order, 1] - y0) / cy).astype(int), ((p[order, 0] - x0) / cx).astype(int)] = p[order, 2]  # highest return wins
    valid = ~np.isnan(z)
    if valid.sum() < 10:
        return np.full((ny, nx, 3), 0.12)
    d, (ii, jj) = ndimage.distance_transform_edt(~valid, return_indices=True)
    zf = z[ii, jj]
    zf[d * cx > 0.75] = np.nan
    zs = ndimage.uniform_filter(np.where(np.isnan(zf), np.nanmedian(zf), zf), 3)
    dzdy, dzdx = np.gradient(zs, cy, cx)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    asp = (np.degrees(np.arctan2(-dzdx, -dzdy)) + 360) % 360
    rgb = hsv_to_rgb(np.stack([asp / 360, np.clip(slope / 14.0, 0, 1) ** 0.8, np.full_like(asp, 0.95)], -1))
    gx, gy = np.meshgrid(x0 + (np.arange(nx) + 0.5) * cx, y0 + (np.arange(ny) + 0.5) * cy)
    gz = ground_function(w)(np.c_[gx.ravel(), gy.ravel()]).reshape(ny, nx)
    rgb[np.isnan(zf) | (zf - gz < 1.5)] = (0.12, 0.12, 0.12)
    return rgb


def facet_style(plane) -> tuple[Any, bool]:
    a, b = plane[0], plane[1]
    pitch = 12 * float(np.hypot(a, b))
    if pitch < FLAT_RISE:
        return (0.78, 0.8, 0.84), True
    asp = (np.degrees(np.arctan2(-a, -b)) + 360) % 360
    return hsv_to_rgb((asp / 360, min(1.0, np.degrees(np.arctan(np.hypot(a, b))) / 14.0) ** 0.8, 0.95)), False


def draw_candidate(ax, res: dict[str, Any] | None, bounds, title: str) -> None:
    if res is None or not res.get("facets"):
        ax.text(0.5, 0.5, "no drawing", transform=ax.transAxes, ha="center", va="center", fontsize=12, color="#888888")  # neutral
    else:
        roof = load_roof(res)
        for f in roof.facets:
            col, flat = facet_style(f.plane)
            ax.add_patch(MPoly(np.array(f.poly.exterior.coords), closed=True, facecolor=col, edgecolor="none", alpha=0.75,
                               hatch="////" if flat else None, zorder=1))
        for e in roof.edges:
            col, ls = EDGE_STYLE.get(e.type, ("#000000", ":"))
            ax.plot([e.p0[0], e.p1[0]], [e.p0[1], e.p1[1]], color=col, ls=ls, lw=1.8, zorder=3, solid_capstyle="butt")
        for ring in rings_of(res.get("roof_outline")):
            a = np.array(ring)
            ax.plot(np.r_[a[:, 0], a[0, 0]], np.r_[a[:, 1], a[0, 1]], color="k", lw=0.9, zorder=5)
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=12, pad=3)
    ax.tick_params(labelsize=6)


def square_bounds(foot, pad: float = 3.0) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = foot.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    hw = max(maxx - minx, maxy - miny) / 2 + pad
    return cx - hw, cy - hw, cx + hw, cy + hw


def render_sheet(out_png, label: str, ref: np.ndarray, wide: np.ndarray, foot, ortho_png,
                 cands: list[tuple[str, dict[str, Any] | None]], dpi: int = 75) -> None:
    """Write the blind sheet: top row reference points, aspect map, orthophoto (or the legend when absent); bottom row
    the candidates under their blind letters."""
    bounds = square_bounds(foot)
    fig, axs = plt.subplots(2, 3, figsize=(15, 10.2), dpi=dpi)
    ax = axs[0, 0]
    ax.scatter(ref[:, 0], ref[:, 1], c=ref[:, 2], s=3, cmap="viridis", zorder=2)
    ax.plot(*foot.exterior.xy, color="k", lw=0.8)
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal")
    ax.set_title(f"{label}: roof points by height", fontsize=10, pad=3)
    ax.tick_params(labelsize=6)
    axs[0, 1].imshow(aspect_map(wide, bounds), origin="lower", extent=(bounds[0], bounds[2], bounds[1], bounds[3]),
                     interpolation="nearest")
    axs[0, 1].plot(*foot.exterior.xy, color="w", lw=0.8)
    axs[0, 1].set_title("surface model, hue = downslope direction (grey = flat, black = ground)", fontsize=9, pad=3)
    axs[0, 1].tick_params(labelsize=6)
    ax = axs[0, 2]
    if ortho_png is not None and ortho_png.is_file():
        ax.imshow(plt.imread(str(ortho_png)))
        ax.set_title("orthophoto", fontsize=10, pad=3)
        ax.axis("off")
    else:
        ax.axis("off")
        y = 0.9
        for k, (col, ls) in EDGE_STYLE.items():
            if k in ("parapet", "wall_flashing"):
                continue
            ax.plot([0, 0.14], [y, y], color=col, ls=ls, lw=2.2, transform=ax.transAxes)
            ax.text(0.17, y, k, va="center", fontsize=9, transform=ax.transAxes)
            y -= 0.07
        ax.text(0, y - 0.01, "grey hatched = flat (< 2/12); facet hue = downslope direction", va="top", fontsize=8,
                transform=ax.transAxes)
    for i in range(3):
        if i < len(cands):
            draw_candidate(axs[1, i], cands[i][1], bounds, cands[i][0])
        else:
            axs[1, i].axis("off")
    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi)
    plt.close(fig)
