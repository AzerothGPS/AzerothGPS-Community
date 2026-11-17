"""1.3.0's stutter (reported 2026-11-15: "extreme stuttering in undercity and on flight paths"). An inside map over the
terrain (a building's, a cave's, a whole city's: Undercity's) was laid again on every move of the view, the terrain's
tiles with it and its black outline 56 copies of every block: Undercity's 172 blocks, 9,816 textures placed every few
steps walked. On a flight with the mouse resting on the map, the map moving under it hovered building after building,
each one's map laid every redraw. Each check here failed on 1.3.0."""

import pytest


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("""
      AGPS_LAYOUTS = 0
      local G = AGPS_NS.GPS
      local f = G.LayoutUnderMap
      G.LayoutUnderMap = function(...) AGPS_LAYOUTS = AGPS_LAYOUTS + 1 return f(...) end
    """)
    return lua, ns


def test_walking_in_undercity_keeps_its_map_laid(game):
    lua, ns = game
    G = ns.GPS
    ns.Nav.Clear()
    lua.execute("AGPS_POS = { 1586.0, 239.0, 0 }; AGPS_MAP = 1458")
    for _ in range(3):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.05")
        G.Update()
    lua.execute("AGPS_LAYOUTS = 0")
    most = 0
    for _ in range(60):  # (21 yd walked, a redraw every 0.35 yd)
        lua.execute("AGPS_T = AGPS_T + 0.05; AGPS_POS[1] = AGPS_POS[1] + 0.35")
        G.Update()
        lt = G.laidTiles
        most = max(most, len(lt.quads) if lt and lt.quads else 0)
    assert G.laidTiles.laidSig.endswith(":terrain")  # (Undercity's map over the terrain, as the seamless map shows it)
    assert int(lua.eval("AGPS_LAYOUTS")) <= 3, "Undercity's map was laid again as the player walked"
    assert most <= 2500, f"{most} textures laid for Undercity's map"


def test_a_big_maps_outline_is_lighter_and_a_buildings_is_whole(game):
    lua, ns = game
    G = ns.GPS

    def copies(n):
        rings = G.OutlineRings(n)
        return sum(len(r[3] or G.OUTLINE_OFFSETS) for r in rings.values()) * n

    same = lua.eval("function(a, b) return a == b end")
    assert same(G.OutlineRings(12), G.OUTLINE_RINGS)  # (a building's few blocks: the full fade)
    for n in (40, 172, 350):
        assert copies(n) <= max(G.OUTLINE_MAX_COPIES, 4 * n)
    assert copies(172) < 172 * 56 / 4  # (Undercity's: 9,632 copies on 1.3.0)


def test_a_flight_with_the_mouse_still_hovers_no_building(game):
    lua, ns = game
    G = ns.GPS
    lua.execute("""
      AGPS_HOVER_SPOT = nil
      local G = AGPS_NS.GPS
      AGPS_REAL_CURSOR_WORLD = AGPS_REAL_CURSOR_WORLD or G.CursorWorld
      AGPS_REAL_INTERIOR_UNDER = AGPS_REAL_INTERIOR_UNDER or G.InteriorUnder
      G.CursorWorld = function() return 1586.0, 239.0, 0 end
      G.InteriorUnder = function() return { 1, 1586, 239, 0, 0 }, {}, {} end
      G.Seamless = function() return true end
      G.InteriorZoomOK = function() return true end
      G.CaveAt = function() return nil end
      GetCursorPosition = function() return 500, 400 end
      UnitOnTaxi = function() return true end
    """)
    try:
        G.hoverInsideKey, G.hoverInside = None, None
        for _ in range(4):
            lua.execute("AGPS_T = (AGPS_T or 1000) + 0.2")
            G.BuildingHover()
        assert G.hoverInside is None, "the map moving under a still mouse on a flight hovered a building"
        lua.execute("GetCursorPosition = function() return 520, 410 end; AGPS_T = AGPS_T + 0.2")
        G.BuildingHover()  # (the mouse moved: a hover again)
        assert G.hoverInside is not None
        lua.execute("UnitOnTaxi = function() return false end; AGPS_T = AGPS_T + 0.2")
        G.BuildingHover()  # (on foot, the mouse still: a hover as before)
        assert G.hoverInside is not None
    finally:
        lua.execute("""
          local G = AGPS_NS.GPS
          G.CursorWorld, G.InteriorUnder = AGPS_REAL_CURSOR_WORLD, AGPS_REAL_INTERIOR_UNDER
          GetCursorPosition = function() return 0, 0 end
          UnitOnTaxi = function() return false end
        """)
        G.hoverInsideKey, G.hoverInside = None, None
