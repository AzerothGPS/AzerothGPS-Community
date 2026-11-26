"""One-way ground (item 107, 1.4.1; issue #271): Data/TerrainDown.lua (app/azerothgps/roads/terrain_down.py) and
Passability's use of it. A closed cell the terrain's own rule closes as too steep, no face past 70 degrees, is walked
down its fall line only, its whole way down bounded by its class's fall (Passability.DOWN_FALLS) and taken within the
safe drop. The searches over the cells and the blocks, and the straight lines between points, never go up it."""

import math
import re

import numpy as np
import pytest

from azerothgps import hpa
from azerothgps.roads import terrain as T
from azerothgps.roads import terrain_down as TD
from test_addon_lua import ADDON, env, load  # noqa: F401 (fixtures)

TILE = 1600 / 3


def _down_data():
    text = (ADDON / "Data" / "TerrainDown.lua").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'\[(\d+)\] = \{ w = (\d+), h = (\d+), terrain = "([0-9a-f]+)", rows = \{\n(.*?)\n  \} \},', text,
                         re.S):
        rows = dict((int(r), s) for r, s in re.findall(r'\[(\d+)\] = "([^"]*)"', m.group(5)))
        out[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), m.group(4), rows)
    return out


DOWN = _down_data()
TD_CAP = float(re.search(r"^P\.DOWN_FALL_CAP = (\d+)", (ADDON / "Passability.lua").read_text(encoding="utf-8"), re.M).group(1))
TERRAIN_TEXT = (ADDON / "Data" / "Terrain.lua").read_text(encoding="utf-8")


def test_the_one_way_ground_is_made_for_the_shipped_terrain_grid():
    assert set(DOWN) == {0, 1, 2991}
    for cont, (w, h, stamp, rows) in DOWN.items():
        head, cells = TD.shipped_cells(cont, TERRAIN_TEXT)
        assert (w, h) == (head["w"], head["h"])
        assert stamp == TD.terrain_stamp(TERRAIN_TEXT, cont), "stale: run agps terrain-down --write, then terrain-hpa"
        n = 0
        for r, s in rows.items():
            codes = TD.decode_row(s, w)
            on = codes >= 0
            n += int(on.sum())
            assert (cells[r - 1][on] == 2).all()  # (closed cells only: never water, the deep sea or open ground)
            assert (codes[on] < 16 * len(TD.FALLS)).all()
        assert n > 1000, (cont, n)


def test_a_row_s_runs_come_back_as_they_went():
    rnd = np.random.default_rng(7)
    for _ in range(50):
        w = int(rnd.integers(1, 3000))
        codes = np.full(w, -1, np.int16)
        on = rnd.random(w) < rnd.random()
        codes[on] = rnd.integers(0, 64, int(on.sum()))
        assert (TD.decode_row(TD.encode_row(codes), w) == codes).all()


def _hillside(rows_steep, drop_per_cell, share=1.0, top=1.5, size=14):
    """A made-up hillside: open ground in the north (row 0 up), `rows_steep` closed rows falling `drop_per_cell` each
    southward, open ground below. Returns (cells, share, top, zc, whole)."""
    H = W = size
    zc = np.zeros((H, W))
    first = 4
    for r in range(H):
        k = min(max(r - first + 1, 0), rows_steep + 1)
        zc[r, :] = 200 - k * drop_per_cell
    cells = np.zeros((H, W), np.int8)
    cells[first:first + rows_steep, :] = 2
    sh = np.where(cells == 2, share, 0.0)
    tp = np.where(cells == 2, top, 0.2)
    return cells, sh, tp, zc, np.ones((H, W), bool)


