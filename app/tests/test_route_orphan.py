"""A route never left waiting on nothing (item 80, Kooki3z on 1e503bf8: Orgrimmar to north-west of Astranaar pending for
8 minutes, "Mmmrrglllm... rrrgle mrgl?", no search running; a /reload and the same stop settled in seconds). His saved
routeDebug: the route pending, no points, its legs waiting. Nav.KickWait now works such a route out again after
ORPHAN_SECONDS with nothing queued for it; `/agps route` says what a route waits on (80c)."""

from azerothgps.gameharness import start

START = (1545.9, -4412.4)  # (his spot, routeDebug)
STOP = (2862.756, -174.149)  # (his stop: north-west of Astranaar)
BEFORE = [(1841.0, -4358.0), (-408.0, -2646.0), (-3083.0, -2849.0), (930.0, 951.0)]  # (his session's stops before)
FRAMES_SETTLE = 1000  # (8 ms of searching a frame: fresh, his stop settles in about 825, after his trips in about 290)


def _game():
    lua, ns = start()
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    ns.Router.SYNC_WALKS, ns.Router.WARM = False, True
    ns.Nav.FUN = False
    lua.execute("AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    return lua, ns


def _frames(lua, ns, n, until=None):
    N, G, R = ns.Nav, ns.GPS, ns.Router
    now = lua.eval("function() return os.clock() * 1000 end")
    for i in range(n):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.05")
        G.Update()
        G.PumpSearches()
        t1 = now()
        while R.HasWork() and now() - t1 < 8:
            res = R.Pump(now() + 4, now)
            done, fixed = res if isinstance(res, tuple) else (res, None)
            if done:
                N.SearchDone(fixed)
        if until and until():
            return i
    return None


def _trip(lua, ns, stop, frames):
    N = ns.Nav
    lua.execute(f"AGPS_MAP = 1454; AGPS_POS = {{ {START[0]}, {START[1]}, 1 }}")
    N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
    return _frames(lua, ns, frames, lambda: N.route is not None and not N.route.pending)


def test_his_stop_settles_after_his_session_s_trips():
    lua, ns = _game()
    for stop in BEFORE:
        _trip(lua, ns, stop, 1200)
    got = _trip(lua, ns, STOP, FRAMES_SETTLE)
    assert got is not None, "\n".join(str(x) for x in ns.Nav.WaitReport().values())


def test_a_route_left_waiting_on_nothing_is_worked_out_again():
    lua, ns = _game()
    N, WG = ns.Nav, ns.WorldGrid
    assert _trip(lua, ns, BEFORE[0], 1200) is not None
    # (his state: the route pending, nothing queued for it, as a search dropped from under it leaves it)
    N.route.pending = True
    orphans = WG.stats.orphans or 0
    got = _frames(lua, ns, 400, lambda: not N.route.pending)
    assert (WG.stats.orphans or 0) > orphans
    assert got is not None


def test_the_route_command_says_what_it_waits_on():
    lua, ns = _game()
    said = []
    was = ns.Print
    ns.Print = lambda s: said.append(str(s))
    try:
        lua.globals().SlashCmdList.AZEROTHGPS("route")
    finally:
        ns.Print = was
    assert said and said[0].startswith("route:") and any("grid searches:" in s for s in said)


def test_a_new_trip_never_waits_behind_the_last_one_s_searches():
    # (item 82h, Kooki3z on b84cff45: a 550 yd trip past the Shrine of the Fallen Warrior's hill, (-279.3, -2312.0) to
    # (-569.8, -2291.7), on "Working out the route..." for minutes, a job of an earlier route holding the queue; set
    # elsewhere and back, it settled at once. A new trip drops the last one's background jobs, Router.DropBackground)
    lua, ns = _game()
    N, R = ns.Nav, ns.Router
    lua.execute("AGPS_MAP = 1413; AGPS_POS = { -279.3, -2312.0, 1 }")
    N.SetStops(lua.eval("{ { x = -7155.0, y = -3780.0, cont = 1, name = 'far' } }"), False, "red")  # (Gadgetzan)
    got = _frames(lua, ns, 3000, lambda: R.HasWork() and not R.Warming())
    assert got is not None  # (the long trip's searches queued, its roads built)
    dropped = (R.stats.dropped or 0) if R.stats else 0
    N.SetStops(lua.eval("{ { x = -569.8, y = -2291.7, cont = 1, name = 'near' } }"), False, "red")
    assert (R.stats.dropped or 0) > dropped
    got = _frames(lua, ns, 40, lambda: N.route is not None and not N.route.pending)  # (2 s of frames)
    assert got is not None, chr(10).join(str(x) for x in N.WaitReport().values())


def test_a_region_loads_in_one_go_never_paused_half_loaded():
    # (item 82h: WorldGrid.LoadRegion marked the region, then paused (Router.Breathe) before taking its tiles: a search
    # in the pause took them for none for good, and a job dropped in it (a new trip's) left the region tileless for the
    # session; every walk there was then no way, remembered. Loaded in a job, it never yields now)
    lua, ns = _game()
    WG, R = ns.WorldGrid, ns.Router
    c = WG.Cont(1)
    was = R.Breathe
    R.Breathe = lua.eval("function() coroutine.yield() end")  # (every pause yields, as a slice running out does)
    try:
        got = lua.eval("""function(c)
          local rk
          for k in pairs(c.d.regions) do if c.regions[k] == nil then rk = k break end end
          local rx, ry = rk:match("(%d+):(%d+)")
          local t = coroutine.create(function() return AGPS_NS.WorldGrid.LoadRegion(c, tonumber(rx), tonumber(ry)) end)
          coroutine.resume(t)
          return coroutine.status(t), c.regions[rk]
        end""")(c)
        assert str(got[0]) == "dead" and got[1] is True  # (no pause half way: loaded)
    finally:
        R.Breathe = was
