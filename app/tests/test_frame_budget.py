"""Frame budget: work that runs while the game plays must pause often, never freeze a frame.

Lag spikes have come back more than once (the first road display after a /reload, road and wall
edits): each check here is one of them. Times are CPU milliseconds under lupa, a little slower
than the game's Lua; the limits leave room for that and are far below the spikes they catch.
"""

import os

import pytest

from azerothgps.routecheck import _runtime

FRAME_MS = 40  # the longest a single slice of background work may run (the spikes were 100-300)
ON_CI = os.environ.get("CI") == "true"  # (GitHub Actions; the shared self-hosted runners, by turns 2-4x slower)


@pytest.fixture(scope="module")
def game():
    lua, ns = _runtime()
    lua.execute("GetTime = function() return os.clock() end")
    # (Undercity's level too: routes through its flight master built its roads in the frame)
    from azerothgps.routecheck import ADDON_DIR
    loader = lua.eval("function(src, name) return assert(load(src, '@' .. name)) end")
    for name in ("Data/Transports.lua", "Data/Cities.lua"):
        loader((ADDON_DIR / name).read_text(encoding="utf-8"), name)("AzerothGPS", ns)
    assert ns.Roads[10001]
    return lua, ns


def _drawn(lua, cont, x, y, n=8):
    """n drawn roads and a drawn wall near (x, y), as the road and wall tools save them."""
    rows = [f"{{ op = 'add', continent = {cont}, time = {i}, pts = {{ {x + i * 40},{y}, {x + i * 40 + 60},{y + 60}, "
            f"{x + i * 40 + 110},{y + 140} }} }}" for i in range(1, n + 1)]
    rows.append(f"{{ op = 'wall', continent = {cont}, time = 99, pts = {{ {x},{y - 50}, {x + 100},{y - 50} }} }}")
    return lua.eval("{ " + ", ".join(rows) + " }")


# (and Undercity, 10001: its roads were built in the frame on a route through its flight master)
@pytest.mark.timing
@pytest.mark.parametrize("cont, x, y", [(0, -9460.0, 60.0), (1, -450.0, -2650.0), (2991, 3000.0, 1000.0),
                                        (10001, 1600.0, 240.0)])
def test_the_road_network_rebuilds_in_short_slices(game, cont, x, y):
    lua, ns = game
    R = ns.Router
    ns.db.tracks = _drawn(lua, cont, x, y)
    R.WARM, R.SYNC_WALKS = True, False
    try:
        ns.Passability.RefreshWalls()
        R.Reset()  # (as after a road or wall edit, or a /reload)
        R.WarmUp(cont, x, y)
        clock = lua.eval("function() return os.clock() * 1000 end")
        worst = 0.0
        while R.HasWork():
            a = clock()
            R.Pump(clock() + 1, clock)
            worst = max(worst, clock() - a)
        assert worst < FRAME_MS, f"a slice of the rebuild ran {worst:.0f} ms"
        assert R.GraphReady(cont)  # (built: not a level with no roads here)
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        ns.db.tracks = None
        ns.Passability.RefreshWalls()
        R.Reset()


@pytest.mark.timing
def test_showing_the_roads_never_builds_them_in_the_frame(game):
    lua, ns = game
    G, R = ns.GPS, ns.Router
    R.WARM, R.SYNC_WALKS = True, False
    try:
        R.Reset()
        clock = lua.eval("function() return os.clock() * 1000 end")
        a = clock()
        G.LayoutRoads(-9460.0, 60.0, 0, 0, 600.0, 130.0)
        assert clock() - a < FRAME_MS
        assert not R.GraphReady(0)  # (left to the background work)
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        while R.HasWork():
            R.Pump(1e18, lua.eval("function() return 0 end"))
        R.Reset()


@pytest.mark.timing
def test_merging_many_drawn_roads_stays_cheap(game):
    """Every road or wall edit merges all the drawn roads not in the data yet into the network:
    that has to stay cheap as they pile up in a session (40 took about a second before)."""
    lua, ns = game
    rows = [f"{{ op = 'add', continent = 0, time = {i}, pts = {{ {-9460 + i * 37},{60 + (i % 5) * 50}, "
            f"{-9400 + i * 37},{120 + (i % 5) * 50}, {-9350 + i * 37},{200 + (i % 5) * 50} }} }}" for i in range(1, 41)]
    tracks = lua.eval("{ " + ", ".join(rows) + " }")
    clock = lua.eval("function() return os.clock() * 1000 end")
    a = clock()
    ns.Router.WithTracks(ns.Roads[0], tracks, 0)
    assert clock() - a < 250, f"merging 40 drawn roads took {clock() - a:.0f} ms"


