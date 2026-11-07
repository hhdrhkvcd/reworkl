#!/usr/bin/env python3
"""Build a compact, deterministic offline recovery payload for world states.

The Windows installers select these exact files, not an arbitrary directory
count. No map rasters, music, runtime executables or user data are included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path('map/reworkl_state_manifest.json')
BUNDLE_PATH = Path('assets/world_2026/states.zip')
CHECKSUM_PATH = Path('assets/world_2026/states.sha256')
BUNDLE_DOWNLOAD = 'Reworkl-World-States.zip'
CHECKSUM_DOWNLOAD = 'Reworkl-World-States.sha256'


def state_manifest(root: Path = ROOT) -> dict:
    states = sorted((root / 'history/states').glob('*-Reworkl.txt'), key=lambda p: int(p.name.split('-')[0]))
    if len(states) != 1255 or any(not re.fullmatch(r'[1-9][0-9]*-Reworkl\.txt', p.name) for p in states):
        raise ValueError('The reviewed source must contain all 1255 canonical world state files')
    files = []
    for path in states:
        data = path.read_bytes()
        files.append({'path': path.relative_to(root).as_posix(), 'size': len(data),
                      'sha256': hashlib.sha256(data).hexdigest()})
    # Exact payload paths also prevent unrelated old mod files from being
    # merged during a repair. Large raster/music bytes are NOT duplicated.
    from validate_mod import SOURCE_DIRS
    from materialize_world_map import NAMES
    suffixes = {'.txt','.lua','.mod','.gfx','.gui','.yml','.asset','.dds','.tga','.png','.ogg','.bmp','.csv','.map'}
    payload = {'descriptor.mod', 'thumbnail.png', MANIFEST_PATH.as_posix()}
    for directory in (*SOURCE_DIRS, 'licenses'):
        payload.update(p.relative_to(root).as_posix() for p in (root / directory).rglob('*') if p.is_file() and p.suffix in suffixes)
    payload.update('map/' + name for name in NAMES)
    payload.update(name for name in ('THIRD_PARTY.txt', 'WORLD_2026_RU.txt') if (root / name).is_file())
    return {
        'schema': 1, 'scenario': 'world_2026', 'expected_count': 1255,
        'world_manifest_sha256': hashlib.sha256((root / 'map/reworkl_world_manifest.txt').read_bytes()).hexdigest(),
        'source': 'Millennium Dawn c5143e00268ee9125accefc7130066989de89bce; modified for Reworkl',
        'license': 'CC-BY-SA-4.0; see LICENSE.txt and ATTRIBUTION.txt in the recovery ZIP',
        'files': files, 'payload_paths': sorted(payload),
    }


def manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, ensure_ascii=True, indent=2) + '\n').encode('utf-8')


def build_state_payload(root: Path = ROOT) -> tuple[Path, Path]:
    raw = manifest_bytes(state_manifest(root))
    (root / MANIFEST_PATH).write_bytes(raw)
    output = root / BUNDLE_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            def add(name: str, data: bytes):
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                z.writestr(info, data, compresslevel=6)
            add('manifest.json', raw)
            for item in json.loads(raw)['files']:
                add(item['path'], (root / item['path']).read_bytes())
            add('LICENSE.txt', (root / 'licenses/Millennium-Dawn-CC-BY-SA-4.0.txt').read_bytes())
            add('ATTRIBUTION.txt', (root / 'THIRD_PARTY.txt').read_bytes())
        with zipfile.ZipFile(temporary) as z:
            if z.testzip() is not None:
                raise ValueError('World state recovery payload failed CRC validation')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = root / CHECKSUM_PATH
    checksum.write_text(hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + BUNDLE_DOWNLOAD + '\n', encoding='ascii')
    return output, checksum


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    bundle, checksum = build_state_payload()
    print(f'{bundle}: {bundle.stat().st_size} bytes, 1255 exact states + manifest + attribution')
    print(checksum.read_text().strip())
