"""Item 143 (Kooki3z 2026-11-27, a video of a flight over the Ruins of Lordaeron with the GPS map in the game's world map:
"there are some areas still showing transitioned maps when zoomed in at a point it should only show the terrain map.
Also icons are jumping still, more so on this flight path").

- Zoomed in to the terrain's own stage of the seamless map (G.TerrainAlone: its tiles whole, before they fade out over
  the art) no whole city's map is drawn over the land for a city the player isn't down in (G.CityUnderView): Undercity's
  rings and Sewers stayed over the Ruins. Past it, in the transition, the city's map as before.
- On a flight the player is never down in an underground city (Nav.CityHere): flying in and out of the Ruins' subzone
  flipped the map between Undercity's whole map and one floor of it with that floor's icons.
- Icons stay on their world spot every frame of a flight, at redraws and between them (G.GlidePan); in the world map the
  game's own canvas (its icons and other addons') glides along every frame too, and is set on our view again at once
  when the game changes its map or resets its zoom by itself (G.WorldMapGameMoved).
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

SYNC = """
  local box = WorldMapFrame.ScrollContainer
  box.Child = NewWidget("Frame", "AGPSTestWorldMapChild")
  box.Child.GetWidth = function() return 1002 end
  box.Child.GetHeight = function() return 668 end
  AGPS_WMS = { maps = {}, zooms = {} }
  box.InstantPanAndZoom = function(_, sc, u, v, raw) table.insert(AGPS_WMS.zooms, { sc, u, v, raw }) AGPS_WMS.sc = sc end
  box.SetHorizontalScroll = function(_, h) AGPS_WMS.h = h end
  box.SetVerticalScroll = function(_, v) AGPS_WMS.v = v end
  box.GetHorizontalScroll = function() return AGPS_WMS.h end box.GetVerticalScroll = function() return AGPS_WMS.v end
  WorldMapFrame.GetMapID = function() return AGPS_WMS.map end
  WorldMapFrame.SetMapID = function(_, id) AGPS_WMS.map = id table.insert(AGPS_WMS.maps, id) end
"""
UNSYNC = """
  local box = WorldMapFrame.ScrollContainer
  box.Child, box.InstantPanAndZoom, box.SetHorizontalScroll, box.SetVerticalScroll, box.GetHorizontalScroll, box.GetVerticalScroll = nil
  WorldMapFrame.GetMapID, WorldMapFrame.SetMapID = nil
  WorldMapFrame:Hide()
