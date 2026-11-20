"""Tests for 1.19 specification helpers: task contracts, locks, new strings, contrast, policy limits, out-of-scope
findings. Run: python3 -I -m unittest discover -s tests"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
STATE = SCRIPTS / "dev_state.py"
SCORE = SCRIPTS / "dev_score.py"

PLAN = """# Plan

## M1 — One
Goal.

### T-001 Orders table
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-1: orders stored
- test_notes: unit
- files: src/db/orders.py
- contract:
  - table orders(id, customer_id, total_cents, created_at)
  - GET /api/orders -> [{id, total_cents}]
- shared: yes

### T-002 Orders page
- status: todo
- deps: T-001
- type: feature
- acceptance:
  - AC-2: list orders
- test_notes: unit
- files: src/ui/Orders.tsx
- consumes: T-001

### T-003 Totals widget
- status: todo
- deps:
- type: feature
- acceptance:
  - AC-3: totals
- test_notes: unit
- files: src/ui/Totals.tsx
- consumes: T-002
"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ds("init", "--project", "demo")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ds(self, *args: str, expect: int | None = 0) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, "-I", str(STATE), "--root", str(self.root), *args],
                              capture_output=True, text=True, cwd=self.root)
        if expect is not None:
            self.assertEqual(proc.returncode, expect, msg=f"{args}\n{proc.stdout}\n{proc.stderr}")
        return proc

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)


class TestContracts(Base):
    def test_contract_consumes_shared(self) -> None:
        (self.root / ".dev" / "plan.md").write_text(PLAN, encoding="utf-8")
        out = self.ds("sync-plan", expect=None)
        self.assertIn("T-003: consumes T-002 but does not depend on it", out.stdout + out.stderr)
        tasks = json.loads(self.ds("status", "--json").stdout)["tasks"]
        self.assertIn("GET /api/orders", tasks["T-001"]["contract"])
        self.assertTrue(tasks["T-001"]["shared"])
        self.assertEqual(tasks["T-002"]["consumes"], ["T-001"])
        brief = self.ds("brief", "T-002").stdout
        self.assertIn("Contract you consume from T-001: table orders(id, customer_id, total_cents, created_at)", brief)
        got = {(x["check"], x["id"]) for x in json.loads(self.ds("xref", "--json").stdout)["problems"]}
        self.assertIn(("contract_missing", "T-003"), got)
        self.assertNotIn(("contract_missing", "T-002"), got)


class TestLock(Base):
    def test_one_holder_expiry_and_release(self) -> None:
        self.ds("lock", "acquire", "remote-session", "--holder", "implementer-1")
        proc = self.ds("lock", "acquire", "remote-session", "--holder", "implementer-2", expect=3)
        self.assertIn("held by implementer-1", proc.stdout)
        self.ds("lock", "acquire", "remote-session", "--holder", "implementer-1")          # renew own
        self.ds("lock", "release", "remote-session", "--holder", "implementer-2", expect=1)
        self.ds("lock", "release", "remote-session", "--holder", "implementer-1")
        self.ds("lock", "acquire", "remote-session", "--holder", "implementer-2", "--ttl", "0")
        self.ds("lock", "acquire", "remote-session", "--holder", "implementer-3")           # previous expired
        self.assertIn("implementer-3", self.ds("lock", "status").stdout)
        self.ds("lock", "acquire", "Bad Name", "--holder", "x", expect=1)
        self.assertIn("Locks: remote-session by implementer-3", self.ds("status").stdout)
        self.ds("lock", "acquire", "emulator", "--holder", "a", "--ttl", "0")
        self.ds("cleanup")                                                   # frees expired locks
        self.assertNotIn("emulator", self.ds("lock", "status").stdout)


class TestStringsAndContrast(Base):
    def test_new_user_facing_strings(self) -> None:
        self.git("init", "-q")
        (self.root / ".gitignore").write_text(".dev/\n")
        (self.root / "src").mkdir()
        (self.root / "src" / "Form.tsx").write_text("export const F = () => <p>Hello</p>;\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        base = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        (self.root / "src" / "Form.tsx").write_text(
            "export const F = () => <p>Hello</p>;\n"
            "export const G = () => <button aria-label=\"Salvar pedido\" className=\"btn-primary\">Salvar</button>;\n"
            "toast(\"Pedido salvo com sucesso\");\n")
        (self.root / "src" / "locales").mkdir()
        (self.root / "src" / "locales" / "pt.json").write_text('{\n  "orders.empty": "Nenhum pedido ainda"\n}\n')
        self.git("add", "-A")
        self.git("commit", "-qm", "copy")
        got = {x["text"] for x in json.loads(self.ds("strings", "--since", base, "--json").stdout)["strings"]}
        self.assertTrue({"Salvar pedido", "Salvar", "Pedido salvo com sucesso", "Nenhum pedido ainda"} <= got)
        self.assertNotIn("btn-primary", got)
        self.assertNotIn("Hello", got)                                        # unchanged line

    def test_contrast_of_tokens(self) -> None:
        spec = self.root / ".dev" / "design" / "ui-spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("## 2. Tokens\n| token | value |\n|---|---|\n| color.text | #000000 |\n| color.text-muted | #9a9a9a |\n"
                        "| color.bg | #ffffff |\n| color.border | #767676 |\n", encoding="utf-8")
        rows = {(r["fg"], r["bg"]): r for r in json.loads(self.ds("contrast", "--json").stdout)["pairs"]}
        self.assertEqual(rows[("color.text", "color.bg")]["ratio"], 21.0)
        self.assertFalse(rows[("color.text-muted", "color.bg")]["ok"])
        self.assertTrue(rows[("color.border", "color.bg")]["ok"])            # UI part: 3.0 is enough
        self.ds("contrast", "--strict", expect=1)


class TestPolicyAndScope(Base):
    def test_paid_services_unlimited_is_explicit(self) -> None:
        self.ds("set", "autonomy.pause_policy.paid_services", '{"action": "preauthorize", "limit": {"max_monthly": "unlimited"}}')
        self.ds("set", "autonomy.pause_policy.paid_services", '{"action": "preauthorize", "limit": {"max_monthly": "lots"}}', expect=1)
        self.ds("set", "autonomy.pause_policy.paid_services", '{"action": "preauthorize", "limit": {"max_monthly": 50}}')

    def test_out_of_scope_findings_do_not_score(self) -> None:
        raw = self.root / "a11y-auditor.json"
        raw.write_text(json.dumps({"auditor": "a11y-auditor", "findings": [
            {"id": "F-1", "severity": "high", "title": "global nav has no skip link", "file": "src/Nav.tsx", "out_of_scope": True}]}))
        subprocess.run([sys.executable, "-I", str(SCORE), "score", "--scope", "M1", "--root", str(self.root),
                        "--out", str(self.root / "s.json"), str(raw)], capture_output=True, check=True)
        res = json.loads((self.root / "s.json").read_text())
        self.assertEqual(res["blockers"], [])
        self.assertEqual(res["legacy"][0]["reason"], "out_of_scope")


if __name__ == "__main__":
    unittest.main()
