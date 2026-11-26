"""The common trips settle (item 56, a release blocker: Kooki3z's Orgrimmar to the Crossroads, the most common Horde trip
there is, showed "Working out the route..." for 4+ minutes on 0c5f60b9). Twenty of each faction's everyday trips (a
capital to the towns, flight masters and dungeons near it, town to town), level 60, the default settings: each must
settle (the route no longer pending) within its search budget, worked out as the game does (in slices between frames,
the player standing at the start). The budget is search nodes, not seconds (the same on every PC): NODE_BUDGET is about
10 s of the game's searching at its 1-5 ms a frame. `AGPS_TRIPS_REPORT=<file>` appends each trip's ticks and nodes to it."""

import os

import pytest

from test_map_redraw import game  # noqa: F401

NODE_BUDGET = 150000  # world grid + city grid nodes
# (trips with a budget of their own: his stop by Astranaar's guards, item 80, the way round their edge searched too:
# 153k on 2026-11-25)
BUDGETS = {"org-astranaar-nw": 180000}
MAX_TICKS = 2000  # frames worked (8 ms of searching each) before it counts as never settling

ORG = (1550.8, -4411.4)  # Orgrimmar, the Valley of Strength south of the bank (Kooki3z's start, item 56)
SW = (-8840.0, 600.0)  # Stormwind, the Trade District

HORDE = [
    ("org-crossroads", 1, ORG, (-441.8, -2596.1)),
    ("org-razor-hill", 1, ORG, (313.0, -4746.0)),
    ("org-senjin", 1, ORG, (-820.0, -4918.0)),
    ("org-valley-of-trials", 1, ORG, (-450.0, -4317.0)),
    ("org-ratchet", 1, ORG, (-951.0, -3680.0)),
    ("org-flight-master", 1, ORG, (1677.6, -4315.7)),
    ("org-fm-splintertree", 1, (1677.6, -4315.7), (2286.0, -2565.0)),
    ("crossroads-ratchet", 1, (-441.8, -2596.1), (-951.0, -3680.0)),
    ("crossroads-taurajo", 1, (-441.8, -2596.1), (-2353.0, -1922.0)),
    ("crossroads-wailing-caverns", 1, (-441.8, -2596.1), (-838.0, -2037.0)),
    ("tb-fm-bloodhoof", 1, (-1197.2, 29.7), (-2324.0, -395.0)),
    ("bloodhoof-red-cloud-mesa", 1, (-2324.0, -395.0), (-3217.0, -483.0)),
    ("taurajo-freewind", 1, (-2353.0, -1922.0), (-5454.0, -2446.0)),
    ("sun-rock-stonetalon-peak", 1, (936.0, 911.0), (2659.0, 1450.0)),
    ("undercity-fm-brill", 0, (1569.0, 268.0), (2250.0, 278.0)),
    ("brill-deathknell", 0, (2250.0, 278.0), (1880.0, 1588.0)),
    ("undercity-fm-sepulcher", 0, (1569.0, 268.0), (508.0, 1619.0)),
    ("sepulcher-shadowfang", 0, (508.0, 1619.0), (-217.0, 1583.0)),
    ("undercity-fm-tarren-mill", 0, (1569.0, 268.0), (-27.0, -901.0)),
    ("gadgetzan-fm", 1, (-7139.0, -3752.0), (-7224.0, -3735.0)),
    # (beside an enemy town, item 80: his stop north-west of Astranaar, pending 8 minutes on 1e503bf8)
    ("org-astranaar-nw", 1, (1545.9, -4412.4), (2862.756, -174.149)),
]
ALLIANCE = [
    ("sw-goldshire", 0, SW, (-9480.0, 64.0)),
    ("goldshire-northshire", 0, (-9480.0, 64.0), (-8850.0, -283.0)),
    ("goldshire-eastvale", 0, (-9480.0, 64.0), (-9450.0, -1417.0)),
    ("sw-sentinel-hill", 0, SW, (-10504.0, 1028.0)),
    ("sentinel-hill-moonbrook", 0, (-10504.0, 1028.0), (-11017.0, 1510.0)),
    ("lakeshire-darkshire", 0, (-9228.0, -2202.0), (-10565.0, -1171.0)),
    ("goldshire-lakeshire", 0, (-9480.0, 64.0), (-9228.0, -2202.0)),
    ("if-fm-kharanos", 0, (-4822.0, -1155.0), (-5586.0, -482.0)),
    ("kharanos-anvilmar", 0, (-5586.0, -482.0), (-6134.0, 384.0)),
    ("kharanos-thelsamar", 0, (-5586.0, -482.0), (-5349.0, -2960.0)),
    ("thelsamar-menethil", 0, (-5349.0, -2960.0), (-3673.0, -828.0)),
    ("darnassus-dolanaar", 1, (9952.0, 2254.0), (9788.0, 950.0)),
    ("dolanaar-shadowglen", 1, (9788.0, 950.0), (10583.0, 783.0)),
    ("astranaar-raynewood", 1, (2720.0, -382.0), (2683.0, -1750.0)),
    ("southshore-refuge-pointe", 0, (-803.0, -532.0), (-1251.0, -2527.0)),
    ("menethil-fm-town", 0, (-3792.0, -783.0), (-3673.0, -828.0)),
    ("booty-bay-fm-town", 0, (-14444.0, 510.0), (-14383.0, 487.0)),
    ("darkshire-eastvale", 0, (-10565.0, -1171.0), (-9450.0, -1417.0)),
    ("auberdine-fm-town", 1, (6341.4, 557.7), (6439.0, 412.0)),
    ("theramore-town", 1, (-3680.0, -4388.0), (-3817.0, -4550.0)),
    # (beside an enemy town, item 80: Astranaar to the edge of Splintertree Post)
    ("astranaar-splintertree", 1, (2720.4, -382.4), (2286.4, -2484.7)),
]
TRIPS = [("Horde",) + t for t in HORDE] + [("Alliance",) + t for t in ALLIANCE]


