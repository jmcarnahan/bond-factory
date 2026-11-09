from pathlib import Path

import pytest

from bond_storage import (
    LocalStorageService,
    S3StorageService,
    StorageService,
    StorageSettings,
    attachment_disposition,
    build_storage,
    company_key,
    reset_clients,
)


def test_local_round_trip_and_urls(tmp_path):
    s = LocalStorageService(tmp_path / "up")
    assert s.upload_bytes(b"hello", "a/b.txt") == "a/b.txt"
    assert s.download_bytes("a/b.txt") == b"hello" and s.exists("a/b.txt")
    assert s.get_url("a/b.txt", download_filename="x.txt") == "/uploads/a/b.txt"
    assert s.supports_presigned is False
    src = tmp_path / "src.bin"
    src.write_bytes(b"data")
    s.upload(src, "c/d.bin")
    out = s.download("c/d.bin", tmp_path / "deep" / "copy.bin")
    assert out.read_bytes() == b"data"
    s.delete("a/b.txt")
    s.delete("a/b.txt")  # deleting twice is fine
    assert not s.exists("a/b.txt")
    with pytest.raises(FileNotFoundError):
        s.download_bytes("a/b.txt")


@pytest.mark.parametrize("key", ["../escape", "a/../../escape", "/etc/passwd"])
def test_local_traversal_refused(tmp_path, key):
    s = LocalStorageService(tmp_path / "up")
    for call in (lambda: s.upload_bytes(b"x", key), lambda: s.download_bytes(key), lambda: s.get_url(key),
                 lambda: s.delete(key), lambda: s.exists(key)):
        with pytest.raises(ValueError):
            call()
    assert not (tmp_path / "escape").exists()


def test_local_list_keys(tmp_path):
    s = LocalStorageService(tmp_path)
    for key in ("p/1.txt", "p/2.txt", "q/3.txt"):
        s.upload_bytes(b"x", key)
    listed = s.list_keys("p/")
    assert [k for k, _ in listed] == ["p/1.txt", "p/2.txt"]
    assert all(t.tzinfo is not None and t.utcoffset().total_seconds() == 0 for _, t in listed)
    assert s.list_keys("zzz") == []


def test_base_defaults_via_a_minimal_subclass(tmp_path):
    class Mem(StorageService):
        def __init__(self):
            self.store: dict[str, bytes] = {}

        def upload(self, local_path: Path, key: str) -> str:
            self.store[key] = local_path.read_bytes()
            return key

        def download(self, key, local_path):
            if key not in self.store:
                raise FileNotFoundError(key)
            local_path.write_bytes(self.store[key])
            return local_path

        def get_url(self, key, expires_in=3600, *, download_filename=None, content_type=None):
            return key

        def delete(self, key):
            self.store.pop(key, None)

    m = Mem()
    assert m.upload_bytes(b"zz", "k") == "k" and m.download_bytes("k") == b"zz"
    assert m.exists("k") and not m.exists("nope") and m.supports_presigned is False
    with pytest.raises(NotImplementedError):
        m.list_keys("")


def test_attachment_disposition_is_safe():
    value = attachment_disposition('evil"\r\nSet-Cookie: x=1.pdf')
    assert "\r" not in value and "\n" not in value and 'evil"' not in value
    assert "filename*=UTF-8''" in value
    assert "%C3%A9" in attachment_disposition("café.pdf") and 'filename="caf.pdf"' in attachment_disposition("café.pdf")
    assert 'filename="download"' in attachment_disposition("")


@pytest.mark.parametrize("args,expected", [
    (("acme", "a", "b.pdf"), "c/acme/a/b.pdf"),
    (("acme", "/a/", "", "/b/"), "c/acme/a/b"),
    (("acme", "photos", "x.jpg"), "c/acme/photos/x.jpg"),
    (("acme",), "c/acme"),
])
def test_company_key(args, expected):
    assert company_key(*args) == expected


@pytest.mark.parametrize("parts", [("..", "b", "x.txt"), ("a", "..", "b"), ("a/../b",), (".",), ("a/./b",),
                                   ("..\\b",), ("/../",)])
def test_company_key_refuses_dot_segments(parts):
    with pytest.raises(ValueError, match="segments"):
        company_key("a", *parts)


