#!/usr/bin/env python3
"""Developer-only importer of a PINNED, locally extracted CC-BY-SA map reference.

Not used by an end user's install. No MD gameplay, technology, art or music is
imported. Rebuilds the compact, reviewable geography dataset and raster archive.
Requires Pillow only for the one-time pixel/definition coverage audit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

from clausewitz import load
from validate_mod import LOC, anonymous, at_date

ROOT = Path(__file__).resolve().parents[1]
MD_COMMIT = "c5143e00268ee9125accefc7130066989de89bce"
# The reference has its own tag namespace and a 2000 campaign. Do NOT use its
# historical owners verbatim or mistake a tag such as IND (Indonesia) for India.
ALIASES = {
    "ABK": "GEO", "ACE": "INS", "AFR": "SIE", "AGL": "ANG", "AIA": "SOM",
    "AZE": "AZR", "BEN": "DAH", "BFA": "VOL", "BRU": "BRN", "BUR": "BRD",
    "CAM": "CMR", "CBD": "CAM", "CDI": "IVO", "CHE": "SOV", "CHI": "PRC",
    "CNG": "RCG", "DRC": "COG", "EGU": "EQG", "FAO": "DEN", "FYR": "MAC",
    "GAH": "GHA", "GRA": "GRD", "GRN": "DEN", "GUB": "GNB", "GUI": "GNA",
    "GUY": "GYA", "HAM": "PAL", "HEZ": "LEB", "HKG": "PRC", "HLS": "VAT",
    "IEK": "IRQ", "IND": "INS", "JUB": "SOM", "KAC": "BRM", "KAR": "BRM",
    "KUR": "IRQ", "LUR": "LIB", "MAC": "PRC", "MAR": "MSH", "MAU": "MRT",
    "MAY": "MAL", "MAL": "MLI", "MIC": "FSM", "MLC": "COG", "MLV": "MOL",
    "MOZ": "MZB", "MRT": "MUI", "NAM": "NMB", "NCY": "CYP", "NIG": "NGA",
    "NKR": "AZR", "NPM": "NEP", "NRY": "NOR", "PAP": "PNG", "PAU": "PLU",
    "PMR": "MOL", "PUK": "IRQ", "PUN": "SOM", "RCD": "COG", "SHA": "WES",
    "SHN": "BRM", "SIN": "SNG", "SML": "SOM", "SNA": "SOM", "SOO": "GEO",
    "SRI": "SRL", "SSU": "SSD", "SWS": "SOM", "TAI": "CHI", "TAL": "AFG",
    "TIM": "TML", "TML": "SRL", "TNZ": "TZN", "TRK": "TMS", "UNI": "ANG",
    "VIE": "VIN", "WAA": "BRM",
}
# Inverse lookup must select the sovereign reference, not an absorbed insurgency.
CANONICAL = {target: source for source, target in ALIASES.items()}
CANONICAL.update({
    "GEO": "GEO", "SIE": "SIE", "SOM": "SOM", "SOV": "SOV", "DEN": "DEN",
    "PAL": "PAL", "LEB": "LEB", "PRC": "CHI", "IRQ": "IRQ", "BRM": "BRM",
    "LIB": "LIB", "COG": "DRC", "AZR": "AZE", "CYP": "CYP", "NEP": "NEP",
    "AFG": "AFG", "MOL": "MLV", "SRL": "SRI", "ANG": "AGL", "TML": "TIM",
})
# ISO alpha-2 is only used for independent, separately licensed national flags.
ISO = dict(pair.split(":") for pair in """
ADO:ad AFG:af ALB:al ALG:dz ANG:ao ANT:ag ARG:ar ARM:am AST:au AUS:at AZR:az
BAH:bs BAN:bd BAR:bb BEL:be BHR:bh BHU:bt BLR:by BLZ:bz BOL:bo BOS:ba BOT:bw
BRA:br BRD:bi BRM:mm BRN:bn BUL:bg CAM:kh CAN:ca CAR:cf CHA:td CHI:tw CHL:cl
CMR:cm COG:cd COL:co COM:km COS:cr CRO:hr CUB:cu CYP:cy CZE:cz DAH:bj DEN:dk
DJI:dj DMI:dm DOM:do ECU:ec EGY:eg ELS:sv ENG:gb EQG:gq ERI:er EST:ee ETH:et
FIJ:fj FIN:fi FRA:fr FSM:fm GAB:ga GAM:gm GEO:ge GER:de GHA:gh GNA:gn GNB:gw
GRD:gd GRE:gr GUA:gt GYA:gy HAI:ht HOL:nl HON:hn HUN:hu ICE:is INS:id IRE:ie
IRQ:iq ISR:il ITA:it IVO:ci JAM:jm JAP:jp JOR:jo KAZ:kz KEN:ke KIR:ki KOR:kr
KOS:xk KUW:kw KYR:kg LAO:la LAT:lv LBA:ly LEB:lb LES:ls LIB:lr LIC:li LIT:lt
LUX:lu MAC:mk MAD:mg MAL:my MEX:mx MLI:ml MLD:mv MLT:mt MLW:mw MNC:mc MNT:me
MOL:md MON:mn MOR:ma MRT:mr MSH:mh MUI:mu MZB:mz NAU:nr NEP:np NGA:ng NGR:ne
NIC:ni NKO:kp NMB:na NOR:no NZL:nz OMA:om PAK:pk PAL:ps PAN:pa PAR:py PER:ir
PHI:ph PLU:pw PNG:pg POL:pl POR:pt PRC:cn PRU:pe QAT:qa RAJ:in RCG:cg ROM:ro
RWA:rw SAF:za SAM:ws SAO:st SAU:sa SEN:sn SER:rs SEY:sc SIA:th SIE:sl SLO:sk
SLV:si SMA:sm SNG:sg SOL:sb SOM:so SOV:ru SPR:es SRL:lk SSD:ss STK:kn STL:lc
STV:vc SUD:sd SUR:sr SWA:sz SWE:se SWI:ch SYR:sy TAJ:tj TML:tl TMS:tm TNZ:tz
TOG:tg TON:to TRI:tt TUL:tv TUN:tn TUR:tr TZN:tz UAE:ae UGA:ug UKR:ua URG:uy USA:us UZB:uz VAN:vu
VAT:va VEN:ve VER:cv VIN:vn VOL:bf WES:eh YEM:ye ZAM:zm ZIM:zw
""".split())
# This is a sovereignty-oriented game map, not a reconstruction of front lines.
# Crimea/Sevastopol follow Ukraine's internationally recognised boundaries;
# disputed control is documented rather than silently encoded as annexation.
OVERRIDES = {
    587: ("SYR", "Golan Heights: internationally recognised Syrian sovereignty"),
    1226: ("TML", "East Timor independence; not Indonesia"),
    669: ("UKR", "Crimea: internationally recognised Ukrainian boundaries"),
    1112: ("UKR", "Sevastopol: same sovereignty policy as Crimea"),
    373: ("WES", "Western Sahara: separately marked disputed territory"),
    424: ("CUB", "Guantanamo: Cuban sovereignty; US lease/control not annexation"),
}
BUILDINGS = {"infrastructure", "industrial_complex", "arms_factory", "dockyard", "air_base",
             "naval_base", "bunker", "coastal_bunker", "anti_air_building", "synthetic_refinery",
             "radar_station", "fuel_silo", "rocket_site", "nuclear_reactor"}
RESOURCES = {"oil", "aluminium", "rubber", "tungsten", "steel", "chromium"}
ASSETS = ("cities.bmp", "heightmap.bmp", "provinces.bmp", "rivers.bmp", "terrain.bmp",
          "trees.bmp", "world_normal.bmp", "unitstacks.txt")
# Explicit migration, not the false assumption that old state numbers survive.
# For state-scope actions use the first ID; territorial claims/cores expand all.
CROSSWALK = {
    44: [137, 138], 45: [130], 46: [150], 47: [141], 48: [153], 82: [910],
    102: [125], 103: [127], 104: [128, 1051, 1053], 105: [134],
    106: [136], 107: [131], 108: [132], 109: [126], 163: [127],
    184: [974], 185: [139], 211: [154], 212: [153], 458: [388],
    731: [140], 736: [1061], 764: [998], 801: [154], 802: [133],
    803: [132], 804: [1052], 805: [138], 852: [127], 853: [124],
    934: [137], 970: [135], 1082: [130], 1083: [129, 1054],
}


def normalized(tag: str) -> str:
    # Intentionally non-recursive: MAL and CHI have different meanings in the
    # reference and in vanilla. Recursive aliasing corrupts Malaysia and Taiwan.
    return ALIASES.get(tag, tag)


def locs(path: Path) -> dict[str, str]:
    return {m[1]: m[2] for line in path.read_text(encoding="utf-8-sig").splitlines()
            if (m := LOC.fullmatch(line))}


def import_reference(reference: Path) -> None:
    from PIL import Image
    out = ROOT / "data/world_2026"
    out.mkdir(parents=True, exist_ok=True)
    previous = json.loads((out / "world.json").read_text()) if (out / "world.json").exists() else {}
    legacy = previous.get("legacy_countries", {})
    if not legacy:
        for tag in ("SER", "MNT", "BOS", "CRO", "SLV", "MAC", "KOS"):
            path = next((ROOT / "history/countries").glob(f"{tag} - *.txt"))
            text = path.read_text(encoding="utf-8-sig")
            text = re.split(r"(?m)^1989\.1\.1\s*=", text)[0].rstrip() + "\n"
            legacy[tag] = {"filename": path.name, "text": text}
    alltags = {}
    for p in sorted((reference / "common/country_tags").glob("*.txt")):
        alltags.update({e.key: e.value for e in load(p).children() if isinstance(e.value, str)})
    state_locs = {lang: locs(reference / f"localisation/{lang}/state_names_l_{lang}.yml")
                  for lang in ("english", "russian")}
    country_locs = {lang: locs(reference / f"localisation/{lang}/countries_l_{lang}.yml")
                    for lang in ("english", "russian")}
    states = []
    owners = Counter()
    for path in sorted((reference / "history/states").glob("*.txt")):
        st = load(path).children("state")[0]
        sid = int(st.scalar("id"))
        history = st.children("history")[0]
        source_owner = at_date(history, "owner", "2026.1.1")
        owner = OVERRIDES.get(sid, (normalized(source_owner), ""))[0]
        provinces = [int(v) for e in st.children("provinces") for v in anonymous(e)]
        buildings = {}
        ports = {}
        for group in history.children("buildings"):
            for b in group.children():
                if b.key in BUILDINGS and isinstance(b.value, str):
                    buildings[b.key] = int(float(b.value))
                if b.key and b.key.isdigit() and isinstance(b.value, list):
                    keep = {e.key: int(float(e.value)) for e in b.children()
                            if e.key in BUILDINGS and isinstance(e.value, str)}
                    if keep:
                        ports[b.key] = keep
        buildings["infrastructure"] = max(1, min(5, buildings.get("infrastructure", 1)))
        for key in ("air_base", "naval_base", "anti_air_building", "radar_station"):
            if key in buildings:
                buildings[key] = min(buildings[key], {"air_base": 10, "naval_base": 10, "anti_air_building": 5, "radar_station": 6}[key])
        resources = {e.key: float(e.value) for r in st.children("resources") for e in r.children()
                     if e.key in RESOURCES and isinstance(e.value, str)}
        victory = [list(map(int, anonymous(vp))) for vp in history.children("victory_points")]
        assert all(len(v) == 2 for v in victory), path
        cores = sorted({normalized(str(e.value)) for e in history.children("add_core_of")})
        states.append({"id": sid, "source_file": path.name, "source_owner": source_owner,
                       "owner": owner, "provinces": provinces,
                       "name_en": state_locs["english"].get(st.scalar("name"), path.stem.split("-", 1)[-1]),
                       "name_ru": state_locs["russian"].get(st.scalar("name"), path.stem.split("-", 1)[-1]),
                       "manpower": int(st.scalar("manpower", "1000")),
                       "buildings": buildings, "province_buildings": ports, "resources": resources,
                       "victory_points": victory, "source_cores": cores,
                       "impassable": st.scalar("impassable") == "yes"})
        owners[owner] += 1
    states.sort(key=lambda x: x["id"])
    # Two reference Solomon Islands VPs still live in the pre-split state.
    # Move by actual province membership, never by a guessed numeric state ID.
    province_states = {p: s for s in states for p in s["provinces"]}
    relocations = []
    for state in states:
        for vp in list(state["victory_points"]):
            if vp[0] not in state["provinces"]:
                destination = province_states[vp[0]]
                assert destination["owner"] == state["owner"], (state["id"], vp, destination["id"])
                state["victory_points"].remove(vp)
                destination["victory_points"].append(vp)
                relocations.append({"province": vp[0], "from": state["id"], "to": destination["id"]})
    missing_iso = set(owners) - ISO.keys()
    if missing_iso:
        raise ValueError(f"Missing reviewed ISO flag mapping: {missing_iso}")
    countries = {}
    for tag in sorted(owners):
        source_tag = CANONICAL.get(tag, tag)
        namepath = alltags[source_tag]
        country = load(reference / "common" / namepath)
        palette = [int(float(x)) for e in country.children("color") for x in anonymous(e)]
        assert len(palette) == 3, source_tag
        # Reference Uganda has a typo, B=278. Keep all generated RGBs valid.
        palette = [min(255, max(0, c)) for c in palette]
        names = {}
        for lang, table in country_locs.items():
            names[lang] = next((table[k] for k in [source_tag, source_tag + "_neutrality", source_tag + "_democratic", source_tag + "_communism"] if k in table), Path(namepath).stem)
        capfile = next((reference / "history/countries").glob(source_tag + " - *.txt"))
        capmatch = re.search(r"(?m)^capital\s*=\s*(\d+)", capfile.read_text(encoding="utf-8-sig"))
        capital = int(capmatch[1]) if capmatch else 0
        own = [s for s in states if s["owner"] == tag]
        if not any(s["id"] == capital for s in own):
            capital = max(own, key=lambda s: max([vp[1] for vp in s["victory_points"]] or [0]))["id"]
        # Modern plain names are deliberate, not vanilla's ideological empires.
        overrides = {
            "SOV": ("Russian Federation", "Российская Федерация"),
            "CHI": ("Taiwan", "Тайвань"), "PRC": ("China", "Китай"),
            "RAJ": ("India", "Индия"), "INS": ("Indonesia", "Индонезия"),
            "MAC": ("North Macedonia", "Северная Македония"),
            "SWA": ("Eswatini", "Эсватини"), "TML": ("Timor-Leste", "Восточный Тимор"),
            "VAT": ("Vatican City", "Ватикан"), "WES": ("Western Sahara", "Западная Сахара"),
            "BRM": ("Myanmar", "Мьянма"), "NKO": ("North Korea", "КНДР"),
        }
        en, ru = overrides.get(tag, (names["english"], names["russian"]))
        filename = next((ROOT / "history/countries").glob(tag + " - *.txt"), None)
        filename = filename.name if filename else f"{tag} - Reworkl {tag}.txt"
        countries[tag] = {"source_tag": source_tag, "name_en": en, "name_ru": ru,
                          "iso2": ISO[tag], "color": palette, "capital": capital, "filename": filename}
    # Audit the actual bitmap. Merely counting definitions cannot detect a
    # visible land province omitted from every state, or unknown pixel colours.
    rows = {int(row[0]): row for line in (reference / "map/definition.csv").read_text().splitlines()
            if len(row := line.split(";")) >= 8 and row[0].isdigit()}
    colors = {tuple(map(int, row[1:4])): pid for pid, row in rows.items()}
    bitmap = Image.open(reference / "map/provinces.bmp").convert("RGB")
    pixels = bitmap.getcolors(bitmap.width * bitmap.height)
    unknown = [color for count, color in pixels if color not in colors]
    assert not unknown, unknown
    visible = {colors[color] for count, color in pixels}
    assigned = [v for s in states for v in s["provinces"]]
    assert len(assigned) == len(set(assigned)), "Province assigned twice"
    missing = {p for p in visible if rows[p][4] == "land"} - set(assigned)
    assert not missing, f"Visible land provinces lack a state: {missing}"
    dataset = {"schema": 1, "start_date": "2026.1.1.12", "source_commit": MD_COMMIT,
               "source_url": "https://github.com/MillenniumDawn/Millennium-Dawn",
               "license": "CC-BY-SA-4.0", "policy": "sovereignty-with-explicit-disputed-territories",
               "victory_point_relocations": relocations,
               "raster_dimensions": list(bitmap.size), "visible_provinces": sorted(visible),
               "states": states, "countries": countries, "legacy_countries": legacy,
               "legacy_state_crosswalk": {str(k): v for k, v in CROSSWALK.items()},
               "sovereignty_overrides": {str(k): {"owner": v[0], "reason": v[1]} for k, v in OVERRIDES.items()}}
    (out / "world.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Matched province data and rasters travel together. A tiny JSON owner list
    # placed on the vanilla bitmap would NOT constitute a modern world map.
    maproot = ROOT / "map"
    maproot.mkdir(exist_ok=True)
    for path in (reference / "map").iterdir():
        if path.is_file() and path.name not in ASSETS and path.name not in {"buildings.txt", "colors.txt"}:
            data = path.read_bytes()
            if path.name == "definition.csv":
                text = data.decode("utf-8-sig").replace(";supercity;", ";urban;")
                # Reserve a unique, unused colour for dummy province 0. The
                # source also uses black for real land province 16257.
                text = re.sub(r"(?m)^0;0;0;0;", "0;0;0;1;", text)
                data = ("\n".join(l for l in text.splitlines() if l.strip()) + "\n").encode("utf-8")
            if path.name == "adjacency_rules.txt":
                text = data.decode("utf-8-sig")
                text = re.sub(r"\b[A-Z]{3}\b", lambda m: normalized(m[0]), text)
                data = text.encode("utf-8")
            (maproot / path.name).write_bytes(data)
    (maproot / "ambient_object.txt").write_text("# Use no mod-specific decorative 3D models.\n", encoding="utf-8")
    # Only vanilla building types; MD offices, internet, energy and landmarks
    # would create missing-building errors in a standalone, no-DLC Reworkl.
    position_lines = [line for line in (reference / "map/buildings.txt").read_text().splitlines()
                      if len(parts := line.split(";")) == 7 and parts[1] in BUILDINGS]
    (maproot / "buildings.txt").write_text("\n".join(position_lines) + "\n", encoding="utf-8")
    for subdir in ("strategicregions", "supplyareas"):
        destination = maproot / subdir
        destination.mkdir(exist_ok=True)
        for old in destination.glob("*.txt"):
            old.unlink()
        for path in (reference / "map" / subdir).glob("*.txt"):
            (destination / path.name).write_bytes(path.read_bytes())
    assets_dir = ROOT / "assets/world_2026"
    assets_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    with tarfile.open(assets_dir / "map-data.tar.xz", "w:xz", preset=6) as archive:
        for name in ASSETS:
            data = (reference / "map" / name).read_bytes()
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mtime = 0
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
            manifest.append({"path": "map/" + name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest_text = "# Reproducible, matched CC-BY-SA map assets. Do not mix with vanilla rasters.\n"
    for item in manifest:
        manifest_text += f'map_asset = {{ path = "{item["path"]}" size = {item["size"]} sha256 = "{item["sha256"]}" }}\n'
    (maproot / "reworkl_asset_manifest.txt").write_text(manifest_text, encoding="utf-8")
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    (licenses / "Millennium-Dawn-CC-BY-SA-4.0.txt").write_bytes((reference / "LICENSE").read_bytes())
    print(f"Imported {len(states)} states, {len(countries)} countries, {len(assigned)} assigned provinces.")
    print(f"Pixel audit: {len(visible)} visible provinces; zero unknown colours or unassigned land provinces.")
    print(f"Compressed map source: {(assets_dir / 'map-data.tar.xz').stat().st_size:,} bytes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    import_reference(args.reference.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
