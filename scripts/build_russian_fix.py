#!/usr/bin/env python3
"""Build RU2: mod-only Russian text for both game language layers + safe updater.

Legacy 1.x patch builder. The 2.x world edition already includes its own
full Russian compatibility layer and font overrides. This builder does not
modify that layer or package world-map content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from build_russian_patch import russian_files
from validate_mod import LOC, ROOT

FIX_REVISION = "RU2-2026-11-07"
FIX_FILENAME = "reworkl-russian-fix-2-2026-11-07.zip"
ENGLISH_COMPAT = "localisation/replace/zzzzzz_reworkl_russian_for_english_l_english.yml"
FIX_HELPERS = ("APPLY_RUSSIAN.bat", "Reworkl-Russian.ps1")


def fix_payload(root: Path = ROOT) -> dict[str, bytes]:
    """Keep original keys/engine tokens; only mirror display values, not scripts."""
    files = russian_files(root, include_world=False)
    payload = {path.relative_to(root).as_posix(): path.read_bytes() for path in files}
    translations = {}
    for path in files:
        for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
            match = LOC.fullmatch(line)
            if match:
                translations[match[1]] = match[2]
    lines = ["l_english:", " # RU2: intentional Russian display text when the game uses English."]
    lines.extend(f' {key}:0 "{value}"' for key, value in sorted(translations.items()))
    payload[ENGLISH_COMPAT] = b"\xef\xbb\xbf" + ("\r\n".join(lines) + "\r\n").encode("utf-8")
    return payload


def build_fix(output: Path, root: Path = ROOT) -> int:
    payload = fix_payload(root)
    manifest = {
        "schema": 1,
        "revision": FIX_REVISION,
        "scope": "mod_localisation_only",
        "base_game_menu_changed": False,
        "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
            for name, data in sorted(payload.items())
        ],
    }
    payload["russian-manifest.json"] = (json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")
    for name in FIX_HELPERS:
        source = root / "installer/russian" / name
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Invalid updater helper: {name}")
        payload[name] = source.read_bytes()
    guide = (root / "docs/RUSSIAN_FIX_RU2.md").read_text(encoding="utf-8-sig")
    payload["START_RUSSIAN_RU2.txt"] = b"\xef\xbb\xbf" + guide.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reworkl-ru2-", dir=output.parent) as temp:
        staged = Path(temp) / "russian-fix.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compresslevel=6)
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip():
                raise ValueError("RU2 ZIP CRC check failed")
        staged.replace(output)
    return len(manifest["files"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "releases" / FIX_FILENAME)
    args = parser.parse_args()
    try:
        count = build_fix(args.output.resolve())
    except (OSError, ValueError) as error:
        parser.exit(1, f"RU2 build failed: {error}\n")
    print(f"Built {args.output}: {count} localisation files + updater/manifest/guide, {args.output.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
