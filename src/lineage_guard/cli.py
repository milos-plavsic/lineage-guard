from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path

from lineage_guard.adapters.mcp import DataHubMcpGraph, StdioMcpConfig, open_stdio_session
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import assets, edges, negative_billing_signal
from lineage_guard.domain import QualitySignal, Severity
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
    parser.add_argument("--gms-url", help="DataHub GMS URL for MCP mode.")
    parser.add_argument("--source-urn", help="Source dataset URN for MCP mode.")
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
    graph = InMemoryMetadataGraph(assets(), edges())
    analyzer = IncidentAnalyzer(graph)
    report = analyzer.analyze(negative_billing_signal())
    if args.apply:
        analyzer.apply_writeback(report, approved=True)
    rendered = json.dumps(report.as_dict(), indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


async def _run_mcp(args: argparse.Namespace) -> int:
    token = os.environ.get("DATAHUB_GMS_TOKEN")
    if not args.gms_url or not args.source_urn or not token:
        raise SystemExit("MCP mode requires --gms-url, --source-urn, and DATAHUB_GMS_TOKEN.")
    config = StdioMcpConfig(args.gms_url, token, enable_mutations=args.apply)
    signal = QualitySignal(
        asset_urn=args.source_urn,
        field=args.field,
        rule="quality assertion failed",
        observed="failure reported by the incident trigger",
        severity=Severity.HIGH,
        affected_concerns=tuple(args.concerns or [args.field]),
    )
    async with open_stdio_session(config) as session:
        graph = await DataHubMcpGraph.load(session, args.source_urn)
        analyzer = IncidentAnalyzer(graph)
        report = analyzer.analyze(signal)
        if args.apply:
            analyzer.apply_writeback(report, approved=True)
            await graph.flush()
    rendered = json.dumps(report.as_dict(), indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
