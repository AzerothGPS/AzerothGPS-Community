"""Where each faction's PvP NPCs stand and walk, for routes that keep players of the other
faction away from them (Data/Hostile.lua).

The NPCs that would flag a player of the other side for PvP (asked 2026-11-15: "It should be any alliance NPC that
would flag horde player as PVP, and vise versa"): their faction template's PvP flag (the client's FactionTemplate
Flags & PVP_FLAG; or the NPC's own UnitFlags & UNIT_FLAG_PVP), of a faction hostile to one side only (EnemyGroup: 2
Alliance players, 4 Horde players), from the NPC spawn and patrol data under data/thirdparty. Not the guard flag or a
guard's name any more: Hillsbrad Fields' Footmen (the guard flag, "Footman") made the farm an Alliance town, quest mobs
that flag no one. The guards among them (the guard flag, or a guard's name) at GUARD_YD as before: A and H; the rest
(quest givers, vendors, flight masters, a dig site's workers: asked "guards full, others light") at LIGHT_YD: a and h,
priced lighter by the router (Router.HOSTILE_LIGHT_FACTOR).
Each spawn (and each point of a patrol) becomes a circle of GUARD_YD, plus how far the NPC
wanders; circles close together are merged into one.
Left out (item 99, Kooki3z 2026-11-25: "some of these places we claim enemy faction guards I'm questioning"; checked
against a WoW Forever server's world database, whose spawns are the dump's): seasonal and event spawns (game_event),
placeholders and unselectable NPCs, a faction's pets and wildlife (beasts, critters, mechanical: Teldrassil's wisps, a
hunter's cat), a guard by its name only unless it's a person (humanoid, undead), and a lone patrol: a patrolling NPC's
points (and its spot) more than TOWN_YD from its side's NPCs standing still (the Wandering Protector, a night elf giant
walking Ashenvale's roads, was an 87-circle Alliance "town" named Greenpaw Village). Each circle names its guards
(ns.HostileGuards) so a zone says whose it is.
"""

from __future__ import annotations

import gzip
import math
import re
from collections import Counter
from pathlib import Path

GUARD_FLAG = 0x400  # creature_template.ExtraFlags: a guard (npcs.py: the shipped NPCs' guards; not the enemy areas any more)
GUARD_NAME = re.compile(r"\b(Guard|Guardian|Grunt|Deathguard|Sentinel|Bluffwatcher|Brave|Protector|"
                        r"Mountaineer|Watchman|Defender|Warden|Peacekeeper|Enforcer|Footman|Rifleman)\b")
PVP_FLAG = 0x800  # FactionTemplate.Flags: its NPCs flag a player who attacks them for PvP (FACTION_TEMPLATE_FLAG_PVP)
UNIT_FLAG_PVP = 0x1000  # creature_template.UnitFlags: the NPC itself PvP flagged
GUARD_YD = 35.0  # about how far a guard of a much higher level notices a player
LIGHT_YD = 10.0  # the other PvP NPCs: about where one would notice a player walking by (20 with merge's CELL_YD / 2)
LIGHT_WANDER_YD = 10.0  # (their wander counted up to this: a few walk a whole farm)
CELL_YD = 20.0  # circles within a cell of this size are one
GROUP_ALLIANCE, GROUP_HORDE = 2, 4
PEOPLE = (6, 7)  # (CreatureType: undead, humanoid) a guard by its name only among these
WILDLIFE = (1, 8, 9)  # (CreatureType: beast, critter, mechanical) a faction's pets and wildlife: no guards, no town
INVISIBLE = 0x80  # (creature_template.ExtraFlags)
NOT_SELECTABLE = 0x2000000  # (creature_template.UnitFlags)
NOISE = re.compile(r"\b(Trigger|DND|UNUSED|Dummy|Visual|Invisible|Placeholder|Bunny|Spawner)\b|Only GM|\[|\]", re.I)
PATROL = 2  # (creature.MovementType: waypoints, creature_movement)
TOWN_YD = 250.0  # a patrol's point counts within this of its side's NPCs standing still (the guards walking Dun Algaz: 220)
DUMP = Path("thirdparty") / "cmangos-classic-db" / "ClassicDB_1_12_1_z2815.sql.gz"
# WoW Forever's own camps, whose guards aren't in the 1.12 dump: { continent:
# { side: [(x, y, reach)] } }, merged like the dump's. Camp Gev'rek in Mulgore (Horde): an Alliance player "had to death
# run from the dock" of its zeppelin (a player's report, relayed by Kooki3z 2026-11-21); its dock, and the camp over
# AreaTable 17223's chunks (x -733..-567, y 333..500), so Alliance walks keep off it too.
FOREVER_GUARDS = {
    1: {"A": [(-802.0, 366.5, GUARD_YD), (-650.0, 416.7, 110.0)]},
}


