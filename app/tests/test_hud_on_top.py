"""The map's HUD over every map icon (Kooki3z 2026-11-27, 1.4.2: "our text box should sit on top of map icons", then
"same with height data and all our buttons"; a flight master's icon was drawn across the directions): the directions'
panel, the height strip, Confirm Route, the quick buttons and their flyouts, the Map Menu, search, the corner buttons,
the floor pickers and the grips are all on one layer, GPSFrame's G.hudLayer, drawn over every map icon in each map mode
(the GPS window, the extra window, the game's world map, No Map), also after icons are added or redrawn and on frames
made on it later; no icon is the topmost mouse-taking frame where a button is. With the frames' levels and stratas as
the game's (a frame's level from its parent's, a strata passed down)."""

import pytest

from test_extra_map_window import CHROME
from test_no_map_style import CANVAS, OPENMAP, UNDO
from test_world_map_host import SETUP as WM_SETUP

PRE = """
  AGPS_LEVEL_OF = function(w)
    local n = 0
    while w and not w._level and n < 60 do w, n = w._parent, n + 1 end
    return ((w and w._level) or 5) + n
  end
  AGPS_STRATA_OF = function(w)
    local n = 0
    while w and not w._strata and n < 60 do w, n = w._parent, n + 1 end
    return (w and w._strata) or "MEDIUM"
  end
  -- (the mouse: a button takes it unless told not to, a frame only when told to)
  AGPS_MOUSE_OF = function(w)
    if w._mouse ~= nil then return w._mouse end
    return w._kind == "Button" or w._kind == "CheckButton"
  end
  local function Real(w)
    w.GetFrameLevel, w.GetFrameStrata, w.IsMouseEnabled = AGPS_LEVEL_OF, AGPS_STRATA_OF, AGPS_MOUSE_OF
    w.EnableMouse = function(s, on) s._mouse = on and true or false end
    w.GetNumChildren = function(s) return #(s._kids or {}) end
    return w
  end
  local made = NewWidget
  NewWidget = function(...) return Real(made(...)) end
  Real(Minimap)
  Real(UIParent)
  AGPS_RANK = { BACKGROUND = 1, LOW = 2, MEDIUM = 3, HIGH = 4, DIALOG = 5, FULLSCREEN = 6, FULLSCREEN_DIALOG = 7,
    TOOLTIP = 8 }
  local function Walk(f, out, skipOver, strata)
    for _, k in ipairs(f._kids or {}) do
      if not (skipOver and k.agpsOverHud) and not (strata and AGPS_STRATA_OF(k) ~= strata) then
        out[#out + 1] = k
        Walk(k, out, skipOver, strata)
      end
    end
    return out
  end
  -- Every map icon of map `G`: everything on its canvas (our icons, the game's POIs, other addons' pins, quest areas,
  -- party members, the player arrow's layer, the stops' markers), and `hosts`' frames (the Minimap and its pins, the
  -- world map's pins; not the buttons on its rim in a strata of their own, the game's UI, not the map's icons).
  AGPS_ICONS = function(G, hosts)
    local c = G.Canvas()
    local out = Walk(c, { c }, true)
    for _, h in ipairs(hosts or {}) do
      out[#out + 1] = h
      Walk(h, out, true, AGPS_STRATA_OF(h))
    end
    return out
  end
  -- Whether frame `w` is in the world map's canvas (the scroll frame's child).
  local function InCanvas(w)
    local box = WorldMapFrame and WorldMapFrame.ScrollContainer
    local child = box and rawget(box, "Child")
    local n = 0
    while child and w and n < 60 do
      if w == child then return true end
      w, n = w._parent, n + 1
    end
    return false
  end
  -- Every frame on the HUD layer over every icon, and at each mouse-taking one the topmost mouse-taking frame itself.
  -- `wm`: in the game's world map, which draws its canvas (the scroll frame's child) as one layer at the scroll frame's
  -- level: a frame in it is ordered by that, and by its own level only among the canvas's frames.
  AGPS_ORDER = function(w, wm)
    if wm and InCanvas(w) then
      local box = WorldMapFrame.ScrollContainer
      return AGPS_RANK[AGPS_STRATA_OF(box)] * 100000 + AGPS_LEVEL_OF(box) + AGPS_LEVEL_OF(w) / 20000
    end
    return AGPS_RANK[AGPS_STRATA_OF(w)] * 100000 + AGPS_LEVEL_OF(w)
  end
  AGPS_HUD_CHECK = function(G, icons, wm)
    local function Order(w) return AGPS_ORDER(w, wm) end
    local function Name(w)
      return string.format("%s %q %s/%d", w._kind, tostring(w._text), AGPS_STRATA_OF(w), AGPS_LEVEL_OF(w))
    end
    local hud = G.hudLayer
    local frames = Walk(hud, { hud })
    local top, topIcon = -1, nil
    for _, i in ipairs(icons) do
      local o = Order(i)
      if o > top then top, topIcon = o, i end
    end
    local bad = {}
    for _, f in ipairs(frames) do
      if Order(f) <= top then bad[#bad + 1] = Name(f) .. " under " .. Name(topIcon) end
    end
    for _, f in ipairs(frames) do
      if AGPS_MOUSE_OF(f) then
        local best, bo = f, Order(f)
        for _, i in ipairs(icons) do
          if AGPS_MOUSE_OF(i) and Order(i) >= bo then best, bo = i, Order(i) end
        end
        if best ~= f then bad[#bad + 1] = "the mouse at " .. Name(f) .. " to " .. Name(best) end
      end
    end
    if AGPS_MOUSE_OF(hud) or AGPS_MOUSE_OF(G.topLayer) then bad[#bad + 1] = "the layer takes the mouse" end
    return #frames, table.concat(bad, "; ")
  end
  -- New icons on each of map `G`'s icon layers, each with a glow of its own over it, as the stops' markers have (icons
  -- added after the map was drawn).
  AGPS_ADD_ICONS = function(G)
    for _, layer in ipairs({ G.poiLayer, G.keepLayer, G.markLayer, G.lineLayer }) do
      local b = CreateFrame("Button", nil, layer)
      b:SetFrameLevel(AGPS_LEVEL_OF(layer) + (layer == G.keepLayer and 2 or 1)) -- (a stop's marker: 2 over)
      CreateFrame("Frame", nil, b)
    end
  end
"""


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start, toc_files
    from azerothgps.paths import ADDON_DIR
    first = toc_files()[0]
    lua, ns = start(pre=PRE, replace={first: CHROME + (ADDON_DIR / first).read_text(encoding="utf-8")})
    ns.Nav.FUN = False
    st = ns.settings.gps
    st.shown, st.minimized = True, None
    ns.GPS.ApplySettings()
    return lua, ns


