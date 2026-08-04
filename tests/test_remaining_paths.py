import argparse
import builtins
import json
import runpy
import sys
import threading
import warnings
from contextlib import asynccontextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from lineage_guard import cli, web
from lineage_guard.adapters.mcp import (
    MAX_TOOL_PAYLOAD_BYTES,
    DataHubMcpGraph,
    McpIntegrationError,
    StdioMcpConfig,
    _asset,
    _lineage_target,
    _tool_payload,
    open_stdio_session,
)
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import RAW, assets, edges, negative_billing_signal
from lineage_guard.domain import Asset, LineageEdge, LineageTarget, QualitySignal, Severity
from lineage_guard.remediation import GeneratedArtifact, RemediationGenerator
from lineage_guard.service import IncidentAnalyzer
from scripts import audit_submission, export_static_demo, fetch_healthcare


def test_mcp_config_and_payload_variants(monkeypatch) -> None:
    monkeypatch.setenv("PRESERVED", "yes")
    environment = StdioMcpConfig("http://gms", "secret", enable_mutations=True).environment()
    assert "PRESERVED" not in environment
    assert environment["TOOLS_IS_MUTATION_ENABLED"] == "true"

    with pytest.raises(McpIntegrationError, match="returned an error"):
        _tool_payload(SimpleNamespace(isError=True))
    assert _tool_payload(SimpleNamespace(isError=False, structuredContent={"result": 3})) == 3
    large = SimpleNamespace(
        isError=False,
        structuredContent=None,
        content=[SimpleNamespace(text="x" * (MAX_TOOL_PAYLOAD_BYTES + 1))],
    )
    with pytest.raises(McpIntegrationError, match="textual payload"):
        _tool_payload(large)


def test_mcp_normalizers_cover_rich_and_invalid_entities() -> None:
    assert _lineage_target({"entity": {"urn": RAW}, "degree": "3+"}).distance == 3
    with pytest.raises(McpIntegrationError, match="Malformed"):
        _lineage_target({"entity": {}, "degree": None})
    with pytest.raises(McpIntegrationError, match="missing its URN"):
        _asset({})
    rich = _asset(
        {
            "urn": RAW,
            "name": "fallback",
            "description": "description",
            "ownership": {
                "owners": [
                    {"owner": {"properties": {"displayName": "Display"}}},
                    {"owner": {"properties": {"name": "Name"}}},
                    {"owner": {"urn": "urn:owner"}},
                ]
            },
            "globalTags": {
                "tags": [
                    {"tag": {"properties": {"name": "Critical"}}},
                    {"tag": {"urn": "urn:li:tag:Fallback"}},
                ]
            },
            "usageStats": {"totalQueries": "12"},
        }
    )
    assert rich.owners == ("Display", "Name", "urn:owner")
    assert rich.tags == ("Critical", "urn:li:tag:Fallback")
    assert rich.usage_count == 12


@pytest.mark.asyncio
async def test_mcp_graph_count_filter_and_empty_flush() -> None:
    class Session:
        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name="get_lineage"), SimpleNamespace(name="get_entities")]
            )

        async def call_tool(self, name, arguments):
            del arguments
            if name == "get_lineage":
                return SimpleNamespace(
                    isError=False, structuredContent={"downstreams": {"searchResults": "bad"}}
                )
            raise AssertionError

    with pytest.raises(McpIntegrationError, match="invalid lineage result count"):
        await DataHubMcpGraph.load(Session(), RAW)
    graph = DataHubMcpGraph(Session(), {RAW: Asset(RAW, "raw", "")}, (LineageTarget(RAW, 3),))
    assert graph.get_downstream_lineage(RAW, 2) == ()
    await graph.flush()


