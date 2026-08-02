from scripts.audit_submission import _public_url, _valid_duration


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
