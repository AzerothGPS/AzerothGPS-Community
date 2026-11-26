"""Route speed for 1.4.0 (the route-speed study, 2026-11-25; route-perf-study.md):

- a long leg's best way is searched inside a corridor round the weighed search's way, by the straight line alone,
  with no node limit (WorldGrid.Refine, StepCorridor): it lands where it was cut at 200,000 nodes, and cheaper;
- the first answer's bigger slices don't end 90 s after the stops changed while a grid search is still running
  (Nav.Landing);
- a trip whose plan with a ride is ahead of the walk on paper takes the ride without routing the walk all the way
  (Nav.RideAhead): the Crossroads to Gadgetzan with the flight known;
- the ride check's side walks (`opts.side`: to docks and flight masters, not to one of the trip's stops) are searched
  WorldGrid.SIDE_WALK_CAP nodes at most.

Budgets are nodes, not seconds."""

import pytest

from test_common_trips_settle import settle
from test_map_redraw import game  # noqa: F401

TAURAJO, UNGORO = (-2292.7, -2142.6), (-7446.7, -1316.7)
FREEWIND = (-5454.0, -2446.0)
CROSSROADS, GADGETZAN = (-441.8, -2596.1), (-7139.0, -3752.0)


@pytest.fixture
def grid(game):  # noqa: F811
    lua, ns = game
    st, WG, CG = ns.settings.gps, ns.WorldGrid, ns.CityGrid
    saved = (st.worldGrid, st.cityGrid)
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    CG.Set(True)
    lua.execute("AGPS_RS = { UnitFactionGroup, IsPlayerSpell }; AGPS_LEVEL = 60; "
                "UnitFactionGroup = function() return 'Horde' end; IsPlayerSpell = function() return false end")
    cdb = ns.CharDB()
    was = (cdb.faction, cdb.taxiNodes)
    cdb.faction = "Horde"
    ns.FallSpells.Refresh()
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    WG.failed, WG.failOrder = lua.table(), lua.table()
    yield lua, ns
    lua.execute("UnitFactionGroup, IsPlayerSpell = AGPS_RS[1], AGPS_RS[2]; AGPS_LEVEL = nil")
    cdb.faction, cdb.taxiNodes = was
    ns.Teleports.Changed()
    ns.Nav.FlightsChanged()
    st.worldGrid, st.cityGrid = saved
    WG.Set(bool(saved[0]))
    CG.Set(bool(saved[1]))
    ns.FallSpells.Refresh()
    ns.Router.SYNC_WALKS = True
    ns.Nav.Clear()


def _ends(lua, ns, c, a, b):
    WG = ns.WorldGrid
    starts = WG.Ends(c, a[0], a[1], None)
    goals = lua.table()
    ends = WG.Ends(c, b[0], b[1], None)
    for i in range(1, len(ends) + 1):
        goals[ends[i].id] = ends[i].cost
    WG.UnderGoals(c, b[0], b[1], None, goals)
    WG.NearGoals(c, b[0], b[1], None, goals)
    return starts, goals


# --- the bounded refine
@pytest.mark.parametrize("a,b,budget,gain", [(TAURAJO, UNGORO, 160000, 0.05), (TAURAJO, FREEWIND, 60000, 0.10)],
                         ids=["taurajo-ungoro", "taurajo-freewind"])
def test_the_best_way_is_searched_in_a_corridor_and_lands(grid, a, b, budget, gain):
    lua, ns = grid
    WG = ns.WorldGrid
    c = WG.Cont(1)
    starts, goals = _ends(lua, ns, c, a, b)
    x = WG.Costs(c, a[0], a[1], b[0], b[1], lua.table())
    x.heur = WG.HEUR_LONG
    steps = WG.Search(c, starts, goals, b[0], b[1], None, x)
    assert steps
    cost1, nodes1 = WG.lastCost, WG.lastNodes
    res = WG.RefineCosts(c, x, steps)
    x2, inside = res[0], res[1]
    assert x2.noAlt and x2.noLimit and x2.heur is None and x2.nodeCap is None
    # (the corridor: the way's own cells in it, ground far off it not)
    t = WG.Tile(c, steps[1].key)
    px, py = WG.Pt(c, t, int(steps[1].id) - int(steps[1].key) * 131072, steps[1].ci)
    assert inside(px, py) and not inside(px + 1500, py + 1500)
    was = WG.MAX_NODES
    WG.MAX_NODES = 1000  # (no node limit of its own: the corridor is its bound, it is never cut short)
    try:
        s2 = WG.Search(c, starts, goals, b[0], b[1], inside, x2)
    finally:
        WG.MAX_NODES = was
    assert s2 and not x2.limitHit
    assert WG.lastNodes <= budget, (WG.lastNodes, nodes1)
    assert WG.lastCost <= cost1 * (1 - gain), (WG.lastCost, cost1)


