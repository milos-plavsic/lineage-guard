# Live DataHub MCP integration

LineageGuard uses the official `mcp-server-datahub` package over MCP stdio. Version `0.6.0` is
pinned by default so a new upstream release cannot silently change a judged build.

## Prerequisites

- DataHub Core or Cloud with a reachable GMS endpoint.
- A least-privilege service account token.
- `uvx` on `PATH`.
- The `LineageGuard_Quarantined` tag created in DataHub before applying write-back.
- Optional: a DataHub GMS `/api/graphql` endpoint and `Edit Incidents` privilege for native
  Incident projection.

Install the optional integration dependency:

```bash
uv sync --extra dev --extra mcp
```

Set the token without placing it on the command line or committing it:

```bash
export DATAHUB_GMS_TOKEN="..."
```

PowerShell:

```powershell
$env:DATAHUB_GMS_TOKEN = "..."
```

Run a read-only analysis:

```bash
lineage-guard \
  --mode mcp \
  --gms-url http://localhost:8080 \
  --source-urn 'urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.raw_patients,PROD)' \
  --field billing_amount \
  --concern billing \
  --concern financial \
  --output incident-report.json
```

Run the full proof pipeline from the same live MCP-derived report by supplying bounded, reviewable
recovery evidence and typed change proposals:

```bash
lineage-guard --mode mcp --gms-url "$DATAHUB_GMS_URL" --signal-file quality-event.json \
  --recovery-lab --chronos --proofgraph \
  --recovery-scenario-file examples/recovery-scenario.json \
  --changes-file examples/context-changes.json \
  --radar-weights-file examples/radar-weights.json \
  --output live-proof-report.json --artifacts-dir live-proof-pack
```

The incident report, assets, lineage, owners, tags, and risk decisions in this path come from live
DataHub MCP. Recovery rows and future changes cannot be inferred safely from catalog metadata; they
are operator-supplied, versioned, bounded inputs whose origins are recorded in `execution_context`.

The absence of `--apply` keeps mutation tools disabled at the MCP-server boundary. Adding `--apply`
both enables those server tools and authorizes LineageGuard to invoke them. This double gate is
intentional.

When the server advertises `save_document`, approved immune memories are stored as native Decision
Documents related to the source asset. Document search is negotiated independently because DataHub
MCP hides it until the catalog contains its first Document. If native document writes are
unavailable, LineageGuard uses its bounded description envelope. To additionally raise an
idempotently discovered native Incident, provide
`--datahub-graphql-url "$DATAHUB_GMS_URL/api/graphql"` on the approved Agent A command.

After Agent A exits, run a fresh Agent B process. Omit `--apply` for review-only evaluation:

```bash
lineage-guard --mode mcp --gms-url "$DATAHUB_GMS_URL" \
  --evaluate-change-file examples/inherited-change.json \
  --output inherited-evaluation.json
```

## Failure behavior

LineageGuard rejects missing tools, malformed JSON, incomplete entity context, invalid tag URNs, and
failed MCP mutations. Tokens are inherited by the child process and are never rendered in reports.
For shared or production environments, scope the service account to the smallest applicable DataHub
view and permissions.

## Verified compatibility

The complete workflow was verified on August 2, 2026 in a disposable 4-core, 16 GB GitHub
Codespace against DataHub GMS 1.6.0, DataHub CLI 1.6.0.17, and the pinned DataHub MCP Server 0.6.0.
The test covered fixture ingestion, six dataset relationships, four column relationships, exact
column-path confirmation, entity context reads, signed event intake, durable replay/retry, signed
default-hold enforcement, mutation gating, description write-back, and quarantine-tag write-back.
Sanitized machine-readable results are available in
[`examples/live-datahub-verification.json`](../examples/live-datahub-verification.json).

MCP Server 0.6.0 returned an empty compact column-lineage result for this DataHub 1.6 graph even
though DataHub's SDK and the MCP `get_lineage_paths_between` tool returned the four stored paths.
LineageGuard therefore uses the compact result first and, only when it is empty, checks exact
same-name source-to-target paths for at most 20 already-discovered downstream assets. A validated
path is positive dependency evidence. A missing/error path is never treated as exclusion; it yields
`require_review` unless other evidence justifies monitoring. Renamed target columns consequently
remain unconfirmed in this fallback.

DataHub's description append has no idempotency key. LineageGuard executes idempotent tag additions
before the append, so a missing-tag failure cannot partially duplicate the narrative on retry. A
transport failure after DataHub commits an append but before acknowledging it remains an upstream
at-least-once boundary; operators can reconcile the stable incident marker if that rare ambiguity
occurs.

## Read-consistency receipts

`DataHubMcpGraph.read_downstream_lineage` returns normalized targets plus a versioned receipt. The
receipt independently records source, consistency, completeness, response-cache disposition,
projection reference, safe capabilities, and limitations. It also content-addresses the query and
result for stable audit correlation. The digest is tamper-evident correlation, not authentication
or anonymization.

The pinned MCP surface does not expose a projection watermark or cache disposition, so these values
truthfully default to `UNKNOWN`. Such a read permits `USE_AS_OBSERVATION`; it never permits an
absence or current-state assertion. The legacy `get_downstream_lineage` method remains compatible
for callers that do not yet consume receipts.

The interoperable wire contract is
[`schemas/lineage-read-receipt-v1.schema.json`](../schemas/lineage-read-receipt-v1.schema.json).
