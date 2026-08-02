# LineageGuard

[![CI](https://github.com/milos-plavsic/lineage-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/milos-plavsic/lineage-guard/actions/workflows/ci.yml)
[![Demo](https://img.shields.io/badge/demo-GitHub%20Pages-5ee0b3)](https://milos-plavsic.github.io/lineage-guard/)

LineageGuard turns DataHub lineage and governance context into safe, branch-specific incident
containment. It finds the downstream blast radius of a quality failure, distinguishes materially
affected branches from merely connected ones, proposes actions, and records approved decisions back
into DataHub.

This repository is being built for **Build with DataHub: The Agent Hackathon**.

## Current vertical slice

The included healthcare scenario detects invalid negative billing values upstream of two marts.
LineageGuard quarantines the financially dependent billing branch while allowing the unaffected
demographics branch to continue. Proposed metadata mutations are dry-run by default.

```text
raw_patients → staging_patients ┬→ mart_billing      QUARANTINE
                                └→ mart_demographics CONTINUE
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
pytest
ruff check .
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

`--apply` demonstrates the explicit approval boundary against the in-memory adapter.

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
- `ports.py`: narrow interface for DataHub context and write-back.
- `adapters/`: replaceable metadata graph implementations.
- `remediation.py`: deterministic SQL, policy, report, and integrity-manifest generation.
- `examples/`: judge-readable sample incidents and generated artifacts.

The domain does not depend on an LLM or DataHub transport. The production adapter uses the
official DataHub MCP Server for search, lineage, entity metadata, and approved mutation tools.

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
- Missing context must degrade to monitoring, never an unsupported claim of safety.
- Credentials are supplied through the environment and never stored in the repository.

## Roadmap

1. Record the public demonstration video using the committed runbook.
2. Finalize and submit the Devpost entry.

## License

Apache License 2.0. See `LICENSE`.
