# Operator dashboard

The dashboard presents the same deterministic containment, counterfactual recovery, Chronos temporal
immunity, and artifacts exposed by the CLI. It is a judge-facing demonstration and an operator
decision aid, not a production control plane.

A persistent amber provenance banner identifies the hosted view as an application-owned
DataHub-shaped fixture with no live connection or applied mutation. It separately reports metadata
origin, mutation state, proof integrity, and authentication. Live MCP JSON uses `execution_context`
to identify DataHub metadata and separately supplied recovery/change evidence.

```bash
uv sync --extra dev
uv run lineage-guard-web
```

Open `http://127.0.0.1:8765`. The server binds to loopback by default and exposes:

- `/` — accessible incident console;
- `/api/incidents/current` — current evidence, recovery candidates, certificate, Incident Genome,
  change evaluations, coverage, timeline, and artifact hashes;
- `/healthz` — process health probe.

Use `--host 0.0.0.0` only behind an authenticated reverse proxy. The built-in server deliberately
has no authentication, TLS termination, persistence, or write controls and must not be exposed
directly to an untrusted network.

The recovery panel intentionally shows one rejected and one verified candidate. The rejected clamp
demonstrates why passing the target assertion is insufficient; its billing total diverges from the
trusted snapshot. The certificate is an integrity-bound proposal for release, not evidence that an
operator already approved or executed release.

The Chronos panel shows three intentionally different outcomes: a recurring failure is blocked, an
unchanged safe proposal receives a passport, and a safe guard under changed lineage requires
revalidation. The passport uses the in-toto Statement v1 shape but is unsigned in the demonstration.

The ProofGraph panel is interactive. Select any branch decision to reveal its minimal Causal Cut,
choose any decisive observation, context claim, impact claim, or policy input, and simulate its
removal. The displayed alternative is a precomputed fail-closed policy transition, not browser-side
authority. Evidence Gap Radar shows the highest-value DataHub context improvement with its bounded
priority. The integrity disclosure remains visible beside the Proof Bundle.

The interface supports keyboard navigation, narrow screens, reduced-motion preferences, semantic
headings and landmarks, a skip link, textual status labels, and color-independent decisions.
Browser responses include a restrictive Content Security Policy, clickjacking protection, MIME
sniffing protection, and a no-referrer policy.

## Static judge demo

`uv run python scripts/export_static_demo.py site` exports the packaged interface plus a deterministic
incident evidence bundle and integrity manifest. GitHub Pages publishes this bundle without a
long-running service. The header labels it as a demo environment; live DataHub verification remains a
separate documented workflow.
