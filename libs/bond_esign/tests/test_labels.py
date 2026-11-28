from dataclasses import fields
from datetime import date, datetime

from bond_esign.labels import CertificateLabels

EVENT_KINDS = ["created", "token_issued", "viewed", "code_sent", "code_verified", "code_failed", "consent_given", "signed", "declined", "voided", "expired", "document_built", "completed", "copy_delivered", "downloaded", "link_sent", "reminder_sent"]


def test_english_defaults_and_date():
    en = CertificateLabels()
    assert en.title == "Signature certificate"
    assert en.format_date(date(2026, 11, 27)) == "Nov 27, 2026"
    assert en.stamp_caption.format(name="A", date="d", ref="r") == "Signed electronically by A, d, ref r"
    assert en.page_of.format(n=1, m=2) == "Certificate page 1 of 2"


def test_format_datetime():
    assert CertificateLabels().format_datetime(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02 03:04:05 UTC"
    assert CertificateLabels().format_datetime(datetime(2026, 1, 2, 3, 4, 5), "PST").endswith(" PST")


def test_every_event_kind_has_a_label_in_both_languages():
    for labels in (CertificateLabels(), CertificateLabels.spanish()):
        known = dict(labels.event_kinds)
        assert all(kind in known for kind in EVENT_KINDS)
        assert labels.event_label("brand_new_kind") == "brand_new_kind"


def test_spanish_translates_every_string_field():
    en, es = CertificateLabels(), CertificateLabels.spanish()
    same = {f.name for f in fields(en) if getattr(en, f.name) == getattr(es, f.name)}
    assert same == {"col_seq", "zone_label"}  # symbols that read the same in both languages
    assert es.format_date(date(2026, 11, 27)) == "27 nov 2026"
    assert "{name}" in es.stamp_caption and "{head}" in es.verify_text and "{n}" in es.page_of


def test_methods_and_statuses():
    en = CertificateLabels()
    assert en.method_label("in_person") == "In person" and en.method_label(None) == ""
    assert en.status_label("declined") == "Declined" and en.status_label("odd") == "odd"
