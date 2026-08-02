import json

from scripts.export_static_demo import _entry, export


def test_static_demo_is_self_contained_and_integrity_manifested(tmp_path) -> None:
    manifest = export(tmp_path)

    assert (tmp_path / ".nojekyll").is_file()
    assert {item["path"] for item in manifest["files"]} == {
        "index.html",
        "app.css",
        "app.js",
        "incident.json",
    }
    incident = json.loads((tmp_path / "incident.json").read_text(encoding="utf-8"))
    assert incident["summary"]["status"] == "Contained"
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="app.css"' in html
    assert 'src="app.js"' in html
    assert _entry("sample", b"data") == {
        "path": "sample",
        "bytes": 4,
        "sha256": "3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7",
    }
