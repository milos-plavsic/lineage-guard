from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from lineage_guard.evidence_service import EvidenceQueryService


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "install lineage-guard[mcp] to run the Evidence Chain MCP server"
        ) from error

    service = EvidenceQueryService()
    server = FastMCP(
        "LineageGuard Evidence Chain",
        instructions=(
            "Verify immutable DataHub evidence chains, lifecycle state, and detached "
            "attestations. This server is deterministic and exposes no mutations."
        ),
    )

    @server.tool()
    def verify_evidence_chain(records: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify record integrity, topology, lifecycle transitions, and chain state."""
        return service.verify_chain(records)

    @server.tool()
    def get_evidence_state(records: list[dict[str, Any]], record_digest: str) -> dict[str, Any]:
        """Return a record's active, superseded, expired, or revoked state."""
        return service.get_record_state(records, record_digest)

    @server.tool()
    def verify_detached_attestation(attestation: dict[str, Any]) -> dict[str, Any]:
        """Verify a detached HMAC attestation inside one explicit trust domain."""
        secret = os.environ.get("LINEAGE_GUARD_ATTESTATION_SECRET")
        if secret is None:
            raise RuntimeError("LINEAGE_GUARD_ATTESTATION_SECRET is required")
        return service.verify_detached_attestation(attestation, secret)

    return server


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise SystemExit("the Evidence Chain MCP server accepts no command-line arguments")
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
