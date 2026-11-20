# Self-check before a review

The skill that writes a planning artifact (prd, architecture, ux, ui, plan) runs this check before it finishes, and again after every revision. The expensive review findings are almost always cross-document gaps the writer could have caught in minutes; the reviewer should confirm quality, not discover it.

## 1. Run the deterministic checks
- `python3 -I <KIT>/scripts/dev_state.py --root <project> xref`: ACs with no task, tasks citing ACs that do not exist, screens without a spec, ADRs cited but not recorded, unknown task dependencies. Fix every problem that belongs to the artifact you are writing. A problem in an earlier artifact is a revision of that artifact, never a silent workaround in yours.
- `python3 -I <KIT>/scripts/dev_state.py --root <project> stale`: if one of your sources is stale, update it first (or mark it `--note "no impact: …"`).

## 2. Walk the reviewer's checklist yourself
Read the checklist the reviewer of your artifact uses and answer each item against your text:

| artifact | checklist |
|---|---|
| prd | `<KIT>/shared/checklists/requirements-review.md` (mode prd) |
| plan | `<KIT>/shared/checklists/requirements-review.md` (mode plan) |
| ux, ui | `<KIT>/shared/checklists/design-review.md` |
| architecture | the sections of `requirements-review.md` and `design-review.md` that cite the architecture, plus §2 below |

## 3. Cross-document links (the findings that cost whole rounds)
Check every link in this list that your artifact has, in both directions:
- **Metric ↔ data:** every metric, report, filter or sort in the PRD or a screen has the field, column or event that feeds it in the architecture data model, with its type and its origin (when it is first recorded, by whom).
- **Route ↔ artifact:** every route, page, endpoint, file or published output named in one document exists in the others with the same name (screen inventory, API contract, plan task `files`).
- **AC ↔ task ↔ test:** every active AC has a task; every task's acceptance cites real ACs; the task's `test_notes` say how each AC is verified.
- **Entity ↔ rule:** every business rule (limit, permission, retention, state transition) is written once, in the PRD, and the other documents cite it by AC instead of restating it with different numbers.
- **Env var ↔ config:** every secret, flag or external service in the architecture has its variable name, default and where it is validated.
- **States:** every screen lists loading, empty, error and success; every form states validation timing and messages.

## 4. Record it
Fix what you found, then run `dev_state.py artifact mark <artifact>` so later artifacts know what they were built from. In the summary to the user, say in one line how many problems the self-check fixed.