@pytest.mark.parametrize("company", ["a/b", "a\\b", "..", ".", "/", "x/../y"])
def test_company_key_refuses_a_company_id_that_is_not_one_segment(company):
    with pytest.raises(ValueError, match="company_id"):
        company_key(company, "f.txt")


def test_company_key_dots_inside_names_are_fine(tmp_path):
    assert company_key("a", "..hidden", "v1.2", "x..y.txt") == "c/a/..hidden/v1.2/x..y.txt"
    # and a traversal attempt cannot reach another tenant's bytes through the local backend
    s = LocalStorageService(tmp_path)
    s.upload_bytes(b"tenant b", company_key("b", "x.txt"))
    with pytest.raises(ValueError):
        s.download_bytes(company_key("a", "..", "b", "x.txt"))


def test_disposition_strips_every_control_character():
    value = attachment_disposition("a\x00b\tc\x1f\x7fd.pdf")
    assert all(0x20 <= ord(ch) < 0x7F for ch in value)
    assert 'filename="abcd.pdf"' in value and "%00" not in value and "%09" not in value
    assert attachment_disposition("\x00\t") == attachment_disposition("")


def test_company_key_private_and_empty():
    assert company_key("acme", "a", "b", private=True) == "c/acme/private/a/b"
    assert company_key("acme", private=True) == "c/acme/private"
    with pytest.raises(ValueError):
        company_key("")


def settings(env, **kw):
    return StorageSettings.from_env(bucket_env="MY_BUCKET", env=env, **kw)


def test_settings_defaults():
    s = settings({})
    assert (s.backend, s.bucket, s.region, s.endpoint_url, s.addressing_style) == ("local", None, "us-east-1", None, "virtual")
    assert (s.connect_timeout, s.read_timeout, s.max_attempts, s.local_dir) == (5, 60, 3, "uploads")


def test_settings_env_matrix():
    env = {"STORAGE_BACKEND": "S3", "MY_BUCKET": "files", "AWS_REGION": "eu-west-1",
           "AWS_ENDPOINT_URL_S3": "https://aws.example", "S3_ADDRESSING_STYLE": "PATH",
           "S3_CONNECT_TIMEOUT": "9", "S3_READ_TIMEOUT": "x", "S3_MAX_ATTEMPTS": "", "UPLOADS_DIR": "/data"}
    s = settings(env)
    assert (s.backend, s.bucket, s.region, s.endpoint_url) == ("s3", "files", "eu-west-1", "https://aws.example")
    assert (s.addressing_style, s.connect_timeout, s.read_timeout, s.max_attempts, s.local_dir) == ("path", 9, 60, 3, "/data")
    # S3_* wins over AWS_*
    both = settings({**env, "S3_REGION": "us-west-2", "S3_ENDPOINT_URL": "https://s3.example"})
    assert (both.region, both.endpoint_url) == ("us-west-2", "https://s3.example")
    # an invalid style falls back to virtual; the bucket name comes only from the named variable
    assert settings({"S3_ADDRESSING_STYLE": "bogus", "S3_BUCKET": "ignored"}).addressing_style == "virtual"
    assert settings({"S3_BUCKET": "ignored"}).bucket is None


def test_settings_prefix_wins_then_plain():
    env = {"BOND_STORAGE_BACKEND": "s3", "STORAGE_BACKEND": "local", "BOND_S3_REGION": "ap-south-1"}
    s = settings(env, prefix="BOND_")
    assert s.backend == "s3" and s.region == "ap-south-1"
    assert settings({"STORAGE_BACKEND": "s3"}, prefix="BOND_").backend == "s3"


def test_settings_bad_backend_and_missing_bucket():
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        settings({"STORAGE_BACKEND": "gcs"})
    with pytest.raises(ValueError, match="bucket"):
        build_storage(settings({"STORAGE_BACKEND": "s3"}))


def test_build_storage_local_and_s3(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s")
    reset_clients()
    local = build_storage(settings({"UPLOADS_DIR": str(tmp_path / "u")}))
    assert isinstance(local, LocalStorageService) and (tmp_path / "u").is_dir()
    s3 = build_storage(settings({"STORAGE_BACKEND": "s3", "MY_BUCKET": "b", "S3_REGION": "us-west-1"}))
    assert isinstance(s3, S3StorageService) and s3.bucket == "b" and s3.supports_presigned
    reset_clients()
    assert local.list_keys("") == []
