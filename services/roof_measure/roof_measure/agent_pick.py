"""The agent is an upgrade, never a downgrade: when its roof matches the measured planes worse than the rules'
roof, the rule result is returned.

``rules_if_not_worse`` builds the rule method's model on the same LiDAR blocks and compares both against the snapped
planes with ``quality.plane_mismatch_pct``. Lower mismatch wins; a tie goes to the rule result. It never raises: when
the rule roof cannot be built, or either mismatch is unknown, the agent's roof stands.
"""

from __future__ import annotations

import logging
from typing import Any

from shapely.errors import ShapelyError

from .classify import BlockSet, Classification, RoofBlock, classify_blocks
from .model import build_model
from .planes import snap_with_stats
from .quality import plane_mismatch_pct

log = logging.getLogger(__name__)


def rules_if_not_worse(base: BlockSet, agent_model: dict[str, Any], warning_codes: list[str], **kw: Any
                       ) -> tuple[Classification, list[RoofBlock], str] | None:
    """``(classification, roof_blocks, cause)`` of the rule result when it is at least as good as the agent's, else None.

    ``cause`` is the one-line reason for the warning. ``kw`` is what ``classify_blocks`` takes (``merge_flats``).
    """
    if not base.blocks:
        return None
    try:
        snap = snap_with_stats(base, clip_to_footprint="parcel_street_match" not in warning_codes)
        if snap.failed or not snap.planes:
            return None
        classification = classify_blocks(base, **kw)
        rule_model = build_model(base, classification.blocks, {"method": "lidar_skeleton"}, classification)
        rule = plane_mismatch_pct(snap.planes, rule_model)
        agent = plane_mismatch_pct(snap.planes, agent_model)
    except (ValueError, ShapelyError, ArithmeticError, IndexError, KeyError, TypeError):
        log.info("agent versus rules comparison skipped", exc_info=True)
        return None
    if rule is None or agent is None or agent < rule:
        return None
    cause = f"its roof matched the measured planes worse than the rule roof ({agent:.0f}% against {rule:.0f}% mismatch)"
    return classification, classification.blocks, cause
