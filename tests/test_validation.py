from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_mod import copy_payload
from validate_mod import ROOT, validate


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        copy_payload(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @contextmanager
    def mutate(self, relative, old, new):
        path = self.root / relative
        original = path.read_bytes()
        before = original.decode("utf-8-sig")
        self.assertIn(old, before)
        bom = original.startswith(b"\xef\xbb\xbf")
        path.write_text(before.replace(old, new, 1), encoding="utf-8-sig" if bom else "utf-8")
        try:
            yield
        finally:
            path.write_bytes(original)

    def assert_error(self, fragment):
        self.assertTrue(any(fragment in error for error in validate(self.root).errors), fragment)

    def test_repository_passes(self):
        report = validate(ROOT)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.counts["music_tracks"], 23)
        self.assertEqual(report.counts["focuses"], 198)

    def test_loading_screens_are_registered_and_have_dds_payloads(self):
        self.assertEqual(validate(self.root).counts["loading_screens"], 3)

    def test_loading_screen_replace_path_is_required(self):
        with self.mutate("descriptor.mod", 'replace_path="gfx/loadingscreens"', '# no loading replacement'):
            self.assert_error("Loading screens need replace_path")

    def test_world_country_history_isolation_is_required(self):
        with self.mutate("descriptor.mod", 'replace_path="history/countries"', '# removed country history isolation'):
            self.assert_error("2026 geography requires replace_path=history/countries")

    def test_canonical_1939_scenario_shadow_cannot_add_a_vanilla_bookmark(self):
        path = self.root / "common/bookmarks/blitzkrieg.txt"
        original = path.read_bytes()
        try:
            path.write_text('bookmarks = { bookmark = { date = 1939.8.14.12 } }')
            self.assert_error("Vanilla bookmark shadow must not add a third campaign")
        finally:
            path.write_bytes(original)

    def test_truncated_loading_texture_is_detected(self):
        path = self.root / "gfx/loadingscreens/reworkl_belgrade.dds"
        original = path.read_bytes()
        try:
            path.write_bytes(original[:128])
            self.assert_error("truncated or unexpected DDS payload size")
        finally:
            path.write_bytes(original)

    def test_invalid_loading_texture_header_is_detected(self):
        path = self.root / "gfx/loadingscreens/reworkl_belgrade.dds"
        original = path.read_bytes()
        try:
            path.write_bytes(b"PNG " + original[4:])
            self.assert_error("invalid DDS header")
        finally:
            path.write_bytes(original)

    def test_wrong_loading_texture_dimensions_are_detected(self):
        import struct
        path = self.root / "gfx/loadingscreens/reworkl_belgrade.dds"
        original = path.read_bytes()
        changed = bytearray(original)
        struct.pack_into("<I", changed, 16, 640)
        try:
            path.write_bytes(changed)
            self.assert_error("expected 1920x1080")
        finally:
            path.write_bytes(original)

    def test_loading_placeholder_regression_is_detected(self):
        path = self.root / "gfx/loadingscreens/load_serbia_01.png"
        try:
            path.write_bytes(b"old placeholder")
            self.assert_error("no PNG placeholders")
        finally:
            path.unlink()

    def test_loading_tip_localisation_is_required(self):
        with self.mutate("localisation/replace/reworkl_loading_l_russian.yml", "LOADING_TIP_9", "UNUSED_LOADING_TIP_9"):
            self.assert_error("Missing russian localisation: LOADING_TIP_9")

    def test_filename_case_regression_is_detected(self):
        with self.mutate("music/reworkl_turbofolk/reworkl_turbofolk_music.asset", "Remove_Kebab.ogg", "Remove_kebab.ogg"):
            self.assert_error("missing audio")

    def test_missing_playlist_song_is_detected(self):
        with self.mutate("music/reworkl_turbofolk/reworkl_turbofolk_songs.txt", 'song = "reworkl_armia"', 'song = "missing_song"'):
            self.assert_error("playlist and assets disagree")

    def test_character_case_regression_is_detected(self):
        with self.mutate("common/national_focus/serbia_tree1.txt", "promote_character = Pagangod", "promote_character = pagangod"):
            self.assert_error("missing character pagangod")

    def test_missing_focus_prerequisite_is_detected(self):
        with self.mutate("common/national_focus/serbia_tree1.txt", "focus = old_world_serbia_tree1_focus_86_3", "focus = missing_prerequisite"):
            self.assert_error("unknown focus reference missing_prerequisite")

    def test_foreign_oob_location_is_detected(self):
        with self.mutate("history/units/SER_2026.txt", "location = 11586", "location = 6380"):
            self.assert_error("starts in SOV, not SER")

    def test_old_exists_tag_bug_is_detected(self):
        with self.mutate("events/Y89_automatic_dissolution.txt", "country_exists = SLV", "exists = SLV"):
            self.assert_error("exists takes yes/no")

    def test_missing_namespace_is_detected(self):
        with self.mutate("events/Y89_automatic_dissolution.txt", "add_namespace = Y89_breakup", "# no namespace"):
            self.assert_error("missing event namespace")

    def test_global_serbian_default_is_detected(self):
        with self.mutate("common/national_focus/serbia_tree1.txt", "default = no", "default = yes"):
            self.assert_error("must not be the default tree")

    def test_invalid_factory_effect_is_detected(self):
        with self.mutate("common/national_focus/serbia_tree1.txt", "add_building_construction", "add_buildings"):
            self.assert_error("invalid effect add_buildings")

    def test_duplicate_localisation_is_detected(self):
        with self.mutate("localisation/english/reworkl_music_l_english.yml", 'l_english:', 'l_english:\n reworkl_armia:0 "Duplicate"'):
            self.assert_error("duplicate localisation key reworkl_armia")

    def test_missing_bom_is_detected(self):
        path = self.root / "localisation/russian/reworkl_music_l_russian.yml"
        original = path.read_bytes()
        try:
            path.write_bytes(original[3:])
            self.assert_error("UTF-8 BOM")
        finally:
            path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
