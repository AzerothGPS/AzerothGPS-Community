"""Other addons' world map icons on the GPS map (OtherPins.lua, option otherAddonPins; asked 2026-11-09): a stand-in
HereBeDragons-Pins library (its registry tables and Add/Remove functions, as the real one keeps them) and Zygor's
waypoint list, the map redrawn under the game's Lua 5.1 with the UI stand-in (wowmock.lua)."""

import time

import pytest


# A stand-in HereBeDragons-Pins-2.0 (the fields and functions OtherPins reads): world coordinates as the library's own,
# x = west (UnitPosition's second value), y = north (its first); a real hooksecurefunc for tables while it's found.
STANDIN = r"""
LibStub = { libs = {}, minors = {} }
local function NewPins(name)
  local lib = { worldmapPins = {}, worldmapPinRegistry = {}, minimapPins = {}, minimapPinRegistry = {} }
  function lib:AddWorldMapIconWorld(ref, icon, instanceID, x, y, showFlag)
    self.worldmapPinRegistry[ref] = self.worldmapPinRegistry[ref] or {}
    self.worldmapPinRegistry[ref][icon] = true
    self.worldmapPins[icon] = { instanceID = instanceID, x = x, y = y, worldMapShowFlag = showFlag or 0 }
    return true
  end
  -- (the map version: a zone's 0-1 position to world yards as HereBeDragons does it, its map data from the
  -- client's map bounds: left = the west edge, top = the north edge)
  function lib:AddWorldMapIconMap(ref, icon, uiMapID, u, v, showFlag)
    local b = AGPS_NS.Maps[uiMapID].bounds
    local width, height, left, top = b[4] - b[2], b[3] - b[1], b[4], b[3]
    self:AddWorldMapIconWorld(ref, icon, AGPS_NS.Maps[uiMapID].continent, left - width * u, top - height * v, showFlag)
    self.worldmapPins[icon].uiMapID = uiMapID
    return true
  end
  function lib:RemoveWorldMapIcon(ref, icon)
    if self.worldmapPinRegistry[ref] then self.worldmapPinRegistry[ref][icon] = nil end
    self.worldmapPins[icon] = nil
  end
  function lib:RemoveAllWorldMapIcons(ref)
    for icon in pairs(self.worldmapPinRegistry[ref] or {}) do self.worldmapPins[icon] = nil end
    self.worldmapPinRegistry[ref] = {}
  end
  LibStub.libs[name] = lib
  return lib
end
AGPS_HBD = NewPins("HereBeDragons-Pins-2.0")
AGPS_HBDQ = NewPins("HereBeDragonsQuestie-Pins-2.0")
local mockHook = hooksecurefunc
hooksecurefunc = function(t, name, fn)
  local o = t[name]
  t[name] = function(...) local a, b, c = o(...) fn(...) return a, b, c end
end
AGPS_NS.OtherPins.Discover()
hooksecurefunc = mockHook
-- An icon frame as map addons make them: a button with its main texture in a field.
function AGPS_ICON(tex, field)
  local f = CreateFrame("Button", nil, UIParent)
  local t = f:CreateTexture(nil, "OVERLAY")
  t:SetTexture(tex)
  f[field or "texture"] = t
  f.IsMouseClickEnabled = function() return true end -- (the game's: a button takes clicks)
  return f
end
"""


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute(STANDIN)
    return lua, ns


@pytest.fixture
def g(game):
    lua, ns = game
    lua.execute("""
      for _, lib in ipairs({ AGPS_HBD, AGPS_HBDQ }) do
        for k in pairs(lib.worldmapPins) do lib.worldmapPins[k] = nil end
        for k in pairs(lib.worldmapPinRegistry) do lib.worldmapPinRegistry[k] = nil end
        for k in pairs(lib.minimapPinRegistry) do lib.minimapPinRegistry[k] = nil end
      end
      ZygorGuidesViewer = nil
      AGPS_NS.OtherPins.index = nil
      AGPS_NS.OtherPins.zygorAt = nil
    """)
    ns.Nav.Clear()
    ns.GPS.Follow()  # (a right-click let through to the map zooms it out: back to following the player)
    st = ns.settings.gps
    st.otherAddonPins = None
    st.zoom = 524
    lua.execute("AGPS_POS = { 2254.0, 293.0, 0 }")
    yield lua, ns
    st.otherAddonPins = None


_T = [1000.0]


def _redraw(lua, ns, step=2.0):
    """The map redrawn with time on (past REINDEX_MIN) and its icons gathered again."""
    _T[0] += step
    lua.execute(f"AGPS_T = {_T[0]}")
    ns.GPS.Redraw()
    ns.GPS.Update()


def _copies(lua):
    return [b for b in lua.eval("AGPS_NS.OtherPins.copies").values() if b._shown]


def _copy_of(lua, icon):
    n = lua.eval("""function(icon) local n, hit = 0
      for _, b in ipairs(AGPS_NS.OtherPins.copies) do if b._shown and b.orig == icon then n, hit = n + 1, b end end
      return n, hit end""")(icon)
    assert n[0] <= 1 if isinstance(n, tuple) else True
    return n[1] if isinstance(n, tuple) else None


def _pt(w):
    return w._pt[4], w._pt[5]  # ("CENTER", layer, "CENTER", dx, dy) -> dx, dy


