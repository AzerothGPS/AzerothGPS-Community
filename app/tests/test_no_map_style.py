"""The No Map style (Kooki3z 2026-11-20: "how difficult would it be to add a No Map option? This would require using the
world map and we'd use whatever map others are using instead like OpenMap", then "yes start it, OpenMap is another
addon"): only with the GPS map in the game's world map; none of our own ground drawn, the route, stops and icons over
the map under it, lined up with it exactly: OpenMap's stitched map followed through its API, else the game's map kept
on its own zoom steps and scroll limits. North up; everything as before out of it."""

import math

import pytest

from test_map_redraw import game  # noqa: F401
from test_world_map_host import wm  # noqa: F401

# The game's map canvas, as G.WorldMapSync drives it (test_world_map_host's stubs), with the art layers' zoom steps.
CANVAS = """
  local box = WorldMapFrame.ScrollContainer
  box.Child = NewWidget("Frame", "AGPSNoMapChild")
  box.Child.GetWidth = function() return 1002 end
  box.Child.GetHeight = function() return 668 end
  AGPS_WMS = { maps = {}, zooms = {} }
  box.InstantPanAndZoom = function(_, sc, u, v, raw) table.insert(AGPS_WMS.zooms, { sc, u, v, raw }) end
  box.SetHorizontalScroll = function(_, h) AGPS_WMS.h = h end
  box.SetVerticalScroll = function(_, v) AGPS_WMS.v = v end
  box.GetHorizontalScroll = function() return AGPS_WMS.h end box.GetVerticalScroll = function() return AGPS_WMS.v end
  WorldMapFrame.GetMapID = function() return AGPS_WMS.map end
  WorldMapFrame.SetMapID = function(_, id) AGPS_WMS.map = id table.insert(AGPS_WMS.maps, id) end
  AGPS_LAYERS_WAS = C_Map.GetMapArtLayers
  -- (each map: three steps, 1, 2 and 3 times the scale that fits it in the box, as the game's CreateZoomLevels makes)
  C_Map.GetMapArtLayers = function()
    return { { layerWidth = 1002, layerHeight = 668, minScale = 1, maxScale = 3, additionalZoomSteps = 1 } }
  end
  AGPS_PIN = { a = 1 }
  function AGPS_PIN:SetAlpha(a) self.a = a end
  function AGPS_PIN:GetAlpha() return self.a end
  WorldMapFrame.EnumeratePinsByTemplate = function(_, tmpl)
    local done = tmpl ~= "MapExplorationPinTemplate"
    return function() if done then return nil end done = true return AGPS_PIN end
  end
"""

UNDO = """
  local box = WorldMapFrame.ScrollContainer
  box.Child, box.InstantPanAndZoom, box.SetHorizontalScroll, box.SetVerticalScroll = nil
  box.GetHorizontalScroll, box.GetVerticalScroll, box.GetCurrentScrollX, box.GetCurrentScrollY = nil
  box.GetCanvasScale, box.zoomLevels = nil
  WorldMapFrame.GetMapID, WorldMapFrame.SetMapID, WorldMapFrame.EnumeratePinsByTemplate = nil
  WorldMapFrame.GetPinFrameLevelsManager = nil
  C_Map.GetMapArtLayers = AGPS_LAYERS_WAS
  OpenMapAPI, ExecuteFrameScript = nil
"""

# OpenMap's API (its API.lua, version 4), stubbed: its stitched map shows Tirisfal's map as the canvas's, laid out as the
# game's (0-1 across its rectangle, east and south), scrolled and scaled by AGPS_OM.
OPENMAP = """
  AGPS_OM = { on = true, ux = 0.5, uy = 0.5, k = 1.4, calls = {} }
  local b = AGPS_NS.Maps[1420].bounds
  local W, H = b[4] - b[2], b[3] - b[1]
  OpenMapAPI = {
    major = 1, version = 4,
    IsStitched = function() return AGPS_OM.on end,
    CanvasFromWorldPos = function(c, x, y)
      if c ~= 0 then return nil end
      return (b[4] - y) / W, (b[3] - x) / H
    end,
    GetView = function() return 0.4, 0.3, 6 end,
    MapAt = function() return 1420 end,
    WorldFromMap = function(id, x, y) return x / 2, y / 2 end,
    ShowWorld = function(u, v, zoom) AGPS_OM.shown = { u, v, zoom } return true end,
    ArtTopLevel = function() return 2100 end,
  }
  local box = WorldMapFrame.ScrollContainer
  box.GetCurrentScrollX = function() return AGPS_OM.ux end
  box.GetCurrentScrollY = function() return AGPS_OM.uy end
  box.GetCanvasScale = function() return AGPS_OM.k end
  box.Child.GetHeight = function() return 1002 * H / W end -- (the map's art its rectangle's shape)
  AGPS_WMS.map = 1420
  ExecuteFrameScript = function(f, name, ...) table.insert(AGPS_OM.calls, { f, name, ... }) end
"""


