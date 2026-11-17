"""After ``complete_tiling``: make the agent's blocks a clean partition of the footprint.

``complete_tiling`` clips blocks to the footprint but lets two sloped blocks overlap (up to 10% is accepted) and leaves
jagged outlines whose straight skeleton has many tiny facets. This pass, deterministic and run on every agent result:

1. the HIGHER block keeps an overlap (levels from the LiDAR under each block), so two sections meet along one straight
   cut: the edge of the higher block;
2. each sloped block's outline is opened (tails and spurs under 2 * ``OPEN_FT`` wide removed) and closed (notches
   under ``CLOSE_FT`` filled where no other block is) with square corners, so the skeleton sees a simple outline;
3. every piece of the footprint nobody holds under ``SLIVER_SQFT`` goes to the neighbouring block it shares the
   longest edge with; a tail cut off a block (narrower than 2 * ``OPEN_FT``) is left uncovered, since glued to a
   neighbour it would make a thin wedge;
4. gable ends are remapped onto the new outlines (``agent_draft.remap_gables``).
A change that would lose more than 10% of a block's area is not made. Returns notes for the model.
"""

from __future__ import annotations

from shapely.geometry import Polygon
from shapely.ops import unary_union

from .agent_draft import capture_gables, remap_gables
from .classify import BlockSet, RoofBlock, assign_levels, clean_polygon, polygons_of, ring_of
from .skeleton import block_geometry

CLOSE_FT = 1.0
OPEN_FT = 1.0
SLIVER_SQFT = 15.0
KEEP = 0.9
RECT_KEEP = 0.85  # a hip block becomes its rectangle when that is within this share of its area
SIMPLIFY_FT = 0.15
TINY_FACET_SQFT = 12.0  # jogs this small are noise (they make a spike facet in the skeleton)


def _largest(g) -> Polygon | None:
    parts = polygons_of(g)
    return max(parts, key=lambda p: p.area) if parts else None


def _longest_neighbour(piece: Polygon, owners: list[tuple[RoofBlock, Polygon]], skip: RoofBlock | None):
    best, length = None, 0.5
    for b, poly in owners:
        if b is skip:
            continue
        n = piece.buffer(0.05).intersection(poly.boundary).length
        if n > length:
            best, length = b, n
    return best


def tidy_tiling(done: list[RoofBlock], blockset: BlockSet) -> list[str]:
    """Partition ``done`` in place (see the module docstring); returns the notes to keep."""
    fp = blockset.footprint
    sloped = [b for b in done if b.form != "flat"]
    if not sloped:
        return []
    captured = capture_gables(done)
    assign_levels(done, blockset)
    notes: list[str] = []
    polys: dict[int, Polygon] = {}
    taken = Polygon()
    cut_off: list[tuple[Polygon, RoofBlock]] = []
    for b in sorted(sloped, key=lambda x: -(x.level_ft or 0.0)):
        p = b.poly
        before = p.area
        p = _largest(p.difference(taken)) or p
        if before - p.area > 1.0:
            notes.append(f"Block {b.id} was trimmed by {before - p.area:.0f} sq ft where it overlapped a higher block.")
        opened = _largest(p.buffer(-OPEN_FT, join_style=2).buffer(OPEN_FT, join_style=2))
        if opened is not None and opened.area >= KEEP * p.area:
            for piece in polygons_of(p.difference(opened)):
                if piece.area >= 0.05:
                    cut_off.append((piece, b))
            p = opened
        closed = _largest(p.buffer(CLOSE_FT, join_style=2).buffer(-CLOSE_FT, join_style=2).intersection(fp)
                          .difference(taken))
        if closed is not None and closed.area >= p.area:
            p = closed
        if b.form == "hip":  # a hip over a near-rectangle: the rectangle (clipped) has 4 faces, not 8
            rect = _largest(p.minimum_rotated_rectangle.intersection(fp).difference(taken))
            if (rect is not None and RECT_KEEP * p.area <= rect.area <= p.area / RECT_KEEP
                    and len(ring_of(rect.simplify(SIMPLIFY_FT), 0.0)) < len(ring_of(p.simplify(SIMPLIFY_FT), 0.0))):
                notes.append(f"Block {b.id} drawn as a rectangle clipped to the footprint.")
                p = rect
        polys[id(b)] = p
        taken = taken.union(p)
    flats = [b for b in done if b.form == "flat"]
    for f in flats:
        polys[id(f)] = _largest(f.poly.difference(taken)) or f.poly
    owners = [(b, polys[id(b)]) for b in done]
    gap = fp.difference(unary_union([p for _, p in owners] + [c.buffer(0.1) for c, _ in cut_off]))
    pieces = [(g, None) for g in polygons_of(gap)]  # a cut-off tail is left uncovered: a thin wedge on a neighbour makes a spike
    for piece, source in pieces:
        if piece.area >= SLIVER_SQFT or piece.area < 0.05:
            continue
        taker = _longest_neighbour(piece, [(b, polys[id(b)]) for b in done], source)
        if taker is None:
            continue
        merged = unary_union([polys[id(taker)], piece]).buffer(0)
        if merged.geom_type == "Polygon":
            polys[id(taker)] = merged
    for b in done:
        b.polygon = ring_of(clean_polygon(polys[id(b)]).simplify(SIMPLIFY_FT, preserve_topology=True), 0.0)  # spikes out
    for b in done:
        if b.form == "hip":
            _drop_tiny_facets(b, notes)
    remap_gables(done, captured)
    return notes


def _tiny(b: RoofBlock) -> bool:
    try:
        geom = block_geometry(b.form, b.polygon, b.pitch_rise, b.gable_edges, b.aspect_deg, b.ridge_gable)
    except ValueError:
        return False  # the buildability check reports it
    return any(f["plan_area"] < TINY_FACET_SQFT for f in geom["facets"])


def _drop_tiny_facets(b: RoofBlock, notes: list[str]) -> None:
    """A facet under ``TINY_FACET_SQFT`` comes from a jog in the outline: simplify harder (area change under 3%)."""
    if not _tiny(b):
        return
    poly = b.poly
    for tol in (0.3, 0.6, 1.0, 1.5):
        q = _largest(poly.simplify(tol, preserve_topology=True))
        if q is None or abs(q.area - poly.area) > 0.03 * poly.area:
            break
        trial = RoofBlock(id=b.id, form=b.form, polygon=ring_of(q, 0.0), pitch_rise=b.pitch_rise,
                          aspect_deg=b.aspect_deg, gable_edges=list(b.gable_edges), ridge_gable=b.ridge_gable)
        if not _tiny(trial):
            b.polygon = trial.polygon
            notes.append(f"Block {b.id}: jogs under {tol} ft removed from its outline (no facet under "
                         f"{TINY_FACET_SQFT:.0f} sq ft).")
            return

