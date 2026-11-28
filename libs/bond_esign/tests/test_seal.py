from datetime import UTC, datetime, timedelta

import pytest
from pdf_samples import Text, make_pdf

pytest.importorskip("pyhanko")
from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyhanko.sign.timestamps import DummyTimeStamper

from bond_esign.certs import make_self_signed_pkcs12
from bond_esign.errors import SEAL_FAILED, EsignError
from bond_esign.seal import Sealer, verify_seal

PASS = b"test-passphrase"


@pytest.fixture(scope="module")
def p12():
    return make_self_signed_pkcs12("Sample Sealer", "Sample Org", years=1, passphrase=PASS)


@pytest.fixture(scope="module")
def tsa_factory():
    """A throwaway time-stamp authority built at run time; no network."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Throwaway TSA")])
    now = datetime.now(UTC) - timedelta(days=1)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
        .sign(key, hashes.SHA256())
    )  # fmt: skip
    a_cert = asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    a_key = asn1_keys.PrivateKeyInfo.load(
        key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return lambda url: DummyTimeStamper(a_cert, a_key)


@pytest.fixture(scope="module")
def pdf():
    return make_pdf([[Text(72, 700, "Sealed text")]])


def _failing(url):
    raise OSError("tsa down")


def test_unsealed_pdf_has_no_seal(pdf):
    assert verify_seal(pdf) == verify_seal(pdf) and verify_seal(pdf).present is False


def test_seal_and_verify(p12, pdf):
    result = Sealer.from_pkcs12(p12, PASS).seal(pdf)
    assert result.timestamped is False and result.pdf.startswith(b"%PDF")
    check = verify_seal(result.pdf)
    assert (check.present, check.intact, check.covers_whole_file, check.timestamped) == (True, True, True, False)
    assert check.subject == "Sample Sealer"
    assert check.signed_at is not None and check.signed_at.tzinfo is None
    assert abs(check.signed_at - datetime.now(UTC).replace(tzinfo=None)) < timedelta(minutes=5)


def test_timestamped_seal(p12, pdf, tsa_factory):
    sealer = Sealer.from_pkcs12(p12, PASS, timestamp_urls=["https://tsa.example.com"], timestamper_factory=tsa_factory)
    result = sealer.seal(pdf)
    assert result.timestamped is True and result.timestamp_url == "https://tsa.example.com"
    check = verify_seal(result.pdf)
    assert check.intact and check.timestamped and check.covers_whole_file


def test_second_server_used_when_first_fails(p12, pdf, tsa_factory):
    def factory(url):
        return _failing(url) if "bad" in url else tsa_factory(url)

    sealer = Sealer.from_pkcs12(
        p12, PASS, timestamp_urls=["https://bad.example.com", "https://good.example.com"], timestamper_factory=factory
    )
    result = sealer.seal(pdf)
    assert result.timestamped and result.timestamp_url == "https://good.example.com"


def test_all_timestampers_failing_still_seals(p12, pdf):
    sealer = Sealer.from_pkcs12(
        p12, PASS, timestamp_urls=["https://a.example.com", "https://b.example.com"], timestamper_factory=_failing
    )
    result = sealer.seal(pdf)
    assert result.timestamped is False and result.timestamp_url is None
    assert verify_seal(result.pdf).intact


def test_require_timestamp_fails(p12, pdf):
    sealer = Sealer.from_pkcs12(
        p12, PASS, timestamp_urls=["https://a.example.com"], require_timestamp=True, timestamper_factory=_failing
    )
    with pytest.raises(EsignError) as err:
        sealer.seal(pdf)
    assert err.value.code == SEAL_FAILED


def test_wrong_passphrase(p12):
    with pytest.raises(EsignError) as err:
        Sealer.from_pkcs12(p12, b"wrong")
    assert err.value.code == SEAL_FAILED


def test_flipped_byte_in_signed_range(p12, pdf):
    sealed = Sealer.from_pkcs12(p12, PASS).seal(pdf).pdf
    at = sealed.index(b"Sealed text") if b"Sealed text" in sealed else sealed.index(b"/Type /Page")
    tampered = bytearray(sealed)
    tampered[at] ^= 0x01
    check = verify_seal(bytes(tampered))
    assert check.present is True and check.intact is False


def test_appended_bytes_break_whole_file_coverage(p12, pdf):
    sealed = Sealer.from_pkcs12(p12, PASS).seal(pdf).pdf
    check = verify_seal(sealed + b"\n% appended after the seal\n")
    assert check.present is True and check.covers_whole_file is False


def test_garbage_is_not_sealed():
    assert verify_seal(b"not a pdf").present is False


def test_fingerprint_and_trusted_follow_the_sealing_certificate(p12, pdf):
    mine = Sealer.from_pkcs12(p12, PASS)
    other = Sealer.from_pkcs12(make_self_signed_pkcs12("Other Sealer", "Other Org", years=1, passphrase=PASS), PASS)
    assert len(mine.fingerprint) == 64 and mine.fingerprint != other.fingerprint
    sealed = mine.seal(pdf).pdf
    check = verify_seal(sealed)
    assert (check.fingerprint, check.trusted) == (mine.fingerprint, None)
    own = verify_seal(sealed, expected_fingerprint=mine.fingerprint.upper())  # case-insensitive
    assert (own.intact, own.trusted) == (True, True)
    foreign = verify_seal(other.seal(pdf).pdf, expected_fingerprint=mine.fingerprint)
    assert (foreign.intact, foreign.covers_whole_file, foreign.trusted) == (True, True, False)
    assert foreign.fingerprint == other.fingerprint
