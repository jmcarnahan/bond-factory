"""Clutter absorption on the label raster: merge flat labels that are one membrane, absorb steep outline strips,
parapets, junk patches and small raised clutter into their neighbour. Metres, building frame."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage as ndi

from .errors import Ctx
from .plane_math import fit_plane, pitch_rise, pres, zat

_LEGACY_OUTSIDE_SHARE = 0.4  # patch outside share when step 2 is switched off


class _Absorber:
    """Mutable working state of one absorption run (the label raster ``lab`` and planes change in place)."""

    def __init__(self, lab: np.ndarray, origin: tuple[float, float, float], planes: list, q: np.ndarray,
                 qlab: np.ndarray, ctx: Ctx) -> None:
        self.lab, self.planes, self.q, self.qlab, self.ctx, self.p = lab, planes, q, qlab, ctx, ctx.p
        minx, miny, self.h = origin
        ny, nx = lab.shape
        xs = minx + (np.arange(nx) + 0.5) * self.h
        ys = miny + (np.arange(ny) + 0.5) * self.h
        self.x, self.y = np.meshgrid(xs, ys)
        self.counts = {"clutter": 0, "flat_merges": 0, "junk": 0, "strips": 0}
        self.parapet_m = 0.0

    def rise(self, label: int) -> float:
        return pitch_rise(self.planes[label])

    def is_flat(self, label: int) -> bool:
        return self.rise(label) < self.p.flat_cut_rise

    def rms_of(self, label: int) -> float:
        m = self.qlab == label
        return float(pres(self.planes[label], self.q[m]).std()) if m.sum() > 3 else 0.1

    def _boundary_gap(self, a: int, b: int) -> float | None:
        """Mean height gap between planes a and b over their shared 4-neighbour boundary (None: not adjacent)."""
        lab, x, y = self.lab, self.x, self.y
        gaps = []
        for sl_a, sl_b in (((slice(None), slice(0, -1)), (slice(None), slice(1, None))),
                           ((slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
            for u, v in ((a, b), (b, a)):
                sel = (lab[sl_a] == u) & (lab[sl_b] == v)
                if sel.any():
                    xm = (x[sl_a][sel] + x[sl_b][sel]) / 2
                    ym = (y[sl_a][sel] + y[sl_b][sel]) / 2
                    gaps.append(np.abs(zat(self.planes[a], xm, ym) - zat(self.planes[b], xm, ym)))
        return float(np.concatenate(gaps).mean()) if gaps else None

    def _try_merge(self, a: int, b: int) -> bool:
        p, planes, q, qlab = self.p, self.planes, self.q, self.qlab
        gap = self._boundary_gap(a, b)
        if gap is None:
            return False
        both_flat = self.is_flat(a) and self.is_flat(b)
        gdiff = math.hypot(planes[a][0] - planes[b][0], planes[a][1] - planes[b][1])
        sel = (qlab == a) | (qlab == b)
        plm = fit_plane(q[sel]) if sel.sum() >= p.absorb_fit_min_pts else planes[a]
        enough = sel.sum() >= p.absorb_min_pts
        tight = enough and pres(plm, q[sel]).std() < p.absorb_one_plane_rms_m
        one_plane = both_flat and tight and pitch_rise(plm) < p.flat_cut_rise
        one_plane_p = (not both_flat) and gdiff < p.absorb_gdiff and tight and pitch_rise(plm) >= p.flat_cut_rise
        if both_flat:
            ok = gap < p.absorb_flat_gap_m or one_plane
        else:
            ok = (gdiff < p.absorb_gdiff and gap < p.absorb_pitched_gap_m) or one_plane_p
        if ok and (pitch_rise(plm) < p.flat_cut_rise) == both_flat and pres(plm, q[sel]).std() < p.absorb_merge_rms_m:
            planes[a] = plm
            self.lab[self.lab == b] = a
            qlab[qlab == b] = a
            self.counts["flat_merges"] += 1
            return True
        return False

    def merge_labels(self) -> bool:
        """Step 1: adjacent labels that are one membrane (flat) or one plane (pitched) become one label."""
        changed = False
        flat = [lbl for lbl in np.unique(self.lab) if lbl >= 0]
        for i, a in enumerate(flat):
            for b in flat[i + 1:]:
                if not (self.lab == a).any() or not (self.lab == b).any():
                    continue
                changed |= self._try_merge(a, b)
        return changed

    def _inscribed(self, comp: np.ndarray) -> float:
        return float(ndi.distance_transform_edt(np.pad(comp, 1)).max() * self.h)

    def _set(self, comp: np.ndarray, target: int, key: str | None) -> bool:
        self.lab[comp] = target
        if key:
            self.counts[key] += 1
        return True

    def _has_own_eave(self, comp: np.ndarray, label: int) -> bool | None:
        """Evidence that a narrow outline region is a roof facet and not a wall or fascia artefact: its outer edge is level
        (the plane's height changes by less than ``s2_eave_slope`` per metre along the edge: an eave, not a rake or a
        hanging strip) and its returns are as dense as the roof's (``s2_strip_density``). None: too little outline to judge."""
        p = self.p
        outer = comp & ndi.binary_dilation(self.lab < 0, structure=np.ones((3, 3), bool))
        if outer.sum() < p.s2_eave_min_cells:
            return None
        xy = np.c_[self.x[outer], self.y[outer]]
        c = xy - xy.mean(0)
        _, sv, vt = np.linalg.svd(c, full_matrices=False)
        t = c @ vt[0]
        if sv[0] < 1e-6 or np.ptp(t) < p.s2_eave_min_len_m:
            return None
        z = zat(self.planes[label], xy[:, 0], xy[:, 1])
        slope = abs(float(np.polyfit(t, z, 1)[0]))
        area = float(comp.sum() * self.h * self.h)
        dens = float((self.qlab == label).sum()) / max(area, 1e-6)
        roof = float((self.qlab >= 0).sum()) / max(float((self.lab >= 0).sum() * self.h * self.h), 1e-6)
        return slope < p.s2_eave_slope and dens >= p.s2_strip_density * roof

    def _steep_strip(self, comp, label, ins, outside) -> bool:
        p = self.p
        if self._inscribed(comp) < p.s2_strip_width / 2 and outside > p.s2_strip_outside_share:
            own = self._has_own_eave(comp, label)
            if own and self.rise(label) <= p.s2_strip_cap_rise:
                return False
            vals, cnt = np.unique(ins, return_counts=True)
            nb = int(vals[cnt.argmax()])
            if nb != label:
                return self._set(comp, nb, "strips")
        return False

    def _big_pitched_patch(self, comp, label, ins, outside) -> bool:
        p = self.p
        vals, cnt = np.unique(ins, return_counts=True)
        flats = [x for x in vals if self.is_flat(x)]
        if flats and sum(cnt[list(vals).index(x)] for x in flats) / len(ins) >= p.flat_patch_share \
                and outside <= p.flat_patch_outside_share:
            real = self.rms_of(label) < p.s2_patch_rms and self.rise(label) >= p.s2_patch_pitch
            if not real:
                return self._set(comp, int(max(flats, key=lambda x: cnt[list(vals).index(x)])), "junk")
        return False

    def _parapet(self, comp, label, lr, outside) -> bool:
        p = self.p
        rad = self._inscribed(comp)
        ins = lr[lr >= 0]
        if len(ins) >= p.absorb_min_ring_cells and rad < p.parapet_radius_m:
            vals, cnt = np.unique(ins, return_counts=True)
            nb = int(vals[cnt.argmax()])
            if nb != label and cnt.max() / len(ins) >= p.parapet_neighbour_share and self.is_flat(nb):
                cx, cy = self.x[comp].mean(), self.y[comp].mean()
                above = zat(self.planes[label], cx, cy) - zat(self.planes[nb], cx, cy)
                if above > p.parapet_height_m or self.is_flat(label):
                    self.parapet_m += comp.sum() * self.h * self.h / max(2 * rad, 0.3)
                    self.lab[comp] = nb
                    return True
        return False

    def _inner_patch(self, comp, label, ins, outside, area) -> bool:
        """A pitched patch inside a flat roof (junk unless big and clean), or small raised clutter on a flat one."""
        p = self.p
        vals, cnt = np.unique(ins, return_counts=True)
        nb = int(vals[cnt.argmax()])
        frac = cnt.max() / len(ins)
        flat_labels = [x for x in np.unique(self.lab) if x >= 0 and self.is_flat(x)]
        flat_frac = float(np.isin(ins, flat_labels).mean())
        limit = p.flat_patch_outside_share if p.s2_flat else _LEGACY_OUTSIDE_SHARE
        if self.rise(label) >= p.flat_cut_rise and flat_frac >= p.flat_patch_share and outside <= limit:
            real = area >= p.s2_patch_area and self.rms_of(label) < p.s2_patch_rms and self.rise(label) >= p.s2_patch_pitch
            if not real:
                flats = [x for x in vals if self.is_flat(x)]
                if flats:
                    return self._set(comp, int(max(flats, key=lambda x: cnt[list(vals).index(x)])), "junk")
        if nb == label or frac < p.clutter_neighbour_share or outside > p.clutter_outside_share or not self.is_flat(nb):
            return False
        cx, cy = self.x[comp].mean(), self.y[comp].mean()
        above = zat(self.planes[label], cx, cy) - zat(self.planes[nb], cx, cy)
        if area < p.clutter_small_area_m2 and above > p.clutter_above_m:
            return self._set(comp, nb, "clutter")
        if self.rise(label) >= p.flat_cut_rise and self.rms_of(label) >= self.rms_of(nb) * 0.999:
            return self._set(comp, nb, "junk")
        return False

    def _component(self, label: int, comp: np.ndarray) -> bool:
        p = self.p
        area = comp.sum() * self.h * self.h
        pitched = self.rise(label) >= p.flat_cut_rise
        if area > p.clutter_area_m2 and not (p.s2_flat and pitched):
            return False
        ring = ndi.binary_dilation(comp, structure=np.ones((3, 3), bool), iterations=2) & ~comp
        lr = self.lab[ring]
        ins = lr[lr >= 0]
        if len(ins) < p.absorb_min_ring_cells:
            return False
        outside = float((lr < 0).mean())
        if p.s2_flat and self.rise(label) > p.s2_steep_rise and self._steep_strip(comp, label, ins, outside):
            return True
        if p.s2_flat and pitched and area > p.clutter_area_m2:
            return self._big_pitched_patch(comp, label, ins, outside)
        if outside > p.parapet_outside_share and self._parapet(comp, label, lr, outside):
            return True
        return self._inner_patch(comp, label, ins, outside, area)

    def absorb_components(self) -> bool:
        """Step 2: strips, parapets, junk and clutter, component by component."""
        changed = False
        for label in [x for x in np.unique(self.lab) if x >= 0]:
            comps, n = ndi.label(self.lab == label)
            for c in range(1, n + 1):
                changed |= self._component(label, comps == c)
        return changed


def absorb_labels(lab: np.ndarray, origin: tuple[float, float, float], planes: list, q: np.ndarray,
                  qlab: np.ndarray, diag: dict[str, Any], ctx: Ctx) -> np.ndarray:
    """Clean the label raster ``lab`` (in place; planes and ``qlab`` may change too). Counters go into ``diag``."""
    st = _Absorber(lab, origin, planes, q, qlab, ctx)
    for _ in range(ctx.p.absorb_iters):
        ctx.check()
        changed = st.merge_labels()
        changed |= st.absorb_components()
        if not changed:
            break
    diag["parapet_ft"] = round(st.parapet_m / 0.3048, 1)
    diag["clutter"] = st.counts["clutter"]
    diag["flat_merges"] = st.counts["flat_merges"]
    diag["junk_patches_absorbed"] = st.counts["junk"]
    diag["steep_strips_absorbed"] = st.counts["strips"]
    return lab
