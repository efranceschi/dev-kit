"""Show the demo board with an Autopilot run in progress, without starting Claude Code.

usage: python3 -I autopilot_running.py PROJECT_DIR
Run it after build_demo.py. It logs the start of an /dev-kit:autopilot run in the project's session log with the kit's
own command (dev_state.py event skill_start), as a real run does, so the board's top bar reads "Autopilot running".
Made-up data, for the documentation only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
DS = KIT / "skills" / "core" / "scripts" / "dev_state.py"


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    subprocess.run([sys.executable, "-I", str(DS), "--root", str(root), "event", "skill_start", "--set", "skill=autopilot"],
                   check=True, capture_output=True)
    print("autopilot shown as running")


if __name__ == "__main__":
    main()
