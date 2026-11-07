from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_russian_patch import build_patch, russian_files
from clausewitz import load
from validate_mod import LOC


def entries(path: Path) -> dict[str, str]:
    return dict(match.groups() for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]
                if (match := LOC.fullmatch(line)))


def language(language: str) -> dict[str, str]:
    result = {}
    for path in sorted((ROOT / "localisation").rglob(f"*_l_{language}.yml")):
        result.update(entries(path))
    return result


class RussianLocalisationTests(unittest.TestCase):
    def test_all_english_keys_have_a_russian_counterpart_including_replace(self):
        english, russian = language("english"), language("russian")
        self.assertGreaterEqual(len(english), 950)
        self.assertEqual(sorted(english.keys() - russian.keys()), [])
        self.assertEqual(russian["STATE_104"], "Центральная Босния")
        self.assertIn("Демократическая", russian["SER_democratic_party_long"])

    def test_all_russian_files_have_bom_header_valid_entries_and_unique_keys(self):
        files = russian_files()
        self.assertGreaterEqual(len(files), 7)
        for path in files:
            with self.subTest(path=path.relative_to(ROOT)):
                raw = path.read_bytes()
                self.assertTrue(raw.startswith(b"\xef\xbb\xbfl_russian:\n"))
                self.assertTrue(entries(path))

    def test_serbian_focuses_have_real_russian_names_and_descriptions(self):
        russian = entries(ROOT / "localisation/russian/reworkl_serbia_l_russian.yml")
        names = [key for key in russian if key.startswith("old_world_serbia_") and not key.endswith("_desc")]
        self.assertEqual(len(names), 131)
        self.assertEqual(sum(key.endswith("_desc") for key in russian if key.startswith("old_world_serbia_")), 131)
        for key in names:
            with self.subTest(key=key):
                self.assertRegex(russian[key], "[А-Яа-яЁё]")
                description = russian[key + "_desc"]
                self.assertRegex(description, "[А-Яа-яЁё]")
                self.assertGreater(len(description), 35)
                self.assertNotIn("Describe", description)
                self.assertNotIn("Опишите", description)

    def test_serbian_ideas_characters_countries_events_and_music_are_not_english(self):
        for filename in ("reworkl_serbia_l_russian.yml", "reworkl_music_l_russian.yml"):
            for key, value in entries(ROOT / "localisation/russian" / filename).items():
                with self.subTest(key=key):
                    self.assertRegex(value, "[А-Яа-яЁё]")
                    # A mod brand and the king's Roman numeral are not missing
                    # translations. All other display words should be Cyrillic.
                    visible = re.sub(r"Reworkl|\bII\b", "", value)
                    self.assertNotRegex(visible, "[A-Za-z]{2,}")
                    self.assertNotIn("Describe this", value)
        russian = language("russian")
        self.assertNotEqual(russian["conquermont.1.a"], "Option 1")
        self.assertNotEqual(russian["conquermont.1.b"], "Option 2")

    def test_music_retains_all_23_original_track_keys(self):
        english = entries(ROOT / "localisation/english/reworkl_music_l_english.yml")
        russian = entries(ROOT / "localisation/russian/reworkl_music_l_russian.yml")
        self.assertEqual(english.keys(), russian.keys())
        self.assertEqual(len(russian), 24)  # one station + 23 tracks

    def test_translation_preserves_every_original_serbian_key_and_engine_token(self):
        english = {}
        for path in sorted((ROOT / "localisation/english").glob("zzzz_hmb_old_world_*_l_english.yml")):
            english.update(entries(path))
        russian = entries(ROOT / "localisation/russian/reworkl_serbia_l_russian.yml")
        self.assertEqual(len(english), 403)
        self.assertEqual(english.keys() - russian.keys(), set())
        tokens = re.compile(r"\$[^$]+\$|\[[^\]]+\]|§.|\\[ntr]")
        for key, value in english.items():
            with self.subTest(key=key):
                self.assertEqual(Counter(tokens.findall(value)), Counter(tokens.findall(russian[key])))

    def test_scripted_party_names_are_localised_without_changing_the_focus_script(self):
        russian = language("russian")
        focus = load(ROOT / "common/national_focus/serbia_tree1.txt")
        names = {node.scalar(field) for node in focus.walk() if node.key == "set_party_name"
                 for field in ("name", "long_name") if node.scalar(field)}
        self.assertEqual(names, {"Slavic_Barbarians", "Sandzak_Communists"})
        for key in names:
            self.assertIn(key, russian)
            self.assertRegex(russian[key], "[А-Яа-яЁё]")
        # Research bonuses have their own visible names in focus rewards.
        # Supply them explicitly instead of relying on vanilla/DLC fallback.
        bonuses = {node.scalar("name") for node in focus.walk() if node.key == "add_tech_bonus"}
        self.assertEqual(bonuses, {"infantry_bonus", "armour_bonus", "artillery_bonus"})
        for key in bonuses:
            self.assertIn(key, russian)
            self.assertRegex(russian[key], "[А-Яа-яЁё]")

    def test_small_patch_contains_only_exact_russian_source_bytes_and_guide(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "russian.zip"
            count = build_patch(output)
            self.assertLess(output.stat().st_size, 256 * 1024)
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                expected = {path.relative_to(ROOT).as_posix() for path in russian_files()}
                self.assertEqual(set(archive.namelist()), expected | {"INSTALL_RUSSIAN.txt"})
                self.assertEqual(len(archive.namelist()), count + 1)
                self.assertTrue(archive.read("INSTALL_RUSSIAN.txt").startswith(b"\xef\xbb\xbf"))
                for name in expected:
                    self.assertEqual(archive.read(name), (ROOT / name).read_bytes())
                    self.assertTrue(name.startswith("localisation/"))
                    self.assertTrue(name.endswith("_l_russian.yml"))
                    self.assertNotIn("..", Path(name).parts)

    def test_patch_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "first.zip", Path(temp) / "second.zip"
            build_patch(first)
            build_patch(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_overlay_leaves_gameplay_launch_music_saves_and_other_languages_intact(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "working-mod"
            untouched = {
                "descriptor.mod": (ROOT / "descriptor.mod").read_bytes(),
                "common/national_focus/serbia_tree1.txt": (ROOT / "common/national_focus/serbia_tree1.txt").read_bytes(),
                "localisation/english/keep_l_english.yml": b'\xef\xbb\xbfl_english:\n EXISTING:0 "Keep"\n',
                "music/keep.ogg": b"existing music",
                "2_LAUNCH.bat": b"existing launch helper",
                "save games/keep.hoi4": b"existing save",
                "dlc_load.json": b'{"enabled_mods":["mod/reworkl.mod"]}',
                "userdir.txt": b"existing user data path",
            }
            for name, data in untouched.items():
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            output = Path(temp) / "patch.zip"
            build_patch(output)
            with zipfile.ZipFile(output) as archive:
                archive.extractall(target)
            for name, data in untouched.items():
                self.assertEqual((target / name).read_bytes(), data, name)
            for path in russian_files():
                self.assertEqual((target / path.relative_to(ROOT)).read_bytes(), path.read_bytes())

    def test_invalid_russian_file_does_not_replace_a_previous_good_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            path = root / "localisation/russian/example_l_russian.yml"
            path.parent.mkdir(parents=True)
            path.write_text('l_russian:\n EXAMPLE:0 "Русский текст"\n', encoding="utf-8")
            output = Path(temp) / "patch.zip"
            output.write_bytes(b"previous good download")
            with self.assertRaisesRegex(ValueError, "BOM"):
                build_patch(output, root)
            self.assertEqual(output.read_bytes(), b"previous good download")

    def test_same_language_duplicate_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder in ("russian", "replace"):
                path = root / "localisation" / folder / "example_l_russian.yml"
                path.parent.mkdir(parents=True)
                path.write_text('l_russian:\n EXAMPLE:0 "Текст"\n', encoding="utf-8-sig")
            with self.assertRaisesRegex(ValueError, "Duplicate Russian key"):
                russian_files(root)


if __name__ == "__main__":
    unittest.main()
