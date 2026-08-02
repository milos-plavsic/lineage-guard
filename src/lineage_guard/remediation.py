from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from lineage_guard.domain import Action, IncidentReport

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

    def generate(self, report: IncidentReport) -> tuple[GeneratedArtifact, ...]:
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
        return (
            GeneratedArtifact.create(f"quality/{test_name}.sql", sql),
            GeneratedArtifact.create(
                f"policies/{report.incident_id}.json",
                json.dumps(branch_policy, indent=2),
            ),
            GeneratedArtifact.create(f"reports/{report.incident_id}.md", summary),
        )

    def write(self, report: IncidentReport, destination: Path) -> tuple[GeneratedArtifact, ...]:
        artifacts = self.generate(report)
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
