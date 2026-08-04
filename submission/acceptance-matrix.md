# Hackathon acceptance matrix

Status meanings: **proved** has inspectable evidence; **pending external** requires a hosted service,
published media, or organizer action; **optional** is not required for eligibility.

| Requirement | Status | Evidence / completion action |
|---|---|---|
| Project created during July 6–August 10, 2026 | Proved | First Git commit is dated inside the submission period; preserve Git history. |
| Working software application | Proved locally | CLI, authenticated agent listener, durable journal, dashboard, enforcement contract, SQL execution test, and package build. |
| DataHub OSS plus an eligible agent technology | Proved live | Official MCP adapter plus `examples/live-datahub-verification.json`. |
| Agents That Do Real Work category | Proved | Durable DataHub tool loop, graph write-back, proof-gated recovery, and a fresh-agent incident-memory inheritance test. |
| Meaningful context-graph use | Proved live | Six downstream assets resolved; approved description and tag write-back verified directly in DataHub. Native Document/Incident composition and fresh Agent B handoff have executable contract tests; refreshed external verification is recorded separately when run. |
| Function matches video and description | Pending external | Record only the committed workflow; verify final video against the runbook. |
| Public, easily testable project URL | Proved externally | Public HTTPS demo: <https://milos-plavsic.github.io/lineage-guard/>; URL recorded in `submission/submission.json`. |
| Public source repository | Proved externally | Public repository: <https://github.com/milos-plavsic/lineage-guard>. |
| Complete source, assets, and setup instructions | Proved locally | Source tree, packaged assets, README, `uv.lock`, and runbooks. |
| Apache License 2.0 visible and detected | Proved externally | Complete `LICENSE`; GitHub reports the repository license as Apache-2.0. |
| English text description | Proved | `submission/devpost.md`. |
| Public demonstration video under 3 minutes | Pending external | Record 2:45 script, upload publicly to YouTube or Vimeo, record measured duration. |
| Video shows functioning project | Pending external | Follow `submission/demo-runbook.md` and capture dashboard plus artifacts. |
| No unlicensed trademarks, music, or media | Proved by plan | Original screen recording and narration only; disclosures prohibit external music. |
| Sample outputs available without execution | Proved | `examples/incident-report.json` and `examples/generated/`. |
| Third-party code and data authorized | Proved | Apache-2.0 dependencies and pinned DataHub fixture; `THIRD_PARTY_NOTICES.md`. |
| Pre-existing work and assistance disclosed | Proved | `submission/disclosures.md`. |
| Free judge access through August 31, 2026 | Active commitment | Public Pages demo and repository require no credentials; keep both active through judging. |
| Team representative and entrant eligibility | Pending entrant | Confirm in Devpost account; cannot be proven from the repository. |
| Submission finalized before August 10, 2026 17:00 EDT | Pending entrant | Submit before 23:00 Europe/Budapest and retain confirmation. |
| Meaningful upstream DataHub contribution | Proved externally; review pending | [`datahub#18878`](https://github.com/datahub-project/datahub/pull/18878) fixes Agent Context lineage pagination and passes the relevant upstream build; do not claim merge until maintainer review completes. [`rfcs#13`](https://github.com/datahub-project/rfcs/issues/13) proposes structured evidence provenance. |
| Most Valuable Feedback survey | Optional | Complete once if desired; separate individual bonus. |

## Judging readiness

| Criterion | Evidence |
|---|---|
| Use of DataHub | MCP lineage/entity reads; native related Documents when available; compatible description/tag write-back; optional native Incident; fresh Agent B retrieval and linked prevention outcome. |
| Technical execution | Field-aware authority, authenticated listener, durable retries, fail-closed boundaries, isolated counterfactual SQL, tamper-detecting certificates, 100% line/branch coverage, CI, package build. |
| Originality | A DataHub-native immune loop unifies contain-recover-immunize with cross-agent memory, proof-carrying metadata, exact Causal Cuts, Trust Lens, and Evidence Gap Radar. |
| Real-world usefulness | Contains exposure, proves recovery, blocks recurrence, expires stale proof, and ranks the context needed for safer automation. |
| Submission quality | Responsive semantic dashboard with remote WCAG 2 AA browser gate, concise runbook, examples, architecture, disclosures, and 2:45 script. |
