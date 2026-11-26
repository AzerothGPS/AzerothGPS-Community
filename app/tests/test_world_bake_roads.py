"""The world grid's bake, its roads (worldbake.road_floors, mark_roads) on a small made-up grid: a road with no heights
under an overhang keeps to the floor it came along, and a step in that floor the mesh didn't join gets a road link
(Dun Algaz, 2026-11-22: docs/world-grid-1.4.0.md)."""

from __future__ import annotations

import math

import numpy as np

from azerothgps import worldbake as B
from azerothgps.worldgrid import CELL_PER_TILE, DIRS, FLAG_ROAD, Grid, cell_yd

N = 10  # cells along the gorge (gx 0..9, gy 0)
TOP = range(3, 7)  # cells with the mountain over the gorge (an overhang: the terrain's height is the top's)
STEP_AT = 4  # the floor steps up 3 yd from cell 4 to cell 5, and the mesh doesn't join them (a gate's threshold)
STUB_CELL = (3, 1)  # beside the gorge, in its side: only the mountain top (a road stub ends there, as Dun Algaz's three)


class _Ground:
    """The terrain's height (Data/Heights.lua's): the mountain top's over the overhang, the gorge floor's elsewhere."""

    def __init__(self, cell):
        self.cell = cell

    def sample(self, X, Y):
        i = np.floor(np.asarray(X, float) / self.cell).astype(int)
        return np.where((i >= TOP.start) & (i < TOP.stop), 100.0, 0.0)


def _gorge(step: float = 3.0) -> Grid:
    g = Grid.__new__(Grid)
    g.cont, g.per_tile, g.cell = 99, CELL_PER_TILE, cell_yd(CELL_PER_TILE)
    surf = []  # (gx, z, floor?, gy)
    for i in range(N):
        surf.append((i, 0.0 if i <= STEP_AT else step, True, 0))
        if i in TOP:
            surf.append((i, 100.0, False, 0))
    surf.append((STUB_CELL[0], 101.0, False, STUB_CELL[1]))
    g.n = len(surf)
    g.gx = np.array([s[0] for s in surf], np.int32)
    g.gy = np.array([s[3] for s in surf], np.int32)
    g.z = np.array([s[1] for s in surf], float)
    g.off = np.full(g.n, 4 * 8 + 4, np.int32)
    g.kind = np.zeros(g.n, np.int8)
    g.flags = np.zeros(g.n, np.uint8)
    g.gxmin, g.gymin, g.W, g.H = 0, 0, N, 2
    g.first = np.full(N * 2, -1, np.int64)
    g.count = np.zeros(N * 2, np.int8)
    for s, (i, _z, _f, j) in enumerate(surf):
        if g.first[i * 2 + j] < 0:
            g.first[i * 2 + j] = s
        g.count[i * 2 + j] += 1
    floor = {i: s for s, (i, _z, f, j) in enumerate(surf) if f}
    top = {i: s for s, (i, _z, f, j) in enumerate(surf) if not f and j == 0}
    g.links = np.full((g.n, 8), -1, np.int64)
    east, west = DIRS.index((1, 0)), DIRS.index((-1, 0))
    for layer in (floor, top):
        for i, s in layer.items():
            if i + 1 in layer and not (layer is floor and i == STEP_AT):
                g.links[s, east] = layer[i + 1]
                g.links[layer[i + 1], west] = s
    g.road, g.road_out = [], {}
    g._ground = _Ground(g.cell)
    g._floor, g._top = floor, top
    return g


def _roads(g):
    # (three road pieces with no heights, as the land's roads are, meeting at cells 3 and 6's middles: the middle one
    # wholly under the overhang; first, a stub from cell 3's middle into the gorge's side)
    y = 0.5 * g.cell
    cuts = [0.5, 3.5, 6.5, 9.5]
    x0, x1 = 3.5 * g.cell, (STUB_CELL[0] + 0.5) * g.cell
    y1 = (STUB_CELL[1] + 0.5) * g.cell
    out = [(9, 0, False, [(x0 + (x1 - x0) * t / 8, y + (y1 - y) * t / 8, None) for t in range(9)], y1 - y)]
    for k in range(3):
        x0, x1 = cuts[k] * g.cell, cuts[k + 1] * g.cell
        n = int(math.ceil(x1 - x0))
        out.append((k, 0, False, [(x0 + (x1 - x0) * t / n, y, None) for t in range(n + 1)], x1 - x0))
    return out


def test_a_road_under_an_overhang_keeps_to_the_floor_it_came_along():
    g = _gorge()
    floors = B.road_floors(g, _roads(g))
    for on in floors[1:]:
        assert all(s in g._floor.values() for s in on), [float(g.z[s]) for s in on]


def test_a_step_in_the_road_s_floor_the_mesh_didn_t_join_gets_a_road_link():
    g = _gorge()
    B.mark_roads(g, _roads(g), log=lambda *a: None)
    a, b = g._floor[STEP_AT], g._floor[STEP_AT + 1]
    assert any(r[1] == b for r in g.road_out.get(a, ())) and any(r[1] == a for r in g.road_out.get(b, ()))
    # (the gorge floor walked end to end over the grid and its road links; the mountain top isn't road ground)
    assert g.dist(g._floor[0], g._floor[N - 1], 1e9) < math.inf
    assert all(g.flags[s] & FLAG_ROAD for s in g._floor.values())
    assert not any(g.flags[s] & FLAG_ROAD for s in g._top.values())


def test_a_ramp_s_climb_is_weighed_over_its_surfaces_points_not_the_road_s_yard():
    # (the tunnel north of Dun Algaz to the Wetlands' east, 2026-11-22: its floor climbs 86.5 to 90.6 yd between two
    # cells' points 8 yd apart, and the road crosses from one cell's surface to the next in a yard: refused as a 4 yd
    # climb in one, the tunnel cut in two. ROAD_LINK_SPAN_SLOPE: over the points' yards)
    g = _gorge(step=4.2)
    B.mark_roads(g, _roads(g), log=lambda *a: None)
    a, b = g._floor[STEP_AT], g._floor[STEP_AT + 1]
    assert any(r[1] == b for r in g.road_out.get(a, ()))
    # (a cliff's step is still refused: never a floor tens of yards over the road's, Thousand Needles)
    g = _gorge(step=20.0)
    B.mark_roads(g, _roads(g), log=lambda *a: None)
    a, b = g._floor[STEP_AT], g._floor[STEP_AT + 1]
    assert not any(r[1] == b for r in g.road_out.get(a, ()))
