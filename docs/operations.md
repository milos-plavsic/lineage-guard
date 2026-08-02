# Operations and failure recovery

## Health and logs

`GET /healthz` reports process health. The dashboard emits one-line JSON events for startup, HTTP
requests, and request failures. In a hosted environment, capture standard output and alert on
`request_failed`, repeated HTTP 500 responses, or process restarts.

## Failure modes

- **MCP process cannot start:** verify `uvx`, the pinned package, GMS reachability, and token scope.
- **Required tools missing:** confirm the DataHub MCP version and keep analysis stopped.
- **Incomplete entity context:** fix ingestion or permissions; do not infer missing ownership or
  lineage.
- **Mutation tools missing:** rerun read-only or deliberately enable them after approval.
- **Partial mutation:** inspect the source description and quarantine tag in DataHub before retrying.
- **Artifact integrity mismatch:** regenerate from the committed incident input; do not merge altered
  output without review.
- **Dashboard HTTP 500:** inspect the `request_failed` event; the client receives no internal details.

## Backup and rollback

LineageGuard does not own source data. Its current DataHub write-back is append-only incident context
plus a quarantine tag. Rollback consists of removing the tag and reviewing the appended description
through DataHub's normal governance process. Preserve the incident report and artifact manifest as
the audit record.
