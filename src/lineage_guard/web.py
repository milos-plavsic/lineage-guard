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
from lineage_guard.demo import assets, edges, negative_billing_signal
from lineage_guard.domain import Action
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
    graph = InMemoryMetadataGraph(assets(), edges())
    report = IncidentAnalyzer(graph).analyze(negative_billing_signal())
    artifacts = RemediationGenerator().generate(report)
    quarantined = sum(item.action == Action.QUARANTINE for item in report.decisions)
    return {
        "report": report.as_dict(),
        "summary": {
            "status": "Contained",
            "affectedBranches": quarantined,
            "safeBranches": sum(item.action == Action.CONTINUE for item in report.decisions),
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
                    f"{quarantined} branch requires quarantine; unaffected work can continue."
                ),
                "state": "decision",
            },
            {
                "stage": "Remediation prepared",
                "detail": f"{len(artifacts)} reviewable artifacts generated with integrity hashes.",
                "state": "ready",
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
    }


class LineageGuardHandler(BaseHTTPRequestHandler):
    server_version = "LineageGuard"
    sys_version = ""

    def do_GET(self) -> None:
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


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = ThreadingHTTPServer((args.host, args.port), LineageGuardHandler)
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
