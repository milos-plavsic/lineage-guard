# ADR 0007: Chronos causal immunity and temporal proof expiry

- Status: accepted
- Date: 2026-08-02

## Context

Containment answers what is exposed, and counterfactual recovery answers which repair is safe. Neither
prevents recurrence. Copying an assertion into CI is also insufficient because yesterday's proof may
depend on lineage, schema, ownership, or governance context that no longer exists.

Future-change evaluation must not create an arbitrary-code execution service. A portable passport
should follow an established attestation shape while remaining honest about authentication.

## Decision

Chronos compiles a valid, all-green recovery certificate into an immutable Incident Genome. The
Genome binds the incident, historical fixture, DataHub-derived schema/lineage/governance fingerprint,
recovery certificate, exposed/excluded/review branches, six recovery invariants, and prevention
control set.

The deterministic vertical slice evaluates three typed, application-owned changes:

1. removing the quality guard replays the historical failure and is blocked;
2. preserving the guard under identical context becomes eligible for approval; and
3. preserving the guard after a new lineage edge requires revalidation.

Eligible changes receive a hash-bound in-toto Statement v1 with an immutable change subject and a
LineageGuard change-passport predicate. The Statement is deliberately unsigned: its checksum proves
integrity linkage, not issuer identity. Production deployment must place the Statement in an
authenticated envelope or signing workflow before treating it as an attestation.

Chronos generates a Prevention Pack containing the Genome, regression fixture, historical-failure
assertion, policy, evaluations, coverage map, runbook, change passport, DataHub write-back proposal,
and manifest hashes. A passport means `eligible_for_approval`, never automatic deployment.

## Consequences

- Each resolved incident can become deterministic preventive memory.
- Context changes expire proof instead of silently reusing stale conclusions.
- The historical fixture cannot be detached from the Genome without detection.
- The in-toto Statement shape supports future interoperability without adding a runtime dependency.
- The current change proposals prove the protocol but do not parse arbitrary Git diffs or execute
  untrusted repository code.
- DataHub tag/description write-back remains a dry-run proposal requiring tag provisioning and the
  existing explicit mutation boundary.

## References

- [in-toto Statement v1 specification](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
- [DataHub API tutorials for assertions, contracts, incidents, and structured properties](https://docs.datahub.com/docs/api/tutorials)
