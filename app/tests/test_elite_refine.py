"""Elite areas after the background work (item 132, Kooki3z 2026-11-27 in Tanaris: "routing was avoiding the elites,
then the background recalculate came back and went through them without asking"). West of Sandsorrow Watch his final
route was a straight east-west line with three red stretches through the gold areas, and no "Take it?".

Two causes. The world grid's string pulling (WorldGrid.Pull) drew straight lines from step to step of the search's way
(up to LOOK_AHEAD steps, 400 yd) checked only for being walkable: the search went round the areas, its pulled line
through them. The refine's search (WG.Refine, a long leg's best way searched again in the background) hugs the areas,
so its pulled line cut across them. Now each pulled line is no dearer by the search's costs than the steps it replaces
(WG.PullAllowed). And the trip was looked at for enemies once (Nav.CheckHostileRoute, keyed on the stops): a later
route through them was never asked about. Now each later settled route is looked at again, and an elite area no
question of the trip was about is asked about ("Take it?"), after a yes too."""

import math

import pytest

pytest.importorskip("lupa.lua51")

# (west Tanaris: east of the elite areas by Sandsorrow Watch to west of them, the straight line through two of them;
# world yards, x north, y west)
EAST, WEST = (-6920.0, -3350.0), (-6920.0, -2560.0)
TANARIS = 1


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    yield lua, ns


@pytest.fixture
def trip(game):
    lua, ns = game
    N, R, WG, st = ns.Nav, ns.Router, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.useFlights, st.avoidElites, st.eliteOffset, WG.LONG_LEG_YD, R.WARM, R.SYNC_WALKS)
    st.worldGrid, st.useFlights, st.avoidElites, st.eliteOffset = True, False, None, None
    # (the leg weighed as a long one's (HEUR_LONG) and its best way searched again in the background, WG.Refine: the
    # background work Kooki3z's long walk across Tanaris had, here on a short leg)
    WG.LONG_LEG_YD = 500
    R.WARM, R.SYNC_WALKS = True, False
    lua.execute("UnitFactionGroup = function() return 'Horde', 'Horde' end")
    ns.CharDB().faction = "Horde"
    lua.execute("""
      AGPS_E_ASKED = {}
      AGPS_E_CH = AGPS_NS.GPS.ConfirmHostile
      AGPS_NS.GPS.ConfirmHostile = function(names, side, yes, no, elite)
        AGPS_E_ASKED[#AGPS_E_ASKED + 1] = { names = table.concat(names, ", "), elite = elite }
        return AGPS_E_CH(names, side, yes, no, elite)
      end
      AGPS_E_PULL = AGPS_NS.WorldGrid.PullAllowed""")
    WG.Reset()
    R.Reset()
    yield lua, ns
    lua.execute("AGPS_NS.GPS.ConfirmHostile = AGPS_E_CH AGPS_NS.WorldGrid.PullAllowed = AGPS_E_PULL")
    pending = ns.GPS.PendingQuestion()
    if pending:
        pending.no._scripts.OnClick(pending.no, "LeftButton")
    N.Clear()
    N.route = None
    (st.worldGrid, st.useFlights, st.avoidElites, st.eliteOffset, WG.LONG_LEG_YD, R.WARM, R.SYNC_WALKS) = saved
    WG.Reset()
    R.Reset()


def _settle(lua, ns, frames=6000):
    """The game's frames until the trip is settled: its searches, the refine and the look for enemies all done."""
    N, R = ns.Nav, ns.Router
    clock = lua.eval("function() return os.clock() * 1000 end")
    quiet = 0
    for _ in range(frames):
        lua.execute("AGPS_T = AGPS_T + 0.05")
        N.Status(EAST[0], EAST[1], TANARIS)
        N.Tick()
        if R.HasWork():
            R.Pump(clock() + 20, clock)
        if N.route and not N.route.pending and not R.HasWork() and not N.StretchesPending() and not N.Checking():
            quiet += 1
            if quiet > 60:  # (3 s on: past N.HOSTILE_RECHECK_SECONDS)
                return N.route
        else:
            quiet = 0
    raise AssertionError("the trip never settled")


def _asked(lua):
    asked = lua.eval("AGPS_E_ASKED")
    return [(str(asked[i].names), asked[i].elite is True) for i in range(1, len(asked) + 1)]


def _elite_yards(ns, r):
    """Yards the route walks through elite areas (N.HostileOnRoute's, the ends' own ways in and out left out)."""
    return sum(t[2] for t in (ns.Nav.HostileOnRoute(r) or {}).values() if t[3])


def _red_yards(ns, r):
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


def _start_trip(lua, ns, level):
    N, R = ns.Nav, ns.Router
    lua.execute(f"AGPS_LEVEL = {level} AGPS_E_ASKED = {{}}")
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {EAST[0]}, {EAST[1]}, {TANARIS}")
    N.Clear()
    N.SetStops(lua.eval(f"{{ {{ x = {WEST[0]}, y = {WEST[1]}, cont = {TANARIS}, name = 'west' }} }}"), False, "red")
    # (the straight line crosses the elite areas, none at either end: the areas are this trip's to go round)
    key = R.HostileSide()
    assert key and R.EliteMin() is not None
    for p in (EAST, WEST):
        assert not R.HostileTownsNear(TANARIS, key, p[0], p[1])
    assert any(R.EliteTownsAt(TANARIS, EAST[0], y, key) for y in range(int(EAST[1]), int(WEST[1]), 10))


@pytest.mark.parametrize("level", [25, 40])
def test_the_route_after_the_background_work_still_goes_round_the_elites(trip, level):
    lua, ns = trip
    WG = ns.WorldGrid
    _start_trip(lua, ns, level)
    refined = WG.stats.refined or 0
    r = _settle(lua, ns)
    assert (WG.stats.refined or 0) > refined  # (the refine's way searched and swapped in: the background work)
    assert _elite_yards(ns, r) == 0, [tuple(t.values()) for t in ns.Nav.HostileOnRoute(r).values()]
    assert _red_yards(ns, r) < 1
    # (round them, not far: the straight line is 790 yd)
    assert r.totalYards < 790 * 1.25
    assert _asked(lua) == []


def test_a_later_route_through_the_elites_is_asked_about(trip):
    lua, ns = trip
    N, WG = ns.Nav, ns.WorldGrid
    _start_trip(lua, ns, 25)
    r = _settle(lua, ns)
    assert _elite_yards(ns, r) == 0 and _asked(lua) == []
    # (a later recalculation through them: the pulled lines unchecked, as before the fix)
    lua.execute("AGPS_NS.WorldGrid.PullAllowed = function() return true end")
    WG.Reset()
    N.Invalidate(True)
    r = _settle(lua, ns)
    assert _elite_yards(ns, r) > 50
    asked = _asked(lua)
    assert len(asked) == 1 and asked[0][1], asked
    q = ns.GPS.PendingQuestion()
    assert q and "(elite enemies). Take it?" in str(q.text._text)
    q.yes._scripts.OnClick(q.yes, "LeftButton")
    assert N.RiskAnswer(N.dest) is True
    # (yes: a later route through the same areas isn't asked about again)
    WG.Reset()
    N.Invalidate(True)
    r = _settle(lua, ns)
    assert _elite_yards(ns, r) > 50
    assert len(_asked(lua)) == 1
