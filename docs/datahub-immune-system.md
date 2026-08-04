# DataHub immune system

LineageGuard makes incident learning durable catalog state. Agent A reads DataHub lineage, contains
an incident, and writes a bounded, content-addressed incident memory to the source dataset. Agent B
starts with a fresh DataHub read, reconstructs and verifies that memory, replays a proposed change
against the stored Incident Genome, and writes the prevention outcome and inherited evidence gaps
back to the same asset.

```text
DataHub lineage → Agent A → incident memory → DataHub → Agent B → blocked/safe change
                                  ^                         |
                                  └── prevention outcome ───┘
```

## Deployable carrier and native destination

The canonical contract is
[`datahub-immune-memory-v1.schema.json`](../schemas/datahub-immune-memory-v1.schema.json). The same
canonical JSON bytes and SHA-256 identity are used in both mappings:

| Contract field | Deployable today through DataHub MCP 0.6 | Proposed native Evidence aspect |
|---|---|---|
| `subject_urn` | `update_description.entity_urn` | aspect owner/entity URN |
| complete record | base64url envelope in appended description | aspect value |
| `record_digest` | envelope header and verified payload | aspect key/content digest |
| `parent_digest` | payload link | typed evidence relationship |
| `record_type` | payload discriminator | evidence type discriminator |

The description envelope is a compatibility carrier, not a claim that DataHub currently ships this
aspect. A native aspect can ingest the decoded record without changing its digest, making migration
lossless. Structured properties were rejected as the default because they require pre-provisioned
property definitions; Documents remain a possible discoverability mirror, not the source of truth.

## Integrity and authority

- Every record is canonicalized, bounded to 64 KiB, and verified before it becomes policy input.
- Descriptions are scanned only up to 2 MB and at most 100 distinct records are accepted.
- Repeated digests are semantically deduplicated. A retry can still leave a physical duplicate
  description block because append is not transactional; this is an explicit transport limitation.
- A digest proves integrity, not authorship. DataHub authentication and authorization control reads
  and writes; a future native aspect should additionally expose actor and audit metadata.
- Records contain decisions and evidence references, never raw rows, credentials, or webhook data.
- Unverified/tampered genomes fail closed. Evidence gaps are preserved into prevention outcomes.

## Two-agent acceptance path

The integration tests instantiate fresh DataHub graph snapshots around a stateful MCP session. They
prove that one client writes an incident envelope, a second client retrieves it from the changed
DataHub description, rejects guard removal using the inherited genome, writes the linked prevention
outcome, and a third fresh read sees both records. No Python object is passed between the agents.

In live mode, the first half is enabled by `--apply` only:

```bash
lineage-guard --mode mcp --gms-url https://datahub.example/gms \
  --signal-file quality-event.json --recovery-lab --chronos --proofgraph \
  --recovery-scenario-file recovery-scenario.json --changes-file context-changes.json \
  --apply --output immune-memory.json
```

The Python `InheritedMemoryAgent` is the bounded second-agent interface for CI/change-management
integrations. Its default is proposal-only; `approved=True` is required to write its outcome.
