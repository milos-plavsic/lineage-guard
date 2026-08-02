from types import SimpleNamespace

import pytest

from lineage_guard.adapters.mcp import (
    MAX_TOOL_PAYLOAD_BYTES,
    DataHubMcpGraph,
    McpIntegrationError,
    _bounded_lineage_results,
    _schema_field_urn,
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
            if arguments["urn"].startswith("urn:li:schemaField:"):
                return result(
                    {
                        "downstreams": {
                            "searchResults": [
                                {"entity": {"urn": BILLING}, "degree": 2},
                            ]
                        }
                    }
                )
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
async def test_loads_field_lineage_as_positive_dependency_evidence() -> None:
    session = FakeSession()

    graph = await DataHubMcpGraph.load(session, RAW, source_field="billing_amount")

    targets = graph.get_downstream_lineage(RAW, 5, field="billing_amount")
    dependencies = {target.urn: target.dependent_fields for target in targets}
    assert dependencies[BILLING] == ("billing_amount",)
    assert dependencies[DEMOGRAPHICS] == ()
    assert any(
        arguments["urn"] == _schema_field_urn(RAW, "billing_amount")
        for name, arguments in session.calls
        if name == "get_lineage"
    )


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


@pytest.mark.asyncio
async def test_load_rejects_missing_read_tools() -> None:
    session = FakeSession()
    session.tools.tools = []

    with pytest.raises(McpIntegrationError, match="missing tools"):
        await DataHubMcpGraph.load(session, RAW)


@pytest.mark.asyncio
async def test_load_rejects_incomplete_entity_context() -> None:
    session = FakeSession()
    original = session.call_tool

    async def incomplete(name, arguments):
        if name == "get_entities":
            return result([entity(RAW)])
        return await original(name, arguments)

    session.call_tool = incomplete
    with pytest.raises(McpIntegrationError, match="incomplete entity context"):
        await DataHubMcpGraph.load(session, RAW)


@pytest.mark.asyncio
async def test_mutation_failure_is_reported() -> None:
    session = FakeSession()
    graph = await DataHubMcpGraph.load(session, RAW)
    graph.append_incident_summary(RAW, "summary")
    original = session.call_tool

    async def failing(name, arguments):
        if name == "update_description":
            return result({}, is_error=True)
        return await original(name, arguments)

    session.call_tool = failing
    with pytest.raises(McpIntegrationError, match="mutation failed"):
        await graph.flush()

    session.call_tool = original
    graph.append_incident_summary(RAW, "summary")
    await graph.flush()
    assert sum(name == "update_description" for name, _ in session.calls) == 1

    graph.append_incident_summary(RAW, "summary")
    await graph.flush()
    assert sum(name == "update_description" for name, _ in session.calls) == 1


def test_lineage_bounds_and_schema_field_urn_fail_closed() -> None:
    with pytest.raises(McpIntegrationError, match="truncated"):
        _bounded_lineage_results({"downstreams": {"searchResults": [], "total": 1}}, 100)
    with pytest.raises(McpIntegrationError, match="may be truncated"):
        _bounded_lineage_results(
            {"downstreams": {"searchResults": [{"entity": {"urn": RAW}, "degree": 1}]}},
            1,
        )
    with pytest.raises(McpIntegrationError, match="malformed lineage"):
        _bounded_lineage_results({"downstreams": {"searchResults": ["bad"]}}, 100)
    with pytest.raises(McpIntegrationError, match="schema-field URN"):
        _schema_field_urn(RAW, "bad,field")
    with pytest.raises(McpIntegrationError, match="schema-field URN"):
        _schema_field_urn(RAW, "")
    assert _bounded_lineage_results(None, 100) == []


def test_text_payload_requires_valid_bounded_json() -> None:
    text_result = SimpleNamespace(
        structuredContent=None,
        content=[SimpleNamespace(text='{"result":{"ok":true}}')],
        isError=False,
    )
    assert _tool_payload(text_result) == {"result": {"ok": True}}

    text_result.content = [SimpleNamespace(text="not-json")]
    with pytest.raises(McpIntegrationError, match="invalid JSON"):
        _tool_payload(text_result)

    text_result.content = []
    with pytest.raises(McpIntegrationError, match="no structured"):
        _tool_payload(text_result)


def test_tag_and_snapshot_lookups_validate_inputs() -> None:
    graph = DataHubMcpGraph(FakeSession(), {}, ())
    with pytest.raises(ValueError, match="tag URNs"):
        graph.add_tag(RAW, "quarantined")
    with pytest.raises(LookupError, match="not present"):
        graph.get_asset(RAW)
