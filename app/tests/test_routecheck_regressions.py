"""Trips `agps route-check` flagged, kept as regressions (the addon's real roads and terrain).

Each checks what route-check checks: the route isn't far longer than the terrain grid's own
walk, and its off-road stretches don't cross impassable ground (away from the ends).
"""

import math

import pytest

lupa = pytest.importorskip("lupa")

from test_addon_lua import PRELUDE, load, route_pts  # noqa: E402

DETOUR = {"offroad": (1.4, 150), "road": (2.5, 300)}  # as routecheck.py
BLOCKED_RUN_YD, END_ALLOW_YD = 25, 60


@pytest.fixture(scope="module")
def world():
    lua = lupa.LuaRuntime()
    lua.execute(PRELUDE)
    ns = lua.table()
    ns.IsSecret = lua.eval("function(v) return false end")
    load(lua, ns, "Geo.lua", "Data/Roads.lua", "Data/Terrain.lua", "Passability.lua", "Router.lua")
    ns.Router.SYNC_WALKS = True
    return lua, ns


def grid_walk(ns, cont, sx, sy, tx, ty):
    P = ns.Passability
    limits = (P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS)
    P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS = 400000, 900 * 900
    try:
        ref = P.FindPath(cont, sx, sy, tx, ty)
    finally:
        P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS = limits
    return ref[0] if isinstance(ref, tuple) else ref


def blocked_run(ns, cont, pts, kinds, start, stop):
    """Longest run of impassable ground the route's off-road stretches cross."""
    worst = run = 0.0
    for i, k in enumerate(kinds):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(seg / 3))
        for j in range(n + 1):
            x, y = x1 + (x2 - x1) * j / n, y1 + (y2 - y1) * j / n
            near_end = min(math.hypot(x - start[0], y - start[1]), math.hypot(x - stop[0], y - stop[1])) < END_ALLOW_YD
            if k == 1 and not near_end and ns.Passability.At(cont, x, y) == 2:
                run += seg / n
                worst = max(worst, run)
            else:
                run = 0.0
    return worst


def check_trip(world, cont, start, stop, mode):
    lua, ns = world
    ns.Router.Reset()
    r = ns.Router.Route(cont, *start, *stop, lua.table(offroad=(mode == "offroad")))
    pts, kinds = route_pts(r)
    walk = grid_walk(ns, cont, *start, *stop)
    assert walk is not None
    share, extra = DETOUR[mode]
    assert r.length <= max(walk * share, walk + extra), (r.length, walk)
    assert blocked_run(ns, cont, pts, kinds, start, stop) < BLOCKED_RUN_YD
    return r, walk


# Road mode walks straight there (around obstacles) when the roads go a long way round or
# are only reached across blocked ground (Router.ROAD_DIRECT_PENALTY).

def test_badlands_open_ground_between_ridges_no_loop_through_the_next_zones(world):
    # 389 yd apart in the middle of the Badlands, no road near: was a 15.8 km loop round
    # through Searing Gorge and Loch Modan, with legs over the ridges at both ends.
    r, _ = check_trip(world, 0, (-6716.9, -3378.6), (-6419.4, -3134.6), "road")
    assert r.length < 600


def test_alterac_stop_behind_a_ridge_is_walked_to_not_reached_over_it(world):
    # The last leg ran 371 yd straight over a ridge from a far-off road (1.3 km in all);
    # the walk round the ridge is 690 yd.
    r, _ = check_trip(world, 0, (106.4, -681.0), (-179.8, -190.9), "road")
    assert r.length < 900


def test_desolace_across_the_open_west_not_via_a_road_scrap_over_the_hills(world):
    check_trip(world, 1, (-2099.6, 1597.9), (-1707.0, 2864.0), "road")
    # and the ridge in the north-west: was 6.3 km round by the roads
    check_trip(world, 1, (-1177.8, 1319.5), (-1358.5, 1856.5), "road")


def test_road_mode_still_keeps_to_roads_that_are_only_somewhat_longer(world):
    # South of Razor Hill (Durotar) -> the Crossroads (Barrens): by the roads and the
    # Southfury bridge, not straight across country.
    lua, ns = world
    ns.Router.Reset()
    r = ns.Router.Route(1, -440.0, -4700.0, -450.0, -2640.0, lua.table(offroad=False))
    assert r.road > 0.8 * r.length


