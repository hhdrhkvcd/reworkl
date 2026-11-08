"""Real PowerShell fixture tests: read-only, bounded, time-linked diagnostics."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
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
from build_crash_diagnostics import build, HELPERS

SCRIPT = ROOT / 'installer/diagnostics/Reworkl-Crash-Diagnostics.ps1'
POWERSHELL = os.environ.get('REWORKL_TEST_POWERSHELL') or shutil.which('pwsh') or shutil.which('powershell')


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


class CrashDiagnosticsPackagingTests(unittest.TestCase):
    def test_collector_is_small_deterministic_and_separate_from_installers(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'diagnostics.zip'
            build(path)
            first = path.read_bytes()
            build(path)
            self.assertEqual(first, path.read_bytes())
            self.assertLess(len(first), 32768)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), set(HELPERS))
                for name in HELPERS:
                    self.assertEqual(archive.read(name), (ROOT / 'installer/diagnostics' / name).read_bytes())
        self.assertTrue(SCRIPT.read_bytes().startswith(b'\xef\xbb\xbf'))
        batch = (ROOT / 'installer/diagnostics/COLLECT_REWORKL_CRASH.bat').read_bytes()
        self.assertTrue(batch.isascii())
        self.assertNotIn(b'\n', batch.replace(b'\r\n', b''))
        self.assertIn(b'DisableDelayedExpansion', batch)
        self.assertIn(b'exit /b %RESULT%', batch)
        text = SCRIPT.read_text(encoding='utf-8-sig')
        for forbidden in ('Start-Process', 'Stop-Process', 'taskkill', 'save games/', 'launcher-v2.sqlite', 'Get-ChildItem -Recurse'):
            self.assertNotIn(forbidden, text)


@unittest.skipUnless(POWERSHELL, 'Real PowerShell runtime is not installed on this host')
class CrashDiagnosticsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.base = self.root / 'ASCII base !'
        self.user = self.base / 'reworkl-userdata'
        self.game = self.root / "Game O'Neil"
        self.docs = self.root / 'Документы'
        self.standard = self.docs / 'Paradox Interactive/Hearts of Iron IV'
        self.output = self.root / 'diagnostics output'
        self.home = self.root / 'fake home'
        for path in (self.base, self.user, self.game, self.docs, self.standard, self.home):
            path.mkdir(parents=True, exist_ok=True)
        self.now = datetime.now(timezone.utc)
        self.started = self.now - timedelta(seconds=60)
        self.state_path = self.base / 'reworkl-bat-state.json'
        self.state = dict(schema=1, target=str(self.base / 'reworkl'), user_dir=str(self.user),
                          version='2.0.0-alpha3', game_dir=str(self.game), last_launch_utc=self.started.isoformat(),
                          private_test_secret='DO_NOT_LEAK_STATE')
        self.write_state()
        (self.game / 'hoi4.exe').write_bytes(b'not executed')
        (self.game / 'launcher-settings.json').write_text(json.dumps(dict(gameDataPath=str(self.standard), access_token='DO_NOT_LEAK_LAUNCHER')), encoding='utf-8')
        (self.standard / 'dlc_load.json').write_text(json.dumps(dict(enabled_mods=['mod/old_1989.mod'], disabled_dlcs=[], other_secret='DO_NOT_LEAK_PROFILE')), encoding='utf-8')

    def tearDown(self):
        self.temporary.cleanup()

    def write_state(self):
        self.state_path.write_text(json.dumps(self.state), encoding='utf-8')

    def run_collector(self, extra='', process_override=True):
        driver = self.root / 'driver.ps1'
        mock = "function Write-DiagProcesses($ctx) { Add-DiagLine $ctx '[PROCESS_SNAPSHOT_NOW] fixture, no game execution' }\n" if process_override else ''
        driver.write_text(f". {quote(SCRIPT)} -LibraryOnly\n" + mock +
            f"$env:USERPROFILE = {quote(self.home)}\n" +
            "$env:OneDrive = ''; $env:OneDriveConsumer = ''; $env:OneDriveCommercial = ''\n" + extra +
            f"[void](Export-ReworklCrashDiagnostics {quote(self.base)} {quote(self.output)} {quote(self.docs)})\n", encoding='utf-8-sig')
        env = os.environ.copy()
        if Path(POWERSHELL).name.lower() in ('powershell', 'powershell.exe'):
            env.pop('PSModulePath', None)
        result = subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(driver)],
            env=env, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        zips = list(self.output.glob('REWORKL_CRASH_DIAGNOSTICS_*.zip'))
        self.assertEqual(len(zips), 1, result.stdout + result.stderr)
        with zipfile.ZipFile(zips[0]) as archive:
            self.assertIsNone(archive.testzip())
            self.payload = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
        return self.payload['REPORT.txt'].decode('utf-8-sig')

    def log(self, profile, name, content, time=None):
        path = profile / 'logs' / (name + '.log')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        moment = time or self.now
        os.utime(path, (moment.timestamp(), moment.timestamp()))
        return path

    def crash(self, name, date, with_meta=True):
        folder = self.standard / 'crashes' / name
        folder.mkdir(parents=True)
        if with_meta:
            (folder / 'meta.yml').write_text('DateTime: "' + date + '"\nMods: Reworkl - World 2026 v2.0.0-alpha3\nLaunchArguments: "-userdir=C:/Expected profile !" --secret=DO_NOT_LEAK_GAME_ARGS\n', encoding='utf-8')
        (folder / 'exception.txt').write_text('Application: HOI4\nDate/Time: ' + date + '\nUnhandled Exception C0000005\n', encoding='utf-8')
        return folder

    def test_finds_fresh_standard_profile_without_claiming_it_is_isolated(self):
        self.log(self.standard, 'system', b'Active Mod: Reworkl old\n')
        report = self.run_collector()
        self.assertIn('[OTHER_LOCATION]', report)
        self.assertIn('[LOG_MISSING]', report)
        self.assertIn('mod/old_1989.mod', report)
        self.assertIn('NOT a runtime confirmation', report)
        self.assertTrue(any(n.endswith('/logs/system.log') for n in self.payload))
        self.assertIn(str(self.standard).encode('utf-8'), self.payload['SOURCES.txt'])
        for secret in (b'DO_NOT_LEAK_STATE', b'DO_NOT_LEAK_LAUNCHER', b'DO_NOT_LEAK_PROFILE'):
            self.assertFalse(any(secret in body for body in self.payload.values()))

    def test_stale_logs_are_not_packaged(self):
        self.log(self.standard, 'system', b'OLD LOG CONTENT', self.now - timedelta(days=2))
        report = self.run_collector()
        self.assertIn('[OLD_OR_UNBOUND_LOG_SKIPPED]', report)
        self.assertFalse(any(b'OLD LOG CONTENT' in body for body in self.payload.values()))
        self.assertEqual(set(self.payload), {'REPORT.txt', 'SOURCES.txt'})

    def test_fresh_crash_is_collected_but_old_embedded_date_and_dumps_are_not(self):
        fresh_date = self.now.strftime('%Y-%m-%d %H:%M:%S +0000')
        fresh = self.crash('current', fresh_date)
        (fresh / 'minidump.dmp').write_bytes(b'PRIVATE MEMORY')
        (fresh / 'save.hoi4').write_bytes(b'PRIVATE SAVE')
        (fresh / 'launcher-v2.sqlite').write_bytes(b'PRIVATE ACCOUNT DB')
        self.crash('old_recently_copied', '2020-11-01 14:57:07 +0400')
        report = self.run_collector()
        self.assertIn('[CRASH_CANDIDATE]', report)
        self.assertIn('[CRASH_RECORDED_USERDIR_ARGUMENT] C:/Expected profile !', report)
        self.assertIn('[OLD_CRASH_EMBEDDED_DATE_SKIPPED]', report)
        self.assertEqual(len([n for n in self.payload if n.endswith('/exception.txt')]), 1)
        self.assertTrue(any(b'Unhandled Exception C0000005' in b for b in self.payload.values()))
        joined = b'\n'.join(self.payload.values())
        for forbidden in (b'PRIVATE MEMORY', b'PRIVATE SAVE', b'PRIVATE ACCOUNT DB', b'DO_NOT_LEAK_GAME_ARGS'):
            self.assertNotIn(forbidden, joined)
        meta = next(b for n, b in self.payload.items() if n.endswith('/meta.yml'))
        self.assertIn(b'LaunchArguments: [omitted]', meta)

    def test_exception_timestamp_can_bind_a_crash_without_meta(self):
        self.crash('no_meta', self.now.strftime('%Y-%m-%d %H:%M:%S +0000'), with_meta=False)
        report = self.run_collector()
        self.assertIn('[CRASH_CANDIDATE]', report)
        self.assertNotIn('[CRASH_DATE_UNVERIFIED]', report)
        self.assertTrue(any(n.endswith('/exception.txt') for n in self.payload))

    def test_large_log_is_tailed_and_all_input_files_stay_unchanged(self):
        path = self.log(self.user, 'system', b'EARLY_PRIVATE_PREFIX' + b'x' * (2 * 1024 * 1024) + b'LATEST_END')
        originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.run_collector()
        content = next(b for n, b in self.payload.items() if n.endswith('/system.log'))
        self.assertEqual(len(content), 1048576)
        self.assertTrue(content.endswith(b'LATEST_END'))
        self.assertNotIn(b'EARLY_PRIVATE_PREFIX', content)
        for p, digest in originals.items():
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest, p)

    def test_no_valid_receipt_time_does_not_relabel_old_files_as_current(self):
        self.state['last_launch_utc'] = None
        self.write_state()
        self.log(self.standard, 'system', b'UNBOUND LOG')
        self.crash('unbound', self.now.strftime('%Y-%m-%d %H:%M:%S +0000'))
        report = self.run_collector()
        self.assertIn('[NO_VALID_LAUNCH_TIME]', report)
        self.assertEqual(set(self.payload), {'REPORT.txt', 'SOURCES.txt'})

    def test_live_process_snapshot_exports_only_userdir_not_full_command_line(self):
        extra = f'''function Get-Process {{ [pscustomobject]@{{ Id=123; Path={quote(self.game / 'hoi4.exe')}; StartTime=([DateTime]::Now) }} }}
function Get-CimInstance {{ [pscustomobject]@{{ ProcessId=123; CommandLine='hoi4.exe "-userdir=C:/ASCII base !/reworkl-userdata" --password=DO_NOT_LEAK_PROCESS_ARGS' }} }}
'''
        report = self.run_collector(extra, process_override=False)
        self.assertIn('[PROCESS] pid=123;', report)
        self.assertIn('userdir=C:/ASCII base !/reworkl-userdata', report)
        self.assertNotIn('DO_NOT_LEAK_PROCESS_ARGS', report)

    def test_userdir_settings_are_read_not_changed_and_candidates_are_deduplicated(self):
        profile = self.root / 'custom profile'
        self.log(profile, 'system', b'CUSTOM PROFILE LOG')
        settings = self.game / 'userdir.txt'
        settings.write_text(str(profile), encoding='utf-8')
        original = settings.read_bytes()
        report = self.run_collector()
        self.assertIn('[USERDIR_SETTING]', report)
        self.assertIn('userdir_setting', report)
        self.assertEqual(settings.read_bytes(), original)
        self.assertEqual(len([n for n in self.payload if n.endswith('/system.log')]), 1)


    def test_windows_event_export_is_scoped_and_omits_unrelated_or_secret_fields(self):
        extra = r'''function Get-WinEvent {
    param($LogName, $FilterXPath, $MaxEvents, $ErrorAction)
    $compiled = [Xml.XPath.XPathExpression]::Compile($FilterXPath)
    if ($compiled.ReturnType -ne [Xml.XPath.XPathResultType]::NodeSet) { throw 'Event query must select nodes, not return a Boolean.' }
    [pscustomobject]@{ TimeCreated=([DateTime]::Now) } | Add-Member -MemberType ScriptMethod -Name ToXml -Value {
        '<Event><EventData><Data Name="AppName">hoi4.exe</Data><Data Name="ModuleName">example.dll</Data><Data Name="ExceptionCode">c0000005</Data><Data Name="AccessToken">DO_NOT_LEAK_EVENT</Data></EventData></Event>'
    } -PassThru
}
'''
        report = self.run_collector(extra)
        self.assertIn('[HOI4_APPLICATION_ERROR]', report)
        self.assertIn('ModuleName=example.dll', report)
        self.assertIn('ExceptionCode=c0000005', report)
        self.assertNotIn('DO_NOT_LEAK_EVENT', report)


if __name__ == '__main__':
    unittest.main()
