# RFC proposal: evidence and decision provenance for DataHub agents

## Maintainer question

Should agent-derived operational claims be modeled as an immutable Evidence aspect attached to
existing entities, or as a standalone Decision entity linked to Assertions, Incidents, and assets?

## Problem

Agents can read lineage, assertions, ownership, contracts, incidents, and governance, then act. The
catalog currently preserves the inputs and often the resulting mutation, but not a portable,
machine-verifiable derivation connecting them. Consumers cannot reliably ask which premises were
decisive, whether context drift invalidated the conclusion, or which missing metadata would resolve
an abstained decision.

## Narrow proposed primitive

An immutable, bounded evidence record containing:

- subject URN and typed claim;
- producer identity/reference;
- evidence and rule references;
- context digest and validity/expiry state;
- separate integrity, authentication, authorization, and approval states;
- optional external attestation reference.

It would not replace lineage, Assertions, Incidents, Data Contracts, policies, or audit logs, and it
would not store raw rows, secrets, unbounded transcripts, or a universal trust score.

## Reference implementation

LineageGuard implements a deterministic derivation DAG, exact subset-minimal sufficient evidence
cuts for bounded monotone policies, policy reevaluation under removed evidence, ranked evidence-gap
recommendations, an accessible Trust Lens, and five read-only MCP tools:

- `explain_decision`
- `get_causal_cut`
- `find_evidence_gaps`
- `simulate_context_change`
- `verify_proof_bundle`

Repository: <https://github.com/milos-plavsic/lineage-guard>

Full draft: <https://github.com/milos-plavsic/lineage-guard/blob/main/docs/datahub-rfc-proof-evidence-aspect.md>

## Requested feedback

1. Aspect on existing entities versus standalone Decision entity?
2. Which producer may assert lineage/context completeness?
3. How should evidence expiry integrate with Actions without notification storms?
4. Should authenticated attestations remain external references or be first-class entities?
5. Which authorization boundary should protect derivation traversal from relationship disclosure?

If the direction is useful, I will adapt the draft to the DataHub RFC template and submit it to
`datahub-project/rfcs` rather than proposing schema code prematurely.
