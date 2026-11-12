"""Roof measurement from an address: an importable library (``measure``) and a private job service.

``measure()`` returns the ``bond.roof_model/0.2`` envelope or raises ``MeasureError``; the service wraps the same
pipeline in an async job API. Keys and directories are arguments to ``measure``, never environment variables.
"""

from .library import KILL_GRACE_S, STAGES, MeasureError, measure, purge_cache

__all__ = ["KILL_GRACE_S", "STAGES", "MeasureError", "measure", "purge_cache"]
