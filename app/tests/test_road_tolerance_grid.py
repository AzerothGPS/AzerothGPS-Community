"""Road tolerance in the world grid (item 30, Kooki3z on bbc4c8c4: at +10, Use class spells off, Safe drop 60, from just
east of Camp Taurajo to Bluefen the route ran down the Southern Gold Road to Shady Rest and back up the marsh, 2.6k yd).
The grid's road preference follows Router.RoadFactor (WorldGrid's x.road, in its cost key): +10 no road bonus, -10 the
roads strongly. Here it still goes round: the straight way (900 yd) climbs the ridge between (92 to 216 yd up) and
falls about 180 yd to the marsh; its far side needs a drop of about 100 yd (1.15k yd at 100, 1.6k at 70-80, 1.08k from
130), past Safe drop 60. So the trip is round at any tolerance without a fall spell, the shortest at +10."""

import pytest

from test_map_redraw import game  # noqa: F401

TAURAJO_EAST, BLUEFEN = (-2268.0, -2058.0), (-2800.0, -2780.0)


@pytest.fixture
def no_spells_60(game):  # noqa: F811
    lua, ns = game
    st, WG = ns.settings.gps, ns.WorldGrid
    saved = (st.worldGrid, st.safeDropYd, st.useClassSpells, st.roadTolerance)
    st.worldGrid, st.safeDropYd, st.useClassSpells = True, 60, False
    WG.Set(True)
    lua.execute("AGPS_RT_SPELL = IsPlayerSpell; IsPlayerSpell = function() return false end")
    ns.FallSpells.Refresh()
    yield
    st.worldGrid, st.safeDropYd, st.useClassSpells, st.roadTolerance = saved
    WG.Set(bool(saved[0]))
    lua.execute("IsPlayerSpell = AGPS_RT_SPELL")
    ns.FallSpells.Refresh()
    ns.Router.Reset()


def _route(lua, ns, tol, **opts):
    R, WG = ns.Router, ns.WorldGrid
    ns.settings.gps.roadTolerance = tol
    R.Reset()
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    r = R.Route(1, TAURAJO_EAST[0], TAURAJO_EAST[1], BLUEFEN[0], BLUEFEN[1], lua.table(**opts))
    ks = [r.kinds[i] for i in range(1, len(r.pts) // 2)]
    return r.length, sum(1 for k in ks if k == R.KIND_ROAD), r.pending


def test_road_tolerance_steers_the_world_grid(game, no_spells_60):  # noqa: F811
    lua, ns = game
    at0, road0, p0 = _route(lua, ns, 0)
    at10, road10, p10 = _route(lua, ns, 10)
    atm10, roadm10, pm10 = _route(lua, ns, -10)
    assert not (p0 or p10 or pm10)
    assert at10 < at0 - 200 and road10 == 0, (at10, at0, road10)  # (+10: no road kept, shorter)
    assert atm10 > at0 and roadm10 > road0, (atm10, at0, roadm10, road0)  # (-10: onto the roads)


def test_the_straight_way_needs_a_drop_past_safe_drop_60(game, no_spells_60):  # noqa: F811
    lua, ns = game
    at60, _, _ = _route(lua, ns, 10)
    at130, _, _ = _route(lua, ns, 10, maxDrop=130)
    assert at60 > 2000 and at130 < 1200, (at60, at130)
