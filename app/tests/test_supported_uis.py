"""Other addons the GPS map works with (1.4.2, Kooki3z): a full UI replacement's own square minimap (DaylightUI's Info
Panel, EllesmereUI's Minimap) detected, the minimap square's border then hidden by itself until the player sets it;
OpenMap installed and the GPS map put in the game's world map, the No Map style picked for them and the style before it
back when that's turned off; and Waypoint UI given the route's next stop as its waypoint, never over one of the
player's own. Every other addon here is a stand-in for the API it has (read from its files)."""

import pytest

from test_map_redraw import game, minimap, _expand_setup, MM_SETUP  # noqa: F401
from test_no_map_style import nomap, OPENMAP  # noqa: F401
from test_world_map_host import wm  # noqa: F401

# DaylightUI 2.4.1 (its API.lua: DaylightUI.API, read only; its Info Panel's minimap squares the minimap, says so with
# GetMinimapShape and puts it top left in its panel) and EllesmereUI's Minimap module, as loaded addons.
LOADED = """
  AGPS_LOADED = {}
  AGPS_OLD_LOADED, AGPS_OLD_LOADED2 = C_AddOns.IsAddOnLoaded, IsAddOnLoaded
  C_AddOns.IsAddOnLoaded = function(name) return AGPS_LOADED[name] == true end
  IsAddOnLoaded = C_AddOns.IsAddOnLoaded
"""
DAYLIGHT = """
  AGPS_LOADED.DaylightUI, AGPS_LOADED.DaylightUI_InfoPanel = true, true
  AGPS_DUI = { modules = { InfoPanel = true }, map = true }
  DaylightUI = { API = {
    IsModuleEnabled = function(name) return AGPS_DUI.modules[name] == true end,
    GetSetting = function(scope, path)
      if scope == "InfoPanel" and AGPS_DUI.modules.InfoPanel and path == "map.enabled" then return AGPS_DUI.map end
    end,
  } }
  AGPS_OLD_SHAPE = GetMinimapShape
  GetMinimapShape = function() return "SQUARE" end
"""
UNDO = """
  C_AddOns.IsAddOnLoaded, IsAddOnLoaded = AGPS_OLD_LOADED, AGPS_OLD_LOADED2
  DaylightUI = nil
  if AGPS_OLD_SHAPE ~= nil or GetMinimapShape ~= nil then GetMinimapShape = AGPS_OLD_SHAPE end
"""
CHROME = """
  AGPS_CH = CreateFrame("Frame", nil, AzerothGPSFrame)
  AGPS_CH.NineSlice = CreateFrame("Frame", nil, AGPS_CH)
  AGPS_CH.TitleContainer = CreateFrame("Frame", nil, AGPS_CH)
  AGPS_CH.SetBorder = function(s, layout) s._border = layout; s.NineSlice:Show() end
"""


@pytest.fixture
def uis(minimap):  # noqa: F811
    lua, ns = minimap
    st = ns.settings.gps
    lua.execute("AGPS_OLD_SHAPE = GetMinimapShape")
    lua.execute(LOADED)
    yield lua, ns
    lua.execute(UNDO)
    st.replaceMinimapNoBorder = False


def _border_check(ns):
    O = ns.Options
    O.Show()
    O.ShowPage("Minimap")
    cb = next(c.control for c in O.settingControls.values() if c.key == "replaceMinimapNoBorder")
    O.Refresh()
    return cb


