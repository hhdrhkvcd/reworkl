from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from clausewitz import load
from website.download_assets import ASCII_PAYLOAD_PATH, prepare_windows_files


class WindowsDownloadsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        sources = self.root / 'website/downloads'
        sources.mkdir(parents=True)
        shutil.copy2(ROOT / 'descriptor.mod', self.root / 'descriptor.mod')
        for name in ('reworkl-1.2.0-windows-ascii.mod', 'WINDOWS_ASCII_RU.txt'):
            shutil.copy2(ROOT / 'website/downloads' / name, sources / name)
        self.files = prepare_windows_files(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_versions_have_one_canonical_path_and_ascii_names(self):
        for path, version in [(self.files.legacy, '1.2.0'), (self.files.current, self.files.current_version)]:
            with self.subTest(version=version):
                data = path.read_bytes()
                self.assertTrue(data.isascii())
                self.assertNotIn(b'```', data)
                parsed = load(path)
                self.assertEqual(parsed.scalar('version'), version)
                self.assertEqual(parsed.scalar('path'), ASCII_PAYLOAD_PATH)
                self.assertTrue(parsed.scalar('name').isascii())
                for key in ('name', 'version', 'path'):
                    self.assertEqual(len(parsed.children(key)), 1)

    def test_current_file_preserves_current_loading_screen_registration(self):
        self.assertIn('replace_path="gfx/loadingscreens"', self.files.current.read_text())
        self.assertNotIn('replace_path="gfx/loadingscreens"', self.files.legacy.read_text())
        self.assertEqual(load(self.root / 'descriptor.mod').children('path'), [])

    def test_small_bundle_has_only_the_two_versioned_descriptors_and_guide(self):
        with zipfile.ZipFile(self.files.bundle) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {'1.2.0/reworkl.mod', f'{self.files.current_version}/reworkl.mod', 'INSTALL_WINDOWS_ASCII_RU.txt'})
            self.assertEqual(archive.read('1.2.0/reworkl.mod'), self.files.legacy.read_bytes())
            self.assertEqual(archive.read(f'{self.files.current_version}/reworkl.mod'), self.files.current.read_bytes())
            self.assertNotIn('{{', archive.read('INSTALL_WINDOWS_ASCII_RU.txt').decode())
        self.assertLess(self.files.bundle.stat().st_size, 16 * 1024)
        self.assertNotIn('C:/Users/', self.files.legacy.read_text())
        self.assertNotIn('C:/Users/', self.files.current.read_text())

    def test_build_is_deterministic(self):
        first = self.files.bundle.read_bytes()
        again = prepare_windows_files(self.root)
        self.assertEqual(again.bundle.read_bytes(), first)

    def test_internal_descriptor_with_a_path_is_rejected(self):
        with (self.root / 'descriptor.mod').open('a') as file:
            file.write('\npath="somewhere"\n')
        with self.assertRaisesRegex(ValueError, 'Internal descriptor'):
            prepare_windows_files(self.root)

    def test_invalid_legacy_path_is_rejected(self):
        source = self.root / 'website/downloads/reworkl-1.2.0-windows-ascii.mod'
        source.write_text(source.read_text().replace(ASCII_PAYLOAD_PATH, 'C:/Users/someone/private'))
        with self.assertRaisesRegex(ValueError, 'Legacy descriptor'):
            prepare_windows_files(self.root)

    def test_duplicate_version_is_rejected(self):
        with (self.root / 'descriptor.mod').open('a') as file:
            file.write('\nversion="999.0"\n')
        with self.assertRaisesRegex(ValueError, 'version'):
            prepare_windows_files(self.root)


if __name__ == '__main__':
    unittest.main()