@pytest.mark.asyncio
async def test_open_stdio_session_success_and_oserror(monkeypatch) -> None:
    initialized = []

    class Parameters:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Session:
        def __init__(self, reader, writer):
            self.values = (reader, writer)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            initialized.append(True)

    @asynccontextmanager
    async def transport(parameters):
        assert parameters.kwargs["args"] == ["mcp-server-datahub@0.6.0"]
        yield "reader", "writer"

    monkeypatch.setattr("mcp.StdioServerParameters", Parameters)
    monkeypatch.setattr("mcp.ClientSession", Session)
    monkeypatch.setattr("mcp.client.stdio.stdio_client", transport)
    async with open_stdio_session(StdioMcpConfig("url", "token")) as session:
        assert session.values == ("reader", "writer")
    assert initialized

    @asynccontextmanager
    async def broken(parameters):
        del parameters
        raise OSError("boom")
        yield

    monkeypatch.setattr("mcp.client.stdio.stdio_client", broken)
    with pytest.raises(McpIntegrationError, match="Could not start"):
        async with open_stdio_session(StdioMcpConfig("url", "token")):
            pass


@pytest.mark.asyncio
async def test_open_stdio_session_reports_missing_optional_dependency(monkeypatch) -> None:
    original_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp.client"):
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(McpIntegrationError, match="MCP support is not installed"):
        async with open_stdio_session(StdioMcpConfig("url", "token")):
            pass


def test_audit_helpers_and_entrypoint(tmp_path, monkeypatch, capsys) -> None:
    completed = SimpleNamespace(stdout="")
    with patch("scripts.audit_submission.subprocess.run", return_value=completed):
        assert audit_submission._clean_worktree(tmp_path)
        assert not audit_submission._created_in_submission_period(tmp_path)
    completed.stdout = "dirty\n"
    with patch("scripts.audit_submission.subprocess.run", return_value=completed):
        assert not audit_submission._clean_worktree(tmp_path)
    completed.stdout = "2025-01-01T00:00:00+00:00\n"
    with patch("scripts.audit_submission.subprocess.run", return_value=completed):
        assert not audit_submission._created_in_submission_period(tmp_path)
    with patch("scripts.audit_submission.subprocess.run", side_effect=OSError):
        assert not audit_submission._created_in_submission_period(tmp_path)
    monkeypatch.setattr(
        audit_submission, "audit", lambda root: (audit_submission.Check("x", True, "e"),)
    )
    monkeypatch.setattr(sys, "argv", ["audit", "--root", str(tmp_path)])
    assert audit_submission.main() == 0
    assert "PASS" in capsys.readouterr().out


def test_script_mains(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["export", str(tmp_path / "site")])
    assert export_static_demo.main() == 0
    assert "schemaVersion" in capsys.readouterr().out
    monkeypatch.setattr(
        fetch_healthcare,
        "download_fixture",
        lambda destination, metadata_only=False: {"ok": metadata_only},
    )
    monkeypatch.setattr(sys, "argv", ["fetch", "--destination", str(tmp_path), "--metadata-only"])
    assert fetch_healthcare.main() == 0
    assert '"ok": true' in capsys.readouterr().out


def test_service_empty_summary_and_escape_guard(tmp_path, monkeypatch) -> None:
    graph = InMemoryMetadataGraph((assets()[0],), ())
    report = IncidentAnalyzer(graph).analyze(negative_billing_signal())
    assert "Branch decisions: none" in report.proposed_writeback["append_description"]["markdown"]
    generator = RemediationGenerator()
    monkeypatch.setattr(
        generator,
        "generate",
        lambda report, recovery=None, chronos=None, proofgraph=None, proof_bundle=None: (
            GeneratedArtifact.create("../escape", "x"),
        ),
    )
    with pytest.raises(ValueError, match="escapes destination"):
        generator.write(report, tmp_path)


