"""BAT packaging plus real PowerShell integration against isolated fixtures.

No HOI4 execution. Start-Process is replaced only inside test driver processes.
Runtime tests run on Windows CI (PowerShell 5.1 and 7); skips are explicit elsewhere.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_mod import BAT_HELPERS, build_bat_toolkit, helper_path

SCRIPT = ROOT / 'installer/bat/Reworkl-Bat.ps1'
POWERSHELL = os.environ.get('REWORKL_TEST_POWERSHELL') or shutil.which('pwsh') or shutil.which('powershell')


def powershell_env():
    import os
    env = os.environ.copy()
    if Path(POWERSHELL).name.lower() in ('powershell', 'powershell.exe'):
        env.pop('PSModulePath', None)
    return env


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


class BatPackagingTests(unittest.TestCase):
    def test_bat_helpers_are_crlf_ascii_and_preserve_exit_codes(self):
        for name in BAT_HELPERS:
            data = helper_path(name).read_bytes()
            if name.endswith('.bat'):
                self.assertTrue(data.isascii())
                self.assertIn(b'\r\n', data)
                self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
                self.assertIn(b'DisableDelayedExpansion', data)
                self.assertIn(b'"%~dp0Reworkl-Bat.ps1"', data)
                self.assertIn(b'exit /b %RESULT%', data)
                self.assertNotIn(b'rmdir /s', data.lower())
                self.assertNotIn(b'taskkill', data.lower())
        self.assertTrue(SCRIPT.read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_atomic_replace_uses_a_real_backup_path_not_a_null_string_argument(self):
        text = SCRIPT.read_text(encoding='utf-8-sig')
        body = text.split('function Write-Atomic(', 1)[1].split('function Backup-Files(', 1)[0]
        self.assertNotIn('[IO.File]::Replace($temporary, $Path, $null)', body)
        self.assertIn('[IO.File]::Replace($temporary, $Path, $previous)', body)
        self.assertIn("$previous = Join-Path $parent", body)
        self.assertIn('$replaced = $false', body)

    def test_root_install_bat_uses_the_new_workflow_not_python(self):
        data = (ROOT / 'install.bat').read_bytes()
        self.assertIn(b'installer\\bat\\1_INSTALL.bat', data)
        self.assertNotIn(b'python', data.lower())

    def test_custom_scenarios_have_no_dlc_requirement_and_serbia_has_legacy_tanks(self):
        from clausewitz import load
        self.assertFalse(load(ROOT / 'descriptor.mod').children('dependencies'))
        self.assertNotIn('has_dlc', (ROOT / 'common/bookmarks/Y89_bookmarks.txt').read_text())
        for path in (ROOT / 'common/national_focus').glob('*.txt'):
            self.assertNotIn('has_dlc', path.read_text(), path.name)
        text = (ROOT / 'history/countries/SER - Serbia.txt').read_text()
        self.assertIn('limit = { has_dlc = "No Step Back" }', text)
        self.assertIn('else = { set_technology = { gwtank = 1 basic_light_tank = 1 } }', text)

    def test_small_toolkit_is_reproducible_and_only_contains_reworkl_helpers(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bat.zip'
            build_bat_toolkit(path)
            first = path.read_bytes()
            build_bat_toolkit(path)
            self.assertEqual(first, path.read_bytes())
            self.assertLess(len(first), 1024 * 1024)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), set(BAT_HELPERS))
                for name in archive.namelist():
                    content = archive.read(name).decode('utf-8-sig') if not name.endswith('.zip') else ''
                    self.assertNotIn('Umalilend', content)
                    self.assertNotIn('C:/Users/мо', content)
                    self.assertNotIn('C:\\Users\\мо', content)


@unittest.skipUnless(POWERSHELL, 'Real PowerShell runtime is not installed on this host')
class BatWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "Reworkl папка O'Neil"
        self.game = self.root / "Game O'Neil with spaces"
        self.base = self.root / 'ASCII base !'
        self.source.mkdir()
        self.game.mkdir()
        (self.game / 'hoi4.exe').write_bytes(b'NEVER EXECUTE: fake game fixture')
        for name in ('common', 'events', 'gfx', 'history', 'interface', 'localisation', 'map', 'music'):
            (self.source / name).mkdir()
            (self.source / name / 'fixture.txt').write_text('old payload', encoding='utf-8')
        (self.source / 'thumbnail.png').write_bytes(b'test thumbnail')
        (self.source / 'descriptor.mod').write_text(
            'name="Reworkl — test"\nversion="1.2.0"\nreplace_path="common/bookmarks"\nreplace_path="gfx/loadingscreens"\nsupported_version="1.19.*"\n', encoding='utf-8')
        (self.source / 'common/bookmarks').mkdir()
        (self.source / 'common/bookmarks/Y89_bookmarks.txt').write_text(
            'bookmarks={ bookmark={name=Y89_BOOKMARK_1989 date=1989.1.1.12} bookmark={date=1936.1.1.12} }', encoding='utf-8')
        (self.source / 'scripts').mkdir()
        (self.source / 'scripts/ignored.txt').write_text('not payload')
        (self.source / 'original.zip').write_bytes(b'not payload')
        for name in ('dlc/dlc001_pack/dlc001.dlc', 'dlc_metadata/portrait.dlc'):
            path = self.game / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'DLC metadata fixture')
        (self.game / 'launcher-settings.json').write_bytes(b'{"gameId":"hoi4","gameDataPath":"old path","other":{"keep":true}}\r\n')
        self.user = self.base / 'reworkl-userdata'
        self.target = self.base / 'reworkl'
        self.original = self.root / 'Original Documents'
        self.original.mkdir()
        (self.original / 'dlc_load.json').write_bytes(b'{"enabled_mods":["mod/other.mod"],"disabled_dlcs":[]}')
        (self.original / 'campaign.hoi4').write_bytes(b'old save')

    def tearDown(self):
        self.temporary.cleanup()

    def run_ps(self, body):
        driver = self.root / 'driver.ps1'
        driver.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            f'. {ps_quote(SCRIPT)} -LibraryOnly\n'
            'function Assert-Closed {}\n'
            f'$source = {ps_quote(self.source)}\n$game = {ps_quote(self.game)}\n$base = {ps_quote(self.base)}\n'
            + body, encoding='utf-8-sig')
        return subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(driver)], env=powershell_env(), capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)

    def install(self):
        result = self.run_ps('Invoke-Reworkl -Action Install -Source $source -GameDir $game -BaseDir $base -NonInteractive\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def load_state(self):
        return json.loads((self.base / 'reworkl-bat-state.json').read_text(encoding='utf-8-sig'))

    def launch_body(self):
        receipt = ps_quote(self.root / 'launch.json')
        return '''function Start-Process {
    param($FilePath, $WorkingDirectory, $ArgumentList, [switch]$PassThru)
    $data = [pscustomobject]@{exe=$FilePath; cwd=$WorkingDirectory; arguments=$ArgumentList}
    [IO.File]::WriteAllText(RECEIPT, (ConvertTo-Json -InputObject $data))
    return [pscustomobject]@{Id=12345}
}
Invoke-Reworkl -Action Launch -GameDir $game -BaseDir $base -NonInteractive
'''.replace('RECEIPT', receipt)

    def launch(self):
        result = self.run_ps(self.launch_body())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def logs(self, *, dlc=0, mods=1, custom=True):
        logs = self.user / 'logs'
        logs.mkdir(exist_ok=True)
        (logs / 'system.log').write_text(f'Active Mod Count: {mods}\nActive Mod: Reworkl - test\nActive DLC Count: {dlc}\n')
        book = "common/bookmarks/Y89_bookmarks.txt' Bookmarks #2" if custom else "common/bookmarks/the_gathering_storm.txt' Bookmarks #1"
        (logs / 'setup.log').write_text(f"Bookmarks loaded '{book}\n")

    def test_atomic_write_can_overwrite_existing_files_repeatedly(self):
        destination = self.source / "settings O'Neil.json"
        result = self.run_ps(
            f'$destination = {ps_quote(destination)}\n'
            "Write-Atomic $destination 'first'\n"
            "Write-Atomic $destination 'second'\n"
            "Write-Atomic $destination 'third'\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(destination.read_bytes(), b'third')
        self.assertEqual(list(self.source.glob('.reworkl-*')), [])

    def test_install_is_isolated_ascii_and_really_disables_discovered_dlc(self):
        self.install()
        self.assertEqual((self.target / 'music/fixture.txt').read_text(), 'old payload')
        self.assertFalse((self.target / 'scripts').exists())
        self.assertFalse((self.target / 'original.zip').exists())
        external = (self.user / 'mod/reworkl.mod').read_bytes()
        self.assertTrue(external.isascii())
        self.assertIn(f'path="{self.target.as_posix()}"'.encode(), external)
        self.assertIn(b'version="1.2.0"', external)
        self.assertIn(b'replace_path="gfx/loadingscreens"', external)
        self.assertNotRegex((self.target / 'descriptor.mod').read_text(encoding='utf-8-sig'), r'(?m)^\s*path\s*=')
        state = json.loads((self.user / 'dlc_load.json').read_text())
        self.assertEqual(state['enabled_mods'], ['mod/reworkl.mod'])
        self.assertEqual(set(state['disabled_dlcs']), {'dlc/dlc001_pack/dlc001.dlc', 'dlc_metadata/portrait.dlc'})
        self.assertEqual(self.load_state()['disabled_dlc_count'], 2)
        self.assertEqual((self.original / 'campaign.hoi4').read_bytes(), b'old save')
        self.assertIn(b'other.mod', (self.original / 'dlc_load.json').read_bytes())

    def test_base_game_without_installed_dlc_has_an_empty_disable_list(self):
        shutil.rmtree(self.game / 'dlc')
        shutil.rmtree(self.game / 'dlc_metadata')
        self.install()
        state = json.loads((self.user / 'dlc_load.json').read_text())
        self.assertEqual(state['disabled_dlcs'], [])
        self.assertEqual(self.load_state()['disabled_dlc_count'], 0)

    def test_update_keeps_backup_and_existing_saves_and_unknown_json_properties(self):
        self.install()
        (self.target / 'old-marker.txt').write_bytes(b'keep old mod')
        (self.user / 'save games').mkdir()
        (self.user / 'save games/new-save.hoi4').write_bytes(b'keep new save')
        (self.user / 'dlc_load.json').write_text('{"enabled_mods":["mod/other.mod"],"disabled_dlcs":["dlc/extra.dlc"],"unknown":{"keep":true}}')
        self.install()
        backups = list((self.base / 'reworkl-backups').glob('*/previous-reworkl/old-marker.txt'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'keep old mod')
        self.assertFalse((self.target / 'old-marker.txt').exists())
        self.assertEqual((self.user / 'save games/new-save.hoi4').read_bytes(), b'keep new save')
        state = json.loads((self.user / 'dlc_load.json').read_text())
        self.assertEqual(state['unknown'], {'keep': True})
        self.assertIn('dlc/extra.dlc', state['disabled_dlcs'])

    def test_incomplete_source_does_not_change_existing_installation(self):
        self.install()
        before = (self.target / 'music/fixture.txt').read_bytes()
        old_state = (self.base / 'reworkl-bat-state.json').read_bytes()
        shutil.rmtree(self.source / 'music')
        result = self.run_ps('Invoke-Reworkl -Action Install -Source $source -GameDir $game -BaseDir $base -NonInteractive')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.target / 'music/fixture.txt').read_bytes(), before)
        self.assertEqual((self.base / 'reworkl-bat-state.json').read_bytes(), old_state)

    def test_failed_activation_rolls_back_payload_and_both_config_files(self):
        self.install()
        old_state = (self.base / 'reworkl-bat-state.json').read_bytes()
        old_external = (self.user / 'mod/reworkl.mod').read_bytes()
        old_load = (self.user / 'dlc_load.json').read_bytes()
        (self.source / 'music/fixture.txt').write_text('new payload')
        result = self.run_ps('''Rename-Item Function:Write-Atomic Write-AtomicOriginal
function Write-Atomic { param($Path, $Text)
    if ($Path -eq (Join-Path $base 'reworkl-userdata/dlc_load.json')) { throw 'injected write failure' }
    Write-AtomicOriginal $Path $Text
}
Invoke-Reworkl -Action Install -Source $source -GameDir $game -BaseDir $base -NonInteractive
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.target / 'music/fixture.txt').read_text(), 'old payload')
        self.assertEqual((self.user / 'mod/reworkl.mod').read_bytes(), old_external)
        self.assertEqual((self.user / 'dlc_load.json').read_bytes(), old_load)
        self.assertEqual((self.base / 'reworkl-bat-state.json').read_bytes(), old_state)

    def test_launch_rewrites_registration_and_uses_quoted_ascii_userdir(self):
        self.install()
        (self.user / 'mod/reworkl.mod').write_bytes(b'bad external')
        (self.user / 'dlc_load.json').write_text('{"enabled_mods":[],"disabled_dlcs":[]}')
        self.launch()
        receipt = json.loads((self.root / 'launch.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(Path(receipt['exe']), self.game / 'hoi4.exe')
        self.assertEqual(Path(receipt['cwd']), self.game)
        self.assertEqual(receipt['arguments'], f'-nolauncher "-userdir={self.user.as_posix()}"')
        self.assertIsNotNone(self.load_state()['last_launch_utc'])
        self.assertEqual(json.loads((self.user / 'dlc_load.json').read_text())['enabled_mods'], ['mod/reworkl.mod'])
        self.assertNotIn(b'bad external', (self.user / 'mod/reworkl.mod').read_bytes())

    def test_failed_launch_restores_prelaunch_files(self):
        self.install()
        before = (self.base / 'reworkl-bat-state.json').read_bytes()
        result = self.run_ps("function Start-Process { throw 'injected launch failure' }\nInvoke-Reworkl -Action Launch -GameDir $game -BaseDir $base -NonInteractive")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.base / 'reworkl-bat-state.json').read_bytes(), before)

    def test_dry_run_does_not_write_state_or_start_a_process(self):
        self.install()
        before = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        result = self.run_ps("function Start-Process { throw 'must not launch' }\nInvoke-Reworkl -Action Launch -GameDir $game -BaseDir $base -DryRun")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertIn('[DRY_RUN]', result.stdout)

    def check(self):
        return self.run_ps('exit (Invoke-Reworkl -Action Check -BaseDir $base)')

    def test_fresh_fixture_logs_confirm_only_loading_and_zero_dlc(self):
        self.install()
        self.launch()
        self.logs()
        before = (self.user / 'dlc_load.json').read_bytes()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('REWORKL LOADED; ACTIVE DLC: 0', result.stdout)
        self.assertEqual((self.user / 'dlc_load.json').read_bytes(), before)

    def test_old_logs_without_bat_launch_do_not_pass(self):
        self.install()
        self.logs()
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn('[NO_LAUNCH]', result.stdout)

    def test_unchanged_logs_do_not_confirm_a_new_launch(self):
        self.install()
        self.logs()
        self.launch()
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn('[STALE_LOG]', result.stdout)

    def test_active_dlc_or_vanilla_bookmarks_do_not_pass(self):
        self.install()
        self.launch()
        self.logs(dlc=38, custom=False)
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn('[DLC_MODE_UNCONFIRMED]', result.stdout)
        self.assertIn('[NO_REWORKL_BOOKMARKS]', result.stdout)
        self.assertIn('[VANILLA_BOOKMARKS]', result.stdout)

    def test_optional_plan_b_restores_exact_original_bytes(self):
        self.install()
        settings = self.game / 'launcher-settings.json'
        original = settings.read_bytes()
        result = self.run_ps('Invoke-Reworkl -Action PatchLauncher -GameDir $game -BaseDir $base')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patched = json.loads(settings.read_text())
        self.assertEqual(patched['gameDataPath'], self.user.as_posix())
        self.assertEqual(patched['other'], {'keep': True})
        self.assertEqual((self.game / 'userdir.txt').read_text().strip(), self.user.as_posix())
        result = self.run_ps('Invoke-Reworkl -Action RestoreLauncher -GameDir $game -BaseDir $base')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse((self.game / 'userdir.txt').exists())

    def test_plan_b_does_not_overwrite_a_subsequent_game_update_on_restore(self):
        self.install()
        result = self.run_ps('Invoke-Reworkl -Action PatchLauncher -GameDir $game -BaseDir $base')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        settings = self.game / 'launcher-settings.json'
        settings.write_bytes(b'{"gameDataPath":"changed by game update"}')
        result = self.run_ps('Invoke-Reworkl -Action RestoreLauncher -GameDir $game -BaseDir $base')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'changed by game update', settings.read_bytes())
        self.assertTrue((self.base / 'reworkl-plan-b.json').exists())

    def test_plan_b_restores_preexisting_userdir_file(self):
        self.install()
        path = self.game / 'userdir.txt'
        path.write_bytes(b'D:/OldUserData\r\n')
        for action in ['PatchLauncher', 'RestoreLauncher']:
            result = self.run_ps(f'Invoke-Reworkl -Action {action} -GameDir $game -BaseDir $base')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(path.read_bytes(), b'D:/OldUserData\r\n')

    def test_non_ascii_base_is_rejected_before_writing(self):
        other = self.root / 'Папка'
        result = self.run_ps(f'Invoke-Reworkl -Action Install -Source $source -GameDir $game -BaseDir {ps_quote(other)} -NonInteractive')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(other.exists())


    def make_world_source(self):
        from world_installer_fixture import make_world_source
        make_world_source(self.source)

    def test_explicit_new_bundle_cannot_silently_launch_an_old_install(self):
        self.install()
        before = (self.base / 'reworkl-bat-state.json').read_bytes()
        self.make_world_source()
        body = self.launch_body().replace('-Action Launch', '-Action Launch -Source $source')
        result = self.run_ps(body)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('INSTALLED_BUILD_MISMATCH', result.stdout + result.stderr)
        self.assertFalse((self.root / 'launch.json').exists())
        self.assertEqual((self.base / 'reworkl-bat-state.json').read_bytes(), before)

    def test_same_version_but_changed_bookmark_is_not_silently_launched(self):
        self.make_world_source()
        self.install()
        path = self.source / 'common/bookmarks/Y89_bookmarks.txt'
        path.write_text(path.read_text() + '\n# later build of the same version\n')
        result = self.run_ps(self.launch_body().replace('-Action Launch', '-Action Launch -Source $source'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('INSTALLED_BUILD_MISMATCH', result.stdout + result.stderr)
        self.assertFalse((self.root / 'launch.json').exists())

    def test_one_click_refuses_a_legacy_source_without_changing_the_install(self):
        self.install()
        before = (self.base / 'reworkl-bat-state.json').read_bytes()
        result = self.run_ps(self.launch_body().replace('-Action Launch', '-Action Start2026 -Source $source'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FULL_2026_ZIP_REQUIRED', result.stdout + result.stderr)
        self.assertFalse((self.root / 'launch.json').exists())
        self.assertEqual((self.base / 'reworkl-bat-state.json').read_bytes(), before)

    def test_one_click_updates_legacy_payload_before_start_and_collects_no_private_profile(self):
        self.install()
        (self.target / 'old-only-marker.txt').write_text('old map marker')
        self.make_world_source()
        self.user.mkdir(exist_ok=True)
        (self.user / 'private-save.hoi4').write_bytes(b'NEVER INCLUDE IN DIAGNOSTICS')
        (self.user / 'pdx_settings.txt').write_text('private preference fixture')
        report = self.root / 'REWORKL_START_RESULT.txt'
        body = self.launch_body().split('Invoke-Reworkl -Action Launch', 1)[0]
        body += f'exit (Invoke-Reworkl -Action Start2026 -Source $source -GameDir $game -BaseDir $base -ReportPath {ps_quote(report)} -NonInteractive)\n'
        result = self.run_ps(body)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)  # Fake process supplies no real game logs.
        self.assertTrue((self.root / 'launch.json').is_file())
        self.assertEqual(self.load_state()['version'], '2.0.0-alpha2')
        self.assertFalse((self.target / 'old-only-marker.txt').exists())
        self.assertIn('2026.1.1', (self.target / 'common/bookmarks/Y89_bookmarks.txt').read_text())
        for name in ['map/provinces.bmp', 'map/definition.csv', 'map/default.map', 'licenses/flag-icons-MIT.txt']:
            self.assertEqual((self.target / name).read_bytes(), (self.source / name).read_bytes())
        self.assertIn('NOT CONFIRMED', report.read_text())
        with zipfile.ZipFile(next(self.root.glob('REWORKL_DIAGNOSTICS_*.zip'))) as archive:
            self.assertEqual(set(archive.namelist()), {'START_RESULT.txt', 'SOURCES.txt'})
        self.assertEqual((self.user / 'private-save.hoi4').read_bytes(), b'NEVER INCLUDE IN DIAGNOSTICS')

    def test_world_check_accepts_empty_canonical_shadows_not_real_1939(self):
        self.make_world_source()
        self.install()
        self.launch()
        self.logs()
        (self.user / 'logs/system.log').write_text('Active Mod Count: 1\nActive Mod: Reworkl - World 2026 v2.0.0-alpha2\nActive DLC Count: 0\n')
        path = self.user / 'logs/setup.log'
        path.write_text(path.read_text() + "Bookmarks loaded 'common/bookmarks/blitzkrieg.txt' Bookmarks #0\nBookmarks loaded 'common/bookmarks/the_gathering_storm.txt' Bookmarks #0\n")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path.write_text(path.read_text() + "Bookmarks loaded 'common/bookmarks/blitzkrieg.txt' Bookmarks #1\n")
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn('[VANILLA_BOOKMARKS]', result.stdout)

    def test_world_check_does_not_accept_a_generic_reworkl_or_old_combined_name(self):
        self.make_world_source()
        self.install()
        self.launch()
        self.logs()  # Generic Reworkl - test is NOT proof of World 2026 alpha2.
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn('[WRONG_BUILD_OR_PROFILE]', result.stdout)


    def test_extra_legacy_states_and_other_mod_files_are_excluded_not_counted(self):
        self.make_world_source()
        (self.source / 'history/states/107-OldSerbia.txt').write_text('old same ID')
        (self.source / 'common/bookmarks/extra_1939.txt').write_text('old extra campaign')
        self.install()
        self.assertEqual(len(list((self.target / 'history/states').glob('*.txt'))), 1255)
        self.assertFalse((self.target / 'history/states/107-OldSerbia.txt').exists())
        self.assertFalse((self.target / 'common/bookmarks/extra_1939.txt').exists())
        self.assertTrue((self.source / 'history/states/107-OldSerbia.txt').exists())

    def test_equal_file_count_cannot_hide_missing_required_states(self):
        self.make_world_source()
        (self.source / 'history/states/1255-Reworkl.txt').unlink()
        (self.source / 'history/states/old-extra.txt').write_text('not the missing state')
        result = self.run_ps('Invoke-Reworkl -Action Install -Source $source -GameDir $game -BaseDir $base -NonInteractive')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WORLD_STATES_INCOMPLETE', result.stdout + result.stderr)
        self.assertIn('missing=1', result.stdout + result.stderr)
        self.assertIn('1255-Reworkl.txt', result.stdout + result.stderr)
        self.assertFalse(self.target.exists())

    def test_recovery_restores_missing_or_changed_states_without_touching_source(self):
        self.make_world_source()
        from world_installer_fixture import add_recovery_bundle
        add_recovery_bundle(self.source)
        (self.source / 'history/states/1255-Reworkl.txt').unlink()
        path = self.source / 'history/states/1-Reworkl.txt'
        path.write_text('corrupted loose file')
        result = self.install()
        self.assertIn('missing_loose=1; changed_loose=1', result.stdout)
        self.assertEqual((self.target / 'history/states/1255-Reworkl.txt').read_text(), 'state={ id=1255 }')
        self.assertEqual((self.target / 'history/states/1-Reworkl.txt').read_text(), 'state={ id=1 }')
        self.assertFalse((self.source / 'history/states/1255-Reworkl.txt').exists())
        self.assertEqual(path.read_text(), 'corrupted loose file')

    def test_recovery_can_install_when_the_loose_state_folder_is_absent(self):
        self.make_world_source()
        from world_installer_fixture import add_recovery_bundle
        add_recovery_bundle(self.source)
        shutil.rmtree(self.source / 'history/states')
        self.install()
        self.assertEqual(len(list((self.target / 'history/states').glob('*.txt'))), 1255)
        self.assertFalse((self.source / 'history/states').exists())

    def test_bad_recovery_archive_does_not_replace_the_installed_mod(self):
        self.install()
        before = (self.base / 'reworkl-bat-state.json').read_bytes()
        self.make_world_source()
        from world_installer_fixture import add_recovery_bundle, BUNDLE_DOWNLOAD
        add_recovery_bundle(self.source)
        (self.source.parent / BUNDLE_DOWNLOAD).write_bytes(b'corrupted archive')
        result = self.run_ps('Invoke-Reworkl -Action Install -Source $source -GameDir $game -BaseDir $base -NonInteractive')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WORLD_STATE_ARCHIVE_CORRUPT', result.stdout + result.stderr)
        self.assertEqual((self.base / 'reworkl-bat-state.json').read_bytes(), before)
        self.assertEqual((self.target / 'history/fixture.txt').read_text(), 'old payload')


    def test_start_preflight_failure_saves_report_and_report_only_zip(self):
        self.make_world_source()
        (self.source / 'history/states/1255-Reworkl.txt').unlink()
        logs = self.base / 'reworkl-userdata/logs'
        logs.mkdir(parents=True)
        (logs / 'system.log').write_text('unrelated old game run')
        report = self.root / 'reports/start.txt'
        result = subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(SCRIPT), '-Action', 'Start2026', '-Source', str(self.source), '-GameDir', str(self.game),
            '-BaseDir', str(self.base), '-ReportPath', str(report), '-NonInteractive'],
            env=powershell_env(), capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('WORLD_STATES_INCOMPLETE', report.read_text(encoding='utf-8-sig'))
        self.assertIn('1255-Reworkl.txt', report.read_text(encoding='utf-8-sig'))
        bundles = list(report.parent.glob('REWORKL_DIAGNOSTICS_*.zip'))
        self.assertEqual(len(bundles), 1, result.stdout + result.stderr)
        with zipfile.ZipFile(bundles[0]) as archive:
            self.assertEqual(set(archive.namelist()), {'START_RESULT.txt', 'SOURCES.txt'})
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
