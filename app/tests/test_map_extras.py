"""Map extras from the walk grids (item 114, 1.4.1; Kooki3z 2026-11-26, the grid ideas), with the whole addon
(gameharness, MapExtras.lua):

(a) the route's height profile: a strip along the map's bottom, its climbs, drops and jumps, the player a dot on it,
    worked out once a route part, hidden when flat, short, off (option `heightProfile`) or on the minimap square;
(b) the jump landing preview: a planned jump hovered rings where it lands, its drop in yards and whether it hurts at the
    Safe drop setting (yards only: the player's health is secret);
(c) the floor picker: where the grids' floors stack (Undercity's, here), "+" and "-" pick the floor shown, starting on
    the floor the tracker reports; a floor picked drives the route's floor fade and a double-clicked stop's height.
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401

OPEN = (2000.0, 0.0)  # (Tirisfal's fields: no building, no cave, one floor)
UC = 10001  # (Undercity's own level)
UC_STACK = (1403.0, 435.0)  # (five floors over each other in Undercity's city grid: the sewers to the rings)


def _part(lua, pts, cont, fz=None, zs=None, kinds=None):
    flat = ", ".join(f"{v}" for p in pts for v in p)
    ks = ", ".join(str(k) for k in (kinds or [0] * (len(pts) - 1)))
    f = f", fz = {{ {', '.join(str(v) for v in fz)} }}" if fz else ""
    z = f", zs = {{ {', '.join(str(v) for v in zs)} }}" if zs else ""
    return lua.eval(f"{{ cont = {cont}, pts = {{ {flat} }}, kinds = {{ {ks} }}{f}{z}, stop = 1 }}")


def _route(lua, part, consumed=0):
    return lua.eval("function(p, c) return { parts = { p }, pts = p.pts, kinds = p.kinds, fullFirst = p, consumed = c } end")(
        part, consumed)


@pytest.fixture
def mx(game):  # noqa: F811
    lua, ns = game
    lua.execute("AGPS_NS.MapExtras.profileCache = setmetatable({}, { __mode = 'k' })")
    G = ns.GPS
    st = G.mx
    st.spot, st.pick, st.lookAt = None, None, None
    ns.Nav.ResetTrack()
    yield lua, ns
    st.spot, st.pick, st.lookAt = None, None, None
    ns.settings.gps.heightProfile = True
    ns.settings.gps.floorPicker = True
    lua.execute("AGPS_NS.Geo.override = nil")
    ns.Nav.ResetTrack()


# --- (a) the profile ------------------------------------------------------------------------------------------------

def test_a_route_up_and_down_has_its_climb_and_drop(mx):
    lua, ns = mx
    MX = ns.MapExtras
    # (up 30 yd over 60, flat, down 20 over 40)
    fz = [0, 10, 20, 30, 30, 30, 20, 10]
    p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
    pr = MX.Profile(p)
    assert pr is not None and pr.len == pytest.approx(140)
    assert pr.lo == 0 and pr.hi == 30
    assert pr.up == pytest.approx(30) and pr.down == pytest.approx(20)
    kinds = [pr.colKind[j] for j in range(1, MX.PROFILE_COLS + 1)]
    assert kinds[0] == "up" and kinds[-1] == "down" and "flat" in kinds and "jump" not in kinds
    assert len([pr.cols[j] for j in range(0, MX.PROFILE_COLS + 1)]) == MX.PROFILE_COLS + 1
    assert MX.ZAlong(pr.s, 30) == pytest.approx(15)


def test_a_flat_or_short_route_has_no_profile(mx):
    lua, ns = mx
    MX = ns.MapExtras
    flat = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(6)], 0, fz=[50, 51, 52, 51, 50, 52])
    assert MX.Profile(flat) is None
    short = _part(lua, [(OPEN[0], OPEN[1]), (OPEN[0] + 20, OPEN[1])], 0, fz=[0, 15])
    assert MX.Profile(short) is None
    # (a ride: no ground to show)
    ride = _part(lua, [(OPEN[0] + 100 * k, OPEN[1]) for k in range(4)], 0, fz=[0, 40, 80, 120], kinds=[2, 2, 2])
    assert MX.Profile(ride) is None


def test_a_jump_is_in_the_profile_with_its_drop(mx):
    lua, ns = mx
    MX, R = ns.MapExtras, ns.Router
    D = R.KIND_DROP
    fz = [40, 40, 40, 15, 15, 15]
    p = _part(lua, [(OPEN[0] + 15 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz, kinds=[0, 0, D, 0, 0])
    pr = MX.Profile(p)
    assert len(pr.jumps) == 1
    j = pr.jumps[1]
    assert j[1] == pytest.approx(30) and j[2] == pytest.approx(45)
    assert j[3] == 40 and j[4] == 15 and j[5] >= 25 - 1e-6 and j.kind == "drop"
    assert "jump" in [pr.colKind[k] for k in range(1, MX.PROFILE_COLS + 1)]
    # (a jump on flat ground still shows: no rise needed)
    fz2 = [10, 10, 10, 10, 10]
    p2 = _part(lua, [(OPEN[0] + 15 * k, OPEN[1]) for k in range(len(fz2))], 0, fz=fz2,
               kinds=[0, R.KIND_JUMP, 0, 0])
    assert MX.Profile(p2) is not None and MX.Profile(p2).jumps[1].kind == "jump"


def test_the_ground_fills_a_stretch_without_heights_once_and_within_its_budget(mx):
    lua, ns = mx
    MX = ns.MapExtras
    # (Brill to the Ruins of Lordaeron: the map's ground along it)
    p = _part(lua, [(2254.0, 293.0), (2000.0, 300.0), (1800.0, 250.0)], 0)
    before = MX.groundLooks
    pr = MX.Profile(p)
    looks = MX.groundLooks - before
    assert pr is not None and pr.hi - pr.lo >= MX.PROFILE_MIN_RISE
    assert 0 < looks <= MX.PROFILE_MAX_LOOKS + 2
    # (kept: the same part asks the ground no more)
    assert lua.eval("rawequal")(MX.Profile(p), pr) and MX.groundLooks - before == looks
    # (a very long one: still within the budget)
    far = _part(lua, [(2254.0, 293.0), (2254.0 - 3000, 293.0), (2254.0 - 3000, 293.0 + 3000)], 0)
    before = MX.groundLooks
    MX.Profile(far)
    assert MX.groundLooks - before <= MX.PROFILE_MAX_LOOKS + 3
    # (a level of its own without the route's heights: nothing guessed from the land over it)
    uc = _part(lua, [(UC_STACK[0] + 10 * k, UC_STACK[1]) for k in range(6)], UC)
    assert MX.Profile(uc) is None


def test_the_strip_shows_the_profile_and_the_dot_moves_along(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    fz = [0, 10, 20, 30, 30, 30, 20, 10]
    p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
    f = G.mx.strip
    MX.OnRedraw(G, _route(lua, p, 0), 0, OPEN[0], OPEN[1], 200)
    assert f._shown and G.mx.profile is not None
    shown = [l for l in f.lines.values() if l._shown]
    assert len(shown) == MX.PROFILE_COLS
    assert "Up 30 yd, down 20 yd" == f.text._text
    x0 = f.dotEdge._pt[4]
    MX.OnRedraw(G, _route(lua, p, 70), 0, OPEN[0], OPEN[1], 200)
    x1 = f.dotEdge._pt[4]
    assert x1 > x0
    # (the dot moved; the strip's lines weren't laid again)
    assert lua.eval("rawequal")(f.laid, G.mx.profile)
    # (in the player's units: Options > General's meters)
    ns.settings.gps.distanceUnits = "metric"
    try:
        MX.OnRedraw(G, _route(lua, p, 70), 0, OPEN[0], OPEN[1], 200)
        assert f.text._text == "Up 27 m, down 18 m"
        assert MX.HurtLine(25)[0] == "Some fall damage: within your safe drop (36 m)."
    finally:
        ns.settings.gps.distanceUnits = "yards"
    MX.OnRedraw(G, _route(lua, p, 70), 0, OPEN[0], OPEN[1], 200)
    assert f.text._text == "Up 30 yd, down 20 yd"
    # off: hidden; a flat route: hidden
    ns.settings.gps.heightProfile = False
    MX.OnRedraw(G, _route(lua, p, 70), 0, OPEN[0], OPEN[1], 200)
    assert not f._shown
    ns.settings.gps.heightProfile = True
    flat = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(6)], 0, fz=[50] * 6)
    MX.OnRedraw(G, _route(lua, flat), 0, OPEN[0], OPEN[1], 200)
    assert not f._shown
    # (never on the minimap square)
    assert MX.StripWanted(lua.eval("{ square = true }"), _route(lua, p)) is None


def test_the_map_redraws_with_the_strip_on_a_real_route(mx):
    """Brill up the hill to the Ruins of Lordaeron over the world grid (the players' default): the strip on the map,
    its heights the grid's; the Router's own route carries the inn's floor on over the land (`fz` 35.5 all the way),
    which the grid's surfaces put right (MX.Snap)."""
    lua, ns = mx
    G, N, MX = ns.GPS, ns.Nav, ns.MapExtras
    ns.settings.gps.worldGrid = True
    ns.Router.Reset()
    try:
        N.SetStops(lua.eval("{ { x = 1800, y = 250, cont = 0 } }"), False, "red")
        errors = len(ns.db.errors or {})
        for t in range(3):
            lua.execute(f"AGPS_T = {9000 + t}")
            G.Update()
        assert len(ns.db.errors or {}) == errors, ns.db.errors[len(ns.db.errors)].err
        assert N.route is not None
        p = G.mx.profile
        assert p is not None and G.mx.strip._shown
        assert p.hi - p.lo >= 8  # (the Ruins stand over Brill's fields)
        # the same route as the Router's own (the inn's floor carried on): snapped to the grid's ground
        flat = _part(lua, [(2254.0, 293.0), (2100.0, 160.0), (1930.0, 237.0)], 0, fz=[35.5, 35.5, 35.5])
        ns.WorldGrid.SurfacesAt(ns.WorldGrid.Cont(0), 1930.0, 237.0)  # (its tiles loaded, as a route there has them)
        ns.WorldGrid.SurfacesAt(ns.WorldGrid.Cont(0), 2100.0, 160.0)
        snapped = MX.BuildProfile(flat)
        assert snapped is not None and snapped.hi > 40
        N.Clear()
        G.Update()
        assert not G.mx.strip._shown
    finally:
        N.Clear()
        ns.settings.gps.worldGrid = False
        ns.Router.Reset()


# --- (a) the strip's close X (item 122) -----------------------------------------------------------------------------

def _click_x(lua, G, shift=False):
    lua.execute(f"AGPS_SHIFT_WAS = IsShiftKeyDown IsShiftKeyDown = function() return {'true' if shift else 'false'} end")
    try:
        b = G.mx.strip.close
        b.GetScript(b, "OnClick")(b, "LeftButton", False)
    finally:
        lua.execute("IsShiftKeyDown = AGPS_SHIFT_WAS")


def _stops(lua, *spots):
    return lua.eval("{ " + ", ".join(f"{{ x = {x}, y = {y}, cont = 0 }}" for x, y in spots) + " }")


def test_the_x_is_a_yellow_letter_in_the_top_right_clear_of_the_text(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    f = G.mx.strip
    b = f.close
    same = lua.eval("rawequal")
    assert b._kind == "Button" and same(b._parent, f)
    assert b._pts["TOPRIGHT"][1] == "TOPRIGHT" and b._w == MX.CLOSE_SIZE <= MX.STRIP_TEXT_H + 2
    assert b.x._text == "X"
    # (the text "Up 25 yd, down 96 yd" ends before it)
    assert same(f.text._pts["RIGHT"][2], b) and f.text._pts["RIGHT"][3] == "LEFT" and f.text._pts["TOPLEFT"] is not None
    # (subtle; lit under the mouse, with its tooltip)
    assert b._alpha == MX.CLOSE_ALPHA and not b.lit
    lua.execute("AGPS_TIP = {} local o = GameTooltip.AddLine GameTooltip.AddLine = function(s, t, ...) "
                "AGPS_TIP[#AGPS_TIP + 1] = t return o(s, t, ...) end AGPS_TIP_WAS = o")
    try:
        b.GetScript(b, "OnEnter")(b)
        assert b.lit and b._alpha == MX.CLOSE_LIT_ALPHA
        tip = [lua.eval("AGPS_TIP")[i] for i in range(1, len(lua.eval("AGPS_TIP")) + 1)]
        assert "Click: hide it for this route." in tip and "Shift-click: turn it off (Options > Map)." in tip
    finally:
        lua.execute("GameTooltip.AddLine = AGPS_TIP_WAS")
    b.GetScript(b, "OnLeave")(b)
    assert not b.lit and b._alpha == MX.CLOSE_ALPHA


def test_a_click_hides_the_strip_till_a_new_destination(mx):
    lua, ns = mx
    G, N, MX = ns.GPS, ns.Nav, ns.MapExtras
    fz = [0, 10, 20, 30, 30, 30, 20, 10]
    p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
    f = G.mx.strip
    try:
        N.SetStops(_stops(lua, (OPEN[0] + 140, OPEN[1])), False, "red")
        MX.OnRedraw(G, _route(lua, p), 0, OPEN[0], OPEN[1], 200)
        assert f._shown
        _click_x(lua, G)
        assert not f._shown and ns.settings.gps.heightProfile is not False
        MX.OnRedraw(G, _route(lua, p, 30), 0, OPEN[0], OPEN[1], 200)
        assert not f._shown
        # a reroute to the same stop (the route worked out again; the same stop set again): still hidden
        N.route = None
        N.SetStops(_stops(lua, (OPEN[0] + 140, OPEN[1])), False, "red")
        p2 = _part(lua, [(OPEN[0] + 20 * k, OPEN[1] + 1) for k in range(len(fz))], 0, fz=fz)
        MX.OnRedraw(G, _route(lua, p2), 0, OPEN[0], OPEN[1], 200)
        assert not f._shown
        # a new destination: back
        N.SetStops(_stops(lua, (OPEN[0] + 300, OPEN[1])), False, "red")
        MX.OnRedraw(G, _route(lua, p2), 0, OPEN[0], OPEN[1], 200)
        assert f._shown
        # a stop added to the route closed: back
        _click_x(lua, G)
        MX.OnRedraw(G, _route(lua, p2), 0, OPEN[0], OPEN[1], 200)
        assert not f._shown
        N.AddStop(lua.eval(f"{{ x = {OPEN[0] + 500}, y = {OPEN[1]}, cont = 0 }}"), False, "red")
        MX.OnRedraw(G, _route(lua, p2), 0, OPEN[0], OPEN[1], 200)
        assert f._shown
        # the route cleared and the same one set again: back
        _click_x(lua, G)
        MX.OnRedraw(G, _route(lua, p2), 0, OPEN[0], OPEN[1], 200)
        assert not f._shown
        N.Clear()
        N.SetStops(_stops(lua, (OPEN[0] + 300, OPEN[1]), (OPEN[0] + 500, OPEN[1])), False, "red")
        MX.OnRedraw(G, _route(lua, p2), 0, OPEN[0], OPEN[1], 200)
        assert f._shown
        # a stop reached (the rest of the same route): still hidden
        _click_x(lua, G)
        N.RemoveStop(1)  # (as Nav.CheckArrival takes a stop reached off)
        assert len(N.stops) == 1
        MX.OnRedraw(G, _route(lua, p2), 0, OPEN[0], OPEN[1], 200)
        assert not f._shown
    finally:
        N.Clear()
        MX.closed = None


def test_a_shift_click_turns_the_option_off_and_options_shows_it(mx):
    lua, ns = mx
    G, N, MX, O = ns.GPS, ns.Nav, ns.MapExtras, ns.Options
    fz = [0, 10, 20, 30, 30, 30, 20, 10]
    p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
    f = G.mx.strip
    O.Show()
    cb = next(c.control for c in O.settingControls.values() if c.key == "heightProfile" and not c.mirror)
    try:
        O.Refresh()
        assert cb.GetChecked(cb)
        N.SetStops(_stops(lua, (OPEN[0] + 140, OPEN[1])), False, "red")
        MX.OnRedraw(G, _route(lua, p), 0, OPEN[0], OPEN[1], 200)
        assert f._shown
        _click_x(lua, G, shift=True)
        assert not f._shown and ns.settings.gps.heightProfile is False
        assert not cb.GetChecked(cb)  # (the open options panel shows it off)
        # (off for every route now, a new destination too)
        N.SetStops(_stops(lua, (OPEN[0] + 300, OPEN[1])), False, "red")
        MX.OnRedraw(G, _route(lua, p), 0, OPEN[0], OPEN[1], 200)
        assert not f._shown
        # (turned on again in Options: it shows on this route)
        ns.settings.gps.heightProfile = True
        MX.OnRedraw(G, _route(lua, p), 0, OPEN[0], OPEN[1], 200)
        assert f._shown
    finally:
        N.Clear()
        MX.closed = None
        ns.settings.gps.heightProfile = True
        if O.IsShown():
            O.Toggle()


def test_the_x_works_in_the_world_map_too(mx):
    """The GPS map in the game's world map (Options > Map): the same map's strip, hidden by its X there, on a real
    route (Brill up to the Ruins of Lordaeron, as test_the_map_redraws_with_the_strip_on_a_real_route)."""
    from test_world_map_host import SETUP as WM_SETUP

    lua, ns = mx
    G, N, MX, st = ns.GPS, ns.Nav, ns.MapExtras, ns.settings.gps
    st.worldGrid = True
    ns.Router.Reset()
    lua.execute(WM_SETUP)
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        N.SetStops(lua.eval("{ { x = 1800, y = 250, cont = 0 } }"), False, "red")
        for t in range(3):
            lua.execute(f"AGPS_T = {9100 + t}")
            G.Update()
        assert N.route is not None and G.mx.strip._shown
        _click_x(lua, G)
        lua.execute("AGPS_T = 9110")
        G.Update()
        assert not G.mx.strip._shown and st.heightProfile is not False
        # (a new destination there: back)
        N.SetStops(lua.eval("{ { x = 1810, y = 240, cont = 0 } }"), False, "red")
        for t in range(3):
            lua.execute(f"AGPS_T = {9120 + t}")
            G.Update()
        if G.mx.profile is not None:
            assert G.mx.strip._shown
        assert MX.closed is None
    finally:
        N.Clear()
        MX.closed = None
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
        st.worldGrid = False
        ns.Router.Reset()


# --- (b) jumps ------------------------------------------------------------------------------------------------------

def test_the_hurt_line_goes_by_the_safe_drop_setting_in_yards(mx):
    lua, ns = mx
    MX = ns.MapExtras
    was = ns.settings.gps.safeDropYd
    try:
        ns.settings.gps.safeDropYd = 39
        assert MX.HurtLine(10)[0] == "No fall damage."
        assert MX.HurtLine(14)[0] == "No fall damage."
        assert MX.HurtLine(25)[0] == "Some fall damage: within your safe drop (39 yd)."
        assert MX.HurtLine(50)[0].startswith("Past your safe drop (39 yd)")
        ns.settings.gps.safeDropYd = 20
        assert MX.HurtLine(25)[0].startswith("Past your safe drop (20 yd)")
        assert MX.HurtLine(None) is None
        lua.execute("AGPS_GHOST = UnitIsGhost UnitIsGhost = function() return true end")
        try:
            assert MX.HurtLine(80)[0] == "No fall damage as a ghost."
        finally:
            lua.execute("UnitIsGhost = AGPS_GHOST")
    finally:
        ns.settings.gps.safeDropYd = was


def test_a_hovered_jump_says_where_it_lands_and_whether_it_hurts(mx):
    lua, ns = mx
    G, R = ns.GPS, ns.Router
    D = R.KIND_DROP
    fz = [40, 40, 40, 40, 15, 15]
    pts = [(OPEN[0] + 15 * k, OPEN[1]) for k in range(len(fz))]
    # (the drop in two pieces: a step off the rim, then the fall)
    p = _part(lua, pts, 0, fz=fz, kinds=[0, 0, D, D, 0])
    info = G.JumpInfo(lua.eval("function(p) return { part = p, i = 4 } end")(p))
    assert (info.landX, info.landY) == pts[4]  # (the run's foot: past its last piece)
    assert info.x == pts[2][0]  # (its top: the run's first piece)
    tip = G.JumpTip(info)
    lines = [tip.lines[i] for i in range(1, len(tip.lines) + 1)]
    assert any(line.startswith("Falls about") for line in lines)
    assert any("safe drop" in line or "No fall damage" in line for line in lines)
    assert "The ring on the map is where you land." in lines
    assert lines[-1].startswith("Right-click")  # (the hint stays last)
    # (a running jump with the route's heights: its drop from them)
    J = R.KIND_JUMP
    p2 = _part(lua, pts, 0, fz=[40, 40, 40, 31, 31, 31], kinds=[0, 0, J, 0, 0])
    info2 = G.JumpInfo(lua.eval("function(p) return { part = p, i = 3 } end")(p2))
    assert info2.kind == "jump" and info2.dz == pytest.approx(9)


def test_the_landing_ring_sits_on_the_jumps_foot_on_the_map(mx):
    lua, ns = mx
    G, MX, R = ns.GPS, ns.MapExtras, ns.Router
    D = R.KIND_DROP
    p = _part(lua, [(OPEN[0] + 15 * k, OPEN[1]) for k in range(6)], 0, fz=[40, 40, 40, 40, 15, 15], kinds=[0, 0, D, D, 0])
    was = G.jumpSegN
    try:
        G.jumpSegN = 0
        G.AddJumpSeg(10, 0, 20, 0, p, 3)
        G.AddJumpSeg(20, 0, 32, -4, p, 4)
        sg = G.jumpSegs[1]
        MX.ShowLanding(G, sg, lua.eval("{ dz = 25 }"))
        ring = G.mx.ring
        assert ring.shown and (ring.x, ring.y) == (32, -4)  # (the end of the run's last piece)
        assert all(l._shown for l in ring.lines.values())
        assert ring.label._text == "25 yd down"  # (Locales: "%s down")
        MX.ShowLanding(G, None)
        assert not ring.shown and not any(l._shown for l in ring.lines.values())
    finally:
        G.jumpSegN = was




# (each frame's level as the game has it: the one set, else one over its parent's; the stand-in's GetFrameLevel is 5
# whatever was set, so levels set from another's would all be 5 and a bit. Run before the addon's files load: every
# widget made after has it.)
_REAL_LEVELS = """
  AGPS_LEVEL_OF = function(w)
    local n = 0
    while w and not w._level and n < 50 do w, n = w._parent, n + 1 end
    return ((w and w._level) or 5) + n
  end
  local made = NewWidget
  NewWidget = function(...)
    local w = made(...)
    w.GetFrameLevel = AGPS_LEVEL_OF
    return w
  end
"""


def _ring_over_the_route(lua, G, MX):
    """The landing ring's label, its backing and its lines are on a frame over the route's lines and the stops' pins."""
    level = lua.eval("AGPS_LEVEL_OF")
    D = lua.eval("AGPS_NS.Router.KIND_DROP")
    p = _part(lua, [(OPEN[0] + 15 * k, OPEN[1]) for k in range(6)], 0, fz=[40, 40, 40, 40, 15, 15],
              kinds=[0, 0, D, D, 0])
    G.jumpSegN = 0
    G.AddJumpSeg(10, 0, 20, 0, p, 3)
    G.AddJumpSeg(20, 0, 32, -4, p, 4)
    MX.ShowLanding(G, G.jumpSegs[1], lua.eval("{ dz = 213 }"))
    ring = G.mx.ring
    route = level(G.lineLayer)
    for w in [ring.label, ring.back] + [ring.lines[k] for k in range(1, len(ring.lines) + 1)]:
        assert w is not None
        assert level(w["_parent"]) > route, (level(w["_parent"]), route)
        assert level(w["_parent"]) > level(G.keepLayer) + 2  # (the stops' pins: up to 2 over keepLayer)
    assert lua.eval("function(a, b) return a == b end")(ring.host, G.ringLayer)
    assert ring.label._text == "213 yd down" and ring.label._shown and ring.back._shown
    assert ring.back._tex.startswith("color:0.00,0.00,0.00")  # (a dark backing: readable over any line's color)
    # (off the coil: the jump's top is left of its foot, so the label's right of the ring; the other way, left)
    assert ring.side == "right" and ring.label._pts["LEFT"][3] == "CENTER" and ring.label._pts["LEFT"][4] > 32
    G.jumpSegN = 0
    G.AddJumpSeg(60, 0, 50, 0, p, 3)
    G.AddJumpSeg(50, 0, 38, -4, p, 4)
    MX.ShowLanding(G, G.jumpSegs[1], lua.eval("{ dz = 213 }"))
    assert ring.side == "left" and ring.label._pts["RIGHT"][4] < 38
    MX.ShowLanding(G, None)
    assert not ring.label._shown and not ring.back._shown


def test_the_landing_label_is_over_the_route_line_in_both_map_modes():
    """Kooki3z 2026-11-26 (item 131): "text is under the route, can't see it": the "213 yd down" by a spell jump's
    landing ring was on G.markLayer, a level under the route's lines. Over them (and the stops' pins), on a dark
    backing, in the GPS window and in the game's world map. (An addon of its own: the frames' levels as the game's.)"""
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    from test_world_map_host import SETUP as WM_SETUP

    lua, ns = start(pre=_REAL_LEVELS)
    G, st = ns.GPS, ns.settings.gps
    G.Update()
    _ring_over_the_route(lua, G, ns.MapExtras)
    # (the world map: the window's frames moved to its levels, each kept where it was over the window's own)
    lua.execute(WM_SETUP)
    st.shown, st.minimized, st.useWorldMap = True, None, True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()
    assert G.WorldMapHosted()
    lua.execute("AGPS_T = (AGPS_T or 0) + 0.5")
    G.Update()
    assert lua.eval("AGPS_LEVEL_OF")(G.ringLayer) > lua.eval("AGPS_LEVEL_OF")(G.lineLayer) > 100  # (moved up there)
    _ring_over_the_route(lua, G, ns.MapExtras)


# --- the map's buttons over the strip and the ring (item 134) -------------------------------------------------------

_BUTTONS_UNDER = """
  return function(G)
    local L = AGPS_LEVEL_OF
    local strip, ring = G.mx.strip, G.ringLayer
    local bad, n = {}, 0
    local own = AzerothGPSFrame:GetFrameStrata()
    local function Walk(f)
      for _, k in ipairs(f._kids or {}) do
        -- (a dropdown's list, the search's panel: in a strata of their own, over everything by that)
        if k ~= strip and not (k._strata and k._strata ~= own) then
          if k._kind == "Button" or k._kind == "CheckButton" then
            n = n + 1
            if L(k) <= L(strip) or L(k) <= L(ring) then
              bad[#bad + 1] = string.format("%s %s at %d (strip %d, ring %d)", k._kind, tostring(k._text), L(k),
                L(strip), L(ring))
            end
          end
          Walk(k)
        end
      end
    end
    Walk(G.topLayer)
    -- (the strip's own X over it)
    if L(strip.close) <= L(strip) then bad[#bad + 1] = "the X" end
    return n, table.concat(bad, "; ")
  end
"""


def _buttons_over_the_strip(lua, G):
    n, bad = lua.execute(_BUTTONS_UNDER)(G)
    assert n > 20, n  # (the map menu, search, the quick buttons, the floor bars' + and -, Clear Route, ...)
    assert bad == "", bad


def test_every_map_button_is_over_the_strip_and_the_ring_in_both_map_modes():
    """Kooki3z 2026-11-26 (item 134): "buttons should always go over this": the height profile strip (item 114) was
    at the buttons' level and the landing ring's layer (item 131) over them, so the strip's line showed through the
    round buttons. Every button on the map's button layer (search, the map menu, the quick buttons and their flyouts,
    the floor bars' + and -, Clear Route, the corner buttons) is over both, in the GPS window and in the world map;
    the ring still over the route's lines and the stops' pins."""
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    from test_world_map_host import SETUP as WM_SETUP

    lua, ns = start(pre=_REAL_LEVELS)
    G, st = ns.GPS, ns.settings.gps
    G.Update()
    level = lua.eval("AGPS_LEVEL_OF")
    strip = G.mx.strip
    assert lua.eval("rawequal")(strip._parent, G.topLayer) and level(strip) == level(G.topLayer)
    assert level(G.ringLayer) > level(G.keepLayer) + 2 and level(G.ringLayer) < level(G.topLayer)
    _buttons_over_the_strip(lua, G)
    lua.execute(WM_SETUP)
    st.shown, st.minimized, st.useWorldMap = True, None, True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()
    assert G.WorldMapHosted()
    lua.execute("AGPS_T = (AGPS_T or 0) + 0.5")
    G.Update()
    assert level(strip) > 100  # (moved up there)
    _buttons_over_the_strip(lua, G)
    _ring_over_the_route(lua, G, ns.MapExtras)


_POINT = {"BOTTOMLEFT": (0, 0), "BOTTOM": (0.5, 0), "BOTTOMRIGHT": (1, 0), "LEFT": (0, 0.5), "CENTER": (0.5, 0.5),
          "RIGHT": (1, 0.5), "TOPLEFT": (0, 1), "TOP": (0.5, 1), "TOPRIGHT": (1, 1)}


def _rect(lua, w, top, W, H):
    """(left, bottom, right, top) of widget `w` on the map's button layer (`top`, W x H), from its first anchor and
    its size as set; None when it isn't placed on the layer."""
    same = lua.eval("rawequal")
    if same(w, top):
        return (0.0, 0.0, float(W), float(H))
    pts = w._pts
    ww, wh = w._w, w._h
    if w._kind == "FontString":  # (the info line: as tall and wide as its text)
        ww, wh = w.GetStringWidth(w), w.GetStringHeight(w)
    if pts is None or ww is None or wh is None:
        return None
    a = None
    for p in _POINT:
        if pts[p] is not None:
            a = [pts[p][i] for i in range(1, len(pts[p]) + 1)]
            break
    if a is None:
        return None
    p, parent = a[0], w._parent
    if len(a) == 1:
        rel, rp, x, y = parent, p, 0, 0
    elif isinstance(a[1], (int, float)):
        rel, rp, x, y = parent, p, a[1], a[2] if len(a) > 2 else 0
    else:
        rel = a[1] if a[1] is not None else parent
        rp = a[2] if len(a) > 2 and a[2] is not None else p
        x, y = (a[3] if len(a) > 3 else 0) or 0, (a[4] if len(a) > 4 else 0) or 0
    r = _rect(lua, rel, top, W, H)
    if r is None:
        return None
    fx, fy = _POINT[rp]
    ax, ay = r[0] + (r[2] - r[0]) * fx + x, r[1] + (r[3] - r[1]) * fy + y
    px, py = _POINT[p]
    left, bottom = ax - ww * px, ay - wh * py
    return (left, bottom, left + ww, bottom + wh)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _shown_buttons(lua, G):
    out = []
    strip = G.mx.strip
    own = lua.eval("AzerothGPSFrame:GetFrameStrata()")

    def walk(f):
        kids = f._kids
        for i in range(1, len(kids or []) + 1):
            k = kids[i]
            if lua.eval("rawequal")(k, strip) or not k._shown or (k._strata and k._strata != own):
                continue
            if k._kind in ("Button", "CheckButton"):
                out.append(k)
            walk(k)
    walk(G.topLayer)
    return out


@pytest.mark.parametrize("size", ["default", "wide", "smallest strip", "smallest"])
def test_the_strip_and_its_text_are_clear_of_the_bottom_left_buttons(mx, size):
    """Item 134 (Kooki3z's shot: the map menu, the magnifier and a row of round teleport buttons with the strip's
    line through them and "Up 11 yd, down 0 yd" beside them): the strip sits over the bottom row of round buttons
    going right from the map menu button, its text and its line on no button, at the map's default size, a wide one,
    the smallest that has the strip and the smallest there is (no strip)."""
    lua, ns = mx
    G, MX, st = ns.GPS, ns.MapExtras, ns.settings.gps
    W, H = {"default": G.MapSize(), "wide": (700, 500), "smallest strip": (2 * MX.STRIP_SIDE + MX.STRIP_MIN_W,) * 2,
            "smallest": (G.SIZE_MIN, G.SIZE_MIN)}[size]
    top = G.topLayer
    quick_was = st.quick
    route_btn = G.confirmRouteBtn
    btn_was = route_btn._shown
    lua.eval("function(f, w, h) f.GetWidth = function() return w end f.GetHeight = function() return h end end")(top, W, H)
    try:
        # (the teleports and the hearthstone in the row, as in the shot)
        st.quick = lua.eval("{ hearth = 'barRight', questRoute = 'barRight', pauseRoute = 'barRight' }")
        G.LayoutQuick()
        fz = [0, 10, 20, 30, 30, 30, 20, 10]
        p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
        f = G.mx.strip
        # (over the info line, then over Confirm Route / Clear Route)
        for confirm in (False, True):
            route_btn._shown = confirm
            MX.OnRedraw(G, _route(lua, p, 0), 0, OPEN[0], OPEN[1], 200)
            if size == "smallest":
                assert not f._shown  # (too narrow for it)
                continue
            assert f._shown
            sr = _rect(lua, f, top, W, H)
            assert sr is not None and sr[0] == MX.STRIP_SIDE and sr[2] == W - MX.STRIP_SIDE
            close = sr[2] - 1 - MX.CLOSE_SIZE
            text = (sr[0] + MX.STRIP_PAD + 1, sr[3] - 1 - MX.STRIP_TEXT_H, close - 2, sr[3] - 1)
            rects = [(b, _rect(lua, b, top, W, H)) for b in _shown_buttons(lua, G)]
            rects = [(b, r) for b, r in rects if r is not None]
            assert any(lua.eval("rawequal")(b, G.mapButton) for b, _ in rects)
            row = [r for b, r in rects if MAP_RIGHT < r[0] < W / 2 and r[3] <= MAP_TOP]
            if size != "smallest strip":
                assert row, "no round buttons in the bottom row to test against"
                assert G.BottomRowTop() is not None
            if confirm:
                assert any(lua.eval("rawequal")(b, route_btn) for b, _ in rects)
            for b, r in rects:
                assert not _overlap(text, r), (size, confirm, b._text, r, text)
                assert not _overlap(sr, r), (size, confirm, b._text, r, sr)
            # (and over the info line)
            assert sr[1] > _rect(lua, G.mx.below[1], top, W, H)[3]
    finally:
        route_btn._shown = btn_was
        st.quick = quick_was
        lua.execute("AGPS_NS.GPS.topLayer.GetWidth, AGPS_NS.GPS.topLayer.GetHeight = nil, nil")
        G.LayoutQuick()


MAP_RIGHT, MAP_TOP = 3 + 32, 3 + 32  # (GPSFrame's map menu button: 32 across, 3 in from the corner)

# --- (c) the floor picker -------------------------------------------------------------------------------------------

def test_the_grids_floors_at_a_stacked_spot_and_none_on_open_ground(mx):
    lua, ns = mx
    MX = ns.MapExtras
    fl, kind = MX.FloorsAt(UC, *UC_STACK)
    floors = [fl[i] for i in range(1, len(fl) + 1)]
    assert kind == "city" and len(floors) >= 3 and floors == sorted(floors)
    assert all(b - a > MX.FLOOR_GAP for a, b in zip(floors, floors[1:]))
    fl2, _ = MX.FloorsAt(0, *OPEN)
    assert len(fl2) == 0


def _stand(lua, ns, x, y, level, z):
    """The player at (x, y) on `level`, the floor tracker reporting z there."""
    lua.execute(f"AGPS_NS.Geo.override = {{ x = {x}, y = {y}, cont = 0 }}")
    lua.execute(f"AGPS_T = (AGPS_T or 5000) + 1")
    ns.Nav.SetTrackForTests(level, x, y, z)


def test_the_floor_picker_starts_on_your_floor_and_steps_through_them(mx):
    lua, ns = mx
    G, MX, N = ns.GPS, ns.MapExtras, ns.Nav
    st = G.mx
    x, y = UC_STACK
    fl, _ = MX.FloorsAt(UC, x, y)
    floors = [fl[i] for i in range(1, len(fl) + 1)]
    n = len(floors)
    mine = floors[1]  # (the second from the bottom)
    _stand(lua, ns, x, y, UC, mine)
    assert N.PlayerFloorZ(UC) == mine
    MX.OnRedraw(G, None, UC, x, y, 200)
    assert st.spot is not None and MX.YourFloor(st) == 2
    assert MX.ShownFloor(st) == n - 1  # (counted from the top: yours)
    bar = st.bar
    assert bar._shown and bar.count._text == f"2/{n}"
    assert MX.PickedZ(st, UC) is None  # (nothing picked: the tracker's floor, as before)
    # up a floor: picked; the route's fade goes by it
    assert MX.FloorStep(st, True)
    assert MX.PickedZ(st, UC) == floors[2]
    assert G.FloorFadeKey(UC) == math.floor(floors[2] + 0.5)
    MX.RefreshFloorBar(G)
    assert bar.count._text == f"3/{n}"
    # all the way up, then past the top: all floors (no fade)
    while MX.FloorStep(st, True):
        pass
    assert MX.ShownFloor(st) == 0 and MX.PickedZ(st, UC) is False and G.FloorFadeKey(UC) is None
    MX.RefreshFloorBar(G)
    assert bar.count._text == f"All {n}" and bar.up._enabled is False and bar.down._enabled is True
    # down to the bottom, no further
    while MX.FloorStep(st, False):
        pass
    assert MX.ShownFloor(st) == n and MX.PickedZ(st, UC) == floors[0]
    assert not MX.FloorStep(st, False)


def test_the_floor_picker_follows_whatever_floor_the_tracker_reports(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    st = G.mx
    x, y = UC_STACK
    fl, _ = MX.FloorsAt(UC, x, y)
    floors = [fl[i] for i in range(1, len(fl) + 1)]
    for k, z in enumerate(floors):
        _stand(lua, ns, x, y, UC, z + 0.7)  # (a tracker's height a little off the grid's floor: still that floor)
        MX.OnRedraw(G, None, UC, x, y, 200)
        assert MX.YourFloor(st) == k + 1
    # (no floor tracked: all of them)
    ns.Nav.ResetTrack()
    lua.execute("AGPS_T = (AGPS_T or 5000) + 100")
    MX.OnRedraw(G, None, UC, x, y, 200)
    assert MX.YourFloor(st) is None and MX.ShownFloor(st) == 0


def test_a_double_clicked_stop_goes_on_the_floor_picked_near_it(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    st = G.mx
    x, y = UC_STACK
    lua.execute("AGPS_NS.Geo.override = { x = 2254, y = 293, cont = 0 }")  # (the player far off: no floor of theirs)
    MX.OnRedraw(G, None, UC, x, y, 200)
    assert MX.ClickZ(st, UC, x, y) is None  # (none picked)
    MX.FloorStep(st, False)  # (from all floors: the top one)
    top = MX.PickedZ(st, UC)
    z = MX.ClickZ(st, UC, x + 2, y)
    assert z is not None and abs(z - top) <= 2 * MX.FLOOR_GAP
    assert MX.ClickZ(st, UC, x + 200, y) is None  # (far from the pick)
    assert MX.ClickZ(st, 0, x, y) is None  # (another level)


def test_a_pick_holds_near_its_spot_and_goes_when_the_map_moves_away(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    st = G.mx
    x, y = UC_STACK
    lua.execute("AGPS_NS.Geo.override = { x = 2254, y = 293, cont = 0 }")
    MX.OnRedraw(G, None, UC, x, y, 200)
    MX.FloorStep(st, False)
    assert MX.PickedZ(st, UC) is not None
    lua.execute("AGPS_T = (AGPS_T or 5000) + 1")
    MX.OnRedraw(G, None, UC, x + 3, y, 200)
    assert MX.PickedZ(st, UC) is not None
    lua.execute("AGPS_T = (AGPS_T or 5000) + 1")
    MX.OnRedraw(G, None, 0, OPEN[0], OPEN[1], 200)
    assert st.pick is None and st.spot is None and not st.bar._shown


def test_the_floor_picker_is_off_by_its_option_zoomed_out_and_on_open_ground(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    st = G.mx
    x, y = UC_STACK
    MX.OnRedraw(G, None, UC, x, y, 200)
    assert st.bar._shown
    ns.settings.gps.floorPicker = False
    lua.execute("AGPS_T = (AGPS_T or 5000) + 1")
    MX.OnRedraw(G, None, UC, x, y, 200)
    assert not st.bar._shown
    ns.settings.gps.floorPicker = True
    lua.execute("AGPS_T = (AGPS_T or 5000) + 1")
    MX.OnRedraw(G, None, UC, x, y, MX.FLOOR_MAX_ZOOM + 100)
    assert not st.bar._shown
    lua.execute("AGPS_T = (AGPS_T or 5000) + 1")
    MX.OnRedraw(G, None, 0, OPEN[0], OPEN[1], 200)
    assert not st.bar._shown


def test_floor_lines_mark_yours_and_the_one_shown(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    st = G.mx
    x, y = UC_STACK
    fl, _ = MX.FloorsAt(UC, x, y)
    n = len(fl)
    _stand(lua, ns, x, y, UC, fl[1])
    MX.OnRedraw(G, None, UC, x, y, 200)
    lines = [(e[1], e[2]) for e in MX.FloorLines(st).values()]
    assert len(lines) == n
    assert lines[0][0].startswith(f"{n} (top): ") and lines[-1][0].startswith("1 (ground): ")
    assert lines[-1][0].endswith("(you)") and lines[-1][1]  # (yours, shown)
    assert sum(1 for _, on in lines if on) == 1


def _wg_loaded(ns, cont, x, y, r=12):
    """The world grid's tiles round (x, y) loaded, as a route there has them (the picker and strip never load one)."""
    WG = ns.WorldGrid
    c = WG.Cont(cont)
    for dx in (-r, 0, r):
        for dy in (-r, 0, r):
            WG.SurfacesAt(c, x + dx, y + dy)


def test_the_world_grids_floors_in_an_inn_and_none_on_a_steep_hillside(mx):
    lua, ns = mx
    MX = ns.MapExtras
    ns.settings.gps.worldGrid = True
    try:
        _wg_loaded(ns, 0, -9468.0, 17.0)
        fl, kind = MX.FloorsAt(0, -9468.0, 17.0)  # (Goldshire's inn, the Lion's Pride: three stories)
        floors = [fl[i] for i in range(1, len(fl) + 1)]
        assert kind == "world" and len(floors) == 3 and floors == sorted(floors)
        # (a hillside west of the Ruins of Lordaeron whose steep cells hold two surfaces 4.5 yd apart: one floor)
        _wg_loaded(ns, 0, 1683.0, -92.0)
        assert len(MX.FloorsAt(0, 1683.0, -92.0)[0]) == 0
        _wg_loaded(ns, 0, 2000.0, 0.0)
        assert len(MX.FloorsAt(0, 2000.0, 0.0)[0]) == 0
    finally:
        ns.settings.gps.worldGrid = False


def test_a_world_grid_walk_down_the_barrens_hills_shows_its_jumps(mx):
    """The Barrens' hills north of the Crossroads' south road to below them (test_world_grid's BARRENS_A, B) with a
    spell's reach: the walk's falls are the profile's jumps, the biggest its 124 yd off the hillside."""
    lua, ns = mx
    MX, WG, R = ns.MapExtras, ns.WorldGrid, ns.Router
    ns.settings.gps.worldGrid = True
    try:
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
        r = WG.Walk(WG.Cont(1), -2241.0, -1916.9, None, -2743.5, -2892.9, None, lua.table(maxDrop=196))
        part = lua.eval("function(r) return { cont = 1, pts = r.pts, kinds = r.kinds, fz = r.fz } end")(r)
        drops = sum(1 for i in range(1, len(r.pts) // 2) if r.kinds[i] == R.KIND_DROP)
        p = MX.BuildProfile(part)
        jumps = [p.jumps[k] for k in range(1, len(p.jumps) + 1)]
        assert 0 < len(jumps) <= drops
        assert max(j[5] for j in jumps) > 100
        assert p.hi - p.lo > 150 and p.down > p.up
    finally:
        ns.settings.gps.worldGrid = False
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()


def test_the_floors_are_looked_at_only_when_the_map_moves_or_now_and_then(mx):
    """The frame budget: every redraw asks MX.OnRedraw, the grids are asked again only after the map's middle moved
    FLOOR_MOVE_YD (at most every FLOOR_MIN_EVERY seconds), or every FLOOR_EVERY standing still; the strip's lines are
    laid once a profile, each redraw moving the dot only."""
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    x, y = UC_STACK
    lua.execute("AGPS_T = 20000")
    MX.OnRedraw(G, None, UC, x, y, 200)
    before = MX.floorLooks
    for k in range(30):  # (half a second at 60 frames a second, standing still)
        lua.execute(f"AGPS_T = {20000 + (k + 1) / 60}")
        MX.OnRedraw(G, None, UC, x, y, 200)
    assert MX.floorLooks == before
    for k in range(30):  # (dragged 30 yd in half a second: a look every FLOOR_MIN_EVERY)
        lua.execute(f"AGPS_T = {20001 + (k + 1) / 60}")
        MX.OnRedraw(G, None, UC, x + k, y, 200)
    assert 0 < MX.floorLooks - before <= 6
    fz = [0, 10, 20, 30, 30, 30, 20, 10]
    p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
    MX.OnRedraw(G, _route(lua, p, 0), 0, OPEN[0], OPEN[1], 200)
    lua.execute("""AGPS_LINE_MOVES = 0
      for _, l in ipairs(AGPS_NS.GPS.mx.strip.lines) do
        l.SetStartPoint = function() AGPS_LINE_MOVES = AGPS_LINE_MOVES + 1 end
      end""")
    try:
        for k in range(10):
            MX.OnRedraw(G, _route(lua, p, 5 * k), 0, OPEN[0], OPEN[1], 200)
        assert lua.eval("AGPS_LINE_MOVES") == 0  # (the lines weren't placed again)
    finally:
        lua.execute("for _, l in ipairs(AGPS_NS.GPS.mx.strip.lines) do l.SetStartPoint = nil end")


def test_neither_shows_on_the_map_sent_back_to_the_minimap_square(mx):
    lua, ns = mx
    G, MX = ns.GPS, ns.MapExtras
    fz = [0, 10, 20, 30, 30, 30, 20, 10]
    p = _part(lua, [(OPEN[0] + 20 * k, OPEN[1]) for k in range(len(fz))], 0, fz=fz)
    lua.execute("AGPS_MM_WAS = AGPS_NS.GPS.MinimapMode AGPS_NS.GPS.MinimapMode = function() return true end")
    try:
        MX.OnRedraw(G, _route(lua, p, 0), UC, *UC_STACK, 200)
        assert not G.mx.strip._shown and not G.mx.bar._shown
        assert G.mx.strip.text._text == ""  # (nothing stale left in it)
    finally:
        lua.execute("AGPS_NS.GPS.MinimapMode = AGPS_MM_WAS")
    lua.execute("AGPS_T = (AGPS_T or 5000) + 5")
    MX.OnRedraw(G, _route(lua, p, 0), UC, *UC_STACK, 200)
    assert G.mx.strip._shown and G.mx.bar._shown
