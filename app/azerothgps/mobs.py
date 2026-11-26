"""Every enemy mob, for the search (1.4.0, Kooki3z 2026-11-22: "add all enemy mobs to the search function, only showing
the closest one in the list. If the mob level is orange or red to the player, show their level range like (11-12) or
(11) to the left of the enemies' name").

From the CMaNGOS dump (hostile.py's DUMP), its continents (maps 0 and 1; dungeons left out), and Zephras Isle's
(ISLE_FILE: a WoW Forever world database's spawns on map 2991 hostile to a side, numbers and names only, ISLE_SQL):
each creature hostile to the Alliance or the Horde by the client's FactionTemplate (npcs.py's `hostile`), and friendly
to neither (the other faction's guards and townsfolk are not mobs). Left out: critters, the unselectable and invisible
ones, the ones a seasonal event spawns, placeholders by name. Creatures of one name are one mob (the dump has a few ids
for some; the search lists a name once): the lowest id, the levels of all, the enemy of both sides when either.

Each mob's spawns are thinned to camps: a spawn within CAMP_YD of one kept on its level is that one (the search takes
the nearest spawn, and a camp's mobs walk about anyway). Kept as `level x y z`, whole yards, delta-coded within a level
(spawns()): one string, `ns.MobsPacked`, read at the first search (Layers' `L.ShippedMobs`: each line's head only; a
mob's spawns are read when it is found, `L.MobSpawns`), never at login. Search only: nothing routed or drawn but the
stop a player picks.

Each mob also has its rank (creature_template's Rank: 0 normal, 1 elite, 2 rare elite, 3 boss, 4 rare; of the
creatures of its name, an elite's over a plain rare's). Elite areas (Data/Elites.lua, item 91, Kooki3z 2026-11-26:
"avoid elite enemy areas", the Razorfen Downs quilboar a route from the Barrens' south cut through): the outdoor spawns
of the elites (ranks 1 to 3) on the continents and Zephras Isle (dungeons aren't in the data; Undercity's left out), each
a circle of ELITE_YD plus how far it wanders (at most ELITE_WANDER_YD), circles in one ELITE_CELL_YD cell merged, and
circles whose edges are within AREA_GAP_YD of each other one area, of one enemy side ("A", "H", "B"). An area needs
ELITE_MIN spawns (a lone rare elite or a quest's one elite is no area). Each area keeps its elites' levels: the router
avoids the areas whose top level is at or above the player's level plus the option's offset (Router.EliteMin), through
the guard zones' code (Router.HostileSide).

`agps mobs` reports; `--write` writes Data/Mobs.lua and Data/Elites.lua. Run it again when the dump changes.
"""
from __future__ import annotations

import csv
import gzip
import math
from collections import defaultdict
from pathlib import Path

from .hostile import DUMP, _rows
from .npcs import (ALLIANCE_FT, CRITTER, HORDE_FT, INVISIBLE, NOISE, NOT_SELECTABLE, UNDER_Z, UNDERCITY, _undercity,
                   faction_templates, friendly, hostile)
from .paths import ADDON_DIR

FILE = ADDON_DIR / "Data" / "Mobs.lua"
ELITES_FILE = ADDON_DIR / "Data" / "Elites.lua"
ISLE_FILE = Path(__file__).parent / "data" / "isle_mobs.tsv"
ISLE = 2991
# (the query the isle's snapshot was made with, on that TrinityCore-style world database; the rows kept were the ones
# hostile to a side and friendly to neither by the client's FactionTemplate, their columns renamed as ISLE_FILE's)
ISLE_SQL = ("SELECT c.guid, c.id, c.map, c.position_x, c.position_y, c.position_z, c.MovementType, t.name, t.subname, "
            "t.faction, IF(c.npcflag <> 0, c.npcflag, t.npcflag), t.type, t.unit_flags, t.flags_extra, t.minlevel, "
            "t.maxlevel, t.`rank` FROM creature c JOIN creature_template t ON t.entry = c.id WHERE c.map = 2991")
