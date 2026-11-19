# Onboarding of an existing project (brownfield)

Used by `start` when `.dev/` does not exist and stack detection reports `"greenfield": false` (code or manifests present): a project that was **not** built with dev-kit. Runs **before** `interview`. `DS` = `python3 -I "<KIT>/scripts/dev_state.py" --root <project root>`. The goal: the kit learns what already exists and the project's own conventions, freezes a baseline, and never treats legacy as work to redo or as debt that blocks gates. The rules that later skills follow are in `conventions.md` §16.

Never modify existing source, docs, CI or git history during onboarding; only `.dev/` and the baseline tag are written.

## 1. Git
1. Not a repository → `git init` and commit everything as "Baseline before dev-kit". Repository → `git status --short`, current branch, remote.
2. Dirty tree → one AskUserQuestion: commit, stash, or continue as is (the baseline then excludes the uncommitted files; say so in `discovery.md`).
3. Tag the baseline: `git tag dev-kit-baseline` (skip if the tag exists; never move it). Note the sha. Everything after this tag is "new work".

## 2. Discovery → `.dev/discovery.md`
Write from `<KIT>/shared/templates/discovery.md`. Start from the detection JSON, then read README, CLAUDE.md, `docs/`, manifests, CI files, top-level folders, routes, models/migrations, `.env.example`. For repos with more than ~50 source files spawn the `Explore` agent with the project root and ask for: modules and responsibilities, entry points, routes/commands, screens and design system, data model, auth, external integrations, how to build/test/run. State facts only; mark anything unverified as `(inferred)`. If `discovery.md` already exists, resume: fill missing sections, do not rewrite.

Also record the project's conventions (§11 of the template):
- **Commit style**: `git log -50 --format=%s`. Conventional Commits → `{type}: {summary}`; a ticket prefix (e.g. `ABC-12 …`) → `{summary}` (the ticket goes in the summary when the user gives one); no pattern → the dev-kit default.
- **Version and tags**: version field of the main manifest, `git tag --sort=-creatordate | head`, tag prefix (`v`, none, `release-`), CHANGELOG file and format.
- **Deploy**: how production is deployed today. A CI/CD pipeline that deploys on merge or tag → `method: external`.

## 3. Existing documentation and decisions
List in §12 of `discovery.md` every document that already states requirements or decisions: PRDs, specs, RFCs, user stories, `docs/adr/`, `decisions/`, `ARCHITECTURE.md`, API specs (OpenAPI), user guides. When a remote exists and `gh` is available, run `gh issue list --state open --limit 50` and note the count and the most relevant links; do not import issues.

## 4. Baseline of tests → `.dev/qa/baseline.md`
Write from `<KIT>/shared/templates/baseline.md`. Run the project's test command once (from detection or discovery), plus coverage when the tool is already configured. Record: command, passed/failed/skipped counts, coverage if any, date, sha. Each pre-existing failure becomes an issue of class `intangible` (`DS add-issue --type bug --class intangible --origin baseline`), not a finding. No test command or no tests → record "no automated tests" and let `test` write the plan later; never install tooling here.

## 5. Decisions → `.dev/decisions.md`
- ADRs the project already has: one entry each with `source: imported`, the original title, and a link to the file; never copy or rewrite their content.
- Structural facts not covered by them: one ADR each (stack and versions, persistence, auth, deployment, main libraries grouped by purpose) with `source: discovered`, `status: accepted`, and a one-line "Decision" taken from the code.

These stop reviewers from flagging pre-existing dependencies and structure as undocumented.

## 6. Choose the entry mode
One AskUserQuestion, recommended option first (derived from the user's input and §12 of discovery):
- **feature** — the user wants a new capability or a behaviour change (default when the input describes one).
- **maintenance** — only bugs and small improvements (recommended when the input is a bug or "keep it working").
- **import** — the project already has a PRD, specs or user stories worth using as the source (recommended when §12 lists them).

## 7. Mark the state
`DS init --language <tag> --phase interview --project "<name>" --stack-json '<detected json>' --brownfield-json '{"baseline_ref":"dev-kit-baseline","baseline_sha":"<sha>","mode":"<mode>"}' --autonomy-json '{"commit_style":"<from discovery>","pause_policy":{"dirty_tree":{"action":"ask"}}<, "production": {...} when discovery found a deploy>}'`. Record the session: `DS event session_start --set trigger=start --set brownfield=true --set mode=<mode>`.

## 8. Hand over, by mode
- **feature** → invoke `interview --express`, framed on the change the user wants, not on the product as a whole. Blocks 5–8 and 10 are pre-filled from `discovery.md` as `inferred`; confirm them in one question. Then the normal pipeline.
- **import** → invoke `interview --express` passing the documents in §12 as the primary source: only blocks they do not cover are asked. `prd` is then derived from those documents (ACs tagged `existing`/`new`); stages whose artifact already exists in the project (e.g. an architecture document) are written as a short `.dev/` summary that links to the original. Then as `feature`.
- **maintenance** →
  1. `interview --express` limited to autonomy, quality and deploy consent (block 9–10); everything else `inferred` from discovery.
  2. `prd`: as-built only, every AC `existing`; `architecture`: summary of discovery with links to the ADRs.
  3. Write `.dev/plan.md` with only `# Plan` and `## M1 — Maintenance` (no tasks), run `DS sync-plan`, then `DS review prd n/a --note "maintenance mode: as-built PRD"`, the same for `design` and `plan`, and `DS set phase implement`.
  4. Tell the user that bugs and improvements now go through `/dev-kit:issue` (they become tasks in M1), and that `/dev-kit:start` with a feature switches to the feature path (`DS init --brownfield-json '{"mode":"feature"}'`, then `prd` revision and `plan replan`).
