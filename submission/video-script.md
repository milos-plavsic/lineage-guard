# Demonstration video script

Target duration: **2 minutes 45 seconds**. Hard ceiling: **2 minutes 55 seconds**. Record in English
at 1080p. Use only original narration and screen recording; do not add copyrighted music.

## 0:00–0:15 — Problem

Show the dashboard title and healthcare lineage.

> A bad upstream field should not force an entire data platform offline. LineageGuard uses DataHub
> context to hold uncertain work, contain confirmed impact, and continue only branches proven safe.

## 0:15–0:38 — Trigger and DataHub context

Show the negative `billing_amount` signal, then DataHub lineage from `raw_patients` through staging to
the billing and demographics marts.

> Our synthetic healthcare pipeline emits a signed negative-billing event. LineageGuard durably
> deduplicates it, then calls DataHub's official MCP Server for dataset lineage, field lineage, and
> batched entity context.

## 0:38–1:10 — Selective decision

Return to the blast-radius panel. Focus on the billing quarantine and demographics continue states.

> Connection is not the same as field impact. Column lineage confirms billing depends on the failed
> field, and business metadata makes it material, so it is quarantined. Complete field evidence
> excludes demographics, so it can continue. Staging remains under review. Missing evidence never
> becomes a claim of safety.

## 1:10–1:36 — Proof-carrying recovery

Scroll to the before/after recovery twin and both candidate cards.

> Fixing the check is not enough. In an isolated shadow pipeline, clamping negatives to zero makes
> the assertion green but destroys the trusted billing total, so LineageGuard rejects it. Restoring
> the governed snapshot passes six invariants. The recovery certificate binds the incident, DataHub
> context, SQL, output, and checks—but still cannot release anything without approval.

## 1:36–2:05 — Chronos causal immunity

Show the three change cards, Incident Genome, coverage map, and passport.

> Chronos now converts the incident and cure into preventive memory. Removing the billing guard
> replays the historical failure and is blocked. Preserving it earns an in-toto-shaped passport.
> Then a new DataHub lineage edge appears: yesterday's proof expires automatically, even though the
> guard still passes. Every incident makes the platform harder to break twice.

## 2:05–2:23 — Artifacts and action

Show candidate SQL, evaluation JSON, certificate, manifest, then the approval boundary.

> Every artifact has an integrity hash and is ready for review. Approved mode sends an idempotent,
> signed default-hold plan to an orchestrator and requires its exact receipt. DataHub then preserves
> the incident and quarantine decision for the next person or agent.

## 2:23–2:39 — Technical proof

Show a terminal with tests and the MCP adapter filenames, then the health endpoint.

> The safety authority is deterministic, the MCP boundary fails closed, and the event journal handles
> duplicates, conflicts, retries, and crashes. Full line and branch coverage includes authenticated
> HTTP, field evidence, counterfactual SQL, certificate tampering, enforcement, write authorization,
> passport tampering, context drift, enforcement, and oversized responses.

## 2:39–2:50 — Close

Return to the full dashboard.

> LineageGuard turns DataHub's graph into a data-platform immune system: contain what is exposed,
> release what is proven, and prevent what is remembered.