def _check(lua, G, hosts=None, wm=False):
    icons = lua.globals().AGPS_ICONS(G, lua.table_from(hosts or []))
    n, bad = lua.globals().AGPS_HUD_CHECK(G, icons, wm)
    assert n > 20, n  # (the directions, the strip, Confirm Route, the quick buttons, the corner buttons, ...)
    assert bad == "", bad


def _hud_has_everything(lua, G):
    """The pieces named in the request are on the HUD layer."""
    inside = lua.eval("""function(G, f)
      local n = 0
      while f and n < 20 do if f == G.hudLayer then return true end f, n = f._parent, n + 1 end
      return false
    end""")
    for name, f in [("directions", G.navPanel), ("height strip", G.mx.strip), ("Confirm Route", G.confirmRouteBtn),
                    ("search", G.searchButton), ("Back to Your Position", G.mapButtons.recenter),
                    ("import", G.mapButtons["import"]), ("size grip", G.sizeGrip)]:
        assert f is not None and inside(G, f), name


def _set_route(lua, ns):
    ns.Nav.SetStops(lua.eval("{ { x = 2204, y = 303, cont = 0, name = 'The Gallows' } }"), False, "red")


def test_the_hud_is_over_every_icon_in_the_gps_window(game):
    lua, ns = game
    G = ns.GPS
    _set_route(lua, ns)
    G.Update()
    _hud_has_everything(lua, G)
    _check(lua, G)
    # (icons added and the map redrawn: still under it; a button made on the HUD later: over them too)
    lua.globals().AGPS_ADD_ICONS(G)
    lua.execute("AGPS_T = AGPS_T + 2")
    G.Update()
    lua.eval("function(G) CreateFrame('Button', nil, G.topLayer) end")(G)
    _check(lua, G)
    ns.Nav.Clear()


