"""File-overlay/installer contracts, NOT a HOI4 or PowerShell emulator."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_mod import BAT_HELPERS, source_files
from clausewitz import load, parse


class StartupRoutingContracts(unittest.TestCase):
    def test_canonical_vanilla_files_are_shadowed_even_in_a_simple_file_overlay(self):
        # These stand-in files only model filename precedence, not game loading.
        vanilla = {
            'the_gathering_storm.txt': 'bookmarks = { bookmark = { date = 1936.1.1.12 default = yes } }',
            'blitzkrieg.txt': 'bookmarks = { bookmark = { date = 1939.8.14.12 } }',
        }
        ours = {p.name: p.read_text() for p in (ROOT / 'common/bookmarks').glob('*.txt')}
        for name in vanilla:
            self.assertIn(name, ours)
            self.assertFalse(parse(ours[name]).children('bookmarks'))
        for respect_replace_path in (True, False):
            overlay = {} if respect_replace_path else dict(vanilla)
            overlay.update(ours)
            bookmarks = [b for text in overlay.values() for group in parse(text).children('bookmarks') for b in group.children('bookmark')]
            self.assertEqual(len(bookmarks), 2)
            self.assertEqual({b.scalar('date') for b in bookmarks}, {'2026.1.1.12', '1936.1.1.12'})
            self.assertEqual([b.scalar('date') for b in bookmarks if b.scalar('default') == 'yes'], ['2026.1.1.12'])

    def test_country_histories_cannot_merge_unreviewed_vanilla_setup(self):
        tags = {e.key for p in (ROOT / 'common/country_tags').glob('*.txt') for e in load(p).children()}
        histories = {p.stem.split(' - ', 1)[0] for p in (ROOT / 'history/countries').glob('*.txt')}
        self.assertEqual(histories, tags)
        self.assertEqual(len(histories), 199)  # 198 active plus releasable YUG.
        self.assertIn('history/countries', {e.value for e in load(ROOT / 'descriptor.mod').children('replace_path')})

    def test_single_start_button_requires_the_sibling_full_mod(self):
        self.assertIn('0_START_2026.bat', BAT_HELPERS)
        wrapper = (ROOT / 'installer/bat/0_START_2026.bat').read_text()
        self.assertIn('if not exist "%~dp0reworkl\\descriptor.mod"', wrapper)
        self.assertIn('-Action Start2026 -Source "%~dp0reworkl"', wrapper)
        self.assertIn('REWORKL_START_RESULT.txt', wrapper)
        self.assertIn('exit /b %RESULT%', wrapper)

    def test_single_start_checks_source_then_installs_before_launching(self):
        text = (ROOT / 'installer/bat/Reworkl-Bat.ps1').read_text(encoding='utf-8-sig')
        body = text.split('function Invoke-Start2026(', 1)[1].split('function Invoke-Patch(', 1)[0]
        self.assertLess(body.index("$description.Version -notlike '2.*'"), body.index('Invoke-Install'))
        actual = body.split('return 0', 1)[1]  # After the dry-run branch.
        self.assertLess(actual.index('Invoke-Install'), actual.index('Invoke-Launch'))
        self.assertLess(actual.index('Invoke-Launch'), actual.index('Invoke-Check'))
        self.assertLess(actual.index('Invoke-Check'), actual.index('Export-StartupDiagnostics'))

    def test_normal_launch_rejects_a_different_bundled_version_without_copying(self):
        text = (ROOT / 'installer/bat/Reworkl-Bat.ps1').read_text(encoding='utf-8-sig')
        body = text.split('function Invoke-Launch(', 1)[1].split('function Invoke-Check(', 1)[0]
        self.assertLess(body.index('Assert-BundledVersion'), body.index('Start-Process'))
        self.assertNotIn('Invoke-Install', body)
        guard = text.split('function Assert-BundledVersion(', 1)[1].split('function Invoke-Launch(', 1)[0]
        self.assertIn('$expected.Version -ne $Installed.Version', guard)
        self.assertIn('INSTALLED_BUILD_MISMATCH', guard)
        self.assertIn('File-Hash', guard)

    def test_diagnostics_are_bounded_selected_logs_not_a_private_profile_dump(self):
        text = (ROOT / 'installer/bat/Reworkl-Bat.ps1').read_text(encoding='utf-8-sig')
        body = text.split('function Export-StartupDiagnostics(', 1)[1].split('function Invoke-Start2026(', 1)[0]
        self.assertIn("@('system','setup','error')", body)
        self.assertIn('$stream.Length - 1048576', body)
        self.assertIn('LastWriteTimeUtc', body)
        self.assertIn('Assert-PlainPath $path', body)
        self.assertNotIn('Get-ChildItem', body)
        self.assertNotIn('mods_registry.json', body)
        self.assertNotIn('dlc_load.json', body)
        self.assertNotIn('Copy-Item', body)

    def test_new_payload_contains_both_filename_shadows(self):
        paths = {p.relative_to(ROOT).as_posix() for p in source_files()}
        self.assertIn('common/bookmarks/blitzkrieg.txt', paths)
        self.assertIn('common/bookmarks/the_gathering_storm.txt', paths)


if __name__ == '__main__':
    unittest.main()
