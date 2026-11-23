"""Roof engine subpackage (plane-based modelling; see the roof-engine plan).

``measure_roof`` is the one entry point. Everything heavy (numpy, scipy, shapely) is imported lazily inside it, so
``import roof_measure`` stays numpy-free (tests/test_library_imports.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .params import EngineParams
    from .types import EngineResult, RoofPoints

__all__ = ["measure_roof"]


def measure_roof(points: RoofPoints, footprint_m: Any, *, params: EngineParams | None = None,
                 deadline: float | None = None, outline_source: str = "county", parcel_match: str | None = None,
                 context: Any = None) -> EngineResult:
    """Measure one roof.

    ``points`` are the roof returns (metres, any metric frame; z absolute), ``footprint_m`` the building outline
    (shapely polygon, same frame). ``deadline`` is a ``time.monotonic()`` value: past it the engine raises
    ``EngineTimeout``. ``outline_source`` names the outline's provider ("county" / "lariac" outlines are wall lines
    and get the measured overhang). ``parcel_match`` is passed through to ``quality``. ``context`` is an optional
    (m, 4) cloud x, y, z, ASPRS class (wider than the roof) used only for the ``extra_roof_ring_ratio`` signal.

    Never crashes on bad input: unusable points or footprints give a refused result (``result.refused``, the reason
    in ``result.quality.verdict``: ``lidar_too_sparse``, ``bad_footprint`` or ``bad_points``); a passed deadline raises
    ``EngineTimeout`` and any unexpected failure ``EngineFailure``; both are ``EngineError``.
    """
    from .errors import EngineError, EngineFailure
    from .measure import measure_stages
    from .params import DEFAULT

    try:
        return measure_stages(points, footprint_m, params=params or DEFAULT, deadline=deadline,
                              outline_source=outline_source, parcel_match=parcel_match, context=context)[0]
    except EngineError:
        raise
    except Exception as ex:  # callers only ever see EngineError subclasses
        raise EngineFailure(f"{type(ex).__name__}: {str(ex)[:200]}") from ex
