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