def test_a_pin_is_drawn_where_azerothgps_draws_the_same_spot(g):
    # the library's world x, y are AzerothGPS's y, x: a pin at the player's spot as HereBeDragons gives it
    # (GetPlayerWorldPosition: UnitPosition's second value, then its first) lands on an AzerothGPS pin put there
    lua, ns = g
    P = ns.Pins
    ref = P.Add(lua.eval("{ level = 0, x = 2254 + 60, y = 293 - 40, name = 'Mine', icon = 136777 }"))
    try:
        icon = lua.eval("AGPS_ICON(136001)")
        lua.globals().AGPS_HBD.AddWorldMapIconWorld(lua.globals().AGPS_HBD, "Questie", icon, 0, 293 - 40, 2254 + 60, 1)
        _redraw(lua, ns)
        c = _copy_of(lua, icon)
        mine = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.pin is not None and w.pin.name == "Mine"]
        assert c and len(mine) == 1
        (cx, cy), (mx, my) = _pt(c), _pt(mine[0])
        assert abs(cx - mx) <= 1 and abs(cy - my) <= 1  # (the pin's on whole pixels)
        assert (cx, cy) != (0, 0)
        assert c.tex._tex == 136001  # (its own look)
        assert c.wx == 2254 + 60 and c.wy == 293 - 40 and c.cont == 0
    finally:
        P.Remove(ref)


def test_a_zone_pin_lands_where_a_way_line_for_that_spot_goes(g):
    # a pin by a zone's 0-1 position (AddWorldMapIconMap, as Questie, RestedXP and TomTom add theirs) is drawn at the
    # world spot Import.ToStop makes of the same /way (Tirisfal Glades 61.0, 52.0: by Brill)
    lua, ns = g
    icon = lua.eval("AGPS_ICON(136002)")
    hbd = lua.globals().AGPS_HBD
    hbd.AddWorldMapIconMap(hbd, "TomTom", icon, 1420, 0.61, 0.52, 3)
    _redraw(lua, ns)
    stop = ns.Import.ToStop(lua.eval("{ mapID = 1420, x = 61.0, y = 52.0 }"))
    c = _copy_of(lua, icon)
    assert c and abs(c.wx - stop.x) < 1e-6 and abs(c.wy - stop.y) < 1e-6 and stop.cont == 0
    # (and at that spot on the screen: the map's own projection of it)
    li = ns.GPS.laidIcons
    dx, dy = ns.Geo.ScreenOffset(li.x, li.y, stop.x, stop.y)
    dx, dy = ns.Geo.Rotate(dx * li.s, dy * li.s, li.rot)
    assert abs(_pt(c)[0] - dx) < 1e-6 and abs(_pt(c)[1] - dy) < 1e-6


def test_out_of_view_pins_arent_drawn_and_removed_ones_go(g):
    lua, ns = g
    hbd = lua.globals().AGPS_HBD
    near = lua.eval("AGPS_ICON(136003)")
    far = lua.eval("AGPS_ICON(136004)")
    hbd.AddWorldMapIconWorld(hbd, "RXP", near, 0, 293 + 30, 2254, 0)
    hbd.AddWorldMapIconWorld(hbd, "RXP", far, 0, 293 + 6000, 2254, 0)
    _redraw(lua, ns)
    assert _copy_of(lua, near) and not _copy_of(lua, far)
    v = lua.eval("AGPS_NS.OtherPins.version")
    hbd.RemoveWorldMapIcon(hbd, "RXP", near)
    assert lua.eval("AGPS_NS.OtherPins.version") > v  # (the hook saw it)
    assert ns.OtherPins.Pending()  # (a quiet idle map redraws sooner)
    _redraw(lua, ns)
    assert not _copy_of(lua, near) and not _copies(lua)
    # (and a pin added is drawn at the next redraw past REINDEX_MIN, its signature changed: no forced redraw)
    hbd.AddWorldMapIconWorld(hbd, "RXP", near, 0, 293 + 30, 2254, 0)
    _T[0] += 2
    lua.execute(f"AGPS_T = {_T[0]}")
    ns.GPS.Update()
    assert _copy_of(lua, near)


def test_the_option_off_draws_none(g):
    lua, ns = g
    hbd = lua.globals().AGPS_HBD
    icon = lua.eval("AGPS_ICON(136005)")
    hbd.AddWorldMapIconWorld(hbd, "RXP", icon, 0, 293, 2254 + 20, 0)
    _redraw(lua, ns)
    assert _copy_of(lua, icon)
    ns.settings.gps.otherAddonPins = False
    _redraw(lua, ns)
    assert not _copies(lua)
    ns.settings.gps.otherAddonPins = True
    _redraw(lua, ns)
    assert _copy_of(lua, icon)


def test_own_and_hidden_and_faded_icons_arent_copied(g):
    lua, ns = g
    hbd = lua.globals().AGPS_HBD
    own = lua.eval("AGPS_ICON(136006)")
    hidden = lua.eval("AGPS_ICON(136007)")
    faded = lua.eval("AGPS_ICON(136008)")
    plain = lua.eval("AGPS_ICON(136009, 'icon')")  # (TomTom keeps it in .icon)
    hidden.hidden = True  # (Questie's FakeHide)
    lua.execute("""local f = ...; f.texture.GetVertexColor = function() return 1, 1, 1, 0 end""", faded)
    for ref, icon in (("AzerothGPS_StreetView", own), ("Questie", hidden), ("Questie", faded), ("TomTom", plain)):
        hbd.AddWorldMapIconWorld(hbd, ref, icon, 0, 293 + 10, 2254 + 10, 0)
    _redraw(lua, ns)
    assert [c.tex._tex for c in _copies(lua)] == [136009]


