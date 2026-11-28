"""An elite area at a walk's end (items 142 and 130, Kooki3z 2026-11-27).

142: a level 25 Alliance druid from the middle of the Barrens into west Tanaris, to a stop at the WEST edge of the gold
elite area (42-46) west of Sandsorrow Watch: the route came from the east and crossed the whole area, drawn red. A walk's
own end area was all free for the router (item 91), so entering from the far side cost nothing. Now only the stop's way
in is free (Router.EliteFree: the shortest line from the area's edge to the stop, Router.ELITE_FREE_YD round it); the rest
costs as any elite area's, so the way round outside wins when it's cheaper, and a crossing is asked about.

130: "Take it?" -> No when the start is in the area (or the stop): the router left the trip's own end area free, so No found
the same way through and asked again after 10 s. The start's area stays free in the first plan (the player is in it, and
the ride check walks from the player's spot rounded: test_elite_areas' Dire Maul), but after a No it's free only along its
shortest way out (Router.EndsExempt, Router.EliteStartCharged), so the search really looks for a way round."""

import math

import pytest

pytest.importorskip("lupa.lua51")

TANARIS, EK = 1, 0
# (west Tanaris: the stop 40 yd past the west edge of the 42-46 area west of Sandsorrow Watch, Data/Elites.lua; world
# yards, x north, y west)
TAN_STOP = (-7035.0, -2630.0)
GADGETZAN = (-7100.0, -3750.0)
TAN_INSIDE, TAN_FAR = (-7035.0, -2700.0), (-7035.0, -2850.0)  # (in the area: near its west edge, and its east part)
# (item 124: Kooki3z's GM.log .go xyz 2954 -1321 165 0, 23 yd out of Hearthglen's 55-63 Scarlet elites; the stop at its
# north edge, Western Plaguelands 46, 13)
HG_START, HG_STOP = (2954.0, -1321.0), (2994.0, -1561.0)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    yield lua, ns


@pytest.fixture
def char(game):
    lua, ns = game
    N, R, WG, st = ns.Nav, ns.Router, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.useFlights, st.avoidElites, st.eliteOffset, st.avoidHostile, ns.CharDB().faction)
    st.worldGrid, st.useFlights, st.avoidElites, st.eliteOffset, st.avoidHostile = True, False, None, None, None
    lua.execute("""
      AGPS_X_UFG, AGPS_X_LVL = UnitFactionGroup, AGPS_LEVEL
      AGPS_X_ASKED = {}
      AGPS_X_CH = AGPS_NS.GPS.ConfirmHostile
      AGPS_NS.GPS.ConfirmHostile = function(names, side, yes, no, elite)
        AGPS_X_ASKED[#AGPS_X_ASKED + 1] = { names = table.concat(names, ", "), elite = elite }
        return AGPS_X_CH(names, side, yes, no, elite)
      end""")

    def be(faction, level):
        lua.execute(f"UnitFactionGroup = function() return '{faction}', '{faction}' end; AGPS_LEVEL = {level}")
        ns.CharDB().faction = faction
        WG.Reset()
        R.Reset()

    yield lua, ns, be
    lua.execute("AGPS_NS.GPS.ConfirmHostile = AGPS_X_CH")
    for _ in range(2):
        pending = ns.GPS.PendingQuestion()
        if pending:
            pending.no._scripts.OnClick(pending.no, "LeftButton")
    N.Clear()
    N.route = None
    (st.worldGrid, st.useFlights, st.avoidElites, st.eliteOffset, st.avoidHostile, ns.CharDB().faction) = saved
    lua.execute("UnitFactionGroup = AGPS_X_UFG AGPS_LEVEL = AGPS_X_LVL")
    WG.Reset()
    R.Reset()


def _settle(lua, ns, a, cont, frames=6000):
    """The game's frames until the trip is settled: its searches, the background work and the look for enemies done."""
    N, R = ns.Nav, ns.Router
    clock = lua.eval("function() return os.clock() * 1000 end")
    quiet = 0
    for _ in range(frames):
        lua.execute("AGPS_T = AGPS_T + 0.05")
        N.Status(a[0], a[1], cont)
        N.Tick()
        if R.HasWork():
            R.Pump(clock() + 20, clock)
        if N.route and not N.route.pending and not R.HasWork() and not N.StretchesPending() and not N.Checking():
            quiet += 1
            if quiet > 60:  # (3 s on: past Nav.HOSTILE_RECHECK_SECONDS)
                return N.route
        else:
            quiet = 0
    raise AssertionError("the trip never settled")


