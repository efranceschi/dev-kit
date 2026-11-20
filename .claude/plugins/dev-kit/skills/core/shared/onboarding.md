# Onboarding of an existing project (brownfield)

Used by `start` when `.dev/` does not exist and stack detection reports `"greenfield": false` (manifests, manifests in subfolders, or source files present): a project that was **not** built with dev-kit. Runs **before** `interview`. `DS` = `python3 -I "<KIT>/scripts/dev_state.py" --root <project root>`. The goal: the kit learns what already exists and the project's own conventions, freezes a baseline, and never treats legacy as work to redo or as debt that blocks gates. The rules that later skills follow are in `conventions.md` §16.

Never modify existing source, docs, CI or git history during onboarding; only `.dev/` and the baseline tag are written.

## 1. Git
1. Not a repository → `git init` and commit everything as "Baseline before dev-kit". Repository → `git status --short`, current branch, remote.
2. Dirty tree → one AskUserQuestion: commit, stash, or continue as is (the baseline then excludes the uncommitted files; say so in `discovery.md`).
3. Tag the baseline: `git tag dev-kit-baseline` (skip if the tag exists; never move it). Record the sha **of the tag** (`git rev-list -n 1 dev-kit-baseline`), not of HEAD. Everything after this tag is "new work".

## 2. State first
Create the state now, so every later step can log and register issues: `DS init --language <tag> --phase interview --project "<name>" --stack-json '<detected json>' --brownfield-json '{"baseline_ref":"dev-kit-baseline","baseline_sha":"<sha>"}'`. Existing projects keep `pause_policy.dirty_tree` at `ask` automatically (the tree may hold the user's own work). Then start the session: `DS event session_start --set trigger=start --set brownfield=true` and `DS event skill_start --set skill=start --set args_kind=onboarding`.

## 3. Discovery → `.dev/discovery.md`
Steps 3, 4 and 5 are independent: run them at the same time (the test baseline in the background, one `Explore` agent for the code and one for the existing documents and decisions when the repository is large), then write the files.

Write from `<KIT>/shared/templates/discovery.md`. Start from the detection JSON, then read README, CLAUDE.md, `docs/`, manifests, CI files, top-level folders, routes, models/migrations, `.env.example`. For repos with more than ~50 source files spawn the `Explore` agent with the project root and ask for: modules and responsibilities, entry points, routes/commands, screens and design system, data model, auth, external integrations, how to build/test/run. State facts only; mark anything unverified as `(inferred)`. If `discovery.md` already exists, resume: fill missing sections, do not rewrite.

Also record the project's conventions (§11 of the template):
- **Commit style**: `git log -50 --format=%s`. Conventional Commits → `{type}: {summary}`; a ticket prefix (e.g. `ABC-12 …`) → `{summary}` (the ticket goes in the summary when the user gives one); no pattern → the dev-kit default.
- **Version and tags**: version field of the main manifest, `git tag --sort=-creatordate | head`, tag prefix (`v`, none, `release-`), CHANGELOG file and format.
- **Deploy**: how production is deployed today. A CI/CD pipeline that deploys on merge or tag → `method: external`.

## 4. Existing documentation and decisions
List in §12 of `discovery.md` every document that already states requirements or decisions: PRDs, specs, RFCs, user stories, `docs/adr/`, `decisions/`, `ARCHITECTURE.md`, API specs (OpenAPI), user guides. When a remote exists and `gh` is available, run `gh issue list --state open --limit 50` and note the count and the most relevant links; do not import issues.

## 5. Baseline of tests → `.dev/qa/baseline.md`
Write from `<KIT>/shared/templates/baseline.md`. Run the project's test command once (from detection or discovery), plus coverage when the tool is already configured. Record: command, passed/failed/skipped counts, coverage if any, date, sha. Each pre-existing failure becomes an issue, not a finding: `DS add-issue --type bug --class intangible --origin baseline --title "<test id> fails at baseline" --severity <low, or medium when it covers a main path> --note "qa/baseline.md"`. No test command or no tests → record "no automated tests" and let `test` write the plan later; never install tooling here.

## 6. Decisions → `.dev/decisions.md`
- ADRs the project already has: one entry each with `source: imported`, the original title, and a `link:` to the file; never copy or rewrite their content.
- Structural facts not covered by them: one ADR each (stack and versions, persistence, auth, deployment, main libraries grouped by purpose) with `source: discovered`, `status: accepted`, and a one-line "Decision" taken from the code.

These stop reviewers from flagging pre-existing dependencies and structure as undocumented.

## 7. Entry mode and first milestone
One AskUserQuestion with two questions, recommended option first (derived from the user's input and §12 of discovery):
- **Mode:**
  - **feature** — the user wants a new capability or a behaviour change (default when the input describes one).
  - **maintenance** — only bugs and small improvements (recommended when the input is a bug or "keep it working").
  - **import** — the project already has a PRD, specs or user stories worth using as the source (recommended when §12 lists them).
- **Number of the first milestone** (default `1`, i.e. `M1`): projects that already count iterations, sprints or releases may continue their numbering (e.g. `7` → the first dev-kit milestone is `M7`). Recommend `1` unless discovery shows a numbering in use.

## 8. Mark the state
`DS init --brownfield-json '{"mode":"<mode>","first_milestone":<n>}' --autonomy-json '{"commit_style":"<from discovery>"<, "production": {...} when discovery found a deploy>}'`. Log `DS event skill_end --set skill=start --set status=ok`.

## 9. Hand over, by mode
- **feature** → invoke `interview --express`, framed on the change the user wants, not on the product as a whole. Blocks 5–8 and 10 are pre-filled from `discovery.md` as `inferred`; confirm them in one question. Then the normal pipeline; `plan` numbers milestones from `M<first_milestone>`.
- **import** → invoke `interview --express` passing the documents in §12 as the primary source: only blocks they do not cover are asked. `prd` is then derived from those documents (ACs tagged `existing`/`new`/`changed`, keeping their original ids as references); stages whose artifact already exists in the project (e.g. an architecture document) are written as a short `.dev/` summary that links to the original. Then as `feature`.
- **maintenance** →
  1. `interview --express` limited to quality, autonomy and deploy consent (blocks 8–10); everything else `inferred` from discovery. The interview returns here instead of recommending `autopilot`.
  2. `prd`: as-built only, every AC `existing`; `architecture`: summary of discovery with links to the ADRs.
  3. Write `.dev/plan.md` with only `# Plan` and `## M<n> — Maintenance` (`n` = `first_milestone`, no tasks), run `DS sync-plan`, then `DS review prd n/a --note "maintenance mode: as-built PRD"`, the same for `design` and `plan`, and `DS set phase implement`.
  4. Tell the user that bugs and improvements now go through `/dev-kit:issue` (they become tasks in `M<n>`); when those tasks are done, `qa M<n>` gates them like any milestone and the next issues open `M<n+1> — Maintenance`. `/dev-kit:start` with a feature switches to the feature path (`DS init --brownfield-json '{"mode":"feature"}'`, which reopens the `n/a` reviews, then `prd` revision and `plan replan`).
