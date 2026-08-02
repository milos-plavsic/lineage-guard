from pathlib import Path

from scripts.audit_submission import (
    _created_in_submission_period,
    _public_url,
    _valid_duration,
    audit,
)


def test_public_url_requires_https_host() -> None:
    assert _public_url("https://example.com/demo")
    assert not _public_url("http://example.com/demo")
    assert not _public_url(None)
    assert _public_url("https://github.com/example/project", hosts={"github.com"})
    assert not _public_url("https://example.com/project", hosts={"github.com"})


def test_video_duration_is_strictly_under_three_minutes() -> None:
    assert _valid_duration(179)
    assert not _valid_duration(180)
    assert not _valid_duration(None)


def test_empty_repository_has_no_valid_creation_date(tmp_path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert not _created_in_submission_period(tmp_path)


def test_repository_audit_evaluates_complete_requirement_set() -> None:
    checks = audit(Path(__file__).resolve().parents[1])
    by_name = {check.name: check for check in checks}

    assert len(checks) == 14
    assert by_name["Apache 2.0 license"].passed
    assert by_name["Repository URL"].passed
    assert by_name["Project URL"].passed
    assert not by_name["Public video URL"].passed
    assert not by_name["Video under 3 minutes"].passed
