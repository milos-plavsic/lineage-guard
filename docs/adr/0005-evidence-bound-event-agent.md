# ADR 0005: Evidence-bound event agent and enforcement protocol

- Status: accepted
- Date: 2026-08-02

## Context

Dataset reachability and keyword matches cannot prove that a particular failed field affects—or does
not affect—a downstream asset. An operational agent also needs durable delivery semantics and a real
action boundary; a manual CLI plus a catalog tag is insufficient evidence of containment.

An LLM in the authorization path would add probabilistic behavior without improving the provenance
of a continuation decision. Cross-system action cannot be made transactionally atomic between an
orchestrator and DataHub.

## Decision

LineageGuard uses a deterministic evidence lattice:

1. confirmed field dependency can quarantine when business materiality is also present;
2. complete field exclusion is the only evidence that can authorize continuation;
3. descriptive metadata can indicate exposure but can only monitor;
4. insufficient evidence requires review.

The agent accepts bounded HMAC-authenticated events, journals payload identity and processing leases
in SQLite, records every stage, and returns the durable original result for redelivery. Approved
action sends an independently signed, incident-idempotent plan to an operator-controlled endpoint.
Every unknown directive defaults to `hold`; only confirmed exclusions receive `allow`. The
orchestrator must acknowledge the exact incident before DataHub context is updated.

## Consequences

- Missing column lineage reduces automation instead of creating a false claim of safety.
- The safety decision is reproducible, auditable, and independent of model availability.
- The generic enforcement protocol integrates with any orchestrator but requires a receiver adapter.
- Orchestrator containment precedes DataHub write-back, favoring safety during partial failure.
- SQLite supports a single-node deployment; coordinated multi-node workers require a shared
  transactional journal.
- Ambiguous network outcomes still require reconciliation despite idempotency keys and durable state.
