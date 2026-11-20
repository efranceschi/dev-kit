#!/usr/bin/env python3
"""dev_ui.py - Claude Code interface integration for a dev-kit project (conventions.md §15).

A plugin cannot ship settings, so the spinner tips and the status line are written to the project's personal
settings file, <project>/.claude/settings.local.json, which Claude Code keeps out of git. Only what belongs to the
kit is touched: spinner tips whose text starts with "dev-kit: " and a statusLine whose command runs
dev_statusline.py. A status line of the user's own is never replaced. The choices are also recorded in
.dev/state.json (autonomy.ui), which the hooks read for the session title and the notifications.

Standard library only. Usage:
  python3 -I dev_ui.py [--root DIR] status [--json]
  python3 -I dev_ui.py [--root DIR] apply  [--tips] [--tips-file FILE] [--statusline] [--notify] [--title]
  python3 -I dev_ui.py [--root DIR] remove [--tips] [--statusline] [--notify] [--title]
  python3 -I dev_ui.py [--root DIR] decline     the user said no when start offered it: never offer again
  python3 -I dev_ui.py [--root DIR] repair      rewrite the status line path after a plugin update (silent if fine)
  python3 -I dev_ui.py tips                     the English spinner tips from shared/tips.json, as JSON

--tips-file: a JSON array of strings, the spinner tips already translated into the user's language (the skill
translates; kit files are English only). Without it the English texts are used.
Exit codes: 0 ok · 1 usage or an unreadable settings file (never overwritten).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
TIPS_PATH = SCRIPTS.parent / "shared" / "tips.json"
STATUSLINE = SCRIPTS / "dev_statusline.py"
PREFIX = "dev-kit: "
MARKER = "dev_statusline.py"
MAX_TIPS = 60
REFRESH_S = 10
sys.path.insert(0, str(SCRIPTS))  # -I drops the script dir


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"dev_ui: {msg}", file=sys.stderr)
    sys.exit(1)


def find_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cur = Path.cwd().resolve()
    for p in [cur, *cur.parents]:
        if (p / ".dev" / "state.json").exists():
            return p
    return cur


def settings_path(root: Path) -> Path:
    return root / ".claude" / "settings.local.json"


def read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError) as e:
        fail(f"{path} is not valid JSON ({e}); fix it first, it was not changed")
    if not isinstance(data, dict):
        fail(f"{path} is not a JSON object; it was not changed")
    return data


def write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def keep_out_of_git(root: Path) -> None:
    """Claude Code ignores the file only when it writes it itself; add it to .git/info/exclude (local, untracked)."""
    rel = ".claude/settings.local.json"
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if top.returncode != 0:
            return
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel], capture_output=True, timeout=5)
        if ignored.returncode == 0:
            return
        gitdir = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"], capture_output=True, text=True, timeout=5)
        exclude = (root / gitdir.stdout.strip() if not Path(gitdir.stdout.strip()).is_absolute() else Path(gitdir.stdout.strip())) / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        prefix = os.path.relpath(root, top.stdout.strip()).replace(os.sep, "/")
        line = rel if prefix in (".", "") else f"{prefix}/{rel}"
        old = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if line not in old.splitlines():
            exclude.write_text(old + ("" if old.endswith("\n") or not old else "\n") + line + "\n", encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        pass


def catalog_tips() -> list[dict]:
    try:
        return [t for t in json.loads(TIPS_PATH.read_text(encoding="utf-8")).get("tips", []) if t.get("spinner")]
    except (OSError, json.JSONDecodeError):
        return []


def clean_tip(text: str) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(text))).strip()
    if not text.startswith(PREFIX):
        text = PREFIX + text
    return text[:500]


def ours_tip(t: object) -> bool:
    text = t if isinstance(t, str) else (t.get("text") if isinstance(t, dict) else None)
    return isinstance(text, str) and text.startswith(PREFIX)


def ours_statusline(sl: object) -> bool:
    return isinstance(sl, dict) and MARKER in str(sl.get("command", ""))


def statusline_command() -> str:
    return f'python3 -I "{STATUSLINE}"'


def set_tips(data: dict, texts: list[str] | None) -> int:
    over = data.get("spinnerTipsOverride")
    over = dict(over) if isinstance(over, dict) else {}
    others = [t for t in over.get("tips", []) if not ours_tip(t)] if isinstance(over.get("tips"), list) else []
    mine = [clean_tip(t) for t in (texts or []) if str(t).strip()][:MAX_TIPS]
    if others or mine:
        over["tips"] = others + mine
    else:
        over.pop("tips", None)
    if over:
        data["spinnerTipsOverride"] = over
    else:
        data.pop("spinnerTipsOverride", None)
    return len(mine)


def record_state(root: Path, **flags: bool) -> None:
    if not (root / ".dev" / "state.json").exists():
        return
    import dev_state as ds  # noqa: E402 - only when there is a project
    store = ds.Store(root)
    store.load()
    auto = store.state.setdefault("autonomy", ds._copy(ds.DEFAULT_AUTONOMY))
    auto["ui"] = {**ds.DEFAULT_AUTONOMY["ui"], **(auto.get("ui") or {}), **flags, "offered": True}
    store.save()
    store.log("ui " + " ".join(f"{k}={'on' if v else 'off'}" for k, v in flags.items()) if flags else "ui offer declined")


def load_texts(tips_file: str | None) -> list[str]:
    if tips_file:
        try:
            texts = json.loads(Path(tips_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            fail(f"--tips-file: {e}")
        if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            fail("--tips-file must hold a JSON array of strings")
        return texts
    return [t["en"] for t in catalog_tips()]


def cmd_status(root: Path, a: argparse.Namespace) -> None:
    data = read_settings(settings_path(root))
    over = data.get("spinnerTipsOverride") if isinstance(data.get("spinnerTipsOverride"), dict) else {}
    n = sum(1 for t in over.get("tips", []) if ours_tip(t)) if isinstance(over.get("tips"), list) else 0
    sl = data.get("statusLine")
    state = "dev-kit" if ours_statusline(sl) else ("other" if sl else None)
    path_ok = state != "dev-kit" or str(STATUSLINE) in str(sl.get("command", ""))
    ui = {}
    if (root / ".dev" / "state.json").exists():
        try:
            ui = json.loads((root / ".dev" / "state.json").read_text(encoding="utf-8")).get("autonomy", {}).get("ui") or {}
        except (OSError, json.JSONDecodeError):
            ui = {}
    out = {"settings": str(settings_path(root)), "spinner_tips": n, "statusline": state, "statusline_path_ok": path_ok,
           "title": ui.get("title", True), "notify": ui.get("notify", False), "offered": ui.get("offered", False),
           "tips_disabled": data.get("spinnerTipsEnabled") is False}
    if a.json:
        print(json.dumps(out, indent=2))
        return
    print(f"Settings: {out['settings']}")
    print(f"Spinner tips: {n or 'off'}" + (" (spinnerTipsEnabled is false here: no tip shows)" if out["tips_disabled"] else ""))
    print("Status line: " + {"dev-kit": "dev-kit" + ("" if path_ok else " (old path: run repair)"), "other": "your own (left as it is)",
                             None: "off"}[state])
    print(f"Session title and banner: {'on' if out['title'] else 'off'} · Notifications: {'on' if out['notify'] else 'off'}")


def cmd_apply(root: Path, a: argparse.Namespace) -> None:
    if not (a.tips or a.statusline or a.notify or a.title):
        fail("apply needs at least one of --tips --statusline --notify --title")
    path = settings_path(root)
    data = read_settings(path)
    flags: dict[str, bool] = {}
    notes = []
    if a.tips:
        n = set_tips(data, load_texts(a.tips_file))
        flags["spinner_tips"] = True
        notes.append(f"{n} spinner tips (from the next session)")
    if a.statusline:
        sl = data.get("statusLine")
        if sl and not ours_statusline(sl):
            notes.append("status line not changed: this project already has its own")
        else:
            data["statusLine"] = {"type": "command", "command": statusline_command(), "refreshInterval": REFRESH_S}
            flags["statusline"] = True
            notes.append("status line")
    if a.notify:
        flags["notify"] = True
        notes.append("notifications")
    if a.title:
        flags["title"] = True
        notes.append("session title")
    if a.tips or a.statusline:
        write_settings(path, data)
        keep_out_of_git(root)
    record_state(root, **flags)
    print("on: " + ", ".join(notes) + (f" · {path}" if a.tips or a.statusline else ""))


def cmd_remove(root: Path, a: argparse.Namespace) -> None:
    every = not (a.tips or a.statusline or a.notify or a.title)
    path = settings_path(root)
    data = read_settings(path)
    flags: dict[str, bool] = {}
    if every or a.tips:
        set_tips(data, [])
        flags["spinner_tips"] = False
    if every or a.statusline:
        if ours_statusline(data.get("statusLine")):
            data.pop("statusLine")
        flags["statusline"] = False
    if every or a.notify:
        flags["notify"] = False
    if every or a.title:
        flags["title"] = False
    if path.exists():
        write_settings(path, data)
    record_state(root, **flags)
    print("off: " + ", ".join(k.replace("_", " ") for k in flags))


def cmd_decline(root: Path, a: argparse.Namespace) -> None:
    record_state(root)
    print("not offered again; turn any of it on later with /dev-kit:settings")


def cmd_repair(root: Path, a: argparse.Namespace) -> None:
    path = settings_path(root)
    if not path.exists():
        return
    data = read_settings(path)
    sl = data.get("statusLine")
    if ours_statusline(sl) and str(STATUSLINE) not in str(sl.get("command", "")):
        data["statusLine"] = {**sl, "command": statusline_command()}
        write_settings(path, data)
        print("status line path updated")


def cmd_tips(root: Path, a: argparse.Namespace) -> None:
    print(json.dumps([{"id": t["id"], "en": t["en"]} for t in catalog_tips()], indent=1, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dev_ui.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="project root (default: walk up from cwd to find .dev/state.json, else cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status); s.add_argument("--json", action="store_true")
    for name, fn in (("apply", cmd_apply), ("remove", cmd_remove)):
        s = sub.add_parser(name); s.set_defaults(fn=fn)
        for flag in ("--tips", "--statusline", "--notify", "--title"):
            s.add_argument(flag, action="store_true")
        if name == "apply":
            s.add_argument("--tips-file")
    sub.add_parser("decline").set_defaults(fn=cmd_decline)
    sub.add_parser("repair").set_defaults(fn=cmd_repair)
    sub.add_parser("tips").set_defaults(fn=cmd_tips)
    a = p.parse_args(argv)
    a.fn(find_root(a.root), a)


if __name__ == "__main__":
    main()
