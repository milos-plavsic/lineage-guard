# DataHub Evidence Chain

The DataHub Evidence Chain is LineageGuard's interoperable contract for durable agent decisions. It
generalizes the immune-memory loop into an append-only causal graph that any DataHub agent can read
without trusting the process that wrote it.

## Invariants

1. Every record is canonical JSON bounded to 64 KiB and identified by its SHA-256 digest.
2. Incident records are roots. Outcomes and lifecycle records name an existing parent digest.
3. A record belongs to exactly one DataHub subject and incident; cross-chain parents are invalid.
4. Records are immutable. Correction occurs through supersession, expiry, or revocation records.
5. Native Document URNs are deterministic: `urn:li:document:lineage-guard-<digest>`.
6. DataHub `related_documents` mirrors the digest parent edge; the encoded parent remains the
   portable source of truth.
7. Missing parents, invalid digests, cycles, malformed lifecycle payloads, absent replacements, and
   record-limit overflow fail closed.
8. Agent B derives current lineage and governance context from a fresh DataHub read. Request payloads
   cannot substitute catalog state.
   Schema fields, lineage edges, and governance labels are canonicalized as sorted sets before
   hashing, so an MCP traversal-order change cannot create false context drift.
9. Keys named like credentials are rejected recursively before persistence. Record scans are bounded
   to 2 MB and 100 records.
10. Integrity does not imply identity. DataHub authorization/audit is the default trust boundary;
    detached attestations add portable authentication where required.

## Record lifecycle

```text
incident ──→ prevention_outcome ──→ supersession
    │                │                    └──→ replacement
    │                ├──→ expiry
    │                └──→ revocation
    └──→ prevention_outcome
```

Lifecycle records contain a bounded reason, an RFC 3339 UTC effective time, and—only for
supersession—the replacement digest. Future-effective records are verified but do not change current
state. Revoked, expired, or superseded incident roots are not eligible policy inputs.

## DataHub projection

| Protocol concept | DataHub representation |
|---|---|
| operational event | native `CUSTOM / LINEAGE_GUARD` Incident |
| immutable record | Decision Document with deterministic URN |
| causal parent | `related_documents` plus `parent_digest` |
| governed subject | `related_assets` |
| discovery | `lineage-guard`, `immune-memory`, and record-type topics |
| compatibility | verified bounded description envelope |
| future native model | Evidence/Decision aspect with identical canonical bytes |

Documents provide human visibility and AI context today. A future native Evidence aspect can ingest
the same canonical records without changing their identities or policy semantics.

## Operations

All commands are read-only unless `--apply` is explicitly present:

```bash
lineage-guard --mode mcp --gms-url "$DATAHUB_GMS_URL" --source-urn "$URN" \
  --evidence-action verify --output chain-verification.json

lineage-guard --mode mcp --gms-url "$DATAHUB_GMS_URL" --source-urn "$URN" \
  --evidence-action expire --record-digest "$DIGEST" --reason "context TTL elapsed" \
  --effective-at 2026-08-05T12:00:00Z --apply

lineage-guard --mode mcp --gms-url "$DATAHUB_GMS_URL" --source-urn "$URN" \
  --evidence-action supersede --record-digest "$OLD" --replacement-digest "$NEW" \
  --reason "new verified policy evidence" --effective-at 2026-08-05T12:00:00Z --apply
```

For a detached HMAC-SHA-256 attestation, provide a secret of at least 32 bytes through
`LINEAGE_GUARD_ATTESTATION_SECRET`, select `--evidence-action attest`, supply the target digest and a
public `--attestation-key-id`, and protect the resulting attestation as an independent artifact.
HMAC is suitable for a shared administrative trust domain; asymmetric organizational signing can
implement the same detached contract without changing evidence records.

Install `.[mcp]` and run `lineage-guard-evidence-mcp` to expose bounded read-only tools for chain
verification, lifecycle-state lookup, and attestation verification. The server reads the HMAC
secret from its environment and never carries it in MCP requests, traces, or model context. The
portable JSON contracts are published in `schemas/datahub-evidence-chain-v1.schema.json`,
`schemas/datahub-immune-memory-v1.schema.json`, and
`schemas/datahub-evidence-attestation-v1.schema.json`.

LineageGuard's own `LineageGuard_Quarantined` operational tag is deliberately excluded from the
immunity context fingerprint. All external ownership and governance labels remain inputs; this one
exclusion prevents the enforcement action from invalidating the proof that authorized it.

## Retention and privacy

Evidence records should contain metadata and digests, not row data or credentials. DataHub access
policies, domains, ownership, and audit logs govern visibility. Expiry changes policy eligibility but
does not erase audit history. Physical deletion remains a separately authorized retention operation
because silently deleting a parent would invalidate descendants.

## Upstream path

The protocol deliberately composes current DataHub primitives. The upstream sequence is:

1. Make Document excerpt completeness explicit for safe agent reads.
2. Standardize retry-safe, deterministic Document writes and conflict receipts.
3. Publish the record and verification contract as an RFC backed by live evidence.
4. Add a native Evidence/Decision model only after maintainer agreement on ownership,
   authorization, retention, search, and event semantics.
