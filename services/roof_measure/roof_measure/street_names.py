"""Street-line normalisation: "12 Ave B" and "12 AVENUE B" become the same string.

WHY: the county's situs address spells street types out ("AVENUE B") while a lead types "Ave B". Comparing the raw
strings called that a weak "street" match. Pure functions, no I/O.

Canonical form: upper case, no punctuation, one space between tokens; USPS street types in full (AVENUE, STREET),
directionals as letters (N, SW) except when the directional word IS the street name ("North St"), ordinals as digits
(FIRST -> 1ST), unit designators and their value dropped. Spanish prefixes (AVENIDA, CALLE, CAMINO, VIA) are left
alone.
"""

from __future__ import annotations

import re

# canonical long form -> accepted spellings (USPS Publication 28, the common ones)
_SUFFIXES = {
    "ALLEY": ("ALY", "ALLEE"), "AVENUE": ("AVE", "AV", "AVEN", "AVENU"), "BOULEVARD": ("BLVD", "BOUL", "BLV"),
    "CIRCLE": ("CIR", "CIRC"), "COURT": ("CT",), "COVE": ("CV",), "CANYON": ("CYN", "CANYN"),
    "CRESCENT": ("CRES", "CRSENT"), "CROSSING": ("XING",), "DRIVE": ("DR", "DRV"), "EXPRESSWAY": ("EXPY", "EXPR"),
    "FREEWAY": ("FWY", "FRWY"), "GROVE": ("GRV",), "HEIGHTS": ("HTS",), "HIGHWAY": ("HWY", "HIWAY"),
    "LANE": ("LN",), "LOOP": (), "PARKWAY": ("PKWY", "PKY", "PARKWY"), "PATH": (), "PLACE": ("PL",),
    "PLAZA": ("PLZ",), "ROAD": ("RD",), "ROW": (), "SQUARE": ("SQ", "SQR"), "STREET": ("ST", "STR", "STRT"),
    "TERRACE": ("TER", "TERR"), "TRAIL": ("TRL", "TRAILS"), "TURNPIKE": ("TPKE", "TRNPK"), "WALK": (), "WAY": (),
}
SUFFIX_CANON = {long: long for long in _SUFFIXES} | {s: long for long, vs in _SUFFIXES.items() for s in vs}

_DIRECTIONALS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "NORTHEAST": "NE", "NORTHWEST": "NW",
                 "SOUTHEAST": "SE", "SOUTHWEST": "SW"}
_DIR_SHORT = frozenset(_DIRECTIONALS.values())
_ORDINALS = {"FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH", "FIFTH": "5TH", "SIXTH": "6TH",
             "SEVENTH": "7TH", "EIGHTH": "8TH", "NINTH": "9TH", "TENTH": "10TH"}
_UNITS = frozenset({"APT", "APARTMENT", "UNIT", "STE", "SUITE", "SPC", "SPACE", "BLDG", "BUILDING", "RM", "ROOM",
                    "FL", "FLOOR", "#"})
_NUMBER = re.compile(r"^\d+[A-Z]?$")
_FRACTION = re.compile(r"^\d+/\d+$")


def _tokens(line: str) -> list[str]:
    text = line.upper().replace("#", " # ")
    text = re.sub(r"[^A-Z0-9/# ]", " ", text)  # punctuation and hyphens become spaces; "/" stays for "1/2"
    return text.split()


def _drop_units(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] in _UNITS and i > 0:  # never the first word: the house number or street name comes first
            i += 2  # the designator and its value
            continue
        out.append(tokens[i])
        i += 1
    return out


def _is_marker(tok: str) -> bool:
    """A lone letter or a number: the thing that follows "Ave" in "Ave B" or "Avenue 64"."""
    return len(tok) == 1 or tok.isdigit()


def _street_words(words: list[str]) -> list[str]:
    """Canonicalise the street part (no house number)."""
    out: list[str] = []
    n = len(words)
    for i, w in enumerate(words):
        remaining = n - i - 1
        if w in _DIRECTIONALS:
            # "North St": the word is the name when it is the first word and nothing but a suffix follows
            out.append(w if (i == 0 and remaining < 2) else _DIRECTIONALS[w])
        elif w in _ORDINALS:
            out.append(_ORDINALS[w])
        elif w == "ST" and i == 0 and remaining >= 1 and not (remaining == 1 and _is_marker(words[i + 1])):
            out.append("SAINT")  # "St Andrews Pl": a leading ST is SAINT; "St H" stays a street called H
        elif w in SUFFIX_CANON:
            out.append(SUFFIX_CANON[w])
        else:
            out.append(w)
    return out


def normalize_street(line: str) -> str:
    """Canonical text of a street line, house number and fraction kept ("12 1/2 Ave B" -> "12 1/2 AVENUE B")."""
    tokens = _drop_units(_tokens(line or ""))
    head: list[str] = []
    if len(tokens) > 1 and _NUMBER.match(tokens[0]):
        head.append(tokens.pop(0))
        if len(tokens) > 1 and _FRACTION.match(tokens[0]):
            head.append(tokens.pop(0))
    return " ".join(head + _street_words(tokens))


def street_key(line: str) -> str:
    """The canonical street name only (house number and fraction removed): "12 Ave B" -> "AVENUE B"."""
    parts = normalize_street(line).split()
    while parts and (_NUMBER.match(parts[0]) or _FRACTION.match(parts[0])) and len(parts) > 1:
        parts.pop(0)
    return " ".join(parts)


def _split_direction(key: str) -> tuple[str, str]:
    parts = key.split()
    if len(parts) >= 3 and parts[0] in _DIR_SHORT:
        return parts[0], " ".join(parts[1:])
    return "", key


def same_street(a: str, b: str) -> bool:
    """True when two street keys (``street_key``) name the same street.

    A missing directional on one side is tolerated ("182ND STREET" vs "W 182ND STREET"); a street type missing on one
    side is tolerated only when the other side's name is otherwise identical and has exactly one type word.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    da, na = _split_direction(a)
    db, nb = _split_direction(b)
    if (da == db or not da or not db) and na == nb:
        return True
    wa, wb = na.split(), nb.split()
    short, long = (wa, wb) if len(wa) < len(wb) else (wb, wa)
    return (len(long) == len(short) + 1 and long[:-1] == short and long[-1] in SUFFIX_CANON.values()
            and (da == db or not da or not db))
