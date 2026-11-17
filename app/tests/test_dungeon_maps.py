"""Dungeons' world maps from another WoW version (issue #4; app/azerothgps/dungeonmaps.py, Data/DungeonMaps.lua):
the inventory accounts for every dungeon and floor, only floors that match are shipped, and the map draws a
dungeon's own art over its world map in the terrain view (the world map alone in the map styles), aligned,
per floor, with nothing left over from another dungeon or floor, and as before where there's none."""

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from azerothgps import dungeonmaps as D
from azerothgps import interiors as I

REPO = Path(__file__).resolve().parents[2]
DATA_LUA = REPO / "addon" / "AzerothGPS" / "Data" / "DungeonMaps.lua"
GNOMEREGAN, DEADMINES, WAILING = 20090, 20036, 20043


def _inventory():
    return json.loads(D.INVENTORY.read_text(encoding="utf-8"))


# --- the inventory and the data shipped -------------------------------------------------------------------


def test_every_dungeon_and_floor_is_accounted_for():
    inv = _inventory()
    src = inv["source"]
    assert src["name"] and src["build"] and src["url"].startswith("https://") and src["build"] in src["url"]
    rows = inv["dungeons"]
    # (every level the addon has for a dungeon or raid, but the tram, is in it)
    text = (REPO / "addon" / "AzerothGPS" / "Data" / "Instances.lua").read_text(encoding="utf-8")
    levels = {int(m) for m in re.findall(r"^ns\.Instances\[(\d+)\] =", text, re.M)}
    assert levels and levels <= {e["level"] for e in rows}
    assert len({e["map"] for e in rows}) == len(rows)
    for e in rows:
        assert e["status"] in ("accepted", "skipped") and e["why"], e["name"]
        for f in e["floors"]:
            assert f["status"] in ("accepted", "skipped"), (e["name"], f["ui"])
            assert (f["status"] == "skipped") == bool(f["why"]), (e["name"], f["ui"])
            if f["status"] == "accepted":  # (every check passed, its evidence kept)
                ev = f["evidence"]
                assert ev["footprint_matched"] >= D.FOOTPRINT_MATCH and ev["inside_bounds"] >= D.ALIGN_SHARE
                assert ev["models_paired"] >= 1 and ev["art_tiles"] == len(f["data"]["art"]["tiles"]) > 0
        assert (e["status"] == "accepted") == any(f["status"] == "accepted" for f in e["floors"]), e["name"]
    # (the dungeons whose layout changed in the other version are skipped: they keep their map)
    by = {e["map"]: e for e in rows}
    assert by[90]["status"] == "accepted" and len(by[90]["floors"]) == 4
    for mid in (33, 43, 229):  # Shadowfang Keep, Wailing Caverns, Blackrock Spire
        assert by[mid]["status"] == "skipped", by[mid]["name"]
    assert all(e["status"] == "skipped" for e in rows if e["raid"])  # (dungeons only)


def test_only_the_accepted_floors_are_shipped():
    inv = _inventory()
    assert DATA_LUA.read_text(encoding="utf-8") == D.dungeon_maps_lua(inv)  # (written from the inventory)
    text = DATA_LUA.read_text(encoding="utf-8")
    shipped = {int(lvl): [int(u) for u in re.findall(r"\{ ui = (\d+),", body)]
               for lvl, body in re.findall(r"^  \[(\d+)\] = \{ name = .*? floors = \{\n(.*?)\n  \} \},", text, re.M | re.S)}
    want = {e["level"]: [f["ui"] for f in e["floors"] if f["status"] == "accepted"] for e in inv["dungeons"]}
    assert shipped == {k: v for k, v in want.items() if v}
    # (numbers and names only: the game's textures by file id, nothing of theirs in the data)
    assert "loadstring" not in text and "Interface\\" not in text


# --- the checks, on made-up models ---------------------------------------------------------------------------


class _Cd:
    def name(self, fid):
        return f"model{fid}.wmo"


class _Models:
    """A Models stand-in: placements, each model's groups (boxes, ids) and meshes (one flat square a group)."""

    def __init__(self, placements, wmos, terrain=False):
        self.cd, self.placements, self._w, self.terrain = _Cd(), placements, wmos, terrain

    def wmo(self, fid):
        return self._w[fid]["info"]

    def mesh(self, fid, gi):
        return self._w[fid]["mesh"][gi]

    def verts(self, fid, gi):
        return self.mesh(fid, gi)[0]