@pytest.fixture
def nomap(wm):  # noqa: F811
    lua, ns = wm
    st = ns.settings.gps
    was = {k: st[k] for k in ("style", "styleBeforeNone", "rotate", "zoom", "showRoads")}
    lua.execute(CANVAS)
    yield lua, ns
    G = ns.GPS
    ns.Nav.Clear()
    lua.execute(UNDO)
    lua.execute("WorldMapFrame:Hide()")
    G.WorldMapChanged()
    for k, v in was.items():
        st[k] = v
    G.Follow()
    G.Update()


def _open(lua, ns):
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().ToggleWorldMap()
    assert G.WorldMapHosted()


def test_no_map_only_with_the_map_in_the_world_map(nomap):
    lua, ns = nomap
    G, st = ns.GPS, ns.settings.gps
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    G.SetStyle("zone")
    st.useWorldMap = False
    G.ApplySettings()
    assert G.SetStyle("none") is False and st.style == "zone"  # (refused, said in chat)
    slash = lua.globals().SlashCmdList.AZEROTHGPS
    slash("style none")
    assert st.style == "zone"
    st.useWorldMap = True
    G.ApplySettings()
    assert G.SetStyle("none") is True and st.style == "none" and st.styleBeforeNone == "zone"
    # (the world map closed: the style picked before it, everything as before)
    assert not G.WorldMapHosted() and not G.NoMapOn() and G.Style() == "zone"
    lua.globals().ToggleWorldMap()
    assert G.NoMapOn() and G.Style() == "none"
    lua.globals().ToggleWorldMap()
    st.useWorldMap = False  # (the option off: the style before it too, the setting kept)
    G.ApplySettings()
    assert G.Style() == "zone" and st.style == "none"
    slash("style seamless")
    st.useWorldMap = True
    slash("style nomap")
    assert st.style == "none" and st.styleBeforeNone == "seamless"


def test_no_map_draws_no_ground_but_the_route_and_icons_north_up(nomap):
    lua, ns = nomap
    G, st = ns.GPS, ns.settings.gps
    _open(lua, ns)
    G.SetStyle("minimap")
    st.rotate, st.showRoads = True, True
    G.Follow()
    G.Update()
    G.WorldMapArtPins(False)
    assert lua.eval("AGPS_PIN.a") == 0  # (under our own ground: the game's explored areas unseen, as before)
    own_level = lua.eval("AzerothGPSFrame")._level
    lua.execute("""WorldMapFrame.GetPinFrameLevelsManager = function()
      return { GetValidFrameLevel = function(_, name) return name == "PIN_FRAME_LEVEL_MAP_EXPLORATION" and 2010 or nil end }
    end""")
    assert G.SetStyle("none")
    ns.Nav.SetStops(lua.eval("{ { x = 2204, y = 303, cont = 0, name = 'The Gallows' } }"), False, "red")
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert G.NoMapOn() and G.Style() == "none"
    assert lua.eval("#AGPS_NS.GPS.laidTiles.quads") == 0  # (no terrain, no map art)
    assert lua.eval("AzerothGPSFrame._bg[4]") == 0  # (no dark backdrop of ours either)
    assert G.seamArt is None and G.InteriorMapShown()[0] is None
    _, segs = G.DrawnSegs()
    assert segs > 0  # (the roads and the route: drawn)
    assert [b for b in G.stopPins.values() if b._shown and b.title == "The Gallows"]
    assert G.ViewState()[3] == 0  # (north up, heading-up on)
    G.WorldMapArtPins(False)
    assert lua.eval("AGPS_PIN.a") == 1  # (the game's explored areas: the map's own, shown)
    # (over them, so the route isn't under them; still under the game's other icons)
    G.WorldMapTick()
    assert G.WorldMapLevel() == 2011 and lua.eval("AzerothGPSFrame")._level == 2011
    # another style again: everything as before
    assert G.SetStyle("minimap")
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    G.WorldMapTick()
    assert not G.NoMapOn() and lua.eval("AzerothGPSFrame._bg[4]") > 0
    assert lua.eval("AGPS_PIN.a") == 0 and lua.eval("AzerothGPSFrame")._level == own_level