@pytest.mark.timing
@pytest.mark.parametrize("cont", [0, 1])
def test_cave_entrances_are_worked_out_within_a_frame(game, cont):
    lua, ns = game
    clock = lua.eval("function() return os.clock() * 1000 end")
    a = clock()
    ns.GPS.CaveEntrances(cont)
    assert clock() - a < FRAME_MS


# (the overnight profile, 2026-10-07: the first route on a continent works out the other faction's guards' towns, every
# guard's circle joined to those it overlaps, and that ran in one piece: 180-220 ms, a hitch. The runtime above has no
# faction, so the guards were never weighed here: this one has, as in the game)
@pytest.mark.timing
@pytest.mark.parametrize("cont, side, x, y", [(0, "H", -9460.0, 60.0), (1, "A", -450.0, -2650.0)])
def test_the_road_network_with_a_faction_rebuilds_in_short_slices(cont, side, x, y):
    lua, ns = _runtime()  # (fresh: the guards' towns are worked out once per continent and side)
    lua.execute("GetTime = function() return os.clock() end")
    from azerothgps.routecheck import ADDON_DIR
    loader = lua.eval("function(src, name) return assert(load(src, '@' .. name)) end")
    loader((ADDON_DIR / "Data/Hostile.lua").read_text(encoding="utf-8"), "Data/Hostile.lua")("AzerothGPS", ns)
    ns.Nav = lua.eval("{ Faction = function() return '%s' end }" % side)
    R = ns.Router
    assert R.HostileSide() == side and ns.Hostile[cont][side]
    R.WARM, R.SYNC_WALKS = True, False
    R.Reset()
    R.WarmUp(cont, x, y)
    clock = lua.eval("function() return os.clock() * 1000 end")
    worst = 0.0
    while R.HasWork():
        a = clock()
        R.Pump(clock() + 1, clock)
        worst = max(worst, clock() - a)
    assert worst < FRAME_MS, f"a slice of the rebuild ran {worst:.0f} ms"
    assert R.GraphReady(cont)


@pytest.mark.parametrize("cont, x1, y1, x2, y2, most_mb", [
    (1, -3716.7, -5783.3, -83.3, 150.0, 3.5),  # (from out in the sea, no way there: every road looked at; 6.6 MB)
    (1, 250.0, -2950.0, 6783.3, -2783.3, 1.2),  # (Grol'dom Farm to Frostfire Hot Springs, 11k yd; 1.8 MB)
])
def test_a_long_routes_search_makes_little_garbage(game, cont, x1, y1, x2, y2, most_mb):
    # (the overnight trip sweep, 2026-10-07: a recalculation's road search made a table for each step it looked at, two
    # for a road, and one for each entry in its heap; redraws past 150 ms, a collection in them, 35 MB in one) the
    # steps by roads kept as numbers, the heap as two lists: the garbage of a long route's search, the collector stopped
    lua, ns = game
    R = ns.Router
    bench = lua.eval("""function(R, cont, x1, y1, x2, y2)
      R.Route(cont, x1, y1, x2, y2, { offroad = false }) -- (the graph, its walks and links: built once)
      collectgarbage('collect')
      collectgarbage('stop')
      local kb = collectgarbage('count')
      local r = R.Route(cont, x1, y1, x2, y2, { offroad = false })
      local mb = (collectgarbage('count') - kb) / 1024
      collectgarbage('restart')
      return mb, r.length
    end""")
    mb, length = bench(R, cont, x1, y1, x2, y2)
    assert length > 0
    assert mb < most_mb, f"{mb:.1f} MB"


def test_out_of_a_caves_chamber_joined_to_nothing(game):
    # (the overnight trip sweep, 2026-10-07) 82 pieces of the caves' roads are joined to nothing: no land road, no gap
    # link (chambers the caves' build didn't join to their mouths). Down in one, every route out was "No way there
    # found": Mulgore's Venture Co. Mine to Bloodhoof Village. Their roads aren't ones to get on or off at
    # (Router.Pieces, CaveLevel's `open`): the same cave's joined roads within SHUT_REACH_YD instead. None that near
    # (Emberstrife's Den: another cave's, 900 yd off): no way, as before, not a line through the mountain
    lua, ns = game
    R = ns.Router
    r = R.Route(1, -1501.5, -1036.2, -2307.0, -393.0, lua.eval("{ offroad = false }"))
    assert not r.noWay and not r.unconnected and r.length < 3000
    r = R.Route(1, -4987.7, -3833.0, -3150.0, -2850.0, lua.eval("{ offroad = false }"))
    assert r.noWay
    # (and never a line through the rock to a stand-in: Woodpaw Den's only one was 294 yd through it; no way instead)
    P = ns.Passability
    r = R.Route(1, -4835.2, 863.0, -4405.0, 222.0, lua.eval("{ offroad = false }"))
    for i in range(1, len(r.kinds) + 1):
        ax, ay, bx, by = r.pts[2 * i - 1], r.pts[2 * i], r.pts[2 * i + 1], r.pts[2 * i + 2]
        if r.kinds[i] != R.KIND_ROAD and ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 >= 100:
            assert r.noWay or P.SegmentCost(1, ax, ay, bx, by) is not None, (ax, ay, bx, by)


