"""Lift first (1.4.2, Kooki3z 2026-11-27: "nearby lift should take priority over spell jump option unless its like 30
more seconds to get to the lift").

A spell jump (a drop past the player's own safe drop, one a fall spell makes safe) with a lift's car within
Router.LIFT_FIRST_REACH_YD of its top, for the same climb, costs Router.LIFT_FIRST_S (30 s) more in every search: the
route takes the lift (its wait and ride, the walk to it and from it) unless that way is 30 s or more slower. With the
whole addon at Freewind Post (Thousand Needles), whose mesa's rim a mage with Slow Fall can jump off by its lift.
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401

pytest.importorskip("lupa")

MAGE = "IsPlayerSpell = function(id) return id == 130 end GetItemCount = function(id) return id == 17056 and 20 or 0 end"
NO_SPELL = "IsPlayerSpell = function() return false end GetItemCount = function() return 0 end"
FREEWIND_SHAFTS = ((-5399.2, -2504.6), (-5382.5, -2489.4))  # (Data/LiftTimes.lua's station 4)
MESA_TOP = (-5430.0, -2450.0)  # (Freewind Post's mesa, by the lift's top)
# (the canyon floor south-east: the jump off the rim by the lift is a few seconds quicker than the lift)
FLOOR_NEAR = (-5300.0, -2600.0)
# (from the mesa's south-west edge to the canyon floor west: the jump straight down from the start, 104 yd from the
# lift, is far quicker than walking to the lift, riding it and walking back round the mesa's foot)
WEST_EDGE, FLOOR_WEST = (-5500.0, -2480.0), (-5649.2, -2504.6)


def _kinds(ns, r):
    """[(kind, x, y, fall), ...]: the route's drops and lift rides, each run's first piece."""
    R = ns.Router
    out = []
    for p in range(1, len(r.parts) + 1):
        part = r.parts[p]
        n = len(part.pts) // 2
        ks = [part.kinds[i] for i in range(1, n)]
        for i, k in enumerate(ks):
            if k in (R.KIND_DROP, R.KIND_LIFT_UP, R.KIND_LIFT_DOWN) and (i == 0 or ks[i - 1] != k):
                fall = R.DropFall(part.pts, part.kinds, i + 1)[0] if k == R.KIND_DROP else None
                out.append((k, part.pts[2 * i + 1], part.pts[2 * i + 2], fall))
    return out


def _near(p, shafts, yd):
    return min(math.dist(p, s) for s in shafts) <= yd


@pytest.fixture
def trip(game):  # noqa: F811
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, st.zoom, st.fastestOrder, st.expertJumper, st.cityGrid, st.worldGrid, ns.Router.LIFT_FIRST_S)
    lua.execute("AGPS_LF = { IsPlayerSpell, GetItemCount, UnitIsGhost }")

    def run(a, b, *setup):
        st.zoom, st.fastestOrder, st.expertJumper = 300, False, False
        st.cityGrid = st.worldGrid = True
        ns.WorldGrid.Set(True)
        cdb.faction = "Horde"
        N.Clear()
        lua.execute(NO_SPELL)
        for c in setup:
            lua.execute(c)
        ns.FallSpells.Refresh()
        ns.Router.Reset()
        lua.execute(f"AGPS_MAP = 1441 AGPS_POS = {{ {a[0]}, {a[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        for _ in range(20):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
        assert N.route is not None and not N.route.noWay
        return N.route

    try:
        yield run
    finally:
        (cdb.faction, st.zoom, st.fastestOrder, st.expertJumper, st.cityGrid, st.worldGrid,
         ns.Router.LIFT_FIRST_S) = saved
        ns.WorldGrid.Set(st.worldGrid)
        N.Clear()
        lua.execute("IsPlayerSpell, GetItemCount, UnitIsGhost = AGPS_LF[1], AGPS_LF[2], AGPS_LF[3]")
        ns.FallSpells.Refresh()
        ns.Router.Reset()
        lua.execute("AGPS_MAP = nil AGPS_POS = { 2254.0, 293.0, 0 } AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()


def _spell_drops(ns, r):
    plain = ns.Nav.PlainSafeDrop()
    return [k for k in _kinds(ns, r) if k[0] == ns.Router.KIND_DROP and k[3] and k[3] > plain + 0.5]


def _lift_rides(ns, r):
    R = ns.Router
    return [k for k in _kinds(ns, r) if k[0] in (R.KIND_LIFT_DOWN, R.KIND_LIFT_UP)]


def test_the_constant_is_thirty_seconds(game):  # noqa: F811
    lua, ns = game
    assert ns.Router.LIFT_FIRST_S == 30


def test_a_lift_beats_a_spell_jump_less_than_30_s_faster(game, trip):  # noqa: F811
    """Off the mesa's rim by the lift with Slow Fall is a few seconds quicker than the lift: the lift."""
    lua, ns = game
    R = ns.Router
    R.LIFT_FIRST_S = 0  # (the rule off: the jump by the lift, as before)
    before = trip(MESA_TOP, FLOOR_NEAR, MAGE)
    jumps = _spell_drops(ns, before)
    assert jumps and all(_near(j[1:3], FREEWIND_SHAFTS, R.LIFT_FIRST_REACH_YD) for j in jumps), _kinds(ns, before)
    R.LIFT_FIRST_S = 30
    r = trip(MESA_TOP, FLOOR_NEAR, MAGE)
    assert not _spell_drops(ns, r), _kinds(ns, r)
    downs = _lift_rides(ns, r)
    assert downs and all(_near(d[1:3], FREEWIND_SHAFTS, 15) for d in downs) and downs[0][0] == R.KIND_LIFT_DOWN
    # (the jump's way wasn't 30 s quicker: its yards within that of the lift's way)
    assert r.totalYards - before.totalYards < R.LIFT_FIRST_S * ns.Lifts.YD_PER_SECOND


