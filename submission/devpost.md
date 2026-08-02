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

LineageGuard receives a data-quality signal, retrieves downstream lineage and entity context through
DataHub's official MCP Server, and evaluates each branch against the failing business concern. It
produces a deterministic risk score, explains every decision, quarantines only materially affected
branches, and lets unrelated branches continue.

For the healthcare demonstration, negative billing values enter `raw_patients`. Both billing and
demographics marts share the upstream pipeline, but only the financial branch depends on the failing
concern. LineageGuard proposes quarantine for `mart_billing` while allowing
`mart_demographics` to continue.

It then generates a PR-ready SQL assertion, machine-readable branch policy, operator report, and
SHA-256 manifest. Approved decisions can be written back to DataHub as incident context and a
quarantine tag, leaving knowledge for the next person or agent. Write-back is dry-run by default and
requires two explicit approval gates.

## How we built it

The Python domain core is deterministic and transport-independent. A DataHub MCP adapter calls
`get_lineage` and batched `get_entities`, normalizes graph context, and uses `update_description` and
`add_tags` only after approval. The operator dashboard and CLI share the same analysis and artifact
generation code.

The demonstration uses DataHub's official synthetic healthcare fixture pinned to an immutable
upstream commit. Acquisition streams files to disk and verifies their sizes and Git object hashes.
The repository includes an accessible, responsive incident console, structured health and request
events, automated tests, threat modeling, architecture decisions, and reproducible sample output.

## Challenges we ran into

Lineage means exposure, not necessarily impact. Treating every connected asset as broken would simply
automate blanket shutdowns. We separated graph reachability from semantic concern matching and made
each branch decision evidence-bearing. We also designed around incomplete metadata: missing context
stops analysis rather than becoming a false claim of safety.

MCP mutation calls can change shared catalog state, so read and write capabilities are deliberately
separated. LineageGuard must approve a mutation and the MCP server must independently expose mutation
tools. Generated source-system remediation remains reviewable output rather than an automatic write.

## Accomplishments that we're proud of

- Branch-specific containment that preserves availability for unaffected data products.
- Meaningful two-way DataHub integration instead of catalog search alone.
- Reproducible, executable remediation artifacts with integrity hashes.
- Fail-closed handling for malformed, incomplete, or oversized MCP context.
- A judge-readable demo that runs without credentials while retaining the real MCP boundary.
- A lightweight architecture suitable for memory-constrained development environments.

## What we learned

Metadata becomes operationally valuable when an agent can connect technical lineage to business
meaning and then preserve its decision as new context. The graph answers where a problem can travel;
governance metadata helps answer where it matters. Reliable agents also need visible uncertainty and
permission boundaries more than unconstrained autonomy.

## What's next

Next steps include native DataHub incident entities, policy adapters for Airflow, Dagster, and dbt,
column-level concern propagation, owner approval workflows, event-driven assertion ingestion, and
evaluation against larger cross-platform graphs.

## Built with

Python, DataHub Core, DataHub MCP Server, Model Context Protocol, SQLite, HTML, CSS, JavaScript, uv,
pytest, and Ruff.

## Challenge category

Agents That Do Real Work.

## DataHub technologies

DataHub OSS / Core Platform and DataHub MCP Server.