def test_monitor_decision_and_cyclic_memory_graph() -> None:
    source = Asset("source", "source", "")
    target = Asset("target", "billing", "billing")
    graph = InMemoryMetadataGraph(
        (source, target),
        (LineageEdge("source", "target"), LineageEdge("target", "source")),
    )
    signal = QualitySignal("source", "field", "rule", "observed", Severity.LOW, ("billing",))
    report = IncidentAnalyzer(graph).analyze(signal, max_hops=2)
    assert report.decisions[0].action.value == "monitor"
    assert graph.get_downstream_lineage("source", 1) == (LineageTarget("target", 1),)


def test_web_main_normal_and_keyboard_interrupt(monkeypatch) -> None:
    class Server:
        def __init__(self, address, handler):
            self.address = address
            self.handler = handler

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    monkeypatch.setattr(web, "LineageGuardServer", Server)
    monkeypatch.setattr(sys, "argv", ["web", "--port", "8765"])
    assert web.main() == 0


def test_web_internal_error_is_sanitized(monkeypatch) -> None:
    def broken(self):
        raise ValueError("sensitive detail")

    monkeypatch.setattr(web.LineageGuardHandler, "_handle_get", broken)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.LineageGuardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2)
        assert error.value.code == 500
        assert json.load(error.value) == {"error": "internal_error"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_mcp_cli_complete_flow(tmp_path, monkeypatch, capsys) -> None:
    class Graph(InMemoryMetadataGraph):
        async def flush(self):
            self.flushed = True

    graph = Graph(assets(), edges())

    configs = []

    @asynccontextmanager
    async def session(config):
        configs.append(config)
        yield object()

    async def load(session_value, source_urn, *, source_field=None):
        assert session_value is not None and source_urn == RAW
        assert source_field == "billing_amount"
        return graph

    monkeypatch.setattr(cli, "open_stdio_session", session)
    monkeypatch.setattr(cli.DataHubMcpGraph, "load", load)
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "token")
    monkeypatch.setenv("LINEAGE_GUARD_ENFORCEMENT_SECRET", "x" * 32)
    enforced = []
    monkeypatch.setattr(
        cli.SignedWebhookEnforcer,
        "enforce",
        lambda self, report: enforced.append(report.incident_id),
    )
    output = tmp_path / "report.json"
    artifacts = tmp_path / "artifacts"
    args = argparse.Namespace(
        gms_url="http://gms",
        source_urn=RAW,
        apply=True,
        field="billing_amount",
        concerns=["billing"],
        artifacts_dir=artifacts,
        output=output,
        enforcement_webhook="http://localhost/hook",
    )
    assert await cli._run_mcp(args) == 0
    assert configs[-1].enable_mutations is True
    assert output.is_file() and (artifacts / "manifest.json").is_file()
    assert graph.flushed
    assert enforced
    assert "incident_id" in capsys.readouterr().out

    args.apply = False
    args.concerns = None
    args.artifacts_dir = None
    args.output = None
    args.enforcement_webhook = None
    assert await cli._run_mcp(args) == 0
    assert configs[-1].enable_mutations is False

    args.apply = True
    assert await cli._run_mcp(args) == 0


def test_demo_cli_without_optional_outputs(capsys) -> None:
    assert cli.main([]) == 0
    assert "incident_id" in capsys.readouterr().out


def test_executable_entrypoints(monkeypatch, tmp_path) -> None:
    cases = [
        ("scripts.export_static_demo", ["export", str(tmp_path / "site")], 0),
        ("scripts.fetch_healthcare", ["fetch", "--metadata-only"], 0),
        ("scripts.audit_submission", ["audit", "--root", str(Path.cwd())], 1),
        ("lineage_guard.cli", ["lineage-guard", "--output", str(tmp_path / "report.json")], 0),
        ("lineage_guard.web", ["web", "--port", "0"], "--port must be between 1 and 65535"),
    ]
    monkeypatch.setattr(fetch_healthcare, "download_fixture", lambda *args, **kwargs: {})
    for module, argv, code in cases:
        monkeypatch.setattr(sys, "argv", argv)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with pytest.raises(SystemExit) as error:
                runpy.run_module(module, run_name="__main__")
        assert error.value.code == code