def test_daylightuis_minimap_takes_the_square_border_away_whatever_the_option_says(uis):
    # (Kooki3z 2026-11-27, his screenshot of DaylightUI's: "maybe just remove the boarder all together when one of these
    # UIs are enabled": no border, edge or frame of ours round the square; the option grayed with a note, and the
    # player's own setting back as it was without that UI)
    lua, ns = uis
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    _expand_setup(lua)
    lua.execute(CHROME)
    lua.execute("AzerothGPSFrame.SetBackdropBorderColor = function(s, r, g, b, a) s._edgeA = a end "
                "AzerothGPSFrame.SetBackdropColor = function(s, r, g, b, a) s._groundA = a end")
    G.chrome = lua.eval("AGPS_CH")
    ch = G.chrome
    f = lua.eval("AzerothGPSFrame")
    try:
        st.replaceMinimapNoBorder = False
        st.replaceMinimap = True
        G.ApplySettings()
        # (no other UI: the border and our frame's edge show, as before)
        assert G.SupportedMinimapUI() is None and ch.NineSlice._shown and not G.SquareBare()
        assert f._edgeA > 0 and f._groundA > 0
        for picked in (False, True):
            st.replaceMinimapNoBorder = picked
            lua.execute(DAYLIGHT)
            G.ApplySettings()
            assert G.SupportedMinimapUI() == "DaylightUI" and G.SquareHidesBorder() and G.SquareBare()
            # (none of ours round it: the metal border, our frame's own edge and ground)
            assert ch.NineSlice._shown is False and f._edgeA == 0 and f._groundA == 0
            assert st.replaceMinimapNoBorder is picked  # (the setting itself untouched)
            cb = _border_check(ns)
            assert cb.GetChecked(cb) is True and cb.agpsOn is False  # (what's shown, grayed)
            O.Toggle()
            # DaylightUI's minimap turned off in it: the player's own setting again
            lua.execute("AGPS_DUI.map = false")
            G.ApplySettings()
            assert G.SupportedMinimapUI() is None and not G.SquareBare()
            assert (ch.NineSlice._shown is False) is picked and G.SquareHidesBorder() is picked
            cb = _border_check(ns)
            assert cb.agpsOn is True and cb.GetChecked(cb) is picked
            O.Toggle()
            lua.execute("DaylightUI = nil AGPS_LOADED = {}")
    finally:
        st.replaceMinimap, st.replaceMinimapNoBorder = False, False
        G.ApplySettings()
        G.chrome, G.mmChromeCompact = None, None


def test_ellesmereuis_minimap_counts_too(uis):
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    st.replaceMinimapNoBorder = False
    assert G.SupportedMinimapUI() is None and not G.SquareHidesBorder()
    lua.execute("AGPS_LOADED.EllesmereUI = true")
    assert G.SupportedMinimapUI() is None  # (its core alone: not its minimap)
    lua.execute("AGPS_LOADED.EllesmereUIMinimap = true")
    assert G.SupportedMinimapUI() == "EllesmereUI" and G.SquareHidesBorder()
    st.replaceMinimapNoBorder = False  # (the player's own setting, the border on: none all the same, theirs kept)
    assert G.SquareHidesBorder() and st.replaceMinimapNoBorder is False


def test_daylightuis_minimap_is_square_and_the_square_follows_it_into_its_panel(uis):
    # (its Info Panel puts the minimap at its panel's top left, sized its own, and puts it back there after the game's
    # layout passes; the square goes where it is, and its addon buttons' drawer has ours to place)
    lua, ns = uis
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    lua.execute(DAYLIGHT)
    # the game's own minimap (no square): square, by DaylightUI's word; our route and button go by it
    assert G.MinimapSquare()
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        m = G.mmState
        assert m.on and m.applied
        lua.execute("""
          AGPS_PANEL = CreateFrame("Frame", "DaylightUIInfoPanelBody", UIParent)
          AGPS_PANEL:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -4, -4)
          AGPS_PANEL:SetSize(240, 300)
          Minimap._parent = AGPS_PANEL
          Minimap:ClearAllPoints()
          Minimap:SetPoint("TOPLEFT", AGPS_PANEL, "TOPLEFT", 0, 0)
        """)
        m.moves = None
        assert G.OnMinimapMoved() is True
        assert lua.eval("rawequal")(m.home.parent, lua.eval("AGPS_PANEL"))
        # the Minimap back on the square's anchor, DaylightUI's place kept to give back
        pts = lua.eval("function() local t = {} for k, p in pairs(Minimap._pts) do t[#t + 1] = p end return t end")()
        assert len(pts) == 1 and lua.eval("rawequal")(pts[1][2], G.mmAnchor)
        assert m.was.points[1][1] == "TOPLEFT" and lua.eval("rawequal")(m.was.points[1][2], lua.eval("AGPS_PANEL"))
        # our minimap button in its drawer (another parent): left where the drawer puts it
        b = O.button
        if b is not None:
            lua.globals().AGPS_B = b
            lua.execute("AGPS_DRAWER = CreateFrame('Frame', nil, UIParent) AGPS_B:SetParent(AGPS_DRAWER)")
            assert not O.ButtonOwned()
            lua.execute("AGPS_B:SetParent(Minimap)")
    finally:
        st.replaceMinimap = False
        G.ApplySettings()


# ---------------------------------------------------------------------------- OpenMap: No Map with the world map


@pytest.fixture
def chat(nomap):  # noqa: F811
    lua, ns = nomap
    st = ns.settings.gps
    was = {k: st[k] for k in ("useWorldMap", "noMapAuto")}
    lua.execute("""
      AGPS_CHAT = {}
      AGPS_OLD_CHAT = DEFAULT_CHAT_FRAME
      DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) table.insert(AGPS_CHAT, m) end }
    """)
    yield lua, ns
    lua.execute("DEFAULT_CHAT_FRAME = AGPS_OLD_CHAT")
    for k, v in was.items():
        st[k] = v
    ns.GPS.ApplySettings()


