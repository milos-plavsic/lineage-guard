from __future__ import annotations

from dataclasses import asdict
from typing import Any

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import build_demo_chronos
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.proofgraph import build_demo_proofgraph, verify_proof_bundle
from lineage_guard.recovery import CounterfactualRecoveryLab, demo_recovery_scenario
from lineage_guard.service import IncidentAnalyzer


class ProofQueryService:
    """Bounded read-only query surface shared by MCP, HTTP, and tests."""

    def __init__(self) -> None:
        metadata = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
        self.report = IncidentAnalyzer(metadata).analyze(negative_billing_signal())
        self.recovery = CounterfactualRecoveryLab().evaluate(self.report, demo_recovery_scenario())
        self.chronos = build_demo_chronos(self.report, self.recovery)
        self.graph, self.bundle = build_demo_proofgraph(self.report, self.recovery, self.chronos)

    def explain_decision(self, decision_node_id: str) -> dict[str, Any]:
        return self.graph.explain(decision_node_id)

    def get_causal_cut(self, decision_node_id: str) -> dict[str, Any]:
        return self.graph.explain(decision_node_id)["causal_cut"]

    def find_evidence_gaps(self, limit: int = 10) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return [asdict(item) for item in self.graph.evidence_gaps[:limit]]

    def simulate_context_change(
        self, decision_node_id: str, evidence_node_id: str
    ) -> dict[str, Any]:
        explanation = self.graph.explain(decision_node_id)
        match = next(
            (
                item
                for item in explanation["counterfactuals"]
                if item["evidence_node_id"] == evidence_node_id
            ),
            None,
        )
        if match is None:
            raise KeyError("evidence is not a simulated causal input for this decision")
        return match

    def verify_proof_bundle(self) -> dict[str, Any]:
        return {
            "valid": verify_proof_bundle(self.bundle, self.graph),
            "authenticated": self.bundle.authenticated,
            "statement_sha256": self.bundle.statement_sha256,
            "graph_sha256": self.graph.graph_sha256,
        }
