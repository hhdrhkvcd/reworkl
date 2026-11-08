#!/usr/bin/env python3
"""Small standalone read-only collector; no mod reinstall or game binaries."""
from pathlib import Path
import argparse
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILENAME = 'reworkl-crash-diagnostics-1.zip'
HELPERS = ('COLLECT_REWORKL_CRASH.bat', 'Reworkl-Crash-Diagnostics.ps1', 'CRASH_DIAGNOSTICS_RU.txt')
STANDALONE_FILENAME = 'COLLECT_REWORKL_CRASH.bat'
STANDALONE_MARKER = '::REWORKL_EMBEDDED_POWERSHELL::'


def build_standalone(output: Path, root: Path = ROOT):
    """One visible, readable BAT: run the exact collector, without sidecars.

    The batch preamble exits before the embedded PowerShell section. The child
    interpreter reads this file as UTF-8 and receives the output directory as a
    value, never as interpolated executable code. No encoded/remote code or
    additional bootstrap extraction is needed.
    """
    body = (root / 'installer/diagnostics/Reworkl-Crash-Diagnostics.ps1').read_text(encoding='utf-8-sig')
    if STANDALONE_MARKER in body:
        raise ValueError('Embedded collector unexpectedly contains the BAT section marker')
    command = (
        'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command '
        '"$self=$env:REWORKL_CRASH_SELF;'
        '$text=[IO.File]::ReadAllText($self,[Text.Encoding]::UTF8);'
        f"$marker='{STANDALONE_MARKER}';"
        '$index=$text.LastIndexOf($marker,[StringComparison]::Ordinal);'
        "if($index -lt 0){throw 'Collector section is missing'};"
        '& ([scriptblock]::Create($text.Substring($index+$marker.Length))) '
        '-OutputDir ([IO.Path]::GetDirectoryName($self))"'
    )
    # CMD has an 8191-character command limit. No payload or user path is put
    # onto the command line; paths with spaces, Cyrillic, quotes and ! stay data.
    if len(command) >= 8000:
        raise ValueError('Standalone collector command exceeds the CMD safe limit')
    preamble = f'''@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title REWORKL - READ ONLY CRASH COLLECTION
echo REWORKL: СБОР ДИАГНОСТИКИ ВЫЛЕТА
echo Это самостоятельный файл. Распаковывать или устанавливать мод не нужно.
echo Игра не запускается. Настройки, мод и сохранения не меняются.
echo.
set "REWORKL_CRASH_SELF=%~f0"
{command}
set "REWORKL_COLLECT_RESULT=%ERRORLEVEL%"
echo.
if "%REWORKL_COLLECT_RESULT%"=="0" (
  echo ГОТОВО. Рядом с этим BAT появился НОВЫЙ архив:
  echo REWORKL_CRASH_DIAGNOSTICS_...zip
  echo Пришли этот новый ZIP, а не START_RESULT.txt и не сам BAT.
) else (
  echo Не удалось собрать отчёт. Пришли фотографию этого окна с ошибкой.
)
echo Это только диагностика, не исправление вылета.
if not defined REWORKL_NO_PAUSE pause
exit /b %REWORKL_COLLECT_RESULT%
{STANDALONE_MARKER}
'''
    content = (preamble + body).replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.reworkl-one-file-', dir=output.parent) as temp:
        staged = Path(temp) / STANDALONE_FILENAME
        staged.write_bytes(content)
        staged.replace(output)
    return output


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
    parser.add_argument('--standalone', action='store_true', help='Build a single BAT with no sidecar files or archive extraction')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / 'releases' / (STANDALONE_FILENAME if args.standalone else FILENAME)
    path = build_standalone(output) if args.standalone else build(output)
    print(f'Built {path}: {path.stat().st_size} bytes; read-only collection, not a game fix.')
