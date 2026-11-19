#!/usr/bin/env python3
"""lint_suite.py - consistency checks for a suite of skills and agents that lives under .claude/.

Usage: python3 -I lint_suite.py [--claude-dir DIR]
Defaults: DIR = the plugin folder that contains skills/ and agents/. Every skill and agent in it is checked.

Checks
  - every skill has frontmatter, name == folder, description 1..1024 chars
  - core exists, has no way to be invoked (disable-model-invocation true, user-invocable false)
  - skills reference support files only as ${CLAUDE_SKILL_DIR}/../core/<path>, and each path exists
  - agents and shared files never use ${CLAUDE_SKILL_DIR} or ${CLAUDE_PLUGIN_ROOT} (not substituted there); they use <KIT>/<path>, which must exist
  - every skill declares the kit root; every agent that uses <KIT> explains where it comes from
  - every scoring dimension in scripts/dev_score.py maps to an existing agent and vice versa
  - every file of the kit is in English (accented letters or common Portuguese words are errors, except ALLOW_NON_ENGLISH)
  - the help catalog matches the skills and the generated docs are fresh (scripts/dev_docs.py check), when docs/ exists
Exit 0 when clean, 1 on any error.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

KNOWN_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "Grep", "Glob", "Bash", "WebSearch", "WebFetch", "Agent", "Task",
               "AskUserQuestion", "Skill", "NotebookEdit", "TodoWrite", "ToolSearch", "LS"}
KIT_REF = re.compile(r"<KIT>/([A-Za-z0-9_./\-]+)")
NON_SCORED = {"architect", "implementer"}
# Kit files are English only (conventions §1). Exceptions are deliberate language examples, listed here.
ALLOW_NON_ENGLISH = {
    "skills/core/shared/checklists/copy-review.md": "forms of address example (tu/você)",
    "docs/e2e-checklist.md": "the Portuguese end-to-end scenario quotes simulated user input",
}
ENGLISH_WORDS_WITH_ACCENTS = {"résumé", "café", "naïve", "façade", "cliché", "déjà"}
NON_ENGLISH = re.compile(r"[ãõçáéíóúâêôàÃÕÇÁÉÍÓÚÂÊÔÀñ]|\b(?:não|você|também|está|então|porque|usuário|projeto|tarefa|"
                         r"para o|para a|com o|com a|fazer|quando o|que o|isso|aqui)\b", re.IGNORECASE)
TEXT_SUFFIXES = {".md", ".json", ".py", ".dot", ".txt", ".yaml", ".yml", ".toml"}


def non_english(text: str) -> list[str]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        clean = line
        for w in ENGLISH_WORDS_WITH_ACCENTS:
            clean = re.sub(w, "", clean, flags=re.IGNORECASE)
        m = NON_ENGLISH.search(clean)
        if m:
            hits.append(f"line {n}: '{m.group(0)}'")
    return hits


def frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---\n"):
        return None, "missing frontmatter"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "unterminated frontmatter"
    fm: dict = {}
    key = None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and key:
            fm[key] = (fm[key] + " " + line.strip()).strip()
            continue
        if ":" not in line:
            return None, f"bad frontmatter line: {line!r}"
        key, _, val = line.partition(":")
        key = key.strip()
        fm[key] = val.strip().strip('"').strip("'")
    return fm, ""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude-dir", default=str(Path(__file__).resolve().parents[3]))
    a = ap.parse_args(argv)
    claude = Path(a.claude_dir).resolve()
    core_name = "core"
    core = claude / "skills" / core_name
    errors: list[str] = []
    warnings: list[str] = []
    names: set[str] = set()

    def err(m: str) -> None:
        errors.append(m)

    skill_files = sorted((claude / "skills").glob("*/SKILL.md"))
    agent_files = sorted((claude / "agents").glob("*.md"))
    if not skill_files:
        err(f"no skills under {claude / 'skills'}")
    if not core.exists():
        err(f"missing support skill {core_name}")

    for sf in skill_files:
        rel = sf.relative_to(claude)
        text = sf.read_text(encoding="utf-8")
        fm, why = frontmatter(text)
        if fm is None:
            err(f"{rel}: {why}")
            continue
        name = fm.get("name", "")
        names.add(name)
        if name != sf.parent.name:
            err(f"{rel}: name '{name}' != folder '{sf.parent.name}'")
        desc = fm.get("description", "")
        if not desc:
            err(f"{rel}: empty description")
        elif len(desc) > 1024:
            err(f"{rel}: description longer than 1024 chars ({len(desc)})")
        for tool in [t.strip().split("(")[0] for t in fm.get("allowed-tools", "").split(",") if t.strip()]:
            if tool not in KNOWN_TOOLS and not tool.startswith("mcp__"):
                warnings.append(f"{rel}: unknown tool in allowed-tools: {tool}")
        if name == core_name:
            if fm.get("disable-model-invocation") != "true" or fm.get("user-invocable") != "false":
                err(f"{rel}: the support skill must set disable-model-invocation: true and user-invocable: false")
            continue
        if "${CLAUDE_PLUGIN_ROOT}" in text:
            err(f"{rel}: plugin variable found; this suite is not a plugin")
        if "Kit root (`<KIT>`" not in text:
            err(f"{rel}: must declare the kit root and pass it to agents")
        for ref in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/\.\./" + re.escape(core_name) + r"/([A-Za-z0-9_./\-]+)", text):
            ref = ref.rstrip(".,;:)`'\"")
            if not ref.endswith("/") and not any(c in ref for c in "<*{") and not (core / ref).exists():
                err(f"{rel}: references missing {core_name}/{ref}")
        if "${CLAUDE_SKILL_DIR}/scripts" in text or "${CLAUDE_SKILL_DIR}/shared" in text:
            err(f"{rel}: support files live in {core_name}; use ${{CLAUDE_SKILL_DIR}}/../{core_name}/...")
        if len(text) > 25000:
            warnings.append(f"{rel}: long body ({len(text)} chars)")

    for af in agent_files:
        rel = af.relative_to(claude)
        text = af.read_text(encoding="utf-8")
        fm, why = frontmatter(text)
        if fm is None:
            err(f"{rel}: {why}")
            continue
        name = fm.get("name", "")
        names.add(name)
        if name != af.stem:
            err(f"{rel}: name '{name}' != file '{af.stem}'")
        if not fm.get("description"):
            err(f"{rel}: empty description")
        if fm.get("model") not in ("haiku", "sonnet", "opus"):
            err(f"{rel}: agent model must be haiku | sonnet | opus (not inherit), got '{fm.get('model')}'")
        if fm.get("effort") not in ("low", "medium", "high", "xhigh", "max"):
            err(f"{rel}: agent must declare effort low | medium | high | xhigh | max, got '{fm.get('effort')}'")
        if not fm.get("tools"):
            warnings.append(f"{rel}: no tools declared (inherits all)")
        for tool in [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]:
            if tool.split("(")[0] not in KNOWN_TOOLS and not tool.startswith("mcp__"):
                warnings.append(f"{rel}: unknown tool: {tool}")
        if "${CLAUDE_" in text:
            err(f"{rel}: ${{CLAUDE_*}} variables are not substituted in agents; use <KIT>")
        if "<KIT>" in text and "Kit root:" not in text:
            err(f"{rel}: uses <KIT> but does not explain where the kit root comes from")

    scan = list(skill_files) + list(agent_files) + sorted((core / "shared").rglob("*.md"))
    for f in scan:
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(claude)
        if f.is_relative_to(core / "shared") and "${CLAUDE_" in text:
            err(f"{rel}: shared files are not substituted; use <KIT>")
        for ref in KIT_REF.findall(text):
            ref = ref.rstrip(".,;:)`'\"")
            if not ref.endswith("/") and not any(c in ref for c in "<*{") and not (core / ref).exists():
                err(f"{rel}: <KIT>/{ref} does not exist")

    score_py = core / "scripts" / "dev_score.py"
    if score_py.exists():
        spec = importlib.util.spec_from_file_location("dev_score_lint", score_py)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        mapped = set(mod.AUDITOR_DIMENSION)
        agents = {f.stem for f in agent_files}
        for n in sorted(mapped - agents):
            err(f"dev_score.py maps '{n}' but agents/{n}.md does not exist")
        for n in sorted(agents - mapped - NON_SCORED):
            err(f"agent '{n}' has no scoring dimension in dev_score.py")
        if set(mod.DEFAULT_QUALITY["weights"]) != set(mod.AUDITOR_DIMENSION.values()):
            err("dev_score.py weights do not match the set of dimensions")

    for f in sorted(claude.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_SUFFIXES or "__pycache__" in f.parts or f.name == Path(__file__).name:
            continue
        rel = f.relative_to(claude).as_posix()
        if rel in ALLOW_NON_ENGLISH:
            continue
        hits = non_english(f.read_text(encoding="utf-8", errors="replace"))
        if hits:
            err(f"{rel}: non-English text ({'; '.join(hits[:3])}); kit files are English only")

    docs_py = core / "scripts" / "dev_docs.py"
    if docs_py.exists() and (claude / "docs").exists():
        import subprocess
        res = subprocess.run([sys.executable, "-I", str(docs_py), "check"], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            err(f"docs: {line}")
        if res.returncode not in (0, 1):
            err(f"docs: dev_docs.py check crashed: {res.stderr.strip()[:200]}")

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"\n{len(skill_files)} skills (incl. {core_name}), {len(agent_files)} agents, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
