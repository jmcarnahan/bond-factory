from pathlib import Path

import bond_capture_py
from bond_capture_py import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_every_export_resolves():
    for name in bond_capture_py.__all__:
        assert hasattr(bond_capture_py, name), name


def test_prompt_template_ships_with_the_package():
    text = (Path(bond_capture_py.__file__).parent / "prompt_v1.md").read_text()
    assert "<!-- BEGIN SYSTEM PROMPT -->" in text and "{{today}}" in text
