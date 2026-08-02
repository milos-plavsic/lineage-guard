# Operations and failure recovery

## Health and logs

Both HTTP processes expose `GET /healthz`. The dashboard and agent listener emit one-line JSON
access/failure events. Capture standard output and alert on `processing_failed`, `request_failed`,
repeated 5xx responses, expired event leases, or process restarts.

## Authenticated event agent

Run the listener on loopback behind a TLS reverse proxy. Never expose the built-in plaintext server
directly to a network.

```bash
export DATAHUB_GMS_TOKEN='scoped-service-token'
export LINEAGE_GUARD_WEBHOOK_SECRET='at-least-32-random-bytes'
lineage-guard-agent \
  --gms-url https://datahub.example/gms \
  --journal /var/lib/lineage-guard/events.sqlite3 \
  --artifacts-dir /var/lib/lineage-guard/artifacts
```

Send `POST /v1/quality-events` with `Content-Type: application/json` and
`X-LineageGuard-Signature: sha256=<HMAC-SHA256(raw-body)>`. The versioned event schema is shown in
`examples/quality-event.json`. Duplicate completed events return the durable original result;
concurrent delivery returns `409` with `Retry-After`; reuse of an event ID with a different payload
is rejected.

Approved enforcement additionally requires `--apply`, `--enforcement-webhook`, and a separate
`LINEAGE_GUARD_ENFORCEMENT_SECRET`. The orchestrator must atomically acknowledge the exact incident
and honor the idempotency key. Its default directive is `hold`; only proven field exclusions receive
`allow`. Enforcement occurs before DataHub write-back so a catalog outage cannot create an unsafe
continuation window.

## Failure modes

- **MCP process cannot start:** verify `uvx`, the pinned package, GMS reachability, and token scope.
- **Required tools missing:** confirm the DataHub MCP version and keep analysis stopped.
- **Incomplete entity context:** fix ingestion or permissions; do not infer missing ownership or
  lineage.
- **Mutation tools missing:** rerun read-only or deliberately enable them after approval.
- **Failed mutation:** confirmed operations are removed from the in-process queue; the failed and
  remaining operations stay retryable. After an ambiguous transport failure, reconcile DataHub
  before a new process retries an append operation.
- **Agent crash:** retry after the five-minute lease. The SQLite journal preserves attempts and stage
  history and recovers stale `processing` events.
- **Event conflict:** assign globally unique event IDs; never reuse an ID for changed evidence.
- **Enforcement failure:** no DataHub write is attempted. Correct the orchestrator and redeliver the
  same event.
- **Artifact integrity mismatch:** regenerate from the committed incident input; do not merge altered
  output without review.
- **Dashboard HTTP 500:** inspect the `request_failed` event; the client receives no internal details.
- **No recovery certificate:** at least one invariant failed. Inspect `recovery/evaluations.json`;
  never reinterpret a rejected candidate as releasable.
- **Certificate mismatch:** discard the bundle and regenerate from the exact incident, current rows,
  trusted snapshot, and tolerance. A hash mismatch is not repairable by editing the certificate.

## Counterfactual recovery lab

```bash
lineage-guard --recovery-lab --artifacts-dir recovery-evidence --output recovery-report.json
```

This command uses the committed deterministic healthcare scenario and application-owned SQL. It does
not read production rows, alter source data, or release quarantined branches. The trusted snapshot is
part of the proof context. In production, retrieve it through a governed point-in-time store, enforce
dataset-specific invariants, authenticate the certificate issuer, and route the proposed transition
through the same approval and signed enforcement boundary used for containment.

## Chronos temporal immunity

```bash
lineage-guard --chronos --artifacts-dir prevention-pack --output immunity-report.json
```

Review `immunity/evaluations.json` before the passport. `blocked` means the historical failure escaped
the proposed guard. `revalidation_required` means the DataHub context fingerprint changed, even if
the guard itself still passes. Only `eligible_for_approval` produces a passport, and that passport is
an unsigned in-toto Statement until a deployment signer wraps it in an authenticated envelope.

The deterministic demonstration never reads a Git repository or runs change-supplied code. A future
PR integration must use an isolated, resource-limited runner, immutable checkout, least-privilege
token, reviewed parser, and authenticated attestation service.

## Backup and rollback

LineageGuard does not own source data. DataHub write-back is append-only incident context plus a
quarantine tag. Rollback requires an approved inverse orchestrator plan, tag removal, and description
review through normal governance. Back up the SQLite journal and artifacts together; preserve the
incident report, manifest, transition history, and orchestrator receipt as the audit record.
