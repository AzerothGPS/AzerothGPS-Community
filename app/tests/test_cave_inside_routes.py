"""Routes to stops inside caves (item 84c, a 1.4.0 release blocker). Kooki3z (Horde 60, just west of the Wailing Caverns'
hill) double-clicked a spot inside the caverns with the cave's inside view up: the route hung on its faded line,
"Charging extra for the shortcut...", never settling. The stop's floor (the portal's, z 19) isn't on the world grid's
tunnels from the mouth (docs/world-grid-1.4.0.md section 11), so its search took the leg's whole node budget, then the
ride check searched the same stop again from Ratchet's, Thunder Bluff's and Orgrimmar's flight masters, and so on.

Now (WorldGrid.CaveLeg) a stop inside any cave in Data/Caves.lua is reached by the grid's walk to the cave's mouth, then
the cave's own roads inside (the dotted path on its map); and a stop the grid can't reach from a short leg's start
within its budget (WorldGrid.Unreached) is no way at once for every other leg and plan to it: "No way found yet"."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("lupa.lua51")

START = (-817.9, -1862.7)  # (Kooki3z's spot, just west of the hill; DB map 1, z 91.7)
STOP = (-666.9, -2226.7)  # (his stop inside, ~394 yd east-north-east, the cave's floor there)
WC = "cave371662"
MAX_TICKS = 1200  # (frames worked, 8 ms of searching each, 0.05 s apart: 60 s of game time)
SETTLE_TICKS = 200  # (10 s)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    lua.execute("AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    yield lua, ns
    st.worldGrid, st.cityGrid = False, False


def settle(lua, ns, start, stop, z, cont=1, ticks=MAX_TICKS):
    """The trip worked out as the game does (in slices between frames): (ticks till settled, a route or no way, or
    None; the route or None; nodes searched)."""
    R, N, WG = ns.Router, ns.Nav, ns.WorldGrid
    WG.Reset()
    now = lua.eval("function() return os.clock() * 1000 end")
    R.Reset()
    R.SYNC_WALKS = False
    N.Clear()
    lua.execute(f"AGPS_POS = {{ {start[0]}, {start[1]}, {cont} }}")
    n0 = WG.stats.nodes
    N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = {cont}, z = {z}, name = 'stop' }} }}"), False, "red")
    r, settled = None, None
    # (the game's clock only goes on: a trip after another, its timers in the past)
    t0 = float(lua.globals().AGPS_T or 0) + 1000
    try:
        for tick in range(ticks):
            lua.execute(f"AGPS_T = {t0 + tick * 0.05}")
            r = N.Route(start[0], start[1], cont)
            t1 = now()
            while R.HasWork() and now() - t1 < 8:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if (r and not r.pending) or (r is None and N.noWayGrid and not N.warming):
                settled = tick
                break
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
    return settled, r, WG.stats.nodes - n0


def points(r):
    out = []
    for i in range(1, len(r.parts) + 1):
        p = r.parts[i]
        if p.pts:
            for k in range(1, len(p.pts) + 1, 2):
                fz = p.fz and p.fz[(k + 1) // 2]
                out.append((p.pts[k], p.pts[k + 1], fz if isinstance(fz, (int, float)) else None))
    return out


def floor_inside(ns, x, y):
    G = ns.GPS
    G.hoveredCave = G.CaveAt(1, x, y)
    try:
        return G.ClickFloorZ(1, x, y)
    finally:
        G.hoveredCave = None


def test_his_stop_inside_the_wailing_caverns_is_routed_in_by_the_mouth(game):
    lua, ns = game
    z = floor_inside(ns, *STOP)
    assert z is not None and z < 40, z  # (the cave's floor there, not the hill's top over it)
    ticks, r, nodes = settle(lua, ns, START, STOP, z)
    assert ticks is not None and ticks <= SETTLE_TICKS, (ticks, nodes)
    assert r is not None and not r.noWay, "no route"
    pts = points(r)
    ways = [(-765.0, -1984.0), (-815.0, -2074.0)]
    near = min(math.hypot(x - wx, y - wy) for x, y, _ in pts for wx, wy in ways)
    assert near <= 60, f"not by the cave's mouth ({near:.0f} yd)"
    # (never over the hill (its top 190): down from the mouth, ~80, along the cave's path to the floor)
    zs = [fz for _, _, fz in pts if fz is not None]
    assert max(zs) < 100, max(zs)
    assert abs(zs[-1] - z) <= 3, (zs[-1], z)
    # (the cave's own path inside: the last stretch is under the hill, each point over the cave's grid)
    WG = ns.WorldGrid
    inside = [p for p in pts if p[2] is not None and WG.InCave(1, p[0], p[1], p[2], WG.CAVE_DOOR_Z) == WC]
    assert len(inside) >= 10, len(inside)
    assert r.totalYards < 1000, r.totalYards


def test_a_stop_the_grid_cant_reach_settles_as_no_way_found_yet(game):
    """The hang itself: with no cave road to take (CaveLeg off, as for a cave without one), the stop's floor off the
    grid settles as "No way found yet" (the gap logged), never searched again from the flight masters."""
    lua, ns = game
    WG, N = ns.WorldGrid, ns.Nav
    z = floor_inside(ns, *STOP)
    lua.execute("AGPS_CAVELEG = AGPS_NS.WorldGrid.CaveLeg; AGPS_NS.WorldGrid.CaveLeg = function() return nil end")
    gaps0 = len(WG.gaps)
    try:
        ticks, r, nodes = settle(lua, ns, START, STOP, z)
    finally:
        lua.execute("AGPS_NS.WorldGrid.CaveLeg = AGPS_CAVELEG")
    assert ticks is not None, f"never settled ({nodes} nodes)"
    assert r is None and N.noWayGrid, "not no way"
    assert WG.StopUnreached(1, *STOP)
    # (the leg's own search, round the guards and through them, and nothing more: no flight master's walk searched)
    budget = WG.NODES_BASE + WG.NODES_PER_YD * math.dist(START, STOP)
    assert nodes <= 2 * budget + 1000, nodes
    assert len(WG.gaps) > gaps0 or any(abs(g.x2 - STOP[0]) < 1 for g in WG.gaps.values())


def test_an_unreached_stop_is_forgotten_after_a_while(game):
    lua, ns = game
    WG = ns.WorldGrid
    WG.Reset()
    lua.execute("AGPS_T = 1000")
    WG.Unreached(1, 10.0, 20.0, 5.0)
    assert WG.IsUnreached(1, 10.0, 20.0, 5.0) and WG.StopUnreached(1, 10.0, 20.0)
    assert not WG.IsUnreached(1, 10.0, 20.0, 50.0)  # (another floor there)
    lua.execute(f"AGPS_T = {1000 + WG.UNREACHED_SECONDS + 1}")
    assert not WG.StopUnreached(1, 10.0, 20.0) and not WG.IsUnreached(1, 10.0, 20.0, 5.0)
    WG.Unreached(1, 10.0, 20.0, 5.0)
    WG.Reset()
    assert not WG.IsUnreached(1, 10.0, 20.0, 5.0)


def test_the_route_inside_the_cave_is_drawn_faded_from_outside(game):
    """Item 84d (Kooki3z on 48a626d9): the stretch under the hill drawn faded while the player's outside (the floor fade,
    G.FloorFade: the cave path's points carry their heights), full on the floor he's on once he's in there."""
    lua, ns = game
    G, N, WG = ns.GPS, ns.Nav, ns.WorldGrid
    z = floor_inside(ns, *STOP)
    ticks, r, _ = settle(lua, ns, START, STOP, z)
    assert ticks is not None and r is not None
    lua.execute("AGPS_NS.GPS.floorFadeCache = setmetatable({}, { __mode = 'k' })")
    N.ResetTrack()
    try:
        def alphas(px, py, pz):
            lua.execute("AGPS_T = (AGPS_T or 5000) + 1")
            N.SetTrackForTests(1, px, py, pz)
            out = []
            for i in range(1, len(r.parts) + 1):
                p = r.parts[i]
                if not (p.pts and int(p.cont) == 1):
                    continue
                for k in range(1, len(p.pts) // 2):
                    x, y = (p.pts[2 * k - 1] + p.pts[2 * k + 1]) / 2, (p.pts[2 * k] + p.pts[2 * k + 2]) / 2
                    zs = p.zs or p.fz
                    zk = zs and zs[k + 1]
                    deep = isinstance(zk, (int, float)) and WG.InCave(1, x, y, zk, WG.CAVE_UNDER_YD) == WC
                    out.append((deep, G.FloorFade(r, p, k)))
            return out

        outside = alphas(START[0], START[1], 91.7)
        deep = [a for d, a in outside if d]
        assert len(deep) >= 10
        # (under the hill: faded by the shared floor-fade rule, G.FloorFadeAlpha, never below its least, G.FLOOR_FADE_MIN)
        assert max(deep) < 1 and min(deep) >= G.FLOOR_FADE_MIN - 1e-9, deep
        assert any(abs(a - G.FLOOR_FADE_MIN) < 1e-9 for a in deep), deep  # (the deep floor: the least alpha)
        assert all(a == 1 for d, a in outside[:2])  # (the walk to the mouth, on the land: as it was)
        inside = alphas(STOP[0], STOP[1], z)
        assert inside[-1][1] == 1  # (on the stop's floor: full)
    finally:
        N.ResetTrack()
        N.Clear()


@pytest.mark.parametrize("style", ["seamless", "minimap"])
def test_a_routes_cave_shows_its_inside_at_any_zoom(style):
    """Item 84d: while the route's stop is inside a cave, its inside view stays up at any zoom (past the inside maps'
    zoom limit), on the GPS map in either style (world-map mode and the minimap draw the same view), until the route's
    cleared."""
    from test_atlas import _seamless
    lua, ns = _seamless(on=style == "seamless")
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    z = floor_inside(ns, *STOP)
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = {START[0]}, {START[1]}, 1, 0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    lua.execute("AGPS_NS.GPS.CursorWorld = function() return nil end")
    N.dest = lua.eval(f"{{ x = {STOP[0]}, y = {STOP[1]}, cont = 1, z = {z} }}")
    try:
        for zoom in (80.0, 600.0, 3000.0):
            st.zoom = zoom
            G.Follow()
            G.Update()
            assert G.shownView.cave is not None and G.hoveredCave == WC, (style, zoom)
        N.dest = None
        G.Update()
        assert G.shownView.cave is None
    finally:
        N.dest = None
