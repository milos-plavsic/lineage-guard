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

## Residual risks

Column lineage can itself be absent or incorrect; its completeness assertion is therefore a trusted
metadata premise that must be governed and monitored. Cross-system transactions cannot be atomic:
LineageGuard applies the fail-safe orchestrator hold first, then records DataHub context. An ambiguous
network failure can still require reconciliation. SQLite is suitable for a single-node agent; a
multi-node deployment needs a transactional shared journal. The built-in HTTP server must remain on
loopback behind a production TLS proxy with rate limiting and network policy.
