import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from lineage_guard.web import SECURITY_HEADERS, LineageGuardHandler, build_view_model


def test_dashboard_model_exposes_decisions_timeline_and_artifacts() -> None:
    model = build_view_model()

    assert model["summary"] == {
        "status": "Contained",
        "affectedBranches": 1,
        "safeBranches": 2,
        "maxRisk": 100,
    }
    assert len(model["timeline"]) == 5
    assert {artifact["relative_path"] for artifact in model["artifacts"]} == {
        "quality/assert_billing_amount_non_negative.sql",
        "policies/9edb78125e19.json",
        "reports/9edb78125e19.md",
    }


def test_dashboard_declares_browser_security_boundaries() -> None:
    assert "default-src 'self'" in SECURITY_HEADERS["Content-Security-Policy"]
    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"


def test_http_server_exposes_health_page_and_incident_api() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), LineageGuardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/healthz", timeout=2) as response:
            assert json.load(response) == {"status": "ok"}
        with urlopen(base_url, timeout=2) as response:
            assert response.status == 200
            assert "default-src 'self'" in response.headers["Content-Security-Policy"]
            assert b"LineageGuard Incident Console" in response.read()
        with urlopen(f"{base_url}/api/incidents/current", timeout=2) as response:
            payload = json.load(response)
            assert payload["report"]["incident_id"] == "9edb78125e19"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