def test_a_long_walk_s_refine_is_the_bounded_one(grid):
    """WorldGrid.Walk's own (the walks worked out at once, as the bake and the tests do): the refine's search counted,
    never cut, and within its budget."""
    lua, ns = grid
    WG = ns.WorldGrid
    c = WG.Cont(1)
    ns.Router.SYNC_WALKS = True
    n0, r0, c0 = WG.stats.nodes, WG.stats.refineNodes or 0, WG.stats.refineCut or 0
    r = WG.Walk(c, TAURAJO[0], TAURAJO[1], None, UNGORO[0], UNGORO[1], None, lua.table())
    assert r and 9000 < r.length < 10500, r and r.length
    refine = (WG.stats.refineNodes or 0) - r0
    assert 0 < refine <= 160000 and (WG.stats.refineCut or 0) == c0, refine
    assert WG.stats.nodes - n0 <= 260000, WG.stats.nodes - n0  # (290k before, its refine cut at 200,000 with nothing)


# --- the landing slice
def test_the_bigger_slices_go_on_past_90_s_while_a_grid_search_runs(grid):
    lua, ns = grid
    N, G, WG = ns.Nav, ns.GPS, ns.WorldGrid
    N.Clear()
    lua.execute(f"AGPS_POS = {{ {TAURAJO[0]}, {TAURAJO[1]}, 1 }}; AGPS_T = 50000")
    N.SetStops(lua.eval(f"{{ {{ x = {UNGORO[0]}, y = {UNGORO[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
    was = WG.jobCount
    try:
        assert N.Landing() and G.PumpBudget(16, N.Landing()) == 4
        lua.execute(f"AGPS_T = AGPS_T + {N.LANDING_SECONDS + 10}")
        WG.jobCount = 0
        assert not N.Fresh() and not N.Landing()  # (nothing searched: 1 ms a frame, as before)
        assert G.PumpBudget(16, N.Landing()) == 1
        WG.jobCount = 1  # (a leg still searched: a quarter of the frame still, 4 ms of 16)
        assert N.Landing() and G.PumpBudget(16, N.Landing()) == 4
        lua.execute(f"AGPS_T = AGPS_T + {N.LANDING_MAX_SECONDS}")
        assert not N.Landing() and G.PumpBudget(16, N.Landing()) == 1  # (never for good)
    finally:
        WG.jobCount = was
        N.Clear()


# --- the ride ahead on paper
def _know_flights(lua, ns, cont, side):
    from azerothgps import tripsweep as ts
    known = ts._masters(ns, cont, side[0])
    ns.CharDB().taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                     + "".join(f"{{ nodeID = {n}, known = true }}," for n in known) + " } } }")
    ns.Teleports.Changed()
    ns.Nav.FlightsChanged()


def test_the_crossroads_to_gadgetzan_with_the_flight_known_settles_without_the_walk(grid):
    lua, ns = grid
    N = ns.Nav
    _know_flights(lua, ns, 1, "Horde")
    N.Invalidate(True, True)
    ticks, nodes, r = settle(lua, ns, "Horde", 1, CROSSROADS, GADGETZAN)
    assert ticks is not None and ticks <= 40, ticks
    assert nodes <= 3000, nodes  # (the walk all the way alone was 38,688, its best way 200,000 more)
    rides = [p for p in r.parts.values() if p.ride or p.transport or p.flight]
    assert (r.totalYards or 0) < 1000 and (r.totalRide or 0) > 0, (r.totalYards, r.totalRide, len(rides))
    # (its check, asked again now its walks are in: final, the walk all the way never routed)
    R, WG, CG = ns.Router, ns.WorldGrid, ns.CityGrid
    now = lua.eval("function() return os.clock() * 1000 end")
    n0 = WG.stats.nodes + CG.stats.nodes
    R.SYNC_WALKS = False
    try:
        for tick in range(60):
            lua.execute("AGPS_T = AGPS_T + 0.05")
            r = N.Route(CROSSROADS[0], CROSSROADS[1], 1) or r
            for _ in range(200):
                if not R.HasWork():
                    break
                if R.Pump(now() + 4, now):
                    N.SearchDone(True)
            if "not routed" in (N.lastRideCheck or ""):
                break
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
    assert "not routed" in (N.lastRideCheck or ""), N.lastRideCheck
    assert WG.stats.nodes + CG.stats.nodes - n0 <= 3000
    assert not r.pending and (r.totalYards or 0) < 1000 and (r.totalRide or 0) > 0


def test_a_ride_is_ahead_only_when_its_least_beats_the_walk_s_least(grid):
    lua, ns = grid
    N = ns.Nav
    d = lua.eval("{ cont = 1, x = 7000, y = 0 }")
    ride = lua.eval("function(secs) return { { walk = true, cont = 1, x1 = 0, y1 = 0, x2 = 100, y2 = 0 }, "
                    "{ ride = { 1, 0, 0, 1, 0, 0, secs }, from = 1 }, "
                    "{ walk = true, cont = 1, x1 = 6900, y1 = 0, x2 = 7000, y2 = 0 } } end")
    walk = lua.eval("{ { walk = true, cont = 1, x1 = 0, y1 = 0, x2 = 7000, y2 = 0 } }")
    assert N.RideAhead(1, 0, 0, d, ride(300), 7) == pytest.approx(1000)  # (the walk's least: 7,000 yd at 7 a second)
    assert N.RideAhead(1, 0, 0, d, ride(1200), 7) is None  # (the ride slower than the straight walk: both routed)
    assert N.RideAhead(1, 0, 0, d, walk, 7) is None  # (no ride in the plan)
    assert N.RideAhead(1, 6500, 0, d, ride(10), 7) is None  # (a short trip: not worth a check at all)
    assert N.RideAhead(0, 0, 0, d, ride(300), 7) is None  # (a stop on another continent)
    N.RIDE_FIRST = False
    try:
        assert N.RideAhead(1, 0, 0, d, ride(300), 7) is None
    finally:
        N.RIDE_FIRST = True


# --- a plan's side walks
SEARCHES = """
local WG = AGPS_NS.WorldGrid
AGPS_SIDE = { caps = {}, real = WG.Search }
WG.Search = function(c, starts, goals, tx, ty, inside, x)
  AGPS_SIDE.caps[#AGPS_SIDE.caps + 1] = x and x.nodeCap or 0
  return AGPS_SIDE.real(c, starts, goals, tx, ty, inside, x)
end
"""


def test_the_ride_check_s_side_walk_is_searched_to_its_cap_at_most(grid):
    lua, ns = grid
    R, N, WG = ns.Router, ns.Nav, ns.WorldGrid
    now = lua.eval("function() return os.clock() * 1000 end")
    N.Clear()
    R.Reset()
    R.SYNC_WALKS = False
    lua.execute(SEARCHES)
    ask = lua.eval("""function(sx, sy, tx, ty)
      local WG = AGPS_NS.WorldGrid
      return WG.Walk(WG.Cont(1), sx, sy, nil, tx, ty, nil, { side = true })
    end""")
    was = WG.SIDE_WALK_CAP
    try:
        assert WG.SIDE_WALK_CAP == 60000
        WG.SIDE_WALK_CAP = 2000
        n0, cut0 = WG.stats.nodes, WG.stats.sideCut or 0
        # (the ride check's, to a spot that is none of the trip's stops: there are none)
        assert ask(TAURAJO[0], TAURAJO[1], FREEWIND[0], FREEWIND[1]) == "pending"
        for _ in range(4000):
            if not R.HasWork():
                break
            R.Pump(now() + 20, now)
        caps = list(lua.eval("AGPS_SIDE.caps").values())
        assert caps and all(0 < cap <= 2000 for cap in caps), caps
        assert WG.stats.nodes - n0 <= 2 * 2001 + 400, WG.stats.nodes - n0  # (round the guards, then through them)
        assert (WG.stats.sideCut or 0) == cut0 + 1
        # (the same leg asked as the route's own: its search isn't a side walk's)
        lua.execute("AGPS_SIDE.caps = {}")
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
        WG.failed, WG.failOrder = lua.table(), lua.table()
        assert WG.Walk(WG.Cont(1), TAURAJO[0], TAURAJO[1], None, FREEWIND[0], FREEWIND[1], None, lua.table()) == "pending"
        for _ in range(20000):
            if not R.HasWork():
                break
            R.Pump(now() + 20, now)
        caps = list(lua.eval("AGPS_SIDE.caps").values())
        assert caps and caps[0] > 2000, caps
    finally:
        WG.SIDE_WALK_CAP = was
        lua.execute("AGPS_NS.WorldGrid.Search = AGPS_SIDE.real")
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
