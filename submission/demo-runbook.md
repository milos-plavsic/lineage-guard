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
7. If demonstrating the agent trigger, prepare the committed `examples/quality-event.json`; never
   display either HMAC secret.

## Deterministic dashboard path

1. Start `uv run lineage-guard-web`.
2. Open `http://127.0.0.1:8765`.
3. Establish the forked healthcare lineage and negative billing signal.
4. Show staging at `monitor`: dependency is confirmed, but material branch impact needs review.
5. Show billing at risk 100 with `quarantine` and confirmed field dependency.
6. Show demographics with `continue` and confirmed field exclusion—not a missing keyword.
7. Show the recovery twin: clamp-to-zero passes the target check but fails total conservation.
8. Show trusted restoration passing all six invariants and receiving a recovery certificate.
9. Walk through the seven-stage evidence timeline.
10. Show the artifact filenames and hashes.
11. Open the committed candidate SQL, evaluations, certificate, and branch policy.

## Authenticated agent path

1. Start the loopback listener with a disposable journal and read-only DataHub credentials.
2. HMAC-sign and POST `examples/quality-event.json` to `/v1/quality-events`.
3. Show the structured `proposed` result, generated artifacts, and journal stage history.
4. Deliver the same event again and show `duplicate: true` without repeated DataHub work.
5. Explain that approved mode independently requires mutation capability and, when configured, an
   exact signed orchestrator receipt before DataHub write-back.

## Live DataHub path

1. Use a remotely hosted DataHub instance; do not start Quickstart on the constrained workstation.
2. Follow `docs/healthcare-fixture.md` to ingest and enrich the fixture.
3. Run the MCP command from `docs/live-datahub.md` without `--apply` first.
4. Contrast the evidence honestly: the deterministic fixture proves demographic exclusion and may
   continue it; the live graph confirms four billing dependencies but holds two unproven
   demographic branches for review.
5. Enable `--apply` only on disposable demonstration metadata and show the resulting description and
   quarantine tag.

## Recovery

If live infrastructure fails, continue with the deterministic dashboard and committed artifacts.
Do not troubleshoot credentials on camera. Preserve the video narrative: problem, DataHub context,
selective decision, artifacts, safety, proof.
