# Documentation review checklist (docs-reviewer)

Verify that the documentation matches the product as built. **Execute what the docs say.** Findings use `category: docs`.

## README
- Purpose and audience stated in two sentences; matches the PRD.
- Prerequisites with versions; install, run, test, lint, build, deploy commands: **run each one** (or its `--help`/dry-run) in a clean state when safe; a command that fails → `high`.
- Environment variables: every one used in code appears in `.env.example` and the README (grep for `process.env`, `os.environ`, `getenv`, config loaders); undocumented variable → `medium`; secret value present in docs → `critical`.
- Project structure section matches the real tree; links resolve (relative paths exist).
- Screenshots exist and show the current UI (dates/versions not stale).

## User guide
- One section per persona journey in `ux-flows.md`; steps match the actual UI labels (grep the strings; compare with screenshots); features the guide describes exist; features that exist but are missing from the guide (main flows) → `medium`.
- Language and tone match the brief; glossary consistent with the UI.

## API docs
- Every route/operation in code is documented with auth, parameters, request/response examples and error formats; examples are valid against the real schema (validate one or two by calling the endpoint if the app can run); documented endpoints that do not exist → `high`.
- OpenAPI/schema file, if generated, is up to date with the code.

## CHANGELOG and release notes
- Every `[T-xxx]` feature/fix commit since the last tag is represented; version and date correct; fix tasks from QA listed; known limitations (open questions) disclosed.

## Developer docs
- Architecture overview and ADR pointers present; how to add a feature/migration/test; commit convention; CLAUDE.md "dev-kit" section accurate (state location, resume command, test/lint commands).
- Code comments explain why; public modules have docstrings/types; no stale TODOs that contradict the docs.

## Quality of writing
- Skimmable: headings, short sections, code blocks for commands; no walls of text; no marketing fluff; consistent terminology; spelling and grammar in the doc language.

## Severity
Instructions that fail or mislead on the main setup/run path → `high`; missing main-flow guide/API coverage → `medium`; polish → `low`.
