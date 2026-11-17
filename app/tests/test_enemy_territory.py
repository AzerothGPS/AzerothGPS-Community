"""The other faction's territory on a route (Data/Hostile.lua: their guards' reach), with the whole addon (gameharness).

Reported 2026-11-14 by a Horde player, with a screenshot of the Wetlands: the route ran through Dun Algaz past the
Alliance's guards. "If we have to force a player through opposing faction area we should warn them and that part of
the route should be red. If there is any other route with avoid enemy territory turned on we should use that instead
even if higher level area walks are needed to get there. Also if they have that setting turned off for avoiding it
should still show red for that area."

Dun Algaz is the only way on foot between the Wetlands and Loch Modan; the flight round it (Hammerfall to Kargath, or
farther round at a low level) is the other way, and the ride check (Nav's CompareRide) weighed only the walks' time and
the zones too high, never the guards the router keeps away from.
"""

import math

import pytest

WETLANDS = (-3900.0, -2550.0)  # (south of Thelgen Rock, the road north of Dun Algaz)
BY_DUN_ALGAZ = (-4300.0, -2500.0)  # (a little north of its guards: they show on the map and the minimap from here)
LOCH_MODAN = (-5600.0, -3300.0)
RED = "1.00,0.15,0.15"  # Nav.HOSTILE_COLOR


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    ns.settings.gps.fastestOrder = False
    return lua, ns


@pytest.fixture
def trip(game):
    """trip(start, stop, faction, level, known=None (all its flight masters), avoid=True): the route the addon settles
    on from `start` to `stop` on the Eastern Kingdoms, with the player there."""
    from azerothgps import tripsweep as ts

    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, cdb.taxiNodes, st.avoidHostile, st.zoom)
    said = lua.eval("{}")
    old_print = ns.Print
    ns.Print = lua.eval("function(t) return function(msg) t[#t + 1] = msg end end")(said)
    # (the map's popups: kept to answer, AGPS_ASKS { text, yes, no }; none answered by themselves)
    lua.execute("""
      AGPS_ASKS = {}
      AGPS_CONFIRM = AGPS_NS.GPS.Confirm
      AGPS_NS.GPS.Confirm = function(text, yes, no) AGPS_ASKS[#AGPS_ASKS + 1] = { text = text, yes = yes, no = no } return true end
      AGPS_USABLE = AGPS_NS.Nav.TransportUsable
    """)

    def settle():
        for _ in range(4):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()

    def run(start, stop, faction, level, known=None, avoid=True, rides=True, force="red"):
        lua.execute("AGPS_ASKS = {} AGPS_NS.Nav.TransportUsable = " + ("AGPS_USABLE" if rides else "function() return false end"))
        known = ts._masters(ns, 0, faction[0]) if known is None else known
        st.avoidHostile = avoid
        st.zoom = 600
        lua.execute(f"AGPS_LEVEL = {level}")
        cdb.faction = faction
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in known) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        ns.Router.Reset()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {start[0]}, {start[1]}, 0")
        N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 0, name = 'stop' }} }}"), False, force)
        N.Invalidate(True, True)
        ns.GPS.Follow()
        settle()
        return N.route, [str(said[i]) for i in range(1, len(said) + 1)]

    run.settle = settle
    run.said = lambda: [str(said[i]) for i in range(1, len(said) + 1)]

    try:
        yield run
    finally:
        ns.Print = old_print
        lua.execute("AGPS_NS.GPS.Confirm = AGPS_CONFIRM AGPS_NS.Nav.TransportUsable = AGPS_USABLE")
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes, st.avoidHostile, st.zoom = saved
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()
        ns.GPS.UpdateMinimapRoute(True)


def _asks(lua):
    a = lua.eval("AGPS_ASKS")
    return [a[i] for i in range(1, len(a) + 1)]


def _rides(r):
    return [str(r.legs[i].ride[10]) for i in range(1, len(r.legs) + 1) if r.legs[i].ride] if r.legs else []


def _guard_yards(ns, r):
    from azerothgps.routequality import guard_yards, walk_parts

    return guard_yards(ns, walk_parts(ns, r))


