# Project brief — {{project_name}}

> Purpose: single source of requirements and decisions captured in the interview. Every later skill reads this before asking anything.
> Derived from: interview on {{date}} · Status: draft | approved
> Language of this project's conversation/artifacts: {{language}} · Application UI language(s): {{app_languages}}

## Block 1 — Product and context
- **Problem:**
- **Audience / market:**
- **Value proposition / differentiators:**
- **References / competitors:**
- **Success metrics (v1):**
- **Project type:** greenfield | rewrite | brownfield (repo summary: …)
- **Existing project (brownfield only):** entry mode feature | maintenance | import · first milestone M{{n}} · facts in `.dev/discovery.md` · commit style `{{template}}` · version source and tag prefix {{…}}

## Block 2 — Users and roles
- **Personas:**
- **Roles & permissions model:**
- **Locales / i18n:**
- **Devices / contexts of use:**

## Block 3 — Scope
- **Must (MVP):**
- **Should / Could:**
- **Won't (explicitly out):**
- **Priority order:**
- **Deadline / budget constraints:**

## Block 4 — Domain and data
- **Core entities & relationships:**
- **Volume & growth:**
- **Import / export / uploads / reporting:**
- **Retention, backup, deletion, personal data (LGPD/GDPR), audit:**

## Block 5 — Stack and infrastructure
- **Frontend / backend / mobile stack:** (delegated → architect decides)
- **Database / cache / search:**
- **Hosting / deploy / environments:**
- **CI/CD, containers:**
- **Available credentials & env var names (never values):**
- **Runtime/package manager constraints:**

## Block 6 — Integrations and auth
- **Authentication & sessions, MFA:**
- **Notifications (email/SMS/push) & provider:**
- **Payments / billing:**
- **Third-party APIs, webhooks, jobs/queues, file storage, analytics:**

## Block 7 — UX and UI
- **Platform(s):**
- **Visual references & brand assets:**
- **Tone of voice, density:**
- **Dark mode, responsiveness, accessibility level, keyboard-first:**
- **Design system / component library:**

## Block 8 — Quality bar
- **Tests (layers, coverage target, mandatory e2e flows):**
- **Lint / format / type strictness / pre-commit:**
- **Performance & scale targets:**
- **Security level, secrets handling, dependency policy:**
- **Observability:**
- **Quality bar (gate cut-offs):** standard | premium | prototype → `autonomy.quality` values

## Block 9 — Process and autonomy
- **Autonomy level & always_ask overrides:**
- **Allowed actions:** install deps · run servers/browsers · create configs · call external services · git hooks
- **Git:** commit per task · branches · push
- **Task time budget / max fix rounds:**
- **How to reach the user on blocking questions:**

## Block 10 — Delivery
- **Definition of done for v1:**
- **Production:** method · host · when (per_milestone | per_milestone_flagged | on_release | manual | none) · smoke checks · prerequisites
- **Local deploy per milestone:** keep_running | smoke | off (inferred) · port · notify
- **Versioning, changelog, documentation expected:**
- **Handover / maintenance:**

## Open items
See `.dev/open-questions.md`.
