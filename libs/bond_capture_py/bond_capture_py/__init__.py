"""Natural-language capture. Imports only pydantic, tzdata and the standard library; never another bond lib."""

from bond_capture_py.candidates import (
    FLAG_LOW_CONFIDENCE,
    LOW_CONFIDENCE,
    CaptureResult,
    EventCandidate,
    LinkCandidate,
    TaskCandidate,
)
from bond_capture_py.capture import parse_capture
from bond_capture_py.errors import CODES, CaptureDenied, CaptureError, LlmInvalid, LlmUnavailable
from bond_capture_py.fallback import degraded_draft
from bond_capture_py.prompt import build_prompt, fence
from bond_capture_py.protocols import CaptureGuard, EntityResolver, LlmClient
from bond_capture_py.schema import MAX_ITEMS, MAX_LINKS, MAX_TEXT, MODEL_SCHEMA

__version__ = "0.1.0"

__all__ = [
    "CODES",
    "FLAG_LOW_CONFIDENCE",
    "LOW_CONFIDENCE",
    "MAX_ITEMS",
    "MAX_LINKS",
    "MAX_TEXT",
    "MODEL_SCHEMA",
    "CaptureDenied",
    "CaptureError",
    "CaptureGuard",
    "CaptureResult",
    "EntityResolver",
    "EventCandidate",
    "LinkCandidate",
    "LlmClient",
    "LlmInvalid",
    "LlmUnavailable",
    "TaskCandidate",
    "build_prompt",
    "degraded_draft",
    "fence",
    "parse_capture",
]
