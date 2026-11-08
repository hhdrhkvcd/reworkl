#!/usr/bin/env python3
"""Small standalone read-only collector; no mod reinstall or game binaries."""
from pathlib import Path
import argparse
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILENAME = 'reworkl-crash-diagnostics-1.zip'
HELPERS = ('COLLECT_REWORKL_CRASH.bat', 'Reworkl-Crash-Diagnostics.ps1', 'CRASH_DIAGNOSTICS_RU.txt')


def build(output: Path, root: Path = ROOT):
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.reworkl-diagnostics-', dir=output.parent) as temp:
        staged = Path(temp) / 'diagnostics.zip'
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in HELPERS:
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 8, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (root / 'installer/diagnostics' / name).read_bytes())
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip():
                raise ValueError('Diagnostics toolkit CRC check failed')
        staged.replace(output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'releases' / FILENAME)
    args = parser.parse_args()
    path = build(args.output)
    print(f'Built {path}: {path.stat().st_size} bytes; read-only collection, not a game fix.')
