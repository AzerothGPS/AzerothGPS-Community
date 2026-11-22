"""The GPS map in the game's own world map window (the option `useWorldMap`, asked 2026-11-10: "an option that uses the
in game map instead of the GPS map, adding the buttons to that map instead ... instead of the minimap logo popping out
the GPS map it'd instead pop out the main map"): laid over the world map's map area while that window is open, at its
size, with no frame of its own; no window of its own while it's closed; the square's logo and the show/hide key open
the world map; the game's Minimap is its own again meanwhile."""

import pytest

from test_map_redraw import MM_SETUP, game  # noqa: F401

SETUP = MM_SETUP + """
  WorldMapFrame.ScrollContainer = NewWidget("ScrollFrame", "AGPSTestWorldMapBox")
  WorldMapFrame.ScrollContainer.GetWidth = function() return 700 end
  WorldMapFrame.ScrollContainer.GetHeight = function() return 460 end
  WorldMapFrame._strata = "HIGH"
  WorldMapFrame:Hide()
  AGPS_TOGGLES = 0
  ToggleWorldMap = function()
    AGPS_TOGGLES = AGPS_TOGGLES + 1
    WorldMapFrame:SetShown(not WorldMapFrame:IsShown())
    AGPS_NS.GPS.WorldMapChanged() -- (as its OnShow and OnHide do in the game)
  end
"""


@pytest.fixture
def wm(game):  # noqa: F811
    lua, ns = game
    lua.execute(SETUP)
    st = ns.settings.gps
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized", "windowFrame")}
    st.shown, st.minimized = True, None
    yield lua, ns
    lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
    for k, v in was.items():
        st[k] = v
    ns.GPS.WorldMapChanged()
    ns.GPS.ApplySettings()


def test_off_the_world_map_changes_nothing(wm):
    lua, ns = wm
    G = ns.GPS
    f = lua.eval("AzerothGPSFrame")
    G.ApplySettings()
    own = (f._w, f._h)
    lua.execute("WorldMapFrame:Show()")
    G.WorldMapChanged()
    assert not G.WorldMapHosted() and f._shown and (f._w, f._h) == own


def test_the_map_is_laid_over_the_world_map_while_it_is_open(wm):
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    f = lua.eval("AzerothGPSFrame")
    box = lua.eval("WorldMapFrame.ScrollContainer")
    own = tuple(G.MapSize(None, True))
    zoom = st.zoom
    st.useWorldMap = True
    G.ApplySettings()
    assert G.WorldMapWanted() and not G.WorldMapHosted()
    assert not f._shown  # (no window of its own while the world map is closed)
    lua.globals().AzerothGPS_ToggleMap()  # (the show/hide key: the world map)
    assert lua.eval("AGPS_TOGGLES") == 1 and G.WorldMapHosted()
    assert f._shown and tuple(G.MapSize()) == (700, 460) and (f._w, f._h) == (700, 460)
    assert tuple(G.MapSize(None, True)) == own and st.zoom == zoom  # (the player's own size and zoom: untouched)
    assert f._pt[1] == "TOPLEFT" and lua.eval("rawequal")(f._pt[2], box)
    assert G.topInset == G.WORLD_MAP_INSET  # (the directions right of the world map's own corner buttons)
    # (that window's child meanwhile: the game draws its world map as one picture, a frame from outside is under
    # all of it or over all of it, read from the game 2026-11-10; so it fades and hides with it too)
    assert lua.eval("rawequal")(f.GetParent(f), G.WorldMapCanvas())
    # (in the world map's own strata, from a low frame level: over its art, under its icons, which start near 2000)
    assert f._strata == "HIGH" and f._level == G.WorldMapLevel() == box.GetFrameLevel(box) + 1
    # (the game's window raised since, its art with it: one over its art again, seen in a recording 2026-11-10)
    lua.execute("WorldMapFrame.ScrollContainer.GetFrameLevel = function() return 300 end")
    G.WorldMapTick()
    assert f._level == 301
    lua.execute("WorldMapFrame.ScrollContainer.GetFrameLevel = nil")
    G.WorldMapTick()
    assert G.Canvas()._level is not None  # (every frame in it moved along, one by one)
    for part in (G.chrome, G.sizeGrip, G.moveTab):  # (the world map's own frame: none of ours)
        assert part is None or not part._shown
    lua.globals().AzerothGPS_ToggleMap()
    assert lua.eval("AGPS_TOGGLES") == 2 and not G.WorldMapHosted() and not f._shown
    # (back on the screen, its own window's strata: over the game's windows since 1.3.14, as the map grown out of the
    # minimap square)
    assert f._strata == G.MINIMAP_EXPANDED_STRATA and lua.eval("rawequal")(f.GetParent(f), lua.eval("UIParent"))
    st.useWorldMap = False
    G.ApplySettings()
    assert f._shown and (f._w, f._h) == own  # (off: its own window again, as it was)


