## Independent MCP corroboration and agent-safety impact

On 2026-08-02, I independently observed the same empty-read failure family on DataHub GMS 1.6.0, DataHub CLI
1.6.0.17, and `mcp-server-datahub` 0.6.0 while building a lineage-aware incident agent.

The MCP compact downstream column-lineage query returned empty for `billing_amount`, while:

- the stored fixture contained four same-name column relationships;
- DataHub's SDK confirmed those relationships; and
- MCP `get_lineage_paths_between` returned all four exact source-to-target paths.

Sanitized versioned evidence and counts are here:
<https://github.com/milos-plavsic/lineage-guard/blob/main/examples/live-datahub-verification.json>

This matters especially for agents: an empty compact result is indistinguishable from absent lineage
unless the client knows that freshness/completeness is unproven. Treating it as negative evidence can
authorize unsafe continuation.

Our bounded mitigation is:

1. Query compact lineage first.
2. Only when empty, query exact same-name paths for at most 20 already discovered downstream assets.
3. Treat a confirmed path as positive dependency evidence.
4. Treat a missing/error path as unknown—never as proven exclusion.

The implementation and contract tests are in
[`DataHubMcpGraph.load`](https://github.com/milos-plavsic/lineage-guard/blob/main/src/lineage_guard/adapters/mcp.py).

The `skipCache` GraphQL workaround described here, and the MCP limitation documented in #18636,
suggest two complementary fixes:

- avoid or sharply limit caching of empty `searchAcrossLineage` results; and
- expose a freshness bypass or explicit `complete/fresh` response state through MCP lineage tools.

I can contribute a focused MCP regression test or documentation patch once maintainers indicate the
preferred contract. I am deliberately not opening a duplicate issue because this evidence appears to
corroborate #18623.
