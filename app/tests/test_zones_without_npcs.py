"""Zones with no shipped NPCs (asked 2026-11-23, after Riverglades turned out to have none: the 1.12 dump, the client's
files and the server snapshot have none there). Every zone on the continents (Data/Maps.lua's type 3, continents 0, 1
and 2991) gets at least one shipped NPC (Data/Npcs.lua) placed in it by Data/Zones.lua's grid, or is on the reviewed
list app/azerothgps/data/zones_without_npcs.json: a new zone without NPCs fails here until it's added there knowingly
(and its NPCs logged in the live game)."""
import json
import math

import lupa

from pathlib import Path

import azerothgps
from azerothgps.npcspots import NPCS_LUA, parse_lua
from azerothgps.paths import ADDON_DIR

ALLOW = Path(azerothgps.__file__).parent / "data" / "zones_without_npcs.json"
CONTINENTS = (0, 1, 2991)
ZONE_TILE = 1600 / 3


def _data(name):
    lua = lupa.LuaRuntime()
    lua.execute("ns = {}")
    loader = lua.eval("function(src, name) return assert(load(src, '@' .. name)) end")
    loader((ADDON_DIR / "Data" / name).read_text(encoding="utf-8"), name)("AzerothGPS", lua.globals().ns)
    return lua.globals().ns


def _zone_at(grids, cont, x, y):
    """Router.ZoneAt: the zone (uiMap) at world (x, y) on `cont` from Data/Zones.lua, 0 for none."""
    g = grids.get(cont)
    if not g:
        return 0
    runs = g.get(math.floor((32 - x / ZONE_TILE) * 16))
    col = math.floor((32 - y / ZONE_TILE) * 16)
    if not runs or col < 0:
        return 0
    c = 0
    for i in range(0, len(runs) - 1, 2):
        c += runs[i + 1]
        if col < c:
            return runs[i]
    return 0


def zones_without_npcs() -> dict[int, str]:
    """The zones (uiMap: name) no shipped NPC stands in: by Data/Zones.lua's grid, or for a zone the grid never names
    (Ironforge, Undercity, Zephras Isle: their parent zone's there) by its bounds in Data/Maps.lua."""
    maps = _data("Maps.lua").Maps
    zones, bounds = {}, {}
    for k in maps.keys():
        m = maps[k]
        if m.type == 3 and m.continent is not None and int(m.continent) in CONTINENTS:
            zones[int(k)] = str(m.name)
            if m.bounds:
                bounds[int(k)] = (int(m.continent), *(m.bounds[i] for i in range(1, 5)))
    zl = _data("Zones.lua").Zones
    grids, named = {}, set()
    for c in zl.keys():
        rows = zl[c].rows
        grids[int(c)] = {int(r): list(rows[r].values()) for r in rows.keys()}
        for runs in grids[int(c)].values():
            named.update(runs[0::2])
    _, npcs = parse_lua(NPCS_LUA.read_text(encoding="utf-8"))
    have = set()
    for n in npcs.values():
        for lv, x, y, _ in n["spawns"]:
            cont = 0 if lv == 10001 else lv  # (Undercity's level is the Eastern Kingdoms')
            have.add(_zone_at(grids, cont, x, y))
            for z, (bc, x0, y0, x1, y1) in bounds.items():
                if z not in named and bc == cont and x0 <= x <= x1 and y0 <= y <= y1:
                    have.add(z)
    return {z: name for z, name in sorted(zones.items()) if z not in have}


def test_zones_without_npcs_are_the_reviewed_ones():
    allowed = {int(k): v for k, v in json.loads(ALLOW.read_text(encoding="utf-8"))["zones"].items()}
    found = zones_without_npcs()
    new = {z: n for z, n in found.items() if z not in allowed}
    assert not new, (f"zone(s) with no shipped NPCs: {new}. Add them to {ALLOW.name} once reviewed (and log their "
                     "NPCs in the live game)")
    shipped = {z: n for z, n in allowed.items() if z not in found}
    assert not shipped, (f"zone(s) on {ALLOW.name} that have shipped NPCs now: {shipped}. Take them off the list")