# A leg to or from the roads that the terrain blocks in a straight line, taken as a last
# resort (not one of the nearest few, which search the grid anyway), is walked around the
# obstacle once searched, like a gap between road pieces, instead of drawn over the ridge.

@pytest.mark.parametrize("cont, start, stop", [
    (0, (726.0, -579.9), (431.2, 207.7)),  # Alterac Mountains: over a ridge to the stop
    (0, (1039.2, -3791.9), (-73.4, -3558.4)),  # The Hinterlands: 360 yd over the hills
    (0, (-8771.7, -2812.3), (-9692.5, -3239.2)),  # Redridge Mountains: 313 yd
])
def test_blocked_legs_to_the_roads_are_walked_around(world, cont, start, stop):
    lua, ns = world
    ns.Router.ROAD_DIRECT_PENALTY = 1e9  # (the roads only: not walked straight there instead)
    try:
        ns.Router.Reset()
        r = ns.Router.Route(cont, *start, *stop, lua.table(offroad=False))
        pts, kinds = route_pts(r)
        assert r.road > 0
        assert blocked_run(ns, cont, pts, kinds, start, stop) < BLOCKED_RUN_YD
    finally:
        ns.Router.ROAD_DIRECT_PENALTY = 2


# Loch Modan (asked 2026-11-14, with a screenshot): the Maker's Terrace's roads are joined to the rest only by a link
# 195 yd over the cliffs to Stonesplinter Valley's, and the main road's stretch south of Thelsamar by one over the hill.
# Routes to the Terrace from the road north of Stonesplinter Valley (and the other way), and into the valley from the
# south, hopped the cliffs on that link, dotted. The user drew a wall there: none here. "No wall hopping allowed": by
# Thelsamar's roads and a walk over open ground instead, every leg off the roads clear of the cliffs.

@pytest.mark.parametrize("start, stop", [
    ((-5743.0, -2820.0), (-6116.7, -3250.0)),  # the road north of Stonesplinter Valley -> the Maker's Terrace
    ((-6116.7, -3250.0), (-5743.0, -2820.0)),
    ((-5800.0, -3350.0), (-5834.1, -2752.3)),  # from the south -> Loch Modan 27.5, 73.2
])
def test_loch_modan_no_hop_over_the_cliffs_by_the_makers_terrace(world, start, stop):
    lua, ns = world
    P = ns.Passability
    ns.Router.Reset()
    for _ in range(2):  # (fresh, and again with the hops known)
        r =ns.Router.Route(0, *start, *stop, lua.table(offroad=False))
        pts, kinds = route_pts(r)
        assert not r.unconnected
        hops = [(pts[i], pts[i + 1]) for i, k in enumerate(kinds)
                if k == 1 and P.SegmentCost(0, *pts[i], *pts[i + 1]) is None]
        assert hops == []
        assert r.hops == 0



# Grom'gol (Stranglethorn Vale, issue #676): a recorded walk up the zeppelin tower, its pieces and stairs 35 to 70 yd from
# the flight master, were the stop's nearest roads, all reached straight, and took every walk round
# (WALK_AROUND_CANDIDATES) from the road 430 yd off whose walk round the hill is the way: 540 yd by the roads, 13 points.

def test_a_walk_up_a_tower_by_the_stop_leaves_the_walk_round_to_the_further_road(world):
    lua, ns = world
    ns.Router.Reset()
    tower = [t for t in ns.FloorTracks[0].values() if t.time == 1795054079]
    assert len(tower) == 3  # (shipped, stairs and all)
    r = ns.Router.Route(0, -12113.5, -161.5, -12414.2, 146.3, lua.table(offroad=False))
    pts, kinds = route_pts(r)
    # (450 yd before Kooki3z's walk up the road to the tower, 2026-11-18 20.54, was drawn: the route now keeps to it, 543 yd)
    assert r.length < 560, (r.length, pts)
    assert blocked_run(ns, 0, pts, kinds, (-12113.5, -161.5), (-12414.2, 146.3)) < BLOCKED_RUN_YD


# Tarren Mill (Hillsbrad, issue #682): Kooki3z's road to the flight master (PR #665, time 1795057104), along the road
# there, split the roads by it; they were all the start's ENTRY_CANDIDATES, on the town's side, and the south road 204 yd
# off, the way south-east, wasn't one: 732 yd north through the town and back down. (The whole addon, as route-quality
# weighs it: H20 Ivar's Patch -> Chillwind Point, 411 s before the road, 460 s with it.)

