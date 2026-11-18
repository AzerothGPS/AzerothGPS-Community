"""Router.SetLegProvider: another addon's walk for a leg (a navigation mesh's walk inside a capital, asked
2026-11-17). The provider is asked first for every leg; its route is taken as it is, nil (or an error) is the Router's
own, "pending" the Router's own marked provisional. With none set, routes are exactly as before."""

import pytest

BRILL = (2254.0, 293.0)
TIRISFAL = (2050.0, 380.0)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    yield lua, ns
    ns.Router.SetLegProvider(None)


def _pts(r):
    return [r.pts[i] for i in range(1, len(r.pts) + 1)]


def test_no_provider_routes_as_before_and_a_nil_or_failing_one_too(game):
    lua, ns = game
    R = ns.Router
    R.SetLegProvider(None)
    own = _pts(R.Route(0, *BRILL, *TIRISFAL, lua.table()))
    assert len(own) >= 4
    asked = []
    R.SetLegProvider(lambda *a: asked.append(a[:5]) or None)
    assert _pts(R.Route(0, *BRILL, *TIRISFAL, lua.table())) == own
    assert asked and asked[0] == (0, *BRILL, *TIRISFAL)
    R.SetLegProvider(lua.eval("function() error('broken') end"))
    assert _pts(R.Route(0, *BRILL, *TIRISFAL, lua.table())) == own
    R.SetLegProvider(lua.eval("function() return { pts = { 1, 2 }, kinds = {} } end"))  # (one point: not a walk)
    assert _pts(R.Route(0, *BRILL, *TIRISFAL, lua.table())) == own
    R.SetLegProvider(None)
    assert R.LegProvider() is None


def test_a_providers_walk_is_the_leg_and_pending_marks_the_routers_own(game):
    lua, ns = game
    R = ns.Router
    mine = lua.eval("""function(cont, sx, sy, tx, ty, opts)
      if opts.tz == 99 then return "pending" end
      return { pts = { sx, sy, sx + 5, sy + 5, tx, ty }, kinds = { 0, 0 }, length = 10, road = 10, fz = { 1, 2, 3 } }
    end""")
    try:
        R.SetLegProvider(mine)
        r = R.Route(0, *BRILL, *TIRISFAL, lua.table())
        assert _pts(r) == [*BRILL, BRILL[0] + 5, BRILL[1] + 5, *TIRISFAL] and r.fz[3] == 3 and not r.pending
        r = R.Route(0, *BRILL, *TIRISFAL, lua.table(tz=99))
        assert r.pending and len(_pts(r)) >= 4 and _pts(r)[:2] == list(BRILL)
    finally:
        R.SetLegProvider(None)


def test_nav_walks_take_the_providers_leg(game):
    # (the route the player follows: its walking leg is the provider's, drawn and turned from its points)
    lua, ns = game
    R, N = ns.Router, ns.Nav
    mine = lua.eval("""function(cont, sx, sy, tx, ty, opts)
      local mx, my = (sx + tx) / 2 + 40, (sy + ty) / 2
      return { pts = { sx, sy, mx, my, tx, ty }, kinds = { 0, 0 }, length = 1, road = 1, mine = true }
    end""")
    was = lua.eval("AGPS_POS")
    try:
        lua.globals().AGPS_POS = lua.table(BRILL[0], BRILL[1], 0)
        R.SetLegProvider(mine)
        N.SetStops(lua.eval("{ { x = %f, y = %f, cont = 0, name = 'Spot' } }" % TIRISFAL), False, "red")
        N.Invalidate(True, True)
        r = N.Route(BRILL[0], BRILL[1], 0)
        part = r.parts[1]
        p = _pts(part)
        mx = (BRILL[0] + TIRISFAL[0]) / 2 + 40
        assert any(abs(p[k] - mx) < 0.5 for k in range(0, len(p), 2)), p
    finally:
        R.SetLegProvider(None)
        N.SetStops(lua.table(), False, "red")
        N.Invalidate(True, True)
        lua.globals().AGPS_POS = was