def test_zoomed_out_only_icons_meant_for_a_continent_show(g):
    lua, ns = g
    hbd = lua.globals().AGPS_HBD
    zone = lua.eval("AGPS_ICON(136010)")
    cont = lua.eval("AGPS_ICON(136011)")
    hbd.AddWorldMapIconWorld(hbd, "RXP", zone, 0, 293 + 40, 2254, 1)  # (its parent zone at most)
    hbd.AddWorldMapIconWorld(hbd, "RXP", cont, 0, 293 - 40, 2254, 2)  # (on the continent's map too)
    _T[0] += 2
    lua.execute(f"AGPS_T = {_T[0]}")
    ns.OtherPins.Stamp()
    lua.execute("""local OP = AGPS_NS.OtherPins
      OP.Draw(AGPS_NS.GPS.poiLayer, 2254, 293, 0, 0, 0.05, 300, 6000, "far")""")
    assert [c.tex._tex for c in _copies(lua)] == [136011]
    lua.execute("""AGPS_NS.OtherPins.Draw(AGPS_NS.GPS.poiLayer, 2254, 293, 0, 0, 0.05, 300, 6000, "near")""")
    assert sorted(c.tex._tex for c in _copies(lua)) == [136010, 136011]
    lua.execute("""AGPS_NS.OtherPins.Draw(AGPS_NS.GPS.poiLayer, 2254, 293, 0, 0, 0.05, 300, 6000, "none")""")
    assert not _copies(lua)


def test_the_cap_holds_nearest_first(g):
    lua, ns = g
    lua.execute("""
      local hbd = AGPS_HBD
      for i = 1, 1000 do
        local a = i * 2.39996
        local r = i * 0.25
        hbd:AddWorldMapIconWorld("Questie", AGPS_ICON(140000 + i), 0, 293 + r * math.sin(a), 2254 + r * math.cos(a), 0)
      end
    """)
    _redraw(lua, ns)
    OP = ns.OtherPins
    shown = _copies(lua)
    assert len(shown) == OP.MAX_DRAWN == OP.drawn
    # (nearest the view's middle first: the first 200 by distance, give or take the last ring of cells)
    worst = max(abs(c.wy - 293) + abs(c.wx - 2254) for c in shown)
    assert worst < 400


def test_a_big_registry_redraws_within_a_frame_budget(g):
    # Questie can have thousands of icons: indexing them is done only when the registry changed (at most every
    # REINDEX_MIN), a gather looks only at the cells round the view, and a redraw with nothing changed gathers nothing
    lua, ns = g
    lua.execute("""
      local hbd = AGPS_HBDQ
      for i = 1, 5000 do
        local x, y = -4000 + (i * 7919) % 8000, -3000 + (i * 104729) % 9000
        hbd:AddWorldMapIconWorld("Questie", AGPS_ICON(150000 + i % 50), i % 2, y, x, 1)
      end
    """)
    OP = ns.OtherPins
    _redraw(lua, ns)  # (the map's own first redraw, its setup, out of the timing)
    lua.execute("AGPS_NS.OtherPins.index = nil")
    _T[0] += 2
    lua.execute(f"AGPS_T = {_T[0]}")
    t0 = time.perf_counter()
    OP.Stamp()
    index_ms = (time.perf_counter() - t0) * 1000
    assert OP.index.count == 5000
    _T[0] += 2
    lua.execute(f"AGPS_T = {_T[0]}")
    ns.GPS.Redraw()
    ns.GPS.Update()
    gather_ms = ns.perf["redraw: other addons' icons"].last
    print(f"index 5000 pins: {index_ms:.1f} ms; gather: {gather_ms:.1f} ms; looked at {OP.scanned}, drawn {OP.drawn}")
    assert 0 < OP.scanned < 1000  # (only the cells round the view)
    assert index_ms < 60 and gather_ms < 16  # (Lua 5.1 under lupa; the game's is faster)
    lua.execute("AGPS_IX = AGPS_NS.OtherPins.index")
    scanned = OP.scanned
    _T[0] += 0.1
    lua.execute(f"AGPS_T = {_T[0]}")
    OP.scanned = -1
    ns.GPS.Update()  # (nothing changed: no indexing, the icons kept)
    assert lua.eval("AGPS_IX == AGPS_NS.OtherPins.index") and OP.scanned == -1
    assert scanned >= 0


