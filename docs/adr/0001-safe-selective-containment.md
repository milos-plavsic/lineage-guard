# ADR 0001: Safe selective containment

## Status

Accepted.

## Context

A quality failure can propagate through lineage while affecting downstream branches differently.
Blanket shutdowns damage availability; unconstrained autonomous mutations create unacceptable risk.

## Decision

LineageGuard separates evidence collection, deterministic impact scoring, proposed action, and
approved mutation. It defaults to dry-run. Mutations require an explicit approval flag and are
performed through a narrow metadata-graph port. A branch is quarantined only when the failing
concern is materially connected to that branch and its risk threshold is met.

## Consequences

Decisions are reproducible and testable without an LLM. DataHub remains the system of context and
institutional memory. Human approval is retained for mutations. The first release favors safety and
explainability over unconstrained autonomy.

