"""Real-site test configuration, kept outside git. See tests/sites.example.json for the schema."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SITES_PATH = ROOT / "local" / "sites.json"
LOCAL_DATA = ROOT / "local" / "test-data"
PLACEHOLDER = {"line1": "100 Example Ave", "city": "Sampletown", "state": "CA", "zip": "90000",
               "formatted": "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"}


def load_site(name: str = "site1") -> dict | None:
    """The named site from local/sites.json, or None when the file or the key is missing."""
    try:
        return json.loads(SITES_PATH.read_text()).get(name)
    except (OSError, ValueError):
        return None


def local_data_path(filename: str) -> Path | None:
    """Path of a file under local/test-data, or None when it is absent."""
    path = LOCAL_DATA / filename
    return path if path.is_file() else None