def test_hover_and_clicks_reach_the_original_safely(g):
    lua, ns = g
    hbd = lua.globals().AGPS_HBD
    lua.execute("""
      AGPS_SEEN = {}
      local f = AGPS_ICON(136020)
      f:SetScript("OnEnter", function(self) AGPS_SEEN.enter = self GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText("Kill 10 boars") GameTooltip:Show() end)
      f:SetScript("OnLeave", function(self) AGPS_SEEN.leave = self end)
      f:SetScript("OnClick", function(self, button) AGPS_SEEN.click = button end)
      AGPS_OK = f
      local bad = AGPS_ICON(136021)
      bad:SetScript("OnEnter", function() error("boom") end)
      bad:SetScript("OnClick", function() error("boom") end)
      bad.ShouldButtonPassThrough = function(_, b) return b == "RightButton" end
      AGPS_BAD = bad
    """)
    ok, bad = lua.globals().AGPS_OK, lua.globals().AGPS_BAD
    hbd.AddWorldMapIconWorld(hbd, "Questie", ok, 0, 293 + 15, 2254, 0)
    hbd.AddWorldMapIconWorld(hbd, "Questie", bad, 0, 293 - 15, 2254, 0)
    _redraw(lua, ns)
    c, d = _copy_of(lua, ok), _copy_of(lua, bad)
    seen = lua.globals().AGPS_SEEN
    c._scripts.OnEnter(c)
    assert lua.eval("AGPS_SEEN.enter == AGPS_OK")  # (the original's own handler, on the original)
    c._scripts.OnClick(c, "LeftButton")
    assert seen.click == "LeftButton"
    c._scripts.OnClick(c, "RightButton")
    assert seen.click == "RightButton"
    c._scripts.OnLeave(c)
    assert lua.eval("AGPS_SEEN.leave == AGPS_OK")
    # (an addon's handler failing: caught, our own tooltip instead, no error out of the copy)
    d._scripts.OnEnter(d)
    tip = lua.globals().GameTooltip
    assert lua.eval("function(d) return GameTooltip._owner == d end")(d)
    d._scripts.OnClick(d, "LeftButton")
    d._scripts.OnClick(d, "RightButton")  # (let through to the map: its right-click)
    d._scripts.OnLeave(d)
    # (a protected frame is never called)
    lua.execute("AGPS_OK.IsProtected = function() return true end AGPS_SEEN.enter = nil")
    c._scripts.OnEnter(c)
    assert seen.enter is None
    # (double-click: a stop there)
    lua.execute("AGPS_OK.IsProtected = nil")
    real = ns.GPS.AddStopAt
    lua.execute("AGPS_STOP = nil")
    ns.GPS.AddStopAt = lua.eval("function(x, y, name, cont) AGPS_STOP = { x, y, name, cont } end")
    try:
        c._scripts.OnDoubleClick(c)
    finally:
        ns.GPS.AddStopAt = real
    st = lua.globals().AGPS_STOP
    assert st[1] == 2254 and st[2] == 293 + 15 and st[4] == 0


def test_an_addons_own_tooltip_is_moved_onto_the_copy(g):
    # (TomTom shows its waypoints' text in a tooltip of its own, anchored on its pin: hidden with the world map)
    lua, ns = g
    hbd = lua.globals().AGPS_HBD
    lua.execute("""
      AGPS_TT = AGPS_TT or CreateFrame("GameTooltip", "TomTomTooltip", UIParent)
      AGPS_TT:Hide()
      GameTooltip:Hide()
      local f = AGPS_ICON(136025, "icon")
      f:SetScript("OnEnter", function(self) AGPS_TT:SetOwner(self, "ANCHOR_BOTTOMLEFT") AGPS_TT:Show() end)
      f:SetScript("OnLeave", function() AGPS_TT:Hide() end)
      f.IsVisible = function() return false end
      AGPS_TF = f
    """)
    hbd.AddWorldMapIconWorld(hbd, "TomTom", lua.globals().AGPS_TF, 0, 293 + 5, 2254 + 5, 3)
    _redraw(lua, ns)
    c = _copy_of(lua, lua.globals().AGPS_TF)
    c._scripts.OnEnter(c)
    assert lua.eval("function(c) return AGPS_TT._shown and AGPS_TT._pts.BOTTOMLEFT[2] == c end")(c)
    assert not lua.eval("function(c) return GameTooltip._shown and GameTooltip._owner == c end")(c)  # (none of ours)
    c._scripts.OnLeave(c)
    assert not lua.globals().AGPS_TT._shown


QUESTIE_PIN = r"""
  local f = AGPS_ICON(136050)
  f.GetSize = function() return 16, 16 end
  f.texture.GetDrawLayer = function() return "OVERLAY", 0 end
  local glow = f:CreateTexture(nil, "OVERLAY", nil, -1)
  glow:SetTexture(136060)
  glow.GetDrawLayer = function() return "OVERLAY", -1 end
  glow.GetSize = function() return 16 * 1.13, 16 * 1.13 end
  glow.GetVertexColor = function() return 0.2, 0.9, 0.3, 1 end
  local overlay = f:CreateTexture(nil, "OVERLAY", nil, 1)
  overlay:SetTexture(136061)
  overlay:Hide()
  f.glowTexture, f.overlayTexture = glow, overlay
  f.GetRegions = function() return f.texture, overlay, glow end
  f.data = { Type = "monster", ObjectiveData = { Color = { 0.8, 0.1, 0.6 } } }
  return f
"""


def _extras(c):
    return [e for e in (c.extras or {}).values() if e._shown]


def test_questies_glow_comes_with_its_icon(g):
    # (the user's test, 2026-11-10: Questie's objective icons have a soft glow in their quest's color under them on the
    # world map; the copies were bare dots) the icon's other textures come along: their art, color, size and layer
    lua, ns = g
    hbd = lua.globals().AGPS_HBDQ
    shown = lua.execute("return (function() " + QUESTIE_PIN + " end)()")
    hbd.AddWorldMapIconWorld(hbd, "Questie", shown, 0, 293 + 12, 2254, 1)
    plain = lua.eval("AGPS_ICON(136051)")
    hbd.AddWorldMapIconWorld(hbd, "Questie", plain, 0, 293 - 12, 2254, 1)
    _redraw(lua, ns)
    c = _copy_of(lua, shown)
    ex = _extras(c)
    assert len(ex) == 1  # (the glow; the hidden overlay isn't)
    glow = ex[0]
    assert glow._tex == 136060 and glow._vc == "0.20,0.90,0.30"
    assert glow._layer == "OVERLAY" and glow._sub == -1 and c.tex._layer == "OVERLAY" and c.tex._sub == 0  # (under it)
    assert abs(glow._w / c._w - 1.13) < 1e-6 and abs(glow._h / c._h - 1.13) < 1e-6  # (scaled with the icon)
    assert lua.eval("function(e, c) return e._pt[2] == c end")(glow, c) and glow._pt[4] == 0 and glow._pt[5] == 0
    assert not _extras(_copy_of(lua, plain))  # (an icon without one: no extra layer)
    # (the world map closed: Questie's OnHide hid the glow; the copy still has the one its OnShow would show, in the
    # quest's color, with Questie's "always glow" option on, and none with it off)
    lua.execute("""Questie = { db = { profile = { alwaysGlowMap = true } } }""")
    lua.execute("local f = ...; f.glowTexture:Hide()", shown)
    _redraw(lua, ns)
    ex = _extras(_copy_of(lua, shown))
    assert len(ex) == 1 and ex[0]._vc == "0.80,0.10,0.60" and abs(ex[0]._w / _copy_of(lua, shown)._w - 1.13) < 1e-6
    lua.execute("Questie.db.profile.alwaysGlowMap = false")
    _redraw(lua, ns)
    assert not _extras(_copy_of(lua, shown))
    lua.execute("Questie = nil")


