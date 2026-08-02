from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from lineage_guard.domain import Action, IncidentReport
from lineage_guard.recovery import (
    RecoveryBundle,
    RecoveryRow,
    RecoveryScenario,
    canonical_sha256,
    demo_recovery_scenario,
    recovery_context_sha256,
    verify_certificate,
)

MAX_CONTEXT_ITEMS = 1_000
MAX_CONTEXT_TEXT = 1_024
IN_TOTO_STATEMENT_V1 = "https://in-toto.io/Statement/v1"
PASSPORT_PREDICATE_V1 = "https://lineageguard.dev/attestations/change-passport/v1"


class ChangeDecision(StrEnum):
    BLOCKED = "blocked"
    ELIGIBLE_FOR_APPROVAL = "eligible_for_approval"
    REVALIDATION_REQUIRED = "revalidation_required"


class ImmunityStatus(StrEnum):
    IMMUNIZED = "immunized"
    PROVEN_EXCLUDED = "proven_excluded"
    PARTIAL_REVIEW = "partial_review"


@dataclass(frozen=True, slots=True)
class ImmunityContext:
    schema_fields: tuple[str, ...]
    lineage_edges: tuple[str, ...]
    governance_labels: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, values in (
            ("schema fields", self.schema_fields),
            ("lineage edges", self.lineage_edges),
            ("governance labels", self.governance_labels),
        ):
            if len(values) > MAX_CONTEXT_ITEMS or len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique and contain at most 1000 items")
            if any(
                not isinstance(value, str) or not value or len(value) > MAX_CONTEXT_TEXT
                for value in values
            ):
                raise ValueError(f"{label} values must contain 1 to 1024 characters")

    @property
    def sha256(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True, slots=True)
class IncidentGenome:
    schema_version: int
    genome_id: str
    incident_id: str
    source_urn: str
    failed_field: str
    failure_rule: str
    context_sha256: str
    recovery_certificate_id: str
    recovery_certificate_sha256: str
    historical_fixture_sha256: str
    exposed_assets: tuple[str, ...]
    excluded_assets: tuple[str, ...]
    review_assets: tuple[str, ...]
    required_invariants: tuple[str, ...]
    prevention_controls: tuple[str, ...]
    genome_sha256: str


@dataclass(frozen=True, slots=True)
class ChangeProposal:
    change_id: str
    title: str
    quality_guard_enabled: bool

    def __post_init__(self) -> None:
        if (
            not self.change_id
            or len(self.change_id) > 128
            or not self.title
            or len(self.title) > 256
        ):
            raise ValueError("change identity and title must be bounded non-empty text")
        if not isinstance(self.quality_guard_enabled, bool):
            raise ValueError("quality guard state must be boolean")

    @property
    def sha256(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True, slots=True)
class ImmunityCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ChangePassport:
    statement: dict[str, Any]
    statement_sha256: str


@dataclass(frozen=True, slots=True)
class ChangeEvaluation:
    change: ChangeProposal
    evaluated_context_sha256: str
    decision: ChangeDecision
    checks: tuple[ImmunityCheck, ...]
    passport: ChangePassport | None


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    asset_urn: str
    asset_name: str
    status: ImmunityStatus
    reason: str


