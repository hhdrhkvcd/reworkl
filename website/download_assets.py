"""Build small, public launcher downloads without repackaging game/audio data."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
import zipfile

ASCII_PAYLOAD_PATH = 'C:/HOI4Mods/reworkl'
ASCII_DISPLAY_NAME = 'Reworkl - Yugoslavia, Serbia and Turbo-folk'
LEGACY_VERSION = '1.2.0'


@dataclass(frozen=True)
class WindowsFiles:
    legacy: Path
    current: Path
    bundle: Path
    instructions: Path
    current_version: str


def descriptor_version(text: str) -> str:
    values = re.findall(r'^version="([0-9][A-Za-z0-9_.-]*)"\s*$', text, re.M)
    if len(values) != 1:
        raise ValueError('Expected exactly one safe version in descriptor')
    return values[0]


def prepare_windows_files(root: Path, output_dir: Path | None = None) -> WindowsFiles:
    """Create both explicitly labelled versions and a deterministic small ZIP.

    Only these two descriptors and a generic guide enter the public bundle.
    Personal registrations, uploaded logs and other files in releases are never
    scanned or published. Invoke before starting the HTTP server.
    """
    sources = root / 'website/downloads'
    legacy = (sources / 'reworkl-1.2.0-windows-ascii.mod').read_text(encoding='ascii')
    if descriptor_version(legacy) != LEGACY_VERSION:
        raise ValueError('Legacy download version is not 1.2.0')
    if len(re.findall(r'^path=', legacy, re.M)) != 1 or f'path="{ASCII_PAYLOAD_PATH}"' not in legacy or '```' in legacy:
        raise ValueError('Legacy descriptor has an invalid path or markup')
    internal = (root / 'descriptor.mod').read_text(encoding='utf-8')
    version = descriptor_version(internal)
    if re.search(r'^\s*(?:path|remote_file_id)\s*=', internal, re.M):
        raise ValueError('Internal descriptor must not inherit a path or Workshop ID')
    current, names = re.subn(r'^name="[^"\n]*"\s*$', f'name="{ASCII_DISPLAY_NAME}"', internal, flags=re.M)
    if names != 1:
        raise ValueError('Expected exactly one mod name')
    current = current.rstrip() + f'\npath="{ASCII_PAYLOAD_PATH}"\n'
    if not current.isascii():
        raise ValueError('The Windows launcher download must contain ASCII bytes only')
    guide = (sources / 'WINDOWS_ASCII_RU.txt').read_text(encoding='utf-8').replace('{{CURRENT_VERSION}}', version)
    if '{{' in guide:
        raise ValueError('Unresolved guide token')
    output_dir = output_dir or root / 'releases'
    output_dir.mkdir(parents=True, exist_ok=True)
    legacy_name = f'reworkl-{LEGACY_VERSION}-windows-ascii.mod'
    current_name = f'reworkl-{version}-windows-ascii.mod'
    bundle_name = 'reworkl-windows-ascii-files.zip'
    guide_name = 'reworkl-windows-ascii-instructions.txt'
    with tempfile.TemporaryDirectory(prefix='.reworkl-web-files-', dir=output_dir) as temp:
        stage = Path(temp)
        (stage / legacy_name).write_bytes(legacy.encode('ascii'))
        (stage / current_name).write_bytes(current.encode('ascii'))
        (stage / guide_name).write_text(guide, encoding='utf-8')
        variants = {LEGACY_VERSION: legacy.encode('ascii'), version: current.encode('ascii')}
        with zipfile.ZipFile(stage / bundle_name, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            items = {f'{key}/reworkl.mod': data for key, data in variants.items()}
            items['INSTALL_WINDOWS_ASCII_RU.txt'] = guide.encode('utf-8')
            for name, data in sorted(items.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        with zipfile.ZipFile(stage / bundle_name) as archive:
            if archive.testzip():
                raise ValueError('Windows files ZIP failed its CRC check')
        for name in {legacy_name, current_name, bundle_name, guide_name}:
            (stage / name).replace(output_dir / name)
    return WindowsFiles(output_dir / legacy_name, output_dir / current_name, output_dir / bundle_name, output_dir / guide_name, version)