def test_the_squares_logo_opens_the_world_map_and_the_minimap_is_its_own_meanwhile(wm):
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    f = lua.eval("AzerothGPSFrame")
    st.useWorldMap, st.replaceMinimap = True, True
    G.ApplySettings()
    m = G.mmState
    try:
        side = G.MinimapSquareSide()
        assert m.on and m.applied and G.MinimapMode() and (f._w, f._h) == (side, side) and G.mmButton._shown
        G.mmButton._scripts.OnClick(G.mmButton, "LeftButton")
        assert lua.eval("AGPS_TOGGLES") == 1 and G.WorldMapHosted() and not m.expanded
        assert not G.MinimapMode() and (f._w, f._h) == (700, 460)
        # (the square keeps a map of its own: a second one, made of the same code, where the first one's square was,
        # under the game's Minimap left as it is on the square; asked 2026-11-10, "need to just be 2 duplicate
        # instances of AzerothGPS drawings when opened")
        assert m.applied and G.MinimapTaken() and lua.eval("AGPS_MM.ground") is False
        c = ns.mapClone
        assert c is not None and c.clone is True and not G.clone and ns.MakeMapClone is not None
        assert lua.eval("rawequal")(ns.GPS, G) and lua.eval("rawequal")(lua.eval("AzerothGPSFrame"), f)  # (the first: untouched)
        # (another addon's Shift-clicks on bosses and NPCs, API.OnIconShiftClick, work on both maps: issue #383)
        assert lua.eval("rawequal")(c.iconClicks, G.iconClicks)
        lua.globals().AzerothGPS.OnIconShiftClick("Test", lua.eval("function(info) return info.kind == 'npc' end"))
        try:
            assert c.IconShiftClick(c.NpcClickInfo(2135, "Abe Winters", None, 0, 2237.8, 304.1, 36.8)) is True
        finally:
            lua.globals().AzerothGPS.OnIconShiftClick("Test", None)
        cf = c.Canvas().GetParent(c.Canvas())
        assert not lua.eval("rawequal")(cf, f) and cf._shown and (cf._w, cf._h) == (side, side)
        assert c.MinimapMode() and c.mmState.on and lua.eval("rawequal")(c.mmState.home, m.home)
        assert not c.WorldMapWanted() and c.ClickThroughWanted(ns.settings.gps, False, False) is True
        masks = lua.eval("#AGPS_MM.masks")
        box = ns.Atlas.artBox  # (the stitched map's art: the first map's stays its own, the second has its own engine)
        assert c.ArtSpan() == G.ArtSpan()
        c.ApplySettings()
        c.Update()
        assert (box is None and ns.Atlas.artBox is None) or lua.eval("rawequal")(ns.Atlas.artBox, box)
        assert not c.mmChromeCompact is False and c.chrome is None or c.mmChromeCompact is True  # (the square's border, no title bar)
        assert lua.eval("#AGPS_MM.masks") == masks  # (nothing of the game's Minimap touched by the second)
        assert st.replaceMinimap is True and st.useWorldMap is True and st.shown is True  # (the player's settings: theirs)
        # (the logo stays on the square's corner, and the map's icons and route go on the minimap standing in)
        assert G.mmButton._shown and lua.eval("rawequal")(G.mmButton._pt[2], G.mmAnchor)
        G.SetMinimapExpanded(True)  # (never a window of its own as well)
        assert not m.expanded and lua.eval("AGPS_TOGGLES") == 1
        lua.globals().ToggleWorldMap()
        assert G.MinimapMode() and m.applied and (f._w, f._h) == (side, side) and G.mmButton._shown
        assert not m.standIn and G.MinimapTaken() and lua.eval("AGPS_MM.ground") is False  # (the map's own again)
        assert not cf._shown  # (the first one back on the square: the second put away)
    finally:
        st.replaceMinimap = False
        G.ApplySettings()


def test_the_tutorial_runs_on_the_maps_own_window(wm):
    lua, ns = wm
    T, G, st = ns.Tutorial, ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    ok = T.Start(lua.eval("{ 'route' }"))
    ok = ok[0] if isinstance(ok, tuple) else ok
    assert ok is True
    try:
        assert st.useWorldMap is False and not G.WorldMapWanted()
    finally:
        T.Exit()
    assert st.useWorldMap is True  # (back as the player had it)


def test_the_tutorial_offers_the_world_map_option_and_turns_it_on_as_it_ends(wm):
    # (asked 2026-11-10: "add this to the tutorials")
    lua, ns = wm
    T, G, st = ns.Tutorial, ns.GPS, ns.settings.gps
    st.useWorldMap = False
    ok = T.Start(lua.eval("{ 'window' }"))
    assert (ok[0] if isinstance(ok, tuple) else ok) is True
    for _ in range(12):
        if str(T.run.step.title) == "In the game's world map":
            break
        T.NextClicked()
    assert str(T.run.step.title) == "In the game's world map"
    box = T.panel.checks[1]
    assert str(box.label._text) == "Show the GPS map in the game's world map" and box._shown
    # (asked 2026-11-10: "during this step it should be done automatically to demo the feature. If they don't check
    # it then next step puts it back": shown by itself on this step, the checkbox only whether it's kept after)
    assert st.useWorldMap is True and lua.eval("WorldMapFrame:IsShown()") and G.WorldMapHosted()
    T.Back()
    assert st.useWorldMap is False and not lua.eval("WorldMapFrame:IsShown()")  # (the step before: its own window)
    T.NextClicked()
    assert G.WorldMapHosted()
    T.NextClicked()
    assert st.useWorldMap is False and not lua.eval("WorldMapFrame:IsShown()")  # (unticked: put back, and stays so)
    T.Exit()
    assert st.useWorldMap is False
    T.Start(lua.eval("{ 'window' }"))
    for _ in range(12):
        if str(T.run.step.title) == "In the game's world map":
            break
        T.NextClicked()
    box = T.panel.checks[1]
    box.GetChecked = lua.eval("function() return true end")
    box._scripts.OnClick(box)
    assert G.WorldMapHosted()
    T.NextClicked()
    # (the steps after: on the map's own window again)
    assert st.useWorldMap is False and not lua.eval("WorldMapFrame:IsShown()")
    T.Exit()
    assert st.useWorldMap is True and G.WorldMapWanted()  # (kept, as the tutorial ends)


def test_the_map_fades_as_the_world_map_does_and_closes_as_the_player_moves_or_fights(wm):
    # (asked 2026-11-10: "when moving the game fades the map window ... it should do the same to match"; "if collapse
    # on move/combat is on, this happens with the in game map too when popped out from gps icon on minimap or hotkey")
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    f = lua.eval("AzerothGPSFrame")
    lua.execute("""
      AGPS_WM_ALPHA = 1
      AzerothGPSFrame.SetAlpha = function(fr, v) fr._alpha = v end
      WorldMapFrame.GetAlpha = function() return AGPS_WM_ALPHA end
      AGPS_WM_MOVING = false
      AGPS_REAL_MOVING = IsPlayerMoving
      IsPlayerMoving = function() return AGPS_WM_MOVING end
      HideUIPanel = function(fr) fr:Hide() AGPS_NS.GPS.WorldMapChanged() end
    """)
    was = (st.replaceMinimapCollapseOnMove, st.replaceMinimapCollapseOnCombat)
    st.useWorldMap = True
    st.replaceMinimapCollapseOnMove, st.replaceMinimapCollapseOnCombat = True, True
    G.ApplySettings()
    try:
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted() and G.wmState.byUs and G.wmTicker._shown
        assert lua.eval("rawequal")(f.GetParent(f), G.WorldMapCanvas())  # (faded with the game's window: in it)
        lua.execute("AGPS_WM_MOVING = true")
        G.WorldMapTick()
        assert not G.WorldMapHosted() and not G.wmTicker._shown  # (a step: closed)
        lua.execute("AGPS_WM_MOVING = false")
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        G.MinimapCombatStarts()
        assert not G.WorldMapHosted()  # (a fight: closed)
        # opened by the player with the game's own key: theirs, left open
        lua.execute("WorldMapFrame:Show()")
        G.WorldMapChanged()
        assert G.WorldMapHosted() and not G.wmState.byUs
        lua.execute("AGPS_WM_MOVING = true")
        G.WorldMapTick()
        G.MinimapCombatStarts()
        assert G.WorldMapHosted()
    finally:
        lua.execute("IsPlayerMoving = AGPS_REAL_MOVING HideUIPanel = nil WorldMapFrame.GetAlpha = nil AGPS_WM_MOVING = nil AzerothGPSFrame.SetAlpha = nil")
        st.replaceMinimapCollapseOnMove, st.replaceMinimapCollapseOnCombat = was


