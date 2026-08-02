from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import (
    BILLING,
    DEMOGRAPHICS,
    assets,
    edges,
    field_dependencies,
    negative_billing_signal,
)
from lineage_guard.domain import Action
from lineage_guard.service import IncidentAnalyzer


def test_selectively_quarantines_only_material_branch() -> None:
    report = IncidentAnalyzer(
        InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    ).analyze(negative_billing_signal())
    decisions = {decision.asset.urn: decision for decision in report.decisions}

    assert decisions[BILLING].action is Action.QUARANTINE
    assert decisions[DEMOGRAPHICS].action is Action.CONTINUE
    assert report.proposed_writeback["add_tag"] == [
        {"urn": BILLING, "tag": "urn:li:tag:LineageGuard_Quarantined"}
    ]


def test_writeback_requires_explicit_approval() -> None:
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    analyzer = IncidentAnalyzer(graph)
    report = analyzer.analyze(negative_billing_signal())

    try:
        analyzer.apply_writeback(report)
    except PermissionError:
        pass
    else:
        raise AssertionError("writeback occurred without explicit approval")

    assert graph.tags == []
    assert graph.descriptions == []


def test_approved_writeback_is_auditable() -> None:
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    analyzer = IncidentAnalyzer(graph)
    report = analyzer.analyze(negative_billing_signal())

    analyzer.apply_writeback(report, approved=True)

    assert graph.tags == [(BILLING, "urn:li:tag:LineageGuard_Quarantined")]
    assert graph.descriptions[0][0] == report.source.urn
    assert report.incident_id in graph.descriptions[0][1]


def test_analysis_rejects_invalid_hop_limit() -> None:
    analyzer = IncidentAnalyzer(InMemoryMetadataGraph(assets(), edges()))

    try:
        analyzer.analyze(negative_billing_signal(), max_hops=0)
    except ValueError as error:
        assert "at least 1" in str(error)
    else:
        raise AssertionError("invalid hop limit was accepted")


def test_memory_graph_reports_unknown_asset() -> None:
    graph = InMemoryMetadataGraph(assets(), edges())

    try:
        graph.get_asset("urn:missing")
    except LookupError as error:
        assert "Asset not found" in str(error)
    else:
        raise AssertionError("unknown asset unexpectedly resolved")
