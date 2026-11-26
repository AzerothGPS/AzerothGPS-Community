"""Data checks against the walk grids (item 112, 1.4.1; gridcheck.py): the drawn roads with heights (ns.FloorTracks),
the capitals' and buildings' roads with node heights (Data/Capitals.lua, Data/Indoors.lua) and the shipped NPCs'
spawns (Data/Npcs.lua) against the city and world grids' floors, read from the addon's own files (no client: CI runs
it, in a few seconds).

A road or track that leaves the grid's floors or jumps between floors the grid doesn't join (Orgrimmar's old Wind Rider
tower coil, the model case: item 110), and an NPC off every floor round its spawn, fail the test unless listed in
data/grid_known_offenders.json with why (most are floors the grids lack: checked against the cities' collision and the
world mesh where those were at hand)."""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest

from azerothgps import gridcheck as G

KNOWN = json.loads((Path(__file__).parent / "data" / "grid_known_offenders.json").read_text(encoding="utf-8"))
COIL = "Capitals:1:1653,-4351,28>1673,-4341,60"  # (Orgrimmar's Wind Rider tower: the old coil up its ramp)
DORAS = (3310, 1, 1676.2, -4313.4, 61.7)  # (Wind Rider Master, on the tower's top: Data/Npcs.lua)


@pytest.fixture(scope="module")
def found():
    return {"tracks": G.track_offenders(), "roads": G.overlay_offenders(), "npcs": G.npc_offenders()}


def _new(found, kind):
    return {k: v for k, v in found[kind].items() if k not in KNOWN[kind]}


def _stale(found, kind):
    gone = sorted(set(KNOWN[kind]) - set(found[kind]))
    if gone:
        warnings.warn(f"grid_known_offenders.json's {kind} no longer offending (take them out): {gone}")


@pytest.mark.parametrize("kind", ["tracks", "roads", "npcs"])
def test_no_new_offenders(found, kind):
    new = _new(found, kind)
    _stale(found, kind)
    assert not new, (f"new {kind} off the grid's floors (fix the data, or list them in data/grid_known_offenders.json "
                     f"with why; `agps grid-check` prints them all): {new}")


def test_the_old_wind_rider_coil_is_caught_as_a_floor_jump(found):
    offs = found["roads"].get(COIL)
    assert offs and any(o["kind"] == "jump" and abs(o["dz"]) >= 9 for o in offs), offs


def test_a_track_on_the_grid_s_own_floors_is_clean():
    # (up the coil's stairs road's own points, at the city grid's floor under each: the floor followed, no jump)
    rid, cont, pts, zs, _st = next(r for r in G.overlay_roads(("Capitals.lua",)) if r[0] == COIL)
    g = G.city_grid_at(cont, pts[0], pts[1])
    xs, hs = [], []
    for x, y, z, _a in G._samples(pts, zs)[:10]:  # (its foot, before the coil climbs off its turn)
        i, j = g.ij(x, y)
        q, qz = min(g.surfaces(i, j), key=lambda sf: abs(sf[1] - z))
        xs += [x, y]
        hs.append(qz)
    assert G.check_track(cont, {"pts": xs, "zs": hs}) == []


def test_a_track_off_the_floors_and_a_drawn_jump_are_caught():
    cont = 1
    pts = [1640.0, -4380.0, 1645.7, -4363.3]  # (Orgrimmar's Valley of Strength, by the tower's foot)
    top = max(G.floors_round(cont, 1642.0, -4372.0)[0])  # (the street, a floor under it and the ground's under both)
    off = G.check_track(cont, {"pts": pts, "zs": [top + 30, top + 30]})
    assert [o["kind"] for o in off] == ["off"] and off[0]["yd"] >= G.TRACK_OFF_YD
    jump = G.check_track(cont, {"pts": [1640.0, -4380.0, 1641.0, -4379.0], "zs": [top, top + 20]})
    assert any(o["kind"] == "jump" for o in jump)


def test_an_npc_on_its_floor_passes_and_one_floating_is_caught():
    nid, level, x, y, z = DORAS
    assert G.check_spawn(level, x, y, z) is None
    bad = G.check_spawn(level, x, y, z + 25)
    assert bad and bad["kind"] == "floating" and bad["grid"] == "city"
    bad = G.check_spawn(level, x, y, z - 25)  # (between the tower's floors: none within NPC_Z)
    assert bad and bad["kind"] in ("floating", "under")


def test_the_overlay_ids_are_the_roads_ends():
    # (kept when Capitals.lua's roads are numbered again: the known list holds)
    ids = [r[0] for r in G.overlay_roads()]
    assert len(ids) > 3000 and all(i.count(">") == 1 for i in ids)


def test_the_decoders_read_the_grids_as_the_addon_does():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    _lua, ns = start()
    WG, CG = ns.WorldGrid, ns.CityGrid
    for cont, x, y in [(1, 300.0, -4700.0), (0, -9460.0, 60.0), (0, -2357.0, -2423.0), (1, 10758.0, 2209.0)]:
        t = WG.SurfacesAt(WG.Cont(cont), x, y)
        lua_zs = sorted(round(t[i].z, 2) for i in range(1, len(t) + 1))
        w = G.world_grid(cont)
        py_zs = sorted(round(z, 2) for z in w.cell_zs(math.floor(x / w.cell), math.floor(y / w.cell)))
        assert py_zs and py_zs == lua_zs, (cont, x, y)
    for name, x, y in [("Orgrimmar", 1671.0, -4337.0), ("Undercity", 1600.0, 230.0), ("Ironforge", -4840.0, -1080.0)]:
        c = CG.City(name)
        t = CG.SurfacesAt(c, x, y)
        lua_zs = sorted(round(t[i].z, 2) for i in range(1, len(t) + 1))
        g = next(g for g in G.city_grids() if g.name == name)
        py = g.surfaces(*g.ij(x, y))
        assert py and sorted(round(z, 2) for _q, z in py) == lua_zs, name
        # (and the links: each of the cell's surfaces walks onto the same neighbors as CityGrid.lua's Link)
        for q, _z in py:
            ci = CG.CellAt(c, x, y)
            h = int(c.h)
            lua_n = set()
            for d in range(1, 9):
                k = CG.Link(c, q, d)
                if k and k > 0:
                    ni, nj = ci // h + G.DX[d - 1], ci % h + G.DY[d - 1]
                    lua_n.add(int(CG.First(c, ni * h + nj)) + k - 1)
            assert lua_n <= g.neighbors(q), (name, q)
