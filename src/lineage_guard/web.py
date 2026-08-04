from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import build_demo_chronos
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.domain import Action
from lineage_guard.proofgraph import build_demo_proofgraph
from lineage_guard.recovery import CounterfactualRecoveryLab, demo_recovery_scenario
from lineage_guard.remediation import RemediationGenerator
from lineage_guard.service import IncidentAnalyzer

LOGGER = logging.getLogger("lineage_guard.web")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def build_view_model() -> dict[str, Any]:
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    report = IncidentAnalyzer(graph).analyze(negative_billing_signal())
    recovery = CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
    chronos = build_demo_chronos(report, recovery)
    proofgraph, proof_bundle = build_demo_proofgraph(report, recovery, chronos)
    artifacts = RemediationGenerator().generate(report, recovery, chronos, proofgraph, proof_bundle)
    quarantined = sum(item.action == Action.QUARANTINE for item in report.decisions)
    review = sum(
        item.action in {Action.MONITOR, Action.REQUIRE_REVIEW} for item in report.decisions
    )
    return {
        "provenance": {
            "execution_mode": "deterministic_fixture",
            "metadata_source": "application_owned_datahub_shaped_fixture",
            "live_datahub_connected": False,
            "mutations_applied": False,
            "proof_integrity_valid": True,
            "proof_authenticated": False,
            "approval_state": "not_requested",
        },
        "report": report.as_dict(),
        "summary": {
            "status": "Contained",
            "affectedBranches": quarantined,
            "safeBranches": sum(item.action == Action.CONTINUE for item in report.decisions),
            "reviewBranches": review,
            "maxRisk": max((item.risk_score for item in report.decisions), default=0),
        },
        "timeline": [
            {
                "stage": "Signal received",
                "detail": report.signal.observed,
                "state": "detected",
            },
            {
                "stage": "Context resolved",
                "detail": f"DataHub lineage identified {len(report.decisions)} downstream assets.",
                "state": "context",
            },
            {
                "stage": "Blast radius classified",
                "detail": (
                    f"{quarantined} branch requires quarantine, {review} requires review, "
                    "and only evidence-backed unaffected work can continue."
                ),
                "state": "decision",
            },
            {
                "stage": "Remediation prepared",
                "detail": f"{len(artifacts)} reviewable artifacts generated with integrity hashes.",
                "state": "ready",
            },
            {
                "stage": "Counterfactual repairs evaluated",
                "detail": (
                    "A superficial clamp passed the quality rule but failed value conservation; "
                    "trusted restoration passed every invariant."
                ),
                "state": "verified",
            },
            {
                "stage": "Recovery proof issued",
                "detail": (
                    f"Certificate {recovery.certificate.certificate_id} binds the incident, "
                    "DataHub context, repair SQL, output, and checks."
                ),
                "state": "certified",
            },
            {
                "stage": "Incident Genome compiled",
                "detail": (
                    f"Genome {chronos.genome.genome_id} converts containment and recovery proof "
                    "into executable prevention controls."
                ),
                "state": "immunized",
            },
            {
                "stage": "Historical failure replayed",
                "detail": (
                    "Guard removal is blocked; guard preservation receives a proof passport."
                ),
                "state": "prevented",
            },
            {
                "stage": "Context drift detected",
                "detail": (
                    "A new ML lineage edge expires yesterday's proof and requires revalidation."
                ),
                "state": "expired",
            },
            {
                "stage": "Causal proof derived",
                "detail": (
                    f"ProofGraph bound {len(proofgraph.nodes)} evidence and authority nodes into "
                    f"{len(proofgraph.causal_cuts)} exact Causal Cuts."
                ),
                "state": "explained",
            },
            {
                "stage": "Evidence gap ranked",
                "detail": (
                    f"Radar prioritized {len(proofgraph.evidence_gaps)} context improvement(s) "
                    "without granting new authority."
                ),
                "state": "prioritized",
            },
            {
                "stage": "Approval required",
                "detail": (
                    "DataHub write-back remains dry-run until an operator explicitly approves it."
                ),
                "state": "pending",
            },
        ],
        "artifacts": [asdict(artifact) for artifact in artifacts],
        "recovery": recovery.as_dict(),
        "chronos": chronos.as_dict(),
        "proofgraph": proofgraph.as_dict(),
        "proof_bundle": asdict(proof_bundle),
    }


class LineageGuardHandler(BaseHTTPRequestHandler):
    server_version = "LineageGuard"
    sys_version = ""

    def do_GET(self) -> None:
        try:
            self._handle_get()
        except (OSError, RuntimeError, ValueError):
            LOGGER.exception(json.dumps({"event": "request_failed", "path": self.path}))
            self._send_json({"error": "internal_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_get(self) -> None:
        routes = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        if self.path == "/healthz":
            self._send_json({"status": "ok"})
            return
        if self.path == "/api/incidents/current":
            self._send_json(build_view_model(), cache=False)
            return
        if route := routes.get(self.path):
            name, content_type = route
            body = files("lineage_guard.web_assets").joinpath(name).read_bytes()
            self._send(body, content_type, cache=True)
            return
        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        self._send_json({"error": "method_not_allowed"}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info(
            json.dumps(
                {
                    "event": "http_request",
                    "client": self.client_address[0],
                    "request": format % args,
                }
            )
        )

    def _send_json(
        self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK, cache: bool = False
    ) -> None:
        self._send(
            json.dumps(payload, separators=(",", ":")).encode(),
            "application/json; charset=utf-8",
            status=status,
            cache=cache,
        )

    def _send(
        self,
        body: bytes,
        content_type: str,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        cache: bool,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LineageGuard operator dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


class LineageGuardServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = LineageGuardServer((args.host, args.port), LineageGuardHandler)
    LOGGER.info(json.dumps({"event": "server_started", "url": f"http://{args.host}:{args.port}"}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