def test_a_spell_jump_more_than_30_s_faster_is_kept(game, trip):  # noqa: F811
    """Straight off the mesa's south-west edge, 104 yd from the lift, to the canyon floor west of it: the lift's way
    (to it, down, and back round the foot) is far more than 30 s slower, so the jump stays."""
    lua, ns = game
    R = ns.Router
    lift_way = trip(WEST_EDGE, FLOOR_WEST)  # (no fall spell: the lift)
    assert _lift_rides(ns, lift_way) and not _spell_drops(ns, lift_way)
    r = trip(WEST_EDGE, FLOOR_WEST, MAGE)
    jumps = _spell_drops(ns, r)
    assert jumps and not _lift_rides(ns, r), _kinds(ns, r)
    # (within the lift's reach: weighed, and still the faster way by more than 30 s)
    assert _near(jumps[0][1:3], FREEWIND_SHAFTS, R.LIFT_FIRST_REACH_YD)
    assert R.LiftFirstYards(1, jumps[0][1], jumps[0][2], jumps[0][3], None) == R.LIFT_FIRST_S * ns.Lifts.YD_PER_SECOND
    assert lift_way.totalYards - r.totalYards > R.LIFT_FIRST_S * ns.Lifts.YD_PER_SECOND


@pytest.mark.parametrize("a,b", [(MESA_TOP, FLOOR_NEAR), (WEST_EDGE, FLOOR_WEST)], ids=["near", "west"])
def test_no_fall_spell_is_unchanged(game, trip, a, b):  # noqa: F811
    lua, ns = game
    R = ns.Router
    R.LIFT_FIRST_S = 0
    off = trip(a, b)
    assert R.LiftFirstFloor(1) is None  # (no fall spell: no spell jump to weigh)
    R.LIFT_FIRST_S = 30
    on = trip(a, b)
    assert list(on.pts) == list(off.pts) and on.totalYards == off.totalYards


def test_what_the_rule_weighs(game, trip):  # noqa: F811
    lua, ns = game
    R, N = ns.Router, ns.Nav
    trip(MESA_TOP, FLOOR_NEAR, MAGE)
    floor = R.LiftFirstFloor(1)
    plain = N.PlainSafeDrop()
    assert floor == pytest.approx(plain + 0.5)
    yd = R.LIFT_FIRST_S * ns.Lifts.YD_PER_SECOND
    x, y = -5417.0, -2486.0  # (the rim by the lift)
    assert R.LiftFirstYards(1, x, y, 125, 89.5, floor) == yd
    assert R.LiftFirstYards(1, x, y, plain, 89.5, floor) == 0  # (a plain drop: as it was)
    assert R.LiftFirstYards(1, x, y, 125, 300, floor) == 0  # (not the lift's climb: a ledge far above its top)
    assert R.LiftFirstYards(1, -5399.2, -2504.6 + R.LIFT_FIRST_REACH_YD + 20, 125, 89.5, floor) == 0  # (out of reach)
    assert R.LiftFirstYards(1, -1500.0, -1900.0, 125, 130, floor) == 0  # (no lift anywhere near: the Barrens)
    assert R.LiftFirstYards(0, x, y, 125, 89.5) == 0  # (another continent)
    # (a ghost needs no spell: no rule)
    lua.execute("UnitIsGhost = function(u) return u == 'player' end")
    assert R.LiftFirstFloor(1) is None and R.LiftFirstYards(1, x, y, 125, 89.5) == 0