def test_the_games_map_is_kept_on_the_same_ground_so_its_icons_line_up(wm):
    # (asked 2026-11-10: "should fall between the map and all its original icons on top ... our map > our icons >
    # everything else": the game's map follows ours, zone or continent, at our scale and place)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      local box = WorldMapFrame.ScrollContainer
      box.Child = NewWidget("Frame", "AGPSTestWorldMapChild")
      box.Child.GetWidth = function() return 1002 end
      box.Child.GetHeight = function() return 668 end
      AGPS_WMS = { maps = {}, zooms = {} }
      box.InstantPanAndZoom = function(_, sc, u, v, raw) table.insert(AGPS_WMS.zooms, { sc, u, v, raw }) end
      box.SetHorizontalScroll = function(_, h) AGPS_WMS.h = h end
      box.SetVerticalScroll = function(_, v) AGPS_WMS.v = v end
      box.GetHorizontalScroll = function() return AGPS_WMS.h end box.GetVerticalScroll = function() return AGPS_WMS.v end
      WorldMapFrame.GetMapID = function() return AGPS_WMS.map end
      WorldMapFrame.SetMapID = function(_, id) AGPS_WMS.map = id table.insert(AGPS_WMS.maps, id) end
    """)
    st.useWorldMap = True
    G.ApplySettings()
    try:
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
        # Durotar, close in: the zone's own map
        G.LookAt(1, -600.0, -4200.0, 300.0)
        G.Update(True)
        assert G.WorldMapSync() is True
        x, y, cont, rot, s, _ = G.ViewState()
        assert rot == 0
        zone = lua.eval("AGPS_WMS.map")
        m = ns.Maps[zone]
        assert m.type == 3 and str(m.name) == "Durotar"
        b = list(m.bounds.values())
        sc = lua.eval("AGPS_WMS.zooms[#AGPS_WMS.zooms][1]")
        mapW, mapH = b[3] - b[1], b[2] - b[0]
        assert sc == pytest.approx(s * mapW / 1002)  # (a yard as big on the game's map as on ours)
        # (in the game's own canvas, among its icons by level, and as big as ever whatever the canvas's zoom)
        child = lua.eval("WorldMapFrame.ScrollContainer.Child")
        ff = lua.eval("AzerothGPSFrame")
        assert lua.eval("rawequal")(ff.GetParent(ff), child) and ff._level == child.GetFrameLevel(child) + 1
        lua.execute("AGPS_SCALES = {} AzerothGPSFrame.SetScale = function(_, k) table.insert(AGPS_SCALES, k) end")
        lua.execute("WorldMapFrame.ScrollContainer.Child.GetEffectiveScale = function() return 2.5 end")
        assert G.WorldMapKeepScale() is True and lua.eval("AGPS_SCALES[#AGPS_SCALES]") == pytest.approx(1 / 2.5)
        assert G.WorldMapKeepScale() is False
        lua.execute("WorldMapFrame.ScrollContainer.Child.GetEffectiveScale = nil AzerothGPSFrame.SetScale = nil")
        # the view's middle is at our canvas's middle on the game's map too
        box = lua.eval("WorldMapFrame.ScrollContainer")
        dx, dy = box.GetWidth(box) / 2, box.GetHeight(box) / 2  # (the map's middle: the scroll frame's)
        u, v = (b[3] - y) / mapW, (b[2] - x) / mapH
        assert lua.eval("AGPS_WMS.h") == pytest.approx(u * 1002 - dx / sc)
        assert lua.eval("AGPS_WMS.v") == pytest.approx(v * 668 - dy / sc)
        assert G.WorldMapSync() is False  # (nothing moved: nothing set again)
        # (the game's scroll frame pulling its vertical scroll back: set again, reported 2026-11-12)
        want = lua.eval("AGPS_WMS.v")
        lua.execute("AGPS_WMS.v = AGPS_WMS.v - 40")
        assert G.WorldMapSync() is True and lua.eval("AGPS_WMS.v") == pytest.approx(want)
        assert G.WorldMapSync() is False
        # (but held at its limit by the game, set once and left there: setting it again every frame fought the game
        # every frame, 1.2.5's stutters reported 2026-11-13)
        lua.execute("AGPS_WMS.sets = 0 AGPS_WMS.v = AGPS_WMS.v - 80 AGPS_WMS.limit = AGPS_WMS.v")
        lua.execute("""WorldMapFrame.ScrollContainer.SetVerticalScroll = function(_, v)
          AGPS_WMS.sets = AGPS_WMS.sets + 1 AGPS_WMS.v = math.min(v, AGPS_WMS.limit) end""")
        assert G.WorldMapSync() is True
        for _ in range(5):
            assert G.WorldMapSync() is False
        assert lua.eval("AGPS_WMS.sets") == 1
        # (pulled back a frame later by the game's own update, the same each time: tried once more, then left)
        lua.execute("AGPS_WMS.limit = nil WorldMapFrame.ScrollContainer.SetVerticalScroll = function(_, v) AGPS_WMS.sets = AGPS_WMS.sets + 1 AGPS_WMS.v = v end")
        held = lua.eval("AGPS_WMS.v")
        for _ in range(5):
            G.WorldMapSync()
            lua.execute("AGPS_WMS.v = %r" % held)
        assert lua.eval("AGPS_WMS.sets") <= 3
        lua.execute("WorldMapFrame.ScrollContainer.SetVerticalScroll = function(_, v) AGPS_WMS.v = v end")
        # zoomed far out: the continent's map
        G.LookAt(1, -600.0, -4200.0, 9000.0)
        G.Update(True)
        assert G.WorldMapSync() is True
        assert ns.Maps[lua.eval("AGPS_WMS.map")].type == 2
        # a map picked in the game's own bar: ours looks at it
        lua.execute("AGPS_WMS.map = 1413")  # (The Barrens)
        G.WorldMapSync()
        G.Update(True)
        x, y = G.ViewState()[0], G.ViewState()[1]
        bb = list(ns.Maps[1413].bounds.values())
        assert x == pytest.approx((bb[0] + bb[2]) / 2) and y == pytest.approx((bb[1] + bb[3]) / 2)
        # other addons' icons: their own on the game's map, no copies of ours meanwhile
        assert ns.OtherPins.On() is False
    finally:
        lua.execute("""
          local box = WorldMapFrame.ScrollContainer
          box.Child, box.InstantPanAndZoom, box.SetHorizontalScroll, box.SetVerticalScroll, box.GetHorizontalScroll, box.GetVerticalScroll = nil
          WorldMapFrame.GetMapID, WorldMapFrame.SetMapID = nil
        """)
        lua.execute("WorldMapFrame:Hide()")
        G.WorldMapChanged()
        G.Follow()
    assert ns.OtherPins.On() is True


def test_frames_over_everything_by_their_strata_are_put_over_by_level_in_the_world_map(wm):
    # (seen in game 2026-11-10: "Path color dropdown for dungeons is hidden behind the dungeon map, should be on top";
    # in the game's map canvas a strata means nothing, so those go far up by level, over the game's icons too)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    lst = G.pathColorList
    assert lst is not None and lst._strata == "FULLSCREEN_DIALOG"
    lua.execute("AGPS_PCL = AGPS_NS.GPS.pathColorList AGPS_PCL.GetFrameLevel = function(s) return s._level or 10 end")
    own = lst.GetFrameLevel(lst)
    st.useWorldMap = True
    G.ApplySettings()
    try:
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
        assert lst._level >= G.WORLD_MAP_OVER and lst._level > 3000  # (over the game's icons: 2000 to about 2900)
        lua.globals().ToggleWorldMap()
        assert lst._level == own  # (back out: its own level, its strata doing the work again)
    finally:
        lua.execute("AGPS_PCL.GetFrameLevel = nil AGPS_PCL = nil")


def test_the_maps_buttons_are_over_the_games_icons_in_the_world_map_and_the_map_under_them(wm):
    # (seen in game 2026-11-11, other addons' icons drawn across Clear Route: "Map overlays are going over our
    # buttons, our buttons should always be on top of those")
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    b, poi = G.searchButton, G.poiLayer
    assert b is not None and poi is not None
    # (in the window's own strata, as in the game: the stand-in frames don't take their parent's)
    lua.execute("AGPS_SB, AGPS_PL = AGPS_NS.GPS.searchButton, AGPS_NS.GPS.poiLayer "
                "AGPS_SB.GetFrameStrata = function() return AzerothGPSFrame:GetFrameStrata() end "
                "AGPS_PL.GetFrameStrata = AGPS_SB.GetFrameStrata")
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().ToggleWorldMap()
    try:
        assert G.WorldMapHosted()
        # (the game's icons: 2000 to about 2900)
        assert b._level >= min(9000, G.WorldMapLevel() + G.WORLD_MAP_BUTTONS)
        assert poi._level < G.WorldMapLevel() + 100 and b._level > poi._level + 3000
        assert b._level < G.WorldMapLevel() + G.WORLD_MAP_OVER
    finally:
        lua.globals().ToggleWorldMap()
        lua.execute("AGPS_SB.GetFrameStrata, AGPS_PL.GetFrameStrata = nil, nil AGPS_SB, AGPS_PL = nil, nil")
    assert b._level < 200  # (back out: where it was over the map)


def test_with_the_games_controller_ui_on_the_map_is_not_in_the_games_world_map(wm):
    # (seen in game 2026-11-11 with the controller UI on: "AzerothGPS SetPreferredGamepadInteractTarget()",
    # ADDON_ACTION_FORBIDDEN, 32 times with the map opened by the square's logo and 24 more with the game's own key,
    # "worked for the first couple map opens then got the same error". The game runs that function of its own each time
    # a panel is shown or hidden; a panel shown by an addon, or the game's map read after an addon set its zone and
    # zoom, makes it forbidden)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.execute("""
      AGPS_TW, AGPS_HP, AGPS_CALLS, AGPS_STYLE = ToggleWorldMap, HideUIPanel, 0, 1
      ToggleWorldMap = function(...) AGPS_CALLS = AGPS_CALLS + 1 return AGPS_TW(...) end
      HideUIPanel = function(...) AGPS_CALLS = AGPS_CALLS + 1 if AGPS_HP then return AGPS_HP(...) end end
      Enum = Enum or {}
      AGPS_IDT = Enum.InputDeviceInterfaceType
      Enum.InputDeviceInterfaceType = { Mkb = 0, Gamepad = 1 }
      C_InputInterfaceStyle = { GetCurrentStyle = function() return AGPS_STYLE end }
      AGPS_SAID, AGPS_PRINT = 0, AGPS_NS.Print
      AGPS_NS.Print = function() AGPS_SAID = AGPS_SAID + 1 end
      AGPS_SETS, AGPS_SMI = 0, WorldMapFrame.SetMapID
      WorldMapFrame.SetMapID = function() AGPS_SETS = AGPS_SETS + 1 end
    """)
    wmf = lua.eval("WorldMapFrame")
    try:
        assert G.ControllerUI() and G.PanelsHeld() and G.panelsHeldSaid is None
        # the option is the player's still, but not in effect: said once
        assert G.WorldMapWanted() is False and G.WorldMapWanted() is False and st.useWorldMap is True
        assert lua.eval("AGPS_SAID") == 1
        G.ApplySettings()
        # nothing of the game's opened or closed from here
        assert G.ToggleWorldMap() is False and G.CloseWorldMap() is False
        assert not wmf._shown and lua.eval("AGPS_CALLS") == 0
        # the game's map opened by the player's own key: the game's alone, nothing set on it
        lua.eval("AGPS_TW")()
        G.WorldMapChanged()
        assert wmf._shown and not G.WorldMapHosted() and lua.eval("AGPS_SETS") == 0
        lua.eval("AGPS_TW")()
        G.WorldMapChanged()
        # the controller UI off: as before
        lua.execute("AGPS_STYLE = 0")
        G.mmEvents._scripts.OnEvent(G.mmEvents, "INPUT_DEVICE_INTERFACE_TRANSITION")
        assert not G.ControllerUI() and G.WorldMapWanted() is True
        assert G.ToggleWorldMap() is True and wmf._shown and lua.eval("AGPS_CALLS") == 1 and G.WorldMapHosted()
        assert G.CloseWorldMap() is True and not wmf._shown
    finally:
        lua.execute("""
          if WorldMapFrame:IsShown() then AGPS_TW() end
          ToggleWorldMap, HideUIPanel, C_InputInterfaceStyle = AGPS_TW, AGPS_HP, nil
          WorldMapFrame.SetMapID = AGPS_SMI
          Enum.InputDeviceInterfaceType = AGPS_IDT
          AGPS_NS.Print = AGPS_PRINT
          AGPS_NS.GPS.panelsHeldSaid = nil
          AGPS_TW, AGPS_HP, AGPS_CALLS, AGPS_STYLE, AGPS_IDT, AGPS_SAID, AGPS_PRINT, AGPS_SETS, AGPS_SMI = nil
        """)
        G.WorldMapChanged()


def test_a_double_click_on_any_icon_of_the_games_map_makes_a_stop_there(wm):
    # (asked 2026-11-10: "support double clicking default map quest icons, questie icons, any icon for routing"; the
    # icons are the game's and other addons' frames over the map, a button inside one for some, so the click is heard
    # from the game, not through the map)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.execute("""
      AGPS_ADDS, AGPS_NOW, AGPS_FOCUS = {}, 100, nil
      AGPS_WAS = { add = AGPS_NS.GPS.AddPending, time = GetTime, foci = GetMouseFoci, cur = GetCursorPosition }
      AGPS_NS.GPS.AddPending = function(dx, dy) table.insert(AGPS_ADDS, { dx, dy }) end
      GetTime = function() return AGPS_NOW end
      GetMouseFoci = function() return { AGPS_FOCUS } end
      GetCursorPosition = function() return 321, 123 end
    """)
    try:
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
        lua.execute("""
          local child = AGPS_NS.GPS.WorldMapCanvas()
          local pin = CreateFrame("Frame", nil, child)
          AGPS_ICON = CreateFrame("Button", nil, pin) -- (another addon's: a button in the game's pin)
          AGPS_ICON.GetCenter = function() return 400, 300 end
          AGPS_ICON.GetEffectiveScale = function() return 1 end
          AGPS_ICON.GetWidth = function() return 16 end
          AGPS_ICON.GetHeight = function() return 16 end
          AGPS_AREA = CreateFrame("Frame", nil, child) -- (an area over the map: where the pointer is)
          AGPS_AREA.GetCenter = function() return 400, 300 end
          AGPS_AREA.GetEffectiveScale = function() return 1 end
          AGPS_AREA.GetWidth = function() return 500 end
          AGPS_AREA.GetHeight = function() return 500 end
          AGPS_OURS = CreateFrame("Frame", nil, AzerothGPSFrame)
          AGPS_CANVAS_ES, AGPS_CCX, AGPS_CCY = nil, nil, nil
        """)
        g = lua.globals()
        n = lambda: lua.eval("#AGPS_ADDS")  # noqa: E731
        spot = G.WorldMapIconSpot
        g.AGPS_FOCUS = g.AGPS_ICON
        assert G.WorldMapIconDown("LeftButton") is False and n() == 0  # (one click: the icon's own)
        g.AGPS_NOW = 100.2
        assert G.WorldMapIconDown("LeftButton") is True and n() == 1  # (the second: a stop at the icon's middle)
        dx, dy = spot(g.AGPS_ICON)
        assert lua.eval("AGPS_ADDS[1][1]") == pytest.approx(dx) and lua.eval("AGPS_ADDS[1][2]") == pytest.approx(dy)
        ax, ay = spot(g.AGPS_AREA)
        assert (ax, ay) != (dx, dy) and ax - dx == pytest.approx((321 - 400) * (ax - dx) / (321 - 400))
        # (too slow, another button, another icon between: not a double-click)
        g.AGPS_NOW = 101
        assert G.WorldMapIconDown("LeftButton") is False
        g.AGPS_NOW = 102
        assert G.WorldMapIconDown("LeftButton") is False
        g.AGPS_NOW = 102.1
        assert G.WorldMapIconDown("RightButton") is False
        g.AGPS_FOCUS = g.AGPS_AREA
        assert G.WorldMapIconDown("LeftButton") is False and n() == 1
        # (the map's own frames and anything outside the game's map: never)
        assert spot(g.AGPS_OURS) is None and spot(lua.eval("UIParent")) is None and spot(None) is None
        g.AGPS_FOCUS = g.AGPS_OURS
        assert G.WorldMapIconDown("LeftButton") is False
        g.AGPS_NOW = 102.2
        assert G.WorldMapIconDown("LeftButton") is False and n() == 1
        # (the import button: left of the game's own button in that corner, back in its corner outside)
        lua.execute("AGPS_NS.GPS.mapButtons.import.SetPoint = function(_, _, x) AGPS_IMPORT_X = x end")
        G.ApplySettings()
        assert g.AGPS_IMPORT_X == -6 - G.WORLD_MAP_CORNER
        lua.globals().ToggleWorldMap()
        assert g.AGPS_IMPORT_X == -6
        lua.execute("AGPS_NS.GPS.mapButtons.import.SetPoint = nil AGPS_IMPORT_X = nil")
        g.AGPS_FOCUS = g.AGPS_ICON
        assert G.WorldMapIconDown("LeftButton") is False  # (the world map closed: nothing heard)
    finally:
        lua.execute("""
          AGPS_NS.GPS.AddPending, GetTime, GetMouseFoci, GetCursorPosition = AGPS_WAS.add, AGPS_WAS.time, AGPS_WAS.foci, AGPS_WAS.cur
          AGPS_ADDS, AGPS_WAS, AGPS_ICON, AGPS_AREA, AGPS_OURS, AGPS_FOCUS = nil, nil, nil, nil, nil, nil
        """)


def test_the_games_map_is_kept_under_ours_on_a_land_with_no_continent_map(wm):
    # (seen in game 2026-11-11: "on Zephras Isle using in game map it has this permanent static image that follows the
    # player's position on map pan": Zephras Isle has zones only, and the game's map was never moved under ours there)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      local box = WorldMapFrame.ScrollContainer
      box.Child = NewWidget("Frame", "AGPSTestWorldMapChild2")
      box.Child.GetWidth = function() return 1002 end
      box.Child.GetHeight = function() return 668 end
      AGPS_WMS = { maps = {}, zooms = {} }
      box.InstantPanAndZoom = function(_, sc, u, v, raw) table.insert(AGPS_WMS.zooms, { sc, u, v, raw }) end
      box.SetHorizontalScroll = function(_, h) AGPS_WMS.h = h end
      box.SetVerticalScroll = function(_, v) AGPS_WMS.v = v end
      box.GetHorizontalScroll = function() return AGPS_WMS.h end box.GetVerticalScroll = function() return AGPS_WMS.v end
      WorldMapFrame.GetMapID = function() return AGPS_WMS.map end
      WorldMapFrame.SetMapID = function(_, id) AGPS_WMS.map = id table.insert(AGPS_WMS.maps, id) end
    """)
    st.useWorldMap = True
    G.ApplySettings()
    try:
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
        assert G.ContinentMap(2991) is None
        b = list(ns.Maps[2521].bounds.values())
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        for zoom in (300.0, 9000.0):  # (close in, and zoomed far out: no continent's map to go to)
            G.LookAt(2991, cx, cy, zoom)
            G.Update(True)
            assert G.WorldMapSync() is True
            m = ns.Maps[lua.eval("AGPS_WMS.map")]
            assert m.continent == 2991 and m.type == 3
            mb = list(m.bounds.values())
            sc = lua.eval("AGPS_WMS.zooms[#AGPS_WMS.zooms][1]")
            assert sc == pytest.approx(G.ViewState()[4] * (mb[3] - mb[1]) / 1002)
        # the game's own map of the isle, when it shows one already: kept
        lua.execute("AGPS_WMS.map = 2665")
        G.wmState.mapID = 2665
        G.LookAt(2991, cx + 50, cy, 300.0)
        G.Update(True)
        G.WorldMapSync()
        assert lua.eval("AGPS_WMS.map") == 2665
    finally:
        lua.execute("""
          local box = WorldMapFrame.ScrollContainer
          box.Child, box.InstantPanAndZoom, box.SetHorizontalScroll, box.SetVerticalScroll, box.GetHorizontalScroll, box.GetVerticalScroll = nil
          WorldMapFrame.GetMapID, WorldMapFrame.SetMapID = nil
        """)
        lua.execute("WorldMapFrame:Hide()")
        G.WorldMapChanged()


