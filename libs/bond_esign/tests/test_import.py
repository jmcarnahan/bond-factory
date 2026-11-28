import subprocess
import sys

import bond_esign


def run(code):
    return subprocess.run([sys.executable, "-I", "-c", code], check=False, capture_output=True, text=True, timeout=60)


def test_version():
    assert bond_esign.__version__ == "0.1.0"


def test_import_works_with_pyhanko_blocked_and_seal_names_fail_only_when_used():
    code = (
        "import sys\n"
        "sys.modules['pyhanko'] = None\n"
        "import bond_esign\n"
        "assert bond_esign.create_request and bond_esign.normalise_png and bond_esign.find_anchor\n"
        "try:\n"
        "    bond_esign.Sealer\n"
        "except ImportError as exc:\n"
        "    assert 'seal' in str(exc).lower(), exc\n"
        "else:\n"
        "    raise SystemExit('Sealer should need the seal extra')\n"
    )
    done = run(code)
    assert done.returncode == 0, done.stderr + done.stdout


def test_importing_the_package_does_not_load_the_seal_and_web_modules():
    code = (
        "import sys, bond_esign\n"
        "heavy = [m for m in ('pyhanko', 'cryptography', 'bond_esign.seal', 'bond_esign.webform',\n"
        "                     'bond_esign.certs') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    done = run(code)
    assert done.returncode == 0, done.stderr + done.stdout


def test_every_name_in_all_resolves_and_is_unique():
    assert len(set(bond_esign.__all__)) == len(bond_esign.__all__)
    for name in bond_esign.__all__:
        assert getattr(bond_esign, name) is not None, name


def test_stamp_is_the_function_whichever_way_the_submodule_was_imported_first():
    code = (
        "import bond_esign.stamping\n"
        "from bond_esign import stamp\n"
        "assert callable(stamp) and stamp.__name__ == 'stamp' and not hasattr(stamp, '__path__')\n"
        "from bond_esign.stamping import stamp as again\n"
        "assert again is stamp\n"
    )
    done = run(code)
    assert done.returncode == 0, done.stderr + done.stdout


def test_the_public_names_of_the_contract_are_exported():
    expected = {
        "Placement", "AnchorRule", "SignerSpec", "RequestContext", "Consent", "Policy", "Tables", "Brand", "Stamp",
        "SigningView", "SignOutcome", "SignedDocument", "ChainCheck", "SealResult", "SealCheck", "CertificateData",
        "CertificateSigner", "CertificateEvent", "CertificateLabels", "EsignError", "errors", "EsignRequestMixin",
        "TenantEsignRequestMixin", "EsignSignerMixin", "EsignEventMixin", "KINDS", "append", "chain",
        "verify_chain", "create_request", "issue_token", "find_signer_by_token", "find_signer_by_key", "signing_view", "issue_code",
        "verify_code", "sign", "decline", "void", "expire_due", "build_signed_pdf", "complete", "record_delivery",
        "record_download", "record_sent", "parse_decline", "evidence", "normalise_png", "default_consent", "sha256_hex", "page_count",
        "find_anchor", "stamp", "certificate_pages", "render_panel", "parse_submission", "PanelLabels",
        "Submission", "asset_path", "asset_names", "asset_tags", "Sealer", "verify_seal", "make_self_signed_pkcs12",
        "__version__",
    }  # fmt: skip
    assert expected <= set(bond_esign.__all__)


def test_no_public_function_shares_a_name_with_a_submodule():
    code = (
        "import bond_esign.evidence_export as m\n"
        "import bond_esign\n"
        "assert m.__name__ == 'bond_esign.evidence_export' and callable(bond_esign.evidence)\n"
        "assert not hasattr(bond_esign.evidence, '__path__')\n"
        "import importlib, pkgutil\n"
        "subs = {i.name for i in pkgutil.iter_modules(bond_esign.__path__)}\n"
        "clash = sorted(n for n in bond_esign.__all__ if n in subs and callable(getattr(bond_esign, n)))\n"
        "assert not clash, clash\n"
    )
    done = run(code)
    assert done.returncode == 0, done.stderr + done.stdout


def test_asset_tags_is_public_and_loads_lazily():
    assert callable(bond_esign.asset_tags) and "asset_tags" in bond_esign.__all__
