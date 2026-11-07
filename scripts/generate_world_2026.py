#!/usr/bin/env python3
"""Generate standalone, vanilla-compatible histories from reviewed geography.

Normal rebuilds require no internet or external mod. The MD reference supplies
only geography, positions and old baseline population/industry, NOT 2026 news,
leaders, focus trees, equipment, rules, technologies or units.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from clausewitz import load, parse
from materialize_world_map import ensure_map_assets
from validate_mod import LOC

ROOT = Path(__file__).resolve().parents[1]
NATO = "USA ENG FRA GER ITA CAN POR SPR NOR ICE DEN HOL BEL LUX GRE TUR POL CZE HUN BUL ROM EST LAT LIT SLO SLV CRO ALB MNT MAC FIN SWE".split()
COMMUNIST = {"PRC", "NKO", "CUB", "LAO", "VIN"}
# Engine profiles only, NOT claims about current parties or election outcomes.
DEMOCRATIC = set(NATO) | {"SER", "BOS", "KOS", "CHI", "JAP", "KOR", "AST", "NZL", "SWI", "IRE", "AUS"}
FOCUSES = [
    ("administration", "Государственное управление", "Подготовить общую программу развития.", "GFX_goal_generic_political_pressure", 4, 0, None, "add_political_power = 120"),
    ("economy", "Гражданская экономика", "Расширить производственную базу столицы.", "GFX_goal_generic_construct_civ_factory", 2, 2, "administration", "capital_scope = { add_extra_state_shared_building_slots = 1 add_building_construction = { type = industrial_complex level = 1 instant_build = yes } }"),
    ("logistics", "Транспорт и снабжение", "Улучшить инфраструктуру столицы. Это базовая механика HOI4, не модель современной экономики.", "GFX_goal_generic_construct_infrastructure", 2, 4, "economy", "capital_scope = { add_building_construction = { type = infrastructure level = 1 instant_build = yes } }"),
    ("science", "Образование и исследования", "Расширить исследовательские возможности страны.", "GFX_goal_generic_scientific_exchange", 6, 2, "administration", "add_research_slot = 1"),
    ("defence", "Основы обороны", "Подготовить кадры для базовой армии сценария. Современные вооружения пока не моделируются.", "GFX_goal_generic_army_doctrines", 10, 2, "administration", "army_experience = 30"),
    ("industry", "Оборонная промышленность", "Построить одну военную фабрику.", "GFX_goal_generic_construct_mil_factory", 10, 4, "defence", "capital_scope = { add_extra_state_shared_building_slots = 1 add_building_construction = { type = arms_factory level = 1 instant_build = yes } }"),
    ("cooperation", "Международное сотрудничество", "Развивать дипломатические и торговые связи без сценарного объявления войн.", "GFX_goal_generic_improve_relations", 6, 4, "science", "add_political_power = 100"),
    ("stability", "Стабильность страны", "Укрепить устойчивость государственного управления.", "GFX_goal_generic_national_unity", 6, 6, "cooperation", "add_stability = 0.1"),
]


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_loc(path: str, language: str, values: dict[str, str]) -> None:
    lines = ["l_" + language + ":"]
    for key, value in values.items():
        # Reference values already have Clausewitz-compatible escapes. JSON
        # inputs do not contain embedded quotes in our generated prose.
        value = value.replace('"', '\\"') if '\\"' not in value else value
        lines.append(f' {key}:0 "{value}"')
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(("\n".join(lines) + "\n").encode("utf-8-sig"))


def migrate_legacy(text: str, crosswalk: dict[str, list[int]]) -> str:
    """Rewrite AST-identified numeric state refs, never x/y/cost/province IDs."""
    changes = []
    tree = parse(text)
    for node in tree.walk():
        if node.key and node.key.isdigit() and isinstance(node.value, list):
            if node.key not in crosswalk:
                raise ValueError(f"Unreviewed legacy state scope: {node.key}")
            changes.append((node.start, node.start + len(node.key), str(crosswalk[node.key][0])))
        if node.key in {"owns_state", "controls_state", "add_state_core", "remove_state_core", "transfer_state", "add_state_claim", "remove_state_claim", "capital"} and isinstance(node.value, str) and node.value.isdigit():
            if node.value not in crosswalk:
                raise ValueError(f"Unreviewed legacy state reference: {node.value}")
            targets = crosswalk[node.value]
            line_start = text.rfind("\n", 0, node.start) + 1
            indent = re.match(r"\s*", text[line_start:node.start])[0]
            replacement = ("\n" + indent).join(f"{node.key} = {sid}" for sid in targets)
            changes.append((node.start, node.end, replacement))
    for start, end, value in sorted(changes, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def generate() -> None:
    world = json.loads((ROOT / "data/world_2026/world.json").read_text(encoding="utf-8"))
    countries = world["countries"]
    states = world["states"]
    crosswalk = world["legacy_state_crosswalk"]
    # Save the authored 1936 focus/event source once for deterministic rebuilds.
    legacy_dir = ROOT / "data/world_2026/legacy"
    legacy_dir.mkdir(exist_ok=True)
    for relative in ("common/national_focus/serbia_tree1.txt", "events/old_world_events.txt"):
        original = legacy_dir / Path(relative).name
        if not original.exists():
            original.write_bytes((ROOT / relative).read_bytes())
        text = migrate_legacy(original.read_text(encoding="utf-8-sig"), crosswalk)
        # Correct the pre-existing yes-instead-of-country state trigger.
        text = text.replace("is_fully_controlled_by = yes", "is_fully_controlled_by = ROOT")
        write(relative, text)
    # Installed distributions carry a compact independent ownership/capital
    # contract as well, so validation does not depend on this source JSON.
    manifest = ['world_2026 = {', '    start_date = "2026.1.1.12"',
                f'    states = {len(states)}', f'    countries = {len(countries)}',
                '    owners = {']
    manifest += [f'        {s["id"]} = {s["owner"]}' for s in states]
    manifest += ['    }', '    capitals = {']
    manifest += [f'        {tag} = {c["capital"]}' for tag, c in countries.items()]
    manifest += ['    }', '}']
    write('map/reworkl_world_manifest.txt', '\n'.join(manifest))
    # Delete only the old state history set. Keeping its differently named
    # 213 files beside the new geography would create duplicate state IDs.
    for old in (ROOT / "history/states").glob("*.txt"):
        old.unlink()
    for state in states:
        sid, owner = state["id"], state["owner"]
        shared = sum(state["buildings"].get(k, 0) for k in ("arms_factory", "industrial_complex", "dockyard"))
        slots = min(40, max(2, shared + 2))
        text = f'# Generated geography derivative, CC-BY-SA-4.0; see licenses/.\nstate = {{\n    id = {sid}\n    name = "RW26_STATE_{sid}"\n    manpower = {state["manpower"]}\n    state_category = rw26_slots_{slots}\n'
        if state["impassable"]:
            text += "    impassable = yes\n"
        if state["resources"]:
            text += "    resources = { " + " ".join(f"{k} = {v:g}" for k, v in state["resources"].items()) + " }\n"
        text += "    provinces = { " + " ".join(map(str, state["provinces"])) + " }\n"
        text += f"    history = {{\n        owner = {owner}\n        add_core_of = {owner}\n"
        # A claim is explicitly NOT an owner/controller change or a front line.
        claims = []
        if sid in (669, 1112):
            claims.append("SOV")
        if sid == 587:
            claims.append("ISR")
        if sid == 133:
            claims.append("SER")
        if sid in (372, 373):
            claims.append("MOR")
        if owner == "CHI":
            claims.append("PRC")
        for claimant in claims:
            text += f"        add_claim_by = {claimant}\n"
        for province, points in state["victory_points"]:
            text += f"        victory_points = {{ {province} {points} }}\n"
        text += "        buildings = {\n"
        for key, value in state["buildings"].items():
            if value:
                text += f"            {key} = {value}\n"
        for province, buildings in state["province_buildings"].items():
            text += f"            {province} = {{ " + " ".join(f"{k} = {v}" for k, v in buildings.items() if v) + " }\n"
        text += "        }\n    }\n}\n"
        write(f"history/states/{sid}-Reworkl.txt", text)
    write("common/state_category/rw26_categories.txt", "# Scenario-specific vanilla building slots.\n" + "\n".join(f"rw26_slots_{n} = {{ local_building_slots = {n} }}" for n in range(2, 41)))
    # Do not ship orphaned vanilla histories on the replacement world map.
    # Vanilla tag definitions remain available for vanilla script references;
    # only our reviewed active histories plus the authored releasable YUG load.
    for old in (ROOT / "history/countries").glob("*.txt"):
        if old.stem.split(" - ", 1)[0] not in set(countries) | {"YUG"}:
            old.unlink()
    tags = []
    colors = []
    characters = ["characters = {"]
    for tag, info in countries.items():
        tags.append(f'{tag} = "countries/reworkl_world/{tag}.txt"')
        color = " ".join(map(str, info["color"]))
        write(f"common/countries/reworkl_world/{tag}.txt", f"graphical_culture = western_european_gfx\ngraphical_culture_2d = western_european_2d\ncolor = {{ {color} }}")
        colors.append(f"RW26_{tag} = {{ color = rgb {{ {color} }} color_ui = rgb {{ {color} }} }}")
        party = "communism" if tag in COMMUNIST else "democratic" if tag in DEMOCRATIC else "neutrality"
        ideology = {"communism": "leninism", "democratic": "conservatism", "neutrality": "despotism"}[party]
        characters.extend([f"    RW26_{tag}_government = {{", "        name = RW26_GENERIC_GOVERNMENT",
                           "        portraits = { civilian = { large = GFX_portrait_RW26_government } }",
                           f'        country_leader = {{ ideology = {ideology} desc = RW26_GENERIC_GOVERNMENT_DESC expire = "2101.1.1" }}', "    }"])
        cap = info["capital"]
        old = world["legacy_countries"].get(tag)
        if old:
            base = re.sub(r"(?m)^capital\s*=\s*\d+", f"capital = {cap}", old["text"])
        else:
            base = f'capital = {cap}\noob = "{tag}_2026"\nset_research_slots = 3\nset_convoys = 30\nset_stability = 0.6\nset_war_support = 0.2\n'
            base += "set_technology = { infantry_weapons = 1 infantry_weapons1 = 1 tech_support = 1 tech_engineers = 1 tech_trucks = 1 basic_train = 1 }\n"
            base += f"set_politics = {{ ruling_party = {party} elections_allowed = no }}\nset_popularities = {{ {party} = 100 }}\nrecruit_character = RW26_{tag}_government\n"
        dated = f'\n2026.1.1 = {{\n    capital = {cap}\n    oob = "{tag}_2026"\n    set_cosmetic_tag = RW26_{tag}\n'
        if old:
            for node in parse(base).walk():
                if node.key == "recruit_character" and isinstance(node.value, str):
                    dated += f"    retire_character = {node.value}\n"
            dated += "    remove_ideas = { Serbian_Economy Serbian_arms noorg }\n" if tag == "SER" else ""
            dated += f"    recruit_character = RW26_{tag}_government\n"
        dated += f"    promote_character = RW26_{tag}_government\n    set_politics = {{ ruling_party = {party} elections_allowed = no }}\n    set_popularities = {{ {party} = 100 }}\n    set_stability = 0.6\n    set_war_support = 0.2\n}}\n"
        write("history/countries/" + info["filename"], "# Reworkl world: government and army profiles are gameplay placeholders.\n" + base + dated)
        capstate = next(s for s in states if s["id"] == cap)
        location = max(capstate["victory_points"], key=lambda vp: vp[1])[0] if capstate["victory_points"] else capstate["provinces"][0]
        army = 'division_template = {\n    name = "Территориальная бригада"\n    regiments = { infantry = { x = 0 y = 0 } infantry = { x = 0 y = 1 } infantry = { x = 1 y = 0 } infantry = { x = 1 y = 1 } }\n    priority = 1\n}\n'
        army += f'units = {{\n    division = {{ name = "1-я территориальная бригада" location = {location} division_template = "Территориальная бригада" start_equipment_factor = 1.0 start_experience_factor = 0.1 }}\n}}\n'
        write(f"history/units/{tag}_2026.txt", "# Small, fictional vanilla-equipment starter force, NOT a real 2026 OOB.\n" + army)
    # YUG is kept as a valid releasable tag for the authored 1936 focus effects.
    tags.append('YUG = "countries/Yugoslavia.txt"')
    write("history/countries/YUG - Yugoslavia.txt", "# Releasable 1936 focus tag; not an active 1989/2026 federation.\ncapital = 131\nset_research_slots = 3\nset_stability = 0.5\nset_war_support = 0.2\n")
    write("common/country_tags/zyy_old_world_countries.txt", "\n".join(tags))
    write("common/countries/rw26_cosmetic_tags.txt", "\n".join(colors))
    characters.append("}")
    write("common/characters/rw26_governments.txt", "\n".join(characters))
    write("interface/rw26_portrait.gfx", 'spriteTypes = { spriteType = { name = "GFX_portrait_RW26_government" texturefile = "gfx/portraits/RW26_government.dds" } }')
    # The 1936 armies also need a province audit: province 797, for example,
    # has become a Syrian province on the matched modern map.
    province_states = {p: s for s in states for p in s["provinces"]}
    for tag in world["legacy_countries"]:
        path = ROOT / f"history/units/{tag}_1936.txt"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        capital = countries[tag]["capital"]
        capital_state = next(s for s in states if s["id"] == capital)
        fallback = max(capital_state["victory_points"], key=lambda vp: vp[1])[0] if capital_state["victory_points"] else capital_state["provinces"][0]
        text = re.sub(r"(\blocation\s*=\s*)(\d+)", lambda m: m[1] + (m[2] if province_states.get(int(m[2]), {}).get("owner") == tag else str(fallback)), text)
        write(path.relative_to(ROOT).as_posix(), text)
    tree = ['focus_tree = {', '    id = rw26_world_tree', '    default = no',
            '    country = { factor = 100000 modifier = { add = -100000 tag = SER has_start_date < 1937.1.1 } }',
            '    continuous_focus_position = { x = 6 y = 9 }']
    for key, title, desc, icon, x, y, prerequisite, reward in FOCUSES:
        tree.extend([f"    focus = {{ id = RW26_{key} icon = {icon} x = {x} y = {y} cost = 5"])
        if prerequisite:
            tree.append(f"        prerequisite = {{ focus = RW26_{prerequisite} }}")
        tree.extend([f"        completion_reward = {{ {reward} }}", "        ai_will_do = { factor = 1 }", "    }"])
    tree.append("}")
    write("common/national_focus/rw26_world_tree.txt", "\n".join(tree))
    bookmarks = '''bookmarks = {
    bookmark = {
        name = RW26_BOOKMARK_2026
        desc = RW26_BOOKMARK_2026_DESC
        date = 2026.1.1.12
        picture = GFX_select_date_1936
        default_country = SER
        default = yes
'''
    for tag in ("SER", "SOV", "USA", "PRC", "GER", "RAJ", "BRA", "SAF"):
        party = "communism" if tag in COMMUNIST else "democratic" if tag in DEMOCRATIC else "neutrality"
        bookmarks += f"        {tag} = {{ history = RW26_BOOKMARK_COUNTRY_HISTORY ideology = {party} focuses = {{ RW26_administration RW26_economy RW26_defence }} }}\n"
    bookmarks += '''        "---" = { history = RW26_BOOKMARK_OTHER }
    }
    bookmark = {
        name = REWORKL_BOOKMARK_SERBIA
        desc = REWORKL_BOOKMARK_SERBIA_DESC
        date = 1936.1.1.12
        picture = GFX_select_date_1936
        default_country = SER
        SER = {
            history = REWORKL_BOOKMARK_SERBIA_HISTORY
            ideology = neutrality
            focuses = { old_world_serbia_tree1_focus_86_3 old_world_serbia_fixkosovo old_world_serbia_tree1_focus_8 }
            ideas = { Serbian_Economy Serbian_arms noorg }
        }
        "---" = { history = REWORKL_BOOKMARK_SERBIA_OTHER }
    }
}'''
    # Keep the filename for the existing installer/log-discovery contract.
    write("common/bookmarks/Y89_bookmarks.txt", bookmarks)
    # Shadow the exact vanilla filenames as a second line of defence. These
    # intentionally have ZERO bookmarks; the two real campaigns live above.
    # This also prevents an incomplete external registration merging 1939.
    for filename in ("the_gathering_storm.txt", "blitzkrieg.txt"):
        write("common/bookmarks/" + filename,
              "# Reworkl: vanilla scenario intentionally disabled.\n"
              "# See Y89_bookmarks.txt for World 2026 and alternative Serbia 1936.")
    trigger = (ROOT / "common/scripted_triggers/reworkl_triggers.txt").read_text()
    if "RW26_is_2026_campaign" not in trigger:
        write("common/scripted_triggers/reworkl_triggers.txt", trigger + "\nRW26_is_2026_campaign = { has_start_date > 2025.12.31 has_start_date < 2027.1.1 }\n")
    startup = '''on_actions = {
    on_startup = {
        effect = {
            if = {
                limit = { RW26_is_2026_campaign = yes NOT = { has_global_flag = RW26_WORLD_INITIALIZED } }
                set_global_flag = RW26_WORLD_INITIALIZED
                every_country = {
                    limit = { exists = yes }
                    load_focus_tree = { tree = rw26_world_tree keep_completed = yes }
                }
                USA = { create_faction = RW26_NATO }
'''
    for tag in NATO:
        if tag != "USA":
            startup += f"                USA = {{ add_to_faction = {tag} }}\n"
    startup += '''            }
            if = {
                limit = { has_start_date < 1937.1.1 country_exists = SER NOT = { has_global_flag = REWORKL_SERBIA_INITIALIZED } }
                set_global_flag = REWORKL_SERBIA_INITIALIZED
                SER = { load_focus_tree = { tree = serbia_tree1 keep_completed = yes } }
            }
        }
    }
}
'''
    write("common/on_actions/Y89_on_actions.txt", startup)
    write("history/general/rw26_general.txt", "# No inherited 1936 wars or faction setup. NATO is initialised once by the 2026 start hook.")
    # Avoid mod/DLC-specific 3D city models and MD-only naval terrain types.
    write("map/cities.txt", 'types_source = "map/cities.bmp"\npixel_step_x = 2\npixel_step_y = 2\n# Decorative city meshes omitted; cities still have victory points and names.')
    for path in (ROOT / "map/strategicregions").glob("*.txt"):
        text = path.read_text(encoding="utf-8-sig")
        text = re.sub(r"(naval_terrain\s*=\s*)water_littoral\b", r"\1water_shallow_sea", text)
        text = re.sub(r"(naval_terrain\s*=\s*)ocean\b", r"\1water_deep_ocean", text)
        path.write_text(text, encoding="utf-8")
    values = {
        "RW26_BOOKMARK_2026": "Мир — 2026",
        "RW26_BOOKMARK_2026_DESC": "1 января 2026 года. Современные государства по всему миру: 198 стран и отдельно обозначенных территорий, новая сетка регионов и независимые балканские страны. Это политическая карта, а не карта текущих линий фронта. Руководители, армии, технологии и общие фокусы пока условные и основаны на базовых механиках HOI4.",
        "RW26_BOOKMARK_COUNTRY_HISTORY": "Выберите страну на мировой карте. Границы приведены к отдельным современным государствам. Для спорных территорий действует явно описанная политика из документа WORLD_2026_RU.txt. Сценарий не воспроизводит действующие правительства, реальное вооружение или численность армий 2026 года.",
        "RW26_BOOKMARK_OTHER": "Можно выбрать любую страну на карте, не только отмеченные державы. Начните новую игру: сохранения версии 1989 несовместимы с новой географией.",
        "RW26_GENERIC_GOVERNMENT": "Государственное руководство",
        "RW26_GENERIC_GOVERNMENT_DESC": "Условное руководство для игрового прототипа. Имя и портрет действующего главы государства не заявляются. Политический профиль использует четыре базовые идеологии HOI4 и не является справочником современной политики.",
        "RW26_NATO": "НАТО",
        "REWORKL_BOOKMARK_SERBIA": "Сербия — 1936 (альтернативная)",
        "REWORKL_BOOKMARK_SERBIA_DESC": "Независимая Сербия и авторское дерево фокусов 1936 года сохранены. Кампания использует общую новую географическую сетку; мировые границы здесь не являются реконструкцией исторического 1936 года.",
        "REWORKL_BOOKMARK_SERBIA_HISTORY": "Альтернативная независимая Сербия: исторические персонажи и исходное дерево фокусов. Ссылки на Белград, Косово, Черногорию и соседние регионы перенесены на новую карту.",
        "REWORKL_BOOKMARK_SERBIA_OTHER": "Общая мировая карта модификации; это альтернативная кампания, не ванильный сценарий Второй мировой войны.",
    }
    for key, title, desc, *_ in FOCUSES:
        values["RW26_" + key] = title
        values["RW26_" + key + "_desc"] = desc
    for state in states:
        values[f'RW26_STATE_{state["id"]}'] = state["name_ru"]
    for tag, info in countries.items():
        for prefix in (tag, "RW26_" + tag):
            values[prefix] = info["name_ru"]
            values[prefix + "_DEF"] = info["name_ru"]
            values[prefix + "_ADJ"] = info["name_ru"]
            for party in ("democratic", "neutrality", "communism", "fascism"):
                values[prefix + "_" + party] = info["name_ru"]
                values[prefix + "_" + party + "_DEF"] = info["name_ru"]
                values[prefix + "_" + party + "_ADJ"] = info["name_ru"]
    places = ROOT / "data/world_2026/place_names.json"
    if places.is_file():
        values.update(json.loads(places.read_text(encoding="utf-8")))
    # Russian edition: preserve English source files, but make the mod's text
    # readable in both UI language selections. The new Cyrillic font overrides
    # are essential; mirroring text alone does not supply missing glyphs.
    write_loc("localisation/russian/rw26_world_l_russian.yml", "russian", values)
    write_loc("localisation/english/rw26_world_l_english.yml", "english", values)
    regenerate_russian_compatibility()
    ensure_map_assets(ROOT)
    print(f"Generated {len(states)} standalone states, {len(countries)} countries and starter OOBs.")
    print("2026 default / Serbia 1936 additional; no MD technologies or runtime dependency.")


def regenerate_russian_compatibility() -> None:
    values = {}
    for path in sorted((ROOT / "localisation/russian").glob("*.yml")):
        for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
            if match := LOC.fullmatch(line):
                values[match[1]] = match[2]
    write_loc("localisation/replace/zzzzzz_reworkl_russian_for_english_l_english.yml", "english", values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
