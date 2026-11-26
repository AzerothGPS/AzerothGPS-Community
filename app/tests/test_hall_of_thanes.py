"""Ironforge's Great Forge to the Hall of Thanes' way in (Kooki3z 2026-11-23, "Hall of Thanes route is still wrong";
the measured portal (-4822.3, -932.4), z 399.0, deep under the city). The way down is Kooki3z's recorded walk; its
turns wind over each other, and links between road pieces a floor apart (Router.BRIDGE_FLOOR_SLOPE, a yard of height
for every 1/0.3 yd across at most) cut through the rock between them: the Alliance, with no guards to weigh, took
them. A stop put there with no height gets the walk's floor (399), not the mountain's top over the city (856)."""

import math

import pytest

pytest.importorskip("lupa")

FORGE = (-4814.6, -1073.3, 502.25)
WAY_IN = (-4822.3, -932.4, 399.0)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.settings.gps.cityGrid = True
    ns.CharDB().faction = "Alliance"
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end')
    return lua, ns


@pytest.mark.parametrize("faction", ["Alliance", "Horde"])
def test_the_great_forge_to_the_hall_of_thanes_walks_the_recorded_way_down(game, faction):
    lua, ns = game
    ns.CharDB().faction = faction
    lua.execute(f'UnitFactionGroup = function() return "{faction}", "{faction}" end')
    try:
        ns.Router.Reset()
        r = ns.Router.Route(0, FORGE[0], FORGE[1], WAY_IN[0], WAY_IN[1],
                            lua.table_from({"z": FORGE[2], "tz": WAY_IN[2]}))
    finally:
        ns.CharDB().faction = "Alliance"
        lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end')
    n = len(r.pts) // 2
    pts = [(r.pts[2 * i - 1], r.pts[2 * i], r.fz[i]) for i in range(1, n + 1)]
    assert abs(pts[-1][2] - 399) < 3, pts[-1]
    # (down by the walk: no stretch a floor down in a straight line through the rock)
    for a, b in zip(pts, pts[1:]):
        if a[2] and b[2]:
            d = math.dist(a[:2], b[:2])
            assert abs(a[2] - b[2]) <= 5 + d * 0.6, (a, b)
    assert r.length > 450, r.length


def test_a_stop_at_the_way_in_with_no_height_gets_the_walk_s_floor_not_the_mountain_s(game):
    lua, ns = game
    z, src = tuple(ns.Nav.GuessStopZ(lua.table_from({"x": WAY_IN[0], "y": WAY_IN[1], "cont": 0})))
    assert src != "terrain" and abs(z - 399) < 5, (z, src)
