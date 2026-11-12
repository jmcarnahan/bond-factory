import bond_push_py
from bond_push_py import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_every_export_resolves():
    for name in bond_push_py.__all__:
        assert hasattr(bond_push_py, name), name
