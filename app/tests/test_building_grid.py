"""The buildings' walk grids out in the open world (1.4.2, item 119; buildinggrid.py, `agps building-grid`): each region
folder's Buildings.lua, its size within Kooki3z's budget, baked with the parameters there now, readable, and loaded with
its region. Phase A: the data only, nothing routes on it yet."""

import math
import re

import pytest

from azerothgps import buildinggrid as BG
from azerothgps import citygrid as CGP
from azerothgps import worldbake as WB
from azerothgps.gameharness import start

# (Kooki3z 2026-11-27 dropped the 10 MB cap on the 1.4.2 data: "i dont mind if we go past 10mb")


def _files():
    return sorted(WB.addons_root().glob(f"AzerothGPS_WG*/{BG.FILE}"))


def test_there_are_building_grids():
    assert len(_files()) >= 20, "agps building-grid bake --write"


def test_the_building_grids_are_baked_with_the_parameters_there_now():
    stamp = BG.bake_stamp()
    for f in _files():
        assert f'bake = "{stamp}"' in f.read_text(encoding="utf-8"), (
            f"{f.parent.name}: buildinggrid's or citygrid's parameters changed: agps building-grid bake --write")


def test_the_city_grids_are_from_the_same_bake(monkeypatch):
    # (one run bakes both, `agps building-grid bake --write`: the buildings' stamp takes the city grids')
    txt = CGP.out_path().read_text(encoding="utf-8")
    assert f'bake = "{CGP.bake_stamp()}"' in txt
    before = BG.bake_stamp()
    monkeypatch.setattr(CGP, "ANCHOR_WAY_YD", CGP.ANCHOR_WAY_YD + 1)
    assert BG.bake_stamp() != before


def test_every_placement_has_its_grid_and_each_grid_decodes():
    data = BG.shipped()
    assert data
    n = 0
    for (cont, rx, ry), reg in data.items():
        for vid, x, y, _z, _yaw in reg["p"]:
            assert vid in reg["m"], (cont, rx, ry, vid)
            assert BG.region_key(cont, x, y) == (cont, rx, ry)
            n += 1
        for vid, s in reg["m"].items():
            d = BG.decode(s)
            assert d["cells"], vid
            for cell, ss in d["cells"].items():
                assert 1 <= len(ss) <= CGP.MAX_IN_CELL
                zs = [q[0] for q in ss]
                assert zs == sorted(zs), (vid, cell)
                for q in ss:
                    for dd, t in enumerate(q[4]):
                        if t:
                            dx, dy = CGP.DIRS[dd]
                            assert t <= len(d["cells"].get((cell[0] + dx, cell[1] + dy), ())), (vid, cell, dd)
    assert n > 1500


def test_the_encoding_round_trips():
    # (a small grid of three cells, one stacked, its links: what encode writes, decode reads)
    city = CGP.City("building", "", 0, cell=BG.CELL)
    surf = {(0, 0): [[1.0, set(), 1.0, 1.0], [9.5, set(), 0.5, 1.5]], (1, 0): [[1.25, set(), 3.0, 1.0]],
            (0, 1): [[40.0, set(), 1.0, 3.0]]}
    links = {(0, 0, 0): [0, -1, -1, -1, -1, -1, -1, -1], (0, 0, 1): [-1] * 8, (1, 0, 0): [-1, -1, 0, -1, -1, -1, -1, -1],
             (0, 1, 0): [-1, -1, -1, 1, -1, -1, -1, -1]}
    g = CGP.Grid(city, 0.0, 0.0, 2, 2, BG.CELL, surf, links, [])
    g.flags = {(0, 0, 1): BG.F_REACH, (0, 1, 0): BG.F_DOOR}
    d = BG.decode(BG.encode(g))
    c = d["cells"]
    assert [q[0] for q in c[(0, 0)]] == [1.0, 9.5] and c[(1, 0)][0][0] == 1.25 and c[(0, 1)][0][0] == 40.0
    assert c[(0, 0)][0][4][0] == 1 and c[(1, 0)][0][4][2] == 1 and not any(c[(0, 0)][1][4])
    assert c[(0, 1)][0][4][3] == 2  # (a link the heights don't imply: 30 yd down)
    assert c[(0, 0)][1][1] == BG.F_REACH and c[(0, 1)][0][1] == BG.F_DOOR
    assert (c[(0, 0)][1][2], c[(0, 0)][1][3]) == (2, 6)


def test_frames_turn_back_and_forth():
    r = {"x": 100.0, "y": -50.0, "z": 3.0, "yaw": 37.5}
    import numpy as np
    p = np.array([[4.0, -2.0, 1.5]])
    w = BG.to_world(p, r)
    assert np.allclose(BG.to_frame(w, r), p)
    # (the frame is the model's own for an untilted placement: walknet.Placed's turn)
    from azerothgps import walknet
    from azerothgps.interiors import Placement
    xf = walknet.Placed(Placement(1, 1, 100.0, -50.0, 3.0, 37.5, 0.0, (0, 0, 0, 0)))
    assert np.allclose(xf(p[0]), w[0])


@pytest.mark.parametrize("name, cont, x, y, z", [
    ("Foggy MacKreel, inside Thandol Span", 0, -2357.0, -2423.0, 74.9),
])
def test_floors_the_world_grid_lacks_are_in_a_building_grid(name, cont, x, y, z):
    zs = BG.floors_at(cont, x, y, BG.shipped(), r=1)
    assert zs and min(abs(f - z) for f in zs) <= 3.0, (name, sorted(round(f, 1) for f in zs))


def test_the_regions_load_their_buildings_and_only_the_building_routing_reads_them():
    lua, ns = start()
    reg = sorted(BG.shipped())[0]
    c = ns.WorldGrid.Cont(reg[0])
    assert ns.WorldGrid.LoadRegion(c, reg[1], reg[2])
    all_ = lua.eval("rawget(_G, 'AzerothGPS_BuildingGrids')")
    e = all_[f"{reg[0]}:{reg[1]}:{reg[2]}"]
    assert e.bake == BG.bake_stamp() and e.cell == BG.CELL
    # (read by BuildingGrid.lua alone, 1.4.2's steps 3-5)
    from azerothgps.paths import ADDON_DIR
    for f in ADDON_DIR.rglob("*.lua"):
        if f.name != "BuildingGrid.lua":
            assert "AzerothGPS_BuildingGrids" not in f.read_text(encoding="utf-8", errors="replace"), f.name


def test_regions_with_buildings_are_regions_of_the_world_grid():
    for (cont, rx, ry) in BG.shipped():
        head = WB.out_path(cont).read_text(encoding="utf-8")
        assert re.search(rf'\["{rx}:{ry}"\] = \d+', head), (cont, rx, ry)
        assert math.isfinite(rx)