def test_in_the_world_map_the_map_neither_fades_nor_goes_click_through(wm):
    # (asked 2026-11-12: "the opacity settings, turn with me, etc is for the GPS map only not if using the in game map")
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    saved = (st.useWorldMap, st.fadeMoving, st.clickThroughMoving, st.clickThroughCombat)
    st.fadeMoving, st.clickThroughMoving, st.clickThroughCombat = True, True, True
    try:
        st.useWorldMap = False
        G.ApplySettings()
        assert G.MapFades() is True and G.ClickThroughWanted(st, True, True) is True
        st.useWorldMap = True
        G.ApplySettings()
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
        assert G.MapFades() is False and G.ClickThroughWanted(st, True, True) is False
    finally:
        st.useWorldMap, st.fadeMoving, st.clickThroughMoving, st.clickThroughCombat = saved
        lua.execute("WorldMapFrame:Hide()")
        G.WorldMapChanged()
        G.ApplySettings()


def test_in_a_fight_the_logo_and_key_open_the_maps_own_window_not_the_world_map(wm):
    # (seen in game 2026-11-12: with the world map option, the logo or the key in combat said "Interface action failed
    # because of an AddOn" and nothing opened: the game doesn't let an addon open its world map in a fight)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    saved = (st.useWorldMap, st.shown)
    lua.execute("AGPS_TOGGLES = 0")  # (the fixture's ToggleWorldMap counts them)
    st.useWorldMap, st.shown = True, True
    G.ApplySettings()
    try:
        lua.execute("InCombatLockdown = function() return true end")
        assert G.ToggleWorldMap() is False
        lua.globals().AzerothGPS_ToggleMap()  # (the key)
        assert lua.eval("AGPS_TOGGLES") == 0 and not G.WorldMapHosted()
        assert G.wmState.own and lua.eval("AzerothGPSFrame._shown")  # (its own window for the fight)
        lua.globals().AzerothGPS_ToggleMap()
        assert not G.wmState.own and not lua.eval("AzerothGPSFrame._shown")
        lua.globals().AzerothGPS_ToggleMap()
        assert G.wmState.own
        # out of the fight the key opens the world map again, the map in it, its own window let go
        lua.execute("InCombatLockdown = function() return false end")
        lua.globals().AzerothGPS_ToggleMap()
        assert lua.eval("AGPS_TOGGLES") == 1 and G.WorldMapHosted() and not G.wmState.own
    finally:
        lua.execute("InCombatLockdown = function() return false end")
        lua.execute("WorldMapFrame:Hide()")
        G.WorldMapChanged()
        st.useWorldMap, st.shown = saved
        G.wmState.own = None
        G.ApplySettings()