def test_zygors_waypoints_show(g):
    lua, ns = g
    lua.execute("""
      local none = {}
      local f = AGPS_ICON(136030, "icon")
      ZygorGuidesViewer = { Pointer = { Icons = { none = none }, waypoints = {
        { m = 1420, x = 0.61, y = 0.52, overworld = true, icon = {}, frame_worldmap = f, title = "Brill" },
        { m = 1420, x = 0.62, y = 0.52, overworld = false, icon = {}, frame_worldmap = AGPS_ICON(136031, "icon") },
        { m = 1420, x = 0.60, y = 0.52, overworld = true, icon = none, frame_worldmap = AGPS_ICON(136032, "icon") },
      } } }
      AGPS_ZF = f
    """)
    _redraw(lua, ns)
    shown = _copies(lua)
    assert [c.tex._tex for c in shown] == [136030]
    stop = ns.Import.ToStop(lua.eval("{ mapID = 1420, x = 61.0, y = 52.0 }"))
    assert abs(shown[0].wx - stop.x) < 1e-6 and abs(shown[0].wy - stop.y) < 1e-6 and shown[0].title == "Brill"
    lua.execute("ZygorGuidesViewer.Pointer.waypoints[1] = nil ZygorGuidesViewer.Pointer.waypoints = {}")
    _redraw(lua, ns)
    assert not _copies(lua)


def test_the_minimap_square_leaves_out_what_the_games_minimap_shows(g):
    # (1.2.0's minimap mode: the game's minimap shows an addon's own minimap icons over the square)
    lua, ns = g
    hbd = lua.globals().AGPS_HBD
    both = lua.eval("AGPS_ICON(136040)")
    world = lua.eval("AGPS_ICON(136041)")
    hbd.AddWorldMapIconWorld(hbd, "Questie", both, 0, 293 + 10, 2254, 0)
    hbd.AddWorldMapIconWorld(hbd, "Other", world, 0, 293 - 10, 2254, 0)
    lua.execute("AGPS_HBD.minimapPinRegistry.Questie = { [AGPS_ICON(1)] = true }")
    # (stubbed, never deleted: on main there's none yet, with 1.2.0's minimap replacement GPSFrame calls the real one)
    orig = ns.GPS.MinimapMode
    try:
        ns.GPS.MinimapMode = lua.eval("function() return true end")
        _redraw(lua, ns)
        assert [c.tex._tex for c in _copies(lua)] == [136041]
        ns.GPS.MinimapMode = lua.eval("function() return false end")
        _redraw(lua, ns)
        assert len(_copies(lua)) == 2
    finally:
        ns.GPS.MinimapMode = orig


def test_the_option_is_on_the_map_page():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Options.lua").read_text(encoding="utf-8")
    assert "Show other addons' map icons" in src and "otherAddonPins" in src


def test_a_tooltip_owned_by_the_hidden_original_shows_on_the_copy(g):
    # (reported 2026-11-12: Questie's icons said "Another addon's map icon". Questie owns its tooltip by its own
    # icon, hidden with the world map, and the game shows no tooltip whose owner is hidden: it's given the copy.)
    lua, ns = g
    hbd = lua.globals().AGPS_HBDQ
    lua.execute("""
      AGPS_MOCKHOOK = hooksecurefunc
      hooksecurefunc = function(t, name, fn)
        local o = t[name]
        t[name] = function(...) local a, b, c = o(...) fn(...) return a, b, c end
      end
      AGPS_NS.OtherPins.hooked = {}
      AGPS_REALSHOW = GameTooltip.Show
      GameTooltip.Show = function(self)  -- (the game's: a hidden owner, no tooltip)
        local o = self._owner
        if o and o.IsVisible and not o:IsVisible() then self._shown = false return end
        AGPS_REALSHOW(self)
      end
      GameTooltip:Hide()
      local f = AGPS_ICON(136070)
      f.IsVisible = function() return false end
      f:SetScript("OnEnter", function(self) GameTooltip:SetOwner(self, "ANCHOR_CURSOR")
        GameTooltip:SetText("Quest: The Sleeping Bag") GameTooltip:Show() end)
      f:SetScript("OnLeave", function() GameTooltip:Hide() end)
      AGPS_QF = f
    """)
    try:
        hbd.AddWorldMapIconWorld(hbd, "Questie", lua.globals().AGPS_QF, 0, 293 - 25, 2254 + 5, 3)
        _redraw(lua, ns)
        c = _copy_of(lua, lua.globals().AGPS_QF)
        c._scripts.OnEnter(c)
        assert lua.eval("function(c) return GameTooltip._shown and GameTooltip._owner == c end")(c)
        assert lua.eval("GameTooltip._text") == "Quest: The Sleeping Bag"  # (not ours)
        assert ns.OtherPins.entering is None
        c._scripts.OnLeave(c)
        assert not lua.globals().GameTooltip._shown
        # (outside a copy's hover nothing is changed: an owner hidden elsewhere stays)
        lua.execute("AGPS_HID = CreateFrame('Frame') AGPS_HID.IsVisible = function() return false end GameTooltip:SetOwner(AGPS_HID)")
        assert lua.eval("GameTooltip._owner == AGPS_HID")
    finally:
        lua.execute("GameTooltip.Show = AGPS_REALSHOW hooksecurefunc = AGPS_MOCKHOOK GameTooltip:Hide()")