def _model(fid, rooms, gids):
    """A model of square rooms ((x0, y0, x1, y1) in its frame, at height 0..5), with MOGP ids `gids`."""
    boxes, mesh = [], []
    for x0, y0, x1, y1 in rooms:
        boxes.append((x0, y0, 0.0, x1, y1, 5.0))
        v = np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], np.float32)
        mesh.append((v, np.array([[0, 1, 2], [0, 2, 3]])))
    xs = [r[0] for r in rooms] + [r[2] for r in rooms]
    ys = [r[1] for r in rooms] + [r[3] for r in rooms]
    info = {"fid": fid, "n": len(rooms), "bbox": (min(xs), min(ys), 0.0, max(xs), max(ys), 5.0), "boxes": boxes,
            "gids": list(gids), "files": ()}
    return {fid: {"info": info, "mesh": mesh}}


def _placed(fid, x=100.0, y=200.0, yaw=0.0):
    # (a placement's world bounds: generous, as the MODF's)
    return I.Placement(fid, 1, x, y, 0.0, yaw, 0.0, (x - 80, y - 80, x + 80, y + 80))


ROOMS = [(-40, -40, -10, 40), (-10, -5, 40, 5), (40, -20, 60, 20)]


def _floor(gids=(11, 12, 13), tiles=1):
    # (yaw 0: local x is world -X, local y world -Y; the rooms then lie round (100, 200), in these bounds)
    return {"ui": 1, "name": "A floor", "index": 1, "bounds": (30.0, 140.0, 170.0, 260.0),
            "regions": [(30.0, 140.0, 170.0, 260.0)], "gids": list(gids),
            "art": {"w": 1002, "h": 668, "tiles": [(1000 + k, 0, 0, 256, 256, 256, 256) for k in range(tiles)]}}


def test_a_floor_laid_out_alike_is_accepted_with_its_heights_and_rooms():
    a = _Models([_placed(7)], _model(7, ROOMS, (11, 12, 13)))
    b = _Models([_placed(7)], _model(7, ROOMS, (11, 12, 13)))
    res = D.verify_floor(a, b, _floor(), art_ok=lambda fid: True)
    assert res["ok"], res["why"]
    assert res["evidence"]["footprint_matched"] == 1.0 and res["evidence"]["vertices_matched"] == 1.0
    assert res["z"] == (0.0, 5.0)
    r = res["rooms"]  # (round its rooms, within its bounds)
    assert 30 <= r[0] < r[2] <= 170 and 140 <= r[1] < r[3] <= 260


def test_a_model_whose_groups_were_numbered_anew_is_matched_by_its_groups():
    # (WoW Forever re-authored Blackrock Depths' and the Sunken Temple's models: new group ids, same rooms)
    a = _Models([_placed(8)], _model(8, ROOMS, (91, 92, 93)))
    b = _Models([_placed(7)], _model(7, ROOMS, (11, 12, 13)))
    res = D.verify_floor(a, b, _floor(), art_ok=lambda fid: True)
    assert res["ok"], res["why"]
    assert res["evidence"]["renumbered"] == 3


@pytest.mark.parametrize("change, why", [
    ("moved", "the models over it differ"),  # (placed elsewhere)
    ("turned", "the models over it differ"),
    ("rooms", "its rooms differ"),  # (a room of its added in the other version: the Upper Spire's revamp)
    ("art", "art tiles aren't in WoW Forever's client"),
    ("bounds", "line up"),  # (its map's bounds somewhere else)
])
def test_a_floor_that_doesnt_match_is_skipped(change, why):
    a = _Models([_placed(7)], _model(7, ROOMS, (11, 12, 13)))
    rooms, place, floor = ROOMS, _placed(7), _floor()
    if change == "moved":
        place = _placed(7, x=104.0)
    elif change == "turned":
        place = _placed(7, yaw=90.0)
    elif change == "rooms":
        rooms = ROOMS[:2] + [(40, -20, 60, 40)]
    elif change == "bounds":
        floor["bounds"] = (150.0, 140.0, 290.0, 260.0)
        floor["regions"] = [floor["bounds"]]
    b = _Models([place], _model(7, rooms, (11, 12, 13)))
    res = D.verify_floor(a, b, floor, art_ok=lambda fid: change != "art")
    assert not res["ok"] and why in res["why"]


