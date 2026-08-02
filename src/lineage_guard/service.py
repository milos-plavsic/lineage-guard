from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256

from lineage_guard.domain import (
    Action,
    Asset,
    BranchDecision,
    IncidentReport,
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
        edges = self._graph.get_downstream_lineage(signal.asset_urn, max_hops)
        distances = self._distances(source.urn, edges, max_hops)
        decisions = tuple(
            self._decision(self._graph.get_asset(urn), distance, signal)
            for urn, distance in sorted(distances.items(), key=lambda item: (item[1], item[0]))
            if urn != source.urn
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
                "add_tag": [{"urn": urn, "tag": "LineageGuard:Quarantined"} for urn in quarantined],
            },
        )

    def apply_writeback(self, report: IncidentReport, *, approved: bool = False) -> None:
        if not approved:
            raise PermissionError("DataHub mutations require explicit approval")
        description = report.proposed_writeback["append_description"]
        self._graph.append_incident_summary(description["urn"], description["markdown"])
        for mutation in report.proposed_writeback["add_tag"]:
            self._graph.add_tag(mutation["urn"], mutation["tag"])

    @staticmethod
    def _distances(source: str, edges: tuple, max_hops: int) -> dict[str, int]:
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.upstream_urn].append(edge.downstream_urn)
        distances = {source: 0}
        queue = deque([source])
        while queue:
            current = queue.popleft()
            if distances[current] >= max_hops:
                continue
            for downstream in adjacency[current]:
                if downstream not in distances:
                    distances[downstream] = distances[current] + 1
                    queue.append(downstream)
        return distances

    @staticmethod
    def _decision(asset: Asset, distance: int, signal: QualitySignal) -> BranchDecision:
        normalized = f"{asset.name} {asset.description} {' '.join(asset.tags)}".lower()
        matching = tuple(
            concern for concern in signal.affected_concerns if concern.lower() in normalized
        )
        criticality = 25 if "critical" in {tag.lower() for tag in asset.tags} else 0
        usage = min(asset.usage_count // 10, 20)
        proximity = max(0, 15 - ((distance - 1) * 5))
        relevance = 25 if matching else 0
        risk = min(
            100,
            _SEVERITY_WEIGHT[signal.severity] + criticality + usage + proximity + relevance,
        )

        if matching and risk >= 70:
            action = Action.QUARANTINE
            rationale = (
                "The failing concern is material to this branch and the impact score is high."
            )
        elif matching:
            action = Action.MONITOR
            rationale = "The branch has plausible exposure; validate it before allowing promotion."
        else:
            action = Action.CONTINUE
            rationale = "No branch-specific dependency on the failing concern was found."
        return BranchDecision(asset, distance, matching, risk, action, rationale)

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
