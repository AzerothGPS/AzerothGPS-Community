"""Stops in a closed hole of a floored city's grid (a house left out of Ironforge's cells, R.CaveNearDown): routed by the
city's own roads, not to the land roads far off and a straight line through the rock. Reported 2026-11-16: from the
Great Forge to Gerrig Bonegrip (NPC 2786) in The Forlorn Cavern, a staircase south of the forge and then straight
through the rock; from other spots round through the Mystic Ward and then a straight line. The whole addon
(gameharness)."""
import math

import pytest

pytest.importorskip("lupa.lua51")

GERRIG = (-4598.9, -1115.5, 505.0)  # (Gerrig Bonegrip's spot, in his house in The Forlorn Cavern)
FORGE = (-4760.0, -1108.0, 500.0)  # (the Great Forge)
FORGE_WEST = (-4795.0, -1105.0, 500.0)
# (Ironforge NPCs in such holes: Gerrig's neighbors, Jondor Steelbrow's and Lissyphus Finespindle's shops, Ginny
# Longberry's; from the forge each ended in a straight line through the rock before, Jondor's 173 yd over it)
HOLES = {
    "Gerrig Bonegrip": GERRIG,
    "Thistleheart": (-4604.1, -1117.5, 505.0),
    "Briarthorn": (-4599.1, -1111.7, 505.0),
    "Jondor Steelbrow": (-5016.2, -997.4, 504.0),
    "Lissyphus Finespindle": (-5033.4, -1146.1, 505.4),
    "Ginny Longberry": (-4715.9, -961.3, 505.4),
    "Pithwick": (-4963.6, -1014.2, 504.0),
}


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def _route(lua, ns, s, t):
    r = ns.Router.Route(0, s[0], s[1], t[0], t[1], lua.table_from({"z": s[2], "tz": t[2]}))
    assert r is not None and r.pts
    f = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    pts = list(zip(f[0::2], f[1::2]))
    return r, pts


def _open(lua, a, b):
    seg = lua.eval("function(ax, ay, bx, by) return AGPS_NS.Passability.SegmentCost(0, ax, ay, bx, by) end")
    return seg(a[0], a[1], b[0], b[1]) is not None


@pytest.mark.parametrize("start", [FORGE, FORGE_WEST], ids=["forge", "forge-west"])
def test_the_great_forge_to_gerrig_bonegrip_goes_by_the_forlorn_cavern(game, start):
    lua, ns = game
    r, pts = _route(lua, ns, start, GERRIG)
    last = math.dist(pts[-2], pts[-1])
    assert pts[-1] == pytest.approx(GERRIG[:2], abs=0.5)
    assert (r.blocked or 0) == 0
    # (the road graph reaches the cavern's node by his house, 24 yd off, in about 347 yd: not 814 round by the
    # Mystic Ward, not a last line from the land roads 280 yd off)
    assert r.length <= 347 + 24 + 60, r.length
    assert last <= 35, last
    assert _open(lua, pts[-2], pts[-1])


@pytest.mark.parametrize("name", list(HOLES))
def test_ironforge_npcs_in_closed_holes_end_on_an_open_last_step(game, name):
    lua, ns = game
    t = HOLES[name]
    r, pts = _route(lua, ns, FORGE, t)
    last = math.dist(pts[-2], pts[-1])
    assert (r.blocked or 0) == 0
    assert r.length <= 600, r.length  # (not round the city: Ginny Longberry's was 1002 yd, Thistleheart's 811)
    # (40 before Kooki3z's walks into Pithwick's shop, issue #862: Jondor's route by them is 15 yd shorter in all and
    # comes to his shop from the south, 43 yd over open floor)
    assert last <= 45, last
    assert _open(lua, pts[-2], pts[-1])


def test_pithwick_is_reached_by_kooki3zs_walk_into_his_shop(game):
    # (issue #862: walked in game up into his shop, its Stairs walk on the shop's floor at 503.9, not the landing 510.5
    # over it; the route ended 21 yd off him before)
    lua, ns = game
    r, pts = _route(lua, ns, FORGE, HOLES["Pithwick"])
    assert math.dist(pts[-2], pts[-1]) <= 5
    assert all(abs(r.fz[i] - 504) <= 2 for i in range(len(pts) - 2, len(pts) + 1))


THANES_DOOR = (-4822.27, -932.42, 399.04)  # (the Hall of Thanes' way in, under the city: test_instances.py's)


@pytest.mark.parametrize("start", [FORGE, FORGE_WEST], ids=["forge", "forge-west"])
def test_the_hall_of_thanes_door_is_reached_down_kooki3zs_walks(game, start):
    # (issue #918: walked in game from the halls at 502 down to the Hall of Thanes' floor at 399; before, the route
    # stayed on the streets at 502 and its last step went to the door 100 yd under them)
    lua, ns = game
    r, pts = _route(lua, ns, start, THANES_DOOR)
    assert (r.blocked or 0) == 0
    assert r.length <= 700, r.length
    assert math.dist(pts[-2], pts[-1]) <= 10  # (the walk ends by the portal)
    assert all(abs(r.fz[i] - THANES_DOOR[2]) <= 3 for i in range(len(pts) - 2, len(pts) + 1))


def test_cave_near_down_only_under_the_citys_floor(game):
    lua, ns = game
    R = ns.Router
    x, y, z = GERRIG
    assert R.CaveDown(0, x, y, None, z) is False  # (the gap rule finds none: his house is left out of the cells)
    assert R.CaveNearDown(0, x, y, z) is True
    assert R.CaveNearDown(0, x, y, 650.0) is False  # (the mountain over the city: up)
    assert R.CaveNearDown(0, x, y, None) is False
    assert R.CaveNearDown(0, -5600.0, -480.0, 400.0) is False  # (Dun Morogh's snow, nowhere near the city)
