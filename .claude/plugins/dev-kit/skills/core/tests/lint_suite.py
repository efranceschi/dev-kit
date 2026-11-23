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
  - every script command quoted in an inline code span (`dev_state.py ...`, `DS ...`, `dev_score.py`/`SC`,
    `dev_cost.py`/`DC`, `dev_board.py`/`DB`) names an existing subcommand and existing flags
  - help.json args and each skill's argument-hint mention the same --flags
  - counts and section ranges written in prose ("23 skills", "17 agents", "§0–§16") match the kit
  - every skill has a telemetry stage, and the feedback areas listed in conventions §13 match dev_telemetry.py
  - every "conventions.md §N" reference points to an existing section
  - no skill tells the model to invoke a skill marked disable-model-invocation
Exit 0 when clean, 1 on any error.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

AGENT_COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")  # Claude Code subagent colors; the board uses the same names
KNOWN_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "Grep", "Glob", "Bash", "WebSearch", "WebFetch", "Agent", "Task",
               "AskUserQuestion", "Skill", "NotebookEdit", "TodoWrite", "ToolSearch", "LS"}
KIT_REF = re.compile(r"<KIT>/([A-Za-z0-9_./\-]+)")
NON_SCORED = {"architect", "implementer"}
# Kit files are English only (conventions §1). Exceptions are deliberate language examples, listed here.
ALLOW_NON_ENGLISH = {
    "skills/core/shared/checklists/copy-review.md": "forms of address example (tu/você)",
    "docs/e2e-checklist.md": "the Portuguese end-to-end scenario quotes simulated user input",
    "skills/core/shared/board/i18n/pt-BR.json": "the board's Portuguese (Brazil) catalog: its translations are the point",
    "skills/core/scripts/dev_risk.py": "risk keywords also match task titles written in the user's language (Portuguese)",
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
            err(f"{rel}: ${{CLAUDE_PLUGIN_ROOT}} is only substituted in hooks; skills use ${{CLAUDE_SKILL_DIR}}")
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
        if fm.get("color") not in AGENT_COLORS:
            err(f"{rel}: agent must declare color {' | '.join(AGENT_COLORS)} (shown by Claude Code and the board), got '{fm.get('color')}'")
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

    contract_checks(claude, core, skill_files, agent_files, err)

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"\n{len(skill_files)} skills (incl. {core_name}), {len(agent_files)} agents, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


# --------------------------------------------------------------------------- contract checks (1.12.0)

class _Parser(Exception):
    def __init__(self, parser):
        self.parser = parser


def cli_surface(script: Path) -> dict | None:
    """{subcommand: set(flags)} plus "" for global flags, read from the script's own argparse definition."""
    import argparse
    spec = importlib.util.spec_from_file_location(f"lint_{script.stem}", script)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.path.insert(0, str(script.parent))
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        sys.path.remove(str(script.parent))
    original = argparse.ArgumentParser.parse_args

    def grab(self, *a, **k):
        raise _Parser(self)
    argparse.ArgumentParser.parse_args = grab  # type: ignore[assignment]
    try:
        try:
            (mod.build_parser() if hasattr(mod, "build_parser") else mod.main([])).parse_args([])
        except _Parser as got:
            parser = got.parser
        else:
            return None
    finally:
        argparse.ArgumentParser.parse_args = original  # type: ignore[assignment]
    out = {"": set(parser._option_string_actions)}
    for act in parser._actions:
        if isinstance(act, argparse._SubParsersAction):
            for name, sp in act.choices.items():
                out[name] = set(sp._option_string_actions) | out[""]
    return out


ALIASES = {"DS": "dev_state.py", "SC": "dev_score.py", "DC": "dev_cost.py", "DB": "dev_board.py", "UI": "dev_ui.py",
           "DW": "dev_worker.py", "DR": "dev_router.py"}
CODE_SPAN = re.compile(r"`([^`\n]+)`")


def check_commands(claude: Path, core: Path, files: list[Path], err) -> None:
    surfaces = {}
    for name in set(ALIASES.values()):
        try:
            s = cli_surface(core / "scripts" / name)
        except Exception as e:  # noqa: BLE001
            err(f"lint: cannot read the CLI of {name}: {e}")
            continue
        if s:
            surfaces[name] = s
    for f in files:
        rel = f.relative_to(claude)
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for span in CODE_SPAN.findall(line):
                toks = span.replace('"', " ").replace("'", " ").split()
                for i, tok in enumerate(toks):
                    script = ALIASES.get(tok) if i == 0 else None
                    if script is None:
                        script = next((v for v in surfaces if tok.endswith(v)), None)
                    if script is None or script not in surfaces:
                        continue
                    rest = toks[i + 1:]
                    while rest and rest[0] == "--root":
                        rest = rest[2:]
                    if not rest or not re.fullmatch(r"[a-z][a-z-]*", rest[0]):
                        break
                    sub = rest[0]
                    known = surfaces[script]
                    if sub not in known:
                        err(f"{rel}:{n}: `{script} {sub}` is not a subcommand")
                        break
                    for t in rest[1:]:
                        flag = t.strip("[](),.;|").split("=")[0]
                        if flag.startswith("--") and re.fullmatch(r"--[a-z][a-z-]*", flag) and flag not in known[sub]:
                            err(f"{rel}:{n}: `{script} {sub}` has no flag {flag}")
                    break


def contract_checks(claude: Path, core: Path, skill_files: list[Path], agent_files: list[Path], err) -> None:
    import json
    shared_md = sorted((core / "shared").rglob("*.md"))
    docs_md = sorted((claude / "docs").glob("*.md")) if (claude / "docs").exists() else []
    md_files = list(skill_files) + list(agent_files) + shared_md + docs_md + [p for p in (claude / "README.md",) if p.exists()]
    check_commands(claude, core, md_files, err)

    # scripts and hooks measure, skills do not (conventions §13): no skill logs durations or agent events itself
    manual = re.compile(r"`?(agent_spawn|agent_end)`?|duration_s")
    for sf in skill_files:
        for i, line in enumerate(sf.read_text(encoding="utf-8").splitlines(), 1):
            if manual.search(line):
                err(f"{sf.relative_to(claude)}:{i}: skills do not measure time or agents (the scripts and hooks do, conventions §13)")

    skills = {}
    for sf in skill_files:
        fm, _ = frontmatter(sf.read_text(encoding="utf-8"))
        if fm:
            skills[fm.get("name", "")] = (sf, fm)
    user_skills = [n for n in skills if n != "core"]

    # help.json args vs argument-hint
    help_json = core / "shared" / "help.json"
    if help_json.exists():
        cat = {s["name"]: s for s in json.loads(help_json.read_text(encoding="utf-8")).get("skills", [])}
        for name, (sf, fm) in skills.items():
            if name not in cat:
                continue
            hint = set(re.findall(r"--[a-z][a-z-]*", fm.get("argument-hint", "")))
            args = set(re.findall(r"--[a-z][a-z-]*", " ".join(a.get("arg", "") for a in cat[name].get("args", []))))
            for flag in sorted(hint - args):
                err(f"help.json: skill {name} lacks {flag} (in its argument-hint)")
            for flag in sorted(args - hint):
                err(f"skills/{name}/SKILL.md: argument-hint lacks {flag} (in help.json)")

    # counts and section ranges in prose
    conv = core / "shared" / "conventions.md"
    sections = {int(m) for m in re.findall(r"^## (\d+)\.", conv.read_text(encoding="utf-8"), flags=re.M)} if conv.exists() else set()
    prose = md_files + [claude / ".claude-plugin" / "plugin.json"] + [p for p in (claude.parents[1] / "README.md", claude.parents[1] / "GET_STARTED.md") if p.exists()]
    for f in prose:
        text = f.read_text(encoding="utf-8")
        rel = f.name if not f.is_relative_to(claude) else f.relative_to(claude)
        for m in re.finditer(r"\b(\d+) (skills|agents)\b(?! \(incl)", text):
            want = len(user_skills) if m.group(2) == "skills" else len(agent_files)
            if int(m.group(1)) not in (want, want + 1 if m.group(2) == "skills" else want):
                err(f"{rel}: says '{m.group(0)}' but the kit has {want} {m.group(2)}")
        for m in re.finditer(r"§(\d+)[–-]§(\d+)", text):
            if sections and f != conv and "conventions" in text[max(0, m.start() - 80):m.start()] + str(rel) \
                    and (int(m.group(1)) != min(sections) or int(m.group(2)) != max(sections)):
                err(f"{rel}: range '{m.group(0)}' but conventions.md has §{min(sections)}–§{max(sections)}")
        for m in re.finditer(r"conventions(?:\.md)?`?\s*§(\d+)", text):
            if sections and int(m.group(1)) not in sections:
                err(f"{rel}: conventions §{m.group(1)} does not exist")

    # telemetry stages and feedback areas
    tel_py = core / "scripts" / "dev_telemetry.py"
    if tel_py.exists():
        spec = importlib.util.spec_from_file_location("dev_telemetry_lint", tel_py)
        tel = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(tel)  # type: ignore[union-attr]
        for name in sorted(set(user_skills) - set(tel.SKILL_STAGE)):
            err(f"dev_telemetry.py: skill {name} has no entry in SKILL_STAGE")
        m = re.search(r"\*\*Feedback areas\*\*[^\n]*", conv.read_text(encoding="utf-8")) if conv.exists() else None
        listed = set(re.findall(r"`([a-z_]+)`", m.group(0).split("):", 1)[-1])) if m else set()
        if not m:
            err("conventions.md §13: no '**Feedback areas**' list")
        elif listed != set(tel.FEEDBACK_AREAS):
            err(f"conventions.md §13 feedback areas differ from dev_telemetry.FEEDBACK_AREAS: {sorted(listed ^ set(tel.FEEDBACK_AREAS))}")

    # skills that the model may not invoke
    locked = [n for n, (_, fm) in skills.items() if fm.get("disable-model-invocation") == "true" and n != "core"]
    for name, (sf, _) in skills.items():
        for n, line in enumerate(sf.read_text(encoding="utf-8").splitlines(), 1):
            for lk in locked:
                if lk != name and re.search(rf"\binvoke\w*\s+(?:`/dev-kit:|`)?{lk}`", line, flags=re.I) \
                        and not re.search(r"\bnever\b|only be started by the user|user starts", line, flags=re.I):
                    err(f"{sf.relative_to(claude)}:{n}: tells the model to invoke `{lk}`, which has disable-model-invocation")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