def _map_colors(lua):
    return {str(w._vc) if w._vc else str(w._tex).replace("color:", "") for w in lua.eval("AGPS_WIDGETS").values()
            if w._kind == "Line" and w._shown}


def _minimap_colors(ns):
    G = ns.GPS
    n = G.UpdateMinimapRoute(True)
    return {str(G.minimapRoute.lines[i]._tex).replace("color:", "")[:14] for i in range(1, n + 1)}


@pytest.mark.parametrize("level", [30, 20])
def test_a_horde_walk_through_dun_algaz_takes_the_flight_round_it(game, trip, level):
    # avoid on, the flight paths known: not the walk through Dun Algaz (4k yd, 1.1k of it past the Alliance's guards)
    # but a flight to Kargath. At level 30 from Hammerfall (the walk there through the Arathi Highlands, too high for
    # level 20 then); at level 20 the way with a ride walked through Dun Algaz to Thorium Point first, and is planned
    # again past that walk (CompareRide's `avoid`): farther round, past far fewer guards, zones too high or not. The
    # flight is more than 30% slower than the walk: the safe way meanwhile, and the player asked (the next test)
    lua, ns = game
    r, _ = trip(WETLANDS, LOCH_MODAN, "Horde", level)
    assert "Kargath, Badlands" in _rides(r), (_rides(r), str(ns.Nav.lastRideCheck))
    assert _guard_yards(ns, r) < 400, str(ns.Nav.lastRideCheck)
    if level == 30:
        assert _rides(r) == ["Kargath, Badlands"] and ns.Nav.HostileOnRoute(r) is None


@pytest.mark.parametrize("risk", [True, False])
def test_a_safe_way_30_percent_slower_asks_to_risk_it(game, trip, risk):
    # (asked 2026-11-14: "If a safe route would 30% longer or more, ask the player if they want to risk going through
    # enemy territory to save time") level 30, the flights known: the walk through Dun Algaz about 1k s, the flight
    # round it half as long again. One popup naming the place and the time saved; yes: the walk (warned, red), no: the
    # flight; not asked again for the trip
    lua, ns = game
    N = ns.Nav
    r, said = trip(WETLANDS, LOCH_MODAN, "Horde", 30)
    asks = _asks(lua)
    assert len(asks) == 1, [str(a.text) for a in asks]
    text = str(asks[0].text)
    assert "Dun Algaz" in text and "Risk enemy territory to save the time?" in text and "m " in text, text
    (asks[0].yes if risk else asks[0].no)()
    trip.settle()
    r = N.route
    if risk:
        assert not _rides(r) and _guard_yards(ns, r) > 500, str(N.lastRideCheck)
        warned = [m for m in trip.said() if "Enemy territory" in m]
        assert warned and "no way round" not in warned[-1], trip.said()
    else:
        assert _rides(r) == ["Kargath, Badlands"]
    N.Invalidate(True, True)
    trip.settle()
    assert len(_asks(lua)) == 1 and bool(_rides(N.route)) != risk  # (the answer kept for the trip)


def test_a_safe_way_less_than_30_percent_slower_is_taken_without_asking(game, trip):
    # level 40 from farther north in the Wetlands: the flight round Dun Algaz a quarter slower than the walk through it
    lua, ns = game
    r, _ = trip((-3500.0, -2400.0), LOCH_MODAN, "Horde", 40)
    assert "Kargath, Badlands" in _rides(r) and not _asks(lua), str(ns.Nav.lastRideCheck)


