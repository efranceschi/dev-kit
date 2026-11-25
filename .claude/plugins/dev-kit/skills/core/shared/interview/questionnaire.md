# interview questionnaire

Goal: leave the interview with **every decision the rest of the pipeline would otherwise have to ask about**, so that `autopilot` can run for hours without stopping. Completeness beats speed; but never ask what is already known.

## How to run it

1. **Pre-fill before asking.** Parse the user's opening message, any files they pointed to, and the repository (run `dev_detect_stack.py`; skim README, manifests, existing docs). Mark each item below as `known`, `inferable`, or `unknown`.
2. **Ask block by block**, one AskUserQuestion call per block (up to 4 questions per call). Skip a block entirely if every item is `known`. For `inferable` items, state the inference as the recommended option so the user just confirms.
3. **Every question has a recommended option first**, marked "(Recomendado)"/"(Recommended)" in the user's language, and an option meaning "decide for me". "Decide for me" answers are recorded in `brief.md` as `delegated` so later skills know they may decide alone.
4. **Follow-ups are allowed** (one extra round per block at most) when an answer opens a new branch (e.g. payments = yes → which provider, which currency).
5. **Write as you go.** After each block, append its section to `.dev/brief.md` (template `shared/templates/brief.md`). If the session dies mid-interview, `interview` resumes at the first block without a section.
6. **Close.** Show a compact summary (one line per block), ask for a single confirmation, then: derive initial ADRs into `decisions.md`, run `dev_state.py init` with `--language`, `--stack-json` and `--autonomy-json`, then `dev_state.py artifact mark brief`, which closes the interview step of the lifecycle (existing project in `maintenance` mode: hand back to the onboarding instead, `onboarding.md` step 9).

## Blocks and items

### Block 1 — Product and context
- One-sentence problem statement; who suffers from it today and how they cope.
- Target audience and market (B2B, B2C, internal tool, personal).
- Value proposition / what makes it different; 1–3 reference products or competitors.
- Success metrics for v1 (e.g. "10 users complete onboarding").
- Project type: greenfield, rewrite, or adding to an existing codebase (existing code → `start` runs the onboarding first: baseline tag, `.dev/discovery.md`, entry mode; this block then only confirms what discovery found).

### Block 2 — Users and roles
- Personas (name, goal, technical level).
- Roles/permissions model: single user, roles (admin/user), multi-tenant orgs, public visitors.
- Application language(s) and locale(s) (date/number formats, currency); i18n needed now or later.
- Devices/contexts of use (desktop at work, mobile on the go, offline needs).