def test_the_hud_is_over_the_games_minimap_dots_over_the_extra_window(game):
    """The game's Minimap, taken by the first map onto the square, is lifted a strata over the lowest one (its dots, the
    tracked flight masters, herbs and ore, over the map's icons); the extra map window is in the lowest one, so where
    they overlap the Minimap's dots were over its text and buttons. Its HUD goes over them: in the Minimap's strata, over
    it and its pins, also a pin added later; back where it was once the Minimap's given back."""
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    st.extraWindow = True
    G.ApplySettings()
    e = ns.extraMap
    try:
        assert e is not None
        ef = lua.eval("function(e) local c = e.Canvas() return c:GetParent() end")(e)
        assert lua.globals().AGPS_STRATA_OF(ef) == "BACKGROUND"
        hud_level = lua.globals().AGPS_LEVEL_OF(e.hudLayer)
        lua.execute("""
          Minimap._strata, Minimap._level = "LOW", 40
          AGPS_MMPIN = CreateFrame("Button", nil, Minimap)
          AGPS_MMPIN:SetFrameLevel(47)
        """)
        G.mmState.applied = True
        e.ApplyHud(True)
        _check(lua, e, [lua.eval("Minimap")])
        assert lua.globals().AGPS_STRATA_OF(e.navPanel or e.hudLayer) == "LOW"
        # (another addon's pin on the Minimap later, higher up: the HUD over it at the next check)
        lua.execute("AGPS_MMPIN2 = CreateFrame('Button', nil, Minimap) AGPS_MMPIN2:SetFrameLevel(90)")
        lua.globals().AGPS_ADD_ICONS(e)
        lua.execute("AGPS_T = AGPS_T + 2")
        e.Update()
        _check(lua, e, [lua.eval("Minimap")])
        # (the first window, in a strata over the Minimap's: over it as it is)
        G.Update()
        _check(lua, G, [lua.eval("Minimap")])
        # (given back: the HUD in the window's strata and at its level again)
        G.mmState.applied = None
        e.ApplyHud(True)
        assert lua.globals().AGPS_STRATA_OF(e.hudLayer) == "BACKGROUND"
        assert lua.globals().AGPS_LEVEL_OF(e.hudLayer) == hud_level
        _check(lua, e)
    finally:
        G.mmState.applied = None
        lua.execute("""
          for _, p in ipairs({ AGPS_MMPIN, AGPS_MMPIN2 }) do p:SetParent(UIParent) p:Hide() end
          Minimap._strata, Minimap._level = nil, nil
        """)
        st.extraWindow = False
        G.ApplySettings()


def _open_world_map(lua, ns):
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().ToggleWorldMap()
    assert G.WorldMapHosted()
    lua.execute("AGPS_T = AGPS_T + 2")
    G.Update()


def _world_map_pins(lua, levels):
    """The game's and other addons' icons on the world map's canvas (the game's: 2000 to about 2900)."""
    return [lua.eval(f"""(function()
      local p = CreateFrame("Button", nil, AGPS_NS.GPS.WorldMapCanvas())
      p:SetFrameLevel({lvl})
      AGPS_WM_PINS = AGPS_WM_PINS or {{}}
      table.insert(AGPS_WM_PINS, p)
      return p
    end)()""") for lvl in levels]


