# ADR 0007: Content-addressed immune memory in DataHub

- Status: accepted
- Date: 2026-08-04

## Decision

Use one immutable, versioned JSON record as the semantic source of truth. Deploy it through a
bounded base64url envelope appended with DataHub MCP `update_description`; map the identical bytes
to the proposed native Evidence aspect when available. Incident records are roots. Prevention
outcomes link to a root with `parent_digest`.

## Why

This works against the repository's pinned and tested MCP surface, preserves DataHub authorization,
supports fresh-agent retrieval, and avoids a second migration model. Content identity makes replay
and semantic deduplication deterministic. A compact append-only record also retains history that a
mutable “latest status” property would erase.

## Consequences

Catalog descriptions are not an ideal high-volume event store and append is not transactional.
Strict bounds prevent unbounded catalog growth from entering the agent; operators should migrate
records to a native aspect as it becomes available. Integrity is verified, but authentication still
depends on DataHub access controls and audit logs. Searchable Documents may mirror records later,
but cannot become an independent authority.
