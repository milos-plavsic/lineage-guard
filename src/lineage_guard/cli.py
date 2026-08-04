from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from lineage_guard.adapters.mcp import DataHubMcpGraph, StdioMcpConfig, open_stdio_session
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import build_chronos, build_demo_chronos, load_context_changes
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.domain import QualitySignal, Severity
from lineage_guard.enforcement import SignedWebhookConfig, SignedWebhookEnforcer
from lineage_guard.events import load_quality_event
from lineage_guard.immune_memory import build_incident_memory
from lineage_guard.proofgraph import build_demo_proofgraph, load_radar_weights
from lineage_guard.recovery import (
    CounterfactualRecoveryLab,
    demo_recovery_scenario,
    load_recovery_scenario,
)
from lineage_guard.remediation import RemediationGenerator
from lineage_guard.service import IncidentAnalyzer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lineage-guard",
        description="Analyze DataHub lineage and propose selective incident containment.",
    )
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path.")
    parser.add_argument(
        "--mode", choices=("demo", "mcp"), default="demo", help="Metadata source to use."
    )
    parser.add_argument(
        "--enforcement-webhook",
        help="Approved orchestrator endpoint; requires --apply and a secret environment variable.",
    )
    parser.add_argument("--gms-url", help="DataHub GMS URL for MCP mode.")
    parser.add_argument("--source-urn", help="Source dataset URN for MCP mode.")
    parser.add_argument(
        "--signal-file",
        help="Read a versioned quality event from this JSON file, or '-' for standard input.",
    )
    parser.add_argument(
        "--artifacts-dir", type=Path, help="Write reviewable remediation artifacts here."
    )
    parser.add_argument(
        "--recovery-lab",
        action="store_true",
        help="Run the deterministic counterfactual recovery lab (demo mode only).",
    )
    parser.add_argument(
        "--chronos",
        action="store_true",
        help="Compile recovery proof into temporal immunity controls (demo mode only).",
    )
    parser.add_argument(
        "--proofgraph",
        action="store_true",
        help="Build causal proofs, ranked evidence gaps, and a portable Proof Bundle.",
    )
    parser.add_argument(
        "--recovery-scenario-file",
        type=Path,
        help="Bounded trusted/current evidence required for non-demo recovery.",
    )
    parser.add_argument(
        "--changes-file",
        type=Path,
        help="Bounded typed changes required for non-demo Chronos and ProofGuard.",
    )
    parser.add_argument(
        "--radar-weights-file",
        type=Path,
        help="Optional versioned Evidence Gap Radar weights; defaults remain explicit.",
    )
    parser.add_argument("--field", default="billing_amount", help="Failing field name.")
    parser.add_argument(
        "--concern",
        action="append",
        dest="concerns",
        help="Affected business concern; repeat for multiple values.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply proposed metadata mutations (demo adapter only in this milestone).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "mcp":
        return asyncio.run(_run_mcp(args))
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    analyzer = IncidentAnalyzer(graph)
    report = analyzer.analyze(negative_billing_signal())
    scenario = (
        load_recovery_scenario(args.recovery_scenario_file)
        if args.recovery_scenario_file
        else demo_recovery_scenario()
    )
    recovery = (
        CounterfactualRecoveryLab().evaluate(report, scenario)
        if (args.recovery_lab or args.chronos or args.proofgraph)
        else None
    )
    chronos = (
        (
            build_chronos(report, recovery, scenario, load_context_changes(args.changes_file))
            if args.changes_file
            else build_demo_chronos(report, recovery)
        )
        if (args.chronos or args.proofgraph) and recovery
        else None
    )
    proofgraph, proof_bundle = (
        build_demo_proofgraph(
            report,
            recovery,
            chronos,
            load_radar_weights(args.radar_weights_file) if args.radar_weights_file else None,
        )
        if args.proofgraph and recovery and chronos
        else (None, None)
    )
    if args.artifacts_dir:
        RemediationGenerator().write(
            report, args.artifacts_dir, recovery, chronos, proofgraph, proof_bundle
        )
    if args.apply:
        analyzer.apply_writeback(report, approved=True)
    payload = report.as_dict()
    payload["execution_context"] = {
        "mode": "deterministic_fixture",
        "metadata_source": "application_owned_fixture",
        "live_datahub_connected": False,
        "mutations_applied": bool(args.apply),
    }
    if recovery is not None:
        payload["recovery"] = recovery.as_dict()
    if chronos is not None:
        payload["chronos"] = chronos.as_dict()
    if proofgraph is not None and proof_bundle is not None:
        payload["proofgraph"] = proofgraph.as_dict()
        payload["proof_bundle"] = asdict(proof_bundle)
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


async def _run_mcp(args: argparse.Namespace) -> int:
    recovery_lab = getattr(args, "recovery_lab", False)
    chronos_requested = getattr(args, "chronos", False)
    proofgraph_requested = getattr(args, "proofgraph", False)
    scenario_file = getattr(args, "recovery_scenario_file", None)
    changes_file = getattr(args, "changes_file", None)
    radar_weights_file = getattr(args, "radar_weights_file", None)
    full_requested = recovery_lab or chronos_requested or proofgraph_requested
    if full_requested and not scenario_file:
        raise SystemExit("live recovery requires --recovery-scenario-file")
    if (chronos_requested or proofgraph_requested) and not changes_file:
        raise SystemExit("live Chronos and ProofGuard require --changes-file")
    token = os.environ.get("DATAHUB_GMS_TOKEN")
    signal_file = getattr(args, "signal_file", None)
    event = load_quality_event(signal_file) if signal_file else None
    source_urn = event.signal.asset_urn if event else args.source_urn
    if event and args.source_urn and args.source_urn != source_urn:
        raise SystemExit("--source-urn does not match the quality event source URN.")
    if not args.gms_url or not source_urn or not token:
        raise SystemExit(
            "MCP mode requires --gms-url, a source URN or --signal-file, and DATAHUB_GMS_TOKEN."
        )
    config = StdioMcpConfig(args.gms_url, token, enable_mutations=args.apply)
    webhook = getattr(args, "enforcement_webhook", None)
    if webhook and not args.apply:
        raise SystemExit("--enforcement-webhook requires --apply approval.")
    enforcement_secret = os.environ.get("LINEAGE_GUARD_ENFORCEMENT_SECRET")
    if webhook and not enforcement_secret:
        raise SystemExit("--enforcement-webhook requires LINEAGE_GUARD_ENFORCEMENT_SECRET.")
    signal = (
        event.signal
        if event
        else QualitySignal(
            asset_urn=source_urn,
            field=args.field,
            rule="quality assertion failed",
            observed="failure reported by the incident trigger",
            severity=Severity.HIGH,
            affected_concerns=tuple(args.concerns or [args.field]),
        )
    )
    async with open_stdio_session(config) as session:
        graph = await DataHubMcpGraph.load(session, source_urn, source_field=signal.field)
        analyzer = IncidentAnalyzer(graph)
        report = analyzer.analyze(signal)
        lineage_read = graph.read_downstream_lineage(source_urn, 5, field=signal.field)
        recovery = None
        chronos = None
        proofgraph = None
        proof_bundle = None
        if full_requested:
            scenario = load_recovery_scenario(scenario_file)
            recovery = CounterfactualRecoveryLab().evaluate(report, scenario)
            if chronos_requested or proofgraph_requested:
                chronos = build_chronos(
                    report,
                    recovery,
                    scenario,
                    load_context_changes(changes_file),
                )
            if proofgraph_requested and chronos:
                proofgraph, proof_bundle = build_demo_proofgraph(
                    report,
                    recovery,
                    chronos,
                    load_radar_weights(radar_weights_file) if radar_weights_file else None,
                )
        if args.artifacts_dir:
            RemediationGenerator().write(
                report,
                args.artifacts_dir,
                recovery,
                chronos,
                proofgraph,
                proof_bundle,
            )
        evidence_gaps = (
            tuple(asdict(item) for item in proofgraph.evidence_gaps) if proofgraph else ()
        )
        memory = build_incident_memory(
            report,
            lineage_read,
            event_id=event.event_id if event else None,
            occurred_at=event.occurred_at if event else None,
            genome=chronos.genome if chronos else None,
            evidence_gaps=evidence_gaps,
        )
        if args.apply:
            if webhook:
                enforcer = SignedWebhookEnforcer(
                    SignedWebhookConfig(webhook, enforcement_secret or "")
                )
                await asyncio.to_thread(enforcer.enforce, report)
            analyzer.apply_writeback(report, approved=True)
            graph.append_immune_memory(source_urn, memory)
            await graph.flush()
    payload = report.as_dict()
    payload["lineage_read_receipt"] = lineage_read.receipt.as_dict()
    payload["immune_memory"] = memory.as_dict()
    payload["execution_context"] = {
        "mode": "live_mcp",
        "metadata_source": "datahub_mcp",
        "live_datahub_connected": True,
        "mutations_applied": bool(args.apply),
        "recovery_evidence_source": (
            "operator_supplied_bounded_file" if recovery else "not_supplied"
        ),
        "change_evidence_source": ("operator_supplied_bounded_file" if chronos else "not_supplied"),
    }
    if recovery:
        payload["recovery"] = recovery.as_dict()
    if chronos:
        payload["chronos"] = chronos.as_dict()
    if proofgraph and proof_bundle:
        payload["proofgraph"] = proofgraph.as_dict()
        payload["proof_bundle"] = asdict(proof_bundle)
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
