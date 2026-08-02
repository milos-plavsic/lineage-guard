from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    evidence: str


def audit(root: Path) -> tuple[Check, ...]:
    metadata = json.loads((root / "submission/submission.json").read_text(encoding="utf-8"))
    checks = [
        Check("Apache 2.0 license", "Apache License" in (root / "LICENSE").read_text(), "LICENSE"),
        Check(
            "English description",
            (root / "submission/devpost.md").stat().st_size > 1000,
            "submission/devpost.md",
        ),
        Check(
            "Video script",
            "2 minutes 45 seconds" in (root / "submission/video-script.md").read_text(),
            "submission/video-script.md",
        ),
        Check(
            "Sample output",
            (root / "examples/incident-report.json").is_file(),
            "examples/incident-report.json",
        ),
        Check(
            "Generated artifacts",
            (root / "examples/generated/manifest.json").is_file(),
            "examples/generated/manifest.json",
        ),
        Check("Setup instructions", "## Run it" in (root / "README.md").read_text(), "README.md"),
        Check(
            "Repository URL",
            _public_url(metadata.get("repositoryUrl")),
            str(metadata.get("repositoryUrl")),
        ),
        Check(
            "Project URL", _public_url(metadata.get("projectUrl")), str(metadata.get("projectUrl"))
        ),
        Check(
            "Public video URL", _public_url(metadata.get("videoUrl")), str(metadata.get("videoUrl"))
        ),
        Check(
            "Video under 3 minutes",
            _valid_duration(metadata.get("videoDurationSeconds")),
            str(metadata.get("videoDurationSeconds")),
        ),
        Check("Clean Git worktree", _clean_worktree(root), "git status --porcelain"),
    ]
    return tuple(checks)


def _public_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _valid_duration(value: object) -> bool:
    return isinstance(value, int) and 0 < value < 180


def _clean_worktree(root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local Devpost submission requirements.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    checks = audit(args.root)
    for check in checks:
        print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.evidence}")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
