import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from lineage_guard.demo import RAW
from lineage_guard.events import QualityEvent
from lineage_guard.journal import (
    MAX_JOURNAL_RESULT_BYTES,
    MAX_TRANSITION_DETAIL_BYTES,
    ClaimDisposition,
    EventJournal,
    JournalError,
)


def event(event_id="assertion:1", *, digest="a" * 64) -> QualityEvent:
    return QualityEvent.from_dict(
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
        },
        digest,
    )


def test_journal_deduplicates_completed_event_and_preserves_result(tmp_path) -> None:
    journal = EventJournal(tmp_path / "state" / "events.sqlite3")
    claim = journal.claim(event())
    assert claim.disposition is ClaimDisposition.NEW
    assert claim.attempts == 1
    assert journal.claim(event()).disposition is ClaimDisposition.BUSY

    result = {"incident_id": "incident-1", "status": "completed"}
    journal.complete(event().event_id, "incident-1", result)
    duplicate = journal.claim(event())
    assert duplicate.disposition is ClaimDisposition.DUPLICATE
    assert duplicate.result == result
    assert [item["stage"] for item in journal.history(event().event_id)] == [
        "claimed",
        "completed",
    ]
    assert journal.history("unknown") == ()

    conflict = journal.claim(event(digest="b" * 64))
    assert conflict.disposition is ClaimDisposition.CONFLICT


def test_failed_and_expired_processing_events_are_retryable(tmp_path) -> None:
    path = tmp_path / "events.sqlite3"
    journal = EventJournal(path, lease_seconds=1)
    first = event("failed:1")
    journal.claim(first)
    journal.fail(first.event_id, "mcp_unavailable")
    retry = journal.claim(first)
    assert retry.disposition is ClaimDisposition.RETRY
    assert retry.attempts == 2
    journal.record_transition(first.event_id, "context_resolved", {"assets": 3})
    assert journal.history(first.event_id)[-1]["detail"] == {"assets": 3}

    stale = event("stale:1")
    journal.claim(stale)
    old = (datetime.now(UTC) - timedelta(seconds=2)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE quality_events SET updated_at = ? WHERE event_id = ?",
            (old, stale.event_id),
        )
    retry = journal.claim(stale)
    assert retry.disposition is ClaimDisposition.RETRY
    assert retry.attempts == 2


def test_journal_validates_transitions_and_bounds(tmp_path) -> None:
    with pytest.raises(ValueError, match="lease"):
        EventJournal(tmp_path / "invalid.sqlite3", lease_seconds=0)

    journal = EventJournal(tmp_path / "events.sqlite3")
    with pytest.raises(ValueError, match="error code"):
        journal.fail("missing", "")
    with pytest.raises(ValueError, match="error code"):
        journal.fail("missing", "x" * 129)
    with pytest.raises(JournalError, match="not in a processing"):
        journal.fail("missing", "failed")
    with pytest.raises(ValueError, match="snake_case"):
        journal.record_transition("missing", "Bad Stage")
    with pytest.raises(JournalError, match="unknown event"):
        journal.record_transition("missing", "received")
    with pytest.raises(JournalError, match="safety limit"):
        journal.complete("missing", "incident", {"value": "x" * MAX_JOURNAL_RESULT_BYTES})

    current = event()
    journal.claim(current)
    with pytest.raises(JournalError, match="transition detail"):
        journal.record_transition(
            current.event_id, "oversized", {"value": "x" * MAX_TRANSITION_DETAIL_BYTES}
        )
    journal.complete(current.event_id, "incident", {})
    with pytest.raises(JournalError, match="not in a processing"):
        journal.complete(current.event_id, "incident", {})
