import io

import pytest
from PIL import Image

from bond_storage import images
from bond_storage.images import ImageTooLarge, UnreadableImage


def raw(fmt, size=(40, 20), **save):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, fmt, **save)
    return out.getvalue()


@pytest.mark.parametrize("fmt,kind", [("PNG", "png"), ("JPEG", "jpeg"), ("GIF", "gif"), ("WEBP", "webp")])
def test_sniff_each_format(fmt, kind):
    assert images.sniff(raw(fmt)) == kind


def test_sniff_heic_and_unknown():
    assert images.sniff(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00") == "heic"
    assert images.sniff(b"\x00\x00\x00\x18ftypmif1") == "heic"
    assert images.sniff(b"<html>") is None and images.sniff(b"") is None and images.sniff(b"%PDF-1.4") is None


def test_bomb_guard():
    img = Image.new("RGB", (100, 100))
    images.guard_bomb(img, 10_000)
    with pytest.raises(ImageTooLarge):
        images.guard_bomb(img, 9_999)
    with pytest.raises(ImageTooLarge):
        images.image_from_bytes(raw("PNG", (100, 100)), max_pixels=5_000)
    assert images.image_from_bytes(raw("PNG", (100, 100)), max_pixels=10_000).size == (100, 100)


def _png_header_declaring(width, height):
    import struct
    import zlib

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")


def test_declared_size_is_refused_from_the_header_without_decoding():
    data = _png_header_declaring(50_000, 50_000)  # 2.5 billion pixels in a body of about 60 bytes
    assert len(data) < 100
    for limit in (40_000_000, 10**10):  # past Pillow's own open-time limit, and a caller limit above it
        with pytest.raises(ImageTooLarge):
            images.image_from_bytes(data, max_pixels=limit)
    # 81 million pixels is under Pillow's own limit, so only our guard can refuse it. Its body is not a valid
    # picture, so if decoding ran first this would raise UnreadableImage instead.
    window = _png_header_declaring(9_000, 9_000)
    with Image.open(io.BytesIO(window)) as lazy:
        assert lazy.size == (9_000, 9_000)
        with pytest.raises(ImageTooLarge):
            images.guard_bomb(lazy, 40_000_000)
    with pytest.raises(ImageTooLarge):
        images.image_from_bytes(window, max_pixels=40_000_000)


def test_unreadable_inputs():
    for data in (b"", b"not a picture", b"\x89PNG\r\n\x1a\ntruncated", raw("JPEG")[:30]):
        with pytest.raises(UnreadableImage):
            images.image_from_bytes(data)
    with pytest.raises(UnreadableImage):
        images.image_from_bytes(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00")  # HEIC without pillow-heif


def jpeg_with_metadata():
    exif = Image.Exif()
    exif[274] = 6  # orientation: rotate 90 clockwise to display
    exif[271] = "MakerName"
    return raw("JPEG", (40, 20), exif=exif.tobytes(), icc_profile=b"fake-icc-profile")


def test_strip_metadata_applies_orientation_first_and_removes_everything():
    original = images.image_from_bytes(jpeg_with_metadata())
    assert original.getexif().get(274) == 6 and original.info.get("icc_profile")
    clean = images.strip_metadata(original)
    assert clean.size == (20, 40)  # turned upright before the tag was dropped
    assert clean.info == {} and len(clean.getexif()) == 0
    again = images.image_from_bytes(images.encode(clean, "JPEG"))
    assert len(again.getexif()) == 0 and "icc_profile" not in again.info and again.size == (20, 40)


def test_strip_metadata_png_text_and_alpha():
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Author", "someone")
    out = io.BytesIO()
    Image.new("RGBA", (8, 8), (1, 2, 3, 128)).save(out, "PNG", pnginfo=info)
    source = images.image_from_bytes(out.getvalue())
    assert source.text.get("Author") == "someone"
    clean = images.strip_metadata(source)
    assert clean.mode == "RGBA" and clean.info == {} and clean.getpixel((0, 0)) == (1, 2, 3, 128)
    assert not getattr(images.image_from_bytes(images.encode(clean, "PNG")), "text", {})


def test_thumbnail_keeps_aspect_never_enlarges_and_copies():
    big = Image.new("RGB", (400, 200))
    thumb = images.thumbnail(big, 100)
    assert thumb.size == (100, 50) and big.size == (400, 200)
    assert images.thumbnail(Image.new("RGB", (30, 20)), 100).size == (30, 20)
    assert images.thumbnail(Image.new("RGB", (20, 400)), 100).size == (5, 100)
