"""A short leg whose way is long round settles (item 139, Kooki3z 2026-11-27: level 60 Alliance, no flight paths, on
Darkshore's west coast road at 40.2, 64.2, to Felwood behind the ridge at (5322, -655); Roads or shortcuts +10, elites
avoided at -10: after 5 minutes still the straight line and the provisional ones, and Felwood's elite area by the stop
"keeps flashing"). The stop is 985 yd off in a straight line, the walk 8-9k yd south through Ashenvale and up Felwood's
road; the grid's search floods the shut-in coast first, ~135k nodes, over the short leg's budget (109k) and the guards'
cap (80k, Bloodvenom Post beside the line) at every Road tolerance: cut short, the stop "unreached" for two minutes and
searched again the same way. Now a short leg to a stop gets the whole budget (WorldGrid.MAX_NODES) at once, and one cut
short even then is no way for good from round there (WorldGrid.EXHAUSTED_YD): "No way found yet", never searched
again. The enemy areas shown near the route stay steady while it's worked out (Nav.EnemyZonesNearSteady).
Budget: nodes, not the clock. On 20738978 (before): ~150 s of game time at 0, +10 and -10 alike, 420k nodes."""

import pytest

from test_map_redraw import game  # noqa: F401

START = (5529.9, 308.6)  # (Darkshore 40.2, 64.2: Data/Maps.lua's bounds)
STOP = (5322.0, -655.0)
NODE_BUDGET = 180000
DT = 0.05  # (game seconds a tick: 15 ms of search each, about the game's landing slices, GPSFrame's WARM_MS a frame)


def _setup(lua, ns, tol):
    R, N, WG, st = ns.Router, ns.Nav, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd, st.avoidElites, st.eliteOffset,
             st.avoidHostile, st.avoidHighZones, st.showAvoided)
    st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd = True, True, tol, 60
    st.avoidElites, st.eliteOffset, st.avoidHostile, st.avoidHighZones, st.showAvoided = True, -10, True, True, True
    WG.Set(True)
    lua.execute("AGPS_139 = { UnitFactionGroup }; AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Alliance' end")
    ns.CharDB().faction = "Alliance"
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    R.Reset()
    R.SYNC_WALKS = False
    return saved


def _teardown(lua, ns, saved, now):
    R, N, WG, st = ns.Router, ns.Nav, ns.WorldGrid, ns.settings.gps
    while R.HasWork():
        R.Pump(now() + 50, now)
    R.SYNC_WALKS = True
    lua.execute("UnitFactionGroup = AGPS_139[1]; AGPS_LEVEL = nil")
    (st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd, st.avoidElites, st.eliteOffset, st.avoidHostile,
     st.avoidHighZones, st.showAvoided) = saved
    WG.Set(bool(saved[0]))
    N.Clear()


def _run(lua, ns, ticks, now, shown=None):
    """Ticks the trip; returns the settled route or None. `shown`: a list each tick's shown enemy areas go to."""
    R, N = ns.Router, ns.Nav
    for tick in range(ticks):
        lua.execute(f"AGPS_T = {100 + tick * DT}")
        r = N.Route(START[0], START[1], 1)
        t1 = now()
        while R.HasWork() and now() - t1 < 15:
            res = R.Pump(now() + 4, now)
            done, fixed = res if isinstance(res, tuple) else (res, None)
            if done:
                N.SearchDone(fixed)
        if shown is not None:
            z = N.EnemyZonesShown(1, STOP[0] - 1500, STOP[1] - 1500, STOP[0] + 1500, STOP[1] + 1500, START[0],
                                  START[1], N.route)
            shown.append({int(z[i][4]) for i in range(1, len(z) + 1)})
        if r and not r.pending:
            return r
    return None