def _said(lua):
    return [str(m) for m in lua.eval("AGPS_CHAT").values()]


def _world_map_box(ns):
    O = ns.Options
    O.Show()
    O.ShowPage("Map")
    return next(c.control for c in O.settingControls.values() if c.key == "useWorldMap")


def _tick(ns, cb, on):
    cb.SetChecked(cb, on)
    cb._scripts.OnClick(cb)
    ns.Options.Apply()


def test_with_openmap_the_world_map_option_turns_on_no_map_and_back(chat):
    lua, ns = chat
    G, st = ns.GPS, ns.settings.gps
    lua.execute(OPENMAP)
    G.SetStyle("zone")
    st.useWorldMap = False
    G.ApplySettings()
    cb = _world_map_box(ns)
    _tick(ns, cb, True)
    assert st.useWorldMap is True and st.style == "none" and st.styleBeforeNone == "zone" and st.noMapAuto is True
    said = [m for m in _said(lua) if "No Map" in m]
    assert len(said) == 1 and "OpenMap" in said[0]
    # off again: the style before it, the setting itself too
    _tick(ns, cb, False)
    assert st.useWorldMap is False and st.style == "zone" and not st.noMapAuto
    # on again: No Map again, said again
    _tick(ns, cb, True)
    assert st.style == "none" and len([m for m in _said(lua) if "No Map" in m]) == 2
    # another style picked meanwhile: theirs, kept when the option goes off
    assert G.SetStyle("nospoiler") and not st.noMapAuto
    _tick(ns, cb, False)
    assert st.style == "nospoiler"
    # No Map picked by the player: stays their setting (the style before it is what shows out of the world map)
    st.useWorldMap = True
    G.ApplySettings()
    assert G.SetStyle("none")
    _tick(ns, cb, False)
    assert st.style == "none" and G.Style() == "nospoiler"
    ns.Options.Toggle()


def test_with_openmap_the_setup_card_turns_on_no_map_and_its_skip_puts_the_style_back(chat):
    lua, ns = chat
    G, st, S = ns.GPS, ns.settings.gps, ns.Setup
    lua.execute(OPENMAP)
    G.SetStyle("minimap")
    st.useWorldMap = False
    G.ApplySettings()
    S.open = True  # (the window's own state: only Pick's part of it here)
    try:
        assert S.Pick("useWorldMap", True)
        assert st.style == "none" and st.noMapAuto is True
        S.Pick("useWorldMap", True)  # (the same card again: nothing more said)
        assert len([m for m in _said(lua) if "No Map" in m]) == 1
    finally:
        S.open = None
    # (the setup's Skip puts the option back as it was: the style with it)
    st.useWorldMap = False
    G.ApplySettings()
    assert st.style == "minimap" and not st.noMapAuto


def test_without_openmap_the_world_map_option_leaves_the_style(chat):
    lua, ns = chat
    G, st = ns.GPS, ns.settings.gps
    G.SetStyle("zone")
    st.useWorldMap = False
    G.ApplySettings()
    assert not G.OpenMapInstalled()
    cb = _world_map_box(ns)
    _tick(ns, cb, True)
    assert st.useWorldMap is True and st.style == "zone" and not st.noMapAuto
    assert not [m for m in _said(lua) if "No Map" in m]
    _tick(ns, cb, False)
    ns.Options.Toggle()


