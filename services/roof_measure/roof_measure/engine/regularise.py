"""Plane regularisation: flatten near-flat planes, snap aspects to the wall axes, equalise pitches, refit offsets."""

from __future__ import annotations

import math

import numpy as np

from .errors import Ctx
from .params import EngineParams
from .plane_math import aspect_deg, compact, pitch_rise, pres


def _flatten(planes: list, p: EngineParams) -> None:
    for pl in planes:
        if pitch_rise(pl) < p.reg_flat_rise:
            pl[0] = pl[1] = 0.0


def _snap_aspects(planes: list, thetas: list[float], p: EngineParams) -> None:
    """Snap each plane's downslope direction to the nearest wall axis when within ``s3_snap_az`` degrees."""
    for pl in planes:
        g = math.hypot(pl[0], pl[1])
        if g < p.reg_grad_min:
            continue
        az = aspect_deg(pl)
        rels = [((az - ((90.0 - t) % 90.0) + 45.0) % 90.0) - 45.0 for t in thetas]
        rel = min(rels, key=abs)
        if abs(rel) <= p.s3_snap_az:
            r = math.radians(az - rel)
            pl[0] = -g * math.sin(r)
            pl[1] = -g * math.cos(r)


def _equalise_pitches(planes: list, npts: np.ndarray, p: EngineParams) -> None:
    """Planes of one connected group (similar gradient, or opposing gable halves) share an area-weighted pitch."""
    k = len(planes)
    g = np.array([math.hypot(q[0], q[1]) for q in planes])
    thr = p.reg_pitch_tol / 12.0
    pitched = [i for i in range(k) if 12 * g[i] >= p.reg_pitched_rise]
    seen: set[int] = set()
    for i in pitched:
        if i in seen:
            continue
        grp = [i]
        seen.add(i)
        stack = [i]
        while stack:
            a = stack.pop()
            for b in pitched:
                if b in seen:
                    continue
                dg = abs(g[a] - g[b])
                opposing = abs(((aspect_deg(planes[a]) - aspect_deg(planes[b])) + 180) % 360 - 180) > p.reg_opposing_deg
                if dg <= thr or (opposing and dg <= p.reg_opposing_tol / 12):
                    seen.add(b)
                    grp.append(b)
                    stack.append(b)
        if len(grp) > 1:
            gm = np.average(g[grp], weights=npts[grp] + 1)
            for b in grp:
                if g[b] > 0:
                    if 12 * g[b] >= p.flat_cut_rise:
                        tgt = max(gm, p.flat_cut_rise / 12 + 1e-4)  # never push a >= 2/12 plane under the cut
                    else:
                        tgt = min(gm, p.reg_below_cut_rise / 12)
                    s = tgt / g[b]
                    planes[b][0] *= s
                    planes[b][1] *= s


def regularise(pts: np.ndarray, lab: np.ndarray, planes: list, theta: float | list[float],
               p: EngineParams) -> list:
    """Return regularised copies of ``planes``; ``theta`` is the wall axis angle(s) in degrees from +x, CCW."""
    planes = [q.copy() for q in planes]
    npts = np.array([(lab == i).sum() for i in range(len(planes))], float)
    thetas = list(theta) if isinstance(theta, (list, tuple)) else [theta]
    _flatten(planes, p)
    _snap_aspects(planes, thetas, p)
    _equalise_pitches(planes, npts, p)
    for i, pl in enumerate(planes):
        m = lab == i
        if m.sum() >= 3:
            r = pts[m, 2] - pl[0] * pts[m, 0] - pl[1] * pts[m, 1]
            pl[2] = np.median(r)
    return planes


def merge_identical(pts: np.ndarray, lab: np.ndarray, planes: list, p: EngineParams,
                    ctx: Ctx) -> tuple[np.ndarray, list]:
    """Planes that became identical after regularisation are one plane (even when apart: two facets, one plane)."""
    changed = True
    while changed:
        ctx.check()
        changed = False
        for i in range(len(planes)):
            for j in range(i + 1, len(planes)):
                if (lab == i).sum() == 0 or (lab == j).sum() == 0:
                    continue
                if np.linalg.norm(planes[i][:2] - planes[j][:2]) > p.identical_gdiff:
                    continue
                if np.abs(pres(planes[i], pts[lab == j])).mean() > p.identical_mean_m:
                    continue
                lab[lab == j] = i
                changed = True
    return compact(lab, planes)
