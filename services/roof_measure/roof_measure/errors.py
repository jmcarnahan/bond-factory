"""API error codes: the object shape, which exception becomes which code, which codes are retryable."""

from __future__ import annotations

from typing import Any

REQUEST_CODES = {"invalid_request": 422, "unauthorized": 401, "unknown_job": 404, "queue_full": 429}
JOB_CODES = ("address_not_found", "no_footprint", "ambiguous_building", "no_lidar_coverage", "lidar_too_sparse",
             "measurement_failed", "upstream_unavailable", "timeout", "interrupted")
RETRYABLE = frozenset({"queue_full", "upstream_unavailable", "timeout", "interrupted"})
MESSAGES = {
    "invalid_request": "The request is invalid.",
    "unauthorized": "Missing or invalid bearer token.",
    "unknown_job": "No such job; submit the measurement again.",
    "queue_full": "The service is busy; retry shortly.",
    "address_not_found": "The address could not be located.",
    "no_footprint": "No building outline was found at this location.",
    "ambiguous_building": "More than one building of similar size is near this point; supply coordinates of the roof.",
    "no_lidar_coverage": "No LiDAR coverage was found for this building.",
    "lidar_too_sparse": "The LiDAR data over this roof is too sparse to measure.",
    "measurement_failed": "The roof could not be measured.",
    "upstream_unavailable": "A data source was unavailable; retry later.",
    "timeout": "The measurement took too long; retry later.",
    "interrupted": "The service restarted while measuring; submit again.",
}


def retryable_for(code: str) -> bool:
    return code in RETRYABLE


def error_object(code: str, message: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message or MESSAGES.get(code, MESSAGES["measurement_failed"]),
            "retryable": retryable_for(code)}


def error_body(code: str, message: str | None = None) -> dict[str, Any]:
    return {"error": error_object(code, message)}


_BY_NAME = {
    "FootprintUnavailable": "upstream_unavailable", "GeocodeUnavailable": "upstream_unavailable", "LidarUnavailable": "upstream_unavailable",
    "FootprintError": "no_footprint", "AmbiguousBuilding": "ambiguous_building", "LidarTooSparse": "lidar_too_sparse",
    "LidarError": "no_lidar_coverage", "GeocodeError": "address_not_found", "BadResponse": "upstream_unavailable",
    "DeadlineExceeded": "timeout", "TimeoutError": "timeout",
}
# transient errors from the SDKs (matched by class name over the cause chain) and from our own wrappers (by text)
_TRANSIENT_CLASSES = frozenset({
    "RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError", "OverloadedError",
    "TimeoutException", "TransportError", "ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError",
    "ConnectionError", "Timeout"})
_TRANSIENT_TEXT = ("http 429", "http 500", "http 502", "http 503", "http 504", "http 529", "request failed",
                   "rate limit", "overloaded", "connection error", "timed out")


def is_transient(exc: BaseException) -> bool:
    """True for upstream blips: SDK/httpx/requests network and 429/5xx errors, also behind a wrapper's cause."""
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if any(c.__name__ in _TRANSIENT_CLASSES for c in type(e).__mro__):
            return True
        if type(e).__name__ in ("SolarUnavailable", "AgentError", "PipelineError") and any(
                m in str(e).lower() for m in _TRANSIENT_TEXT):
            return True
        e = e.__cause__ or e.__context__
    return False


def code_for(exc: BaseException) -> str:
    """Map an exception raised by the pipeline to one of the job failure codes (class names: no imports)."""
    import requests

    if isinstance(exc, requests.RequestException) or is_transient(exc):
        return "upstream_unavailable"
    for cls in type(exc).__mro__:
        code = _BY_NAME.get(cls.__name__)
        if code:
            return code
    return "measurement_failed"  # PipelineError, BlocksError, ModelError, AgentError, SolarUnavailable, the rest


HUMAN_MESSAGE_CLASSES = frozenset({
    "GeocodeError", "FootprintError", "AmbiguousBuilding", "LidarError", "LidarTooSparse", "BlocksError", "ModelError",
    "PipelineError", "SolarUnavailable", "DeadlineExceeded", "FootprintUnavailable", "LidarUnavailable", "GeocodeUnavailable"})


def error_from(exc: BaseException) -> dict[str, Any]:
    """The job error object: the code, and for pipeline classes their own one-line human message (<= 300 chars).

    Other exceptions (bugs, library errors) get the generic message for their code: their text can hold paths.
    """
    code = code_for(exc)
    if type(exc).__name__ in HUMAN_MESSAGE_CLASSES and str(exc).strip():
        notes = " ".join(getattr(exc, "__notes__", []))
        return error_object(code, " ".join(f"{exc} {notes}".split())[:300])
    return error_object(code)
