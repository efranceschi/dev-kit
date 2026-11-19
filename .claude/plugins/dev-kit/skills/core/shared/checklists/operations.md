# Resilience and operations review checklist (ops-reviewer)

Review how the system behaves when things go wrong and how operators can see and run it. Scale the expectations to the brief (a local personal tool needs far less than a public SaaS). Findings use `category: operations`.

## Configuration and environments
- All config from environment variables with validation at boot (fail fast with a clear message); `.env.example` lists every variable (names only); no environment-specific values in code.
- Separate dev/test/prod settings; safe defaults (debug off in prod); secrets not logged.
- One-command setup and run documented and working from a clean checkout (try it when possible).

## Failure handling
- Timeouts on every outbound call (HTTP, DB, queue); retries with backoff and jitter only for idempotent operations; circuit-breaking or graceful degradation for non-critical dependencies.
- Errors are caught at boundaries and translated to consistent responses; no unhandled promise rejections/uncaught exceptions; process exits non-zero on fatal startup errors.
- Background jobs: retries, dead-letter or visible failure, idempotency, graceful shutdown (finish in-flight work on SIGTERM).
- Input limits: body size, upload size, request rate on public endpoints.

## Observability
- Structured logs (JSON or key=value) with level, timestamp, request/correlation id; no secrets or personal data; log levels used sensibly.
- Error tracking hook (Sentry or equivalent) when the brief asks for it; metrics for request rate/latency/errors for services with SLOs.
- Health endpoints: liveness and readiness that check real dependencies (DB), unauthenticated but without sensitive data.

## Delivery
- Dockerfile or deploy config builds reproducibly: pinned base image, non-root user, multi-stage build, `.dockerignore`, no secrets baked in, healthcheck.
- CI runs lint, type-check, tests, build on every push; caches dependencies; fails on errors; matches the commands in `architecture.md`.
- Migrations run as a deploy step with a rollback plan; zero-downtime considerations only if the brief requires.
- Backups and restore procedure documented for stateful stores when the brief mentions retention.

## Developer experience
- Scripts for dev, test, lint, build, migrate, seed; README accurate; pre-commit hooks if the brief wants them.

## Severity
Crash or data loss on a plausible failure of a main path → `high`; missing timeout/retry strategy on an external call used by a main flow → `high`; missing health check/logging/CI in a service meant to be deployed → `medium`; polish → `low`.
