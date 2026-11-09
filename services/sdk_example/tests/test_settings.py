import pytest

from sdk_example.settings import Settings


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOND_OAUTH_KEY")
    s = Settings.from_env()
    assert s.mode == "fake"
    assert s.database_url == "sqlite:///out/sdk_example.db"
    assert s.auth_secret == "dev-secret-change-me"
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
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", "dev-secret-change-me")
    with pytest.raises(RuntimeError):
        Settings.from_env()


def test_real_mode_with_secret_works(monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", "a-real-secret")
    assert Settings.from_env().mode == "real"


def test_wildcard_cors_origin_raises(monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_CORS_ORIGINS", "http://a.test,*")
    with pytest.raises(RuntimeError, match="CORS"):
        Settings.from_env()
