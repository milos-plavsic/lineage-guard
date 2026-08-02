from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import os
from collections.abc import Sequence
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from lineage_guard.adapters.mcp import StdioMcpConfig
from lineage_guard.agent import EventBusyError, EventConflictError, IncidentAgent
from lineage_guard.enforcement import SignedWebhookConfig, SignedWebhookEnforcer
from lineage_guard.events import MAX_EVENT_BYTES, InvalidQualityEvent, QualityEvent
from lineage_guard.journal import EventJournal

LOGGER = logging.getLogger("lineage_guard.agent_web")
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class AgentHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], agent: IncidentAgent, secret: str) -> None:
        super().__init__(address, AgentRequestHandler)
        self.agent = agent
        self.webhook_secret = secret.encode()


class AgentRequestHandler(BaseHTTPRequestHandler):
    server: AgentHttpServer
    server_version = "LineageGuardAgent"
    sys_version = ""

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/v1/quality-events":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json({"error": "unsupported_media_type"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = 0
        if not 1 <= length <= MAX_EVENT_BYTES:
            self._send_json(
                {"error": "invalid_content_length"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            return
        body = self.rfile.read(length)
        expected = (
            "sha256=" + hmac.new(self.server.webhook_secret, body, digestmod=sha256).hexdigest()
        )
        if not hmac.compare_digest(self.headers.get("X-LineageGuard-Signature", ""), expected):
            self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        try:
            event = QualityEvent.from_bytes(body)
            result = asyncio.run(self.server.agent.process(event))
        except InvalidQualityEvent:
            self._send_json({"error": "invalid_quality_event"}, HTTPStatus.BAD_REQUEST)
            return
        except EventConflictError:
            self._send_json({"error": "event_conflict"}, HTTPStatus.CONFLICT)
            return
        except EventBusyError:
            self._send_json(
                {"error": "event_in_progress"},
                HTTPStatus.CONFLICT,
                extra_headers={"Retry-After": "5"},
            )
            return
        except Exception:
            LOGGER.exception(json.dumps({"event": "processing_failed"}))
            self._send_json({"error": "processing_failed"}, HTTPStatus.BAD_GATEWAY)
            return
        self._send_json(result)

    def _send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info(json.dumps({"event": "http_access", "message": format % args}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lineage-guard-agent",
        description="Receive authenticated quality events and run the LineageGuard agent.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--gms-url", required=True)
    parser.add_argument("--journal", type=Path, default=Path(".lineage-guard/events.sqlite3"))
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--enforcement-webhook")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("agent listener must bind to loopback behind a TLS reverse proxy")
    if not 1 <= args.port <= 65_535:
        raise SystemExit("--port must be between 1 and 65535")
    token = os.environ.get("DATAHUB_GMS_TOKEN")
    webhook_secret = os.environ.get("LINEAGE_GUARD_WEBHOOK_SECRET")
    if not token or not webhook_secret or len(webhook_secret.encode()) < 32:
        raise SystemExit(
            "DATAHUB_GMS_TOKEN and a 32-byte LINEAGE_GUARD_WEBHOOK_SECRET are required"
        )
    enforcement_secret = os.environ.get("LINEAGE_GUARD_ENFORCEMENT_SECRET")
    if args.enforcement_webhook and (not args.apply or not enforcement_secret):
        raise SystemExit("enforcement requires --apply and LINEAGE_GUARD_ENFORCEMENT_SECRET")
    enforcer = (
        SignedWebhookEnforcer(
            SignedWebhookConfig(args.enforcement_webhook, enforcement_secret or "")
        )
        if args.enforcement_webhook
        else None
    )
    agent = IncidentAgent(
        EventJournal(args.journal),
        StdioMcpConfig(args.gms_url, token, enable_mutations=args.apply),
        artifacts_root=args.artifacts_dir,
        enforcer=enforcer,
    )
    server = AgentHttpServer((args.host, args.port), agent, webhook_secret)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