def test_the_world_maps_opening_is_in_the_debug_export_with_the_log_off(wm):
    # (2026-11-13: the first open after a /reload drew zoomed in, the art alone, no route; it happens before anyone
    # could tick Debug log, so the world map's opening and its next redraws are kept from login: ns.Debug.Keep)
    lua, ns = wm
    G, st, D = ns.GPS, ns.settings.gps, ns.Debug
    st.useWorldMap = True
    G.ApplySettings()
    assert not D.On()
    try:
        lua.globals().ToggleWorldMap()
        G.Update()
        text = str(D.Text())
        assert "since login (" in text and "world map open" in text and "redraw in the world map" in text
        assert "hosted=true" in text and "wmSize=700x460" in text
        assert len(D.log) == 0 or not D.On()  # (the log itself: still only while ticked)
    finally:
        lua.globals().ToggleWorldMap()
        st.useWorldMap = False
        G.ApplySettings()



def test_the_world_map_loaded_after_the_addon_is_hooked_as_it_loads(wm):
    # (2026-11-13: the game loads its world map when first needed; after a /reload WorldMapFrame wasn't there as
    # AzerothGPS started, its hooks were never made, and the first open was never set up: drawn zoomed in, the art
    # alone, no route. Tried again as addons load, as Route Here's are.)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.execute("AGPS_WMF = WorldMapFrame WorldMapFrame = nil")
    was = (G.wmHooked, G.wmEvents, G.wmTicker)
    G.wmHooked, G.wmEvents, G.wmTicker = None, None, None
    try:
        G.InitWorldMapHost()
        assert not G.wmHooked and G.wmEvents is not None
        lua.execute("WorldMapFrame = AGPS_WMF")
        G.wmEvents._scripts.OnEvent(G.wmEvents, "ADDON_LOADED", "Blizzard_WorldMap")
        assert G.wmHooked and G.wmTicker is not None
        lua.execute("WorldMapFrame:Show() WorldMapFrame._scripts.OnShow(WorldMapFrame)")  # (its OnShow, as the game runs it)
        assert G.WorldMapHosted() and G.wmTicker._shown, "the open was not set up"
        assert "world map open" in str(ns.Debug.Text())
    finally:
        lua.execute("WorldMapFrame = AGPS_WMF WorldMapFrame:Hide()")
        G.WorldMapChanged()
        G.wmHooked, G.wmEvents, G.wmTicker = was
        st.useWorldMap = False
        G.ApplySettings()



