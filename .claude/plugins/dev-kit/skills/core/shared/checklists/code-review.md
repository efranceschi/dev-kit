# Code review checklist (code-reviewer)

Review the diff of the scope (milestone or task) against `plan.md` acceptance criteria and `architecture.md`. Report only verified issues; read the surrounding code before claiming a bug.

## Correctness (critical/high)
- Logic matches the acceptance criteria; off-by-one, null/undefined paths, error handling that swallows failures, race conditions, wrong async handling (unawaited promises, missing transaction boundaries).
- Input validation at boundaries; consistent error responses; idempotency where retried.
- Data integrity: migrations reversible, constraints match the model, no destructive migration without ADR.

## Conformance (high/medium)
- Follows `architecture.md` module boundaries, naming, folder layout and contracts; no new dependency without ADR (check `decisions.md`).
- Uses existing utilities instead of re-implementing; no dead code or leftover debug output.
- Configuration via env/config, no hard-coded URLs, secrets, ports.

## Maintainability (medium/low)
- Functions do one thing; no deep nesting; clear names; comments explain *why*, not *what*.
- Types are precise (no `any`/`Object` escapes without reason); public interfaces documented.
- Duplication that will drift (same logic in two places).

## Performance (medium unless on hot path)
- N+1 queries, missing indexes for new queries, unbounded lists without pagination, heavy work on the request path that belongs in a job, large bundles / blocking renders.

## Tests (coordinate with test-auditor, do not duplicate)
- Does the diff change behaviour without changing or adding tests? Flag as `test-gap`.

## Output
Follow `shared/prompts/auditor-output-contract.md`. For each finding, give the exact file and line and a one-line failure scenario.
