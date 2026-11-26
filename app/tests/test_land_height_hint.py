"""The stop's height against the player's out on the land (Kooki3z 2026-11-20: "since we know on routing height changes,
why can't we say when we get closer to the destination how much higher/lower it is?"): Nav.LandHeightHint, from the
map's ground heights."""

import pytest


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def test_near_the_stop_it_says_how_far_above_or_below_it_is(game):
    lua, ns = game
    N = ns.Nav
    lua.execute("""
      AGPS_GPH = AGPS_NS.Ground.PointHeight
      AGPS_NS.Ground.PointHeight = function(_, x, y) return AGPS_GROUND(x, y) end
      AGPS_GROUND = function(x) if x > 2280 then return 40 end return 10 end
      -- (open land: no road with a height by the player; by Brill's buildings their inside roads tell the floor,
      -- Nav.PlayerHeightNear)
      AGPS_HN = AGPS_NS.Router.HeightsNear
      AGPS_NS.Router.HeightsNear = function() return {} end
      AGPS_IB = AGPS_NS.Nav.InBuilding
      AGPS_NS.Nav.InBuilding = function() return nil end
    """)
    saved_dest, saved_route = N.dest, N.route
    try:
        N.route = None
        N.dest = lua.table(x=2290.0, y=293.0, cont=0, name="the stop")
        way, yd = N.HeightHint(2254.0, 293.0, 0)
        assert way == "up" and yd == pytest.approx(30)
        assert "Above you" in str(N.HeightText(2254.0, 293.0, 0))
        # the stop below: down
        lua.execute("AGPS_GROUND = function(x) if x > 2280 then return -5 end return 10 end")
        assert N.HeightHint(2254.0, 293.0, 0)[0] == "down"
        # a few yards apart (the ground's bumps): nothing said
        lua.execute("AGPS_GROUND = function(x) if x > 2280 then return 15 end return 10 end")
        assert N.HeightHint(2254.0, 293.0, 0) is None
        # far from the stop: nothing said
        lua.execute("AGPS_GROUND = function(x) if x > 2280 then return 40 end return 10 end")
        assert N.HeightHint(2254.0 - 200, 293.0, 0) is None
        # no ground data (a cave, a building): nothing said
        lua.execute("AGPS_GROUND = function() return false end")
        assert N.HeightHint(2254.0, 293.0, 0) is None
        # the stop's own height wins over the ground there
        lua.execute("AGPS_GROUND = function() return 10 end")
        N.dest = lua.table(x=2290.0, y=293.0, cont=0, name="the stop", z=60.0)
        way, yd = N.HeightHint(2254.0, 293.0, 0)
        assert way == "up" and yd == pytest.approx(50)
    finally:
        N.dest, N.route = saved_dest, saved_route
        lua.execute("AGPS_NS.Ground.PointHeight = AGPS_GPH AGPS_NS.Router.HeightsNear = AGPS_HN "
                    "AGPS_NS.Nav.InBuilding = AGPS_IB")
