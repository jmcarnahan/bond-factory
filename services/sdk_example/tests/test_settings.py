import pytest

from sdk_example.settings import DEV_SECRET, Settings


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOND_OAUTH_KEY")
    s = Settings.from_env()
    assert s.mode == "fake"
    assert s.database_url == "sqlite:///out/sdk_example.db"
    assert s.auth_secret == DEV_SECRET
    assert s.cors_origins == ("http://localhost:8078",)
    assert s.redirect_allowlist == ("http://localhost:8078",)
    assert s.tz == "UTC"


def test_fake_mode_persists_oauth_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOND_OAUTH_KEY")
    first = Settings.from_env().oauth_key
    assert first
    assert (tmp_path / "out" / "oauth.key").read_text().strip() == first
    assert Settings.from_env().oauth_key == first


def test_env_key_wins(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOND_OAUTH_KEY", "from-env")
    assert Settings.from_env().oauth_key == "from-env"
    assert not (tmp_path / "out").exists()


def test_allowlist_parsing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SDK_EXAMPLE_REDIRECT_ALLOWLIST", " http://a.test , ,http://b.test ")
    monkeypatch.setenv("SDK_EXAMPLE_CORS_ORIGINS", "http://c.test")
    s = Settings.from_env()
    assert s.redirect_allowlist == ("http://a.test", "http://b.test")
    assert s.cors_origins == ("http://c.test",)


def test_real_mode_without_secret_raises(monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    with pytest.raises(RuntimeError, match="SDK_EXAMPLE_AUTH_SECRET must be set in real mode"):
        Settings.from_env()


def test_real_mode_with_dev_secret_raises(monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", DEV_SECRET)
    with pytest.raises(RuntimeError):
        Settings.from_env()


def test_real_mode_with_secret_works(monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", "a-real-secret")
    monkeypatch.setenv("SDK_EXAMPLE_PUBLIC_BASE", "https://api.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_REDIRECT_ALLOWLIST", "https://app.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_CORS_ORIGINS", "https://app.example.org")
    s = Settings.from_env()
    assert s.mode == "real" and s.native_redirects == () and s.native_schemes == ()  # no sdkdemo defaults outside fake mode


def _real(monkeypatch, **extra):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", "a-real-secret")
    monkeypatch.setenv("SDK_EXAMPLE_PUBLIC_BASE", "https://api.example.org")
    for name, value in extra.items():
        monkeypatch.setenv(f"SDK_EXAMPLE_{name}", value)


def test_real_mode_needs_a_redirect_allowlist(monkeypatch):
    _real(monkeypatch)
    with pytest.raises(RuntimeError, match="REDIRECT_ALLOWLIST must be set"):
        Settings.from_env()


def test_real_mode_refuses_a_cors_origin_the_origin_rule_would_block(monkeypatch):
    _real(monkeypatch, REDIRECT_ALLOWLIST="https://app.example.org", CORS_ORIGINS="https://other.example.org")
    with pytest.raises(RuntimeError, match="not in the redirect allowlist"):
        Settings.from_env()
    monkeypatch.setenv("SDK_EXAMPLE_CORS_ORIGINS", "https://api.example.org,https://app.example.org")
    assert Settings.from_env().cors_origins  # the API's own origin and the allowlist are fine


def test_wildcard_cors_origin_raises(monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_CORS_ORIGINS", "http://a.test,*")
    with pytest.raises(RuntimeError, match="CORS"):
        Settings.from_env()


def test_fake_mode_defaults_the_native_scheme_and_connections_can_be_switched_off(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert Settings.from_env().native_schemes == ("org.example.sdkdemo",) and Settings.from_env().connections
    monkeypatch.setenv("SDK_EXAMPLE_CONNECTIONS", "0")
    assert Settings.from_env().connections is False
