# Healthcare fixture workflow

LineageGuard uses DataHub's official synthetic healthcare fixture. Acquisition is pinned to upstream
commit `a6479c691dd2a40dd89563396d9c8b2b28bee83c`; every file is streamed to disk and checked against
its Git object digest and expected size before becoming visible at its destination.

Preview the scripts and metadata without downloading the 31 MB SQLite database:

```bash
uv run python scripts/fetch_healthcare.py --metadata-only
```

Fetch the complete fixture when a DataHub endpoint is available:

```bash
uv run python scripts/fetch_healthcare.py
cd .fixtures/healthcare
datahub ingest -c ingest.yaml
python add_lineage.py
python add_metadata.py
```

The files land under `.fixtures/`, which is excluded from version control. The acquisition manifest
records the exact source, commit, license, sizes, and verified hashes. Review upstream scripts before
execution; the fetch command downloads them but never executes them.

The pinned database was verified locally using read-only SQLite access. It contains 55,500 rows in
each of the raw, staging, billing, and demographics tables, plus the expected three lineage views.
The observed planted defects are recorded in
[`examples/healthcare-fixture-verification.json`](../examples/healthcare-fixture-verification.json).

Running the ingestion commands requires a configured DataHub CLI and reachable DataHub instance. It
does not require DataHub to be hosted on the same machine. Do not launch the local Docker Quickstart
on a memory-constrained host.
