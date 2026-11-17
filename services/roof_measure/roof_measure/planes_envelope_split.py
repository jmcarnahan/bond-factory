"""A big roof section split into sub-sections at its valleys (internal, for ``planes_envelope``).

On a big section (a main gable, a cross gable and a wing with hips, a dozen planes) every pair of planes brings a
roof line and the lines of planes far apart cut through planes that have nothing to do with them. A roof is built
of parts that meet in valleys: neighbours whose shared border is a ridge, a hip or a seam (both slope away from it,
or one face) belong to one part; a valley joins two parts. ``subsections`` finds the parts, ``sub_regions`` gives
each its region (each part is a lower envelope, the roof is the higher part where two meet: valleys), and the
caller partitions each part on its own.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .classify import polygons_of
from .planes_envelope_cells import (
    COVERED_SHARE,
    NEAR_FT,
    _kind,
    cut,
    label_arrangement,
    label_envelope,
    measured_gap,
    tidy_labels,
)
from .planes_envelope_geom import Eq, anchor_between, long_line, meet_line, straight_runs, z_at
from .planes_envelope_lines import box_sides, section_chords
from .planes_envelope_measure import _offset, _shifted, touch_points

JOIN_KINDS = ("ridge", "hip", "seam")  # neighbours meeting in one of these are one part of the roof
SMALL_SQFT = 80.0  # a plane with a smaller cluster joins its longest-bordering neighbour's part
MIN_TOUCH_PTS = 8
MAX_SHIFT_FT = 3.0
MIN_GRAD_DIFF = 0.05
MIN_KEEP_SHARE = 0.4  # a plane left with less than this share of its raw area means the envelope failed there
MAX_DISAGREE = 0.25  # ... as does raw coverage disagreeing with the lowest plane on more than this share


def _runs(line: BaseGeometry) -> list[LineString]:
    out: list[LineString] = []
    for part in getattr(line, "geoms", [line]):
        if part.geom_type == "LineString":
            out += straight_runs(part)
    return out


def subsections(members: list[int], shared: dict[tuple[int, int], BaseGeometry], eqs: list[Eq],
                raws: list[BaseGeometry], shapes: list[BaseGeometry]) -> list[list[int]]:
    """The parts of a section: connected components of neighbours whose (gap-filled) border is mostly a ridge, a
    hip or a seam by the planes' own equations; a plane with less than ``SMALL_SQFT`` of cluster joins the part of
    the neighbour it shares the longest border with (it has too little roof to say)."""
    parent = {k: k for k in members}

    def small(k: int) -> bool:
        return 0.0 < raws[k].area < SMALL_SQFT

    def find(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for (i, j), line in shared.items():
        if i not in parent or j not in parent:
            continue
        ri = raws[i] if not raws[i].is_empty else shapes[i]
        rj = raws[j] if not raws[j].is_empty else shapes[j]
        m = measured_gap(ri, rj, eqs[i], eqs[j])
        length: dict[str, float] = {}
        for run in _runs(line):
            if run.length >= 0.5:
                k, _ = _kind(run, i, j, shapes, eqs, True, m)
                length[k] = length.get(k, 0.0) + run.length
        if length and max(length, key=lambda k: length[k]) in JOIN_KINDS and not (small(i) or small(j)):
            parent[find(i)] = find(j)
    for k in members:  # a small plane (a cricket, a cheek) joins the part it shares the longest border with
        if small(k):
            nbs = [(line.length, j) for (a, b), line in shared.items() for i, j in ((a, b), (b, a))
                   if i == k and j in parent and not small(j)]
            if nbs:
                parent[find(k)] = find(max(nbs)[1])
    groups: dict[int, list[int]] = {}
    for k in members:
        groups.setdefault(find(k), []).append(k)
    return sorted(groups.values(), key=lambda g: g[0])


def sub_regions(reg: BaseGeometry, groups: list[list[int]], shared: dict[tuple[int, int], BaseGeometry],
                eqs: list[Eq], raws: list[BaseGeometry], shapes: list[BaseGeometry],
                dirs: list[float]) -> list[BaseGeometry]:
    """Each part's region inside the section region ``reg``. Each part is the lower envelope of its planes and two
    parts meet in valleys, so the roof is the HIGHER of the parts there: ``reg`` is cut along the valley lines
    between parts and the parts' current borders, and each cell goes to the part whose clusters cover most of it
    when they cover more than ``COVERED_SHARE``, else to the part whose surface (its lowest nearby plane) is highest
    at the cell, among the parts with a cluster within ``NEAR_FT``."""
    part_of = {k: g for g, ks in enumerate(groups) for k in ks}
    unions = [unary_union([shapes[k] for k in ks]) for ks in groups]
    chords: list[BaseGeometry] = [u.boundary for u in unions]
    for (i, j) in shared:
        if i in part_of and j in part_of and part_of[i] != part_of[j]:
            ri = raws[i] if not raws[i].is_empty else shapes[i]
            rj = raws[j] if not raws[j].is_empty else shapes[j]
            ml = meet_line(eqs[i], eqs[j], anchor_between(ri, rj), dirs, MIN_GRAD_DIFF)
            if ml is None:
                continue
            touch = touch_points(ri, rj)
            if len(touch) >= MIN_TOUCH_PTS:
                offs = sorted(_offset(q, ml) for q in touch)
                m = offs[len(offs) // 2]
                if abs(m) <= MAX_SHIFT_FT:
                    ml = _shifted(ml, m)
            chords.append(long_line(*ml))
    cells = cut(reg, chords)
    owner = []
    for c in cells:
        cover = [sum(c.intersection(raws[k]).area for k in ks if not raws[k].is_empty) for ks in groups]
        top = max(range(len(groups)), key=lambda g: cover[g])
        if cover[top] > COVERED_SHARE * c.area:  # measured: the part whose clusters cover it
            owner.append(top)
            continue
        rp = c.representative_point()
        best = None
        for g, ks in enumerate(groups):
            near = [k for k in ks if (raws[k] if not raws[k].is_empty else shapes[k]).distance(rp) <= NEAR_FT]
            if near:
                z = min(z_at(eqs[k], rp.x, rp.y) for k in near)
                if best is None or z > best[0]:
                    best = (z, g)
        owner.append(best[1] if best is not None else
                     max(range(len(groups)), key=lambda g: (c.intersection(unions[g]).area, -g)))
    return [unary_union([c for c, o in zip(cells, owner, strict=True) if o == g]) for g in range(len(groups))]


def _starved(cells: list[Polygon], labels: list[int], members: list[int], raws: list[BaseGeometry]) -> list[int]:
    """Planes left with less than ``MIN_KEEP_SHARE`` of their raw cluster's area."""
    kept = {k: sum(c.area for c, lab in zip(cells, labels, strict=True) if lab == k) for k in members}
    return [k for k in members if raws[k].area > 0 and kept[k] < MIN_KEEP_SHARE * raws[k].area]