def _scales(lua, ns, mid):
    """The game's zoom steps for map `mid` in the box (G.NoMapSteps' own sum, done here by hand)."""
    box = lua.eval("WorldMapFrame.ScrollContainer")
    base = min(box.GetWidth(box) / 1002, box.GetHeight(box) / 668)
    return [base * k for k in (1, 2, 3)]


def test_on_the_games_map_the_view_keeps_to_its_zoom_steps_and_range(nomap):
    lua, ns = nomap
    G, st = ns.GPS, ns.settings.gps
    _open(lua, ns)
    assert G.SetStyle("none")
    G.Follow()

    def drawn(zoom):
        st.zoom = zoom
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        G.WorldMapSync()
        return lua.eval("AGPS_WMS.map"), lua.eval("AGPS_WMS.zooms[#AGPS_WMS.zooms][1]")

    # (Brill: Tirisfal's map, one of its three steps; the deepest for a zoom closer than it goes)
    mid, sc = drawn(60)
    assert mid == 1420 and sc == pytest.approx(_scales(lua, ns, mid)[2])
    mid2, sc2 = drawn(900)
    assert mid2 == 1420 and min(abs(math.log(sc2 / k)) for k in _scales(lua, ns, mid2)) < 1e-9
    # (zoomed out past the zone: the continent's map, at its own steps; no further out than it fits)
    mid3, sc3 = drawn(200000)
    assert ns.Maps[mid3].type == 2 and sc3 == pytest.approx(_scales(lua, ns, mid3)[0])
    # the view's middle within the game's own scroll limits: never pulled off ours
    x, y, cont, rot, s, _ = G.ViewState()
    b = list(ns.Maps[mid3].bounds.values())
    c = G.Canvas()
    w, h = c.GetWidth(c), c.GetHeight(c)
    assert b[1] + w / 2 / s - 1e-6 <= y <= b[3] - w / 2 / s + 1e-6 or y == pytest.approx((b[1] + b[3]) / 2)
    assert b[0] + h / 2 / s - 1e-6 <= x <= b[2] - h / 2 / s + 1e-6 or x == pytest.approx((b[0] + b[2]) / 2)
    # the wheel: one step at a time, in and out, and no further than the map goes
    drawn(60)
    zooms = []
    for _ in range(3):
        assert G.NoMapWheel(-1) is True
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        zooms.append(G.ViewState()[4])
    assert zooms[0] > zooms[1] > zooms[2]  # (each notch out: a smaller scale)
    G.NoMapWheel(1)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert G.ViewState()[4] == pytest.approx(zooms[1])
    drawn(60)
    s0 = G.ViewState()[4]
    assert G.NoMapWheel(1) is True  # (the closest step: taken, nothing changes)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert G.ViewState()[4] == pytest.approx(s0)
    # (another style: the wheel is the map's own again)
    G.SetStyle("minimap")
    assert G.NoMapWheel(1) is False