def test_a_road_to_the_flight_master_leaves_the_walk_south_east_to_the_south_road():
    from azerothgps import gameharness

    lua, ns = gameharness.start()
    assert ns.RoadTracksIn[1795057104]  # (shipped)
    lua.execute("AGPS_LEVEL = 20; UnitFactionGroup = function() return 'Horde' end")
    ns.Router.Reset()
    r = ns.Router.Route(0, -0.1, -859.9, 516.7, -1450.0, lua.table())
    pts, kinds = route_pts(r)
    assert math.hypot(pts[1][0] - 165.3, pts[1][1] - -979.5) < 5, pts  # (straight onto the south road)
    assert max(y for _, y in pts) < -850, pts  # (not north through the town)
    assert r.length < 1250


# (PR #846: Brill inn rebuilt with 3 fewer nodes moved every later road id, and the nearest roads to
# Tarren Mill's flight master came out of pairs() in another order. The 8th and 9th are the same node's two roads,
# 145.6 yd off: the road west to the Hillsbrad crossroads fell out of the ENTRY_CANDIDATES, and the walk to Crown Guard
# Tower went round by the town's road, 3331 s -> 3365 s. Roads the same yards off are taken by edge, whatever the ids.)

def test_roads_the_same_yards_off_come_in_edge_order_whatever_the_ids():
    from azerothgps import gameharness

    lua, ns = gameharness.start()
    lua.execute("AGPS_LEVEL = 10; UnitFactionGroup = function() return 'Horde' end")
    R = ns.Router
    R.Reset()
    R.Route(0, -0.1, -859.9, 1850.0, -3750.0, lua.table())  # (the roads built)
    near = R.NearestEdges(0, -0.1, -859.9)
    got = [(near[i].dist, near[i].edge) for i in range(1, len(near) + 1)]
    ties = [(a, b) for a, b in zip(got, got[1:]) if a[0] == b[0]]
    assert len(ties) >= 3  # (the junctions by the flight master)
    assert got == sorted(got), [t for t in ties if t[0][1] > t[1][1]]
    for x, y in ((-0.1, -859.9), (1850.0, -3750.0), (-1816.7, -3316.7)):
        al = R.NearestEdgesAll(0, x, y)
        got = [(al[i].dist, al[i].edge) for i in range(1, len(al) + 1)]
        assert got == sorted(got)


def test_a_recorded_walks_top_isnt_joined_to_the_ground_road_by_its_foot(world):
    # (the same walk's top, 31 yd up the tower, ended 14 yd from its own way to the stairs' foot on the ground and was
    # joined onto it: a step from the ground onto the tower's top. WithTracks' LandHeightOK, R.LAND_CLIMB)
    lua, ns = world
    ns.Router.Reset()
    ns.Router.Route(0, -12113.5, -161.5, -12414.2, 146.3, lua.table(offroad=False))
    g = ns.Router.DebugGraph(0)
    top = None
    for k in range(1, int(g.count) + 1):
        if math.hypot(g.n[2 * k - 1] - -12415.5, g.n[2 * k] - 208.0) < 0.2:
            top = k
    assert top is not None, "the walk's top end is a node of its own, where it was recorded"
    at = [ei for ei in range(1, len(g.e) + 1) if top in (g.e[ei][1], g.e[ei][2])]
    assert len(at) == 1 and g.nz[top] and g.nz[top] > 30

@pytest.fixture(scope="module")
def caves_world():
    # (route-check's: the caves', capitals' and buildings' grids and roads too)
    from azerothgps.routecheck import _runtime

    return _runtime()


# Stormwind's canal walkway by the moored rowboats: where its floor (99-104) begins on the canal side, by x (measured from
# the city's model faces, 2026-10-08); the walkway lies to +y
SW_CANAL_EDGE = [(-8641, 936), (-8643, 939), (-8645, 941), (-8647, 944), (-8650, 942), (-8652, 940), (-8654, 938),
                 (-8658, 935), (-8662, 933), (-8666, 931), (-8669, 930)]


