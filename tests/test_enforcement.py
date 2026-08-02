import json
from unittest.mock import patch
from urllib.error import URLError

import pytest

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.enforcement import (
    MAX_ENFORCEMENT_RESPONSE_BYTES,
    EnforcementError,
    SignedWebhookConfig,
    SignedWebhookEnforcer,
)
from lineage_guard.service import IncidentAnalyzer


def report():
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    return IncidentAnalyzer(graph).analyze(negative_billing_signal())


class Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, maximum):
        return self.body[:maximum]


def test_sends_signed_idempotent_fail_closed_plan() -> None:
    incident = report()
    acknowledgement = json.dumps(
        {"accepted": True, "incident_id": incident.incident_id, "receipt_id": "receipt-1"}
    ).encode()

    with patch("lineage_guard.enforcement.urlopen", return_value=Response(acknowledgement)) as send:
        receipt = SignedWebhookEnforcer(
            SignedWebhookConfig("https://orchestrator.example/events", "x" * 32)
        ).enforce(incident)

    request = send.call_args.args[0]
    body = json.loads(request.data)
    assert receipt.receipt_id == "receipt-1"
    assert request.get_header("Idempotency-key") == incident.incident_id
    assert request.get_header("X-lineageguard-signature").startswith("sha256=")
    assert body["default_action"] == "hold"
    assert {item["decision"]: item["action"] for item in body["directives"]}["continue"] == "allow"
    assert {item["decision"]: item["action"] for item in body["directives"]}["quarantine"] == "hold"


@pytest.mark.parametrize(
    "config",
    [
        ("http://example.com/hook", "x" * 32, 10),
        ("https://example.com/hook", "short", 10),
        ("http://localhost/hook", "x" * 32, 0),
        ("http://localhost/hook", "x" * 32, 61),
    ],
)
def test_rejects_unsafe_webhook_configuration(config) -> None:
    with pytest.raises(ValueError):
        SignedWebhookConfig(*config)


def test_allows_loopback_http() -> None:
    assert SignedWebhookConfig("http://127.0.0.1/hook", "x" * 32).url.startswith("http://")


@pytest.mark.parametrize(
    "response",
    [
        Response(b"{}", 300),
        Response(b"x" * (MAX_ENFORCEMENT_RESPONSE_BYTES + 1)),
    ],
)
def test_rejects_unsafe_transport_response(response) -> None:
    enforcer = SignedWebhookEnforcer(SignedWebhookConfig("https://example.com", "x" * 32))
    with (
        patch("lineage_guard.enforcement.urlopen", return_value=response),
        pytest.raises(EnforcementError, match="unsafe containment"),
    ):
        enforcer.enforce(report())


def test_wraps_transport_failure_without_leaking_details() -> None:
    enforcer = SignedWebhookEnforcer(SignedWebhookConfig("https://example.com", "x" * 32))
    with (
        patch("lineage_guard.enforcement.urlopen", side_effect=URLError("secret")),
        pytest.raises(EnforcementError, match="request failed") as error,
    ):
        enforcer.enforce(report())
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b'{"accepted":false}',
        b'{"accepted":true,"incident_id":"wrong","receipt_id":"r"}',
        b'{"accepted":true,"incident_id":"9edb78125e19","receipt_id":2}',
    ],
)
def test_rejects_invalid_or_mismatched_acknowledgement(body) -> None:
    enforcer = SignedWebhookEnforcer(SignedWebhookConfig("https://example.com", "x" * 32))
    with (
        patch("lineage_guard.enforcement.urlopen", return_value=Response(body)),
        pytest.raises(EnforcementError, match="acknowledge|JSON"),
    ):
        enforcer.enforce(report())
