"""Auto maps where the game has none (item 115, Kooki3z 2026-11-26): the caves and buildings whose models have no
minimap art drawn from their walkable cells, floor by floor (Data/AutoMaps.lua, automaps.py; G.AutoArt,
G.LayoutAutoMap). The floor shown full, the others faint; the floor a parameter (item 114's floor picker drives it).
The GPS map and world-map mode are one redraw: the same view.cave."""

import time

import pytest

from azerothgps import automaps as A
from azerothgps.paths import ADDON_DIR
from test_map_redraw import game  # noqa: F401

TERRORWEB = "cave392956"  # (the Terrorweb Tunnel, Eastern Plaguelands: no art, two floors)
TALONDEEP = "cave300408"  # (the Talondeep Path, Ashenvale to Stonetalon)
ASTRANAAR_INN = "in239623"  # (Astranaar's inn: a night elf building, no art, two floors)
FRAME_MS = 40  # (test_frame_budget.py's)
LOADED_KB = 200  # the data loaded (at login): at most this much more of the heap
MEMORY_KB = 1024  # and every map decoded (each map is decoded only once shown or hovered)


def _maps():
    text = (ADDON_DIR / "Data" / "AutoMaps.lua").read_text(encoding="utf-8")
    import re
    return re.findall(r'^  \{ "([^"]+)", "([^"]*)", "(cave|inside)", ([-\d.]+), ([-\d.]+), (\d+), (\d+), \{ (.*) \} \},$',
                      text, re.M)


def test_the_data_covers_the_caves_and_buildings_with_no_art():
    maps = _maps()
    caves = [m for m in maps if m[2] == "cave"]
    insides = [m for m in maps if m[2] == "inside"]
    assert len(caves) >= 45 and len(insides) >= 20, (len(caves), len(insides))
    keys = [m[0] for m in maps]
    assert len(keys) == len(set(keys))
    no_art = {k for _c, k, _n, _x, _y in A.caves_without_art()}
    assert {m[0] for m in caves} <= no_art  # (never over a cave with its own art)
    for key in (TERRORWEB, TALONDEEP):
        assert key in keys


def test_rectangles_pack_and_unpack():
    import numpy as np
    m = np.zeros((7, 9), bool)
    m[1:4, 2:6] = True
    m[4, 2:6] = True
    m[5, 0:2] = True
    rs = A.rects(m)
    back = np.zeros_like(m)
    for r, c, h, w in rs:
        assert not back[r:r + h, c:c + w].any()  # (no overlaps)
        back[r:r + h, c:c + w] = True
    assert (back == m).all() and len(rs) == 2
    assert A.unpack(A.pack([0, 63, 64, 4095])) == [0, 63, 64, 4095]


def test_grouping_puts_a_floor_over_another_on_a_floor_of_its_own():
    import numpy as np
    low = (np.repeat(np.arange(10), 10), np.tile(np.arange(10), 10), np.full(100, 50.0))
    high = (np.repeat(np.arange(3, 7), 4), np.tile(np.arange(3, 7), 4), np.full(16, 60.0))
    beside = (np.repeat(np.arange(12, 16), 4), np.tile(np.arange(3, 7), 4), np.full(16, 61.0))
    fl = A.group_floors([low, high, beside], 20, 20)
    assert len(fl) == 2  # (the bit beside the lower floor at the upper one's height: on the upper)
    assert fl[0][0].sum() == 100 and fl[1][0].sum() == 32 and fl[0][1].max() < fl[1][1].min()


