#!/usr/bin/env python3
"""Reworkl download website. Python 3.10+, no third-party runtime dependencies.

The document root is deliberately NOT the repository. Only public website
assets, the installation guide and the selected ZIP are served. Download
responses support HEAD, byte ranges and streaming for interrupted transfers.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from email.utils import formatdate
import hashlib
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit

if __package__:
    from .download_assets import prepare_windows_files
else:
    from download_assets import prepare_windows_files

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Release:
    path: Path
    version: str
    size: int
    sha256: str
    modified: str

    @classmethod
    def read(cls, path: Path, version: str) -> Release:
        checksum = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                checksum.update(chunk)
        stat = path.stat()
        return cls(path.resolve(), version, stat.st_size, checksum.hexdigest(), formatdate(stat.st_mtime, usegmt=True))

    @property
    def url(self) -> str:
        return '/download/' + quote(self.path.name)

    def metadata(self) -> dict:
        return {
            'name': 'Reworkl — Мир 2026, Сербия и Turbo-folk' if self.version.startswith('2.') else 'Reworkl — Югославия, Сербия и Turbo-folk',
            'version': self.version,
            'filename': self.path.name,
            'size_bytes': self.size,
            'sha256': self.sha256,
            'download_url': self.url,
            'supported_game_version': '1.19.x',
            'music_tracks': 23,
            'loading_screens': 3,
            'campaigns': 2,
            'engine_tested': False,
            'start_date': '2026.1.1' if self.version.startswith('2.') else '1989.1.1',
            'world_states': 1255 if self.version.startswith('2.') else 213,
            'world_entities': 198 if self.version.startswith('2.') else None,
            'release_stage': 'alpha' if self.version.startswith('2.') else 'legacy',
        }


@dataclass(frozen=True)
class DownloadFile:
    release: Release
    filename: str
    content_type: str

    def metadata(self) -> dict:
        return {
            'version': self.release.version,
            'filename': self.filename,
            'content_type': self.content_type,
            'size_bytes': self.release.size,
            'sha256': self.release.sha256,
        }


def byte_range(header: str, size: int) -> tuple[int, int]:
    """Resolve a single inclusive HTTP byte range, or raise ValueError."""
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip())
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError('Unsupported or empty byte range')
    first, last = match.groups()
    if not first:
        count = int(last)
        if count <= 0:
            raise ValueError('Empty suffix range')
        return max(0, size - count), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable byte range')
    return start, end


class DownloadServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], release: Release, site: Path = SITE, toolkit: Release | None = None, files: dict[str, DownloadFile] | None = None):
        self.release = release
        self.toolkit = toolkit
        self.files = dict(files or {})
        self.site = site.resolve()
        super().__init__(address, DownloadHandler)


class DownloadHandler(BaseHTTPRequestHandler):
    server_version = 'Reworkl'
    sys_version = ''

    def end_headers(self) -> None:
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        # No frame-ancestors / X-Frame-Options: the Arena live preview embeds
        # this page on a different origin. No external fonts/CDN are required.
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'")
        super().end_headers()

    def do_HEAD(self) -> None:
        self.route(head=True)

    def do_GET(self) -> None:
        self.route(head=False)

    def body(self, data: bytes, content_type: str, head: bool, status: int = 200, attachment: str | None = None) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        if attachment:
            self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        if not head:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def not_found(self, head: bool) -> None:
        self.body('Страница не найдена. Вернуться на сайт: /\n'.encode(), 'text/plain; charset=utf-8', head, HTTPStatus.NOT_FOUND)

    def route(self, head: bool) -> None:
        try:
            path = unquote(urlsplit(self.path).path)
        except (ValueError, UnicodeError):
            self.not_found(head)
            return
        if '\x00' in path:
            self.not_found(head)
            return
        release = self.server.release
        legacy = self.server.files.get('/download/reworkl.mod')
        current = self.server.files.get('/download/reworkl-current.mod')
        windows_zip = self.server.files.get('/download/reworkl-windows-ascii-files.zip')
        bat_tools = self.server.files.get('/download/reworkl-bat-nodlc.zip')
        russian_patch = self.server.files.get('/download/reworkl-russian-localisation.zip')
        russian_fix = self.server.files.get('/download/reworkl-russian-fix-2.zip')
        if path in ('/', '/index.html'):
            html = (self.server.site / 'index.html').read_text(encoding='utf-8')
            values = {
                'VERSION': release.version,
                'SIZE': f'{release.size / 1_000_000:.1f}'.replace('.', ','),
                'DOWNLOAD_URL': release.url,
                'SHA256': release.sha256,
                'LEGACY_DESCRIPTOR_SIZE': str(legacy.release.size) if legacy else '—',
                'CURRENT_DESCRIPTOR_SIZE': str(current.release.size) if current else '—',
                'CURRENT_DESCRIPTOR_VERSION': current.release.version if current else release.version,
                'BAT_TOOLS_SIZE': f'{bat_tools.release.size / 1000:.1f}'.replace('.', ',') if bat_tools else '—',
                'RU_PATCH_SIZE': f'{russian_patch.release.size / 1000:.1f}'.replace('.', ',') if russian_patch else '—',
                'RU_FIX_SIZE': f'{russian_fix.release.size / 1000:.1f}'.replace('.', ',') if russian_fix else '—',
                'WINDOWS_PACKAGE_SIZE': f'{windows_zip.release.size / 1000:.1f}'.replace('.', ',') if windows_zip else '—',
            }
            for key, value in values.items():
                html = html.replace('{{' + key + '}}', escape(value, quote=True))
            self.body(html.encode(), 'text/html; charset=utf-8', head)
        elif path == '/api/release':
            metadata = release.metadata()
            metadata['additional_downloads'] = {url: item.metadata() for url, item in self.server.files.items()}
            self.body(json.dumps(metadata, ensure_ascii=False).encode(), 'application/json; charset=utf-8', head)
        elif path == '/healthz':
            available = release.path.is_file()
            self.body(json.dumps({'status': 'ok' if available else 'unavailable'}).encode(), 'application/json; charset=utf-8', head, 200 if available else 503)
        elif path in (release.url, '/download'):
            self.download(head)
        elif self.server.toolkit and path in (self.server.toolkit.url, '/repair'):
            self.download(head, self.server.toolkit)
        elif path in self.server.files:
            item = self.server.files[path]
            self.download(head, item.release, content_type=item.content_type, filename=item.filename)
        elif path == '/world-2026.txt':
            self.body((ROOT / 'WORLD_2026_RU.txt').read_bytes(), 'text/plain; charset=utf-8', head)
        elif path == '/installation.txt':
            guide = ROOT / 'docs/INSTALL.md'
            self.body(guide.read_bytes(), 'text/plain; charset=utf-8', head, attachment='Reworkl-installation.txt')
        elif path in ('/styles.css', '/app.js') or path.startswith('/assets/'):
            # Resolve before checking the root, including percent-encoded
            # traversal and symlinks. No arbitrary repository files are public.
            candidate = (self.server.site / path.lstrip('/')).resolve()
            assets = (self.server.site / 'assets').resolve()
            allowed = candidate in {self.server.site / 'styles.css', self.server.site / 'app.js'} or candidate.is_relative_to(assets)
            if '\x00' in path or '..' in path.split('/') or not allowed or not candidate.is_file():
                self.not_found(head)
                return
            kind = {
                '.css': 'text/css; charset=utf-8',
                '.js': 'text/javascript; charset=utf-8',
                '.svg': 'image/svg+xml',
                '.ttf': 'font/ttf',
            }.get(candidate.suffix, mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream')
            self.body(candidate.read_bytes(), kind, head)
        else:
            self.not_found(head)

    def download(self, head: bool, release: Release | None = None, *, content_type: str = 'application/zip', filename: str | None = None) -> None:
        release = release or self.server.release
        if not release.path.is_file():
            self.body('Архив временно недоступен. Перезагрузите страницу позже.\n'.encode(), 'text/plain; charset=utf-8', head, 503)
            return
        etag = '"' + release.sha256 + '"'
        if self.headers.get('If-None-Match') == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header('ETag', etag)
            self.end_headers()
            return
        start, end = 0, release.size - 1
        status = HTTPStatus.OK
        requested = self.headers.get('Range')
        if_range = self.headers.get('If-Range')
        if requested and (not if_range or if_range in (etag, release.modified)):
            try:
                start, end = byte_range(requested, release.size)
                status = HTTPStatus.PARTIAL_CONTENT
            except ValueError:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header('Content-Range', f'bytes */{release.size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        remaining = end - start + 1
        self.send_response(status)
        download_name = filename or release.path.name
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Disposition', f'attachment; filename="{download_name}"; filename*=UTF-8\'\'{quote(download_name)}')
        self.send_header('Content-Length', str(remaining))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('ETag', etag)
        self.send_header('Last-Modified', release.modified)
        self.send_header('Cache-Control', 'public, max-age=3600' if release is self.server.release else 'no-cache')
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header('Content-Range', f'bytes {start}-{end}/{release.size}')
        self.end_headers()
        if head:
            return
        try:
            with release.path.open('rb') as source:
                source.seek(start)
                while remaining:
                    block = source.read(min(256 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError):
            # Cancelling a download is normal, not a server error.
            pass


def main() -> None:
    sys.path.insert(0, str(ROOT / 'scripts'))
    from build_russian_patch import PATCH_FILENAME, PATCH_REVISION, build_patch
    from build_russian_fix import FIX_FILENAME, FIX_REVISION, build_fix

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '3000')))
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    descriptor = (ROOT / 'descriptor.mod').read_text(encoding='utf-8')
    match = re.search(r'^version="([\w.\-]+)"', descriptor, re.M)
    if not match:
        parser.error('No version found in descriptor.mod')
    version = match[1]
    archive = ROOT / 'releases' / f'reworkl-{version}.zip'
    if not archive.is_file():
        print('Preparing the downloadable mod archive…', flush=True)
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_mod.py'), '--output', str(archive)], check=True, cwd=ROOT)
    toolkit_path = ROOT / 'releases/reworkl-activation-tools.zip'
    if not toolkit_path.is_file():
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_mod.py'), '--tools-only'], check=True, cwd=ROOT)
    bat_path = ROOT / 'releases/reworkl-bat-nodlc.zip'
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_mod.py'), '--bat-only'], check=True, cwd=ROOT)
    russian_path = ROOT / 'releases' / PATCH_FILENAME
    if not russian_path.is_file():
        build_patch(russian_path)
    fix_path = ROOT / 'releases' / FIX_FILENAME
    if not fix_path.is_file():
        build_fix(fix_path)
    release = Release.read(archive, version)
    toolkit = Release.read(toolkit_path, version)
    windows = prepare_windows_files(ROOT)
    text_type = 'text/plain; charset=utf-8'
    files = {
        '/download/reworkl-russian-fix-2.zip': DownloadFile(Release.read(fix_path, FIX_REVISION), FIX_FILENAME, 'application/zip'),
        '/download/reworkl-russian-localisation.zip': DownloadFile(Release.read(russian_path, f'RU-{PATCH_REVISION}'), PATCH_FILENAME, 'application/zip'),
        '/download/reworkl-bat-nodlc.zip': DownloadFile(Release.read(bat_path, version), f'reworkl-bat-nodlc-{version}.zip', 'application/zip'),
        '/download/reworkl.mod': DownloadFile(Release.read(windows.legacy, '1.2.0'), 'reworkl.mod', text_type),
        '/download/reworkl-current.mod': DownloadFile(Release.read(windows.current, windows.current_version), 'reworkl.mod', text_type),
        '/download/reworkl-windows-ascii-files.zip': DownloadFile(Release.read(windows.bundle, windows.current_version), windows.bundle.name, 'application/zip'),
        '/windows-path.txt': DownloadFile(Release.read(windows.instructions, windows.current_version), 'INSTALL_WINDOWS_ASCII_RU.txt', text_type),
    }
    server = DownloadServer((args.host, args.port), release, toolkit=toolkit, files=files)
    print(f'Reworkl website listening on {args.host}:{server.server_port}', flush=True)
    print(f'Download: {release.url} ({release.size} bytes)', flush=True)
    print('Russian fix RU2: /download/reworkl-russian-fix-2.zip (English/Russian mod text + updater)', flush=True)
    print('Russian translation: /download/reworkl-russian-localisation.zip (localisation only)', flush=True)
    print('Updated Windows files: /download/reworkl.mod and /download/reworkl-current.mod', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
