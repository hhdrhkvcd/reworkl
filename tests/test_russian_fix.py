"""RU2 packaging and real, explicitly optional PowerShell updater tests.

No game execution and no writes outside isolated fixtures. Windows CI exercises
both PowerShell 5.1 and 7; a parser/static check is not a substitute for runtime.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_russian_fix import ENGLISH_COMPAT, FIX_HELPERS, FIX_REVISION, build_fix, fix_payload
from build_russian_patch import russian_files
from validate_mod import LOC

POWERSHELL = os.environ.get("REWORKL_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")


def powershell_env():
    import os
    env = os.environ.copy()
    if Path(POWERSHELL).name.lower() in ('powershell', 'powershell.exe'):
        env.pop('PSModulePath', None)
    return env


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def parse_loc(data):
    return dict(match.groups() for line in data.decode("utf-8-sig").splitlines()[1:]
                if (match := LOC.fullmatch(line)))


class RussianFixPackagingTests(unittest.TestCase):
    def test_english_layer_mirrors_all_russian_display_values_and_engine_tokens(self):
        payload = fix_payload()
        russian = {}
        for path in russian_files(include_world=False):
            russian.update(parse_loc(path.read_bytes()))
        english = parse_loc(payload[ENGLISH_COMPAT])
        self.assertEqual(english, russian)
        self.assertGreaterEqual(len(english), 700)
        self.assertTrue(payload[ENGLISH_COMPAT].startswith(b"\xef\xbb\xbfl_english:\r\n"))
        self.assertEqual(english["old_world_serbia_tree1_focus_2"], "Премии рабочим")
        for menu_key in ("FE_NEW", "FE_LOAD", "FE_OPTIONS", "NEW_GAME", "LOAD_GAME", "OPTIONS"):
            self.assertNotIn(menu_key, english)

    def test_package_manifest_hashes_and_only_locale_payload_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "ru2.zip"
            self.assertEqual(build_fix(output), 8)
            self.assertLess(output.stat().st_size, 256 * 1024)
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(len(archive.namelist()), 12)
                manifest = json.loads(archive.read("russian-manifest.json"))
                self.assertEqual(manifest["revision"], FIX_REVISION)
                self.assertFalse(manifest["base_game_menu_changed"])
                paths = {item["path"] for item in manifest["files"]}
                self.assertEqual(paths, set(fix_payload()))
                self.assertEqual(set(archive.namelist()), paths | set(FIX_HELPERS) | {"russian-manifest.json", "START_RUSSIAN_RU2.txt"})
                for item in manifest["files"]:
                    raw = archive.read(item["path"])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
                    self.assertEqual(len(raw), item["size_bytes"])
                    self.assertTrue(item["path"].startswith("localisation/"))
                    self.assertNotIn("..", Path(item["path"]).parts)
                    self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
                for name in FIX_HELPERS:
                    self.assertEqual(archive.read(name), (ROOT / "installer/russian" / name).read_bytes())

    def test_build_is_deterministic_and_does_not_change_normal_english_or_launch_files(self):
        protected = [*ROOT.glob("localisation/english/*.yml"), *ROOT.glob("installer/bat/*"), ROOT / "descriptor.mod"]
        protected.append(ROOT / ENGLISH_COMPAT)
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "first.zip", Path(temp) / "second.zip"
            build_fix(first)
            build_fix(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(before, {path: path.read_bytes() for path in protected})
        self.assertTrue((ROOT / ENGLISH_COMPAT).is_file())  # world edition intentionally ships full compatibility

    def test_updater_encoding_exit_code_and_scope_guards(self):
        wrapper = (ROOT / "installer/russian/APPLY_RUSSIAN.bat").read_bytes()
        self.assertTrue(wrapper.isascii())
        self.assertNotIn(b"\n", wrapper.replace(b"\r\n", b""))
        self.assertIn(b"DisableDelayedExpansion", wrapper)
        self.assertIn(b'exit /b %RESULT%', wrapper)
        raw = (ROOT / "installer/russian/Reworkl-Russian.ps1").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        for path in fix_payload():
            self.assertIn("'" + path + "'", text)
        for forbidden in ("Start-Process", "Stop-Process", "Invoke-Expression", "-Recurse", "DownloadString", "Write-Atomic"):
            self.assertNotIn(forbidden, text)
        self.assertIn(FIX_REVISION, text)
        self.assertIn("$ReadOnly", text)
        self.assertIn("Ru-PlainPath", text)
        self.assertIn("[ROLLBACK]", text)
        self.assertIn("[ENGINE_TEST] NOT_PERFORMED", text)

    def test_invalid_source_keeps_previous_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            source = root / "localisation/russian/broken_l_russian.yml"
            source.parent.mkdir(parents=True)
            source.write_text('l_russian:\n TEST:0 "Текст"\n', encoding="utf-8")
            output = Path(temp) / "good.zip"
            output.write_bytes(b"previous good archive")
            with self.assertRaisesRegex(ValueError, "BOM"):
                build_fix(output, root)
            self.assertEqual(output.read_bytes(), b"previous good archive")


@unittest.skipUnless(POWERSHELL, "Real PowerShell runtime is not installed on this host")
class RussianFixRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.package = self.root / "RU папка O'Neil !"
        archive = self.root / "ru2.zip"
        build_fix(archive)
        with zipfile.ZipFile(archive) as package:
            package.extractall(self.package)
        self.base = self.root / "Public ASCII !"
        self.target = self.base / "reworkl"
        self.target.mkdir(parents=True)
        self.protected = {
            self.target / "descriptor.mod": 'name="Reworkl — fixture"\nversion="1.2.0"\n'.encode(),
            self.target / "common/bookmarks/Y89_bookmarks.txt": b"bookmarks fixture",
            self.target / "common/national_focus/serbia_tree1.txt": b"focus gameplay MUST NOT CHANGE",
            self.target / "music/keep.ogg": b"existing music",
            self.target / "localisation/english/keep_l_english.yml": b'\xef\xbb\xbfl_english:\n KEEP:0 "Keep English"\n',
            self.base / "reworkl-userdata/dlc_load.json": b'{"enabled_mods":["mod/reworkl.mod"]}',
            self.base / "reworkl-userdata/settings.txt": b'language="l_english"\n',
            self.base / "reworkl-userdata/save games/keep.hoi4": b"existing save",
            self.root / "Game/userdir.txt": b"working pointer",
            self.root / "Game/launcher-settings.json": b'{"gameDataPath":"keep"}',
            self.root / "Working helpers/Reworkl-Bat.ps1": b"working helper",
            self.root / "Working helpers/2_LAUNCH.bat": b"working launch BAT",
            self.base / "reworkl-bat-state.json": json.dumps({"schema": 1, "target": str(self.target), "user_dir": str(self.base / "reworkl-userdata")}).encode(),
        }
        for path, raw in self.protected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.old_locale = {}
        for index, name in enumerate(fix_payload()):
            if name == ENGLISH_COMPAT:
                continue
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = f"old untranslated localisation {index}\r\n".encode()
            path.write_bytes(raw)
            self.old_locale[path] = raw

    def tearDown(self):
        self.temporary.cleanup()

    def run_update(self, *, read_only=False, target=None, injected=""):
        driver = self.root / "driver.ps1"
        driver.write_text(
            "$ErrorActionPreference='Stop'\n"
            + f". {quote(self.package / 'Reworkl-Russian.ps1')} -LibraryOnly\n"
            + injected + "\n"
            + f"exit (Invoke-RussianUpdate {quote(self.package)} {quote(target or '')} {quote(self.base)} ${str(read_only).lower()})\n",
            encoding="utf-8-sig",
        )
        return subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(driver)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=powershell_env(), timeout=45)

    def assert_protected(self):
        for path, raw in self.protected.items():
            self.assertEqual(path.read_bytes(), raw, str(path))

    def test_apply_uses_installed_bat_target_preserves_gameplay_settings_and_saves(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name, raw in fix_payload().items():
            self.assertEqual((self.target / name).read_bytes(), raw)
        self.assert_protected()
        backups = list((self.base / "reworkl-russian-backups").iterdir())
        self.assertEqual(len(backups), 1)
        for path, raw in self.old_locale.items():
            self.assertEqual((backups[0] / "files" / path.relative_to(self.target)).read_bytes(), raw)
        report = (self.package / "REWORKL_RUSSIAN_REPORT.txt").read_text(encoding="utf-8-sig")
        self.assertIn("[RESULT] LOCALISATION_FILES_VERIFIED", report)
        self.assertIn("[BASE_GAME_MENU] Unchanged", report)

    def test_check_only_does_not_modify_localisation_or_create_backups(self):
        result = self.run_update(read_only=True)
        self.assertNotEqual(result.returncode, 0)
        for path, raw in self.old_locale.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertFalse((self.target / ENGLISH_COMPAT).exists())
        self.assertFalse((self.base / "reworkl-russian-backups").exists())
        self.assert_protected()

    def test_corrupt_package_is_rejected_before_writing_mod(self):
        path = self.package / ENGLISH_COMPAT
        path.write_bytes(path.read_bytes() + b"corruption")
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing/damaged package", result.stdout)
        for path, raw in self.old_locale.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertFalse((self.base / "reworkl-russian-backups").exists())
        self.assert_protected()

    def test_unknown_target_does_not_create_a_fake_install(self):
        target = self.root / "wrong folder"
        result = self.run_update(target=target)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())
        self.assert_protected()

    def test_copy_failure_rolls_back_including_the_new_english_compat_file(self):
        injection = """
$script:OriginalCopy = ${function:Ru-CopyFile}
$script:CopyCalls = 0
function Ru-CopyFile([string]$Source, [string]$Destination) {
    $script:CopyCalls++
    if ($script:CopyCalls -eq 4) { throw 'simulated copy failure' }
    & $script:OriginalCopy $Source $Destination
}
"""
        result = self.run_update(injected=injection)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[ROLLBACK]", result.stdout)
        for path, raw in self.old_locale.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertFalse((self.target / ENGLISH_COMPAT).exists())
        self.assert_protected()


if __name__ == "__main__":
    unittest.main()
