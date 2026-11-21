"""The extra GPS map window (Options > Map, `extraWindow`; Kooki3z 2026-11-20: "another option for someone to create an
additional GPS window they can leave open on (like on a second monitor) and esc key wouldn't close it. Can still route
from it, can still popout another one from the minimap button, its literally just a duplicate GPS map window with
actions in sync across them"; "They can still double click the icon to collapse it"): a second BuildMap of its own
(GPSFrame's G.extra), the mouse its own, the route and settings shared, its place, size and zoom kept apart."""

import pytest

# (the map's window frame, the client's PortraitFrameTemplate, a stand-in: its title bar, close button and logo)
CHROME = '''
  local real = CreateFrame
  CreateFrame = function(kind, name, parent, template)
    local w = real(kind, name, parent, template)
    if template == "PortraitFrameTemplate" and not w.NineSlice then
      w.NineSlice, w.Bg, w.PortraitContainer = real("Frame"), w:CreateTexture(), real("Frame")
      w.PortraitContainer.portrait = w:CreateTexture()
      w.TitleContainer = real("Frame")
      w.TitleContainer.TitleText = w:CreateFontString()
      w.CloseButton = real("Button")
    end
    return w
  end
'''


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start, toc_files
    from azerothgps.paths import ADDON_DIR
    first = toc_files()[0]
    lua, ns = start(replace={first: CHROME + (ADDON_DIR / first).read_text(encoding="utf-8")})
    st = ns.settings.gps
    st.shown, st.minimized = True, None
    ns.GPS.ApplySettings()
    return lua, ns


@pytest.fixture
def extra(game):
    lua, ns = game
    st = ns.settings.gps
    st.extraWindow = True
    ns.GPS.ApplySettings()
    yield lua, ns, ns.extraMap
    st.extraWindow = False
    for k in ("extraWindowPoint", "extraWindowSize", "extraWindowWidth", "extraWindowZoom", "extraWindowMinimized",
              "extraWindowMiniAt"):
        st[k] = None
    st.shown, st.minimized = True, None
    ns.GPS.ApplySettings()
    ns.Nav.Clear()


def _frame(e):
    c = e.Canvas()
    return c.GetParent(c)


def test_off_by_default_no_extra_window(game):
    lua, ns = game
    assert ns.DEFAULTS.gps.extraWindow is False
    assert ns.extraMap is None or not _frame(ns.extraMap)._shown


def test_the_option_opens_a_second_interactive_map_window(extra):
    lua, ns, e = extra
    G = ns.GPS
    f = lua.eval("AzerothGPSFrame")
    assert e is not None and e.clone is True and e.extra is True and not e.square
    assert not G.clone and not G.extra and lua.eval("rawequal")(ns.GPS, G)  # (the first map: itself)
    ef = _frame(e)
    assert not lua.eval("rawequal")(ef, f) and ef._shown and f._shown  # (both shown)
    # (the mouse its own: not the square's click-through; a window of its own, not the minimap, not the world map)
    assert e.ClickThroughWanted(ns.settings.gps, False, False) is False and ef._mouse is not False
    assert not e.MinimapMode() and not e.WorldMapWanted() and not e.mmState.on
    assert e.chrome is not None and e.logo is not None  # (the window frame and its corner logo)
    # (none of the things done once: its own background pump never runs, no Escape catcher, no quest pick events)
    assert not e.pumpFrame._shown and e.escCatcher is None and e.pickEvents is None and e.mmEvents is None
    assert G.pumpFrame._shown is not False


