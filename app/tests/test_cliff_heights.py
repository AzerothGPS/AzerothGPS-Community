"""Cliffs from the map's ground heights (Kooki3z 2026-11-20, Freewind Post: "not a safe path down"): off-road walks and
legs don't go up or down ground steeper than Passability.CLIFF_SLOPE (about 50 degrees) when the terrain grid calls it
open. A straight leg drops down one only as far as a safe jump, never climbs one; walks over the grid go round it; a
gentle slope is walked as before, and no ground height (no data) is as before. And the start's raised road (a bridge)
stays a candidate when the ground there is up at its height (Router.OffRaised: a mesa's top and the bridge off it)."""

import math

import pytest

from test_addon_lua import env, load, nav_env  # noqa: F401 (fixtures)

pytest.importorskip("lupa")

# open dry ground in the Barrens (the grid's 0 for 160 yd round): A on the high side of an edge along y = -2000, B on
# the low side
A, B = (-1500.0, -2075.0), (-1500.0, -1925.0)

# The ground as a mesa's side: 100 yd at A's side, 0 at B's, across the edge along y = -2000 in `width` yards; over
# |x + 1500| <= 80 the edge is `width` wide, past it the edge widens (1.35 yd a yard) to a gentle slope round its ends.
MESA = """
return function(width, gentle)
  return function(cont, x, y)
    if cont ~= 1 then return nil end
    local w = gentle and 150 or width + math.max(0, math.abs(x + 1500) - 80) * 1.35
    local t = (-2000 - y) / (w / 2)
    return 50 + 50 * math.max(-1, math.min(1, t))
  end
end
"""


def ground(lua, ns, at):
    ns.Ground = lua.table(At=at) if at is not None else None
    ns.Passability.ClearCache()
    if ns.Router is not None:
        ns.Router.Reset()


@pytest.fixture
def mesa(nav_env):
    lua, ns = nav_env
    load(lua, ns, "Data/Terrain.lua", "Passability.lua")
    yield lua, ns, lua.execute(MESA)
    ground(lua, ns, None)


def test_a_straight_leg_never_goes_down_or_up_a_cliff_and_a_gentle_slope_is_walked(mesa):
    lua, ns, make = mesa
    P = ns.Passability
    assert P.SegmentCost(1, *A, *B) is not None  # (no ground heights: open, as before)
    ground(lua, ns, make(20, False))  # (100 yd down in 20: a cliff)
    assert P.CliffAlong(1, *A, *B) and P.CliffAlong(1, *B, *A)
    assert P.SegmentCost(1, *A, *B) is None and P.SegmentCost(1, *B, *A) is None
    ground(lua, ns, make(20, True))  # (100 yd over 150: a third of a yard a yard)
    assert not P.CliffAlong(1, *A, *B) and not P.CliffAlong(1, *B, *A)
    assert P.SegmentCost(1, *A, *B) is not None and P.SegmentCost(1, *B, *A) is not None


def test_cliff_checks_in_the_background_pause_across_short_legs(mesa):
    # (release 1.3.12's CI: a slice of the route's background work 56 ms, test_map_redraw's caves' roads trip) the
    # checks paused every SEG_YIELD_EVERY heights of one leg, but the road network's dead ends check up to 32 short legs
    # each: none ever paused. Now a pause every CLIFF_YIELD_EVERY heights, counted across the legs; the same answers
    lua, ns, make = mesa
    P = ns.Passability
    ground(lua, ns, make(20, False))
    run = lua.eval("""function(P, GD, legs)
      local reads, most, pauses = 0, 0, 0
      local at = GD.At
      GD.At = function(...) reads = reads + 1 return at(...) end
      local co = coroutine.create(function()
        local out = {}
        for i, l in ipairs(legs) do out[i] = P.CliffAlong(1, l[1], l[2], l[3], l[4]) end
        return out
      end)
      local ok, out
      while true do
        reads = 0
        ok, out = coroutine.resume(co)
        assert(ok, out)
        most = math.max(most, reads)
        if coroutine.status(co) == "dead" then break end
        pauses = pauses + 1
      end
      GD.At = at
      return out, pauses, most
    end""")
    # (40 legs of 60 yd, 16 heights each: half across the edge, a cliff, half along the high side)
    legs = [(-1700.0 + 10 * i, -2030.0, -1700.0 + 10 * i, -1970.0) if i % 2 else
            (-1700.0 + 10 * i, -2090.0, -1640.0 + 10 * i, -2090.0) for i in range(40)]
    out, pauses, most = run(P, ns.Ground, lua.table_from([lua.table_from(l) for l in legs]))
    got = [out[i + 1] for i in range(len(legs))]
    assert pauses >= 40 * 16 // P.CLIFF_YIELD_EVERY - 1, pauses
    assert most <= 2 * (P.CLIFF_YIELD_EVERY + 1), most  # (two reads a height: the ground's and the water's)
    P.ClearCliffMemo()
    assert got == [bool(P.CliffAlong(1, *l)) for l in legs]  # (in the frame, no pauses: the same)
    assert any(got) and not all(got)