def _tuples(s: str):
    i, n = 0, len(s)
    while i < n:
        if s[i] != "(":
            i += 1
            continue
        i += 1
        vals, cur, q = [], [], False
        while i < n:
            c = s[i]
            if q:
                if c == "\\":
                    cur.append(s[i + 1])
                    i += 2
                    continue
                if c == "'":
                    if i + 1 < n and s[i + 1] == "'":
                        cur.append("'")
                        i += 2
                        continue
                    q = False
                    i += 1
                    continue
                cur.append(c)
                i += 1
                continue
            if c == "'":
                q = True
            elif c == ",":
                vals.append("".join(cur))
                cur = []
            elif c == ")":
                vals.append("".join(cur))
                i += 1
                break
            else:
                cur.append(c)
            i += 1
        yield vals


def _rows(txt: str, table: str):
    m = re.search(r"CREATE TABLE `%s` \((.*?)\n\) ENGINE" % table, txt, re.S)
    cols = re.findall(r"^\s*`(\w+)`", m.group(1), re.M)
    for m in re.finditer(r"INSERT INTO `%s` (?:\([^)]*\) )?VALUES\s*(.*?);\n" % table, txt, re.S):
        for vals in _tuples(m.group(1)):
            if len(vals) == len(cols):
                yield dict(zip(cols, vals))


def _sources(txt: str, faction_templates: dict[int, dict]) -> tuple[dict, dict]:
    """The NPCs whose spawns count, { entry: "A" / "H" / "a" / "h" }, and the ones left out, { entry: why } (item 99,
    Kooki3z 2026-11-25: "some of these places we claim enemy faction guards I'm questioning")."""
    side, left = {}, {}
    for r in _rows(txt, "creature_template"):
        ft = faction_templates.get(int(r["Faction"]))
        if not ft or not (int(ft["Flags"]) & PVP_FLAG or int(r["UnitFlags"] or 0) & UNIT_FLAG_PVP):
            continue
        enemy = ft["EnemyGroup"]
        if enemy & GROUP_ALLIANCE and not enemy & GROUP_HORDE:
            s = "a"
        elif enemy & GROUP_HORDE and not enemy & GROUP_ALLIANCE:
            s = "h"
        else:
            continue
        kind, flagged = int(r["CreatureType"] or 0), int(r["ExtraFlags"] or 0) & GUARD_FLAG
        if NOISE.search(r["Name"]) or int(r["ExtraFlags"] or 0) & INVISIBLE or int(r["UnitFlags"] or 0) & NOT_SELECTABLE:
            left[r["Entry"]] = "placeholder or unselectable"
            continue
        if kind in WILDLIFE and not flagged:
            left[r["Entry"]] = "wildlife or pet"
            continue
        guard = flagged or (kind in PEOPLE and GUARD_NAME.search(r["Name"]))
        side[r["Entry"]] = s.upper() if guard else s
    return side, left


