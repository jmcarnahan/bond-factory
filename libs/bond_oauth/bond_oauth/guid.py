"""Shapes of tenant ids, device hashes and attempt ids."""

import re

GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}")  # a sha256 hex digest
ATTEMPT = re.compile(r"[A-Za-z0-9_-]{1,64}")
