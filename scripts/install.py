#!/usr/bin/env python3
"""Install the local mod without touching saves or the launcher database."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile

from build_mod import copy_payload, launcher_descriptor
from validate_mod import ROOT, validate


def detect_user_dir() -> Path | None:
    home = Path.home()
    documents = [home / "Documents"]
    if sys.platform == "win32":
        # Respect Windows redirected/OneDrive Documents rather than guessing.
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)
        if result == 0 and buffer.value:
            documents.insert(0, Path(buffer.value))
        if os.environ.get("OneDrive"):
            documents.append(Path(os.environ["OneDrive"]) / "Documents")
    candidates = [p / "Paradox Interactive/Hearts of Iron IV" for p in documents]
    if sys.platform.startswith("linux"):
        candidates.insert(0, home / ".local/share/Paradox Interactive/Hearts of Iron IV")
    return next((p for p in candidates if p.is_dir()), None)


def install(user_dir: Path, root: Path = ROOT) -> tuple[Path, Path | None]:
    report = validate(root)
    if report.errors:
        raise ValueError("Refusing to install an invalid mod:\n" + "\n".join(report.errors))
    mod_dir = user_dir.resolve() / "mod"
    mod_dir.mkdir(parents=True, exist_ok=True)
    target = mod_dir / "reworkl"
    descriptor = mod_dir / "reworkl.mod"
    if target.is_symlink() or descriptor.is_symlink():
        raise ValueError("Refusing to replace a symlink at the installation destination")
    if target.resolve() == root.resolve() or target.resolve() in root.resolve().parents:
        raise ValueError("The source is already in the installation directory; use the manual installation instructions")
    backup = None
    # All copying and validation happens before the existing installation moves.
    with tempfile.TemporaryDirectory(prefix=".reworkl-install-", dir=mod_dir) as temporary:
        stage = Path(temporary) / "reworkl"
        copy_payload(stage, root)
        staged_descriptor = Path(temporary) / "reworkl.mod"
        staged_descriptor.write_text(launcher_descriptor(root, target.as_posix()), encoding="utf-8")
        installed_new = False
        try:
            if target.exists() or descriptor.exists():
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup = mod_dir / ("reworkl-backup-" + timestamp)
                backup.mkdir()
                if target.exists():
                    target.rename(backup / "reworkl")
                if descriptor.exists():
                    descriptor.rename(backup / "reworkl.mod")
            stage.rename(target)
            installed_new = True
            staged_descriptor.replace(descriptor)
        except OSError:
            import shutil
            if installed_new:
                shutil.rmtree(target)
            if backup:
                if (backup / "reworkl").exists():
                    (backup / "reworkl").rename(target)
                if (backup / "reworkl.mod").exists():
                    (backup / "reworkl.mod").rename(descriptor)
            raise
    return target, backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-dir", type=Path, help="HOI4 user-data folder, NOT the Steam game installation")
    args = parser.parse_args()
    user_dir = args.user_dir or detect_user_dir()
    if user_dir is None:
        parser.exit(1, "HOI4 user-data folder not found. Start the game once or supply --user-dir PATH. See docs/INSTALL.md.\n")
    try:
        target, backup = install(user_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Installation failed: {error}\n")
    print(f"Installed: {target}")
    if backup:
        print(f"Previous installation backed up: {backup}")
    print("Enable only 'Reworkl — Югославия, Сербия и Turbo-folk' in a new launcher playset. Start a NEW campaign.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