def _trip(lua, ns, cont, a, b):
    N = ns.Nav
    lua.execute(f"AGPS_X_ASKED = {{}} AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {a[0]}, {a[1]}, {cont}")
    N.Clear()
    N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
    return _settle(lua, ns, a, cont)


def _asked(lua):
    asked = lua.eval("AGPS_X_ASKED")
    return [(str(asked[i].names), asked[i].elite is True) for i in range(1, len(asked) + 1)]


def _elite_yards(ns, r):
    """Yards the route walks through elite areas past its ends' ways in and out (Nav.HostileOnRoute's, the question's)."""
    return sum(t[2] for t in (ns.Nav.HostileOnRoute(r) or {}).values() if t[3])


def _red_yards(ns, r):
    """Yards of the walk drawn red (Nav.HostileSpans, the map's own: every elite yard, the ways in and out too)."""
    N = ns.Nav
    yd = 0.0
    for part in r.parts.values():
        pts = part.pts
        for i in range(1, len(pts) // 2):
            spans = N.HostileSpans(part, i)
            if spans:
                d = math.dist((pts[2 * i - 1], pts[2 * i]), (pts[2 * i + 1], pts[2 * i + 2]))
                yd += d * sum(spans[j + 1] - spans[j] for j in range(1, len(spans), 2))
    return yd


def test_only_the_stops_way_into_its_elite_area_is_free(char):
    lua, ns, be = char
    R = ns.Router
    be("Alliance", 25)
    key = R.HostileSide()
    area = R.EliteTownsAt(TANARIS, *TAN_FAR, key)
    assert area and R.EliteTownsAt(TANARIS, *TAN_INSIDE, key)
    (t,) = list(area.keys())
    # (the stop 40 yd out of the area: in it, Router.ELITE_NEAR, but its way in is only round the stop itself)
    near = R.HostileTownsNear(TANARIS, key, *TAN_STOP)
    assert near and near[t] is not True and list(near[t].values()) == [*TAN_STOP, *TAN_STOP]
    # (a stop inside it, near the west edge: its way in is from the west edge, the shortest)
    ex, ey, depth = R.EliteExit(TANARIS, key, t, *TAN_INSIDE)
    assert 0 < depth <= 60 and ey > TAN_INSIDE[1]
    for stop in (TAN_STOP, TAN_INSIDE):
        exempt = R.EndsExempt(TANARIS, key, *GADGETZAN, *stop)
        assert not R.HostileAt(TANARIS, *stop, key, exempt)  # (the stop itself: free)
        assert R.HostileAt(TANARIS, *TAN_FAR, key, exempt)  # (the area's far side: paid for, as any elite area's)
    exempt = R.EndsExempt(TANARIS, key, *GADGETZAN, *TAN_INSIDE)
    assert not R.HostileAt(TANARIS, (TAN_INSIDE[0] + ex) / 2, (TAN_INSIDE[1] + ey) / 2, key, exempt)


def test_the_starts_elite_area_is_free_until_a_no(char):
    lua, ns, be = char
    R, N = ns.Router, ns.Nav
    be("Alliance", 25)
    key = R.HostileSide()
    (t,) = list(R.EliteTownsAt(TANARIS, *TAN_FAR, key).keys())
    was = N.riskOk
    try:
        N.riskOk = lua.eval("{}")
        exempt = R.EndsExempt(TANARIS, key, *TAN_INSIDE, *GADGETZAN)
        assert exempt[t] is True and not R.HostileAt(TANARIS, *TAN_FAR, key, exempt)
        N.riskOk = lua.eval("{ trip = false }")  # ("Take it?" -> No: item 130)
        assert R.EliteStartCharged()
        exempt = R.EndsExempt(TANARIS, key, *TAN_INSIDE, *GADGETZAN)
        assert exempt[t] is not True and R.HostileAt(TANARIS, *TAN_FAR, key, exempt)
        assert not R.HostileAt(TANARIS, *TAN_INSIDE, key, exempt)
    finally:
        N.riskOk = was


def test_tanaris_a_stop_at_the_west_edge_is_reached_round_the_area(char):
    """Item 142's trip, from the east (Gadgetzan, on his way in from the Barrens): round the area, not across it."""
    lua, ns, be = char
    be("Alliance", 25)
    r = _trip(lua, ns, TANARIS, GADGETZAN, TAN_STOP)
    assert _elite_yards(ns, r) == 0, [tuple(t.values()) for t in ns.Nav.HostileOnRoute(r).values()]
    assert _red_yards(ns, r) < 5  # (1.4.1: 182 yd, the whole area)
    assert _asked(lua) == []
    assert r.totalYards < 1160 * 1.1  # (the way across was 1,159 yd: round it, not far)


def test_hearthglen_crosses_and_asks_then_no_finds_the_way_round(char):
    """Item 124's trip, then No (item 130): the start 23 yd out of Hearthglen's area is in it, free in the first plan, so
    the walk crosses the middle and asks; No plans again with the start's area paid for, and goes round."""
    lua, ns, be = char
    N = ns.Nav
    be("Alliance", 25)
    r = _trip(lua, ns, EK, HG_START, HG_STOP)
    assert _elite_yards(ns, r) > 50 and _red_yards(ns, r) > 100
    asked = _asked(lua)
    assert len(asked) == 1 and asked[0][1] and "Hearthglen" in asked[0][0], asked
    q = ns.GPS.PendingQuestion()
    assert q and "(elite enemies). Take it?" in str(q.text._text)
    q.no._scripts.OnClick(q.no, "LeftButton")
    assert N.RiskAnswer(N.dest) is False
    r = _settle(lua, ns, HG_START, EK)
    # (well past Nav.REFUSED_SECONDS: no "No way around ..." either, the way round is settled)
    for _ in range(300):
        lua.execute("AGPS_T = AGPS_T + 0.05")
        N.Status(HG_START[0], HG_START[1], EK)
        N.Tick()
    r = N.route
    assert r and not r.pending and not N.paused
    assert _elite_yards(ns, r) == 0, [tuple(t.values()) for t in (N.HostileOnRoute(r) or {}).values()]
    assert ns.GPS.PendingQuestion() is None and N.guardsAsking is None
    assert r.totalYards < 600  # (round its corner: the way through was ~250 yd)


# (item 135c with 142, the 1.4.2 combined build: the Alliance town in Silithus, its guards at the edge of the big elite
# area round it; Horde. The terrain search's `townEnds` "t" frees the town's guards for a walk to the trip's own stop,
# and set the elite area there to all free too: the walk from the south went straight across 278 yd of elites)
SIL_STOP, SIL_SOUTH = (-7170.0, 1406.0), (-7750.0, 1450.0)


def test_a_walk_into_an_enemy_town_at_an_elite_areas_edge_frees_the_town_not_the_area(char):
    lua, ns, be = char
    R, P = ns.Router, ns.Passability
    be("Horde", 25)
    key = R.HostileSide()
    near = R.HostileTownsNear(TANARIS, key, *SIL_STOP)
    assert near
    towns = [t for t, v in near.items() if v is True]
    areas = [t for t, v in near.items() if v is not True]
    assert towns and areas, dict(near.items())
    exempt = R.EndsExempt(TANARIS, key, *SIL_SOUTH, *SIL_STOP)
    cost = {}
    for town_ends in (None, "t"):
        found = P.FindPath(TANARIS, *SIL_SOUTH, *SIL_STOP, False, False, town_ends)
        assert found, town_ends
        cost[town_ends], path = found[0], found[1]
        off = sum(R.EliteYardsOff(TANARIS, key, t, exempt[t], path, 1) for t in areas)
        assert off < 5, (town_ends, off, cost[town_ends])
    assert cost["t"] <= cost[None] + 1e-6  # (the town's own guards: free for the walk to the stop in it)


def test_silithus_a_trip_into_the_enemy_town_goes_round_the_elite_area(char):
    lua, ns, be = char
    be("Horde", 25)
    r = _trip(lua, ns, TANARIS, SIL_SOUTH, SIL_STOP)
    assert _elite_yards(ns, r) == 0, [tuple(t.values()) for t in (ns.Nav.HostileOnRoute(r) or {}).values()]
    assert _asked(lua) == []
