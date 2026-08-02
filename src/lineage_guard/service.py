from __future__ import annotations

from hashlib import sha256

from lineage_guard.domain import (
    Action,
    Asset,
    BranchDecision,
    EvidenceStrength,
    IncidentReport,
    LineageTarget,
    QualitySignal,
    Severity,
)
from lineage_guard.ports import MetadataGraph

_SEVERITY_WEIGHT = {
    Severity.LOW: 10,
    Severity.MEDIUM: 25,
    Severity.HIGH: 45,
    Severity.CRITICAL: 65,
}


class IncidentAnalyzer:
    def __init__(self, graph: MetadataGraph) -> None:
        self._graph = graph

    def analyze(self, signal: QualitySignal, *, max_hops: int = 5) -> IncidentReport:
        if max_hops < 1:
            raise ValueError("max_hops must be at least 1")

        source = self._graph.get_asset(signal.asset_urn)
        targets = self._graph.get_downstream_lineage(signal.asset_urn, max_hops, field=signal.field)
        decisions = tuple(
            self._decision(self._graph.get_asset(target.urn), target, signal)
            for target in sorted(targets, key=lambda item: (item.distance, item.urn))
        )
        incident_id = sha256(
            f"{signal.asset_urn}|{signal.field}|{signal.rule}|{signal.observed}".encode()
        ).hexdigest()[:12]
        quarantined = [
            decision.asset.urn for decision in decisions if decision.action == Action.QUARANTINE
        ]
        summary = self._summary(incident_id, source, signal, decisions)
        return IncidentReport(
            incident_id=incident_id,
            source=source,
            signal=signal,
            decisions=decisions,
            proposed_writeback={
                "append_description": {"urn": source.urn, "markdown": summary},
                "add_tag": [
                    {"urn": urn, "tag": "urn:li:tag:LineageGuard_Quarantined"}
                    for urn in quarantined
                ],
            },
        )

    def apply_writeback(self, report: IncidentReport, *, approved: bool = False) -> None:
        if not approved:
            raise PermissionError("DataHub mutations require explicit approval")
        description = report.proposed_writeback["append_description"]
        incident_marker = f"### LineageGuard incident {report.incident_id}"
        if incident_marker not in report.source.description:
            self._graph.append_incident_summary(description["urn"], description["markdown"])
        for mutation in report.proposed_writeback["add_tag"]:
            self._graph.add_tag(mutation["urn"], mutation["tag"])

    @staticmethod
    def _decision(asset: Asset, target: LineageTarget, signal: QualitySignal) -> BranchDecision:
        normalized = f"{asset.name} {asset.description} {' '.join(asset.tags)}".lower()
        matching = tuple(
            concern for concern in signal.affected_concerns if concern.lower() in normalized
        )
        normalized_fields = {field.casefold() for field in target.dependent_fields}
        if signal.field.casefold() in normalized_fields:
            evidence_strength = EvidenceStrength.CONFIRMED_DEPENDENCY
            evidence = (f"column lineage depends on {signal.field}",)
        elif target.field_lineage_complete:
            evidence_strength = EvidenceStrength.CONFIRMED_EXCLUSION
            evidence = (f"complete column lineage excludes {signal.field}",)
        elif matching:
            evidence_strength = EvidenceStrength.METADATA_INDICATION
            evidence = tuple(f"metadata matches concern: {concern}" for concern in matching)
        else:
            evidence_strength = EvidenceStrength.INSUFFICIENT
            evidence = ("no complete field-level dependency evidence",)
        criticality = 25 if "critical" in {tag.lower() for tag in asset.tags} else 0
        usage = min(asset.usage_count // 10, 20)
        proximity = max(0, 15 - ((target.distance - 1) * 5))
        relevance = {
            EvidenceStrength.CONFIRMED_DEPENDENCY: 25,
            EvidenceStrength.METADATA_INDICATION: 15,
            EvidenceStrength.CONFIRMED_EXCLUSION: 0,
            EvidenceStrength.INSUFFICIENT: 0,
        }[evidence_strength]
        risk = min(
            100,
            _SEVERITY_WEIGHT[signal.severity] + criticality + usage + proximity + relevance,
        )

        if evidence_strength == EvidenceStrength.CONFIRMED_DEPENDENCY and matching and risk >= 70:
            action = Action.QUARANTINE
            rationale = "Field-level lineage confirms exposure and the impact score is high."
        elif evidence_strength in {
            EvidenceStrength.CONFIRMED_DEPENDENCY,
            EvidenceStrength.METADATA_INDICATION,
        }:
            action = Action.MONITOR
            rationale = "Exposure is plausible; validate it before allowing promotion."
        elif evidence_strength == EvidenceStrength.CONFIRMED_EXCLUSION:
            action = Action.CONTINUE
            rationale = (
                "Complete field-level lineage confirms this branch excludes the failed field."
            )
        else:
            action = Action.REQUIRE_REVIEW
            rationale = "Evidence is insufficient to prove impact or safe continuation."
        return BranchDecision(
            asset,
            target.distance,
            matching,
            evidence_strength,
            evidence,
            risk,
            action,
            rationale,
        )

    @staticmethod
    def _summary(
        incident_id: str,
        source: Asset,
        signal: QualitySignal,
        decisions: tuple[BranchDecision, ...],
    ) -> str:
        outcomes = ", ".join(f"{item.asset.name}={item.action}" for item in decisions) or "none"
        return (
            f"\n\n### LineageGuard incident {incident_id}\n"
            f"Source: `{source.name}`; field: `{signal.field}`; rule: {signal.rule}; "
            f"observed: {signal.observed}. Branch decisions: {outcomes}."
        )
