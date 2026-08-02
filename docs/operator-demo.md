# Operator dashboard

The dashboard presents the same deterministic incident analysis, counterfactual recovery evidence,
and artifacts exposed by the CLI. It is a judge-facing demonstration and an operator decision aid,
not a production control plane.

```bash
uv sync --extra dev
uv run lineage-guard-web
```

Open `http://127.0.0.1:8765`. The server binds to loopback by default and exposes:

- `/` — accessible incident console;
- `/api/incidents/current` — current evidence, decisions, recovery candidates, certificate,
  timeline, and artifact hashes;
- `/healthz` — process health probe.

Use `--host 0.0.0.0` only behind an authenticated reverse proxy. The built-in server deliberately
has no authentication, TLS termination, persistence, or write controls and must not be exposed
directly to an untrusted network.

The recovery panel intentionally shows one rejected and one verified candidate. The rejected clamp
demonstrates why passing the target assertion is insufficient; its billing total diverges from the
trusted snapshot. The certificate is an integrity-bound proposal for release, not evidence that an
operator already approved or executed release.

The interface supports keyboard navigation, narrow screens, reduced-motion preferences, semantic
headings and landmarks, a skip link, textual status labels, and color-independent decisions.
Browser responses include a restrictive Content Security Policy, clickjacking protection, MIME
sniffing protection, and a no-referrer policy.

## Static judge demo

`uv run python scripts/export_static_demo.py site` exports the packaged interface plus a deterministic
incident evidence bundle and integrity manifest. GitHub Pages publishes this bundle without a
long-running service. The header labels it as a demo environment; live DataHub verification remains a
separate documented workflow.
