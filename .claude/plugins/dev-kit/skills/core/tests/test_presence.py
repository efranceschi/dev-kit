"""Presence steps (3.17, conventions.md §10): the four steps, the user's exceptions over them, and the migration of a
state written before them, which must keep the action of every pause point and the model escalation mode.

Run: python3 -I -m unittest discover -s .claude/plugins/dev-kit/skills/core/tests -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from test_dev_state import Base

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dev_state as ds  # noqa: E402

BF = '{"baseline_ref":"dev-kit-baseline","baseline_sha":"abc1234","mode":"feature"}'
PRODUCT_EXTERNAL = ("security_model_change", "scope_change_major", "paid_services", "credentials", "delete_data",
                    "public_exposure", "production_deploy")


def effective(auto: dict) -> dict:
    """The action of every pause point (a missing one is ask) and the model mode, as any kit reads them."""
    pp = auto.get("pause_policy") or {}
    out = {p: pp.get(p, {"action": "ask"}) for p in ds.PAUSE_ACTIONS}
    out["model_escalation"] = (auto.get("model_policy") or {}).get("mode", "ask")
    return out


class TestSteps(Base):
    def setUp(self) -> None:
        super().setUp()
        self.run_state("init")

    def auto(self) -> dict:
        return self.state()["autonomy"]

    def test_new_project_is_supervised_and_not_migrated(self) -> None:
        a = self.auto()
        self.assertEqual(a["presence"]["step"], "supervised")
        self.assertNotIn("migrated", a["presence"])
        self.assertNotIn("New: presence steps", self.run_state("status").stdout)
        self.assertFalse((self.root / ".dev" / "decisions.md").exists()
                         and "presence" in (self.root / ".dev" / "decisions.md").read_text(encoding="utf-8").lower())

    def test_assisted_decides_operational_points_and_asks_the_rest(self) -> None:
        self.run_state("set", "autonomy.presence", "assisted")
        e = effective(self.auto())
        self.assertEqual(e["dirty_tree"]["action"], "auto_recommend")
        self.assertEqual(e["rounds_exhausted"]["action"], "auto_recommend")
        self.assertEqual(e["ci_timeout"]["action"], "park")
        self.assertEqual(e["blocked_env"]["action"], "park")
        self.assertEqual(e["model_escalation"], "preapproved")
        for p in PRODUCT_EXTERNAL:
            self.assertEqual(e[p]["action"], "ask", p)

    def test_milestone_parks_product_and_external_points(self) -> None:
        self.run_state("set", "autonomy.presence", "milestone")
        e = effective(self.auto())
        for p in PRODUCT_EXTERNAL:
            self.assertEqual(e[p]["action"], "park", p)
        self.assertEqual(e["dirty_tree"]["action"], "auto_recommend")

    def test_unattended_step_equals_the_old_preset(self) -> None:
        self.run_state("set", "autonomy.presence", "unattended")
        self.assertEqual(self.auto()["pause_policy"], ds.UNATTENDED_PAUSE_POLICY)
        self.assertEqual(self.auto()["model_policy"]["mode"], "preapproved")

    def test_level_unattended_is_an_alias(self) -> None:
        self.run_state("set", "autonomy.level", "unattended")
        a = self.auto()
        self.assertEqual(a["level"], "high")
        self.assertEqual(a["presence"]["step"], "unattended")
        self.run_state("set", "autonomy.level", "cautious")  # a level leaves the step as it is
        self.assertEqual(self.auto()["presence"]["step"], "unattended")
        self.run_state("set", "autonomy.presence", "supervised")
        self.assertEqual(effective(self.auto())["paid_services"]["action"], "ask")
        self.assertEqual(self.auto()["model_policy"]["mode"], "ask")

    def test_exceptions_win_and_survive_a_change_of_step(self) -> None:
        self.run_state("set", "autonomy.presence", "milestone")
        self.run_state("set", "autonomy.pause_policy.security_model_change", "ask")
        self.run_state("set", "autonomy.model_policy.mode", "off")
        a = self.auto()
        self.assertEqual(a["presence"]["overrides"]["security_model_change"], {"action": "ask"})
        self.assertEqual(a["model_policy"]["mode"], "off")
        self.run_state("set", "autonomy.presence", "unattended")
        a = self.auto()
        self.assertEqual(a["pause_policy"]["security_model_change"]["action"], "ask")
        self.assertEqual(a["model_policy"]["mode"], "off")
        self.run_state("set", "autonomy.pause_policy.security_model_change", "default")
        self.assertEqual(self.auto()["pause_policy"]["security_model_change"]["action"], "auto_recommend")
        self.run_state("set", "autonomy.presence.overrides", "{}")
        self.assertEqual(self.auto()["presence"]["overrides"], {})
        self.assertEqual(self.auto()["model_policy"]["mode"], "preapproved")

    def test_setting_the_step_value_is_not_an_exception(self) -> None:
        self.run_state("set", "autonomy.presence", "assisted")
        self.run_state("set", "autonomy.pause_policy.dirty_tree", "auto_recommend")
        self.assertEqual(self.auto()["presence"]["overrides"], {})

    def test_floors_still_hold_in_exceptions(self) -> None:
        self.run_state("set", "autonomy.pause_policy.scope_change_major", "auto_recommend", expect=1)
        self.run_state("set", "autonomy.presence.overrides", json.dumps({"credentials": {"action": "auto_recommend"}}), expect=1)
        self.run_state("set", "autonomy.presence", "reckless", expect=1)

    def test_interview_json_with_presence_and_exception(self) -> None:
        self.run_state("init", "--autonomy-json", json.dumps({
            "presence": "milestone", "pause_policy": {"paid_services": {"action": "preauthorize",
                                                                         "limit": {"max_monthly": 20, "currency": "USD"}}}}))
        a = self.auto()
        self.assertEqual(a["presence"]["step"], "milestone")
        self.assertEqual(a["pause_policy"]["paid_services"]["limit"]["max_monthly"], 20)
        self.assertEqual(a["pause_policy"]["credentials"]["action"], "park")
        self.assertIn("Presence: milestone", self.run_state("status").stdout)


class TestBrownfield(Base):
    def test_dirty_tree_stays_ask_at_every_step_unless_an_exception(self) -> None:
        self.run_state("init", "--brownfield-json", BF)
        for step in ds.PRESENCE_STEPS:
            self.run_state("set", "autonomy.presence", step)
            self.assertEqual(self.state()["autonomy"]["pause_policy"]["dirty_tree"]["action"], "ask", step)
        self.run_state("set", "autonomy.pause_policy.dirty_tree", "auto_recommend")
        self.assertEqual(self.state()["autonomy"]["pause_policy"]["dirty_tree"]["action"], "auto_recommend")


class TestMigration(Base):
    """A 3.16 state (no presence) loaded by 3.17 keeps every action; one fixture per old level, plus custom ones."""

    def write_old(self, auto_patch: dict, brownfield: bool = False) -> dict:
        self.run_state("init", *(["--brownfield-json", BF] if brownfield else []))
        p = self.root / ".dev" / "state.json"
        s = json.loads(p.read_text(encoding="utf-8"))
        auto = s["autonomy"]
        auto.pop("presence", None)
        auto["pause_policy"] = {}
        auto["model_policy"]["mode"] = "ask"
        if brownfield:
            auto["pause_policy"]["dirty_tree"] = {"action": "ask"}
        auto.update(json.loads(json.dumps(auto_patch)))
        p.write_text(json.dumps(s, indent=2), encoding="utf-8")
        return effective(auto)

    def migrate_and_check(self, before: dict) -> dict:
        self.run_state("set", "language", "en")  # any command that saves writes the migration
        a = self.state()["autonomy"]
        self.assertEqual(effective(a), before)
        return a

    def test_each_old_level_keeps_every_action(self) -> None:
        for level in ("high", "balanced", "cautious"):
            with self.subTest(level=level):
                a = self.migrate_and_check(self.write_old({"level": level}))
                self.assertEqual(a["presence"]["step"], "supervised")
                self.assertEqual(a["presence"]["overrides"], {})
                self.assertEqual(a["level"], level)

    def test_unattended_becomes_high_plus_step(self) -> None:
        before = self.write_old({"level": "unattended", "pause_policy": ds.UNATTENDED_PAUSE_POLICY,
                                 "model_policy": {"mode": "preapproved", "tiers": {}}})
        a = self.migrate_and_check(before)
        self.assertEqual(a["level"], "high")
        self.assertEqual(a["presence"]["step"], "unattended")
        self.assertEqual(a["presence"]["overrides"], {})
        self.assertEqual(a["presence"]["migrated"]["from_level"], "unattended")

    def test_custom_points_become_exceptions(self) -> None:
        pp = {**ds.UNATTENDED_PAUSE_POLICY, "public_exposure": {"action": "ask"}}
        pp.pop("ci_timeout")  # missing meant ask
        before = self.write_old({"level": "unattended", "pause_policy": pp,
                                 "model_policy": {"mode": "off", "tiers": {}}})
        a = self.migrate_and_check(before)
        self.assertEqual(set(a["presence"]["overrides"]), {"public_exposure", "ci_timeout", "model_escalation"})
        before = self.write_old({"level": "high", "pause_policy": {"security_model_change": {"action": "park"}}})
        a = self.migrate_and_check(before)
        self.assertEqual(a["presence"]["overrides"], {"security_model_change": {"action": "park"}})

    def test_brownfield_unattended(self) -> None:
        pp = {**ds.UNATTENDED_PAUSE_POLICY, "dirty_tree": {"action": "ask"}}
        before = self.write_old({"level": "unattended", "pause_policy": pp,
                                 "model_policy": {"mode": "preapproved", "tiers": {}}}, brownfield=True)
        a = self.migrate_and_check(before)
        self.assertEqual(a["presence"]["overrides"], {})

    def test_backup_adr_and_notice(self) -> None:
        self.write_old({"level": "unattended", "pause_policy": ds.UNATTENDED_PAUSE_POLICY,
                        "model_policy": {"mode": "preapproved", "tiers": {}}})
        self.assertIn("New: presence steps", self.run_state("status", "--short").stdout)
        self.run_state("set", "language", "en")
        self.assertTrue(list((self.root / ".dev" / "backup").glob("state-pre-presence-*.json")))
        dec = (self.root / ".dev" / "decisions.md").read_text(encoding="utf-8")
        self.assertEqual(dec.count("Autonomy presence steps"), 1)
        self.run_state("set", "language", "pt-BR")  # the ADR is written once
        self.assertEqual((self.root / ".dev" / "decisions.md").read_text(encoding="utf-8").count("Autonomy presence steps"), 1)
        self.assertIn("New: presence steps", self.run_state("status").stdout)
        self.run_state("set", "autonomy.presence", "milestone")  # choosing a step ends the notice
        self.assertNotIn("New: presence steps", self.run_state("status").stdout)


if __name__ == "__main__":
    unittest.main()
