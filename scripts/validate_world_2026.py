"""Offline geography contracts for the 2026 edition; NOT an engine smoke test."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import struct

from clausewitz import Entry, load
from materialize_world_map import asset_manifest, sha256


BUILDINGS = {"infrastructure", "industrial_complex", "arms_factory", "dockyard", "air_base",
             "naval_base", "bunker", "coastal_bunker", "anti_air_building", "synthetic_refinery",
             "radar_station", "fuel_silo", "rocket_site", "nuclear_reactor"}
RESOURCES = {"oil", "aluminium", "rubber", "tungsten", "steel", "chromium"}


def validate_world(root: Path, parsed: dict[Path, Entry], states: dict[str, Entry], report) -> None:
    # Delayed import allows validate_mod to call this without an import cycle.
    from validate_mod import anonymous, at_date
    manifest_tree = parsed.get(Path("map/reworkl_world_manifest.txt"))
    report.require(manifest_tree is not None, "Missing 2026 world ownership manifest")
    if not manifest_tree:
        return
    world = manifest_tree.children("world_2026")
    report.require(len(world) == 1, "Invalid world manifest wrapper")
    if not world:
        return
    world = world[0]
    owners = {e.key: e.value for block in world.children("owners") for e in block.children()}
    capitals = {e.key: str(e.value) for block in world.children("capitals") for e in block.children()}
    report.require(len(states) == int(world.scalar("states")) == 1255, "Expected all 1255 world states")
    report.require(len(capitals) == int(world.scalar("countries")) == 198, "Expected 198 world countries/territories")
    report.require(set(states) == set(owners), "State set disagrees with world ownership manifest")
    actual_owners = set()
    assigned = {}
    categories = {e.key for p, tree in parsed.items() if p.parent == Path("common/state_category") for e in tree.children()}
    for sid, state in states.items():
        history = state.children("history")
        if not history:
            report.errors.append(f"State {sid}: no history")
            continue
        owner = at_date(history[0], "owner", "2026.1.1")
        report.require(owner == owners.get(sid), f"State {sid}: unexpected 2026 owner {owner}; expected {owners.get(sid)}")
        report.require(owner in capitals, f"State {sid}: unregistered modern owner {owner}")
        actual_owners.add(owner)
        report.require(state.scalar("state_category") in categories, f"State {sid}: undefined state category")
        for group in state.children("provinces"):
            for value in anonymous(group):
                report.require(value not in assigned, f"Province {value} occurs in multiple states")
                assigned[value] = sid
        for resources in state.children("resources"):
            report.require(all(e.key in RESOURCES for e in resources.children()), f"State {sid}: non-vanilla resource")
        for vp in history[0].children("victory_points"):
            values = anonymous(vp)
            report.require(len(values) == 2 and values[0] in {v for p in state.children('provinces') for v in anonymous(p)}, f"State {sid}: victory point outside state")
        for buildings in history[0].children("buildings"):
            for building in buildings.children():
                if building.key and building.key.isdigit():
                    report.require(assigned.get(building.key) == sid, f"State {sid}: province building outside state")
                    report.require(all(e.key in BUILDINGS for e in building.children()), f"State {sid}: non-vanilla province building")
                else:
                    report.require(building.key in BUILDINGS, f"State {sid}: non-vanilla building {building.key}")
        report.require(not any(n.key in {"set_variable", "add_dynamic_modifier", "add_province_modifier"} for n in history[0].walk()), f"State {sid}: reference-mod gameplay leaked into standalone history")
    report.require(actual_owners == set(capitals), "A world country has no owned territory")
    replacements = {e.value for e in parsed[Path("descriptor.mod")].children("replace_path")}
    for required in ("history/states", "history/countries", "history/general", "map/strategicregions", "map/supplyareas"):
        report.require(required in replacements, f"2026 geography requires replace_path={required}")
    for filename in ("the_gathering_storm.txt", "blitzkrieg.txt"):
        shadow = parsed.get(Path("common/bookmarks") / filename)
        report.require(shadow is not None, f"Missing canonical vanilla bookmark shadow: {filename}")
        if shadow is not None:
            report.require(not shadow.children("bookmarks"), f"Vanilla bookmark shadow must not add a third campaign: {filename}")
    history_tags = {p.stem.split(" - ", 1)[0] for p in parsed if p.parent == Path("history/countries")}
    report.require(history_tags == set(capitals) | {"YUG"}, "World history must contain only the 198 reviewed profiles and releasable YUG")
    definition = root / "map/definition.csv"
    report.require(definition.is_file(), "Missing world province definitions")
    defined = {}
    rgb = set()
    if definition.is_file():
        for num, row in enumerate(csv.reader(definition.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"), 1):
            try:
                pid = str(int(row[0]))
                color = tuple(int(v) for v in row[1:4])
                assert len(row) >= 8 and len(color) == 3 and all(0 <= c <= 255 for c in color)
                assert pid not in defined and color not in rgb
                assert row[4] in {"land", "sea", "lake"}
                assert row[6] in {"plains", "forest", "mountain", "hills", "desert", "jungle", "urban", "marsh", "ocean", "lakes", "unknown"}
                defined[pid] = row[4]
                rgb.add(color)
            except (ValueError, IndexError, AssertionError):
                report.errors.append(f"map/definition.csv:{num}: invalid province, duplicate RGB/ID or non-vanilla terrain")
    report.require(len(defined) == 16550, "Expected full matched world province definition set")
    lands = {p for p, kind in defined.items() if kind == "land" and p != "0"}
    report.require(lands <= set(assigned), "Visible world land provinces missing from state history")
    report.require(set(assigned) <= set(defined), "State references undefined world province")
    region_provinces = {}
    regions = []
    for path, tree in parsed.items():
        if path.parent != Path("map/strategicregions"):
            continue
        for region in tree.children("strategic_region"):
            regions.append(region.scalar("id"))
            for values in region.children("provinces"):
                for province in anonymous(values):
                    report.require(province not in region_provinces, f"Province {province}: multiple strategic regions")
                    region_provinces[province] = region.scalar("id")
    report.require(len(regions) == len(set(regions)) and len(regions) == 222, "Incomplete/duplicate world strategic regions")
    report.require(set(region_provinces) == set(defined) - {"0"}, "Strategic regions do not cover the complete world province set")
    try:
        assets = asset_manifest(root)
        for name, (size, digest) in assets.items():
            path = root / name
            report.require(path.is_file() and not path.is_symlink(), f"Missing/linked world map asset: {name}")
            if path.is_file():
                report.require(path.stat().st_size == size and sha256(path) == digest, f"World map checksum mismatch: {name}")
                if path.suffix == ".bmp":
                    with path.open("rb") as source:
                        header = source.read(54)
                    report.require(header[:2] == b"BM", f"Invalid map BMP: {name}")
                    width, height = struct.unpack_from("<ii", header, 18)
                    expected = (2816, 1024) if path.name in {"trees.bmp", "world_normal.bmp"} else (5632, 2048)
                    report.require((width, abs(height)) == expected, f"Wrong map raster dimensions: {name}")
    except (OSError, ValueError) as error:
        report.errors.append(f"World map manifest: {error}")
    nodes = root / "map/supply_nodes.txt"
    railways = root / "map/railways.txt"
    for path in (nodes, railways):
        report.require(path.is_file(), f"Missing modern supply geometry: {path.name}")
        if not path.is_file():
            continue
        for line, value in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            fields = value.split("#", 1)[0].split()
            if not fields:
                continue
            try:
                values = list(map(int, fields))
                if path == nodes:
                    assert len(values) == 2 and str(values[1]) in assigned
                else:
                    assert values[1] == len(values) - 2 and values[0] in range(1, 6)
                    assert all(str(v) in assigned for v in values[2:])
            except (ValueError, IndexError, AssertionError):
                report.errors.append(f"map/{path.name}:{line}: invalid or foreign-province supply geometry")
    for tag, capital in capitals.items():
        report.require(capital in states and owners.get(capital) == tag, f"{tag}: world capital is not owned")
        histories = [tree for path, tree in parsed.items() if path.parent == Path("history/countries") and path.stem.startswith(tag + " - ")]
        report.require(len(histories) == 1, f"{tag}: missing/duplicate country history")
        if len(histories) == 1:
            history = histories[0]
            report.require(at_date(history, "capital", "2026.1.1") == capital, f"{tag}: wrong 2026 capital")
            oob = at_date(history, "oob", "2026.1.1")
            report.require(oob == tag + "_2026", f"{tag}: modern OOB not selected")
            report.require((root / "history/units" / (oob + ".txt")).is_file(), f"{tag}: modern OOB missing")
            report.require(at_date(history, "set_cosmetic_tag", "2026.1.1") == "RW26_" + tag, f"{tag}: modern cosmetic/flag not selected")
        for folder, size in (("", (82, 52)), ("medium", (41, 26)), ("small", (10, 7))):
            path = root / "gfx/flags" / folder / ("RW26_" + tag + ".tga")
            report.require(path.is_file(), f"{tag}: missing modern flag ({folder or 'normal'})")
            if path.is_file():
                header = path.read_bytes()[:18]
                report.require(len(header) == 18 and struct.unpack_from("<HH", header, 12) == size and header[16] == 24, f"{tag}: invalid modern flag TGA")
    font = parsed.get(Path("interface/zzzz_reworkl_cyrillic.gfx"))
    font_names = set()
    if font:
        for group in font.children("bitmapfonts"):
            for override in group.children("bitmapfont_override"):
                font_names.add(override.scalar("name"))
                languages = {v for e in override.children("languages") for v in anonymous(e)}
                report.require({"l_english", "l_russian"} <= languages, "Cyrillic fonts must work with both UI selections")
    report.require({"hoi4_typewriter16", "hoi4_typewriter22", "hoi_20b", "hoi_24header"} <= font_names, "Missing Cyrillic country-selection font overrides")
    for name in ("licenses/Millennium-Dawn-CC-BY-SA-4.0.txt", "licenses/flag-icons-MIT.txt", "THIRD_PARTY.txt", "WORLD_2026_RU.txt"):
        report.require((root / name).is_file(), f"Missing attribution/instructions: {name}")
    report.counts.update(world_countries=len(capitals), strategic_regions=len(regions), world_provinces=len(defined) - 1)