def test_a_safe_drop_is_taken_downhill_only(mesa):
    lua, ns, _ = mesa
    P = ns.Passability
    # (a 10 yd step down over 4 yd at y = -2000: within the safe jump's 14)
    ground(lua, ns, lua.eval("function(cont, x, y) return 5 + 5 * math.max(-1, math.min(1, (-2000 - y) / 2)) end"))
    assert P.SegmentCost(1, *A, *B) is not None  # (down: the drop is safe)
    assert P.SegmentCost(1, *B, *A) is None  # (up: no climbing it)
    # (30 yd down over 4: more than the safe jump, neither way)
    ground(lua, ns, lua.eval("function(cont, x, y) return 15 + 15 * math.max(-1, math.min(1, (-2000 - y) / 2)) end"))
    assert P.SegmentCost(1, *A, *B) is None and P.SegmentCost(1, *B, *A) is None


def test_a_walk_over_the_grid_goes_round_the_cliff(mesa):
    lua, ns, make = mesa
    P = ns.Passability
    c, _ = P.FindPath(1, *A, *B)
    assert c is not None and c < 160  # (no heights: straight across)
    ground(lua, ns, make(20, False))
    c, path = P.FindPath(1, *A, *B)
    assert c is not None and c > 200, c  # (round the edge's end)
    pts = [(path[i], path[i + 1]) for i in range(1, len(path), 2)]
    at = ns.Ground.At
    for p, q in zip(pts, pts[1:]):  # (no leg of it falls or climbs the edge)
        assert abs(at(1, *q) - at(1, *p)) < 40, (p, q)
    ground(lua, ns, make(20, True))
    c, _ = P.FindPath(1, *A, *B)
    assert c is not None and c < 160  # (a gentle slope: straight down it)


def test_routes_go_round_the_cliff_both_ways(env):
    lua, ns = env
    lua.execute("GetTime = function() return 0 end")
    ns.db = lua.eval("{}")
    load(lua, ns, "Data/Terrain.lua", "Passability.lua", "Data/Maps.lua", "Data/Roads.lua", "Router.lua")
    R = ns.Router
    R.WARM = False
    make = lua.execute(MESA)
    pump = lua.eval("function(R) while R.HasWork() do R.Pump(math.huge, function() return 0 end) end end")

    def route(a, b):
        for _ in range(20):
            r = R.Route(1, a[0], a[1], b[0], b[1], lua.table(offroad=True))
            if not r.pending:
                return r
            pump(R)
        return r

    try:
        ground(lua, ns, make(20, True))
        assert route(A, B).length < 160 and route(B, A).length < 160  # (a gentle slope: straight)
        ground(lua, ns, make(20, False))
        down, up = route(A, B), route(B, A)
        assert not down.pending and not up.pending
        assert down.length > 200 and up.length > 200, (down.length, up.length)
    finally:
        ground(lua, ns, None)


OFFRAISED = """
local R = ...
-- (two roads by the spot: edge 1 on the ground 10 yd off, at 0; edge 2 a bridge 30 yd off, at 90)
local g = { raised = { [2] = true }, nz = { 0, 0, 90, 90 }, e = { { 1, 2, 100 }, { 3, 4, 100 } } }
local function list() return { { edge = 1, dist = 10, along = 0 }, { edge = 2, dist = 30, along = 0 } } end
local function edges(l)
  local out = {}
  for _, c in ipairs(l) do out[#out + 1] = c.edge end
  return table.concat(out, ",")
end
return g, list, edges
"""