def test_the_world_maps_level_pass_sets_only_frames_not_at_their_level(wm):
    # (reported 2026-11-13, 30% CPU spikes: the world map's tick goes over every frame in the map once a second; setting
    # each one's level again, the game passing it down to its children, cost the most, though nothing had changed)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()
    try:
        assert G.WorldMapHosted()
        lua.execute("AGPS_T = AGPS_T + 2")
        G.WorldMapTick()  # (settled: every frame at its level)
        lua.execute("AGPS_LEVEL_SETS = 0")
        canvas = G.Canvas()
        lua.execute("""
          AGPS_COUNT_SETS = function(f) local set = f.SetFrameLevel
            f.GetFrameLevel = function(self) return self._level or 5 end -- (the stand-in's: the level it was given)
            f.SetFrameLevel = function(self, l) AGPS_LEVEL_SETS = AGPS_LEVEL_SETS + 1 return set(self, l) end end
        """)
        lua.eval("AGPS_COUNT_SETS")(canvas)
        lua.eval("AGPS_COUNT_SETS")(lua.eval("AzerothGPSFrame"))
        lua.execute("AGPS_T = AGPS_T + 2")
        G.WorldMapTick()  # (the levels they report now: set once)
        lua.execute("AGPS_LEVEL_SETS = 0 AGPS_T = AGPS_T + 2")
        G.WorldMapTick()
        assert lua.eval("AGPS_LEVEL_SETS") == 0
        canvas.SetFrameLevel(canvas, 3)  # (a frame moved by something else: put back)
        lua.execute("AGPS_LEVEL_SETS = 0 AGPS_T = AGPS_T + 2")
        G.WorldMapTick()
        assert lua.eval("AGPS_LEVEL_SETS") == 1 and canvas._level != 3
    finally:
        lua.globals().AzerothGPS_ToggleMap()
        st.useWorldMap = False
        G.ApplySettings()