def test_options_map_style_tells_openmap_players_to_pick_no_map(chat):
    # (Kooki3z 2026-11-27: "make it more clear that No Map is what players want to use when using openmap": a note at the
    # top of Options > Map > Map style, only with the OpenMap addon installed, its space closed up without it; No Map's
    # own tip and note name OpenMap; our own style called OpenMap is said to be AzerothGPS's, not the addon)
    lua, ns = chat
    O, G, st = ns.Options, ns.GPS, ns.settings.gps
    O.Show()
    O.ShowPage("Map")
    nt = O.openMapNote
    dd = next(c.control for c in O.settingControls.values() if c.key == "style")
    was = st.useWorldMap
    try:
        st.useWorldMap = True
        G.ApplySettings()
        O.Refresh()
        assert not G.OpenMapInstalled()
        assert nt._shown is False
        y_without = dd._pt[3]
        lua.execute(OPENMAP)
        assert G.OpenMapInstalled()
        O.Refresh()
        assert nt._shown is True and dd._pt[3] < y_without  # (the list below it moved down to make room)
        text = str(nt._text)
        assert "OpenMap addon" in text and "No Map" in text and "Show the GPS map in the game's world map" in text
        assert len(text) <= 160  # (shortened for 1.4.2: Kooki3z, "shorten it")
        # No Map's tip in the list, and its note under the list, name OpenMap as the case for it
        tip = next(o.tip for o in O.styleChoices.values() if o.value == "none")
        assert "OpenMap" in str(tip)
        notes = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString"]
        assert any(t.startswith("No Map (with") and "OpenMap" in t for t in notes)
        assert any(t.startswith("OpenMap (the default, AzerothGPS's own style, not the OpenMap addon)") for t in notes)
        lua.execute("OpenMapAPI = nil")
        O.Refresh()
        assert nt._shown is False and dd._pt[3] == y_without
    finally:
        lua.execute("OpenMapAPI = nil")
        st.useWorldMap = was
        G.ApplySettings()
        O.Refresh()
        O.Toggle()


# ---------------------------------------------------------------------------- Waypoint UI: the next stop


# Waypoint UI 1.7.5's navigation API (its API.lua: WaypointUIAPI.Navigation), and the game's waypoint and
# super-tracking it sets through it, recorded.
WAYPOINTUI = """
  AGPS_WUI = { nav = nil, made = {}, cleared = 0, game = nil, tracked = nil }
  local function setGame(mapID, x, y)
    AGPS_WUI.game = mapID and { uiMapID = mapID, position = { x = x, y = y } } or nil
    AGPS_NS.Import.OnUserWaypoint() -- (USER_WAYPOINT_UPDATED, as the game fires it)
    AGPS_NS.WaypointUI.OnUserWaypoint()
  end
  AGPS_WUI.setGame = setGame
  WaypointUIAPI = { Navigation = {
    GetUserNavigation = function() return AGPS_WUI.nav end,
    IsUserNavigationFlagged = function(f) return AGPS_WUI.nav ~= nil and AGPS_WUI.nav.flags == f end,
    IsPathStepWaypointTracked = function() return AGPS_WUI.step == true end,
    NewUserNavigation = function(o)
      if not o.mapID or o.mapID == 0 then return nil end
      AGPS_WUI.nav = { name = o.name, mapID = o.mapID, x = o.x / 100, y = o.y / 100, flags = o.flags }
      table.insert(AGPS_WUI.made, o)
      setGame(o.mapID, o.x / 100, o.y / 100)
      return AGPS_WUI.nav
    end,
    ClearUserNavigation = function(preserveWaypoint)
      AGPS_WUI.cleared = AGPS_WUI.cleared + 1
      AGPS_WUI.nav = nil
      if not preserveWaypoint then setGame(nil) end -- (its own: the game's waypoint kept, the record dropped)
    end,
  } }
  AGPS_OLD_CMAP = { C_Map.HasUserWaypoint, C_Map.GetUserWaypoint, C_Map.SetUserWaypoint, C_Map.ClearUserWaypoint }
  C_Map.HasUserWaypoint = function() return AGPS_WUI.game ~= nil end
  C_Map.GetUserWaypoint = function() return AGPS_WUI.game end
  C_Map.SetUserWaypoint = function(p) AGPS_WUI.game = { uiMapID = p.uiMapID, position = p.position } end
  C_Map.ClearUserWaypoint = function() AGPS_WUI.game = nil end
  AGPS_OLD_ST = C_SuperTrack
  C_SuperTrack = {
    IsSuperTrackingAnything = function() return AGPS_WUI.tracked ~= nil end,
    IsSuperTrackingUserWaypoint = function() return AGPS_WUI.tracked == "waypoint" end,
  }
"""
WAYPOINTUI_UNDO = """
  WaypointUIAPI = nil
  C_Map.HasUserWaypoint, C_Map.GetUserWaypoint, C_Map.SetUserWaypoint, C_Map.ClearUserWaypoint = unpack(AGPS_OLD_CMAP)
  C_SuperTrack = AGPS_OLD_ST
"""
GALLOWS = "{ { x = 2204, y = 303, cont = 0, name = 'The Gallows' } }"
BRILL = "{ { x = 2250, y = 305, cont = 0, name = 'Brill' }, { x = 2204, y = 303, cont = 0, name = 'The Gallows' } }"


