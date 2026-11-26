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

`agps mobs` reports; `--write` writes Data/Mobs.lua. Run it again when the dump changes.
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
ISLE_FILE = Path(__file__).parent / "data" / "isle_mobs.tsv"
ISLE = 2991
# (the query the isle's snapshot was made with, on that TrinityCore-style world database; the rows kept were the ones
# hostile to a side and friendly to neither by the client's FactionTemplate, their columns renamed as ISLE_FILE's)
ISLE_SQL = ("SELECT c.guid, c.id, c.map, c.position_x, c.position_y, c.position_z, c.MovementType, t.name, t.subname, "
            "t.faction, IF(c.npcflag <> 0, c.npcflag, t.npcflag), t.type, t.unit_flags, t.flags_extra, t.minlevel, "
            "t.maxlevel, t.`rank` FROM creature c JOIN creature_template t ON t.entry = c.id WHERE c.map = 2991")
CAMP_YD = 25.0


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


def _add(mobs, key, cid, name, lo, hi, sd, spawn):
    m = mobs.get(key)
    if m is None:
        m = mobs[key] = {"id": cid, "name": name, "lo": lo, "hi": hi, "side": sd, "spawns": []}
    m["id"], m["lo"], m["hi"] = min(m["id"], cid), min(m["lo"], lo), max(m["hi"], hi)
    if m["side"] != sd:
        m["side"] = "B"  # (an enemy of each side somewhere: listed once, for both)
    m["spawns"].append(spawn)


def build(data_dir: Path, ft: dict[int, dict] | None = None, isle: list[dict] | None = None, undercity=None):
    """(mobs {name: {id, name, lo, hi, side, spawns [(level, x, y, z)]}}, report {why left out: count}).
    Spawns as in the data (camps(): thinned); down in Undercity on its level (10001: the Apothecarium's captives), as
    npcs.py's `undercity(x, y, z)`."""
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
            _add(mobs, t["Name"], int(e), t["Name"], int(t["MinLevel"]), int(t["MaxLevel"]), sd, (level, x, y, z))
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
        _add(mobs, r["name"], int(r["id"]), r["name"], int(r["minlevel"]), int(r["maxlevel"]), sd,
             (ISLE, float(r["x"]), float(r["y"]), float(r["z"])))
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
    """Data/Mobs.lua: one line a mob in one long string, `id|name|min level|max level|side|spawns`."""
    lines = []
    for m in sorted(mobs.values(), key=lambda m: (m["id"], m["side"])):
        lines.append("|".join((str(m["id"]), m["name"], str(m["lo"]), str(m["hi"]), m["side"],
                               spawns_text(camps(m["spawns"], yd)))))
    body = "\n".join(lines)
    assert "]==]" not in body
    out = ["-- GENERATED by `agps mobs --write` from the CMaNGOS dump's creatures and Zephras Isle's (isle_mobs.tsv).",
           "-- Do not edit by hand. Every enemy mob, for the search only (1.4.0): one line each,",
           "-- id|name|min level|max level|side|spawns. Side: the enemy of A, H, or B (both). Spawns: one camp each,",
           "-- \"level x y z dx dy dz ...\" a level (whole yards, each after the first the change from the one before),",
           "-- split by \";\". Read at the first search (Layers.lua's L.ShippedMobs), never at login.",
           "local _, ns = ...",
           "ns.MobsPacked = [==[",
           body,
           "]==]"]
    return "\n".join(out) + "\n"
