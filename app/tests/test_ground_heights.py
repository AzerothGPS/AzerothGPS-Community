"""The map's ground heights baked from the client's terrain (Data/Heights.lua, heights.py; 1.3.10, issue #685): the
grids' strings decode the same in Python and in the addon (Ground.lua), the shipped grid reads the same both ways,
matches the pipeline's terrain_at within the grid's own error (with the client), is decoded only while the road or wall
tools are open, a tile at a time, and a road drawn takes the ground's height at each point (none in a building)."""

import math
import random
import re
from pathlib import Path

import pytest

from azerothgps import heights as HT

lupa = pytest.importorskip("lupa")

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
TILE = 1600 / 3


def ground_lua():
    lua = lupa.LuaRuntime()
    ns = lua.table()
    lua.eval("function(src, ns) assert(load(src, '@Ground.lua'))('AzerothGPS', ns) end")(
        (ADDON / "Ground.lua").read_text(encoding="utf-8"), ns)
    return lua, ns


def shipped():
    """Data/Heights.lua read back: (n, {cont: {(tx, ty): (ground, water)}})."""
    text = (ADDON / "Data" / "Heights.lua").read_text(encoding="utf-8")
    n = int(re.search(r"ns\.Heights = \{ n = (\d+)", text).group(1))
    out, cur, water = {}, None, False
    for line in text.splitlines():
        m = re.match(r"ns\.Heights(\.water)?\[(\d+)\] = \{", line)
        if m:
            water, cur = bool(m.group(1)), out.setdefault(int(m.group(2)), {})
            continue
        m = re.match(r'  \[(\d+)\] = "(.*)",$', line)
        if m and cur is not None:
            key = int(m.group(1))
            g, w = cur.get((key // 64, key % 64), (None, None))
            cur[(key // 64, key % 64)] = (g, m.group(2)) if water else (m.group(2), w)
    return n, out


def random_grid(rng, n, holes=True):
    g, z = [], rng.uniform(-50, 300)
    for i in range(n):
        row = []
        for j in range(n):
            z += rng.choice([0, 0, 0, 1, -1, 2, -3, 7]) + rng.choice([0] * 40 + [90, -200, 1500])
            z = max(-600.0, min(1400.0, z))
            row.append(None if holes and rng.random() < 0.05 else int(round(z)))
        g.append(row)
    if holes:  # (a run of none, and a flat stretch: the run codes)
        for j in range(n):
            g[2][j] = None
        g[4] = [g[4][0]] * n
    return g


def test_a_grid_encodes_and_decodes_back_in_python_and_in_the_addon():
    rng = random.Random(7)
    lua, ns = ground_lua()
    for n in (5, 33, 65):
        for holes in (True, False):
            g = random_grid(rng, n, holes)
            s = HT.encode(g)
            assert all(35 <= ord(c) <= 126 and c != "\\" for c in s)
            assert HT.decode(s, n) == g
            got = ns.Ground.Decode(s, n)
            flat = [got[k] for k in range(1, n * n + 1)]
            assert flat == [False if v is None else v for row in g for v in row]
    # (a string cut short: no grid)
    assert ns.Ground.Decode(HT.encode(random_grid(rng, 9))[:-3], 9) is None


def test_the_shipped_grid_reads_the_same_in_the_addon_and_is_decoded_only_with_the_tools_open():
    n, tiles = shipped()
    assert n in (32, 64) and set(tiles) >= {0, 1}
    lua, ns = ground_lua()
    lua.eval("function(src, ns) assert(load(src, '@Heights.lua'))('AzerothGPS', ns) end")(
        (ADDON / "Data" / "Heights.lua").read_text(encoding="utf-8"), ns)
    GD = ns.Ground
    # the tools closed: nothing read, nothing decoded
    ns.GPS = lua.table(roadMode=False, wallMode=False)
    assert GD.At(1, 1400.0, -4400.0) is None and GD.decoded == 0
    ns.GPS.roadMode = True
    rng = random.Random(3)
    checked = 0
    for cont in (0, 1):
        keys = sorted(tiles[cont])
        for _ in range(150):
            tx, ty = rng.choice(keys)
            x = (32 - ty - rng.random()) * TILE
            y = (32 - tx - rng.random()) * TILE
            want = HT.grid_at(tiles[cont], n, x, y)
            got = GD.At(cont, x, y)
            if want is None:
                assert got is None
            else:
                assert got is not None and abs(got - want) < 1e-6
                checked += 1
            w = HT.grid_at(tiles[cont], n, x, y, water=True)
            gw = GD.At(cont, x, y, True)
            assert (w is None and gw is None) or abs(gw - w) < 1e-6
    assert checked > 200
    # (a tile at a time, the oldest let go past CACHE_TILES; let go when the tools close)
    assert GD.decoded > GD.CACHE_TILES
    # off the map: none
    assert GD.At(1, 40000.0, 40000.0) is None
    # Razor Hill (about 16 yd up) and Goldshire (about 57)
    assert abs(GD.At(1, 340.0, -4690.0) - 16) < 3 and abs(GD.At(0, -9460.0, 60.0) - 57) < 3


def test_the_shipped_grid_matches_the_pipelines_terrain_within_the_grids_error():
    from azerothgps.cli import DATA, DEFAULT_WOW, PRODUCT

    if not (DEFAULT_WOW / ".build.info").exists() or not (DATA / "ref" / "listfile.csv").exists():
        pytest.skip("needs the local WoW install and data/ref (listfile + dbd)")
    from azerothgps.caves import Ground
    from azerothgps.extract.spike import ClientData
    from azerothgps.roads.recorded import terrain_at

    try:
        cd = ClientData(DEFAULT_WOW, PRODUCT, DATA / "ref")
    except Exception as ex:  # (a client this reader can't open)
        pytest.skip(f"the client doesn't open: {ex!r}")
    n, tiles = shipped()
    q = TILE / n
    rng = random.Random(11)
    for cont in (0, 1):
        ground = Ground(cd, cont)
        keys = sorted(tiles[cont])
        errs = []
        for _ in range(120):
            tx, ty = rng.choice(keys)
            x = (32 - ty - rng.random()) * TILE
            y = (32 - tx - rng.random()) * TILE
            got = HT.grid_at(tiles[cont], n, x, y)
            if got is None:
                continue
            # the grid's error there: the terrain's own spread over the cell round it (and a half for the rounding)
            i, j = math.floor(((32 - ty) * TILE - x) / q), math.floor(((32 - tx) * TILE - y) / q)
            xs = [(32 - ty) * TILE - (i + a / 4) * q for a in range(5) for _b in range(5)]
            ys = [(32 - tx) * TILE - (j + b / 4) * q for _a in range(5) for b in range(5)]
            cell = terrain_at(ground, xs, ys)
            want = terrain_at(ground, [x], [y])[0]
            if not (math.isfinite(want) and all(math.isfinite(v) for v in cell)):
                continue
            spread = max(cell) - min(cell)
            assert abs(got - want) <= spread + 0.6, (cont, x, y, got, want, spread)
            errs.append(abs(got - want))
        assert len(errs) > 60
        assert sorted(errs)[len(errs) // 2] < 2.0  # (most of the map: within a couple of yards)
        # at the grid's own points: the terrain's height, rounded
        for _ in range(40):
            tx, ty = rng.choice(keys)
            i, j = rng.randrange(n + 1), rng.randrange(n + 1)
            x, y = (32 - ty) * TILE - i * q, (32 - tx) * TILE - j * q
            got = HT.grid_at(tiles[cont], n, min(x, (32 - ty) * TILE - 1e-6), min(y, (32 - tx) * TILE - 1e-6))
            want = terrain_at(ground, [x], [y])[0]
            if got is not None and math.isfinite(want):
                assert abs(got - want) <= 0.6 + (0.2 if i == 0 or j == 0 else 0), (cont, x, y, got, want)


def test_a_drawn_roads_points_take_the_grids_height_but_in_a_building():
    lua, ns = ground_lua()
    # a tile of its own: ground at 100 + the row (south) number, a hole in its middle
    n = 4
    g = [[100 + i for _j in range(n + 1)] for i in range(n + 1)]
    g[2][2] = None
    ns.Heights = lua.table(n=n, cell=TILE / n, water=lua.table())
    ns.Heights[5] = lua.table()
    ns.Heights[5][30 * 64 + 30] = HT.encode(g)
    ns.GPS = lua.table(roadMode=True)
    x0, y0 = (32 - 30) * TILE, (32 - 30) * TILE  # (the tile's north-west corner)
    q = TILE / n
    ns.Nav = lua.eval("{ InBuilding = function(level, x, y) return x < %f end }" % (x0 - 3 * q))
    pts = lua.table(x0 - 10, y0 - 10, x0 - 2 * q, y0 - 2 * q, x0 - 2.5 * q, y0 - 10, x0 - 3 * q - 1, y0 - 3 * q)
    hs = ns.Ground.RoadHeights(5, pts)
    got = [hs[k] for k in range(1, 5)]
    assert got[0] == pytest.approx(100 + 10 / q, abs=0.06)
    assert got[1] is False  # (over the hole)
    assert got[2] == pytest.approx(102.5, abs=0.06)
    assert got[3] is False  # (in a building: the import works it out)
    # no grid for the level (a city's own): none at all
    assert ns.Ground.RoadHeights(10001, pts) is None