def test_the_start_on_a_mesa_top_keeps_its_bridge(nav_env):
    lua, ns = nav_env
    R = ns.Router
    g, make, edges = lua.execute(OFFRAISED, R)
    real = R.GroundZ
    try:
        # (no ground height: the bridge left out, as before)
        R.GroundZ = lua.eval("function() return nil end")
        assert edges(R.OffRaised(g, make(), None, 1, 0, 0)) == "1"
        # (the ground up at the bridge's height: on the mesa's top with it, kept)
        R.GroundZ = lua.eval("function() return 89 end")
        assert edges(R.OffRaised(g, make(), None, 1, 0, 0)) == "1,2"
        # (down on the ground under it: left out)
        R.GroundZ = lua.eval("function() return 2 end")
        assert edges(R.OffRaised(g, make(), None, 1, 0, 0)) == "1"
    finally:
        R.GroundZ = real
    # (by the map's ground itself, Ground.At, through Router.GroundZ)
    ns.Ground = lua.table(At=lua.eval("function(cont, x, y) return 86 end"))
    try:
        assert edges(R.OffRaised(g, make(), None, 1, 0, 0)) == "1,2"
        ns.Ground.At = lua.eval("function(cont, x, y) return 0 end")
        assert edges(R.OffRaised(g, make(), None, 1, 0, 0)) == "1"
    finally:
        ns.Ground = None


def test_freewind_posts_mesa_top_isnt_walked_off():
    """The reported route: from the mesa's top to the road northwest of it, every leg was off-road, straight down the
    cliff (89 yd to -40 in eight steps). Now no off-road leg falls or climbs more than a safe jump."""
    from azerothgps.gameharness import start

    lua, ns = start()
    R = ns.Router
    r = R.Route(1, -5409.0, -2424.0, -5356.0, -2311.0, lua.table(offroad=False))
    assert r is not None and not r.noWay
    n = len(r.pts) // 2
    pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
    kinds = [r.kinds[i] for i in range(1, n)]
    off = [(p, q) for k, p, q in zip(kinds, pts, pts[1:]) if k == R.KIND_OFFROAD]
    assert off
    for p, q in off:
        za, zb = R.GroundZ(1, *p), R.GroundZ(1, *q)
        if za is not None and zb is not None:
            assert abs(za - zb) <= R.TRACK_DROP_MAX, (p, q, za, zb)
        assert not ns.Passability.CliffAlong(1, *p, *q), (p, q)
    assert any(k != R.KIND_OFFROAD for k in kinds)  # (down by the roads: the way down from the mesa)


def test_up_from_the_great_lifts_foot_takes_the_lift():
    """Kooki3z 2026-11-20 at the Great Lift: "this should've required me to take the lift back up". From the lift's foot
    in Thousand Needles' canyon to the plateau by its top, the route walked straight up the canyon wall, cell by cell
    (-45 yd to 111). Now it rides the lift up and walks on from its top."""
    from azerothgps.gameharness import start

    lua, ns = start()
    R, P = ns.Router, ns.Passability
    foot, stop = (-4900.0, -1900.0), (-4575.0, -1750.0)
    r = R.Route(1, *foot, *stop, lua.table(offroad=False))
    assert r is not None and not r.noWay
    n = len(r.pts) // 2
    pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
    kinds = [r.kinds[i] for i in range(1, n)]
    assert R.KIND_LIFT_UP in kinds
    for k, p, q in zip(kinds, pts, pts[1:]):
        if k != R.KIND_OFFROAD or min(math.dist(p, foot), math.dist(q, foot)) < P.END_SLACK:
            continue  # (the start's own few yards: the player's there)
        za, zb = R.GroundZ(1, *p), R.GroundZ(1, *q)
        assert not P.CliffAlong(1, *p, *q), (p, q, za, zb)
        assert za is None or zb is None or zb - za <= R.TRACK_DROP_MAX, (p, q, za, zb)


