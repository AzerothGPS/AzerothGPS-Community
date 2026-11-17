"""In a city, the next stop outside it (asked 2026-11-15: "pause recalculating routes while inside the city only for
destinations outside the city to save on compute"): the route is kept while the player walks it, not worked out again
every few seconds; off it, or out of the city, as before."""

import math

import pytest


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    ns.CharDB().faction = "Horde"
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end')
    lua.execute("AGPS_REAL_CITY_HOLD = AGPS_NS.Nav.CityHold")
    return lua, ns


VALLEY_OF_STRENGTH = (1630.0, -4380.0)  # (Orgrimmar's own cells)
RAZOR_HILL = (271.0, -4650.0)
TROLL_TRAINER = (1645.0, -4362.0)  # (in the city too)


def _walk(lua, ns, start, stop, steps, step_yd=2.0, secs=0.5):
    """Set the route, then walk it `steps` steps; how many times it was worked out again."""
    N, G = ns.Nav, ns.GPS
    lua.execute(f"AGPS_MAP = 1454; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {start[0]}, {start[1]}, 1")
    N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 1 }} }}"), False, "red")
    for _ in range(4):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    r = N.route
    assert r, "no route"
    pts = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    path = list(zip(pts[0::2], pts[1::2]))
    same = lua.eval("rawequal")
    worked, walked, last = 0, 0, N.route
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        n = max(1, int(math.hypot(bx - ax, by - ay) / step_yd))
        for k in range(1, n + 1):
            if walked >= steps:
                return worked
            x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
            lua.execute(f"AGPS_T = AGPS_T + {secs}; AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
            G.Update()
            walked += 1
            if N.route and not same(N.route, last):
                worked += 1
                last = N.route
    return worked


def test_walking_out_of_orgrimmar_to_razor_hill_the_route_is_kept(game):
    lua, ns = game
    N = ns.Nav
    assert N.InCapital(1, *VALLEY_OF_STRENGTH)
    assert _walk(lua, ns, VALLEY_OF_STRENGTH, RAZOR_HILL, 60) == 0, "worked out again walking it in the city"
    lua.execute("AGPS_NS.Nav.CityHold = function() return false end")
    try:
        assert _walk(lua, ns, VALLEY_OF_STRENGTH, RAZOR_HILL, 60) > 0  # (as before: every few seconds)
    finally:
        lua.execute("AGPS_NS.Nav.CityHold = AGPS_REAL_CITY_HOLD")


def test_a_stop_in_the_city_and_off_the_route_are_as_before(game):
    lua, ns = game
    N = ns.Nav
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {VALLEY_OF_STRENGTH[0]}, {VALLEY_OF_STRENGTH[1]}")
    N.SetStops(lua.eval(f"{{ {{ x = {TROLL_TRAINER[0]}, y = {TROLL_TRAINER[1]}, cont = 1 }} }}"), False, "red")
    assert not N.CityHold(VALLEY_OF_STRENGTH[0], VALLEY_OF_STRENGTH[1], 1)  # (the stop in the city: as before)
    N.SetStops(lua.eval(f"{{ {{ x = {RAZOR_HILL[0]}, y = {RAZOR_HILL[1]}, cont = 1 }} }}"), False, "red")
    assert N.CityHold(VALLEY_OF_STRENGTH[0], VALLEY_OF_STRENGTH[1], 1)
    assert not N.CityHold(RAZOR_HILL[0] + 300, RAZOR_HILL[1], 1)  # (out of the city: as before)
    # off the route in the city: worked out again
    G = ns.GPS
    for _ in range(4):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
    before = N.route
    lua.execute("AGPS_T = AGPS_T + 5; AGPS_POS[1], AGPS_POS[2] = 1680.0, -4440.0")  # (60 yd off, another way)
    G.Update()
    assert N.route and not lua.eval("rawequal")(N.route, before)
