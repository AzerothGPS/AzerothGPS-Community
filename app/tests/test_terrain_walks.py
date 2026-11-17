"""The terrain grid against walks on foot (test walks of Shortest Path Forever's shorter lines,
issue #271): the ground a walk crossed is open, and where a walk got stuck stays closed."""

import struct

import numpy as np
import pytest

from azerothgps.roads import terrain as T
from test_addon_lua import env, load  # noqa: F401 (fixtures)


@pytest.fixture
def grid(env):
    lua, ns = env
    ns.db = lua.eval("{}")
    load(lua, ns, "Data/Terrain.lua", "Passability.lua")
    return ns.Passability


def test_the_sea_over_a_steep_seabed_is_swum_from_alterac_to_silverpine(grid):
    # (spf-53, walked 2026-11-13, arrived: 1,815 yd, 400 of them swum over a seabed down to 500 yd deep and steeper
    # than 50 degrees, which closed it; our route went 4.2k yd round by the roads)
    P = grid
    for x, y in [(-1081.75, 589.75), (-1118.75, 646.5), (-1155.75, 703.25), (-1190.5, 756.75), (-1225.5, 812.0)]:
        assert P.At(0, x, y) == 1, (x, y)
    P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS = 400000, 900 * 900
    r = P.FindPath(0, -90.2, -239.4, -1289.0, 913.3)
    assert isinstance(r, tuple), "no walk found"
    assert r[0] < 2600  # (the walk's cost, swimming weighed: 2.9k yd before)


@pytest.mark.parametrize("cont, x, y", [
    (0, -4901.25, -2323.75),  # spf-11, Loch Modan
    (0, 1736.0, -751.25),  # spf-15, Western Plaguelands
    (1, -454.25, 29.25),  # spf-20, Thunder Bluff
    (0, -5977.0, -968.75),  # spf-31, Loch Modan
    (1, -2157.0, -1537.75),  # spf-33, Dustwallow Marsh
    (0, -11379.25, -353.25),  # spf-54, Duskwood
])
def test_where_a_walk_got_stuck_on_steep_ground_stays_closed(grid, cont, x, y):
    assert grid.At(cont, x, y) == 2


def _tile(liquid_type, surface=0.0, base=-50.0):
    """An ADT tile's root with one chunk: a slope rising 10 yd a vertex eastward from `base`, under a liquid layer
    over the whole chunk at `surface`."""
    mcvt = []
    for i in range(17 * 8 + 9):
        row, k = divmod(i, 17)
        mcvt.append(k * 10.0 if k < 9 else (k - 9) * 10.0 + 5.0)
    mcvt = struct.pack("<145f", *mcvt)
    header = bytearray(T.MCNK_HEADER)
    struct.pack_into("<II", header, 4, 0, 0)
    struct.pack_into("<f", header, 0x68 + 8, base)
    mcnk = bytes(header) + b"TVCM" + struct.pack("<I", len(mcvt)) + mcvt
    heads = bytearray(256 * 12)
    struct.pack_into("<III", heads, 0, len(heads), 1, 0)
    inst = struct.pack("<HHffBBBBII", liquid_type, 0, surface, surface, 0, 0, 8, 8, 0, 0)
    mh2o = bytes(heads) + inst
    return b"O2HM" + struct.pack("<I", len(mh2o)) + mh2o + b"KNCM" + struct.pack("<I", len(mcnk)) + mcnk


def test_a_quad_deep_enough_under_water_isnt_steep():
    root = _tile(2)
    steep, water = T.tile_grid(root)
    assert steep[:8, :8].all() and water[:8, :8].all()  # (without the liquids' kinds: as before)
    steep, water = T.tile_grid(root, swim_types={2})
    # quads' tops -40, -30, ... over the base: under the surface by 2 yd or more up to the 4th column
    assert not steep[:8, :4].any() and steep[:8, 4:8].all()
    assert water[:8, :8].all()
    steep, _ = T.tile_grid(_tile(3), swim_types={2})  # (magma isn't swum)
    assert steep[:8, :8].all()
