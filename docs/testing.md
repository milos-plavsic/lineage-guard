# Validation strategy

LineageGuard uses layered tests so deterministic logic, transport boundaries, packaged software, and
the public judge experience are validated independently. CI is intentionally bounded to ten minutes
and does not start containers, browsers, or a local DataHub stack.

## Automated CI gate

The Linux workflow runs on Python 3.11 and 3.14 and requires:

- Ruff lint and formatting checks;
- unit, integration, authenticated HTTP, durable-journal, enforcement-contract, integrity, and
  failure-path tests;
- 100% line and branch coverage across `lineage_guard` and `scripts`, with no omitted files,
  coverage exclusions, or suppression pragmas;
- successful source and wheel builds; and
- installation and CLI execution from the built wheel in an isolated environment;
- a zero-error Pa11y 4.1.1 browser audit against the exported demo at WCAG 2 AA.

Run the same gate locally:

```bash
uv sync --locked --extra dev --extra mcp
uv run ruff check .
uv run ruff format --check .
uv run pytest --cov --cov-report=term-missing
uv build
```

## Fixture and deployment checks

The pinned healthcare fixture is verified by expected byte size and Git blob digest during
acquisition. Read-only SQLite checks confirm database integrity, 55,500 records in each of four
entities, and the four planted issue counts recorded in
`examples/healthcare-fixture-verification.json`.

The GitHub Pages deployment exposes the dashboard assets, incident payload, and manifest over
HTTPS. Each deployed asset can be hashed and compared with `manifest.json`; judges do not need
credentials or local software.

## External integration boundary

Tests use a contract-faithful fake MCP session to exercise dataset and field lineage, normalization,
response bounds and truncation, missing tools, malformed/incomplete data, mutation gating, retryable
mutation contracts, and failures. Real HTTP tests verify inbound HMAC authentication, event conflicts,
busy retries, response sanitization, outbound signed default-hold enforcement, idempotency keys, and
exact acknowledgements. SQLite tests cover concurrent leases, duplicates, failures, stale recovery,
payload conflicts, bounds, and transition history. A genuine end-to-end run additionally requires a
reachable DataHub GMS endpoint and a short-lived, least-privilege token.

Do not substitute a local DataHub Quickstart on this memory-constrained workstation. Deferring that
single external test preserves host reliability and does not weaken the deterministic or protocol
boundary tests.

For disposable remote validation, `.devcontainer/devcontainer.json` requests four CPUs, at least
12 GB RAM, Docker-in-Docker, and SSH access. Use a short Codespaces idle timeout and retention period,
store DataHub credentials only as Codespaces secrets or ephemeral environment variables, and delete
the Codespace after exporting sanitized test evidence.
