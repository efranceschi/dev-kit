#!/usr/bin/env python3
"""dev_perms.py - the permissions a dev-kit run needs without anyone at the console (conventions.md §17).

Standard library only. Commands (--root defaults to the current directory):
  show [--json]                      the kit's safe set, which of its rules the project's settings already have, and
                                     the permissions that were denied in unattended runs because nobody answered
  apply [--file local|project] [--rule R ...] [--miss KEY] [--json]
                                     add allow rules to .claude/settings.local.json (local, the default) or
                                     .claude/settings.json (project): the kit's safe set, only the --rule ones, or
                                     the rule of one denied permission (--miss, which is then forgotten).
                                     Only `permissions.allow` is touched (merged, never removed); never a deny or ask
                                     rule, a directory or a permission mode
  dismiss KEY [--json]               forget a denied permission

The safe set is what audits run all the time and what cannot change the project: read-only git, file inspection
(ls, wc, du, stat, head, tail, grep, gzip -c to measure a size...), the dependency scanners, and the measurement
scripts an auditor writes in its own scratch folder `.dev/tmp/` (run with `timeout`). The PermissionRequest hook
(dev_agent_hook.py) allows a command made only of these at once in an unattended run (a round child, the board's
worker or Autopilot), so an audit never waits 10 minutes for `gzip -c dist/app.js | wc -c`; `round run` and the
board's headless runs also pass the same rules to Claude Code as --allowedTools. A permission outside the set that
nobody answers is recorded in .dev/run/permission-misses.json: `show` lists it with the rule that would allow it,
and the board shows it (read-only) in Needs you.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

# read-only commands (first words); a command made only of these, with no output redirection, is safe
SAFE_PREFIXES = [
    "git status", "git diff", "git log", "git show", "git blame", "git grep", "git ls-files", "git ls-tree",
    "git cat-file", "git rev-parse", "git rev-list", "git describe", "git check-ignore", "git merge-base",
    "git shortlog", "git count-objects",
    "ls", "wc", "du", "stat", "file", "head", "tail", "cat", "grep", "egrep", "rg", "uniq", "cut", "diff", "cmp",
    "jq", "sha256sum", "sha1sum", "md5sum", "shasum", "realpath", "basename", "dirname", "pwd", "nproc", "uname",
    "which", "gzip -c", "gzip -9c", "gzip -9 -c", "gzip -c9", "gzip -cd", "gunzip -c", "brotli -c", "zstd -c",
    "node --version", "npm --version", "python3 --version", "npm audit", "npm ls", "pip-audit", "cargo audit",
]
# measurement scripts in the auditor's scratch folder (resource-isolation.md): code the kit's own agent wrote
MEASURE_RUNNERS = ("node", "python3", "python", "bun", "deno run", "npx tsx", "tsx")
SCRATCH = ".dev/tmp/"
# words that turn a safe command into one that writes or runs something else
UNSAFE_ARGS = re.compile(r"(?:^|\s)(?:--output(?:=|\s)|-o\s|--exec\b|-exec\b|--open-files-in-pager\b|-O\b|--ext-diff\b)")
# rules written to settings / passed as --allowedTools: the same set, minus what only the hook can check safely
SETTINGS_SKIP = {"git diff", "git log", "git show", "git status", "git rev-parse", "git check-ignore", "git ls-files"}


def _split(cmd: str) -> list[str] | None:
    """The simple commands of a command line (&&, ||, ;, | and newlines), or None when it has a construct the
    hook does not judge (substitution, process substitution, a redirection that writes, a heredoc)."""
    if re.search(r"`|\$\(|<\(|>\(|<<", cmd):
        return None
    # redirections that only discard or merge output are fine; any other `>` writes a file
    clean = re.sub(r"\d?>>?\s*/dev/null|\d?>&\d|&>\s*/dev/null", " ", cmd)
    if ">" in clean:
        return None
    parts = [p.strip() for p in re.split(r"&&|\|\||;|\||\n", clean)]
    return [p for p in parts if p]


def _strip_wrappers(seg: str) -> str:
    s = seg.strip()
    while True:
        m = re.match(r"^(?:timeout\s+(?:-[ks]\s*\S+\s+|--\S+\s+)*\d+[smh]?\s+|time\s+|nice\s+(?:-n\s*\d+\s+)?)", s)
        if not m:
            return s
        s = s[m.end():]


def _measure_ok(seg: str, timed: bool) -> bool:
    for r in MEASURE_RUNNERS:
        if seg.startswith(r + " "):
            rest = seg[len(r):].strip()
            try:
                words = shlex.split(rest)
            except ValueError:
                return False
            if not words:
                return False
            script = words[0].removeprefix("./")
            return timed and script.startswith(SCRATCH) and ".." not in script
    return False


def segment_safe(seg: str) -> bool:
    raw = seg.strip()
    if re.fullmatch(r"cd\s+\S+", raw) or raw in ("true", ":"):
        return True
    s = _strip_wrappers(raw)
    timed = s != raw and raw.startswith("timeout")
    if _measure_ok(s, timed):
        return True
    if UNSAFE_ARGS.search(" " + s):
        return False
    return any(s == p or s.startswith(p + " ") for p in SAFE_PREFIXES)


def is_safe(cmd: str) -> bool:
    """Whether a Bash command is made only of the kit's safe set (read-only, or a timed scratch measurement)."""
    if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > 2000:
        return False
    parts = _split(cmd)
    return bool(parts) and all(segment_safe(p) for p in parts)


