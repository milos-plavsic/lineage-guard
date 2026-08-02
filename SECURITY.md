# Security policy

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose credentials, metadata, or systems.
Until a dedicated security address is published, contact the repository owner privately through
their GitHub profile. Include reproduction steps, affected versions, impact, and mitigations. Never
include production tokens or sensitive catalog content.

## Trust boundaries

- DataHub metadata is untrusted input and is validated before it becomes SQL or a file path.
- MCP tool payloads are bounded to 2 MB and incomplete context fails closed.
- Credentials are accepted through the environment, excluded from reports, and passed only to the
  official version-pinned MCP child process.
- Read-only analysis is the default. Metadata mutations require both server capability enablement and
  explicit LineageGuard approval.
- Generated SQL is an assertion for review; LineageGuard does not execute remediation against source
  systems.
- The built-in dashboard binds to loopback and has no authentication. Never expose it directly to an
  untrusted network.

## Supported versions

Security fixes are applied to the latest commit on `main` until the first stable release is tagged.
