# Negative billing incident

An upstream `billing_amount` assertion finds 37 negative values. Both billing and demographics
derive from the same staging table, but only the billing mart depends on the failing financial
concern.

Expected decision:

- quarantine `mart_billing`;
- allow `mart_demographics` to continue;
- append an incident summary to the source asset;
- propose a `LineageGuard:Quarantined` tag for the billing mart;
- perform no mutation until explicitly approved.