def test_over_openmap_its_view_is_followed_exactly(nomap):
    lua, ns = nomap
    G, st = ns.GPS, ns.settings.gps
    _open(lua, ns)
    lua.execute(OPENMAP)
    assert G.SetStyle("none")
    st.rotate = True
    om = lua.eval("AGPS_OM")
    b = list(ns.Maps[1420].bounds.values())
    W, H = b[3] - b[1], b[2] - b[0]
    child = lua.eval("WorldMapFrame.ScrollContainer.Child")
    cw, ch = child.GetWidth(child), child.GetHeight(child)

    def check():
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        x, y, cont, rot, s, _ = G.ViewState()
        assert cont == 0 and rot == 0
        for px, py in ((2254.0, 293.0), (1500.0, -900.0), (3600.0, 2800.0)):
            hx, hy = (b[3] - py) / W, (b[2] - px) / H
            want = ((hx - om.ux) * cw * om.k, (om.uy - hy) * ch * om.k)  # (where OpenMap's canvas puts it)
            east, north = (y - py) * s, (px - x) * s  # (where ours draws it: Geo.ScreenOffset times the scale)
            assert east == pytest.approx(want[0], abs=1e-6) and north == pytest.approx(want[1], abs=1e-6)
        return x, y, s

    x1, y1, s1 = check()
    # OpenMap zoomed and panned (the player's wheel or drag on it): followed at the next frame
    lua.execute("AGPS_OM.k = 3.1 AGPS_OM.ux = 0.62 AGPS_OM.uy = 0.41")
    lua.execute("AGPS_T = AGPS_T + 1")
    G.WorldMapTick()
    x2, y2, s2 = check()
    assert s2 == pytest.approx(s1 * 3.1 / 1.4) and (x2, y2) != (x1, y1)
    # never driven: its map, zoom and scroll are its own
    maps = lua.eval("#AGPS_WMS.maps")
    assert G.WorldMapSync() is False and lua.eval("#AGPS_WMS.maps") == maps
    # over its art (OpenMapAPI.ArtTopLevel), under the map's icons
    G.WorldMapTick()
    assert G.WorldMapLevel() == 2101
    # the wheel, a right-click and a drag go to its canvas, as on its own map
    G.NoMapWheel(1, 10, 10)
    calls = om.calls
    assert calls[len(calls)][2] == "OnMouseWheel" and calls[len(calls)][3] == 1
    assert G.NoMapPress() is True and calls[len(calls)][2] == "OnMouseDown"
    G.NoMapRelease(True)
    assert calls[len(calls)][2] == "OnMouseUp"
    lua.execute("""WorldMapFrame.ScrollContainer.mouseButtonInfo = { LeftButton = { down = true } }""")
    G.NoMapPress()
    n = len(calls)
    G.NoMapRelease(False)  # (a click, not a drag: ours; its pan only stopped)
    assert len(calls) == n and lua.eval("WorldMapFrame.ScrollContainer.mouseButtonInfo.LeftButton.down") is False
    # back to the player: its view glides there (OpenMapAPI.ShowWorld), ours following it
    G.Follow()
    shown = lua.eval("AGPS_OM.shown")
    assert shown is not None
    assert shown[1] == pytest.approx((b[3] - 293.0) / W / 2) and shown[2] == pytest.approx((b[2] - 2254.0) / H / 2)
    # OpenMap's stitched map off (Blizzard's again): the game's map, driven on its steps as without it
    lua.execute("AGPS_OM.on = false AGPS_T = AGPS_T + 1")
    G.Update()
    assert G.WorldMapSync() is True


# hooksecurefunc as the game has it (the stand-in's does nothing): after the method, with its arguments
HOOKS = """
  AGPS_HOOKS_WAS = hooksecurefunc
  hooksecurefunc = function(t, name, f)
    local o = t[name]
    t[name] = function(...) local r = { o(...) } f(...) return unpack(r) end
  end
"""


