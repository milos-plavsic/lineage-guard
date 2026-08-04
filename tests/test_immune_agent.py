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
from lineage_guard.demo import RAW, assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.immune_agent import InheritedMemoryAgent
from lineage_guard.immune_memory import build_incident_memory
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
    agent = InheritedMemoryAgent()
    dry_run = await agent.evaluate(
        graph,
        RAW,
        ChangeProposal("pr-unsafe", "Remove guard", False),
        demo_immunity_context(report),
    )
    assert dry_run["status"] == "proposed"
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
