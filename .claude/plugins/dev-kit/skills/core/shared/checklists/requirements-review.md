# Requirements and plan review checklist (requirements-reviewer)

Two modes. Findings use `category: requirements` (PRD) or `category: planning` (plan).

## Mode `prd` — review `.dev/prd.md` against `.dev/brief.md`
- **Completeness**: every must-have in brief block 3 has a story; every persona in block 2 appears in at least one story; each NFR from blocks 2, 4, 7, 8 appears with a measurable target. Missing must-have → `critical`.
- **Testability**: each AC is observable and specific (value, message, limit, role, state). Vague words (fast, easy, intuitive, properly, secure, user-friendly) without a number or observable outcome → `high`.
- **Consistency**: no two ACs contradict; roles/permissions consistent across stories; terminology identical across sections (same entity, same name). Contradiction → `high`.
- **Scope discipline**: nothing in the PRD that the brief put under "won't"; nothing the brief marked must that the PRD demoted without an ADR. Scope drift → `high`.
- **Ambiguity and hidden decisions**: every assumption listed in §8 with an ADR id; assumptions that change cost or risk (paid service, data retention, public access) flagged for the user. Unrecorded assumption → `medium`.
- **Edge and failure behaviour**: empty states, invalid input, permission denied, concurrent edits, limits, offline where relevant are covered by ACs. Missing for a main flow → `high`.
- **Data and privacy**: personal data identified, retention/deletion rules present when the brief says LGPD/GDPR. Missing → `high`.
- **Measurable success**: success metrics from the brief are traceable to features.

## Mode `plan` — review `.dev/plan.md` against PRD, architecture, design
- **Coverage**: every AC appears in at least one task; every mandatory e2e flow has a task that writes it; every screen in `ui-spec.md` is built by some task. Orphan AC → `critical`. Existing projects: only `new` and `changed` ACs need tasks; `existing` ACs are not orphans.
- **Slicing**: tasks are vertical slices completable in one sitting with tests included; horizontal "build all models" tasks → `medium`; tasks larger than ~90 minutes of work → `medium`.
- **Order and dependencies**: the first milestone is a walking skeleton incl. tooling and CI (new projects only; in existing projects it is the first slice of new work, numbered from `brownfield.first_milestone`); no task depends on a later one; no dependency cycles; dependencies are minimal and justified (`xref --json` on the temp copy: each `unjustified_dep` is `medium` - remove the dependency, or add `consumes` or `dep_reasons`; a milestone whose critical path covers all its tasks while some share no file and no contract is `medium`). Cycle or forward dependency → `critical`.
- **Testability**: each task has `test_notes` naming layers; each AC has a place where it will be proven.
- **Feasibility**: files listed exist in the architecture layout; needed credentials/services are available or flagged as `always_ask`.
- **Risk first**: the riskiest integration or unknown is scheduled early with a spike or thin slice. Late risk → `medium`.
- **Parser contract**: headings and field names follow `shared/conventions.md` §4 so `dev_state.py sync-plan` loads everything (run it in a temp copy if unsure).

Severity per `shared/conventions.md` §7. Report only verified issues; quote the section and ids.
