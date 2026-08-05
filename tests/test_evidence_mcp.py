import asyncio
import builtins
import json
import runpy
import sys
import warnings

import pytest

from lineage_guard import evidence_mcp
from lineage_guard.evidence_chain import sign_record
from lineage_guard.evidence_service import EvidenceQueryService
from lineage_guard.immune_memory import ImmuneMemoryRecord, MemoryRecordType


def _payload(result):
    if isinstance(result, tuple):
        return result[1]
    return json.loads(result[0].text)


def _record() -> ImmuneMemoryRecord:
    return ImmuneMemoryRecord.create(
        MemoryRecordType.INCIDENT, "urn:li:dataset:evidence", "incident", {}
    )


def test_service_verifies_chain_state_and_attestation() -> None:
    record = _record()
    service = EvidenceQueryService()
    bundle = [record.as_dict()]
    assert service.verify_chain(bundle)["valid"] is True
    assert service.get_record_state(bundle, record.record_digest)["state"] == "active"
    attestation = sign_record(record, key_id="test", secret=b"a" * 32)
    result = service.verify_detached_attestation(attestation.as_dict(), "a" * 32)
    assert result == {"record_digest": record.record_digest, "key_id": "test", "valid": True}


def test_service_rejects_invalid_inputs_and_queries() -> None:
    service = EvidenceQueryService()
    record = _record()
    with pytest.raises(ValueError, match="array"):
        service.verify_chain("not-an-array")
    with pytest.raises(ValueError, match="verification"):
        service.get_record_state([{**record.as_dict(), "record_digest": "bad"}], "bad")
    invalid_root = ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME,
        "urn:li:dataset:evidence",
        "incident",
        {},
    )
    with pytest.raises(ValueError, match="invalid"):
        service.get_record_state([invalid_root.as_dict()], invalid_root.record_digest)
    with pytest.raises(KeyError, match="absent"):
        service.get_record_state([record.as_dict()], "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="object"):
        service.verify_detached_attestation("bad", "a" * 32)
    with pytest.raises(ValueError, match="text"):
        service.verify_detached_attestation({}, 123)
    with pytest.raises(ValueError, match="malformed"):
        service.verify_detached_attestation({}, "a" * 32)


def test_server_registers_and_executes_read_only_tools(monkeypatch) -> None:
    record = _record()
    secret = "a" * 32
    monkeypatch.setenv("LINEAGE_GUARD_ATTESTATION_SECRET", secret)
    attestation = sign_record(record, key_id="test", secret=secret.encode())
    server = evidence_mcp.create_server()
    assert {tool.name for tool in asyncio.run(server.list_tools())} == {
        "verify_evidence_chain",
        "get_evidence_state",
        "verify_detached_attestation",
    }
    records = [record.as_dict()]
    verified = _payload(
        asyncio.run(server.call_tool("verify_evidence_chain", {"records": records}))
    )
    state = _payload(
        asyncio.run(
            server.call_tool(
                "get_evidence_state",
                {
                    "records": records,
                    "record_digest": record.record_digest,
                },
            )
        )
    )
    signed = _payload(
        asyncio.run(
            server.call_tool(
                "verify_detached_attestation",
                {
                    "attestation": attestation.as_dict(),
                },
            )
        )
    )
    assert verified["valid"] and state["state"] == "active" and signed["valid"]


def test_server_requires_attestation_secret(monkeypatch) -> None:
    monkeypatch.delenv("LINEAGE_GUARD_ATTESTATION_SECRET", raising=False)
    record = _record()
    attestation = sign_record(record, key_id="test", secret=b"a" * 32)
    server = evidence_mcp.create_server()
    with pytest.raises(Exception, match="LINEAGE_GUARD_ATTESTATION_SECRET"):
        asyncio.run(
            server.call_tool("verify_detached_attestation", {"attestation": attestation.as_dict()})
        )


def test_main_and_missing_extra(monkeypatch) -> None:
    class Server:
        def run(self, *, transport):
            assert transport == "stdio"

    original_create = evidence_mcp.create_server
    monkeypatch.setattr(evidence_mcp, "create_server", lambda: Server())
    assert evidence_mcp.main() == 0
    with pytest.raises(SystemExit, match="accepts no"):
        evidence_mcp.main(["unexpected"])

    original_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match=r"lineage-guard\[mcp\]"):
        original_create()


def test_executable_entrypoint(monkeypatch) -> None:
    from mcp.server.fastmcp import FastMCP

    monkeypatch.setattr(FastMCP, "run", lambda self, *, transport: None)
    monkeypatch.setattr(sys, "argv", ["lineage-guard-evidence-mcp"])
    with warnings.catch_warnings(), pytest.raises(SystemExit) as error:
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("lineage_guard.evidence_mcp", run_name="__main__")
    assert error.value.code == 0
