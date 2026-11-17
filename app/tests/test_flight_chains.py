"""One flight where one flight goes there, not landing and boarding again mid-way (issue #372).

Reported 2026-11-15 (1.2.8, Alliance, 16 flight paths): "fly to Stormwind, then fly on to Menethil" from Sentinel Hill.
A flown trip's recorded seconds are on the taxi only (Taxi.lua), a trip never flown was costed yards / FLIGHT_SPEED plus
FLIGHT_OVERHEAD, so two flown trips chained (Sentinel Hill > Stormwind 82 s, Stormwind > Menethil 343 s: 425 s) beat
the one flight never flown (445 s estimated) though it flies over Stormwind anyway."""

import pytest

SENTINEL_HILL, STORMWIND, MENETHIL, IRONFORGE = 4, 2, 7, 6


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def _plan(lua, ns, flights):
    N, G = ns.Nav, ns.GPS
    cdb = ns.CharDB()
    cdb.faction = "Alliance"
    nodes = "".join(f"{{ nodeID = {n}, known = true }}, " for n in (SENTINEL_HILL, STORMWIND, MENETHIL, IRONFORGE))
    cdb.taxiNodes = lua.eval(f"{{ [1415] = {{ nodes = {{ {nodes} }} }} }}")
    cdb.flights = lua.eval("{" + ", ".join(
        f'["{a} > {b}"] = {{ from = "{a}", to = "{b}", seconds = {s}, samples = 1 }}' for a, b, s in flights) + "}")
    N.FlightsChanged()
    lua.execute("AGPS_MAP = 1436; AGPS_POS = { -10628.9, 1036.7, 0 }")  # (at Sentinel Hill's flight master)
    N.SetStops(lua.eval("{ { x = -3792.3, y = -783.3, cont = 0 } }"), False, "red")  # (Menethil's)
    for _ in range(30):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    return N.StepsText(99)


def test_two_flown_trips_dont_beat_the_one_flight_over_the_same_way(game):
    lua, ns = game
    steps = _plan(lua, ns, [("Sentinel Hill, Westfall", "Stormwind, Elwynn", 82),
                            ("Stormwind, Elwynn", "Menethil Harbor, Wetlands", 343)])
    assert "Menethil" in steps, steps
    assert steps.count("Take the flight") == 1 and "Stormwind" not in steps, steps  # (was: to Stormwind, then on)


def test_a_flown_trip_still_wins_over_its_estimate(game):
    lua, ns = game
    steps = _plan(lua, ns, [("Sentinel Hill, Westfall", "Menethil Harbor, Wetlands", 400)])
    assert steps.count("Take the flight") == 1 and "Menethil" in steps, steps