def test_a_walk_over_the_land_a_little_past_its_reach_when_the_roads_go_far_round(game):
    # (the overnight trip sweep, 2026-10-07) from Beggar's Haunt's door in Duskwood to Turner's Logging Camp, 3,016 yd
    # apart: past OFFROAD_WALK_AROUND (3,000), so roads only, 12.4k yd round; 75 yd nearer, the walk over the land was
    # 4.1k. Searched up to DETOUR_WALK_MAX when the roads go DETOUR_WALK_FACTOR times as far as the line. (Since the
    # Swamp of Sorrows roads drawn in game, issue #328, that trip's roads are 6.8k and taken; this one, 3,300 yd from
    # the same door, is 7.4k by the roads only and 3.4k with the walk. That spot was out at sea, closed since 1.3.10: now
    # the water still swum by the shore there, 3,180 yd away, 7.1k by the roads only and 3.2k with the walk)
    lua, ns = game
    R = ns.Router
    r = R.Route(0, -10451.0, -1527.0, -9480.0, 1500.0, lua.eval("{ offroad = false }"))
    assert r.length < 5000, r.length




@pytest.mark.timing
def test_a_restored_routes_first_update_never_builds_the_roads_in_the_frame():
    # (QA, 2026-10-07: right after login with a route restored, the arrow's first update followed the
    # player's floor (Nav.TrackCityZ -> Router.HeightsNear), which built Eastern Kingdoms' road network in the frame: a
    # 1.1 s hitch, "arrow window" 1115 ms) a road query in the frame starts the background warm-up and gets nothing
    # for now; the warm-up builds it in slices, and the queries answer after it
    import time

    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    R, N = ns.Router, ns.Nav
    R.Reset()  # (as at login: nothing built yet)
    R.WARM, R.SYNC_WALKS = True, False  # (the game's way)
    N.SetStops(lua.eval("{ { x = 1800, y = 220, cont = 0, name = 'x' } }"), False, "red")
    lua.execute("AGPS_T = AGPS_T + 0.25")
    t0 = time.perf_counter()
    N.Status(2254.0, 293.0, 0)  # (what the arrow's update runs first)
    assert not R.GraphReady(0), "the roads were built in the frame"
    assert (time.perf_counter() - t0) * 1000 < 200
    assert R.HeightsNear(0, 2254.0, 293.0, 20) is None and len(R.NearestEdges(0, 2254.0, 293.0)) == 0
    clock = lambda: time.perf_counter() * 1000.0
    for _ in range(4000):
        if R.GraphReady(0) and not R.HasWork():
            break
        R.Pump(clock() + 5, clock)
    assert R.GraphReady(0)
    assert len(R.NearestEdges(0, 2254.0, 293.0)) > 0  # (answered once built)


# (issue #322: walking by Brill's buildings, the player and the road point a walk was searched to stood in the cells of
# the walls drawn round them, shut in: each search flooded its whole box before giving up, about 200 slices of
# background work, and the next one from the player's new spot did it again, all the walk long)
SHUT_IN_WALKS = [(2328.0, 305.0, 2320.0, 297.0), (2328.0, 305.0, 2316.0, 295.0), (2252.0, 314.0, 2241.0, 306.0),
                 (2259.0, 354.0, 2272.0, 337.0)]


def _search_slices(lua):
    return lua.eval("""function(P, cont, x1, y1, x2, y2, road2)
      local co = coroutine.create(function() return P.FindPath(cont, x1, y1, x2, y2, false, road2) end)
      local n, ok, c, path = 0
      repeat ok, c, path = coroutine.resume(co); n = n + 1 until coroutine.status(co) == 'dead'
      assert(ok, c)
      return n, c, path and #path or 0
    end""")


@pytest.mark.parametrize("x1, y1, x2, y2", SHUT_IN_WALKS)
def test_a_walk_to_shut_in_cells_gives_up_at_once(game, x1, y1, x2, y2):
    lua, ns = game
    n, c, _ = _search_slices(lua)(ns.Passability, 0, x1, y1, x2, y2, True)
    assert c is None
    assert n <= 3, f"{n} slices to give up"