def test_stormwinds_street_by_the_canal_stays_on_the_walkway(caves_world):
    # (test walks, 2026-10-08: three tries on two trips stepped off into the canal at Stormwind 45.7, 58.1) the city's
    # street cut the canal's bend 2-6 yd out over the water at the walkway's height; a drawn fix (an erased loop and a
    # road 4 yd in) puts it on the walkway
    lua, ns = caves_world
    for start, stop in (((-8555.2, 1096.9), (-8802.0, 767.3)), ((-8229.2, 1128.1), (-8519.4, 862.9))):
        ns.Router.Reset()
        r = ns.Router.Route(0, *start, *stop, lua.table(offroad=False))
        pts, _ = route_pts(r)
        dense = []
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(x2 - x1, y2 - y1)))
            dense += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n)]
        for x, y in dense:
            if SW_CANAL_EDGE[-1][0] <= x <= SW_CANAL_EDGE[0][0] and 920 <= y <= 950:
                i = next(i for i in range(len(SW_CANAL_EDGE) - 1) if SW_CANAL_EDGE[i + 1][0] <= x)
                (ax, ay), (bx, by) = SW_CANAL_EDGE[i], SW_CANAL_EDGE[i + 1]
                edge = ay + (by - ay) * (x - ax) / (bx - ax)
                assert y >= edge + 1, (start, round(x, 1), round(y, 1), round(edge, 1))


def test_a_walk_onto_a_road_on_a_mountain_shelf_doesnt_climb_the_cliff_to_it(caves_world):
    # (random route tests, 2026-10-08: three tries into Ironforge stuck on the slope by Misty Pine Refuge's lake)
    # Ironforge's gate road runs on a shelf whose cells are all blocked; a walk onto it ended in blocked ground and got a
    # stop's STOP_SLACK (40 yd), enough to go up the cliff from the lake: 53-75 degree slopes. A road's point keeps
    # END_SLACK (Passability.FindPath's road1/road2): onto the switchback road below over open ground instead
    lua, ns = caves_world
    ns.Router.Reset()
    start, stop = (-5312.0, -904.0), (-5031.0, -825.0)  # (the lake's shore; the gate road by the gate)
    r = ns.Router.Route(0, *start, *stop, lua.table(offroad=False))
    pts, kinds = route_pts(r)
    assert blocked_run(ns, 0, pts, kinds, start, stop) < BLOCKED_RUN_YD
    assert r.road > 0.7 * r.length


def test_dun_algaz_goes_round_by_the_road_not_through_the_mountain(caves_world):
    # (reported, a screenshot) from the Dun Algaz road north: a 276 yd straight link through the mountain
    # from one cave mouth's road to another's (a gap link joining road pieces nothing else joined); the road
    # round, drawn in game, joins them now, and the route takes it
    lua, ns = caves_world
    ns.Router.Reset()
    r = ns.Router.Route(0, -4325.0, -2395.0, -4055.0, -2449.0, lua.table(offroad=False))
    pts, kinds = route_pts(r)
    assert r.length < 450
    assert max(math.dist(pts[i], pts[i + 1]) for i, k in enumerate(kinds) if k == 1) < 60


def test_ironforge_to_the_wetlands_by_the_roads(caves_world):
    # (reported, a screenshot: a straight line over the mountains, "Walk 2.2k yd") a road drawn by Dun
    # Algaz's cave mouths, once shipped, was a piece of its own nearer the Wetlands' roads than Dun Algaz's;
    # the gap link joining them, under BRIDGE_SHORT, was one of the nearest few per node, and the cave
    # mouth's shorter ones pushed it out: the Wetlands cut off from the south (every joining link kept now)
    lua, ns = caves_world
    for start in ((-5010.0, -800.0), (-8900.0, 600.0)):  # Ironforge's gate, Stormwind
        ns.Router.Reset()
        r = ns.Router.Route(0, *start, -3900.0, -2700.0, lua.table(offroad=False))
        assert not r.unconnected and r.road > 0.8 * r.length, start


def test_a_shipped_drawn_road_joins_the_cave_mouths_roads(caves_world):
    # (the same road: drawn in game from one cave mouth's road to another's, its ends joined them there;
    # shipped, the data's build joins drawn roads to the land's roads only) a loose end within TRACK_SNAP
    # of a cave's mouth joins it (Router.JoinDrawnEnds)
    lua, ns = caves_world
    ns.Router.Reset()
    ns.Router.Route(0, -4325.0, -2395.0, -4055.0, -2449.0, lua.table(offroad=False))
    g = ns.Router.DebugGraph(0)
    for end in ((-4097.1, -2465.9), (-4092.7, -2435.7)):
        n = min(range(1, int(g.count) + 1), key=lambda i: math.dist((g.n[2 * i - 1], g.n[2 * i]), end))
        assert math.dist((g.n[2 * n - 1], g.n[2 * n]), end) < 1 and g.adjIdx[n + 1] - g.adjIdx[n] >= 2, end


