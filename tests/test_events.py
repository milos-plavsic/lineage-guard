import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from lineage_guard.demo import RAW
from lineage_guard.events import (
    MAX_EVENT_BYTES,
    InvalidQualityEvent,
    QualityEvent,
    load_quality_event,
)


def payload() -> dict:
    return {
        "schema_version": 1,
        "event_id": "assertion:billing-2026-08-02",
        "occurred_at": "2026-08-02T12:30:00Z",
        "producer": "datahub-actions",
        "signal": {
            "asset_urn": RAW,
            "field": "billing_amount",
            "rule": "values must be non-negative",
            "observed": "37 negative values",
            "severity": "high",
            "affected_concerns": ["billing", "financial"],
        },
    }


def test_parses_bounded_versioned_event_and_stable_digest(tmp_path, monkeypatch) -> None:
    rendered = json.dumps(payload(), sort_keys=True, separators=(",", ":")).encode()
    event = QualityEvent.from_bytes(rendered)
    assert event.signal.asset_urn == RAW
    assert len(event.payload_sha256) == 64

    path = tmp_path / "event.json"
    path.write_bytes(rendered)
    assert load_quality_event(str(path)) == event

    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(rendered)))
    assert load_quality_event("-") == event
    assert QualityEvent.from_dict(payload()).payload_sha256 == event.payload_sha256


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item.update(schema_version=2), "schema_version"),
        (lambda item: item.update(event_id="bad id"), "unsupported characters"),
        (lambda item: item.update(occurred_at="not-a-time"), "RFC 3339"),
        (lambda item: item.update(occurred_at="2026-08-02T12:30:00"), "timezone"),
        (lambda item: item.update(signal=[]), "signal must"),
        (lambda item: item["signal"].update(asset_urn="not-a-urn"), "DataHub URN"),
        (lambda item: item["signal"].update(severity="urgent"), "severity"),
        (lambda item: item["signal"].update(affected_concerns=[]), "1 to 20"),
        (lambda item: item["signal"].update(affected_concerns=[""]), "non-empty"),
        (lambda item: item["signal"].update(field=""), "signal.field"),
        (lambda item: item.update(producer="x" * 257), "producer"),
    ],
)
def test_rejects_invalid_event_fields(mutate, message) -> None:
    candidate = payload()
    mutate(candidate)
    with pytest.raises(InvalidQualityEvent, match=message):
        QualityEvent.from_dict(candidate)


def test_rejects_invalid_event_envelopes() -> None:
    for body in (b"", b"x" * (MAX_EVENT_BYTES + 1)):
        with pytest.raises(InvalidQualityEvent, match="between 1"):
            QualityEvent.from_bytes(body)


def test_committed_quality_event_is_executable() -> None:
    event = load_quality_event(
        str(Path(__file__).resolve().parents[1] / "examples" / "quality-event.json")
    )
    assert event.producer == "datahub-actions"
    assert event.signal.field == "billing_amount"
    for body, message in ((b"not-json", "UTF-8 JSON"), (b"[]", "JSON object")):
        with pytest.raises(InvalidQualityEvent, match=message):
            QualityEvent.from_bytes(body)
