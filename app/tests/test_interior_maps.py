"""Interior maps from another WoW version (issue #41; app/azerothgps/interiormaps.py, Data/InteriorMaps.lua): the
inventory accounts for every candidate map, the capitals and WoW Forever's caves; only floors that match are shipped;
and the map draws a cave's own art over its world map in the terrain view (the world map alone in the map styles),
and the inside map over it, aligned, with nothing left over from another interior, and as before where there's none."""

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from azerothgps import dungeonmaps as D
from azerothgps import interiormaps as IM
from azerothgps import interiors as I

REPO = Path(__file__).resolve().parents[2]
DATA_LUA = REPO / "addon" / "AzerothGPS" / "Data" / "InteriorMaps.lua"
CAVES_LUA = REPO / "addon" / "AzerothGPS" / "Data" / "Caves.lua"


def _inventory():
    return json.loads(IM.INVENTORY.read_text(encoding="utf-8"))


# --- the inventory and the data shipped -------------------------------------------------------------------


def test_every_interior_map_capital_and_cave_is_accounted_for():
    inv = _inventory()
    src = inv["source"]
    assert src["name"] and src["build"] and src["url"].startswith("https://") and src["build"] in src["url"]
    rows = inv["interiors"]
    uis = [ui for e in rows for ui in e["uis"]]
    assert uis and len(uis) == len(set(uis))  # (each of the source's maps once)
    for e in rows:
        assert e["status"] in ("accepted", "skipped") and e["why"], e["name"]
        assert sorted(f["ui"] for f in e["floors"]) == sorted(e["uis"]), e["name"]
        for f in e["floors"]:
            assert f["status"] in ("accepted", "skipped"), (e["name"], f["ui"])
            assert (f["status"] == "skipped") == bool(f["why"]), (e["name"], f["ui"])
            if f["status"] == "accepted":  # (every check passed, its evidence kept)
                ev = f["evidence"]
                assert ev["checked"] in ("indoor rooms", "the whole map")
                assert ev["footprint_matched"] >= D.FOOTPRINT_MATCH and ev["inside_bounds"] >= D.ALIGN_SHARE
                assert ev["models_paired"] >= 1 and ev["art_tiles"] == len(f["data"]["art"]["tiles"]) > 0
                if ev["checked"] == "the whole map":
                    assert ev["ground_matched"] >= D.TERRAIN_SHARE
                assert f["data"]["places"]
        assert (e["status"] == "accepted") == any(f["status"] == "accepted" for f in e["floors"]), e["name"]
    by = {e["name"]: e for e in rows}
    # (mines whose rooms are WoW Forever's; the ones the other version rebuilt skipped: they keep their map)
    for name in ("Fargodeep Mine", "Jasperlode Mine", "The Gaping Chasm", "Burning Blade Coven"):
        assert by[name]["status"] == "accepted", name
    assert len([f for f in by["Fargodeep Mine"]["floors"] if f["status"] == "accepted"]) == 2
    for name in ("Frostmane Hold", "Skull Rock", "OldIronforge", "Uldaman"):
        assert by[name]["status"] == "skipped", name
    # every capital, Ironforge too: WoW Forever has their maps
    assert {c["name"] for c in inv["cities"]} == set(IM.CAPITALS)
    for c in inv["cities"]:
        assert c["status"] in ("skipped", "unavailable") and c["why"]
    assert all(c["fv_maps"] for c in inv["cities"])
    # every cave of the addon's (named) is accounted for, and each accepted one has a shipped map of its models
    caves = {(c["cont"], c["name"]): c for c in inv["caves"]}
    for c in inv["caves"]:
        assert c["status"] in ("accepted", "skipped", "unavailable") and c["why"]
    text = CAVES_LUA.read_text(encoding="utf-8")
    for cont in (0, 1):
        body = text.split(f"ns.Caves[{cont}] = {{", 1)[1].split("\n}", 1)[0]
        for name in set(re.findall(r'^  \{ "([^"]+)", "cave', body, re.M)):
            assert (cont, name) in caves, (cont, name)
    assert caves[(0, "Fargodeep Mine")]["status"] == "accepted"


def test_only_the_accepted_floors_are_shipped():
    inv = _inventory()
    assert DATA_LUA.read_text(encoding="utf-8") == IM.interior_maps_lua(inv)  # (written from the inventory)
    text = DATA_LUA.read_text(encoding="utf-8")
    shipped = sorted(int(u) for u in re.findall(r"\{ ui = (\d+),", text))
    want = sorted(f["ui"] for e in inv["interiors"] for f in e["floors"] if f["status"] == "accepted")
    assert shipped == want and shipped
    # (numbers and names only: the game's textures by file id, nothing of theirs in the data)
    assert "loadstring" not in text and "Interface\\" not in text
    assert "Data\\InteriorMaps.lua" in (REPO / "addon" / "AzerothGPS" / "AzerothGPS.toc").read_text(encoding="utf-8")