def test_giving_up_on_shut_in_cells_finds_the_same_walks(game):
    # (the shortcut is exact: the walks found, and those not, are the same as the search's own, round Brill's walls)
    lua, ns = game
    P = ns.Passability
    slices = _search_slices(lua)
    pairs = []
    for i, (x1, y1) in enumerate([(2328.0, 305.0), (2252.0, 314.0), (2259.0, 354.0), (2290.0, 297.0), (2300.0, 300.0)]):
        for k, (dx, dy) in enumerate([(-8, -8), (12, -4), (-14, 9), (6, 16), (30, -25), (-40, 5)]):
            pairs.append((x1, y1, x1 + dx, y1 + dy, (i + k) % 2 == 0))
    found = {}
    for limit in (P.SHUT_IN_CELLS, 0):
        P.SHUT_IN_CELLS = limit
        try:
            found[limit] = [slices(P, 0, *p)[1:] for p in pairs]
        finally:
            P.SHUT_IN_CELLS = 400
    assert found[400] == found[0]
    assert any(f[0] is None for f in found[0]) and any(f[0] is not None for f in found[0])


# (issue #348: the QA character is Alliance, the harness's Horde. As an Alliance player by Brill, the ride check was
# provisional every time, a walk in it still searched, and queued again at each recalculation: 2 s of background work a
# check, every slice of every frame for it, 160 to 200 ms a second live, though the rides take thousands of seconds
# against a 200 s walk)
# (timing: the background gets its work a frame by the CPU's clock, so a slow CPU rejoins the walk more)
@pytest.mark.timing
@pytest.mark.parametrize("faction", ["Horde", "Alliance"])
def test_walking_by_brills_buildings_keeps_the_terrain_search_small(faction):
    # (issue #322, the check c116-rt-c: from Brill's square to the Agamand Family Crypt's hills, zoomed in, the live
    # walk's "terrain search" was 100 ms a second, pumped on nearly every frame. The player steering by the arrow isn't
    # on the line: walked here up to 25 yd off it, by Brill's buildings, every walk searched from the player's spot to a
    # road point shut in by the walls drawn round them flooded its whole box first, about 1,500 slices in 30 s)
    import math

    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    G, N, R, T = ns.GPS, ns.Nav, ns.Router, ns.Turns
    ns.CharDB().faction = faction
    clock = lua.eval("function() return os.clock() * 1000 end")
    lua.globals().debugprofilestop = clock
    lua.execute("AGPS_POS[1], AGPS_POS[2] = 2300.0, 300.0")
    G.SetZoom(60)
    R.WARM, R.SYNC_WALKS = True, False
    R.CLOCK_PAUSES = False  # (its pauses counted as the work done: by the counts alone, issue #841)
    lua.execute("""
      AGPS_FRAME = function(dt)
        for _, w in ipairs(AGPS_WIDGETS) do
          local f = w._scripts.OnUpdate
          if f and w._shown then f(w, dt) end
        end
      end
      local P = AGPS_NS.Passability
      local fp = P.FindPath
      local searching = setmetatable({}, { __mode = "k" })
      P.FindPath = function(...) -- (each pause of a search: a slice of the background work)
        local co = coroutine.running()
        if co then searching[co] = true end
        local c, path = fp(...)
        if co then searching[co] = nil end
        return c, path
      end
      local R = AGPS_NS.Router
      local bg = R.Background
      local riding = setmetatable({}, { __mode = "k" })
      R.Background = function(key, fn, done) -- (the ride check's jobs, Nav's RideInstead)
        if string.sub(key, 1, 5) == "ride:" then
          local f = fn
          fn = function(...)
            riding[coroutine.running()] = true
            return f(...)
          end
        end
        return bg(key, fn, done)
      end
      AGPS_SEARCH_SLICES, AGPS_RIDE_SLICES = 0, 0
      local yield = coroutine.yield
      coroutine.yield = function(...)
        local co = coroutine.running()
        if co and searching[co] then AGPS_SEARCH_SLICES = AGPS_SEARCH_SLICES + 1 end
        if co and riding[co] then AGPS_RIDE_SLICES = AGPS_RIDE_SLICES + 1 end
        return yield(...)
      end""")
    frame = lua.eval("AGPS_FRAME")
    fps = 60
    t = float(lua.eval("AGPS_T"))

    def step(x=None, y=None):
        nonlocal t
        t += 1 / fps
        lua.execute(f"AGPS_T = {t}" + (f"; AGPS_POS[1], AGPS_POS[2] = {x}, {y}" if x is not None else ""))
        frame(1 / fps)

    N.SetStops(lua.eval("{ { x = 2867, y = 792, cont = 0, name = 'Hills' } }"), False, "red")
    for _ in range(fps * 90):
        if N.route:
            break
        step()
    assert N.route
    for _ in range(fps * 2):
        step()
    # (a background job finishing in the last frame may have dropped the route for its recalculation, N.Invalidate:
    # back on the next frames)
    for _ in range(fps * 10):
        if N.route:
            break
        step()
    assert N.route
    lua.execute("AGPS_SEARCH_SLICES, AGPS_RIDE_SLICES = 0, 0")
    path, yd = T.Path(N.route), 0.0
    for i in range(fps * 30):
        yd += 7.0 / fps
        x, y = T.PointAt(path, yd)
        step(x + 25 * math.sin(i / fps * 1.3), y + 25 * math.cos(i / fps * 0.9))
    slices = lua.eval("AGPS_SEARCH_SLICES")
    # (as Alliance its walk is rejoined more, Nav's Rejoin, weaving off it: 420 to 720 here, Horde 50 to 240; 1,500 before #322)
    assert slices < (400 if faction == "Horde" else 1000), f"{slices} slices of terrain search in 30 s"
    ride = lua.eval("AGPS_RIDE_SLICES")
    assert ride < 1000, f"{ride} slices of the ride check in 30 s"  # (12,000 as Alliance before)


