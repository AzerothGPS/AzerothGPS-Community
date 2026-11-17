"""The arrow doesn't look past stairs until they're reached (asked 2026-11-15: "for the arrow, there is a 'look ahead'
feature to prevent jerkiness but we need to consider if there are stairs to be taken the arrow doesn't look past that
until reached"): no further than the next flight's near end, then on it no further than its far end."""

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
    return lua, ns


def _along(path, x, y):
    """How far along `path` the point nearest (x, y) is."""
    pts = [path.pts[i] for i in range(1, len(path.pts) + 1)]
    cum = [path.cum[i] for i in range(1, len(path.cum) + 1)]
    best, bd = 0.0, math.inf
    for i in range(len(cum) - 1):
        ax, ay, bx, by = pts[2 * i], pts[2 * i + 1], pts[2 * i + 2], pts[2 * i + 3]
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2)) if L2 else 0.0
        d = (ax + vx * t - x) ** 2 + (ay + vy * t - y) ** 2
        if d < bd:
            best, bd = cum[i] + (cum[i + 1] - cum[i]) * t, d
    return best


@pytest.mark.parametrize("indoors", [False, True])
def test_the_arrow_aims_no_further_than_the_stairs_until_on_them(game, indoors):
    lua, ns = game
    N, G, T = ns.Nav, ns.GPS, ns.Turns
    N.ResetCityTrack()
    res = G.SearchPlaces("cooking trainer", 8)
    e = next(res[i] for i in range(1, len(res) + 1) if res[i].cont == 10001)  # (Undercity's, up on its platform)
    lua.execute(f"AGPS_MAP = 1458; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {e.x}, {e.y}, 0; "
                f"AGPS_T = (AGPS_T or 5000) + 100; IsIndoors = function() return {str(indoors).lower()} end")
    N.AnchorFloor(10001, e.x, e.y, e.z)
    N.SetStops(lua.eval("{ { x = 1611.7, y = 252.5, cont = 10001, z = -62, name = 'Bridge' } }"), False, "red")
    for _ in range(6):
        lua.execute("AGPS_T = AGPS_T + 0.3")
        G.Update()
    path = T.Ahead(N.route, "Bridge")[0]
    flights = T.Stairs(path, 200)
    assert len(flights) >= 1, "no stairs on the way down from the Cooking Trainer"
    f = flights[1]
    assert f.s0 > 5  # (ahead of the player, past STAIR_REACHED_YD)
    tx, ty = T.Target(path, e.x, e.y)
    assert _along(path, tx, ty) <= f.s0 + 0.5, "the arrow looked past the stairs before they're reached"
    # at their foot (or top): on to their far end, no further
    x, y = T.PointAt(path, f.s0)
    tx, ty = T.Target(path, x, y)
    a = _along(path, tx, ty)
    assert f.s0 < a <= f.s1 + 0.5
    lua.execute("IsIndoors = function() return false end")
    N.Clear()
