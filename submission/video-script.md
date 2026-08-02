# Demonstration video script

Target duration: **2 minutes 45 seconds**. Hard ceiling: **2 minutes 55 seconds**. Record in English
at 1080p. Use only original narration and screen recording; do not add copyrighted music.

## 0:00–0:15 — Problem

Show the dashboard title and healthcare lineage.

> A bad upstream field should not force an entire data platform offline. LineageGuard uses DataHub
> context to contain the branch that is actually affected while healthy data products keep running.

## 0:15–0:38 — Trigger and DataHub context

Show the negative `billing_amount` signal, then DataHub lineage from `raw_patients` through staging to
the billing and demographics marts.

> Our synthetic healthcare pipeline reports negative billing values. LineageGuard calls DataHub's
> official MCP Server for downstream lineage and batched entity context—descriptions, owners, tags,
> usage, and business meaning.

## 0:38–1:10 — Selective decision

Return to the blast-radius panel. Focus on the billing quarantine and demographics continue states.

> Both marts are connected, but connection is not the same as impact. Billing carries the financial
> concern and scores one hundred, so it is quarantined. Demographics has no dependency on billing
> semantics, so it continues. Every result includes its evidence and rationale; missing context stops
> analysis instead of being treated as safe.

## 1:10–1:38 — Artifacts

Show the generated SQL, JSON policy, report, and manifest.

> LineageGuard now generates a SQL assertion that returns violating rows, a machine-readable branch
> policy, a human remediation report, and SHA-256 integrity hashes. These artifacts are ready for a
> pull request and can be reviewed without running the platform.

## 1:38–2:06 — Write-back and safety

Show dry-run output, then the approval boundary. If the live environment is available, show the
description and quarantine tag in DataHub after approval.

> The default is read-only. A write requires explicit approval in LineageGuard and mutation tools
> independently enabled in DataHub MCP. Approved incident context is appended to the source and the
> affected branch receives a quarantine tag, so the next person or agent inherits the decision.

## 2:06–2:30 — Technical proof

Show a terminal with tests and the MCP adapter filenames, then the health endpoint.

> The decision core is deterministic, the MCP boundary fails closed, and automated tests cover
> containment, write authorization, generated SQL, fixture integrity, HTTP behavior, and oversized
> responses. The same core powers both the CLI and accessible dashboard.

## 2:30–2:45 — Close

Return to the full dashboard.

> LineageGuard turns DataHub's context graph into safe operational action: contain what is broken,
> preserve what is healthy, and write the knowledge back.
