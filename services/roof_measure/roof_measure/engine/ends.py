"""End pieces of an interior line: a piece of the boundary between two facets that on its own reads as no edge (``kink``: one
slope carries on across it; ``seam``: the two planes meet) but that touches a line of the SAME two facets: the valley, hip or
step it ends. Where a boundary turns at an eave corner the slope test of the last piece changes sign and the piece used to be
dropped, with its feet, from every total. A piece like that keeps the type of the line it continues.
"""

from __future__ import annotations

import numpy as np

from .params import EngineParams

ADOPTABLE = ("ridge", "hip", "valley", "level_change")  # types a boundary piece can continue
ADOPTING = ("kink", "seam")  # why a piece got no edge of its own: it may be the end of a line


def _touch(a0: np.ndarray, a1: np.ndarray, b0: np.ndarray, b1: np.ndarray, tol: float) -> bool:
    return min(float(np.hypot(*(u - v))) for u in (a0, a1) for v in (b0, b1)) <= tol


def adopt_end_pieces(raw: list, dropped: list, p: EngineParams) -> tuple[list, list]:
    """(pieces to add to ``raw`` as (type, a, b, facet-index pair), the dropped pieces that stay dropped).

    ``raw`` holds the typed boundary pieces (type, a, b, facet-index tuple); ``dropped`` the untyped shared pieces as
    (facet-id pair, length m, why, a, b, facet-index pair). A dropped piece of kind ``kink`` or ``seam`` touching (within
    ``p.end_touch_m``) a typed crease or step piece of the same facet pair takes its type, and so can the next piece after it:
    it is repeated until nothing more joins. Pieces under ``p.edge_min_seg_m`` stay dropped (the chain step drops them too)."""
    typed = [(t, a, b, fs) for t, a, b, fs in raw if len(fs) == 2 and t in ADOPTABLE]
    pending = [d for d in dropped if d[2] in ADOPTING and d[1] >= p.edge_min_seg_m]
    added: list = []
    taken: set[int] = set()
    joined = True
    while joined:
        joined = False
        for k, (_ids, _len, _why, a, b, fs) in enumerate(pending):
            near = [t for t, a2, b2, fs2 in typed if fs2 == fs and _touch(a, b, a2, b2, p.end_touch_m)]
            if k in taken or not near:
                continue
            length = {t: 0.0 for t in near}  # the longest touching line decides when two different ones meet the piece
            for t2, a2, b2, fs2 in typed:
                if fs2 == fs and t2 in length:
                    length[t2] += float(np.hypot(*(b2 - a2)))
            piece = (max(length, key=length.get), a, b, fs)
            typed.append(piece)
            added.append(piece)
            taken.add(k)
            joined = True
    kept = {id(d) for k, d in enumerate(pending) if k in taken}
    return added, [d for d in dropped if id(d) not in kept]


CREASES = ("ridge", "hip", "valley")


def resolve_steps(chains: list, jumps: list, stubs: list, p: EngineParams) -> list[tuple[str, float | None] | None]:
    """For each chain (type, facet-index pair, p0, p1): ``(type, jump m)`` it really is when it is a piece of another line, else None.

    A short step (clutter on its own, ``stubs``) that touches a line of the same two facets is the end of that line and takes
    its type and jump (the longest such line decides; stubs that touch only each other join in turn, until nothing more does).
    A run of steps (one or several pieces end to end) with a ridge, hip or valley of the same two facets at BOTH its ends is a jog
    of the boundary round something on the roof (a chimney): two planes meet in one line, so there is no wall between them, and
    the run keeps the crease type."""
    kinds = [c[0] for c in chains]
    jmp = list(jumps)
    open_stub = list(stubs)
    out: list[tuple[str, float | None] | None] = [None] * len(chains)

    def touching(k: int, end: np.ndarray, allowed: tuple) -> list[int]:
        return [j for j, (_t, fs, a, b) in enumerate(chains)
                if j != k and not open_stub[j] and fs == chains[k][1] and kinds[j] in allowed
                and min(float(np.hypot(*(end - v))) for v in (a, b)) <= p.end_touch_m]

    def longest(near: list[int]) -> int:
        return max(near, key=lambda j: float(np.hypot(*(chains[j][3] - chains[j][2]))))

    joined = True
    while joined:
        joined = False
        for k in range(len(chains)):
            if open_stub[k] and (near := sorted(set(touching(k, chains[k][2], ADOPTABLE)) | set(touching(k, chains[k][3], ADOPTABLE)))):
                best = longest(near)
                kinds[k], jmp[k], open_stub[k] = kinds[best], jmp[best], False
                out[k] = (kinds[k], jmp[k])
                joined = True
    steps = [k for k, (_t, fs, _a, _b) in enumerate(chains) if kinds[k] == "level_change" and len(fs) == 2 and not open_stub[k]]
    seen: set[int] = set()
    for k0 in steps:  # each run of steps of one facet pair that joins end to end
        if k0 in seen:
            continue
        run, todo = [], [k0]
        while todo:
            k = todo.pop()
            if k in run:
                continue
            run.append(k)
            todo += [j for j in steps if j not in run and chains[j][1] == chains[k][1]
                     and min(float(np.hypot(*(u - v))) for u in chains[k][2:] for v in chains[j][2:]) <= p.end_touch_m]
        seen.update(run)
        points = [e for k in run for e in chains[k][2:]]
        free = [e for e in points if sum(float(np.hypot(*(e - f))) <= p.end_touch_m for f in points) == 1]  # ends no other piece meets
        if len(free) != 2:
            continue
        ends = [touching(k0, e, CREASES) for e in free]
        if ends[0] and ends[1]:
            best = longest(sorted(set(ends[0]) | set(ends[1])))
            for k in run:
                out[k] = (kinds[best], jmp[best])
    return out
