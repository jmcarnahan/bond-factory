"""Opt-in checks against Apple's real sandbox. Skipped unless BOND_PUSH_NETWORK=1 and every variable below is set.

Nothing here reads a key in a default run: the skip is decided from the environment alone.
"""

import os

import pytest

from bond_push_py.send_test import MADE_UP_TOKEN, VARIABLES, send_alert, verdict

_NEEDED = ["BOND_PUSH_NETWORK", *VARIABLES.values()]
_UNSET = [name for name in _NEEDED if not os.environ.get(name)]
_ON = os.environ.get("BOND_PUSH_NETWORK") == "1" and not _UNSET

pytestmark = pytest.mark.skipif(
    not _ON, reason="live Apple check: set BOND_PUSH_NETWORK=1 and " + ", ".join(VARIABLES.values()))


def _args(**override):
    values = {name: os.environ[var] for name, var in VARIABLES.items()}
    values.update(override)
    return values


def test_sandbox_accepts_an_alert_to_a_real_device():
    result = send_alert(**_args())
    assert result.ok, verdict(result)


def test_sandbox_reports_a_made_up_token_as_dead():
    result = send_alert(**_args(token=MADE_UP_TOKEN))
    assert not result.ok and result.error in ("BadDeviceToken", "Unregistered"), verdict(result)
