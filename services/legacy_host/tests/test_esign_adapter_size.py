"""The adopter's adapter stays small: if it needs more than 150 lines, the lib's seam is wrong."""

from pathlib import Path

import legacy_host.esign_native as native


def test_the_native_adapter_is_under_150_lines():
    assert len(Path(native.__file__).read_text().splitlines()) < 150
