"""Send one real alert to prove an Apple key, team and app capability before wiring anything.

    python -m bond_push_py.send_test            # reads the variables below
    python -m bond_push_py.send_test --help

Variables (a flag of the same name overrides): ``BOND_PUSH_KEY_PATH`` (the .p8 file), ``BOND_PUSH_KEY_ID``,
``BOND_PUSH_TEAM_ID``, ``BOND_PUSH_TOPIC`` (the app's bundle id), ``BOND_PUSH_DEVICE_TOKEN`` (from a development build
on a real phone). It sends to the SANDBOX host unless ``--environment production``. It prints one verdict line
(``accepted``, ``unregistered``, ``retryable`` or ``rejected``) that also names the host used (sandbox or production),
with a hint for ``BadDeviceToken`` and ``DeviceTokenNotForTopic``, and exits 0 only for ``accepted``. The key is read from
the file at run time; the device token, key id and team id are never printed.
"""

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from bond_push_py.apns import ApnsSender
from bond_push_py.messages import PushMessage, PushResult

VARIABLES = {
    "key_path": "BOND_PUSH_KEY_PATH",
    "key_id": "BOND_PUSH_KEY_ID",
    "team_id": "BOND_PUSH_TEAM_ID",
    "topic": "BOND_PUSH_TOPIC",
    "token": "BOND_PUSH_DEVICE_TOKEN",
}
#: A well-formed token no device owns: Apple answers it with a dead-token verdict.
MADE_UP_TOKEN = "00" * 32


def verdict(result: PushResult) -> str:
    """One word and, when Apple gave one, its reason. Never contains the token."""
    if result.ok:
        return "accepted"
    if result.unregistered:
        return f"unregistered ({result.error})"
    if result.retryable:
        return f"retryable ({result.error})"
    return f"rejected ({result.error})"


#: Reasons Apple gives that name a wrong host or a wrong bundle id more often than a dead device.
HINTS = {
    "BadDeviceToken": "the token is not valid for this host (a debug build needs sandbox; TestFlight and store builds "
                      "need production) or it is not a real device token",
    "DeviceTokenNotForTopic": "the token belongs to a different bundle id than the topic, or the host is wrong",
}


def report(result: PushResult, environment: str) -> str:
    """The verdict line ``main`` prints: the verdict, the host used and, for a wrong-host or wrong-topic reason, a hint.
    ``BadDeviceToken`` and ``DeviceTokenNotForTopic`` are not called ``unregistered``: Apple's reason is shown as is."""
    reason = result.error or ""
    if not result.ok and reason in HINTS:
        text = f"rejected token ({reason})"
    else:
        text = verdict(result)
    line = f"{text} on the {environment} host"
    return f"{line}. Hint: {HINTS[reason]}" if not result.ok and reason in HINTS else line


def missing(values: Mapping[str, str | None]) -> list[str]:
    """The variable names that have no value."""
    return [VARIABLES[name] for name in VARIABLES if not values.get(name)]


def send_alert(key_path: str, key_id: str, team_id: str, topic: str, token: str, *,
               environment: str = "sandbox", title: str = "Bond push check",
               body: str = "If you can read this, the key and the app capability work.",
               client=None) -> PushResult:
    """Send one alert through ``ApnsSender``. The key file is read here, when called, and nowhere else."""
    key_pem = Path(key_path).read_text()
    message = PushMessage(token=token, environment=environment, topic=topic, title=title, body=body)
    with ApnsSender(key_pem, key_id, team_id, client=client) as sender:
        return sender.send([message])[0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bond_push_py.send_test",
        description="Send one real alert to the Apple sandbox. Defaults come from the environment: "
        + ", ".join(VARIABLES.values()) + ". Exits 0 only when Apple accepts the push.")
    parser.add_argument("--key-path", help=f"the .p8 key file ({VARIABLES['key_path']})")
    parser.add_argument("--key-id", help=f"({VARIABLES['key_id']})")
    parser.add_argument("--team-id", help=f"({VARIABLES['team_id']})")
    parser.add_argument("--topic", help=f"the app's bundle id ({VARIABLES['topic']})")
    parser.add_argument("--token", help=f"a device token ({VARIABLES['token']}); keep it out of shell history")
    parser.add_argument("--environment", choices=("sandbox", "production"), default="sandbox",
                        help="Apple host to use (default sandbox)")
    parser.add_argument("--title", default="Bond push check")
    parser.add_argument("--body", default="If you can read this, the key and the app capability work.")
    return parser


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:  # --help is 0; a bad flag is a failure
        return 0 if exc.code in (0, None) else 1
    env = os.environ if environ is None else environ
    values = {name: getattr(args, name) or env.get(var) for name, var in VARIABLES.items()}
    absent = missing(values)
    if absent:
        print("missing: " + ", ".join(absent) + " (set the variables or pass the flags; see --help)", file=sys.stderr)
        return 1
    try:
        result = send_alert(**values, environment=args.environment, title=args.title, body=args.body)
    except (OSError, ValueError) as exc:  # includes UnicodeDecodeError: a binary or non-UTF-8 key file
        print(f"cannot read the key file: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(report(result, args.environment))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
