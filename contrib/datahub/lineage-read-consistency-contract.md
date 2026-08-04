# Lineage read consistency contract

Status: proposal for maintainer discussion  
Date: 2026-08-04  
Related: [datahub-project/datahub#18623](https://github.com/datahub-project/datahub/issues/18623),
[datahub-project/datahub#18636](https://github.com/datahub-project/datahub/issues/18636), and
[datahub-project/datahub#18809](https://github.com/datahub-project/datahub/issues/18809)

## Decision

A lineage response is an observation from a particular read path, not proof of the current graph.
DataHub should expose structured consistency metadata and document which layer each control affects.
Until a backend can prove a stronger property, the metadata must say `UNKNOWN`; clients must not
infer freshness or completeness from an empty result, a non-empty result, or `skipCache: true`.

This proposal deliberately avoids a universal `fresh` boolean. Freshness is relative to a write or
watermark, completeness is relative to a requested traversal, and cache bypass is a separate fact.

## The three independent layers

1. **Response cache** — Apollo and DataHub's lineage-search cache can replay an older response.
   `skipCache` bypasses this layer.
2. **Projection** — `searchAcrossLineage` reads a search index that may not yet reflect graph
   writes or removals. Cache bypass does not make this projection current.
3. **Authority** — graph-store reads can provide read-your-writes behavior for an acknowledged
   graph write, but still require authorization parity and a precisely defined traversal.

The current UI hook describes `skipCache` as bypassing Apollo and Elasticsearch caches and sends
it as part of `SearchAcrossLineageInput`: [`useSearchAcrossLineage.ts`](https://github.com/datahub-project/datahub/blob/master/datahub-web-react/src/app/lineageV3/queries/useSearchAcrossLineage.ts).
The server's response cache is independently controlled by `LINEAGE_SEARCH_CACHE_ENABLED`:
[`environment-vars.md`](https://github.com/datahub-project/datahub/blob/master/docs/deploy/environment-vars.md#lineage-search-cache-enabled).

## Additive response metadata

The same vocabulary should be used by GraphQL and agent/MCP surfaces. Names can follow each API's
style, but semantics must not drift.

```json
{
  "readConsistency": {
    "source": "SEARCH_INDEX",
    "consistency": "EVENTUAL",
    "completeness": "UNKNOWN",
    "responseCache": "BYPASSED",
    "asOf": null,
    "watermark": null
  }
}
```

Closed enums:

- `source`: `SEARCH_INDEX`, `GRAPH_STORE`, `UNKNOWN`
- `consistency`: `EVENTUAL`, `READ_YOUR_WRITES`, `UNKNOWN`
- `completeness`: `COMPLETE`, `INCOMPLETE`, `UNKNOWN`
- `responseCache`: `HIT`, `MISS`, `BYPASSED`, `NOT_APPLICABLE`, `UNKNOWN`

Normative rules:

- `asOf` is the source projection's time, not the request or response time. It is `null` if the
  backend cannot establish it.
- `watermark` is an opaque, source-specific convergence token. Clients may compare it only when
  the server explicitly documents ordering for that token type.
- `COMPLETE` means the requested traversal is fully represented at the stated `asOf` or
  `watermark`. A capped, timed-out, partially paginated, or unbounded traversal cannot claim it.
- `READ_YOUR_WRITES` is valid only relative to an acknowledged write/session contract. Merely
  selecting the graph store is insufficient.
- `BYPASSED` describes only the response-cache layer. It does not imply `COMPLETE` or current.
- Older servers and adapters default every unverifiable property to `UNKNOWN`/`null`.
- Authorization is evaluated before results and metadata are returned. A fallback must never
  widen visibility or disclose hidden-edge counts through metadata.

## Consumer behavior

| Observation | Safe interpretation | Decision-critical action |
| --- | --- | --- |
| Empty + `UNKNOWN` completeness | No visible matches were observed | Retry after a bound, verify against an authoritative path, or abstain |
| Non-empty + eventual projection | These matches existed in a projection | Verify if stale removals would make the decision unsafe |
| `BYPASSED` cache | No cached response was intentionally used | Do not infer projection freshness |
| `COMPLETE` at a suitable watermark | Complete for the declared traversal and point | Evaluate against the caller's required write/watermark |
| Partial pagination or traversal cap | Known incomplete observation | Continue within bounds or abstain |

## Alternatives considered

| Option | Correctness | Compatibility/cost | Decision |
| --- | --- | --- | --- |
| Documentation only | Prevents some misuse but is not machine-enforceable | Lowest cost, immediate | Do now, but insufficient alone |
| MCP-only envelope | Gives agents honest semantics | Additive; cannot manufacture index state | Useful first client surface |
| Backend/GraphQL metadata | One authoritative contract for all clients | Requires projection watermark plumbing | Recommended target |
| Automatic graph-store fallback | Can corroborate critical reads | Potentially expensive; traversal and auth semantics can differ | Opt-in and bounded only |
| Always use graph store | Stronger visibility after writes | Loses search ranking/filter behavior and may not scale equivalently | Reject as universal default |

## Staged implementation

1. Document the consistency matrix and clarify that `skipCache` changes only response caching.
2. Add the optional envelope to agent/MCP results. Report only observable facts and use `UNKNOWN`
   for projection freshness and completeness.
3. Add equivalent optional GraphQL metadata backed by a real index watermark or source event
   version. Preserve existing fields and behavior.
4. Offer bounded graph-store corroboration for negative or decision-critical reads. Require an
   explicit hop/result/time budget, authorization parity, and an outcome of `INCOMPLETE` rather
   than silent truncation.

## Executable acceptance contract

The integration fixture records an acknowledged write token `W`, polls with a finite deadline, and
captures the returned consistency envelope on every read. Assertions use server-observed tokens or
watermarks, never workstation wall-clock ordering.

```gherkin
Feature: Lineage read consistency is truthful

  Scenario: newly added edge
    Given lineage edge E is acknowledged with token W
    When E is read immediately from the graph-store surface in W's session
    Then E is present and consistency is READ_YOUR_WRITES
    When the search surface is read before its watermark covers W
    Then it does not report COMPLETE at or after W unless E is present
    And it eventually returns E with a watermark covering W

  Scenario: removed edge
    Given removal of E is acknowledged with token W
    Then a read-your-writes graph-store read does not return E
    And a search response that still returns E does not report COMPLETE at or after W
    And the search surface eventually omits E with a watermark covering W

  Scenario: response-cache bypass is not projection freshness
    Given a cacheable search read returned empty before the projection covered W
    And the projection later covers W
    When the same read is made with skipCache true
    Then responseCache is BYPASSED
    And freshness and completeness are derived independently from the projection watermark

  Scenario: bounded traversal
    Given more matching edges exist than one result page or configured traversal bound
    When only part of the traversal is returned
    Then completeness is INCOMPLETE
    And the response exposes a continuation or a machine-readable limiting reason

  Scenario: authorization parity
    Given a caller cannot view edge H
    When graph-store corroboration is enabled
    Then H is absent from results
    And metadata does not reveal whether H exists

  Scenario: unknown remains unknown
    Given the backend exposes no projection watermark
    When the search surface responds
    Then asOf and watermark are null
    And completeness is UNKNOWN
    And no request-time timestamp is presented as projection freshness
```

Additional invariant/property tests should generate page boundaries, traversal caps, write/remove
sequences, and cache hit/miss/bypass combinations. For every generated response:

```text
completeness == COMPLETE => traversal exhausted AND no limiting reason
responseCache == BYPASSED !=> completeness == COMPLETE
asOf != null => asOf was supplied by the data source
watermark covers W AND completeness == COMPLETE => projection agrees with authorized source at W
```

## Compatibility and observability

The change is additive. Existing clients ignore the envelope; new clients treat a missing envelope
as unknown. Metrics should count responses by source, consistency, completeness, cache disposition,
and limiting reason, without entity URNs or other high-cardinality identifiers. Traces may carry a
hashed correlation identifier but must not expose authorization-sensitive lineage.

Success is measurable: no surface asserts current absence or presence without a declared point of
reference, cache bypass is never presented as index freshness, bounded reads advertise truncation,
and add/remove convergence tests pass without fixed sleeps.
