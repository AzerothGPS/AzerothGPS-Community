"""Rides cost their time only: what a flight, a zeppelin or a boat passes over isn't walked (gameharness).

Asked 2026-11-18 (Kooki3z, after the Tarren Mill report, #648): "Flight paths should be immune to crossing into
dangerous spots or in too high level zones because you can't be harmed or take any action while on a flight." Only the
walks before and after a ride count: no extra cost in the plan for the zones too high it flies over (Nav.PlanYards is
on the walks), none past the other faction's guards (Nav.HostileWalkYards, the ride check's walks), no "Keep this
route?" (Nav.RedOnRoute) or "Risk enemy territory?" question, and no town in "Through enemy territory" (Nav.HostileOnRoute,
Nav.HostileSpans: the walk kinds only). Each test also checks that the ride it uses really passes over such ground, so
it can't pass by missing it.
"""

import pytest

TARREN_MILL = (5.0, -855.0)  # (by its flight master)
BY_KARGATH = (-6600.0, -2180.0)  # (its flight passes over the Arathi Highlands and near the Alliance's guards)
BY_GROMGOL = (-12390.0, 146.0)  # (by the zeppelin from Brill, over the Alliance's guards on the way)
WETLANDS = (-3900.0, -2550.0)  # (the road north of Dun Algaz)
LOCH_MODAN = (-5600.0, -3300.0)
TRANSPORT = 2  # Nav.KIND_TRANSPORT


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    ns.settings.gps.fastestOrder = False
    return lua, ns


@pytest.fixture
def trip(game):
    """trip(start, stop): the route a Horde level 24 player with every Horde flight master on the Eastern Kingdoms
    settles on, the questions asked meanwhile in AGPS_ASKS."""
    from azerothgps import tripsweep as ts

    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, cdb.taxiNodes, st.avoidHostile)
    lua.execute("""
      AGPS_ASKS = {}
      AGPS_CONFIRM = AGPS_NS.GPS.Confirm
      AGPS_NS.GPS.Confirm = function(text) AGPS_ASKS[#AGPS_ASKS + 1] = text return true end
    """)

    def run(start, stop):
        lua.execute("AGPS_ASKS = {} AGPS_LEVEL = 24")
        st.avoidHostile = True
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { " + "".join(
            f"{{ nodeID = {n}, known = true }}, " for n in ts._masters(ns, 0, "H")) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        ns.Router.Reset()
        lua.execute(f"AGPS_MAP = 1424; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {start[0]}, {start[1]}, 0")
        N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        for i in range(50):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
            if i >= 12 and not N.RideChecking():
                break
        return N.route

    try:
        yield run
    finally:
        lua.execute("AGPS_NS.GPS.Confirm = AGPS_CONFIRM AGPS_LEVEL = nil AGPS_MAP = nil")
        cdb.faction, cdb.taxiNodes, st.avoidHostile = saved
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()


def _asks(lua):
    a = lua.eval("AGPS_ASKS")
    return [str(a[i]) for i in range(1, len(a) + 1)]


def _parts(r):
    return [r.parts[i] for i in range(1, len(r.parts) + 1)]


def _kinds(part):
    return {part.kinds[i] for i in range(1, len(part.kinds) + 1)}


def _over(ns, part):
    """(yards past the other faction's guards, yards in zones too high) along route part `part`, every piece counted."""
    R = ns.Router
    side, red, pts = ns.Nav.Faction(), R.RedZones(), part.pts
    guards = high = 0
    for i in range(1, len(pts) - 2, 2):
        guards += R.HostileYards(part.cont, pts[i], pts[i + 1], pts[i + 2], pts[i + 3], side)
        high += sum(yd for z, yd in R.ZoneYards(part.cont, pts[i], pts[i + 1], pts[i + 2], pts[i + 3]).items() if red[z])
    return guards, high


def _ride_parts(r):
    return [p for p in _parts(r) if _kinds(p) == {TRANSPORT}]


def _walked(lua, part):
    """`part` as if walked: its pieces given a walk's kind."""
    return lua.eval("function(p) local k = {} for i = 1, #p.pts / 2 - 1 do k[i] = 0 end "
                    "return { cont = p.cont, pts = p.pts, kinds = k } end")(part)


