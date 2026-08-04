from __future__ import annotations

from collections.abc import Sequence

from lineage_guard.proof_service import ProofQueryService


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError("install lineage-guard[mcp] to run the ProofGraph MCP server") from error

    service = ProofQueryService()
    server = FastMCP(
        "LineageGuard ProofGraph",
        instructions=(
            "Read deterministic decision explanations, causal cuts, evidence gaps, "
            "counterfactuals, and proof verification. This server exposes no mutations."
        ),
    )

    @server.tool()
    def explain_decision(decision_node_id: str) -> dict:
        """Explain a decision from the same derivation graph that produced it."""
        return service.explain_decision(decision_node_id)

    @server.tool()
    def get_causal_cut(decision_node_id: str) -> dict:
        """Return the minimal decisive evidence set for a decision."""
        return service.get_causal_cut(decision_node_id)

    @server.tool()
    def find_evidence_gaps(limit: int = 10) -> list[dict]:
        """Rank missing metadata by decision value, uncertainty, cost, and risk."""
        return service.find_evidence_gaps(limit)

    @server.tool()
    def simulate_context_change(decision_node_id: str, evidence_node_id: str) -> dict:
        """Return the precomputed fail-closed result of removing decisive evidence."""
        return service.simulate_context_change(decision_node_id, evidence_node_id)

    @server.tool()
    def verify_proof_bundle() -> dict:
        """Verify content integrity and disclose the bundle authentication state."""
        return service.verify_proof_bundle()

    return server


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise SystemExit("the ProofGraph MCP server accepts no command-line arguments")
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
