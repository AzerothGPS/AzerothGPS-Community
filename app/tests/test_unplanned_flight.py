"""A flight the route didn't plan, taken anyway (reported 2026-11-15: "flying against a planned route's direction the
arrow doesn't get paused like it would if the route was planned to go there"). Any flight is followed as one: "Flying to
<there>", when it lands, the arrow paused, the route worked out again only on landing. A flight to Undercity wasn't:
its flight master is down on the city's level (10001), the flight over Tirisfal (0), and the route as it was before
boarding was kept, its arrow pointing back along it."""

import pytest

TARREN_MILL, UNDERCITY = "Tarren Mill, Hillsbrad", "Undercity, Tirisfal"


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    cdb = ns.CharDB()
    cdb.faction = "Horde"
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end')
    masters = {}
    for p in lua.eval("AGPS_NS.Pois[0]").values():
        if p[1] == 1:
            masters[p[4]] = (p[5], p[2], p[3])
    nodes = "".join(f"{{ nodeID = {m[0]}, known = true }}, " for m in masters.values())
    cdb.taxiNodes = lua.eval(f"{{ [1415] = {{ nodes = {{ {nodes} }} }} }}")
    ns.Nav.FlightsChanged()
    lua.execute("AGPS_REAL_TAXI_CURRENT = AGPS_NS.Taxi.Current")
    return lua, ns, masters


def _board(lua, ns, masters, stop):
    N, G = ns.Nav, ns.GPS
    _, x, y = masters[TARREN_MILL]
    lua.execute(f"""
      UnitOnTaxi = function() return false end
      AGPS_NS.Taxi.Current = AGPS_REAL_TAXI_CURRENT
      AGPS_MAP = 1424; AGPS_POS = {{ {x}, {y}, 0 }}
    """)
    N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 0 }} }}"), False, "red")
    for _ in range(20):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    lua.execute(f"""
      AGPS_FLY = {{ from = "{TARREN_MILL}", to = "{UNDERCITY}", start = AGPS_T }}
      AGPS_NS.Taxi.Current = function() return AGPS_FLY end
      UnitOnTaxi = function() return true end
    """)
    return x, y


def _fly(lua, ns, x, y, masters, frames):
    _, tx, ty = masters[UNDERCITY]
    for _ in range(frames):
        x += (tx - x) * 0.02
        y += (ty - y) * 0.02
        lua.execute(f"AGPS_T = AGPS_T + 0.25; AGPS_POS = {{ {x}, {y}, 0 }}")
        ns.GPS.Update()
    return x, y


def _land(lua):
    lua.execute("UnitOnTaxi = function() return false end; AGPS_NS.Taxi.Current = AGPS_REAL_TAXI_CURRENT")


def test_a_flight_to_undercity_away_from_the_route_is_followed_as_a_flight(game):
    lua, ns, masters = game
    N = ns.Nav
    x, y = _board(lua, ns, masters, (-35.0, -935.0))  # (the stop: Southshore, south; the flight goes north)
    try:
        for _ in range(4):
            x, y = _fly(lua, ns, x, y, masters, 10)
            r = N.route
            assert r and r.flying and r.flying.to == UNDERCITY, "the route from before boarding was kept"
            assert (r.pts[1], r.pts[2]) == (x, y)  # (the flight's line from the player)
            status = N.Status(x, y, 0)
            assert "Flying to " + UNDERCITY in status and "lands in" in status
    finally:
        _land(lua)


def test_while_the_landings_roads_are_built_the_flight_shows_alone(game):
    # (Undercity's roads built in the frame on boarding: 0.8 s; built in the background meanwhile)
    lua, ns, masters = game
    N = ns.Nav
    x, y = _board(lua, ns, masters, (-35.0, -935.0))
    lua.execute("""
      local R = AGPS_NS.Router
      AGPS_REAL_READY, AGPS_REAL_WARM = R.GraphReady, R.WarmUp
      AGPS_WARMED = {}
      R.GraphReady = function(c) if c == 10001 then return false end return AGPS_REAL_READY(c) end
      R.WarmUp = function(c) AGPS_WARMED[#AGPS_WARMED + 1] = c return c == 10001 end
    """)
    try:
        x, y = _fly(lua, ns, x, y, masters, 4)
        r = N.route
        assert r.flying and r.walkYards == 0 and len(r.parts) == 1, "the way on from Undercity was worked out meanwhile"
        assert 10001 in list(lua.eval("AGPS_WARMED").values())
        lua.execute("local R = AGPS_NS.Router; R.GraphReady, R.WarmUp = AGPS_REAL_READY, AGPS_REAL_WARM")
        x, y = _fly(lua, ns, x, y, masters, int(N.FLYING_REST_EVERY / 0.25) + 2)
        r = N.route
        assert r.flying and r.walkYards > 0, "the way on from the landing never came once its roads were built"
    finally:
        lua.execute("local R = AGPS_NS.Router; R.GraphReady, R.WarmUp = AGPS_REAL_READY or R.GraphReady, AGPS_REAL_WARM or R.WarmUp")
        _land(lua)
