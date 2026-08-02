# Operator dashboard

The dashboard presents the same deterministic incident analysis and remediation artifacts exposed by
the CLI. It is a judge-facing demonstration and an operator decision aid, not a production control
plane.

```bash
uv sync --extra dev
uv run lineage-guard-web
```

Open `http://127.0.0.1:8765`. The server binds to loopback by default and exposes:

- `/` — accessible incident console;
- `/api/incidents/current` — current evidence, decisions, timeline, and artifact hashes;
- `/healthz` — process health probe.

Use `--host 0.0.0.0` only behind an authenticated reverse proxy. The built-in server deliberately
has no authentication, TLS termination, persistence, or write controls and must not be exposed
directly to an untrusted network.

The interface supports keyboard navigation, narrow screens, reduced-motion preferences, semantic
headings and landmarks, a skip link, textual status labels, and color-independent decisions.
Browser responses include a restrictive Content Security Policy, clickjacking protection, MIME
sniffing protection, and a no-referrer policy.
