#!/usr/bin/env python3
"""Build a deterministic, localisation-only update for an already working mod."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile
import zipfile

from validate_mod import LOC, ROOT

PATCH_REVISION = "2026-11-07"
PATCH_FILENAME = f"reworkl-russian-localisation-{PATCH_REVISION}.zip"
GUIDE = Path("docs/RUSSIAN_LOCALISATION.md")


def russian_files(root: Path = ROOT, *, include_world: bool = True) -> list[Path]:
    """Only Russian YML; never package scripts, descriptors or user settings."""
    base = root.resolve()
    files = sorted((root / "localisation").rglob("*_l_russian.yml"))
    if not include_world:
        files = [p for p in files if p.name != "rw26_world_l_russian.yml"]
    if not files:
        raise ValueError("No Russian localisation files found")
    seen: dict[str, Path] = {}
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(base):
            raise ValueError(f"Localisation cannot be a symlink or outside the repository: {path}")
        relative = path.relative_to(root)
        if relative.parts[1] not in {"russian", "replace"}:
            raise ValueError(f"Unexpected Russian localisation directory: {relative}")
        raw = path.read_bytes()
        if not raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError(f"Russian localisation needs a UTF-8 BOM: {relative}")
        lines = raw.decode("utf-8-sig").splitlines()
        if not lines or lines[0] != "l_russian:":
            raise ValueError(f"Wrong Russian language header: {relative}")
        for number, line in enumerate(lines[1:], 2):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = LOC.fullmatch(line)
            if not match:
                raise ValueError(f"Invalid localisation entry: {relative}:{number}")
            key, value = match.groups()
            if key in seen and (seen[key] == relative or "rw26_world_l_russian.yml" not in {relative.name, seen[key].name}):
                raise ValueError(f"Duplicate Russian key {key}: {seen[key]}, {relative}")
            if re.search(r"Describe this (focus|national spirit)", value, re.I):
                raise ValueError(f"Untranslated placeholder: {relative}:{number}")
            seen[key] = relative
    return files


def build_patch(output: Path, root: Path = ROOT) -> int:
    files = russian_files(root)
    guide_path = root / GUIDE
    if guide_path.is_symlink() or not guide_path.resolve().is_relative_to(root.resolve()):
        raise ValueError("The Russian patch guide must be inside the repository")
    guide = guide_path.read_bytes()
    # Validate before touching the destination. Stage beside it for an atomic
    # final replacement, keeping a previous good download on any failure.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reworkl-ru-", dir=output.parent) as temp:
        staged = Path(temp) / "russian.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            def add(name: str, data: bytes) -> None:
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compresslevel=6)
            for path in files:
                # Open inside the working mod directory and merge this folder.
                # There is intentionally no extra reworkl/reworkl wrapper.
                add(path.relative_to(root).as_posix(), path.read_bytes())
            add("INSTALL_RUSSIAN.txt", b"\xef\xbb\xbf" + guide.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip():
                raise ValueError("Russian patch ZIP CRC check failed")
        staged.replace(output)
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "releases" / PATCH_FILENAME)
    args = parser.parse_args()
    try:
        count = build_patch(args.output.resolve())
    except (OSError, ValueError) as error:
        parser.exit(1, f"Russian patch build failed: {error}\n")
    print(f"Built {args.output}: {count} Russian YML files + guide, {args.output.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
