import io

import pytest
from conftest import blank_png, expect, sig_png
from PIL import Image

from bond_esign import Policy, normalise_png, typed_renderable
from bond_esign.signature_image import check_typed

BIG = 1_000_000


def decode(data):
    return Image.open(io.BytesIO(data)).convert("RGBA")


def png_of(img):
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_crops_to_the_ink_with_a_four_pixel_margin_and_keeps_transparency():
    out = normalise_png(sig_png(300, 120, pad=40), max_bytes=BIG)
    img = decode(out)
    ink_w = 300 - 80 + 4  # line width 4 widens the box by about 2 px each side
    assert abs(img.width - (ink_w + 8)) <= 6 and img.height < 120
    assert img.getchannel("A").getextrema()[0] == 0  # corners stay transparent
    assert img.getchannel("A").getbbox()[0] <= 6  # ink starts at about the margin


def test_the_same_input_gives_the_same_bytes_and_metadata_is_dropped():
    from PIL.PngImagePlugin import PngInfo

    base = Image.open(io.BytesIO(sig_png()))
    info = PngInfo()
    info.add_text("Comment", "secret location data")
    out = io.BytesIO()
    base.save(out, format="PNG", pnginfo=info)
    first = normalise_png(out.getvalue(), max_bytes=BIG)
    assert first == normalise_png(out.getvalue(), max_bytes=BIG) == normalise_png(sig_png(), max_bytes=BIG)
    assert b"secret" not in first and b"tEXt" not in first and b"iCCP" not in first
    assert Image.open(io.BytesIO(first)).info == {}


def test_an_opaque_white_canvas_is_cropped_by_its_non_white_pixels_and_stays_opaque():
    img = decode(normalise_png(sig_png(transparent=False), max_bytes=BIG))
    assert img.getchannel("A").getextrema() == (255, 255) and img.width < 300


@pytest.mark.parametrize(
    "data",
    [b"", b"hello", b"\x89PNG\r\n\x1a\n", b"\x89PNG\r\n\x1a\n" + b"\0" * 30, sig_png()[:80], b"GIF89a" + sig_png()],
)
def test_non_png_truncated_and_header_only_input_is_rejected(data):
    with expect("signature_invalid"):
        normalise_png(data, max_bytes=BIG)


def test_a_jpeg_renamed_png_is_rejected():
    out = io.BytesIO()
    Image.new("RGB", (100, 50), "white").save(out, format="JPEG")
    with expect("signature_invalid"):
        normalise_png(out.getvalue(), max_bytes=BIG)


def test_over_max_bytes_is_rejected_before_decoding():
    data = sig_png()
    with expect("signature_invalid"):
        normalise_png(data, max_bytes=len(data) - 1)
    assert normalise_png(data, max_bytes=len(data) + 5000)


def test_over_2400_by_1200_pixels_is_rejected_from_the_header():
    with expect("signature_invalid"):
        normalise_png(png_of(Image.new("RGBA", (2401, 100))), max_bytes=BIG)
    with expect("signature_invalid"):
        normalise_png(png_of(Image.new("RGBA", (100, 1201))), max_bytes=BIG)


def test_a_header_that_claims_a_huge_image_never_reaches_the_decoder():
    data = bytearray(sig_png())
    data[16:24] = (60000).to_bytes(4, "big") + (60000).to_bytes(4, "big")  # 3.6 gigapixels in the IHDR
    with expect("signature_invalid"):
        normalise_png(bytes(data), max_bytes=BIG)


def test_a_header_that_lies_about_a_small_size_is_rejected():
    data = bytearray(sig_png())
    data[16:24] = (100).to_bytes(4, "big") + (50).to_bytes(4, "big")
    with expect("signature_invalid"):
        normalise_png(bytes(data), max_bytes=BIG)


def test_pillows_bomb_guard_is_honoured_and_the_global_limit_is_left_alone(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 20_000)  # pretend an operator tightened Pillow's limit
    for size in ((300, 120), (300, 400)):  # over the limit (warning) and over twice the limit (error)
        with expect("signature_invalid"):
            normalise_png(sig_png(*size), max_bytes=BIG)
    assert Image.MAX_IMAGE_PIXELS == 20_000


def test_a_solid_image_at_the_size_limit_is_accepted_and_small():
    out = normalise_png(png_of(Image.new("RGBA", (2400, 1200), (0, 0, 0, 255))), max_bytes=BIG)
    assert len(out) < 20_000 and decode(out).size == (2400, 1200)


