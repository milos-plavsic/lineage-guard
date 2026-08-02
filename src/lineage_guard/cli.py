from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path

from lineage_guard.adapters.mcp import DataHubMcpGraph, StdioMcpConfig, open_stdio_session
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.domain import QualitySignal, Severity
from lineage_guard.enforcement import SignedWebhookConfig, SignedWebhookEnforcer
from lineage_guard.events import load_quality_event
from lineage_guard.recovery import CounterfactualRecoveryLab, demo_recovery_scenario
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
    recovery = (
        CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
        if args.recovery_lab
        else None
    )
    if args.artifacts_dir:
        RemediationGenerator().write(report, args.artifacts_dir, recovery)
    if args.apply:
        analyzer.apply_writeback(report, approved=True)
    payload = report.as_dict()
    if recovery is not None:
        payload["recovery"] = recovery.as_dict()
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


async def _run_mcp(args: argparse.Namespace) -> int:
    if getattr(args, "recovery_lab", False):
        raise SystemExit("--recovery-lab uses the deterministic demo scenario; select --mode demo")
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
        if args.artifacts_dir:
            RemediationGenerator().write(report, args.artifacts_dir)
        if args.apply:
            if webhook:
                enforcer = SignedWebhookEnforcer(
                    SignedWebhookConfig(webhook, enforcement_secret or "")
                )
                await asyncio.to_thread(enforcer.enforce, report)
            analyzer.apply_writeback(report, approved=True)
            await graph.flush()
    rendered = json.dumps(report.as_dict(), indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
