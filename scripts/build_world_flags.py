#!/usr/bin/env python3
"""Developer-only national flag/placeholder conversion. Not needed to install.

Uses the MIT flag-icons project's pinned, modern national SVGs, independently
of the geography reference. Pillow/resvg-py are only developer dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS_COMMIT = "ac7e0eb3259eb62aa6100c435607e2fe03896a97"


def build(source: Path) -> None:
    import resvg_py
    from PIL import Image
    world = json.loads((ROOT / "data/world_2026/world.json").read_text(encoding="utf-8"))
    manifest = []
    for tag, country in world["countries"].items():
        svg = source / "flags/4x3" / (country["iso2"] + ".svg")
        if not svg.is_file():
            raise ValueError(f"Missing national flag: {tag}: {svg}")
        rendered = resvg_py.svg_to_bytes(svg_path=str(svg), width=328, height=246, skip_system_fonts=True)
        image = Image.open(io.BytesIO(rendered)).convert("RGBA")
        for subfolder, size in (("", (82, 52)), ("medium", (41, 26)), ("small", (10, 7))):
            path = ROOT / "gfx/flags" / subfolder / ("RW26_" + tag + ".tga")
            path.parent.mkdir(parents=True, exist_ok=True)
            flag = image.resize(size, Image.Resampling.LANCZOS)
            # Store fully opaque RGB so transparent margins cannot become holes.
            background = Image.new("RGB", size, (240, 240, 240))
            background.paste(flag, mask=flag.getchannel("A"))
            background.save(path, format="TGA")
            manifest.append({"path": path.relative_to(ROOT).as_posix(), "size": list(size),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    portrait_svg = ROOT / "assets/world_2026/government.svg"
    portrait = resvg_py.svg_to_bytes(svg_path=str(portrait_svg), width=156, height=210, skip_system_fonts=True)
    image = Image.open(io.BytesIO(portrait)).convert("RGB")
    path = ROOT / "gfx/portraits/RW26_government.dds"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="DDS", pixel_format="DXT1")
    (ROOT / "licenses/flag-icons-MIT.txt").write_bytes((source / "LICENSE").read_bytes())
    payload = {"source_url": "https://github.com/lipis/flag-icons", "source_commit": FLAGS_COMMIT,
               "license": "MIT", "flags": manifest}
    (ROOT / "data/world_2026/flags.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Converted {len(world['countries'])} national flags in 3 engine sizes; created neutral government icon.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    build(args.source.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
