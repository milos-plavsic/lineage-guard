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

## Backup and rollback

LineageGuard does not own source data. DataHub write-back is append-only incident context plus a
quarantine tag. Rollback requires an approved inverse orchestrator plan, tag removal, and description
review through normal governance. Back up the SQLite journal and artifacts together; preserve the
incident report, manifest, transition history, and orchestrator receipt as the audit record.
