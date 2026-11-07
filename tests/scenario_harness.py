"""Regression model of this mod's scenario startup, NOT a HOI4 emulator.

Unimplemented triggers fail loudly. A small explicit set of unrelated
(diplomatic/visual) effects is ignored; combat and engine scheduling are not
modelled. The real scripts are read, not reimplemented as a second calendar.
"""
from collections import Counter, defaultdict
from pathlib import Path
import re

from clausewitz import load
from validate_mod import ROOT, anonymous, at_date, date_tuple


class CalendarModel:
    def __init__(self, start="2026.1.1", root=ROOT):
        self.root = root
        self.start = start
        self.date = start
        self.owners = {}
        self.cores = defaultdict(set)
        for path in (root / "history/states").glob("*.txt"):
            state = load(path).children("state")[0]
            sid = state.scalar("id")
            history = state.children("history")[0]
            self.owners[sid] = at_date(history, "owner", start)
            for node in history.children("add_core_of"):
                self.cores[sid].add(node.value)
        self.globals = set()
        self.flags = defaultdict(set)
        self.focuses = defaultdict(set)
        self.ideas = defaultdict(set)
        self.trees = {}
        self.cosmetics = {}
        self.armies = defaultdict(int)
        for path in (root / "history/countries").glob("*.txt"):
            tag = path.stem.split(" - ")[0]
            if tag not in self.owners.values():
                continue
            history = load(path)
            oob = at_date(history, "oob", start)
            if oob and (root / "history/units" / (oob + ".txt")).is_file():
                self.armies[tag] = sum(len(u.children("division")) for u in load(root / "history/units" / (oob + ".txt")).children("units"))
        self.factions = defaultdict(set)
        self.faction_creations = Counter()
        self.releases = Counter()
        self.fired = Counter()
        self.embargoes = set()
        self.events = {}
        for path in (root / "events").glob("*.txt"):
            for event in load(path).children("country_event"):
                self.events[event.scalar("id")] = event
        self.triggers = {n.key: n for n in load(root / "common/scripted_triggers/reworkl_triggers.txt").children()}
        self.actions = load(root / "common/on_actions/Y89_on_actions.txt").children("on_actions")[0]

    def exists(self, country):
        return country in self.owners.values()

    @staticmethod
    def compare(left, op, right):
        return {"=": left == right, ">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[op]

    def matches(self, block, country):
        return all(self.condition(n, country) for n in block.children())

    def condition(self, node, country):
        key = node.key
        if key == "NOT":
            return not self.matches(node, country)
        if key == "OR":
            return any(self.condition(n, country) for n in node.children())
        if key == "AND":
            return self.matches(node, country)
        if key in self.triggers:
            return self.matches(self.triggers[key], country) == (node.value == "yes")
        if key == "tag":
            return country == node.value
        if key in {"date", "has_start_date"}:
            value = self.date if key == "date" else self.start
            return self.compare(date_tuple(value), node.op, date_tuple(node.value))
        if key == "country_exists":
            return self.exists(node.value)
        if key == "exists":
            return self.exists(country) == (node.value == "yes")
        if key == "has_global_flag":
            return node.value in self.globals
        if key == "has_country_flag":
            return node.value in self.flags[country]
        if key == "has_completed_focus":
            return node.value in self.focuses[country]
        if key == "num_divisions":
            return self.compare(self.armies[country], node.op, int(node.value))
        if key == "owns_state":
            return self.owners.get(node.value) == country
        if key == "has_war_with":
            return False  # These tests do not simulate wars.
        raise AssertionError(f"Unmodelled calendar trigger: {key}")

    def fire(self, event_id, country, force=False):
        event = self.events[event_id]
        if not force and event.scalar("fire_only_once") == "yes" and self.fired[event_id]:
            return
        if not force and event.children("trigger") and not self.matches(event.children("trigger")[0], country):
            return
        self.fired[event_id] += 1
        for immediate in event.children("immediate"):
            self.execute(immediate, country)

    def execute(self, block, country="global"):
        ignored = {"limit", "remove_state_claim", "remove_wargoal", "diplomatic_relation", "white_peace"}
        for node in block.children():
            key = node.key
            if key in ignored:
                continue
            if key == "if":
                limits = node.children("limit")
                if not limits or self.matches(limits[0], country):
                    self.execute(node, country)
            elif key and re.fullmatch(r"[A-Z]{3}", key):
                self.execute(node, key)
            elif key == "every_country":
                for tag in sorted(set(self.owners.values())):
                    limits = node.children("limit")
                    if not limits or self.matches(limits[0], tag):
                        self.execute(node, tag)
            elif key == "create_faction":
                self.factions[country].add(country)
                self.faction_creations[country] += 1
            elif key == "add_to_faction":
                self.factions[country].add(node.value)
            elif key == "set_global_flag":
                self.globals.add(node.value)
            elif key == "set_country_flag":
                self.flags[country].add(node.value)
            elif key == "load_focus_tree":
                self.trees[country] = node.scalar("tree")
                if node.scalar("keep_completed") != "yes":
                    self.focuses[country].clear()
            elif key == "country_event":
                # The only delayed event is informational and has no effects.
                self.fire(node.scalar("id"), country)
            elif key == "complete_national_focus":
                self.focuses[country].add(node.value)
            elif key == "transfer_state":
                self.owners[node.value] = country
            elif key == "add_state_core":
                self.cores[node.value].add(country)
            elif key == "release":
                for state, owner in list(self.owners.items()):
                    if owner == country and node.value in self.cores[state]:
                        self.owners[state] = node.value
                self.releases[node.value] += 1
            elif key == "load_oob":
                oob = load(self.root / "history/units" / (node.value + ".txt"))
                self.armies[country] += sum(len(u.children("division")) for u in oob.children("units"))
            elif key == "send_embargo":
                self.embargoes.add((country, node.value))
            elif key == "set_cosmetic_tag":
                self.cosmetics[country] = node.value
            elif key in {"add_ideas", "remove_ideas"}:
                ids = anonymous(node) if isinstance(node.value, list) else [node.value]
                for idea in ids:
                    if key == "add_ideas":
                        self.ideas[country].add(idea)
                    else:
                        self.ideas[country].discard(idea)
            else:
                raise AssertionError(f"Unmodelled calendar effect: {key}")

    def startup(self):
        self.execute(self.actions.children("on_startup")[0].children("effect")[0])

    def daily(self, date):
        self.date = date
        for action in self.actions.children("on_daily"):
            for effect in action.children("effect"):
                self.execute(effect)
