"""World geography/packaging regressions. These do NOT execute Hearts of Iron IV."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_mod import source_files
from clausewitz import load
from generate_world_2026 import migrate_legacy
from import_world_reference import normalized
from materialize_world_map import NAMES, ensure_map_assets
from validate_mod import LOC, anonymous, at_date, validate


class World2026Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = json.loads((ROOT / "data/world_2026/world.json").read_text())
        cls.countries = cls.world["countries"]
        cls.states = {s["id"]: s for s in cls.world["states"]}

    def test_world_covers_all_un_members_observers_and_declared_special_cases(self):
        # Independent explicit ISO roster, not a count copied from the generator.
        expected = set('''af al dz ad ao ag ar am au at az bs bh bd bb by be bz bj bt bo ba bw br bn bg bf bi cv kh cm ca cf td cl cn co km cg cd cr ci hr cu cy cz dk dj dm do ec eg sv gq er ee sz et fj fi fr ga gm ge de gh gr gd gt gn gw gy ht hn hu is in id ir iq ie il it jm jp jo kz ke ki kp kr kw kg la lv lb ls lr ly li lt lu mg mw my mv ml mt mh mr mu mx fm md mc mn me ma mz mm na nr np nl nz ni ne ng mk no om pk pw pa pg py pe ph pl pt qa ro ru rw kn lc vc ws sm st sa sn rs sc sl sg sk si sb so za ss es lk sd sr se ch sy tj tz th tl tg to tt tn tr tm tv ug ua ae gb us uy uz vu ve vn ye zm zw ps va'''.split())
        self.assertEqual(len(expected), 195)
        actual = {c["iso2"] for c in self.countries.values()}
        self.assertEqual(actual, expected | {"tw", "xk", "eh"})
        self.assertEqual(len(self.countries), 198)

    def test_namespace_translation_is_non_recursive_and_not_china_india_confusion(self):
        self.assertEqual(normalized("CHI"), "PRC")
        self.assertEqual(normalized("TAI"), "CHI")
        self.assertEqual(normalized("IND"), "INS")
        self.assertEqual(normalized("RAJ"), "RAJ")
        self.assertEqual(normalized("MAY"), "MAL")
        self.assertEqual(normalized("MAL"), "MLI")
        self.assertEqual(normalized("MAC"), "PRC")
        self.assertEqual(normalized("FYR"), "MAC")

    def test_modern_independence_is_in_real_history_not_just_bookmark(self):
        for state in self.states.values():
            path = ROOT / f'history/states/{state["id"]}-Reworkl.txt'
            history = load(path).children("state")[0].children("history")[0]
            self.assertEqual(at_date(history, "owner", "2026.1.1"), state["owner"])
        self.assertEqual(self.states[1226]["owner"], "TML")
        self.assertIn("SSD", self.countries)
        self.assertNotIn("YUG", {s["owner"] for s in self.states.values()})

    def test_disputed_territory_policy_is_explicit_and_consistent(self):
        for sid, owner in {669: "UKR", 1112: "UKR", 587: "SYR", 373: "WES", 372: "WES", 424: "CUB", 133: "KOS", 595: "PRC", 1106: "PRC", 705: "GEO", 706: "GEO"}.items():
            self.assertEqual(self.states[sid]["owner"], owner, sid)
        crimea = load(ROOT / "history/states/669-Reworkl.txt").children("state")[0].children("history")[0]
        self.assertEqual(crimea.scalar("owner"), "UKR")
        self.assertIn("SOV", [e.value for e in crimea.children("add_claim_by")])
        policy = (ROOT / "WORLD_2026_RU.txt").read_text()
        self.assertIn("НЕ реконструкция военных линий фронта", policy)
        self.assertIn("неделимая провинция", policy)

    def test_each_country_capital_and_starter_force_are_on_its_own_territory(self):
        provinces = {p: s["owner"] for s in self.states.values() for p in s["provinces"]}
        for tag, country in self.countries.items():
            self.assertEqual(self.states[country["capital"]]["owner"], tag)
            history = load(ROOT / "history/countries" / country["filename"])
            self.assertEqual(at_date(history, "capital", "2026.1.1"), str(country["capital"]))
            self.assertEqual(at_date(history, "oob", "2026.1.1"), tag + "_2026")
            self.assertEqual(at_date(history, "set_cosmetic_tag", "2026.1.1"), "RW26_" + tag)
            army = load(ROOT / "history/units" / (tag + "_2026.txt"))
            divisions = [d for units in army.children("units") for d in units.children("division")]
            self.assertEqual(len(divisions), 1)
            self.assertEqual(provinces[int(divisions[0].scalar("location"))], tag)

    def test_no_stalin_or_1989_presidency_is_loaded_as_a_2026_russian_leader(self):
        source = (ROOT / "history/countries" / self.countries["SOV"]["filename"]).read_text()
        self.assertNotIn("stalin", source.lower())
        self.assertIn("RW26_SOV_government", source)
        leader = (ROOT / "common/characters/rw26_governments.txt").read_text()
        self.assertIn('expire = "2101.1.1"', leader)
        self.assertIn("RW26_GENERIC_GOVERNMENT_DESC", leader)

    def test_country_flags_are_modern_cosmetic_variants_in_all_engine_sizes(self):
        manifest = json.loads((ROOT / "data/world_2026/flags.json").read_text())
        self.assertEqual(manifest["source_commit"], "ac7e0eb3259eb62aa6100c435607e2fe03896a97")
        self.assertEqual(len(manifest["flags"]), 594)
        for flag in manifest["flags"]:
            raw = (ROOT / flag["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), flag["sha256"])
            self.assertEqual(struct.unpack_from("<HH", raw, 12), tuple(flag["size"]))

    def test_matched_map_and_required_licenses_are_in_install_payload(self):
        paths = {p.relative_to(ROOT).as_posix() for p in source_files()}
        for required in [*("map/" + n for n in NAMES), "map/definition.csv", "map/default.map", "map/railways.txt", "map/supply_nodes.txt", "THIRD_PARTY.txt", "WORLD_2026_RU.txt", "licenses/flag-icons-MIT.txt", "licenses/Millennium-Dawn-CC-BY-SA-4.0.txt"]:
            self.assertIn(required, paths)
        self.assertFalse(any(p.startswith((".cache/", "assets/", "data/")) for p in paths))

    def test_map_archive_contains_only_the_eight_matched_assets_no_reference_mod(self):
        with tarfile.open(ROOT / "assets/world_2026/map-data.tar.xz") as archive:
            members = archive.getmembers()
            self.assertEqual({m.name for m in members}, NAMES)
            self.assertTrue(all(m.isfile() and "/" not in m.name for m in members))
        self.assertLess((ROOT / "assets/world_2026/map-data.tar.xz").stat().st_size, 8 * 1024 * 1024)

    def test_music_and_three_user_selected_loading_images_are_byte_identical(self):
        preserved = json.loads((ROOT / "data/world_2026/preserved_assets.json").read_text())
        self.assertEqual(len(preserved), 26)
        self.assertEqual(sum(p.endswith(".ogg") for p in preserved), 23)
        self.assertEqual(sum(p.endswith(".dds") for p in preserved), 3)
        for path, digest in preserved.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)

    def test_legacy_migration_changes_state_references_not_layout_values(self):
        sample = "focus = { id = example x = 107 y = 802 cost = 105 completion_reward = { 107 = { add_state_core = 1083 } controls_state = 802 } }"
        migrated = migrate_legacy(sample, self.world["legacy_state_crosswalk"])
        self.assertIn("x = 107 y = 802 cost = 105", migrated)
        self.assertIn("131 = {", migrated)
        self.assertIn("add_state_core = 129", migrated)
        self.assertIn("add_state_core = 1054", migrated)
        self.assertIn("controls_state = 133", migrated)

    def test_all_generated_country_and_state_names_are_russian_in_both_ui_layers(self):
        layers = []
        for language in ("russian", "english"):
            path = ROOT / f"localisation/{language}/rw26_world_l_{language}.yml"
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            values = {m[1]: m[2] for line in path.read_text(encoding="utf-8-sig").splitlines() if (m := LOC.fullmatch(line))}
            self.assertEqual(values["RW26_SOV"], "Российская Федерация")
            self.assertEqual(values["RW26_BOOKMARK_2026"], "Мир — 2026")
            self.assertIn("VICTORY_POINTS_11586", values)
            layers.append(values)
        self.assertEqual(layers[0], layers[1])
        self.assertTrue((ROOT / "interface/zzzz_reworkl_cyrillic.gfx").is_file())

    def test_old_unsupported_2026_election_story_is_not_in_the_live_mod(self):
        for path in (ROOT / "localisation").rglob("*.yml"):
            self.assertNotIn("Y26_SER_elections", path.read_text(encoding="utf-8-sig"))
            self.assertNotIn("52,7%", path.read_text(encoding="utf-8-sig"))

    def test_all_offline_world_contracts_pass(self):
        report = validate(ROOT)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.counts["world_countries"], 198)
        self.assertEqual(report.counts["world_provinces"], 16549)
        self.assertEqual(report.counts["strategic_regions"], 222)


class SafeMapMaterializationTests(unittest.TestCase):
    def make_source(self, root, extra=None, corrupt=False):
        (root / "map").mkdir()
        (root / "assets/world_2026").mkdir(parents=True)
        text = ""
        for name in sorted(NAMES):
            data = ("fixture " + name).encode()
            text += f'map_asset = {{ path = "map/{name}" size = {len(data)} sha256 = "{hashlib.sha256(data).hexdigest()}" }}\n'
        (root / "map/reworkl_asset_manifest.txt").write_text(text)
        with tarfile.open(root / "assets/world_2026/map-data.tar.xz", "w:xz") as archive:
            for name in sorted(NAMES):
                data = ("fixture " + name).encode()
                if corrupt and name == "provinces.bmp":
                    data = b"x" * len(data)
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            if extra:
                member = tarfile.TarInfo(extra)
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))

    def test_valid_archive_materializes_once_without_overwriting_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root)
            self.assertEqual(ensure_map_assets(root), 8)
            self.assertEqual(ensure_map_assets(root), 0)
            (root / "map/provinces.bmp").write_bytes(b"user-modified")
            with self.assertRaisesRegex(ValueError, "not overwriting"):
                ensure_map_assets(root)
            self.assertEqual((root / "map/provinces.bmp").read_bytes(), b"user-modified")

    def test_corrupt_archive_is_rejected_before_any_asset_is_placed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root, corrupt=True)
            with self.assertRaisesRegex(ValueError, "checksum"):
                ensure_map_assets(root)
            self.assertFalse((root / "map/cities.bmp").exists())

    def test_path_traversal_is_rejected_without_extracting_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root, extra="../../outside.txt")
            with self.assertRaisesRegex(ValueError, "Unexpected entry"):
                ensure_map_assets(root)
            self.assertFalse((root / "map/provinces.bmp").exists())
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