def test_floor_heights_asked_in_the_frame_never_build_the_road_index_there(game):
    # (website issue #548, 2026-11-17: "screen tearing on a Variable Refresh Rate monitor with g-sync" with the addon on.
    # With V-Sync off G-Sync tears on a sudden long frame: walking in Brill after a login, the floor followed
    # (Nav.TrackCityZ) asked for the heights near and built the whole road index in the frame, 37 ms. Now none yet,
    # and the index built in the background's slices.)
    lua, ns = game
    R = ns.Router
    assert R.HeightsNear(0, -8990.0, 830.0, 10) is not None  # (built at once: the tests' way)
    g = R.DebugGraph(0)
    idx = g.segIndex
    assert idx is not None
    g.segIndex = None
    R.WARM, R.SYNC_WALKS = True, False
    try:
        assert R.HeightsNear(0, -8990.0, 830.0, 10) is None
        assert g.segIndex is None and R.HasWork()
        clock = lua.eval("function() return os.clock() * 1000 end")
        while R.HasWork():
            R.Pump(clock() + 1, clock)
        assert g.segIndex is not None
        assert R.HeightsNear(0, -8990.0, 830.0, 10) is not None
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        if g.segIndex is None:
            g.segIndex = idx


# (asked 2026-11-18, Kooki3z in game: "long routes going off course is causing lag spikes for each route". The capture's
# trip: a Horde level 24 from Kalimdor to Hillsbrad by Orgrimmar's flight, the zeppelin to Brill, Undercity's lift and
# Tarren Mill's flight, then Loch Modan and Westfall. Off the route with a short walk from the player, the whole plan
# was worked out in the frame, again every few seconds while off it: 20 to 40 ms each time here; off a long walk, the
# way back onto it was routed in the frame. Counted, not timed: a plan or a route in the frame is the hitch.)
REROUTE_STOPS = ("{ { x = -427.73204, y = -1909.33, cont = 0, name = 'Hillsbrad' }, "
                 "{ x = -4717.4475, y = -3226.72351, cont = 0, name = 'Loch Modan' }, "
                 "{ x = -10622.66492, y = 1641.17, cont = 0, name = 'Westfall' } }")


