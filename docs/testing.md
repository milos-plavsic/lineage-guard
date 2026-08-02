# Validation strategy

LineageGuard uses layered tests so deterministic logic, transport boundaries, packaged software, and
the public judge experience are validated independently. CI is intentionally bounded to ten minutes
and does not start containers, browsers, or a local DataHub stack.

## Automated CI gate

The Linux workflow runs on Python 3.11 and 3.14 and requires:

- Ruff lint and formatting checks;
- unit, integration, HTTP, integrity, and failure-path tests;
- at least 85% branch-aware coverage across `lineage_guard` and `scripts`;
- successful source and wheel builds; and
- installation and CLI execution from the built wheel in an isolated environment.

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

Tests use a contract-faithful fake MCP session to exercise DataHub reads, normalization, response
bounds, missing tools, malformed/incomplete data, mutation gating, mutation contracts, and mutation
failure. A genuine end-to-end run additionally requires a reachable DataHub GMS endpoint and a
short-lived, least-privilege token. Follow `docs/live-datahub.md` when those are available.

Do not substitute a local DataHub Quickstart on this memory-constrained workstation. Deferring that
single external test preserves host reliability and does not weaken the deterministic or protocol
boundary tests.

For disposable remote validation, `.devcontainer/devcontainer.json` requests four CPUs, at least
12 GB RAM, Docker-in-Docker, and SSH access. Use a short Codespaces idle timeout and retention period,
store DataHub credentials only as Codespaces secrets or ephemeral environment variables, and delete
the Codespace after exporting sanitized test evidence.
