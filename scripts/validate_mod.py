#!/usr/bin/env python3
"""Offline integrity checks for the merged HOI4 mod (Python 3.10+, no deps).

Checks this repository's definitions and integration contracts, not the full
HOI4 engine schema or external vanilla/DLC content. See docs/TESTING.md.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import struct
import sys

from clausewitz import Entry, ParseError, load

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("common", "events", "gfx", "history", "interface", "localisation", "music", "map")
SCRIPT_SUFFIXES = {".txt", ".gfx", ".gui", ".asset", ".mod"}
FEDERAL_STATES = {45, 102, 103, 104, 105, 106, 107, 108, 109, 163, 764, 802, 803, 804, 852, 853, 970, 1082, 1083}
REPUBLICS = {"SLV", "CRO", "MAC", "BOS", "MNT", "KOS"}
DATE = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}(?:\.\d{1,2})?$")
LOC = re.compile(r'^\s*([\w.]+):\d*\s+"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$')


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)


def date_tuple(value: str) -> tuple[int, ...]:
    parts = tuple(int(x) for x in value.split("."))
    return parts[:3]


def at_date(block: Entry, key: str, date: str) -> str:
    """Apply dated history fields in date order, independent of source order."""
    value = block.scalar(key)
    dated = [e for e in block.children() if e.key and DATE.fullmatch(e.key)]
    for entry in sorted(dated, key=lambda e: date_tuple(e.key)):
        if date_tuple(entry.key) <= date_tuple(date):
            value = entry.scalar(key, value)
    return value


def anonymous(entry: Entry) -> list[str]:
    return [e.value for e in entry.children() if e.key is None and isinstance(e.value, str)]


LOADING_SCREENS = {f"reworkl_{name}.dds" for name in ("belgrade", "mountains", "headquarters")}


def validate_loading_screens(root: Path, descriptor: Entry, report: Report) -> None:
    """Check the engine's DDS directory, not unused custom sprite names."""
    replacements = {entry.value for entry in descriptor.children("replace_path")}
    report.require("gfx/loadingscreens" in replacements, "Loading screens need replace_path=\"gfx/loadingscreens\" in descriptor.mod")
    folder = root / "gfx/loadingscreens"
    files = sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    report.require({p.name for p in files} == LOADING_SCREENS, "Expected exactly the three Reworkl DDS loading screens (no PNG placeholders)")
    report.counts["loading_screens"] = len(files)
    for path in files:
        try:
            with path.open("rb") as source:
                header = source.read(128)
            size = path.stat().st_size
        except OSError as error:
            report.errors.append(f"Loading screen {path.name}: {error}")
            continue
        if len(header) < 128 or header[:4] != b"DDS " or struct.unpack_from("<I", header, 4)[0] != 124:
            report.errors.append(f"Loading screen {path.name}: invalid DDS header")
            continue
        height, width = struct.unpack_from("<II", header, 12)
        report.require((width, height) == (1920, 1080), f"Loading screen {path.name}: expected 1920x1080")
        report.require(header[84:88] == b"DXT1" and struct.unpack_from("<I", header, 76)[0] == 32, f"Loading screen {path.name}: expected DXT1 DDS pixel format")
        mipmaps = struct.unpack_from("<I", header, 28)[0]
        report.require(mipmaps in (0, 1), f"Loading screen {path.name}: unexpected mipmap levels")
        expected_size = 128 + ((width + 3) // 4) * ((height + 3) // 4) * 8
        report.require(size == expected_size, f"Loading screen {path.name}: truncated or unexpected DDS payload size")
    for obsolete in ("interface/Y89_loadingscreens.gfx", "common/loading_tips/Y89_loading_tips.txt"):
        report.require(not (root / obsolete).exists(), f"Remove obsolete loading-screen registration: {obsolete}")


def validate(root: Path = ROOT) -> Report:
    report = Report()
    try:
        from materialize_world_map import ensure_map_assets
        ensure_map_assets(root)
    except (OSError, ValueError) as error:
        report.errors.append(str(error))
        return report
    parsed: dict[Path, Entry] = {}
    files = [root / "descriptor.mod"]
    for dirname in SOURCE_DIRS:
        folder = root / dirname
        report.require(folder.is_dir(), f"Missing source directory: {dirname}")
        files.extend(p for p in folder.rglob("*") if p.is_file() and p.suffix in SCRIPT_SUFFIXES and p.relative_to(root).as_posix() not in {"map/buildings.txt", "map/unitstacks.txt", "map/railways.txt", "map/supply_nodes.txt", "map/weatherpositions.txt"})
    for path in sorted(files):
        try:
            parsed[path.relative_to(root)] = load(path)
        except (OSError, UnicodeError, ParseError) as error:
            report.errors.append(str(error))
    report.counts["scripts"] = len(parsed)
    if report.errors:
        return report

    def definitions(folder: str, wrapper: str, id_key: str = "id") -> dict[str, Entry]:
        result = {}
        for path, tree in parsed.items():
            if path.parent != Path(folder):
                continue
            for node in tree.children(wrapper):
                key = node.scalar(id_key)
                report.require(bool(key) and key not in result, f"{path}:{node.line}: missing/duplicate {wrapper} ID: {key}")
                result[key] = node
        return result

    # Localisation: BOM, headers, proper quoting and duplicates inside a file.
    locs: dict[str, dict[str, str]] = {"english": {}, "russian": {}}
    for path in sorted((root / "localisation").rglob("*.yml")):
        data = path.read_bytes()
        rel = path.relative_to(root)
        report.require(data.startswith(b"\xef\xbb\xbf"), f"{rel}: HOI4 localisation needs UTF-8 BOM")
        try:
            lines = data.decode("utf-8-sig").splitlines()
        except UnicodeError as error:
            report.errors.append(f"{rel}: {error}")
            continue
        lang = next((lang for lang in locs if lines and lines[0] == f"l_{lang}:"), None)
        report.require(lang is not None, f"{rel}: missing supported language header")
        if lang is None:
            continue
        report.require(path.name.endswith(f"_l_{lang}.yml"), f"{rel}: filename and language header disagree")
        seen = set()
        for num, line in enumerate(lines[1:], 2):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = LOC.fullmatch(line)
            report.require(match is not None, f"{rel}:{num}: malformed localisation")
            if not match:
                continue
            key, text = match.groups()
            report.require(key not in seen, f"{rel}:{num}: duplicate localisation key {key}")
            seen.add(key)
            locs[lang][key] = text
    report.counts["localisation_keys"] = sum(map(len, locs.values()))

    def localized(key: str) -> None:
        for lang, entries in locs.items():
            report.require(key in entries, f"Missing {lang} localisation: {key}")

    # Launcher metadata and both distinct campaigns.
    descriptor = parsed[Path("descriptor.mod")]
    modern = descriptor.scalar("version").startswith("2.") or (root / "map/reworkl_world_manifest.txt").exists()
    for key in ("name", "version", "supported_version", "picture"):
        report.require(bool(descriptor.scalar(key)), f"descriptor.mod: missing {key}")
    report.require((root / descriptor.scalar("picture")).is_file(), "Missing launcher thumbnail")
    report.require(not descriptor.children("remote_file_id"), "Local mod must not inherit the source Workshop ID")
    report.require(not descriptor.children("path"), "Internal descriptor must not contain an installation-specific path")
    bookmarks = []
    for path, tree in parsed.items():
        if path.parent == Path("common/bookmarks"):
            for wrapper in tree.children("bookmarks"):
                bookmarks.extend(wrapper.children("bookmark"))
    report.counts["bookmarks"] = len(bookmarks)
    report.require(len(bookmarks) == 2, "Expected separate world 2026 and Serbia 1936 bookmarks" if modern else "Expected separate Yugoslavia and Serbia bookmarks")
    report.require(sum(b.scalar("default") == "yes" for b in bookmarks) == 1, "Expected exactly one default bookmark")
    report.require({b.scalar("date") for b in bookmarks} == {"1936.1.1.12", "2026.1.1.12" if modern else "1989.1.1.12"}, "Bookmark dates were changed")
    for bookmark in bookmarks:
        for key in ("name", "desc"):
            localized(bookmark.scalar(key))
        country = bookmark.scalar("default_country")
        report.require(bool(bookmark.children(country)), f"Bookmark default country {country} is not selectable")
        for entry in bookmark.children(country) + bookmark.children("---"):
            localized(entry.scalar("history"))
    defines = (root / "common/defines/Y89_defines.lua").read_text(encoding="utf-8")
    start = re.search(r'NGame.START_DATE\s*=\s*"([\d.]+)"', defines)
    report.require(start is not None and date_tuple(start[1]) <= (1936, 1, 1), "START_DATE excludes the Serbian bookmark")

    trees = definitions("common/national_focus", "focus_tree")
    focuses = {}
    for tree_id, tree in trees.items():
        report.require(tree.scalar("default") == "no", f"{tree_id} must not be the default tree for unrelated countries")
        for focus in tree.children("focus"):
            key = focus.scalar("id")
            report.require(bool(key) and key not in focuses, f"Missing/duplicate focus ID: {key}")
            focuses[key] = focus
            localized(key)
    report.counts["focus_trees"] = len(trees)
    report.counts["focuses"] = len(focuses)
    # A missing prerequisite or cycle can make a branch permanently unplayable.
    edges = {}
    for key, focus in focuses.items():
        edges[key] = []
        for block in focus.children("prerequisite") + focus.children("mutually_exclusive"):
            for ref in block.children("focus"):
                report.require(ref.value in focuses, f"{key}: unknown focus reference {ref.value}")
                if block.key == "prerequisite" and ref.value in focuses:
                    edges[key].append(ref.value)
    visiting, visited = set(), set()

    def visit(key: str) -> None:
        if key in visiting:
            report.errors.append(f"Focus prerequisite cycle at {key}")
            return
        if key in visited:
            return
        visiting.add(key)
        for child in edges[key]:
            visit(child)
        visiting.remove(key)
        visited.add(key)
    for key in edges:
        visit(key)

    chars = {}
    ideas = {}
    sprites = set()
    for path, tree in parsed.items():
        if path.parent == Path("common/characters"):
            for group in tree.children("characters"):
                for char in group.children():
                    report.require(char.key not in chars, f"Duplicate character: {char.key}")
                    chars[char.key] = char
        if path.parent == Path("common/ideas"):
            for group in tree.children("ideas"):
                for category in group.children():
                    for idea in category.children():
                        report.require(idea.key not in ideas, f"Duplicate idea: {idea.key}")
                        ideas[idea.key] = idea
                        localized(idea.key)
                        for modifier in idea.children("modifier"):
                            fields = [e.key for e in modifier.children()]
                            report.require(len(fields) == len(set(fields)), f"{idea.key}: duplicate numeric modifier")
                            for mod in modifier.children():
                                report.require(mod.key not in {"rule", "allow_create_faction", "can_not_declare_war", "fort_factor"}, f"{idea.key}: misplaced/invalid modifier {mod.key}")
        if path.suffix == ".gfx":
            for node in tree.walk():
                if node.key == "spriteType":
                    name = node.scalar("name")
                    report.require(name not in sprites, f"Duplicate sprite: {name}")
                    sprites.add(name)
                    texture = node.scalar("texturefile")
                    report.require(bool(texture) and (root / texture).is_file(), f"{path}: missing texture {texture}")
    report.counts["characters"] = len(chars)
    report.counts["ideas"] = len(ideas)
    for char_id, char in chars.items():
        localized(char.scalar("name"))
        if char_id.startswith("Y89_"):
            for role in char.children("country_leader"):
                report.require(date_tuple(role.scalar("expire")) >= (2100, 1, 1), f"{char_id}: leader expires during the 1989 campaign")
        for node in char.walk():
            if node.key in {"large", "small"} and isinstance(node.value, str) and ("old_world" in node.value or "Y89" in node.value):
                report.require(node.value in sprites, f"{char_id}: missing portrait sprite {node.value}")
    for focus_id, focus in focuses.items():
        for node in focus.walk():
            if node.key == "promote_character":
                cid = node.scalar("character") if isinstance(node.value, list) else node.value
                report.require(cid in chars, f"{focus_id}: missing character {cid} (IDs are case-sensitive)")
                if cid in chars and isinstance(node.value, list):
                    report.require(node.scalar("ideology") in {r.scalar("ideology") for r in chars[cid].children("country_leader")}, f"{focus_id}: character ideology does not match {cid}")
            if node.key in {"add_ideas", "remove_ideas", "has_idea", "remove_idea", "add_idea", "idea"}:
                refs = anonymous(node) if isinstance(node.value, list) else [node.value]
                for ref in refs:
                    report.require(ref in ideas, f"{focus_id}: unknown custom idea {ref}")

    # HOI4 discovers loading art directly in gfx/loadingscreens. Keep the
    # lower loading UI in the base game rather than overriding outdated GUIs.
    validate_loading_screens(root, descriptor, report)
    for number in range(10):
        localized(f"LOADING_TIP_{number}")

    # State history and all selectable/released countries' OOB locations.
    states = definitions("history/states", "state")
    provinces = {}
    for state_id, state in states.items():
        for values in state.children("provinces"):
            for province in anonymous(values):
                report.require(province not in provinces, f"Province {province} occurs in multiple states")
                provinces[province] = state_id
    if not modern:
        for sid in FEDERAL_STATES:
            state = states.get(str(sid))
            report.require(state is not None, f"Missing federal state: {sid}")
            if state:
                history = state.children("history")[0]
                report.require(at_date(history, "owner", "1989.1.1") == "YUG", f"State {sid} not Yugoslav before 1989 OOB loading")
                report.require(at_date(history, "owner", "1936.1.1") != "YUG", f"State {sid} incorrectly merged in Serbian sandbox")
    for path, tree in parsed.items():
        if path.parent == Path("common/country_tags"):
            for tag in tree.children():
                report.require(isinstance(tag.value, str) and (root / "common" / tag.value).is_file(), f"{path}: country definition missing for {tag.key}")
        if path.parent != Path("history/units"):
            continue
        if modern and path.stem == "Y89_YUG":
            continue  # Historical, inaccessible 1989 asset; not a modern start OOB.
        tag = "YUG" if path.stem == "Y89_YUG" else path.stem.split("_")[0]
        date = "2026.1.1" if path.stem.endswith("_2026") else "1989.1.1" if tag == "YUG" else "1936.1.1"
        templates = {t.scalar("name") for t in tree.children("division_template")}
        for units in tree.children("units"):
            for division in units.children("division"):
                report.require(division.scalar("division_template") in templates, f"{path}: undefined division template")
                location = division.scalar("location")
                sid = provinces.get(location)
                report.require(sid is not None, f"{path}: province {location} is outside included states")
                if sid is not None:
                    owner = at_date(states[sid].children("history")[0], "owner", date)
                    report.require(owner == tag, f"{path}: division {division.scalar('name')} starts in {owner}, not {tag}")
    if not modern:
        for sid, state in states.items():
            owner = at_date(state.children("history")[0], "owner", "1989.1.1")
            report.require(owner not in REPUBLICS | {"SER"}, f"State {sid} leaves {owner} independent before the 1989 breakup")
    # The custom 1082/1083 states also need their building positions. This file
    # is semicolon-delimited data, not a Clausewitz script.
    positions = root / "map/buildings.txt"
    report.require(positions.is_file(), "Missing building positions for the custom states")
    if positions.is_file():
        position_states = set()
        rows = positions.read_text(encoding="utf-8-sig").splitlines()
        for line, text in enumerate(rows, 1):
            fields = text.split(";")
            try:
                assert len(fields) == 7
                position_states.add(int(fields[0]))
                for value in fields[2:6]:
                    float(value)
                int(fields[6])
            except (ValueError, AssertionError):
                report.errors.append(f"map/buildings.txt:{line}: invalid building position")
        if modern:
            report.require(position_states <= {int(s) for s in states}, "Building positions reference missing world states")
        else:
            for custom in (1082, 1083):
                report.require(custom in position_states, f"No building positions for custom state {custom}")
        report.counts["building_positions"] = len(rows)
    report.counts["states"] = len(states)
    if modern:
        from validate_world_2026 import validate_world
        validate_world(root, parsed, states, report)

    events = definitions("events", "country_event")
    report.counts["events"] = len(events)
    namespaces = {n.value for p, tree in parsed.items() if p.parent == Path("events") for n in tree.children("add_namespace")}
    for event_id, event in events.items():
        report.require(event_id.split(".")[0] in namespaces, f"{event_id}: missing event namespace")
        for key in ("title", "desc"):
            localized(event.scalar(key))
        for option in event.children("option"):
            localized(option.scalar("name"))
    for path, tree in parsed.items():
        for node in tree.walk():
            if node.key == "exists":
                report.require(node.value in {"yes", "no"}, f"{path}:{node.line}: exists takes yes/no; use country_exists for a tag")
            if node.key in {"add_buildings", "add_core"}:
                report.errors.append(f"{path}:{node.line}: invalid effect {node.key}")
            if node.key == "add_trait" and isinstance(node.value, str):
                report.errors.append(f"{path}:{node.line}: add_trait needs a trait block")
            if node.key == "is_at_war_with":
                report.errors.append(f"{path}:{node.line}: use has_war_with, not is_at_war_with")
            if node.key == "country_event" and isinstance(node.value, list):
                eid = node.scalar("id")
                if eid.startswith(("Y89_", "conquermont.")):
                    report.require(eid in events, f"{path}:{node.line}: missing event {eid}")
            if node.key == "load_focus_tree":
                tid = node.scalar("tree") if isinstance(node.value, list) else node.value
                report.require(tid in trees, f"{path}:{node.line}: unknown tree {tid}")
            if node.key in {"oob", "load_oob"} and isinstance(node.value, str) and (node.value.startswith("Y89_") or node.value.split("_")[0] in REPUBLICS | {"SER", "YUG"}):
                report.require((root / "history/units" / (node.value + ".txt")).is_file(), f"{path}:{node.line}: missing OOB {node.value}")

    # Radio: exact case-sensitive paths, complete playlist, localisation and GUI.
    assets, songs, audio_paths, stations = {}, [], set(), set()
    for path, tree in parsed.items():
        if not path.is_relative_to("music"):
            continue
        if path.suffix == ".asset":
            for music in tree.children("music"):
                name = music.scalar("name")
                audio = root / path.parent / music.scalar("file")
                report.require(name not in assets, f"Duplicate music asset: {name}")
                assets[name] = audio
                audio_paths.add(audio)
                report.require(audio.is_file(), f"{path}: missing audio (including filename case): {music.scalar('file')}")
                if audio.is_file():
                    header = audio.open("rb")
                    with header:
                        data = header.read(256)
                    ident = data.find(b"\x01vorbis")
                    report.require(data.startswith(b"OggS") and ident >= 0, f"{audio.relative_to(root)}: not Ogg Vorbis")
                    if ident >= 0 and len(data) >= ident + 16:
                        channels = data[ident + 11]
                        rate = int.from_bytes(data[ident + 12:ident + 16], "little")
                        report.require(channels == 2 and rate == 44100, f"{audio.relative_to(root)}: expected stereo 44100 Hz")
                localized(name)
        if path.suffix == ".txt":
            stations.add(tree.scalar("music_station"))
            for music in tree.children("music"):
                songs.append(music.scalar("song"))
                chances = music.children("chance")
                report.require(bool(chances) and float(chances[0].scalar("factor", "0")) > 0, f"{path}: song cannot play")
    report.require(stations == {"reworkl_turbofolk"}, "Radio station namespace is not unique")
    report.require(set(songs) == set(assets) and len(songs) == len(set(songs)), "Radio playlist and assets disagree or contain duplicate tracks")
    report.require(audio_paths == set((root / "music").rglob("*.ogg")), "An OGG file is missing from the radio")
    report.require(len(assets) == 23, "Expected all 23 original tracks")
    localized("reworkl_turbofolk_TITLE")
    gui = parsed.get(Path("interface/reworkl_turbofolk.gui"))
    names = {n.scalar("name") for n in gui.children("guiTypes")[0].children()} if gui else set()
    for suffix in ("faceplate", "stations_entry"):
        report.require("reworkl_turbofolk_" + suffix in names, f"Missing radio GUI: {suffix}")
    report.counts["music_tracks"] = len(assets)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=ROOT)
    args = parser.parse_args()
    report = validate(args.root.resolve())
    for key, count in report.counts.items():
        print(f"{key}: {count}")
    if report.errors:
        print(f"\nFAIL: {len(report.errors)} error(s)", file=sys.stderr)
        for error in report.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("\nPASS: offline integrity checks. An in-game smoke test is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