CAMP_YD = 25.0
ELITE_RANKS = (1, 2, 3)  # (creature_template.Rank: elite, rare elite, boss; 4 is a plain rare)
ELITE_YD = 25.0  # about how far an elite near the player's level notices them
ELITE_WANDER_YD = 15.0  # (its wander counted up to this)
ELITE_CELL_YD = 10.0  # elites' circles in one cell this size: one circle
AREA_GAP_YD = 40.0  # circles whose edges are this near each other: one area
ELITE_MIN = 3  # spawns an area needs


def mob_side(f: dict, alliance: dict, horde: dict) -> str | None:
    """Who mob faction template `f` is an enemy of: "A", "H", "B" (both); None: not a mob (hostile to neither, or one
    side's own: friendly to either)."""
    if friendly(f, alliance) or friendly(f, horde):
        return None
    ha, hh = hostile(f, alliance), hostile(f, horde)
    if ha and hh:
        return "B"
    if ha or hh:
        return "A" if ha else "H"
    return None


def _left_out(name: str, ctype: int, unit_flags: int, extra: int, event: bool) -> str | None:
    if event:
        return "seasonal"
    if ctype == CRITTER:
        return "critter"
    if unit_flags & NOT_SELECTABLE or extra & INVISIBLE:
        return "unselectable"
    if NOISE.search(name) or "|" in name:
        return "placeholder"
    return None


def _add(mobs, key, cid, name, lo, hi, sd, spawn, rank=0):
    m = mobs.get(key)
    if m is None:
        m = mobs[key] = {"id": cid, "name": name, "lo": lo, "hi": hi, "side": sd, "rank": rank, "spawns": []}
    m["id"], m["lo"], m["hi"] = min(m["id"], cid), min(m["lo"], lo), max(m["hi"], hi)
    m["rank"] = max(m.get("rank", 0), rank, key=lambda r: (r in ELITE_RANKS, r))  # (an elite's over a plain rare's)
    if m["side"] != sd:
        m["side"] = "B"  # (an enemy of each side somewhere: listed once, for both)
    m["spawns"].append(spawn)


def build(data_dir: Path, ft: dict[int, dict] | None = None, isle: list[dict] | None = None, undercity=None,
          elites: list | None = None):
    """(mobs {name: {id, name, lo, hi, side, rank, spawns [(level, x, y, z)]}}, report {why left out: count}).
    Spawns as in the data (camps(): thinned); down in Undercity on its level (10001: the Apothecarium's captives), as
    npcs.py's `undercity(x, y, z)`. With `elites` (a list), each elite's outdoor spawn appended to it: (continent, x, y,
    min level, max level, side, wander yards), for elite_areas()."""
    ft = ft if ft is not None else faction_templates()
    if undercity is None:
        undercity = _undercity()
    alliance, horde = ft[ALLIANCE_FT], ft[HORDE_FT]
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    tpl = {r["Entry"]: r for r in _rows(txt, "creature_template")}
    entries = defaultdict(list)  # (a spawn of one of several creatures: creature id 0)
    for r in _rows(txt, "creature_spawn_entry"):
        entries[r["guid"]].append(r["entry"])
    events = {r["guid"]: int(r["event"]) for r in _rows(txt, "game_event_creature")}
    report: dict[str, int] = defaultdict(int)
    mobs: dict[tuple, dict] = {}
    for s in _rows(txt, "creature"):
        m = int(s["map"])
        if m not in (0, 1):
            continue
        for e in ([s["id"]] if s["id"] != "0" else entries.get(s["guid"], [])):
            t = tpl.get(e)
            f = t and ft.get(int(t["Faction"]))
            if not f:
                report["unknown"] += 1
                continue
            sd = mob_side(f, alliance, horde)
            if sd is None:
                report["not an enemy"] += 1
                continue
            why = _left_out(t["Name"], int(t["CreatureType"]), int(t["UnitFlags"]), int(t["ExtraFlags"]),
                            events.get(s["guid"], 0) > 0)
            if why:
                report[why] += 1
                continue
            x, y, z = (float(s[k]) for k in ("position_x", "position_y", "position_z"))
            level = UNDERCITY if m == 0 and z < UNDER_Z and undercity(x, y, z) else m
            rank = int(t.get("Rank") or 0)
            _add(mobs, t["Name"], int(e), t["Name"], int(t["MinLevel"]), int(t["MaxLevel"]), sd, (level, x, y, z), rank)
            if elites is not None and rank in ELITE_RANKS and level == m:
                elites.append((m, x, y, int(t["MinLevel"]), int(t["MaxLevel"]), sd, float(s.get("spawndist") or 0)))
            report["kept"] += 1
    for r in (isle if isle is not None else isle_rows()):
        f = ft.get(int(r["faction"]))
        sd = f and mob_side(f, alliance, horde)
        if not sd:
            report["not an enemy"] += 1
            continue
        why = _left_out(r["name"], int(r["type"]), int(r["unit_flags"]), int(r["flags_extra"]), False)
        if why:
            report[why] += 1
            continue
        rank = int(r.get("rank") or 0)
        _add(mobs, r["name"], int(r["id"]), r["name"], int(r["minlevel"]), int(r["maxlevel"]), sd,
             (ISLE, float(r["x"]), float(r["y"]), float(r["z"])), rank)
        if elites is not None and rank in ELITE_RANKS:
            elites.append((ISLE, float(r["x"]), float(r["y"]), int(r["minlevel"]), int(r["maxlevel"]), sd, 0.0))
        report["kept"] += 1
    return mobs, dict(report)


