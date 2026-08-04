from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from lineage_guard.chronos import IN_TOTO_STATEMENT_V1, ChronosBundle
from lineage_guard.domain import Action, BranchDecision, EvidenceStrength, IncidentReport
from lineage_guard.recovery import RecoveryBundle, canonical_sha256, verify_certificate

PROOF_BUNDLE_PREDICATE_V1 = "https://lineageguard.dev/attestations/proof-bundle/v1"
MAX_GRAPH_ITEMS = 10_000
MAX_CUT_CANDIDATES = 10_000


class ProofNodeKind(StrEnum):
    OBSERVATION = "observation"
    CONTEXT = "context"
    RULE = "rule"
    DECISION = "decision"
    PROOF = "proof"


class ProofRelation(StrEnum):
    USED = "used"
    GENERATED = "generated"
    DERIVED_FROM = "derived_from"


class PolicyOperator(StrEnum):
    EVIDENCE = "evidence"
    ALL = "all"
    ANY = "any"


@dataclass(frozen=True, slots=True)
class PolicyExpression:
    expression_id: str
    operator: PolicyOperator
    evidence_node_id: str | None = None
    children: tuple[PolicyExpression, ...] = ()

    def __post_init__(self) -> None:
        if not self.expression_id or len(self.expression_id) > 256:
            raise ValueError("policy expression IDs must be bounded non-empty text")
        leaf = self.operator == PolicyOperator.EVIDENCE
        if leaf != (self.evidence_node_id is not None) or leaf == bool(self.children):
            raise ValueError("evidence expressions have one evidence ID; groups have children")


@dataclass(frozen=True, slots=True)
class ProofNode:
    node_id: str
    kind: ProofNodeKind
    claim: str
    source: str
    sha256: str
    decisive: bool = False


@dataclass(frozen=True, slots=True)
class ProofEdge:
    source_id: str
    target_id: str
    relation: ProofRelation


@dataclass(frozen=True, slots=True)
class CausalCut:
    decision_node_id: str
    evidence_node_ids: tuple[str, ...]
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Counterfactual:
    evidence_node_id: str
    original_action: Action
    resulting_action: Action
    explanation: str


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    gap_id: str
    asset_urn: str
    title: str
    recommended_action: str
    decisions_unlocked: int
    uncertainty_reduction: int
    criticality: int
    freshness_need: int
    collection_cost: int
    privacy_risk: int
    priority_score: int
    scoring_factors: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class RadarWeights:
    uncertainty: int = 35
    criticality: int = 30
    freshness: int = 15
    decisions_unlocked: int = 10
    collection_cost: int = 7
    privacy_risk: int = 3

    def __post_init__(self) -> None:
        values = asdict(self).values()
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100
            for value in values
        ):
            raise ValueError("Radar weights must be integer percentages from 0 to 100")
        if sum(values) != 100:
            raise ValueError("Radar weights must sum to 100")


DEFAULT_RADAR_WEIGHTS = RadarWeights()


@dataclass(frozen=True, slots=True)
class ProofBundle:
    statement: dict[str, Any]
    statement_sha256: str
    authenticated: bool


@dataclass(frozen=True, slots=True)
class ProofGraph:
    schema_version: int
    incident_id: str
    nodes: tuple[ProofNode, ...]
    edges: tuple[ProofEdge, ...]
    causal_cuts: tuple[CausalCut, ...]
    counterfactuals: tuple[Counterfactual, ...]
    evidence_gaps: tuple[EvidenceGap, ...]
    graph_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def explain(self, decision_node_id: str) -> dict[str, Any]:
        node_index = {node.node_id: node for node in self.nodes}
        decision = node_index.get(decision_node_id)
        if decision is None or decision.kind != ProofNodeKind.DECISION:
            raise KeyError(f"unknown decision node: {decision_node_id}")
        cut = next(item for item in self.causal_cuts if item.decision_node_id == decision_node_id)
        return {
            "decision": asdict(decision),
            "causal_cut": asdict(cut),
            "evidence": [asdict(node_index[node_id]) for node_id in cut.evidence_node_ids],
            "counterfactuals": [
                asdict(item)
                for item in self.counterfactuals
                if item.evidence_node_id in cut.evidence_node_ids
            ],
        }


