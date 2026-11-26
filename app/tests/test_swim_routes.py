"""Swims on a route (asked for 1.3.10), with the whole addon (gameharness).

After #687 closed the deep sea far from shore, shorter swims stayed, and the trip's time counted them at walking
speed. Now: a swim is timed at the game's swim speed (GetUnitSpeed's fourth value, 4.7 yd/s to a run's 7), unless
water is as fast as land for the character (Water Walking, Levitate, Aquatic Form on or known, an Elixir of Water
Walking in the bags: Nav.WaterFast); it's drawn as a wavy line on the GPS map, in the world map and on the minimap;
right-clicking it goes round by land for that trip (Nav.SkipSwim); and Options > Routing's "Allow swimming", off,
keeps routes on land wherever there's a way.
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP as WM_SETUP

ISLE = (950.0, 216.7)  # (the Dawning Isles in Lordamere Lake)
SHORE = (1100.0, 500.0)  # (the lake's north-east shore, across the water from the isle: or round by its north end)


@pytest.fixture
def trip(game):  # noqa: F811
    """trip(start, stop, allow=True): the route the addon settles on, the player at `start` on the Eastern Kingdoms."""
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, st.allowSwim, st.zoom, st.fastestOrder)
    lua.execute("AGPS_LEVEL = 60")

    def settle():
        for _ in range(6):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()

    def run(start, stop, allow=True):
        st.allowSwim, st.zoom, st.fastestOrder = allow, 600, False
        cdb.faction = "Alliance"
        N.Clear()
        ns.Router.Reset()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {start[0]}, {start[1]}, 0")
        N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        settle()
        return N.route

    run.settle = settle
    try:
        yield run
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, st.allowSwim, st.zoom, st.fastestOrder = saved
        N.Clear()
        N.SyncSwim()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()
        ns.GPS.UpdateMinimapRoute(True)


@pytest.fixture
def water(game):  # noqa: F811
    """water(spell=None, aura=None, item=None): the character knows `spell`, has `aura` on, `item` in the bags."""
    lua, ns = game
    lua.execute("""
      AGPS_SW = { IsPlayerSpell, IsSpellKnown, GetItemCount, C_UnitAuras }
    """)

    def set_(spell=None, aura=None, item=None):
        lua.execute(f"""
          IsPlayerSpell = function(id) return id == {spell or -1} end
          IsSpellKnown = IsPlayerSpell
          GetItemCount = function(id) return id == {item or -1} and 1 or 0 end
          C_UnitAuras = {{ GetPlayerAuraBySpellID = function(id) if id == {aura or -1} then return {{ spellId = id }} end end }}
        """)
        ns.Nav.ForgetWaterFast()
        return ns.Nav.WaterFast()

    try:
        yield set_
    finally:
        lua.execute("IsPlayerSpell, IsSpellKnown, GetItemCount, C_UnitAuras = AGPS_SW[1], AGPS_SW[2], AGPS_SW[3], AGPS_SW[4]")
        ns.Nav.ForgetWaterFast()


def _segs(ns):
    G = ns.GPS
    pool, n = G.DrawnSegs()
    return [tuple(pool[i][k] for k in range(1, 5)) for i in range(1, n + 1)]


def _wave_lines(ns):
    """The route's lines drawn short and at an angle to their swim: a wave's (G.WaveLines)."""
    return [s for s in _segs(ns) if 0 < math.dist(s[:2], s[2:]) <= ns.GPS.SWIM_WAVE_PX]


def test_a_swim_is_timed_slower_than_running(game, trip):
    lua, ns = game
    N = ns.Nav
    r = trip(ISLE, SHORE)
    assert r and r.swimYards > 200 and r.swimYards <= r.walkYards, (r.swimYards, r.walkYards)
    swim = N.SwimSpeed()
    assert swim == pytest.approx(4.7)  # (GetUnitSpeed's fourth value)
    secs = N.TripSecs(r.walkYards, r.swimYards, r.rideSeconds, 7)
    assert secs == pytest.approx((r.walkYards - r.swimYards) / 7 + r.swimYards / swim + r.rideSeconds)
    assert secs > r.walkYards / 7 + r.rideSeconds + 15  # (1.4.1, one-way ground: 261 yd swum, 82 walked)
    # (on a mount too: left at the water's edge)
    assert N.TripSecs(r.walkYards, r.swimYards, 0, 14) == pytest.approx(
        (r.walkYards - r.swimYards) / 14 + r.swimYards / swim)
    # the panel's times say so
    assert N.FormatTime(secs) in str(N.TimesLine(r.walkYards, r.rideSeconds, 7, None, False, None, r.swimYards))
    # (followed: the swim behind the player isn't counted again)
    full = r.fullFirst
    behind = N.SwimYards(full, len(full.pts) // 2 - 1, 1)
    assert behind == pytest.approx(N.SwimYards(full)) and behind > 200


@pytest.mark.parametrize("how", ["aura", "spell", "item"])
def test_water_walking_or_aquatic_form_makes_water_as_fast_as_land(game, trip, water, how):
    lua, ns = game
    N = ns.Nav
    r = trip(ISLE, SHORE)
    slow = N.TripSecs(r.walkYards, r.swimYards, r.rideSeconds, 7)
    fast = {"aura": lambda: water(aura=546),  # (Water Walking on)
            "spell": lambda: water(spell=1066),  # (Aquatic Form known)
            "item": lambda: water(item=8827)}[how]()  # (an Elixir of Water Walking in the bags)
    assert fast and fast.spell in (546, 1066, 11319)
    assert (fast.active is True) == (how == "aura")
    assert N.TripSecs(r.walkYards, r.swimYards, r.rideSeconds, 7) == pytest.approx(r.walkYards / 7 + r.rideSeconds)
    assert N.TripSecs(r.walkYards, r.swimYards, r.rideSeconds, 7) < slow - 15
    assert "as fast as on land" in "\n".join(str(v) for v in ns.GPS.SwimTip().lines.values())
    assert water() is None  # (none: slow again)
    assert N.TripSecs(r.walkYards, r.swimYards, r.rideSeconds, 7) == pytest.approx(slow)


def test_with_swimming_off_routes_go_round_by_land(game, trip):
    lua, ns = game
    P = ns.Passability
    on = trip(ISLE, SHORE)
    swum, walked = on.swimYards, on.walkYards
    assert not P.avoidSwim
    off = trip(ISLE, SHORE, allow=False)
    assert P.avoidSwim and P.SwimCost() > P.SWIM_COST
    # (from the isle some water is swum still, the shortest way off it; then round the lake by land)
    assert off.swimYards < swum / 3 and off.walkYards > walked * 2, (off.swimYards, swum, off.walkYards, walked)
    # back on: the swim again
    again = trip(ISLE, SHORE)
    assert not P.avoidSwim and again.swimYards == pytest.approx(swum, rel=0.05)


def test_right_clicking_a_swim_goes_round_by_land_for_that_trip(game, trip):
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Passability
    r = trip(ISLE, SHORE)
    swum = r.swimYards
    assert G.swimSegN > 0
    sg = G.swimSegs[1]
    cx, cy = lua.eval("function(f) return f:GetCenter() end")(G.markLayer)
    mx, my = cx + (sg[1] + sg[3]) / 2, cy + (sg[2] + sg[4]) / 2
    lua.execute(f"AGPS_CUR = GetCursorPosition GetCursorPosition = function() return {mx}, {my} end")
    try:
        tip = G.SwimTip()
        assert str(tip.title) == "Swim" and "Right-click" in str(tip.lines[len(tip.lines)])
        assert G.SwimClick() is True  # (the map's right-click over it: "Remove?" there)
    finally:
        lua.execute("GetCursorPosition = AGPS_CUR")
    ask = G.removeAsk
    assert ask._shown and ask.swim
    ask.GetScript(ask, "OnClick")(ask)
    trip.settle()
    assert N.noSwim and P.avoidSwim and ns.CharDB().noSwim
    r2 = N.route
    assert r2.swimYards < swum / 3 and r2.walkYards > r.walkYards * 2, (r2.swimYards, swum)
    # (the same stops set again: the same trip, still by land)
    N.SetStops(lua.eval(f"{{ {{ x = {SHORE[0]}, y = {SHORE[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
    assert N.noSwim
    # a new trip swims again
    r3 = trip(ISLE, SHORE)
    assert not N.noSwim and not P.avoidSwim and r3.swimYards == pytest.approx(swum, rel=0.05)


def test_a_swim_is_drawn_wavy_on_the_map_the_world_map_and_the_minimap(game, trip):
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    st = ns.settings.gps
    trip(ISLE, SHORE)
    G.Update()
    assert G.swimSegN > 0 and len(_wave_lines(ns)) > 20
    # (on the minimap: more lines than the same route drawn straight)
    wavy = G.UpdateMinimapRoute(True)
    lua.execute("AGPS_SS = AGPS_NS.Nav.SwimSpans AGPS_NS.Nav.SwimSpans = function() return false end")
    try:
        flat = G.UpdateMinimapRoute(True)
        G.Update()
        assert G.swimSegN == 0 and len(_wave_lines(ns)) < 5
    finally:
        lua.execute("AGPS_NS.Nav.SwimSpans = AGPS_SS")
    assert wavy > flat + 10, (wavy, flat)
    # in the game's world map (the option `useWorldMap`): the same
    lua.execute(WM_SETUP)
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
        assert G.swimSegN > 0 and len(_wave_lines(ns)) > 20
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
    # with swimming off, no swim to draw: the route goes round by land
    trip(ISLE, SHORE, allow=False)
    G.Update()
    assert N.route.swimYards < 100


def test_the_swims_split_a_piece_in_order_with_the_guards_reach(game):
    lua, ns = game
    N = ns.Nav
    # (straight from the isle north-east over the lake to its shore)
    part = lua.eval(f"{{ cont = 0, pts = {{ {ISLE[0]}, {ISLE[1]}, {SHORE[0]}, {SHORE[1]} }}, kinds = {{ 1 }} }}")
    spans = N.SwimSpans(part, 1)
    ts = [spans[i] for i in range(1, len(spans) + 1)]
    assert ts and ts == sorted(ts) and all(0 <= t <= 1 for t in ts)
    pc = lua.eval("{}")
    N.EachRoutePiece(part, 1, lua.eval("function(t) return function(a, b, h, s) t[#t + 1] = { a, b, h, s } end end")(pc))
    pieces = [(pc[i][1], pc[i][2], pc[i][3], pc[i][4]) for i in range(1, len(pc) + 1)]
    assert pieces[0][0] == 0 and pieces[-1][1] == 1
    assert all(math.isclose(pieces[k][1], pieces[k + 1][0]) for k in range(len(pieces) - 1))
    assert any(p[3] for p in pieces)
    # a road or a ride over water isn't a swim
    for k in (0, 2):
        assert N.SwimSpans(lua.eval(f"{{ cont = 0, pts = {{ {ISLE[0]}, {ISLE[1]}, {SHORE[0]}, {SHORE[1]} }}, kinds = {{ {k} }} }}"), 1) is False


WETLANDS = (-2860.0, -1400.0)  # (the Wetlands' north coast, west of the strait to Arathi and Hillsbrad)
NEAR = (-2875.0, -1395.0)  # (a stop just along the coast from there)
OFF = (-2740.0, -1200.0)  # (up the coast toward the strait: off the way to Thandol Span)
MALEB = (-861.0, -473.7)  # (Magistrate Henry Maleb, Southshore)


def _strait_swim(ns, r):
    """Yards of the route's swims out in the strait north of Thandol Span (Nav.SwimSpans past x -2600)."""
    yd = 0.0
    for p in r.parts.values():
        for i in range(1, len(p.pts) // 2):
            sp = ns.Nav.SwimSpans(p, i)
            if sp:
                x1, y1, x2, y2 = p.pts[2 * i - 1], p.pts[2 * i], p.pts[2 * i + 1], p.pts[2 * i + 2]
                for j in range(1, len(sp), 2):
                    a, b = sp[j], sp[j + 1]
                    if max(x1 + (x2 - x1) * a, x1 + (x2 - x1) * b) > -2600:
                        yd += (b - a) * math.dist((x1, y1), (x2, y2))
    return yd


def _over_thandol(r):
    return any(-2500 < p.pts[i] < -2250 and -2550 < p.pts[i + 1] < -2350
               for p in r.parts.values() for i in range(1, len(p.pts), 2))


@pytest.mark.parametrize("how", ["removed", "option off"])
def test_a_swim_left_out_stays_out_on_every_reroute_the_stops_reached_and_a_reload(game, trip, how):
    # (reported 2026-11-19 with a video: from the Wetlands' coast toward Southshore the route swam the strait; the swim
    # removed, the route came back hugging the coast in the same water, "No way round by land", though Thandol Span
    # is. A walk searched over the water lost to the roads, but rerouting from beside where it was searched took it up
    # again priced by its yards alone (Router's Reuse), the water at running cost)
    lua, ns = game
    N, P = ns.Nav, ns.Passability
    trip(WETLANDS, MALEB, allow=(how != "option off"))
    N.SetStops(lua.eval(f"{{ {{ x = {NEAR[0]}, y = {NEAR[1]}, cont = 0, name = 'near' }},"
                        f" {{ x = {MALEB[0]}, y = {MALEB[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
    trip.settle()
    if how == "removed":
        N.SkipSwim()
        trip.settle()
        assert N.noSwim and ns.CharDB().noSwim
    assert P.avoidSwim

    def check(where):
        r = N.route
        assert r is not None, where
        assert _strait_swim(ns, r) == 0 and _over_thandol(r), (where, round(r.swimYards), round(_strait_swim(ns, r)))

    check("left out")
    # off course, up the coast toward the strait: worked out again from there, still by land
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {OFF[0]}, {OFF[1]}")
    trip.settle()
    check("off course")
    # the first stop reached: on to the next, still by land
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {NEAR[0]}, {NEAR[1]}")
    trip.settle()
    assert len(N.stops) == 1
    check("a stop reached")
    # (a /reload: the stops and the trip's swim left out brought back)
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {WETLANDS[0]}, {WETLANDS[1]}")
    N.noSwim = None
    N.Restore()
    N.Invalidate(True, True)
    trip.settle()
    assert (N.noSwim is not None) == (how == "removed")
    check("after a reload")


# (the live report, 2026-11-19, the swim removed and a /reload: from the Wetlands' north shore by Dun Modr the route
# swam north up the bay along Arathi's west coast to Hillsbrad, weighed 10 times a yard and still taken. The client it
# was seen in ran a Router without #699's fix; either way a removed swim's water is now banned for the trip)
DUN_MODR = (-2796.7, -1425.7)


def _water_points(ns, r):
    """Points every few yards along the route's swims: (cont, x, y)."""
    out = []
    for p in r.parts.values():
        for i in range(1, len(p.pts) // 2):
            sp = ns.Nav.SwimSpans(p, i)
            if sp:
                x1, y1, x2, y2 = p.pts[2 * i - 1], p.pts[2 * i], p.pts[2 * i + 1], p.pts[2 * i + 2]
                for j in range(1, len(sp), 2):
                    a, b = sp[j], sp[j + 1]
                    n = max(1, int((b - a) * math.dist((x1, y1), (x2, y2)) / 4))
                    for k in range(n + 1):
                        t = a + (b - a) * k / n
                        out.append((p.cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    return out


# (in the bay north of the Wetlands up Arathi's west coast to Hillsbrad's shore: the live report's route swam there)
BAY = [(-2237.0, -1704.0), (-1862.0, -1404.0), (-1621.0, -1096.0)]


def _banned_yards(ns, r, ends):
    """Yards of the route's pieces off the roads over banned water (swum, or straight over it: a hop), but within
    STOP_SLACK of `ends` (a stop in the marsh's water: its last yards are)."""
    N, P, R = ns.Nav, ns.Passability, ns.Router
    yd = 0.0
    for p in r.parts.values():
        pts = p.pts
        for i in range(1, len(p.pts) // 2):
            if p.kinds[i] != R.KIND_OFFROAD:
                continue
            x1, y1, x2, y2 = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
            n = max(1, math.ceil(math.dist((x1, y1), (x2, y2)) / 4))
            for j in range(n):
                x, y = x1 + (x2 - x1) * (j + 0.5) / n, y1 + (y2 - y1) * (j + 0.5) / n
                if (N.InSwimBan(p.cont, x, y) and not N.SwimStays(p.cont, x, y)
                        and min(math.dist((x, y), e) for e in ends) > P.STOP_SLACK):
                    yd += math.dist((x1, y1), (x2, y2)) / n
    return yd


@pytest.mark.parametrize("start", [DUN_MODR, WETLANDS])
def test_a_removed_swims_water_is_banned_for_the_trip(game, trip, start):
    lua, ns = game
    N, P = ns.Nav, ns.Passability
    trip(start, MALEB)
    N.SetStops(lua.eval(f"{{ {{ x = {NEAR[0]}, y = {NEAR[1]}, cont = 0, name = 'near' }},"
                        f" {{ x = {MALEB[0]}, y = {MALEB[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
    trip.settle()
    assert _water_points(ns, N.route)  # (it swims along the coast)
    N.SkipSwim()
    trip.settle()
    bans = list(N.swimBans.values())
    assert bans and not any(b.lifted for b in bans) and ns.CharDB().swimBans
    # (the bay whole, up Arathi's west coast to Hillsbrad's shore; closed, as a wall is)
    for x, y in BAY:
        assert any(P.InSwimSection(b, 0, x, y) for b in bans) and P.At(0, x, y) == 2, (x, y)

    def check(where):
        r = N.route
        assert r is not None, where
        banned = _banned_yards(ns, r, (start, NEAR, MALEB, OFF))
        assert banned == 0 and _strait_swim(ns, r) == 0 and _over_thandol(r), (where, banned)
        assert not any(b.lifted for b in N.swimBans.values()), where

    check("removed")
    # off course, up the coast toward the strait: worked out again from there, still by land
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {OFF[0]}, {OFF[1]}")
    trip.settle()
    check("off course")
    # the first stop reached: on to the next, still by land
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {NEAR[0]}, {NEAR[1]}")
    trip.settle()
    assert len(N.stops) == 1
    check("a stop reached")
    # a /reload: the stops and the banned water brought back
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {start[0]}, {start[1]}")
    N.noSwim, N.swimBans = None, lua.table()
    P.SetSwimBans(lua.table())
    N.Restore()
    assert len(N.swimBans) == len(bans)
    N.Invalidate(True, True)
    trip.settle()
    assert P.At(0, *BAY[1]) == 2
    check("after a reload")
    # a new trip swims again: nothing banned
    trip(start, MALEB)
    assert not N.noSwim and len(N.swimBans) == 0 and P.At(0, *BAY[1]) == 1


@pytest.mark.timing
def test_the_bay_is_banned_whole_but_not_the_sea(game):
    lua, ns = game
    P = ns.Passability
    import time
    # (a short swim along the Wetlands' coast: the bay up to Hillsbrad's shore, a few milliseconds)
    a = time.perf_counter()
    bay = P.SwimSection(0, lua.table(-2866.0, -1406.0, -2949.0, -1493.0))
    assert (time.perf_counter() - a) * 1000 < 20
    assert all(P.InSwimSection(bay, 0, x, y) for x, y in BAY) and bay.n <= P.SWIM_BAN_MAX_CELLS
    # (a short swim out at sea, off Westfall: a patch round it, never the sea)
    sea = P.SwimSection(0, lua.table(-10600.0, 2200.0, -10650.0, 2220.0))
    if sea:
        x0, x1, y0, y1 = P.SwimSectionBox(sea)
        assert x1 - x0 <= 2 * P.SWIM_BAN_REACH_YD + 200 and y1 - y0 <= 2 * P.SWIM_BAN_REACH_YD + 200
        assert sea.n <= P.SWIM_BAN_MAX_CELLS


def test_an_isle_is_still_swum_to_and_says_why(game, trip):
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    r = trip(SHORE, ISLE)
    swum = r.swimYards
    assert swum > 200
    N.SkipSwim()
    trip.settle()
    # (the lake banned, the isle cut off: the water swum after all, the plan worked out again; never "No way")
    r2 = N.route
    assert r2 is not None and r2.swimYards > 50
    assert any(b.lifted for b in N.swimBans.values())
    assert any(N.SwimStays(*q) for q in _water_points(ns, r2))
    # the swim's tooltip says so, and right-clicking it does nothing more
    G.Update()
    assert G.swimSegN > 0
    sg = None
    for i in range(1, G.swimSegN + 1):
        if G.SwimSegStays(G.swimSegs[i]):
            sg = G.swimSegs[i]
            break
    assert sg is not None
    cx, cy = lua.eval("function(f) return f:GetCenter() end")(G.markLayer)
    mx, my = cx + (sg[1] + sg[3]) / 2, cy + (sg[2] + sg[4]) / 2
    lua.execute(f"AGPS_CUR = GetCursorPosition GetCursorPosition = function() return {mx}, {my} end")
    try:
        lines = "\n".join(str(v) for v in G.SwimTip().lines.values())
        assert "No way round by land" in lines and "Right-click" not in lines
        assert G.SwimClick() is False
    finally:
        lua.execute("GetCursorPosition = AGPS_CUR")


def test_the_no_way_line_only_when_there_is_none(game, trip):
    lua, ns = game
    G = ns.GPS
    # (swimming off, a swim still on the route: removable, never "No way round by land")
    trip(ISLE, SHORE, allow=False)
    G.Update()
    assert G.swimSegN > 0
    sg = G.swimSegs[1]
    assert not G.SwimSegStays(sg)
    cx, cy = lua.eval("function(f) return f:GetCenter() end")(G.markLayer)
    mx, my = cx + (sg[1] + sg[3]) / 2, cy + (sg[2] + sg[4]) / 2
    lua.execute(f"AGPS_CUR = GetCursorPosition GetCursorPosition = function() return {mx}, {my} end")
    try:
        lines = "\n".join(str(v) for v in G.SwimTip().lines.values())
        assert "No way round by land" not in lines and "Right-click" in lines
        assert G.SwimClick() is True
    finally:
        lua.execute("GetCursorPosition = AGPS_CUR")
    G.removeAsk.Hide(G.removeAsk)


@pytest.mark.timing
def test_banning_a_bay_stays_within_the_frame_budget(game, trip):
    # (the flood at the click is a few milliseconds; the blocks the ban changes are worked out in the background
    # searches, a slice at a time)
    from test_frame_budget import FRAME_MS  # noqa: F401  (the background searches' slices)
    CLICK_MS = 150
    lua, ns = game
    N, P = ns.Nav, ns.Passability
    trip(DUN_MODR, MALEB)
    clock = lua.eval("os.clock")
    a = clock()
    N.SkipSwim()
    # (a one-off click, not a background slice: CLICK_MS. On CI's slower runners the bay's flood took 55-138 ms against
    # FRAME_MS, 5-6 ms here; slicing the flood is #739's.)
    assert (clock() - a) * 1000 < CLICK_MS
    assert len(N.swimBans) > 0
    worst = lua.eval("""function(P)
      local co = coroutine.create(function() return P.FindPath(0, -2796.7, -1425.7, -1600.0, -2100.0) end)
      local worst, n = 0, 0
      while coroutine.status(co) ~= "dead" do
        local a = os.clock()
        assert(coroutine.resume(co))
        worst, n = math.max(worst, os.clock() - a), n + 1
      end
      return worst * 1000, n
    end""")(P)
    assert worst[0] < FRAME_MS, worst


# (reported 2026-11-19 with a screenshot: in Hillsbrad at 62.0, 33.3, on the east shore of the pond south of Tarren
# Mill, the route swam straight across it, then a line off the roads to the road toward Southshore, not round its south
# shore on land. Water was priced at the swim cost everywhere, but a straight line over open ground was never walked
# round, and water is open: the start's leg, the walk straight there, the walk's own straightening (Passability.
# FindPath) and Router.Smooth's corners each crossed it at running cost)
POND_SHORE = (0.620, 0.333)  # (Hillsbrad's map, uiMap 1424)


@pytest.mark.parametrize("stop", [(0.58, 0.38), (0.55, 0.40), "maleb"])
def test_a_pond_is_walked_round_when_that_is_cheaper_than_swimming_it(game, trip, stop):
    lua, ns = game
    P = ns.Passability
    sx, sy, _ = ns.Layers.MapToWorld(1424, *POND_SHORE)
    if stop == "maleb":
        tx, ty = MALEB
    else:
        tx, ty, _ = ns.Layers.MapToWorld(1424, *stop)
    r = trip((sx, sy), (tx, ty))
    assert r is not None and not P.avoidSwim and P.SwimCost() == P.SWIM_COST
    assert r.swimYards < 5, (round(r.swimYards), round(r.walkYards))
    # (round its south shore: a few yards more than straight across, far less than the swim's extra cost)
    first = r.parts[1].pts
    assert len(first) > 4 and first[3] > -330, [round(v) for v in list(first.values())[:8]]
    # the walk itself, searched from the shore: round the pond, not straightened back across it
    cost, path = P.FindPath(0, sx, sy, -378.1, -774.0)
    straight = P.SegmentCost(0, sx, sy, -378.1, -774.0)
    assert cost < straight and len(path) > 4, (cost, straight)


def _bags(lua, ns, spells=(), items=None):
    """The character knows `spells` and has `items` ({ id: count }) in the bags; then the bags changed (BAG_UPDATE)."""
    known = " or ".join(f"id == {s}" for s in spells) or "false"
    counts = ", ".join(f"[{k}] = {v}" for k, v in (items or {}).items())
    lua.execute(f"""
      IsPlayerSpell = function(id) return {known} end
      IsSpellKnown = IsPlayerSpell
      AGPS_BAGS = {{ {counts} }}
      GetItemCount = function(id) return AGPS_BAGS[id] or 0 end
      C_UnitAuras = {{ GetPlayerAuraBySpellID = function() end }}
      AGPS_T = AGPS_T + 5
    """)
    lua.eval("AGPS_FIRE")("BAG_UPDATE", 0)


# (asked 2026-11-19: a character who crosses water at land speed is routed so: water priced as land, not only timed so.
# A spell counts only castable now, its reagent in the bags: Water Walking a Fish Oil (17058), Levitate a Light Feather
# (17056), the client's SpellReagents; Aquatic Form none; the Elixir of Water Walking (8827) in the bags)
@pytest.mark.parametrize("how", ["water walking", "elixir", "aquatic form"])
def test_water_as_fast_as_land_is_priced_as_land_and_crosses_the_pond(game, trip, water, how):
    lua, ns = game
    N, P = ns.Nav, ns.Passability
    sx, sy, _ = ns.Layers.MapToWorld(1424, *POND_SHORE)
    tx, ty, _ = ns.Layers.MapToWorld(1424, 0.58, 0.38)

    def route():
        trip.settle()
        return N.route

    trip((sx, sy), (tx, ty))
    if how == "water walking":
        # a shaman with Water Walking but no Fish Oil: water's a swim, round the pond
        _bags(lua, ns, spells=(546,))
        r = route()
        assert N.WaterFast() is None and not P.waterFast and P.SwimCost() == P.SWIM_COST
        assert r.swimYards < 5, round(r.swimYards)
        _bags(lua, ns, spells=(546,), items={17058: 5})
    elif how == "elixir":
        _bags(lua, ns, items={8827: 1})
    else:
        _bags(lua, ns, spells=(1066,))
    fast = N.WaterFast()
    assert fast and P.waterFast and P.SwimCost() == pytest.approx(P.WATER_FAST_COST)
    r = route()
    assert r.swimYards > 40, round(r.swimYards)  # (straight across the pond)
    if how == "water walking":
        assert fast.spell == 546 and fast.name.endswith("(Fish Oil: 5)"), fast.name
        assert f"{fast.name}: as fast as on land." in "\n".join(str(v) for v in ns.GPS.SwimTip().lines.values())
        # the last Fish Oil used: worked out again, round the pond
        _bags(lua, ns, spells=(546,), items={17058: 0})
        r = route()
        assert N.WaterFast() is None and not P.waterFast
        assert r.swimYards < 5, round(r.swimYards)
    # swimming left out (the option off) still goes round, however fast the water
    if how == "elixir":
        r = trip((sx, sy), (tx, ty), allow=False)
        assert P.avoidSwim and P.SwimCost() == P.AVOID_SWIM_COST and r.swimYards < 5
    water()  # (put back)
    N.SyncSwim()
    assert not P.waterFast


def test_levitate_needs_its_light_feather(game, water):
    lua, ns = game
    N = ns.Nav
    _bags(lua, ns, spells=(1706,))
    assert N.WaterFast() is None
    _bags(lua, ns, spells=(1706,), items={17056: 2})
    fast = N.WaterFast()
    assert fast and fast.spell == 1706 and fast.count == 2
    water()


# (reported 2026-11-19: in the Wetlands' marsh by Saltspray Glen, about 29.6, 19.9, a stop ~170 yd north-west was one
# straight line swimming along two channels; on land north-west, across a channel where it's narrow, then along the
# bank swims far less for a few yards more)
MARSH, MARSH_STOP = (-2776.4, -1613.7), (-2654.1, -1491.3)


def test_a_short_trip_through_a_marsh_crosses_its_channels_where_they_are_narrow(game, trip):
    lua, ns = game
    N, P = ns.Nav, ns.Passability
    straight = sum((b - a) for a, b in zip(*[iter(list(P.WaterSpans(0, *MARSH, *MARSH_STOP).values()))] * 2)) \
        * math.dist(MARSH, MARSH_STOP)
    assert straight > 100, straight
    r = trip(MARSH, MARSH_STOP)
    assert len(r.parts[1].pts) > 4  # (not the straight line)
    assert r.swimYards < straight - 50 and r.walkYards < math.dist(MARSH, MARSH_STOP) * 1.15, (
        round(r.swimYards), round(straight), round(r.walkYards))
    # timed with its swim at the swim speed, the rest at running speed
    assert N.TripSecs(r.walkYards, r.swimYards, 0, 7) == pytest.approx(
        (r.walkYards - r.swimYards) / 7 + r.swimYards / N.SwimSpeed())


# (reported 2026-11-19: from the Wetlands' western marsh to a stop in the water of the bay below Stromgarde, by
# Arathi's shore, the route went round by Thandol Span and back down Arathi's coast, 4.9k yd; the swim there is 2.1k.
# Road mode's preference for the roads, ROAD_DIRECT_PENALTY, multiplied the swim's own price too: a yard swum weighed
# three on the roads)
WEST_MARSH = (-3030.0, -1299.0)  # (the Wetlands 22, 32)
BAY_STOP = (-1349.3, -914.1)  # (Hillsbrad 61.9, 82.0: the bay's north-east side, west of Faldir's Cove)


def test_a_stop_in_the_bay_is_swum_to_straight_from_the_marsh(game, trip):
    lua, ns = game
    N = ns.Nav
    r = trip(WEST_MARSH, BAY_STOP)
    assert r.walkYards < 2600 and r.swimYards > 1500, (r.walkYards, r.swimYards)
    # swimming off: round by land
    off = trip(WEST_MARSH, BAY_STOP, allow=False)
    assert off.walkYards > 4000 and off.swimYards < r.swimYards / 3, (off.walkYards, off.swimYards)
    # the swim removed: round by land for that trip
    trip(WEST_MARSH, BAY_STOP)
    N.SkipSwim()
    trip.settle()
    gone = N.route
    assert N.noSwim and gone.walkYards > 4000 and gone.swimYards < r.swimYards / 3, (gone.walkYards, gone.swimYards)


def _queued(lua):
    """How many jobs the Router's background queue holds (its `walkJobs`)."""
    return int(lua.eval("""(function()
      local i = 1
      while true do
        local n, v = debug.getupvalue(AGPS_NS.Router.Pump, i)
        if not n then return -1 end
        if n == "walkJobs" then return #v end
        i = i + 1
      end
    end)()"""))


def test_in_game_the_swim_lands_once_its_walk_is_in_not_after_the_ride_checks_walks(game):
    # (#742: QA saw #719's trip still 5.4k yd round by Thandol Span in game. The route there is worked out in the
    # background: provisional by the roads while the walk straight there is searched; once that walk was in, the
    # route's recalculation was queued behind the ride check's 80 walk searches, and landed half a minute later)
    lua, ns = game
    N, st, R, G = ns.Nav, ns.settings.gps, ns.Router, ns.GPS
    cdb = ns.CharDB()
    saved = (cdb.faction, st.allowSwim, st.zoom, st.fastestOrder)
    lua.execute("AGPS_LEVEL = 60")
    st.allowSwim, st.zoom, st.fastestOrder = True, 600, False
    cdb.faction = "Horde"
    try:
        N.Clear()
        R.Reset()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {WEST_MARSH[0]}, {WEST_MARSH[1]}, 0")
        R.WARM, R.SYNC_WALKS = True, False
        N.SetStops(lua.eval(f"{{ {{ x = {BAY_STOP[0]}, y = {BAY_STOP[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        t = float(lua.eval("AGPS_T")) + 10
        provisional, landed = None, None
        for _ in range(6000):
            t += 0.05
            lua.execute(f"AGPS_T = {t}")
            G.Update()
            G.PumpSearches()  # (as the map's OnUpdate does: N.SearchDone when a search is in)
            r = N.route
            if r and r.pending and provisional is None:
                provisional = r.walkYards
            if r and not r.pending and r.swimYards > 1500:
                landed = (r.walkYards, r.swimYards, _queued(lua), N.RideChecking())
                break
            if not R.HasWork() and r and not r.pending:
                break
        assert provisional and provisional > 4000, provisional  # (by the roads while the walk is searched)
        assert landed and landed[0] < 2600, (N.route.walkYards, N.route.swimYards)
        # (the ride check still to finish: not waited for. Its walks were queued ahead, 20 and more of them left when the
        # swim landed; `low` since 2026-11-23, after the route's own searches, the check may not have queued them yet)
        assert landed[3], landed  # (N.RideChecking: the check still running when the swim landed)
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        R.Reset()
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, st.allowSwim, st.zoom, st.fastestOrder = saved
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def _leg_yards(r):
    out = {}
    for p in range(1, len(r.parts) + 1):
        part = r.parts[p]
        n = len(part.pts) // 2
        yd = sum(math.dist((part.pts[2 * i - 1], part.pts[2 * i]), (part.pts[2 * i + 1], part.pts[2 * i + 2]))
                 for i in range(1, n))
        out[part.stop or 1] = out.get(part.stop or 1, 0) + yd
    return out


def test_avoiding_a_swim_is_for_its_stop_only(game):  # noqa: F811
    # (item 42c, Kooki3z 2026-11-24: right-clicking a swim avoided swimming for every stop of the route; with world
    # routing on it's for that stop only, saved with it, the next stop's swim kept)
    lua, ns = game
    N, st, WG = ns.Nav, ns.settings.gps, ns.WorldGrid
    cdb = ns.CharDB()
    saved = (cdb.faction, st.allowSwim, st.fastestOrder, st.worldGrid)
    lua.execute("AGPS_LEVEL = 60")
    try:
        st.allowSwim, st.fastestOrder, st.worldGrid = True, False, True
        WG.Set(True)
        cdb.faction = "Alliance"
        N.Clear()
        ns.Router.Reset()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {ISLE[0]}, {ISLE[1]}, 0")
        N.SetStops(lua.eval(f"{{ {{ x = {SHORE[0]}, y = {SHORE[1]}, cont = 0, name = 'a' }},"
                            f" {{ x = {ISLE[0] + 10}, y = {ISLE[1] - 10}, cont = 0, name = 'b' }} }}"), False, "red")
        N.Invalidate(True, True)
        for _ in range(12):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
        before = _leg_yards(N.route)
        assert N.AvoidLegSwim(1) is True and N.AvoidLegSwim(1) is False
        assert N.stops[1].avoidSwim and not N.stops[2].avoidSwim and ns.CharDB().stops[1].avoidSwim
        for _ in range(12):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
        after = _leg_yards(N.route)
        # (the first stop: less water, a longer way; from the isle some swim stays, it's an island)
        assert after[1] > before[1] + 20, (before, after)
        assert after[2] == pytest.approx(before[2], rel=0.05), (before, after)  # (the second's swim kept)
        assert not N.noSwim  # (not the whole trip's)
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, st.allowSwim, st.fastestOrder, st.worldGrid = saved
        WG.Set(bool(saved[3]))
        N.Clear()
        N.SyncSwim()


def test_the_swim_weight_comes_from_one_reading_on_foot(game):  # noqa: F811
    """Item 62/63a (Kooki3z, a mage at GM speed 5, then 1 and a /reload: still 350 yd swum down the Southfury). The
    ratio is read only on foot (not mounted, no ability, no form), from one GetUnitSpeed; a mounted or boosted reading
    leaves it; `/agps debug speeds reset` starts over; never under SWIM_MIN."""
    lua, ns = game
    N, WG = ns.Nav, ns.WorldGrid
    old = lua.eval("GetUnitSpeed")
    lua.execute("AGPS_IM = IsMounted")
    try:
        lua.execute("GetUnitSpeed = function() return 0, 7, 7, 4.72 end; IsMounted = function() return false end")
        N.Speeds()
        assert abs(WG.SwimWeight() - 7 / 4.72) < 1e-6
        # (mounted: a fast swim read with the mount's run: the ratio kept)
        lua.execute("GetUnitSpeed = function() return 14, 14, 14, 30 end; IsMounted = function() return true end")
        N.Speeds()
        assert abs(WG.SwimWeight() - 7 / 4.72) < 1e-6
        # (GM speed on foot: both fast, the ratio the same)
        lua.execute("GetUnitSpeed = function() return 0, 35, 35, 23.6 end; IsMounted = function() return false end")
        N.Speeds()
        assert abs(WG.SwimWeight() - 35 / 23.6) < 1e-6
        lua.globals().SlashCmdList.AZEROTHGPS("debug speeds reset")
        assert N.SwimRatio() is not None  # (read again at once, by the command's own reading)
    finally:
        lua.globals().GetUnitSpeed = old
        lua.execute("IsMounted = AGPS_IM")
        N.ResetSpeeds()