@pytest.fixture
def wui(game):  # noqa: F811
    lua, ns = game
    st = ns.settings.gps
    ns.Nav.Clear()
    lua.execute(WAYPOINTUI)
    ns.WaypointUI.fed = None
    ns.WaypointUI.seen = lua.table()
    ns.WaypointUI.ready = True
    yield lua, ns
    ns.Nav.Clear()
    lua.execute(WAYPOINTUI_UNDO)
    st.waypointUI = True
    st.waypointUIPins = True
    ns.WaypointUI.seen = lua.table()
    ns.WaypointUI.fed = None
    ns.CharDB().mapPin = None


def _made(lua):
    return [dict(o.items()) for o in lua.eval("AGPS_WUI.made").values()]


def test_waypoint_ui_gets_the_next_stop_and_moves_on_with_the_route(wui):
    lua, ns = wui
    W, N = ns.WaypointUI, ns.Nav
    assert W.Available() and W.On()
    assert W.Tick() is False and _made(lua) == []  # (no route: nothing)
    N.SetStops(lua.eval(BRILL), False, "red")
    assert W.Tick() is True
    made = _made(lua)
    assert len(made) == 1 and made[0]["name"] == "Brill" and made[0]["flags"] == W.FLAG and made[0]["suppressAudio"]
    mapID, u, v = ns.Import.MapPoint(0, 2250, 305)
    assert made[0]["mapID"] == mapID and made[0]["x"] == pytest.approx(u * 100) and made[0]["y"] == pytest.approx(v * 100)
    assert W.Ours()
    # the game's waypoint is ours: our map takes it for no pin of the player's
    assert ns.CharDB().mapPin is None
    # nothing changed: told nothing more
    assert W.Tick() is False and len(_made(lua)) == 1
    # Brill reached: the next stop
    N.RemoveStop(1)
    assert W.Tick() is True and _made(lua)[-1]["name"] == "The Gallows"
    # the route cleared: ours taken away
    N.Clear()
    assert W.Tick() is True and lua.eval("AGPS_WUI.cleared") == 1 and not W.Ours()
    assert lua.eval("AGPS_WUI.game") is None and ns.CharDB().mapPin is None
    assert W.Tick() is False


def test_waypoint_ui_never_replaces_the_players_own_waypoint_or_tracked_quest(wui):
    lua, ns = wui
    W, N = ns.WaypointUI, ns.Nav
    # the player's own in Waypoint UI (no flag of ours)
    lua.execute("AGPS_WUI.nav = { name = 'Mine', mapID = 18, x = 0.5, y = 0.5 }")
    N.SetStops(lua.eval(GALLOWS), False, "red")
    assert W.Tick() is False and _made(lua) == []
    N.Clear()
    assert W.Tick() is False and lua.eval("AGPS_WUI.cleared") == 0 and lua.eval("AGPS_WUI.nav.name") == "Mine"
    # the game's map pin of theirs (Ctrl-click on our map, the game's map): left too
    lua.execute("AGPS_WUI.nav = nil")
    ns.Import.SetMapPin(0, 2300, 320)
    assert ns.CharDB().mapPin is not None
    N.SetStops(lua.eval(GALLOWS), False, "red")
    assert W.Tick() is False and _made(lua) == []
    ns.Import.ClearMapPin()
    # a quest the game super-tracks: not taken over
    lua.execute("AGPS_WUI.tracked = 'quest'")
    assert W.Tick() is False and _made(lua) == []
    lua.execute("AGPS_WUI.tracked = nil")
    assert W.Tick() is True and len(_made(lua)) == 1
    # the player sets one of their own over ours: theirs from then on, never cleared by the route
    lua.execute("AGPS_WUI.nav = { name = 'Mine', mapID = 18, x = 0.4, y = 0.4 }")
    N.Clear()
    assert W.Tick() is False and lua.eval("AGPS_WUI.cleared") == 0


def test_waypoint_ui_option_off_takes_ours_away_and_without_the_addon_nothing_runs(wui):
    lua, ns = wui
    W, N, st = ns.WaypointUI, ns.Nav, ns.settings.gps
    N.SetStops(lua.eval(GALLOWS), False, "red")
    assert W.Tick() is True
    st.waypointUI = False
    assert not W.On() and W.Tick() is True and lua.eval("AGPS_WUI.cleared") == 1
    assert W.Tick() is False
    st.waypointUI = True
    assert W.Tick() is True
    # a stop no zone map has (a dungeon's): none of ours left on the last one
    lua.execute("AGPS_MP = AGPS_NS.Import.MapPoint AGPS_NS.Import.MapPoint = function() return nil end")
    try:
        assert W.Tick() is True and not W.Ours()
    finally:
        lua.execute("AGPS_NS.Import.MapPoint = AGPS_MP")
    # the option on the Directions page, gray without the addon
    O = ns.Options
    O.Show()
    O.ShowPage("Directions")
    c = next(c for c in O.settingControls.values() if c.key == "waypointUI")
    O.Refresh()
    assert c.control.agpsOn is True
    lua.execute("WaypointUIAPI = nil")
    O.Refresh()
    assert c.control.agpsOn is False
    assert not W.Available() and W.Tick() is False
    O.Toggle()