def test_questies_tooltip_lists_the_hovered_icon_wherever_the_world_map_is(g):
    # (reported 2026-11-12: on the GPS map Questie's icons still said "Another addon's map icon": Questie lists the icons
    # its world map has as pins, none with that map closed. Its own call with an owner and icons lists those given.)
    lua, ns = g
    hbd = lua.globals().AGPS_HBDQ
    lua.execute("""
      AGPS_QCALL = nil
      QuestieLoader = { ImportModule = function(_, name)
        if name ~= "MapIconTooltip" then return nil end
        return { ShowOnTooltip = function(icon, tip, owner, icons)
          AGPS_QCALL = { icon = icon, owner = owner, n = #icons, first = icons[1] }
          tip:SetOwner(owner, "ANCHOR_CURSOR") tip:SetText("[19] Goblin Invaders") tip:Show()
        end }
      end }
      GameTooltip:Hide()
      local f = AGPS_ICON(136080)
      f:SetScript("OnEnter", function() error("the world map's listing should not be used") end)
      AGPS_QI = f
      local f2 = AGPS_ICON(136081)
      AGPS_QI2 = f2
    """)
    try:
        hbd.AddWorldMapIconWorld(hbd, "Questie", lua.globals().AGPS_QI, 0, 293 - 40, 2254 - 20, 3)
        hbd.AddWorldMapIconWorld(hbd, "Questie", lua.globals().AGPS_QI2, 0, 293 - 40, 2254 - 20.5, 3)
        _redraw(lua, ns)
        c = _copy_of(lua, lua.globals().AGPS_QI)
        c._scripts.OnEnter(c)
        call = lua.globals().AGPS_QCALL
        assert call is not None and lua.eval("function(c) return AGPS_QCALL.owner == c and AGPS_QCALL.icon == AGPS_QI end")(c)
        assert call.n == 2  # (the other Questie icon at its spot too)
        assert lua.eval("function(c) return GameTooltip._shown and GameTooltip._owner == c end")(c)
        assert lua.eval("GameTooltip._text") == "[19] Goblin Invaders"
        # (without Questie's call: the icon's own OnEnter, as before)
        lua.execute("QuestieLoader = nil")
        c._scripts.OnEnter(c)
        assert "should not be used" in str(ns.OtherPins.lastError)
    finally:
        lua.execute("QuestieLoader = nil GameTooltip:Hide()")



def test_questies_icons_show_from_its_own_module_copy_of_the_library(g):
    # (reported 2026-11-14: Questie 12.9.0 keeps HereBeDragons-Pins as a module of its own, QuestieLoader._modules.HBDPins,
    # not in LibStub, and none of its icons showed on the GPS map)
    lua, ns = g
    lua.execute("""
      local lib = { worldmapPins = {}, worldmapPinRegistry = {}, minimapPins = {}, minimapPinRegistry = {} }
      for k, v in pairs(AGPS_HBD) do if type(v) == "function" then lib[k] = v end end
      QuestieLoader = { _modules = { HBDPins = lib } }
      AGPS_QMOD = lib
      local mockHook = hooksecurefunc
      hooksecurefunc = function(t, name, fn)
        local o = t[name]
        t[name] = function(...) local a, b, c = o(...) fn(...) return a, b, c end
      end
      AGPS_NS.OtherPins.Discover()
      AGPS_NS.OtherPins.Discover() -- (again at the next addon loaded: still one record)
      hooksecurefunc = mockHook
    """)
    try:
        n, questie = lua.eval("""(function() local n, q = 0, false
          for _, r in ipairs(AGPS_NS.OtherPins.libs) do if r.lib == AGPS_QMOD then n, q = n + 1, r.questie end end
          return n, q end)()""")
        assert n == 1 and questie
        lib = lua.globals().AGPS_QMOD
        icon = lua.eval("AGPS_ICON(136002)")
        lib.AddWorldMapIconWorld(lib, "Questie", icon, 0, 293 - 30, 2254 + 30, 1)
        _redraw(lua, ns)
        c = _copy_of(lua, icon)
        assert c and c.tex._tex == 136002
    finally:
        lua.execute("""QuestieLoader = nil
          local OP = AGPS_NS.OtherPins
          for i = #OP.libs, 1, -1 do if OP.libs[i].lib == AGPS_QMOD then OP.byLib[AGPS_QMOD] = nil table.remove(OP.libs, i) end end
          OP.index = nil""")


