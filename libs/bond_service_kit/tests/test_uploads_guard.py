"""The uploads guard decides on the resolved path: parent segments and symbolic links are followed first.

Requests go to the ASGI app with a hand-built scope (the path decoded the way a server decodes it), so no client
normalises a dot segment before the app sees it.
"""

import asyncio
import os
from urllib.parse import unquote

import pytest
from fastapi import FastAPI

from bond_service_kit import mount_uploads

MARKER = b"%PDF-PRIVATE-MARKER"
needs_symlink = pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symbolic links on this platform")


def fetch(app: FastAPI, raw_path: str) -> tuple[int, bytes]:
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": unquote(raw_path), "raw_path": raw_path.encode(), "query_string": b"", "root_path": "",
        "headers": [], "server": ("test", 80), "client": ("test", 1),
    }
    status, chunks = 0, []

    sent_request = False
    finished = asyncio.Event()

    async def receive():
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await finished.wait()  # a streamed file response listens for a disconnect: hold it until the body is sent
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                finished.set()

    async def run():
        await asyncio.wait_for(app(scope, receive, send), timeout=10)

    asyncio.run(run())
    return status, b"".join(chunks)


@pytest.fixture
def uploads(tmp_path):
    for rel, data in {
        "private/doc.pdf": MARKER, "private/sub/deep.txt": MARKER, "a.png": b"\x89PNG",
        "pub/nested/file.v1.2.tar.gz": b"nested-bytes", "privateer.txt": b"lookalike-file",
        "private-notes/x.txt": b"lookalike-folder", "pub/other.png": b"\x89PNG-other",
    }.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    app = FastAPI()
    mount_uploads(app, tmp_path)
    return app, tmp_path


def _climbs(name: str) -> dict[str, str]:
    return {
        "plain": f"/uploads/../{name}/private/doc.pdf",
        "encoded-dots": f"/uploads/%2e%2e/{name}/private/doc.pdf",
        "encoded-slashes": f"/uploads/..%2f{name}%2fprivate%2fdoc.pdf",
        "all-encoded": f"/uploads/%2e%2e%2f{name}%2fprivate%2fdoc.pdf",
        "doubled-slashes": f"/uploads/%2e%2e//{name}//private//doc.pdf",
        "upper-case": f"/uploads/%2e%2e/{name}/PRIVATE/doc.pdf",
        "mixed-case": f"/uploads/%2e%2e/{name}/Private/doc.pdf",
        "two-climbs": f"/uploads/x/%2e%2e/%2e%2e/{name}/private/doc.pdf",
        "dot-segment": f"/uploads/%2e%2e/{name}/./private/doc.pdf",
        "inner-climb": f"/uploads/%2e%2e/{name}/private/sub/../doc.pdf",
        "inner-climb-deep": f"/uploads/pub/../%2e%2e/{name}/private/sub/deep.txt",
    }


_CLIMB_IDS = list(_climbs("x"))


@pytest.mark.parametrize("case", _CLIMB_IDS)
def test_a_path_that_leaves_and_re_enters_the_private_prefix_is_a_missing_file(uploads, case):
    app, root = uploads
    missing = fetch(app, "/uploads/does-not-exist.pdf")
    url = _climbs(root.name)[case]
    status, body = fetch(app, url)
    assert (status, body) == missing == (404, missing[1]), url
    assert MARKER not in body


def test_a_custom_private_prefix_is_resolved_too(tmp_path):
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "doc.pdf").write_bytes(MARKER)
    app = FastAPI()
    mount_uploads(app, tmp_path, private_prefix="secret/")
    missing = fetch(app, "/uploads/nope.pdf")
    assert fetch(app, f"/uploads/%2e%2e/{tmp_path.name}/secret/doc.pdf") == missing
    assert fetch(app, "/uploads/secret/doc.pdf") == missing


@needs_symlink
def test_a_directory_symlink_to_the_private_folder_is_a_missing_file(uploads):
    app, root = uploads
    (root / "pub" / "dirlink").symlink_to(root / "private", target_is_directory=True)
    missing = fetch(app, "/uploads/does-not-exist.pdf")
    for url in ("/uploads/pub/dirlink/doc.pdf", "/uploads/pub/dirlink/sub/deep.txt"):
        status, body = fetch(app, url)
        assert (status, body) == missing, url
        assert MARKER not in body