# ---------------------------------------------------------------------------- Waypoint UI: the player's pins as stops
# (Kooki3z for 1.4.2: "when user uses ctrl-click and sets a pin, auto add that as a stop as well": a Ctrl-click pin of
# Waypoint UI's (or the game's world map's) is the game's waypoint, USER_WAYPOINT_UPDATED; WaypointUI.lua's
# W.OnUserWaypoint)


def _pin(lua, ns, cont, x, y, step=False):
    """The player's Ctrl-click pin at a world spot, as Waypoint UI sets it: its own navigation (no flag of ours), then
    the game's waypoint and its event. `step`: one of its pathfinding's steps on the way instead."""
    mapID, u, v = ns.Import.MapPoint(cont, x, y)
    lua.execute("AGPS_WUI.step = %s" % ("true" if step else "false"))
    if not step:
        lua.eval("function(m, u, v) AGPS_WUI.nav = { name = 'Map Pin', mapID = m, x = u, y = v } end")(mapID, u, v)
    lua.eval("AGPS_WUI.setGame")(mapID, u, v)
    lua.execute("AGPS_WUI.step = false")


def _stops(ns):
    return [(d.name, d.x, d.y) for d in ns.Nav.stops.values()]


def _pin_said(lua):
    return [m for m in _said(lua) if "Waypoint UI pin added to your route" in m]


@pytest.fixture
def wuipins(wui):
    lua, ns = wui
    lua.execute("""
      AGPS_CHAT = {}
      AGPS_OLD_CHATFRAME = DEFAULT_CHAT_FRAME
      DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) table.insert(AGPS_CHAT, m) end }
    """)
    quiet = ns.settings.gps.quietChat
    ns.settings.gps.quietChat = False
    yield lua, ns
    ns.settings.gps.quietChat = quiet
    lua.execute("DEFAULT_CHAT_FRAME = AGPS_OLD_CHATFRAME")


def test_a_waypoint_ui_pin_starts_a_route_then_is_added_as_the_last_stop(wuipins):
    lua, ns = wuipins
    N, st = ns.Nav, ns.settings.gps
    assert len(N.stops) == 0
    _pin(lua, ns, 0, 2250, 305)  # (by Brill)
    stops = _stops(ns)
    assert len(stops) == 1 and stops[0][1] == pytest.approx(2250, abs=2) and stops[0][2] == pytest.approx(305, abs=2)
    assert stops[0][0].startswith("Map pin (")
    said = _pin_said(lua)
    assert len(said) == 1 and stops[0][0] in said[0]  # (said once, with the stop's name)
    # with a route going: the new pin is its last stop, not ordered in
    N.SetStops(lua.eval(BRILL), False, "red")
    fastest = st.fastestOrder
    st.fastestOrder = True
    try:
        _pin(lua, ns, 0, 2300, 320)
    finally:
        st.fastestOrder = fastest
    stops = _stops(ns)
    assert len(stops) == 3 and [s[0] for s in stops[:2]] == ["Brill", "The Gallows"]
    assert stops[2][1] == pytest.approx(2300, abs=2) and stops[2][2] == pytest.approx(320, abs=2)
    assert len(_pin_said(lua)) == 2
    # clearing the pin leaves the stop
    lua.execute("AGPS_WUI.nav = nil")
    lua.eval("AGPS_WUI.setGame")(None)
    assert len(N.stops) == 3