def safe_rules() -> list[str]:
    """The safe set as Claude Code permission rules (settings allow list, --allowedTools)."""
    out = [f"Bash({p} *)" for p in SAFE_PREFIXES if p not in SETTINGS_SKIP and " --version" not in p]
    out += [f"Bash({p})" for p in SAFE_PREFIXES if " --version" in p]
    for r in ("node", "python3"):
        out += [f"Bash(timeout * {r} {SCRATCH}*)"]
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------- settings files
def settings_path(root: Path, which: str) -> Path:
    return root / ".claude" / ("settings.local.json" if which == "local" else "settings.json")


def read_settings(p: Path) -> dict:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def present(root: Path) -> set[str]:
    have: set[str] = set()
    for which in ("local", "project"):
        allow = (read_settings(settings_path(root, which)).get("permissions") or {}).get("allow") or []
        have |= {x for x in allow if isinstance(x, str)}
    return have


RULE_RE = re.compile(r"^(?:Bash|Read|Grep|Glob|WebFetch|Edit|Write)(?:\([^()\n]{1,300}\))?$")


def apply_rules(root: Path, rules: list[str], which: str = "local") -> list[str]:
    """Merge allow rules into a settings file; returns the ones added. Refuses anything that is not an allow rule
    of the usual shape, and never broadens a tool to all its uses (a bare `Bash` is refused)."""
    bad = [r for r in rules if not RULE_RE.match(r) or r in ("Bash", "Edit", "Write") or r.endswith("(*)")]
    if bad:
        raise ValueError(f"not an allow rule the kit writes: {', '.join(bad)}")
    p = settings_path(root, which)
    cur = read_settings(p)
    if p.exists() and not cur and p.read_text(encoding="utf-8", errors="replace").strip():
        raise ValueError(f"{p} is not valid JSON: fix it first, nothing was written")
    perms = cur.setdefault("permissions", {})
    if not isinstance(perms, dict):
        raise ValueError(f"{p}: permissions is not an object, nothing was written")
    allow = perms.setdefault("allow", [])
    if not isinstance(allow, list):
        raise ValueError(f"{p}: permissions.allow is not a list, nothing was written")
    added = [r for r in dict.fromkeys(rules) if r not in allow]
    if added:
        allow.extend(added)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    return added


# ---------------------------------------------------------------- permissions nobody answered
def misses_path(root: Path) -> Path:
    return root / ".dev" / "run" / "permission-misses.json"


def _load_misses(root: Path) -> dict:
    v = read_settings(misses_path(root))
    return v if isinstance(v, dict) else {}