def test_a_double_click_on_it_adds_a_stop_both_windows_share(extra):
    lua, ns, e = extra
    G, N = ns.GPS, ns.Nav
    ef = _frame(e)
    # (the cursor off the player, a way from the map's middle: a stop there isn't reached at once)
    lua.execute("AGPS_OLD_CURSOR = GetCursorPosition GetCursorPosition = function() return 420, 400 end")
    try:
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False)
        assert len(N.stops) == 1
        e.Update()  # (its view drawn: where the click is on the map)
        lua.execute("AGPS_T = AGPS_T + 5")
        ef._scripts.OnMouseDown(ef, "LeftButton")
        ef._scripts.OnMouseUp(ef, "LeftButton")
        lua.execute("AGPS_T = AGPS_T + 0.1")
        ef._scripts.OnMouseDown(ef, "LeftButton")
        ef._scripts.OnMouseUp(ef, "LeftButton")
        assert len(N.stops) == 2  # (onto the route: the one route, ns.Nav)
        # the first window draws it too: the same stops in its redraw
        G.Update()
        e.Update()
        a, b = G.GlideFill(lua.table()), e.GlideFill(lua.table())
        assert (a[6], a[7]) == (b[6], b[7]) == (2, 0)  # (the route's stops, none waiting in either)
    finally:
        lua.execute("GetCursorPosition = AGPS_OLD_CURSOR")
        N.Clear()


def test_settings_changed_in_either_window_apply_to_both(extra):
    lua, ns, e = extra
    G, st = ns.GPS, ns.settings.gps
    was_style, was_alpha = st.style, st.alpha
    try:
        e.SetStyle("zone")  # (the extra window's map menu: the player's setting)
        assert st.style == "zone" and G.Style() == "zone"
        st.alpha = 0.55
        G.ApplySettings()  # (the options: the first map's, mirrored to the extra one)
        assert _frame(e)._alpha == 0.55
    finally:
        st.style, st.alpha = was_style, was_alpha
        G.ApplySettings()


def test_its_place_size_and_zoom_are_its_own_and_saved(extra):
    lua, ns, e = extra
    G, st = ns.GPS, ns.settings.gps
    point, size, zoom = [st.point[i] for i in range(1, 6)], st.size, st.zoom
    ef = _frame(e)
    # (at first the first window's place, a little down and right; its size and zoom)
    assert ef._pt[4] == point[3] + 40 and ef._pt[5] == point[4] - 40
    e.MoveMapBy(10, 20)
    assert st.extraWindowPoint is not None and st.extraWindowPoint[4] == point[3] + 50
    assert [st.point[i] for i in range(1, 6)] == point  # (the first window's: untouched)
    e.SetZoom(777)
    assert st.extraWindowZoom == 777 and st.zoom == zoom
    st.extraWindowSize = size + 120
    e.ApplySettings()
    assert (ef._w, ef._h) == (size + 120, size + 120) and st.size == size
    f = lua.eval("AzerothGPSFrame")
    assert (f._w, f._h) == tuple(G.MapSize())


@pytest.mark.parametrize("esc", [True, False])
def test_escape_never_closes_it(extra, esc):
    lua, ns, e = extra
    G, st = ns.GPS, ns.settings.gps
    was = st.escClosesMap
    try:
        st.escClosesMap = esc
        G.ApplySettings()
        ef = _frame(e)
        assert ef._shown and e.EscCatcherWanted() is False
        special = lua.eval("UISpecialFrames")
        names = [special[i] for i in range(1, len(special) + 1)]
        assert all(not lua.eval("rawequal")(lua.globals()[n], ef) for n in names)
        # the game's Escape: every frame in UISpecialFrames hidden
        for n in names:
            w = lua.globals()[n]
            if w is not None:
                w.Hide(w)
        e.ApplySettings()
        assert ef._shown
    finally:
        st.escClosesMap = was
        G.ApplySettings()


def test_a_double_click_on_its_logo_collapses_and_expands_it(extra):
    lua, ns, e = extra
    G, st = ns.GPS, ns.settings.gps
    f, ef = lua.eval("AzerothGPSFrame"), _frame(e)
    plate = e.logo.plate
    lua.execute("AGPS_T = 50")
    plate._scripts.OnMouseUp(plate, "LeftButton")
    lua.execute("AGPS_T = 50.2")
    plate._scripts.OnMouseUp(plate, "LeftButton")
    icon = e.miniIcon
    assert st.extraWindowMinimized and not ef._shown and icon._shown
    assert not st.minimized and f._shown  # (the first window: as it was)
    assert not lua.eval("rawequal")(icon, lua.globals().AzerothGPSMiniIcon)
    icon._scripts.OnDoubleClick(icon, "LeftButton")
    assert not st.extraWindowMinimized and ef._shown and not icon._shown


