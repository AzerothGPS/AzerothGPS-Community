"""The "Enemy territory" chat line once a trip, and no planning over and over by Dun Algaz (issue #652, 1.3.9).

Reported 2026-11-18 by Kooki3z, Horde level 24, on a multi-stop trip in its listed order through Dun Algaz (Loch Modan
(45, 13), then Hillsbrad (93, 39)): "Enemy territory: no way round it found, the route passes the other faction's guards
at Dun Algaz (red on the map)." in chat again and again, along with "Routing paused: it was making your game stutter".

The line was said once a route by the stops' version (Nav.CheckHostileRoute): every stop reached, death (the body's
stop), pause and resume (the stutter watch's pause, then the Resume button), the same stops set again and /reload made
a new one, each with the trip worked out again, and said it again. Now it's said once a trip for each town
(Nav.hostileSaid, saved with the stops); the directions' line and the red on the map stay.

And walking off and on the road by Dun Algaz, each reroute from a new spot made the ride check of the player's square
again from there while the last was provisional (its walks still searched): the trip planned about seven times over
each time, and the new walks it searched, between fixed points, made the whole trip be worked out again as each
finished (Nav.SearchDone). A square's check is now made from its first spot.
"""

import pytest

WETLANDS = (-3900.0, -2550.0)  # (south of Thelgen Rock, north of Dun Algaz)
BY_DUN_ALGAZ = (-4300.0, -2500.0)  # (a little north of its guards)
LOCH_MODAN = (-5600.0, -3300.0)
# (Kooki3z's trip, as their saved stops had it)
KOOKI3Z_STOPS = ("{ { x = -4717.4475, y = -3226.72351, cont = 0, name = 'Loch Modan (45, 13)' }, "
                 "{ x = -427.73204, y = -1909.33, cont = 0, name = 'Hillsbrad Foothills (93, 39)' } }")
