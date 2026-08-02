# LineageGuard

## Tagline

Contain the broken branch, not the whole data platform.

## Inspiration

Data incidents rarely respect team boundaries. A single malformed field can feed transformations,
dashboards, and models, yet conventional incident response often treats every downstream asset as
equally unsafe. That creates a damaging choice: leave unreliable data running or stop healthy work.
LineageGuard uses DataHub's context graph to make a third option possible—evidence-based selective
containment.

## What it does

LineageGuard receives an HMAC-authenticated, versioned data-quality event, durably deduplicates it,
and retrieves dataset plus field lineage and entity context through DataHub's official MCP Server.
It distinguishes confirmed dependency, complete field exclusion, descriptive indication, and
insufficient evidence. It produces a deterministic risk score and explanation, proposes quarantine
for confirmed material impact, permits continuation only for a proven exclusion, and routes every
uncertain branch to review.

For the healthcare demonstration, negative billing values enter `raw_patients`. Both billing and
demographics marts share the upstream pipeline, but only the financial branch depends on the failing
concern. LineageGuard proposes quarantine for `mart_billing` while allowing
`mart_demographics` to continue.

It then generates a PR-ready SQL assertion, machine-readable branch policy, operator report, and
SHA-256 manifest. With explicit approval, it first sends an HMAC-signed, idempotent default-hold plan
to an orchestrator endpoint and requires an exact receipt. It then writes incident context and a
quarantine tag to DataHub, leaving durable knowledge for the next person or agent. Dry-run is the
default; mutation capability, approval, and enforcement credentials are independent gates.

## How we built it

The Python domain core is deterministic and transport-independent. A durable agent state machine
authenticates events, manages SQLite leases/retries/conflicts, calls dataset and schema-field
`get_lineage` plus batched `get_entities`, records each stage, and uses `update_description` and
`add_tags` only after approval. The listener, CLI, operator dashboard, and generated artifacts share
the same decision model.

The demonstration uses DataHub's official synthetic healthcare fixture pinned to an immutable
upstream commit. Acquisition streams files to disk and verifies their sizes and Git object hashes.
The repository includes an accessible, responsive incident console, structured health and request
events, automated tests, threat modeling, architecture decisions, and reproducible sample output.

## Challenges we ran into

Lineage means exposure, not necessarily impact. Treating every connected asset as broken would simply
automate blanket shutdowns. We separated dataset reachability, column dependency, business metadata,
and evidence completeness. A keyword can raise concern but cannot prove independence. Only complete
field exclusion can authorize continuation; absent evidence produces review.

MCP mutation calls can change shared catalog state, so read and write capabilities are deliberately
separated. LineageGuard must approve a mutation and the MCP server must independently expose mutation
tools. Generated source-system remediation remains reviewable output rather than an automatic write.

## Accomplishments that we're proud of

- Field-aware containment that preserves availability only when independence is positively proven.
- Meaningful two-way DataHub integration instead of catalog search alone.
- Authenticated event ingestion with durable deduplication, crash leases, retries, and stage history.
- A real signed orchestrator action protocol with default-hold semantics and exact receipts.
- Reproducible, executable remediation artifacts with integrity hashes.
- Fail-closed handling for malformed, incomplete, or oversized MCP context.
- A judge-readable demo that runs without credentials while retaining the real MCP boundary.
- A lightweight architecture suitable for memory-constrained development environments.

## What we learned

Metadata becomes operationally valuable when an agent can connect technical lineage to governed
action and preserve the result as new context. Field lineage answers where a specific failure can
travel; business metadata helps prioritize the confirmed exposure. Reliable operational agents need
durable identity, visible uncertainty, abstention, idempotency, and permission boundaries more than
unconstrained generative autonomy.

## What's next

Next steps include native DataHub incident entities, packaged Airflow/Dagster/dbt receivers for the
signed enforcement protocol, owner approval integration, multi-node journal backends, and evaluation
against larger cross-platform graphs.

## Built with

Python, DataHub Core, DataHub MCP Server, Model Context Protocol, SQLite, HTML, CSS, JavaScript, uv,
pytest, and Ruff.

## Challenge category

Agents That Do Real Work.

## DataHub technologies

DataHub OSS / Core Platform and DataHub MCP Server.
