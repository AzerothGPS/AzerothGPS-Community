"""Whelgar's Excavation Site (Wetlands; a player's report with their drawn road): routes to Excavation Leader Whelgar,
in the cave at the dig site, were wrong from every side. The terrain grid closes the dig site's pit and the gap
north of it (walkable ground: its way down isn't the terrain's), so the cave's way out was walked 824 yd round over
the hills to a road in the south-west, routes looped round to it or walked through the rock, and the terrain was
searched again from each new spot on every reroute. Now the player's road (river road, the gap between the hills,
the dig site's east side) leads to the mouth, the cave's way out joins it there, and the last stretch in is by the
cave's own road, not a walk through its rock."""

import math
from collections import Counter

import pytest

WHELGAR = (-3592.0, -1995.0)
MOUTH = (-3564.0, -1962.0)  # (the cave's mouth node, Data/Caves.lua's cave68442679)
GAP = (-3420.0, -1922.0)  # (the gap between the hills on the player's road)
OLD_JOIN = (-3976.0, -1516.0)  # (the far road the old way out ran to)
STARTS = {
    "Menethil": (-3606.0, -869.3),  # (Wetlands 11.6, 52.9)
    "east": (-3705.2, -2759.2),  # (Wetlands 57.3, 56.5)
    "north": (-3212.4, -1761.9),  # (the river road north of the site)
}


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("""
      AGPS_FP = { goals = {} }
      local P = AGPS_NS.Passability
      local real = P.FindPath
      P.FindPath = function(cont, x1, y1, x2, y2, ...)
        if AGPS_FP.on then
          local k = string.format("%.0f,%.0f", x2, y2)
          AGPS_FP.goals[k] = (AGPS_FP.goals[k] or 0) + 1
        end
        return real(cont, x1, y1, x2, y2, ...)
      end
    """)
    return lua, ns


def _route(lua, ns, start):
    N, G = ns.Nav, ns.GPS
    ns.Router.Reset()
    lua.execute(f"AGPS_MAP = 1437; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {start[0]}, {start[1]}, 0")
    N.SetStops(lua.eval(f"{{ {{ x = {WHELGAR[0]}, y = {WHELGAR[1]}, cont = 0 }} }}"), False, "red")
    for _ in range(6):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    r = N.route
    assert r, "no route"
    p = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    return r, list(zip(p[0::2], p[1::2])), [r.kinds[i] for i in range(1, len(r.kinds) + 1)]


def _near(pts, spot, yd):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1)))
        if any(math.hypot(x1 + (x2 - x1) * k / n - spot[0], y1 + (y2 - y1) * k / n - spot[1]) <= yd for k in range(n + 1)):
            return True
    return False


@pytest.mark.parametrize("name", list(STARTS))
def test_whelgar_is_reached_from_the_north_through_the_cave_mouth(game, name):
    lua, ns = game
    P = ns.Passability
    start = STARTS[name]
    r, pts, kinds = _route(lua, ns, start)
    assert not r.unconnected and not r.noWay
    assert _near(pts, GAP, 15), "not in through the gap north of the dig site"
    assert _near(pts, MOUTH, 5), "not in by the cave's mouth"
    assert not _near(pts, OLD_JOIN, 100), "by the old way out round the hills"
    # (no stretch off the roads over ground the terrain or the cave's rock closes: the start's own spot aside)
    for i, k in enumerate(kinds):
        if k != ns.Router.KIND_OFFROAD:
            continue
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        n = max(1, int(math.hypot(x2 - x1, y2 - y1)))
        shut = sum(1 for j in range(n + 1)
                   if math.hypot(x1 + (x2 - x1) * j / n - start[0], y1 + (y2 - y1) * j / n - start[1]) > 60
                   and P.At(0, x1 + (x2 - x1) * j / n, y1 + (y2 - y1) * j / n) == 2)
        assert shut <= 4, ((round(x1), round(y1)), (round(x2), round(y2)), shut)


def test_the_caves_way_out_joins_the_road_at_its_mouth(game):
    # (its way out ran from the mouth's ground 824 yd round over the hills to a road in the south-west)
    lua, ns = game
    ns.Router.Reset()
    ns.Router.Route(0, -3212.4, -1761.9, *WHELGAR, lua.table(offroad=False))
    g = ns.Router.DebugGraph(0)

    def node(i):
        return g.n[2 * i - 1], g.n[2 * i]

    near = [i for i in range(1, int(g.count) + 1) if math.dist(node(i), MOUTH) < 60]
    assert near
    caves = 0
    for i in near:
        for k in range(int(g.adjIdx[i]), int(g.adjIdx[i + 1])):
            if g.cave[int(g.adjE[k])]:  # (the cave's own roads and its way out)
                caves += 1
                assert g.adjLen[k] < 100, (node(i), node(int(g.adjTo[k])), g.adjLen[k])
    assert caves


@pytest.mark.parametrize("name", ["Menethil", "north"])
def test_walking_to_whelgar_doesnt_search_the_terrain_again_from_every_spot(game, name):
    # (the player's debug log: "terrain search" 150-270 ms a second while walking, spikes over 1 s: walks to the far
    # way out and to the shut-in mouth searched again from each new spot on every reroute)
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    _, pts, _ = _route(lua, ns, STARTS[name])
    lua.execute("AGPS_FP.goals = {}; AGPS_FP.on = true")
    try:
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(bx - ax, by - ay) / 8))
            for k in range(1, n + 1):
                x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
                lua.execute(f"AGPS_T = AGPS_T + 1; AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
                G.Update()
    finally:
        lua.execute("AGPS_FP.on = false")
    goals = Counter({k: v for k, v in lua.eval("AGPS_FP.goals").items()})
    assert sum(goals.values()) <= 50, goals.most_common(8)
    assert max(goals.values(), default=0) <= 4, goals.most_common(8)