# (from 1100, 1150 the walk to Thunder Bluff's flight master is 400 yd: the whole plan again; from the capture's own
# spot it's 2,000 yd, past Nav.REJOIN_MIN_YD: the way back onto it)
@pytest.mark.timing
@pytest.mark.parametrize("sx, sy", [(1100.0, 1150.0), (1212.9, 1258.1)])
def test_going_off_course_on_a_long_route_works_nothing_out_in_the_frame(sx, sy):
    pytest.importorskip("lupa.lua51")
    from azerothgps import tripsweep as ts
    from azerothgps.gameharness import start

    lua, ns = start()
    N, R = ns.Nav, ns.Router
    N.FUN = False
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end; AGPS_LEVEL = 24')
    cdb = ns.CharDB()
    cdb.faction = "Horde"
    known = {1415: ts._masters(ns, 0, "H"), 1414: ts._masters(ns, 1, "H")}
    cdb.taxiNodes = lua.eval("{ " + ", ".join(f"[{m}] = {{ nodes = {{ "
                                              + "".join(f"{{ nodeID = {n}, known = true }}, " for n in ids) + "} }"
                                              for m, ids in known.items()) + " }")
    ns.Teleports.Changed()
    N.FlightsChanged()
    R.WARM, R.SYNC_WALKS = True, False
    lua.execute(f"AGPS_POS = {{ {sx}, {sy}, 1 }}")
    N.SetStops(lua.eval(REROUTE_STOPS), False, "red")
    lua.execute("""
      AGPS_WORK = { plans = 0, routes = 0 }
      local N, R = AGPS_NS.Nav, AGPS_NS.Router
      local plan, route = N.Plan, R.Route
      N.Plan = function(...) AGPS_WORK.plans = AGPS_WORK.plans + 1 return plan(...) end
      R.Route = function(...) AGPS_WORK.routes = AGPS_WORK.routes + 1 return route(...) end
    """)
    work = lua.eval("AGPS_WORK")
    clock = lua.eval("function() return os.clock() * 1000 end")

    def frame(x, y, budget):
        """One frame: the arrow's update in it (its plans and routes counted), then the background's slice."""
        lua.execute(f"AGPS_POS = {{ {x}, {y}, 1 }}; AGPS_T = AGPS_T + 0.1")
        work.plans, work.routes = 0, 0
        N.Status(x, y, 1)
        did = (work.plans, work.routes)
        if R.HasWork():
            R.Pump(clock() + budget, clock)
        return did

    for _ in range(400):  # (settled: the trip worked out, its searches done)
        frame(sx, sy, 50)
        if N.route and not R.HasWork():
            break
    assert N.route and not R.HasWork()
    rides = [str(N.route.legs[i].ride[10]) for i in range(1, len(N.route.legs) + 1) if N.route.legs[i].ride]
    assert rides[0] == "Orgrimmar, Durotar" and "Tarren Mill, Hillsbrad" in rides, rides
    # (5 ms of background work a frame, the reference PC's: on the CI runner, by turns 2-4x slower, as much work a
    # frame as that, `_cpu_slower`. Here, as before: 5 ms)
    budget = 5 * (_cpu_slower(lua) if ON_CI else 1)
    try:
        x, landed, frames = sx, 0, 0
        for _ in range(300):  # (walking east, away from the walk south-west to the flight master: 30 s off course)
            x += 0.7
            before = N.route
            plans, routes = frame(x, sy, budget)
            assert (plans, routes) == (0, 0), f"{plans} plans and {routes} routes in the frame, {x - sx:.0f} yd off"
            frames += 1
            if N.route is not before and N.route and abs(N.route.pts[1] - x) < 40:
                landed, frames = landed + 1, 0
            assert frames < 60, f"no route from where the player went ({budget:.1f} ms a frame)"  # (two reroutes' worth)
        assert landed >= 5  # (rerouted all the way, from the player's spot each time)
    finally:
        R.WARM, R.SYNC_WALKS = False, True


# (Bridges' sorts pause by the clock, Router.SortByFirst: a table.sort of 3,600 pairs was the slow-client test's worst
# slice on the CI runner, issue #841. It's Lua 5.1's sort step for step, so the order, ties too, is the game's
# and no route changes)
def test_sort_by_first_orders_as_the_games_table_sort():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    bad = lua.execute("""
      local R = AGPS_NS.Router
      math.randomseed(841)
      for _, n in ipairs({ 0, 1, 2, 3, 4, 5, 7, 12, 50, 101, 300, 3600 }) do
        for _, spread in ipairs({ 3, 40, 1e9 }) do
          local a, b = {}, {}
          for i = 1, n do
            local p = { math.random(1, spread), i }
            a[i], b[i] = p, p
          end
          table.sort(a, function(x, y) return x[1] < y[1] end)
          R.SortByFirst(b)
          for i = 1, n do
            if a[i] ~= b[i] then return n .. " pairs, spread " .. spread .. ": apart at " .. i end
          end
        end
      end""")
    assert bad is None, bad


