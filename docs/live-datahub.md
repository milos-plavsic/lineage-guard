# Live DataHub MCP integration

LineageGuard uses the official `mcp-server-datahub` package over MCP stdio. Version `0.6.0` is
pinned by default so a new upstream release cannot silently change a judged build.

## Prerequisites

- DataHub Core or Cloud with a reachable GMS endpoint.
- A least-privilege service account token.
- `uvx` on `PATH`.
- The `LineageGuard_Quarantined` tag created in DataHub before applying write-back.

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
  --source-urn 'urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.raw_patients,PROD)' \
  --field billing_amount \
  --concern billing \
  --concern financial \
  --output incident-report.json
```

The absence of `--apply` keeps mutation tools disabled at the MCP-server boundary. Adding `--apply`
both enables those server tools and authorizes LineageGuard to invoke them. This double gate is
intentional.

## Failure behavior

LineageGuard rejects missing tools, malformed JSON, incomplete entity context, invalid tag URNs, and
failed MCP mutations. Tokens are inherited by the child process and are never rendered in reports.
For shared or production environments, scope the service account to the smallest applicable DataHub
view and permissions.
