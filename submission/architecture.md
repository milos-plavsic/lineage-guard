# Architecture

```mermaid
flowchart LR
    S[Quality signal] --> A[Incident analyzer]
    D[(DataHub context graph)] <-->|Official MCP tools| M[MCP adapter]
    M --> A
    A --> P[Branch decisions]
    P --> R[Remediation generator]
    R --> Q[SQL assertion]
    R --> J[Branch policy]
    R --> H[Human report]
    R --> I[Integrity manifest]
    P --> G{Explicit approval}
    G -->|approved| M
    G -->|default| X[Dry-run record]
    A --> U[Operator dashboard]
```

DataHub is the system of context and institutional memory. The analyzer is deterministic so the same
evidence always produces the same decision. MCP is the interoperability boundary; source-system
changes remain reviewable artifacts. The approval gate prevents an analysis permission from silently
becoming a write permission.
