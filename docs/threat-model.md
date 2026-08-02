# Threat model

## Assets

DataHub credentials, catalog metadata, incident evidence, generated artifacts, operator decisions,
and the integrity of DataHub write-back.

## Adversaries and failure sources

- malicious or malformed metadata attempting SQL or path injection;
- compromised or incompatible MCP servers returning oversized or incomplete responses;
- accidental mutation without informed operator approval;
- credential disclosure through command lines, logs, exceptions, or committed files;
- browser attacks against a publicly exposed demo;
- upstream fixture substitution;
- ambiguous lineage causing an unsafe claim that a branch is unaffected.
- forged, replayed, conflicting, or oversized quality events;
- leaked subprocess environment variables or enforcement credentials;
- partial action across the orchestrator and DataHub.
- a repair that passes the target assertion while damaging rows, unrelated fields, or business totals;
- arbitrary SQL escaping the counterfactual evaluation boundary;
- a recovery certificate reused with different incident context or output.
- stale prevention proof reused after schema, lineage, or governance drift;
- a historical fixture detached from the Incident Genome that learned from it;
- an unsigned passport mistaken for authenticated deployment authorization.

## Controls

| Threat | Control | Evidence |
|---|---|---|
| SQL identifier injection | Conservative identifier allowlist | `test_rejects_untrusted_sql_identifier` |
| Artifact path escape | Resolved-path containment check | Remediation generator |
| Oversized or truncated MCP response | 2 MB ceiling; explicit total/cap checks stop analysis | MCP adapter tests |
| Missing metadata | Incomplete snapshots raise and stop analysis | MCP adapter contract |
| Unauthorized write | Dry-run default and double approval gate | Write-back tests |
| Credential leakage | Environment-only tokens; explicit child-process environment allowlist | MCP adapter tests |
| Fixture substitution | Pinned commit, size, and Git-blob verification | Acquisition tests and manifest |
| Browser injection | DOM text nodes and restrictive CSP | Packaged JavaScript and HTTP smoke test |
| Network exposure | Loopback default; reverse-proxy requirement | Operator guide |
| Unsafe continuation | Only complete field-lineage exclusion permits `continue` | Analyzer tests |
| Weak semantic evidence | Metadata indication can monitor but cannot authorize continuation | Analyzer tests |
| Forged/replayed event | HMAC authentication, payload digest, durable ID deduplication | Agent HTTP/journal tests |
| Event ID collision | Same ID with changed payload is a hard conflict | Journal tests |
| Concurrent/crashed worker | Immediate transaction, processing lease, stale recovery | Journal tests |
| Unsafe orchestrator action | Separate HMAC secret, HTTPS, default hold, exact acknowledgement | Enforcement tests |
| Partial MCP retry | Completed queue entries retained; failed entries remain retryable | MCP mutation tests |
| Superficial repair | Six independent recovery invariants; all must pass | Recovery tests and sample evaluations |
| Counterfactual SQL escape | Only application-owned queries; bounded rows; fresh in-memory SQLite database | Recovery ADR and tests |
| Certificate/context substitution | Canonical incident, input, SQL, output, and check digests | Certificate tamper test |
| Stale change proof | Exact schema/lineage/governance fingerprint; drift forces revalidation | Chronos drift test |
| Detached historical fixture | Fixture digest embedded in the Incident Genome and checked at generation | Prevention Pack tests |
| Passport overreach | Decision is only `eligible_for_approval`; unsigned status documented and tested | Chronos ADR and passport tests |

## Residual risks

Column lineage can itself be absent or incorrect; its completeness assertion is therefore a trusted
metadata premise that must be governed and monitored. Cross-system transactions cannot be atomic:
LineageGuard applies the fail-safe orchestrator hold first, then records DataHub context. An ambiguous
network failure can still require reconciliation. SQLite is suitable for a single-node agent; a
multi-node deployment needs a transactional shared journal. The built-in HTTP server must remain on
loopback behind a production TLS proxy with rate limiting and network policy.

The recovery lab's trusted snapshot is a trust anchor, not independently proven truth. A production
deployment must govern snapshot provenance, retention, access, and freshness. SHA-256 detects
alteration but does not authenticate the issuer; signed approval remains necessary before release.
