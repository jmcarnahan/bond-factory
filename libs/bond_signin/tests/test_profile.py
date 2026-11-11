"""Display-name cleaning and ``profile_of``."""

from types import SimpleNamespace

import pytest

from bond_signin import IdentityProfile, profile_of
from bond_signin.profile import NAME_MAX, normalize_name


@pytest.mark.parametrize("raw, clean", [
    ("  Dora  ", "Dora"),
    ("A\nB", "A B"),
    ("A\t\tB", "A B"),
    ("A   B \r\n C", "A B C"),
    ("A\x00B", "AB"),
    ("A\x1bB\x7f", "AB"),
    ("A\u200bB", "AB"),
    ("A \u200b B", "A B"),
    ("A\u00adB", "AB"),
    ("A\u2060B", "AB"),
    ("A\u061cB", "AB"),
    ("A\u202aB\u202dC\u2067D\u2068E", "ABCDE"),
    ("A\u2028B\u2029C", "A B C"),
    ("Dora\U000e0041", "Dora"),
    ("A\u202eB", "AB"),
    ("A\u2066B\u2069", "AB"),
    ("\ufeffDora", "Dora"),
    ("A\ue000B", "AB"),
    ("A\u0378B", "A\u0378B"),  # unassigned code points are kept: they may be newer letters
    ("A\u200cB", "A\u200cB"),
    ("A\u200dB", "A\u200dB"),
    ("A\u200eB\u200fC", "A\u200eB\u200fC"),
    ("Zoë Ünal", "Zoë Ünal"),
    ("محمد", "محمد"),
    ("李雷", "李雷"),
])
def test_normalize_name(raw, clean):
    assert normalize_name(raw) == clean


@pytest.mark.parametrize("raw", [123, ["x"], None, b"Dora", "", "   ", "\n\t", "\u200b\x00", "\u202e",
                                 "\u200c", "\u200d", "\u200f", "\u0301\u0301", "\u00ad", "\U000e0041\U000e0042"])
def test_unusable_values_give_none(raw):
    assert normalize_name(raw) is None


def test_long_names_are_cut_to_the_cap():
    assert normalize_name("a" * 300) == "a" * NAME_MAX == normalize_name("a" * NAME_MAX + "b")


def test_literal_cap_is_256():
    assert len(normalize_name("a" * 1000)) == 256


def test_cut_does_not_end_on_a_dangling_joiner():
    cut = normalize_name("a" * 254 + "\U0001F468\u200d\U0001F469")
    assert cut.endswith("\U0001F468") and not cut.endswith("\u200d")


def test_cut_leaves_no_trailing_space():
    cut = normalize_name("a" * 255 + " " + "b")
    assert cut == "a" * 255 and not cut.endswith(" ")


def test_profile_of_reads_the_identity_name():
    assert profile_of(SimpleNamespace(name="  Dora  ")) == IdentityProfile("Dora")


@pytest.mark.parametrize("identity", [SimpleNamespace(), SimpleNamespace(name=None), SimpleNamespace(name=" ")])
def test_profile_of_is_none_without_a_usable_name(identity):
    assert profile_of(identity) is None
