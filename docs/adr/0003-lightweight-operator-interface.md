# ADR 0003: Lightweight operator interface

## Status

Accepted.

## Context

The hackathon requires a clear, testable demonstration, while the development host has strict memory
limits. Introducing a JavaScript build system or web framework would add operational weight without
improving the core incident workflow.

## Decision

Ship a dependency-free Python HTTP process with packaged HTML, CSS, and JavaScript. It calls the
same domain service and remediation generator as the CLI, publishes a health probe and structured
request logs, binds to loopback by default, and sets restrictive browser security headers. The UI is
responsive and designed around WCAG-compatible semantic structure, keyboard access, reduced motion,
and non-color status cues.

## Consequences

The demo starts quickly with a small memory footprint and cannot drift from the verified decision
core. It is not a general production web server and must sit behind authenticated TLS infrastructure
if hosted publicly. A managed deployment can replace the transport later without replacing the
domain or presentation model.