# Orgrimmar's Leatherworking hut on the Drag: its spiked west wall at a body's height (the city model's walls cut at
# 25.7, where a street crossed them, 2026-10-08)
ORG_LW_HUT_WALL = [((1854.74, -4547.47), (1849.32, -4550.98)), ((1850.9, -4551.23), (1852.37, -4550.27)),
                   ((1848.77, -4552.63), (1852.37, -4550.27))]


def _crosses(a, b, c, d):
    r, s = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return False
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    return 0 <= t <= 1 and 0 <= u <= 1


def test_orgrimmars_leatherworking_hut_is_gone_into_by_its_door(caves_world):
    # (a test walk the user watched, 2026-10-08: to the Leatherworking Trainer the character walked into the hut's spiked
    # wall, the door 5 yd to its right; and leaving him, H1-004 stuck at that wall) the city's street from the north
    # ran through the wall; erased, routes go round by the street through the door
    lua, ns = caves_world
    trainer = (1856.7, -4564.2)
    for a, b in (((1851.0, -4529.0), trainer), (trainer, (1851.0, -4529.0)), ((1830.0, -4520.0), trainer)):
        ns.Router.Reset()
        r = ns.Router.Route(1, *a, *b, lua.table(offroad=False, z=24.8, tz=24.8))
        pts, _ = route_pts(r)
        for p, q in zip(pts, pts[1:]):
            assert not any(_crosses(p, q, *w) for w in ORG_LW_HUT_WALL), (a, b, p, q)


def test_stormwinds_warrior_trainer_is_left_by_the_stairs_not_out_of_the_window(caves_world):
    # (a test walk, 2026-10-08, A1-015: upstairs in Old Town's Command Center the arrow said "Jump down here" at a
    # window, 112 -> 102) the walk grid's drops off ledges had no wall check, and the window's frame left a way
    # through its cells; a drop through a wall at a body's height is left out (walknet.wall_crosser)
    lua, ns = caves_world
    ns.Router.Reset()
    r = ns.Router.Route(0, -8688.5, 326.0, -8980.0, 1042.0, lua.table(offroad=False, z=109.5, tz=101.5, maxDrop=14))
    pts, kinds = route_pts(r)
    assert not r.unconnected
    drops = [(pts[i], pts[i + 1]) for i, k in enumerate(kinds) if k == ns.Router.KIND_DROP]
    assert not any(-8720 < x < -8700 and 320 < y < 340 for (x, y), _ in drops), drops


def test_a_fall_into_stormwinds_canal_swims_to_a_way_out(caves_world):
    # (asked 2026-10-08, q-117-canals: "a way out when you fall into a capital's canal"; A1-026's fall off the quay north
    # of the Trade District: the route from the water was a straight line up the quay's wall) a capital's water is a level
    # of its own (Data/Capitals.lua's `_water`, capitals.build_water): swimming in it, the route swims along it to the
    # nearest way out (the floor beside it at about its surface) and on by the streets; never by choice
    lua, ns = caves_world
    R = ns.Router
    spot, trainer = (-8482.0, 696.0), (-8433.7, 692.6)
    R.Reset()
    r = R.Route(0, *spot, *trainer, lua.table(offroad=False, swimming=True, tz=103.4))
    pts, kinds = route_pts(r)
    assert not r.unconnected and (r.swum or 0) > 10
    assert abs(r.fz[2] - 95) < 2  # (onto the swim road beside it, at the surface: not straight up to the quay's road, 100)
    # not swimming (a boat over it): as before, no swim
    R.Reset()
    assert not R.Route(0, *spot, *trainer, lua.table(offroad=False, swimming=False, tz=103.4)).swum
    # on land: never through the water (A1-026's own trip, the quay by it; a trainer by a pool's edge)
    for start, stop, cont, z, tz in (((-8978.1, 767.3), trainer, 0, 98.4, 103.4),  # (Orgrimmar's First Aid Trainer, Thunder
                                     ((1310.0, -4388.0), (1484.4, -4157.5), 1, None, 43.9),  # Bluff's Mage Trainer: by water)
                                     ((-1334.0, 176.0), (-954.4, 264.1), 1, None, 111.0)):
        R.Reset()
        o = {"offroad": False, "tz": tz}
        if z:
            o["z"] = z
        assert not R.Route(cont, *start, *stop, lua.table(**o)).swum, start


