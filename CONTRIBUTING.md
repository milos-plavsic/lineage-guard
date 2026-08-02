# Contributing

Use Python 3.11 or newer and `uv`.

```bash
uv sync --extra dev --extra mcp
uv run ruff format .
uv run ruff check .
uv run pytest
```

Keep the domain deterministic, preserve dry-run defaults, add tests for every failure mode, and
record consequential architectural changes under `docs/adr/`. Never commit credentials, private
metadata, downloaded fixtures, or generated environment files. Contributions are accepted under the
Apache License 2.0.