def test_over_openmap_the_map_stays_on_its_points_every_frame_and_keeps_its_size(nomap):
    # (Kooki3z's test 2026-11-20, a video: "icons are hidden and icons jump around badly" as OpenMap zoomed and glided:
    # its canvas moves in its own updates, every frame; ours followed only at our redraws, our frame carrying the
    # canvas's new scale meanwhile, and a redraw then laid its icons out at that scale: too small)
    lua, ns = nomap
    G, st = ns.GPS, ns.settings.gps
    lua.execute(HOOKS)
    try:
        _open(lua, ns)
        lua.execute(OPENMAP)
        lua.execute("""
          local box = WorldMapFrame.ScrollContainer
          box.GetEffectiveScale = function() return 1 end
          box.Child.GetEffectiveScale = function() return AGPS_OM.k end
          AzerothGPSFrame.GetEffectiveScale = function(f) return AGPS_OM.k * (f._scale or 1) end
        """)
        assert G.SetStyle("none")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        f = lua.eval("AzerothGPSFrame")
        assert f._scale == pytest.approx(1 / 1.4)  # (as big as ever: the box's scale, whatever the canvas's)
        x0, y0, _, _, s0, _ = G.ViewState()
        b = list(ns.Maps[1420].bounds.values())
        W, H = b[3] - b[1], b[2] - b[0]
        child = lua.eval("WorldMapFrame.ScrollContainer.Child")
        cw, ch = child.GetWidth(child), child.GetHeight(child)
        c = G.Canvas()
        # OpenMap's glide and zoom, frame by frame, its setters called as its own SetView does; no redraw of ours
        for k, ux, uy in ((1.6, 0.52, 0.49), (2.2, 0.55, 0.47), (3.0, 0.58, 0.44), (2.4, 0.57, 0.45), (1.1, 0.5, 0.5)):
            lua.execute(f"AGPS_OM.k, AGPS_OM.ux, AGPS_OM.uy = {k}, {ux}, {uy}")
            lua.execute("""
              local box = WorldMapFrame.ScrollContainer
              box.Child:SetScale(AGPS_OM.k)
              box:SetHorizontalScroll(0)
              box:SetVerticalScroll(0)
            """)
            assert f._scale == pytest.approx(1 / k)  # (its size kept at once, before any redraw)
            r = c._scale or 1
            pt = c._pts["CENTER"]
            assert pt is not None and r == pytest.approx(k / 1.4)
            ox, oy = pt[4] * r, pt[5] * r  # (our canvas's middle from the frame's: its own units times its scale)
            for px, py in ((2254.0, 293.0), (1500.0, -900.0), (3600.0, 2800.0)):
                hx, hy = (b[3] - py) / W, (b[2] - px) / H
                want = ((hx - ux) * cw * k, (uy - hy) * ch * k)
                got = (ox + r * s0 * (y0 - py), oy + r * s0 * (px - x0))  # (as drawn, moved with our canvas)
                assert got[0] == pytest.approx(want[0], abs=1e-6) and got[1] == pytest.approx(want[1], abs=1e-6)
        # the redraw: laid out again for this view, our canvas as it always is, the icons laid at the box's scale
        seen = []
        lay = G.LayoutPois
        G.LayoutPois = lambda *a: (seen.append(f.GetEffectiveScale(f)), lay(*a))[1]
        try:
            lua.execute("AGPS_OM.k = 2.7 WorldMapFrame.ScrollContainer.Child:SetScale(2.7)")
            lua.execute("AGPS_OM.k = 3.3")  # (zoomed again, no setter heard: the redraw keeps the size first)
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        finally:
            G.LayoutPois = lay
        assert seen and all(v == pytest.approx(1) for v in seen)
        assert (c._scale or 1) == 1 and G.noMapXf is None and c._pts["CENTER"] is None
        x, y, _, _, s, _ = G.ViewState()
        assert s == pytest.approx(s0 * 3.3 / 1.4)
        # another style: our canvas clips again, as always
        G.SetStyle("minimap")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.noMapXf is None
    finally:
        lua.execute("hooksecurefunc = AGPS_HOOKS_WAS AzerothGPSFrame.GetEffectiveScale = nil")
        lua.execute("WorldMapFrame.ScrollContainer.GetEffectiveScale = nil")


# OpenMap's coordinates (its Map/Extras.lua, read only: a 1 x 22 bar 9000 levels over the map in its bottom-right
# corner, its two pills to its left) on a narrow world map, across the middle where Confirm Route goes.
OPENMAP_COORDS = """
  local box = WorldMapFrame.ScrollContainer
  box.GetWidth = function() return 500 end
  box.GetHeight = function() return 400 end
  box.GetLeft = function() return 20 end
  box.GetRight = function() return 520 end
  box.GetBottom = function() return 10 end
  box.GetTop = function() return 410 end
  local function Rect(f, l, b, w, h, level)
    f.GetLeft = function() return l end
    f.GetBottom = function() return b end
    f.GetWidth = function() return w end
    f.GetHeight = function() return h end
    f.GetFrameLevel = function() return level end
    return f
  end
  local bar = Rect(CreateFrame("Frame", nil, box), 520 - 40, 18, 1, 22, 9000)
  Rect(CreateFrame("Frame", nil, bar), 520 - 40 - 150, 18, 150, 24, 9001)
  Rect(CreateFrame("Frame", nil, bar), 520 - 40 - 306, 18, 150, 24, 9001)
  local G = AGPS_NS.GPS
  G.mapButtons.import.GetFrameLevel = function() return 4050 end
  G.TopLayer().GetWidth = function() return 500 end
  G.TopLayer().GetHeight = function() return 400 end
"""
OPENMAP_COORDS_UNDO = """
  local box = WorldMapFrame.ScrollContainer
  box.GetLeft, box.GetRight, box.GetBottom, box.GetTop = nil, nil, nil, nil
  box.GetWidth = function() return 700 end
  box.GetHeight = function() return 460 end
  box._kids = {}
  local G = AGPS_NS.GPS
  G.mapButtons.import.GetFrameLevel = nil
  G.TopLayer().GetWidth, G.TopLayer().GetHeight = nil, nil
"""