def _save_misses(root: Path, data: dict) -> None:
    p = misses_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = dict(sorted(data.items(), key=lambda kv: kv[1].get("last", 0))[-50:])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def suggest_rule(tool: str, target: str, label: str | None) -> str | None:
    """The rule `apply --miss` writes: the one Claude Code suggested, else the first two words of
    the command (`Bash(npx lighthouse *)`), never a bare tool."""
    if label and "," not in label and RULE_RE.match(label) and not label.endswith("(*)") and label not in ("Bash", "Edit", "Write"):
        return label
    if tool == "Bash" and target:
        parts = _split(target)
        if not parts or len(parts) != 1:
            return None
        try:
            words = shlex.split(_strip_wrappers(parts[0]))
        except ValueError:
            return None
        words = [w for w in words[:2] if re.fullmatch(r"[A-Za-z0-9_./:@+-]{1,60}", w)]
        if words and not words[0].startswith("-"):
            return f"Bash({' '.join(words)} *)"
    return None


def record_miss(root: Path, tool: str, target: str, agent: str | None, how: str, label: str | None = None,
                where: str | None = None) -> str:
    """A permission denied in an unattended run because nobody answered (or an auditor's was let go): kept for the
    board's Needs you until allowed or dismissed. Returns its key."""
    target = " ".join(str(target or "").split())[:200]
    key = "M-" + hashlib.sha256(f"{tool}\0{target}".encode()).hexdigest()[:10]
    data = _load_misses(root)
    cur = data.get(key) or {"key": key, "tool": tool[:40], "target": target, "count": 0, "first": time.time()}
    cur.update(count=int(cur.get("count", 0)) + 1, last=time.time(), agent=(agent or None), how=how, where=where,
               rule=suggest_rule(tool, target, label))
    data[key] = cur
    _save_misses(root, data)
    return key


def misses(root: Path) -> list[dict]:
    return sorted(_load_misses(root).values(), key=lambda m: -float(m.get("last", 0)))


def dismiss(root: Path, key: str) -> bool:
    data = _load_misses(root)
    if key not in data:
        return False
    data.pop(key)
    _save_misses(root, data)
    return True


def allow_miss(root: Path, key: str, which: str = "local") -> list[str]:
    """`apply --miss KEY`: write the denied permission's rule to the settings and forget it."""
    m = _load_misses(root).get(key)
    if not m:
        raise KeyError(key)
    if not m.get("rule"):
        raise ValueError("this permission has no rule the kit can write; allow it in Claude Code's /permissions")
    added = apply_rules(root, [m["rule"]], which)
    dismiss(root, key)
    return added


# ---------------------------------------------------------------- command line
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dev_perms.py", description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--json", action="store_true")
    a_ = sub.add_parser("apply")
    a_.add_argument("--file", choices=["local", "project"], default="local")
    a_.add_argument("--rule", action="append", default=[])
    a_.add_argument("--miss", help="the key of a denied permission (show lists them): write its rule")
    a_.add_argument("--json", action="store_true")
    d = sub.add_parser("dismiss")
    d.add_argument("key")
    d.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    if a.cmd == "show":
        have = present(root)
        rules = safe_rules()
        out = {"safe_set": rules, "missing": [r for r in rules if r not in have], "denied": misses(root)}
        if a.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"kit safe set: {len(rules)} rules, {len(out['missing'])} not in .claude/settings*.json"
                  + (" (apply them: dev_perms.py apply)" if out["missing"] else ""))
            for m in out["denied"]:
                print(f"denied {m['key']}: {m['tool']} {m['target'][:80]} ({m['count']}x, {m.get('how')})"
                      + (f" -> rule {m['rule']}" if m.get("rule") else ""))
        return 0
    if a.cmd == "apply":
        try:
            added = allow_miss(root, a.miss, a.file) if a.miss else apply_rules(root, a.rule or safe_rules(), a.file)
        except KeyError:
            print(f"dev_perms: no denied permission {a.miss} (dev_perms.py show lists them)", file=sys.stderr)
            return 1
        except ValueError as e:
            print(f"dev_perms: {e}", file=sys.stderr)
            return 1
        out = {"file": str(settings_path(root, a.file).relative_to(root)), "added": added}
        print(json.dumps(out, indent=2) if a.json else
              f"{len(added)} rule(s) added to {out['file']}" + (": " + ", ".join(added[:8]) + (" ..." if len(added) > 8 else "") if added else " (all there already)")
              + "; new Claude Code sessions use them")
        return 0
    ok = dismiss(root, a.key)
    print(json.dumps({"dismissed": ok}) if a.json else ("dismissed" if ok else f"no denied permission {a.key}"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
