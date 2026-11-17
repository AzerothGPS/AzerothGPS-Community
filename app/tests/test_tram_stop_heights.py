"""The Deeprun Tram's stops have heights (reported 1.3.4: in Stormwind's Dwarven District at 66.2, 34.9 with a stop in
Ironforge, "572 m on foot to: Deeprun Tram" left the district, went south and east round to Stormwind Keep, through
it and back to the tram from above, not the 155 yd inside the district). The tram row in Data/Transports.lua had no
height for either end, so the walk to it ended on the road nearest in the plane: the keep's, about 25 yd over the way
in. Its ends now carry the client's AreaTrigger heights (`z1`, `z2`), and the walks to and from them use them."""

import pytest

DWARVEN_DISTRICT = (-8400.1, 572.7, 97.0)  # (the report: Stormwind City 66.2, 34.9, height about 97)
IRONFORGE = (-4821.8, -1155.4)
KEEP_ROAD_Z = 110  # (the keep's road over the tram's way in is at 122; the district's at 92 to 97)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    ns.CharDB().faction = "Alliance"
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end')
    return lua, ns


def _pump(lua, ns):
    lua.eval("function(R) while R.HasWork() do R.Pump(math.huge, function() return 0 end) end end")(ns.Router)


def _tram(ns):
    rows = ns.Transports
    return next(rows[i] for i in range(1, len(rows) + 1) if rows[i][8] == "tram")


def _fz(part):
    return [part.fz[i] for i in range(1, len(part.fz) + 1)] if part.fz else []


def test_the_tram_stops_have_their_heights(game):
    _, ns = game
    t = _tram(ns)
    assert t.z1 == pytest.approx(96.6, abs=0.5)  # Stormwind's way in (AreaTrigger 2173)
    assert t.z2 == pytest.approx(508.2, abs=0.5)  # Ironforge's (AreaTrigger 2175)


def test_the_walk_to_the_tram_from_the_dwarven_district_stays_in_it(game):
    lua, ns = game
    t = _tram(ns)
    x, y, z = DWARVEN_DISTRICT
    r = None
    for _ in range(10):
        r = ns.Router.Route(0, x, y, t[2], t[3], lua.table(z=z, tz=t.z1))
        if not r.pending:
            break
        _pump(lua, ns)
    assert not r.pending
    assert r.length < 300
    assert max(_fz(r)) < KEEP_ROAD_Z


def test_the_route_to_ironforge_walks_to_the_tram_the_short_way(game):
    lua, ns = game
    N = ns.Nav
    N.SetDestination(IRONFORGE[0], IRONFORGE[1], 0, "Ironforge")
    r = None
    for _ in range(10):
        r = N.Route(DWARVEN_DISTRICT[0], DWARVEN_DISTRICT[1], 0)
        _pump(lua, ns)
    legs = [r.legs[i] for i in range(1, len(r.legs) + 1)]
    k = next(i for i, leg in enumerate(legs) if leg.ride and leg.ride[8] == "tram")
    walk = legs[k - 1]
    assert walk.walk and (walk.x2, walk.y2) == (_tram(ns)[2], _tram(ns)[3])
    assert walk.yards < 300  # (572 m, 620 yd, round by the keep before)
    assert max(_fz(r.parts[1])) < KEEP_ROAD_Z
    N.Clear()
