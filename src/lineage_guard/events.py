from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from lineage_guard.domain import QualitySignal, Severity

MAX_EVENT_BYTES = 65_536
_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class InvalidQualityEvent(ValueError):
    """Raised when an inbound quality event is unsafe or structurally invalid."""


@dataclass(frozen=True, slots=True)
class QualityEvent:
    event_id: str
    occurred_at: str
    producer: str
    signal: QualitySignal
    payload_sha256: str

    @classmethod
    def from_bytes(cls, body: bytes) -> QualityEvent:
        if not body or len(body) > MAX_EVENT_BYTES:
            raise InvalidQualityEvent("event body must be between 1 and 65536 bytes")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidQualityEvent("event body must be UTF-8 JSON") from error
        if not isinstance(payload, dict):
            raise InvalidQualityEvent("event body must be a JSON object")
        return cls.from_dict(payload, sha256(body).hexdigest())

    @classmethod
    def from_dict(cls, payload: dict[str, Any], digest: str = "") -> QualityEvent:
        if payload.get("schema_version") != 1:
            raise InvalidQualityEvent("unsupported quality-event schema_version")
        event_id = _bounded_string(payload.get("event_id"), "event_id", 128)
        if not _EVENT_ID.fullmatch(event_id):
            raise InvalidQualityEvent("event_id contains unsupported characters")
        occurred_at = _bounded_string(payload.get("occurred_at"), "occurred_at", 64)
        try:
            timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise InvalidQualityEvent("occurred_at must be an RFC 3339 timestamp") from error
        if timestamp.tzinfo is None:
            raise InvalidQualityEvent("occurred_at must include a timezone")
        producer = _bounded_string(payload.get("producer"), "producer", 256)
        raw_signal = payload.get("signal")
        if not isinstance(raw_signal, dict):
            raise InvalidQualityEvent("signal must be a JSON object")
        asset_urn = _bounded_string(raw_signal.get("asset_urn"), "signal.asset_urn", 1024)
        if not asset_urn.startswith("urn:li:"):
            raise InvalidQualityEvent("signal.asset_urn must be a DataHub URN")
        try:
            severity = Severity(raw_signal.get("severity"))
        except ValueError as error:
            raise InvalidQualityEvent("signal.severity is unsupported") from error
        concerns = raw_signal.get("affected_concerns")
        if not isinstance(concerns, list) or not 1 <= len(concerns) <= 20:
            raise InvalidQualityEvent("signal.affected_concerns must contain 1 to 20 values")
        normalized_concerns = tuple(
            _bounded_string(item, "signal.affected_concerns[]", 128) for item in concerns
        )
        signal = QualitySignal(
            asset_urn=asset_urn,
            field=_bounded_string(raw_signal.get("field"), "signal.field", 256),
            rule=_bounded_string(raw_signal.get("rule"), "signal.rule", 2_000),
            observed=_bounded_string(raw_signal.get("observed"), "signal.observed", 2_000),
            severity=severity,
            affected_concerns=normalized_concerns,
        )
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return cls(event_id, occurred_at, producer, signal, digest or sha256(canonical).hexdigest())


def load_quality_event(path: str) -> QualityEvent:
    if path == "-":
        import sys

        body = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
    else:
        body = Path(path).read_bytes()
    return QualityEvent.from_bytes(body)


def _bounded_string(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InvalidQualityEvent(f"{field} must be a non-empty string up to {maximum} characters")
    return value.strip()