def test_a_steep_bank_is_one_way_down_its_fall_line_and_classed_by_its_fall():
    cells, sh, tp, zc, whole = _hillside(2, 10.0)  # (30 yd from the top's open ground to the foot's)
    code = TD.one_way(cells, sh, tp, zc, whole, 8.333, log=lambda *_: None)
    inner = code[4:6, 2:-2]
    assert (inner >= 0).all()
    assert (inner % 16 == 4).all()  # (south, +row: down the hill)
    assert (inner // 16 == 2).all()  # (25 < 30 <= 39)
    cells, sh, tp, zc, whole = _hillside(1, 10.0)  # (20 yd)
    code = TD.one_way(cells, sh, tp, zc, whole, 8.333, log=lambda *_: None)
    assert (code[4, 2:-2] // 16 == 1).all()


def test_a_mountainside_past_the_biggest_class_ridge_filling_and_sheer_faces_stay_closed_both_ways():
    quiet = dict(log=lambda *_: None)
    # (100 yd of it: no class bounds that fall)
    assert (TD.one_way(*_hillside(8, 12.0), 8.333, **quiet) < 0).all()
    # (closed by the ridge filling or the pockets: fewer than half its quads steep)
    assert (TD.one_way(*_hillside(2, 10.0, share=0.25), 8.333, **quiet) < 0).all()
    # (a face past 70 degrees in it: a cliff)
    assert (TD.one_way(*_hillside(2, 10.0, top=3.0), 8.333, **quiet) < 0).all()


def test_the_blocks_walk_one_way_ground_down_only():
    K = hpa.K
    V = np.zeros((K, K), np.int8)
    V[10:14, :] = 2  # (a band across the block)
    Dn = np.full((K, K), -1, np.int16)
    Dn[10:14, :] = 4  # (one-way, its fall line south: +row)
    north, south = 5 * K + 16, 20 * K + 16
    d = hpa.walks(V, 0, [north, south], 1, 1.5, Dn, 0.5)
    assert np.isfinite(d[0, 1]) and not np.isfinite(d[1, 0])
    two_way = hpa.walks(V, 0, [north, south], 1, 1.5)
    assert not np.isfinite(two_way[0, 1]) and not np.isfinite(two_way[1, 0])


@pytest.fixture
def terrain(env):
    lua, ns = env
    ns.db = lua.eval("{}")
    load(lua, ns, "Data/Terrain.lua", "Passability.lua")  # (with TerrainDown, Buildings, TerrainHPA: as the toc)
    return lua, ns, ns.Passability


def _centre(cont, c, r):
    head, _ = _HEADS[cont]
    k = TILE / head["cell"]
    return (32 - head["ty0"] - (r - 0.5) / k) * TILE, (32 - head["tx0"] - (c - 0.5) / k) * TILE


_HEADS = {c: TD.shipped_cells(c, TERRAIN_TEXT) for c in (0, 1)}


def _banks(cont, top_class=None, want=8, run=3):
    """Straight one-way banks: (open cell above, open cell below) with `run` or more one-way cells between, each of
    class `top_class` or under and its fall line straight down a row or a column, the same way, closed either side."""
    head, cells = _HEADS[cont]
    w, h, _stamp, rows = DOWN[cont]
    codes = {r: TD.decode_row(s, w) for r, s in rows.items()}
    if top_class is None:  # (the classes taken at the cap)
        top_class = max(i for i, f in enumerate(TD.FALLS) if f <= TD_CAP)

    def code(c, r):  # (1-based)
        row = codes.get(r)
        return int(row[c - 1]) if row is not None and 1 <= c <= w else -1

    steps = {0: (1, 0), 4: (0, 1), 8: (-1, 0), 12: (0, -1)}
    out = []
    for r in sorted(codes):
        for c0 in np.flatnonzero(codes[r] >= 0):
            c = int(c0) + 1
            k = code(c, r)
            if k // 16 > top_class or k % 16 not in steps:
                continue
            dc, dr = steps[k % 16]
            top = (c - dc, r - dr)
            if not (1 <= top[1] <= h and cells[top[1] - 1, top[0] - 1] == 0):
                continue
            n, (fc, fr), walled = 0, (c, r), True
            while code(fc, fr) >= 0 and code(fc, fr) // 16 <= top_class and code(fc, fr) % 16 == k % 16:
                # (closed beside it, both sides: no way up round its edge)
                for sc, sr in ((fc + dr, fr + dc), (fc - dr, fr - dc)):
                    walled = walled and 1 <= sr <= h and 1 <= sc <= w and cells[sr - 1, sc - 1] == 2
                n, fc, fr = n + 1, fc + dc, fr + dr
            if not walled:
                continue
            if n >= run and 1 <= fr <= h and cells[fr - 1, fc - 1] == 0:
                out.append((top, (fc, fr)))
                if len(out) >= want:
                    return out
    return out


@pytest.mark.parametrize("cont", [0, 1])
def test_a_one_way_bank_is_walked_down_and_never_straight_up(terrain, cont):
    lua, ns, P = terrain
    P.SetDropMax(39)
    # (the ends' slack, a player standing there, would cross a short bank either way: none at all, not even the cells
    # beside an end, as a cell's yards under nothing give)
    P.END_SLACK = -ns.Terrain[cont].cell
    banks = _banks(cont, want=16, run=1)
    assert len(banks) >= 4, banks
    down_ok = tried = 0
    for top, foot in banks:
        a, b = _centre(cont, *top), _centre(cont, *foot)
        if not (P.IsOpen(cont, *a) and P.IsOpen(cont, *b)):
            continue  # (a building's or a wall's cell in game: an end on closed ground has its own slack)
        tried += 1
        if P.SegmentCost(cont, *a, *b, 0) is not None:
            down_ok += 1
        assert P.SegmentCost(cont, *b, *a, 0) is None  # (never straight up it)
        P.ClearCache()
        r = P.FindPath(cont, *a, *b)
        down = r[0] if isinstance(r, tuple) else None
        r = P.FindPath(cont, *b, *a)
        up = r[0] if isinstance(r, tuple) else None
        assert down is not None and down <= 1.5 * math.dist(a, b), (top, foot, down)
        assert up is None or up > down + 8, (top, foot, down, up)  # (up: round by the open ground, if at all)
    assert tried >= 4 and down_ok >= tried // 2, (tried, down_ok)


def test_the_class_is_taken_only_within_the_safe_drop_and_the_cap(terrain):
    lua, ns, P = terrain
    w, h, _stamp, rows = DOWN[0]
    g = ns.Terrain[0]
    found = {}
    for r, s in rows.items():
        codes = TD.decode_row(s, w)
        for cls in range(len(TD.FALLS)):
            hit = np.flatnonzero(codes // 16 == cls)
            if len(hit) and cls not in found:
                found[cls] = (r, int(hit[0]) + 1, int(codes[hit[0]]))
    assert set(found) == set(range(len(TD.FALLS)))
    assert [P.DOWN_FALLS[i + 1] for i in range(len(TD.FALLS))] == list(TD.FALLS)
    for drop in (14, 25, 39, 60, 400):  # (60 and over: a fall spell's; still never past DOWN_FALL_CAP)
        P.SetDropMax(drop)
        for cls, (r, c, k) in found.items():
            want = k % 16 if TD.FALLS[cls] <= min(drop, P.DOWN_FALL_CAP) else None
            assert P.DownCell(g, r, c) == want, (drop, cls)
            assert P.DownCell(g, r, c, 14) == (k % 16 if cls == 0 else None)


@pytest.mark.parametrize("trip", [
    (1, 824.0, 480.0, 921.0, 262.0),  # (Stonetalon's ledge, test_cliff_heights)
    (1, 921.0, 262.0, 824.0, 480.0),  # (... and back up)
    (0, -5474.1, -2955.5, -5300.0, -2700.0),  # (Loch Modan's mountains)
    (0, 135.0, -500.0, 600.0, -900.0),  # (Alterac's hills, spf-53's)
    (1, -2241.0, -1916.9, -2743.5, -2892.9),  # (the Barrens' hills by the Crossroads' south road)
])
def test_no_walk_s_line_goes_up_one_way_ground(terrain, trip):
    lua, ns, P = terrain
    P.SetDropMax(39)
    r = P.FindPath(*trip)
    if not isinstance(r, tuple):
        return
    pts = [r[1][i] for i in range(1, len(r[1]) + 1)]
    cont = trip[0]
    g = ns.Terrain[cont]
    head, _ = _HEADS[cont] if cont in _HEADS else TD.shipped_cells(cont, TERRAIN_TEXT)
    k = TILE / head["cell"]
    # (the ends' slack: the player's standing there; an end on closed ground has START_SLACK or STOP_SLACK of it)
    def slack(x, y, far):
        col = math.floor(((32 - y / TILE) - head["tx0"]) * k) + 1
        row = math.floor(((32 - x / TILE) - head["ty0"]) * k) + 1
        return (far if P.IsOpen(cont, x, y) is False else P.END_SLACK) + head["cell"]
    ends = [((trip[1], trip[2]), slack(trip[1], trip[2], P.START_SLACK)),
            ((trip[3], trip[4]), slack(trip[3], trip[4], P.STOP_SLACK))]
    for i in range(0, len(pts) - 2, 2):
        x1, y1, x2, y2 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        n = max(1, math.ceil(math.dist((x1, y1), (x2, y2)) / (head["cell"] / 3)))  # (SegmentCost's own samples)
        for q in range(n + 1):
            x, y = x1 + (x2 - x1) * q / n, y1 + (y2 - y1) * q / n
            if any(math.dist((x, y), e) <= yd for e, yd in ends):
                continue
            col = math.floor(((32 - y / TILE) - head["tx0"]) * k) + 1
            row = math.floor(((32 - x / TILE) - head["ty0"]) * k) + 1
            d = P.DownCell(g, row, col)
            if d is not None:
                assert P.DownAlong(d, -(y2 - y1), -(x2 - x1)), (trip, (x, y), d)
