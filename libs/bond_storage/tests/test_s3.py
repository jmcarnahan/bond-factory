import io
from datetime import UTC, datetime
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from bond_storage import S3StorageService, reset_clients


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("AWS_ENDPOINT_URL_S3", raising=False)
    reset_clients()
    yield
    reset_clients()


def make(**kw):
    kw.setdefault("region", "us-west-1")
    return S3StorageService("bkt", **kw)


def body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def test_put_get_delete_and_content_type():
    s = make()
    with Stubber(s.s3) as stub:
        stub.add_response("put_object", {}, {"Bucket": "bkt", "Key": "k", "Body": b"hi", "ContentType": "text/plain"})
        stub.add_response("get_object", {"Body": body(b"hi")}, {"Bucket": "bkt", "Key": "k"})
        stub.add_response("delete_object", {}, {"Bucket": "bkt", "Key": "k"})
        assert s.upload_bytes(b"hi", "k", content_type="text/plain") == "k"
        assert s.download_bytes("k") == b"hi"
        s.delete("k")
        stub.assert_no_pending_responses()


def test_missing_object_is_file_not_found_and_outage_propagates():
    s = make()
    with Stubber(s.s3) as stub:
        stub.add_client_error("get_object", "NoSuchKey", http_status_code=404)
        stub.add_client_error("get_object", "SlowDown", http_status_code=503)
        stub.add_client_error("head_object", "404", http_status_code=404)
        stub.add_client_error("head_object", "AccessDenied", http_status_code=403)
        stub.add_response("head_object", {})
        with pytest.raises(FileNotFoundError):
            s.download_bytes("gone")
        with pytest.raises(ClientError):
            s.download_bytes("throttled")
        assert s.exists("gone") is False
        with pytest.raises(ClientError):
            s.exists("forbidden")
        assert s.exists("here") is True


def test_a_missing_bucket_is_a_storage_error_not_a_missing_file():
    s = make()
    with Stubber(s.s3) as stub:
        stub.add_client_error("get_object", "NoSuchBucket", http_status_code=404)
        stub.add_client_error("head_object", "NoSuchBucket", http_status_code=404)
        with pytest.raises(ClientError) as info:
            s.download_bytes("k")
        assert info.value.response["Error"]["Code"] == "NoSuchBucket"
        with pytest.raises(ClientError):
            s.exists("k")


def test_list_keys_paginates_and_returns_aware_utc():
    s = make()
    t1, t2 = datetime(2030, 1, 1, tzinfo=UTC), datetime(2030, 1, 2)
    with Stubber(s.s3) as stub:
        stub.add_response("list_objects_v2", {"Contents": [{"Key": "p/1", "LastModified": t1}], "IsTruncated": True,
                                              "NextContinuationToken": "t"}, {"Bucket": "bkt", "Prefix": "p/"})
        stub.add_response("list_objects_v2", {"Contents": [{"Key": "p/2", "LastModified": t2}], "IsTruncated": False},
                          {"Bucket": "bkt", "Prefix": "p/", "ContinuationToken": "t"})
        out = s.list_keys("p/")
    assert [k for k, _ in out] == ["p/1", "p/2"]
    assert all(t.tzinfo is not None and t.utcoffset().total_seconds() == 0 for _, t in out)


def test_presign_carries_disposition_and_type():
    s = make()
    url = s.get_url("c/1/a b.pdf", 600, download_filename='my "file".pdf', content_type="application/pdf")
    query = parse_qs(urlparse(url).query)
    assert query["response-content-type"] == ["application/pdf"]
    disposition = query["response-content-disposition"][0]
    assert disposition.startswith("attachment; filename=") and "filename*=UTF-8''" in disposition and '"file"' not in disposition
    assert query["X-Amz-Expires"] == ["600"] and "X-Amz-Signature" in query
    plain = parse_qs(urlparse(s.get_url("k")).query)
    assert "response-content-disposition" not in plain and "response-content-type" not in plain


def test_virtual_addressing_is_the_default():
    url = make().get_url("a/b.txt")
    assert urlparse(url).netloc == "bkt.s3.us-west-1.amazonaws.com" and urlparse(url).path == "/a/b.txt"


def test_endpoint_and_path_addressing_are_reflected():
    s = make(endpoint_url="http://localhost:9000", addressing_style="path", region="us-east-1")
    parsed = urlparse(s.get_url("a/b.txt"))
    assert (parsed.netloc, parsed.path) == ("localhost:9000", "/bkt/a/b.txt")
    assert s.s3.meta.endpoint_url == "http://localhost:9000"
    assert s.s3.meta.config.s3["addressing_style"] == "path"
    virtual = make(endpoint_url="http://localhost:9000", addressing_style="virtual", region="us-east-1")
    assert urlparse(virtual.get_url("k")).netloc == "bkt.localhost:9000"


def test_client_config_timeouts_retries_signature():
    cfg = make(connect_timeout=7, read_timeout=11, max_attempts=4).s3.meta.config
    assert (cfg.signature_version, cfg.connect_timeout, cfg.read_timeout) == ("s3v4", 7, 11)
    # botocore reports total attempts (the retry count plus the first try)
    assert cfg.retries["mode"] == "standard" and cfg.retries["total_max_attempts"] == 5
    default = make(region="eu-central-1").s3.meta.config
    assert (default.connect_timeout, default.read_timeout, default.retries["total_max_attempts"]) == (5, 60, 4)


def test_clients_are_cached_by_region_endpoint_style_until_reset():
    a, b = make(), make()
    assert a.s3 is b.s3
    assert make(region="eu-west-1").s3 is not a.s3
    assert make(endpoint_url="http://x:1", addressing_style="path").s3 is not a.s3
    assert make(addressing_style="path").s3 is not a.s3
    reset_clients()
    assert make().s3 is not a.s3


def test_bad_addressing_style_refused():
    with pytest.raises(ValueError):
        make(addressing_style="bogus")


def test_upload_and_download_files_use_the_client(tmp_path):
    client = MagicMock()
    s = S3StorageService("bkt", region="us-west-1", client=client)
    src = tmp_path / "f.bin"
    src.write_bytes(b"1")
    assert s.upload(src, "k") == "k"
    client.upload_file.assert_called_once_with(str(src), "bkt", "k")
    s.download("k", tmp_path / "d" / "out.bin")
    client.download_file.assert_called_once_with("bkt", "k", str(tmp_path / "d" / "out.bin"))
    client.download_file.side_effect = ClientError({"Error": {"Code": "404", "Message": "x"}}, "HeadObject")
    with pytest.raises(FileNotFoundError):
        s.download("k", tmp_path / "again.bin")