def isle_rows(path: Path = ISLE_FILE) -> list[dict]:
    """ISLE_FILE's rows (tab-separated, a header line)."""
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def camps(spawns: list, yd: float = CAMP_YD) -> list:
    """`spawns` (level, x, y, z) thinned: one within `yd` of one kept on its level is left out (in their order)."""
    kept: list = []
    for p in spawns:
        if not any(k[0] == p[0] and math.hypot(k[1] - p[1], k[2] - p[2]) <= yd for k in kept):
            kept.append(p)
    return kept


def spawns_text(spawns: list) -> str:
    """Spawns as `level x y z dx dy dz ...` a level, split by ";": whole yards, each after the first the change from the
    one before (sorted by x within a level)."""
    groups = []
    by: dict[int, list] = defaultdict(list)
    for lv, x, y, z in spawns:
        by[lv].append((round(x), round(y), round(z)))
    for lv in sorted(by):
        pts = sorted(set(by[lv]))
        nums = [lv, *pts[0]]
        for a, b in zip(pts, pts[1:]):
            nums += [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
        groups.append(" ".join(map(str, nums)))
    return ";".join(groups)


def read_spawns(text: str) -> list:
    """spawns_text's back: [(level, x, y, z)] (the tests')."""
    out = []
    for g in text.split(";"):
        n = [int(v) for v in g.split()]
        lv, x, y, z = n[:4]
        out.append((lv, x, y, z))
        for i in range(4, len(n), 3):
            x, y, z = x + n[i], y + n[i + 1], z + n[i + 2]
            out.append((lv, x, y, z))
    return out


def lua_text(mobs: dict, yd: float = CAMP_YD) -> str:
    """Data/Mobs.lua: one line a mob in one long string, `id|name|min level|max level|side|rank|spawns`."""
    lines = []
    for m in sorted(mobs.values(), key=lambda m: (m["id"], m["side"])):
        lines.append("|".join((str(m["id"]), m["name"], str(m["lo"]), str(m["hi"]), m["side"], str(m.get("rank", 0)),
                               spawns_text(camps(m["spawns"], yd)))))
    body = "\n".join(lines)
    assert "]==]" not in body
    out = ["-- GENERATED by `agps mobs --write` from the CMaNGOS dump's creatures and Zephras Isle's (isle_mobs.tsv).",
           "-- Do not edit by hand. Every enemy mob, for the search only (1.4.0): one line each,",
           "-- id|name|min level|max level|side|rank|spawns. Side: the enemy of A, H, or B (both). Rank: creature_template's",
           "-- (0 normal, 1 elite, 2 rare elite, 3 boss, 4 rare). Spawns: one camp each,",
           "-- \"level x y z dx dy dz ...\" a level (whole yards, each after the first the change from the one before),",
           "-- split by \";\". Read at the first search (Layers.lua's L.ShippedMobs), never at login.",
           "local _, ns = ...",
           "ns.MobsPacked = [==[",
           body,
           "]==]"]
    return "\n".join(out) + "\n"


def elite_areas(elites: list) -> dict:
    """{ continent: [ {lo, hi, side, n (spawns), circles [(x, y, r)]} ] }: the elites' spawns (build()'s `elites`) as
    areas: each a circle of ELITE_YD plus its wander (up to ELITE_WANDER_YD); circles in one ELITE_CELL_YD cell merged
    (their middle, the biggest reach plus half a cell); circles whose edges are within AREA_GAP_YD one area, per enemy
    side; ELITE_MIN spawns at least. Sorted by continent, then the area's first circle, for a stable file."""
    groups: dict = defaultdict(list)
    for cont, x, y, lo, hi, sd, wander in elites:
        groups[(cont, sd)].append((x, y, ELITE_YD + min(max(wander, 0.0), ELITE_WANDER_YD), lo, hi))
    out: dict = defaultdict(list)
    cell = 2 * (ELITE_YD + ELITE_WANDER_YD) + AREA_GAP_YD
    for (cont, sd), pts in sorted(groups.items()):
        n = len(pts)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        buckets: dict = defaultdict(list)
        for i, p in enumerate(pts):
            buckets[(math.floor(p[0] / cell), math.floor(p[1] / cell))].append(i)
        for i, p in enumerate(pts):
            kx, ky = math.floor(p[0] / cell), math.floor(p[1] / cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in buckets.get((kx + dx, ky + dy), ()):
                        q = pts[j]
                        if j > i and math.hypot(p[0] - q[0], p[1] - q[1]) <= p[2] + q[2] + AREA_GAP_YD:
                            a, b = find(i), find(j)
                            if a != b:
                                parent[a] = b
        members: dict = defaultdict(list)
        for i in range(n):
            members[find(i)].append(pts[i])
        for ms in members.values():
            if len(ms) < ELITE_MIN:
                continue
            cells: dict = {}
            for x, y, r, *_ in ms:
                k = (math.floor(x / ELITE_CELL_YD), math.floor(y / ELITE_CELL_YD))
                c = cells.setdefault(k, [0.0, 0.0, 0, 0.0])
                c[0], c[1], c[2], c[3] = c[0] + x, c[1] + y, c[2] + 1, max(c[3], r)
            circles = sorted((round(c[0] / c[2]), round(c[1] / c[2]), round(c[3] + ELITE_CELL_YD / 2))
                             for c in cells.values())
            out[cont].append({"lo": min(m[3] for m in ms), "hi": max(m[4] for m in ms), "side": sd, "n": len(ms),
                              "circles": circles})
    for cont in out:
        out[cont].sort(key=lambda a: (a["circles"][0], a["side"]))
    return dict(sorted(out.items()))


def elites_lua(areas: dict) -> str:
    """Data/Elites.lua: ns.EliteAreas[continent] = { { min level, max level, side, { x, y, r, ... } }, ... }."""
    out = ["-- GENERATED by `agps mobs --write` from the CMaNGOS dump's creatures and Zephras Isle's (isle_mobs.tsv).",
           "-- Do not edit by hand. Elite enemy areas (item 91; mobs.py's elite_areas): per continent, each area",
           "-- { min level, max level, side (the enemy of A, H or B: both), { x, y, reach, ... } } in world yards.",
           "-- Routes keep out of the ones at or above the player's level plus the option's offset (Router.EliteMin), as",
           "-- they keep out of the other faction's guards (Router.HostileSide); drawn gold on the map.",
           "local _, ns = ...",
           "ns.EliteAreas = {"]
    for cont, areas in areas.items():
        out.append(f"  [{cont}] = {{")
        for a in areas:
            flat = ",".join(str(v) for c in a["circles"] for v in c)
            out.append(f'    {{ {a["lo"]}, {a["hi"]}, "{a["side"]}", {{ {flat} }} }},')
        out.append("  },")
    out.append("}")
    return "\n".join(out) + "\n"
