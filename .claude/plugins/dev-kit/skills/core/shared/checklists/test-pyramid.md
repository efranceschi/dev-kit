# Test strategy and pyramid — checklist

Use when writing `qa/test-plan.md`, when `implement` decides which tests a task needs, and when `test-auditor` audits.

## Shape
| Layer | Share (guide) | Scope | Speed | Tooling by stack (pick what exists) |
|---|---|---|---|---|
| Unit | ~70% | pure functions, validators, reducers, domain rules | ms | vitest/jest, pytest, go test, cargo test |
| Integration | ~20% | API routes with real DB (test container/sqlite), repository layer, component + store | s | supertest, httpx/TestClient, testing-library |
| End-to-end | ~10% | the mandatory flows from the brief (block 8), happy path + 1 critical error path each | s–min | Playwright, Cypress, Detox |
| Static | always | type-check, lint, format, dependency audit | s | tsc, mypy/pyright, eslint, ruff, clippy |

## Rules for every task
1. Each acceptance criterion the task serves has at least one test naming the AC (`AC-4` in test title or comment).
2. Test the behaviour, not the implementation: assert outputs/side effects, not internal calls, unless the call *is* the contract.
3. One failure reason per test; descriptive names (`rejects invalid email with inline message`).
4. Edge cases: empty, boundary, invalid type, unauthorised, concurrent/duplicate, locale-specific formats.
5. No sleeps; deterministic data (fixed seeds/clocks); isolate external services with fakes at the boundary.
6. Tests must run in CI from a clean checkout with one command recorded in `architecture.md`.

## Audit questions (test-auditor)
- Does every AC in the milestone map to a passing test? (gap → `high`, `category: test-gap`)
- Are there tests that cannot fail (no assertions, assert true, snapshot-everything)? (`medium`)
- Are the mandatory e2e flows present and green? (`high` if missing)
- Flaky indicators: retries, timing-dependent waits, order dependence. (`medium`)
- Test data leaks between tests / shared mutable fixtures. (`medium`)
- Coverage vs target in brief; report the number, do not chase 100%.