def test_orgrimmars_wind_rider_tower_is_the_way_up_to_the_valley_of_spirits(caves_world):
    # (reported 2026-11-12, a screenshot of the route to the First Aid Trainer: "there is a spiral staircase right here
    # that gets to the top and you can get to valley of spirits from there or go down cleft of shadow") the tower's
    # spiral was in the city's roads, but its walkway north off the top ended 9 yd short of the upper way west (the
    # floor goes on round its west side at 52): the routes went round by the Drag and up through the Cleft. A road
    # with its heights joins them (overrides/roads_1.geojson, Roads.lua's FloorTracks)
    lua, ns = caves_world
    R = ns.Router
    trainer = (1484.4, -4157.5)  # (Orgrimmar's First Aid Trainer, 43.9 up)
    for start, most in (((1630.0, -4380.0), 600), ((1690.0, -4330.0), 450)):  # (the bank; the tower's foot)
        R.Reset()
        r = R.Route(1, *start, *trainer, lua.table(offroad=False, tz=43.9))
        pts, _ = route_pts(r)
        assert r.length < most, (start, r.length)
        assert min(math.hypot(x - 1666.5, y + 4258.5) for x, y in pts) < 3, start  # (over the walkway's end)


def test_by_a_ragged_gap_in_ironforges_grid_the_spot_is_still_in_the_city(caves_world):
    # (a test walk, 2026-10-08: from the Mining Trainer's door, 14 yd from his spot, the route to the Warlock Trainer
    # went over the mountain, 1284 yd for 296) the city's cells round the door's barrels and crates are ragged: one
    # 1 yd off, none exactly CAVE_GAP_YD out, and the gap rule looked only that far. The nearest cell each way now
    lua, ns = caves_world
    for start in ((-4720.0, -1108.0), (-4718.0, -1110.0)):
        assert ns.Router.CaveDown(0, *start), start
        ns.Router.Reset()
        r = ns.Router.Route(0, *start, -4602.5, -1122.3, lua.table(offroad=False, tz=505.0))
        assert r.length < 400, (start, r.length)


def test_ironforges_tram_is_walked_to_inside_the_city(caves_world):
    # (reported, a screenshot: "10.4k yd to the Deeprun Tram" from Ironforge's Military Ward, and "the only
    # way walks through the Wetlands, Loch Modan") the tram's way in lies in a strip of the city's grid with
    # no cells, taken as up on the mountain: the walk went out by the gate and round. A gap that narrow
    # between the city's cells is down in the city (Router.CaveDown, CAVE_GAP_YD)
    lua, ns = caves_world
    R = ns.Router
    assert R.CaveDown(0, -4840.3, -1330.5)
    R.Reset()
    r = R.Route(0, -4944.0, -1232.0, -4840.3, -1330.5, lua.table(offroad=False))
    assert r.length < 400


@pytest.mark.parametrize("cont, start, stop", [
    (0, (-4750.6, -1483.4), (-4621.7, -1226.9)),  # by Ironforge: 10.4 km round, the walk 308 yd
    (1, (-853.6, 25.1), (-1463.3, -254.1)),  # by Thunder Bluff: over 31 yd of blocked ground
])
def test_trips_by_a_capitals_roads_keep_their_walk(caves_world, cont, start, stop):
    # (route-check, 2026-10-06) the rule against the flat terrain walk to a trainer upstairs in a building went by the
    # height of the road nearest the stop; a capital's roads have heights too, and trips ending by Ironforge's or
    # Thunder Bluff's lost their walk. It goes by the stop's (or the start's) own height in a building with its inside
    # (Router's offFloor)
    check_trip(caves_world, cont, start, stop, "offroad")