# Darkcloud Pinnacle (Kooki3z 2026-11-20): a small mesa, cliffs all round it. Stubbed ground, so the case holds
# whatever roads ship there: a pillar 100 yd high (52 yd round, its side 12 yd across) on the Barrens' open ground, no
# road within 500 yd; the start 150 yd south of it
PILLAR = """
return function(cx, cy)
  return function(cont, x, y)
    if cont ~= 1 then return nil end
    local r = math.sqrt((x - cx) ^ 2 + (y - cy) ^ 2)
    return 100 * math.max(0, math.min(1, (52 - r) / 12))
  end
end
"""
PILLAR_TOP, BELOW = (-1500.0, -2000.0), (-1500.0, -2150.0)
# a walkable way up as the player records one ("thinks I can climb this": his recorded path round the mesa's west
# side up onto it): round the pillar's west side and onto its top
RECORDED = "{ -1500,-2140, -1560,-2060, -1560,-1960, -1500,-1940, -1500,-1965 }"


def pillar(lua, ns):
    ns.Ground = lua.table(At=lua.execute(PILLAR)(*PILLAR_TOP))
    ns.Passability.ClearCache()
    ns.Router.Reset()


def test_a_stop_only_reached_up_a_cliff_says_so_and_draws_no_line():
    """Kooki3z 2026-11-20: "If I picked a spot that actually isn't reachable then should've said too high or route not
    possible". A stop on top of a mesa with cliffs all round and no road up was a straight climb up its side; now no
    way on foot, said so: "That spot can't be reached on foot from here (a cliff in the way).", and nothing drawn."""
    from azerothgps.gameharness import start

    lua, ns = start()
    R, N, G = ns.Router, ns.Nav, ns.GPS
    pillar(lua, ns)
    r = R.Route(1, *BELOW, *PILLAR_TOP, lua.table(offroad=False))
    assert r.noWay and r.cliff
    lua.execute(f"AGPS_MAP = 1413; AGPS_POS = {{ {BELOW[0]}, {BELOW[1]}, 1 }}")
    N.SetStops(lua.eval(f"{{ {{ x = {PILLAR_TOP[0]}, y = {PILLAR_TOP[1]}, cont = 1 }} }}"), False, "red")
    for _ in range(10):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    assert N.Route(*BELOW, 1) is None
    assert N.Status(*BELOW, 1) == ns.L["That spot can't be reached on foot from here (a cliff in the way)."]
    # (a stop that's walked to: the usual text, not this one)
    N.SetStops(lua.eval(f"{{ {{ x = {BELOW[0] - 60}, y = {BELOW[1] - 40}, cont = 1 }} }}"), False, "red")
    for _ in range(10):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    assert N.Route(*BELOW, 1) is not None
    assert "cliff" not in str(N.Status(*BELOW, 1))


def test_a_recorded_way_up_the_mesa_is_taken_not_the_climb():
    """Kooki3z 2026-11-20 at Darkcloud Pinnacle: "thinks I can climb this", while his recorded path went round the mesa's
    side up onto it. With a road up it, the route takes the road; the straight climb up the side is no way (with no
    heights it was the way: straight up, 150 yd)."""
    from azerothgps.gameharness import start

    lua, ns = start()
    R, P = ns.Router, ns.Passability
    ns.db.tracks = lua.eval(f"{{ {{ op = 'add', continent = 1, zone = 'The Barrens', time = 1795210000, "
                            f"pts = {RECORDED} }} }}")
    pillar(lua, ns)
    r = R.Route(1, *BELOW, *PILLAR_TOP, lua.table(offroad=False))
    assert not r.noWay and not r.cliff and r.length > 250
    n = len(r.pts) // 2
    pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
    kinds = [r.kinds[i] for i in range(1, n)]
    assert min(math.dist(p, (-1560.0, -1960.0)) for p in pts) < 5  # (along the recorded way, round the west side)
    for k, p, q in zip(kinds, pts, pts[1:]):
        if k == R.KIND_OFFROAD:
            assert not P.CliffAlong(1, *p, *q), (p, q)


HALL_OF_LEGENDS, VALLEY = (1645.5, -4273.0), (1602.7, -4397.6)  # (Orgrimmar: up by the Hall, down in the Valley)


