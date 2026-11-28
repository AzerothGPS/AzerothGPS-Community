"""Other UIs' frames over ours, and ours placed round theirs (1.4.2, Kooki3z's screenshots 2026-11-27): DaylightUI's Info
Panel was over the GPS minimap square, OpenMap's coordinates and tab rail over the map's bottom-right buttons in the
world map, EllesmereUI's minimap buttons half over the square and the player off its middle; the GPS window's frame off
by itself under those UIs, as the square's border is, until the player sets it."""

import pytest

from test_map_redraw import _expand_setup, game, minimap  # noqa: F401
from test_supported_uis import DAYLIGHT, uis  # noqa: F401
from test_world_map_host import wm  # noqa: F401

# DaylightUI 2.4.1's Info Panel (its Panel.lua and Minimap.lua, read only): a LOW strata panel top right, its map area
# MAP_LIFT (20) levels over the panel, the Minimap a child of that area at its top left, as big as the area.
DUI_PANEL = """
  AGPS_DPANEL = CreateFrame("Frame", "DaylightUIInfoPanelBody", UIParent)
  AGPS_DPANEL:SetFrameStrata("LOW")
  AGPS_DPANEL.GetFrameLevel = function() return 3 end
  AGPS_DAREA = CreateFrame("Frame", nil, AGPS_DPANEL)
  AGPS_DAREA:SetFrameStrata("LOW")
  AGPS_DAREA.GetFrameLevel = function() return 23 end
  AGPS_DAREA.GetWidth = function() return 225 end
  AGPS_DAREA.GetHeight = function() return 225 end
  AGPS_DAREA:SetPoint("TOPLEFT", AGPS_DPANEL, "TOPLEFT", 5, -5)
  AGPS_DAREA.GetNumPoints = function() return 1 end
  AGPS_DAREA.GetPoint = function() return "TOPLEFT", AGPS_DPANEL, "TOPLEFT", 5, -5 end
  AGPS_MM_PARENT = Minimap._parent
  Minimap._parent = AGPS_DAREA
  Minimap.GetFrameLevel = function(s) return s._level or 24 end
"""
DUI_PANEL_UNDO = """
  Minimap._parent = AGPS_MM_PARENT
  Minimap.GetFrameLevel, Minimap._level = nil, nil
"""


def test_the_square_is_over_daylightuis_panel_and_under_the_minimap(uis):  # noqa: F811
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    frame = lua.eval("AzerothGPSFrame")
    st.replaceMinimap, st.replaceMinimapSize, st.replaceMinimapSizePicked = True, "large", None
    G.ApplySettings()
    assert frame._strata == "BACKGROUND"  # (no other UI: the lowest strata, as ever)
    lua.execute(DAYLIGHT)
    lua.execute(DUI_PANEL)
    try:
        G.mmState.moves = None
        G.ApplySettings()
        assert lua.eval("rawequal")(G.SquarePanel(), lua.eval("AGPS_DAREA"))
        # (its strata, one over its map area: over its backdrop, strip and meter; our popups not lifted for it)
        assert frame._strata == "LOW" and frame._level == 24 and G.sqTop >= 24
        assert not ns.popupsOver
        # (the game's Minimap over the whole square: its dots, the panel's texts and our route on it)
        mm = lua.eval("Minimap")
        assert mm._level == G.sqTop + 1
        # (DaylightUI putting it back at its own level when it applies its settings: over the square again)
        lua.execute("Minimap._level = 24")
        G.LiftMinimap()
        assert mm._level == G.sqTop + 1
        # (the square as big as its map area, centered on the area itself: its strip under the map no more covered,
        # no band of its panel down the square's right and along its bottom, Kooki3z's screenshot of 2026-11-27)
        assert G.MinimapSquareSide() == 225 + 6
        pt = G.mmAnchor._pt
        assert lua.eval("rawequal")(pt[2], lua.eval("AGPS_DAREA")) and pt[3] == "CENTER"
        assert pt[1] == "CENTER" and (pt[4], pt[5]) == (pytest.approx(0), pytest.approx(0))
        # the drawing order (Kooki3z: "the row of text on the minimap from daylightUI, sit that on top of our minimap,
        # but our pause button and logo should be on top of theirs"):
        # their panel and map area under the square,
        assert frame._level > lua.eval("AGPS_DAREA:GetFrameLevel()") > lua.eval("AGPS_DPANEL:GetFrameLevel()")
        # their texts on the map (zone, coordinates, clock) are the Minimap's children: over the square with it,
        assert mm._level > G.sqTop
        # our logo and pause button over all of theirs (MEDIUM over their LOW strata), the logo inside the square's
        # corner, clear of their text row (its original spot off under their minimap, Kooki3z 2026-11-28)
        order = ns.STRATA_ORDER
        b = G.mmButton
        assert order[b._strata] > order["LOW"]
        assert _inside_spot(lua, G)
        lua.execute("AGPS_NS.Nav.paused = true")
        try:
            G.PlaceMinimapButton()
            r = G.mmResume
            assert r is not None and r._shown
            assert r._strata == b._strata
            assert r._pt[4] == pytest.approx(G.MINIMAP_LOGO_INSIDE + b.logoSize + G.MINIMAP_RESUME_GAP)
        finally:
            lua.execute("AGPS_NS.Nav.paused = nil")
            G.PlaceMinimapButton()
        # (a size the player picks: theirs)
        st.replaceMinimapSizePicked = True
        assert G.MinimapSquareSide() == G.MINIMAP_SIDES["large"]
        st.replaceMinimapSizePicked = None
        # (DaylightUI's minimap turned off: the lowest strata and the square's own level again, the Minimap's too)
        lua.execute("AGPS_DUI.map = false")
        G.ApplySettings()
        assert G.SquarePanel() is None and frame._strata == "BACKGROUND" and G.sqTop is None
        assert G.mmLift is None and mm._level == 24
    finally:
        lua.execute(DUI_PANEL_UNDO)
        st.replaceMinimap, st.replaceMinimapSize, st.replaceMinimapSizePicked = False, "small", None
        G.ApplySettings()