def test_empty_dot_and_tiny_marks_are_rejected():
    with expect("signature_invalid"):
        normalise_png(blank_png(), max_bytes=BIG)
    dot = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    dot.paste((0, 0, 0, 255), (100, 40, 104, 44))
    with expect("signature_invalid"):
        normalise_png(png_of(dot), max_bytes=BIG)
    thin = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    thin.paste((0, 0, 0, 255), (20, 40, 180, 42))  # wide enough, but only 2 px tall
    with expect("signature_invalid"):
        normalise_png(png_of(thin), max_bytes=BIG)
    few = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    for x in range(0, 40, 2):  # 20 pixels spread over a 40x20 area: right size, too little ink
        few.putpixel((20 + x, 20 + (x % 20)), (0, 0, 0, 255))
    with expect("signature_invalid"):
        normalise_png(png_of(few), max_bytes=BIG)


def test_faint_transparent_noise_is_not_ink():
    faint = Image.new("RGBA", (200, 80), (0, 0, 0, 10))
    with expect("signature_invalid"):
        normalise_png(png_of(faint), max_bytes=BIG)


def test_the_ink_just_big_enough_passes():
    img = Image.new("RGBA", (100, 40), (0, 0, 0, 0))
    img.paste((0, 0, 0, 255), (10, 10, 22, 16))  # 12x6 solid block = 72 ink pixels
    assert normalise_png(png_of(img), max_bytes=BIG)


def test_typed_renderable_latin1_and_any():
    for ok in ("Pat Example", "José Núñez", "Zoë Ångström", "O'Brien-Smith Jr.", "Price €5"):
        assert typed_renderable(ok, "latin-1") and typed_renderable(ok, "any")
    for bad in ("李小龍", "Pat 😀", "Anna Łukasz"):
        assert not typed_renderable(bad, "latin-1") and typed_renderable(bad, "any")
    for never in ("", "Pat\nExample", "Pat\x00", "tab\there", "bell\x07"):
        assert not typed_renderable(never, "latin-1") and not typed_renderable(never, "any")
    with pytest.raises(ValueError):
        typed_renderable("x", "utf-16")


def test_check_typed_strips_caps_the_length_and_explains_the_remedy():
    assert check_typed("  Pat  ", Policy()) == "Pat"
    assert check_typed("a" * 120, Policy()) == "a" * 120
    with expect("signature_invalid"):
        check_typed("a" * 121, Policy())
    with pytest.raises(Exception) as info:
        check_typed("李", Policy())
    assert info.value.code == "name_not_renderable" and "draw" in info.value.message.lower()


def _block(w, h, *, hollow=0):
    """A 100x60 transparent canvas with an opaque w x h block; ``hollow`` interior pixels are cleared again."""
    img = Image.new("RGBA", (100, 60), (0, 0, 0, 0))
    img.paste((0, 0, 0, 255), (10, 10, 10 + w, 10 + h))
    cleared = 0
    for y in range(12, 10 + h - 1):
        for x in range(12, 10 + w - 1):
            if cleared < hollow:
                img.putpixel((x, y), (0, 0, 0, 0))
                cleared += 1
    return png_of(img)


def test_the_ink_box_minimum_is_12_wide_and_6_tall():
    for w, h in ((11, 20), (20, 5)):
        with expect("signature_invalid"):
            normalise_png(_block(w, h), max_bytes=BIG)
    assert normalise_png(_block(12, 6), max_bytes=BIG)
    assert normalise_png(_block(12, 20), max_bytes=BIG) and normalise_png(_block(40, 6), max_bytes=BIG)


def test_the_ink_pixel_minimum_is_60():
    assert normalise_png(_block(12, 6, hollow=12), max_bytes=BIG)  # 72 - 12 = 60 pixels: enough
    with expect("signature_invalid"):
        normalise_png(_block(12, 6, hollow=13), max_bytes=BIG)  # 59 pixels: not enough


def test_the_size_limit_is_exactly_2400_by_1200():
    for size in ((2401, 10), (10, 1201)):
        with expect("signature_invalid"):
            normalise_png(png_of(Image.new("RGBA", size, (0, 0, 0, 255))), max_bytes=BIG)
    assert normalise_png(png_of(Image.new("RGBA", (2400, 1200), (0, 0, 0, 255))), max_bytes=BIG)