@needs_symlink
def test_a_file_symlink_to_a_private_file_is_a_missing_file(uploads):
    app, root = uploads
    (root / "pub" / "filelink.pdf").symlink_to(root / "private" / "doc.pdf")
    missing = fetch(app, "/uploads/does-not-exist.pdf")
    status, body = fetch(app, "/uploads/pub/filelink.pdf")
    assert (status, body) == missing
    assert MARKER not in body


@needs_symlink
def test_a_symlink_pointing_outside_the_uploads_directory_is_404(uploads, tmp_path_factory):
    app, root = uploads
    outside = tmp_path_factory.mktemp("outside") / "outside.txt"
    outside.write_bytes(b"outside-secret")
    (root / "pub" / "outlink.txt").symlink_to(outside)
    status, body = fetch(app, "/uploads/pub/outlink.txt")
    assert status == 404
    assert b"outside-secret" not in body


@pytest.mark.parametrize("raw", ["/uploads/a%00b", "/uploads/a\x00b", "/uploads/private/%00", "/uploads/pub/other.png%00.txt"])
def test_a_null_byte_answers_404_not_500(uploads, raw):
    app, _ = uploads
    missing = fetch(app, "/uploads/does-not-exist.pdf")
    assert missing[0] == 404
    assert fetch(app, raw) == missing


def test_a_null_byte_answers_404_with_an_empty_private_prefix(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    app = FastAPI()
    mount_uploads(app, tmp_path, private_prefix="")
    missing = fetch(app, "/uploads/does-not-exist.pdf")
    assert missing[0] == 404
    assert fetch(app, "/uploads/a%00b") == missing
    assert fetch(app, "/uploads/a.png") == (200, b"\x89PNG")


def test_an_empty_private_prefix_blocks_nothing(tmp_path):
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "doc.pdf").write_bytes(b"open")
    app = FastAPI()
    mount_uploads(app, tmp_path, private_prefix="")
    assert fetch(app, "/uploads/private/doc.pdf") == (200, b"open")


@needs_symlink
def test_a_symlink_between_two_public_files_is_served(uploads):
    app, root = uploads
    (root / "pub" / "alias.png").symlink_to(root / "pub" / "other.png")
    assert fetch(app, "/uploads/pub/alias.png") == (200, b"\x89PNG-other")


def test_public_files_with_dots_in_nested_folders_are_served(uploads):
    app, _ = uploads
    assert fetch(app, "/uploads/pub/nested/file.v1.2.tar.gz")[1] == b"nested-bytes"
    assert fetch(app, "/uploads/pub/x/../nested/file.v1.2.tar.gz") == (200, b"nested-bytes")
    assert fetch(app, "/uploads/pub/x/%2e%2e/nested/file.v1.2.tar.gz") == (200, b"nested-bytes")


def test_a_name_that_merely_starts_with_the_private_prefix_is_served(uploads):
    app, root = uploads
    assert fetch(app, "/uploads/privateer.txt") == (200, b"lookalike-file")
    assert fetch(app, "/uploads/private-notes/x.txt") == (200, b"lookalike-folder")
    assert fetch(app, f"/uploads/%2e%2e/{root.name}/privateer.txt") == (200, b"lookalike-file")


def test_a_leading_separator_cannot_escape_the_directory(uploads):
    app, _ = uploads
    status, body = fetch(app, "/uploads//etc/hosts")
    assert status == 404
    assert b"localhost" not in body


@needs_symlink
def test_a_self_referencing_symlink_is_a_missing_file(uploads):
    app, root = uploads
    (root / "pub" / "loop").symlink_to(root / "pub" / "loop")
    missing = fetch(app, "/uploads/does-not-exist.pdf")
    assert missing[0] == 404
    assert fetch(app, "/uploads/pub/loop") == missing
    assert fetch(app, "/uploads/pub/loop/x.png") == missing


@needs_symlink
def test_a_self_referencing_symlink_is_a_missing_file_with_an_empty_private_prefix(tmp_path):
    (tmp_path / "loop").symlink_to(tmp_path / "loop")
    app = FastAPI()
    mount_uploads(app, tmp_path, private_prefix="")
    missing = fetch(app, "/uploads/does-not-exist.pdf")
    assert missing[0] == 404
    assert fetch(app, "/uploads/loop") == missing
