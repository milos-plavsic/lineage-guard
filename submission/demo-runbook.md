# Demo runbook

## Preflight

1. Use the committed `main` revision and a clean working tree.
2. Run `uv sync --locked --extra dev --extra mcp`.
3. Run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest`.
4. Regenerate examples with:
   `uv run lineage-guard --output examples/incident-report.json --artifacts-dir examples/generated`.
5. Confirm regenerated files produce no Git diff.
6. If demonstrating live write-back, confirm the scoped DataHub service account, existing quarantine
   tag, and disposable demonstration metadata. Never display the token.

## Deterministic dashboard path

1. Start `uv run lineage-guard-web`.
2. Open `http://127.0.0.1:8765`.
3. Establish the forked healthcare lineage and negative billing signal.
4. Show billing at risk 100 with `quarantine`.
5. Show demographics with `continue`.
6. Walk through the five-stage evidence timeline.
7. Show the artifact filenames and hashes.
8. Open the committed SQL assertion and branch policy in the repository.

## Live DataHub path

1. Use a remotely hosted DataHub instance; do not start Quickstart on the constrained workstation.
2. Follow `docs/healthcare-fixture.md` to ingest and enrich the fixture.
3. Run the MCP command from `docs/live-datahub.md` without `--apply` first.
4. Compare live entity URNs and decisions with the deterministic output.
5. Enable `--apply` only on disposable demonstration metadata and show the resulting description and
   quarantine tag.

## Recovery

If live infrastructure fails, continue with the deterministic dashboard and committed artifacts.
Do not troubleshoot credentials on camera. Preserve the video narrative: problem, DataHub context,
selective decision, artifacts, safety, proof.
