from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from lineage_guard.chronos import ChronosBundle
from lineage_guard.domain import Action, IncidentReport
from lineage_guard.proofgraph import ProofBundle, ProofGraph, verify_proof_bundle
from lineage_guard.recovery import DEFAULT_CANDIDATES, RecoveryBundle, canonical_sha256

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    relative_path: str
    content: str
    sha256: str

    @classmethod
    def create(cls, relative_path: str, content: str) -> GeneratedArtifact:
        normalized = content.rstrip() + "\n"
        digest = sha256(normalized.encode("utf-8")).hexdigest()
        return cls(relative_path, normalized, digest)


class RemediationGenerator:
    """Generate reviewable artifacts without executing changes against source systems."""

    def generate(
        self,
        report: IncidentReport,
        recovery: RecoveryBundle | None = None,
        chronos: ChronosBundle | None = None,
        proofgraph: ProofGraph | None = None,
        proof_bundle: ProofBundle | None = None,
    ) -> tuple[GeneratedArtifact, ...]:
        table = self._identifier(report.source.name, "source asset name")
        field = self._identifier(report.signal.field, "quality signal field")
        test_name = f"assert_{field}_non_negative"
        sql = (
            f"-- LineageGuard incident {report.incident_id}\n"
            f"-- Returns violating rows; an empty result means the assertion passes.\n"
            f'SELECT *\nFROM "{table}"\nWHERE "{field}" < 0'
        )
        branch_policy = {
            "schema_version": 2,
            "incident_id": report.incident_id,
            "source_urn": report.source.urn,
            "default_action": "require-human-review",
            "branches": [
                {
                    "asset_urn": decision.asset.urn,
                    "asset_name": decision.asset.name,
                    "action": decision.action,
                    "risk_score": decision.risk_score,
                    "evidence_strength": decision.evidence_strength,
                    "evidence": list(decision.evidence),
                    "rationale": decision.rationale,
                }
                for decision in report.decisions
            ],
        }
        summary = self._summary(report, test_name)
        artifacts = (
            GeneratedArtifact.create(f"quality/{test_name}.sql", sql),
            GeneratedArtifact.create(
                f"policies/{report.incident_id}.json",
                json.dumps(branch_policy, indent=2),
            ),
            GeneratedArtifact.create(f"reports/{report.incident_id}.md", summary),
        )
        return (
            artifacts
            + self._recovery_artifacts(recovery)
            + self._chronos_artifacts(report, chronos)
            + self._proofgraph_artifacts(report, proofgraph, proof_bundle)
        )

    def write(
        self,
        report: IncidentReport,
        destination: Path,
        recovery: RecoveryBundle | None = None,
        chronos: ChronosBundle | None = None,
        proofgraph: ProofGraph | None = None,
        proof_bundle: ProofBundle | None = None,
    ) -> tuple[GeneratedArtifact, ...]:
        artifacts = self.generate(report, recovery, chronos, proofgraph, proof_bundle)
        root = destination.resolve()
        for artifact in artifacts:
            target = (root / artifact.relative_path).resolve()
            if root not in target.parents:
                raise ValueError(f"Artifact path escapes destination: {artifact.relative_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(artifact.content, encoding="utf-8", newline="\n")
        manifest = {
            "schema_version": 1,
            "incident_id": report.incident_id,
            "artifacts": [
                {"path": artifact.relative_path, "sha256": artifact.sha256}
                for artifact in artifacts
            ],
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        return artifacts

    @staticmethod
    def _proofgraph_artifacts(
        report: IncidentReport,
        proofgraph: ProofGraph | None,
        proof_bundle: ProofBundle | None,
    ) -> tuple[GeneratedArtifact, ...]:
        if proofgraph is None and proof_bundle is None:
            return ()
        if (
            proofgraph is None
            or proof_bundle is None
            or proofgraph.incident_id != report.incident_id
            or not verify_proof_bundle(proof_bundle, proofgraph)
        ):
            raise ValueError("ProofGraph artifacts require a valid matching Proof Bundle")
        return (
            GeneratedArtifact.create(
                f"proofgraph/graphs/{report.incident_id}.json",
                json.dumps(proofgraph.as_dict(), indent=2),
            ),
            GeneratedArtifact.create(
                f"proofgraph/bundles/{report.incident_id}.intoto.json",
                json.dumps(asdict(proof_bundle), indent=2),
            ),
            GeneratedArtifact.create(
                "proofgraph/evidence-gaps.json",
                json.dumps(
                    {
                        "schema_version": proofgraph.schema_version,
                        "evidence_gaps": [asdict(item) for item in proofgraph.evidence_gaps],
                    },
                    indent=2,
                ),
            ),
            GeneratedArtifact.create(
                "proofgraph/causal-cuts.json",
                json.dumps(
                    {
                        "schema_version": proofgraph.schema_version,
                        "causal_cuts": [asdict(item) for item in proofgraph.causal_cuts],
                        "counterfactuals": [asdict(item) for item in proofgraph.counterfactuals],
                    },
                    indent=2,
                ),
            ),
        )

    @staticmethod
    def _recovery_artifacts(recovery: RecoveryBundle | None) -> tuple[GeneratedArtifact, ...]:
        if recovery is None:
            return ()
        candidates = {candidate.candidate_id: candidate for candidate in DEFAULT_CANDIDATES}
        artifacts = tuple(
            GeneratedArtifact.create(
                f"recovery/candidates/{evaluation.candidate_id}.sql",
                candidates[evaluation.candidate_id].query,
            )
            for evaluation in recovery.evaluations
        )
        evaluation_document = {
            "schema_version": recovery.schema_version,
            "incident_id": recovery.incident_id,
            "context_sha256": recovery.context_sha256,
            "evaluations": [asdict(evaluation) for evaluation in recovery.evaluations],
        }
        artifacts += (
            GeneratedArtifact.create(
                "recovery/evaluations.json", json.dumps(evaluation_document, indent=2)
            ),
        )
        if recovery.certificate is not None:
            artifacts += (
                GeneratedArtifact.create(
                    f"recovery/certificates/{recovery.certificate.certificate_id}.json",
                    json.dumps(asdict(recovery.certificate), indent=2),
                ),
            )
        return artifacts

    @classmethod
    def _chronos_artifacts(
        cls, report: IncidentReport, chronos: ChronosBundle | None
    ) -> tuple[GeneratedArtifact, ...]:
        if chronos is None:
            return ()
        if chronos.genome.incident_id != report.incident_id:
            raise ValueError("Chronos genome does not match the incident report")
        if canonical_sha256([asdict(row) for row in chronos.historical_fixture]) != (
            chronos.genome.historical_fixture_sha256
        ):
            raise ValueError("Chronos historical fixture does not match the incident genome")
        fixture = "\n".join(
            [
                "CREATE TABLE historical_negative_billing (",
                "    record_id TEXT PRIMARY KEY,",
                "    billing_amount_cents INTEGER NOT NULL,",
                "    region TEXT NOT NULL",
                ");",
                *(
                    f"INSERT INTO historical_negative_billing VALUES "
                    f"({cls._sql_literal(row.record_id)}, {row.billing_amount_cents}, "
                    f"{cls._sql_literal(row.region)});"
                    for row in chronos.historical_fixture
                ),
            ]
        )
        assertion = "SELECT *\nFROM historical_negative_billing\nWHERE billing_amount_cents < 0"
        policy = {
            "schema_version": 1,
            "genome_id": chronos.genome.genome_id,
            "context_sha256": chronos.genome.context_sha256,
            "required_invariants": list(chronos.genome.required_invariants),
            "rule": (
                "block when the historical failure is not detected; revalidate on context drift"
            ),
        }
        writeback = {
            "schema_version": 1,
            "requires_explicit_approval": True,
            "append_description": {
                "urn": report.source.urn,
                "markdown": (
                    f"\n\n### LineageGuard immunity {chronos.genome.genome_id}\n"
                    f"Incident `{report.incident_id}` compiled into preventive controls. "
                    f"Context: `{chronos.genome.context_sha256}`."
                ),
            },
            "add_tag": [
                {"urn": item.asset_urn, "tag": "urn:li:tag:LineageGuard_Immunized"}
                for item in chronos.coverage
                if item.status == "immunized"
            ],
        }
        artifacts = (
            GeneratedArtifact.create(
                f"immunity/genomes/{chronos.genome.genome_id}.json",
                json.dumps(asdict(chronos.genome), indent=2),
            ),
            GeneratedArtifact.create(f"immunity/regression/{report.incident_id}.sql", fixture),
            GeneratedArtifact.create(
                f"immunity/assertions/{report.signal.field}_historical_failure.sql",
                assertion,
            ),
            GeneratedArtifact.create(
                f"immunity/policies/{chronos.genome.genome_id}.json",
                json.dumps(policy, indent=2),
            ),
            GeneratedArtifact.create(
                "immunity/evaluations.json",
                json.dumps(
                    {
                        "schema_version": chronos.schema_version,
                        "evaluations": [asdict(item) for item in chronos.evaluations],
                    },
                    indent=2,
                ),
            ),
            GeneratedArtifact.create(
                "immunity/coverage.json",
                json.dumps(
                    {
                        "schema_version": chronos.schema_version,
                        "coverage": [asdict(item) for item in chronos.coverage],
                    },
                    indent=2,
                ),
            ),
            GeneratedArtifact.create(
                "immunity/datahub-writeback.json", json.dumps(writeback, indent=2)
            ),
            GeneratedArtifact.create(
                f"immunity/runbooks/{chronos.genome.genome_id}.md",
                cls._immunity_runbook(chronos),
            ),
        )
        passports = tuple(
            GeneratedArtifact.create(
                f"immunity/passports/{item.change.change_id}.intoto.json",
                json.dumps(asdict(item.passport), indent=2),
            )
            for item in chronos.evaluations
            if item.passport is not None
        )
        return artifacts + passports

    @staticmethod
    def _sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def _immunity_runbook(chronos: ChronosBundle) -> str:
        return "\n".join(
            [
                f"# Immunity runbook: {chronos.genome.genome_id}",
                "",
                f"Historical incident: `{chronos.genome.incident_id}`.",
                f"Context fingerprint: `{chronos.genome.context_sha256}`.",
                "",
                "Replay the historical fixture before approving an intersecting change.",
                "Block recurrence, require revalidation after context drift, and treat a passport",
                "as eligibility for approval—not deployment authorization.",
            ]
        )

    @staticmethod
    def _identifier(value: str, label: str) -> str:
        if not _SQL_IDENTIFIER.fullmatch(value):
            raise ValueError(f"Unsafe {label}: {value!r}")
        return value

    @staticmethod
    def _summary(report: IncidentReport, test_name: str) -> str:
        quarantined = [
            decision.asset.name
            for decision in report.decisions
            if decision.action == Action.QUARANTINE
        ]
        continuing = [
            decision.asset.name
            for decision in report.decisions
            if decision.action == Action.CONTINUE
        ]
        review = [
            decision.asset.name
            for decision in report.decisions
            if decision.action in {Action.MONITOR, Action.REQUIRE_REVIEW}
        ]
        return "\n".join(
            [
                f"# Remediation proposal: {report.incident_id}",
                "",
                f"Signal: `{report.signal.field}` {report.signal.rule} ({report.signal.observed}).",
                "",
                f"Quarantine: {', '.join(quarantined) or 'none'}.",
                f"Continue: {', '.join(continuing) or 'none'}.",
                f"Review: {', '.join(review) or 'none'}.",
                "",
                f"Validation query: `quality/{test_name}.sql`.",
                "",
                "No source data or orchestration state is changed by these artifacts. Apply only",
                "after owner review and successful validation in the target environment.",
            ]
        )