def test_ellesmereuis_square_is_fitted_and_centered_on_the_player(uis):  # noqa: F811
    # (EllesmereUI's cropped minimap parents the Minimap to a layout frame of its own centered on the Minimap: the square
    # was reckoned from it, so it moved with the Minimap and the player's arrow was off the square's middle)
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_LOADED.EllesmereUI, AGPS_LOADED.EllesmereUIMinimap = true, true
      AGPS_MM_PARENT = Minimap._parent
      AGPS_LAYOUT = CreateFrame("Frame", nil, UIParent)
      AGPS_LAYOUT.GetNumPoints = function() return 1 end
      AGPS_LAYOUT.GetPoint = function() return "CENTER", Minimap, "CENTER", 0, 0 end
      AGPS_LAYOUT.GetCenter = function() return 1000, 700 end -- (wherever the Minimap is now)
      Minimap._parent = AGPS_LAYOUT
      Minimap._w, Minimap._h = 300, 300
      UIParent.GetCenter = function() return 960, 540 end
    """)
    st.replaceMinimap, st.replaceMinimapSizePicked = True, None
    try:
        G.ApplySettings()
        m = G.mmState
        assert m.on and lua.eval("rawequal")(m.home.parent, lua.eval("UIParent"))
        assert (m.home.dx, m.home.dy) == (1800 - 960, 950 - 540)
        side = G.MinimapSquareSide()
        assert side == 306 and m.setW == 300  # (its map's size: the Minimap the size it gave it)
        a = G.mmAnchor
        pt = a._pt
        # (the square centered on the Minimap's place, from the screen, not from the layout frame)
        assert lua.eval("rawequal")(pt[2], lua.eval("UIParent"))
        assert pt[1] == "CENTER" and (pt[4], pt[5]) == (pytest.approx(840), pytest.approx(410))
        # (its mover puts it somewhere else: the square follows, centered there)
        lua.execute("""
          Minimap._pts = { TOPRIGHT = { "TOPRIGHT", UIParent, "TOPRIGHT", -40, -60 } }
        """)
        m.moves = None
        assert G.OnMinimapMoved() is True
        u = lua.eval("UIParent")
        ex = u.GetLeft(u) + u.GetWidth(u) - 40 - 150 - 960  # (its middle from the screen's: TOPRIGHT, less half its side)
        ey = u.GetBottom(u) + u.GetHeight(u) - 60 - 150 - 540
        assert (m.home.dx, m.home.dy) == (pytest.approx(ex), pytest.approx(ey))
        assert (a._pt[4], a._pt[5]) == (pytest.approx(ex), pytest.approx(ey))
        # (its map size changed in it: the square fitted to the new one)
        lua.execute("Minimap._pts = { CENTER = { 'CENTER', AGPS_NS.GPS.mmAnchor, 'CENTER', 0, 0 } } Minimap._w = 250")
        m.moves = None
        G.OnMinimapMoved()
        assert m.home.w == 250 and G.MinimapSquareSide() == 256 and m.setW == 250
    finally:
        lua.execute("Minimap._parent = AGPS_MM_PARENT UIParent.GetCenter = nil Minimap._w, Minimap._h = 198, 198")
        st.replaceMinimap = False
        G.ApplySettings()


def _frame_box(ns):
    O = ns.Options
    O.Show()
    O.ShowPage("Window")
    cb = next(c.control for c in O.settingControls.values() if c.key == "windowFrame")
    O.Refresh()
    return cb


@pytest.mark.parametrize("ui", ["DaylightUI", "EllesmereUI"])
def test_the_window_frame_is_off_under_a_supported_ui_until_the_player_sets_it(uis, ui):  # noqa: F811
    lua, ns = uis
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    st.windowFrame, st.windowFramePicked = True, None
    try:
        assert G.WindowFramed()
        if ui == "DaylightUI":
            lua.execute(DAYLIGHT)
        else:
            lua.execute("AGPS_LOADED.EllesmereUIMinimap = true")
        assert G.SupportedMinimapUI() == ui
        G.ApplySettings()
        assert not G.WindowFramed() and st.windowFrame is True  # (the setting itself untouched)
        if G.chrome is not None:
            assert G.chrome._shown is False
        cb = _frame_box(ns)
        assert cb.GetChecked(cb) is False  # (the check box says what's shown)
        # the player ticks it: theirs, with that UI still there
        cb.SetChecked(cb, True)
        cb._scripts.OnClick(cb)
        O.Toggle()
        assert st.windowFrame is True and st.windowFramePicked is True and G.WindowFramed()
        # unticked by them: off, and still theirs without that UI
        cb = _frame_box(ns)
        cb.SetChecked(cb, False)
        cb._scripts.OnClick(cb)
        O.Toggle()
        lua.execute("DaylightUI = nil AGPS_LOADED = {}")
        assert G.SupportedMinimapUI() is None and not G.WindowFramed()
    finally:
        st.windowFrame, st.windowFramePicked = True, None
        G.ApplySettings()


# OpenMap 0.8.13's frames over the world map's bottom-right corner (its Map/Extras.lua and Map/Panel.lua, read only):
# the coordinates (a 1 x 22 bar 9000 levels over the map, its pills to its left) left of the game's quest log button,
# and the tab rail (a frame over the whole map, 9300 over) with its tabs low on the right edge going up. The map's box
# as in Kooki3z's screenshot: 775 x 555.
OPENMAP_CORNER = """
  local box = WorldMapFrame.ScrollContainer
  box.GetWidth = function() return 775 end
  box.GetHeight = function() return 555 end
  box.GetLeft = function() return 20 end
  box.GetRight = function() return 795 end
  box.GetBottom = function() return 10 end
  box.GetTop = function() return 565 end
  local function Rect(f, l, b, w, h, level)
    f.GetLeft = function() return l end
    f.GetBottom = function() return b end
    f.GetWidth = function() return w end
    f.GetHeight = function() return h end
    f.GetFrameLevel = function() return level end
    AGPS_RECTS[#AGPS_RECTS + 1] = { l, b, l + w, b + h }
    return f
  end
  AGPS_RECTS = {}
  -- (the game's quest log button in the corner, lifted over the icons by OpenMap)
  Rect(CreateFrame("Button", nil, box), 795 - 34, 11, 32, 32, 9002)
  local bar = Rect(CreateFrame("Frame", nil, box), 795 - 40, 18, 1, 22, 9000)
  Rect(CreateFrame("Frame", nil, bar), 795 - 40 - 150, 18, 150, 24, 9001)
  Rect(CreateFrame("Frame", nil, bar), 795 - 40 - 306, 18, 150, 24, 9001)
  local rail = Rect(CreateFrame("Frame", nil, box), 20, 10, 775, 555, 9300)
  AGPS_RECTS[#AGPS_RECTS] = nil -- (a layer over the whole map: only its tabs are in the way)
  Rect(CreateFrame("Button", nil, rail), 795 - 40, 10 + 44, 40, 42, 9301)
  Rect(CreateFrame("Button", nil, rail), 795 - 32, 10 + 89, 32, 16, 9301)
  for i = 0, 2 do Rect(CreateFrame("Button", nil, rail), 795 - 32, 10 + 108 + i * 37, 32, 34, 9301) end
  -- (a game's map pin under our buttons: not in the way)
  Rect(CreateFrame("Frame", nil, box), 795 - 70, 10, 28, 28, 2500)
  AGPS_RECTS[#AGPS_RECTS] = nil
  AGPS_NS.GPS.mapButtons.import.GetFrameLevel = function() return 4050 end
"""


def test_the_bottom_right_buttons_are_clear_of_openmaps_frames_in_the_world_map(wm):  # noqa: F811
    lua, ns = wm
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().ToggleWorldMap()
    try:
        assert G.WorldMapHosted()
        imp, rc = G.mapButtons["import"], G.mapButtons.recenter
        # (without OpenMap: left of the game's own corner button, as before; Back to Your Position in that spot since the
        # import button went into the map menu's row, 1.4.2)
        assert (imp._pt[2], imp._pt[3]) == (-6 - G.WORLD_MAP_CORNER, 6)
        assert rc._pt[1] == "BOTTOMRIGHT" and lua.eval("rawequal")(rc._pt[2], imp)
        assert (rc._pt[3], rc._pt[4], rc._pt[5]) == ("BOTTOMRIGHT", 0, 0)
        lua.execute(OPENMAP_CORNER)
        rects = [(r[1], r[2], r[3], r[4]) for r in lua.eval("AGPS_RECTS").values()]

        def hits(x, y):
            r, b = 795 + x, 10 + y
            col = (r - 28, b, r, b + G.CORNER_COLUMN * G.CORNER_STEP)
            return [o for o in rects if o[0] < col[2] and o[2] > col[0] and o[1] < col[3] and o[3] > col[1]]

        # (where it was: under OpenMap's coordinates, the column over it into its tabs' row)
        assert hits(-6 - G.WORLD_MAP_CORNER, 6)
        G.ApplySettings()
        x, y = imp._pt[2], imp._pt[3]
        assert hits(x, y) == [] and (x, y) != (-6 - G.WORLD_MAP_CORNER, 6)
        assert y == pytest.approx(18 + 24 - 10 + G.CORNER_GAP)  # (over the coordinates, still in the corner)
        # (OpenMap's frames gone: back in the corner, by the world map's tick too)
        lua.execute("for _, k in ipairs({ WorldMapFrame.ScrollContainer:GetChildren() }) do k:Hide() end")
        lua.execute("AGPS_NS.GPS.wmState.levelAt = nil")
        G.WorldMapTick()
        assert (imp._pt[2], imp._pt[3]) == (-6 - G.WORLD_MAP_CORNER, 6)
    finally:
        lua.execute("AGPS_NS.GPS.mapButtons.import.GetFrameLevel = nil")
        lua.execute("""
          local box = WorldMapFrame.ScrollContainer
          box.GetLeft, box.GetRight, box.GetBottom, box.GetTop = nil, nil, nil, nil
          box.GetWidth = function() return 700 end
          box.GetHeight = function() return 460 end
          box._kids = {}
        """)


# StreetView's buttons (AzerothGPS_StreetView's Figure.lua, read only): its figure and Street Guess's, 28 across, going
# up the bottom-right column from Back to Your Position (or the import button while that's hidden), 4 between.
STREETVIEW = """
  local G = AGPS_NS.GPS
  local top = G.TopLayer()
  local below = G.mapButtons.import
  AGPS_SV = {}
  for i = 1, 2 do
    local b = CreateFrame("Button", nil, top)
    b:SetSize(28, 28)
    b:SetPoint("BOTTOM", below, "TOP", 0, 4)
    local rel = below
    b.GetPoint = function() return "BOTTOM", rel, "TOP", 0, 4 end
    AGPS_SV[i] = b
    below = b
  end
"""
STREETVIEW_UNDO = "for _, b in ipairs(AGPS_SV or {}) do b:Hide() end AGPS_SV = nil"


def _strip_route(lua, ns):
    from test_map_extras import OPEN, _part, _route

    fz = [0, 10, 20, 30, 30, 30, 20, 10]
    p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
    return _route(lua, p, 0)


def _layer_size(lua, ns, w, h):
    lua.eval("function(f, w, h) f.GetWidth = function() return w end f.GetHeight = function() return h end end")(
        ns.GPS.TopLayer(), w, h)


@pytest.mark.parametrize("rail_on", ["box", "window"])
def test_the_strips_x_is_clear_of_the_corner_column_and_openmap_in_the_world_map(wm, rail_on):  # noqa: F811
    """Kooki3z's screenshot 2026-11-27 for 1.4.2 (OpenMap, No Map, the world map: "i get overlap with streetview, also
    can't click the X here"): the height profile strip's X at its right end was under the bottom-right column there
    (left of the game's corner button in the world map, OpenMap's coordinates pushing it up), StreetView's figure and
    Street Guess's button going up it over the X. The strip keeps clear of the column and of OpenMap's frames (its tab
    rail on the world map window itself, as OpenMap has it, or on the scroll frame), its X clear of them all and so the
    topmost thing where it is; in the GPS window, as before."""
    from test_map_extras import _overlap, _rect

    lua, ns = wm
    G, MX, st = ns.GPS, ns.MapExtras, ns.settings.gps
    top = G.TopLayer()
    same = lua.eval("rawequal")
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().ToggleWorldMap()
    W, H = 775, 555
    try:
        assert G.WorldMapHosted()
        corner = OPENMAP_CORNER
        if rail_on == "window":
            corner = corner.replace('CreateFrame("Frame", nil, box), 20, 10, 775, 555, 9300',
                                    'CreateFrame("Frame", nil, WorldMapFrame), 20, 10, 775, 555, 9300')
            assert corner != OPENMAP_CORNER
        lua.execute(corner)
        lua.execute(STREETVIEW)
        _layer_size(lua, ns, W, H)
        G.ApplySettings()
        lua.execute("AGPS_T = (AGPS_T or 0) + 1")
        G.Update()
        openmap = [(r[1] - 20, r[2] - 10, r[3] - 20, r[4] - 10) for r in lua.eval("AGPS_RECTS").values()]
        # (OpenMap's frames seen wherever it puts them: its tabs on the window's rail too)
        seen = [tuple(o.values()) for o in G.wmCoverRects.values()]
        for r in openmap:
            if r[2] - r[0] >= 4:  # (the coordinates' 1-wide bar holds its pills, which count)
                assert any(s == pytest.approx(r) for s in seen), (rail_on, r)
        f = G.mx.strip
        MX.OnRedraw(G, _strip_route(lua, ns), 0, 2000.0, 0.0, 200)
        assert f._shown
        sr = _rect(lua, f, top, W, H)
        x_rect = _rect(lua, f.close, top, W, H)
        assert sr is not None and x_rect is not None
        assert x_rect[2] == pytest.approx(sr[2] - 1) and x_rect[3] == pytest.approx(sr[3])  # (still its top right)
        column = [G.mapButtons["import"], G.mapButtons.recenter] + list(lua.eval("AGPS_SV").values())
        col_rects = [_rect(lua, b, top, W, H) for b in column]
        assert all(r is not None for r in col_rects)
        # (StreetView's buttons left where it put them, over the corner, as before the map menu takes them in (1.4.2,
        # G.SyncCompanions, test_map_layers.py): the column the strip keeps clear of is theirs too)
        # now: the strip and its X clear of the whole column (buttons shown or not) and of OpenMap's frames
        room = tuple(G.CornerColumnRect().values())
        for r in col_rects + [room] + openmap:
            assert not _overlap(x_rect, r), (rail_on, r, x_rect)
            assert not _overlap(sr, r), (rail_on, r, sr)
        assert sr[0] == MX.STRIP_SIDE and sr[2] - sr[0] >= MX.STRIP_MIN_W
        # (the X topmost where it is: nothing of ours or OpenMap's at a higher level over it)
        level = f.close._level
        assert level is not None and level >= f._level  # (the stand-in's levels: a child's as its parent's)
        over = [b for b in _shown(lua, top) if not same(b, f.close) and _rect(lua, b, top, W, H) is not None
                and _overlap(x_rect, _rect(lua, b, top, W, H)) and (b._level or 0) >= level]
        assert over == []
        # (a click on it still hides the strip for this route)
        lua.execute("AGPS_SHIFT_WAS = IsShiftKeyDown IsShiftKeyDown = function() return false end")
        try:
            f.close._scripts.OnClick(f.close)
        finally:
            lua.execute("IsShiftKeyDown = AGPS_SHIFT_WAS")
        assert not f._shown
        MX.closed = None
        # (out of the world map: the strip as wide as ever, the column back in its corner, nothing of OpenMap's kept)
        lua.globals().ToggleWorldMap()
        G.ApplySettings()
        _layer_size(lua, ns, 400, 400)
        MX.OnRedraw(G, _strip_route(lua, ns), 0, 2000.0, 0.0, 200)
        sr = _rect(lua, f, top, 400, 400)
        assert G.wmCoverRects is None and (sr[0], sr[2]) == (MX.STRIP_SIDE, 400 - MX.STRIP_SIDE)
    finally:
        MX.closed = None
        lua.execute(STREETVIEW_UNDO)
        lua.execute("AGPS_NS.GPS.mapButtons.import.GetFrameLevel = nil")
        lua.execute("AGPS_NS.GPS.TopLayer().GetWidth, AGPS_NS.GPS.TopLayer().GetHeight = nil, nil")
        lua.execute("""
          local box = WorldMapFrame.ScrollContainer
          box.GetLeft, box.GetRight, box.GetBottom, box.GetTop = nil, nil, nil, nil
          box.GetWidth = function() return 700 end
          box.GetHeight = function() return 460 end
          box._kids = {}
          WorldMapFrame._kids = {}
        """)


def _shown(lua, f):
    out = []
    kids = f._kids
    for i in range(1, len(kids or []) + 1):
        k = kids[i]
        if not k._shown:
            continue
        if k._kind in ("Button", "CheckButton"):
            out.append(k)
        out.extend(_shown(lua, k))
    return out
def test_the_minimap_logo_can_be_hidden_and_the_resume_button_stays_put(uis):  # noqa: F811
    # (Kooki3z 2026-11-27 for 1.4.2: "add option to hide minimap logo button"; its clicks are reached by the Show/Hide
    # GPS key, /agps show and /agps, said in the option's tooltip)
    lua, ns = uis
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    _expand_setup(lua)
    st.replaceMinimap, st.replaceMinimapLogo = True, True
    try:
        G.ApplySettings()
        b = G.mmButton
        assert b._shown and G.SquareLogoShown()
        lua.execute("AGPS_NS.Nav.paused = true")
        G.PlaceMinimapButton()
        r = G.mmResume
        assert r._shown
        at = (r._pt[1], r._pt[3], r._pt[4], r._pt[5])
        # off: hidden, on the square and with another UI too; the Resume Routing button where it was, clickable
        for ui in (None, "DaylightUI"):
            if ui:
                lua.execute(DAYLIGHT)
                st.replaceMinimapLogo = True
                G.ApplySettings()
                at = (r._pt[1], r._pt[3], r._pt[4], r._pt[5])
            st.replaceMinimapLogo = False
            G.ApplySettings()
            assert b._shown is False and r._shown
            assert (r._pt[1], r._pt[3], r._pt[4], r._pt[5]) == at
            assert r._scripts["OnClick"] is not None
        # on again: shown
        st.replaceMinimapLogo = True
        G.ApplySettings()
        assert b._shown
        # (the option listed on the Minimap page, and found by the search)
        O.Show()
        O.ShowPage("Minimap")
        c = next(c for c in O.settingControls.values() if c.key == "replaceMinimapLogo")
        O.Search("logo on the minimap")
        rows = [row for p in O.search.pages.values() for row in p.rows.values()]
        hit = [row for row in rows if lua.eval("rawequal")(row.w, c.control)]
        assert hit and hit[0].w._shown
        O.Search("")
        O.Toggle()
    finally:
        lua.execute("AGPS_NS.Nav.paused = nil DaylightUI = nil")
        st.replaceMinimap, st.replaceMinimapLogo = False, True
        G.ApplySettings()


# The game's frame levels and stratas as they work (the stand-in's are fixed numbers): a frame's level is what was set,
# else its parent's and one more each frame down; its strata what was set, else its parent's; mouse as enabled.
REAL_FRAMES = """
  AGPS_LEVEL_OF = function(w)
    local n = 0
    while w and not w._level and n < 50 do w, n = w._parent, n + 1 end
    return ((w and w._level) or 5) + n
  end
  local made = NewWidget
  NewWidget = function(...)
    local w = made(...)
    w.GetFrameLevel = AGPS_LEVEL_OF
    w.GetFrameStrata = function(s)
      local f, n = s, 0
      while f and not f._strata and n < 60 do f, n = f._parent, n + 1 end
      return (f and f._strata) or "MEDIUM"
    end
    w.EnableMouse = function(s, v) s._mouse = v and true or false end
    w.IsMouseEnabled = function(s) return s._mouse or false end
    return w
  end
"""


def _hosted_with_openmap(rail_on="window"):
    """A fresh game (REAL_FRAMES) with the GPS map in the world map, OpenMap's corner frames and StreetView's buttons,
    the button layer as big as the world map's box (775 x 555)."""
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    from test_world_map_host import SETUP as WM_SETUP

    lua, ns = start(pre=REAL_FRAMES)
    G, st = ns.GPS, ns.settings.gps
    G.Update()
    lua.execute(WM_SETUP)
    st.shown, st.minimized, st.useWorldMap = True, None, True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()
    assert G.WorldMapHosted()
    corner = OPENMAP_CORNER
    if rail_on == "window":
        corner = corner.replace('CreateFrame("Frame", nil, box), 20, 10, 775, 555, 9300',
                                'CreateFrame("Frame", nil, WorldMapFrame), 20, 10, 775, 555, 9300')
    # (every one of its frames there taking the mouse, the worst case; its levels as it sets them)
    corner = corner.replace("AGPS_RECTS[#AGPS_RECTS + 1] = { l, b, l + w, b + h }",
                            "AGPS_RECTS[#AGPS_RECTS + 1] = { l, b, l + w, b + h } f._mouse = true")
    corner = corner.replace("f.GetFrameLevel = function() return level end", "f._level = level")
    lua.execute(corner.replace("AGPS_NS.GPS.mapButtons.import.GetFrameLevel = function() return 4050 end", ""))
    lua.execute(STREETVIEW)
    _layer_size(lua, ns, 775, 555)
    G.ApplySettings()
    return lua, ns


def _tick(lua, G, n=1):
    for _ in range(n):
        lua.execute("AGPS_T = (AGPS_T or 0) + 1.1 AGPS_NS.GPS.wmState.levelAt = nil")
        G.WorldMapTick()


def _strip_at(lua, G, W=775, H=555):
    from test_map_extras import _rect

    f = G.mx.strip
    return _rect(lua, f, G.TopLayer(), W, H), _rect(lua, f.close, G.TopLayer(), W, H)


def test_the_strip_stays_put_as_openmap_and_the_map_change_round_it():
    """Kooki3z's video 2026-11-27 for 1.4.2 (OpenMap, No Map, the world map: "its position jumps too much"): the strip
    went over Clear Route when that showed and back down when it didn't, so a drag on the map or following again moved
    it, and OpenMap's coordinates come and go with the pointer. At a fixed map size it stays where it is through the
    world map's ticks, redraws, Confirm Route / Clear Route showing and hiding, and OpenMap's cursor coordinates
    showing and hiding; Confirm Route goes over it."""
    from test_map_extras import _overlap, _rect

    lua, ns = _hosted_with_openmap()
    G, MX = ns.GPS, ns.MapExtras
    route = _strip_route(lua, ns)
    MX.OnRedraw(G, route, 0, 2000.0, 0.0, 200)
    assert G.mx.strip._shown
    first = _strip_at(lua, G)
    btn = G.confirmRouteBtn
    kids = lua.eval("WorldMapFrame.ScrollContainer._kids")
    cursor = None
    for i in range(1, len(kids) + 1):  # (the cursor's pill: the left one of the coordinates bar's two)
        k = kids[i]
        if k._kids and len(k._kids) == 2:
            cursor = k._kids[2]
    assert cursor is not None
    for step in range(8):
        btn._shown = step % 2 == 0  # (a drag, then following again)
        cursor._shown = step % 3 != 0  # (the pointer on OpenMap's map and off it)
        _tick(lua, G)
        MX.OnRedraw(G, route, 0, 2000.0, 0.0, 200)
        assert _strip_at(lua, G) == first, step
    # (Confirm Route over it, clear of it)
    G.Follow()
    G.PadPan(40, 0)  # (looking round: the crosshair and Confirm Route)
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    G.Update()
    MX.OnRedraw(G, route, 0, 2000.0, 0.0, 200)
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    G.Update()
    MX.OnRedraw(G, route, 0, 2000.0, 0.0, 200)
    assert btn._shown and G.mx.strip._shown
    sr = _strip_at(lua, G)[0]
    br = _rect(lua, btn, G.TopLayer(), 775, 555)
    assert br is not None and not _overlap(br, sr) and br[1] >= sr[3]
    # (another map size: worked out again for it, by the rule and not a fixed width: from the left margin, clear of the
    # bottom-right column (only Back to Your Position since the import button and StreetView's went into the map
    # menu, 1.4.2) and of OpenMap's frames, narrower than on the wider map, and kept through ticks and redraws)
    _layer_size(lua, ns, 700, 555)
    MX.OnRedraw(G, route, 0, 2000.0, 0.0, 200)
    sr2, x2 = _strip_at(lua, G, 700)
    assert sr2[0] == MX.STRIP_SIDE and sr2[2] <= 700 - MX.STRIP_SIDE and sr2[2] - sr2[0] < sr[2] - sr[0]
    assert sr2[2] - sr2[0] >= MX.STRIP_MIN_W
    for r in [tuple(c.values()) for c in G.BottomCovers().values()]:
        assert not _overlap(sr2, r) and not _overlap(x2, r), r
    for _ in range(3):
        _tick(lua, G)
        MX.OnRedraw(G, route, 0, 2000.0, 0.0, 200)
        assert _strip_at(lua, G, 700)[0] == sr2


def _mouse_frames(lua, f, top, W, H, out):
    from test_map_extras import _rect

    kids = f._kids
    for i in range(1, len(kids or []) + 1):
        k = kids[i]
        if not k._shown:
            continue
        if k._kind in ("Button", "CheckButton") or k._mouse:
            r = _rect(lua, k, top, W, H)
            if r is not None:
                out.append((k, r))
        _mouse_frames(lua, k, top, W, H, out)
    return out


@pytest.mark.parametrize("rail_on", ["box", "window"])
def test_the_topmost_frame_taking_the_mouse_at_the_x_is_the_x(rail_on):
    """Kooki3z's video 2026-11-27 for 1.4.2: the pointer on the strip's X, and nothing: no tooltip, no light, no click.
    The world map's tick lifted the map's buttons WORLD_MAP_BUTTONS over the map again each second from the level it
    had lifted them to, until every one was at the cap: the strip and its X both at 9000, the X's clicks the strip's.
    Through many ticks, of everything that takes the mouse there (ours, StreetView's, OpenMap's), the X is on top at
    its middle, alone; and every button stays over the strip (item 134)."""
    lua, ns = _hosted_with_openmap(rail_on)
    G, MX = ns.GPS, ns.MapExtras
    level = lua.eval("AGPS_LEVEL_OF")
    same = lua.eval("rawequal")
    route = _strip_route(lua, ns)
    f = G.mx.strip
    for t in range(6):
        _tick(lua, G)
        MX.OnRedraw(G, route, 0, 2000.0, 0.0, 200)
        assert f._shown and f._mouse  # (the strip under it takes the mouse: its own tooltip)
        _, xr = _strip_at(lua, G)
        cx, cy = (xr[0] + xr[2]) / 2, (xr[1] + xr[3]) / 2
        hits = [k for k, r in _mouse_frames(lua, G.TopLayer(), G.TopLayer(), 775, 555, [])
                if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]]
        assert any(same(k, f.close) for k in hits), t
        others = [(k._kind, level(k)) for k in hits if not same(k, f.close)]
        assert all(lv < level(f.close) for _, lv in others), (t, others, level(f.close))
        assert level(f) < level(f.close) < 9000, (t, level(f), level(f.close))
        # (OpenMap's frames: none there, whatever their level; the map's box from (20, 10))
        om = list(lua.eval("AGPS_RECTS").values())
        assert not any(r[1] - 20 <= cx <= r[3] - 20 and r[2] - 10 <= cy <= r[4] - 10 for r in om), t
        # (every button over the strip, as in the GPS window)
        for k, _ in _mouse_frames(lua, G.TopLayer(), G.TopLayer(), 775, 555, []):
            if k._kind == "Button" and not same(k, f.close) and not same(k._parent, f):
                assert level(k) > level(f), (t, k._text, level(k), level(f))
EUI_CROPPED = """
  AGPS_LOADED.EllesmereUI, AGPS_LOADED.EllesmereUIMinimap = true, true
  AGPS_MM_PARENT = Minimap._parent
  AGPS_LAYOUT = CreateFrame("Frame", nil, UIParent)
  AGPS_LAYOUT.GetNumPoints = function() return 1 end
  AGPS_LAYOUT.GetPoint = function() return "CENTER", Minimap, "CENTER", 0, 0 end
  AGPS_LAYOUT.GetWidth = function() return Minimap._eui end
  AGPS_LAYOUT.GetHeight = function() return Minimap._eui - 40 end -- (its title bar's crop, 20 a side)
  Minimap._parent = AGPS_LAYOUT
  Minimap._w, Minimap._h, Minimap._eui = 300, 300, 300
  AGPS_MM_ES = 1
  Minimap.GetEffectiveScale = function() return AGPS_MM_ES end
  UIParent.GetCenter = function() return 960, 540 end
"""
EUI_CROPPED_UNDO = """
  Minimap._parent = AGPS_MM_PARENT
  UIParent.GetCenter, Minimap.GetEffectiveScale, AzerothGPSFrame.GetEffectiveScale = nil, nil, nil
  Minimap._w, Minimap._h, Minimap._eui = 198, 198, nil
"""


def test_ellesmereuis_minimap_resized_or_scaled_is_followed_every_time(uis):  # noqa: F811
    # (Kooki3z's recording 2026-11-27: its size slider dragged, the square stayed at its old size over a black map;
    # the follow stopped after five moves in two seconds, meant for a place fought over)
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    lua.execute(EUI_CROPPED)
    st.replaceMinimap, st.replaceMinimapSizePicked = True, None
    try:
        G.ApplySettings()
        m = G.mmState
        assert G.MinimapSquareSide() == 306 and m.setW == 300
        for size in range(310, 410, 10):  # (more than the limit, at once)
            lua.execute(f"Minimap._w, Minimap._h, Minimap._eui = {size}, {size}, {size}")
            assert G.OnMinimapMoved() is True
            assert G.MinimapSquareSide() == size + 6 and m.setW == size
            assert lua.eval("AzerothGPSFrame._w") == size + 6
        # (its scale: the square in the screen's units the same size as the Minimap drawn)
        lua.execute("AGPS_MM_ES = 1.25")
        assert G.OnMinimapMoved() is True
        assert G.MinimapSquareSide() == round(400 * 1.25 + 6)
        assert m.setW == pytest.approx((G.MinimapSquareSide() - 6) / 1.25)
        # (its mask set as it applies: ours again, the Minimap not black over the square)
        lua.execute("AGPS_MM.masks = {} Minimap:SetMaskTexture(130937)")
        G.OnMinimapMask(130937)
        assert G.minimapForce is True
        G.OnMinimapMoved()
        assert lua.eval("AGPS_MM.mask") in (G.MINIMAP_SQUARE, G.MINIMAP_CLEAR)
    finally:
        lua.execute(EUI_CROPPED_UNDO)
        st.replaceMinimap = False
        G.ApplySettings()


def test_ellesmereuis_border_is_over_the_square_and_lined_up_with_it(uis):  # noqa: F811
    # (its border is a frame of the Minimap's at the Minimap's level, round its layout frame: the square under the
    # Minimap, its map exactly that frame's size and place, nothing of ours outside it)
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    lua.execute(EUI_CROPPED)
    lua.execute("AzerothGPSFrame.SetBackdropBorderColor = function(s, r, g, b, a) s._edgeA = a end")
    st.replaceMinimap, st.replaceMinimapSizePicked = True, None
    try:
        G.ApplySettings()
        f = lua.eval("AzerothGPSFrame")
        mm = lua.eval("Minimap")
        order = ns.STRATA_ORDER
        # (under the Minimap and so under its border)
        assert order[f._strata] < order[mm.GetFrameStrata(mm)]
        # (as wide as its map and as tall as its cropped frame, the canvas BORDER in from our see-through edge)
        assert (f._w, f._h) == (300 + 6, 260 + 6) and G.SquareBare() and f._edgeA == 0
        assert mm._w == 300  # (the Minimap its own size: its border's frame is centered on it)
        # (the square and the Minimap's anchor on the same middle)
        a = G.mmAnchor
        assert f._pt[1] == a._pt[1] == "CENTER" and (f._pt[4], f._pt[5]) == (a._pt[4], a._pt[5])
        assert lua.eval("rawequal")(mm._pt[2], a) and mm._pt[1] == "CENTER"
    finally:
        lua.execute(EUI_CROPPED_UNDO)
        st.replaceMinimap = False
        G.ApplySettings()


def test_the_logo_stays_put_as_the_world_map_opens_and_closes(uis):  # noqa: F811
    # (Kooki3z's recording 2026-11-27: the logo jumped as the world map opened and closed. In it the first map's frame is
    # that window's child at its canvas's scale, and the square's size and the Minimap's anchor, the logo's place
    # then, were worked out by that scale)
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    lua.execute(EUI_CROPPED)
    st.replaceMinimap, st.replaceMinimapSizePicked = True, None
    try:
        G.ApplySettings()
        a = G.mmAnchor
        before = (G.MinimapSquareSide(), a._w, a._h, a._pt[1], a._pt[4], a._pt[5], lua.eval("Minimap._w"))
        f = lua.eval("AzerothGPSFrame")
        assert (a._w, a._h) == (f._w, f._h)  # (the logo's two hosts the same box)
        lua.execute("AzerothGPSFrame.GetEffectiveScale = function() return 0.6 end")  # (as in the world map)
        G.mmState.placedKey = None
        G.ApplySettings()
        after = (G.MinimapSquareSide(), a._w, a._h, a._pt[1], a._pt[4], a._pt[5], lua.eval("Minimap._w"))
        assert after == before
    finally:
        lua.execute(EUI_CROPPED_UNDO)
        st.replaceMinimap = False
        G.ApplySettings()


def _logo_at(lua, G):
    b = G.mmButton
    return (b._pt[1], lua.eval("rawequal")(b._pt[2], G.mmAnchor), b._pt[3], b._pt[4], b._pt[5], b._w, b._h, b._shown,
            G.mmAnchor._pt[1], G.mmAnchor._pt[4], G.mmAnchor._pt[5], G.mmAnchor._w, G.mmAnchor._h)


def test_the_logo_is_in_one_place_as_the_gps_map_and_the_world_map_open_and_close(wm, uis):  # noqa: F811
    # (Kooki3z 2026-11-27 under EllesmereUI: "the logo still jumps on the minimap when opening the map". It went from
    # the window (the square) to the Minimap's anchor as the map came out of the square or went into the world map,
    # and was sized by the window's scale, the world map canvas's there)
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    lua.execute(EUI_CROPPED)
    st.replaceMinimap, st.replaceMinimapSizePicked, st.replaceMinimapKeepSquare = True, None, True
    try:
        # the world map
        st.useWorldMap = True
        G.ApplySettings()
        before = _logo_at(lua, G)
        assert before[0] == "BOTTOMLEFT" and before[1] is True and before[7] is True
        lua.globals().ToggleWorldMap()
        assert G.WorldMapHosted()
        lua.execute("AzerothGPSFrame.GetEffectiveScale = function() return 0.6 end")  # (that window's canvas's scale)
        G.ApplySettings()
        assert _logo_at(lua, G) == before
        lua.execute("AzerothGPSFrame.GetEffectiveScale = nil")
        lua.globals().ToggleWorldMap()
        G.ApplySettings()
        assert _logo_at(lua, G) == before
        # the GPS map out of the square (the square kept), and back
        st.useWorldMap = False
        G.ApplySettings()
        assert _logo_at(lua, G) == before
        G.SetMinimapExpanded(True)
        G.ApplySettings()
        assert G.SquareKeptOut() and _logo_at(lua, G) == before
        G.SetMinimapExpanded(False)
        G.mmState.tween = None
        G.ApplySettings()
        assert _logo_at(lua, G) == before
    finally:
        lua.execute(EUI_CROPPED_UNDO)
        st.replaceMinimap, st.useWorldMap = False, False
        lua.execute("if WorldMapFrame:IsShown() then WorldMapFrame:Hide() end")
        G.WorldMapChanged()
        G.ApplySettings()


def test_the_minimap_logo_drags_round_the_squares_edge_only_while_unlocked(uis):  # noqa: F811
    # (Kooki3z 2026-11-27 for 1.4.2: "make the AzerothGPS logo on the minimap movable around the minimap like the buttons
    # do", "locked by default")
    lua, ns = uis
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    lua.execute(EUI_CROPPED)
    st.replaceMinimap, st.replaceMinimapSizePicked = True, None
    st.replaceMinimapLogoUnlocked, st.replaceMinimapLogoAngle = False, None
    lua.execute("""
      AGPS_CUR = { 300, 300 }
      AGPS_OLD_CUR, AGPS_OLD_TIME = GetCursorPosition, GetTime
      GetCursorPosition = function() return AGPS_CUR[1], AGPS_CUR[2] end
      AGPS_NOW = 1000
      GetTime = function() return AGPS_NOW end
    """)
    try:
        G.ApplySettings()
        a = G.mmAnchor
        lua.execute("""
          local a = AGPS_NS.GPS.mmAnchor
          a.GetWidth = function(s) return s._w end
          a.GetHeight = function(s) return s._h end
          a.GetCenter = function() return 300, 300 end
        """)
        b = G.mmButton
        # (under EllesmereUI's minimap: inside the square's corner, its original spot off there)
        assert st.replaceMinimapLogoKeep is not False and _inside_spot(lua, G) and not G.LogoKept()
        # locked (the default): a drag does nothing, a click opens the map
        assert G.LogoUnlocked() is False
        b._scripts.OnDragStart(b)
        assert b._scripts["OnUpdate"] is None and st.replaceMinimapLogoAngle is None
        b._scripts.OnDragStop(b)
        b._scripts.OnClick(b, "LeftButton")
        assert G.mmState.expanded
        G.SetMinimapExpanded(False)
        G.mmState.tween = None
        G.ApplySettings()
        # unlocked: dragged up from the middle, it goes to the top edge and stays there
        st.replaceMinimapLogoUnlocked = True
        b._scripts.OnDragStart(b)
        lua.execute("AGPS_CUR = { 300, 500 }")
        b._scripts.OnUpdate(b)
        b._scripts.OnDragStop(b)
        assert b._scripts["OnUpdate"] is None and st.replaceMinimapLogoAngle == pytest.approx(90)
        # (the player's own "Keep the logo in its original spot" untouched under the UI, for when it's gone)
        assert st.replaceMinimapLogoKeep is not False
        half = b.logoSize / 2
        assert b._pt[1] == "CENTER" and lua.eval("rawequal")(b._pt[2], a)
        assert b._pt[4] == pytest.approx(0, abs=1e-6) and b._pt[5] == pytest.approx(a._h / 2 - half)
        # (the drag's own button-up is no click; a click after it is)
        b._scripts.OnClick(b, "LeftButton")
        assert not G.mmState.expanded
        lua.execute("AGPS_NOW = 1001")
        b._scripts.OnClick(b, "LeftButton")
        assert G.mmState.expanded
        G.SetMinimapExpanded(False)
        G.mmState.tween = None
        G.ApplySettings()
        # (kept after a reload: the setting; on the square as it's set again)
        G.ApplySettings()
        assert b._pt[1] == "CENTER" and b._pt[5] == pytest.approx(a._h / 2 - half)
        # the Resume Routing button beside it
        lua.execute("AGPS_NS.Nav.paused = true")
        G.PlaceMinimapButton()
        r = G.mmResume
        assert r._shown and lua.eval("rawequal")(r._pt[2], b)
        lua.execute("AGPS_NS.Nav.paused = nil")
        G.PlaceMinimapButton()
        # EllesmereUI's minimap resized: still on the top edge of the new size
        lua.execute("Minimap._w, Minimap._h, Minimap._eui = 360, 360, 360")
        G.OnMinimapMoved()
        assert st.replaceMinimapLogoAngle == pytest.approx(90)
        assert a._w == 366 and b._pt[5] == pytest.approx(a._h / 2 - b.logoSize / 2)
        # locked again: stays where it is, no more dragging
        st.replaceMinimapLogoUnlocked = False
        b._scripts.OnDragStart(b)
        assert b._scripts["OnUpdate"] is None and st.replaceMinimapLogoAngle == pytest.approx(90)
        # (the option on the Minimap page)
        O = ns.Options
        O.Show()
        O.ShowPage("Minimap")
        assert any(c.key == "replaceMinimapLogoUnlocked" for c in O.settingControls.values())
        O.Toggle()
    finally:
        lua.execute("GetCursorPosition, GetTime = AGPS_OLD_CUR, AGPS_OLD_TIME AGPS_NS.Nav.paused = nil")
        lua.execute(EUI_CROPPED_UNDO)
        st.replaceMinimap, st.replaceMinimapLogoUnlocked, st.replaceMinimapLogoAngle = False, False, None
        st.replaceMinimapLogoKeep = True
        G.ApplySettings()


def _original_spot(lua, G):
    # (1.4.1's: the logo's middle MINIMAP_LOGO_IN of its width in from the square's left, hanging below its bottom by the
    # share the window's corner logo hangs over its top)
    b = G.mmButton
    size = b.logoSize
    ns = lua.eval("AGPS_NS")
    return (b._pt[1] == "CENTER" and lua.eval("rawequal")(b._pt[2], G.mmAnchor) and b._pt[3] == "BOTTOMLEFT"
            and abs(b._pt[4] - size * G.MINIMAP_LOGO_IN) < 1e-6
            and abs(b._pt[5] - ((ns.TITLE_MID or 11) - 2) * size / (ns.CORNER_LOGO_UNITS or 62)) < 1e-6)


def test_keep_the_logo_in_its_original_spot(uis):  # noqa: F811
    # (Kooki3z 2026-11-28: "an option on by default that keeps its original position and is unticked when the minimap
    # logo was moved and greyed out while the button is unlocked")
    lua, ns = uis
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    _expand_setup(lua)
    st.replaceMinimap = True
    st.replaceMinimapLogoUnlocked, st.replaceMinimapLogoAngle, st.replaceMinimapLogoKeep = False, None, True
    lua.execute("""
      AGPS_OLD_CUR = GetCursorPosition
      GetCursorPosition = function() return 300, 500 end
    """)

    def box():
        O.Show()
        O.ShowPage("Minimap")
        c = next(c.control for c in O.settingControls.values() if c.key == "replaceMinimapLogoKeep")
        O.Refresh()
        return c

    try:
        # under DaylightUI's or EllesmereUI's minimap: off, grayed with a note, the logo inside the square's corner, and
        # still dragged while unlocked (Kooki3z 2026-11-28: "When using Ellesmere or DaylightUI this original spot
        # option should be off and greyed out")
        for ui in ("DaylightUI", "EllesmereUI"):
            lua.execute(DAYLIGHT if ui == "DaylightUI" else "AGPS_LOADED.EllesmereUIMinimap = true")
            G.ApplySettings()
            assert G.SupportedMinimapUI() == ui and not G.LogoKept() and _inside_spot(lua, G)
            c = box()
            assert c.agpsOn is False and c.GetChecked(c) is False
            note = next(r for r in O.search.pages[O.pages["Minimap"].index].rows.values()
                        if r.w and str(getattr(r.w, "_text", "")) == f"Off while {ui}'s minimap is in use.")
            assert note is not None
            O.Toggle()
            assert st.replaceMinimapLogoKeep is True  # (the setting itself untouched)
            lua.execute("DaylightUI = nil AGPS_LOADED = {}")
        # without them: the player's own setting again, 1.4.1's spot
        G.ApplySettings()
        assert G.LogoKept() and _original_spot(lua, G)
        lua.execute("""
          local a = AGPS_NS.GPS.mmAnchor
          a.GetWidth = function(s) return s._w end
          a.GetHeight = function(s) return s._h end
          a.GetCenter = function() return 300, 300 end
        """)
        b = G.mmButton
        c = box()
        assert c.agpsOn is True and c.GetChecked(c) is True
        O.Toggle()
        # unlocked: grayed out; a drag moves the logo and unticks it
        st.replaceMinimapLogoUnlocked = True
        c = box()
        assert c.agpsOn is False
        O.Toggle()
        b._scripts.OnDragStart(b)
        b._scripts.OnUpdate(b)
        b._scripts.OnDragStop(b)
        assert st.replaceMinimapLogoKeep is False and st.replaceMinimapLogoAngle == pytest.approx(90)
        assert b._pt[1] == "CENTER" and b._pt[3] == "CENTER" and not _original_spot(lua, G)
        # (after a /reload: the settings as they were, the logo where it was dropped)
        G.ApplySettings()
        assert b._pt[3] == "CENTER" and st.replaceMinimapLogoKeep is False
        # locked, ticked again: back in its original spot, and kept there (the angle left for later)
        st.replaceMinimapLogoUnlocked = False
        c = box()
        assert c.agpsOn is True and c.GetChecked(c) is False
        c.SetChecked(c, True)
        c._scripts.OnClick(c)
        O.Toggle()
        assert st.replaceMinimapLogoKeep is True
        G.ApplySettings()
        assert _original_spot(lua, G) and st.replaceMinimapLogoAngle == pytest.approx(90)
        G.ApplySettings()
        assert _original_spot(lua, G)
    finally:
        lua.execute("GetCursorPosition = AGPS_OLD_CUR DaylightUI = nil")
        st.replaceMinimap, st.replaceMinimapLogoUnlocked = False, False
        st.replaceMinimapLogoAngle, st.replaceMinimapLogoKeep = None, True
        G.ApplySettings()


def _inside_spot(lua, G):
    # (under DaylightUI's or EllesmereUI's minimap: inside the square's bottom-left corner)
    b = G.mmButton
    return (b._pt[1] == "BOTTOMLEFT" and lua.eval("rawequal")(b._pt[2], G.mmAnchor) and b._pt[3] == "BOTTOMLEFT"
            and b._pt[4] == G.MINIMAP_LOGO_INSIDE and b._pt[5] == G.MINIMAP_LOGO_INSIDE)
