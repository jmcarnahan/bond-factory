"""Checks on what a signer submits as a signature: the drawn PNG and the typed name."""

import io
import warnings

from bond_esign.errors import NAME_NOT_RENDERABLE, SIGNATURE_INVALID, EsignError
from bond_esign.types import Policy

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_WIDTH, MAX_HEIGHT = 2400, 1200
MIN_INK_WIDTH, MIN_INK_HEIGHT, MIN_INK_PIXELS = 12, 6, 60
MARGIN = 4
ALPHA_THRESHOLD = 16  # transparent canvas: a pixel with alpha above this is ink
WHITE_THRESHOLD = 235  # opaque canvas: a pixel darker than this is ink
MAX_TYPED_CHARS = 120

_BAD = "That signature image could not be used. Please draw it again, or type your name instead."


def _invalid(why: str = _BAD) -> EsignError:
    return EsignError(SIGNATURE_INVALID, why)


def _header_size(data: bytes) -> tuple[int, int]:
    """Width and height from the PNG header, read before any pixel is decoded."""
    if data[:8] != PNG_MAGIC or len(data) < 24 or data[12:16] != b"IHDR":
        raise _invalid("The signature must be a PNG image.")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def normalise_png(data: bytes, *, max_bytes: int) -> bytes:
    """Validate a drawn signature and return it cropped to its ink, as a clean metadata-free PNG.

    Rejects (``signature_invalid``) anything that is not a PNG, is over ``max_bytes`` or 2400x1200 pixels,
    fails to decode, or has less ink than a real signature (a dot, an empty canvas). The same input always
    gives the same bytes.
    """
    from PIL import Image

    if len(data) > max_bytes:
        raise _invalid("That signature image is too large.")
    width, height = _header_size(data)
    if not (0 < width <= MAX_WIDTH and 0 < height <= MAX_HEIGHT):
        raise _invalid("That signature image is too large.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as opened:
                if opened.format != "PNG" or opened.size != (width, height):
                    raise _invalid()
                opened.load()
                rgba = opened.convert("RGBA")
    except EsignError:
        raise
    except Exception as exc:  # Pillow raises many unrelated types on damaged or hostile input
        raise _invalid() from exc

    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 255:
        mask = alpha.point(lambda v: 255 if v > ALPHA_THRESHOLD else 0)
    else:
        mask = rgba.convert("L").point(lambda v: 255 if v < WHITE_THRESHOLD else 0)
    box = mask.getbbox()
    if box is None:
        raise _invalid("The signature is empty. Please draw your signature.")
    left, top, right, bottom = box
    if (right - left) < MIN_INK_WIDTH or (bottom - top) < MIN_INK_HEIGHT or mask.histogram()[255] < MIN_INK_PIXELS:
        raise _invalid("The signature is too small. Please draw your full signature.")
    crop = (max(0, left - MARGIN), max(0, top - MARGIN), min(width, right + MARGIN), min(height, bottom + MARGIN))
    cropped = rgba.crop(crop)
    clean = Image.frombytes("RGBA", cropped.size, cropped.tobytes())  # a fresh image carries no metadata
    out = io.BytesIO()
    clean.save(out, format="PNG", compress_level=9, optimize=False)
    result = out.getvalue()
    if len(result) > max_bytes:
        raise _invalid("That signature image is too large.")
    return result


def typed_renderable(name: str, charset: str = "latin-1") -> bool:
    """Whether a typed name can be drawn with the standard PDF fonts (``latin-1``) or at all (``any``)."""
    if charset not in ("latin-1", "any"):
        raise ValueError(f"unknown typed_charset {charset!r}")
    if not name or not all(ch.isprintable() for ch in name):
        return False
    if charset == "any":
        return True
    try:
        name.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def check_drawn_name(name: str) -> str:
    """The optional name that goes with a drawn signature: only its length and printable characters are checked.

    The charset policy does not apply: the name is printed on the certificate, never drawn as the signature.
    """
    name = name.strip()
    if len(name) > MAX_TYPED_CHARS:
        raise _invalid("That name is too long. Please shorten it, or leave it out.")
    if not all(ch.isprintable() for ch in name):
        raise EsignError(NAME_NOT_RENDERABLE, "That name has characters that cannot be used. Please retype it.")
    return name


def check_typed(name: str, policy: Policy) -> str:
    """The stripped typed name when it may be used, else the ``EsignError`` to show the signer."""
    name = name.strip()
    if len(name) > MAX_TYPED_CHARS:
        raise _invalid("That name is too long. Please shorten it, or draw your signature.")
    if not typed_renderable(name, policy.typed_charset):
        raise EsignError(
            NAME_NOT_RENDERABLE,
            "Some letters in that name cannot be printed in a typed signature. Please draw your signature instead.",
        )
    return name
