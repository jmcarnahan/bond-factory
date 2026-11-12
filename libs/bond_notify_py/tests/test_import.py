import bond_notify_py
from bond_notify_py import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_every_export_resolves():
    for name in bond_notify_py.__all__:
        assert hasattr(bond_notify_py, name), name
