import json
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lineage_guard.web import SECURITY_HEADERS, LineageGuardHandler, build_view_model, main


def test_dashboard_model_exposes_decisions_timeline_and_artifacts() -> None:
    model = build_view_model()

    assert model["summary"] == {
        "status": "Contained",
        "affectedBranches": 1,
        "safeBranches": 1,
        "reviewBranches": 1,
        "maxRisk": 100,
    }
    assert len(model["timeline"]) == 12
    artifact_paths = {artifact["relative_path"] for artifact in model["artifacts"]}
    assert len(artifact_paths) == 20
    assert "proofgraph/causal-cuts.json" in artifact_paths
    assert {
        "quality/assert_billing_amount_non_negative.sql",
        "policies/9edb78125e19.json",
        "reports/9edb78125e19.md",
        "recovery/candidates/clamp-to-zero.sql",
        "recovery/candidates/restore-trusted-value.sql",
        "recovery/evaluations.json",
        f"recovery/certificates/{model['recovery']['certificate']['certificate_id']}.json",
        "immunity/evaluations.json",
        "immunity/coverage.json",
        "immunity/datahub-writeback.json",
    } <= artifact_paths
    assert [item["verdict"] for item in model["recovery"]["evaluations"]] == [
        "rejected",
        "verified",
    ]
    assert model["recovery"]["certificate"]["transition"] == "quarantine_to_release"
    assert [item["decision"] for item in model["chronos"]["evaluations"]] == [
        "blocked",
        "eligible_for_approval",
        "revalidation_required",
    ]


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
            assert payload["recovery"]["certificate"]["candidate_id"] == "restore-trusted-value"
            assert payload["chronos"]["genome"]["genome_id"].startswith("lg-genome-")
        with urlopen(f"{base_url}/app.css", timeout=2) as response:
            assert response.headers["Cache-Control"] == "public, max-age=3600"
            assert response.headers["Content-Type"].startswith("text/css")
        try:
            urlopen(f"{base_url}/missing", timeout=2)
        except HTTPError as error:
            assert error.code == 404
            assert json.load(error) == {"error": "not_found"}
        else:
            raise AssertionError("unknown route unexpectedly succeeded")
        try:
            urlopen(Request(base_url, method="POST"), timeout=2)
        except HTTPError as error:
            assert error.code == 405
            assert json.load(error) == {"error": "method_not_allowed"}
        else:
            raise AssertionError("POST request unexpectedly succeeded")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_web_rejects_invalid_port(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["lineage-guard-web", "--port", "0"])

    try:
        main()
    except SystemExit as error:
        assert "between 1 and 65535" in str(error)
    else:
        raise AssertionError("invalid port was accepted")
