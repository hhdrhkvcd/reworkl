#!/usr/bin/env python3
"""Expand the small, pinned map archive for development/builds (stdlib only).

Expanded BMPs/unitstacks are deliberately not stored twice in Git. End users
receive the ready-expanded mod in the release ZIP and never need Python.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import tarfile
import tempfile

from clausewitz import load

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"cities.bmp", "heightmap.bmp", "provinces.bmp", "rivers.bmp", "terrain.bmp",
         "trees.bmp", "world_normal.bmp", "unitstacks.txt"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def asset_manifest(root: Path) -> dict[str, tuple[int, str]]:
    path = root / "map/reworkl_asset_manifest.txt"
    if not path.is_file():
        raise ValueError("Missing modern map asset manifest")
    records = {}
    for entry in load(path).children("map_asset"):
        name = entry.scalar("path")
        if name not in {"map/" + n for n in NAMES} or name in records:
            raise ValueError(f"Invalid/duplicate map asset path: {name}")
        records[name] = int(entry.scalar("size")), entry.scalar("sha256")
    if set(records) != {"map/" + n for n in NAMES}:
        raise ValueError("Incomplete matched map asset manifest")
    return records


def ensure_map_assets(root: Path = ROOT) -> int:
    archive = root / "assets/world_2026/map-data.tar.xz"
    if not archive.is_file():
        return 0  # Installed/extracted distribution: already-expanded assets.
    if (root / "map").is_symlink() or not (root / "map").resolve().is_relative_to(root.resolve()):
        raise ValueError("Refusing a linked map directory")
    manifest = asset_manifest(root)
    missing = []
    for name, (length, digest) in manifest.items():
        path = root / name
        if path.is_symlink():
            raise ValueError(f"Refusing a map asset symlink: {name}")
        if path.exists():
            if not path.is_file() or path.stat().st_size != length or sha256(path) != digest:
                raise ValueError(f"Existing map asset modified; not overwriting it: {name}")
        else:
            missing.append(name)
    if not missing:
        return 0
    # Read and validate EVERY entry before replacing any missing source asset.
    with tempfile.TemporaryDirectory(prefix=".map-stage-", dir=archive.parent) as tmp:
        stage = Path(tmp)
        with tarfile.open(archive, "r:xz") as source:
            seen = set()
            for member in source:
                name = "map/" + member.name
                if name not in manifest or name in seen or not member.isfile():
                    raise ValueError(f"Unexpected entry in map archive: {member.name}")
                seen.add(name)
                length, digest = manifest[name]
                if member.size != length:
                    raise ValueError(f"Map archive size mismatch: {name}")
                target = stage / member.name
                with source.extractfile(member) as data, target.open("wb") as out:
                    while block := data.read(1024 * 1024):
                        out.write(block)
                if sha256(target) != digest:
                    raise ValueError(f"Map archive checksum mismatch: {name}")
            if seen != set(manifest):
                raise ValueError("Map archive is incomplete")
        for name in missing:
            path = root / name
            path.parent.mkdir(exist_ok=True)
            (stage / path.name).replace(path)
    return len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=ROOT)
    args = parser.parse_args()
    count = ensure_map_assets(args.root.resolve())
    print(f"Materialized {count} missing map assets; existing files were not overwritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
