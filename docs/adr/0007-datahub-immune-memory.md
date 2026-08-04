# ADR 0007: Content-addressed immune memory in DataHub

- Status: accepted
- Date: 2026-08-04

## Decision

Use one immutable, versioned JSON record as the semantic source of truth. Prefer an asset-related,
content-indexed DataHub Document when MCP exposes save and retrieval capabilities. Use a bounded
base64url `update_description` envelope only as a compatibility fallback. Optionally project
operational lifecycle into a native DataHub Incident through its authorized API. Map identical
canonical bytes to the proposed Evidence aspect when available. Incident records are roots;
prevention outcomes link to a root with `parent_digest`.

## Why

This composes DataHub's existing Incident and Document entities instead of rebuilding their roles,
preserves DataHub authorization and search, supports fresh-agent retrieval, and avoids a second
migration model. Runtime capability negotiation retains compatibility with older MCP servers.
Content identity makes replay and semantic deduplication deterministic.

## Consequences

Catalog descriptions are not an ideal high-volume event store and append is not transactional.
Strict bounds prevent unbounded catalog growth from entering the agent; operators should migrate
records to a native aspect as it becomes available. Integrity is verified, but authentication still
depends on DataHub access controls and audit logs. Searchable Documents may mirror records later,
but cannot become an independent authority.
