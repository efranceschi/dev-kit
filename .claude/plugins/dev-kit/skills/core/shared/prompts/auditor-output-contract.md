# Auditor output contract

All auditor agents and `code-reviewer`, `spec-tracer` end their final message with exactly one fenced JSON block following this schema, preceded by a short prose summary (max 10 lines) in the language given in the prompt.

```json
{
  "auditor": "code-reviewer",
  "scope": "M1 | T-003 | path/",
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
      "confidence": "high | low (optional; low counts half)",
      "legacy": "true only in existing projects, for a problem in untouched code (optional)"
    }
  ],
  "previous": [
    {"id": "F-003", "state": "closed | open", "evidence": "how you verified it"}
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

`kit_feedback` (optional): at most 3 items per list, each with an `area` from the list in `conventions.md` §13 (e.g. qa, review, implement, scoring, isolation, prompts, scripts, other) and a `note` of at most 140 characters about **the dev-kit itself** (your instructions, checklists, tools, isolation): never about the project, and never with file paths, URLs, names or data from the project.

Agents that run commands follow `shared/prompts/resource-isolation.md` (slot, port, database, processes, files).

Rules:
- `verdict` is `fail` when any finding is `critical` or `high`.
- Only report what you verified by reading code, running commands or inspecting artifacts. Mark anything inferred but unverified with `"confidence": "low"` in the finding.
- No duplicate findings; merge instances of the same root cause into one finding listing all files.
- Existing projects (`.dev/state.json` has `brownfield`, `conventions.md` §16): a problem that already existed at `brownfield.baseline_ref` and that the scope does not make worse gets `"legacy": true`. Legacy findings never score or block; the orchestrator turns them into `intangible` issues. Do not mark as legacy anything in lines the scope added or changed.
- Keep `title` ≤ 60 characters. Severity follows `shared/conventions.md` §7.
- If the scope is empty or cannot be found, return `findings: []`, `verdict: "pass"` and explain in `summary`.
- Write nothing to the repository. You are read-only except for running tests/linters, scratch builds, and saving screenshots/raw tool output under `.dev/qa/<scope>/` when your own instructions say so.
- The `auditor` value must be your exact agent name: `dev_score.py` maps it to a scoring dimension (code, security, tests, spec, ux, a11y, visual, copy, performance, data, operations, dependencies, docs, design, requirements). The score is computed from your findings by a fixed formula, so severity and confidence must be honest: inflating or hiding findings changes the gate outcome.
