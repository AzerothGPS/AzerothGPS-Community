"""A walk to the boat that's a long way round, on a trip to another continent (reported 2026-11-23: from Ironforge's
bank to Ratchet the route walked to Menethil Harbor's boat, 1,040 yd straight through the mountain and 8.3k yd round by
Loch Modan, never taking the gryphon from Ironforge to Menethil; from the Great Forge it flew). The ride check, which
plans again past a walk a long way round (Nav.WalkDetour), runs only for a stop on the player's continent: for one
across the sea Nav.WithoutBlockedWalks plans again past it."""

import pytest

IRONFORGE, MENETHIL, RATCHET = 6, 7, 80
RATCHET_STOP = (-894.6, -3773.0)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute('UnitLevel = function() return 30 end')  # (the Wetlands not too high: no detour weighed in for them)
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end')
    cdb = ns.CharDB()
    cdb.faction = "Alliance"
    cdb.taxiNodes = lua.eval(f"{{ [1415] = {{ nodes = {{ {{ nodeID = {IRONFORGE}, known = true }},"
                             f" {{ nodeID = {MENETHIL}, known = true }} }} }},"
                             f" [1414] = {{ nodes = {{ {{ nodeID = {RATCHET}, known = true }} }} }} }}")
    ns.Nav.FlightsChanged()
    return lua, ns


def _route_from(lua, ns, x, y):
    N = ns.Nav
    N.Clear()
    lua.execute(f"AGPS_MAP = 1455; AGPS_POS = {{ {x}, {y}, 0 }}")
    N.SetStops(lua.eval(f"{{ {{ x = {RATCHET_STOP[0]}, y = {RATCHET_STOP[1]}, cont = 1 }} }}"), False, "red")
    for _ in range(40):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        ns.GPS.Update()
    r = N.route
    assert r and r.legs
    return r


def _first_ride(r):
    for leg in r.legs.values():
        if leg.ride:
            return str(leg.ride[8]), str(leg.ride[10])
    return None


@pytest.mark.parametrize("spot", [(-4891.0, -917.0), (-4660.8, -953.6), (-4684.7, -1236.4)],
                         ids=["bank", "mystic ward", "explorers league"])
def test_ironforge_to_ratchet_flies_to_menethil_not_round_by_loch_modan(game, spot):
    lua, ns = game
    r = _route_from(lua, ns, *spot)
    kind, to = _first_ride(r)
    assert kind == "flight" and "Menethil" in to, (kind, to)
    assert r.walkYards < 2000, r.walkYards  # (the walk round by Loch Modan: 8.3k yd)


def test_from_the_great_forge_it_still_flies(game):
    lua, ns = game
    r = _route_from(lua, ns, -4763.4, -1107.8)
    kind, to = _first_ride(r)
    assert kind == "flight" and "Menethil" in to
