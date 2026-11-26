"""The shipped destinations with no height source in range (1.4.0, Kooki3z 2026-11-23: every stop gets a height when
it's made, Nav.GuessStopZ: its own, an NPC's spot's, the grid's floor, the map's ground, a road's, NPC's or place's within
Nav.STOP_Z_YD; beyond that "height unknown"). Swept over the NPC spawns without a height, the capitals' and towns'
places, the map's points of interest and the dungeons' entrances, each asked of the addon's own Nav.GuessStopZ in the game
harness. Written to data/height_unknown.json for other tools to read: {"stops": [{id, name, cont or
map, x, y, source, why}]}, a dungeon's MapID in `map`. The addon says the same at run time to Nav.heightUnknownHook."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "height_unknown.json"


def _lua_list(t) -> list:
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []


def sweep(log=print) -> list:
    """Every shipped destination Nav.GuessStopZ finds no height for: [{id, name, cont|map, x, y, source, why}]."""
    from .gameharness import start

    lua, ns = start()
    N, L = ns.Nav, ns.Layers
    out = []

    def ask(source, name, cont, x, y, id=None, map=None):
        d = lua.table_from({"x": x, "y": y, "cont": cont})
        _z, src = N.GuessStopZ(d)
        if src == "unknown":
            row = {"id": id, "name": name, "x": round(x, 1), "y": round(y, 1), "source": source,
                   "why": "no height in range"}
            if map is not None:
                row["map"] = map
            else:
                row["cont"] = cont
            out.append(row)

    # (the hook quiet while sweeping: this is the offline list)
    N.heightUnknownHook = None
    npcs = L.ShippedNpcs()[0]  # (its list; the by-id and by-name too)
    n_npc = 0
    for n in _lua_list(npcs):
        sp = n.spawns
        for i in range(1, len(sp) - 2, 4):
            z = sp[i + 3]
            if z is None:
                n_npc += 1
                ask("npc", n.name, sp[i], sp[i + 1], sp[i + 2], id=n.id)
    n_place = 0
    for ui, c in (ns.CityPlaces or {}).items():
        for p in _lua_list(c):
            if p[4] is None:
                xy = lua.eval("function(L, ui, x, y) local wx, wy, lv = L.MapToWorld(ui, x / 100, y / 100) "
                              "return { wx, wy, lv } end")(L, ui, p[1], p[2])
                if xy[1] is not None:
                    n_place += 1
                    ask("city place", p[3], xy[3], xy[1], xy[2])
    for _ui, t in (ns.TownPlaces or {}).items():
        for p in _lua_list(t):
            if p.z is None and p.x is not None:
                n_place += 1
                ask("town place", p[1], t.cont, p.x, p.y)
    n_poi = 0
    for cont, lst in (ns.Pois or {}).items():
        for p in _lua_list(lst):
            n_poi += 1
            ask("poi", p[4], p[7] if p[7] is not None else cont, p[2], p[3], id=p[5])
    n_door = 0
    for _lv, inst in (ns.Instances or {}).items():
        for e in _lua_list(inst.entrances):
            n_door += 1
            ask("dungeon entrance", inst.name, e[1], e[2], e[3], map=inst.map)
    log(f"{len(out)} of {n_npc} NPC spawns, {n_place} places, {n_poi} points of interest and {n_door} dungeon "
        f"entrances with no height in range")
    return out


def write(stops: list, path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stops": stops}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