# (issue #841, the live QA of #744: an Alliance level 12 in the Wetlands, a route to the bay below Stromgarde. Eastern
# Kingdoms' roads built in a route's job, not the warm-up's: the slices ran to 88 ms live, where the Lua is several times
# slower than here, the stutter watch counted them, and Routing was paused ("perf"): no route at all. Here the
# pump's clock runs LIVE_SLOWER times the CPU's, standing in for the live client: the loops pause by that clock, a slice
# of route work stays under STUTTER_MS, and the road data built once isn't counted at all)
# LIVE_SLOWER times a reference PC's, not this one's (issue #849: by this CPU's own wall clock every bound hung on the
# machine, and the CI runner, 2-3x slower and busy with the suite, failed by turns). The clock counts this thread's own
# CPU time (`_thread_ms`: the other processes' turns on the CPU aren't the client's work, and multiplied by 8 one was
# a 180 ms slice), and its factor is LIVE_SLOWER * SLOW_REF_MS / a fixed Lua workload's time (`_SLOW_WORK`, the best
# of SLOW_TIMINGS before the frames): a slower CPU gets a smaller factor, so the modeled client does as much a frame
# anywhere. SLOW_REF_MS is that best on the dev PC the 8x was tuned on, quiet, by that clock (2026-11-21: 3.3 to 3.4 ms).
# The factor was taken again before every frame (#938): the best of the last half second of frames' short
# timings, a best, not a median, as before. The CI runners share their PC's 8 cores (16 threads) with up to 15 job
# containers of 3 CPUs, so how much a CPU millisecond of this thread gets done swings 2-4x there for seconds at a time
# (the core's other thread busy, the VM's vCPU waiting: a thread's CPU clock counts those too). One factor from the
# start held a quiet moment's speed for minutes: the slices ran 2-3x long by it, 30 ms against 25 at "7.0x", on main
# and most PRs, 2026-11-21 to 23. A best of half a second of frames still finds the CPU's quick moments; on this PC
# its middle factor is the start's (6.4x vs 5.9-7.4x, 2026-11-23))
LIVE_SLOWER = 8
SLOW_REF_MS = 3.4
SLOW_TIMINGS = 9
SLOW_REF_RUNS = 40  # (the workload's rounds SLOW_REF_MS is for)
# (it makes no garbage: what it left would be the collector's work inside the route's slices, 476 ms ones)
_SLOW_WORK = """(function()
  local t, sqrt = {}, math.sqrt
  for i = 1, 1000 do t[i] = { i, 0, x = 0 } end
  local function step(p, i) p[2] = (p[2] + i * 7919) % 1000; p.x = p.x * 0.5 + sqrt(p[2]) end
  return function(n)
    local s = 0
    for r = 1, n do
      for i = 1, 1000 do
        local p = t[i]
        step(p, r)
        if p[2] < 500 then s = s + p.x else s = s - p[1] end
      end
    end
    return s
  end
end)()"""


def _thread_ms():
    """A clock of this thread's own CPU time, in ms. Linux (the CI runner): time.thread_time. Windows' is only as fine
    as the 15.6 ms tick, so there the thread's cycles (QueryThreadCycleTime), at the fastest rate a few spins see."""
    import sys
    import time

    if sys.platform != "win32":
        return lambda: time.thread_time() * 1000.0
    import ctypes

    k32 = ctypes.windll.kernel32
    k32.GetCurrentThread.restype = ctypes.c_void_p
    k32.QueryThreadCycleTime.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulonglong)]
    h, c = k32.GetCurrentThread(), ctypes.c_ulonglong()

    def cycles():
        k32.QueryThreadCycleTime(h, ctypes.byref(c))
        return c.value

    rate = 0.0
    for _ in range(5):
        c0, t0 = cycles(), time.perf_counter()
        while time.perf_counter() - t0 < 0.02:
            pass
        rate = max(rate, (cycles() - c0) / (time.perf_counter() - t0))
    return lambda: cycles() * 1000.0 / rate


def _cpu_slower(lua):
    """How many times slower than the reference PC this thread runs `_SLOW_WORK` right now (the best of SLOW_TIMINGS;
    never under 1)."""
    cpu, work = _thread_ms(), lua.eval(_SLOW_WORK)
    best = float("inf")
    for _ in range(SLOW_TIMINGS):
        c = cpu()
        work(SLOW_REF_RUNS)
        best = min(best, cpu() - c)
    return max(1.0, best / SLOW_REF_MS)


