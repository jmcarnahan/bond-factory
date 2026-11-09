"""Storage key conventions."""

import re

_SEPARATORS = re.compile(r"[/\\]")


def _refuse_dots(text: str, what: str) -> None:
    if any(segment in (".", "..") for segment in _SEPARATORS.split(text)):
        raise ValueError(f"{what} must not contain '.' or '..' segments")


def company_key(company_id: str, *parts: str, private: bool = False) -> str:
    """``c/<company_id>/[private/]a/b``.

    Every object lives under its company. Private objects sit under ``private/``, where the local uploads mount never serves
    them. Raises ``ValueError`` for an empty ``company_id``, one containing ``/`` or ``\\``, or any ``.`` / ``..`` segment
    (so a key can never climb out of its company). Parts are stripped of ``/`` and empty ones skipped.
    """
    if not company_id:
        raise ValueError("company_id is required")
    if _SEPARATORS.search(company_id) or company_id in (".", ".."):
        raise ValueError("company_id must be a single path segment")
    tail = [p.strip("/") for p in parts if p and p.strip("/")]
    for part in tail:
        _refuse_dots(part, "a key part")
    middle = ["private"] if private else []
    return "/".join(["c", company_id, *middle, *tail])
