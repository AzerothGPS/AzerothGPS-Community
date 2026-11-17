"""layers.py: floors over floors (Undercity's, the dungeons')."""

import numpy as np

from azerothgps import layers, walknet


def test_a_doorways_gap_is_never_filled_through_a_wall():
    # (issue #315) a gap of a cell between two floors at one height is a doorway's threshold, filled; not when the
    # straight line across it goes through a wall at a body's height (Undercity's west lift shaft's floor was joined
    # diagonally through its slanting wall, whose cells met only at their corners, onto the walkway's curb outside)
    NB, H, W = 12, 7, 7
    f = np.zeros((NB, H, W), bool)
    f[5, 2, 2] = f[5, 4, 4] = True  # (two floors, a diagonal cell apart: cell (3, 3) between them empty)
    u = {"bands": f.copy(), "Z0": 0.0, "px_to_world": lambda r, c: (2.0 * r + 1, 2.0 * c + 1)}
    nowall = np.zeros_like(f)
    g, n = layers.fill_seams(f, u, nowall)
    assert n == 1 and g[5, 3, 3]
    # a wall standing across the gap (from (5, 9) to (9, 5), through cell (3, 3)'s middle), from the floor up
    tri = [(5.0, 9.0), (9.0, 5.0), (9.0, 5.0)]
    wall = ((5.0, 15.0), tri, [5.0, 5.0, 15.0])
    g, n = layers.fill_seams(f, u, nowall, crosses=walknet.wall_crosser([wall]))
    assert n == 0 and not g[5, 3, 3]
    # a wall over the gap, a doorway's lintel above a body's height: filled
    lintel = ((9.0, 15.0), tri, [9.0, 9.0, 15.0])
    g, n = layers.fill_seams(f, u, nowall, crosses=walknet.wall_crosser([lintel]))
    assert n == 1 and g[5, 3, 3]
