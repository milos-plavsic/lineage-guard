from __future__ import annotations

import argparse
import hashlib
import json
from importlib.resources import files
from pathlib import Path

from lineage_guard.web import build_view_model

ASSET_NAMES = ("index.html", "app.css", "app.js")


def export(destination: Path) -> dict[str, object]:
    destination.mkdir(parents=True, exist_ok=True)
    exported = []
    assets = files("lineage_guard.web_assets")
    for name in ASSET_NAMES:
        content = assets.joinpath(name).read_bytes()
        (destination / name).write_bytes(content)
        exported.append(_entry(name, content))
    incident = json.dumps(build_view_model(), separators=(",", ":")).encode()
    (destination / "incident.json").write_bytes(incident)
    exported.append(_entry("incident.json", incident))
    (destination / ".nojekyll").write_bytes(b"")
    manifest = {"schemaVersion": 1, "mode": "deterministic-demo", "files": exported}
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def _entry(name: str, content: bytes) -> dict[str, object]:
    return {"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the static LineageGuard judge demo.")
    parser.add_argument("destination", type=Path, nargs="?", default=Path("site"))
    args = parser.parse_args()
    print(json.dumps(export(args.destination), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
