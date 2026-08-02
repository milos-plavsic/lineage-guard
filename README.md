# LineageGuard

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
pytest
ruff check .
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

`--apply` demonstrates the explicit approval boundary against the in-memory adapter. It does not
contact a real DataHub instance in this milestone.

## Architecture

- `domain.py`: immutable incident evidence and decisions.
- `service.py`: deterministic graph traversal and selective containment policy.
- `ports.py`: narrow interface for DataHub context and write-back.
- `adapters/`: replaceable metadata graph implementations.
- `examples/`: judge-readable sample incidents and generated artifacts.

The domain does not depend on an LLM or DataHub transport. The production adapter will use the
official DataHub MCP Server for search, lineage, entity metadata, and approved mutation tools.

See [ADR 0001](docs/adr/0001-safe-selective-containment.md) for the safety rationale.

## Safety model

- Read operations and proposed actions are separate from writes.
- All metadata mutations require explicit approval.
- Evidence and rationale accompany every branch decision.
- Missing context must degrade to monitoring, never an unsupported claim of safety.
- Credentials are supplied through the environment and never stored in the repository.

## Roadmap

1. Connect the official DataHub MCP Server.
2. Ingest the provided healthcare dataset and assertions.
3. Generate dbt/SQL remediation artifacts and validation evidence.
4. Add an operator-facing web demonstration and incident timeline.
5. Package the public demo, three-minute video, and Devpost submission.

## License

Apache License 2.0. See `LICENSE`.

