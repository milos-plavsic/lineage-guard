from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from lineage_guard.domain import IncidentReport

MAX_GRAPHQL_RESPONSE_BYTES = 1_000_000


class DataHubIncidentError(RuntimeError):
    """Raised when the optional native DataHub Incident projection fails safely."""


@dataclass(frozen=True, slots=True)
class DataHubIncidentReceipt:
    urn: str
    created: bool


class DataHubIncidentClient:
    def __init__(self, graphql_url: str, token: str, *, timeout_seconds: float = 15.0) -> None:
        if not graphql_url.startswith(("https://", "http://")):
            raise ValueError("DataHub GraphQL URL must use HTTP or HTTPS")
        if not token or timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("DataHub incident credentials and timeout must be valid")
        self._url = graphql_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds

    def ensure_incident(self, report: IncidentReport) -> DataHubIncidentReceipt:
        title = f"LineageGuard {report.incident_id}"
        existing = self._find(report.source.urn, title)
        if existing:
            return DataHubIncidentReceipt(existing, False)
        mutation = """
          mutation RaiseLineageGuardIncident($input: RaiseIncidentInput!) {
            raiseIncident(input: $input)
          }
        """
        result = self._execute(
            mutation,
            {
                "input": {
                    "resourceUrn": report.source.urn,
                    "type": "CUSTOM",
                    "customType": "LINEAGE_GUARD",
                    "title": title,
                    "description": report.proposed_writeback["append_description"]["markdown"],
                    "priority": (
                        "CRITICAL"
                        if max((item.risk_score for item in report.decisions), default=0) >= 90
                        else "HIGH"
                    ),
                }
            },
        )
        urn = result.get("raiseIncident")
        if not isinstance(urn, str) or not urn.startswith("urn:li:incident:"):
            raise DataHubIncidentError("DataHub did not return a valid incident URN")
        return DataHubIncidentReceipt(urn, True)

    def _find(self, asset_urn: str, title: str) -> str | None:
        query = """
          query ExistingLineageGuardIncidents($urn: String!) {
            dataset(urn: $urn) {
              incidents(start: 0, count: 100) {
                total
                incidents { urn title }
              }
            }
          }
        """
        result = self._execute(query, {"urn": asset_urn})
        dataset = result.get("dataset")
        incidents = dataset.get("incidents") if isinstance(dataset, dict) else None
        values = incidents.get("incidents") if isinstance(incidents, dict) else None
        if not isinstance(values, list) or len(values) > 100:
            raise DataHubIncidentError("DataHub returned malformed incident search results")
        for item in values:
            if isinstance(item, dict) and item.get("title") == title:
                urn = item.get("urn")
                if isinstance(urn, str) and urn.startswith("urn:li:incident:"):
                    return urn
        return None

    def _execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables}).encode()
        request = Request(
            self._url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read(MAX_GRAPHQL_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, OSError) as error:
            raise DataHubIncidentError("DataHub Incident API request failed") from error
        if len(raw) > MAX_GRAPHQL_RESPONSE_BYTES:
            raise DataHubIncidentError("DataHub Incident API response exceeded 1 MB")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DataHubIncidentError("DataHub Incident API returned invalid JSON") from error
        if not isinstance(payload, dict) or payload.get("errors"):
            raise DataHubIncidentError("DataHub Incident API returned a GraphQL error")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DataHubIncidentError("DataHub Incident API returned no data")
        return data