def test_the_games_own_quest_areas_are_unseen_under_ours_in_the_world_map(wm):
    # (reported 2026-11-14: in the world map the quest areas were too dark: the game's own filled areas, map icons over
    # ours, with ours under them) unseen while ours are drawn; seen with ours off and once the world map is closed
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_BLOB = { a = 1 }
      function AGPS_BLOB:SetAlpha(a) self.a = a end
      function AGPS_BLOB:GetAlpha() return self.a end
      WorldMapFrame.EnumeratePinsByTemplate = function(_, tmpl)
        local done = tmpl ~= "QuestBlobPinTemplate"
        return function() if done then return nil end done = true return AGPS_BLOB end
      end
    """)
    alpha = lambda: lua.eval("AGPS_BLOB:GetAlpha()")  # noqa: E731
    was = (st.layerQuests, st.layerQuestAreas)
    try:
        st.useWorldMap, st.layerQuests, st.layerQuestAreas = True, True, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        G.WorldMapArtPins(False)
        assert alpha() == 0
        st.layerQuestAreas = False  # (ours off: the game's own back, at the next look)
        G.wmState.artPinsAt = None
        G.WorldMapTick()
        assert alpha() == 1
        st.layerQuestAreas = True
        G.wmState.artPinsAt = None
        G.WorldMapTick()
        assert alpha() == 0
        lua.globals().AzerothGPS_ToggleMap()  # (closed: the game's map as it was)
        assert not G.WorldMapHosted() and alpha() == 1
    finally:
        st.layerQuests, st.layerQuestAreas = was
        lua.execute("WorldMapFrame.EnumeratePinsByTemplate = nil")


def test_agps_show_hide_toggle_open_out_the_map_as_the_minimap(wm):
    # (asked 2026-11-15: "what is the command to open the map? this should also work in minimap mode": /agps toggle
    # only flipped the window's setting, which the map as the minimap ignores)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    slash = lua.globals().SlashCmdList.AZEROTHGPS
    st.useWorldMap, st.replaceMinimap = False, True
    G.ApplySettings()
    assert G.mmState.on and not G.mmState.expanded
    slash("toggle")
    assert G.mmState.expanded and st.shown
    slash("toggle")
    assert not G.mmState.expanded and st.shown  # (back to the square, never hidden)
    slash("show")
    slash("show")
    assert G.mmState.expanded
    slash("hide")
    assert not G.mmState.expanded and st.shown
    st.replaceMinimap = False
    G.ApplySettings()


def test_agps_show_hide_toggle_open_the_world_map_with_the_map_in_it(wm):
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    slash = lua.globals().SlashCmdList.AZEROTHGPS
    st.useWorldMap, st.replaceMinimap = True, False
    G.ApplySettings()
    assert not G.WorldMapHosted()
    slash("toggle")
    assert G.WorldMapHosted()
    slash("show")
    assert G.WorldMapHosted()  # (open already: left open)
    slash("hide")
    assert not G.WorldMapHosted()
    slash("hide")
    assert not G.WorldMapHosted()
    slash("show")
    assert G.WorldMapHosted()
    slash("toggle")
    assert not G.WorldMapHosted()


def test_a_question_on_the_map_in_the_world_map_takes_clicks(wm):
    # (2026-11-15: in the game's world map window "I get a popup I can't actually click yes or no": the question was
    # put on the map, which sits under the world map's own icons and canvas there; over everything now)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()
    assert G.WorldMapHosted()
    box = G.Ask("AzerothGPSTestAsk", "Keep this route?", "Yes", "No", lua.eval("function() end"), lua.eval("function() end"))
    assert box is not None
    assert box.GetFrameStrata(box) == ns.POPUP_OVER_STRATA, box.GetFrameStrata(box)
    assert not box.onMap
    box.Hide(box)

def test_in_a_city_the_world_map_shows_its_inside_map_as_the_gps_window_does(wm):
    # (a player's screenshot 2026-11-16: in Ironforge's Forlorn Cavern, the GPS map in the game's world map showed Dun
    # Morogh's snow with the city's names over the mountain, the minimap square the city's map. The game's map went to
    # Ironforge (its own: the player's map, a subzone changed), taken for a map picked in its bar, and ours looked at
    # the whole of Ironforge's rectangle, zoomed out past its inside map.) Both maps, the same: the city's map
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      local box = WorldMapFrame.ScrollContainer
      box.Child = NewWidget("Frame", "AGPSTestWorldMapChild")
      box.Child.GetWidth = function() return 1002 end
      box.Child.GetHeight = function() return 668 end
      AGPS_WMS = { maps = {}, zooms = {} }
      box.InstantPanAndZoom = function(_, sc, u, v, raw) table.insert(AGPS_WMS.zooms, { sc, u, v, raw }) end
      box.SetHorizontalScroll = function(_, h) AGPS_WMS.h = h end
      box.SetVerticalScroll = function(_, v) AGPS_WMS.v = v end
      box.GetHorizontalScroll = function() return AGPS_WMS.h end box.GetVerticalScroll = function() return AGPS_WMS.v end
      WorldMapFrame.GetMapID = function() return AGPS_WMS.map end
      WorldMapFrame.SetMapID = function(_, id) AGPS_WMS.map = id table.insert(AGPS_WMS.maps, id) end
      AGPS_INDOORS_REAL = IsIndoors
      IsIndoors = function() return true end
      AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -4840.0, -1100.0, 0
      -- (the game's own answer for a spot in Ironforge on the continent's map: its zone, Dun Morogh)
      AGPS_CMAP = C_Map
      C_Map = setmetatable({ GetMapInfoAtPosition = function() return { mapID = 1426, mapType = 3 } end },
        { __index = AGPS_CMAP })
    """)
    zoom = st.zoom
    st.useWorldMap, st.zoom = True, 200.0
    G.ApplySettings()
    try:
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
        G.Follow()
        G.Update(True)
        G.WorldMapSync()
        G.Update(True)
        assert G.inside is not None  # (the city's map, on the player)
        assert lua.eval("AGPS_WMS.map") == 1455  # (the game's map Ironforge's too: its icons line up)
        # the game going to the player's own map, Ironforge (a subzone changed), or Ironforge picked in its bar
        lua.execute("AGPS_WMS.map = 1455")
        G.WorldMapSync()
        G.Update(True)
        assert G.inside is not None and not G.IsFree()  # (still the city's map, on the player)
        # Undercity picked in the bar, the player in Ironforge: looked at close enough for its whole map
        lua.execute("AGPS_WMS.map = 1458")
        G.WorldMapSync()
        G.Update(True)
        x, y = G.ViewState()[0], G.ViewState()[1]
        assert 1237 <= x <= 1878 and -87 <= y <= 874
        assert G.viewZoom <= G.CITY_MAX_ZOOM * (G.ZoomScale() or 1) + 1e-6
    finally:
        st.zoom = zoom
        lua.execute("""
          local box = WorldMapFrame.ScrollContainer
          box.Child, box.InstantPanAndZoom, box.SetHorizontalScroll, box.SetVerticalScroll, box.GetHorizontalScroll, box.GetVerticalScroll = nil
          WorldMapFrame.GetMapID, WorldMapFrame.SetMapID = nil
          IsIndoors = AGPS_INDOORS_REAL AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0
          C_Map = AGPS_CMAP
        """)
        lua.execute("WorldMapFrame:Hide()")
        G.WorldMapChanged()
        G.Follow()