@pytest.mark.parametrize("risk", [False, True])
def test_the_answer_holds_while_the_ride_check_is_worked_out_again(game, trip, risk):
    # (asked 2026-11-16: "I chose No here and the route didn't change") the answer forgot the ride checks and the one
    # worked out again, planning past a long way round, took a while in the game: with nothing remembered meanwhile the
    # route was the walk past Dun Algaz. The way answered is the route at once, the check still running
    lua, ns = game
    N, R = ns.Nav, ns.Router
    trip(WETLANDS, LOCH_MODAN, "Horde", 30)
    asks = _asks(lua)
    assert len(asks) == 1 and "Dun Algaz" in str(asks[0].text)
    real = R.Background
    lua.execute("""AGPS_HELD = AGPS_NS.Router.Background
      AGPS_NS.Router.Background = function(key, fn, done)
        if string.sub(key, 1, 5) == "ride:" then return end -- (the check not done yet)
        return AGPS_HELD(key, fn, done)
      end""")
    try:
        (asks[0].yes if risk else asks[0].no)()
        trip.settle()
        assert N.RideChecking()  # (its check still to come)
        assert bool(_rides(N.route)) != risk, (_rides(N.route), str(N.lastRideCheck))
    finally:
        R.Background = real


def test_a_provisional_ride_check_doesnt_undo_the_safe_way_while_asking(game, trip):
    # (asked 2026-11-16: "after a few seconds it went to the dangerous route anyway before selecting No") with "Risk
    # enemy territory?" up, the safe way shown; a check worked out again whose walks were still searched said "walk" and
    # the route went past Dun Algaz. A provisional answer never replaces a final one
    lua, ns = game
    N, R = ns.Nav, ns.Router
    trip(WETLANDS, LOCH_MODAN, "Horde", 30)
    assert len(_asks(lua)) == 1 and _rides(N.route)  # (asking: the safe way meanwhile)
    real = R.Background
    lua.execute("""AGPS_HELD = AGPS_NS.Router.Background
      AGPS_NS.Router.Background = function(key, fn, done)
        if string.sub(key, 1, 5) == "ride:" then -- (worked out, but its walks still searched: the walk "won")
          return AGPS_HELD(key, fn, function(res)
            if res then res.final, res.won, res.risk = false, false, nil end
            return done(res)
          end)
        end
        return AGPS_HELD(key, fn, done)
      end""")
    try:
        lua.execute("AGPS_POS[1] = AGPS_POS[1] + 250")  # (on: another square (RIDE_CHECK_YD), checked again)
        N.Invalidate(False)  # (the route worked out again, as walking on does)
        trip.settle()
        assert any(str(v).startswith("pending ride:") or str(v).startswith("last ") for v in N.RideDebug().values())
        print("DBG", list(N.RideDebug().values()), str(N.lastRideCheck)[:300])
        assert _rides(N.route), (_rides(N.route), str(N.lastRideCheck))
    finally:
        R.Background = real


def test_the_risk_question_is_asked_once_a_route(game, trip):
    # (asked 2026-11-16: "On a single route this should only be asked once and remembered while that route is active")
    # answered, not asked again: the same stop set again (a quest route's update, a reorder), and after a /reload (saved
    # with the stops, as the zones too high said yes to are); a new stop is asked about
    lua, ns = game
    N = ns.Nav
    trip(WETLANDS, LOCH_MODAN, "Horde", 30)
    asks = _asks(lua)
    assert len(asks) == 1
    asks[0].no()
    trip.settle()
    stop = N.stops[1]
    key = N.RiskKey(stop)
    assert N.riskOk[key] is False and ns.CharDB().riskOk[key] is False  # (saved with the route)
    N.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'stop' } }" % (stop.x, stop.y)), False)
    trip.settle()
    assert len(_asks(lua)) == 1 and N.riskOk[key] is False  # (the same stop: kept, not asked)
    N.riskOk = lua.eval("{}")  # (as a /reload: the answers come back from the saved route)
    N.Restore()
    trip.settle()
    assert N.riskOk[key] is False and len(_asks(lua)) == 1
    N.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'other' } }" % (stop.x + 300, stop.y)), False)
    assert N.riskOk[key] is None  # (another stop: its own question)