# A stand-in for the game's world map canvas (Blizzard_MapCanvas' MapCanvasMixin, the fields and functions OtherPins
# reads): `pinPools` (template -> pool, `EnumerateActive`), `GetMapID`, and `AcquirePin`/`RemovePin` making and dropping
# pins whose `GetPosition` is their 0-1 spot on that map; each pin's OnEnter is its OnMouseEnter and its OnMouseUp the
# canvas's, as AcquirePin sets them. AcquirePin here takes (template, texture, u, v, size, HereBeDragons' icon).
CANVAS = r"""
  local wm = WorldMapFrame
  wm.pinPools, wm.mapID = {}, 1420
  wm.GetMapID = function(self) return self.mapID end
  wm.AcquirePin = function(self, tmpl, tex, u, v, size, icon)
    local pool = self.pinPools[tmpl]
    if not pool then
      pool = { active = {} }
      pool.EnumerateActive = function(p) return pairs(p.active) end
      self.pinPools[tmpl] = pool
    end
    local pin = CreateFrame("Frame", nil, UIParent)
    pin.pinTemplate, pin.normalizedX, pin.normalizedY, pin.icon = tmpl, u, v, icon
    pin.GetPosition = function(p) return p.normalizedX, p.normalizedY end
    pin.GetSize = function() return size or 20, size or 20 end
    if tex then
      pin.Icon = pin:CreateTexture(nil, "ARTWORK")
      pin.Icon:SetTexture(tex)
    end
    pin.OnMouseEnter = function(p) AGPS_SEEN.enter = p end
    pin:SetScript("OnEnter", pin.OnMouseEnter)
    pin:SetScript("OnMouseUp", function(p, button, inside) AGPS_SEEN.up = { button, inside } end)
    pin.ShouldMouseButtonBePassthrough = function() return false end
    pin.IsMouseClickEnabled = function() return true end
    pin:Show()
    pool.active[pin] = true
    return pin
  end
  wm.RemovePin = function(self, pin) self.pinPools[pin.pinTemplate].active[pin] = nil pin:Hide() end
  wm.RemoveAllPinsByTemplate = function(self, tmpl)
    for pin in pairs((self.pinPools[tmpl] or { active = {} }).active) do self:RemovePin(pin) end
  end
  wm.OnMapChanged = function() end
  AGPS_SEEN = {}
  local mockHook = hooksecurefunc
  hooksecurefunc = function(t, name, fn)
    local o = t[name]
    t[name] = function(...) local a, b, c = o(...) fn(...) return a, b, c end
  end
  AGPS_NS.OtherPins.Discover()
  hooksecurefunc = mockHook
"""

CANVAS_OFF = r"""
  local wm = WorldMapFrame
  for _, k in ipairs({ "pinPools", "mapID", "GetMapID", "AcquirePin", "RemovePin", "RemoveAllPinsByTemplate",
    "OnMapChanged" }) do wm[k] = nil end
  wm:Show()
  issecurevariable = nil
  local OP = AGPS_NS.OtherPins
  OP.canvas, OP.canvasAt, OP.canvasRead = {}, nil, nil
  OP.canvasHooked[wm] = nil
"""


def test_every_addons_world_map_pins_show(g):
    # (asked 2026-11-14: "it should be for all addon map overlays to show on the gps map too just like the world map")
    # an addon's own pin template on the game's world map (DungeonQuestAtlas' markers, through its data provider) is
    # copied at its spot; the game's own pins, an overlay over the whole map, and HereBeDragons' pins of a library
    # already read are not; a HereBeDragons pin of a copy found nowhere else brings its icon
    lua, ns = g
    lua.execute(CANVAS)
    try:
        lua.execute("WorldMapFrame:Hide()")  # (closed: its pins stay, for the map it last showed)
        lua.execute("""
          local wm = WorldMapFrame
          AGPS_DQA = wm:AcquirePin("DungeonQuestAtlasPinTemplate", 136090, 0.61, 0.52)
          wm:AcquirePin("QuestPinTemplate", 136091, 0.605, 0.52)
          wm:AcquirePin("ShortestPathForeverRoutePinTemplate", 136092, 0.61, 0.53, 1000)
          AGPS_KNOWN = AGPS_ICON(136093)
          AGPS_HBD:AddWorldMapIconWorld("TomTom", AGPS_KNOWN, 0, 293 + 20, 2254 - 20, 0)
          wm:AcquirePin("HereBeDragonsPinsTemplate", nil, 0.60, 0.51, 1, AGPS_KNOWN)
          AGPS_LOOSE = AGPS_ICON(136094)
          wm:AcquirePin("HereBeDragonsPinsTemplateSomeAddon", nil, 0.615, 0.525, 1, AGPS_LOOSE)
        """)
        _redraw(lua, ns)
        assert sorted(c.tex._tex for c in _copies(lua)) == [136090, 136093, 136094]
        known = lua.eval("""(function() local n = 0
          for _, b in ipairs(AGPS_NS.OtherPins.copies) do if b._shown and b.orig == AGPS_KNOWN then n = n + 1 end end
          return n end)()""")
        assert known == 1  # (copied once, from its library)
        dqa = lua.globals().AGPS_DQA
        c = _copy_of(lua, dqa)
        stop = ns.Import.ToStop(lua.eval("{ mapID = 1420, x = 61.0, y = 52.0 }"))
        assert abs(c.wx - stop.x) < 1e-6 and abs(c.wy - stop.y) < 1e-6 and c.cont == 0
        li = ns.GPS.laidIcons
        dx, dy = ns.Geo.ScreenOffset(li.x, li.y, stop.x, stop.y)
        dx, dy = ns.Geo.Rotate(dx * li.s, dy * li.s, li.rot)
        assert abs(_pt(c)[0] - dx) < 1e-6 and abs(_pt(c)[1] - dy) < 1e-6
        # hover and clicks reach the pin as the world map's would: its OnMouseEnter, the canvas's mouse-up (inside)
        seen = lua.globals().AGPS_SEEN
        c._scripts.OnEnter(c)
        assert lua.eval("AGPS_SEEN.enter == AGPS_DQA")
        c._scripts.OnClick(c, "LeftButton")
        assert seen.up[1] == "LeftButton" and seen.up[2] is True
        c._scripts.OnClick(c, "RightButton")  # (the pin takes it: ShouldMouseButtonBePassthrough says no)
        assert seen.up[1] == "RightButton"
        c._scripts.OnLeave(c)
        # removed from the world map: gone from the GPS map (the canvas's RemovePin hooked)
        v = lua.eval("AGPS_NS.OtherPins.canvasVersion")
        lua.execute("WorldMapFrame:RemovePin(AGPS_DQA)")
        assert lua.eval("AGPS_NS.OtherPins.canvasVersion") > v
        assert ns.OtherPins.Pending()
        _redraw(lua, ns)
        assert not _copy_of(lua, dqa)
        assert sorted(c.tex._tex for c in _copies(lua)) == [136093, 136094]
    finally:
        lua.execute(CANVAS_OFF)