def test_turning_it_off_hides_it_and_on_again_brings_it_back_where_it_was(extra):
    lua, ns, e = extra
    G, st = ns.GPS, ns.settings.gps
    ef = _frame(e)
    e.MoveMapBy(-30, 15)
    saved = [st.extraWindowPoint[i] for i in range(1, 6)]
    st.extraWindow = False
    G.ApplySettings()
    assert not ef._shown and (e.miniIcon is None or not e.miniIcon._shown)
    assert lua.eval("AzerothGPSFrame")._shown
    st.extraWindow = True
    G.ApplySettings()
    assert lua.eval("rawequal")(ns.extraMap, e) and ef._shown  # (the same window again, not another)
    assert [ef._pt[i] for i in (1, 3, 4, 5)] == [saved[i] for i in (0, 2, 3, 4)]
    # its close button: the option off
    e.chrome.CloseButton._scripts.OnClick(e.chrome.CloseButton)
    assert st.extraWindow is False and not ef._shown and lua.eval("AzerothGPSFrame")._shown and st.shown


def test_the_first_window_and_the_minimap_square_clone_are_unaffected(extra):
    # (the minimap button still pops out the first window; with the map in the game's world map, the square's own
    # second map is made and shown as before, and the extra window stays its own beside both)
    from test_world_map_host import SETUP  # (the minimap's stand-in, MM_SETUP, and the world map's)
    lua, ns, e = extra
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    ef = _frame(e)
    try:
        st.useWorldMap, st.replaceMinimap = True, True
        G.ApplySettings()
        assert G.MinimapMode() and ef._shown and not e.MinimapMode()
        G.mmButton._scripts.OnClick(G.mmButton, "LeftButton")
        assert G.WorldMapHosted()
        c = ns.mapClone
        assert c is not None and c.square and not c.extra and not lua.eval("rawequal")(c, e)
        cf = _frame(c)
        assert cf._shown and c.MinimapMode() and ef._shown and not e.WorldMapHosted()
        assert c.ClickThroughWanted(st, False, False) is True  # (the square's: only shows, as before)
        lua.globals().ToggleWorldMap()
        assert not cf._shown and ef._shown and G.MinimapMode()
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        st.useWorldMap, st.replaceMinimap = False, False
        G.WorldMapChanged()
        G.ApplySettings()
    assert ef._shown and lua.eval("AzerothGPSFrame")._shown


def test_on_at_login_it_is_made_once_the_seamless_map_is_loaded():
    # (Core.lua's PLAYER_LOGIN starts the map before the stitched map's art loads: made then, the extra window had no
    # room for that art and drew the Terrain style; it waits a frame for it, as the square's second map gets its own
    # engine from the first one's chunks)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    pre = "AGPS_TIMERS = {} C_Timer.After = function(s, f) AGPS_TIMERS[#AGPS_TIMERS + 1] = f end"
    lua, ns = start(pre=pre, saved="AzerothGPSDB = { settings = { gps = { style = 'seamless', extraWindow = true, "
                                   "extraWindowPoint = { 'TOPLEFT', 'UIParent', 'BOTTOMLEFT', 900, 700 } } }, "
                                   "seamlessDefault60 = true, mapStyles75 = true }")
    G, A = ns.GPS, ns.Atlas
    lua.execute("local t = AGPS_TIMERS AGPS_TIMERS = {} for _, f in ipairs(t) do pcall(f) end")
    e = ns.extraMap
    assert e is not None and _frame(e)._shown
    assert G.ArtSpan() > 0 and e.ArtSpan() == G.ArtSpan() and e.Seamless()  # (room for the stitched map's art as the first map has)
    assert not lua.eval("rawequal")(e.Canvas(), G.Canvas())
    assert [_frame(e)._pt[i] for i in (1, 3, 4, 5)] == ["TOPLEFT", "BOTTOMLEFT", 900, 700]  # (where it was left)
    assert A.loaded is not None
