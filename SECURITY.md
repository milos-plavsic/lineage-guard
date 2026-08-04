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
- Generated repair SQL executes only against a fresh, bounded in-memory demo shadow; candidate SQL is
  application-owned and never runs against source systems.
- Recovery certificates provide integrity linkage, not issuer authentication or release approval.
- Chronos evaluates bounded, typed demo changes; it does not clone repositories or execute arbitrary
  pull-request code.
- Change passports use the in-toto Statement v1 shape but remain unsigned until a deployment supplies
  an authenticated signing envelope. A passport is never automatic deployment authority.
- ProofGraph explanations are derived from the authority DAG rather than generated text. Every node,
  cut, graph, and cross-pillar bundle is canonically hashed; demo bundles remain explicitly unsigned.
- Counterfactuals are bounded, application-owned transitions. The dashboard and MCP server never
  execute user-supplied code or mutate DataHub, policies, evidence, or source systems.
- Evidence Gap Radar uses an explicit integer-bounded scoring model. Privacy and collection cost are
  penalties, recommendations are advisory, and missing evidence never authorizes continuation.
- Non-demo recovery, changes, and Radar weights require strict versioned files with size, row,
  identifier, type, unknown-field, and combinatorial bounds. Their operator-supplied origin is
  recorded separately from live DataHub metadata.
- The built-in dashboard binds to loopback and has no authentication. Never expose it directly to an
  untrusted network.

## Supported versions

Security fixes are applied to the latest commit on `main` until the first stable release is tagged.
