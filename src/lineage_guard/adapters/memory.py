from __future__ import annotations

from lineage_guard.domain import Asset, LineageEdge


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

    def get_downstream_lineage(self, urn: str, max_hops: int) -> tuple[LineageEdge, ...]:
        del urn, max_hops
        return self._edges

    def append_incident_summary(self, urn: str, summary: str) -> None:
        self.descriptions.append((urn, summary))

    def add_tag(self, urn: str, tag: str) -> None:
        self.tags.append((urn, tag))
