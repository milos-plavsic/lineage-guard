# Submission disclosures

- The LineageGuard application was newly created during the hackathon submission period.
- Development used an AI coding assistant. Architecture, code, tests, documentation, and generated
  artifacts are included in the public repository for review.
- Standard development components include Python, uv, pytest, Ruff, Hatchling, and the official MCP
  Python SDK.
- DataHub integration uses the official Apache-2.0 `mcp-server-datahub` package, pinned to version
  `0.6.0` by default.
- Chronos change passports follow the in-toto Statement v1 data shape for interoperability. No
  in-toto implementation is vendored or added as a runtime dependency, and demo passports are
  explicitly unsigned: they prove content integrity, not signer identity or deployment approval.
- ProofGraph maps its derivation model to W3C PROV concepts and packages the cross-pillar result in an
  in-toto-shaped statement. These are compatibility mappings; no W3C, CloudEvents, OpenTelemetry, or
  in-toto implementation is vendored into the safety-critical runtime.
- The optional synthetic healthcare fixture comes from DataHub's Apache-2.0 `static-assets`
  repository at the exact revision documented in `scripts/fetch_healthcare.py`.
- No proprietary data, third-party music, or unlicensed media is included.
- The deterministic demo adapter and sample artifacts are explicitly identified; they do not claim to
  be a live DataHub response.
- “Agent” refers to the implemented durable observe-contextualize-decide-act tool loop. No LLM is
  used in the safety-critical authority, and no generative-AI semantic inference is claimed.
- The generic signed enforcement protocol is fully implemented and tested against its HTTP contract;
  a product-specific Airflow, Dagster, or dbt receiver is not bundled or claimed.
- `continue` in the deterministic fixture relies on explicitly complete field-dependency evidence.
  Live environments without trustworthy column lineage produce monitoring/review, not inferred safety.
- Chronos evaluates bounded, application-owned change proposals in the deterministic demo. It does
  not execute arbitrary pull-request code, and its DataHub immunity write-back is an approval-gated
  proposal rather than a claimed live mutation.
- Evidence Gap Radar uses disclosed application-owned weights and deterministic demo context. It is
  advisory, does not claim universal calibration, and never grants continuation or mutation authority.