def test_our_own_waypoint_sent_to_waypoint_ui_never_comes_back_as_a_stop(wuipins):
    lua, ns = wuipins
    W, N = ns.WaypointUI, ns.Nav
    N.SetStops(lua.eval(BRILL), False, "red")
    assert W.Tick() is True  # (the next stop sent: the game's waypoint set, its event fired while we set it)
    assert len(N.stops) == 2 and _pin_said(lua) == []
    # the event coming later, once we're done: ours by the place it was sent to, not by when
    assert W.busy is None and W.OnUserWaypoint() is False and len(N.stops) == 2
    # moved on to the next stop: still ours
    N.RemoveStop(1)
    assert W.Tick() is True and W.OnUserWaypoint() is False and len(N.stops) == 1
    # after a /reload: Waypoint UI puts back ours (its flag), our own record of it gone
    W.fed = None
    lua.eval("AGPS_WUI.setGame")(lua.eval("AGPS_WUI.nav.mapID"), lua.eval("AGPS_WUI.nav.x"), lua.eval("AGPS_WUI.nav.y"))
    assert len(N.stops) == 1 and _pin_said(lua) == []
    # a step of Waypoint UI's own pathfinding on the way to a pin: not a pin
    N.Clear()
    W.Tick()
    _pin(lua, ns, 0, 2280, 340, step=True)
    assert len(N.stops) == 0 and _pin_said(lua) == []


def test_a_repeated_pin_or_one_on_a_stop_adds_nothing(wuipins):
    lua, ns = wuipins
    N = ns.Nav
    _pin(lua, ns, 0, 2250, 305)
    assert len(N.stops) == 1
    # the same pin set again (Waypoint UI puts it back, or the player sets it there again): nothing more
    _pin(lua, ns, 0, 2250, 305)
    _pin(lua, ns, 0, 2252, 306)  # (a few yards off: the same)
    assert len(N.stops) == 1 and len(_pin_said(lua)) == 1
    # the stop reached (gone from the route) and the pin put back again: not taken again
    N.RemoveStop(1)
    _pin(lua, ns, 0, 2250, 305)
    assert len(N.stops) == 0
    # a pin on a stop the route has (a map pin shared in chat, already its stop): nothing
    N.SetStops(lua.eval(GALLOWS), False, "red")
    _pin(lua, ns, 0, 2204, 303)
    assert len(N.stops) == 1 and len(_pin_said(lua)) == 1


def test_the_pins_option_off_adds_nothing_and_without_waypoint_ui_nothing_happens(wuipins):
    lua, ns = wuipins
    W, N, st = ns.WaypointUI, ns.Nav, ns.settings.gps
    st.waypointUIPins = False
    assert not W.PinsOn()
    _pin(lua, ns, 0, 2250, 305)
    assert len(N.stops) == 0 and _pin_said(lua) == []
    st.waypointUIPins = True
    # the option: under Send the next stop to Waypoint UI on the Directions page, on by default, gray without the addon
    assert ns.DEFAULTS.gps.waypointUIPins is True
    O = ns.Options
    O.Show()
    O.ShowPage("Directions")
    c = next(c for c in O.settingControls.values() if c.key == "waypointUIPins")
    O.Refresh()
    assert c.control.agpsOn is True
    # without Waypoint UI: the game's own Ctrl-click pin is no stop
    lua.execute("WaypointUIAPI = nil")
    O.Refresh()
    assert c.control.agpsOn is False
    O.Toggle()
    assert not W.Available() and not W.PinsOn()
    lua.execute("AGPS_WUI.nav = nil")
    mapID, u, v = ns.Import.MapPoint(0, 2300, 320)
    lua.eval("AGPS_WUI.setGame")(mapID, u, v)
    assert W.OnUserWaypoint() is False and len(N.stops) == 0 and _pin_said(lua) == []


def test_the_pin_there_at_login_is_no_new_stop(wuipins):
    lua, ns = wuipins
    W, N = ns.WaypointUI, ns.Nav
    # the game's waypoint kept from before, and our map's saved pin (put back as the game's at login)
    mapID, u, v = ns.Import.MapPoint(0, 2250, 305)
    lua.eval("function(m, u, v) AGPS_WUI.game = { uiMapID = m, position = { x = u, y = v } } end")(mapID, u, v)
    ns.CharDB().mapPin = lua.eval("{ cont = 0, x = 2300, y = 320 }")
    W.seen, W.ready = lua.table(), False
    assert W.OnUserWaypoint() is False  # (before login: not yet looked at)
    W.Seed()
    assert W.ready and W.OnUserWaypoint() is False
    lua.execute("AGPS_WUI.game = nil")
    ns.Import.RestoreMapPin()
    assert W.OnUserWaypoint() is False and len(N.stops) == 0 and _pin_said(lua) == []
    # a new pin after that: a stop
    _pin(lua, ns, 0, 2204, 303)
    assert len(N.stops) == 1


# (Kooki3z 1.4.2: "removing stop isn't working, I remove, add another and the old one is still there and a stop gets
# added to the route": Waypoint UI drops its record of ours on its own (a quest super-tracked, ours cleared with its
# pathfinding on: ClearUserNavigation(true)) and leaves the game's waypoint where we put it; that one was then taken for
# the player's pin, a stop again and our map's pin)


