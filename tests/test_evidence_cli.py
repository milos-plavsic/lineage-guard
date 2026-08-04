import argparse
import json
from contextlib import asynccontextmanager

import pytest

import lineage_guard.cli as cli
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import RAW, assets, edges
from lineage_guard.immune_memory import ImmuneMemoryRecord, MemoryRecordType


def arguments(tmp_path, action: str, *, apply: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        gms_url="http://gms",
        source_urn=RAW,
        evidence_action=action,
        apply=apply,
        record_digest=None,
        replacement_digest=None,
        reason=None,
        effective_at=None,
        attestation_key_id=None,
        output=tmp_path / f"{action}.json",
    )


@pytest.fixture
def evidence_graph() -> InMemoryMetadataGraph:
    graph = InMemoryMetadataGraph(assets(), edges())
    graph.append_immune_memory(
        RAW, ImmuneMemoryRecord.create(MemoryRecordType.INCIDENT, RAW, "incident", {})
    )
    return graph


@pytest.fixture
def mcp(monkeypatch, evidence_graph):
    approvals = []

    @asynccontextmanager
    async def session(config):
        approvals.append(config.enable_mutations)
        yield object()

    async def load(*args, **kwargs):
        return evidence_graph

    monkeypatch.setattr(cli, "open_stdio_session", session)
    monkeypatch.setattr(cli.DataHubMcpGraph, "load", load)
    return approvals


@pytest.mark.asyncio
async def test_verify_chain_is_read_only(tmp_path, mcp) -> None:
    args = arguments(tmp_path, "verify")
    assert await cli._run_evidence_action(args, "token") == 0
    payload = json.loads(args.output.read_text())
    assert payload["status"] == "verified"
    assert payload["chain_verification"]["valid"] is True
    assert payload["execution_context"]["mutations_applied"] is False
    assert mcp == [False]
    args.output = None
    assert await cli._run_evidence_action(args, "token") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "record_type"),
    [("expire", "expiry"), ("revoke", "revocation")],
)
async def test_lifecycle_action_writes_immutable_child(
    tmp_path, evidence_graph, mcp, action, record_type
) -> None:
    root = evidence_graph.get_immune_memories(RAW)[0]
    args = arguments(tmp_path, action, apply=True)
    args.record_digest = root.record_digest
    args.reason = "governed lifecycle transition"
    args.effective_at = "2026-08-05T00:00:00Z"
    assert await cli._run_evidence_action(args, "token") == 0
    payload = json.loads(args.output.read_text())
    assert payload["status"] == "written"
    assert payload["lifecycle_record"]["record_type"] == record_type
    assert payload["lifecycle_record"]["parent_digest"] == root.record_digest
    assert mcp == [True]


@pytest.mark.asyncio
async def test_supersession_and_attestation(tmp_path, evidence_graph, mcp, monkeypatch) -> None:
    root = evidence_graph.get_immune_memories(RAW)[0]
    replacement = ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME,
        RAW,
        root.incident_id,
        {},
        parent_digest=root.record_digest,
    )
    evidence_graph.append_immune_memory(RAW, replacement)
    args = arguments(tmp_path, "supersede", apply=True)
    args.record_digest = root.record_digest
    args.replacement_digest = replacement.record_digest
    args.reason = "replacement proof"
    args.effective_at = "2026-08-05T00:00:00Z"
    assert await cli._run_evidence_action(args, "token") == 0

    monkeypatch.setenv("LINEAGE_GUARD_ATTESTATION_SECRET", "a" * 32)
    attest = arguments(tmp_path, "attest")
    attest.record_digest = replacement.record_digest
    attest.attestation_key_id = "operator-key"
    assert await cli._run_evidence_action(attest, "token") == 0
    payload = json.loads(attest.output.read_text())
    assert payload["status"] == "attested"
    assert payload["attestation"]["key_id"] == "operator-key"


@pytest.mark.asyncio
async def test_evidence_actions_fail_closed(tmp_path, mcp) -> None:
    args = arguments(tmp_path, "expire")
    with pytest.raises(SystemExit, match="--apply"):
        await cli._run_evidence_action(args, "token")
    read_only = arguments(tmp_path, "verify", apply=True)
    with pytest.raises(SystemExit, match="not valid"):
        await cli._run_evidence_action(read_only, "token")
    args.apply = True
    args.record_digest = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="not found"):
        await cli._run_evidence_action(args, "token")
    args.gms_url = None
    with pytest.raises(SystemExit, match="require"):
        await cli._run_evidence_action(args, "token")


@pytest.mark.asyncio
async def test_evidence_action_rejects_invalid_chain(tmp_path, evidence_graph, mcp) -> None:
    evidence_graph.append_immune_memory(
        RAW,
        ImmuneMemoryRecord.create(
            MemoryRecordType.PREVENTION_OUTCOME,
            RAW,
            "incident",
            {},
            parent_digest="sha256:" + "f" * 64,
        ),
    )
    with pytest.raises(ValueError, match="chain verification"):
        await cli._run_evidence_action(arguments(tmp_path, "verify"), "token")


def test_main_dispatches_evidence_action(monkeypatch) -> None:
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "token")

    async def action(args, token):
        assert args.evidence_action == "verify" and token == "token"
        return 7

    monkeypatch.setattr(cli, "_run_evidence_action", action)
    assert (
        cli.main(
            [
                "--mode",
                "mcp",
                "--gms-url",
                "http://gms",
                "--source-urn",
                RAW,
                "--evidence-action",
                "verify",
            ]
        )
        == 7
    )
