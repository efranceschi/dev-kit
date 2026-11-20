# Auditor output contract

All auditor and reviewer agents deliver one JSON result following the schema below.

## Delivery
1. Your prompt has an `Output file:` line (e.g. `.dev/qa/M1/raw/code-reviewer.json`). Write the JSON object, and only the JSON object, to that path with the Write tool. It is the only file you write; everything else stays read-only.
2. Validate it: `python3 -I <KIT>/scripts/dev_score.py check --fix <Output file>`. Exit 1 lists what breaks the contract (unknown severity, missing `findings`, unknown `auditor`, invalid JSON): fix the file and run it again until it exits 0. Agents without Bash skip this step; the orchestrator runs it.
3. Your final message is short: at most 5 lines of prose in the language given in the prompt (verdict, counts by severity, the one or two most important findings by id), then the line `Output: <path>`. Do not repeat the findings or paste the JSON: the orchestrator reads the file, and long messages are paid again on every later turn of the session.
4. No `Output file:` line (an older orchestrator): end the message with the JSON in one fenced `json` block instead, after the same short summary.

Use exactly these key names and values: `state` (not `status`) in `previous`, the four severities as written, ids `F-001`, `F-002`… unique within your result. `check --fix` normalises common synonyms, but a result it has to rewrite is a contract miss.

```json
{
  "auditor": "code-reviewer",
  "scope": "M1 | T-003 | path/",
  "sha": "the Audited commit given in the prompt (or git rev-parse HEAD)",
  "summary": "one sentence",
  "stats": {"files_reviewed": 12, "tests_run": true, "tests_passed": 48, "tests_failed": 0},
  "findings": [
    {
      "id": "F-001",
      "severity": "critical | high | medium | low",
      "category": "correctness | security | test-gap | spec-gap | maintainability | performance | usability | accessibility | consistency | design | visual | copy | data | operations | dependencies | docs | requirements | planning",
      "title": "short claim, no rationale",
      "file": "src/auth/login.ts",
      "line": 42,
      "evidence": "what was observed (quote, command output, screenshot name)",
      "failure_scenario": "concrete input/state -> wrong outcome",
      "recommendation": "what to change",
      "acceptance_ref": "AC-4 | null",
      "task_ref": "T-003 | null",
      "effort": "S | M | L",
      "in_change": "true | false (re-runs of document reviews only, see below)",
      "contradicts": "F-nnn when the recommendation reverses an earlier one (optional)",
      "confidence": "high | low (optional; low counts half)",
      "legacy": "true only in existing projects, for a problem in untouched code (optional)"
    }
  ],
  "previous": [
    {"id": "F-003", "state": "closed | open", "partial": "true when open but partly fixed (optional)", "evidence": "how you verified it"}
  ],
  "kit_feedback": {
    "worked": [{"area": "qa", "note": "≤140 chars about the dev-kit"}],
    "failed": [],
    "improve": []
  },
  "verdict": "pass | fail"
}
```

Re-runs (delta mode, round ≥ 2): your prompt lists the previous round's findings of your dimension. For **each** of them, verify it against the current code or artifact and report it in `previous` as `closed` (fixed, with evidence) or `open` (still there). An omitted previous finding counts as open. Do not repeat a previous finding in `findings`; report there only what is new. New `low` findings are recorded but do not affect the score in a re-run, so spend your effort on closing the old ones and on anything new that is medium or worse.

Incremental audits (`conventions.md` §18):
- `Baseline: <path>` in your prompt holds the suite, lint, type-check, data smoke and harness results of this round. Read it; do not run those again. Run a command yourself only for what the baseline lacks and your dimension needs (a scanner, one targeted test, a query), and say so in `stats`.
- `Files to review:` lists the files you must review this round (changed, with open findings, or a spot check); read their direct callers and callees as needed. The other files of the scope were verified unchanged by an earlier round of your dimension: do not re-audit them, but a finding you notice there in passing is still reported.
- A previous finding that is only partly fixed stays `"state": "open"` with `"partial": true` and evidence of what is left; never `closed`.
- A problem that another dimension also reports (same file and line): report it anyway from your angle; `dev_score.py consolidate` links the two and one fix task is created.

Document reviews in delta mode (prd, design, plan, docs; your prompt then also gives `Changes since round <n-1>:` with a diff of the artifact):
- Review the **changed text** and what it directly affects (a renamed entity, an edited AC and the tasks, screens or metrics that cite it). Do not re-read the whole document looking for new defects: the first round did that.
- Mark every new finding `"in_change": true` (in or caused by the changed text) or `false` (in text the revision did not touch). A `false` finding below `critical` is recorded but does not score: it waits for a later revision instead of resetting this one.
- Before recommending a change, check the previous findings: if your recommendation would undo or reverse one that was applied (the earlier fix caused the problem you see), set `"contradicts": "F-nnn"` and explain the trade-off in `recommendation`. Such a finding is capped at `medium`, and the orchestrator settles the trade-off with an ADR instead of starting another round.

`kit_feedback` (optional): at most 3 items per list, each with an `area` from the list in `conventions.md` §13 (e.g. qa, review, implement, scoring, isolation, prompts, scripts, other) and a `note` of at most 140 characters about **the dev-kit itself** (your instructions, checklists, tools, isolation): never about the project, and never with file paths, URLs, names or data from the project.

Agents that run commands follow `shared/prompts/resource-isolation.md` (slot, port, database, processes, files).

Rules:
- `verdict` is `fail` when any finding is `critical` or `high`.
- Only report what you verified by reading code, running commands or inspecting artifacts. Mark anything inferred but unverified with `"confidence": "low"` in the finding.
- No duplicate findings; merge instances of the same root cause into one finding listing all files.
- Existing projects (`.dev/state.json` has `brownfield`, `conventions.md` §16): a problem that already existed at `brownfield.baseline_ref` and that the scope does not make worse gets `"legacy": true`. Legacy findings never score or block; the orchestrator turns them into `intangible` issues. Do not mark as legacy anything in lines the scope added or changed.
- Keep `title` ≤ 60 characters. Severity follows `shared/conventions.md` §7.
- Audit the `Audited commit:` of your prompt and copy it to `sha`. If you see the working tree change while you work (someone fixing in parallel), audit the commit anyway and say so in `summary`.
- If the scope is empty or cannot be found, return `findings: []`, `verdict: "pass"` and explain in `summary`.
- Write nothing to the repository except your `Output file:`. You are read-only otherwise, except for running tests/linters, scratch builds, and saving screenshots/raw tool output under `.dev/qa/<scope>/` when your own instructions say so.
- The `auditor` value must be your exact agent name: `dev_score.py` maps it to a scoring dimension (code, security, tests, spec, ux, a11y, visual, copy, performance, data, operations, dependencies, docs, design, requirements). The score is computed from your findings by a fixed formula, so severity and confidence must be honest: inflating or hiding findings changes the gate outcome.