def settle(lua, ns, side, cont, start, stop):
    """The trip set and worked out as the game does: (ticks till settled or None, nodes searched, the route)."""
    R, N, WG, CG = ns.Router, ns.Nav, ns.WorldGrid, ns.CityGrid
    lua.execute(f"AGPS_LEVEL = 60; UnitFactionGroup = function() return '{side}' end")
    ns.CharDB().faction = side
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    WG.failed, WG.failOrder = lua.table(), lua.table()
    CG.routes, CG.order = lua.table(), lua.table()
    now = lua.eval("function() return os.clock() * 1000 end")
    R.Reset()
    R.SYNC_WALKS = False
    N.Clear()
    lua.execute(f"AGPS_POS = {{ {start[0]}, {start[1]}, {cont} }}")
    n0 = WG.stats.nodes + CG.stats.nodes
    N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
    r, settled = None, None
    try:
        for tick in range(MAX_TICKS):
            lua.execute(f"AGPS_T = {tick * 0.05}")
            r = N.Route(start[0], start[1], cont)
            t1 = now()
            while R.HasWork() and now() - t1 < 8:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if r and not r.pending:
                settled = tick
                break
            if WG.stats.nodes + CG.stats.nodes - n0 > NODE_BUDGET * 3:
                break  # (far past it: no need to see how far)
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
    return settled, WG.stats.nodes + CG.stats.nodes - n0, r


@pytest.mark.parametrize("side,name,cont,start,stop", TRIPS, ids=[t[1] for t in TRIPS])
def test_a_common_trip_settles_within_its_budget(game, side, name, cont, start, stop):  # noqa: F811
    lua, ns = game
    st, WG, CG = ns.settings.gps, ns.WorldGrid, ns.CityGrid
    saved = (st.worldGrid, st.cityGrid)
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    CG.Set(True)
    lua.execute("AGPS_UFG = UnitFactionGroup")
    try:
        ticks, nodes, r = settle(lua, ns, side, cont, start, stop)
        if os.environ.get("AGPS_TRIPS_REPORT"):
            with open(os.environ["AGPS_TRIPS_REPORT"], "a", encoding="utf-8") as f:
                f.write(f"{name}: ticks {ticks} nodes {nodes} yd {r and round(r.totalYards or 0)}" + chr(10))
        assert ticks is not None, f"{name}: never settled ({nodes} nodes)"
        assert nodes <= BUDGETS.get(name, NODE_BUDGET), f"{name}: {nodes} nodes"
    finally:
        lua.execute("UnitFactionGroup = AGPS_UFG; AGPS_LEVEL = nil")
        st.worldGrid, st.cityGrid = saved
        WG.Set(bool(saved[0]))
        CG.Set(bool(saved[1]))
        ns.Nav.Clear()


def test_the_first_route_after_login_orgrimmar_to_the_crossroads_settles():
    """Item 56b (Kooki3z couldn't get the 4 minutes again later: a first route after login?): a fresh start (nothing
    loaded, no road network built, no grid region in yet), its first route Orgrimmar to the Crossroads settles within
    the budget."""
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    ticks, nodes, r = settle(lua, ns, "Horde", 1, ORG, (-441.8, -2596.1))
    assert ticks is not None, f"never settled ({nodes} nodes)"
    assert nodes <= NODE_BUDGET and r.totalYards < 4000, (nodes, r.totalYards)


