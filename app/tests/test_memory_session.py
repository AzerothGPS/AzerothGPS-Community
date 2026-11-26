"""AzerothGPS's memory over a session of routes (item 59, Kooki3z 2026-11-24 on the live client: "AddOn Memory 551 MB
(374 MB AzerothGPS)"). Five cross-zone trips in the harness held 192 MB live and 113 MB kept: the far drops' cache
(WorldGrid's c.far) kept every surface it ever looked at (307k, 24 MB), and the searches' tables waited on the game's
own collector steps. Now the cache is two generations of FAR_CACHE_MAX, and a collector cycle runs in the background
whenever the heap has grown GC_GROWTH_MB. Budgets (the harness's Lua; 1.3.14 started at 31 MB, 1.4.0 at 35):
kept <= KEPT_MB, live (after the background's work) <= LIVE_MB (his game read 374 MB)."""

from test_common_trips_settle import settle
from test_map_redraw import game  # noqa: F401

KEPT_MB, LIVE_MB = 120, 220  # (live: when the collector last ran varies by machine, 152-178 over 98 kept seen in CI)
TRIPS = [("Horde", 1, (1550.8, -4411.4), (-5454.0, -2446.0)), ("Horde", 1, (313.0, -4746.0), (-3680.0, -4388.0)),
         ("Horde", 1, (1550.8, -4411.4), (2286.0, -2565.0)), ("Horde", 1, (-441.8, -2596.1), (936.0, 911.0)),
         ("Horde", 1, (1550.8, -4411.4), (2720.0, -382.0))]


def test_memory_stays_within_budget_over_a_session_of_cross_zone_trips(game):  # noqa: F811
    lua, ns = game
    st, WG, CG = ns.settings.gps, ns.WorldGrid, ns.CityGrid
    saved = (st.worldGrid, st.cityGrid)
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    CG.Set(True)
    mem = lua.eval("function() return collectgarbage('count') / 1024 end")
    full = lua.eval("function() collectgarbage('collect'); collectgarbage('collect'); return collectgarbage('count') / 1024 end")
    drain = lua.eval("""function()
      local R, n = AGPS_NS.Router, 0
      local now = function() return os.clock() * 1000 end
      while R.HasWork() and n < 5000 do R.Pump(now() + 4, now) n = n + 1 end
    end""")
    lua.execute("AGPS_UFG = UnitFactionGroup")
    try:
        for side, cont, a, b in TRIPS:
            ticks, nodes, r = settle(lua, ns, side, cont, a, b)
            assert ticks is not None, (a, b, nodes)
            drain()
            live = mem()
            kept = full()
            assert kept <= KEPT_MB, (a, b, kept)
            assert live <= LIVE_MB, (a, b, live, kept)
        c = WG.Cont(1)
        assert (c.farN or 0) <= WG.FAR_CACHE_MAX  # (the far drops' cache: two generations at most)
        assert (WG.stats.gcCycles or 0) > 0
    finally:
        lua.execute("UnitFactionGroup = AGPS_UFG; AGPS_LEVEL = nil")
        st.worldGrid, st.cityGrid = saved
        WG.Set(bool(saved[0]))
        CG.Set(bool(saved[1]))
