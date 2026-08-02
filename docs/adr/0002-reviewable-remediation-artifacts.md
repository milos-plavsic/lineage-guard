# ADR 0002: Reviewable remediation artifacts

## Status

Accepted.

## Context

An incident agent must do more than describe a problem, but directly rewriting production data or
orchestration state from incomplete metadata is unsafe. Judges must also be able to evaluate output
quality without running the entire platform.

## Decision

LineageGuard generates deterministic, PR-ready artifacts rather than directly changing source
systems. Each incident yields a non-mutating SQL assertion, a machine-readable branch policy, a
human-readable remediation proposal, and a manifest containing SHA-256 digests. SQL identifiers are
accepted only from a conservative allowlist. Generated assertions return violating rows and are
tested against an in-memory SQL engine.

## Consequences

Operators can review, version, and validate every proposed change. Artifact integrity is auditable,
and examples remain judge-readable without infrastructure. Automatic source-system repair remains
outside the current trust boundary; adapters for specific orchestrators can be added later without
weakening the core safety model.
