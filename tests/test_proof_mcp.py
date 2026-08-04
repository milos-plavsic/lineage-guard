import asyncio
import builtins
import json
import runpy
import sys
import warnings

import pytest

from lineage_guard import proof_mcp


def payload(result):
    if isinstance(result, tuple):
        return result[1]
    return json.loads(result[0].text)


def test_server_registers_and_executes_five_read_only_tools() -> None:
    server = proof_mcp.create_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "explain_decision",
        "get_causal_cut",
        "find_evidence_gaps",
        "simulate_context_change",
        "verify_proof_bundle",
    }
    decisions = proof_mcp.ProofQueryService().graph.causal_cuts
    decision_id = decisions[0].decision_node_id
    explanation = payload(
        asyncio.run(server.call_tool("explain_decision", {"decision_node_id": decision_id}))
    )
    cut = payload(
        asyncio.run(server.call_tool("get_causal_cut", {"decision_node_id": decision_id}))
    )
    gaps = payload(asyncio.run(server.call_tool("find_evidence_gaps", {"limit": 1})))
    evidence_id = explanation["counterfactuals"][0]["evidence_node_id"]
    simulation = payload(
        asyncio.run(
            server.call_tool(
                "simulate_context_change",
                {"decision_node_id": decision_id, "evidence_node_id": evidence_id},
            )
        )
    )
    verification = payload(asyncio.run(server.call_tool("verify_proof_bundle", {})))
    assert cut["size"] and gaps and simulation["resulting_action"]
    assert verification["valid"] is True


def test_main_runs_stdio_and_rejects_arguments(monkeypatch) -> None:
    class Server:
        def run(self, *, transport):
            assert transport == "stdio"

    monkeypatch.setattr(proof_mcp, "create_server", lambda: Server())
    assert proof_mcp.main() == 0
    with pytest.raises(SystemExit, match="accepts no"):
        proof_mcp.main(["unexpected"])


def test_missing_mcp_extra_has_clear_error(monkeypatch) -> None:
    original_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match=r"lineage-guard\[mcp\]"):
        proof_mcp.create_server()


def test_executable_entrypoint(monkeypatch) -> None:
    from mcp.server.fastmcp import FastMCP

    monkeypatch.setattr(FastMCP, "run", lambda self, *, transport: None)
    monkeypatch.setattr(sys, "argv", ["lineage-guard-proof-mcp"])
    with warnings.catch_warnings(), pytest.raises(SystemExit) as error:
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("lineage_guard.proof_mcp", run_name="__main__")
    assert error.value.code == 0
