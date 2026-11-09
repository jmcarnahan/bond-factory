"""Scope policy: what sign-in asks for, which role asks follow, and e-mail matching."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

_GMAIL = ("gmail.com", "googlemail.com")


class UnknownScopeSet(LookupError):
    code = "invalid_request"


@dataclass(frozen=True)
class ScopeSet:
    id: str
    provider: str
    scopes: tuple[str, ...]
    label: str = ""


@dataclass(frozen=True)
class ScopePolicy:
    """``signin``: scopes per provider asked at sign-in. ``by_capability``: sets asked after sign-in per role."""

    signin: Mapping[str, tuple[str, ...]]
    by_capability: Mapping[str, tuple[ScopeSet, ...]] = field(default_factory=dict)

    def signin_scopes(self, provider: str) -> tuple[str, ...]:
        return tuple(self.signin.get(provider, ()))

    def wanted(self, caps: Iterable[str], provider: str) -> list[ScopeSet]:
        """The union of the sets of every held capability for ``provider``; each set once, first-seen order."""
        held = set(caps)
        seen: dict[str, ScopeSet] = {}
        for cap, sets in self.by_capability.items():
            if cap in held:
                for item in sets:
                    if item.provider == provider:
                        seen.setdefault(item.id, item)
        return list(seen.values())

    def set(self, set_id: str) -> ScopeSet:
        for sets in self.by_capability.values():
            for item in sets:
                if item.id == set_id:
                    return item
        raise UnknownScopeSet(set_id)


def _has_all(granted: Iterable[str], wanted: Sequence[str]) -> bool:
    have = {g.lower() for g in granted}
    return all(w.lower() in have for w in wanted)


def wanted_sets(policy: ScopePolicy, caps: Iterable[str], provider: str, granted_scopes: Iterable[str]) -> list[dict]:
    """The ``wanted`` list of ``GET /connections``: ``{id, provider, label, scopes, granted}`` per set."""
    granted = list(granted_scopes or ())
    return [{"id": s.id, "provider": s.provider, "label": s.label, "scopes": list(s.scopes),
             "granted": _has_all(granted, s.scopes)} for s in policy.wanted(caps, provider)]


def connect_scopes(policy: ScopePolicy, set_id: str, granted: Iterable[str]) -> list[str]:
    """Scopes for ``start?set=``. Microsoft: granted plus the set (no server-side merge). Google: the set alone,
    ``include_granted_scopes`` merges. Raises ``UnknownScopeSet`` (code ``invalid_request``)."""
    chosen = policy.set(set_id)
    if chosen.provider != "microsoft":
        return list(chosen.scopes)
    merged: dict[str, str] = {}
    for scope in [*granted, *chosen.scopes]:
        merged.setdefault(scope.lower(), scope)
    return list(merged.values())


def normalize_email(provider: str, email: str) -> str:
    """Lowercase and strip. Google addresses at gmail.com / googlemail.com also lose dots and the ``+tag``.
    For matching only: the stored invite e-mail is unchanged."""
    value = (email or "").strip().lower()
    local, sep, domain = value.rpartition("@")
    if provider == "google" and sep and domain in _GMAIL:
        return local.split("+", 1)[0].replace(".", "") + "@" + domain
    return value