def _tick(lua, G):
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()


def _drag_map(lua, G, dx, dy):
    frame = lua.globals().AzerothGPSFrame
    lua.execute("AGPS_CUR_WAS = GetCursorPosition GetCursorPosition = function() return 300, 300 end")
    try:
        frame._scripts.OnMouseDown(frame, "LeftButton")
        lua.execute(f"GetCursorPosition = function() return {300 + dx}, {300 + dy} end")
        frame._scripts.OnUpdate(frame, 0.05)
        frame._scripts.OnMouseUp(frame, "LeftButton")
    finally:
        lua.execute("GetCursorPosition = AGPS_CUR_WAS")
    _tick(lua, G)


@pytest.mark.parametrize("openmap", [False, True])
def test_confirm_route_and_the_way_back_show_on_no_map(nomap, openmap):
    """Kooki3z 2026-11-27 for 1.4.2: "using openmap addon and no map ... don't get confirm/cancel route buttons". Over
    OpenMap's map each redraw took OpenMap's view for the map's own, dropping the player's look: a drag on the map (which
    pans OpenMap's view) left no crosshair, so no Confirm Route, and nothing to go back with. Now, with OpenMap and
    without it: a drag shows the crosshair, Confirm Route and Back to Your Position, kept over the redraws that follow
    OpenMap's view; Confirm Route routes to the middle; a double-clicked stop shows Confirm Route (1), and Back to Your
    Position drops it. Confirm Route is clear of OpenMap's coordinates on a narrow map."""
    lua, ns = nomap
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    btn, back = G.confirmRouteBtn, G.mapButtons.recenter
    _open(lua, ns)
    if openmap:
        lua.execute(OPENMAP)
        lua.execute(OPENMAP_COORDS)
    try:
        assert G.SetStyle("none")
        G.ApplySettings()
        G.Follow()
        _tick(lua, G)
        assert G.NoMapOn() and G.NoMapStitched() is openmap
        assert not btn._shown and not G.crossShown
        # a drag on the map: the crosshair, Confirm Route and the way back
        _drag_map(lua, G, 60, 20)
        for _ in range(3):  # (and kept as OpenMap's view is followed at each redraw)
            assert G.crossShown and btn._shown and back._shown
            assert btn._text == "Confirm Route"
            _tick(lua, G)
        if openmap:
            # (clear of OpenMap's coordinates: their pills' top is 32 over the map's bottom)
            y = btn._pts["BOTTOM"][3]
            assert y >= 32 + 3 and G.routeButtonY == y
            # (and the strip, when there's one, over it: G.mx.below's button)
        x, y, cont = tuple(G.ViewState())[:3]
        btn._scripts.OnClick(btn)
        assert N.dest is not None and (N.dest.x, N.dest.y) == (pytest.approx(x), pytest.approx(y))
        _tick(lua, G)
        assert not G.crossShown and not btn._shown  # (routed: no crosshair)
        N.Clear()
        # a double-clicked stop: Confirm Route (1); Back to Your Position drops it
        G.Follow()
        _tick(lua, G)
        G.AddPending(10, 10)
        _tick(lua, G)
        assert btn._shown and btn._text == "Confirm Route (1)" and back._shown
        _tick(lua, G)
        assert btn._shown and G.PendingStop(1) is not None
        back._scripts.OnClick(back)
        _tick(lua, G)
        assert G.PendingStop(1) is None and not btn._shown and not G.crossShown
        if openmap:
            assert lua.eval("AGPS_OM.shown") is not None  # (OpenMap's view glided back to the player)
    finally:
        if openmap:
            lua.execute(OPENMAP_COORDS_UNDO)
        N.Clear()


# ---------------------------------------------------------------------------- Options > Map > Map style: what No Map lacks