def test_no_way_round_dun_algaz_is_warned_and_drawn_red(game, trip):
    # no ride to take (no flight path known, the boats and zeppelins left out): the walk through Dun Algaz, said once in
    # chat and in the directions panel, and its stretch past the guards red on the map and the minimap; the rest of
    # the route in its usual blue
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    r, said = trip(BY_DUN_ALGAZ, LOCH_MODAN, "Horde", 30, known=[], rides=False)
    assert not _rides(r) and _guard_yards(ns, r) > 500
    warned = [m for m in said if "Enemy territory" in m]
    assert len(warned) == 1 and "Dun Algaz" in warned[0] and "no way round" in warned[0], said
    assert "Dun Algaz" in str(N.HostileNote())
    lua.execute("AGPS_T = AGPS_T + 0.5")
    G.Update()
    assert len([m for m in said if "Enemy territory" in m]) == 1  # (once a route)
    colors = _map_colors(lua)
    assert RED in colors and "0.05,0.28,0.85" in colors, colors
    assert RED in _minimap_colors(ns)


def test_the_directions_line_goes_once_the_route_shown_misses_the_guards(game, trip):
    # (asked 2026-11-14, a screenshot: after a /reload the route went round Southshore by the hearthstone, and the
    # directions still said "Through enemy territory: Southshore", looked for on the route before; the stops the same)
    lua, ns = game
    N = ns.Nav
    trip(BY_DUN_ALGAZ, LOCH_MODAN, "Horde", 30, known=[], rides=False)
    assert "Dun Algaz" in str(N.HostileNote())
    r = N.route
    # (the same route, its walk moved far off the guards: as a route worked out again)
    lua.globals().AGPS_R = r
    lua.execute(f"""
      local r = AGPS_R
      local np = {{}}
      for k, part in ipairs(r.parts) do
        local q = {{}}
        for i = 1, #part.pts, 2 do q[i], q[i + 1] = part.pts[i] - 3000, part.pts[i + 1] end
        np[k] = {{ pts = q, kinds = part.kinds, cont = part.cont, stop = part.stop }}
      end
      local copy = {{}}
      for key, v in pairs(r) do copy[key] = v end
      copy.parts = np
      AGPS_NS.Nav.route = copy
    """)
    assert N.HostileNote() is None
    lua.globals().AGPS_R = r
    lua.execute("AGPS_NS.Nav.route = AGPS_R")
    assert "Dun Algaz" in str(N.HostileNote())


def test_with_avoiding_off_the_stretch_past_their_guards_is_still_red(game, trip):
    lua, ns = game
    r, said = trip(BY_DUN_ALGAZ, LOCH_MODAN, "Horde", 30, avoid=False)
    assert ns.Router.HostileSide() is None and not _rides(r)  # (the walk: guards not weighed)
    assert RED in _map_colors(lua) and RED in _minimap_colors(ns)
    warned = [m for m in said if "Enemy territory" in m]
    assert len(warned) == 1 and "Dun Algaz" in warned[0] and "no way round" not in warned[0], said


def test_an_alliance_route_through_dun_algaz_isnt_red(game, trip):
    # (their own guards)
    lua, ns = game
    r, said = trip(BY_DUN_ALGAZ, LOCH_MODAN, "Alliance", 30, known=[], rides=False)
    assert ns.Nav.HostileOnRoute(r) is None and ns.Nav.HostileNote() is None
    assert RED not in _map_colors(lua) and RED not in _minimap_colors(ns)
    assert not [m for m in said if "Enemy territory" in m]


def test_the_stretches_past_guards_split_a_piece_in_order(game):
    lua, ns = game
    N = ns.Nav
    cdb = ns.CharDB()
    fac = cdb.faction
    try:
        cdb.faction = "Horde"
        # (straight down the road's line of guards at x = -4430: in their reach from about y = -2480 to -2720)
        part = lua.eval("{ cont = 0, pts = { -4430, -2300, -4430, -2900 }, kinds = { 0 } }")
        spans = N.HostileSpans(part, 1)
        ts = [spans[i] for i in range(1, len(spans) + 1)]
        assert ts and ts == sorted(ts) and 0 < ts[0] < ts[-1] < 1
        assert -2300 - 600 * ts[0] == pytest.approx(-2440, abs=60)
        pc = lua.eval("{}")
        N.EachHostilePiece(spans, lua.eval("function(t) return function(a, b, h) t[#t + 1] = { a, b, h } end end")(pc))
        pieces = [(pc[i][1], pc[i][2], pc[i][3]) for i in range(1, len(pc) + 1)]
        assert pieces[0][0] == 0 and pieces[-1][1] == 1 and not pieces[0][2] and not pieces[-1][2]
        assert all(math.isclose(pieces[k][1], pieces[k + 1][0]) for k in range(len(pieces) - 1))
        assert any(p[2] for p in pieces)
        # a ride over them isn't in their reach; the Alliance's own guards aren't hostile to them
        ride = lua.eval("{ cont = 0, pts = { -4430, -2300, -4430, -2900 }, kinds = { 2 } }")
        assert N.HostileSpans(ride, 1) is False
        cdb.faction = "Alliance"
        assert N.HostileSpans(lua.eval("{ cont = 0, pts = { -4430, -2300, -4430, -2900 }, kinds = { 0 } }"), 1) is False
    finally:
        cdb.faction = fac