@pytest.mark.parametrize("tol", [10, 0])
def test_darkshore_to_felwood_settles_round_the_ridge(game, tol):  # noqa: F811
    lua, ns = game
    N, WG = ns.Nav, ns.WorldGrid
    now = lua.eval("function() return os.clock() * 1000 end")
    saved = _setup(lua, ns, tol)
    n0 = WG.stats.nodes
    try:
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {START[0]}, {START[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {STOP[0]}, y = {STOP[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        shown = []
        r = _run(lua, ns, 1200, now, shown)  # (a minute of game time; 11-12 s now)
        assert r is not None, "never settled"
        assert WG.stats.nodes - n0 <= NODE_BUDGET, WG.stats.nodes - n0
        # (the walk round: south through Ashenvale and up Felwood's road, not a line over the ridge)
        xs = [r.parts[i].pts[k] for i in range(1, len(r.parts) + 1) for k in range(1, len(r.parts[i].pts) + 1, 2)]
        assert 7000 < r.totalYards < 11000 and min(xs) < 3500, (r.totalYards, min(xs))
        assert not r.throughGuards
        # (the enemy areas shown stay up while it's worked out: none hidden and shown again)
        gone = set()
        for a, b in zip(shown, shown[1:]):
            assert not (b & gone), sorted(b & gone)
            gone |= a - b
    finally:
        _teardown(lua, ns, saved, now)


def test_a_short_leg_cut_short_with_the_whole_budget_is_no_way_for_good(game):  # noqa: F811
    lua, ns = game
    N, WG = ns.Nav, ns.WorldGrid
    now = lua.eval("function() return os.clock() * 1000 end")
    saved = _setup(lua, ns, 10)
    old = (WG.MAX_NODES, WG.HOSTILE_CAP)
    WG.MAX_NODES, WG.HOSTILE_CAP = 40000, 30000  # (a budget this way can't be found within)
    WG.hpaOff = True  # (the grid's own search's budget: HPA*, item 127, finds this way in 33k nodes)
    try:
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {START[0]}, {START[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {STOP[0]}, y = {STOP[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        assert _run(lua, ns, 1200, now) is None
        assert (WG.stats.exhausted or 0) >= 1
        # (said, not searched again: each start the trip's plans try (here, and Auberdine's dock) once, then never,
        # past the stop's "unreached" two minutes and on; before, the same 190k-node search every two minutes)
        assert _run(lua, ns, 6000, now) is None
        n1 = WG.stats.nodes
        assert _run(lua, ns, 6000, now) is None
        assert WG.stats.nodes == n1, WG.stats.nodes - n1
        assert N.noWayGrid and N.Route(START[0], START[1], 1) is None
    finally:
        WG.MAX_NODES, WG.HOSTILE_CAP = old
        WG.hpaOff = None
        _teardown(lua, ns, saved, now)


def test_enemy_areas_near_the_route_stay_up_while_it_is_worked_out(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    st = ns.settings.gps
    saved = (st.avoidElites, st.eliteOffset)
    st.avoidElites, st.eliteOffset = True, -10
    lua.execute("AGPS_139b = { UnitFactionGroup }; AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Alliance' end")
    ns.CharDB().faction = "Alliance"
    old = (N.dest, N.route, N.zoneHold)
    box = (STOP[0] - 600, STOP[1] - 600, STOP[0] + 600, STOP[1] + 600)

    def line(pts, pending):
        flat = ", ".join(str(v) for v in pts)
        return lua.eval(f"{{ pending = {'true' if pending else 'nil'}, parts = {{ {{ cont = 1, pts = {{ {flat} }} }} }} }}")

    def shown():
        z = N.EnemyZonesShown(1, *box, START[0], START[1], N.route)
        return {(int(z[i][4]), bool(z[i][5])) for i in range(1, len(z) + 1)}

    lua.execute("AGPS_139c = AGPS_NS.Nav.Checking")
    try:
        N.dest = lua.eval(f"{{ x = {STOP[0]}, y = {STOP[1]}, cont = 1 }}")
        N.zoneHold = None
        # (the provisional way up Felwood's road past the stop: by the elite area north of it)
        north = line([5100, -700, 5322, -655, 5640, -715], True)
        N.route = north
        first = shown()
        elite = {z for z in first if z[1]}  # (Felwood's elite circles, Data/Elites.lua's)
        assert elite, sorted(first)
        # (then none for a moment, then the straight line: the elite area stays up)
        N.route = None
        assert shown() >= first
        N.route = line([START[0], START[1], STOP[0], STOP[1]], True)
        assert shown() >= first
        # (settled on a way that doesn't pass it: its own areas from then on)
        lua.execute("AGPS_NS.Nav.Checking = function() return false end")
        settled = line([START[0], START[1], 3000, 0, 3000, -600, STOP[0], STOP[1]], False)
        N.route = settled
        assert not (shown() & elite)
    finally:
        lua.execute("AGPS_NS.Nav.Checking = AGPS_139c")
        N.dest, N.route, N.zoneHold = old
        st.avoidElites, st.eliteOffset = saved
        lua.execute("UnitFactionGroup = AGPS_139b[1]; AGPS_LEVEL = nil")
