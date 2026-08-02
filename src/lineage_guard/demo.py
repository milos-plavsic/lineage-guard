from __future__ import annotations

from lineage_guard.domain import Asset, LineageEdge, QualitySignal, Severity

RAW = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.raw_patients,PROD)"
STAGING = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.staging_patients,PROD)"
BILLING = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.mart_billing,PROD)"
DEMOGRAPHICS = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.mart_demographics,PROD)"


def assets() -> tuple[Asset, ...]:
    return (
        Asset(RAW, "raw_patients", "Raw healthcare records", ("Data Platform",)),
        Asset(STAGING, "staging_patients", "Standardized patient records", ("Data Platform",)),
        Asset(
            BILLING,
            "mart_billing",
            "Financial billing and insurance reporting",
            ("Finance Analytics",),
            ("Critical", "billing"),
            240,
        ),
        Asset(
            DEMOGRAPHICS,
            "mart_demographics",
            "Population age and demographic reporting",
            ("Clinical Analytics",),
            ("demographics",),
            80,
        ),
    )


def edges() -> tuple[LineageEdge, ...]:
    return (
        LineageEdge(RAW, STAGING),
        LineageEdge(STAGING, BILLING),
        LineageEdge(STAGING, DEMOGRAPHICS),
    )


def negative_billing_signal() -> QualitySignal:
    return QualitySignal(
        asset_urn=RAW,
        field="billing_amount",
        rule="values must be non-negative",
        observed="37 negative values in the latest batch",
        severity=Severity.HIGH,
        affected_concerns=("billing", "financial"),
    )
