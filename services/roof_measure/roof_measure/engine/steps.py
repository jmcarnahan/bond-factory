"""Names of a step between two roofs (plan 3.1, E4): the line where a higher roof stands over a lower one.

  * ``step_flashing`` (sidewall): the step line runs DOWN the lower roof's slope (within ``step_along_deg`` of its fall line);
  * ``wall_flashing`` (headwall): the line runs ACROSS the lower slope with the upper roof up-slope of it, or the lower roof is
    low-slope (flat): a wall that water runs up to;
  * ``level_change``: only a step between two low-slope facets.

The line test comes first (a step along the fall line is sidewall whatever stands beside it), then "is the upper roof up-slope
of the line" (the lower facet's fall direction points away from the upper roof). A step across the lower slope with the upper
roof DOWN-slope of it (a lower roof draining into a higher wall) is sidewall flashing too.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from .edge_measure import into
from .params import EngineParams
from .plane_math import zat
from .types import Facet


def lower_upper(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray) -> tuple[Facet, Facet]:
    """(lower, upper) facet of a step, by plane height at the middle of the line."""
    mid = (p0 + p1) / 2
    return (fa, fb) if zat(fa.plane, *mid) <= zat(fb.plane, *mid) else (fb, fa)


def step_name(low_plane: Sequence[float], low_flat: bool, up_flat: bool, line: np.ndarray, to_upper: np.ndarray,
              p: EngineParams) -> str:
    """The name of a step from the numbers alone: the lower facet's plane (``z = a x + b y + c``) and whether it and the upper
    one are low-slope, the unit direction of the step line, and the unit direction across the line towards the upper roof."""
    if low_flat:
        return "level_change" if up_flat else "wall_flashing"
    fall = -np.array(low_plane[:2], float)
    fall /= max(float(np.hypot(*fall)), 1e-12)
    if math.degrees(math.acos(min(1.0, abs(float(line @ fall))))) <= p.step_along_deg:
        return "step_flashing"
    return "wall_flashing" if float(to_upper @ fall) < -p.step_up_cos else "step_flashing"


def step_type(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, p: EngineParams) -> tuple[str, str]:
    """(edge type, id of the higher facet) of the step line p0-p1 between ``fa`` and ``fb``."""
    low, up = lower_upper(fa, fb, p0, p1)
    line = (p1 - p0) / max(float(np.hypot(*(p1 - p0))), 1e-12)
    return step_name(low.plane, low.roof_type == "flat", up.roof_type == "flat", line, -into(low, p0, p1), p), up.id