def _rect_sides(raw: BaseGeometry) -> list[LineString]:
    """The sides of the cluster's minimum rotated rectangle, each run 1 ft past its corners."""
    ring = list(raw.minimum_rotated_rectangle.exterior.coords) if not raw.is_empty else []
    out = []
    for a, b in itertools.pairwise(ring):
        ln = math.dist(a, b)
        if ln > 1e-6:
            d = ((b[0] - a[0]) / ln, (b[1] - a[1]) / ln)
            out.append(LineString([(a[0] - d[0], a[1] - d[1]), (b[0] + d[0], b[1] + d[1])]))
    return out


def partition(reg: BaseGeometry, members: list[int], raws: list[BaseGeometry], shapes: list[BaseGeometry],
               eqs: list[Eq], shared: dict[tuple[int, int], BaseGeometry], dirs: list[float], u: float, fp: Polygon,
               log_to: list[dict[str, Any]], tight: bool = False) -> tuple[list[Polygon], list[int], dict[str, Any]]:
    """Cells of one section (or part of one) and the plane each goes to, with how it was decided."""
    sides: dict[int, list[tuple[Polygon, BaseGeometry]]] = {}
    chords = (section_chords(members, raws, shapes, eqs, shared, dirs, u, sides, log_to, reg.boundary)
              if len(members) > 1 else [])
    boxed: list[int] = []
    for rnd in range(3 if tight else 2):  # later passes outline the clusters of planes no roof line isolated
        cells = cut(reg, chords) if chords else polygons_of(reg)
        labels, disagree = label_envelope(cells, members, raws, eqs, shapes, sides)
        labels = tidy_labels(cells, labels, raws, sides, fp.exterior)
        starved = _starved(cells, labels, members, raws)
        if not starved or len(members) < 2 or (boxed and not tight) or rnd == 2:
            break
        if not boxed:  # a dormer, an awning: the box of its cluster in the building axes
            boxed = starved
            chords = chords + [side for k in starved for side in box_sides(raws[k], u, fp)]
        else:  # (retry only) a small plane at an angle: its cluster's own rectangle
            chords = chords + [side for k in starved for side in _rect_sides(raws[k])]
    method = "envelope"
    if disagree > MAX_DISAGREE or starved:
        method = "arrangement"
        labels = tidy_labels(cells, label_arrangement(cells, members, raws, shapes, sides), raws, sides, fp.exterior)
    return cells, labels, {"method": method, "disagree": round(disagree, 3), "starved": starved, "boxed": boxed,
                           "cells": len(cells)}
