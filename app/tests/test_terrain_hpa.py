"""Searching the terrain by blocks (Data/TerrainHPA.lua, app/azerothgps/hpa.py; Passability.FindPath)."""

import math
import re

import pytest

from azerothgps import hpa
from test_addon_lua import ADDON, env, load  # noqa: F401 (fixtures)


@pytest.fixture
def terrain(env):
    lua, ns = env
    ns.db = lua.eval("{}")
    # (the blocks come with the terrain; and the buildings, as the blocks were prepared with them: without them, the
    # blocks worked out again around a wall walked through buildings and came out shorter than the prepared ones)
    load(lua, ns, "Data/Terrain.lua", "Data/Buildings.lua", "Passability.lua")
    return lua, ns, ns.Passability


def cost_of(P, *trip):
    r = P.FindPath(*trip)
    return (r[0], r[1]) if isinstance(r, tuple) else (None, None)


def test_the_blocks_are_prepared_from_the_data_as_it_is():
    lua, ns = hpa.runtime()
    text = (ADDON / "Data" / "TerrainHPA.lua").read_text(encoding="utf-8")
    have = dict(re.findall(r'ns\.TerrainHPA\[(\d+)\] = \{[^\n]*?stamp = "([0-9a-f]+)"', text))
    for c in hpa.CONTS:
        assert have.get(str(c)) == hpa.stamp(lua, ns, c), "stale: run agps terrain-hpa (or install-addon)"


@pytest.mark.parametrize("trip", [
    (0, -11515.8, 467.0, -9992.1, 224.3),  # across Duskwood
    (0, -9453.3, -40.9, -11124.8, 177.7),  # Elwynn Forest into Westfall
])
def test_long_walks_by_blocks_within_a_small_budget(terrain, trip):
    lua, ns, P = terrain
    full, _ = cost_of(P, *trip)  # (cell by cell, the whole budget)
    P.PATH_MAX_EXPANSIONS = 3000
    P.HPA_MIN_CELLS = 10 ** 9
    P.ClearCache()
    assert cost_of(P, *trip)[0] is None  # cell by cell, it doesn't get there on this budget
    P.HPA_MIN_CELLS = 40
    P.ClearCache()
    by_blocks, pts = cost_of(P, *trip)
    assert by_blocks == pytest.approx(full, rel=0.03)
    assert (pts[1], pts[2]) == (trip[1], trip[2]) and (pts[len(pts) - 1], pts[len(pts)]) == (trip[3], trip[4])


def test_no_way_through_agrees(terrain):
    lua, ns, P = terrain
    # (Loch Modan's mountains, where a walk on foot got stuck: none within the search's box. Alterac's, here before,
    # has one since the sea over a steep seabed is swum: issue #271)
    trip = (0, -5474.1, -2955.5, -4957.7, -1182.6)
    P.HPA_MIN_CELLS = 10 ** 9
    assert cost_of(P, *trip)[0] is None
    P.HPA_MIN_CELLS = 40
    P.ClearCache()
    assert cost_of(P, *trip)[0] is None


def test_a_wall_drawn_in_game_changes_its_blocks(terrain):
    lua, ns, P = terrain
    trip = (0, -9453.3, -40.9, -11124.8, 177.7)
    P.PATH_MAX_EXPANSIONS = 3000  # (by blocks only: cell by cell doesn't get there on this)
    before, way = cost_of(P, *trip)
    # a wall across the way, halfway along the walk found (not the straight line between its ends: the walk goes
    # round buildings and hills, and a wall off it changes nothing)
    flat = [way[i] for i in range(1, len(way) + 1)]
    pts = list(zip(flat[0::2], flat[1::2]))
    legs = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    half, k = sum(legs) / 2, 0
    while half > legs[k]:
        half, k = half - legs[k], k + 1
    (ax, ay), (bx, by) = pts[k], pts[k + 1]
    t = half / legs[k]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    mx, my, px, py = ax + dx * t, ay + dy * t, -dy / n, dx / n
    wall = [mx - px * 150, my - py * 150, mx + px * 150, my + py * 150]
    ns.db.tracks = lua.eval("{}")
    ns.db.tracks[1] = lua.table(continent=0, op="wall", time=1, pts=lua.table(*wall))
    P.RefreshWalls()
    after, pts = cost_of(P, *trip)
    assert after is not None
    # the walk before crossed the wall; the one after doesn't (its blocks were worked out again). Not "longer":
    # searching by blocks, a wall splitting a block's opening in two gives each part its own way through, and that
    # can find a slightly shorter way than before (2026-10-06, with more of the buildings blocked)
    crossed = any(P.CrossesWall(0, flat[i], flat[i + 1], flat[i + 2], flat[i + 3]) for i in range(0, len(flat) - 2, 2))
    assert crossed
    flat = [pts[i] for i in range(1, len(pts) + 1)]
    for i in range(0, len(flat) - 2, 2):
        assert not P.CrossesWall(0, flat[i], flat[i + 1], flat[i + 2], flat[i + 3])
