"""Run the real release installer when PowerShell is available (Windows CI).

No fake interpreter: these integration cases are explicitly skipped when the
host has no PowerShell. They never launch HOI4 or change the real user folder.
"""
from pathlib import Path
import os
import json
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'installer/Install-Reworkl.ps1'
POWERSHELL = os.environ.get('REWORKL_TEST_POWERSHELL') or shutil.which('pwsh') or shutil.which('powershell')


def powershell_env():
    import os
    env = os.environ.copy()
    if Path(POWERSHELL).name.lower() in ('powershell', 'powershell.exe'):
        env.pop('PSModulePath', None)
    return env


class ReleaseHelperPackagingTests(unittest.TestCase):
    def test_ps51_script_has_bom_and_cmd_files_use_crlf(self):
        self.assertTrue(SCRIPT.read_bytes().startswith(b'\xef\xbb\xbf'))
        for name in ('INSTALL_REWORKL.cmd', 'CHECK_REWORKL.cmd'):
            data = (ROOT / 'installer' / name).read_bytes()
            self.assertIn(b'\r\n', data)
            self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
            self.assertIn(b'"%~dp0Install-Reworkl.ps1"', data)
            self.assertIn(b'exit /b %RESULT%', data)


@unittest.skipUnless(POWERSHELL, 'Real PowerShell runtime is not installed on this host')
class ReleaseInstallerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "Extracted Reworkl O'Neil"
        self.source.mkdir()
        self.user = self.base / 'Документы игрока' / 'Hearts of Iron IV'
        self.user.mkdir(parents=True)
        self.payload_dirs = ('common', 'events', 'gfx', 'history', 'interface', 'localisation', 'map', 'music')
        for name in self.payload_dirs:
            (self.source / name).mkdir()
            (self.source / name / 'fixture.txt').write_text('fixture', encoding='utf-8')
        (self.source / 'descriptor.mod').write_text(
            'name="Reworkl test"\nversion="1.2.2"\nreplace_path="common/bookmarks"\nreplace_path="gfx/loadingscreens"\n', encoding='utf-8')
        (self.source / 'thumbnail.png').write_bytes(b'image fixture')
        (self.source / 'common/bookmarks').mkdir()
        (self.source / 'common/bookmarks/Y89_bookmarks.txt').write_text('bookmarks={ bookmark={date=1936.1.1.12} bookmark={date=1989.1.1.12} }')
        (self.source / 'original.zip').write_bytes(b'not payload')
        (self.source / 'scripts').mkdir()
        (self.source / 'scripts/ignored.txt').write_text('not payload')

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(self, *arguments, source=True):
        command = [POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(getattr(self, 'script', SCRIPT)), '-UserDir', str(self.user)]
        if source:
            command.extend(['-Source', str(self.source)])
        result = subprocess.run(command + list(arguments), text=True, encoding='utf-8', errors='replace', capture_output=True, env=powershell_env(), timeout=75)
        return result

    def test_installs_payload_and_absolute_launcher_path(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.user / 'mod/reworkl'
        self.assertEqual((target / 'music/fixture.txt').read_text(), 'fixture')
        self.assertFalse((target / 'original.zip').exists())
        self.assertFalse((target / 'scripts').exists())
        descriptor = (self.user / 'mod/reworkl.mod').read_text(encoding='utf-8')
        self.assertIn(f'path="{target.as_posix()}"', descriptor)
        self.assertIn('replace_path="common/bookmarks"', descriptor)
        self.assertIn('replace_path="gfx/loadingscreens"', descriptor)
        self.assertNotRegex((target / 'descriptor.mod').read_text(encoding='utf-8-sig'), r'(?m)^\s*path\s*=')
        self.assertIn('[NO_LAUNCH_STATE]', result.stdout)
        self.assertFalse((self.user / 'dlc_load.json').exists())

    def test_update_backs_up_without_touching_saves_or_launcher_state(self):
        old = self.user / 'mod/reworkl'
        old.mkdir(parents=True)
        (old / 'old-marker.txt').write_bytes(b'old mod')
        (self.user / 'mod/reworkl.mod').write_bytes(b'old descriptor')
        save = self.user / 'save games/campaign.hoi4'
        save.parent.mkdir()
        save.write_bytes(b'save data')
        state = self.user / 'dlc_load.json'
        state.write_bytes(b'{"enabled_mods":["mod/other.mod"],"disabled_dlcs":[]}')
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = list((self.user / 'reworkl-backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'reworkl/old-marker.txt').read_bytes(), b'old mod')
        self.assertEqual((backups[0] / 'reworkl.mod').read_bytes(), b'old descriptor')
        self.assertEqual(save.read_bytes(), b'save data')
        self.assertEqual(state.read_bytes(), b'{"enabled_mods":["mod/other.mod"],"disabled_dlcs":[]}')
        self.assertIn('[NOT_ENABLED_LAST_LAUNCH]', result.stdout)

    def test_check_only_is_read_only_and_detects_vanilla_bookmarks(self):
        (self.user / 'logs').mkdir()
        (self.user / 'logs/setup.log').write_text("[17:40:34][no_game_date]: Bookmarks loaded 'common/bookmarks/blitzkrieg.txt' Bookmarks #1\n")
        (self.user / 'dlc_load.json').write_text('{"enabled_mods":[],"disabled_dlcs":[]}')
        before = {p.relative_to(self.user): p.read_bytes() for p in self.user.rglob('*') if p.is_file()}
        result = self.run_installer('-CheckOnly', source=False)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('[NOT_INSTALLED]', result.stdout)
        self.assertIn('[NOT_ENABLED_LAST_LAUNCH]', result.stdout)
        self.assertIn('[SETUP_VANILLA_BOOKMARKS]', result.stdout)
        after = {p.relative_to(self.user): p.read_bytes() for p in self.user.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.user / 'mod').exists())

    def test_existing_install_can_be_registered_in_place(self):
        target = self.user / 'mod/reworkl'
        target.parent.mkdir()
        shutil.copytree(self.source, target)
        (target / 'keep.txt').write_text('keep in-place data')
        external = self.user / 'mod/reworkl.mod'
        external.write_text('path="Z:/missing/reworkl"')
        self.source = target
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f'path="{target.as_posix()}"', external.read_text(encoding='utf-8'))
        self.assertEqual((target / 'keep.txt').read_text(), 'keep in-place data')

    def test_check_recognizes_enabled_custom_bookmarks_but_does_not_launch_game(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (self.user / 'dlc_load.json').write_text(json.dumps({'enabled_mods': ['mod/reworkl.mod'], 'disabled_dlcs': []}))
        (self.user / 'logs').mkdir()
        (self.user / 'logs/setup.log').write_text("[17:40:34][no_game_date]: Bookmarks loaded 'common/bookmarks/Y89_bookmarks.txt' Bookmarks #2\n")
        result = self.run_installer('-CheckOnly', source=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('[PATH_OK]', result.stdout)
        self.assertIn('[ENABLED_LAST_LAUNCH]', result.stdout)
        self.assertIn('[SETUP_MOD_FOUND]', result.stdout)

    def test_incomplete_source_does_not_replace_existing_installation(self):
        old = self.user / 'mod/reworkl'
        old.mkdir(parents=True)
        (old / 'keep.txt').write_text('keep')
        (self.user / 'mod/reworkl.mod').write_text('old descriptor')
        shutil.rmtree(self.source / 'music')
        result = self.run_installer()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual((old / 'keep.txt').read_text(), 'keep')
        self.assertEqual((self.user / 'mod/reworkl.mod').read_text(), 'old descriptor')
        self.assertFalse((self.user / 'reworkl-backups').exists())


    def test_world_recovery_selects_exact_states_and_ignores_old_extras(self):
        from world_installer_fixture import make_world_source, add_recovery_bundle
        make_world_source(self.source)
        add_recovery_bundle(self.source)
        (self.source / 'history/states/1255-Reworkl.txt').unlink()
        (self.source / 'history/states/old-extra.txt').write_text('old wrong map')
        (self.source / 'history/country-extra.txt').write_text('unreviewed old history')
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.user / 'mod/reworkl'
        self.assertEqual(len(list((target / 'history/states').glob('*.txt'))), 1255)
        self.assertEqual((target / 'history/states/1255-Reworkl.txt').read_text(), 'state={ id=1255 }')
        self.assertFalse((target / 'history/states/old-extra.txt').exists())
        self.assertFalse((target / 'history/country-extra.txt').exists())

    def test_world_missing_state_names_and_actual_source_are_reported(self):
        from world_installer_fixture import make_world_source
        make_world_source(self.source)
        (self.source / 'history/states/1255-Reworkl.txt').unlink()
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn('WORLD_STATES_INCOMPLETE', result.stdout + result.stderr)
        self.assertIn('missing=1', result.stdout + result.stderr)
        self.assertIn('1255-Reworkl.txt', result.stdout + result.stderr)
        self.assertFalse((self.user / 'mod/reworkl').exists())


    def test_real_full_world_payload_installs_and_inplace_refresh_removes_extras(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from materialize_world_map import ensure_map_assets
        ensure_map_assets(ROOT)
        result = self.run_installer('-Source', str(ROOT), source=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.user / 'mod/reworkl'
        self.assertEqual(len(list((target / 'history/states').glob('*.txt'))), 1255)
        self.assertEqual((target / 'map/reworkl_state_manifest.json').read_bytes(), (ROOT / 'map/reworkl_state_manifest.json').read_bytes())
        self.assertEqual((target / 'map/provinces.bmp').read_bytes(), (ROOT / 'map/provinces.bmp').read_bytes())
        (target / 'history/states/old-extra.txt').write_text('old state')
        result = self.run_installer('-Source', str(target), source=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((target / 'history/states/old-extra.txt').exists())
        self.assertEqual(len(list((target / 'history/states').glob('*.txt'))), 1255)
        backups = list((self.user / 'reworkl-backups').glob('*/reworkl/history/states/old-extra.txt'))
        self.assertEqual(len(backups), 1)


    def test_shipped_native_repair_handles_the_alpha2_layout_without_source_json(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from world_installer_fixture import prepare_alpha2_repair_source
        kit, missing = prepare_alpha2_repair_source(self.source, self.base / 'delivered fix')
        self.script = kit / 'Install-Reworkl.ps1'
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('[TOOLS_VERSION] 2.0.0-alpha3', result.stdout)
        target = self.user / 'mod/reworkl'
        self.assertEqual((target / missing).read_bytes(), (ROOT / missing).read_bytes())
        self.assertFalse((self.source / missing).exists())
        self.assertFalse((self.source / 'map/reworkl_state_manifest.json').exists())
        self.assertIn('version="2.0.0-alpha2"', (target / 'descriptor.mod').read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