_BUTTONS_OVER = """
  return function(G)
    local strip, ring = G.mx.strip, G.ringLayer
    local function O(w) return AGPS_ORDER(w, true) end
    local bad, n = {}, 0
    local function Walk(f)
      for _, k in ipairs(f._kids or {}) do
        if k ~= strip and AGPS_STRATA_OF(k) == AGPS_STRATA_OF(G.topLayer) then
          if k._kind == "Button" or k._kind == "CheckButton" then
            n = n + 1
            if O(k) <= O(strip) or O(k) <= O(ring) then
              bad[#bad + 1] = string.format("%s %s at %d (strip %d)", k._kind, tostring(k._text), AGPS_LEVEL_OF(k),
                AGPS_LEVEL_OF(strip))
            end
          end
          Walk(k)
        end
      end
    end
    Walk(G.topLayer)
    if O(strip.close) <= O(strip) then bad[#bad + 1] = "the X" end
    return n, table.concat(bad, "; ")
  end
"""


def _buttons_over_the_strip_wm(lua, G):
    """Every button over the height strip and the landing ring, drawn as the world map draws them (item 134)."""
    n, bad = lua.execute(_BUTTONS_OVER)(G)
    assert n > 20, n
    assert bad == "", bad


def _strip_and_route_button(lua, G, pins):
    """Kooki3z's 2026-11-27 screenshot (No Map over OpenMap): the boat, the flight master, the round dots and a blue
    ring over the height strip, and a dock's countdown ("29:38", our dock icon's) over Clear Route. The strip, its line
    (on it) and its X over every icon; Clear Route over every icon of ours, a dock's countdown with it (on its icon);
    every button over the strip, each in its place among them as in the window."""
    level = lua.globals().AGPS_LEVEL_OF

    def order(w):
        return lua.globals().AGPS_ORDER(w, True)

    strip, route = G.mx.strip, G.confirmRouteBtn
    top_icon = max([order(p) for p in pins] + [order(i) for i in lua.globals().AGPS_ICONS(G).values()])
    assert order(strip) > top_icon and level(strip.close) > level(strip)
    assert order(route) > top_icon
    _buttons_over_the_strip_wm(lua, G)


def _world_map_checks(lua, ns, G, levels=(2000, 2500, 2900), later=2950):
    st = ns.settings.gps
    pins = _world_map_pins(lua, list(levels))
    _set_route(lua, ns)
    lua.execute("AGPS_T = AGPS_T + 2")  # (the HUD's next look at the icons: each second)
    G.Update()
    _check(lua, G, pins, wm=True)
    _strip_and_route_button(lua, G, pins)
    # (icons refreshed and added: another addon's pin higher up, ours redrawn)
    pins += _world_map_pins(lua, [later])
    lua.globals().AGPS_ADD_ICONS(G)
    lua.execute("AGPS_T = AGPS_T + 2")
    G.Update()
    _check(lua, G, pins, wm=True)
    _strip_and_route_button(lua, G, pins)
    # (made on the HUD after the world map's level pass: a new button, the world map's size grip, the directions'
    # panel put back on the map from its own window)
    lua.eval("function(G) CreateFrame('Button', nil, G.topLayer) end")(G)
    G.WorldMapGrip()
    st.navPanelDetached = True
    G.ApplyNavDetach()
    st.navPanelDetached = None
    G.ApplyNavDetach()
    _check(lua, G, pins, wm=True)
    # (and the world map's level pass each second: everything stays put, in its order)
    for _ in range(3):
        lua.execute("AGPS_T = AGPS_T + 1.5")
        G.WorldMapTick()
        G.Update()
    _check(lua, G, pins, wm=True)
    _strip_and_route_button(lua, G, pins)
    ns.Nav.Clear()


