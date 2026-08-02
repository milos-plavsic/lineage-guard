# Negative billing incident

An upstream `billing_amount` assertion finds 37 negative values. Both billing and demographics
derive from the same staging table, but only the billing mart depends on the failing financial
concern.

Expected decision:

- quarantine `mart_billing`;
- allow `mart_demographics` to continue;
- reject a clamp-to-zero repair that silently corrupts the trusted billing total;
- certify trusted-value restoration only after all six recovery invariants pass;
- compile the certified incident, historical failure, controls, and context into an Incident Genome;
- block a later change that removes the learned non-negative billing guard;
- mark a guard-preserving change eligible for approval with an unsigned, hash-bound change passport;
- expire that eligibility and require revalidation when lineage context changes;
- append an incident summary to the source asset;
- propose a `LineageGuard:Quarantined` tag for the billing mart;
- propose an immunity tag only after the prevention evidence is generated;
- perform no mutation until explicitly approved.