def test_a_skipped_interior_ships_nothing_and_an_accepted_ones_floors_ship_whole():
    inv = {"source": {"name": "S", "build": "1", "url": "u"}, "client": {"build": "2"}, "time": "t", "cities": [],
           "caves": [], "interiors": [
               {"name": "Kept", "cont": 0, "uis": [5], "status": "skipped", "why": "w",
                "floors": [{"ui": 5, "name": "x", "index": 0, "status": "skipped", "why": "w", "evidence": {}}]},
               {"name": "Shown", "cont": 1, "uis": [6, 7], "status": "accepted", "why": "1 of 2",
                "floors": [{"ui": 6, "name": "y", "index": 1, "status": "skipped", "why": "w", "evidence": {}},
                           {"ui": 7, "name": "z", "index": 2, "status": "accepted", "why": "", "evidence": {},
                            "data": {"bounds": [0, 0, 10, 10], "z": None, "rooms": [1, 1, 9, 9], "places": [[3.5, 4.25]],
                                     "art": {"w": 1002, "h": 668, "tiles": [[55, 0, 0, 256, 256, 256, 256]]}}}]}]}
    text = IM.interior_maps_lua(inv)
    assert "[0] =" not in text and "ui = 5" not in text and "ui = 6" not in text
    assert "[1] =" in text and "ui = 7" in text and "{55,0,0,256,256,256,256}" in text and "z = nil" in text
    assert "places = { 3.50, 4.25 }" in text and 'map = "Shown"' in text


# --- the checks, on made-up models ---------------------------------------------------------------------------


class _Cd:
    def name(self, fid):
        return f"model{fid}.wmo"


class _Models:
    """A Models stand-in (as test_dungeon_maps'): placements, each model's groups (boxes, flags, ids) and meshes."""

    def __init__(self, placements, wmos, terrain=True):
        self.cd, self.placements, self._w, self.terrain = _Cd(), placements, wmos, terrain

    def wmo(self, fid):
        return self._w[fid]["info"]

    def mesh(self, fid, gi):
        return self._w[fid]["mesh"][gi]

    def verts(self, fid, gi):
        return self.mesh(fid, gi)[0]


def _model(fid, rooms, gids, indoor=True):
    boxes, mesh = [], []
    for x0, y0, x1, y1 in rooms:
        boxes.append((x0, y0, 0.0, x1, y1, 5.0))
        v = np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], np.float32)
        mesh.append((v, np.array([[0, 1, 2], [0, 2, 3]])))
    xs = [r[0] for r in rooms] + [r[2] for r in rooms]
    ys = [r[1] for r in rooms] + [r[3] for r in rooms]
    info = {"fid": fid, "n": len(rooms), "bbox": (min(xs), min(ys), 0.0, max(xs), max(ys), 5.0), "boxes": boxes,
            "flags": [IM.INDOOR if indoor else 0x8] * len(rooms), "gids": list(gids), "files": ()}
    return {fid: {"info": info, "mesh": mesh}}


def _placed(fid, x=100.0, y=200.0, yaw=0.0, r=80.0):
    return I.Placement(fid, 1, x, y, 0.0, yaw, 0.0, (x - r, y - r, x + r, y + r))


ROOMS = [(-40, -40, -10, 40), (-10, -5, 40, 5), (40, -20, 60, 20)]


def _floor(gids=(11, 12, 13)):
    # (a cave's map: its bounds wider than its rooms, as the source's parchment round them)
    return {"ui": 1, "name": "A mine", "index": 0, "bounds": (0.0, 100.0, 200.0, 300.0),
            "regions": [(0.0, 100.0, 200.0, 300.0)], "gids": list(gids),
            "art": {"w": 1002, "h": 668, "tiles": [(1000, 0, 0, 256, 256, 256, 256)]}}


class _Ground:
    def __init__(self, dz):
        self.dz = dz

    def sample(self, X, Y):
        h = np.asarray(X, float) * 0.01 + self.dz * (np.asarray(Y, float) > 200)
        return h, np.ones(h.shape, bool)


def _models(extra=(), indoor=True):
    w = _model(7, ROOMS, (11, 12, 13), indoor)
    for p in extra:
        w.update(_model(p.wmo, [(-2, -2, 2, 2)], (99,), True))
    return _Models([_placed(7, r=60.0)] + list(extra), w)