def test_world_map_pins_the_game_placed_and_zone_pins_zoomed_out_arent_copied(g):
    lua, ns = g
    lua.execute(CANVAS)
    try:
        lua.execute("""
          issecurevariable = function(t, k) return k == "pinTemplate" and t.agpsSecure == true end
          local wm = WorldMapFrame
          local p = wm:AcquirePin("SomeNewMapPinTemplate", 136095, 0.61, 0.52)
          p.agpsSecure = true  -- (the game's own code set it: a Blizzard pin by a template not listed)
          AGPS_ZONEPIN = wm:AcquirePin("SomeAddonPinTemplate", 136096, 0.612, 0.522)
        """)
        _redraw(lua, ns)
        assert [c.tex._tex for c in _copies(lua)] == [136096]
        # zoomed out a zone's pins aren't shown ...
        lua.execute("""AGPS_NS.OtherPins.Draw(AGPS_NS.GPS.poiLayer, 2254, 293, 0, 0, 0.05, 300, 6000, "far")""")
        assert not _copies(lua)
        # ... a continent's are: the world map on the Eastern Kingdoms (its map changed: read again)
        lua.execute("""
          local wm = WorldMapFrame
          wm:RemoveAllPinsByTemplate("SomeAddonPinTemplate")
          wm:RemoveAllPinsByTemplate("SomeNewMapPinTemplate")
          wm.mapID = 1415
          wm:OnMapChanged()
          local b = AGPS_NS.Maps[1415].bounds
          local x, y = 2254 + 50, 293
          wm:AcquirePin("SomeAddonPinTemplate", 136097, (b[4] - y) / (b[4] - b[2]), (b[3] - x) / (b[3] - b[1]))
        """)
        _T[0] += 2
        lua.execute(f"AGPS_T = {_T[0]}")
        ns.OtherPins.Stamp()
        lua.execute("""AGPS_NS.OtherPins.Draw(AGPS_NS.GPS.poiLayer, 2254, 293, 0, 0, 0.05, 300, 6000, "far")""")
        shown = _copies(lua)
        assert [c.tex._tex for c in shown] == [136097]
        assert abs(shown[0].wx - (2254 + 50)) < 1e-6 and abs(shown[0].wy - 293) < 1e-6
        # (the whole world's map has no bounds: nothing from it)
        lua.execute("WorldMapFrame.mapID = 947 WorldMapFrame:OnMapChanged()")
        _redraw(lua, ns)
        assert not _copies(lua)
    finally:
        lua.execute(CANVAS_OFF)


def test_questies_tooltip_goes_by_the_crosshair_with_the_controller(g):
    # (asked 2026-11-17: "Questie icons for example seem to be random, can all tooltips go to crosshair": Questie anchors
    # its tooltip on the mouse pointer, which the controller doesn't move)
    lua, ns = g
    hbd = lua.globals().AGPS_HBDQ
    lua.execute("""
      QuestieLoader = { ImportModule = function(_, name)
        if name ~= "MapIconTooltip" then return nil end
        return { ShowOnTooltip = function(icon, tip, owner, icons)
          tip:SetOwner(owner, "ANCHOR_CURSOR") tip:SetText("[25] Souvenirs of Death") tip:Show()
        end }
      end }
      GameTooltip:Hide()
      AGPS_QP = AGPS_ICON(136090)
    """)
    try:
        hbd.AddWorldMapIconWorld(hbd, "Questie", lua.globals().AGPS_QP, 0, 293 - 40, 2254 - 20, 3)
        _redraw(lua, ns)
        c = _copy_of(lua, lua.globals().AGPS_QP)
        ns.Pad.used = True
        c._scripts.OnEnter(c)
        assert lua.eval("GameTooltip._anchor") == "ANCHOR_NONE"
        pt = lua.eval("GameTooltip._pts").BOTTOMLEFT
        assert pt is not None and lua.eval("function(c, p) return p[2] == c end")(c, pt) and pt[3] == "TOPRIGHT"
        # (the mouse in use: Questie's own anchor stays)
        ns.Pad.used = False
        c._scripts.OnEnter(c)
        assert lua.eval("GameTooltip._anchor") == "ANCHOR_CURSOR"
    finally:
        ns.Pad.used = False
        lua.execute("QuestieLoader = nil GameTooltip:Hide()")
