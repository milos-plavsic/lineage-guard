import json
from urllib.error import URLError

import pytest

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.datahub_incidents import (
    MAX_GRAPHQL_RESPONSE_BYTES,
    DataHubIncidentClient,
    DataHubIncidentError,
)
from lineage_guard.demo import assets, edges, negative_billing_signal
from lineage_guard.service import IncidentAnalyzer


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        assert limit == MAX_GRAPHQL_RESPONSE_BYTES + 1
        return self.value


def report():
    return IncidentAnalyzer(InMemoryMetadataGraph(assets(), edges())).analyze(
        negative_billing_signal()
    )


def test_incident_projection_creates_and_is_retry_idempotent(monkeypatch) -> None:
    responses = iter(
        [
            {
                "data": {
                    "dataset": {
                        "incidents": {
                            "incidents": [
                                None,
                                {"title": "different", "urn": "urn:li:incident:other"},
                                {"title": f"LineageGuard {report().incident_id}", "urn": "bad"},
                            ],
                            "total": 3,
                        }
                    }
                }
            },
            {"data": {"raiseIncident": "urn:li:incident:created"}},
            {
                "data": {
                    "dataset": {
                        "incidents": {
                            "incidents": [
                                {
                                    "urn": "urn:li:incident:created",
                                    "title": f"LineageGuard {report().incident_id}",
                                }
                            ]
                        }
                    }
                }
            },
        ]
    )

    def request(value, timeout):
        assert value.headers["Authorization"] == "Bearer token" and timeout == 15
        return Response(json.dumps(next(responses)).encode())

    monkeypatch.setattr("lineage_guard.datahub_incidents.urlopen", request)
    client = DataHubIncidentClient("https://datahub.example/api/graphql", "token")
    assert client.ensure_incident(report()).created
    assert not client.ensure_incident(report()).created


@pytest.mark.parametrize(
    "value",
    ["ftp://bad", ""],
)
def test_incident_client_rejects_invalid_configuration(value) -> None:
    with pytest.raises(ValueError):
        DataHubIncidentClient(value, "token")
    with pytest.raises(ValueError):
        DataHubIncidentClient("https://valid", "", timeout_seconds=0)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"not-json", "invalid JSON"),
        (json.dumps({"errors": [{}]}).encode(), "GraphQL error"),
        (json.dumps({"data": []}).encode(), "no data"),
        (b"x" * (MAX_GRAPHQL_RESPONSE_BYTES + 1), "exceeded"),
    ],
    ids=("invalid-json", "graphql-error", "missing-data", "oversized"),
)
def test_incident_api_fails_closed_on_invalid_responses(monkeypatch, raw, message) -> None:
    monkeypatch.setattr(
        "lineage_guard.datahub_incidents.urlopen", lambda *args, **kwargs: Response(raw)
    )
    with pytest.raises(DataHubIncidentError, match=message):
        DataHubIncidentClient("https://valid", "token").ensure_incident(report())


def test_incident_api_sanitizes_transport_and_shape_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        "lineage_guard.datahub_incidents.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("secret")),
    )
    with pytest.raises(DataHubIncidentError, match="request failed"):
        DataHubIncidentClient("https://valid", "token").ensure_incident(report())

    malformed = {"data": {"dataset": {"incidents": {"incidents": "bad"}}}}
    monkeypatch.setattr(
        "lineage_guard.datahub_incidents.urlopen",
        lambda *args, **kwargs: Response(json.dumps(malformed).encode()),
    )
    with pytest.raises(DataHubIncidentError, match="malformed"):
        DataHubIncidentClient("https://valid", "token").ensure_incident(report())


def test_incident_api_rejects_invalid_created_urn(monkeypatch) -> None:
    responses = iter(
        [
            {"data": {"dataset": {"incidents": {"incidents": []}}}},
            {"data": {"raiseIncident": "bad"}},
        ]
    )
    monkeypatch.setattr(
        "lineage_guard.datahub_incidents.urlopen",
        lambda *args, **kwargs: Response(json.dumps(next(responses)).encode()),
    )
    with pytest.raises(DataHubIncidentError, match="valid incident URN"):
        DataHubIncidentClient("https://valid", "token").ensure_incident(report())