def test_options_says_in_red_what_no_map_lacks_only_while_it_is_picked(nomap):
    """Kooki3z 2026-11-27 for 1.4.2: "add a red notice when no map is selected and using game map that the viewing NPCs
    in buildings and routing to places inside caves are not supported with OpenMap (and anything else you know wouldn't
    work like follow player functions, etc)". Under the Map style list, in Options' warning red: shown only with No Map
    picked and the GPS map in the game's world map, hidden otherwise (its room closed up); its OpenMap line only with the
    OpenMap addon too. The style notes above it are short."""
    lua, ns = nomap
    O, G, st = ns.Options, ns.GPS, ns.settings.gps
    O.Show()
    O.ShowPage("Map")
    red, om_red = O.noMapNotice, O.noMapOpenMapNotice
    dd = next(c.control for c in O.settingControls.values() if c.key == "style")
    was = st.useWorldMap
    try:
        text, om_text = str(red._text), str(om_red._text)
        # (Kooki3z: "just put "NOTICE:" in red the rest of the info can be in grey": "NOTICE:" once, red, at the first
        # line's start; the rest, and the OpenMap line, in the gray of the other notes)
        assert O.WARN_RED == "|cffff4040" and text.startswith(O.WARN_RED + "NOTICE:|r ")
        assert text.count("|c") == 1 and text.count("|r") == 1 and "NOTICE" not in om_text and "|c" not in om_text
        assert str(red._fontObject) == "GameFontDisableSmall" and str(om_red._fontObject) == "GameFontDisableSmall"
        assert text.startswith(O.WARN_RED + "NOTICE:|r No Map can't show ")
        for item in ("building and cave maps", "floors", "NPCs inside", "stops placed inside caves"):
            assert item in text
        assert "OpenMap addon" in om_text and "follow you" in om_text and "zoom in near a stop" in om_text
        assert "pan with a controller" in om_text and "controller" not in text  # (pans on the game's map: OpenMap's only)
        # another style: hidden
        st.useWorldMap = True
        G.ApplySettings()
        G.SetStyle("zone")
        O.Refresh()
        assert red._shown is False and om_red._shown is False
        under = dd._pt[3]
        # No Map with the world map: shown, live (SetStyle refreshes Options); the OpenMap line not without OpenMap
        assert G.SetStyle("none")
        assert red._shown is True and om_red._shown is False
        lua.execute(OPENMAP)
        O.Refresh()
        assert red._shown is True and om_red._shown is True
        # the world map option off: No Map isn't drawn, nothing said
        st.useWorldMap = False
        G.ApplySettings()
        O.Refresh()
        assert red._shown is False and om_red._shown is False
        st.useWorldMap = True
        G.ApplySettings()
        O.Refresh()
        assert red._shown is True
        lua.execute("OpenMapAPI = nil")  # (the gold hint for OpenMap's players hidden too, for the room's check)
        G.SetStyle("zone")
        assert red._shown is False and om_red._shown is False and dd._pt[3] == under
        # (the style notes: a sentence or two each)
        notes = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString"]
        for start in ("OpenMap (the default", "Terrain: the ground", "No Map (with", "Using the OpenMap addon?"):
            n = next(t for t in notes if t.startswith(start))
            assert len(n) <= 200, n
        assert any(t.startswith("OpenMap (the default") and "/reload" in t for t in notes)
    finally:
        lua.execute("OpenMapAPI = nil")
        st.useWorldMap = was
        G.ApplySettings()
        O.Refresh()
        O.Toggle()


BRILL_TAVERN = (2269.5, 244.9)  # (Gallows' End Tavern, Innkeeper Renee's)
WAILING_CAVERNS = (-569.8, -2291.7)  # (over the Wailing Caverns, north of Lushwater Oasis: test_cave_clicks')


def _hover_building(lua, ns, x, y):
    G = ns.GPS
    place, wmo, room = G.InteriorUnder(x, y, 0)
    assert place is not None
    G.hoverInside = lua.eval("function(p, w, r) return { p, w, r, cont = 0 } end")(place, wmo, room)
    G.hoverInsideKey, G.hoverDismissKey = "nomap-test", None
    G.LookAt(0, x, y, 60)
    lua.execute("AGPS_T = AGPS_T + 6")
    G.Redraw()
    G.Update()
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.npc and str(w.npc.name) == "Innkeeper Renee"]


