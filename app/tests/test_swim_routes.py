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
    assert secs > r.walkYards / 7 + r.rideSeconds + 20
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
    assert N.TripSecs(r.walkYards, r.swimYards, r.rideSeconds, 7) < slow - 20
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
