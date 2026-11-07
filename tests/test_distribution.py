from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_mod import BAT_HELPERS, RELEASE_HELPERS, SHARED_HELPERS, helper_path, build, build_toolkit, launcher_descriptor, source_files
from clausewitz import load
from install import install
from validate_mod import ROOT, validate


class DistributionTests(unittest.TestCase):
    def test_launcher_has_path_but_internal_descriptor_does_not(self):
        self.assertIn('path="mod/reworkl"', launcher_descriptor())
        self.assertFalse(load(ROOT / 'descriptor.mod').children('path'))
        self.assertNotIn("remote_file_id", launcher_descriptor())

    def test_allowlist_excludes_original_archives_git_and_scratch(self):
        files = [p.relative_to(ROOT).as_posix() for p in source_files()]
        self.assertIn("music/reworkl_turbofolk/Remove_Kebab.ogg", files)
        self.assertFalse(any(p.startswith((".git/", ".work/", "scripts/", "releases/")) for p in files))
        self.assertFalse(any(p.endswith((".zip", ".z01", ".z02")) for p in files))

    def test_installer_installs_all_assets_with_absolute_launcher_path(self):
        with tempfile.TemporaryDirectory() as temp:
            target, backup = install(Path(temp))
            self.assertIsNone(backup)
            self.assertTrue((target / "music/reworkl_turbofolk/armia.ogg").is_file())
            self.assertEqual(validate(target).errors, [])
            external = target.parent / "reworkl.mod"
            self.assertIn(f'path="{target.as_posix()}"', external.read_text())

    def test_update_backs_up_previous_files_without_touching_saves(self):
        with tempfile.TemporaryDirectory() as temp:
            user_dir = Path(temp)
            old = user_dir / "mod/reworkl"
            old.mkdir(parents=True)
            (old / "old-marker.txt").write_text("old content")
            descriptor = user_dir / "mod/reworkl.mod"
            descriptor.write_text("old descriptor")
            save = user_dir / "save games/campaign.hoi4"
            save.parent.mkdir()
            save.write_bytes(b"existing save")
            target, backup = install(user_dir)
            self.assertIsNotNone(backup)
            self.assertEqual((backup / "reworkl/old-marker.txt").read_text(), "old content")
            self.assertEqual((backup / "reworkl.mod").read_text(), "old descriptor")
            self.assertFalse((target / "old-marker.txt").exists())
            self.assertEqual(save.read_bytes(), b"existing save")

    def test_failed_final_move_restores_previous_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            user_dir = Path(temp)
            old = user_dir / "mod/reworkl"
            old.mkdir(parents=True)
            (old / "marker.txt").write_text("keep me")
            descriptor = user_dir / "mod/reworkl.mod"
            descriptor.write_text("keep descriptor")
            with patch("install.Path.replace", side_effect=OSError("simulated final move failure")):
                with self.assertRaises(OSError):
                    install(user_dir)
            self.assertEqual((old / "marker.txt").read_text(), "keep me")
            self.assertEqual(descriptor.read_text(), "keep descriptor")

    def test_small_activation_toolkit_contains_only_scripts_and_instructions(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'activation-tools.zip'
            build_toolkit(output)
            self.assertLess(output.stat().st_size, 64 * 1024)
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), set(RELEASE_HELPERS) | set(SHARED_HELPERS) | {'ACTIVATION_RU.txt'})

    def test_ready_zip_is_complete_and_valid_after_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "release.zip"
            count = build(out)
            with zipfile.ZipFile(out) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(len(archive.namelist()), count + 2 + len(RELEASE_HELPERS) + len(BAT_HELPERS))
                self.assertIn("reworkl.mod", archive.namelist())
                self.assertIn("INSTALL_RU.md", archive.namelist())
                for helper in RELEASE_HELPERS:
                    self.assertIn(helper, archive.namelist())
                    self.assertFalse(any(n.startswith("reworkl/") and n.endswith(helper) for n in archive.namelist()))
                for helper in BAT_HELPERS:
                    self.assertIn(helper, archive.namelist())
                    self.assertEqual(archive.read(helper), helper_path(helper).read_bytes())
                self.assertTrue(archive.read("Reworkl-Bat.ps1").startswith(b"\xef\xbb\xbf"))
                self.assertTrue(archive.read("Install-Reworkl.ps1").startswith(b"\xef\xbb\xbf"))
                for name in ("belgrade", "mountains", "headquarters"):
                    self.assertIn(f"reworkl/gfx/loadingscreens/reworkl_{name}.dds", archive.namelist())
                self.assertFalse(any("load_serbia_" in p for p in archive.namelist()))
                self.assertFalse(any("3832310762" in p for p in archive.namelist()))
                archive.extractall(Path(temp) / "unpacked")
            self.assertEqual(validate(Path(temp) / "unpacked/reworkl").errors, [])


if __name__ == "__main__":
    unittest.main()