# (PR #993, 2026-11-24) The slow client's clock counts the Lua VM's instructions, not a CPU's time. By the CPU
# clock above (#849, #938) the test failed every try on main and the world grid chain on 2026-11-23/24 (6 of 8 main
# pushes after #988): on the CI runners a CPU millisecond got 2-4x less done from one moment to the next, and the
# workload's best, taken a frame before, didn't follow it, so route slices of 10-16 ms here read 28-172 ms there. On
# this PC the same clock also put the collector's steps into the slices: built slices of 63-80 ms with 90k instructions
# (by the count, 5 ms). Counting instructions, a slice is as long on every machine and every run: a loop in a job that
# doesn't pause is still as long as its steps, and the collector's work (no pause splits it) and the C functions'
# (one instruction a call) aren't counted. VM_PER_MS is the route work's own rate on the reference PC by the CPU clock
# above at LIVE_SLOWER: 18,200-18,600 instructions a millisecond (the reference dev PC, 2026-11-24; the workload's is 36,000)
VM_PER_MS = 18000
VM_HOOK = 1000  # (instructions a count: 0.06 ms of the modeled client)
# (a Lua 5.1 hook's function is kept per coroutine: a new one inherits the count but not the function, so the jobs'
# coroutines get theirs as they're made; the addon makes them with coroutine.create)
_VM_CLOCK = """(function(per_ms, every)
  AGPS_VM = 0
  local sethook, create, clock = debug.sethook, coroutine.create, debugprofilestop
  local function count() AGPS_VM = AGPS_VM + every end
  sethook(count, "", every)
  coroutine.create = function(f)
    local co = create(f)
    sethook(co, count, "", every)
    return co
  end
  debugprofilestop = function() return AGPS_T * 1000 + AGPS_VM / per_ms end
  return function()
    sethook()
    coroutine.create, debugprofilestop = create, clock
  end
end)"""


def test_route_work_on_a_slow_client_stays_in_its_slices_and_never_pauses_routing():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    N, R = ns.Nav, ns.Router
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end; AGPS_LEVEL = 12')
    ns.CharDB().faction = "Alliance"
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -3700.0, -900.0, 0")
    # (the frames' own time, and our work in them as the slow client's: VM_PER_MS instructions a millisecond)
    undo = lua.eval(_VM_CLOCK)(VM_PER_MS, VM_HOOK)
    R.Reset()  # (nothing built: as after a .go onto the continent)
    R.WARM, R.SYNC_WALKS = True, False
    N.STUTTER_WATCH = True
    grace = N.STUTTER_RESUME_GRACE
    N.STUTTER_RESUME_GRACE = 0  # (watched from the first frame)
    lua.execute("""
      AGPS_FRAME = function(dt)
        for _, w in ipairs(AGPS_WIDGETS) do
          local f = w._scripts.OnUpdate
          if f and w._shown then f(w, dt) end
        end
      end
      AGPS_SLICES = { worst = 0, counted = 0, built = 0 }
      local R = AGPS_NS.Router
      local pump = R.Pump
      R.Pump = function(deadline, now)
        local warm = R.Warming()
        local a = debugprofilestop()
        local f, x = pump(deadline, now)
        local d, s = debugprofilestop() - a, AGPS_SLICES
        s.worst = math.max(s.worst, d)
        if R.PumpBuilt and R.PumpBuilt() then
          s.built = s.built + 1
        elseif not warm then
          s.counted = math.max(s.counted, d) -- (what the stutter watch is given)
        end
        return f, x
      end""")
    frame = lua.eval("AGPS_FRAME")
    try:
        N.SetStops(lua.eval("{ { x = -1650, y = -1900, cont = 0, name = 'bay' } }"), False, "red")
        # (until the route, and half a minute on; within 10 minutes. By this CPU's own clock a slower one got less done
        # a frame: the route came 85 s in on a dev PC, past 120 s on the CI runner, PR #846)
        fps, t, left = 30, float(lua.eval("AGPS_T")), None
        for i in range(fps * 600):
            t += 1 / fps
            lua.execute(f"AGPS_T = {t}")
            frame(1 / fps)
            if left is None and (N.route or N.paused):
                left = fps * 30
            elif left is not None:
                left -= 1
                if left <= 0:
                    break
        s = lua.eval("AGPS_SLICES")
        seen = f"frame {i}, {lua.eval('AGPS_VM')} Lua instructions"
        print(seen, f"worst {s.worst:.1f} ms, counted {s.counted:.1f} ms")
        assert not N.paused, f"routing paused ({N.paused}); the worst slice counted ran {s.counted:.0f} ms; {seen}"
        assert not N.degraded, seen
        assert N.route, seen
        assert s.built > 0 and R.GraphReady(0)  # (the roads were built in a route's job, in slices)
        assert s.counted < N.STUTTER_MS, f"a slice of route work ran {s.counted:.0f} ms; {seen}"
        # (the road data's too, though not counted: 117 ms before. A table.sort Bridges did in one go made a 74 ms slice
        # on the CI runner: Router.SortByFirst. By the instruction count 22 ms, 2026-11-24)
        assert s.worst < 3 * N.STUTTER_MS, f"a slice ran {s.worst:.0f} ms; {seen}"
    finally:
        undo()
        N.STUTTER_WATCH, N.STUTTER_RESUME_GRACE = False, grace
        R.WARM, R.SYNC_WALKS = False, True