def test_a_map_with_terrain_is_skipped_when_its_ground_differs():
    class Ground:
        def __init__(self, dz):
            self.dz = dz

        def sample(self, X, Y):
            h = np.asarray(X, float) * 0.01 + self.dz * (np.asarray(Y, float) > 200)
            return h, np.ones(h.shape, bool)

    a = _Models([_placed(7)], _model(7, ROOMS, (11, 12, 13)), terrain=True)
    b = _Models([_placed(7)], _model(7, ROOMS, (11, 12, 13)), terrain=True)
    assert D.verify_floor(a, b, _floor(), Ground(0), Ground(0), lambda fid: True)["ok"]
    res = D.verify_floor(a, b, _floor(), Ground(0), Ground(6.0), lambda fid: True)  # (half of it 6 yd higher)
    assert not res["ok"] and "ground" in res["why"]
    assert not D.verify_floor(a, b, _floor(), None, None, lambda fid: True)["ok"]  # (not compared: not accepted)


def test_a_skipped_dungeon_ships_nothing_and_an_accepted_ones_floors_ship_whole():
    inv = {"source": {"name": "S", "build": "1", "url": "u"}, "client": {"build": "2"}, "time": "t", "dungeons": [
        {"map": 1, "level": 20001, "name": "Kept", "raid": False, "status": "skipped", "why": "w",
         "floors": [{"ui": 5, "name": "x", "index": 1, "status": "skipped", "why": "w", "evidence": {}}]},
        {"map": 2, "level": 20002, "name": "Shown", "raid": False, "status": "accepted", "why": "1 of 2",
         "floors": [{"ui": 6, "name": "y", "index": 1, "status": "skipped", "why": "w", "evidence": {}},
                    {"ui": 7, "name": "z", "index": 2, "status": "accepted", "why": "", "evidence": {},
                     "data": {"bounds": [0, 0, 10, 10], "z": None, "rooms": [1, 1, 9, 9],
                              "art": {"w": 1002, "h": 668, "tiles": [[55, 0, 0, 256, 256, 256, 256]]}}}]}]}
    text = D.dungeon_maps_lua(inv)
    assert "[20001]" not in text and "ui = 6" not in text
    assert "[20002]" in text and "ui = 7" in text and "{55,0,0,256,256,256,256}" in text and "z = nil" in text


# --- the map ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def _laid(ns):
    """The quads the map drew last: [(file id, x, y, w, h, rot, sublayer)]."""
    q = ns.GPS.laidTiles.quads
    return [(q[i][1], q[i][2], q[i][3], q[i][4], q[i][5], q[i][6], q[i][11]) for i in range(1, len(q) + 1)]


def _floor_fids(ns, lvl):
    out = {}
    for f in ns.DungeonMaps[lvl].floors.values():
        out[f.ui] = {t[1] for t in f.tiles.values()}
    return out


def _show(lua, ns, lvl, style="minimap"):
    G = ns.GPS
    ns.settings.gps.style = style
    G.ShowInstance(lvl)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()  # (not the frame's pcall: a failure fails the test)


def _base_fids(ns):
    out = set()
    for lvl in ns.DungeonMaps.keys():
        for s in _floor_fids(ns, lvl).values():
            out |= s
    return out


def test_the_terrain_view_draws_the_dungeons_art_over_its_world_map(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    try:
        _show(lua, ns, GNOMEREGAN)
        f, alone = G.DungeonMapShown()
        assert f is not None and not alone
        fids = _floor_fids(ns, GNOMEREGAN)
        laid = _laid(ns)
        base = [q for q in laid if q[0] in fids[f.ui]]
        art = [q for q in laid if q[0] not in fids[f.ui]]
        assert base and art  # (both layers)
        assert not any(q[0] in s for ui, s in fids.items() if ui != f.ui for q in laid)  # (one floor's map)
        assert {q[6] for q in base} == {G.DUNGEON_MAP_SUBLAYER}
        assert min(q[6] for q in art) > G.DUNGEON_MAP_SUBLAYER  # (the dungeon's art over it)
        assert _shown(lua, lambda w: "Map: " + str(f.name) in str(w._text))  # (the floor's note names it)
        # the world map's styles: the world map alone
        _show(lua, ns, GNOMEREGAN, "zone")
        f, alone = G.DungeonMapShown()
        assert alone and _laid(ns) and all(q[0] in fids[f.ui] for q in _laid(ns))
    finally:
        ns.settings.gps.style = style
        G.Follow()


def _shown(lua, test):
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and test(w)]