class ProofGraphEngine:
    def __init__(self, radar_weights: RadarWeights | None = None) -> None:
        self._radar_weights = radar_weights

    def compile(
        self,
        report: IncidentReport,
        recovery: RecoveryBundle,
        chronos: ChronosBundle,
    ) -> ProofGraph:
        self._validate_inputs(report, recovery, chronos)
        nodes: list[ProofNode] = []
        edges: list[ProofEdge] = []
        cuts: list[CausalCut] = []
        counterfactuals: list[Counterfactual] = []

        signal_id = f"observation:signal:{report.incident_id}"
        nodes.append(
            _node(
                signal_id,
                ProofNodeKind.OBSERVATION,
                f"{report.signal.field}: {report.signal.observed}",
                "datahub-assertion-event",
                decisive=True,
            )
        )
        for decision in report.decisions:
            branch_nodes, branch_edges, cut, branch_counterfactuals = self._branch_proof(
                report, decision, signal_id
            )
            nodes.extend(branch_nodes)
            edges.extend(branch_edges)
            cuts.append(cut)
            counterfactuals.extend(branch_counterfactuals)

        recovery_id = f"proof:recovery:{recovery.certificate.certificate_id}"
        genome_id = f"proof:genome:{chronos.genome.genome_id}"
        nodes.extend(
            (
                _node(
                    recovery_id,
                    ProofNodeKind.PROOF,
                    "all recovery invariants passed",
                    "lineageguard-forge",
                    decisive=True,
                ),
                _node(
                    genome_id,
                    ProofNodeKind.PROOF,
                    "incident compiled into context-bound preventive memory",
                    "lineageguard-chronos",
                    decisive=True,
                ),
            )
        )
        edges.append(ProofEdge(recovery_id, genome_id, ProofRelation.USED))
        gaps = EvidenceGapRadar(self._radar_weights).rank(report)
        if len(nodes) > MAX_GRAPH_ITEMS or len(edges) > MAX_GRAPH_ITEMS:
            raise ValueError("proof graph exceeds the 10000-item safety bound")
        body = {
            "schema_version": 1,
            "incident_id": report.incident_id,
            "nodes": [asdict(item) for item in nodes],
            "edges": [asdict(item) for item in edges],
            "causal_cuts": [asdict(item) for item in cuts],
            "counterfactuals": [asdict(item) for item in counterfactuals],
            "evidence_gaps": [asdict(item) for item in gaps],
        }
        return ProofGraph(
            1,
            report.incident_id,
            tuple(nodes),
            tuple(edges),
            tuple(cuts),
            tuple(counterfactuals),
            gaps,
            canonical_sha256(body),
        )

    @staticmethod
    def _validate_inputs(
        report: IncidentReport, recovery: RecoveryBundle, chronos: ChronosBundle
    ) -> None:
        certificate = recovery.certificate
        exposed = tuple(
            item.asset.urn for item in report.decisions if item.action == Action.QUARANTINE
        )
        excluded = tuple(
            item.asset.urn for item in report.decisions if item.action == Action.CONTINUE
        )
        review = tuple(
            item.asset.urn
            for item in report.decisions
            if item.action in {Action.MONITOR, Action.REQUIRE_REVIEW}
        )
        if (
            certificate is None
            or recovery.incident_id != report.incident_id
            or chronos.genome.incident_id != report.incident_id
            or chronos.genome.recovery_certificate_id != certificate.certificate_id
            or chronos.genome.exposed_assets != exposed
            or chronos.genome.excluded_assets != excluded
            or chronos.genome.review_assets != review
            or not verify_certificate(certificate)
        ):
            raise ValueError(
                "ProofGraph requires matching, valid Sentinel, Forge, and Chronos proof"
            )

    @staticmethod
    def _branch_proof(
        report: IncidentReport, decision: BranchDecision, signal_id: str
    ) -> tuple[list[ProofNode], list[ProofEdge], CausalCut, list[Counterfactual]]:
        key = canonical_sha256(decision.asset.urn)[:12]
        lineage_id = f"context:lineage:{key}"
        impact_id = f"context:impact:{key}"
        policy_id = f"rule:containment:{key}"
        decision_id = f"decision:{decision.action}:{key}"
        lineage_claim = decision.evidence[0]
        impact_claim = (
            f"risk={decision.risk_score}; concerns={','.join(decision.matching_concerns) or 'none'}"
        )
        branch_nodes = [
            _node(
                lineage_id,
                ProofNodeKind.CONTEXT,
                lineage_claim,
                "datahub-column-lineage",
                decisive=True,
            ),
            _node(
                impact_id,
                ProofNodeKind.CONTEXT,
                impact_claim,
                "datahub-governance-and-usage",
                decisive=decision.action == Action.QUARANTINE,
            ),
            _node(
                policy_id,
                ProofNodeKind.RULE,
                "selective-containment-policy-v1",
                "lineageguard-sentinel",
            ),
            _node(
                decision_id,
                ProofNodeKind.DECISION,
                f"{decision.asset.name} -> {decision.action}",
                "lineageguard-sentinel",
            ),
        ]
        branch_edges = [
            ProofEdge(signal_id, policy_id, ProofRelation.USED),
            ProofEdge(lineage_id, policy_id, ProofRelation.USED),
            ProofEdge(policy_id, decision_id, ProofRelation.GENERATED),
        ]
        evidence_ids = [signal_id, lineage_id]
        if decision.action == Action.QUARANTINE:
            branch_edges.append(ProofEdge(impact_id, policy_id, ProofRelation.USED))
            evidence_ids.append(impact_id)
        expression = PolicyExpression(
            policy_id,
            PolicyOperator.ALL,
            children=tuple(
                PolicyExpression(f"{policy_id}:{index}", PolicyOperator.EVIDENCE, node_id)
                for index, node_id in enumerate(evidence_ids)
            ),
        )
        evidence_ids = list(minimal_sufficient_cuts(expression)[0])
        available = set(evidence_ids)
        if not evaluate_policy(expression, available):
            raise ValueError("derived causal cut does not satisfy its policy")
        cut_body = {"decision_node_id": decision_id, "evidence_node_ids": evidence_ids}
        cut = CausalCut(
            decision_id, tuple(evidence_ids), len(evidence_ids), canonical_sha256(cut_body)
        )
        resulting = _without_lineage(decision)
        counterfactuals = [
            Counterfactual(
                signal_id,
                decision.action,
                Action.CONTINUE,
                "Without an active failure observation, containment is not activated.",
            ),
            Counterfactual(
                lineage_id,
                decision.action,
                resulting,
                f"Without this lineage claim, fail closed from {decision.action} to {resulting}.",
            ),
        ]
        if decision.action == Action.QUARANTINE:
            counterfactuals.append(
                Counterfactual(
                    impact_id,
                    decision.action,
                    Action.MONITOR,
                    "Without decisive impact context, confirmed exposure remains monitored.",
                )
            )
        return branch_nodes, branch_edges, cut, counterfactuals