def guard_points(data_dir: Path, faction_templates: dict[int, dict], audit: dict | None = None) -> dict[int, dict[str, list]]:
    """{ continent: { "A": [(x, y, r)], "H": [...], "a": [...], "h": [...] } }: "A" is dangerous to Alliance players (its
    guards), "a" too, lighter (the other NPCs that would flag them for PvP). With `audit` (a dict), every spawn and
    patrol point looked at goes into it: audit[(continent, side)] = [(x, y, entry, name, faction, why)], why "" for the
    ones kept."""
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    side, left = _sources(txt, faction_templates)
    names = {}
    tpl_faction = {}
    for r in _rows(txt, "creature_template"):
        names[r["Entry"]] = r["Name"]
        tpl_faction[r["Entry"]] = int(r["Faction"])
    entries: dict[str, list] = {}  # (a spawn of one of several creatures: creature id 0)
    for r in _rows(txt, "creature_spawn_entry"):
        entries.setdefault(r["guid"], []).append(r["entry"])
    events = {r["guid"]: int(r["event"]) for r in _rows(txt, "game_event_creature")}

    def note(mp, s, x, y, e, why):
        if audit is not None:
            audit.setdefault((mp, s.upper()), []).append((x, y, e, names.get(e, "?"), tpl_faction.get(e), why))

    spawns = []  # (map, side, x, y, reach, entry, guid, patrols)
    for r in _rows(txt, "creature"):
        mp = int(r["map"])
        if mp not in (0, 1):
            continue
        x, y = float(r["position_x"]), float(r["position_y"])
        for e in ([r["id"]] if r["id"] != "0" else entries.get(r["guid"], [])[:1]):
            s = side.get(e)
            if not s:
                if e in left:
                    note(mp, "A" if _side_of(e, faction_templates, tpl_faction) == "a" else "H", x, y, e, left[e])
                continue
            if events.get(r["guid"], 0) > 0:
                note(mp, s, x, y, e, "seasonal or event spawn")
                continue
            wander = float(r["spawndist"] or 0)
            reach = GUARD_YD + wander if s.isupper() else LIGHT_YD + min(wander, LIGHT_WANDER_YD)
            spawns.append((mp, s, x, y, reach, e, r["guid"], int(r["MovementType"] or 0) == PATROL))
    patrol: dict[str, list] = {}
    for r in _rows(txt, "creature_movement"):  # (patrols: each point)
        patrol.setdefault(r["Id"], []).append((float(r["PositionX"]), float(r["PositionY"])))
    # (a town: where its NPCs stand still. A patrol's points, and a patrolling NPC's own spot, count only within
    # TOWN_YD of one of its side's standing NPCs (a guard's, of its standing guards): a lone NPC walking a road is no
    # town. The Wandering Protector, a night elf giant walking Ashenvale's roads, drew an 87-circle "town" named
    # Greenpaw Village, item 99; a mounted mountaineer riding the Wetlands road past a dig site's workers, another)
    town: dict = {}
    for mp, s, x, y, _, _, g, walks in spawns:
        if not (walks and g in patrol):
            cells = town.setdefault((mp, s), {})
            cells.setdefault((math.floor(x / TOWN_YD), math.floor(y / TOWN_YD)), []).append((x, y))

    def in_town(mp, s, x, y):
        kx, ky = math.floor(x / TOWN_YD), math.floor(y / TOWN_YD)
        return any((x - ox) ** 2 + (y - oy) ** 2 <= TOWN_YD ** 2
                   for k in {s, s.upper()} for i in (-1, 0, 1) for j in (-1, 0, 1)
                   for ox, oy in town.get((mp, k), {}).get((kx + i, ky + j), ()))

    out: dict[int, dict[str, list]] = {}
    for mp, s, x, y, reach, e, g, walks in spawns:
        sides = out.setdefault(mp, {"A": [], "H": [], "a": [], "h": []})
        pts = patrol.get(g) if walks else None
        if pts is None or in_town(mp, s, x, y):
            sides[s].append((x, y, reach, e))
            note(mp, s, x, y, e, "")
        else:
            note(mp, s, x, y, e, "a lone patrol's spot")
        for px, py in pts or ():
            if in_town(mp, s, px, py):
                sides[s].append((px, py, GUARD_YD if s.isupper() else LIGHT_YD, e))
                note(mp, s, px, py, e, "")
            else:
                note(mp, s, px, py, e, "a lone patrol's road")
    for mp, sides in FOREVER_GUARDS.items():
        for s, circles in sides.items():
            out.setdefault(mp, {"A": [], "H": [], "a": [], "h": []})[s].extend(circles)
    return out