def test_an_indoor_map_is_accepted_though_the_land_over_it_changed():
    # (Cataclysm reshaped the hills over Fargodeep Mine: its rooms, all the map draws, are the same)
    res = IM.verify_interior(_models(), _models(), _floor(), _Ground(0), _Ground(6.0), lambda fid: True)
    assert res["ok"], res["why"]
    ev = res["evidence"]
    assert ev["checked"] == "indoor rooms" and ev["ground_matched"] < D.TERRAIN_SHARE  # (evidence only)
    assert res["places"] == [[100.0, 200.0]] and res["z"] == (0.0, 5.0)


def test_a_map_of_outdoor_pieces_is_checked_as_the_whole_map():
    # (its art may draw the land: the ground must be the same, as a dungeon's with terrain)
    a, b = _models(indoor=False), _models(indoor=False)
    assert IM.verify_interior(a, b, _floor(), _Ground(0), _Ground(0), lambda fid: True)["ok"]
    res = IM.verify_interior(a, b, _floor(), _Ground(0), _Ground(6.0), lambda fid: True)
    assert not res["ok"] and "ground" in res["why"] and res["evidence"]["checked"] == "the whole map"
    # (a map not tied to any model's rooms: the same)
    res = IM.verify_interior(_models(), _models(), _floor(gids=()), _Ground(0), _Ground(6.0), lambda fid: True)
    assert not res["ok"] and res["evidence"]["checked"] == "the whole map"


def test_a_model_added_far_off_the_rooms_doesnt_count_but_one_among_them_does():
    # (a zeppelin tower out on the land over the parchment's corner: not the cave's; a new model in its rooms is)
    far = _placed(8, x=10.0, y=110.0, r=3.0)
    near = _placed(8, x=110.0, y=200.0, r=3.0)
    assert IM.verify_interior(_models(), _models([far]), _floor(), _Ground(0), _Ground(0), lambda fid: True)["ok"]
    res = IM.verify_interior(_models(), _models([near]), _floor(), _Ground(0), _Ground(0), lambda fid: True)
    assert not res["ok"] and "models over it differ" in res["why"]
    # (on a whole map's check, the far one counts too)
    res = IM.verify_interior(_models(indoor=False), _Models([_placed(7, r=60.0), far], {
        **_model(7, ROOMS, (11, 12, 13), False), **_model(8, [(-2, -2, 2, 2)], (99,))}), _floor(), _Ground(0), _Ground(0),
        lambda fid: True)
    assert not res["ok"] and "models over it differ" in res["why"]


@pytest.mark.parametrize("change, why", [
    ("moved", "the models over it differ"),
    ("turned", "the models over it differ"),
    ("rooms", "its rooms differ"),
    ("art", "art tiles aren't in WoW Forever's client"),
    ("bounds", "line up"),
])
def test_an_indoor_map_that_doesnt_match_is_skipped(change, why):
    a = _models()
    rooms, place, floor = ROOMS, _placed(7, r=60.0), _floor()
    if change == "moved":
        place = _placed(7, x=104.0, r=60.0)
    elif change == "turned":
        place = _placed(7, yaw=90.0, r=60.0)
    elif change == "rooms":
        rooms = ROOMS[:2] + [(40, -20, 60, 40)]
    elif change == "bounds":
        floor["bounds"] = (150.0, 100.0, 350.0, 300.0)
        floor["regions"] = [floor["bounds"]]
    b = _Models([place], _model(7, rooms, (11, 12, 13)))
    res = IM.verify_interior(a, b, floor, _Ground(0), _Ground(0), lambda fid: change != "art")
    assert not res["ok"] and why in res["why"], res["why"]


# --- the map ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def _laid(ns):
    q = ns.GPS.laidTiles.quads
    return [(q[i][1], q[i][2], q[i][3], q[i][4], q[i][5], q[i][6], q[i][11]) for i in range(1, len(q) + 1)]


def _map_fids(ns):
    """{ui: the floor's art file ids} of every interior map."""
    out = {}
    for cont in ns.InteriorMaps.keys():
        for f in ns.InteriorMaps[cont].values():
            out[f.ui] = {t[1] for t in f.tiles.values()}
    return out


def _all_fids(ns):
    out = set()
    for s in _map_fids(ns).values():
        out |= s
    return out


def _cave(ns, cont, name):
    caves = ns.Caves[cont]
    for i in range(1, len(caves) + 1):
        if caves[i][1] == name:
            return caves[i][2]
    raise AssertionError(name)