class EvidenceGapRadar:
    def __init__(self, weights: RadarWeights | None = None) -> None:
        self._weights = weights or DEFAULT_RADAR_WEIGHTS

    def rank(self, report: IncidentReport) -> tuple[EvidenceGap, ...]:
        gaps = []
        for decision in report.decisions:
            if decision.action not in {Action.MONITOR, Action.REQUIRE_REVIEW}:
                continue
            base_uncertainty = {
                EvidenceStrength.CONFIRMED_DEPENDENCY: 35,
                EvidenceStrength.METADATA_INDICATION: 70,
                EvidenceStrength.INSUFFICIENT: 100,
                EvidenceStrength.CONFIRMED_EXCLUSION: 0,
            }[decision.evidence_strength]
            criticality = min(100, decision.risk_score)
            privacy = 20 if "clinical" in " ".join(decision.asset.owners).casefold() else 10
            needs_governance = decision.evidence_strength == EvidenceStrength.CONFIRMED_DEPENDENCY
            definitions = (
                (
                    (
                        "governance",
                        f"Resolve business impact classification for {decision.asset.name}",
                        f"Add authoritative criticality and concern classification for "
                        f"{decision.asset.name}.",
                        base_uncertainty,
                        35,
                        50,
                    ),
                    (
                        "freshness",
                        f"Prove context freshness for {decision.asset.name}",
                        "Record observation time and enforce a governed maximum evidence age.",
                        max(25, base_uncertainty - 20),
                        25,
                        100,
                    ),
                )
                if needs_governance
                else (
                    (
                        "column-lineage",
                        f"Resolve exact field lineage for {decision.asset.name}",
                        f"Ingest complete column lineage from {report.signal.field} to "
                        f"{decision.asset.name}, including explicit negative evidence.",
                        base_uncertainty,
                        55,
                        60,
                    ),
                    (
                        "completeness",
                        f"Attest lineage completeness for {decision.asset.name}",
                        "Publish an authenticated completeness assertion for the observed "
                        "lineage scope.",
                        max(30, base_uncertainty - 15),
                        45,
                        90,
                    ),
                )
            )
            for gap_kind, title, recommendation, uncertainty, cost, gap_freshness in definitions:
                gaps.append(
                    self._gap(
                        decision,
                        gap_kind,
                        title,
                        recommendation,
                        uncertainty,
                        criticality,
                        gap_freshness,
                        cost,
                        privacy,
                    )
                )
        return tuple(sorted(gaps, key=lambda item: (-item.priority_score, item.gap_id)))

    def _gap(
        self,
        decision: BranchDecision,
        kind: str,
        title: str,
        recommendation: str,
        uncertainty: int,
        criticality: int,
        freshness: int,
        cost: int,
        privacy: int,
    ) -> EvidenceGap:
        factors = (
            ("uncertainty", uncertainty),
            ("criticality", criticality),
            ("freshness", freshness),
            ("decisions_unlocked", 100),
            ("collection_cost", cost),
            ("privacy_risk", privacy),
        )
        weights = self._weights
        score = round(
            (
                weights.uncertainty * uncertainty
                + weights.criticality * criticality
                + weights.freshness * freshness
                + weights.decisions_unlocked * 100
                - weights.collection_cost * cost
                - weights.privacy_risk * privacy
            )
            / 100
        )
        return EvidenceGap(
            f"gap:{kind}:{canonical_sha256(decision.asset.urn)[:12]}",
            decision.asset.urn,
            title,
            recommendation,
            1,
            uncertainty,
            criticality,
            freshness,
            cost,
            privacy,
            max(0, min(100, score)),
            factors,
        )


