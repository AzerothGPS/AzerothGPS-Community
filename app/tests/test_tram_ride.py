"""In the Deeprun Tram the route is followed as a flight (reported 2026-11-15: a mage riding it from Ironforge to
Stormwind had the route worked out again inside it, "Teleport: Ironforge, walk 388 m to the flight master and fly to
Stormwind"). Its map is a level of its own (20369, base 369), so the old `cont == N.TRAM_MAP` never matched."""

import pytest

IRONFORGE_TRAM = (-4840.3, -1330.5)  # (Data/Transports.lua's tram row: Ironforge's end)
IN_THE_TRAM = (354.0, 2831.0)  # (the report: "Deeprun Tram 354, 2831")
STORMWIND_STOP = (-8830.0, 620.0)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    ns.CharDB().faction = "Alliance"
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end')
    return lua, ns


def test_riding_the_tram_from_ironforge_is_followed_to_stormwind(game):
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    assert N.InTram(369) and N.InTram(N.PlayerLevel(369))
    lua.execute(f"AGPS_MAP = 1455; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {IRONFORGE_TRAM[0]}, {IRONFORGE_TRAM[1]}, 0; "
                "AGPS_T = (AGPS_T or 3000) + 100")
    N.SetStops(lua.eval(f"{{ {{ x = {STORMWIND_STOP[0]}, y = {STORMWIND_STOP[1]}, cont = 0, name = 'Stormwind' }} }}"),
               False, "red")
    for _ in range(6):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
    assert N.route
    # into the tram (its own map)
    lua.execute(f"AGPS_MAP = nil; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {IN_THE_TRAM[0]}, {IN_THE_TRAM[1]}, 369")
    for k in range(10):
        lua.execute(f"AGPS_T = AGPS_T + 1; AGPS_POS[1] = {IN_THE_TRAM[0] + k * 10}")
        G.Update()
        r = N.route
        assert r and r.flying and r.flying.kind == "tram", "the route was worked out again inside the tram"
        assert r.flying.to == "Stormwind City"
    status = N.Status(IN_THE_TRAM[0], IN_THE_TRAM[1], 369)
    assert "Riding the Deeprun Tram to Stormwind City" in status and "arrives in" in status
    assert "Teleport" not in N.StepsText(9)
    # out at Stormwind's end: an ordinary route again
    lua.execute("AGPS_MAP = 1453; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8346.5, 514.0, 0; AGPS_T = AGPS_T + 1")
    G.Update()
    assert not (N.route and N.route.flying)
    N.Clear()