def _drop_record(lua):
    """Waypoint UI drops its record of the waypoint and keeps the game's (its ClearUserNavigation(true))."""
    lua.execute("WaypointUIAPI.Navigation.ClearUserNavigation(true)")


def _names(ns):
    return [d.name for d in ns.Nav.stops.values()]


CROSSROADS = "{ x = 2300, y = 320, cont = 0, name = 'Far Spot' }"


@pytest.mark.parametrize("send", [True, False])
def test_a_removed_stop_stays_removed_and_adding_one_adds_only_it(wuipins, send):
    lua, ns = wuipins
    W, N, st = ns.WaypointUI, ns.Nav, ns.settings.gps
    st.waypointUI = send
    N.SetStops(lua.eval(BRILL), False, "red")
    assert W.Tick() is send  # (Brill sent, with the option on)
    if send:
        _drop_record(lua)  # (Waypoint UI forgets ours, the game's waypoint left at Brill)
    N.RemoveStop(1)  # (Brill removed)
    W.Tick()
    N.AddStop(lua.eval(CROSSROADS), False)
    for _ in range(3):
        W.Tick()
    # the game's waypoint event again (Waypoint UI's re-sync, a super-track change): nothing comes back
    game = lua.eval("AGPS_WUI.game")
    if game is not None:
        lua.eval("AGPS_WUI.setGame")(game.uiMapID, game.position.x, game.position.y)
    W.OnUserWaypoint()
    assert _names(ns) == ["The Gallows", "Far Spot"]
    assert _pin_said(lua) == [] and ns.CharDB().mapPin is None  # (and no pin of the player's on our map)
    # the route cleared with ours left there: the game's waypoint cleared too, nothing comes back
    if send:
        _drop_record(lua)
    N.Clear()
    W.Tick()
    if send:
        assert lua.eval("AGPS_WUI.game") is None
    lua.eval("AGPS_WUI.setGame")(None)
    assert len(N.stops) == 0 and _pin_said(lua) == []


@pytest.mark.parametrize("send", [True, False])
def test_removing_the_stop_a_ctrl_click_pin_made_takes_the_pin_away(wuipins, send):
    lua, ns = wuipins
    W, N, st = ns.WaypointUI, ns.Nav, ns.settings.gps
    st.waypointUI = send
    _pin(lua, ns, 0, 2250, 305)
    assert len(N.stops) == 1 and len(_pin_said(lua)) == 1
    W.Tick()  # (the player's pin: left as it is)
    assert lua.eval("AGPS_WUI.game") is not None
    N.RemoveStop(1)
    W.Tick()
    # the pin went with its stop: Waypoint UI's and the game's
    assert lua.eval("AGPS_WUI.game") is None and lua.eval("AGPS_WUI.nav") is None
    assert ns.CharDB().mapPin is None
    # another stop added: only that one (sent to Waypoint UI with the option on), the old one never back
    N.AddStop(lua.eval(CROSSROADS), False)
    for _ in range(3):
        W.Tick()
    W.OnUserWaypoint()
    assert _names(ns) == ["Far Spot"] and len(_pin_said(lua)) == 1
    if send:
        assert lua.eval("AGPS_WUI.nav.flags") == W.FLAG
    # a pin elsewhere while its stop is on the route is kept; one of the player's not made a stop is never cleared
    N.Clear()
    W.Tick()
    lua.execute("AGPS_WUI.nav = nil")
    lua.eval("AGPS_WUI.setGame")(None)
    st.waypointUIPins = False
    _pin(lua, ns, 0, 2204, 303)
    N.SetStops(lua.eval(GALLOWS), False, "red")
    N.RemoveStop(1)
    W.Tick()
    assert lua.eval("AGPS_WUI.game") is not None  # (not a pin we made a stop of: the player's, left)


def test_without_waypoint_ui_removing_then_adding_a_stop_adds_only_it(wuipins):
    lua, ns = wuipins
    W, N = ns.WaypointUI, ns.Nav
    lua.execute("WaypointUIAPI = nil")
    N.SetStops(lua.eval(BRILL), False, "red")
    W.Tick()
    N.RemoveStop(1)
    N.AddStop(lua.eval(CROSSROADS), False)
    mapID, u, v = ns.Import.MapPoint(0, 2250, 305)
    lua.eval("AGPS_WUI.setGame")(mapID, u, v)  # (the game's own Ctrl-click pin)
    W.Tick()
    assert _names(ns) == ["The Gallows", "Far Spot"] and _pin_said(lua) == []