def build_proof_bundle(
    report: IncidentReport,
    recovery: RecoveryBundle,
    chronos: ChronosBundle,
    graph: ProofGraph,
) -> ProofBundle:
    if graph.incident_id != report.incident_id or graph.graph_sha256 != _graph_digest(graph):
        raise ValueError("cannot bundle a detached or invalid ProofGraph")
    certificate = recovery.certificate
    if certificate is None or chronos.genome.recovery_certificate_id != certificate.certificate_id:
        raise ValueError("cannot bundle detached recovery and immunity proof")
    subject_digest = canonical_sha256(report.as_dict())
    statement = {
        "_type": IN_TOTO_STATEMENT_V1,
        "subject": [{"name": report.incident_id, "digest": {"sha256": subject_digest}}],
        "predicateType": PROOF_BUNDLE_PREDICATE_V1,
        "predicate": {
            "proofgraph_sha256": graph.graph_sha256,
            "sentinel_report_sha256": subject_digest,
            "forge_certificate_sha256": certificate.certificate_sha256,
            "chronos_genome_sha256": chronos.genome.genome_sha256,
            "causal_cut_sha256": [item.sha256 for item in graph.causal_cuts],
            "standards": {
                "provenance": "https://www.w3.org/TR/prov-o/",
                "attestation": IN_TOTO_STATEMENT_V1,
                "trace_context": "https://www.w3.org/TR/trace-context/",
            },
        },
    }
    return ProofBundle(statement, canonical_sha256(statement), False)


def verify_proof_bundle(bundle: ProofBundle, graph: ProofGraph | None = None) -> bool:
    statement = bundle.statement
    valid = (
        isinstance(statement, dict)
        and statement.get("_type") == IN_TOTO_STATEMENT_V1
        and statement.get("predicateType") == PROOF_BUNDLE_PREDICATE_V1
        and canonical_sha256(statement) == bundle.statement_sha256
        and bundle.authenticated is False
    )
    if graph is not None:
        valid = (
            valid
            and _graph_digest(graph) == graph.graph_sha256
            and graph.graph_sha256 == statement.get("predicate", {}).get("proofgraph_sha256")
        )
    return valid


