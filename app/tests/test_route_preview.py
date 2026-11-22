"""API 23 (asked 2026-11-21 for a companion addon reviewing routes): RouteTo sets the live route to one stop, and
PreviewWalk makes routes take a recorded walk as the way while it's on (Router.SetPreview), so the directions and the
arrow can be checked along it before the walk is sent in; ended, routes are exactly as before."""

import math

import pytest

from test_addon_lua import env, load, multi, nav_env  # noqa: F401 (fixtures)

pytest.importorskip("lupa")

CONT = 779  # (a continent of the tests' own: only the roads below)
WALK_TIME = 5000


@pytest.fixture
def preview_env(nav_env):
    lua, ns = nav_env
    load(lua, ns, "Api.lua")
    R = ns.Router
    saved = ns.Roads[CONT], ns.db.tracks, R.SYNC_WALKS
    # a straight road west to east, (0, 0) to (200, 0); and a walk recorded the long way round, north to y = 80
    ns.Roads[CONT] = lua.eval("""{ n = { 0,0, 200,0 }, e = { { 1,2,200,0, 0,0, 100,0, 200,0 } } }""")
    ns.db.tracks = lua.eval("""{
      { op = "add", drawn = true, recorded = true, continent = %d, zone = "Test", time = %d,
        pts = { 0,0, 0,40, 0,80, 100,80, 200,80, 200,40, 200,0 } },
    }""" % (CONT, WALK_TIME))
    R.SYNC_WALKS = True
    R.Reset()
    try:
        yield lua, ns, lua.globals().AzerothGPS
    finally:
        ns.Router.SetPreview(None)
        ns.Roads[CONT], ns.db.tracks, R.SYNC_WALKS = saved
        R.Reset()


def route_len(r):
    p = r.pts
    return sum(math.hypot(p[i + 2] - p[i], p[i + 3] - p[i + 1]) for i in range(1, len(p) - 2, 2))


def north_most(r):
    return max(r.pts[i] for i in range(2, len(r.pts) + 1, 2))


def test_a_previewed_walk_is_the_way_while_on_and_not_after(preview_env):
    lua, ns, A = preview_env
    R = ns.Router
    r = R.Route(CONT, 0.0, 0.0, 200.0, 0.0, lua.table())
    assert r and route_len(r) < 210 and north_most(r) < 5  # (the straight road: the walk is the long way)
    got = []
    done = lua.eval("function(f) return function(...) f(...) end end")(lambda *a: got.append(a))  # (a Lua function)
    ok, n = multi(lua, A.PreviewWalk, lua.table(WALK_TIME), done)
    assert ok is True and n == 1 and A.Previewing() is True
    r = R.Route(CONT, 0.0, 0.0, 200.0, 0.0, lua.table())
    assert r and north_most(r) > 75 and route_len(r) > 350, (route_len(r), north_most(r))
    # (the route from the walk's start to its end, worked out with it on: all along it)
    assert len(got) == 1 and got[0][0] > 0.95 and got[0][2] > 350, got
    # ended: the straight road again
    assert multi(lua, A.PreviewWalk, None) == (True, 0) and A.Previewing() is False
    r = R.Route(CONT, 0.0, 0.0, 200.0, 0.0, lua.table())
    assert r and route_len(r) < 210 and north_most(r) < 5


def test_a_preview_of_no_recorded_walk_is_refused_and_changes_nothing(preview_env):
    lua, ns, A = preview_env
    ns.db.tracks[2] = lua.eval("""{ op = "add", drawn = true, continent = %d, time = 6000, pts = { 0,0, 0,80 } }""" % CONT)
    for times in (lua.table(1234), lua.table(6000), 1234):
        ok, why = multi(lua, A.PreviewWalk, times)
        assert ok is False and why == "none"
    assert A.Previewing() is False and ns.Router.preview is None
    assert multi(lua, A.PreviewWalk, None) == (True, 0)  # (none on: nothing to end)


def test_along_preview_takes_a_road_near_the_walk_all_along_not_one_that_crosses_it(preview_env):
    lua, ns, A = preview_env
    R = ns.Router
    A.PreviewWalk(WALK_TIME)
    pv = R.preview
    assert pv and pv.level == CONT
    edge = lambda *pts: lua.table(1, 2, 0, 0, *pts)  # noqa: E731
    assert R.AlongPreview(pv, edge(0, 0, 0, 80, 150, 80))  # (on it)
    assert R.AlongPreview(pv, edge(2, 10, 2, 70))  # (2 yd off, alongside)
    assert not R.AlongPreview(pv, edge(-50, 40, 50, 40))  # (across it)
    assert not R.AlongPreview(pv, edge(0, 0, 200, 0))  # (its ends on the walk, its middle 80 yd off)


def test_route_to_sets_one_stop_the_player_made(preview_env):
    lua, ns, A = preview_env
    N = ns.Nav
    N.SetStops(lua.eval("{ { x = 1, y = 2, cont = 1, name = 'Old' }, { x = 3, y = 4, cont = 1, name = 'Older' } }"))
    assert multi(lua, A.RouteTo, 1, 120.5, -40.0, 12.25, "Bank")[0] is True
    assert len(N.stops) == 1
    d = N.stops[1]
    assert (d.x, d.y, d.cont, d.z, d.name) == (120.5, -40.0, 1, 12.25, "Bank")
    assert multi(lua, A.RouteTo, 1, None, 3)[0] is False and len(N.stops) == 1  # (no place: nothing changes)
