import hashlib

from scripts.fetch_healthcare import FILES, UPSTREAM_COMMIT, git_blob_digest


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
