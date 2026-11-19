# Onboarding of an existing project (brownfield)

Used by `start` when `.dev/` does not exist and stack detection reports `"greenfield": false` (code or manifests present). Runs **before** `interview`. `DS` = `python3 -I "<KIT>/scripts/dev_state.py" --root <project root>`. The goal: the kit learns what already exists, freezes a baseline, and never treats legacy as work to redo or as debt that blocks gates.

## 1. Git
1. Not a repository → `git init` and commit everything as "Baseline before dev-kit". Repository → `git status --short`, current branch, remote.
2. Dirty tree → one AskUserQuestion: commit, stash, or continue as is (the baseline then excludes the uncommitted files; say so in `discovery.md`).
3. Tag the baseline: `git tag dev-kit-baseline` (skip if the tag exists; never move it). Note the sha. Everything after this tag is "new work".

## 2. Discovery → `.dev/discovery.md`
Write from `templates/discovery.md`. Start from the detection JSON, then read README, CLAUDE.md, `docs/`, manifests, CI files, top-level folders, routes, models/migrations, `.env.example`. For repos with more than ~50 source files spawn the `Explore` agent with the project root and ask for: modules and responsibilities, entry points, routes/commands, data model, auth, external integrations, how to build/test/run. State facts only; mark anything unverified as `(inferred)`. If `discovery.md` already exists, resume: fill missing sections, do not rewrite.

## 3. Baseline of tests → `.dev/qa/baseline.md`
Run the project's test command once (from detection or discovery), plus coverage when the tool is already configured. Record: command, passed/failed/skipped counts, coverage if any, date, sha. Each pre-existing failure becomes an issue of class `intangible` (`DS add-issue`, source `qa/baseline.md`), not a finding. No test command or no tests → record "no automated tests" and let `test` write the plan later; never install tooling here.

## 4. Retroactive ADRs
Append to `.dev/decisions.md` one ADR per structural fact already decided by the code: stack and versions, persistence, auth, deployment, main libraries (group by purpose). Use `source: discovered`, `status: accepted`, and a one-line "Decision" copied from the code. These stop reviewers from flagging pre-existing dependencies as undocumented.

## 5. Mark the state
`DS init --language <tag> --phase interview --project "<name>" --stack-json '<detected json>' --brownfield-json '{"baseline_ref":"dev-kit-baseline","baseline_sha":"<sha>"}'`. Existing docs (README, docs/, CLAUDE.md) stay untouched; `docs` merges into them later.

## 6. Hand over to the interview
Invoke `interview` in `--express` mode, framed on the **change the user wants** (new features, fixes, refactors), not on the product as a whole. Blocks 5–8 are pre-filled from `discovery.md` as `inferred`; confirm them in one question. Then continue the normal pipeline.

## How later skills use the marker (`brownfield` in `state.json`)
- `prd`: add an "As-built" summary from `discovery.md`; tag each AC `existing` (verify only) or `new` (to build). Only `new` ACs need tasks.
- `architecture`: reuse the discovered ADRs; do not re-decide the stack.
- `plan`: no walking-skeleton M1; no tasks for `existing` ACs; milestones hold only new work.
- `qa`: score only what changed since `baseline_ref` (`git diff dev-kit-baseline..HEAD`); pre-existing problems become `intangible` issues, never blocking findings; the baseline test failures in `qa/baseline.md` are not F-001.
- `docs`: merge into existing README/docs instead of overwriting.