def test_in_a_dungeon_the_map_shows_in_the_world_map_with_the_square_the_games_minimap(wm):
    # (seen in game 2026-11-16, 1.3.4: "replace minimap" on, the map in the world map, in the Stockade: the world map
    # black, only the panel's text and buttons; the canvas hidden for the square stayed hidden in the world map)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    lua.execute("AGPS_III = IsInInstance IsInInstance = function() return true, 'party' end")
    keep = st.replaceMinimapKeepSquare
    st.useWorldMap, st.replaceMinimap, st.replaceMinimapKeepSquare = True, True, True
    canvas = G.Canvas()
    try:
        G.ApplySettings()
        assert G.MinimapAway() and G.mmState.awayIn and canvas._shown is False  # (the square: the game's minimap)
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted() and canvas._shown is not False  # (the dungeon's map in the world map)
        G.ApplySettings()
        assert canvas._shown is not False
        lua.globals().ToggleWorldMap()
        assert not G.WorldMapHosted() and canvas._shown is False  # (closed: the square the game's minimap again)
    finally:
        lua.execute("IsInInstance = AGPS_III AGPS_III = nil")
        st.replaceMinimapKeepSquare = keep


def test_escape_can_be_kept_from_closing_the_world_map(wm):
    # (asked 2026-11-20: "Esc by default closes the map, add an option for disabling this". Off: a keyboard frame, shown
    # only while the GPS map is in the open world map, eats Escape and passes every other key; never in combat)
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    was = st.escClosesMap
    assert ns.DEFAULTS.gps.escClosesMap is True
    lua.execute("""
      AGPS_PROP = {}
      AGPS_REAL_ICL = InCombatLockdown
    """)
    try:
        st.useWorldMap = True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        c = G.escCatcher
        assert c is None or not c._shown  # (on by default: the game's Escape as it is)
        st.escClosesMap = False
        G.ApplySettings()
        c = G.escCatcher
        assert c is not None and c._shown
        c.SetPropagateKeyboardInput = lua.eval("function(s, v) AGPS_PROP[#AGPS_PROP + 1] = v end")
        c._scripts.OnKeyDown(c, "ESCAPE")
        c._scripts.OnKeyDown(c, "W")
        assert list(lua.eval("AGPS_PROP").values()) == [False, True]  # (Escape eaten, W passed on)
        # a fight: hidden, Escape closes it as usual; back after
        lua.execute("InCombatLockdown = function() return true end")
        c._scripts.OnEvent(c, "PLAYER_REGEN_DISABLED")
        assert not c._shown
        lua.execute("InCombatLockdown = AGPS_REAL_ICL")
        c._scripts.OnEvent(c, "PLAYER_REGEN_ENABLED")
        assert c._shown
        # the world map closed: gone
        lua.globals().AzerothGPS_ToggleMap()
        assert not G.WorldMapHosted() and not c._shown
    finally:
        lua.execute("InCombatLockdown = AGPS_REAL_ICL")
        st.escClosesMap = was