"""
# (up top at the Ruins of Lordaeron, over Undercity's rooms: the game's map for the player is Undercity's, 1458)
RUINS = (1751.0, 266.0)
UNDERCITY = 1458


@pytest.fixture(params=["window", "worldmap"])
def where(request, game):  # noqa: F811
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    lua.execute(SYNC)
    keys = ("useWorldMap", "replaceMinimap", "shown", "minimized", "zoom", "rotate", "hz")
    was = {k: st[k] for k in keys}
    x0, y0 = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    lua.execute("""
      AGPS_REAL_SUB, AGPS_REAL_MINI, AGPS_REAL_TAXI = GetSubZoneText, GetMinimapZoneText, UnitOnTaxi
      AGPS_SZ, AGPS_TAXI = 'Ruins of Lordaeron', false
      GetSubZoneText = function() return AGPS_SZ end
      GetMinimapZoneText = function() return AGPS_SZ end
      UnitOnTaxi = function() return AGPS_TAXI end
    """)
    st.shown, st.minimized, st.rotate, st.replaceMinimap = True, None, False, False
    st.useWorldMap = request.param == "worldmap"
    G.ApplySettings()
    if st.useWorldMap:
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
    else:
        assert not G.WorldMapHosted()
    # (the seamless map, the default style: its art isn't built offline, the game gives the harness no world
    # map art; its rules are the map's own)
    lua.execute("AGPS_REAL_SEAMLESS = AGPS_NS.GPS.Seamless AGPS_NS.GPS.Seamless = function() return true end")
    ns.Nav.Clear()
    try:
        yield lua, ns, request.param
    finally:
        ns.Nav.Clear()
        lua.execute(UNSYNC)
        lua.execute("""
          GetSubZoneText, GetMinimapZoneText, UnitOnTaxi = AGPS_REAL_SUB, AGPS_REAL_MINI, AGPS_REAL_TAXI
          AGPS_NS.GPS.Seamless = AGPS_REAL_SEAMLESS
          AGPS_MAP = nil
        """)
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x0}, {y0} AGPS_T = AGPS_T + 2")
        G.Follow()
        G.Update()


def _at(lua, ns, x, y, ref, subzone, taxi=False):
    """The player at (x, y) on the Eastern Kingdoms, the map following them `ref` yards out at the reference size."""
    G, st = ns.GPS, ns.settings.gps
    lua.execute(f"""AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0 AGPS_MAP = {UNDERCITY}
      AGPS_SZ = '{subzone}' AGPS_TAXI = {'true' if taxi else 'false'} AGPS_T = AGPS_T + 1""")
    G.Follow()
    st.zoom = ref * G.ZoomScale()
    G.Update()
    G.Update()  # (Nav.PlayerLevel looked at again: its half-second cache)


def _city_art(G):
    sig = G.laidTiles and G.laidTiles.laidSig or ""
    return sig.startswith("in:") or G.inside is not None


def test_the_terrains_zoom_draws_no_city_map_over_the_land_at_undercity(where):
    lua, ns, mode = where
    G = ns.GPS
    terrain = G.SEAM_TILES_OUT[1] * 0.9  # (inside the terrain's own stage: its tiles whole)
    x, y = RUINS
    # up top at the Ruins, on foot and flying over in either subzone: the terrain alone
    for sub, taxi in (("Ruins of Lordaeron", False), ("Ruins of Lordaeron", True), ("Undercity", True)):
        _at(lua, ns, x, y, terrain, sub, taxi)
        assert G.TerrainAlone(ns.settings.gps.zoom), mode
        assert not _city_art(G), (mode, sub, taxi, G.inside, G.laidTiles.laidSig)
        assert G.laidTiles.laidSig.startswith("tiles"), (mode, sub, taxi, G.laidTiles.laidSig)
    # the view dragged over the city from the land, the same zoom: the terrain too (the rule is the zoom's, not the
    # player's)
    _at(lua, ns, x + 200, y + 150, terrain, "Tirisfal Glades")
    G.LookAt(0, x, y, ns.settings.gps.zoom)
    G.Update()
    assert not _city_art(G), (mode, G.inside)
    # zoomed out into the transition (the tiles fading over the art): the city's whole map as before (asked 2026-11-15,
    # "the whole city map should come up ... as soon as you zoom in over it"; 2026-11-16, "zoom in from the map on UC")
    between = (G.SEAM_TILES_OUT[1] + G.SEAM_TILES_OUT[2]) / 2
    _at(lua, ns, x, y, between, "Ruins of Lordaeron", True)
    assert not G.TerrainAlone(ns.settings.gps.zoom)
    assert _city_art(G) and str(G.inside).endswith("7675285"), (mode, G.inside)
    # down in the city (off the flight, the subzone the city's): its own map at the terrain's zoom too, as ever
    _at(lua, ns, 1586.0, 239.0, terrain, "Trade Quarter")
    assert ns.Nav.PlayerLevel(0) == 10001
    assert _city_art(G), (mode, G.inside, G.laidTiles.laidSig)


def test_a_flight_over_the_ruins_never_counts_as_down_in_undercity(where):
    lua, ns, mode = where
    G, N = ns.GPS, ns.Nav
    x, y = RUINS
    between = (G.SEAM_TILES_OUT[1] + G.SEAM_TILES_OUT[2]) / 2
    _at(lua, ns, x, y, between, "Undercity", True)
    shown = set()
    for k in range(40):  # (the subzone going from the Ruins to the city's name and back, as the flight crosses them)
        sub = "Ruins of Lordaeron" if (k // 5) % 2 == 0 else "Undercity"
        lua.execute(f"AGPS_SZ = '{sub}' AGPS_POS[1] = AGPS_POS[1] - 2 AGPS_T = AGPS_T + 0.6")
        G.Update()
        assert N.PlayerLevel(0) == 0, (mode, k, sub)
        shown.add(str(G.inside))
    # (the city's whole map while over its rooms, the land past them: never one floor of it with its icons, flipping in
    # and out with the subzone)
    assert shown <= {"None", "? / 7675285"}, (mode, shown)
    # on foot again, the subzone the city's: down in it, as before
    lua.execute("AGPS_TAXI = false AGPS_T = AGPS_T + 1")
    assert N.PlayerLevel(0) == 10001


def _tick_all(lua):
    lua.execute("""
      AGPS_TICK = AGPS_TICK or function(dt)
        for _, w in pairs(AGPS_WIDGETS) do
          local f = w._scripts and w._scripts.OnUpdate
          if f then f(w, dt) end
        end
      end
    """)
    return lua.eval("AGPS_TICK")


def _expected_scroll(lua, ns, x, y, s, mapid):
    """The game's canvas scroll that puts (x, y) in the middle of its box at our scale (G.WorldMapSync's sums)."""
    b = list(ns.Maps[mapid].bounds.values())
    mapW, mapH = b[3] - b[1], b[2] - b[0]
    sc = s * mapW / 1002
    u, v = (b[3] - y) / mapW, (b[2] - x) / mapH
    box = lua.eval("WorldMapFrame.ScrollContainer")
    return u * 1002 - box.GetWidth(box) / 2 / sc, v * 668 - box.GetHeight(box) / 2 / sc, sc


def test_icons_keep_to_their_world_spot_every_frame_of_a_flight(where):
    lua, ns, mode = where
    G, Geo, st = ns.GPS, ns.Geo, ns.settings.gps
    tick = _tick_all(lua)
    same = lua.eval("rawequal")
    fps = 60
    # a flight from Tirisfal's fields down over the Ruins (about 30 yd a second), north up, 400 yd out
    x, y = 1960.0, 420.0
    _at(lua, ns, x, y, 400, "Tirisfal Glades", True)
    hx, hy = (RUINS[0] - x), (RUINS[1] - y)
    d = math.hypot(hx, hy)
    ux, uy = hx / d * 30 / fps, hy / d * 30 / fps
    for _ in range(10):  # (settled: the first redraws and the icons gathered)
        lua.execute(f"AGPS_T = AGPS_T + {1 / fps}")
        tick(1 / fps)

    def absolute(b):  # (its middle from the canvas's middle: its layer's offset + its own)
        pt = b._pt
        a = pt[2]._pt
        ax, ay = (a[4] or 0, a[5] or 0) if a and a[1] == "CENTER" else (0, 0)
        return ax + pt[4], ay + pt[5]

    last, worst, steps, seen = {}, 0.0, 0.0, set()
    scroll_last, scroll_jump, map_last = None, 0.0, None
    for k in range(fps * 4):
        x, y = x + ux, y + uy
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x}, {y} AGPS_T = AGPS_T + {1 / fps}")
        tick(1 / fps)
        s = G.ViewState()[4]
        for b in lua.eval("AGPS_WIDGETS").values():
            if not (b._shown and b.wx and b.wy and b._pt and same(b._pt[2], G.poiLayer)):
                continue
            dx, dy = Geo.ScreenOffset(x, y, b.wx, b.wy)
            ex, ey = Geo.Rotate(dx * s, dy * s, 0)
            if max(abs(ex), abs(ey)) > G.MapSize()[1] / 2 - 30:
                continue  # (at the edge: culled and gathered again as it comes in)
            ax, ay = absolute(b)
            off = (ax - ex, ay - ey)
            key = (round(float(b.wx), 1), round(float(b.wy), 1))
            seen.add(key)
            worst = max(worst, abs(off[0]), abs(off[1]))
            if key in last:
                steps = max(steps, abs(off[0] - last[key][0]), abs(off[1] - last[key][1]))
            last[key] = off
        if mode == "worldmap":  # (the game's canvas: our view's middle every frame, no step bigger than the flight's)
            h, v = float(lua.eval("AGPS_WMS.h")), float(lua.eval("AGPS_WMS.v"))
            mp = int(lua.eval("AGPS_WMS.map"))
            if mp != map_last:  # (another map picked: its own canvas units)
                scroll_last, map_last = None, mp
            if scroll_last:
                scroll_jump = max(scroll_jump, abs(h - scroll_last[0]), abs(v - scroll_last[1]))
            scroll_last = (h, v)
    assert seen, "no icon on the map along the flight"
    # (on their world spot within a pixel and a half every frame, never a step of more than that between frames: a
    # game icon is drawn on whole pixels, half a pixel either way)
    assert worst <= 1.5, (mode, worst)
    assert steps <= 1.5, (mode, steps)
    if mode == "worldmap":
        # 30 yd a second at 60 frames: half a yard a frame, a few of the game's canvas units; a redraw's catch-up (5 to 10
        # a second) was 3 to 6 yd
        sc = _expected_scroll(lua, ns, x, y, G.ViewState()[4], int(lua.eval("AGPS_WMS.map")))[2]
        assert scroll_jump <= 1.0 / sc, (scroll_jump, 1.0 / sc)


# (the game's own canvas: only in the world map. Its mode alone, not a skip in the window's: CI's gate fails a run on any
# skip that isn't a missing WoW client's, .github/scripts/ci_gate.py ALLOWED_SKIPS)
@pytest.mark.parametrize("where", ["worldmap"], indirect=True)
def test_the_games_canvas_is_set_on_ours_again_as_soon_as_the_game_moves_it(where):
    lua, ns, mode = where
    assert mode == "worldmap"
    G, st = ns.GPS, ns.settings.gps
    x, y = RUINS
    _at(lua, ns, x, y, 400, "Ruins of Lordaeron", True)
    G.WorldMapSync()
    cur = int(lua.eval("AGPS_WMS.map"))
    vx, vy, _, _, s, _ = G.ViewState()
    h, v, sc = _expected_scroll(lua, ns, vx, vy, s, cur)
    assert float(lua.eval("AGPS_WMS.h")) == pytest.approx(h, abs=0.05)
    # the game going to the player's own map by itself (a subzone changed on the flight), its canvas reset to that map's
    # middle and zoomed out (MapCanvasScrollControllerMixin:ResetZoom): ours again within the same call (hooked), never
    # a frame later
    other = 1420 if cur != 1420 else UNDERCITY
    lua.execute(f"AGPS_WMS.map = {other} AGPS_WMS.h, AGPS_WMS.v, AGPS_WMS.sc = 0, 0, 0.1")
    G.WorldMapGameMoved(True)
    assert int(lua.eval("AGPS_WMS.map")) == cur  # (back on the map ours shows)
    assert float(lua.eval("AGPS_WMS.sc")) == pytest.approx(sc)  # (and at our scale again, not the game's reset one)
    assert float(lua.eval("AGPS_WMS.h")) == pytest.approx(h, abs=0.05)
    assert float(lua.eval("AGPS_WMS.v")) == pytest.approx(v, abs=0.05)
    # its zoom reset alone (its window's size), the map still ours: set again at once as well
    lua.execute("AGPS_WMS.h, AGPS_WMS.v, AGPS_WMS.sc = 0, 0, 0.1")
    G.WorldMapGameMoved(False)
    assert float(lua.eval("AGPS_WMS.sc")) == pytest.approx(sc)
    assert float(lua.eval("AGPS_WMS.h")) == pytest.approx(h, abs=0.05)
    # (the game's own call while ours runs, our SetMapID's: not the game's, nothing twice)
    n = len(lua.eval("AGPS_WMS.zooms"))
    lua.execute("AGPS_NS.GPS.wmSyncing = true")
    try:
        G.WorldMapGameMoved(True)
    finally:
        lua.execute("AGPS_NS.GPS.wmSyncing = nil")
    assert len(lua.eval("AGPS_WMS.zooms")) == n
    # the hooks on the game's own OnMapChanged and ResetZoom (hooksecurefunc: the game's code untouched)
    hooked = []
    lua.execute("""
      AGPS_REAL_HSF, AGPS_HOOKED = hooksecurefunc, {}
      hooksecurefunc = function(t, name) table.insert(AGPS_HOOKED, name) end
      WorldMapFrame.OnMapChanged = function() end
      WorldMapFrame.ScrollContainer.ResetZoom = function() end
      AGPS_WAS_HOOKED, AGPS_WAS_TICKER = AGPS_NS.GPS.wmHooked, AGPS_NS.GPS.wmTicker
      AGPS_NS.GPS.wmHooked = nil
    """)
    try:
        G.HookWorldMap()
        hooked = list(lua.eval("AGPS_HOOKED").values())
    finally:
        lua.execute("""
          AGPS_NS.GPS.wmTicker:Hide()
          AGPS_NS.GPS.wmTicker:SetScript("OnUpdate", nil)
          AGPS_NS.GPS.wmHooked, AGPS_NS.GPS.wmTicker = AGPS_WAS_HOOKED, AGPS_WAS_TICKER
          hooksecurefunc = AGPS_REAL_HSF
          WorldMapFrame.OnMapChanged, WorldMapFrame.ScrollContainer.ResetZoom = nil, nil
        """)
    assert "OnMapChanged" in hooked and "ResetZoom" in hooked, hooked
