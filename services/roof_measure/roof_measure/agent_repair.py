"""The agent never crashes after it finishes: build check, advice for the agent, and per-block repair.

The agent's polygons are checked in ``Workspace.finalize`` as it drew them. ``complete_tiling`` then clips them to the
footprint and to each other, and the model builder calls ``block_geometry`` on the CLIPPED polygon, where a gable whose
sides converge can no longer be extended. So the check that counts is the one made here, on the tiled blocks, with the
exact function the builder calls (``block_geometry(form, polygon, pitch, gable_edges, aspect)``).

Order of defence (the agent method is an upgrade, never a new way to fail):
1. :func:`unbuildable` + :func:`advice`: a failure goes back to the agent as a ``finalize`` tool error it can read,
   while it still has rounds.
2. :func:`repair_blocks`: when the answer is final, a gable that cannot be extended becomes a hip over the same polygon
   (a note says so); a block that still cannot be built raises ``ModelError``.
3. The pipeline's existing fallbacks take over from there: the rule result, then the planes-only envelope.
"""

from __future__ import annotations

from collections.abc import Sequence

from .classify import RoofBlock, ridge_azimuth
from .model import ModelError
from .ringgeom import block_geometry

REPAIRED_NOTE = "Gable edges {edges} could not be used on this outline after fitting; drawn as a hip."


def build_error(rb: RoofBlock) -> str | None:
    """The reason ``block_geometry`` refuses this block, or ``None`` when it builds. The call the builder makes."""
    try:
        block_geometry(rb.form, rb.polygon, rb.pitch_rise, rb.gable_edges, rb.aspect_deg, rb.ridge_gable)
    except ValueError as exc:
        return " ".join(str(exc).split())
    return None


def unbuildable(blocks: Sequence[RoofBlock]) -> list[tuple[RoofBlock, str]]:
    """Every sloped block ``block_geometry`` refuses, with the reason (flat blocks have no skeleton)."""
    out = []
    for rb in blocks:
        if rb.form == "flat":
            continue
        why = build_error(rb)
        if why:
            out.append((rb, why))
    return out


def advice(bad: Sequence[tuple[RoofBlock, str, str]], prefix: str = "finalize not accepted, nothing was committed. "
           ) -> str:
    """What the agent reads: ``(block, reason, polygon_id)`` rows turned into one actionable tool error."""
    lines = []
    for rb, why, pid in bad:
        if rb.form == "gable":
            edges = ",".join(str(g) for g in rb.gable_edges)
            lines.append(f"block on polygon {pid}: gable edges {edges} cannot be used on this outline once it is fitted "
                         "to the footprint and the other blocks: choose other gable_edges, call rect_fit on the "
                         "polygon first, or make it a hip")
        else:
            lines.append(f"block on polygon {pid}: a {rb.form} cannot be built on this outline once it is fitted to "
                         f"the footprint and the other blocks ({why[:100]}): call rect_fit on the polygon or split it")
    return prefix + "; ".join(lines)


def repair_blocks(blocks: Sequence[RoofBlock]) -> list[str]:
    """Make every block buildable, in place. Returns the notes to keep (one per repaired block).

    A gable that cannot be extended becomes a hip over the same polygon. Raises :class:`ModelError` when a block is
    still refused (the pipeline then answers with the rule method).
    """
    notes = []
    for rb, why in unbuildable(blocks):
        if rb.form == "gable":
            edges = ",".join(str(g) for g in rb.gable_edges)
            rb.form, rb.gable_edges = "hip", []
            again = build_error(rb)
            if again:
                raise ModelError(f"block {rb.id}: {again}")
            geom = block_geometry(rb.form, rb.polygon, rb.pitch_rise, rb.gable_edges, rb.aspect_deg, rb.ridge_gable)
            rb.ridge_azimuth_deg = ridge_azimuth(rb.form, rb.polygon, rb.aspect_deg, geom)
            text = REPAIRED_NOTE.format(edges=edges)
            rb.notes.append(text)
            rb.confidence = "low"
            notes.append(f"Block {rb.id}: {text}")
        else:
            raise ModelError(f"block {rb.id}: {why}")
    return notes