def _side_of(e, faction_templates, tpl_faction):
    ft = faction_templates.get(tpl_faction.get(e))
    return "a" if ft and ft["EnemyGroup"] & GROUP_ALLIANCE else "h"


def merge(points: list) -> list:
    """Circles close together as one (the biggest reach in each CELL_YD cell, at the cell's
    points' middle), each with the NPC most of its points are (their creature id, or None: x, y, r, id)."""
    cells: dict = {}
    for x, y, r, *who in points:
        k = (math.floor(x / CELL_YD), math.floor(y / CELL_YD))
        c = cells.setdefault(k, [0.0, 0.0, 0, 0.0, Counter()])
        c[0] += x
        c[1] += y
        c[2] += 1
        c[3] = max(c[3], r)
        if who and who[0]:
            c[4][who[0]] += 1
    return [(c[0] / c[2], c[1] / c[2], c[3] + CELL_YD / 2,
             min(c[4].items(), key=lambda kv: (-kv[1], int(kv[0])))[0] if c[4] else None) for c in cells.values()]


def _lua_text(t: str) -> str:
    return t.replace("\\", "\\\\").replace('"', '\\"')


def hostile_lua(cd, data_dir: Path) -> str:
    ft = {r["ID"]: r for r in cd.table("FactionTemplate")}
    pts = guard_points(data_dir, ft)
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    names = {r["Entry"]: r["Name"] for r in _rows(txt, "creature_template")}
    out = [f"-- GENERATED by `agps gen-addon-data` from client {cd.casc.version}. Do not edit by hand.",
           "-- The NPCs that would flag a player for PvP, per faction: circles { x, y, reach, ... } in world yards;",
           "-- A: the guards dangerous to Alliance players (the Horde's), H: to Horde players; a and h: the others",
           "-- (quest givers, vendors, flight masters, workers), lighter (Router.HOSTILE_LIGHT_FACTOR).",
           "-- ns.HostileGuards: for A and H, which guards each circle is (`at`: one creature id a circle, 0 for WoW",
           "-- Forever's own camps; `who`: their English names), for the zones' names (Nav.HostileTownName).",
           "local _, ns = ...", "ns.Hostile = {"]
    guards = []
    for cont in sorted(pts):
        out.append(f"  [{cont}] = {{")
        guards.append(f"  [{cont}] = {{")
        for s in ("A", "H", "a", "h"):
            circles = sorted(merge(pts[cont][s]), key=lambda c: c[:3])
            flat = ",".join(f"{x:.0f},{y:.0f},{r:.0f}" for x, y, r, _ in circles)
            out.append(f"    {s} = {{{flat}}},")
            if s.isupper():
                ids = [int(e) if e else 0 for *_, e in circles]
                who = ", ".join(f'[{e}] = "{_lua_text(names[str(e)])}"' for e in sorted(set(ids)) if e)
                guards.append(f"    {s} = {{ who = {{ {who} }},")
                guards.append(f"      at = {{{','.join(str(e) for e in ids)}}} }},")
        out.append("  },")
        guards.append("  },")
    out.append("}")
    out.append("ns.HostileGuards = {")
    out.extend(guards)
    out.append("}")
    return "\n".join(out) + "\n"
