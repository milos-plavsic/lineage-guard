from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from lineage_guard.domain import Action, IncidentReport

MAX_ENFORCEMENT_RESPONSE_BYTES = 65_536


class EnforcementError(RuntimeError):
    """Raised when an orchestrator does not safely accept a containment plan."""


@dataclass(frozen=True, slots=True)
class EnforcementReceipt:
    incident_id: str
    receipt_id: str


@dataclass(frozen=True, slots=True)
class SignedWebhookConfig:
    url: str
    secret: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("enforcement webhook must use HTTPS, except on loopback")
        if len(self.secret.encode()) < 32:
            raise ValueError("enforcement webhook secret must contain at least 32 bytes")
        if not 0 < self.timeout_seconds <= 60:
            raise ValueError("enforcement webhook timeout must be between 0 and 60 seconds")


class SignedWebhookEnforcer:
    """Request a default-hold plan and verify the orchestrator's exact acknowledgement."""

    def __init__(self, config: SignedWebhookConfig) -> None:
        self._config = config

    def enforce(self, report: IncidentReport) -> EnforcementReceipt:
        body = self._body(report)
        signature = hmac.new(self._config.secret.encode(), body, digestmod=sha256).hexdigest()
        request = Request(
            self._config.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": report.incident_id,
                "X-LineageGuard-Signature": f"sha256={signature}",
            },
        )
        try:
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                response_body = response.read(MAX_ENFORCEMENT_RESPONSE_BYTES + 1)
                status = response.status
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise EnforcementError("orchestrator containment request failed") from error
        if not 200 <= status < 300 or len(response_body) > MAX_ENFORCEMENT_RESPONSE_BYTES:
            raise EnforcementError("orchestrator returned an unsafe containment response")
        try:
            acknowledgement: Any = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EnforcementError("orchestrator acknowledgement must be JSON") from error
        if (
            not isinstance(acknowledgement, dict)
            or acknowledgement.get("accepted") is not True
            or acknowledgement.get("incident_id") != report.incident_id
            or not isinstance(acknowledgement.get("receipt_id"), str)
        ):
            raise EnforcementError("orchestrator did not acknowledge the exact incident")
        return EnforcementReceipt(report.incident_id, acknowledgement["receipt_id"])

    @staticmethod
    def _body(report: IncidentReport) -> bytes:
        payload = {
            "schema_version": 1,
            "incident_id": report.incident_id,
            "source_urn": report.source.urn,
            "default_action": "hold",
            "directives": [
                {
                    "asset_urn": decision.asset.urn,
                    "action": "allow" if decision.action == Action.CONTINUE else "hold",
                    "decision": decision.action,
                    "evidence_strength": decision.evidence_strength,
                }
                for decision in report.decisions
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
