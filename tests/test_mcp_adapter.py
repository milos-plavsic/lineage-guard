from types import SimpleNamespace

import pytest

from lineage_guard.adapters.mcp import (
    MAX_TOOL_PAYLOAD_BYTES,
    DataHubMcpGraph,
    McpIntegrationError,
    _tool_payload,
)
from lineage_guard.demo import BILLING, DEMOGRAPHICS, RAW, STAGING


def result(payload, *, is_error=False):
    return SimpleNamespace(structuredContent=payload, content=[], isError=is_error)


class FakeSession:
    def __init__(self, *, mutations=True) -> None:
        names = ["get_lineage", "get_entities"]
        if mutations:
            names.extend(["update_description", "add_tags"])
        self.tools = SimpleNamespace(tools=[SimpleNamespace(name=name) for name in names])
        self.calls = []

    async def list_tools(self):
        return self.tools

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_lineage":
            return result(
                {
                    "downstreams": {
                        "searchResults": [
                            {"entity": {"urn": STAGING}, "degree": 1},
                            {"entity": {"urn": BILLING}, "degree": 2},
                            {"entity": {"urn": DEMOGRAPHICS}, "degree": 2},
                        ]
                    }
                }
            )
        if name == "get_entities":
            return result([entity(urn) for urn in arguments["urns"]])
        return result({"success": True})


def entity(urn):
    name = urn.split(",")[1].split(".")[-1]
    return {
        "urn": urn,
        "properties": {"name": name, "description": f"{name} billing data"},
        "ownership": {"owners": []},
        "globalTags": {"tags": []},
    }


@pytest.mark.asyncio
async def test_loads_normalized_snapshot_from_official_tools() -> None:
    session = FakeSession()

    graph = await DataHubMcpGraph.load(session, RAW)

    assert graph.get_asset(BILLING).name == "mart_billing"
    assert [(item.urn, item.distance) for item in graph.get_downstream_lineage(RAW, 5)] == [
        (STAGING, 1),
        (BILLING, 2),
        (DEMOGRAPHICS, 2),
    ]


@pytest.mark.asyncio
async def test_flush_uses_official_mutation_contracts() -> None:
    session = FakeSession()
    graph = await DataHubMcpGraph.load(session, RAW)
    graph.append_incident_summary(RAW, "summary")
    graph.add_tag(BILLING, "urn:li:tag:LineageGuard_Quarantined")

    await graph.flush()

    assert (
        "update_description",
        {"entity_urn": RAW, "operation": "append", "description": "summary"},
    ) in session.calls
    assert (
        "add_tags",
        {
            "tag_urns": ["urn:li:tag:LineageGuard_Quarantined"],
            "entity_urns": [BILLING],
        },
    ) in session.calls


@pytest.mark.asyncio
async def test_flush_fails_closed_when_mutations_are_disabled() -> None:
    session = FakeSession(mutations=False)
    graph = await DataHubMcpGraph.load(session, RAW)
    graph.append_incident_summary(RAW, "summary")

    with pytest.raises(McpIntegrationError, match="Mutation tools are unavailable"):
        await graph.flush()


def test_rejects_oversized_tool_payload() -> None:
    oversized = {"value": "x" * MAX_TOOL_PAYLOAD_BYTES}

    with pytest.raises(McpIntegrationError, match="exceeds the safety limit"):
        _tool_payload(result(oversized))