def test_the_warning_is_worked_out_in_short_slices(game):
    # (a lag spike would come back here) the route's towns past their guards are looked for in a background job
    # (N.CheckHostileRoute: Router.Background) that pauses along the way: a long route, 20 times through Dun Algaz's
    # line of guards, in slices under the frame budget
    from test_frame_budget import FRAME_MS

    lua, ns = game
    R, N = ns.Router, ns.Nav
    cdb = ns.CharDB()
    fac = cdb.faction
    pts = []
    for k in range(400):
        pts += [-4430.0 + (k % 2) * 60.0, -2300.0 - 600.0 * ((k // 2) % 2) - 0.5 * k]
    route = lua.eval("function(p, n) local r = { parts = { { cont = 0, pts = p, kinds = {} } } } "
                     "for i = 1, n do r.parts[1].kinds[i] = 0 end return r end")(lua.table(*pts), len(pts) // 2 - 1)
    try:
        cdb.faction = "Horde"
        R.WARM, R.SYNC_WALKS = True, False
        lua.execute("AGPS_TOWNS = nil")
        R.Background("test:hostile", lua.eval("function(N, r) return function() return N.HostileOnRoute(r) end end")(N, route),
                     lua.eval("function(t) AGPS_TOWNS = t end"))
        clock = lua.eval("function() return os.clock() * 1000 end")
        worst = 0.0
        while R.HasWork():
            a = clock()
            R.Pump(clock() + 1, clock)
            worst = max(worst, clock() - a)
        assert worst < FRAME_MS, f"a slice ran {worst:.0f} ms"
        towns = lua.eval("AGPS_TOWNS")
        assert towns and towns[1][1] == "Dun Algaz"
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        cdb.faction = fac


TARREN_MILL = (-30.0, -880.0)  # (by its flight master)
WHELGAR = (-3450.0, -1850.0)  # (Whelgar's Excavation Site, the Wetlands)


@pytest.fixture(scope="module")
def horde_router():
    from azerothgps.routecheck import ADDON_DIR, _runtime

    lua, ns = _runtime("H")
    # (the bridges too, as in the game: Thandol Span's link over the gorge is no hop, Router.OverBridge)
    loader = lua.eval("function(src, name) return assert(load(src, '@' .. name)) end")
    loader((ADDON_DIR / "Data/Bridges.lua").read_text(encoding="utf-8"), "Data/Bridges.lua")("AzerothGPS", ns)
    return lua, ns


def _pts(r):
    flat = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


def test_tarren_mill_to_the_wetlands_is_no_straight_swim(horde_router):
    # (reported 2026-11-14, screenshot: as a Horde character the route from Tarren Mill to the Wetlands was one dotted
    # line straight across) the road through the Arathi Highlands passes 89 yd of an Alliance guard's reach, at 20
    # times a yard, and lost to the direct walk the terrain search found: a 1.6k yd swim down the coast from Hillsbrad
    # (water at 1.5 a yard). The road is priced as the way round the guard post now (Router.BentRoadCost). And
    # since #339 the road's link over Thandol Span (a bridge the terrain grid doesn't know) was a hop at HOP_COST, so
    # the swim won for anyone: a link over a bridge model isn't one (Router.OverBridge)
    lua, ns = horde_router
    R = ns.Router
    R.Reset()
    r = R.Route(0, *TARREN_MILL, *WHELGAR, lua.table(offroad=False))
    pts, kinds = _pts(r), [r.kinds[i] for i in range(1, len(r.kinds) + 1)]
    longest_off = max((math.dist(pts[i], pts[i + 1]) for i, k in enumerate(kinds) if k != R.KIND_ROAD), default=0)
    assert r.road > 0.7 * r.length and longest_off < 600, (r.road, r.length, longest_off)


def test_a_road_past_a_guard_post_bends_round_it(horde_router):
    # (asked 2026-11-14: "avoid their aggro with detour suggestions") the same road passes one Alliance guard's spot in
    # the Arathi Highlands (-1381, -2067, its reach 45 yd): the route goes round it over the field (Router's
    # BendRoundGuards), none of it in their reach, a little longer. (Stromgarde's Cavalrymen stood there: since
    # 2026-11-16 only the NPCs that would flag a player for PvP count, and they don't, so the post is the test's own)
    lua, ns = horde_router
    R = ns.Router
    lua.eval("function(t) table.insert(t, -1381) table.insert(t, -2067) table.insert(t, 45) end")(ns.Hostile[0].H)
    R.HostileChanged()
    try:
        _bends_round_the_post(lua, ns)
    finally:
        lua.eval("function(t) for _ = 1, 3 do table.remove(t) end end")(ns.Hostile[0].H)
        R.HostileChanged()


def _bends_round_the_post(lua, ns):
    R = ns.Router
    r = R.Route(0, *TARREN_MILL, *WHELGAR, lua.table(offroad=False))
    pts = _pts(r)
    guard = sum(R.HostileYards(0, *pts[i], *pts[i + 1], "H") for i in range(len(pts) - 1))
    assert r.bent and guard == 0
    # one leg straight through its spot: bent, and only a little longer; one 60 yd off it: left as it is
    through = lua.eval("{ pts = { -1381, -1900, -1381, -2250 }, kinds = { 0 }, length = 350, road = 350 }")
    b = R.BendRoundGuards(0, through, -1381, -1900, -1381, -2250)
    bp = _pts(b)
    assert b.bent and sum(R.HostileYards(0, *bp[i], *bp[i + 1], "H") for i in range(len(bp) - 1)) == 0
    assert 350 < b.length < 350 + 150 and [b.kinds[i] for i in range(1, len(b.kinds) + 1)].count(R.KIND_OFFROAD) == 3
    past = lua.eval("{ pts = { -1321, -1900, -1321, -2250 }, kinds = { 0 }, length = 350, road = 350 }")
    assert not R.BendRoundGuards(0, past, -1321, -1900, -1321, -2250).bent


def test_zones_too_high_are_asked_about_in_one_popup(game, trip):
    # (asked 2026-11-14: "when routing through multiple higher level zones, just ask in 1 popup") level 14, Tarren Mill
    # to the Wetlands: the stop is in a zone too high (asked when it's set), and the way there walks through the Arathi
    # Highlands too; said yes to once, the trip isn't asked about again
    lua, ns = game
    trip(TARREN_MILL, WHELGAR, "Horde", 14, known=[10, 11, 13], force=None)
    asks = _asks(lua)
    assert len(asks) == 1 and "Wetlands" in str(asks[0].text), [str(a.text) for a in asks]
    asks[0].yes()
    trip.settle()
    assert ns.Nav.route and len(_asks(lua)) == 1, [str(a.text) for a in _asks(lua)]


def test_while_the_ride_check_runs_the_walk_shows_not_the_straight_line_plans_flight(game):
    # (reported 2026-11-14, screenshot: level 20 from Tarren Mill to the Wetlands showed "fly to The Sepulcher, walk
    # 13.1k yd" for half a minute) the plan's ride, chosen by straight lines (the straight walk crossing the Arathi
    # Highlands, too high), was shown while the ride check routed the walks; it chose the walk. Meanwhile now: the walk
    lua, ns = game
    N, G, R = ns.Nav, ns.GPS, ns.Router
    cdb = ns.CharDB()
    saved = (cdb.faction, cdb.taxiNodes)
    try:
        lua.execute("AGPS_LEVEL = 20")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { { nodeID = 10, known = true }, { nodeID = 11, known = true }, "
                                 "{ nodeID = 13, known = true } } } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        R.Reset()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {TARREN_MILL[0]}, {TARREN_MILL[1]}, 0")
        R.WARM, R.SYNC_WALKS = True, False
        N.SetStops(lua.eval(f"{{ {{ x = {WHELGAR[0]}, y = {WHELGAR[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        G.Follow()
        clock = lua.eval("function() return os.clock() * 1000 end")
        shown = []
        for _ in range(600):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            G.Update()
            if R.HasWork():
                R.Pump(clock() + 20, clock)
            if N.route and N.route.legs:
                shown.append(tuple(str(N.route.legs[i].ride[10]) for i in range(1, len(N.route.legs) + 1)
                                   if N.route.legs[i].ride))
            if not R.HasWork() and not N.RideChecking() and len(shown) > 20:
                break
        assert shown and not any("The Sepulcher, Silverpine Forest" in s for s in shown), set(shown)
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = saved
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_at_level_20_tarren_mill_to_the_wetlands_takes_the_road_through_arathi_and_asks(game, trip):
    # (asked 2026-11-14: level 20-25, the way round the Arathi Highlands (30-40) was a 1.6k yd swim down the coast;
    # "take the road through Arathi with a warning") a long swim costs as much a yard as a zone too high
    # (Router.SWIM_DETOUR_YD), so the route walks the road through Arathi, and the trip's one popup names it
    lua, ns = game
    trip(TARREN_MILL, WHELGAR, "Horde", 20, known=[10, 11, 13], force=None)
    asks = _asks(lua)
    assert len(asks) == 1 and "Arathi" in str(asks[0].text), [str(a.text) for a in asks]
    asks[0].yes()
    trip.settle()
    r = ns.Nav.route
    assert r and len(_asks(lua)) == 1, [str(a.text) for a in _asks(lua)]
    R, P = ns.Router, ns.Passability
    wet = 0.0
    for pi in range(1, len(r.parts) + 1):
        part = r.parts[pi]
        pts = [part.pts[i] for i in range(1, len(part.pts) + 1)]
        for i in range(0, len(pts) - 3, 2):
            sc = P.SegmentCost(0, pts[i], pts[i + 1], pts[i + 2], pts[i + 3])
            if sc:
                wet += max(0.0, sc - math.dist(pts[i:i + 2], pts[i + 2:i + 4])) / (P.SWIM_COST - 1)
    assert wet < R.SWIM_DETOUR_YD, wet


def test_an_isles_swim_through_zones_too_high_is_priced_as_before(game, trip):
    # (route-quality, 2026-11-14, with the swim round Arathi priced as a zone too high) level 20 Alliance, from the
    # Dawning Isles in Lordamere Lake to Light's Hope Chapel: the walk swims the lake and goes on through the
    # Plaguelands, a way round nothing: walked as before, not two flights 13 minutes slower
    lua, ns = game
    r, _ = trip((950.0, 216.7), (2250.0, -5350.0), "Alliance", 20, known=[], force=None)
    for a in _asks(lua):
        a.yes()
    trip.settle()
    assert ns.Nav.route and _rides(ns.Nav.route) == [], _rides(ns.Nav.route)


def test_a_stop_by_the_duskwood_river_is_walked_to_from_duskwood_not_round_by_westfall(game, trip):
    # (asked 2026-11-14, a screenshot: Horde from Grom'gol's side of Duskwood to a stop on the river below Elwynn, "why
    # wouldn't this ... be the fastest route?") Elwynn's road pieces north of the stop were all eight of its entry
    # candidates, so Duskwood's road 200 yd further south was never tried: round by Westfall and Goldshire, 5.6k yd.
    # The nearest road on each side of the stop is tried too, over open ground straight to it (Router.ENTRY_SIDES): north
    # up Duskwood, 2.9k yd
    lua, ns = game
    for avoid in (False, True):
        trip((-11634.5, -403.1), (-10013.4, -677.1), "Horde", 20, known=[], avoid=avoid, rides=False, force=None)
        for a in _asks(lua):
            a.yes()
        trip.settle()
        r = ns.Nav.route
        p = r.parts[1].pts
        pts = [(p[i], p[i + 1]) for i in range(1, len(p), 2)]
        walk = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        assert walk < 3500 and max(y for _, y in pts) < 0, (avoid, walk, max(y for _, y in pts))  # (Westfall: y > 0)


def test_a_stop_just_past_a_towns_guards_is_not_in_the_town(game, trip):
    # (asked 2026-11-14, a screenshot: Horde, avoid on, from Nethander Stead to a stop 45 yd past Southshore's westmost
    # guards: the walk went straight through Southshore, drawn red, and no popup. Within TOWN_NEAR of a town's guards
    # a stop is in that town and its guards cost nothing; 60 yd took this stop in.) Round the town's north, past none
    lua, ns = game
    r, _ = trip((-926.4, -849.7), (-799.6, -357.8), "Horde", 20, known=None, force=None)
    for a in _asks(lua):
        a.yes()
    trip.settle()
    r = ns.Nav.route
    assert ns.Nav.HostileOnRoute(r) is None and _guard_yards(ns, r) == 0
    p = r.parts[1].pts
    assert not any(ns.Router.HostileAt(0, p[i], p[i + 1], "H") for i in range(1, len(p), 2)), "through Southshore"


def test_a_walk_takes_zones_too_high_before_the_other_factions_towns():
    # (asked 2026-11-16, a screenshot: "why isn't the pink dotted line the suggested route when avoid enemy territory is
    # on?") level 14 Horde, Grom'gol to past Redridge, with two short roads the player drew (Duskwood, Redridge): the
    # walk went through Darkshire and Lakeshire, 271 yd past their guards, as the way round them crossed zones too high
    # (LEVEL_FACTOR a yard). "If there is any other route with avoid enemy territory turned on we should use that
    # instead even if higher level area walks are needed" (2026-11-14): the way round, none of it past guards
    from azerothgps.gameharness import start

    lua, ns = start(saved="AzerothGPSDB = { tracks = { { ['op'] = 'add', ['time'] = 1794797689, ['pk'] = '-10079.7 -1476.2 -10079.7 -1479 -10079.3 -1481.9 -10078.9 -1484.7 -10077.2 -1487.2 -10075.2 -1489.2 -10073.5 -1491.7 -10071.5 -1493.7 -10069.5 -1496.2 -10067.8 -1498.6 -10067.4 -1501.5 -10067 -1504.3', ['continent'] = 0, ['drawn'] = true, ['zone'] = 'Hillsbrad Foothills', }, { ['op'] = 'add', ['time'] = 1794797732, ['pk'] = '-8800.5 -2577.1 -8797.7 -2577.9 -8794 -2579.1 -8791.1 -2580.3 -8788.7 -2581.5 -8786.2 -2582.8 -8783.8 -2584 -8781.3 -2585.2', ['continent'] = 0, ['drawn'] = true, ['zone'] = 'Hillsbrad Foothills', } } }")
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end; AGPS_LEVEL = 14; '
                'UnitLevel = function() return 14 end')
    ns.CharDB().faction = "Horde"
    R = ns.Router
    assert R.RedZones() is not None
    R.Reset()
    sx, sy, tx, ty = -12407.0, 212.0, -8160.19, -2522.21
    r = R.Route(0, sx, sy, tx, ty, lua.table(offroad=False))
    assert not r.noWay and R.WalkGuardYards(0, r, sx, sy, tx, ty) < R.HOSTILE_OVER_RED_YD
    # (searched with the zones too high priced, as before: through the towns, the case this is about)
    old, R.GuardsOverHighZones = R.GuardsOverHighZones, lua.eval("function(_, r) return r end")
    try:
        R.Reset()
        before = R.Route(0, sx, sy, tx, ty, lua.table(offroad=False))
        assert R.WalkGuardYards(0, before, sx, sy, tx, ty) >= R.HOSTILE_OVER_RED_YD
    finally:
        R.GuardsOverHighZones = old
