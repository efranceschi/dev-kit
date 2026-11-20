#!/usr/bin/env python3
"""dev_statusline.py - Claude Code status line for a dev-kit project (conventions.md §15).

Written to the project's .claude/settings.local.json by dev_ui.py apply --statusline. Claude Code runs it with the
session as JSON on stdin; it prints one line, for example:
  dev-kit · implement · M2 3/7 · ▶ T-014 · ⛔ 1 · ? 2 · ▣ 1 · next /dev-kit:implement
Read-only: it never writes, and prints nothing outside a dev-kit project or on any error (a status line must never
break the session). Symbols instead of words, so the line needs no translation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir


def project_root(payload: dict) -> Path | None:
    ws = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {}
    for raw in (ws.get("project_dir"), ws.get("current_dir"), payload.get("cwd")):
        if not raw:
            continue
        cur = Path(str(raw)).resolve()
        for p in [cur, *cur.parents]:
            if (p / ".dev" / "state.json").is_file():
                return p
    return None


def render(root: Path) -> str:
    import dev_state as ds
    store = ds.Store(root)
    store.state = json.loads(store.path.read_text(encoding="utf-8"))
    s = store.state
    lc = ds.lifecycle(store)
    # construction shows its milestone with progress below; conception and planning show their step
    parts = ["dev-kit", lc["phase"] if lc["phase"] in ("construction", "stable") else ds.phase_label(store, lc)]
    ts = store.tasks()
    for m in store.milestone_order():
        live = [v for v in ts.values() if v["milestone"] == m and v["status"] != "dropped"]
        if live and store.milestones()[m].get("gate", "pending") == "pending":
            parts.append(f"{m} {sum(1 for v in live if v['status'] == 'done')}/{len(live)}")
            break
    inprog = store.in_progress()
    if inprog:
        parts.append(f"▶ {inprog[0]}")
    blocked = sum(1 for v in ts.values() if v["status"] == "blocked")
    if blocked:
        parts.append(f"⛔ {blocked}")
    oq = ds.count_open_questions(store)
    if oq:
        parts.append(f"? {oq}")
    try:
        import dev_worker as dw
        waiting = sum(1 for x in dw.items(root) if x["status"] == "pending")
        if waiting:
            parts.append(f"▣ {waiting}")  # requests from the board, run with /dev-kit:worker
    except Exception:  # noqa: BLE001
        pass
    parts.append(f"next {ds.next_command(store)}")
    return " · ".join(parts)


def main() -> int:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
        root = project_root(payload if isinstance(payload, dict) else {}) or project_root({"cwd": "."})
        if root:
            print(render(root))
    except Exception:  # noqa: BLE001 - never break the status line
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
