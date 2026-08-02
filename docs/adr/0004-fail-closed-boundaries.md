# ADR 0004: Fail-closed integration boundaries

## Status

Accepted.

## Context

DataHub metadata and MCP responses are external input. Missing lineage, incompatible schemas, or
oversized responses must not silently become a claim that a branch is safe. Mutations also cross a
governance boundary and can partially succeed.

## Decision

Bound MCP payloads and lineage result counts, reject malformed or incomplete entity snapshots, keep
mutations disabled by default, require two explicit mutation gates, and return generic HTTP failures
without internal details. Preserve deterministic artifacts as the audit record and document manual
inspection before retrying a partial mutation.

## Consequences

Availability is sacrificed when context cannot be trusted: analysis stops rather than inventing an
answer. Resource consumption is bounded, credentials do not enter reports, and recovery is explicit.
Operators must repair metadata or permissions before analysis resumes.
