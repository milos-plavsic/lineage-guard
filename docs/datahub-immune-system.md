# DataHub immune system

LineageGuard makes incident learning durable catalog state. Agent A reads DataHub lineage, contains
an incident, and writes a bounded, content-addressed incident memory related to the source dataset.
Agent B
starts with a fresh DataHub read, reconstructs and verifies that memory, replays a proposed change
against the stored Incident Genome, and writes the prevention outcome and inherited evidence gaps
back to the same asset.

```text
DataHub lineage → Agent A → incident memory → DataHub → Agent B → blocked/safe change
                                  ^                         |
                                  └── prevention outcome ───┘
```

## Native composition and compatibility carrier

The canonical contract is
[`datahub-immune-memory-v1.schema.json`](../schemas/datahub-immune-memory-v1.schema.json). The same
canonical JSON bytes and SHA-256 identity are used in both mappings:

| Contract field | Preferred DataHub representation | Compatibility fallback | Proposed Evidence aspect |
|---|---|---|---|
| `subject_urn` | Document `related_assets` | `update_description.entity_urn` | aspect owner/entity URN |
| complete record | content-indexed Decision Document | base64url description envelope | aspect value |
| `record_digest` | verified Document content | envelope header and payload | aspect key/content digest |
| `parent_digest` | related record encoded in content | payload link | typed evidence relationship |
| `record_type` | Document subtype/topic and payload | payload discriminator | evidence type discriminator |

At runtime, LineageGuard prefers native Documents only when the MCP server advertises the complete
`save_document` path with independently negotiated `search_documents`. Documents are content indexed, related to the affected
asset, owned and audited by DataHub, and retrievable by a fresh agent. Older servers fall back to the
verified description envelope. The canonical record—not either carrier—is the semantic source of
truth, so both decode to the same digest.

With a separately supplied `--datahub-graphql-url` and `--apply`, LineageGuard also creates or reuses
a native `CUSTOM / LINEAGE_GUARD` DataHub Incident. This gives operators native lifecycle, priority
and authorization while the related Document holds the complete machine-verifiable memory. The
optional Evidence aspect remains a proposal for tighter typed provenance; it is not claimed to ship
in DataHub today.

## Integrity and authority

- Every record is canonicalized, bounded to 64 KiB, and verified before it becomes policy input.
- Each Document/description is scanned only up to 2 MB and at most 100 distinct records are accepted.
- Repeated digests are semantically deduplicated. A retry can still leave a physical duplicate
  description block because append is not transactional; this is an explicit transport limitation.
- A digest proves integrity, not authorship. DataHub authentication and authorization control reads
  and writes; a future native aspect should additionally expose actor and audit metadata.
- Records contain decisions and evidence references, never raw rows, credentials, or webhook data.
- Unverified/tampered genomes fail closed. Evidence gaps are preserved into prevention outcomes.

## Two-agent acceptance path

The integration tests instantiate fresh DataHub graph snapshots around a stateful MCP session. They
exercise both native Documents and the compatibility carrier: one client writes an incident record,
a second retrieves and applies it, and a third sees the linked outcome. No Python object is passed
between the agents.

In live mode, the first half is enabled by `--apply` only:

```bash
lineage-guard --mode mcp --gms-url https://datahub.example/gms \
  --signal-file quality-event.json --recovery-lab --chronos --proofgraph \
  --recovery-scenario-file recovery-scenario.json --changes-file context-changes.json \
  --apply --output immune-memory.json
```

Then stop Agent A and invoke the bounded Agent B CLI with a fresh MCP session:

```bash
lineage-guard --mode mcp --gms-url https://datahub.example/gms \
  --evaluate-change-file examples/inherited-change.json \
  --output inherited-evaluation.json
# Add --apply only after reviewing the proposed prevention outcome.
```

The Python `InheritedMemoryAgent` remains the embeddable interface for CI/change-management
integrations. Both interfaces default to proposal-only.
