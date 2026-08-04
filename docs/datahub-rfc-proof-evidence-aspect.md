# RFC: First-class evidence and decision provenance in DataHub

## Summary

Introduce an interoperable Evidence aspect and read-only proof-query contract so DataHub clients can
answer not only what metadata says, but why a claim is believed, which premises are decisive, when it
expires, and what missing context would resolve uncertainty.

This RFC is a proposal and reference implementation, not a claim that DataHub currently implements
the model.

## Motivation

Agents increasingly consume lineage, assertions, incidents, ownership, contracts, and governance
metadata to make operational decisions. A flat result does not preserve the derivation that connects
those inputs to an outcome. Without provenance, clients cannot reliably detect explanation drift,
stale conclusions, evidence substitution, or the difference between integrity and authentication.

## Goals

- Bind a claim to its subject, evidence, rule, producer, time/context, and validity state.
- Preserve derivation across human, connector, policy-engine, and agent activities.
- Permit minimal causal explanations and bounded counterfactual queries.
- Rank missing metadata without turning recommendations into authority.
- Interoperate with existing DataHub entities and mature external standards.

## Non-goals

- Replacing lineage, assertions, incidents, contracts, policies, or audit logs.
- Treating probabilistic narrative as decision authority.
- Defining a universal trust score.
- Automatically signing, approving, or applying a decision.
- Storing secrets, raw sensitive rows, or unbounded model transcripts in metadata.

## Proposed model

An Evidence record is immutable and content-addressed:

```json
{
  "schemaVersion": 1,
  "claimId": "urn:lineageguard:claim:sha256:...",
  "subjectUrn": "urn:li:dataset:(...)",
  "claimType": "SAFE_TO_CONTINUE",
  "claim": "mart_demographics is excluded from billing_amount exposure",
  "producer": {"kind": "POLICY_ENGINE", "id": "lineageguard-sentinel/v1"},
  "derivedFrom": ["urn:lineageguard:evidence:sha256:..."],
  "rule": "lineageguard/selective-containment/v1",
  "contextDigest": "sha256:...",
  "validity": {"state": "VALID", "expiresOnContextChange": true},
  "authentication": {"state": "UNAUTHENTICATED"},
  "createdAt": "2026-08-04T00:00:00Z"
}
```

Large evidence bodies remain in governed external storage; the aspect contains bounded references,
digests, classifications, and retention metadata. Raw rows and credentials are forbidden.

## DataHub integration

Evidence may attach to Dataset, SchemaField, DataJob, Assertion, Incident, DataContract, MLModel,
Dashboard, or a future Decision entity. Existing URNs remain canonical subjects. Relationships use
typed evidence references rather than overloading operational lineage.

Suggested read operations:

- `getDecisionProof(subjectUrn, decisionId)`
- `getCausalCut(decisionId)`
- `findEvidenceGaps(subjectUrn, limit)`
- `simulateEvidenceChange(decisionId, evidenceId)`
- `verifyProofBundle(bundleDigest)`

MCP names in the reference implementation are `explain_decision`, `get_causal_cut`,
`find_evidence_gaps`, `simulate_context_change`, and `verify_proof_bundle`.

Writes use DataHub's existing authorization and audit boundaries. An evidence writer must not gain
authority to mutate its subject, approve its own decision, or mark its own statement authenticated.

## Provenance and interoperability

The logical mapping is W3C PROV: observations and outputs are Entities, evaluation is an Activity,
producers are Agents, and typed links express use, generation, and derivation. Export uses in-toto
Statements; authentication belongs in a signing envelope. Runtime correlation should carry W3C
Trace Context. CloudEvents is suitable when evidence changes cross event infrastructure.

## Validation

- Reject unknown schema versions, invalid URNs, duplicate IDs, cycles, dangling edges, and oversized
  graphs.
- Canonicalize before hashing and require algorithm identifiers.
- Treat unknown or expired evidence as unavailable; fail closed.
- Separate `integrity_valid`, `authenticated`, `authorized`, and `approved` states.
- Enforce tenant authorization before graph traversal to prevent relationship disclosure.
- Bound query depth, result count, request size, and execution time.

## Ranking model

Evidence-gap priority is a policy output, never a universal truth. The reference model exposes all
factors and weights, rewards uncertainty reduction, business criticality, freshness, and decisions
unlocked, and penalizes collection cost and privacy risk. Deployments must calibrate it using outcome
history and permit governance overrides with audit records.

## Rollout

1. Structured-property prototype holding external proof references.
2. Reference SDK model and MCP read tools.
3. Experimental Evidence aspect behind a feature flag.
4. UI Trust Lens and lineage overlay.
5. Signed evidence producers and retention controls.
6. Outcome-based calibration and general availability after compatibility review.

## Open questions

- Whether Decision should be a standalone entity or an aspect attached to Incident/Assertion.
- Which producers may assert context completeness.
- Retention and deletion semantics when proof references regulated data.
- Cross-tenant proof portability and key discovery.
- How DataHub Actions should subscribe to evidence expiry without notification storms.

## Reference implementation

LineageGuard implements the bounded derivation DAG, exact cuts for its monotone policy, typed
counterfactuals, transparent Radar score, portable unsigned bundle, accessible Trust Lens, and five
read-only MCP tools. It supplies a concrete basis for discussion without coupling the RFC to the
application's incident policy.