KOOKI3Z_FLIGHTS = [10, 11, 13, 20]  # (the flight masters they knew in the Eastern Kingdoms: no Kargath)


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
    """trip(start, stops): a Horde character at level 30 with no flight path known and the boats and zeppelins left out
    (no way round Dun Algaz), the trip `stops` set in its listed order from `start` on the Eastern Kingdoms."""
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, cdb.taxiNodes, st.avoidHostile, st.zoom)
    said = lua.eval("{}")
    old_print = ns.Print
    ns.Print = lua.eval("function(t) return function(msg) t[#t + 1] = msg end end")(said)
    lua.execute("""
      AGPS_CONFIRM = AGPS_NS.GPS.Confirm
      AGPS_NS.GPS.Confirm = function() return true end
      AGPS_USABLE = AGPS_NS.Nav.TransportUsable
      AGPS_NS.Nav.TransportUsable = function() return false end
    """)

    def settle(n=6):
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()

    def to(p):
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {p[0]}, {p[1]}, 0")

    def set_stops(stops):
        N.SetStops(lua.eval("{ " + "".join(f"{{ x = {x}, y = {y}, cont = 0, name = 's{i}' }}, "
                                            for i, (x, y) in enumerate(stops)) + "}"), False, "red", True)
        ns.GPS.Follow()
        settle()

    def run(start, stops):
        st.avoidHostile, st.zoom = True, 600
        lua.execute("AGPS_LEVEL = 30")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = {} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        ns.Router.Reset()
        to(start)
        set_stops(stops)

    def warned():
        return [str(said[i]) for i in range(1, len(said) + 1) if "Enemy territory" in str(said[i])]

    run.settle, run.to, run.set_stops, run.warned = settle, to, set_stops, warned
    try:
        yield run
    finally:
        ns.Print = old_print
        lua.execute("AGPS_NS.GPS.Confirm = AGPS_CONFIRM AGPS_NS.Nav.TransportUsable = AGPS_USABLE AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes, st.avoidHostile, st.zoom = saved
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()


def test_the_enemy_territory_line_is_said_once_a_trip(game, trip):
    # (through Dun Algaz to Loch Modan, then back through it to the Wetlands: each stretch passes the guards)
    lua, ns = game
    N = ns.Nav
    trip(BY_DUN_ALGAZ, [LOCH_MODAN, WETLANDS])
    assert N.route
    warned = trip.warned()
    assert len(warned) == 1 and "Dun Algaz" in warned[0] and "no way round" in warned[0], warned
    # off course: the route worked out again from where the player went
    trip.to((BY_DUN_ALGAZ[0] + 150, BY_DUN_ALGAZ[1] + 150))
    trip.settle()
    assert N.route and len(trip.warned()) == 1
    # paused (the stutter watch's pause) and resumed: the trip worked out again
    N.SetPaused(True, "perf")
    trip.settle()
    N.SetPaused(False)
    trip.settle()
    assert N.route and len(trip.warned()) == 1, trip.warned()
    # the same stops set again (an import's update)
    trip.set_stops([LOCH_MODAN, WETLANDS])
    assert len(trip.warned()) == 1, trip.warned()
    # a /reload: the trip and what was said come back from the saved stops
    N.hostileSaid = lua.eval("{}")
    N.Restore()
    N.Invalidate(True, True)
    trip.settle()
    assert N.route and len(trip.warned()) == 1, trip.warned()
    # Loch Modan reached: the stretch back through Dun Algaz comes in
    trip.to(LOCH_MODAN)
    trip.settle()
    assert len(N.stops) == 1, "the stop wasn't reached"
    trip.settle()
    assert N.route and len(trip.warned()) == 1, trip.warned()
    # (the directions still say it, and the map's red stays: only the chat line is once a trip)
    assert "Dun Algaz" in str(N.HostileNote())
    # a new trip: said again
    N.Clear()
    trip.to(BY_DUN_ALGAZ)
    trip.set_stops([LOCH_MODAN])
    assert len(trip.warned()) == 2, trip.warned()


def test_walking_by_dun_algaz_off_and_on_the_road_plans_a_bounded_amount(game):
    # Kooki3z's trip and flight paths, level 24, worked out the game's way (in the background, pumped each frame), the
    # work counted: no clock in it (debugprofilestop counts calls, the background gets a set number of slices a frame).
    # Two minutes walking from the Wetlands towards Dun Algaz along the route, 20 s on it, 20 s 60 yd off it.
    lua, ns = game
    N, R, T = ns.Nav, ns.Router, ns.Turns
    cdb, st = ns.CharDB(), ns.settings.gps
    saved = (cdb.faction, cdb.taxiNodes, st.avoidHostile)
    lua.execute('AGPS_LEVEL = 24 AGPS_DPS = debugprofilestop')
    cdb.faction, st.avoidHostile = "Horde", True
    cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                             + "".join(f"{{ nodeID = {n}, known = true }}, " for n in KOOKI3Z_FLIGHTS) + "} } }")
    ns.Teleports.Changed()
    N.FlightsChanged()
    N.Clear()
    R.Reset()
    lua.execute("""
      AGPS_CLOCK = 0
      debugprofilestop = function() AGPS_CLOCK = AGPS_CLOCK + 0.01 return AGPS_CLOCK end
      AGPS_SLICE = 0
      AGPS_SLICES = function() AGPS_SLICE = AGPS_SLICE + 1 return AGPS_SLICE end
      AGPS_WORK = { plans = 0, routes = 0, checks = 0, spots = {} }
      local N, R = AGPS_NS.Nav, AGPS_NS.Router
      AGPS_REAL = { plan = N.Plan, route = R.Route, bg = R.Background }
      local checking = setmetatable({}, { __mode = "k" })
      N.Plan = function(cont, x, y, ...)
        AGPS_WORK.plans = AGPS_WORK.plans + 1
        local key = checking[coroutine.running() or 0]
        if key then -- (the ride check's plans: the spots it planned from, per square)
          AGPS_WORK.spots[key] = AGPS_WORK.spots[key] or {}
          AGPS_WORK.spots[key][string.format("%.0f,%.0f", x, y)] = true
        end
        return AGPS_REAL.plan(cont, x, y, ...)
      end
      R.Route = function(...) AGPS_WORK.routes = AGPS_WORK.routes + 1 return AGPS_REAL.route(...) end
      R.Background = function(key, fn, ...)
        if key:sub(1, 5) == "ride:" then
          local f = fn
          fn = function(...) checking[coroutine.running()] = key return f(...) end
        end
        local queued = AGPS_REAL.bg(key, fn, ...)
        if queued and key:sub(1, 5) == "ride:" then AGPS_WORK.checks = AGPS_WORK.checks + 1 end
        return queued
      end
      AGPS_FRAME = function(dt)
        for _, w in ipairs(AGPS_WIDGETS) do
          local f = w._scripts.OnUpdate
          if f and w._shown then f(w, dt) end
        end
        if R.HasWork() then R.Pump(AGPS_SLICES() + 200, AGPS_SLICES) end
      end
    """)
    work, frame = lua.eval("AGPS_WORK"), lua.eval("AGPS_FRAME")

    def step(x, y):
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0; AGPS_T = AGPS_T + 0.05")
        frame(0.05)

    R.WARM, R.SYNC_WALKS = True, False
    try:
        step(*WETLANDS)
        N.SetStops(lua.eval(KOOKI3Z_STOPS), False, "red", True)
        for _ in range(3000):
            step(*WETLANDS)
            if N.route and not R.HasWork():
                break
        assert N.route and not R.HasWork()
        lua.execute("AGPS_WORK.plans, AGPS_WORK.routes, AGPS_WORK.checks, AGPS_WORK.spots = 0, 0, 0, {}")
        path, yd = T.Path(N.route), 0.0
        for i in range(20 * 120):
            yd += 0.35  # (7 yd a second)
            x, y = T.PointAt(path, yd)
            off = 60 if (i // 400) % 2 else 0
            step(x + off, y + off / 2)
        spots = {str(k): len(list(v.keys())) for k, v in work.spots.items()}
        # (each square's check made from one spot: before, from up to five as the player walked through it)
        assert spots and all(n == 1 for n in spots.values()), spots
        # (before: 12 checks, 160 plans and 276 routes; now 9, 137 and 225)
        assert work.checks <= 10, f"{work.checks} ride checks in 2 minutes"
        assert work.plans <= 150, f"{work.plans} plans in 2 minutes"
        assert work.routes <= 250, f"{work.routes} routes in 2 minutes"
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        lua.execute("""
          debugprofilestop = AGPS_DPS
          AGPS_NS.Nav.Plan, AGPS_NS.Router.Route, AGPS_NS.Router.Background = AGPS_REAL.plan, AGPS_REAL.route, AGPS_REAL.bg
          AGPS_LEVEL = nil
        """)
        cdb.faction, cdb.taxiNodes, st.avoidHostile = saved
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()
