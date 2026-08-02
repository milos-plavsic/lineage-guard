from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

UPSTREAM_REPOSITORY = "https://github.com/datahub-project/static-assets"
UPSTREAM_COMMIT = "a6479c691dd2a40dd89563396d9c8b2b28bee83c"
FILES = {
    "README.md": (8521, "0c7e29de064abd0070e8a0ae6738d92334e401ee"),
    "add_lineage.py": (4182, "7fe5523d15e52be54a664ad071437beee4597200"),
    "add_metadata.py": (8441, "90b32fdd35e102d1bd59e0d0fbef3b4a4d9b5dda"),
    "create_db.py": (15111, "b19eeba0c8d6eae1c377f1d2b2e0846ea72803f1"),
    "healthcare.db": (31084544, "648e4233e2ffca212f969c6b877a2837020b64b9"),
    "ingest.yaml": (627, "36da33cd544d74482b52b9e5e736d90af3558624"),
}


def git_blob_digest(path: Path, size: int) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {size}\0".encode())
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_fixture(destination: Path, *, metadata_only: bool = False) -> dict[str, object]:
    destination.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for name, (expected_size, expected_blob) in FILES.items():
        if metadata_only and name == "healthcare.db":
            continue
        target = destination / name
        temporary = destination / f".{name}.download"
        url = (
            "https://raw.githubusercontent.com/datahub-project/static-assets/"
            f"{UPSTREAM_COMMIT}/datasets/healthcare/{name}"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "LineageGuard-Fixture/1"})
        try:
            with (
                urllib.request.urlopen(request, timeout=30) as response,
                temporary.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            actual_size = temporary.stat().st_size
            actual_blob = git_blob_digest(temporary, actual_size)
            if actual_size != expected_size or actual_blob != expected_blob:
                raise ValueError(
                    f"Integrity check failed for {name}: size={actual_size}, blob={actual_blob}"
                )
            os.replace(temporary, target)
            downloaded.append({"path": name, "bytes": actual_size, "git_blob_sha1": actual_blob})
        finally:
            temporary.unlink(missing_ok=True)
    manifest = {
        "source": UPSTREAM_REPOSITORY,
        "commit": UPSTREAM_COMMIT,
        "license": "Apache-2.0",
        "files": downloaded,
    }
    (destination / "fixture-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the pinned official healthcare fixture.")
    parser.add_argument("--destination", type=Path, default=Path(".fixtures/healthcare"))
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    manifest = download_fixture(args.destination, metadata_only=args.metadata_only)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