def test_a_stop_in_the_other_factions_town_is_reached_by_the_road(caves_world):
    # (reported 2026-10-02, overnight route tests: Tarren Mill to Dun Garok came back as a straight walk over
    # Hillsbrad's hills, ignoring the roads) Dun Garok is the Alliance's: the road into it runs past its guards,
    # and their reach cost 20 times a yard, so walking in over the hills looked cheaper. A route doesn't pay
    # for the guards of a town it starts or ends in (R.HostileTownsNear), as with the zones it starts and ends in;
    # passing another town still does. (Since 2026-11-16 the enemy areas are the NPCs that would flag a player for PvP:
    # Dun Garok's Mountaineers flag no one, so the town here is Southshore, its guards)
    lua, ns = caves_world
    from test_addon_lua import load  # noqa: F401  (the addon's own loader)
    had = ns.Hostile
    load(lua, ns, "Data/Hostile.lua")
    nav = ns.Nav
    ns.Nav = lua.eval("{ Faction = function() return 'H' end }")
    try:
        ns.Router.Reset()
        r = ns.Router.Route(0, -34.1, -923.4, -850.0, -540.0, lua.table(offroad=False))
        assert not r.unconnected and r.road > 0.8 * r.length, (r.road, r.length)
        # (Southshore's guards form one town; the trip ends in it)
        towns = ns.Router.HostileTownsNear(0, "H", -850.0, -540.0)
        assert towns and len(list(towns.keys())) >= 1
        assert ns.Router.HostileTownsNear(0, "H", -34.1, -923.4) is None  # (Tarren Mill: the Horde's own)
    finally:
        ns.Nav, ns.Hostile = nav, had
        ns.Router.Reset()


def test_route_check_weighs_the_other_factions_guards_with_a_faction():
    # (the overnight sweeps, 2026-10-07: route-check had no faction, so routes past the other faction's towns were never
    # checked as a character's are) `--faction A|H` loads the guards and gives the Router its side; none, none
    from azerothgps.routecheck import _runtime

    _, ns = _runtime()
    assert ns.Router.HostileSide() is None
    _, ns = _runtime("A")
    assert ns.Router.HostileSide() == "A" and ns.Hostile[0]["A"]


def test_route_check_takes_a_way_round_the_other_factions_guards_for_no_detour():
    # (the overnight sweep, 2026-10-07) as an Alliance character, Western Plaguelands' trip round The Bulwark (Horde
    # guards) is twice the grid's walk, which goes past them: the addon's own option, not a detour. route-check measures
    # the reference walk's yards within their reach (guard_yards) and doesn't flag a route longer for them.
    # (The Deathguard patrol that closed the gap north of the ruins, three circles, left Data/Hostile.lua in the 1.4.0
    # audit as a lone patrol: with the gap open there's no detour left to measure, so the test puts them back itself)
    from azerothgps.routecheck import _runtime, guard_yards

    lua, ns = _runtime("A")
    P, R = ns.Passability, ns.Router
    guards = ns.Hostile[0].A
    for v in (1713, 511, 45, 1729, 553, 45, 1751, 512, 45):
        guards[len(guards) + 1] = v
    R.HostileChanged()
    P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS = 400000, 900 * 900
    ref = P.FindPath(0, 937.1, -147.8, 2003.9, -298.9)
    assert isinstance(ref, tuple) and guard_yards(R, 0, ref, "A") >= 50
    assert guard_yards(R, 0, ref, None) == 0 and guard_yards(R, 0, ref, "H") < 50
    r = R.Route(0, 937.1, -147.8, 2003.9, -298.9, lua.table(offroad=True))
    # (round them: the detour the guards explain. 1.4.1's one-way ground (item 107) made the walk past them 1.7k yd, was
    # 2.5k, and the Router's price for the guards' reach (HOSTILE_FACTOR) now takes it over the 4.6k round them: then
    # never more of it in their reach than the reference walk)
    pts = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    inside = sum(R.HostileYards(0, pts[i], pts[i + 1], pts[i + 2], pts[i + 3], "A") for i in range(0, len(pts) - 3, 2))
    assert r.length > ref[0] * 1.4 or inside <= guard_yards(R, 0, ref, "A") + 1


def test_the_wetlands_valley_1314_opens_is_walked_up_not_hopped(world):
    # (1.3.14's grid reopens a valley through the Wetlands' hills, its quads all gentle; route-check flagged its walks
    # as crossing blocked ground: the cave's grid under it (Data/Caves.lua's rock), which the terrain walk ignores, as
    # route-check now does. On the land's own grid the walk is over open ground)
    check_trip(world, 0, (-3642.8, -3143.4), (-3554.3, -2199.9), "offroad")
