"""Off-road walks weighed as the Router weighs a leg (1.3.14's terrain grid, PR #850): a walk prices the zones too high
for the player, and a walk from closed ground isn't joined onto one searched from open ground beside it."""

import math

import pytest

pytest.importorskip("lupa.lua51")


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start

    return start()


def as_player(lua, ns, faction, level):
    lua.execute(f'AGPS_LEVEL = {level}; UnitLevel = function() return {level} end; '
                f'UnitFactionGroup = function() return "{faction}", "{faction}" end')
    ns.CharDB().faction = faction
    ns.Router.WallsChanged()
    ns.Router.Reset()


def zone_yards(ns, r):
    R = ns.Router
    out = {}
    for i in range(1, len(r.pts) // 2):
        x1, y1, x2, y2 = r.pts[2 * i - 1], r.pts[2 * i], r.pts[2 * i + 1], r.pts[2 * i + 2]
        zy = R.ZoneYards(0, x1, y1, x2, y2)
        for z, yd in zy.items():
            name = ns.Maps[z].name if ns.Maps[z] else z
            out[name] = out.get(name, 0) + yd
    return out


def test_a_level_20_walk_to_lights_hope_keeps_out_of_alterac(game):
    # (route-quality, A20 the Dawning Isles to Light's Hope Chapel) the grid opens Silverpine's hills into the Alterac
    # Mountains; the walk, searched by yards alone, took 2k yd of Alterac (too high at 20), 800 yd shorter and 556 s
    # slower than by Tirisfal. Its steps there cost Router.LEVEL_FACTOR now, as a leg's do
    lua, ns = game
    as_player(lua, ns, "Alliance", 20)
    r = ns.Router.Route(0, 950.0, 216.7, 2250.0, -5350.0, lua.table(offroad=True))
    assert r is not None and not r.noWay
    assert zone_yards(ns, r).get("Alterac Mountains", 0) < 200
    # (at 60 nothing's too high: the shorter walk through Alterac)
    as_player(lua, ns, "Alliance", 60)
    r60 = ns.Router.Route(0, 950.0, 216.7, 2250.0, -5350.0, lua.table(offroad=True))
    assert r60.length < r.length


def test_a_walk_from_closed_ground_isnt_joined_onto_one_from_open_ground_beside_it(game):
    # (route-quality, A30 Under Attack to Moonbrook) the player stands on closed ground in the Burning Steppes; a walk to
    # Morgan's Vigil's flight master searched from open ground 23 yd off goes round (no start slack there), and the
    # player's own walk joined onto it: 1,125 yd for its own 673
    lua, ns = game
    as_player(lua, ns, "Alliance", 30)
    R, P = ns.Router, ns.Passability
    start, beside, stop = (-7741.2, -2722.2), (-7750.0, -2700.0), (-8365.0, -2738.0)
    assert P.At(0, *start) == 2 and math.dist(start, beside) < R.WALK_REUSE_YD
    R.Route(0, *beside, *stop, lua.table(offroad=True, transient=True))
    r = R.Route(0, *start, *stop, lua.table(offroad=True, transient=True))
    assert r.length < 720
