import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from bond_esign.webform import asset_names, asset_path

LIB = Path(__file__).resolve().parent.parent
UV = "/opt/homebrew/bin/uv"


def text(name: str) -> str:
    return asset_path(name).read_text(encoding="utf-8")


def test_assets_exist_and_are_not_empty():
    for name in asset_names():
        assert asset_path(name).stat().st_size > 500


def test_js_clamps_the_canvas_backing_store_to_the_server_limits():
    js = text("bond-esign.js")
    for needle in ("MAX_RATIO = 2;", "MAX_PX_W = 2400;", "MAX_PX_H = 1200;",
                   "Math.min(Math.max(window.devicePixelRatio || 1, 1), MAX_RATIO, MAX_PX_W / w, MAX_PX_H / h)"):  # fmt: skip
        assert needle in js, needle
    assert "canvas.width = Math.max(1, Math.floor(w * dpr))" in js


def test_js_posts_the_drawing_only_when_the_pad_has_ink():
    js = text("bond-esign.js")
    assert 'pad && !pad.isEmpty()) {\n        pngInput.value = pad.toDataURL' in js
    assert "getBoundingClientRect" not in js
    assert "canvas.clientWidth" in js and "canvas.clientHeight" in js


def test_js_is_strictly_clean():
    js = text("bond-esign.js")
    for bad in ("eval(", "new Function", "alert(", "confirm(", "prompt(", "showModal", "innerHTML",
                "http://", "https://", "fetch(", "XMLHttpRequest", "document.write"):  # fmt: skip
        assert bad not in js, bad
    assert not re.search(r"\.on\w+\s*=", js)


def test_vendored_file_loads_nothing_remote():
    js = text("signature_pad.umd.min.js")
    assert "Signature Pad" in js and "MIT" in js[:400]
    urls = set(re.findall(r"https?://[^\"'\s)]+", js))
    # only the licence header link and the SVG namespace strings that never get fetched
    assert urls <= {"https://github.com/szimek/signature_pad", "http://www.w3.org/1999/xlink",
                    "http://www.w3.org/2000/svg"}  # fmt: skip
    assert "importScripts" not in js and "XMLHttpRequest" not in js and "fetch(" not in js
    assert "MIT License" in text("LICENSE-signature_pad")


def test_css_contract():
    css = text("bond-esign.css")
    assert "touch-action: none" in css and css.count("touch-action") == 1
    for prop in ("accent", "border", "text", "surface", "radius"):
        assert f"--bond-esign-{prop}:" in css
    for bad in ("position: fixed", "position: sticky", "z-index", "@import", "url(", "http://", "https://"):
        assert bad not in css, bad
    assert "[hidden]" in css and "display: none !important" in css
    assert "prefers-reduced-motion" in css and ":focus-visible" in css
    for sel in re.findall(r"^([^\s@/}][^{]*)\{", css, flags=re.MULTILINE):
        for one in sel.split(","):
            assert one.strip().startswith(".bond-esign"), one


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_node_check():
    done = subprocess.run(["node", "--check", str(asset_path("bond-esign.js"))], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


def test_wheel_ships_the_web_files(tmp_path):
    uv = shutil.which("uv") or (UV if Path(UV).exists() else None)
    if uv is None:
        pytest.skip("uv is not available to build a wheel")
    done = subprocess.run([uv, "build", "--wheel", "--out-dir", str(tmp_path), str(LIB)],
                          capture_output=True, text=True, timeout=300, check=False)  # fmt: skip
    assert done.returncode == 0, done.stderr[-2000:]
    wheel = next(tmp_path.glob("bond_esign-*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    for name in asset_names():
        assert f"bond_esign/web/{name}" in names