def _node(
    node_id: str,
    kind: ProofNodeKind,
    claim: str,
    source: str,
    *,
    decisive: bool = False,
) -> ProofNode:
    return ProofNode(
        node_id,
        kind,
        claim,
        source,
        canonical_sha256({"node_id": node_id, "claim": claim, "source": source}),
        decisive,
    )


def _without_lineage(decision: BranchDecision) -> Action:
    if decision.matching_concerns:
        return Action.MONITOR
    return Action.REQUIRE_REVIEW


def minimal_sufficient_cuts(expression: PolicyExpression) -> tuple[tuple[str, ...], ...]:
    """Return every subset-minimal sufficient evidence set for a bounded monotone expression."""
    if expression.operator == PolicyOperator.EVIDENCE:
        return ((expression.evidence_node_id or "",),)
    child_cuts = [minimal_sufficient_cuts(child) for child in expression.children]
    candidates: list[frozenset[str]] = []
    if expression.operator == PolicyOperator.ANY:
        candidates = [frozenset(cut) for cuts in child_cuts for cut in cuts]
    else:
        candidates = [frozenset()]
        for cuts in child_cuts:
            candidates = [base | frozenset(cut) for base in candidates for cut in cuts]
            if len(candidates) > MAX_CUT_CANDIDATES:
                raise ValueError("policy expression exceeds the 10000-cut safety bound")
    minimal: list[frozenset[str]] = []
    for candidate in sorted(set(candidates), key=lambda item: (len(item), tuple(sorted(item)))):
        if not any(existing <= candidate for existing in minimal):
            minimal.append(candidate)
    return tuple(tuple(sorted(item)) for item in minimal)


def evaluate_policy(expression: PolicyExpression, available_evidence: set[str]) -> bool:
    if expression.operator == PolicyOperator.EVIDENCE:
        return (expression.evidence_node_id or "") in available_evidence
    outcomes = [evaluate_policy(child, available_evidence) for child in expression.children]
    return any(outcomes) if expression.operator == PolicyOperator.ANY else all(outcomes)


def _graph_digest(graph: ProofGraph) -> str:
    return canonical_sha256(
        {
            "schema_version": graph.schema_version,
            "incident_id": graph.incident_id,
            "nodes": [asdict(item) for item in graph.nodes],
            "edges": [asdict(item) for item in graph.edges],
            "causal_cuts": [asdict(item) for item in graph.causal_cuts],
            "counterfactuals": [asdict(item) for item in graph.counterfactuals],
            "evidence_gaps": [asdict(item) for item in graph.evidence_gaps],
        }
    )


class ProofGuard:
    """Fail-closed facade that compiles and verifies cross-pillar proof-carrying metadata."""

    def __init__(self, radar_weights: RadarWeights | None = None) -> None:
        self._radar_weights = radar_weights

    def compile(
        self,
        report: IncidentReport,
        recovery: RecoveryBundle,
        chronos: ChronosBundle,
    ) -> tuple[ProofGraph, ProofBundle]:
        graph = ProofGraphEngine(self._radar_weights).compile(report, recovery, chronos)
        bundle = build_proof_bundle(report, recovery, chronos, graph)
        if not verify_proof_bundle(bundle, graph):
            raise ValueError("compiled Proof Bundle failed integrity verification")
        return graph, bundle


def build_demo_proofgraph(
    report: IncidentReport,
    recovery: RecoveryBundle,
    chronos: ChronosBundle,
    radar_weights: RadarWeights | None = None,
) -> tuple[ProofGraph, ProofBundle]:
    return ProofGuard(radar_weights).compile(report, recovery, chronos)


def load_radar_weights(path: Path) -> RadarWeights:
    try:
        if path.stat().st_size > 64_000:
            raise ValueError("Radar weights document exceeds 64 KB")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.pop("schema_version", None) != 1:
            raise ValueError("Radar weights schema_version must be 1")
        if set(payload) != set(asdict(DEFAULT_RADAR_WEIGHTS)):
            raise ValueError("Radar weights contain unknown or missing fields")
        return RadarWeights(**payload)
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise ValueError("invalid Radar weights document") from error
