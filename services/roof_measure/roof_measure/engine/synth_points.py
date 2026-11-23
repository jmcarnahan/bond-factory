"""Public synthetic roofs with simulated airborne LiDAR and exact answers (plan tier T6).

`gable(...)`, `hip(...)`, ... return a `SynthRoof` (facets, typed edges, totals: see synth_shapes);
`simulate(roof, ...)` turns one into an (N, 4) [x, y, z, class] cloud (class 2 ground, 1 the rest,
like the LA 2023 survey); `cases()` lists every shape x density plus tree/banding/rotation/offset
variants. Nothing generated is stored: build at test time. Plan dimensions are in feet (roofing
units), heights and overhangs in metres, pitch is rise per 12. A local metric frame only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely

from .synth_shapes import M2FT, SynthRoof, Wing, build

EAVE_M = 3.0  # default eave height above the ground plane
OVERHANG_M = 0.3


def _m(ft: float) -> float:
    return ft / M2FT


def _wing(rect_ft, sides, rise, eave_m, ovh_m, no_ovh="") -> Wing:
    """A wing from a plan rectangle in feet; sides named in no_ovh get no overhang (shared walls)."""
    return Wing(tuple(_m(v) for v in rect_ft), sides, rise, eave_m,
                tuple(0.0 if s in no_ovh else ovh_m for s in "WSEN"))


def _roof(name, wings, rotation_deg, **params) -> SynthRoof:
    return build(name, wings, params, rotation_deg)


def gable(length_ft=40.0, width_ft=26.0, pitch=6.0, eave_m=EAVE_M, overhang_m=OVERHANG_M, rotation_deg=0.0):
    w = [_wing((0, 0, length_ft, width_ft), "SN", pitch, eave_m, overhang_m)]
    return _roof("gable", w, rotation_deg, length_ft=length_ft, width_ft=width_ft, pitch=pitch)


def hip(length_ft=35.0, width_ft=26.0, pitch=4.0, eave_m=EAVE_M, overhang_m=OVERHANG_M, rotation_deg=0.0):
    w = [_wing((0, 0, length_ft, width_ft), "SNWE", pitch, eave_m, overhang_m)]
    return _roof("hip", w, rotation_deg, length_ft=length_ft, width_ft=width_ft, pitch=pitch)


def l_shape(length_ft=44.0, width_ft=24.0, wing_ft=34.0, pitch=6.0, corner="hip", eave_m=EAVE_M,
            overhang_m=OVERHANG_M, rotation_deg=0.0):
    """Two gable wings of equal width; corner="hip" hips the outer corner (one valley), "gable" does not (two)."""
    sides = "SNW" if corner == "hip" else "SN"
    w = [_wing((0, 0, length_ft, width_ft), sides, pitch, eave_m, overhang_m),
         _wing((0, width_ft / 2, width_ft, width_ft / 2 + wing_ft), "WE", pitch, eave_m, overhang_m, no_ovh="S")]
    return _roof("l_shape", w, rotation_deg, corner=corner, pitch=pitch)


def t_shape(length_ft=48.0, width_ft=26.0, stem_w_ft=18.0, stem_ft=20.0, pitch=6.0, eave_m=EAVE_M,
            overhang_m=OVERHANG_M, rotation_deg=0.0):
    x0 = (length_ft - stem_w_ft) / 2
    w = [_wing((0, 0, length_ft, width_ft), "SN", pitch, eave_m, overhang_m),
         _wing((x0, -stem_ft, x0 + stem_w_ft, width_ft / 2), "WE", pitch, eave_m, overhang_m)]
    return _roof("t_shape", w, rotation_deg, pitch=pitch)


def cross_gable(length_ft=48.0, width_ft=26.0, cross_w_ft=18.0, cross_ft=14.0, pitch=6.0, eave_m=EAVE_M,
                overhang_m=OVERHANG_M, rotation_deg=0.0):
    x0 = (length_ft - cross_w_ft) / 2
    w = [_wing((0, 0, length_ft, width_ft), "SN", pitch, eave_m, overhang_m),
         _wing((x0, -cross_ft, x0 + cross_w_ft, width_ft + cross_ft), "WE", pitch, eave_m, overhang_m)]
    return _roof("cross_gable", w, rotation_deg, pitch=pitch)


def dutch_gable(length_ft=40.0, width_ft=26.0, gable_inset_ft=6.0, pitch=6.0, eave_m=EAVE_M,
                overhang_m=OVERHANG_M, rotation_deg=0.0):
    """A hip roof whose ridge is extended past the hips by a small gable (vertical end walls)."""
    w = [_wing((0, 0, length_ft, width_ft), "SNWE", pitch, eave_m, overhang_m),
         _wing((gable_inset_ft, 0, length_ft - gable_inset_ft, width_ft), "SN", pitch, eave_m, overhang_m)]
    return _roof("dutch_gable", w, rotation_deg, pitch=pitch)


def shed(length_ft=30.0, width_ft=20.0, pitch=3.0, eave_m=EAVE_M, overhang_m=OVERHANG_M, rotation_deg=0.0):
    w = [_wing((0, 0, length_ft, width_ft), "S", pitch, eave_m, overhang_m)]
    return _roof("shed", w, rotation_deg, pitch=pitch)


def flat(length_ft=40.0, width_ft=30.0, eave_m=EAVE_M, overhang_m=OVERHANG_M, rotation_deg=0.0):
    w = [_wing((0, 0, length_ft, width_ft), "", 0.0, eave_m, overhang_m)]
    return _roof("flat", w, rotation_deg)


def flat_pitched(length_ft=40.0, width_ft=24.0, flat_ft=16.0, pitch=6.0, level_change_m=0.0, eave_m=EAVE_M,
                 overhang_m=OVERHANG_M, rotation_deg=0.0):
    """A gable with a flat section along one eave: same eave height (a transition) or stepped (level_change)."""
    w = [_wing((0, 0, length_ft, width_ft), "SN", pitch, eave_m, overhang_m),
         _wing((0, -flat_ft, length_ft, 0), "", 0.0, eave_m + level_change_m, overhang_m, no_ovh="N")]
    name = "flat_pitched_step" if level_change_m else "flat_pitched"
    return _roof(name, w, rotation_deg, level_change_m=level_change_m, pitch=pitch)


def two_level(length_ft=26.0, width_ft=24.0, step_m=1.2, pitch=6.0, eave_m=EAVE_M, overhang_m=OVERHANG_M,
              rotation_deg=0.0):
    """Two gables end to end, the second eave step_m higher (a vertical wall between them)."""
    w = [_wing((0, 0, length_ft, width_ft), "SN", pitch, eave_m, overhang_m, no_ovh="E"),
         _wing((length_ft, 0, 2 * length_ft - 4, width_ft), "SN", pitch, eave_m + step_m, overhang_m, no_ovh="W")]
    return _roof("two_level", w, rotation_deg, step_m=step_m, pitch=pitch)


def complex_hip(pitch=6.0, eave_m=EAVE_M, overhang_m=OVERHANG_M, rotation_deg=0.0):
    """Main hip + two hip wings + bays + small hip porches: many small real facets."""
    o, e = overhang_m, eave_m
    w = [_wing((0, 0, 44, 30), "SNWE", pitch, e, o),
         _wing((10, -12, 28, 15), "SWE", pitch, e, o),  # south wing
         _wing((24, 15, 38, 42), "NWE", pitch, e, o),  # north wing
         _wing((-6, 9, 8, 21), "WSN", pitch, e, o),  # west bay
         _wing((36, 8, 50, 22), "ESN", pitch, e, o),  # east bay
         _wing((13, -18, 25, -5), "SWE", pitch, e, o),  # porch on the south wing
         _wing((26, 36, 36, 48), "NWE", pitch, e, o)]  # small end on the north wing
    return _roof("complex_hip", w, rotation_deg, pitch=pitch)


SHAPES = {"gable": gable, "hip": hip, "l_shape": l_shape, "t_shape": t_shape, "cross_gable": cross_gable,
          "dutch_gable": dutch_gable, "shed": shed, "flat": flat, "flat_pitched": flat_pitched,
          "flat_pitched_step": lambda **k: flat_pitched(level_change_m=0.6, **k), "two_level": two_level,
          "complex_hip": complex_hip}
DENSITIES = (16, 8, 4, 2)


@dataclass(frozen=True)
class SynthCase:
    name: str
    roof: SynthRoof
    kwargs: dict = field(default_factory=dict)  # for simulate()

    def points(self) -> np.ndarray:
        return simulate(self.roof, **self.kwargs)


def cases() -> list[SynthCase]:
    """Every shape at 16, 8, 4 and 2 pts/m2, plus tree, banding, rotation and outline-offset variants."""
    out = [SynthCase(f"{n}_d{d}", f(), {"density": d, "seed": 1}) for n, f in SHAPES.items() for d in DENSITIES]
    for n in ("gable", "hip", "l_shape"):
        out.append(SynthCase(f"{n}_d8_trees", SHAPES[n](), {"density": 8, "seed": 2, "trees": 2}))
        out.append(SynthCase(f"{n}_d8_banded", SHAPES[n](), {"density": 8, "seed": 3, "banding": True}))
        out.append(SynthCase(f"{n}_d8_offset", SHAPES[n](), {"density": 8, "seed": 4, "outline_offset_m": (0.8, -0.5)}))
    for n in ("gable", "hip", "l_shape", "dutch_gable", "t_shape"):
        for rot in (17.0, 45.0):
            out.append(SynthCase(f"{n}_d8_rot{int(rot)}", SHAPES[n](rotation_deg=rot), {"density": 8, "seed": 5}))
    return out


def _jitter_grid(rng, bounds, density):
    """Jittered-grid sample positions over a bounding box: even like a lidar swath, ~density per m2."""
    s = 1.0 / math.sqrt(density)
    x0, y0 = math.floor(bounds[0] / s) * s, math.floor(bounds[1] / s) * s
    gx, gy = np.meshgrid(np.arange(x0, bounds[2] + s, s), np.arange(y0, bounds[3] + s, s))
    return (gx.ravel() + rng.uniform(0, s, gx.size), gy.ravel() + rng.uniform(0, s, gx.size))


def _keep_bands(rng, x, y, density):
    """Scan-line banding: 4 m strips alternately dense (all kept) and sparse (a quarter kept)."""
    phase = rng.uniform(0, 8.0)
    dense = (np.floor((x + phase) / 4.0).astype(int) % 2) == 0
    return dense | (rng.uniform(size=x.size) < 0.25)


def simulate(roof: SynthRoof, *, density: float = 8, noise_sigma_m: float = 0.03, seed: int = 0,
             banding: bool = False, trees: int = 0, outline_offset_m: tuple = (0.0, 0.0),
             ground: bool = True) -> np.ndarray:
    """Airborne LiDAR over `roof`: an (N, 4) float array [x, y, z, class], class 2 ground else 1.

    density is returns per m2 of plan area (the survey's way of counting). Roof returns follow the
    facet planes (overhang included) plus vertical noise; ground returns lie on z=0 around the
    building, none under the roof; trees are non-planar domes at the eaves (class 1) that hide part
    of the roof; banding thins alternate strips. outline_offset_m imitates a displaced county
    outline: the points are shifted by -offset, so the unchanged wall outline appears displaced by
    +offset (exact answers for the shifted points: `roof.translated(-dx, -dy)`). One seeded
    numpy Generator only: the same arguments give identical bytes.
    """
    rng = np.random.default_rng(seed)
    boost = 1.6 if banding else 1.0
    outline = roof.roof_polygon()
    minx, miny, maxx, maxy = outline.bounds
    pad = 8.0 if ground else 0.0
    gx, gy = _jitter_grid(rng, (minx - pad, miny - pad, maxx + pad, maxy + pad), density * boost)
    if banding:
        keep = _keep_bands(rng, gx, gy, density)
        gx, gy = gx[keep], gy[keep]
    on_roof = shapely.contains_xy(outline, gx, gy)
    z = np.zeros(gx.size)
    for facet in roof.facets:
        inside = shapely.contains_xy(facet.polygon(), gx, gy)
        z[inside] = facet.plane[0] * gx[inside] + facet.plane[1] * gy[inside] + facet.plane[2]
    cls = np.where(on_roof, 1.0, 2.0)
    z = z + rng.normal(0.0, noise_sigma_m, gx.size)
    sel = on_roof | (ground & ~on_roof)
    pts = np.column_stack([gx, gy, z, cls])[sel]
    if trees:
        pts = _add_trees(rng, roof, pts, density, trees)
    pts[:, 0] -= outline_offset_m[0]
    pts[:, 1] -= outline_offset_m[1]
    return pts[rng.permutation(len(pts))]


def _add_trees(rng, roof, pts, density, n_trees):
    """Domed canopies touching or overhanging an eave; roof returns under them are mostly lost."""
    ring, cen = roof.roof_polygon().exterior, roof.roof_polygon().centroid
    for _ in range(n_trees):
        r = rng.uniform(1.6, 2.6)
        base = ring.interpolate(rng.uniform(0, 1), normalized=True)
        c = np.array([base.x, base.y])
        out = c - np.array([cen.x, cen.y])
        c = c + 0.3 * r * out / max(np.linalg.norm(out), 1e-9)
        d = np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1])
        lost = (d < r) & (pts[:, 3] == 1.0) & (rng.uniform(size=len(pts)) < 0.7)
        pts = pts[~lost]
        m = round(density * math.pi * r * r * 1.3)
        rho = r * np.sqrt(rng.uniform(size=m))
        ang = rng.uniform(0, 2 * math.pi, m)
        zc = EAVE_M + 1.0 + 1.5 * np.sqrt(np.clip(1 - (rho / r) ** 2, 0, 1)) * rng.uniform(-0.4, 1.0, m)
        tree = np.column_stack([c[0] + rho * np.cos(ang), c[1] + rho * np.sin(ang), zc, np.ones(m)])
        pts = np.vstack([pts, tree])
    return pts
