# Hackathon acceptance matrix

Status meanings: **proved** has inspectable evidence; **pending external** requires a hosted service,
published media, or organizer action; **optional** is not required for eligibility.

| Requirement | Status | Evidence / completion action |
|---|---|---|
| Project created during July 6–August 10, 2026 | Proved | First Git commit is dated inside the submission period; preserve Git history. |
| Working software application | Proved locally | CLI, dashboard HTTP smoke test, generated SQL execution test, and package build. |
| DataHub OSS plus an eligible agent technology | Proved live | Official MCP adapter plus `examples/live-datahub-verification.json`. |
| Agents That Do Real Work category | Proved | `submission/submission.json` and Devpost copy. |
| Meaningful context-graph use | Proved live | Six downstream assets resolved; approved description and tag write-back verified directly in DataHub. |
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
| Meaningful upstream DataHub contribution | Optional | Bonus criterion; no contribution is claimed yet. |
| Most Valuable Feedback survey | Optional | Complete once if desired; separate individual bonus. |

## Judging readiness

| Criterion | Evidence |
|---|---|
| Use of DataHub | MCP lineage and entity reads; description and tag write-back; DataHub retains incident knowledge. |
| Technical execution | Deterministic core, fail-closed adapter, executable artifact test, HTTP smoke test, CI, package build. |
| Originality | Semantic branch containment rather than catalog Q&A or blanket downstream shutdown. |
| Real-world usefulness | Preserves unaffected data availability while isolating financially exposed branches. |
| Submission quality | Accessible dashboard, concise runbook, examples, architecture, disclosures, and 2:45 script. |
