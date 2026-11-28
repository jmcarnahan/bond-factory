import base64
import subprocess
import sys

import pytest

pytest.importorskip("cryptography")
from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from bond_esign.certs import make_self_signed_pkcs12


def test_pkcs12_contents():
    data = make_self_signed_pkcs12("Sample Sealer", "Sample Org", years=2, passphrase=b"pw")
    key, cert, extra = pkcs12.load_key_and_certificates(data, b"pw")
    assert key is not None and cert is not None and extra == []
    assert cert.subject.rfc4514_string().startswith("O=Sample Org") or "CN=Sample Sealer" in cert.subject.rfc4514_string()
    usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.digital_signature and usage.content_commitment
    assert key.key_size >= 2048
    assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days >= 2 * 365
    with pytest.raises(ValueError):
        pkcs12.load_key_and_certificates(data, b"other")


def test_empty_passphrase_refused():
    with pytest.raises(ValueError):
        make_self_signed_pkcs12("a", "b", passphrase=b"")


def test_cli_writes_only_the_asked_path(tmp_path):
    out = tmp_path / "seal.p12"
    run = subprocess.run(
        [sys.executable, "-m", "bond_esign.certs", "--cn", "Sample Sealer", "--org", "Sample Org", "--out", str(out),
         "--passphrase", "pw"],
        capture_output=True, text=True, check=True, cwd=tmp_path,
    )  # fmt: skip
    assert base64.b64decode(run.stdout.strip()) == out.read_bytes()
    assert [p.name for p in tmp_path.iterdir()] == ["seal.p12"]
    assert (out.stat().st_mode & 0o077) == 0
