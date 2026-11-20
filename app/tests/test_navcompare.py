"""navcompare.py (a dev tool: the city roads against our Recast meshes, asked 2026-11-18): on/off the mesh by height,
the runs off it, the sources left out, and the ground no road reaches. Synthetic meshes and graphs: no client needed."""

from azerothgps import navcompare as C
from azerothgps import navmesh as N


def _tile(tx, x0, z=1.0, w=10.0):
    t = N.Tile.__new__(N.Tile)
    t.tx, t.ty, t.climb = tx, 0, 1.0
    t.verts = [(x0, 0.0, z), (x0 + w, 0.0, z), (x0 + w, 10.0, z), (x0, 10.0, z)]
    t.polys = [{"verts": [0, 1, 2, 3], "neis": [0, 0, 0, 0], "flags": 1, "area": 11, "type": 0}]
    t.bmin, t.bmax = (x0, 0.0, z), (x0 + w, 10.0, z)
    return t


class Graph:
    """The Router's graph as navcompare reads it: e[id] = {a, b, length, source, x1, y1, ...} (1-based), heights by node."""

    def __init__(self, edges, nz=None, z=None):
        self.e = {i + 1: {k + 1: v for k, v in enumerate(e)} for i, e in enumerate(edges)}
        self.nz = nz
        self.z = z


def test_a_road_over_a_gap_in_the_mesh_is_a_run_off_it():
    # (two floors 0-10 and 20-30 along x; a road from 1 to 29 at y 5: 10-20 is over no floor)
    tiles = {(0, 0): _tile(0, 0.0), (2, 0): _tile(2, 20.0)}
    g = Graph([(1, 2, 28.0, 0, 1.0, 5.0, 29.0, 5.0)], nz={1: 1.0, 2: 1.0})
    res = C.compare("Test", 0, None, tiles, g, log=lambda *a: None)
    assert res["samples"] > 25
    assert len(res["runs"]) == 1
    run = res["runs"][0]
    assert 6 <= run["yards"] <= 9  # (10 to 20, less ON_XY at each side)
    assert run["why"].startswith("no walkable floor")


def test_a_road_on_another_floor_is_off_and_says_which_way():
    tiles = {(0, 0): _tile(0, 0.0, z=20.0)}
    g = Graph([(1, 2, 8.0, 0, 1.0, 5.0, 9.0, 5.0)], nz={1: 1.0, 2: 1.0})
    res = C.compare("Test", 0, None, tiles, g, log=lambda *a: None)
    assert res["runs"] and "19 yd over the road" in res["runs"][0]["why"]
    # (the same road with no height of its own, a land road: any floor under it will do)
    g2 = Graph([(1, 2, 8.0, 0, 1.0, 5.0, 9.0, 5.0)], nz={1: 0.0, 2: 0.0})
    assert C.compare("Test", 0, None, tiles, g2, log=lambda *a: None)["off"] == 0


def test_swims_lifts_and_drops_and_no_height_markers_are_left_out():
    tiles = {(0, 0): _tile(0, 0.0)}
    g = Graph([(1, 2, 8.0, 7, 1.0, 5.0, 9.0, 5.0), (1, 2, 8.0, 5, 1.0, 5.0, 9.0, 5.0),
               (1, 2, 8.0, 4, 1.0, 5.0, 9.0, 5.0), (3, 4, 8.0, 0, 1.0, 5.0, 9.0, 5.0)],
              nz={1: 50.0, 2: 50.0, 3: -10000.0, 4: -10000.0})
    res = C.compare("Test", 0, None, tiles, g, log=lambda *a: None)
    assert res["roads"] == 1 and res["off"] == 0


def test_ground_far_from_every_road_is_a_gap_and_only_the_citys_own():
    # (a big floor 0-100 x 0-10 and a road only at its west end)
    tiles = {(0, 0): _tile(0, 0.0, w=100.0)}
    # (the poly is one: split it so its parts' middles can be far from the road)
    t = tiles[(0, 0)]
    t.verts = [(float(x), y, 1.0) for x in range(0, 101, 10) for y in (0.0, 10.0)]
    # (each joined to the next: its right edge the next one's left, neis 1-based)
    t.polys = [{"verts": [2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1],
                "neis": [0, i + 2 if i < 9 else 0, 0, i if i > 0 else 0], "flags": 1, "area": 11, "type": 0}
               for i in range(10)]
    g = Graph([(1, 2, 8.0, 0, 1.0, 5.0, 9.0, 5.0)], nz={1: 1.0, 2: 1.0})
    places = [("Trainer", 80.0, 5.0)]
    res = C.compare("Test", 0, None, tiles, g, places, log=lambda *a: None)
    assert res["gaps"] and res["gaps"][0]["area"] >= C.GAP_MIN_AREA
    assert "Trainer" in res["gaps"][0]["places"]
    # (with only the west end the city's own ground, none)
    res2 = C.compare("Test", 0, None, tiles, g, places, log=lambda *a: None, inside=lambda x, y: x < 30)
    assert not res2["gaps"]


def test_the_report_writes(tmp_path):
    tiles = {(0, 0): _tile(0, 0.0), (2, 0): _tile(2, 20.0)}
    g = Graph([(1, 2, 28.0, 0, 1.0, 5.0, 29.0, 5.0)], nz={1: 1.0, 2: 1.0})
    res = C.compare("Test", 0, None, tiles, g, log=lambda *a: None)
    index = C.PolyIndex(__import__("azerothgps.recastmesh", fromlist=["x"]).RecastMesh(tiles, 0))
    C.render(res, index, C.road_samples(g, index.box), tmp_path / "t.png")
    md = C.report_md(res, "t.png")
    assert (tmp_path / "t.png").stat().st_size > 0 and "Runs off the mesh" in md
