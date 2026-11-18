"""The navmesh tools (navmesh.py, recastmesh.py): dev tools only, nothing ships. Their geometry offline: the funnel's
line through portals, border edges joined across tiles, and the developer export (asked 2026-11-17)."""

import math

import numpy as np

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


def test_undercitys_mesh_is_a_source_of_its_own_on_its_level():
    # (asked 2026-11-17: Undercity's mesh too; it isn't one of the capitals: its floors are a level of their own)
    from azerothgps.capitals import CAPITALS
    from azerothgps.cities import UNDERCITY_ID

    src = {name: (cont, level) for name, cont, level, _fn in RM.sources()}
    assert src["Undercity"] == (0, UNDERCITY_ID)
    assert all(src[cap.name] == (cap.cont, None) for cap in CAPITALS)


def test_undercitys_model_is_placed_as_its_level_is_and_its_canals_beds_are_not_walked():
    # (its model's frame turned by yaw + 180 about the up axis, as cities.undercity places it; heights the model's +
    # the placement's: the game's)
    T = np.array([[[1.0, 0.0, -125.0], [0.0, 2.0, -125.0], [0.0, 0.0, -125.0]]])
    W = RM.to_world(T, 100.0, 200.0, 62.5, 90.0)
    assert np.allclose(W[0, 0], (100.0, 199.0, -62.5)) and np.allclose(W[0, 1], (102.0, 200.0, -62.5))
    # (a canal: a liquid tile over (0, 0)-(4, 4) at -124; a floor 3 yd under it swum, one 0.5 under waded, one beside walked)
    tri = lambda x, y, z: [[x, y, z], [x + 1, y, z], [x, y + 1, z]]  # noqa: E731
    floors = np.array([tri(1, 1, -127.0), tri(1, 1, -124.5), tri(6, 1, -127.0)])
    assert RM.under_liquid(floors, [((0.0, 0.0, 4.0, 4.0), -124.0)]).tolist() == [True, False, False]


def test_a_level_mesh_is_exported_with_its_level(tmp_path):
    tiles = {(0, 0): _square_tile(0, 0.0), (1, 0): _square_tile(1, 10.0)}
    out = tmp_path / "NavMeshData.lua"
    RM.export_lua({"Test": (0, tiles), "Under": (0, tiles, 10001)}, out, log=lambda *a: None)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert any(ln.startswith("AzerothGPSDevNav['Under'] = { cont = 0, level = 10001, box") for ln in lines)
    assert any(ln.startswith("AzerothGPSDevNav['Test'] = { cont = 0, box") for ln in lines)


def test_only_builds_the_cities_asked_and_keeps_the_others_meshes(tmp_path, monkeypatch):
    # (`agps navmesh build --only Undercity`: the five capitals' meshes already built stay in NavMeshData.lua)
    from azerothgps import cli

    monkeypatch.setenv("AZEROTHGPS_DATA", str(tmp_path))
    monkeypatch.setattr(cli, "DATA", tmp_path)
    (tmp_path / "tools").mkdir()
    RM.tool().write_bytes(b"")
    built = []
    tiles = {(0, 0): _square_tile(0, 0.0)}

    def triangles(name):
        def fn(cd, log):
            built.append(name)
            return None, None, None
        return fn
    monkeypatch.setattr(RM, "sources", lambda: [("Old Town", 1, None, triangles("Old Town")),
                                                ("Under", 0, 10001, triangles("Under"))])
    monkeypatch.setattr(RM, "run_recast", lambda T, log=print, walk=None: tiles)
    monkeypatch.setattr(cli, "_client", lambda args: None)
    monkeypatch.setattr(cli, "_dev_addon", lambda: None)
    RM.save(tiles, RM.mesh_path("Old Town"))
    args = type("A", (), {"what": "build", "only": ["under"], "rebuild": True})()
    assert cli.cmd_navmesh(args) == 0
    assert built == ["Under"]
    text = (tmp_path / "navmesh" / "NavMeshData.lua").read_text(encoding="utf-8")
    assert "AzerothGPSDevNav['Old Town']" in text and "AzerothGPSDevNav['Under'] = { cont = 0, level = 10001," in text
