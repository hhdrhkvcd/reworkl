from __future__ import annotations

import hashlib
from http import HTTPStatus
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from website.server import DownloadFile, DownloadHandler, DownloadServer, Release, byte_range
from website.download_assets import prepare_windows_files
from build_mod import build_bat_toolkit, build_installer_fix, FIX_FILENAME as INSTALLER_FIX_FILENAME
from build_russian_patch import PATCH_FILENAME, PATCH_REVISION, build_patch, russian_files
from build_russian_fix import FIX_FILENAME, FIX_REVISION, build_fix, ENGLISH_COMPAT


class ByteRangeTests(unittest.TestCase):
    def test_closed_open_suffix_and_clamped_ranges(self):
        for header, result in [('bytes=0-9', (0, 9)), ('bytes=9-', (9, 99)), ('bytes=-5', (95, 99)), ('bytes=5-200', (5, 99)), ('bytes=-200', (0, 99))]:
            with self.subTest(header=header):
                self.assertEqual(byte_range(header, 100), result)

    def test_unsatisfiable_and_multiple_ranges_are_rejected(self):
        for header in ['bytes=100-', 'bytes=9-2', 'bytes=-0', 'bytes=-', 'lines=0-1', 'bytes=0-1,4-5']:
            with self.subTest(header=header), self.assertRaises(ValueError):
                byte_range(header, 100)


class WebsiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.archive = Path(cls.temporary.name) / 'reworkl-test.zip'
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as package:
            package.writestr('reworkl/descriptor.mod', 'name="Reworkl"\n')
            package.writestr('reworkl.mod', 'path="mod/reworkl"\n')
        cls.payload = buffer.getvalue()
        cls.archive.write_bytes(cls.payload)
        cls.release = Release.read(cls.archive, '1.2.0-test')
        cls.toolkit_path = Path(cls.temporary.name) / 'activation-tools.zip'
        cls.toolkit_payload = b'PK-test-small-toolkit'
        cls.toolkit_path.write_bytes(cls.toolkit_payload)
        cls.toolkit = Release.read(cls.toolkit_path, 'test')
        cls.windows = prepare_windows_files(Path(__file__).resolve().parents[1], Path(cls.temporary.name) / 'windows')
        cls.bat_path = Path(cls.temporary.name) / 'reworkl-bat-nodlc.zip'
        build_bat_toolkit(cls.bat_path)
        cls.russian_path = Path(cls.temporary.name) / PATCH_FILENAME
        build_patch(cls.russian_path)
        cls.fix_path = Path(cls.temporary.name) / FIX_FILENAME
        build_fix(cls.fix_path)
        cls.installer_fix_path = Path(cls.temporary.name) / INSTALLER_FIX_FILENAME
        build_installer_fix(cls.installer_fix_path)
        cls.extra_files = {
            '/download/' + INSTALLER_FIX_FILENAME: DownloadFile(Release.read(cls.installer_fix_path, cls.windows.current_version), INSTALLER_FIX_FILENAME, 'application/zip'),
            '/download/reworkl-russian-fix-2.zip': DownloadFile(Release.read(cls.fix_path, FIX_REVISION), FIX_FILENAME, 'application/zip'),
            '/download/reworkl-russian-localisation.zip': DownloadFile(Release.read(cls.russian_path, f'RU-{PATCH_REVISION}'), PATCH_FILENAME, 'application/zip'),
            '/download/reworkl-bat-nodlc.zip': DownloadFile(Release.read(cls.bat_path, cls.windows.current_version), f'reworkl-bat-nodlc-{cls.windows.current_version}.zip', 'application/zip'),
            '/download/reworkl.mod': DownloadFile(Release.read(cls.windows.legacy, '1.2.0'), 'reworkl.mod', 'text/plain; charset=utf-8'),
            '/download/reworkl-current.mod': DownloadFile(Release.read(cls.windows.current, cls.windows.current_version), 'reworkl.mod', 'text/plain; charset=utf-8'),
            '/download/reworkl-windows-ascii-files.zip': DownloadFile(Release.read(cls.windows.bundle, cls.windows.current_version), cls.windows.bundle.name, 'application/zip'),
            '/windows-path.txt': DownloadFile(Release.read(cls.windows.instructions, cls.windows.current_version), 'INSTALL_WINDOWS_ASCII_RU.txt', 'text/plain; charset=utf-8'),
        }
        cls.logs = patch.object(DownloadHandler, 'log_message')
        cls.logs.start()
        cls.server = DownloadServer(('127.0.0.1', 0), cls.release, toolkit=cls.toolkit, files=cls.extra_files)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.logs.stop()
        cls.temporary.cleanup()

    def request(self, route, method='GET', headers=None):
        request = Request(self.origin + route, method=method, headers=headers or {})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_homepage_has_real_download_and_no_unresolved_tokens(self):
        status, headers, data = self.request('/')
        self.assertEqual(status, HTTPStatus.OK)
        html = data.decode()
        self.assertIn('Мир.', html)
        self.assertIn(self.release.url, html)
        self.assertIn(self.release.sha256, html)
        self.assertNotIn('{{', html)
        self.assertIn('1.2.0-test', html)
        self.assertIn('text/html', headers['Content-Type'])
        self.assertNotIn('X-Frame-Options', headers)
        self.assertNotIn('frame-ancestors', headers['Content-Security-Policy'])

    def test_modern_release_metadata_is_honest_about_scope_and_engine_status(self):
        data = Release.read(self.archive, '2.0.0-alpha1').metadata()
        self.assertEqual(data['start_date'], '2026.1.1')
        self.assertEqual(data['world_states'], 1255)
        self.assertEqual(data['world_entities'], 198)
        self.assertEqual(data['release_stage'], 'alpha')
        self.assertFalse(data['engine_tested'])

    def test_world_policy_and_real_data_preview_are_public_without_exposing_repo(self):
        status, headers, text = self.request('/world-2026.txt')
        self.assertEqual(status, 200)
        self.assertIn('text/plain', headers['Content-Type'])
        self.assertIn('НЕ реконструкция военных линий фронта', text.decode())
        status, headers, image = self.request('/assets/world-2026-preview.webp')
        self.assertEqual(status, 200)
        self.assertIn('image/webp', headers['Content-Type'])
        self.assertTrue(image.startswith(b'RIFF'))

    def test_preview_host_is_accepted(self):
        status, _, _ = self.request('/', headers={'Host': '3000-example.e2b.app'})
        self.assertEqual(status, 200)

    def test_static_assets_have_correct_types(self):
        for route, kind in [('/styles.css', 'text/css'), ('/app.js', 'text/javascript'), ('/assets/balkans.svg', 'image/svg+xml'), ('/assets/manrope.ttf', 'font/ttf'), ('/assets/loading-belgrade.jpg', 'image/jpeg'), ('/assets/loading-mountains.jpg', 'image/jpeg'), ('/assets/loading-headquarters.jpg', 'image/jpeg')]:
            with self.subTest(route=route):
                status, headers, data = self.request(route)
                self.assertEqual(status, 200)
                self.assertIn(kind, headers['Content-Type'])
                self.assertGreater(len(data), 0)

    def test_api_metadata_matches_archive(self):
        status, _, body = self.request('/api/release')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['sha256'], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(data['size_bytes'], len(self.payload))
        self.assertEqual(data['download_url'], self.release.url)
        self.assertEqual(data['loading_screens'], 3)
        self.assertFalse(data['engine_tested'])

    def test_full_download_is_attachment_with_exact_archive_bytes(self):
        status, headers, body = self.request(self.release.url)
        self.assertEqual(status, 200)
        self.assertEqual(body, self.payload)
        self.assertEqual(int(headers['Content-Length']), len(self.payload))
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertIn('attachment;', headers['Content-Disposition'])
        self.assertIn(self.archive.name, headers['Content-Disposition'])
        self.assertEqual(headers['Accept-Ranges'], 'bytes')

    def test_head_has_download_headers_but_no_body(self):
        status, headers, body = self.request(self.release.url, method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(int(headers['Content-Length']), len(self.payload))

    def test_resumed_download_has_correct_content_range(self):
        for value, start, end in [('bytes=0-15', 0, 15), ('bytes=7-', 7, len(self.payload) - 1), ('bytes=-12', len(self.payload) - 12, len(self.payload) - 1)]:
            with self.subTest(value=value):
                status, headers, body = self.request(self.release.url, headers={'Range': value})
                self.assertEqual(status, 206)
                self.assertEqual(body, self.payload[start:end + 1])
                self.assertEqual(headers['Content-Range'], f'bytes {start}-{end}/{len(self.payload)}')
                self.assertEqual(int(headers['Content-Length']), end - start + 1)

    def test_invalid_range_returns_416_without_body(self):
        status, headers, body = self.request(self.release.url, headers={'Range': 'bytes=999999-'})
        self.assertEqual(status, 416)
        self.assertEqual(headers['Content-Range'], f'bytes */{len(self.payload)}')
        self.assertEqual(body, b'')

    def test_if_range_mismatch_returns_full_file(self):
        status, _, body = self.request(self.release.url, headers={'Range': 'bytes=0-1', 'If-Range': '"outdated"'})
        self.assertEqual(status, 200)
        self.assertEqual(body, self.payload)

    def test_matching_etag_returns_304(self):
        status, _, body = self.request(self.release.url, headers={'If-None-Match': '"' + self.release.sha256 + '"'})
        self.assertEqual(status, 304)
        self.assertEqual(body, b'')

    def test_small_activation_toolkit_is_a_separate_attachment(self):
        for route in ('/repair', self.toolkit.url):
            with self.subTest(route=route):
                status, headers, body = self.request(route)
                self.assertEqual(status, 200)
                self.assertEqual(body, self.toolkit_payload)
                self.assertEqual(int(headers['Content-Length']), len(self.toolkit_payload))
                self.assertIn(self.toolkit_path.name, headers['Content-Disposition'])
                self.assertEqual(headers['ETag'], '"' + self.toolkit.sha256 + '"')

    def test_toolkit_head_and_range_use_its_own_size(self):
        status, headers, body = self.request('/repair', method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(int(headers['Content-Length']), len(self.toolkit_payload))
        status, headers, body = self.request('/repair', headers={'Range': 'bytes=0-3'})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.toolkit_payload[:4])
        self.assertEqual(headers['Content-Range'], f'bytes 0-3/{len(self.toolkit_payload)}')

    def test_both_windows_descriptor_buttons_download_exactly_reworkl_mod(self):
        for route, version in [('/download/reworkl.mod', '1.2.0'), ('/download/reworkl-current.mod', self.windows.current_version)]:
            with self.subTest(version=version):
                status, headers, body = self.request(route)
                self.assertEqual(status, 200)
                self.assertIn('filename="reworkl.mod";', headers['Content-Disposition'])
                self.assertEqual(headers['Content-Type'], 'text/plain; charset=utf-8')
                self.assertEqual(headers['Cache-Control'], 'no-cache')
                self.assertEqual(body, self.extra_files[route].release.path.read_bytes())
                self.assertIn(f'version="{version}"'.encode(), body)
                self.assertIn(b'path="C:/HOI4Mods/reworkl"', body)
                self.assertTrue(body.isascii())

    def test_windows_download_api_hashes_and_versions_match_each_file(self):
        status, _, body = self.request('/api/release')
        self.assertEqual(status, 200)
        metadata = json.loads(body)['additional_downloads']
        self.assertEqual(set(metadata), set(self.extra_files))
        self.assertEqual(metadata['/download/reworkl.mod']['version'], '1.2.0')
        for route, item in self.extra_files.items():
            self.assertEqual(metadata[route]['filename'], item.filename)
            self.assertEqual(metadata[route]['sha256'], hashlib.sha256(item.release.path.read_bytes()).hexdigest())
            self.assertEqual(metadata[route]['size_bytes'], item.release.path.stat().st_size)

    def test_windows_descriptor_head_range_and_etag_are_correct(self):
        status, headers, body = self.request('/download/reworkl.mod', method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(int(headers['Content-Length']), self.windows.legacy.stat().st_size)
        etag = headers['ETag']
        status, headers, body = self.request('/download/reworkl.mod', headers={'Range': 'bytes=0-12'})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.windows.legacy.read_bytes()[:13])
        self.assertEqual(headers['Content-Range'], f'bytes 0-12/{self.windows.legacy.stat().st_size}')
        status, _, body = self.request('/download/reworkl.mod', headers={'If-None-Match': etag})
        self.assertEqual(status, 304)
        self.assertEqual(body, b'')

    def test_no_dlc_bat_kit_is_a_real_small_attachment(self):
        status, headers, body = self.request('/download/reworkl-bat-nodlc.zip')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertEqual(headers['Cache-Control'], 'no-cache')
        self.assertIn(f'filename="reworkl-bat-nodlc-{self.windows.current_version}.zip"', headers['Content-Disposition'])
        self.assertEqual(body, self.bat_path.read_bytes())
        self.assertLess(len(body), 1024 * 1024)

    def test_installer_state_fix_is_small_and_linked_separately_from_the_full_mod(self):
        status, headers, body = self.request('/download/' + INSTALLER_FIX_FILENAME)
        self.assertEqual(status, 200)
        self.assertEqual(body, self.installer_fix_path.read_bytes())
        self.assertIn('filename="' + INSTALLER_FIX_FILENAME + '"', headers['Content-Disposition'])
        self.assertLess(len(body), 1024 * 1024)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIn('Reworkl-World.ps1', archive.namelist())
            self.assertIn('Reworkl-World-States.zip', archive.namelist())
            self.assertIn('Install-Reworkl.ps1', archive.namelist())
            self.assertNotIn('reworkl/descriptor.mod', archive.namelist())
        status, _, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('data-installer-fix', body.decode())
        self.assertNotIn('{{INSTALLER_FIX_SIZE}}', body.decode())

    def test_ru2_updater_download_includes_english_compat_without_replacing_the_full_mod(self):
        status, headers, body = self.request('/download/reworkl-russian-fix-2.zip')
        self.assertEqual(status, 200)
        self.assertEqual(body, self.fix_path.read_bytes())
        self.assertIn(f'filename="{FIX_FILENAME}"', headers['Content-Disposition'])
        self.assertEqual(headers['Cache-Control'], 'no-cache')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(len(archive.namelist()), 12)
            self.assertIn('APPLY_RUSSIAN.bat', archive.namelist())
            self.assertTrue(archive.read(ENGLISH_COMPAT).startswith(b'\xef\xbb\xbfl_english:'))
            self.assertNotIn('2_LAUNCH.bat', archive.namelist())
            self.assertNotIn('descriptor.mod', archive.namelist())
        status, _, html = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('data-russian-fix', html.decode())
        self.assertNotIn('{{RU_FIX_SIZE}}', html.decode())
        self.assertIn('Само базовое меню HOI4', html.decode())

    def test_russian_patch_is_a_localisation_only_download(self):
        status, headers, body = self.request('/download/reworkl-russian-localisation.zip')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertEqual(headers['Cache-Control'], 'no-cache')
        self.assertIn(f'filename="{PATCH_FILENAME}"', headers['Content-Disposition'])
        self.assertEqual(body, self.russian_path.read_bytes())
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()), len(russian_files()) + 1)
            self.assertTrue(all(name == 'INSTALL_RUSSIAN.txt' or name.startswith('localisation/') for name in archive.namelist()))
        status, _, html = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('Только русский текст', html.decode())
        self.assertIn('id="russian"', html.decode())
        self.assertNotIn('{{RU_PATCH_SIZE}}', html.decode())

    def test_windows_zip_and_guide_download_with_their_own_types(self):
        for route, kind in [('/download/reworkl-windows-ascii-files.zip', 'application/zip'), ('/windows-path.txt', 'text/plain; charset=utf-8')]:
            with self.subTest(route=route):
                status, headers, body = self.request(route)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], kind)
                self.assertEqual(body, self.extra_files[route].release.path.read_bytes())
                self.assertIn('attachment;', headers['Content-Disposition'])

    def test_updated_page_links_all_new_files_and_labels_the_versions(self):
        status, _, body = self.request('/')
        self.assertEqual(status, 200)
        html = body.decode()
        self.assertIn('id="files"', html)
        self.assertIn('1.2.0', html)
        self.assertIn(self.windows.current_version, html)
        for route in self.extra_files:
            self.assertIn(f'href="{route}"', html)
        self.assertNotIn('{{', html)
        self.assertIn('reworkl (1).mod', html)

    def test_download_alias_and_guide_are_available(self):
        status, _, body = self.request('/download')
        self.assertEqual(status, 200)
        self.assertEqual(body, self.payload)
        status, headers, body = self.request('/installation.txt')
        self.assertEqual(status, 200)
        self.assertIn('attachment;', headers['Content-Disposition'])
        self.assertIn('reworkl.mod', body.decode())

    def test_repository_files_and_path_traversal_are_not_exposed(self):
        for route in ['/.git/config', '/descriptor.mod', '/website/server.py', '/website/download_assets.py', '/downloads/reworkl-1.2.0-windows-ascii.mod', '/releases/local-registration/Yugoslavia_1989_FIXED.mod', '/releases/reworkl-test.zip', '/assets/../server.py', '/assets/%2e%2e/server.py', '/assets/%00', '/does-not-exist']:
            with self.subTest(route=route):
                status, _, _ = self.request(route)
                self.assertEqual(status, 404)

    def test_missing_archive_returns_useful_error_and_unhealthy_status(self):
        moved = self.archive.with_suffix('.backup')
        self.archive.rename(moved)
        try:
            status, _, body = self.request(self.release.url)
            self.assertEqual(status, 503)
            self.assertIn('недоступен', body.decode())
            status, _, _ = self.request('/healthz')
            self.assertEqual(status, 503)
        finally:
            moved.rename(self.archive)
        status, _, _ = self.request('/healthz')
        self.assertEqual(status, 200)


if __name__ == '__main__':
    unittest.main()