def test_orgrimmars_ledge_is_jumped_down_with_the_health_hidden():
    """Kooki3z 2026-11-20 in Orgrimmar: "should be jumpable cliffside, you can safely jump down from areas in org". The
    client hides the player's health from addons (wowmock too), so Nav.SafeDrop was the free 14 yd and the city's
    22 yd ledges were never jumped: 325 yd up and round the flight master's tower. Out of combat it's taken as
    FALL_SECRET_HEALTH of the most: down the ledge (a drop, "jump down"); in combat too (since 2026-11-23); never up one."""
    from azerothgps.gameharness import start

    lua, ns = start()
    R, N = ns.Router, ns.Nav
    assert N.SafeDrop() > 30  # (out of combat, health hidden)
    # (Kooki3z 2026-11-23: in a city, no hop without Expert jumper: the way round walked; with it, down the ledge)
    r = R.Route(1, *HALL_OF_LEGENDS, *VALLEY, lua.table(offroad=False))
    if r.cityGrid is not None:
        assert R.KIND_DROP not in [r.kinds[i] for i in range(1, len(r.pts) // 2)], r.length
    ns.settings.gps.expertJumper = True
    R.Reset()
    r = R.Route(1, *HALL_OF_LEGENDS, *VALLEY, lua.table(offroad=False))
    kinds = [r.kinds[i] for i in range(1, len(r.pts) // 2)]
    assert R.KIND_DROP in kinds and r.length < 250, r.length
    back = R.Route(1, *VALLEY, *HALL_OF_LEGENDS, lua.table(offroad=False))
    assert R.KIND_DROP not in [back.kinds[i] for i in range(1, len(back.pts) // 2)]  # (never up a ledge)
    # (Kooki3z 2026-11-23, "ignore the in combat jumping distance rule": in combat the same safe drop, down the ledge)
    out = N.SafeDrop()
    lua.execute("UnitAffectingCombat = function() return true end")
    try:
        assert N.SafeDrop() == out
        R.Reset()
        r = R.Route(1, *HALL_OF_LEGENDS, *VALLEY, lua.table(offroad=False))
        assert R.KIND_DROP in [r.kinds[i] for i in range(1, len(r.pts) // 2)] and r.length < 250, r.length
    finally:
        lua.execute("UnitAffectingCombat = function() return false end")
        ns.settings.gps.expertJumper = None


def test_a_cliff_walls_drop_is_the_players_safe_drop():
    """Kooki3z 2026-11-20, Stonetalon Mountains: a ledge dropped off one way but never climbed back. A cliff wall's way
    down was capped at the free 14 yd; now it's the player's safe drop, as the routes' (Nav.SafeDrop: Options' Safe drop,
    39 yd by default, in combat too since 2026-11-23): a 30 yd drop walked down in and out of combat, and never climbed."""
    from azerothgps.gameharness import start

    lua, ns = start()
    R = ns.Router
    # (a cliff wall on the Barrens' open ground along y = -2000, drawn toward +x: its left, +y, 30 yd over its right)
    ns.db.tracks = lua.eval("{ { op = 'wall', drawn = true, continent = 1, time = 1, kind = 'cliff', "
                            "pts = { -1580,-2000, -1500,-2000, -1420,-2000 }, cl = { 50, 50, 50 }, cr = { 20, 20, 20 } } }")
    ns.Passability.RefreshWalls()
    high, low = (-1500.0, -1925.0), (-1500.0, -2075.0)

    def route(a, b):
        R.Reset()
        return R.Route(1, *a, *b, lua.table(offroad=True))

    try:
        assert route(high, low).length < 160  # (down: 30 yd, within the safe drop out of combat)
        assert route(low, high).length > 200  # (never up it)
        lua.execute("UnitAffectingCombat = function() return true end")
        assert route(high, low).length < 160  # (in combat the same safe drop, Kooki3z 2026-11-23)
        assert route(low, high).length > 200
    finally:
        lua.execute("UnitAffectingCombat = function() return false end")
        ns.db.tracks = lua.eval("{}")
        ns.Passability.RefreshWalls()
        R.Reset()


# Kooki3z 2026-11-20, Stonetalon Mountains (his screenshot by the map's 57.6, 66.2): on the road at the top of a ledge
# (the ground ~73 there), the stop to the north-east in the valley below it (~22)
LEDGE_TOP, LEDGE_FOOT = (824.0, 480.0), (921.0, 262.0)


def test_the_stonetalon_ledge_is_walked_down_not_round_by_the_road():
    """The terrain grid closes the ledge's face (steeper than 50 degrees) both ways, so the route went ~640 yd down the
    road to the valley's floor and back up north: "you should be able to go off the cliff here". A straight leg goes
    down a run of the terrain's steep cells (Passability.SteepRunDown) when the ground falls across it; never up."""
    from azerothgps.gameharness import start

    lua, ns = start()
    R, P = ns.Router, ns.Passability
    z = lua.eval("function(x, y) local GD = AGPS_NS.Ground GD.force = true local h = GD.At(1, x, y) "
                 "GD.force = false return h end")  # (the ground's height; the road tools closed, as in game)
    if z(*LEDGE_TOP) is None:
        pytest.skip("no ground data there")
    maxDrop = ns.Nav.SafeDrop()
    r = R.Route(1, *LEDGE_TOP, *LEDGE_FOOT, lua.table(offroad=False, maxDrop=maxDrop))
    assert r.length < 400, r.length  # (straight down off the road by the ledge's top: ~300; was ~640)
    # never up it: the same legs the other way are closed (1.4.1, item 107: the grid's one-way ground walks the face
    # down in a leg or two, ~240 yd, where one straight leg fell 46 yd)
    pts = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    down = 0
    for i in range(0, len(pts) - 2, 2):
        a, b = (pts[i], pts[i + 1]), (pts[i + 2], pts[i + 3])
        if z(*a) - z(*b) > 8:
            down += 1
            assert P.SegmentCost(1, *a, *b) is not None
            assert P.SegmentCost(1, *b, *a) is None
    assert down >= 1
    R.Reset()
    back = R.Route(1, *LEDGE_FOOT, *LEDGE_TOP, lua.table(offroad=False, maxDrop=maxDrop))
    assert back.length > 500, back.length  # (up: round by the road)


# Drops in the open world (Kooki3z 2026-11-23, approved): a step down of Router.STEP_DOWN_YD or less always walked off;
# one up to the free fall (14 yd, no damage) only where it saves Router.DROP_SAVE_YD (60) of walking; two or more such
# in a row down one slope a chain, walked instead without Expert jumper. Cliff walls on the Barrens' open ground along
# y = -2000 (drawn toward +x, their left, +y, the high side), the trip straight across them 150 yd.
OW_HIGH, OW_LOW = (-1500.0, -1925.0), (-1500.0, -2075.0)


def _cliffs(lua, ns, cliffs):
    """Cliff walls [(half length, y, drop)], centered on x = -1500."""
    items = []
    for half, y, dz in cliffs:
        xs = (-1500 - half, -1500, -1500 + half)
        items.append("{ op = 'wall', drawn = true, continent = 1, time = 1, kind = 'cliff', pts = { %s }, cl = { %s }, "
                     "cr = { 20, 20, 20 } }" % (", ".join(f"{x},{y}" for x in xs), ", ".join([str(20 + dz)] * 3)))
    ns.db.tracks = lua.eval("{ " + ", ".join(items) + " }")
    ns.Passability.RefreshWalls()
    ns.Passability.ClearSegMemo()
    ns.Router.Reset()


@pytest.fixture
def open_ground():
    from azerothgps.gameharness import start

    lua, ns = start()

    def route():
        ns.Router.Reset()
        return ns.Router.Route(1, *OW_HIGH, *OW_LOW, lua.table(offroad=True)).length

    yield lua, ns, route
    ns.settings.gps.expertJumper = None
    ns.db.tracks = lua.eval("{}")
    ns.Passability.RefreshWalls()


def test_an_open_world_six_yard_edge_is_dropped(open_ground):
    lua, ns, route = open_ground
    _cliffs(lua, ns, [(300, -2000, 6)])  # (its ends 300 yd off: round them is 500 yd more)
    assert route() < 160  # (straight down the edge)


def test_a_ten_yard_drop_is_taken_only_where_it_saves_sixty_yards(open_ground):
    lua, ns, route = open_ground
    _cliffs(lua, ns, [(50, -2000, 10)])  # (round its end: about 30 yd more than the drop)
    assert route() > 170  # (walked round)
    _cliffs(lua, ns, [(100, -2000, 10)])  # (round its end: about 100 yd more)
    assert route() < 160  # (dropped)


def test_a_chain_of_drops_down_a_slope_is_walked_unless_an_expert_jumper(open_ground):
    lua, ns, route = open_ground
    _cliffs(lua, ns, [(300, y, 8) for y in (-1980, -2000, -2020)])  # (three 8 yd drops 20 yd apart)
    assert route() > 300  # (walked round their ends)
    ns.settings.gps.expertJumper = True
    ns.Passability.ClearSegMemo()
    assert route() < 160  # (an Expert jumper hops down all three)
