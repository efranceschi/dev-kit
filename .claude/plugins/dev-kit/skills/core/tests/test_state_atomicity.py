"""State changes are atomic, serialised and deterministic (conventions §20).

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -p "test_state_atomicity.py" -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from test_dev_state import STATE, Base

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dev_state as ds  # noqa: E402


def snapshot(dev: Path) -> dict:
    """Every versioned artifact of .dev/ (run/ is machine-local) as path -> bytes."""
    return {str(p.relative_to(dev)): p.read_bytes() for p in sorted(dev.rglob("*")) if p.is_file() and "run" not in p.relative_to(dev).parts}


class TestAtomicity(Base):
    def setUp(self) -> None:
        super().setUp()
        self.init_with_plan()

    def test_parallel_add_task_keeps_every_change_and_unique_ids(self) -> None:
        n = 12
        procs = [subprocess.Popen([sys.executable, "-I", str(STATE), "--root", str(self.root), "add-task", "--milestone", "M1",
                                   "--type", "feature", "--title", f"Parallel {i}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, cwd=self.root) for i in range(n)]
        outs = [p.communicate() for p in procs]
        self.assertTrue(all(p.returncode == 0 for p in procs), msg=str(outs))
        ids = [o[0].split()[0] for o in outs]
        self.assertEqual(len(set(ids)), n)
        st = self.state()
        plan = (self.root / ".dev" / "plan.md").read_text(encoding="utf-8")
        for tid in ids:
            self.assertIn(tid, st["tasks"])
            self.assertIn(f"### {tid} ", plan)
        self.run_state("xref", "--strict")

    def test_failed_command_writes_nothing(self) -> None:
        before = snapshot(self.root / ".dev")
        log_before = (self.root / ".dev" / "log.md").read_bytes()
        self.run_state("add-task", "--milestone", "M1", "--type", "bogus", "--title", "x", expect=1)
        self.run_state("add-task", "--milestone", "M1", "--type", "feature", "--title", "x", "--deps", "T-999", expect=1)
        self.assertEqual(snapshot(self.root / ".dev"), before)
        self.assertEqual((self.root / ".dev" / "log.md").read_bytes(), log_before)

    def test_plan_and_state_roll_back_together(self) -> None:
        """A failure after the plan was edited in memory leaves plan.md and state.json untouched."""
        store = ds.Store(self.root)
        before = snapshot(self.root / ".dev")
        with self.assertRaises(RuntimeError):
            with store.transaction():
                ns = type("A", (), dict(type="feature", milestone="M1", milestone_title=None, title="Half", deps=None, acceptance=None,
                                        test_notes=None, files=None, source=None, issue=None, lane=None, force=False))()
                ds.cmd_add_task(store, ns)
                raise RuntimeError("boom after plan.md was staged")
        self.assertEqual(snapshot(self.root / ".dev"), before)

    def test_commit_writes_plan_and_state_together_then_log(self) -> None:
        self.run_state("add-task", "--milestone", "M1", "--type", "feature", "--title", "Whole")
        tid = max(self.state()["tasks"])
        self.assertIn(f"### {tid} ", (self.root / ".dev" / "plan.md").read_text(encoding="utf-8"))
        self.assertIn(f"add-task {tid}", (self.root / ".dev" / "log.md").read_text(encoding="utf-8"))
        self.assertFalse(list((self.root / ".dev").glob(".*.tmp")))
        self.assertFalse((self.root / ".dev" / "run" / "txn.json").exists())

    def test_killed_commit_is_rolled_forward(self) -> None:
        """Temp files complete + a journal on disk = the commit was decided: the next command finishes the renames."""
        dev = self.root / ".dev"
        new_plan = (dev / "plan.md").read_text(encoding="utf-8") + "\n<!-- recovered -->\n"
        st = self.state()
        st["next_task_id"] = 777
        tmp_plan, tmp_state = dev / ".plan.md.1.aa.tmp", dev / ".state.json.1.aa.tmp"
        tmp_plan.write_text(new_plan, encoding="utf-8")
        tmp_state.write_text(json.dumps(st), encoding="utf-8")
        (dev / "run").mkdir(exist_ok=True)
        (dev / "run" / "txn.json").write_text(json.dumps({"files": [[str(tmp_plan), str(dev / "plan.md")],
                                                                    [str(tmp_state), str(dev / "state.json")]]}), encoding="utf-8")
        self.run_state("status", "--short")
        self.assertIn("recovered", (dev / "plan.md").read_text(encoding="utf-8"))
        self.assertEqual(self.state()["next_task_id"], 777)
        self.assertFalse((dev / "run" / "txn.json").exists())

    def test_corrupt_state_points_to_backup(self) -> None:
        self.run_state("add-task", "--milestone", "M1", "--type", "feature", "--title", "Make a backup")
        (self.root / ".dev" / "state.json").write_text("{not json", encoding="utf-8")
        out = self.run_state("status", expect=1)
        self.assertIn("state.json.bak", out.stderr)

    def test_same_commands_same_bytes_with_pinned_clock(self) -> None:
        def build(root: Path) -> dict:
            env = {**os.environ, "DEV_KIT_NOW": "2026-01-02T03:04:05+00:00"}
            def run(*a: str) -> None:
                r = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(root), *a], capture_output=True, text=True, env=env, cwd=root)
                self.assertEqual(r.returncode, 0, msg=r.stderr)
            run("init", "--language", "en", "--project", "demo")
            (root / ".dev" / "plan.md").write_text(self.plan_text(), encoding="utf-8")
            run("sync-plan")
            run("add-task", "--milestone", "M1", "--type", "feature", "--title", "Same")
            run("add-issue", "--type", "bug", "--class", "standard", "--title", "Same bug")
            run("add-question", "Which one?", "--skill", "t")
            return snapshot(root / ".dev")
        import tempfile
        with tempfile.TemporaryDirectory() as other:
            first_root, second_root = Path(other) / "a", Path(other) / "b"
            first_root.mkdir(); second_root.mkdir()
            one, two = build(first_root), build(second_root)
        self.assertEqual(one.keys(), two.keys())
        for k in one:
            self.assertEqual(one[k], two[k], msg=k)

    def plan_text(self) -> str:
        from test_dev_state import PLAN
        return PLAN


if __name__ == "__main__":
    unittest.main()
