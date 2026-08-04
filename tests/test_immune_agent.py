import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lineage_guard.adapters.mcp import DataHubMcpGraph
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import (
    ChangeDecision,
    ChangeProposal,
    build_demo_chronos,
    demo_immunity_context,
)
from lineage_guard.demo import (
    BILLING,
    RAW,
    assets,
    edges,
    field_dependencies,
    negative_billing_signal,
)
from lineage_guard.immune_agent import InheritedMemoryAgent, load_inherited_change
from lineage_guard.immune_memory import (
    MemoryRecordType,
    build_incident_memory,
    build_lifecycle_memory,
)
from lineage_guard.recovery import CounterfactualRecoveryLab, demo_recovery_scenario
from lineage_guard.service import IncidentAnalyzer


class StatefulDataHubSession:
    def __init__(self) -> None:
        self.description = "raw billing data"
        names = ["get_lineage", "get_entities", "update_description", "add_tags"]
        self.tools = SimpleNamespace(tools=[SimpleNamespace(name=name) for name in names])

    async def list_tools(self):
        return self.tools

    async def call_tool(self, name, arguments):
        if name == "get_lineage":
            payload = {"downstreams": {"searchResults": [], "total": 0}}
        elif name == "get_entities":
            payload = [
                {
                    "urn": urn,
                    "properties": {"name": "raw", "description": self.description},
                }
                for urn in arguments["urns"]
            ]
        elif name == "update_description":
            self.description = f"{self.description}\n\n{arguments['description']}"
            payload = {"success": True}
        else:
            payload = {"success": True}
        return SimpleNamespace(structuredContent=payload, content=[], isError=False)


@pytest.mark.asyncio
async def test_second_agent_inherits_blocks_and_writes_outcome() -> None:
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    report = IncidentAnalyzer(graph).analyze(negative_billing_signal())
    chronos = build_demo_chronos(
        report, CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
    )
    incident = build_incident_memory(
        report,
        graph.read_downstream_lineage(RAW, 5, field="billing_amount"),
        genome=chronos.genome,
        evidence_gaps=({"kind": "consistency", "detail": "watermark unavailable"},),
    )
    graph.append_immune_memory(RAW, incident)
    assert graph.get_immunity_context(RAW, "billing_amount") == demo_immunity_context(report)
    graph.add_tag(BILLING, "urn:li:tag:LineageGuard_Quarantined")
    assert graph.get_immunity_context(RAW, "billing_amount") == demo_immunity_context(report)
    agent = InheritedMemoryAgent()
    dry_run = await agent.evaluate(
        graph,
        RAW,
        ChangeProposal("pr-unsafe", "Remove guard", False),
        demo_immunity_context(report),
    )
    assert dry_run["status"] == "proposed"
    assert dry_run["memory_records_observed"] == 1
    assert dry_run["matching_incident_records"] == 1
    assert dry_run["evaluation"]["decision"] == ChangeDecision.BLOCKED
    assert len(graph.get_immune_memories(RAW)) == 1
    written = await agent.evaluate(
        graph,
        RAW,
        ChangeProposal("pr-unsafe", "Remove guard", False),
        demo_immunity_context(report),
        approved=True,
    )
    assert written["status"] == "written"
    assert len(graph.get_immune_memories(RAW)) == 2
    assert graph.get_immune_memories(RAW)[1].payload["evidence_gaps"]


@pytest.mark.asyncio
async def test_second_agent_requires_retrievable_genome() -> None:
    graph = InMemoryMetadataGraph(assets(), edges())
    with pytest.raises(LookupError, match="no matching incident"):
        await InheritedMemoryAgent().evaluate(
            graph,
            RAW,
            ChangeProposal("pr", "Change", True),
            demo_immunity_context(IncidentAnalyzer(graph).analyze(negative_billing_signal())),
        )


