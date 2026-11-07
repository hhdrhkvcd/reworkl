#!/usr/bin/env python3
"""Render a technical political-map preview from the actual mod provinces.

This is a derivative diagram (CC-BY-SA-4.0), NOT an in-game screenshot.
Developer-only Pillow dependency. Existing selected loading artwork is untouched.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    from PIL import Image
    world = json.loads((ROOT / "data/world_2026/world.json").read_text())
    owners = {p: s["owner"] for s in world["states"] for p in s["provinces"]}
    sea = (16, 29, 33)
    colors = {}
    for line in (ROOT / "map/definition.csv").read_text().splitlines():
        row = line.split(";")
        if len(row) < 8:
            continue
        pid = int(row[0])
        rgb = tuple(map(int, row[1:4]))
        colors[rgb] = tuple(world["countries"][owners[pid]]["color"]) if row[4] == "land" and pid in owners else sea
    source = Image.open(ROOT / "map/provinces.bmp").convert("RGB").resize((1408, 512), Image.Resampling.NEAREST)
    points = [colors.get(c, sea) for c in source.getdata()]
    # Single-pixel country/coast outlines, not internal province boundaries.
    border = (28, 35, 33)
    pixels = points.copy()
    for y in range(1, 511):
        for x in range(1, 1407):
            i = y * 1408 + x
            if points[i] != sea and (points[i] != points[i - 1] or points[i] != points[i - 1408]):
                pixels[i] = border
    image = Image.new("RGB", source.size)
    image.putdata(pixels)
    target = ROOT / "website/assets/world-2026-preview.webp"
    image.save(target, "WEBP", quality=92, method=6)
    notice = (ROOT / "THIRD_PARTY.txt").read_text() + "\nThe web map preview is derived from those geographic components and is offered under CC-BY-SA-4.0. It is not a game screenshot.\n"
    (ROOT / "website/assets/world-map-NOTICE.txt").write_text(notice)
    print(f"Rendered actual territory diagram: {target.name}, {target.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
