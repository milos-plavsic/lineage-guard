from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import assets, edges, negative_billing_signal
from lineage_guard.service import IncidentAnalyzer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lineage-guard",
        description="Analyze DataHub lineage and propose selective incident containment.",
    )
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply proposed metadata mutations (demo adapter only in this milestone).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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


if __name__ == "__main__":
    raise SystemExit(main())