def test_a_dungeon_without_a_world_map_is_drawn_as_before(game):
    # (Wailing Caverns: WoW Forever's is bigger than the other version's, skipped) its models' art only, in
    # every style, as before; and WoW Forever's own dungeons, their terrain's tiles
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    assert ns.DungeonMaps[WAILING] is None and ns.DungeonMaps[GNOMEREGAN] is not None
    own = next(lvl for lvl, l in ns.CityLevels.items() if l.terrain and l.instance)
    try:
        for lvl in (WAILING, own):
            for st in ("minimap", "zone"):
                _show(lua, ns, lvl, st)
                assert G.DungeonMapShown()[0] is None
                cx, cy, _cont, rot, s, half = G.ViewState()
                before = G.LayoutInstanceArt(cx, cy, lvl, rot, half / s, half, None)
                if len(before) == 0:
                    before = G.LayoutMinimap(cx, cy, ns.CityLevels[lvl].base, rot, half / s, half)
                assert [q[0] for q in _laid(ns)] == [before[i][1] for i in range(1, len(before) + 1)], (lvl, st)
                assert len(before) > 0
    finally:
        ns.settings.gps.style = style
        G.Follow()


def test_missing_world_map_art_falls_back_to_the_dungeons_own(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    dm = ns.DungeonMaps[GNOMEREGAN]
    saved = [f.tiles for f in dm.floors.values()]
    try:
        _show(lua, ns, GNOMEREGAN)
        with_map, maps = len(_laid(ns)), _base_fids(ns)
        for f in dm.floors.values():
            f.tiles = lua.table()  # (no art for any floor)
        G.Redraw()
        for st in ("minimap", "zone"):
            _show(lua, ns, GNOMEREGAN, st)
            assert G.DungeonMapShown()[0] is None
            laid = _laid(ns)
            assert laid and not {q[0] for q in laid} & maps and len(laid) < with_map
        ns.DungeonMaps[GNOMEREGAN] = None  # (none at all)
        _show(lua, ns, GNOMEREGAN)
        assert G.DungeonMapShown()[0] is None and _laid(ns)
    finally:
        ns.DungeonMaps[GNOMEREGAN] = dm
        for f, t in zip(dm.floors.values(), saved):
            f.tiles = t
        ns.settings.gps.style = style
        G.Follow()
    # a map style looking off the map's art: the dungeon's own art there, not nothing
    f = dm.floors[1]
    far = f.bounds[3] + 3000.0
    assert len(G.LayoutDungeonMap(far, f.bounds[4], f, 0.0, 200.0, 200.0)) == 0
    art = G.LayoutInstanceArt(far, f.bounds[4], GNOMEREGAN, 0.0, 200.0, 200.0, None)
    assert len(G.LayoutDungeon(far, f.bounds[4], GNOMEREGAN, 0.0, 200.0, 200.0, None, f, True)) == len(art)


def test_each_floor_shows_its_own_map_and_nothing_of_another(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    fids = _floor_fids(ns, GNOMEREGAN)
    try:
        _show(lua, ns, GNOMEREGAN)
        seen = set()
        for _ in range(len(G.InstanceFloors(GNOMEREGAN))):
            assert G.FloorStep(False)  # (a floor down)
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
            f = G.DungeonMapShown()[0]
            laid = {q[0] for q in _laid(ns)}
            assert laid & fids[f.ui] and not laid & (_base_fids(ns) - fids[f.ui])
            seen.add(f.ui)
        assert len(seen) >= 2  # (the floors' heights pick their maps)
        # another dungeon: nothing of the first left
        _show(lua, ns, DEADMINES)
        f = G.DungeonMapShown()[0]
        laid = {q[0] for q in _laid(ns)}
        assert f.ui in _floor_fids(ns, DEADMINES) and not laid & _base_fids_of(ns, GNOMEREGAN)
        # back to the land: no dungeon's map
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.DungeonMapShown()[0] is None and not {q[0] for q in _laid(ns)} & _base_fids(ns)
    finally:
        ns.settings.gps.style = style
        G.Follow()


def _base_fids_of(ns, lvl):
    out = set()
    for s in _floor_fids(ns, lvl).values():
        out |= s
    return out


def test_entering_and_leaving_a_dungeon_shows_and_drops_its_map(game):
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    f = ns.DungeonMaps[GNOMEREGAN].floors[1]
    x, y = (f.rooms[1] + f.rooms[3]) / 2, (f.rooms[2] + f.rooms[4]) / 2
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = {x}, {y}, 90, 0 AGPS_T = AGPS_T + 1")
    try:
        assert N.PlayerLevel(90) == GNOMEREGAN
        # (not over the terrain round its way in, G.InstanceTerrainSpot: there, no world map's parchment, as a cave's)
        lua.execute("AGPS_REAL_ITS = AGPS_NS.GPS.InstanceTerrainSpot; AGPS_NS.GPS.InstanceTerrainSpot = function() return nil end")
        G.Follow()
        G.Update()
        shown = G.DungeonMapShown()[0]
        assert shown is not None and {q[0] for q in _laid(ns)} & _floor_fids(ns, GNOMEREGAN)[shown.ui]
    finally:
        lua.execute("AGPS_NS.GPS.InstanceTerrainSpot = AGPS_REAL_ITS or AGPS_NS.GPS.InstanceTerrainSpot")
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()
        G.Update()
    assert G.DungeonMapShown()[0] is None and not {q[0] for q in _laid(ns)} & _base_fids(ns)


def _world_centers(G, quads, cx, cy, rot, s):
    out = {}
    for i in range(1, len(quads) + 1):
        q = quads[i]
        x, y = G.ScreenToWorld(cx, cy, q[2], q[3], rot, s)
        out.setdefault(q[1], []).append((x, y, q[6], q[7], q[8], q[9], q[10]))
    return out


def test_the_layers_stay_aligned_through_pan_zoom_turn_and_resize(game):
    # the world map's tiles land where its bounds put their pixels, and the dungeon's art where its models are,
    # from any view: both stay together as the map pans, zooms, turns (heading up) and is resized
    lua, ns = game
    G = ns.GPS
    f = ns.DungeonMaps[GNOMEREGAN].floors[1]
    b = f.bounds
    tiles = {t[1]: t for t in f.tiles.values()}
    ydx, ydy = (b[3] - b[1]) / f.artH, (b[4] - b[2]) / f.artW
    cx0, cy0 = (f.rooms[1] + f.rooms[3]) / 2, (f.rooms[2] + f.rooms[4]) / 2
    art_at = None
    for rot, zoom, half, pan in ((0.0, 300.0, 300.0, (0, 0)), (1.1, 300.0, 300.0, (0, 0)), (1.1, 150.0, 300.0, (40, -25)),
                                 (-2.5, 420.0, 520.0, (-30, 60)), (0.4, 700.0, 260.0, (5, 5))):
        cx, cy = cx0 + pan[0], cy0 + pan[1]
        s = half / zoom
        base = G.LayoutDungeonMap(cx, cy, f, rot, zoom, half)
        assert len(base) > 0
        for fid, pts in _world_centers(G, base, cx, cy, rot, s).items():
            t = tiles[fid]
            for x, y, qrot, l, r, top, bot in pts:
                assert qrot == pytest.approx(rot)
                u, v = t[2] + (l + r) / 2 * t[6], t[3] + (top + bot) / 2 * t[7]  # (the art pixel there)
                assert (x, y) == pytest.approx((b[3] - v * ydx, b[4] - u * ydy), abs=0.05)
        art = G.LayoutInstanceArt(cx, cy, GNOMEREGAN, rot, zoom, half, None)
        here = {fid: sorted((round(p[0], 1), round(p[1], 1)) for p in pts)
                for fid, pts in _world_centers(G, art, cx, cy, rot, s).items()}
        if art_at is None:
            art_at = here
        for fid in set(here) & set(art_at):  # (the same art in the same world spot from every view)
            assert [c for p in here[fid] for c in p] == pytest.approx([c for p in art_at[fid] for c in p], abs=0.2)


def test_outdoors_the_map_is_unchanged(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    try:
        for st in ("minimap", "zone"):
            ns.settings.gps.style = st
            G.Follow()
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
            assert G.DungeonMapShown()[0] is None and _laid(ns)
            assert not {q[0] for q in _laid(ns)} & _base_fids(ns)
            assert G.DUNGEON_MAP_SUBLAYER not in {q[6] for q in _laid(ns)}
    finally:
        ns.settings.gps.style = style
        G.Follow()
