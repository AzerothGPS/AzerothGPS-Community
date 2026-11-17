"""The navmesh tools (navmesh.py, recastmesh.py): dev tools only, nothing ships. Their geometry offline: the funnel's
line through portals, border edges joined across tiles, and the developer export (asked 2026-11-17)."""

import math

from azerothgps import navmesh as N
from azerothgps import recastmesh as RM


def test_the_funnel_goes_straight_through_portals_in_a_row():
    portals = [((0.0, 10.0, 0.0), (10.0, 10.0, 0.0)), ((0.0, 20.0, 0.0), (10.0, 20.0, 0.0))]
    pts = N._funnel((5.0, 0.0, 0.0), (5.0, 30.0, 0.0), portals)
    assert [(p[0], p[1]) for p in pts] == [(5.0, 0.0), (5.0, 30.0)]


def test_the_funnel_turns_at_a_portals_corner():
    # (a corridor that bends: the line touches the inner corner, (10, 10))
    portals = [((10.0, 10.0, 0.0), (0.0, 10.0, 0.0)), ((10.0, 10.0, 0.0), (10.0, 20.0, 0.0))]
    pts = N._funnel((2.0, 2.0, 0.0), (20.0, 15.0, 0.0), portals)
    assert any(math.dist((p[0], p[1]), (10.0, 10.0)) < 1e-6 for p in pts[1:-1])


def test_border_edges_of_neighbor_tiles_join_where_they_overlap_at_one_height():
    seg = N._overlap((10.0, 0.0, 5.0), (10.0, 8.0, 5.0), (10.0, 4.0, 5.5), (10.0, 12.0, 5.5))
    assert seg and (seg[0][1], seg[1][1]) == (4.0, 8.0)
    assert N._overlap((10.0, 0.0, 5.0), (10.0, 8.0, 5.0), (10.0, 4.0, 15.0), (10.0, 12.0, 15.0)) is None  # (a floor over)


def _square_tile(tx, x0):
    t = N.Tile.__new__(N.Tile)
    t.tx, t.ty, t.climb = tx, 0, 1.0
    t.verts = [(x0, 0.0, 1.0), (x0 + 10, 0.0, 1.0), (x0 + 10, 10.0, 1.0), (x0, 10.0, 1.0)]
    # (the edge on the other tile's side a portal: 0x8000)
    side = 1 if tx == 0 else 3
    neis = [0, 0, 0, 0]
    neis[side] = 0x8000
    t.polys = [{"verts": [0, 1, 2, 3], "neis": neis, "flags": 1, "area": 11, "type": 0}]
    t.bmin, t.bmax = (x0, 0.0, 1.0), (x0 + 10, 10.0, 1.0)
    return t


def test_a_route_crosses_from_tile_to_tile_and_the_export_is_strings(tmp_path):
    tiles = {(0, 0): _square_tile(0, 0.0), (1, 0): _square_tile(1, 10.0)}
    m = RM.RecastMesh(tiles, 0)
    r = m.path(2.0, 5.0, 1.0, 18.0, 5.0, 1.0)
    assert r["found"] and abs(r["yards"] - 16.0) < 1e-6
    out = tmp_path / "NavMeshData.lua"
    RM.export_lua({"Test": (0, tiles)}, out, log=lambda *a: None)
    text = out.read_text(encoding="utf-8")
    assert 'AzerothGPSDevNav["Test"]' in text or "AzerothGPSDevNav['Test']" in text
    assert 'ns = "' in text and 'ps = "' in text  # (strings: Lua 5.1's 262143 constants a function)
