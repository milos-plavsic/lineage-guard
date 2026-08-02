from __future__ import annotations

from typing import Protocol

from lineage_guard.domain import Asset, LineageTarget


class MetadataGraph(Protocol):
    def get_asset(self, urn: str) -> Asset: ...

    def get_downstream_lineage(self, urn: str, max_hops: int) -> tuple[LineageTarget, ...]: ...

    def append_incident_summary(self, urn: str, summary: str) -> None: ...

    def add_tag(self, urn: str, tag: str) -> None: ...