def _show_cave(lua, ns, cont, key, style="minimap"):
    G = ns.GPS
    ns.settings.gps.style = style
    assert G.ShowCave(cont, key)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()  # (not the frame's pcall: a failure fails the test)


def test_a_caves_map_draws_its_own_art_over_its_world_map(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    try:
        _show_cave(lua, ns, 1, _cave(ns, 1, "Burning Blade Coven"))
        f, alone = G.InteriorMapShown()
        assert f is not None and not alone and str(f.map) == "Burning Blade Coven"
        fids = _map_fids(ns)
        laid = _laid(ns)
        base = [q for q in laid if q[0] in fids[f.ui]]
        art = [q for q in laid if q[0] not in fids[f.ui]]
        assert base and art  # (both layers)
        assert {q[6] for q in base} == {G.DUNGEON_MAP_SUBLAYER}
        assert min(q[6] for q in art) > G.DUNGEON_MAP_SUBLAYER  # (the cave's art over it)
        # the world map's styles: the world map alone
        _show_cave(lua, ns, 1, _cave(ns, 1, "Burning Blade Coven"), "zone")
        f, alone = G.InteriorMapShown()
        assert alone and _laid(ns) and all(q[0] in fids[f.ui] for q in _laid(ns))
    finally:
        ns.settings.gps.style = style
        G.Follow()


def test_a_two_floor_interiors_floors_each_show_their_own_map(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    fids = _map_fids(ns)
    try:
        _show_cave(lua, ns, 0, _cave(ns, 0, "Fargodeep Mine"))
        art = G.CaveArt(0, _cave(ns, 0, "Fargodeep Mine"))
        assert len(G.InteriorMapFloors(0, art.list)) == 2
        seen = set()
        for _ in range(len(G.InstanceFloors(art)) + 1):
            f = G.InteriorMapShown()[0]
            laid = {q[0] for q in _laid(ns)}
            assert f is not None and laid & fids[f.ui] and not laid & (_all_fids(ns) - fids[f.ui])
            seen.add(f.ui)
            if not G.FloorStep(False):
                break
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        assert len(seen) == 2  # (the floors' heights pick their maps)
    finally:
        ns.settings.gps.style = style
        G.Follow()


def test_a_cave_without_a_world_map_is_drawn_as_before_and_nothing_is_left_over(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    key = _cave(ns, 0, "Dreadmaul Rock")  # (the other version's isn't WoW Forever's: none)
    art = G.CaveArt(0, key)
    assert art and len(G.InteriorMapFloors(0, art.list)) == 0
    try:
        _show_cave(lua, ns, 1, _cave(ns, 1, "Burning Blade Coven"))  # (one with a map first)
        assert G.InteriorMapShown()[0] is not None
        for st in ("minimap", "zone"):
            _show_cave(lua, ns, 0, key, st)
            assert G.InteriorMapShown()[0] is None
            cx, cy, _cont, rot, s, half = G.ViewState()
            band = None
            before = G.LayoutInstanceArt(cx, cy, art, rot, half / s, half, band)
            assert len(before) > 0
            assert [q[0] for q in _laid(ns)] == [before[i][1] for i in range(1, len(before) + 1)], st
        # back to the land: no interior's map
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.InteriorMapShown()[0] is None and not {q[0] for q in _laid(ns)} & _all_fids(ns)
        assert G.DUNGEON_MAP_SUBLAYER not in {q[6] for q in _laid(ns)}
    finally:
        ns.settings.gps.style = style
        G.Follow()


def test_missing_world_map_art_falls_back_to_the_caves_own(game):
    lua, ns = game
    G = ns.GPS
    style = ns.settings.gps.style
    key = _cave(ns, 1, "Burning Blade Coven")
    orig = ns.InteriorMaps
    floors = orig[1]
    saved = [f.tiles for f in floors.values()]
    try:
        _show_cave(lua, ns, 1, key)
        with_map, maps = len(_laid(ns)), _all_fids(ns)
        for f in floors.values():
            f.tiles = lua.table()  # (no art for any floor)
        G.Redraw()
        for st in ("minimap", "zone"):
            _show_cave(lua, ns, 1, key, st)
            assert G.InteriorMapShown()[0] is None
            laid = _laid(ns)
            assert laid and not {q[0] for q in laid} & maps and len(laid) < with_map
        # (none at all)
        ns.InteriorMaps = None
        G.interiorMapsOf = lua.table()
        G.Redraw()
        _show_cave(lua, ns, 1, key)
        assert G.InteriorMapShown()[0] is None and _laid(ns)
    finally:
        ns.InteriorMaps = orig
        for f, t in zip(floors.values(), saved):
            f.tiles = t
        G.interiorMapsOf = lua.table()
        ns.settings.gps.style = style
        G.Follow()


def _world_centers(G, quads, cx, cy, rot, s):
    out = {}
    for i in range(1, len(quads) + 1):
        q = quads[i]
        x, y = G.ScreenToWorld(cx, cy, q[2], q[3], rot, s)
        out.setdefault(q[1], []).append((x, y, q[6], q[7], q[8], q[9], q[10]))
    return out


def test_the_layers_stay_aligned_through_pan_zoom_turn_and_resize(game):
    # the world map's tiles land where its bounds put their pixels, and the cave's art where its models are, from any
    # view; and its rooms lie inside the map's bounds where the inventory found them
    lua, ns = game
    G = ns.GPS
    art = G.CaveArt(0, _cave(ns, 0, "Jasperlode Mine"))
    f = G.InteriorMapFor(0, art.list, None, (art.x0 + art.x1) / 2, (art.y0 + art.y1) / 2)
    assert f is not None
    b = f.bounds
    assert b[1] <= f.rooms[1] < f.rooms[3] <= b[3] and b[2] <= f.rooms[2] < f.rooms[4] <= b[4]
    tiles = {t[1]: t for t in f.tiles.values()}
    ydx, ydy = (b[3] - b[1]) / f.artH, (b[4] - b[2]) / f.artW
    cx0, cy0 = (f.rooms[1] + f.rooms[3]) / 2, (f.rooms[2] + f.rooms[4]) / 2
    art_at = None
    for rot, zoom, half, pan in ((0.0, 150.0, 300.0, (0, 0)), (1.1, 150.0, 300.0, (0, 0)), (1.1, 80.0, 300.0, (20, -15)),
                                 (-2.5, 220.0, 520.0, (-30, 40)), (0.4, 400.0, 260.0, (5, 5))):
        cx, cy = cx0 + pan[0], cy0 + pan[1]
        s = half / zoom
        base = G.LayoutDungeonMap(cx, cy, f, rot, zoom, half)
        assert len(base) > 0
        for fid, pts in _world_centers(G, base, cx, cy, rot, s).items():
            t = tiles[fid]
            for x, y, qrot, l, r, top, bot in pts:
                assert qrot == pytest.approx(rot)
                u, v = t[2] + (l + r) / 2 * t[6], t[3] + (top + bot) / 2 * t[7]
                assert (x, y) == pytest.approx((b[3] - v * ydx, b[4] - u * ydy), abs=0.05)
        own = G.LayoutInstanceArt(cx, cy, art, rot, zoom, half, None)
        here = {fid: sorted((round(p[0], 1), round(p[1], 1)) for p in pts)
                for fid, pts in _world_centers(G, own, cx, cy, rot, s).items()}
        if art_at is None:
            art_at = here
        for fid in set(here) & set(art_at):
            assert [c for p in here[fid] for c in p] == pytest.approx([c for p in art_at[fid] for c in p], abs=0.2)


def test_the_inside_map_in_a_mine_has_its_world_map_under_it(game):
    # (the player down in Jasperlode Mine: the game's indoors, the inside map, and its world map under it; out again,
    # neither)
    lua, ns = game
    G = ns.GPS
    art = G.CaveArt(0, _cave(ns, 0, "Jasperlode Mine"))
    p = art.list[1]
    w = ns.WMOs[p[1]]
    g = next(g for g in w.groups.values() if g["in"])
    lx, ly = (g[1] + g[4]) / 2, (g[2] + g[5]) / 2
    c, sn = math.cos(p[5]), math.sin(p[5])
    x, y = p[2] + lx * c - ly * sn, p[3] + lx * sn + ly * c
    style = ns.settings.gps.style
    lua.execute("AGPS_OLD_INDOORS = IsIndoors IsIndoors = function() return true end")
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0 AGPS_T = AGPS_T + 1")
    try:
        ns.settings.gps.style = "minimap"
        G.Follow()
        G.Update()
        f = G.InteriorMapShown()[0]
        assert f is not None and str(f.map) == "Jasperlode Mine"
        laid = _laid(ns)
        fids = _map_fids(ns)[f.ui]
        base = [q for q in laid if q[0] in fids]
        inside = [q for q in laid if q[0] not in fids]
        assert base and inside and min(q[6] for q in inside) > G.DUNGEON_MAP_SUBLAYER
    finally:
        lua.execute("IsIndoors = AGPS_OLD_INDOORS")
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        ns.settings.gps.style = style
        G.Follow()
        G.Update()
    assert G.InteriorMapShown()[0] is None and not {q[0] for q in _laid(ns)} & _all_fids(ns)
