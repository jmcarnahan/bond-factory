import subprocess
import sys

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from bond_push_py import PushResult
from bond_push_py import send_test as st


def test_help_works_with_no_environment():
    env = {"PATH": "", "PYTHONPATH": ":".join(p for p in sys.path if p)}
    out = subprocess.run([sys.executable, "-m", "bond_push_py.send_test", "--help"],
                         check=False, env=env, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0
    assert "BOND_PUSH_KEY_PATH" in out.stdout and "BOND_PUSH_DEVICE_TOKEN" in out.stdout


def test_missing_variables_exit_one_and_name_them(capsys):
    assert st.main([], environ={}) == 1
    err = capsys.readouterr().err
    for name in st.VARIABLES.values():
        assert name in err


def test_verdict_words_never_hold_the_token():
    assert st.verdict(PushResult(ok=True)) == "accepted"
    assert st.verdict(PushResult(ok=False, unregistered=True, error="BadDeviceToken")) == "unregistered (BadDeviceToken)"
    assert st.verdict(PushResult(ok=False, retryable=True, error="503")).startswith("retryable")
    assert st.verdict(PushResult(ok=False, error="TopicDisallowed")).startswith("rejected")


@pytest.fixture
def keyfile(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "AuthKey_TEST.p8"
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    return str(path)


def _client(status, body=None):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_send_alert_goes_to_the_sandbox_and_reads_the_verdict(keyfile):
    client, seen = _client(200)
    result = st.send_alert(keyfile, "KEYID", "TEAMID", "com.example.app", "ab" * 32, client=client)
    assert result.ok and seen[0].url.host == "api.sandbox.push.apple.com"
    client, _ = _client(400, {"reason": "BadDeviceToken"})
    assert st.send_alert(keyfile, "KEYID", "TEAMID", "com.example.app", st.MADE_UP_TOKEN, client=client).unregistered


def test_main_prints_a_verdict_and_never_the_token(keyfile, capsys, monkeypatch):
    env = {"BOND_PUSH_KEY_PATH": keyfile, "BOND_PUSH_KEY_ID": "KEYID", "BOND_PUSH_TEAM_ID": "TEAMID",
           "BOND_PUSH_TOPIC": "com.example.app", "BOND_PUSH_DEVICE_TOKEN": "cd" * 32}
    monkeypatch.setattr(st, "send_alert", lambda *a, **k: PushResult(ok=False, unregistered=True, error="Unregistered"))
    assert st.main([], environ=env) == 1
    out = capsys.readouterr().out
    # Changed by the infra fix round: the verdict line now names the host (was exactly "unregistered (Unregistered)").
    assert out.strip() == "unregistered (Unregistered) on the sandbox host" and "cd" * 32 not in out
    monkeypatch.setattr(st, "send_alert", lambda *a, **k: PushResult(ok=True))
    assert st.main(["--topic", "com.example.other"], environ=env) == 0


def test_unreadable_key_file_exits_one(capsys):
    env = {"BOND_PUSH_KEY_PATH": "/nonexistent/key.p8", "BOND_PUSH_KEY_ID": "K", "BOND_PUSH_TEAM_ID": "T",
           "BOND_PUSH_TOPIC": "t", "BOND_PUSH_DEVICE_TOKEN": "ab" * 32}
    assert st.main([], environ=env) == 1
    assert "cannot read the key file" in capsys.readouterr().err


def _env(keyfile, **over):
    env = {"BOND_PUSH_KEY_PATH": keyfile, "BOND_PUSH_KEY_ID": "KEYID", "BOND_PUSH_TEAM_ID": "TEAMID",
           "BOND_PUSH_TOPIC": "com.example.app", "BOND_PUSH_DEVICE_TOKEN": "cd" * 32}
    env.update(over)
    return env


def _patch_client(monkeypatch, client):
    real = st.send_alert
    monkeypatch.setattr(st, "send_alert", lambda *a, **k: real(*a, **k, client=client))


@pytest.mark.parametrize("env_flag,host", [([], "sandbox"), (["--environment", "production"], "production")])
def test_verdict_line_names_the_host_that_was_used(keyfile, capsys, monkeypatch, env_flag, host):
    client, seen = _client(200)
    _patch_client(monkeypatch, client)
    assert st.main(env_flag, environ=_env(keyfile)) == 0
    assert capsys.readouterr().out.strip() == f"accepted on the {host} host"
    assert (seen[0].url.host == "api.sandbox.push.apple.com") == (host == "sandbox")


@pytest.mark.parametrize("reason,hint", [("BadDeviceToken", "host"),
                                         ("DeviceTokenNotForTopic", "bundle id")])
def test_wrong_host_or_topic_reasons_print_reason_and_hint_not_unregistered(keyfile, capsys, monkeypatch, reason, hint):
    client, _ = _client(400, {"reason": reason})
    _patch_client(monkeypatch, client)
    assert st.main([], environ=_env(keyfile)) == 1
    out = capsys.readouterr().out
    assert reason in out and "Hint:" in out and hint in out and "unregistered" not in out and "cd" * 32 not in out


def test_unregistered_reason_keeps_the_unregistered_word(keyfile, capsys, monkeypatch):
    client, _ = _client(410, {"reason": "Unregistered"})
    _patch_client(monkeypatch, client)
    assert st.main([], environ=_env(keyfile)) == 1
    assert capsys.readouterr().out.startswith("unregistered (Unregistered) on the sandbox host")


def test_non_utf8_key_file_is_a_clean_error(tmp_path, capsys):
    bad = tmp_path / "bad.p8"
    bad.write_bytes(b"\xff\xfe\x00\x80binary")
    assert st.main([], environ=_env(str(bad))) == 1
    captured = capsys.readouterr()
    assert "cannot read the key file" in captured.err and "Traceback" not in captured.err and captured.out == ""