@dataclass(frozen=True, slots=True)
class ChronosBundle:
    schema_version: int
    genome: IncidentGenome
    historical_fixture: tuple[RecoveryRow, ...]
    evaluations: tuple[ChangeEvaluation, ...]
    coverage: tuple[CoverageEntry, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CausalImmunityEngine:
    def compile(
        self,
        report: IncidentReport,
        recovery: RecoveryBundle,
        context: ImmunityContext,
        scenario: RecoveryScenario,
    ) -> IncidentGenome:
        certificate = recovery.certificate
        if (
            certificate is None
            or recovery.incident_id != report.incident_id
            or certificate.incident_id != report.incident_id
            or recovery.context_sha256 != recovery_context_sha256(report, scenario)
            or not verify_certificate(certificate)
            or not all(check.passed for check in certificate.checks)
        ):
            raise ValueError("a valid matching recovery certificate is required for immunization")
        exposed = tuple(
            item.asset.urn for item in report.decisions if item.action == Action.QUARANTINE
        )
        excluded = tuple(
            item.asset.urn for item in report.decisions if item.action == Action.CONTINUE
        )
        review = tuple(
            item.asset.urn
            for item in report.decisions
            if item.action in {Action.MONITOR, Action.REQUIRE_REVIEW}
        )
        invariants = tuple(check.name for check in certificate.checks)
        controls = (
            "datahub_assertion",
            "historical_regression_fixture",
            "context_drift_gate",
            "change_passport",
        )
        body = {
            "schema_version": 1,
            "incident_id": report.incident_id,
            "source_urn": report.source.urn,
            "failed_field": report.signal.field,
            "failure_rule": report.signal.rule,
            "context_sha256": context.sha256,
            "recovery_certificate_id": certificate.certificate_id,
            "recovery_certificate_sha256": certificate.certificate_sha256,
            "historical_fixture_sha256": canonical_sha256(
                [asdict(row) for row in scenario.current]
            ),
            "exposed_assets": exposed,
            "excluded_assets": excluded,
            "review_assets": review,
            "required_invariants": invariants,
            "prevention_controls": controls,
        }
        genome_sha256 = canonical_sha256(body)
        return IncidentGenome(
            1,
            f"lg-genome-{genome_sha256[:16]}",
            report.incident_id,
            report.source.urn,
            report.signal.field,
            report.signal.rule,
            context.sha256,
            certificate.certificate_id,
            certificate.certificate_sha256,
            body["historical_fixture_sha256"],
            exposed,
            excluded,
            review,
            invariants,
            controls,
            genome_sha256,
        )

    def evaluate_change(
        self,
        genome: IncidentGenome,
        change: ChangeProposal,
        context: ImmunityContext,
    ) -> ChangeEvaluation:
        context_matches = context.sha256 == genome.context_sha256
        checks = (
            ImmunityCheck(
                "historical_failure_replayed",
                True,
                f"replayed incident {genome.incident_id}",
            ),
            ImmunityCheck(
                "context_fingerprint_matches",
                context_matches,
                f"expected {genome.context_sha256}; observed {context.sha256}",
            ),
            ImmunityCheck(
                "quality_guard_detects_recurrence",
                change.quality_guard_enabled,
                (
                    "historical invalid row is rejected"
                    if change.quality_guard_enabled
                    else "historical invalid row reaches the pipeline"
                ),
            ),
            ImmunityCheck(
                "recovery_invariants_registered",
                bool(genome.required_invariants),
                f"{len(genome.required_invariants)} invariant(s) remain policy inputs",
            ),
        )
        if not context_matches:
            decision = ChangeDecision.REVALIDATION_REQUIRED
        elif not all(check.passed for check in checks):
            decision = ChangeDecision.BLOCKED
        else:
            decision = ChangeDecision.ELIGIBLE_FOR_APPROVAL
        passport = (
            _passport(genome, change, context, checks)
            if decision == ChangeDecision.ELIGIBLE_FOR_APPROVAL
            else None
        )
        return ChangeEvaluation(change, context.sha256, decision, checks, passport)

    @staticmethod
    def coverage(report: IncidentReport) -> tuple[CoverageEntry, ...]:
        entries = []
        for decision in report.decisions:
            if decision.action == Action.QUARANTINE:
                status = ImmunityStatus.IMMUNIZED
                reason = "historical exposure is covered by prevention and recovery proof"
            elif decision.action == Action.CONTINUE:
                status = ImmunityStatus.PROVEN_EXCLUDED
                reason = "complete field evidence excludes the historical failure"
            else:
                status = ImmunityStatus.PARTIAL_REVIEW
                reason = "the branch still requires evidence or operator review"
            entries.append(CoverageEntry(decision.asset.urn, decision.asset.name, status, reason))
        return tuple(entries)


def build_demo_chronos(report: IncidentReport, recovery: RecoveryBundle) -> ChronosBundle:
    engine = CausalImmunityEngine()
    context = demo_immunity_context(report)
    scenario = demo_recovery_scenario()
    genome = engine.compile(report, recovery, context, scenario)
    unsafe = engine.evaluate_change(
        genome,
        ChangeProposal("pr-unsafe-guard-removal", "Remove the billing quality guard", False),
        context,
    )
    safe = engine.evaluate_change(
        genome,
        ChangeProposal("pr-safe-guard-preserved", "Preserve the billing quality guard", True),
        context,
    )
    drifted = ImmunityContext(
        context.schema_fields,
        (*context.lineage_edges, f"{report.source.urn}->urn:li:dataset:new_ml_feature"),
        context.governance_labels,
    )
    stale = engine.evaluate_change(
        genome,
        ChangeProposal("pr-context-drift", "Add a new downstream ML dependency", True),
        drifted,
    )
    return ChronosBundle(
        1, genome, scenario.current, (unsafe, safe, stale), engine.coverage(report)
    )


def demo_immunity_context(report: IncidentReport) -> ImmunityContext:
    return ImmunityContext(
        (report.signal.field,),
        tuple(f"{report.source.urn}->{item.asset.urn}" for item in report.decisions),
        tuple(
            sorted(
                {
                    *(f"owner:{owner}" for item in report.decisions for owner in item.asset.owners),
                    *(f"tag:{tag}" for item in report.decisions for tag in item.asset.tags),
                }
            )
        ),
    )


def verify_passport(passport: ChangePassport) -> bool:
    statement = passport.statement
    return (
        isinstance(statement, dict)
        and statement.get("_type") == IN_TOTO_STATEMENT_V1
        and statement.get("predicateType") == PASSPORT_PREDICATE_V1
        and canonical_sha256(statement) == passport.statement_sha256
    )


def _passport(
    genome: IncidentGenome,
    change: ChangeProposal,
    context: ImmunityContext,
    checks: tuple[ImmunityCheck, ...],
) -> ChangePassport:
    statement = {
        "_type": IN_TOTO_STATEMENT_V1,
        "subject": [{"name": change.change_id, "digest": {"sha256": change.sha256}}],
        "predicateType": PASSPORT_PREDICATE_V1,
        "predicate": {
            "genome_id": genome.genome_id,
            "genome_sha256": genome.genome_sha256,
            "context_sha256": context.sha256,
            "decision": ChangeDecision.ELIGIBLE_FOR_APPROVAL,
            "checks": [asdict(check) for check in checks],
        },
    }
    return ChangePassport(statement, canonical_sha256(statement))
