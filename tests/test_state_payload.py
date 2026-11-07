"""Offline provenance/packaging checks for the installer state repair."""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_mod import BAT_HELPERS, RELEASE_HELPERS, FIX_GUIDE, build_installer_fix, helper_path, source_files
from build_state_payload import BUNDLE_PATH, CHECKSUM_PATH, BUNDLE_DOWNLOAD, MANIFEST_PATH, state_manifest, manifest_bytes


class StatePayloadTests(unittest.TestCase):
    def test_checked_in_manifest_matches_reviewed_source_and_complete_payload(self):
        raw = (ROOT / MANIFEST_PATH).read_bytes()
        self.assertEqual(raw, manifest_bytes(state_manifest(ROOT)))
        data = json.loads(raw)
        self.assertEqual(len(data['files']), 1255)
        self.assertEqual(set(data['payload_paths']), {p.relative_to(ROOT).as_posix() for p in source_files()})
        self.assertNotIn('assets/world_2026/states.zip', data['payload_paths'])

    def test_recovery_contains_only_exact_states_manifest_and_legal_notices(self):
        manifest = json.loads((ROOT / MANIFEST_PATH).read_bytes())
        expected = {record['path'] for record in manifest['files']}
        with zipfile.ZipFile(ROOT / BUNDLE_PATH) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), expected | {'manifest.json', 'LICENSE.txt', 'ATTRIBUTION.txt'})
            self.assertEqual(len(archive.infolist()), 1258)
            self.assertEqual(archive.read('manifest.json'), (ROOT / MANIFEST_PATH).read_bytes())
            for record in manifest['files']:
                data = archive.read(record['path'])
                self.assertEqual(data, (ROOT / record['path']).read_bytes())
                self.assertEqual(len(data), record['size'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
            self.assertIn(b'Attribution-ShareAlike', archive.read('LICENSE.txt'))
            self.assertIn(b'Millennium', archive.read('ATTRIBUTION.txt'))
        sidecar = (ROOT / CHECKSUM_PATH).read_text(encoding='ascii').split()
        self.assertEqual(sidecar, [hashlib.sha256((ROOT / BUNDLE_PATH).read_bytes()).hexdigest(), BUNDLE_DOWNLOAD])

    def test_both_installer_repair_is_small_deterministic_and_has_no_game_rasters(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fix.zip'
            build_installer_fix(path)
            first = path.read_bytes()
            build_installer_fix(path)
            self.assertEqual(first, path.read_bytes())
            self.assertLess(len(first), 1024 * 1024)
            with zipfile.ZipFile(BytesIO(first)) as archive:
                self.assertEqual(set(archive.namelist()), set(BAT_HELPERS) | set(RELEASE_HELPERS) | {FIX_GUIDE})
                self.assertIsNone(archive.testzip())
                for name in archive.namelist():
                    self.assertEqual(archive.read(name), helper_path(name).read_bytes())
                self.assertFalse(any(name.startswith('reworkl/') or name.endswith(('.bmp', '.ogg', '.dds')) for name in archive.namelist()))
                self.assertIn('Alpha2', archive.read(FIX_GUIDE).decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
