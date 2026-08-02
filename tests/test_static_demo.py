import json

from scripts.export_static_demo import export


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
