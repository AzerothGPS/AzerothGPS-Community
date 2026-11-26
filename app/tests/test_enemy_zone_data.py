"""The other faction's guard zones (Data/Hostile.lua, hostile.py), audited (item 99, Kooki3z 2026-11-25: "some of these
places we claim enemy faction guards I'm questioning"; an Ashenvale route said "Through enemy territory: Greenpaw
Village"). Checked against a WoW Forever server's world database (its spawns are the dump's): the zones that were no real
guards are gone and stay gone, and every guard circle says whose it is (ns.HostileGuards)."""

import math
import re
from pathlib import Path

HOSTILE = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Data" / "Hostile.lua"


def _load():
    txt = HOSTILE.read_text(encoding="utf-8")
    zones, guards = {}, {}
    head, _, tail = txt.partition("ns.HostileGuards = {")
    cont = None
    for line in head.splitlines():
        m = re.match(r"\s*\[(\d+)\] = \{", line)
        if m:
            cont = int(m.group(1))
            continue
        m = re.match(r"\s*(\w) = \{(.*)\},", line)
        if m and cont is not None:
            v = [float(t) for t in m.group(2).split(",") if t]
            zones[(cont, m.group(1))] = [tuple(v[i:i + 3]) for i in range(0, len(v), 3)]
    cont, side = None, None
    for line in tail.splitlines():
        m = re.match(r"\s*\[(\d+)\] = \{$", line)
        if m:
            cont = int(m.group(1))
            continue
        m = re.match(r"\s*(\w) = \{ who = \{(.*)\},$", line)
        if m:
            side = m.group(1)
            guards[(cont, side)] = {"who": dict(re.findall(r'\[(\d+)\] = "((?:[^"\\]|\\.)*)"', m.group(2)))}
            continue
        m = re.match(r"\s*at = \{(.*)\} \},$", line)
        if m:
            guards[(cont, side)]["at"] = [t for t in m.group(1).split(",") if t]
    return zones, guards


ZONES, GUARDS = _load()


def _edge(cont, side, x, y):
    """Yards from (x, y) to the nearest of the side's guard zones (negative: inside one)."""
    return min(math.hypot(a - x, b - y) - r for a, b, r in ZONES[(cont, side)])


def test_greenpaw_village_is_no_enemy_territory_for_either_side():
    # (Greenpaw Village, Ashenvale: the furbolgs' village, no guards of either faction. Its "town" was the Wandering
    # Protector's walk, one night elf giant patrolling Ashenvale's roads, 87 circles; it's left out as a lone patrol)
    for side in ("A", "H"):
        assert _edge(1, side, 2291.3, -1445.0) > 100, side
    for x, y in ((2340, -1329), (2234, -1265), (2024, -824), (2396, -1383)):  # (the giant's road)
        assert _edge(1, "H", x, y) > 0, (x, y)


def test_lone_patrols_and_event_spawns_are_no_towns():
    # (the Mounted Ironforge Mountaineer's ride down the Wetlands road: no Alliance town)
    assert _edge(0, "H", -4044, -1152) > 0
    # (no seasonal or event NPC among any zone's guards: the Alterac Valley emissaries, the Wickerman's guardians; nor a
    # faction's pets or wildlife: Teldrassil's wisps, a hunter's cat)
    banned = {"14990", "15103", "15105", "15106", "15195", "12836", "3681", "4242"}
    for key, g in GUARDS.items():
        assert not banned & set(g["at"]), key


def test_the_real_towns_stay():
    # (Splintertree Post for Alliance players, Astranaar for Horde players, Dun Algaz's mountaineers, Southshore)
    assert _edge(1, "A", 2185, -2487) < 0
    assert _edge(1, "H", 2719, -379) < 0
    assert _edge(0, "H", -4707, -2660) < 20  # (a town's middle may fall between its circles)
    assert _edge(0, "H", -780, -536) < 0


def test_every_guard_circle_says_whose_it_is():
    for key in ((0, "A"), (0, "H"), (1, "A"), (1, "H")):
        g = GUARDS[key]
        assert len(g["at"]) == len(ZONES[key]), key
        for e in g["at"]:
            assert e == "0" or e in g["who"], (key, e)
