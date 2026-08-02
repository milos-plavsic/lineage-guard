# LineageGuard

[![CI](https://github.com/milos-plavsic/lineage-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/milos-plavsic/lineage-guard/actions/workflows/ci.yml)
[![Demo](https://img.shields.io/badge/demo-GitHub%20Pages-5ee0b3)](https://milos-plavsic.github.io/lineage-guard/)

LineageGuard is a deterministic safety agent for branch-specific data-incident containment. It
receives authenticated quality events, retrieves dataset and field lineage through DataHub MCP,
separates confirmed dependencies from proven exclusions and uncertain exposure, produces reviewable
controls, and records approved decisions back into DataHub. An optional signed webhook applies an
atomic hold/allow plan through an external orchestrator.

This repository is being built for **Build with DataHub: The Agent Hackathon**.

## Current vertical slice

The included healthcare scenario detects invalid negative billing values upstream of two marts.
LineageGuard quarantines the financially dependent billing branch while allowing the unaffected
demographics branch to continue. Proposed metadata mutations are dry-run by default.

```text
raw_patients → staging_patients  MONITOR
                  ├→ mart_billing      QUARANTINE (confirmed field dependency)
                  └→ mart_demographics CONTINUE   (confirmed field exclusion)
```

## Run it

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
lineage-guard --output incident-report.json
lineage-guard --artifacts-dir remediation
lineage-guard-web
lineage-guard-agent --gms-url https://datahub.example/gms
pytest
ruff check .
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

`--apply` crosses the explicit approval boundary. In MCP mode it enables approved DataHub
description/tag write-back; with `--enforcement-webhook`, it first sends an HMAC-signed,
idempotent, fail-closed plan to an orchestrator. See [operations](docs/operations.md).

For a real DataHub instance, install the `mcp` extra and follow the
[live integration guide](docs/live-datahub.md). The adapter starts the official, version-pinned
DataHub MCP Server and uses its lineage, entity, description, and tag tools.

The lightweight [operator dashboard](docs/operator-demo.md) runs at `http://127.0.0.1:8765` and
visualizes the downstream blast radius, evidence timeline, decisions, and artifact integrity hashes.
The same verified view can be exported as a static judge demo for GitHub Pages.

The [healthcare fixture workflow](docs/healthcare-fixture.md) fetches DataHub's official synthetic
scenario from a pinned commit using streamed downloads and integrity validation. It never starts
Docker or executes downloaded scripts automatically.

## Architecture

- `domain.py`: immutable incident evidence and decisions.
- `service.py`: deterministic graph traversal and selective containment policy.
- `events.py`: bounded, versioned quality-event contract.
- `agent.py`: durable observe-contextualize-decide-act workflow.
- `agent_web.py`: authenticated loopback webhook listener.
- `journal.py`: SQLite deduplication, leases, retries, and stage history.
- `enforcement.py`: signed orchestrator containment protocol.
- `ports.py`: narrow interface for DataHub context and write-back.
- `adapters/`: replaceable metadata graph implementations.
- `remediation.py`: deterministic SQL, policy, report, and integrity-manifest generation.
- `examples/`: judge-readable sample incidents and generated artifacts.

The safety-critical authority does not depend on an LLM. That is deliberate: probabilistic output
cannot authorize continuation or mutation. The agent instead executes a durable tool-using state
machine through the official DataHub MCP Server, with explicit evidence and approval invariants.

Architectural decisions are recorded under [`docs/adr`](docs/adr), including selective containment,
reviewable remediation artifacts, and the lightweight operator interface.

Operational boundaries are documented in the [security policy](SECURITY.md),
[threat model](docs/threat-model.md), and [failure-recovery guide](docs/operations.md). CI verifies
the supported minimum and current Python versions, formatting, linting, tests, and package builds.
The complete test matrix is documented in [the validation strategy](docs/testing.md).

## Safety model

- Read operations and proposed actions are separate from writes.
- All metadata mutations require explicit approval.
- Evidence and rationale accompany every branch decision.
- `continue` requires complete evidence that field lineage excludes the failed field.
- Confirmed dependency can quarantine; descriptive metadata alone can only monitor.
- Missing or incomplete evidence requires review, never an unsupported claim of safety.
- Credentials are supplied through the environment and never stored in the repository.
- Event and enforcement webhooks are independently HMAC authenticated and idempotent.

## Roadmap

1. Record the public demonstration video using the committed runbook.
2. Finalize and submit the Devpost entry.

## License

Apache License 2.0. See `LICENSE`.
