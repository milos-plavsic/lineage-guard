import json
from pathlib import Path


def test_live_datahub_evidence_records_selective_verified_writeback() -> None:
    evidence = json.loads(
        (
            Path(__file__).resolve().parents[1] / "examples/live-datahub-verification.json"
        ).read_text()
    )

    assert evidence["result"] == "pass"
    assert evidence["environment"]["mcpServerVersion"] == "0.6.0"
    assert evidence["lineage"] == {
        "datasetsDiscovered": 7,
        "relationshipsWritten": 6,
        "downstreamAssetsResolvedByMcp": 6,
        "columnRelationshipsWritten": 4,
        "exactColumnPathsConfirmedByMcp": 4,
    }
    assert evidence["incident"]["decisions"]["mart_billing"] == "quarantine"
    assert evidence["incident"]["decisions"]["mart_demographics"] == "require_review"
    assert evidence["writeback"] == {
        "sourceDescriptionContainsIncidentId": True,
        "quarantinedAssets": ["mart_billing", "v_billing_from_staging"],
        "unaffectedAssetWithoutQuarantineTag": "mart_demographics",
    }
    assert evidence["security"]["readOnlyRunMutationToolsEnabled"] is False
    assert evidence["security"]["writeRunMutationToolsEnabled"] is True
    assert evidence["durability"]["duplicateEventReplayedWithoutReprocessing"] is True
    assert evidence["durability"]["journalFinalStatus"] == "completed"
