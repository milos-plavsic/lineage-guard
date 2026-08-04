import json
from pathlib import Path

from lineage_guard.consistency import (
    CacheDisposition,
    Completeness,
    ConsistencyLevel,
    LineageRead,
    ReadCapability,
    ReadConsistency,
    ReadLimitation,
    ReadSource,
    lineage_receipt,
)
from lineage_guard.domain import LineageTarget


def test_unknown_receipt_is_useful_but_cannot_authorize_current_state_claims() -> None:
    targets = (LineageTarget("urn:li:dataset:test", 1),)
    receipt = lineage_receipt(
        source_urn="urn:li:dataset:source",
        max_hops=2,
        max_results=100,
        source_field=None,
        targets=targets,
    )

    assert receipt.capabilities == (ReadCapability.USE_AS_OBSERVATION,)
    assert receipt.limitations == (
        ReadLimitation.SOURCE_UNVERIFIED,
        ReadLimitation.CONSISTENCY_UNVERIFIED,
        ReadLimitation.COMPLETENESS_UNVERIFIED,
        ReadLimitation.RESPONSE_CACHE_UNOBSERVABLE,
        ReadLimitation.PROJECTION_WATERMARK_UNAVAILABLE,
    )
    envelope = receipt.as_dict()
    assert envelope["readConsistency"] == {
        "source": "UNKNOWN",
        "consistency": "UNKNOWN",
        "completeness": "UNKNOWN",
        "responseCache": "UNKNOWN",
        "asOf": None,
        "watermark": None,
    }
    assert envelope["receiptDigest"].startswith("sha256:")
    assert LineageRead(targets, receipt).as_dict() == {
        "targets": [
            {
                "urn": "urn:li:dataset:test",
                "distance": 1,
                "dependent_fields": (),
                "field_lineage_complete": False,
            }
        ],
        "receipt": envelope,
    }


def test_receipts_are_canonical_and_detect_query_or_result_changes() -> None:
    arguments = {
        "source_urn": "urn:li:dataset:source",
        "max_hops": 2,
        "max_results": 100,
        "source_field": None,
        "targets": (LineageTarget("urn:li:dataset:a", 1),),
    }
    first = lineage_receipt(**arguments)
    repeated = lineage_receipt(**arguments)
    changed_query = lineage_receipt(**{**arguments, "max_hops": 3})
    changed_result = lineage_receipt(
        **{**arguments, "targets": (LineageTarget("urn:li:dataset:b", 1),)}
    )

    assert first.receipt_digest == repeated.receipt_digest
    assert first.query_digest != changed_query.query_digest
    assert first.result_digest != changed_result.result_digest
    assert first.receipt_digest not in {changed_query.receipt_digest, changed_result.receipt_digest}


def test_state_capabilities_require_complete_read_your_writes_with_reference() -> None:
    strong = ReadConsistency(
        source=ReadSource.GRAPH_STORE,
        consistency=ConsistencyLevel.READ_YOUR_WRITES,
        completeness=Completeness.COMPLETE,
        response_cache=CacheDisposition.NOT_APPLICABLE,
        watermark="write:42",
    )
    no_reference = ReadConsistency(
        source=ReadSource.GRAPH_STORE,
        consistency=ConsistencyLevel.READ_YOUR_WRITES,
        completeness=Completeness.COMPLETE,
        response_cache=CacheDisposition.NOT_APPLICABLE,
    )

    assert strong.capabilities() == (
        ReadCapability.USE_AS_OBSERVATION,
        ReadCapability.ASSERT_STATE_AT_REFERENCE,
        ReadCapability.ASSERT_ABSENCE_AT_REFERENCE,
    )
    assert strong.limitations() == ()
    assert no_reference.capabilities() == (ReadCapability.USE_AS_OBSERVATION,)
    assert no_reference.limitations() == (ReadLimitation.PROJECTION_WATERMARK_UNAVAILABLE,)

    as_of = ReadConsistency(
        source=ReadSource.SEARCH_INDEX,
        consistency=ConsistencyLevel.READ_YOUR_WRITES,
        completeness=Completeness.COMPLETE,
        response_cache=CacheDisposition.BYPASSED,
        as_of="2026-08-04T18:00:00Z",
    )
    assert ReadCapability.ASSERT_STATE_AT_REFERENCE in as_of.capabilities()
    assert as_of.limitations() == ()

    incomplete = ReadConsistency(
        source=ReadSource.GRAPH_STORE,
        consistency=ConsistencyLevel.READ_YOUR_WRITES,
        completeness=Completeness.INCOMPLETE,
        response_cache=CacheDisposition.MISS,
        watermark="write:42",
    )
    assert incomplete.capabilities() == (ReadCapability.USE_AS_OBSERVATION,)
    assert incomplete.limitations() == (ReadLimitation.TRAVERSAL_INCOMPLETE,)

    eventual = ReadConsistency(
        source=ReadSource.SEARCH_INDEX,
        consistency=ConsistencyLevel.EVENTUAL,
        completeness=Completeness.COMPLETE,
        response_cache=CacheDisposition.HIT,
        watermark="index:42",
    )
    assert eventual.capabilities() == (ReadCapability.USE_AS_OBSERVATION,)
    assert eventual.limitations() == (ReadLimitation.EVENTUAL_PROJECTION,)

    receipt = lineage_receipt(
        source_urn="urn:li:dataset:source",
        max_hops=2,
        max_results=100,
        source_field=None,
        targets=(),
        consistency=strong,
    )
    assert receipt.consistency is strong


def test_wire_schema_is_versioned_and_matches_the_receipt_surface() -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "lineage-read-receipt-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    receipt = lineage_receipt(
        source_urn="urn:li:dataset:source",
        max_hops=1,
        max_results=10,
        source_field=None,
        targets=(),
    ).as_dict()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schemaVersion"]["const"] == receipt["schemaVersion"]
    assert set(schema["required"]) == set(receipt)
    for key, value in receipt["readConsistency"].items():
        property_schema = schema["properties"]["readConsistency"]["properties"][key]
        if value is not None:
            assert value in property_schema["enum"]
