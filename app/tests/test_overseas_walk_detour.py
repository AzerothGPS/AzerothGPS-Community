"""A trip to another continent from Ironforge, the walk to the first ride a long way round (the whole addon, gameharness).

Reported for 1.4.2 (Alliance level 30, Ironforge, Menethil Harbor and Ratchet flight paths known, a stop in Ratchet):
from Ironforge's bank, at the front of the city, the route walked about 8.3k yd round by Loch Modan to Menethil's dock
instead of flying from Ironforge's gryphon master, about 360 yd away; from the Great Forge it flew. The plan's walks are
straight lines (the bank to Menethil's dock 1,040 yd, through the mountain), and the check that plans again past a walk
that's a long way round (Nav's CompareRide, N.WalkDetour) ran only for a stop on the player's own continent.
"""

import pytest

IRONFORGE, MENETHIL, RATCHET = 6, 7, 80
RATCHET_STOP = (-894.6, -3773.0)  # (Kalimdor)
STARTS = {
    "the bank": (-4888.0, -995.0),
    "the Mystic Ward": (-4661.0, -954.0),
    "the Hall of Explorers": (-4684.7, -1236.4),
    "the Great Forge": (-4763.0, -1108.0),
}


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
    """trip(spot, known=None, level=30): the route the addon settles on from `spot` in Ironforge to Ratchet, Alliance at
    `level`, the flight masters `known` ((Eastern Kingdoms' nodes, Kalimdor's); the report's by default); (steps, the
    route)."""
    lua, ns = game
    N = ns.Nav
    cdb = ns.CharDB()
    saved = (cdb.faction, cdb.taxiNodes)
    lua.execute("""
      AGPS_CONFIRM = AGPS_NS.GPS.Confirm
      AGPS_NS.GPS.Confirm = function() return true end
    """)

    def run(spot, known=None, level=30):
        lua.execute(f"AGPS_LEVEL = {level}")
        cdb.faction = "Alliance"
        ek, kal = known or ((IRONFORGE, MENETHIL), (RATCHET,))
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { " + "".join(f"{{ nodeID = {n}, known = true }}, " for n in ek)
                                 + "} }, [1414] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in kal) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        ns.Router.Reset()
        lua.execute(f"AGPS_MAP = 1455; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {spot[0]}, {spot[1]}, 0")
        N.SetStops(lua.eval(f"{{ {{ x = {RATCHET_STOP[0]}, y = {RATCHET_STOP[1]}, cont = 1, name = 'stop' }} }}"),
                   False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        for i in range(60):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
            if i >= 4 and not N.RideChecking() and N.route and not N.route.pending:
                break
        return str(N.StepsText(99)), N.route

    try:
        yield run
    finally:
        lua.execute("AGPS_NS.GPS.Confirm = AGPS_CONFIRM AGPS_LEVEL = nil AGPS_MAP = nil")
        cdb.faction, cdb.taxiNodes = saved
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()


def _rides(r):
    return [str(r.legs[i].ride[10]) for i in range(1, len(r.legs) + 1) if r.legs[i].ride] if r and r.legs else []


@pytest.mark.parametrize("name", list(STARTS))
def test_from_ironforge_to_ratchet_flies_from_ironforge(game, trip, name):
    lua, ns = game
    steps, r = trip(STARTS[name])
    assert r and r.legs, steps
    first = r.legs[1]
    assert first.walk or not first.ride, steps
    # (the first ride is Ironforge's flight to Menethil, the walk to it short: was 8.3k yd round by Loch Modan)
    assert "Menethil Harbor, Wetlands" in _rides(r)[:1], (name, steps, _rides(r))
    assert (first.yards or 0) < 1500, (name, first.yards, steps)


# Every Alliance flight master in the Eastern Kingdoms and Kalimdor (Data/Pois.lua's node ids).
ALL_ALLIANCE = ((2, 4, 5, 6, 7, 8, 12, 14, 16, 19, 43, 45, 66, 67, 71, 74),
                (26, 27, 28, 32, 33, 37, 39, 41, 49, 52, 64, 65, 73, 79, 80))


def _ride_kinds(r):
    return [(str(r.legs[i].ride[8]), str(r.legs[i].ride[10])) for i in range(1, len(r.legs) + 1)
            if r.legs[i].ride] if r and r.legs else []


@pytest.mark.parametrize("level", [30, 60])
def test_every_flight_known_takes_menethils_boat_to_theramore(game, trip, level):
    """Reported again for 1.4.2 (Kooki3z, 2026-11-27, a whole-world view): at level 30 with every Alliance flight known,
    from Ironforge to Ratchet the route flew to Booty Bay by Stormwind and took the boat across the Great Sea (769 s
    planned), not Menethil's boat to Theramore and its flight to Ratchet (609 s). Dustwallow Marsh (35-45) is too high at
    30, and the 294 yd from Theramore's dock to its flight master, inside the Alliance's own town, was paid as a walk
    through the zone (Nav.InOwnTown)."""
    lua, ns = game
    steps, r = trip(STARTS["the bank"], ALL_ALLIANCE, level)
    assert r and r.legs, steps
    kinds = _ride_kinds(r)
    assert kinds[:3] == [("flight", "Menethil Harbor, Wetlands"), ("boat", "Theramore Isle, Dustwallow Marsh"),
                         ("flight", "Ratchet, The Barrens")], (level, kinds, steps)


def test_a_walk_inside_theramore_isnt_through_dustwallow(game):
    """The walk from Theramore's dock to its flight master is in the Alliance's own town (two of its guards' groups),
    not out in Dustwallow Marsh; one from the dock out to Brackenwall Village isn't."""
    lua, ns = game
    N = ns.Nav
    cdb = ns.CharDB()
    saved = cdb.faction
    try:
        cdb.faction = "Alliance"
        assert N.InOwnTown(1, -4016.0, -4741.0, -3825.0, -4517.0)
        assert not N.InOwnTown(1, -4016.0, -4741.0, -3120.0, -2860.0)
        cdb.faction = "Horde"
        assert not N.InOwnTown(1, -4016.0, -4741.0, -3825.0, -4517.0)
    finally:
        cdb.faction = saved


def test_every_eastern_flight_known_none_in_kalimdor_flies_to_booty_bay_for_its_boat(game, trip):
    """Kooki3z's test character (2026-11-27's whole-world view): every Alliance flight in the
    Eastern Kingdoms known and none in Kalimdor. Theramore's and Ratchet's flights unknown, the way is the flight to Booty
    Bay (by Stormwind, drawn through it) and Booty Bay's boat to Ratchet: two rides, each drawn as a dotted line, no swim
    and no walk across the sea."""
    lua, ns = game
    steps, r = trip(STARTS["the bank"], (ALL_ALLIANCE[0], ()), 30)
    assert r and r.legs, steps
    assert _ride_kinds(r) == [("flight", "Booty Bay, Stranglethorn"), ("boat", "Booty Bay, Stranglethorn Vale")], steps
    first = next(r.legs[i].ride for i in range(1, len(r.legs) + 1) if r.legs[i].ride)
    pts = [first.pts[i] for i in range(1, len(first.pts) + 1)]
    assert any(abs(pts[i] + 8835) < 300 and abs(pts[i + 1] - 481) < 300 for i in range(0, len(pts) - 1, 2)), pts
    for i in range(1, len(r.legs) + 1):
        if not r.legs[i].ride:
            assert (r.legs[i].yards or 0) < 600, (i, r.legs[i].yards, steps)
