from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from lineage_guard.domain import IncidentReport

MAX_SCENARIO_ROWS = 10_000
MAX_TEXT_LENGTH = 256
MAX_ABSOLUTE_CENTS = 9_223_372_036_854_775_807


class RecoveryVerdict(StrEnum):
    REJECTED = "rejected"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True)
class RecoveryRow:
    record_id: str
    billing_amount_cents: int
    region: str


@dataclass(frozen=True, slots=True)
class RecoveryScenario:
    current: tuple[RecoveryRow, ...]
    trusted: tuple[RecoveryRow, ...]
    total_tolerance_cents: int = 0

    def __post_init__(self) -> None:
        if not self.current or len(self.current) > MAX_SCENARIO_ROWS:
            raise ValueError(f"current rows must contain 1 to {MAX_SCENARIO_ROWS} records")
        if len(self.trusted) > MAX_SCENARIO_ROWS:
            raise ValueError(f"trusted rows cannot exceed {MAX_SCENARIO_ROWS} records")
        if (
            isinstance(self.total_tolerance_cents, bool)
            or not isinstance(self.total_tolerance_cents, int)
            or self.total_tolerance_cents < 0
            or self.total_tolerance_cents > MAX_ABSOLUTE_CENTS
        ):
            raise ValueError("total tolerance must be a non-negative integer number of cents")
        for label, rows in (("current", self.current), ("trusted", self.trusted)):
            identifiers = [row.record_id for row in rows]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} record identifiers must be unique")
            for row in rows:
                if (
                    not isinstance(row.record_id, str)
                    or not row.record_id
                    or len(row.record_id) > MAX_TEXT_LENGTH
                    or not isinstance(row.region, str)
                    or not row.region
                    or len(row.region) > MAX_TEXT_LENGTH
                ):
                    raise ValueError(f"{label} text values must contain 1 to 256 characters")
                if (
                    isinstance(row.billing_amount_cents, bool)
                    or not isinstance(row.billing_amount_cents, int)
                    or abs(row.billing_amount_cents) > MAX_ABSOLUTE_CENTS
                ):
                    raise ValueError(f"{label} billing amounts must be integer cents")


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    candidate_id: str
    title: str
    query: str


@dataclass(frozen=True, slots=True)
class RecoveryCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate_id: str
    title: str
    verdict: RecoveryVerdict
    checks: tuple[RecoveryCheck, ...]
    before_invalid_rows: int
    after_invalid_rows: int
    trusted_total_cents: int
    candidate_total_cents: int
    query_sha256: str
    output_sha256: str


@dataclass(frozen=True, slots=True)
class RecoveryCertificate:
    schema_version: int
    certificate_id: str
    incident_id: str
    context_sha256: str
    candidate_id: str
    transition: str
    query_sha256: str
    output_sha256: str
    checks: tuple[RecoveryCheck, ...]
    certificate_sha256: str


@dataclass(frozen=True, slots=True)
class RecoveryBundle:
    schema_version: int
    incident_id: str
    context_sha256: str
    evaluations: tuple[CandidateEvaluation, ...]
    certificate: RecoveryCertificate | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


CLAMP_TO_ZERO = RepairCandidate(
    "clamp-to-zero",
    "Clamp invalid billing values to zero",
    """SELECT record_id,
       CASE WHEN billing_amount_cents < 0 THEN 0 ELSE billing_amount_cents END
           AS billing_amount_cents,
       region
FROM current_data
ORDER BY record_id""",
)

RESTORE_TRUSTED_VALUE = RepairCandidate(
    "restore-trusted-value",
    "Restore invalid values from the trusted snapshot",
    """SELECT current.record_id,
       CASE WHEN current.billing_amount_cents < 0
            THEN trusted.billing_amount_cents
            ELSE current.billing_amount_cents END AS billing_amount_cents,
       current.region
FROM current_data AS current
LEFT JOIN trusted_snapshot AS trusted USING (record_id)
ORDER BY current.record_id""",
)

DEFAULT_CANDIDATES = (CLAMP_TO_ZERO, RESTORE_TRUSTED_VALUE)


