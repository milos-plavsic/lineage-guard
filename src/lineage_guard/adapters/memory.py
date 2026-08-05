from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace

from lineage_guard.chronos import OPERATIONAL_GOVERNANCE_TAGS, ImmunityContext
from lineage_guard.consistency import LineageRead, ReadConsistency, lineage_receipt
from lineage_guard.domain import Asset, LineageEdge, LineageTarget
from lineage_guard.immune_memory import ImmuneMemoryRecord, encode_memory, parse_memories


class InMemoryMetadataGraph:
    def __init__(
        self,
        assets: tuple[Asset, ...],
        edges: tuple[LineageEdge, ...],
        *,
        field_dependencies: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._assets = {asset.urn: asset for asset in assets}
        self._edges = edges
        self._field_dependencies = field_dependencies
        self.descriptions: list[tuple[str, str]] = []
        self.tags: list[tuple[str, str]] = []

    def get_asset(self, urn: str) -> Asset:
        try:
            return self._assets[urn]
        except KeyError as error:
            raise LookupError(f"Asset not found: {urn}") from error

    def get_downstream_lineage(
        self, urn: str, max_hops: int, *, field: str | None = None
    ) -> tuple[LineageTarget, ...]:
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
        complete = field is not None and self._field_dependencies is not None
        return tuple(
            LineageTarget(
                target,
                distance,
                self._field_dependencies.get(target, ()) if complete else (),
                complete,
            )
            for target, distance in distances.items()
            if target != urn
        )

    def append_incident_summary(self, urn: str, summary: str) -> None:
        self.descriptions.append((urn, summary))

    def read_downstream_lineage(
        self, urn: str, max_hops: int, *, field: str | None = None
    ) -> LineageRead:
        targets = self.get_downstream_lineage(urn, max_hops, field=field)
        return LineageRead(
            targets,
            lineage_receipt(
                source_urn=urn,
                max_hops=max_hops,
                max_results=len(targets),
                source_field=field,
                targets=targets,
                consistency=ReadConsistency(),
            ),
        )

    def get_immune_memories(self, urn: str) -> tuple[ImmuneMemoryRecord, ...]:
        return parse_memories(self.get_asset(urn).description)

    def get_immunity_context(self, urn: str, field: str) -> ImmunityContext:
        targets = self.get_downstream_lineage(urn, 5, field=field)
        assets = tuple(self.get_asset(target.urn) for target in targets)
        return ImmunityContext(
            (field,),
            tuple(f"{urn}->{target.urn}" for target in targets),
            tuple(
                sorted(
                    {
                        *(f"owner:{owner}" for asset in assets for owner in asset.owners),
                        *(
                            f"tag:{tag}"
                            for asset in assets
                            for tag in asset.tags
                            if tag not in OPERATIONAL_GOVERNANCE_TAGS
                        ),
                    }
                )
            ),
        )

    def append_immune_memory(self, urn: str, record: ImmuneMemoryRecord) -> None:
        if record.subject_urn != urn:
            raise ValueError("immune memory subject does not match the target asset")
        asset = self.get_asset(urn)
        existing = {item.record_digest for item in parse_memories(asset.description)}
        if record.record_digest in existing:
            return
        block = encode_memory(record)
        description = f"{asset.description.rstrip()}\n\n{block}".lstrip()
        self._assets[urn] = replace(asset, description=description)
        self.descriptions.append((urn, block))

    def add_tag(self, urn: str, tag: str) -> None:
        self.tags.append((urn, tag))

    async def flush(self) -> None:
        """Match the live graph contract; in-memory writes are immediately visible."""
