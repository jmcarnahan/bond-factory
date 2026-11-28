"""Make a self-signed PKCS#12 for sealing: ``python -m bond_esign.certs --cn NAME --org ORG --out seal.p12``.

A self-signed seal shows "validity unknown" in Acrobat but still detects later changes. The key is written
only to the path asked for; the base64 of the same bytes goes to stdout for a secret store.
"""

import argparse
import base64
import getpass
import os
import sys
from datetime import UTC, datetime, timedelta

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID
except ImportError as exc:  # pragma: no cover
    raise ImportError("bond_esign.certs needs the 'seal' extra: install bond_esign[seal]") from exc


def make_self_signed_pkcs12(common_name: str, organization: str, *, years: int = 10, passphrase: bytes) -> bytes:
    """RSA 3072, SHA-256, key usage digitalSignature + nonRepudiation; PKCS#12 encrypted with ``passphrase``."""
    if not passphrase:
        raise ValueError("a passphrase is required")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, common_name), x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization)]
    )
    # The ONE place in this library that reads the wall clock: this is a command-line helper, not signing.
    start = datetime.now(UTC) - timedelta(minutes=5)  # a little back-dated against clock skew
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + timedelta(days=365 * years))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )  # fmt: skip
    return pkcs12.serialize_key_and_certificates(
        common_name.encode(), key, cert, None, serialization.BestAvailableEncryption(passphrase)
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bond_esign.certs", description=__doc__.split("\n")[0])
    ap.add_argument("--cn", required=True, help="certificate common name")
    ap.add_argument("--org", required=True, help="organization name")
    ap.add_argument("--out", required=True, help="path for the .p12 file")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--passphrase", help="omit to be prompted")
    args = ap.parse_args(argv)
    phrase = args.passphrase or getpass.getpass("PKCS#12 passphrase: ")
    data = make_self_signed_pkcs12(args.cn, args.org, years=args.years, passphrase=phrase.encode())
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(args.out, 0o600)  # an existing file keeps its old mode through O_CREAT: set it again
    print(base64.b64encode(data).decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
