#!/usr/bin/env python3
"""Build a standalone ZIP; never repackage the original multipart archives."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile
import zipfile

from clausewitz import load
from validate_mod import ROOT, SOURCE_DIRS, validate

ASSET_SUFFIXES = {".txt", ".lua", ".mod", ".gfx", ".gui", ".yml", ".asset", ".dds", ".tga", ".png", ".ogg", ".bmp", ".csv", ".map"}
RELEASE_HELPERS = ("INSTALL_REWORKL.cmd", "CHECK_REWORKL.cmd", "Install-Reworkl.ps1")
BAT_HELPERS = ("0_START_2026.bat", "1_INSTALL.bat", "2_LAUNCH.bat", "3_CHECK.bat", "4_PLAN_B_USERDIR.bat", "5_RESTORE_PLAN_B.bat", "Reworkl-Bat.ps1", "BAT_NO_DLC_RU.txt")


def source_files(root: Path = ROOT) -> list[Path]:
    """Explicit payload allowlist keeps Git, archives and build output out."""
    from materialize_world_map import ensure_map_assets
    ensure_map_assets(root)
    files = [root / "descriptor.mod", root / "thumbnail.png"]
    for name in ("THIRD_PARTY.txt", "WORLD_2026_RU.txt"):
        if (root / name).is_file():
            files.append(root / name)
    files.extend((root / "licenses").glob("*.txt"))
    for dirname in SOURCE_DIRS:
        files.extend(p for p in (root / dirname).rglob("*") if p.is_file() and p.suffix in ASSET_SUFFIXES)
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Payload cannot contain symlinks or outside files: {path}")
    return sorted(files)


def copy_payload(destination: Path, root: Path = ROOT) -> int:
    files = source_files(root)
    for path in files:
        target = destination / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return len(files)


def launcher_descriptor(root: Path = ROOT, path: str = "mod/reworkl") -> str:
    # Quoted paths in Clausewitz need slash/quote escaping on every OS.
    escaped = path.replace("\\", "/").replace('"', '\\"')
    return (root / "descriptor.mod").read_text(encoding="utf-8").rstrip() + f'\npath="{escaped}"\n'


def build(output: Path, root: Path = ROOT) -> int:
    report = validate(root)
    if report.errors:
        raise ValueError("Refusing to package an invalid mod:\n" + "\n".join(report.errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    files = source_files(root)
    # Stage beside the destination; a failure cannot replace a working ZIP.
    with tempfile.TemporaryDirectory(prefix=".reworkl-build-", dir=output.parent) as temp:
        staged = Path(temp) / "reworkl.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            def add(name: str, data: bytes) -> None:
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compresslevel=6)
            for path in files:
                add("reworkl/" + path.relative_to(root).as_posix(), path.read_bytes())
            add("reworkl.mod", launcher_descriptor(root).encode("utf-8"))
            add("INSTALL_RU.md", (root / "docs/INSTALL.md").read_bytes())
            for helper in RELEASE_HELPERS:
                add(helper, (root / "installer" / helper).read_bytes())
            for helper in BAT_HELPERS:
                add(helper, (root / "installer/bat" / helper).read_bytes())
        with zipfile.ZipFile(staged) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"ZIP CRC check failed: {bad}")
        staged.replace(output)
    return len(files)



def build_toolkit(output: Path, root: Path = ROOT) -> None:
    """Small repair download for users who already have the mod payload."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reworkl-tools-", dir=output.parent) as temp:
        staged = Path(temp) / "tools.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in (*RELEASE_HELPERS, "ACTIVATION_RU.txt"):
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (root / "installer" / name).read_bytes())
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip():
                raise ValueError("Activation toolkit CRC check failed")
        staged.replace(output)


def build_bat_toolkit(output: Path, root: Path = ROOT) -> None:
    """Small no-launcher/no-DLC workflow, also usable with existing 1.2.0."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reworkl-bat-", dir=output.parent) as temp:
        staged = Path(temp) / "bat-tools.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in BAT_HELPERS:
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (root / "installer/bat" / name).read_bytes())
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip():
                raise ValueError("BAT toolkit CRC check failed")
        staged.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    version = load(ROOT / "descriptor.mod").scalar("version")
    parser.add_argument("--output", type=Path, default=ROOT / "releases" / f"reworkl-{version}.zip")
    parser.add_argument("--bat-only", action="store_true", help="Build only the small BAT / no-DLC toolkit")
    parser.add_argument("--tools-only", action="store_true", help="Build only the small Windows activation toolkit")
    args = parser.parse_args()
    try:
        bat_tools = ROOT / "releases/reworkl-bat-nodlc.zip"
        build_bat_toolkit(bat_tools)
        if args.bat_only:
            print(f"Built {bat_tools}: {bat_tools.stat().st_size} bytes")
            return 0
        tools = ROOT / "releases/reworkl-activation-tools.zip"
        build_toolkit(tools)
        if args.tools_only:
            print(f"Built {tools}: {tools.stat().st_size} bytes")
            return 0
        count = build(args.output.resolve())
    except (OSError, ValueError) as error:
        parser.exit(1, f"Build failed: {error}\n")
    print(f"Built {args.output}: {count} mod files, {args.output.stat().st_size / 1024 / 1024:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
