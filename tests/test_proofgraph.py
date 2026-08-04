from dataclasses import replace
from pathlib import Path

import pytest

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import build_demo_chronos
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.domain import Action
from lineage_guard.proof_service import ProofQueryService
from lineage_guard.proofgraph import (
    EvidenceGapRadar,
    PolicyExpression,
    PolicyOperator,
    ProofBundle,
    ProofGraphEngine,
    ProofGuard,
    RadarWeights,
    build_demo_proofgraph,
    build_proof_bundle,
    evaluate_policy,
    load_radar_weights,
    minimal_sufficient_cuts,
    verify_proof_bundle,
)
from lineage_guard.recovery import CounterfactualRecoveryLab, demo_recovery_scenario
from lineage_guard.service import IncidentAnalyzer


def evidence():
    report = IncidentAnalyzer(
        InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    ).analyze(negative_billing_signal())
    recovery = CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
    chronos = build_demo_chronos(report, recovery)
    return report, recovery, chronos


def test_proofgraph_derives_minimal_cuts_counterfactuals_and_gaps() -> None:
    report, recovery, chronos = evidence()
    graph, bundle = build_demo_proofgraph(report, recovery, chronos)

    assert len(graph.nodes) == 15 and len(graph.causal_cuts) == 3
    quarantine = next(cut for cut in graph.causal_cuts if ":quarantine:" in cut.decision_node_id)
    assert quarantine.size == 3
    explanation = graph.explain(quarantine.decision_node_id)
    assert len(explanation["evidence"]) == 3
    assert {item["resulting_action"] for item in explanation["counterfactuals"]} == {
        Action.CONTINUE,
        Action.MONITOR,
    }
    assert {item.gap_id.split(":")[1] for item in graph.evidence_gaps} == {
        "freshness",
        "governance",
    }
    assert 0 <= graph.evidence_gaps[0].priority_score <= 100
    assert verify_proof_bundle(bundle, graph) and bundle.authenticated is False


def test_query_service_exposes_all_five_read_only_operations() -> None:
    service = ProofQueryService()
    decision = service.graph.causal_cuts[0].decision_node_id
    explanation = service.explain_decision(decision)
    cut = service.get_causal_cut(decision)
    simulated = service.simulate_context_change(
        decision, explanation["counterfactuals"][0]["evidence_node_id"]
    )

    assert cut["decision_node_id"] == decision
    assert simulated["original_action"] != simulated["resulting_action"]
    assert service.find_evidence_gaps(1)
    assert service.verify_proof_bundle()["valid"] is True
    with pytest.raises(ValueError, match="between 1 and 100"):
        service.find_evidence_gaps(0)
    with pytest.raises(KeyError, match="not a simulated causal input"):
        service.simulate_context_change(decision, "missing")
    with pytest.raises(KeyError, match="unknown decision"):
        service.explain_decision("missing")


def test_proofgraph_rejects_detached_inputs_and_tampering() -> None:
    report, recovery, chronos = evidence()
    graph, bundle = build_demo_proofgraph(report, recovery, chronos)
    detached_report = replace(report, incident_id="other")
    with pytest.raises(ValueError, match="matching, valid"):
        ProofGraphEngine().compile(detached_report, recovery, chronos)
    with pytest.raises(ValueError, match="matching, valid"):
        ProofGraphEngine().compile(
            replace(report, decisions=report.decisions[:-1]), recovery, chronos
        )
    with pytest.raises(ValueError, match="detached or invalid"):
        build_proof_bundle(report, recovery, chronos, replace(graph, graph_sha256="0" * 64))
    with pytest.raises(ValueError, match="detached recovery"):
        build_proof_bundle(
            report,
            recovery,
            replace(
                chronos,
                genome=replace(chronos.genome, recovery_certificate_id="detached"),
            ),
            graph,
        )

    tampered = ProofBundle({**bundle.statement, "predicateType": "wrong"}, "0" * 64, False)
    assert not verify_proof_bundle(tampered)
    assert not verify_proof_bundle(replace(bundle, authenticated=True))
    assert not verify_proof_bundle(bundle, replace(graph, graph_sha256="1" * 64))
    assert not verify_proof_bundle(bundle, replace(graph, nodes=graph.nodes[:-1]))


