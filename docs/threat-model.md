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

## Controls

| Threat | Control | Evidence |
|---|---|---|
| SQL identifier injection | Conservative identifier allowlist | `test_rejects_untrusted_sql_identifier` |
| Artifact path escape | Resolved-path containment check | Remediation generator |
| Oversized MCP response | 2 MB payload ceiling and result-count bound | MCP adapter tests |
| Missing metadata | Incomplete snapshots raise and stop analysis | MCP adapter contract |
| Unauthorized write | Dry-run default and double approval gate | Write-back tests |
| Credential leakage | Environment-only token and ignored `.env` | CLI and repository configuration |
| Fixture substitution | Pinned commit, size, and Git-blob verification | Acquisition tests and manifest |
| Browser injection | DOM text nodes and restrictive CSP | Packaged JavaScript and HTTP smoke test |
| Network exposure | Loopback default; reverse-proxy requirement | Operator guide |

## Residual risks

Metadata descriptions can be incomplete or semantically ambiguous. The deterministic concern match
is explainable but not proof of business independence. Production policy must treat low-confidence or
missing context as requiring review. MCP mutations can partially succeed if the server fails between
calls; operators must inspect DataHub before retrying. The built-in HTTP server is a demo transport,
not an internet-facing security boundary.