### Block 3 — Scope
- MVP feature list (must have), nice-to-have (should/could), explicitly out of scope (won't).
- Priority order among must-haves (drives milestone order).
- Hard deadline or budget constraints, if any.
- Anything that must look/behave exactly like an existing system.

### Block 4 — Domain and data
- Core entities and their key relationships (free text; the architect will formalize).
- Expected volume (users, records, requests/day) and growth.
- Import/export needs, file uploads, reporting.
- Retention, backup, deletion rules; personal data and legal constraints (LGPD/GDPR), audit logging.
- External data sources the product reads (APIs, datasets, feeds): what each covers (regions, period, share of the universe a metric needs), how fresh it is, quotas and latency. A metric over "all customers" fed by a source that covers one region is found at QA otherwise; record each source and its coverage assumption for the architecture's data sources table.

### Block 5 — Stack and infrastructure
- Language/framework preference per layer (frontend, backend, mobile) or "decide for me".
- Database (relational/document/none, managed vs local), caching, search.
- Hosting/deploy target (Vercel, Fly, AWS, VPS, Docker, on-prem, "local only for now").
- CI/CD expectations; containers; environments (dev/staging/prod).
- Existing accounts, credentials, env vars or API keys the user can provide (record names only, never values).
- Package manager and Node/Python/Go versions if constrained.
- Exclusive resources and verification environment: anything only one agent or process may use at a time (a remote session, a shared database, a device or emulator, a rate-limited account) and where verification runs. They become locks (`dev_state.py lock`) in the architecture's exclusive resources table.

### Block 6 — Integrations and auth
- Authentication: none, email+password, magic link, OAuth providers, SSO/SAML; session vs JWT; MFA.
- Email/SMS/push notifications and provider.
- Payments/billing and provider; subscription vs one-off.
- Third-party APIs, webhooks, background jobs/queues, file storage (S3-like), analytics.

### Block 7 — UX and UI
- Platform: web app, mobile (native/PWA), desktop, CLI, API only, or combination.
- Visual references (URLs/screenshots), brand assets (logo, colors, font) or "create an identity".
- Tone of voice for copy (formal, friendly, playful), density (compact/comfortable).
- Dark mode, responsiveness targets, minimum accessibility level (WCAG 2.2 AA recommended), keyboard-first needs.
- Any existing design system/component library to use (shadcn, MUI, Tailwind, etc.).

### Block 8 — Quality bar
- Test expectations: unit/integration/e2e, target coverage, which flows must have e2e.
- Linters/formatters/type strictness; pre-commit hooks.
- Performance targets (page load, API latency), scale targets.
- Security level (basic hygiene vs. regulated), secrets handling, dependency policy.
- Observability: logging, error tracking, metrics.
- **Quality bar for the automatic gates** (recommended option first): `standard` (overall ≥ 85, security ≥ 90), `premium` (overall ≥ 92, every dimension ≥ 80, security ≥ 95), `prototype` (overall ≥ 70, only critical/high block). Record as `autonomy.quality` in block 9's JSON. Explain in one line that agents grade each milestone 0–100 per dimension (code, security, tests, spec, UX, accessibility, visual, copy, performance, data, operations, dependencies) and that the build only advances above the cut-off.

### Block 9 — Process and autonomy
- **How much of the run do you want to follow?** (ask first; recommended option first with its reason): the presence step of `conventions.md` §10. `assisted` (recommended: the kit decides the operational points alone, such as a dirty tree, fix rounds used up with a recommendation, a slow CI or a model escalation, and asks only the product and external decisions), `supervised` (the kit asks at every pause point; for a first project you want to watch closely), `milestone` (never interrupts inside a milestone: the product and external questions are parked and asked together at the end of each milestone), `unattended` (the run never waits: pause points take the `unattended` values, parked items are reported at the end), `custom` (walk the matrix). Explain in one line that the release approval, the PRD and plan confirmations and the floors stay with the user at every step.
- For `milestone`, `unattended` and `custom`: show the §10 matrix already filled (point · action · limit) and ask for confirmation or changes, at most 4 questions per round, each with the recommended action first and one line of reason. Each change is the user's exception over the step. Collect the limits that `preauthorize` needs (any step): monthly spend cap and currency (`paid_services`; `"unlimited"` is accepted only as an explicit answer, never as a default), environments where data may be deleted (`delete_data`, never production), deploy/publish targets (`public_exposure`). State the floors (§10) as facts, not as questions.
- Then: when something is parked, end the run when nothing else can advance (`stop_when_idle`, recommended) or at the first parked item (`stop_first`); and whether to send an app notification per parked item (`notify_on_park`).
- Remind users of every step but `supervised` that Claude Code's own permission prompts must be covered by a permission mode or allowlist (`/fewer-permission-prompts`).
- Autonomy level (the technical choices made alone, independent of the presence step): `high` (recommended for autonomous builds), `balanced`, `cautious` — see `autonomy-policy.md`; adjust `always_ask` list.
- May the agent: install dependencies, run dev servers and browsers, create config files (.env.example, CI), call external services with provided keys, create/modify git hooks?
- Git: one commit per task (recommended), commit message style (existing projects: confirm the style found in `discovery.md` §11 as `autonomy.commit_style`, e.g. `{type}: {summary}`; otherwise the default `[{task}] {type}: {summary}`), branch strategy (main vs feature branch per milestone), push allowed?
- **Model and effort for the agents** (recommended option first: `ask`): show the tier table of `conventions.md` §9 (speed: haiku, balanced: sonnet, quality: opus; escalation only for failed dimensions, effort before model) and say what the presence step already gives (`supervised`: `ask`, confirm before each escalation; every other step: `preapproved`, escalate within the ladder without asking); offer `off` (never escalate) or the other mode only as a change, recorded as the user's exception; and ask whether to move any agent to another tier. Record the tiers as `autonomy.model_policy.tiers`, and `model_policy.mode` only when the user changed it.
- **Issues found during the build** (conventions §15, explain in one line that the milestone cadence never changes): share of each milestone reserved for queued issues (`issue_buffer_pct`, recommended 20; 10 is more conservative), and whether to use a short **cool-down** between milestones for small items (recommended on, `max_tasks` 5). Record as `autonomy.issue_buffer_pct` and `autonomy.cooldown`. Mention that short tips will teach the rest as they become useful (`autonomy.tips`, on by default).
- Time budget per task before marking `blocked` (default 30 min), max fix rounds per QA gate (default 3).
- How the user wants to be reached when a blocking question appears (just stop and summarize; or notification if available).

### Block 10 — Delivery
- **Production** — only if the product will run somewhere beyond the developer's machine. Ask how it gets there and when: method (install script, systemd, docker compose, PaaS, other) and host (local or remote); when to deploy (`per_milestone`, recommended when the user already uses the product while it is being built; `on_release`; `manual`); smoke checks (e.g. a health endpoint and the main routes); and the operational prerequisites (backup credentials, API keys, model downloads, certificates), each with how it will be provided — collect them now so they do not surface as loose open questions later. Record as `autonomy.production` in block 9's JSON, and the consent as `pause_policy.production_deploy` (`ask` recommended; `preauthorize` for the named targets in unattended runs).
- **Local deploy per milestone** — only if it makes sense for the platform (table in `conventions.md` §11: web/API/service with `may_run_servers`, desktop, CLI, native mobile with an emulator; never for libraries, single scripts or documents, where it is recorded as `off (inferred)` without asking). Ask: "When a milestone is approved, do you want a version running locally so you can try it?" — `keep_running` (recommended for web/API/service: you try it while the next milestone is built), `smoke` (recommended for CLI/desktop: proves it runs without keeping anything up), `off`. If not `off`, suggest a free port different from the dev port and ask whether to send an app notification with the URL. Record as `autonomy.local_deploy` in block 9's JSON.
- Environments and what "done" means for v1 (deployed? running locally? passing tests?).
- Versioning scheme (semver), changelog, documentation expected (README, API docs, user guide, ADRs). Existing projects: confirm the version source, tag prefix and CHANGELOG format from `discovery.md` §11 instead of asking.
- Handover: who maintains it, onboarding docs needed.

## Output contract

`brief.md` must have one `## Block N — Title` section per block with a bullet per item: `- **Item:** answer` and, where applicable, `(delegated)` or `(inferred, confirmed)`. Unknowns that the user chose to leave open go to `open-questions.md` via `dev_state.py add-question "<question>" --skill interview --assumption "<assumption>" --impact "<impact>"`.