class CounterfactualRecoveryLab:
    def evaluate(
        self,
        report: IncidentReport,
        scenario: RecoveryScenario,
    ) -> RecoveryBundle:
        context_sha256 = recovery_context_sha256(report, scenario)
        evaluations = tuple(
            self._evaluate_candidate(candidate, scenario) for candidate in DEFAULT_CANDIDATES
        )
        verified = next(
            (
                evaluation
                for evaluation in evaluations
                if evaluation.verdict == RecoveryVerdict.VERIFIED
            ),
            None,
        )
        certificate = (
            _certificate(report.incident_id, context_sha256, verified) if verified else None
        )
        return RecoveryBundle(1, report.incident_id, context_sha256, evaluations, certificate)

    @staticmethod
    def _evaluate_candidate(
        candidate: RepairCandidate, scenario: RecoveryScenario
    ) -> CandidateEvaluation:
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                "CREATE TABLE current_data "
                "(record_id TEXT PRIMARY KEY, billing_amount_cents INTEGER NOT NULL, "
                "region TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE trusted_snapshot "
                "(record_id TEXT PRIMARY KEY, billing_amount_cents INTEGER NOT NULL, "
                "region TEXT NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO current_data VALUES (?, ?, ?)",
                [(row.record_id, row.billing_amount_cents, row.region) for row in scenario.current],
            )
            connection.executemany(
                "INSERT INTO trusted_snapshot VALUES (?, ?, ?)",
                [(row.record_id, row.billing_amount_cents, row.region) for row in scenario.trusted],
            )
            output = connection.execute(candidate.query).fetchall()

        before_invalid = sum(row.billing_amount_cents < 0 for row in scenario.current)
        after_invalid = sum(amount is not None and amount < 0 for _, amount, _ in output)
        null_amounts = sum(amount is None for _, amount, _ in output)
        trusted_total = sum(row.billing_amount_cents for row in scenario.trusted)
        candidate_total = sum(amount for _, amount, _ in output if amount is not None)
        current_shape = sorted((row.record_id, row.region) for row in scenario.current)
        output_shape = sorted((record_id, region) for record_id, _, region in output)
        trusted_identifiers = {row.record_id for row in scenario.trusted}
        invalid_identifiers = {
            row.record_id for row in scenario.current if row.billing_amount_cents < 0
        }
        checks = (
            RecoveryCheck(
                "source_failure_reproduced",
                before_invalid > 0,
                f"observed {before_invalid} invalid source row(s)",
            ),
            RecoveryCheck(
                "quality_rule_passed",
                after_invalid == 0 and null_amounts == 0,
                f"candidate has {after_invalid} negative and {null_amounts} null amount(s)",
            ),
            RecoveryCheck(
                "row_count_preserved",
                len(output) == len(scenario.current),
                f"row count {len(scenario.current)} -> {len(output)}",
            ),
            RecoveryCheck(
                "non_target_data_preserved",
                current_shape == output_shape,
                "record identity and region values are unchanged",
            ),
            RecoveryCheck(
                "trusted_replacements_available",
                invalid_identifiers <= trusted_identifiers,
                f"trusted snapshot covers {len(invalid_identifiers & trusted_identifiers)} of "
                f"{len(invalid_identifiers)} invalid record(s)",
            ),
            RecoveryCheck(
                "trusted_total_within_tolerance",
                abs(candidate_total - trusted_total) <= scenario.total_tolerance_cents,
                f"candidate total {candidate_total}; trusted total {trusted_total}; "
                f"tolerance {scenario.total_tolerance_cents} cents",
            ),
        )
        verdict = (
            RecoveryVerdict.VERIFIED
            if all(check.passed for check in checks)
            else RecoveryVerdict.REJECTED
        )
        return CandidateEvaluation(
            candidate.candidate_id,
            candidate.title,
            verdict,
            checks,
            before_invalid,
            after_invalid,
            trusted_total,
            candidate_total,
            sha256((candidate.query.rstrip() + "\n").encode()).hexdigest(),
            canonical_sha256(output),
        )


def demo_recovery_scenario() -> RecoveryScenario:
    return RecoveryScenario(
        current=(
            RecoveryRow("patient-001", -5_000, "north"),
            RecoveryRow("patient-002", 12_000, "south"),
            RecoveryRow("patient-003", 8_000, "west"),
        ),
        trusted=(
            RecoveryRow("patient-001", 10_000, "north"),
            RecoveryRow("patient-002", 12_000, "south"),
            RecoveryRow("patient-003", 8_000, "west"),
        ),
    )


def load_recovery_scenario(path: Path) -> RecoveryScenario:
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("recovery scenario exceeds 2 MB")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("recovery scenario schema_version must be 1")
        allowed = {"schema_version", "current", "trusted", "total_tolerance_cents"}
        if set(payload) - allowed:
            raise ValueError("recovery scenario contains unknown fields")
        return RecoveryScenario(
            tuple(_recovery_row(item) for item in payload.get("current", [])),
            tuple(_recovery_row(item) for item in payload.get("trusted", [])),
            payload.get("total_tolerance_cents", 0),
        )
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as error:
        raise ValueError("invalid recovery scenario") from error


def _recovery_row(value: Any) -> RecoveryRow:
    if not isinstance(value, dict) or set(value) != {
        "record_id",
        "billing_amount_cents",
        "region",
    }:
        raise ValueError("recovery rows require record_id, billing_amount_cents, and region")
    return RecoveryRow(value["record_id"], value["billing_amount_cents"], value["region"])


def verify_certificate(certificate: RecoveryCertificate) -> bool:
    body = {
        "schema_version": certificate.schema_version,
        "certificate_id": certificate.certificate_id,
        "incident_id": certificate.incident_id,
        "context_sha256": certificate.context_sha256,
        "candidate_id": certificate.candidate_id,
        "transition": certificate.transition,
        "query_sha256": certificate.query_sha256,
        "output_sha256": certificate.output_sha256,
        "checks": [asdict(check) for check in certificate.checks],
    }
    return canonical_sha256(body) == certificate.certificate_sha256


def _certificate(
    incident_id: str, context_sha256: str, evaluation: CandidateEvaluation
) -> RecoveryCertificate:
    certificate_id = sha256(
        f"{incident_id}|{context_sha256}|{evaluation.candidate_id}".encode()
    ).hexdigest()[:16]
    body = {
        "schema_version": 1,
        "certificate_id": certificate_id,
        "incident_id": incident_id,
        "context_sha256": context_sha256,
        "candidate_id": evaluation.candidate_id,
        "transition": "quarantine_to_release",
        "query_sha256": evaluation.query_sha256,
        "output_sha256": evaluation.output_sha256,
        "checks": [asdict(check) for check in evaluation.checks],
    }
    return RecoveryCertificate(
        1,
        certificate_id,
        incident_id,
        context_sha256,
        evaluation.candidate_id,
        "quarantine_to_release",
        evaluation.query_sha256,
        evaluation.output_sha256,
        evaluation.checks,
        canonical_sha256(body),
    )


def canonical_sha256(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def recovery_context_sha256(report: IncidentReport, scenario: RecoveryScenario) -> str:
    return canonical_sha256(
        {
            "report": report.as_dict(),
            "current": [asdict(row) for row in scenario.current],
            "trusted": [asdict(row) for row in scenario.trusted],
            "total_tolerance_cents": scenario.total_tolerance_cents,
        }
    )
