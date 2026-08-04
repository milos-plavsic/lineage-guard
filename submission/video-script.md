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

## 1:36–1:58 — Chronos causal immunity

Show the three change cards, Incident Genome, coverage map, and passport.

> Chronos now converts the incident and cure into preventive memory. Removing the billing guard
> replays the historical failure and is blocked. Preserving it earns an in-toto-shaped passport.
> Then a new DataHub lineage edge appears: yesterday's proof expires automatically, even though the
> guard still passes. Every incident makes the platform harder to break twice.

## 1:58–2:25 — ProofGraph and Evidence Gap Radar

Select the billing decision, show its Causal Cut, simulate removed evidence, then show the Radar.

> ProofGraph makes the automation prove why. The decision and explanation share one deterministic
> derivation graph. Its Causal Cut is the smallest decisive evidence set. Remove any premise and the
> Trust Lens shows the fail-closed alternative. Evidence Gap Radar then identifies the DataHub context
> improvement with the highest decision value. Five read-only MCP tools make this proof reusable by
> other agents.

## 2:25–2:37 — Artifacts and action

Show candidate SQL, evaluation JSON, certificate, manifest, then the approval boundary.

> One unsigned in-toto bundle binds containment, recovery, immunity, graph, and every causal cut.
> Integrity is not approval: mutations still require explicit authorization and an exact signed
> orchestrator receipt.

## 2:37–2:48 — Technical proof

Show a terminal with tests and the MCP adapter filenames, then the health endpoint.

> The safety authority is deterministic and fail-closed. Full statement and branch coverage verifies
> authenticated events, lineage, recovery, drift, causal proofs, tampering, MCP tools, and permissions.

## 2:48–2:55 — Close

Return to the full dashboard.

> LineageGuard makes DataHub proof-carrying: contain what is exposed, release what is proven, prevent
> what is remembered—and show exactly why.
