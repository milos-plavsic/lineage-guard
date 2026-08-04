import sqlite3
from contextlib import asynccontextmanager

import pytest

from lineage_guard.adapters.mcp import DataHubMcpGraph, StdioMcpConfig
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.agent import EventBusyError, EventConflictError, IncidentAgent
from lineage_guard.demo import RAW, assets, edges, field_dependencies
from lineage_guard.enforcement import EnforcementReceipt
from lineage_guard.events import QualityEvent
from lineage_guard.journal import EventJournal, JournalError


def event(event_id="assertion:agent-1", digest="a" * 64) -> QualityEvent:
    return QualityEvent.from_dict(
        {
            "schema_version": 1,
            "event_id": event_id,
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
        },
        digest,
    )


class Graph(InMemoryMetadataGraph):
    def __init__(self):
        super().__init__(assets(), edges(), field_dependencies=field_dependencies())
        self.flushed = False

    async def flush(self):
        self.flushed = True


@asynccontextmanager
async def session_factory(config):
    assert config.token == "token"
    yield object()


@pytest.mark.asyncio
async def test_agent_dry_run_is_durable_and_deduplicated(tmp_path, monkeypatch) -> None:
    graph = Graph()

    async def load(session, source_urn, *, source_field=None):
        assert session is not None and source_urn == RAW and source_field == "billing_amount"
        return graph

    monkeypatch.setattr(DataHubMcpGraph, "load", load)
    journal = EventJournal(tmp_path / "events.sqlite3")
    agent = IncidentAgent(
        journal,
        StdioMcpConfig("http://gms", "token"),
        artifacts_root=tmp_path / "artifacts",
        session_factory=session_factory,
    )

    result = await agent.process(event())
    duplicate = await agent.process(event())

    assert result["status"] == "proposed" and result["duplicate"] is False
    assert duplicate["duplicate"] is True
    assert graph.tags == [] and not graph.flushed
    assert (tmp_path / "artifacts" / result["incident_id"] / "manifest.json").is_file()
    assert [item["stage"] for item in journal.history(event().event_id)] == [
        "claimed",
        "context_resolved",
        "decision_recorded",
        "artifacts_generated",
        "immune_memory_proposed",
        "completed",
    ]


@pytest.mark.asyncio
async def test_approved_agent_enforces_then_updates_datahub(tmp_path, monkeypatch) -> None:
    graph = Graph()
    monkeypatch.setattr(DataHubMcpGraph, "load", lambda *args, **kwargs: None)

    async def load(*args, **kwargs):
        return graph

    monkeypatch.setattr(DataHubMcpGraph, "load", load)

    class Enforcer:
        def enforce(self, report):
            assert not graph.tags
            return EnforcementReceipt(report.incident_id, "orchestrator-receipt")

    journal = EventJournal(tmp_path / "events.sqlite3")
    agent = IncidentAgent(
        journal,
        StdioMcpConfig("http://gms", "token", enable_mutations=True),
        enforcer=Enforcer(),
        session_factory=session_factory,
    )
    result = await agent.process(event())

    assert result["status"] == "applied"
    assert result["enforcement_receipt_id"] == "orchestrator-receipt"
    assert graph.tags and graph.flushed
    stages = [item["stage"] for item in journal.history(event().event_id)]
    assert stages[-4:] == [
        "containment_enforced",
        "datahub_updated",
        "immune_memory_written",
        "completed",
    ]
    assert result["lineage_read_receipt"]["receiptDigest"].startswith("sha256:")
    assert result["immune_memory"]["record_digest"].startswith("sha256:")

    without_enforcer = IncidentAgent(
        journal,
        StdioMcpConfig("http://gms", "token", enable_mutations=True),
        session_factory=session_factory,
    )
    result = await without_enforcer.process(event("assertion:agent-2", "c" * 64))
    assert result["enforcement_receipt_id"] is None


@pytest.mark.asyncio
async def test_agent_rejects_busy_conflicting_and_corrupt_completed_events(
    tmp_path,
) -> None:
    path = tmp_path / "events.sqlite3"
    journal = EventJournal(path)
    config = StdioMcpConfig("http://gms", "token")
    agent = IncidentAgent(journal, config, session_factory=session_factory)

    journal.claim(event())
    with pytest.raises(EventBusyError, match="already being processed"):
        await agent.process(event())
    with pytest.raises(EventConflictError, match="different payload"):
        await agent.process(event(digest="b" * 64))

    corrupt = event("corrupt:1")
    journal.claim(corrupt)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE quality_events SET status='completed', result_json=NULL WHERE event_id=?",
            (corrupt.event_id,),
        )
    with pytest.raises(JournalError, match="no durable result"):
        await agent.process(corrupt)


@pytest.mark.asyncio
async def test_agent_failure_is_journaled_and_retryable(tmp_path, monkeypatch) -> None:
    calls = 0

    async def load(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure with sensitive detail")
        return Graph()

    monkeypatch.setattr(DataHubMcpGraph, "load", load)
    journal = EventJournal(tmp_path / "events.sqlite3")
    agent = IncidentAgent(
        journal,
        StdioMcpConfig("http://gms", "token"),
        session_factory=session_factory,
    )
    with pytest.raises(RuntimeError, match="sensitive detail"):
        await agent.process(event())
    assert journal.history(event().event_id)[-1]["detail"]["error_code"] == "RuntimeError"
    assert (await agent.process(event()))["status"] == "proposed"


def test_enforcer_cannot_bypass_mutation_approval(tmp_path) -> None:
    with pytest.raises(ValueError, match="requires mutation approval"):
        IncidentAgent(
            EventJournal(tmp_path / "events.sqlite3"),
            StdioMcpConfig("http://gms", "token"),
            enforcer=object(),
        )
