from sdk_example.settings import Settings, out_dir_for


def test_generated_files_live_next_to_the_database_not_the_cwd(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.delenv("BOND_OAUTH_KEY")
    data = tmp_path / "data"
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{data}/app.db")
    key = Settings.from_env().oauth_key
    assert (data / "oauth.key").read_text().strip() == key
    assert not (elsewhere / "out").exists()
    assert out_dir_for(f"sqlite:///{data}/app.db") == data.resolve()


def test_a_non_file_database_falls_back_to_out():
    assert out_dir_for("postgresql://example.invalid/db").name == "out"
    assert out_dir_for("sqlite:///:memory:").name == "out"
