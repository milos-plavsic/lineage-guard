# ADR 0006: Proof-carrying counterfactual recovery

- Status: accepted
- Date: 2026-08-02

## Context

Containment limits damage but does not establish when release is safe. A repair can make the failing
assertion green while deleting rows, changing unrelated attributes, or corrupting a conserved
business total. Treating a successful target test as recovery proof exchanges a visible failure for
a silent one.

Executing arbitrary generated SQL would also cross a materially different trust boundary. The
current vertical slice must remain reproducible, bounded, inspectable, and safe on constrained
machines.

## Decision

LineageGuard adds an in-memory SQLite counterfactual recovery lab with two built-in, reviewable SQL
candidates. Candidate SQL is application-owned rather than accepted from an event or network. Input
rows are bounded, identifiers are unique, monetary values use integer cents, and all execution occurs
in a new in-memory database.

A candidate is verified only when every invariant passes:

1. the source failure is reproduced;
2. no negative or null target values remain;
3. row count is preserved;
4. record identity and non-target region values are preserved;
5. trusted replacements cover every invalid record; and
6. the candidate total remains inside an explicit integer tolerance from the trusted snapshot.

The recovery certificate binds the incident report, counterfactual inputs, tolerance, selected SQL,
output, and checks through canonical SHA-256 digests. It proposes `quarantine_to_release`; it does not
perform release or replace the existing explicit approval and signed enforcement boundaries.

## Consequences

- A superficially successful repair can be demonstrated and rejected for a concrete regression.
- Identical context produces identical evaluations, artifacts, and certificates.
- Judges and operators can verify the evidence without credentials or a running DataHub instance.
- The built-in scenario proves the protocol, not universal repair synthesis.
- Real deployments must obtain trusted snapshots through governed, access-controlled storage and
  add domain-specific invariants before enabling recovery action.
- SHA-256 proves integrity and linkage, not authorship. Deployment approval still requires an
  authenticated identity or signed orchestration receipt.