@pytest.fixture
def wm(game):
    lua, ns = game
    lua.execute(WM_SETUP)
    st = ns.settings.gps
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized", "style", "styleBeforeNone",
                              "navPanelDetached")}
    st.shown, st.minimized = True, None
    yield lua, ns
    ns.Nav.Clear()
    lua.execute("""
      for _, p in ipairs(AGPS_WM_PINS or {}) do p:SetParent(UIParent) p:Hide() end
      AGPS_WM_PINS = nil
      WorldMapFrame:Hide() ToggleWorldMap = nil
    """)
    for k, v in was.items():
        st[k] = v
    ns.GPS.WorldMapChanged()
    ns.GPS.ApplySettings()


def test_the_hud_is_over_every_icon_in_the_world_map(wm):
    lua, ns = wm
    G = ns.GPS
    _open_world_map(lua, ns)
    _world_map_checks(lua, ns, G)


@pytest.mark.parametrize("art_top", [2100, 9001])
def test_the_hud_is_over_every_icon_with_no_map(wm, art_top):
    """No Map over OpenMap's stitched map: our map up over OpenMap's art, the HUD over the icons. OpenMap puts its own
    frames at 9000 and more over the map: with its art that high, +WORLD_MAP_BUTTONS went past the old cap of 9000 and
    every button and the strip were flattened there, under the icons (Kooki3z's screenshot 2026-11-27)."""
    lua, ns = wm
    G = ns.GPS
    lua.execute(CANVAS + OPENMAP)
    lua.execute(f"OpenMapAPI.ArtTopLevel = function() return {art_top} end")
    levels = (2000, 2500, 2900) if art_top < 3000 else (art_top + 50, art_top + 200, art_top + 300)
    try:
        _open_world_map(lua, ns)
        assert G.SetStyle("none")
        lua.execute("AGPS_T = AGPS_T + 2")
        G.Update()
        assert G.NoMapOn()
        assert G.WorldMapLevel() > art_top
        _world_map_checks(lua, ns, G, levels, levels[-1] + 20)
    finally:
        lua.execute(UNDO)


# OpenMap v0.8.13's icons, as its code makes them (Map/Stitch.lua, read only): its pin root on the world map's scroll
# frame (the canvas's parent, "on the map's view, which clips them as the canvas does"), at the game's pin level it
# registers (PIN_FRAME_LEVEL_OPENMAP_ICONS); a set of pins per kind on it, each a few levels over it (S.PinSet: flight
# masters 2, routes 1, group 4, waypoints 5), cells of the world on each set, the pins in those at the set's level;
# its player arrow on a frame of its own on the pin root, lifted 8500 over the scroll frame (WorldMap.lua's
# RaisePlayer). Its own bars over the map: the coordinates at 9000 over the scroll frame (Extras.lua), which our
# buttons keep clear of by place.
OPENMAP_PINS = """
  local box = WorldMapFrame.ScrollContainer
  AGPS_OM_ICONS = {}
  local root = CreateFrame("Frame", nil, box)
  root:SetFrameLevel(2650)
  table.insert(AGPS_OM_ICONS, root)
  for _, over in ipairs({ 2, 1, 4, 5 }) do
    local set = CreateFrame("Frame", nil, root)
    set:SetFrameLevel(AGPS_LEVEL_OF(root) + over)
    local cell = CreateFrame("Frame", nil, set)
    cell:SetFrameLevel(AGPS_LEVEL_OF(set))
    for _ = 1, 3 do
      local pin = CreateFrame("Button", nil, cell)
      pin:SetFrameLevel(AGPS_LEVEL_OF(set))
      table.insert(AGPS_OM_ICONS, pin)
    end
    table.insert(AGPS_OM_ICONS, set)
  end
  AGPS_OM_ARROW = CreateFrame("Frame", nil, root)
  AGPS_OM_ARROW.agpsOverHud = true -- (lifted over everything by OpenMap on purpose: not an icon ours go over)
  AGPS_OM_ARROW:SetFrameLevel(math.min(AGPS_LEVEL_OF(box) + 8500, 9500) + 1)
  AGPS_OM_BAR = CreateFrame("Frame", nil, box)
  AGPS_OM_BAR:SetFrameLevel(math.min(AGPS_LEVEL_OF(box) + 9000, 9900))
"""