def test_radar_handles_no_gaps_and_lineage_gap() -> None:
    report, _, _ = evidence()
    resolved = replace(
        report,
        decisions=tuple(
            item for item in report.decisions if item.action in {Action.QUARANTINE, Action.CONTINUE}
        ),
    )
    assert EvidenceGapRadar().rank(resolved) == ()
    review = replace(
        report.decisions[0],
        action=Action.REQUIRE_REVIEW,
        evidence_strength="insufficient",
        risk_score=10_000,
    )
    gaps = EvidenceGapRadar().rank(replace(report, decisions=(review,)))
    assert gaps[0].gap_id.startswith("gap:column-lineage:")
    assert gaps[0].priority_score == 80

    freshness_weights = RadarWeights(
        uncertainty=0,
        criticality=0,
        freshness=100,
        decisions_unlocked=0,
        collection_cost=0,
        privacy_risk=0,
    )
    ranked = EvidenceGapRadar(freshness_weights).rank(report)
    assert ranked[0].gap_id.startswith("gap:freshness:")


def test_graph_enforces_size_bound(monkeypatch) -> None:
    report, recovery, chronos = evidence()
    monkeypatch.setattr("lineage_guard.proofgraph.MAX_GRAPH_ITEMS", 0)
    with pytest.raises(ValueError, match="10000-item"):
        ProofGraphEngine().compile(report, recovery, chronos)


def test_proofguard_fails_closed_if_internal_verification_fails(monkeypatch) -> None:
    report, recovery, chronos = evidence()
    monkeypatch.setattr("lineage_guard.proofgraph.verify_proof_bundle", lambda *args: False)
    with pytest.raises(ValueError, match="failed integrity"):
        ProofGuard().compile(report, recovery, chronos)


def test_exact_minimal_cut_engine_handles_nested_any_all_and_bounds(monkeypatch) -> None:
    def leaf(name):
        return PolicyExpression(name, PolicyOperator.EVIDENCE, name)

    expression = PolicyExpression(
        "root",
        PolicyOperator.ALL,
        children=(
            leaf("signal"),
            PolicyExpression("choice", PolicyOperator.ANY, children=(leaf("a"), leaf("b"))),
        ),
    )
    assert minimal_sufficient_cuts(expression) == (("a", "signal"), ("b", "signal"))
    assert evaluate_policy(expression, {"a", "signal"})
    assert not evaluate_policy(expression, {"signal"})
    redundant = PolicyExpression(
        "redundant",
        PolicyOperator.ANY,
        children=(
            leaf("a"),
            PolicyExpression("both", PolicyOperator.ALL, children=(leaf("a"), leaf("b"))),
        ),
    )
    assert minimal_sufficient_cuts(redundant) == (("a",),)
    monkeypatch.setattr("lineage_guard.proofgraph.MAX_CUT_CANDIDATES", 1)
    with pytest.raises(ValueError, match="cut safety bound"):
        minimal_sufficient_cuts(expression)


def test_policy_and_radar_configuration_validation() -> None:
    with pytest.raises(ValueError, match="bounded"):
        PolicyExpression("", PolicyOperator.EVIDENCE, "x")
    with pytest.raises(ValueError, match="evidence expressions"):
        PolicyExpression("bad", PolicyOperator.EVIDENCE)
    with pytest.raises(ValueError, match="integer percentages"):
        RadarWeights(uncertainty=True)
    with pytest.raises(ValueError, match="sum to 100"):
        RadarWeights(uncertainty=34)


def test_loads_strict_radar_weights_and_derived_cut_guard(tmp_path, monkeypatch) -> None:
    weights = load_radar_weights(Path("examples/radar-weights.json"))
    assert weights == RadarWeights()
    path = tmp_path / "weights.json"
    path.write_text('{"schema_version":2}')
    with pytest.raises(ValueError, match="schema_version"):
        load_radar_weights(path)
    path.write_text('{"schema_version":1,"uncertainty":100}')
    with pytest.raises(ValueError, match="unknown or missing"):
        load_radar_weights(path)
    path.write_text("not-json")
    with pytest.raises(ValueError, match="invalid Radar"):
        load_radar_weights(path)
    path.write_bytes(b" " * 64_001)
    with pytest.raises(ValueError, match="exceeds 64 KB"):
        load_radar_weights(path)

    report, recovery, chronos = evidence()
    monkeypatch.setattr("lineage_guard.proofgraph.evaluate_policy", lambda *args: False)
    with pytest.raises(ValueError, match="does not satisfy"):
        ProofGraphEngine().compile(report, recovery, chronos)
