import hashlib
import hmac
import http.client
import json
import runpy
import sys
import threading
import warnings
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lineage_guard import agent_web
from lineage_guard.agent import EventBusyError, EventConflictError
from lineage_guard.demo import RAW

SECRET = "inbound-secret-that-is-at-least-32-bytes"


def event_body(event_id="assertion:web-1") -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "event_id": event_id,
            "occurred_at": "2026-08-02T12:30:00Z",
            "producer": "datahub-actions",
            "signal": {
                "asset_urn": RAW,
                "field": "billing_amount",
                "rule": "non-negative",
                "observed": "failed",
                "severity": "high",
                "affected_concerns": ["billing"],
            },
        }
    ).encode()


class Agent:
    async def process(self, event):
        if event.event_id == "conflict":
            raise EventConflictError
        if event.event_id == "busy":
            raise EventBusyError
        if event.event_id == "failure":
            raise RuntimeError("sensitive")
        return {"event_id": event.event_id, "status": "proposed"}


@pytest.fixture
def server():
    instance = agent_web.AgentHttpServer(("127.0.0.1", 0), Agent(), SECRET)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def url(server, path):
    return f"http://127.0.0.1:{server.server_port}{path}"


def signed_request(server, body, *, path="/v1/quality-events", content_type="application/json"):
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return Request(
        url(server, path),
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "X-LineageGuard-Signature": f"sha256={signature}",
        },
    )


def error_json(request):
    with pytest.raises(HTTPError) as captured:
        urlopen(request, timeout=2)
    return captured.value, json.load(captured.value)


def test_health_success_and_security_headers(server) -> None:
    with urlopen(url(server, "/healthz"), timeout=2) as response:
        assert json.load(response) == {"status": "ok"}
        assert response.headers["Cache-Control"] == "no-store"
    error, body = error_json(url(server, "/missing"))
    assert error.code == 404 and body == {"error": "not_found"}


def test_authenticated_event_success_and_route_validation(server) -> None:
    body = event_body()
    with urlopen(signed_request(server, body), timeout=2) as response:
        assert json.load(response) == {"event_id": "assertion:web-1", "status": "proposed"}

    error, response = error_json(signed_request(server, body, path="/wrong"))
    assert error.code == 404 and response["error"] == "not_found"
    error, response = error_json(signed_request(server, body, content_type="text/plain"))
    assert error.code == 415 and response["error"] == "unsupported_media_type"


def test_rejects_invalid_length_signature_and_event(server) -> None:
    error, response = error_json(
        Request(url(server, "/v1/quality-events"), data=b"", method="POST")
    )
    assert error.code == 415

    request = Request(
        url(server, "/v1/quality-events"),
        data=event_body(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    error, response = error_json(request)
    assert error.code == 401 and response["error"] == "unauthorized"

    invalid = b"{}"
    error, response = error_json(signed_request(server, invalid))
    assert error.code == 400 and response["error"] == "invalid_quality_event"

    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    connection.putrequest("POST", "/v1/quality-events")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "invalid")
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 413
    connection.close()


@pytest.mark.parametrize(
    ("event_id", "status", "error_code"),
    [
        ("conflict", 409, "event_conflict"),
        ("busy", 409, "event_in_progress"),
        ("failure", 502, "processing_failed"),
    ],
)
def test_sanitizes_agent_outcomes(server, event_id, status, error_code) -> None:
    error, response = error_json(signed_request(server, event_body(event_id)))
    assert error.code == status and response == {"error": error_code}
    if event_id == "busy":
        assert error.headers["Retry-After"] == "5"


def test_main_validates_configuration_and_closes_server(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "token")
    monkeypatch.setenv("LINEAGE_GUARD_WEBHOOK_SECRET", SECRET)
    with pytest.raises(SystemExit, match="loopback"):
        agent_web.main(["--host", "0.0.0.0", "--gms-url", "http://gms"])
    with pytest.raises(SystemExit, match="--port"):
        agent_web.main(["--port", "0", "--gms-url", "http://gms"])

    monkeypatch.delenv("LINEAGE_GUARD_WEBHOOK_SECRET")
    with pytest.raises(SystemExit, match="32-byte"):
        agent_web.main(["--gms-url", "http://gms"])
    monkeypatch.setenv("LINEAGE_GUARD_WEBHOOK_SECRET", SECRET)
    with pytest.raises(SystemExit, match="enforcement requires"):
        agent_web.main(["--gms-url", "http://gms", "--enforcement-webhook", "https://example.com"])

    servers = []

    class Server:
        def __init__(self, address, agent, secret):
            self.values = (address, agent, secret)
            servers.append(self)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    monkeypatch.setattr(agent_web, "AgentHttpServer", Server)
    assert (
        agent_web.main(
            [
                "--gms-url",
                "http://gms",
                "--journal",
                str(tmp_path / "events.sqlite3"),
            ]
        )
        == 0
    )
    assert servers[-1].closed

    monkeypatch.setenv("LINEAGE_GUARD_ENFORCEMENT_SECRET", "x" * 32)
    assert (
        agent_web.main(
            [
                "--gms-url",
                "http://gms",
                "--journal",
                str(tmp_path / "events-2.sqlite3"),
                "--apply",
                "--enforcement-webhook",
                "http://localhost/hook",
            ]
        )
        == 0
    )


def test_executable_entrypoint(tmp_path, monkeypatch) -> None:
    def interrupt(server):
        del server
        raise KeyboardInterrupt

    monkeypatch.setattr(agent_web.ThreadingHTTPServer, "serve_forever", interrupt)
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "token")
    monkeypatch.setenv("LINEAGE_GUARD_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lineage-guard-agent",
            "--gms-url",
            "http://gms",
            "--journal",
            str(tmp_path / "entrypoint.sqlite3"),
            "--port",
            "0",
        ],
    )
    with warnings.catch_warnings(), pytest.raises(SystemExit) as error:
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("lineage_guard.agent_web", run_name="__main__")
    assert error.value.code == "--port must be between 1 and 65535"
