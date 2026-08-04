# ADR 0008: Proof-carrying metadata and evidence-value ranking

## Status

Accepted.

## Context

DataHub provides a rich context graph, but an automated consumer must still distinguish observations,
trusted premises, policy rules, derived decisions, and authenticated proof. Generating prose after a
decision permits explanation drift. Treating missing metadata as a generic error gives platform teams
no rational acquisition priority.

## Decision

LineageGuard constructs a bounded immutable derivation DAG. Nodes are observations, context, rules,
decisions, or proofs. Typed edges map to W3C PROV concepts. The decision and explanation are projections
of this same graph.

For every branch decision, the engine computes all subset-minimal sufficient evidence sets from a
validated bounded monotone policy expression supporting nested `ALL` and `ANY`. Candidate expansion
is capped at 10,000 cuts. The selected Causal Cut is policy-reevaluated before publication. Every
decisive input has a typed, fail-closed counterfactual. No arbitrary code is evaluated.

Evidence Gap Radar emits independently actionable governance, freshness, column-lineage, and
completeness gaps. It uses explicit factors: uncertainty reduction, criticality, freshness need,
decisions unlocked, collection cost, and privacy risk. Versioned operator-supplied weights must sum
to 100; scores are bounded and deterministically tie-broken. Recommendations never authorize
continuation.

The portable Proof Bundle uses the in-toto Statement v1 shape and binds the Sentinel report, Forge
certificate, Chronos Genome, ProofGraph, and all causal cuts. It is unsigned in the demo and therefore
proves integrity, not identity.

## Consequences

- Explanations cannot silently diverge from deterministic authority.
- Operators can test which premise changes an outcome.
- Missing context becomes a prioritized DataHub improvement backlog.
- Graph construction remains linear in incident branches and is bounded to 10,000 nodes and edges.
- Production deployments must authenticate evidence producers and sign the bundle externally.
- A proof is only as sound as its policy and trusted premises.

## Standards mapping

- [W3C PROV-O](https://www.w3.org/TR/prov-o/) for entities, activities, derivation, and responsibility.
- [in-toto Attestation Framework](https://github.com/in-toto/attestation/blob/main/spec/README.md)
  for subject-bound portable claims.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) as the production correlation boundary.
- [CloudEvents](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md) as an optional event
  envelope, not a required core dependency.
