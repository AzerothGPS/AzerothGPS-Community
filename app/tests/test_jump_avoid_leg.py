"""A jump's right-click avoids for its leg (item 26, Kooki3z 2026-11-24 on bbc4c8c4: "Avoid This Jump" changed
nothing; its 10 yd spot ban only moved the drop along the rim). A spell jump's: the leg's spell jumps, its plain drops
within Safe drop kept (the stop's `avoidJumps` "spell"); a plain jump's: all its jumps (`avoidJumps` "all", the walk
way). Only the leg to that stop; kept over a /reload with the stop, gone with it or with the route cleared."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_spell_jumping import (DADDIO_FAR, DADDIO_STOP, LONG, MAGE, WALK_ON_AIR, drops, feathers, safe_drop_60,  # noqa: F401
                                trip, world_grid)


def _straight(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


# (the mage's far-back trip, Slow Fall; and item 12's warrior, Walk on Air with Expert jumper: test_stand_in's)
WARRIOR_SANDS, WARRIOR_STOP = (-6915.0, -2848.0), (-6830.0, -1975.0)


@pytest.mark.parametrize("spell,a,b,expert", [(MAGE, DADDIO_FAR, DADDIO_STOP, False),
                                               (WALK_ON_AIR, WARRIOR_SANDS, WARRIOR_STOP, True)],
                         ids=["mage_slow_fall", "warrior_walk_on_air"])
def test_avoiding_spell_jumps_on_the_tanaris_trip_walks_round(game, trip, world_grid, safe_drop_60, spell, a, b,  # noqa: F811
                                                              expert):
    lua, ns = game
    N = ns.Nav
    ns.settings.gps.expertJumper = expert
    straight = _straight(a, b)
    r = trip("{}", spell, feathers(0 if spell == WALK_ON_AIR else 5), a=a, b=b)
    assert drops(ns, r) >= 1 and r.totalYards < straight * 1.3 + 120, r.totalYards  # (off the rim)
    assert N.AvoidLegJumps(1, "spell") is True and N.AvoidLegJumps(1, "spell") is False  # (once)
    trip.settle(24)
    r2 = N.route
    assert r2.totalYards > straight * 1.3 + 120, r2.totalYards  # (round by a way down, no spell jump)
    assert N.LegMaxDrop(N.stops[1]) == N.PlainSafeDrop()


def test_a_plain_drop_stays_with_spell_jumps_avoided_and_goes_with_all(game, trip):  # noqa: F811
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    was = st.safeDropYd
    try:
        st.safeDropYd = 60
        r = trip(LONG, feathers(0))
        assert drops(ns, r) == 1 and r.totalYards < 300, r.totalYards
        N.AvoidLegJumps(1, "spell")
        trip.settle()
        assert drops(ns, N.route) == 1 and N.route.totalYards < 300  # (a plain drop within Safe drop: kept)
        N.AvoidLegJumps(1, "all")
        trip.settle()
        assert drops(ns, N.route) == 0 and N.route.totalYards > 1000, N.route.totalYards
        assert N.AvoidLegJumps(1, "spell") is False and N.stops[1].avoidJumps == "all"  # ("all" kept)
        # (kept over a /reload with the stop)
        assert ns.CharDB().stops[1].avoidJumps == "all"
        N.Restore()
        assert N.stops[1].avoidJumps == "all"
        # (a new trip jumps again)
        r = trip(LONG, feathers(0))
        assert N.stops[1].avoidJumps is None and drops(ns, r) == 1
    finally:
        st.safeDropYd = was


def test_only_the_leg_to_that_stop(game, trip):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    trip(LONG, feathers(0))
    N.SetStops(lua.eval("{ { x = -1500.0, y = -2100.0, cont = 1, name = 'a' }, { x = -1450.0, y = -2150.0, cont = 1, name = 'b' } }"),
               False, "red")
    N.AvoidLegJumps(2, "all")
    assert N.LegMaxDrop(N.stops[1]) is None and N.LegMaxDrop(N.stops[2]) == N.AVOID_JUMPS_YD