@pytest.mark.asyncio
async def test_second_agent_rejects_invalid_or_inactive_chain() -> None:
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    report = IncidentAnalyzer(graph).analyze(negative_billing_signal())
    chronos = build_demo_chronos(
        report, CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
    )
    incident = build_incident_memory(
        report,
        graph.read_downstream_lineage(RAW, 5, field="billing_amount"),
        genome=chronos.genome,
    )
    dangling = build_lifecycle_memory(
        incident,
        MemoryRecordType.REVOCATION,
        reason="compromised evidence",
        effective_at="2020-01-01T00:00:00Z",
    )
    graph.append_immune_memory(RAW, dangling)
    with pytest.raises(ValueError, match="chain verification"):
        await InheritedMemoryAgent().evaluate(
            graph, RAW, ChangeProposal("pr", "Change", True), None
        )

    graph.append_immune_memory(RAW, incident)
    with pytest.raises(LookupError, match="no matching incident"):
        await InheritedMemoryAgent().evaluate(
            graph, RAW, ChangeProposal("pr", "Change", True), None
        )


@pytest.mark.asyncio
async def test_fresh_mcp_agents_handoff_only_through_datahub() -> None:
    session = StatefulDataHubSession()
    source = await DataHubMcpGraph.load(session, RAW, source_field="billing_amount")
    # Proof inputs are compiled independently; the handoff is only the DataHub description.
    fixture_graph = InMemoryMetadataGraph(
        assets(), edges(), field_dependencies=field_dependencies()
    )
    report = IncidentAnalyzer(fixture_graph).analyze(negative_billing_signal())
    chronos = build_demo_chronos(
        report, CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
    )
    memory = build_incident_memory(
        report,
        source.read_downstream_lineage(RAW, 5, field="billing_amount"),
        genome=chronos.genome,
    )
    source.append_immune_memory(RAW, memory)
    source.append_immune_memory(RAW, memory)
    await source.flush()

    fresh_reader = await DataHubMcpGraph.load(session, RAW)
    fresh_reader.append_immune_memory(RAW, memory)
    outcome = await InheritedMemoryAgent().evaluate(
        fresh_reader,
        RAW,
        ChangeProposal("pr-future", "Remove quality guard", False),
        demo_immunity_context(report),
        approved=True,
    )
    assert outcome["evaluation"]["decision"] == ChangeDecision.BLOCKED

    final_reader = await DataHubMcpGraph.load(session, RAW)
    records = final_reader.get_immune_memories(RAW)
    assert len(records) == 2
    assert records[1].parent_digest == records[0].record_digest

    with pytest.raises(ValueError, match="target asset"):
        final_reader.append_immune_memory("urn:li:dataset:wrong", records[0])


def test_loads_bounded_inherited_change_contract() -> None:
    request = load_inherited_change(Path("examples/inherited-change.json"))
    assert request.source_urn == (
        "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.raw_patients,PROD)"
    )
    assert request.incident_id is None
    assert not request.change.quality_guard_enabled
    assert request.context is None


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: [], "malformed"),
        (lambda value: {**value, "schema_version": 3}, "malformed"),
        (lambda value: {**value, "change": []}, "proposal"),
        (lambda value: {**value, "change": {}}, "proposal"),
        (lambda value: {**value, "context": []}, "malformed"),
        (lambda value: {**value, "source_urn": "bad"}, "DataHub URN"),
        (lambda value: {**value, "incident_id": 7}, "text or null"),
    ],
)
def test_rejects_malformed_inherited_change(tmp_path, mutation, message) -> None:
    value = json.loads(Path("examples/inherited-change.json").read_text())
    path = tmp_path / "request.json"
    path.write_text(json.dumps(mutation(value)), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_inherited_change(path)


def test_loads_legacy_request_context(tmp_path) -> None:
    value = json.loads(Path("examples/inherited-change.json").read_text())
    value["schema_version"] = 1
    value["context"] = {
        "schema_fields": ["billing_amount"],
        "lineage_edges": [f"{RAW}->urn:li:dataset:downstream"],
        "governance_labels": ["tag:critical"],
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    request = load_inherited_change(path)

    assert request.context and request.context.schema_fields == ("billing_amount",)
    value["context"] = {}
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="context is malformed"):
        load_inherited_change(path)
    value["context"] = {
        "schema_fields": None,
        "lineage_edges": [],
        "governance_labels": [],
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="context is invalid"):
        load_inherited_change(path)


def test_rejects_unreadable_invalid_and_oversized_inherited_change(tmp_path) -> None:
    with pytest.raises(ValueError, match="invalid inherited-change"):
        load_inherited_change(tmp_path / "missing")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid inherited-change"):
        load_inherited_change(invalid)
    oversized = tmp_path / "oversized.json"
    oversized.write_text("x" * 2_000_001, encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds 2 MB"):
        load_inherited_change(oversized)
