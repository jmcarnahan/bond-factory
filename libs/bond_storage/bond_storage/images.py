"""Image helpers on Pillow images: sniff, bomb guard, metadata strip, thumbnail.

Nothing here trusts a filename or a client-declared type. HEIC needs the optional ``pillow-heif`` package; without it a HEIC
upload is ``UnreadableImage``.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")


class ImageTooLarge(ValueError):
    """More pixels than allowed (a decompression bomb, or just too big)."""


class UnreadableImage(ValueError):
    """Not a picture this process can read."""


def sniff(data: bytes) -> str | None:
    """``png`` | ``jpeg`` | ``gif`` | ``webp`` | ``heic`` from the leading bytes, else None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
        return "heic"
    return None


def guard_bomb(image: Image.Image, max_pixels: int) -> None:
    """Raise ``ImageTooLarge`` when the image has more than ``max_pixels``. Works on the header size, before any decode."""
    width, height = image.size
    if width * height > max_pixels:
        raise ImageTooLarge(f"{width}x{height} is over {max_pixels} pixels")


def image_from_bytes(data: bytes, *, max_pixels: int = 40_000_000) -> Image.Image:
    """Decode ``data``, refusing a bomb before the pixels are read. Raises ``ImageTooLarge`` or ``UnreadableImage``."""
    if sniff(data) == "heic":
        try:
            import pillow_heif  # type: ignore[import-not-found]

            pillow_heif.register_heif_opener()
        except ImportError as exc:
            raise UnreadableImage("HEIC is not supported here") from exc
    try:
        image = Image.open(io.BytesIO(data))
        guard_bomb(image, max_pixels)
        image.load()
    except Image.DecompressionBombError as exc:
        raise ImageTooLarge("image is too large") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        if isinstance(exc, ImageTooLarge):
            raise
        raise UnreadableImage("not a readable picture") from exc
    return image


def exif_transpose(image: Image.Image) -> Image.Image:
    """The image with its EXIF orientation applied to the pixels."""
    return ImageOps.exif_transpose(image) or image


def strip_metadata(image: Image.Image) -> Image.Image:
    """A copy of the pixels with no metadata at all (EXIF, ICC, XMP, text chunks, ``info``).

    The orientation is applied first, so removing the EXIF tag does not turn a phone photo sideways.
    """
    upright = exif_transpose(image)
    mode = "RGBA" if upright.mode in ("RGBA", "LA") or "transparency" in upright.info else "RGB"
    flat = upright.convert(mode)
    return Image.frombytes(mode, flat.size, flat.tobytes())


def thumbnail(image: Image.Image, max_side: int) -> Image.Image:
    """A copy that fits in ``max_side`` x ``max_side``, aspect kept, never enlarged."""
    thumb = image.copy()
    thumb.thumbnail((max_side, max_side))
    return thumb


def encode(image: Image.Image, fmt: str = "JPEG", *, quality: int = 80) -> bytes:
    """Encode to ``JPEG`` (flattened to RGB) or ``PNG``."""
    out = io.BytesIO()
    if fmt.upper() == "JPEG":
        image.convert("RGB").save(out, "JPEG", quality=quality, optimize=True)
    else:
        image.save(out, fmt.upper(), optimize=True)
    return out.getvalue()
