"""The ride check from down in a city (Undercity's level) to a stop on its continent, with the whole addon (gameharness).

Reported 2026-11-18 (1.3.9, Horde level 24 in Undercity, a trip to Loch Modan and Hillsbrad): "Why would I be told to
go to red area then run all the way when I have the fp to tarren mill?" The route flew to The Sepulcher, west, and
walked 10.3k yd east from there. The plan's walks are straight lines: from The Sepulcher the line to Loch Modan misses
the Arathi Highlands (too high at 24), from Tarren Mill it crosses them, so the plan chose The Sepulcher; the road
from either crosses them. The ride check (Nav's CompareRide), which routes the plan's walks and plans again past a
long way round, ran only for a player on the stop's own continent, never down in the city, so nothing corrected it.
"""

import pytest

SEPULCHER, UNDERCITY, TARREN_MILL, GROMGOL = 10, 11, 13, 20
IN_UNDERCITY = (1566.4, 264.7)  # (by its flight master, down in the city: the report's spot)
LOCH_MODAN = (-4717.4475, -3226.72351)  # (the report's first stop, "Loch Modan (45, 13)")
DURNHOLDE = (-427.7320399999999, -1909.33)  # (its second, "Hillsbrad Foothills (93, 39)")
BRILL = (2250.0, 290.0)


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
    """trip(stop): the route the addon settles on from down in Undercity to `stop`, Horde level 24, the report's
    flight masters on the Eastern Kingdoms known; (steps, the route)."""
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, cdb.taxiNodes, st.avoidHostile)
    lua.execute("""
      AGPS_CONFIRM = AGPS_NS.GPS.Confirm
      AGPS_NS.GPS.Confirm = function() return true end
    """)

    def run(stop):
        st.avoidHostile = True
        lua.execute("AGPS_LEVEL = 24")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { " + "".join(
            f"{{ nodeID = {n}, known = true }}, " for n in (SEPULCHER, UNDERCITY, TARREN_MILL, GROMGOL)) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        ns.Router.Reset()
        lua.execute(f"AGPS_MAP = 1458; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {IN_UNDERCITY[0]}, {IN_UNDERCITY[1]}, 0")
        N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        for _ in range(40):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
            if _ >= 4 and not N.RideChecking():
                break
        return str(N.StepsText(99)), N.route

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


def _rides(r):
    return [str(r.legs[i].ride[10]) for i in range(1, len(r.legs) + 1) if r.legs[i].ride] if r and r.legs else []


def test_from_undercity_to_loch_modan_flies_to_tarren_mill_not_the_sepulcher(game, trip):
    lua, ns = game
    steps, r = trip(LOCH_MODAN)
    assert "Tarren Mill, Hillsbrad" in _rides(r), (steps, str(ns.Nav.lastRideCheck))
    assert "Sepulcher" not in steps, steps  # (was: fly to The Sepulcher, walk 10.3k yd)


def test_from_undercity_to_durnholde_flies_to_tarren_mill(game, trip):
    lua, ns = game
    steps, r = trip(DURNHOLDE)
    assert _rides(r) == ["Tarren Mill, Hillsbrad"], (steps, str(ns.Nav.lastRideCheck))


def test_from_undercity_to_brill_still_walks_out_by_the_lift(game, trip):
    lua, ns = game
    steps, r = trip(BRILL)
    assert "Take the flight" not in steps, steps
    assert "lift" in steps, steps
