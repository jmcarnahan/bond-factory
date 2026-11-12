"""REPLACE (an app swaps in its own contact store). A small in-code contact list with invented names.

One object plays both seams: the tasks lib's `LinkResolver` (labels and search for the link picker) and the capture
lib's `EntityResolver` (a name in a note becomes candidate contacts). Real apps query their own table, for the
signed-in user only.
"""

from __future__ import annotations

from typing import Any

from bond_tasks_py import LINK_KIND_CONTACT

#: id -> display name (invented; example.com is the only domain the repo allows)
CONTACTS: dict[str, str] = {
    "c-sam-rivera": "Sam Rivera",
    "c-samira-ortiz": "Samira Ortiz",
    "c-dana-whitfield": "Dana Whitfield",
    "c-dana-park": "Dana Park",
    "c-lee-harper": "Lee Harper",
    "c-morgan-quill": "Morgan Quill",
}


class FakeContacts:
    """`LinkResolver` and `EntityResolver` over `CONTACTS`. Matching is a case-insensitive substring, best first."""

    def __init__(self, contacts: dict[str, str] | None = None) -> None:
        self.contacts = dict(CONTACTS if contacts is None else contacts)

    def _find(self, query: str, limit: int) -> list[dict]:
        needle = query.strip().lower()
        if not needle:
            return []
        hits = [(name.lower().find(needle), name, cid) for cid, name in self.contacts.items() if needle in name.lower()]
        hits.sort()  # earliest match first, then name
        return [{"id": cid, "label": name} for _, name, cid in hits[:limit]]

    # LinkResolver
    def labels(self, session: Any, links: list[dict]) -> dict[tuple[str, str], str]:
        found = {}
        for link in links:
            if link.get("kind") == LINK_KIND_CONTACT and link.get("id") in self.contacts:
                found[(LINK_KIND_CONTACT, link["id"])] = self.contacts[link["id"]]
        return found

    def search(self, session: Any, user_id: str, kind: str, query: str, limit: int) -> list[dict]:
        if kind != LINK_KIND_CONTACT:
            return []
        return [{"kind": kind, **row} for row in self._find(query, limit)]

    # EntityResolver
    def resolve(self, user_id: str, name: str, kind: str) -> list[dict]:
        return self._find(name, 5) if kind == LINK_KIND_CONTACT else []