def test_a_route_never_waits_on_the_grid_for_good(game):  # noqa: F811
    """Item 56's safety net: a leg's grid search not in after WAIT_MAX_SECONDS (here: one that never ends, first in the
    queue), a fast search beside it (WorldGrid.HEUR_RUSH) and the slow one put behind the queue (Router.Demote): the
    trip settles on the fast one's walk (never the Router's own: no fallback)."""
    lua, ns = game
    R, N, WG, st = ns.Router, ns.Nav, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.cityGrid)
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    lua.execute("AGPS_UFG = UnitFactionGroup; AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    now = lua.eval("function() return os.clock() * 1000 end")
    try:
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
        R.Reset()
        R.SYNC_WALKS = False
        N.Clear()
        start, stop = (-441.8, -2596.1), (-2353.0, -1922.0)
        lua.execute(f"AGPS_T = 1000; AGPS_POS = {{ {start[0]}, {start[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        # (the trip's first grid search never ends; the others as they are)
        lua.execute("""AGPS_WS = AGPS_NS.WorldGrid.Search; AGPS_WS1 = false
          AGPS_NS.WorldGrid.Search = function(...)
            if not AGPS_WS1 then AGPS_WS1 = true while true do coroutine.yield() end end
            return AGPS_WS(...)
          end""")
        w0 = WG.stats.waitedOut or 0
        r = None
        for k in range(1600):
            lua.execute(f"AGPS_T = {1000 + k * 0.05}")
            r = N.Route(start[0], start[1], 1)
            t1 = now()
            while R.HasWork() and now() - t1 < 4:
                res = R.Pump(now() + 2, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if k * 0.05 < WG.WAIT_MAX_SECONDS:
                assert r is None or r.pending, k  # (waiting on the grid meanwhile)
            elif r and not r.pending:
                break
        assert r and not r.pending and (WG.stats.waitedOut or 0) > w0, (r and r.pending, WG.stats.waitedOut)
    finally:
        lua.execute("AGPS_NS.WorldGrid.Search = AGPS_WS")
        R.Reset()
        R.SYNC_WALKS = True
        lua.execute("UnitFactionGroup = AGPS_UFG; AGPS_LEVEL = nil")
        st.worldGrid, st.cityGrid = saved
        WG.Set(bool(saved[0]))
        N.Clear()


def test_a_long_leg_searched_in_vain_isnt_searched_again_from_round_there(game):  # noqa: F811
    """Item 59: Durotar to Un'Goro searched the long leg to the crater from Razor Hill, Ratchet's and Orgrimmar's
    flight masters, 200k nodes each, in vain. A failed long leg covers starts within FAIL_REUSE_YD, and within
    FAIL_SIDE_YD those no nearer the target; a start much nearer (Gadgetzan's) is searched."""
    lua, ns = game
    WG = ns.WorldGrid
    WG.failed, WG.failOrder = lua.table(), lua.table()
    tkey, stop = "1>-6900:-1200:-|test", (-6900.0, -1200.0)
    WG.Failed(tkey, 313.0, -4745.0, *stop)
    assert WG.FailedNear(tkey, 305.0, -4754.0, *stop)  # (the same spot)
    assert WG.FailedNear(tkey, -1004.0, -3837.0, *stop)  # (Ratchet: 2k round, nearer but not by much)
    assert WG.FailedNear(tkey, 1321.0, -4654.0, *stop)  # (Orgrimmar's flight master: further)
    assert not WG.FailedNear(tkey, -6929.0, -4954.0, *stop)  # (Gadgetzan: twice as near, far round)
    assert not WG.FailedNear("1>0:0:-|other", 313.0, -4745.0, *stop)
    WG.Reset()
    assert not WG.FailedNear(tkey, 305.0, -4754.0, *stop)


def test_a_leg_to_the_stop_cut_short_by_its_budget_is_never_skipped(game):  # noqa: F811
    # (items 80/81, Kooki3z by Astranaar: a long leg whose search was stopped by its node budget, the guards' cap and
    # the way through's included, was remembered as searched in vain and skipped for the rest of the session: the trip
    # pending for minutes, or round the world by Booty Bay's boat. A cut leg is still remembered (the ride check's legs
    # to far flight masters aren't searched again and again), but one to the trip's own stop never skipped.)
    lua, ns = game
    WG, N = ns.WorldGrid, ns.Nav
    stop = (-7155.0, -3780.0)  # (Gadgetzan: a long leg, past LONG_LEG_YD)
    tkey = "1>%d:%d:-|test" % stop
    WG.failed, WG.failOrder = lua.table(), lua.table()
    WG.Failed(tkey, ORG[0], ORG[1], stop[0], stop[1], True)
    N.stops = lua.table()
    assert WG.FailedNear(tkey, ORG[0] + 20, ORG[1], *stop)  # (a ride check's leg: skipped)
    N.stops = lua.eval("{ { x = %f, y = %f, cont = 1 } }" % stop)
    assert not WG.FailedNear(tkey, ORG[0] + 20, ORG[1], *stop)  # (the trip's stop: searched again)
    WG.Failed(tkey, ORG[0], ORG[1], stop[0], stop[1])  # (out of ground: no way, skipped even so)
    assert WG.FailedNear(tkey, ORG[0] + 20, ORG[1], *stop)
    N.stops = lua.table()
