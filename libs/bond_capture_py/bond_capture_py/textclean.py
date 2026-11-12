"""Text hygiene for titles and link names: no control characters, no bidi overrides."""

import re

# Built from code points so no invisible character sits in this source file.
_BIDI = [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]  # embeddings and overrides, then isolates
_SPACE_POINTS = [9, 10, 11, 12, 13, 0x2028, 0x2029]
_SPACES = re.compile("[" + "".join(map(chr, _SPACE_POINTS)) + "]+")
_STRIP = re.compile("[" + "".join(map(chr, [*range(32), *range(0x7F, 0xA0), *_BIDI])) + "]")


def clean_text(text: str, cap: int) -> str:
    """Line breaks and tabs become one space, other control characters (C0 with NUL, DEL, C1) and the bidi
    overrides U+202A-202E and isolates U+2066-2069 are removed, then the text is stripped and cut at ``cap``
    characters (and stripped again). May return an empty string."""
    text = _SPACES.sub(" ", text)
    return _STRIP.sub("", text).strip()[:cap].strip()
