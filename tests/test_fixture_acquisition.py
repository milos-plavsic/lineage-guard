import hashlib
from io import BytesIO
from unittest.mock import patch

from scripts.fetch_healthcare import FILES, UPSTREAM_COMMIT, download_fixture, git_blob_digest


def test_fixture_is_immutable_and_size_bounded() -> None:
    assert len(UPSTREAM_COMMIT) == 40
    assert sum(size for size, _ in FILES.values()) < 32 * 1024 * 1024
    assert all(len(blob) == 40 for _, blob in FILES.values())


def test_git_blob_digest_matches_git_object_format(tmp_path) -> None:
    content = b"fixture"
    fixture = tmp_path / "fixture.bin"
    fixture.write_bytes(content)
    expected = hashlib.sha1(
        f"blob {len(content)}\0".encode() + content, usedforsecurity=False
    ).hexdigest()

    assert git_blob_digest(fixture, len(content)) == expected


def test_metadata_download_is_streamed_verified_and_manifested(tmp_path) -> None:
    payloads = {name: b"x" * size for name, (size, _) in FILES.items() if name != "healthcare.db"}
    expected = {
        name: (len(content), hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest())
        for name, content in payloads.items()
    }

    with (
        patch(
            "scripts.fetch_healthcare.FILES", {**expected, "healthcare.db": FILES["healthcare.db"]}
        ),
        patch(
            "scripts.fetch_healthcare.urllib.request.urlopen",
            side_effect=lambda request, timeout: BytesIO(
                payloads[request.full_url.rsplit("/", 1)[-1]]
            ),
        ),
    ):
        manifest = download_fixture(tmp_path, metadata_only=True)

    assert {item["path"] for item in manifest["files"]} == set(payloads)
    assert not (tmp_path / "healthcare.db").exists()
    assert (tmp_path / "fixture-manifest.json").is_file()


def test_integrity_failure_removes_partial_download(tmp_path) -> None:
    with (
        patch("scripts.fetch_healthcare.FILES", {"README.md": (4, "0" * 40)}),
        patch("scripts.fetch_healthcare.urllib.request.urlopen", return_value=BytesIO(b"bad!")),
    ):
        try:
            download_fixture(tmp_path)
        except ValueError as error:
            assert "Integrity check failed" in str(error)
        else:
            raise AssertionError("corrupt fixture was accepted")

    assert not (tmp_path / ".README.md.download").exists()