def test_what_the_notice_lists_is_off_on_no_map(nomap):
    """Each thing the red notice lists, checked off on No Map and on in another style: a building's inside map and its
    NPCs (hovered), a cave's map and its floor for a stop (the route's cave, a double-click over it); and over OpenMap's
    map, the view is OpenMap's: it doesn't follow the player or zoom in near a stop, which the game's map does."""
    lua, ns = nomap
    G, N, WG, st = ns.GPS, ns.Nav, ns.WorldGrid, ns.settings.gps
    _open(lua, ns)
    was_zoom = st.zoom
    try:
        # a building's inside map and the NPCs in it
        assert G.SetStyle("minimap")
        assert _hover_building(lua, ns, *BRILL_TAVERN) and G.shownInside is not None
        assert G.SetStyle("none")
        assert not _hover_building(lua, ns, *BRILL_TAVERN) and G.NoMapOn()
        assert G.shownInside is None and G.InteriorMapShown()[0] is None
        assert G.Seamless() is False  # (the hover over buildings and caves is the OpenMap style's: G.BuildingHover)
        G.hoverInside, G.hoverInsideKey = None, None
        # a cave's map (the route's cave, shown as hovered) and a stop on its floor
        WG.Set(True)
        cave = G.CaveAt(1, *WAILING_CAVERNS)
        ground = ns.Ground.Sample(1, *WAILING_CAVERNS)
        floor = G.CaveFloorZ(1, WAILING_CAVERNS[0], WAILING_CAVERNS[1], ground)
        assert cave is not None and floor is not None
        N.dest = lua.eval("{ x = %f, y = %f, cont = 1, z = %f }" % (WAILING_CAVERNS[0], WAILING_CAVERNS[1], floor))
        for style, shown in (("minimap", True), ("none", False)):
            assert G.SetStyle(style)
            G.LookAt(1, WAILING_CAVERNS[0], WAILING_CAVERNS[1], 120)
            _tick(lua, G)
            assert (G.hoveredCave == cave) is shown, style  # (No Map: no cave map, not even the route's)
            z = G.MapStopZ(1, *WAILING_CAVERNS)
            assert (z < ground - G.CAVE_UNDER_YD) is shown, (style, z, ground)  # (No Map: the ground over it)
        N.dest = None
        # a controller's pan in the other styles too (only over OpenMap's map it doesn't, below)
        for style in ("minimap", "zone", "nospoiler"):
            assert G.SetStyle(style)
            G.Follow()
            _tick(lua, G)
            xa = G.ViewState()[1]
            G.PadPan(40, 0)
            _tick(lua, G)
            assert G.ViewState()[1] != pytest.approx(xa), style
        assert G.SetStyle("none")
        # following, the zoom near a stop and a controller's pan: on the game's map; OpenMap's view is its own
        st.approachZoom = True
        for openmap in (False, True):
            if openmap:
                lua.execute(OPENMAP)
            G.Follow()
            _tick(lua, G)
            x0, y0 = tuple(G.ViewState())[:2]
            lua.execute("AGPS_POS_NM = { AGPS_POS[1], AGPS_POS[2] } AGPS_POS[1] = AGPS_POS[1] + 120")
            try:
                _tick(lua, G)
                x1, y1 = tuple(G.ViewState())[:2]
                px, py, pc = list(lua.eval("{ AGPS_NS.Geo.PlayerWorld() }").values())[:3]
                assert G.IsFree() is openmap
                assert ((x1, y1) == (pytest.approx(x0), pytest.approx(y0))) is openmap  # (OpenMap's: still)
                ns.Nav.SetStops(lua.eval("{ { x = %f, y = %f, cont = 0, name = 'Near' } }" % (px + 20, py)), False, "red")
                assert (G.ApproachTarget(px, py, pc) is None) is openmap
                # a controller's pan (Pad.lua's G.PadPan): moves the game's map, not OpenMap's view
                xa = G.ViewState()[1]
                for _ in range(3):
                    G.PadPan(40, 0)
                    _tick(lua, G)
                assert (G.ViewState()[1] == pytest.approx(xa)) is openmap
                ns.Nav.Clear()
            finally:
                lua.execute("AGPS_POS[1], AGPS_POS[2] = AGPS_POS_NM[1], AGPS_POS_NM[2]")
    finally:
        N.dest = None
        ns.Nav.Clear()
        G.hoverInside, G.hoverInsideKey = None, None
        st.zoom = was_zoom
        lua.execute("OpenMapAPI = nil")
