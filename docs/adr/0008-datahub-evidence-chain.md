# ADR 0008: Immutable DataHub Evidence Chains

## Status

Accepted.

## Decision

Represent durable agent memory as an append-only, content-addressed causal chain. Use deterministic
DataHub Decision Documents and native document relations as the current projection, retain the
bounded description carrier for compatibility, and preserve canonical record identity for migration
to a future Evidence/Decision aspect.

Agent policy consumes only chains that pass complete verification. Current context is derived from a
fresh DataHub read. Lifecycle changes append supersession, expiry, or revocation records instead of
mutating history. Optional authentication is detached from immutable evidence content.

## Consequences

Retries become idempotent, parentage is visible in DataHub, historical decisions remain auditable,
and correction cannot conceal prior state. Search consistency may temporarily hide a just-written
record; deterministic URNs make a repeated write converge safely. Document projection remains less
queryable than a typed aspect, so the generic upstream model remains an RFC rather than a shipped
DataHub claim.
