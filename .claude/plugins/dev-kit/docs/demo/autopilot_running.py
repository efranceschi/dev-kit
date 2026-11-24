"""Show the demo board with its Autopilot switch on and a run in progress, without starting Claude Code.

usage: python3 -I autopilot_running.py PROJECT_DIR PID
Run it after the board started on PROJECT_DIR (build_demo.py, then dev_board.py start). It turns the switch on with the
kit's own command (dev_worker.py autopilot on) and records a run whose process is PID, a process that stays alive while
the screenshots are taken (the board's own pid, from .dev/run/board.json): the board adopts a live run instead of
starting one, so the top bar reads "Autopilot running". Made-up data, for the documentation only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
DW = KIT / "skills" / "core" / "scripts" / "dev_worker.py"


def main() -> None:
    root, pid = Path(sys.argv[1]).resolve(), int(sys.argv[2])
    subprocess.run([sys.executable, "-I", str(DW), "--root", str(root), "autopilot", "on"], check=True, capture_output=True)
    since = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=24)
    run = {"state": "running", "pid": pid, "since": since.isoformat().replace("+00:00", "Z"), "at": since.isoformat().replace("+00:00", "Z"),
           "at_s": time.time(), "runs": 4, "fails": 0}
    (root / ".dev" / "run" / "autopilot-run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"autopilot shown as running (pid {pid})")


if __name__ == "__main__":
    main()
