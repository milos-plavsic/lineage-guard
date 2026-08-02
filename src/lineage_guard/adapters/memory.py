from __future__ import annotations

from collections import defaultdict, deque

from lineage_guard.domain import Asset, LineageEdge, LineageTarget


class InMemoryMetadataGraph:
    def __init__(self, assets: tuple[Asset, ...], edges: tuple[LineageEdge, ...]) -> None:
        self._assets = {asset.urn: asset for asset in assets}
        self._edges = edges
        self.descriptions: list[tuple[str, str]] = []
        self.tags: list[tuple[str, str]] = []

    def get_asset(self, urn: str) -> Asset:
        try:
            return self._assets[urn]
        except KeyError as error:
            raise LookupError(f"Asset not found: {urn}") from error

    def get_downstream_lineage(self, urn: str, max_hops: int) -> tuple[LineageTarget, ...]:
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in self._edges:
            adjacency[edge.upstream_urn].append(edge.downstream_urn)
        distances = {urn: 0}
        queue = deque([urn])
        while queue:
            current = queue.popleft()
            if distances[current] >= max_hops:
                continue
            for downstream in adjacency[current]:
                if downstream not in distances:
                    distances[downstream] = distances[current] + 1
                    queue.append(downstream)
        return tuple(
            LineageTarget(target, distance)
            for target, distance in distances.items()
            if target != urn
        )

    def append_incident_summary(self, urn: str, summary: str) -> None:
        self.descriptions.append((urn, summary))

    def add_tag(self, urn: str, tag: str) -> None:
        self.tags.append((urn, tag))