def test_a_cave_with_no_art_gets_its_map_from_its_cells(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    art = G.CaveArt(0, TERRORWEB)
    assert art and art.auto and str(art.name) == "Terrorweb Tunnel" and len(art.list) == 0
    floors = G.InstanceFloors(art)
    assert len(floors) == 2 and floors[1][1] < floors[2][1]  # (lowest first: the floor bar's order)
    assert len(G.AutoMapFloors(art)) == 2 and G.AutoMapFloors(art)[1][1] == floors[1][1]
    # (the spot a cave grid's cell has: its map, as a cave with art)
    assert art.x0 < art.x1 and art.y0 < art.y1
    assert G.ShowCave(0, TERRORWEB)
    try:
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.shownView.cave is not None and str(G.shownView.cave.key) == TERRORWEB
        G.UpdateInfo()
        assert str(G.infoName) == "Terrorweb Tunnel"
        assert G.FloorStep(False)  # (its floors stepped as a dungeon's)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.shownView.floor == 1
    finally:
        G.Follow()


def test_the_floor_shown_is_full_and_the_others_faint(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    art = G.CaveArt(0, TERRORWEB)
    cx, cy = (art.x0 + art.x1) / 2, (art.y0 + art.y1) / 2
    zoom = max(art.x1 - art.x0, art.y1 - art.y0)

    def alphas(floor):
        q = G.LayoutAutoMap(lua.eval("{}"), cx, cy, art, floor, 0, zoom, 200, False)
        out = [q[i].tint[4] for i in range(1, len(q) + 1)]
        assert all(q[i][1] == G.AUTO_TEX for i in range(1, len(q) + 1))  # (plain color: no art, no filter)
        return out

    every = alphas(None)
    assert every and set(every) == {1}
    for k in (1, 2):
        a = alphas(k)
        assert len(a) == len(every)
        full = sum(1 for v in a if v == 1)
        assert 0 < full < len(a) and set(a) == {1, G.AUTO_FAINT_ALPHA}
        assert full == len(art.auto[k]) // 4  # (that floor's rectangles, all in view)
    # (the floor shown drawn last, over the faint ones)
    q = G.LayoutAutoMap(lua.eval("{}"), cx, cy, art, 1, 0, zoom, 200, False)
    assert q[len(q)].tint[4] == 1 and q[1].tint[4] == G.AUTO_FAINT_ALPHA
    # (the outline over the terrain: only round the floor shown)
    o = G.LayoutAutoMap(lua.eval("{}"), cx, cy, art, 1, 0, zoom, 200, True)
    assert len(o) > len(q)


def test_standing_in_a_building_with_no_art_shows_its_map(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    art = G.AutoArt(1, ASTRANAAR_INN)
    assert art and str(art.name) == "Astranaar" and len(art.floors) == 2
    q = [art.auto[1][1], art.auto[1][2]]  # (a spot on its ground floor)
    st = ns.settings.gps
    zoom = st.zoom
    lua.execute(f"AGPS_OLD_POS = {{ AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] }} "
                f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = {q[0]}, {q[1]}, 1, 0 "
                "AGPS_OLD_IN = IsIndoors IsIndoors = function() return false end AGPS_T = AGPS_T + 1")
    try:
        st.zoom = 80.0
        G.Follow()
        assert G.PlayerAutoMap(1, q[0], q[1]) == ASTRANAAR_INN
        G.Update()
        assert G.shownView.cave is not None and str(G.shownView.cave.key) == ASTRANAAR_INN
        # (zoomed out past the inside maps: the land)
        st.zoom = G.INTERIOR_MAX_ZOOM * 4
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.shownView.cave is None
        # (and hovered: G.BuildingHover finds the building by its cells)
        assert G.AutoMapAt(1, q[0], q[1]) == ASTRANAAR_INN
        assert G.AutoMapAt(1, q[0] + 500, q[1]) is None
    finally:
        st.zoom = zoom
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = AGPS_OLD_POS[1], AGPS_OLD_POS[2], "
                    "AGPS_OLD_POS[3], AGPS_OLD_POS[4] IsIndoors = AGPS_OLD_IN AGPS_T = AGPS_T + 1")
        G.Follow()
        G.Update()


def test_a_cave_s_map_needs_the_player_down_in_it(game):  # noqa: F811
    # (a cave by its cells: up on the hill over it, the game says outdoors: not the cave's map)
    lua, ns = game
    G = ns.GPS
    art = G.AutoArt(0, TERRORWEB)
    q = [art.auto[1][1], art.auto[1][2]]
    lua.execute("AGPS_OLD_IN = IsIndoors IsIndoors = function() return false end")
    try:
        assert G.PlayerAutoMap(0, q[0], q[1]) is None
        lua.execute("IsIndoors = function() return true end")
        assert G.PlayerAutoMap(0, q[0], q[1]) == TERRORWEB
    finally:
        lua.execute("IsIndoors = AGPS_OLD_IN")


@pytest.mark.timing
def test_decoding_and_laying_out_the_biggest_map_fits_in_a_frame(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    biggest = max(_maps(), key=lambda m: int(m[5]) * int(m[6]))
    clock = lua.eval("function() return os.clock() * 1000 end")
    cont = next(c for c in (0, 1) if G.AutoArt(c, biggest[0]) is not None)
    lua.execute(f"AGPS_NS.GPS.autoRows[{cont}] = nil")  # (decoded again from scratch)
    a = clock()
    art = G.AutoArt(cont, biggest[0])
    cx, cy = (art.x0 + art.x1) / 2, (art.y0 + art.y1) / 2
    for floor in (None, 1):
        G.LayoutAutoMap(lua.eval("{}"), cx, cy, art, floor, 0.3, 400, 300, True)
    took = clock() - a
    assert took < FRAME_MS, f"{took:.1f} ms"


def test_the_maps_memory_is_small(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    mem = lua.eval("function() collectgarbage('collect'); collectgarbage('collect'); return collectgarbage('count') end")
    # (none kept meanwhile: the data's strings, interned, would be counted as there already)
    lua.execute("AGPS_NS.AutoMaps = nil AGPS_NS.GPS.autoRows = {} AGPS_NS.GPS.caveArt = {}")
    try:
        before = mem()
        src = (ADDON_DIR / "Data" / "AutoMaps.lua").read_text(encoding="utf-8")
        lua.eval("function(src, ns) return assert((loadstring or load)(src, '@AutoMaps.lua'))('AzerothGPS', ns) end")(src, ns)
        loaded = mem() - before
        for m in _maps():
            assert G.AutoArt(0, m[0]) is not None or G.AutoArt(1, m[0]) is not None
        grown = mem() - before
        print(f"auto maps: {loaded:.0f} KB loaded, {grown:.0f} KB with every map decoded")
        assert loaded < LOADED_KB, f"{loaded:.0f} KB"
        assert grown < MEMORY_KB, f"{grown:.0f} KB"
    finally:
        lua.execute("AGPS_NS.GPS.autoRows = {} AGPS_NS.GPS.caveArt = {}")  # (the data loaded again here stays)


def test_auto_maps_set_no_texture_filter():
    src = (ADDON_DIR / "GPSFrame.lua").read_text(encoding="utf-8")
    block = src[src.index("-- Auto maps where the game has none"):src.index("-- Dungeons and raids (Data/Instances.lua)")]
    assert "TRILINEAR" not in block and "ANISOTROPIC" not in block and "SetTexture" not in block
