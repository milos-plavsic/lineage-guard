from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from lineage_guard.domain import LineageTarget


class ReadSource(StrEnum):
    SEARCH_INDEX = "SEARCH_INDEX"
    GRAPH_STORE = "GRAPH_STORE"
    UNKNOWN = "UNKNOWN"


class ConsistencyLevel(StrEnum):
    EVENTUAL = "EVENTUAL"
    READ_YOUR_WRITES = "READ_YOUR_WRITES"
    UNKNOWN = "UNKNOWN"


class Completeness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class CacheDisposition(StrEnum):
    HIT = "HIT"
    MISS = "MISS"
    BYPASSED = "BYPASSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class ReadCapability(StrEnum):
    USE_AS_OBSERVATION = "USE_AS_OBSERVATION"
    ASSERT_STATE_AT_REFERENCE = "ASSERT_STATE_AT_REFERENCE"
    ASSERT_ABSENCE_AT_REFERENCE = "ASSERT_ABSENCE_AT_REFERENCE"


class ReadLimitation(StrEnum):
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    CONSISTENCY_UNVERIFIED = "CONSISTENCY_UNVERIFIED"
    EVENTUAL_PROJECTION = "EVENTUAL_PROJECTION"
    COMPLETENESS_UNVERIFIED = "COMPLETENESS_UNVERIFIED"
    TRAVERSAL_INCOMPLETE = "TRAVERSAL_INCOMPLETE"
    RESPONSE_CACHE_UNOBSERVABLE = "RESPONSE_CACHE_UNOBSERVABLE"
    PROJECTION_WATERMARK_UNAVAILABLE = "PROJECTION_WATERMARK_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ReadConsistency:
    source: ReadSource = ReadSource.UNKNOWN
    consistency: ConsistencyLevel = ConsistencyLevel.UNKNOWN
    completeness: Completeness = Completeness.UNKNOWN
    response_cache: CacheDisposition = CacheDisposition.UNKNOWN
    as_of: str | None = None
    watermark: str | None = None

    def capabilities(self) -> tuple[ReadCapability, ...]:
        capabilities = [ReadCapability.USE_AS_OBSERVATION]
        referenced_state = (
            self.consistency is ConsistencyLevel.READ_YOUR_WRITES
            and self.completeness is Completeness.COMPLETE
            and (self.as_of is not None or self.watermark is not None)
        )
        if referenced_state:
            capabilities.extend(
                (
                    ReadCapability.ASSERT_STATE_AT_REFERENCE,
                    ReadCapability.ASSERT_ABSENCE_AT_REFERENCE,
                )
            )
        return tuple(capabilities)

    def limitations(self) -> tuple[ReadLimitation, ...]:
        limitations = []
        if self.source is ReadSource.UNKNOWN:
            limitations.append(ReadLimitation.SOURCE_UNVERIFIED)
        if self.consistency is ConsistencyLevel.UNKNOWN:
            limitations.append(ReadLimitation.CONSISTENCY_UNVERIFIED)
        elif self.consistency is ConsistencyLevel.EVENTUAL:
            limitations.append(ReadLimitation.EVENTUAL_PROJECTION)
        if self.completeness is Completeness.UNKNOWN:
            limitations.append(ReadLimitation.COMPLETENESS_UNVERIFIED)
        elif self.completeness is Completeness.INCOMPLETE:
            limitations.append(ReadLimitation.TRAVERSAL_INCOMPLETE)
        if self.response_cache is CacheDisposition.UNKNOWN:
            limitations.append(ReadLimitation.RESPONSE_CACHE_UNOBSERVABLE)
        if self.as_of is None and self.watermark is None:
            limitations.append(ReadLimitation.PROJECTION_WATERMARK_UNAVAILABLE)
        return tuple(limitations)


@dataclass(frozen=True, slots=True)
class ReadReceipt:
    query_digest: str
    result_digest: str
    consistency: ReadConsistency
    schema_version: str = "1.0"

    @property
    def capabilities(self) -> tuple[ReadCapability, ...]:
        return self.consistency.capabilities()

    @property
    def limitations(self) -> tuple[ReadLimitation, ...]:
        return self.consistency.limitations()

    @property
    def receipt_digest(self) -> str:
        return _digest(self._unsigned_dict())

    def _unsigned_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "queryDigest": self.query_digest,
            "resultDigest": self.result_digest,
            "readConsistency": _camel_consistency(self.consistency),
            "capabilities": list(self.capabilities),
            "limitations": list(self.limitations),
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._unsigned_dict(), "receiptDigest": self.receipt_digest}


@dataclass(frozen=True, slots=True)
class LineageRead:
    targets: tuple[LineageTarget, ...]
    receipt: ReadReceipt

    def as_dict(self) -> dict[str, Any]:
        return {
            "targets": [asdict(target) for target in self.targets],
            "receipt": self.receipt.as_dict(),
        }


def lineage_receipt(
    *,
    source_urn: str,
    max_hops: int,
    max_results: int,
    source_field: str | None,
    targets: tuple[LineageTarget, ...],
    consistency: ReadConsistency | None = None,
) -> ReadReceipt:
    query = {
        "direction": "DOWNSTREAM",
        "maxHops": max_hops,
        "maxResults": max_results,
        "sourceField": source_field,
        "sourceUrn": source_urn,
    }
    result = [asdict(target) for target in targets]
    return ReadReceipt(
        query_digest=_digest(query),
        result_digest=_digest(result),
        consistency=consistency or ReadConsistency(),
    )


def _camel_consistency(value: ReadConsistency) -> dict[str, Any]:
    return {
        "source": value.source,
        "consistency": value.consistency,
        "completeness": value.completeness,
        "responseCache": value.response_cache,
        "asOf": value.as_of,
        "watermark": value.watermark,
    }


def _digest(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