def test_a_flight_over_zones_too_high_and_the_other_factions_guards_costs_its_time_only(game, trip):
    lua, ns = game
    N = ns.Nav
    r = trip(TARREN_MILL, BY_KARGATH)
    steps = str(N.StepsText(99))
    assert "Take the flight to Kargath" in steps, steps
    (flight,) = _ride_parts(r)
    guards, high = _over(ns, flight)
    assert guards >= N.HOSTILE_RIDE_YD and high >= 1000, (guards, high)  # (it does fly over both)
    # (no question, no warning, no red)
    assert _asks(lua) == [], _asks(lua)
    assert N.RedOnRoute(r, TARREN_MILL[0], TARREN_MILL[1], 0) is None
    assert N.HostileOnRoute(r) is None
    assert N.HostileNote() is None
    assert not any(N.HostileSpans(flight, i) for i in range(1, len(flight.pts) // 2))
    # (the ride check: the way with the flight 0 yd past guards)
    assert "vs with rides" in str(N.lastRideCheck) and "s (0 past guards): rides" in str(N.lastRideCheck), str(N.lastRideCheck)
    # (the plan: the flight's seconds and the walks' planned seconds, nothing for what the flight passes over)
    walk = N.Speeds()[1]
    legs, secs = N.Plan(0, TARREN_MILL[0], TARREN_MILL[1], walk, N.stops[1])
    expect = 0.0
    for i in range(1, len(legs) + 1):
        leg = legs[i]
        if leg.ride:
            expect += leg.ride[7]
        else:
            # (its walks are in the zones the trip starts and ends in, free of the extra: straight yards)
            expect += ((leg.x2 - leg.x1) ** 2 + (leg.y2 - leg.y1) ** 2) ** 0.5 * N.WALK_FACTOR / walk
    assert any(legs[i].ride for i in range(1, len(legs) + 1))
    assert secs == pytest.approx(expect, abs=0.5), (secs, expect)


def test_a_zeppelin_past_the_other_factions_guards_isnt_enemy_territory(game, trip):
    lua, ns = game
    N = ns.Nav
    r = trip(TARREN_MILL, BY_GROMGOL)
    steps = str(N.StepsText(99))
    assert "zeppelin" in steps, steps
    rides = _ride_parts(r)
    assert any(_over(ns, p)[0] > 0 for p in rides), [_over(ns, p) for p in rides]  # (one passes them)
    assert _asks(lua) == [], _asks(lua)
    assert N.HostileOnRoute(r) is None
    assert N.HostileNote() is None


def test_the_enemy_territory_note_names_only_the_towns_walked_through(game, trip):
    lua, ns = game
    N, R = ns.Nav, ns.Router
    trip(TARREN_MILL, BY_KARGATH)
    (flight,) = _ride_parts(N.route)
    # (a walk through Dun Algaz, the router not keeping off the guards)
    ns.settings.gps.avoidHostile = False
    R.Reset()
    w = R.Route(0, WETLANDS[0], WETLANDS[1], LOCH_MODAN[0], LOCH_MODAN[1], lua.eval("{}"))
    for _ in range(50):
        if not w.pending:
            break
        lua.execute("AGPS_T = AGPS_T + 0.5")
        ns.GPS.Update()
        w = R.Route(0, WETLANDS[0], WETLANDS[1], LOCH_MODAN[0], LOCH_MODAN[1], lua.eval("{}"))
    ns.settings.gps.avoidHostile = True
    walk = lua.eval("function(p) return { cont = 0, pts = p.pts, kinds = p.kinds } end")(w)

    def names(*parts):
        t = N.HostileOnRoute(lua.eval("function(...) return { parts = { ... } } end")(*parts))
        return sorted(str(t[i][1]) for i in range(1, len(t) + 1)) if t else []

    walked = names(walk)
    flown_as_walk = names(_walked(lua, flight))
    assert walked, "the walk through Dun Algaz passes no guards"
    assert set(flown_as_walk) - set(walked), (flown_as_walk, walked)  # (walked, the flight's way would add a town)
    assert names(flight, walk) == walked, (names(flight, walk), walked)
    assert names(flight) == []
