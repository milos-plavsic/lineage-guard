# ADR 0006: Content-addressed lineage read receipts

## Status

Accepted — 2026-08-04

## Context

The DataHub MCP lineage surface does not currently expose its backing source, response-cache
disposition, projection watermark, or a read-your-writes contract. An empty result therefore cannot
prove absence, while a non-empty result can retain an edge that was recently removed. A scalar
confidence score or `fresh` flag would collapse independent facts and encourage unsafe inference.

## Decision

Every enriched MCP lineage read returns a versioned, content-addressed receipt containing:

- separate source, consistency, completeness, cache, time, and watermark claims;
- mechanically derived capabilities and explicit limitations;
- canonical SHA-256 query, result, and whole-receipt digests; and
- no fabricated timestamp, watermark, or source assertion.

The existing `get_downstream_lineage` interface remains unchanged. Consumers that need provenance
use `read_downstream_lineage`. The adapter rejects a receipt request outside the source, field, or
hop scope used to load its snapshot.

Limitations distinguish unknown consistency from known eventual consistency and unknown
completeness from known truncation. This lets consumers select the correct remedy—retry for
convergence, continue traversal, corroborate, or abstain—without parsing prose.

Capabilities express what a consumer may conclude. An unknown read permits only
`USE_AS_OBSERVATION`. Assertion at a reference point, including absence, requires a complete
read-your-writes response with an explicit `asOf` or watermark. “At reference” is intentional: no
watermark is silently reinterpreted as the current instant.

Digests provide deterministic correlation and tamper evidence when a known receipt is compared;
they are not digital signatures and do not authenticate the server. URNs remain outside the
envelope, although predictable identifiers could still be guessed from an unsalted digest, so
digests must not be treated as anonymization.

## Consequences

- Current MCP reads fail closed with `UNKNOWN` claims while remaining auditable and composable.
- Future DataHub metadata can strengthen the envelope without changing its shape.
- Decision engines can authorize conclusions from capabilities instead of duplicating subtle
  freshness logic or interpreting confidence scores.
- Receipts are small and deterministic, but cryptographic authenticity would require a separately
  managed signing key and is deliberately outside this trust boundary.

## Alternatives rejected

- A confidence percentage has no stable calibration or enforceable meaning.
- A single freshness boolean conflates cache bypass, projection convergence, and traversal
  completeness.
- A request-time timestamp would look authoritative while saying nothing about source state.
- Signing local receipts would add key-management cost without authenticating the upstream data.
