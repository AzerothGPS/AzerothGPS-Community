"""A tunnel through to another zone is a way a planned trip takes (the Talondeep Path, Ashenvale to Stonetalon).

A player's report, 2026-11-10: "Journey to Stonetalon Peak" sent an Alliance character from Astranaar "the long way
around straight into Horde Guards": by the Barrens and the Crossroads, 11,300 yd for 6,000. The tunnel's west mouth
opens 800 yd of open ground from Windshear Crag's road, past the cave builder's 500 (caves.ENTRANCE_MAX), so it had no
join onto Kalimdor's roads and the planner knew no way through (caves.TUNNEL_ENTRANCE_MAX since).
"""

import math

import pytest

lupa = pytest.importorskip("lupa")

KALIMDOR = 1
ASTRANAAR = (2720.4, -382.4)
STONETALON_PEAK = (2658.8, 1449.7)
WINDSHEAR_CRAG = (1250.0, -150.0)
WINDSHEAR_ROAD = (1078.0, 65.0)  # where the west mouth's road out meets the zone's road
TUNNEL = ((1936.0, -726.0), (1510.0, -588.0))  # its mouths: Ashenvale's, Stonetalon's
BARRENS = 1413  # (the zone's map id, Router.ZoneAt)
ASTRANAAR_FLIGHT = 28


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    ns.settings.gps.fastestOrder = False
    return lua, ns


def _trip(lua, ns, faction, a, b):
    """The route planned from a to b for a level 25 `faction` character who knows Astranaar's flight only: its points."""
    N = ns.Nav
    lua.execute(f"AGPS_LEVEL = 25; UnitFactionGroup = function() return '{faction}' end")
    cdb = ns.CharDB()
    cdb.faction = faction
    cdb.taxiNodes = lua.eval(f"{{ [1415] = {{ nodes = {{ {{ nodeID = {ASTRANAAR_FLIGHT}, known = true }} }} }} }}")
    ns.Teleports.Changed()
    N.FlightsChanged()
    N.Clear()
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {a[0]}, {a[1]}, {KALIMDOR}")
    N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = {KALIMDOR}, name = 'stop' }} }}"), False, "red")
    N.Invalidate(True, True)
    r = N.Route(a[0], a[1], KALIMDOR)
    assert r, (faction, a, b)
    pts = []
    for part in r.parts.values():
        assert not part.blocked, (faction, a, b, part.blocked)
        p = part.pts
        pts += [(p[2 * i - 1], p[2 * i]) for i in range(1, len(p) // 2 + 1)]
    return r, pts


def test_the_talondeep_paths_west_mouth_is_joined_to_a_road(game):
    lua, ns = game
    over = next(o for o in ns.RoadOverlays[KALIMDOR].values() if o.cave and not o.capital)
    n = over.n
    joins = [(n[2 * j - 1], n[2 * j]) for j in over.joins.values()]
    # (the road out of the west mouth ends on Windshear Crag's, 770 yd off: past caves.ENTRANCE_MAX)
    assert any(math.dist(q, WINDSHEAR_ROAD) < 60 for q in joins), "the Talondeep Path's west mouth has no road out"


def test_astranaar_to_stonetalon_peak_goes_through_the_tunnel(game):
    lua, ns = game
    r, pts = _trip(lua, ns, "Alliance", ASTRANAAR, STONETALON_PEAK)
    assert (r.totalRide or 0) == 0  # (walked: Stonetalon Peak's flight isn't known)
    for mouth in TUNNEL:
        assert min(math.dist(p, mouth) for p in pts) < 60, f"not by the tunnel's mouth at {mouth}"
    zones = {ns.Router.ZoneAt(KALIMDOR, x, y) for x, y in pts}
    assert BARRENS not in zones, "round by the Barrens"
    assert (r.walkYards or 0) < 8000, r.walkYards


def test_windshear_crag_back_to_astranaar_goes_through_the_tunnel(game):
    lua, ns = game
    r, pts = _trip(lua, ns, "Alliance", WINDSHEAR_CRAG, ASTRANAAR)
    assert (r.totalRide or 0) == 0
    for mouth in TUNNEL:
        assert min(math.dist(p, mouth) for p in pts) < 60, f"not by the tunnel's mouth at {mouth}"
    assert (r.walkYards or 0) < 3000, r.walkYards


# The North Gate Pass, Dun Morogh to Loch Modan (asked 2026-11-16: "Why are we going south then back?", Kharanos to the
# Wetlands round by the South Gate Pass; the player drew a road through the tunnel): its roads came out as two pieces,
# one from each mouth, 17 yd apart behind a sliver of rock the cave's grid closed in the passage (caves.join_pieces).
EASTERN_KINGDOMS = 0
KHARANOS = (-5575.63, -882.32)
ALGAZ_STATION = (-4817.8, -2666.7)
NORTH_GATE = ((-5267.0, -2189.0), (-5203.0, -2303.0))  # its mouths: Dun Morogh's, Loch Modan's


def test_the_north_gate_pass_is_one_road_through(game):
    lua, ns = game
    R = ns.Router
    r = R.Route(EASTERN_KINGDOMS, *NORTH_GATE[0], *NORTH_GATE[1], lua.table(offroad=False))
    assert not r.unconnected and r.length < 300, r.length  # (3,091 yd round by the South Gate Pass, before)


def test_kharanos_to_algaz_station_goes_through_the_north_gate(game):
    lua, ns = game
    R = ns.Router
    r = R.Route(EASTERN_KINGDOMS, *KHARANOS, *ALGAZ_STATION, lua.table(offroad=False))
    pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, len(r.pts) // 2 + 1)]
    for mouth in NORTH_GATE:
        assert min(math.dist(p, mouth) for p in pts) < 60, f"not by the North Gate Pass' mouth at {mouth}"
    assert r.length < 3000, r.length  # (3,430 yd by the South Gate Pass, before)
