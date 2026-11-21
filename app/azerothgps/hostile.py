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
"""

from __future__ import annotations

import gzip
import math
import re
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


def guard_points(data_dir: Path, faction_templates: dict[int, dict]) -> dict[int, dict[str, list]]:
    """{ continent: { "A": [(x, y, r)], "H": [...], "a": [...], "h": [...] } }: "A" is dangerous to Alliance players (its
    guards), "a" too, lighter (the other NPCs that would flag them for PvP)."""
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    side = {}  # entry -> "A" / "H"
    for r in _rows(txt, "creature_template"):
        ft = faction_templates.get(int(r["Faction"]))
        if not ft or not (int(ft["Flags"]) & PVP_FLAG or int(r["UnitFlags"] or 0) & UNIT_FLAG_PVP):
            continue
        enemy = ft["EnemyGroup"]
        guard = int(r["ExtraFlags"]) & GUARD_FLAG or GUARD_NAME.search(r["Name"])
        if enemy & GROUP_ALLIANCE and not enemy & GROUP_HORDE:
            side[r["Entry"]] = "A" if guard else "a"
        elif enemy & GROUP_HORDE and not enemy & GROUP_ALLIANCE:
            side[r["Entry"]] = "H" if guard else "h"
    out: dict[int, dict[str, list]] = {}
    spawn = {}  # guid -> (map, side)
    for r in _rows(txt, "creature"):
        s = side.get(r["id"])
        mp = int(r["map"])
        if s and mp in (0, 1):
            x, y = float(r["position_x"]), float(r["position_y"])
            wander = float(r["spawndist"] or 0)
            reach = GUARD_YD + wander if s.isupper() else LIGHT_YD + min(wander, LIGHT_WANDER_YD)
            out.setdefault(mp, {"A": [], "H": [], "a": [], "h": []})[s].append((x, y, reach))
            spawn[r["guid"]] = (mp, s)
    for r in _rows(txt, "creature_movement"):  # (patrols: each point)
        k = spawn.get(r["Id"])
        if k:
            out[k[0]][k[1]].append((float(r["PositionX"]), float(r["PositionY"]), GUARD_YD if k[1].isupper() else LIGHT_YD))
    for mp, sides in FOREVER_GUARDS.items():
        for s, circles in sides.items():
            out.setdefault(mp, {"A": [], "H": [], "a": [], "h": []})[s].extend(circles)
    return out


def merge(points: list) -> list:
    """Circles close together as one (the biggest reach in each CELL_YD cell, at the cell's
    points' middle)."""
    cells: dict = {}
    for x, y, r in points:
        k = (math.floor(x / CELL_YD), math.floor(y / CELL_YD))
        c = cells.setdefault(k, [0.0, 0.0, 0, 0.0])
        c[0] += x
        c[1] += y
        c[2] += 1
        c[3] = max(c[3], r)
    return [(c[0] / c[2], c[1] / c[2], c[3] + CELL_YD / 2) for c in cells.values()]


def hostile_lua(cd, data_dir: Path) -> str:
    ft = {r["ID"]: r for r in cd.table("FactionTemplate")}
    pts = guard_points(data_dir, ft)
    out = [f"-- GENERATED by `agps gen-addon-data` from client {cd.casc.version}. Do not edit by hand.",
           "-- The NPCs that would flag a player for PvP, per faction: circles { x, y, reach, ... } in world yards;",
           "-- A: the guards dangerous to Alliance players (the Horde's), H: to Horde players; a and h: the others",
           "-- (quest givers, vendors, flight masters, workers), lighter (Router.HOSTILE_LIGHT_FACTOR).",
           "local _, ns = ...", "ns.Hostile = {"]
    for cont in sorted(pts):
        out.append(f"  [{cont}] = {{")
        for s in ("A", "H", "a", "h"):
            circles = merge(pts[cont][s])
            flat = ",".join(f"{x:.0f},{y:.0f},{r:.0f}" for x, y, r in sorted(circles))
            out.append(f"    {s} = {{{flat}}},")
        out.append("  },")
    out.append("}")
    return "\n".join(out) + "\n"
