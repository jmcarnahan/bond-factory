import hashlib

import pytest

from bond_esign import Consent, default_consent


def test_english_text_says_the_things_it_must():
    c = default_consent(company_name="Example Roofing", paper_contact="help@example.com")
    assert isinstance(c, Consent) and c.version == "bond-esign-consent/1" and c.language == "en"
    low = c.text.lower()
    for phrase in ("electronically", "paper copy", "no charge", "help@example.com", "decline", "pdf",
                   "same effect as signing on paper", "signed copy", "example roofing"):  # fmt: skip
        assert phrase in low, phrase
    assert "{" not in c.text


def test_spanish_text_exists_and_differs():
    en = default_consent(company_name="Ejemplo SA", paper_contact="ayuda@example.com")
    es = default_consent(company_name="Ejemplo SA", paper_contact="ayuda@example.com", language="es")
    assert es.language == "es" and es.version == en.version and es.text != en.text
    for phrase in ("electrónic", "copia en papel", "sin ningún costo", "ayuda@example.com", "pdf", "copia firmada"):
        assert phrase in es.text.lower(), phrase


def test_unknown_language_is_a_value_error():
    with pytest.raises(ValueError):
        default_consent(company_name="X", paper_contact="y", language="fr")


def test_the_text_is_stable_so_its_hash_can_be_pinned():
    c = default_consent(company_name="Example Roofing", paper_contact="help@example.com")
    assert hashlib.sha256(c.text.encode()).hexdigest() == hashlib.sha256(
        default_consent(company_name="Example Roofing", paper_contact="help@example.com").text.encode()).hexdigest()  # fmt: skip


def test_braces_in_a_company_name_are_left_alone():
    c = default_consent(company_name="{Odd} Roofing", paper_contact="a@example.com")
    assert "{Odd} Roofing" in c.text
