"""The player's arrow while zooming in and out (Kooki3z 2026-11-27, the 1.4.2 test build: "The player arrow on world map
sometimes flashes larger when zooming in and out").

Our arrow keeps its size on the screen every frame, in the GPS window and in the world map (where our frame is scaled
against the game's canvas, G.WorldMapKeepScale). In the world map the game's own arrow (its group members' pin) is
over ours, and the game pings it each time its map changes (GroupMembersPinMixin:OnMapChanged, StartPlayerPing(2,
.25): rings growing out round it for two seconds). Zooming past a stage changes the game's map (a zone's, the
continent's): the ping is stopped at once (G.WorldMapQuietPing). The ping as the world map opens is the game's own,
kept."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

# The game's scroll frame as Blizzard_MapCanvas's MapCanvasScrollControllerMixin runs it: InstantPanAndZoom sets the
# canvas's scale at once; SetMapID resets its zoom (ResetZoom) and its group members' pin (the game's player arrow)
# OnMapChanged starts a ping (StartPlayerPing(2, .25)); the pin is sized 27 / scale.
CANVAS = """
  local box = WorldMapFrame.ScrollContainer
  box.Child = NewWidget("Frame", "AGPSTestWorldMapChild")
  box.Child.GetWidth = function() return 1002 end
  box.Child.GetHeight = function() return 668 end
  AGPS_WMS = { maps = {}, zooms = {}, sc = 0.5 }
  AGPS_PIN = { pings = 0, size = 27 / 0.5, frames = {} }
  function AGPS_PIN:StartPlayerPing() self.pings = self.pings + 1 self.pinging = true end
  function AGPS_PIN:StopPlayerPing() self.pinging = false end
  function AGPS_PIN:Sync() self.size = 27 / AGPS_WMS.sc end
  box.InstantPanAndZoom = function(_, sc, u, v, raw)
    table.insert(AGPS_WMS.zooms, { sc, u, v, raw }) AGPS_WMS.sc = sc AGPS_PIN:Sync()
  end
  box.GetCanvasScale = function() return AGPS_WMS.sc end
  box.Child.GetEffectiveScale = function() return AGPS_WMS.sc end
  box.GetEffectiveScale = function() return 1 end
  box.SetHorizontalScroll = function(_, h) AGPS_WMS.h = h end
  box.SetVerticalScroll = function(_, v) AGPS_WMS.v = v end
  box.GetHorizontalScroll = function() return AGPS_WMS.h end box.GetVerticalScroll = function() return AGPS_WMS.v end
  WorldMapFrame.GetMapID = function() return AGPS_WMS.map end
  WorldMapFrame.SetMapID = function(_, id)
    AGPS_WMS.map = id table.insert(AGPS_WMS.maps, id)
    AGPS_WMS.sc = 0.4 AGPS_PIN:Sync() -- (ResetZoom)
    AGPS_PIN:StartPlayerPing(2, 0.25) -- (GroupMembersPinMixin:OnMapChanged)
    if AGPS_NS.GPS.WorldMapGameMoved then AGPS_NS.GPS.WorldMapGameMoved(true) end -- (our hook on OnMapChanged)
  end
  WorldMapFrame.EnumeratePinsByTemplate = function(_, tmpl)
    local done = tmpl ~= "GroupMembersPinTemplate"
    return function() if done then return nil end done = true return AGPS_PIN end
  end
"""
UNCANVAS = """
  local box = WorldMapFrame.ScrollContainer
  box.Child, box.InstantPanAndZoom, box.SetHorizontalScroll, box.SetVerticalScroll = nil
  box.GetHorizontalScroll, box.GetVerticalScroll, box.GetCanvasScale, box.GetEffectiveScale = nil
  WorldMapFrame.GetMapID, WorldMapFrame.SetMapID, WorldMapFrame.EnumeratePinsByTemplate = nil
  WorldMapFrame:Hide()
"""


@pytest.fixture(params=["window", "worldmap"])
def where(request, game):  # noqa: F811
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    lua.execute(CANVAS)
    keys = ("useWorldMap", "replaceMinimap", "shown", "minimized", "zoom", "rotate")
    was = {k: st[k] for k in keys}
    st.shown, st.minimized, st.rotate, st.replaceMinimap = True, None, False, False
    st.useWorldMap = request.param == "worldmap"
    G.ApplySettings()
    if st.useWorldMap:
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
    else:
        assert not G.WorldMapHosted()
    # (the seamless map, the default style; its art isn't built offline)
    lua.execute("AGPS_REAL_SEAMLESS = AGPS_NS.GPS.Seamless AGPS_NS.GPS.Seamless = function() return true end")
    ns.Nav.Clear()
    try:
        yield lua, ns, request.param
    finally:
        lua.execute(UNCANVAS)
        lua.execute("AGPS_NS.GPS.Seamless = AGPS_REAL_SEAMLESS AzerothGPSFrame._scale = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
        G.Follow()
        G.Update()


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


def test_the_arrow_keeps_its_size_and_never_pings_as_the_zoom_goes_past_a_stage(where):
    lua, ns, mode = where
    G, st = ns.GPS, ns.settings.gps
    tick = _tick_all(lua)
    hosted = mode == "worldmap"

    def frame():
        lua.execute("AGPS_T = AGPS_T + 0.0166")
        tick(1 / 60)

    G.Follow()
    st.zoom = 200 * G.ZoomScale()
    for _ in range(5):
        frame()
    f = lua.eval("AzerothGPSFrame")
    if hosted:
        # (the game's own ping as the world map opens: left as it is)
        assert lua.eval("AGPS_PIN.pings") >= 1 and lua.eval("AGPS_PIN.pinging")
        lua.execute("AGPS_PIN:StopPlayerPing()")
    sizes, game_sizes, maps, pinged = set(), set(), set(), []
    # out a notch a frame, from close in to the continent, and back in: past the zone's and the continent's stages
    for k in range(64):
        G.WheelZoom(1.16 if k < 32 else 1 / 1.16)
        frame()
        arrow = G.MapArrow()
        assert arrow._shown, (mode, k)
        sc = float(lua.eval("AGPS_WMS.sc")) if hosted else 1.0
        own = float(f._scale or 1) if hosted else 1.0
        sizes.add(round(float(arrow._w) * own * sc, 3))  # (on the screen: its size, our frame's scale, the canvas's)
        if hosted:
            maps.add(int(lua.eval("AGPS_WMS.map")))
            game_sizes.add(round(float(lua.eval("AGPS_PIN.size")) * sc, 3))
            if lua.eval("AGPS_PIN.pinging"):
                pinged.append((k, round(st.zoom), int(lua.eval("AGPS_WMS.map"))))
    assert len(sizes) == 1, (mode, sorted(sizes))
    if hosted:
        assert len(maps) >= 2, maps  # (the zoom went past a stage: the game's map changed)
        assert game_sizes == {27.0}, game_sizes
        assert not pinged, pinged  # (base: a ping at each change of the game's map)