def test_the_hud_is_over_openmaps_own_icons_on_the_scroll_frame(wm):
    """Kooki3z 2026-11-27 for 1.4.2, No Map over OpenMap: "OpenMap elements on the map like flight masters and dungeons
    are on top of our buttons still". OpenMap's icons aren't in the world map's canvas but on its scroll frame, so they
    were over the whole canvas, our map and every button of ours in it, whatever our levels. The HUD goes onto the
    scroll frame over them while the map's there (the Map Menu, the quick buttons' flyouts, the layer buttons with
    it), each button the topmost mouse-taking frame at its place; the strip's X under OpenMap's own bars still; back
    on the map's own window after."""
    lua, ns = wm
    G = ns.GPS
    lua.execute(CANVAS + OPENMAP)
    try:
        _open_world_map(lua, ns)
        assert G.SetStyle("none")
        lua.execute(OPENMAP_PINS)
        _set_route(lua, ns)
        lua.execute("AGPS_T = AGPS_T + 2")
        G.Update()
        assert G.NoMapOn()
        box = lua.eval("WorldMapFrame.ScrollContainer")
        assert lua.eval("rawequal")(G.hudLayer._parent, box)
        icons = list(lua.eval("AGPS_OM_ICONS").values())
        _check(lua, G, icons, wm=True)
        level = lua.globals().AGPS_LEVEL_OF
        strip = G.mx.strip
        assert level(strip) > max(level(i) for i in icons) and level(strip) < level(strip.close) < 9000
        assert level(G.confirmRouteBtn) > max(level(i) for i in icons)
        assert level(lua.eval("AGPS_OM_ARROW")) > level(G.confirmRouteBtn)  # (its arrow over all, as OpenMap means)
        # (the Map Menu's pop-out, the search's panel, the path color list: on the HUD, over them)
        inside = lua.eval("""function(G, f)
          local n = 0
          while f and n < 30 do if f == G.hudLayer then return true end f, n = f._parent, n + 1 end
          return false
        end""")
        for name in ("mapMenu", "searchPanel", "pathColorList"):
            f = G[name]
            if f is not None:
                assert inside(G, f), name
        # (OpenMap's own bars over everything: not icons ours go over)
        assert level(lua.eval("AGPS_OM_BAR")) > level(G.confirmRouteBtn)
        # (more of OpenMap's pins later, higher: over them at the next look)
        lua.execute("""
          local p = CreateFrame("Button", nil, AGPS_OM_ICONS[1])
          p:SetFrameLevel(AGPS_LEVEL_OF(AGPS_OM_ICONS[1]) + 30)
          table.insert(AGPS_OM_ICONS, p)
        """)
        for _ in range(3):
            lua.execute("AGPS_T = AGPS_T + 1.5")
            G.WorldMapTick()
            G.Update()
        icons = list(lua.eval("AGPS_OM_ICONS").values())
        _check(lua, G, icons, wm=True)
        _buttons_over_the_strip_wm(lua, G)
        # (the world map closed: the HUD back on the map's own window, at its own level there)
        lua.globals().ToggleWorldMap()
        G.ApplySettings()
        assert not G.WorldMapHosted()
        assert lua.eval("rawequal")(G.hudLayer._parent, lua.eval("AzerothGPSFrame"))
        assert level(G.hudLayer) == level(G.Canvas()) + G.TOP_LEVEL
        _check(lua, G)
    finally:
        lua.execute("for _, f in ipairs(AGPS_OM_ICONS or {}) do f:SetParent(UIParent) f:Hide() end")
        lua.execute("if AGPS_OM_BAR then AGPS_OM_BAR:SetParent(UIParent) AGPS_OM_BAR:Hide() end")
        lua.execute(UNDO)
