"""Read and replay real startup scripts; this model is NOT the HOI4 engine."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from clausewitz import load
from scenario_harness import CalendarModel


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modern = CalendarModel("2026.1.1")
        cls.serbia = CalendarModel("1936.1.1")

    def test_2026_replaces_1989_and_serbia_1936_stays_separate(self):
        bookmarks = load(ROOT / "common/bookmarks/Y89_bookmarks.txt").children("bookmarks")[0].children("bookmark")
        self.assertEqual({b.scalar("date") for b in bookmarks}, {"2026.1.1.12", "1936.1.1.12"})
        main = next(b for b in bookmarks if b.scalar("default") == "yes")
        self.assertEqual(main.scalar("date"), "2026.1.1.12")
        self.assertEqual(main.scalar("default_country"), "SER")

    def test_ownership_is_ready_before_startup_not_a_date_label_or_late_annexation(self):
        model = deepcopy(self.modern)
        self.assertEqual(len(model.owners), 1255)
        self.assertEqual(len(set(model.owners.values())), 198)
        self.assertNotIn("YUG", model.owners.values())
        before = dict(model.owners)
        model.startup()
        self.assertEqual(model.owners, before)
        self.assertFalse(model.releases)

    def test_all_seven_balkan_countries_start_independently(self):
        for sid, tag in {131: "SER", 133: "KOS", 134: "MNT", 136: "MAC", 128: "BOS", 126: "CRO", 124: "SLV"}.items():
            self.assertEqual(self.modern.owners[str(sid)], tag)

    def test_world_tree_is_assigned_to_all_existing_countries(self):
        model = deepcopy(self.modern)
        model.startup()
        self.assertEqual(set(model.trees), set(model.owners.values()))
        self.assertEqual(set(model.trees.values()), {"rw26_world_tree"})
        self.assertIn("RW26_WORLD_INITIALIZED", model.globals)
        self.assertNotIn("REWORKL_1989_INITIALIZED", model.globals)

    def test_startup_is_idempotent_and_does_not_duplicate_armies_or_factions(self):
        model = deepcopy(self.modern)
        before = dict(model.armies)
        model.startup()
        model.startup()
        model.startup()
        self.assertEqual(dict(model.armies), before)
        self.assertEqual(model.faction_creations["USA"], 1)
        self.assertEqual(len(model.factions["USA"]), 32)
        self.assertIn("FIN", model.factions["USA"])
        self.assertIn("SWE", model.factions["USA"])
        self.assertNotIn("SER", model.factions["USA"])

    def test_reload_keeps_player_borders_and_focus_progress(self):
        model = deepcopy(self.modern)
        model.startup()
        model.owners["133"] = "SER"  # A player's later territorial change.
        model.focuses["SER"].add("RW26_economy")
        model.trees["SER"] = "player_selected_tree"
        restored = deepcopy(model)
        restored.daily("2031.6.1")
        restored.startup()
        self.assertEqual(restored.owners, model.owners)
        self.assertEqual(restored.focuses, model.focuses)
        self.assertEqual(restored.trees, model.trees)
        self.assertEqual(restored.faction_creations["USA"], 1)

    def test_no_1989_breakup_calendar_runs_in_2026(self):
        model = deepcopy(self.modern)
        before = dict(model.owners)
        model.startup()
        for date in ("2026.1.2", "2026.6.25", "2027.1.1", "2036.9.8", "2050.2.17"):
            model.daily(date)
        self.assertEqual(model.owners, before)
        self.assertFalse(model.releases)
        self.assertFalse(model.fired)

    def test_legacy_console_breakup_event_cannot_change_modern_borders(self):
        model = deepcopy(self.modern)
        before = dict(model.owners)
        for event in [e for e in model.events if e.startswith("Y89_breakup.")]:
            model.fire(event, "YUG", force=True)
        self.assertEqual(model.owners, before)
        self.assertFalse(model.releases)

    def test_serbia_1936_keeps_its_authored_tree_and_army(self):
        model = deepcopy(self.serbia)
        self.assertEqual(model.armies["SER"], 6)
        model.startup()
        self.assertEqual(model.trees["SER"], "serbia_tree1")
        self.assertIn("REWORKL_SERBIA_INITIALIZED", model.globals)
        self.assertNotIn("RW26_WORLD_INITIALIZED", model.globals)
        self.assertFalse(model.faction_creations)
        model.focuses["SER"].add("old_world_serbia_tree1_focus_86_3")
        model.startup()
        self.assertIn("old_world_serbia_tree1_focus_86_3", model.focuses["SER"])
        self.assertEqual(model.armies["SER"], 6)

    def test_1936_also_has_no_forced_1989_calendar(self):
        model = deepcopy(self.serbia)
        before = dict(model.owners)
        model.startup()
        model.daily("1991.6.25")
        self.assertEqual(model.owners, before)
        self.assertFalse(model.releases)

    def test_serbian_geographic_focus_references_are_migrated(self):
        text = (ROOT / "common/national_focus/serbia_tree1.txt").read_text()
        self.assertIn("controls_state = 133", text)  # Kosovo, not the Philippines.
        self.assertIn("add_state_core = 134", text)  # Montenegro, not Oman.
        self.assertIn("add_state_core = 129", text)
        self.assertIn("add_state_core = 1054", text)
        self.assertNotIn("controls_state = 802", text)
        self.assertNotIn("add_state_core = 1083", text)

    def test_1936_army_no_longer_uses_reassigned_syrian_province_797(self):
        text = (ROOT / "history/units/SER_1936.txt").read_text()
        self.assertNotIn("location = 797", text)
        self.assertIn("location = 11586", text)


if __name__ == "__main__":
    unittest.main()
