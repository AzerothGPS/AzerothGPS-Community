"""A floor under a liquid is no way to walk (walknet.build), also when the floor beside it is the height the gaps
between floor pieces are filled from. Reported 2026-11-19: in Ironforge's Great Forge the routes ran through the lava
pits, their floor 2.6 yd under the lava; the gap fill took the ring's height across them cell by cell, and the city's
roads ran over them."""

from azerothgps import walknet


def square(x0, y0, x1, y1, z):
    """Two floor triangles (walknet.build's format), flat at z."""
    a, b, c, d = (x0, y0), (x1, y0), (x1, y1), (x0, y1)
    return [([a, b, c], [z, z, z], False), ([a, c, d], [z, z, z], False)]


def build():
    # (a ring 60 yd across at 10 round a pit 20 yd across, its floor at 0 under lava up to 2.6)
    floors = (square(-30, -30, 30, -10, 10) + square(-30, 10, 30, 30, 10) + square(-30, -10, -10, 10, 10)
              + square(10, -10, 30, 10, 10) + square(-10, -10, 10, 10, 0))
    lava = [([(-10, -10), (10, -10), (10, 10), (-10, 10)], 2.6)]
    return walknet.build(floors, [], lava, label="pit", log=lambda s: None)


def test_the_floor_under_the_lava_stays_closed():
    u = build()
    walk, top = u["walk"], u["top"]
    for x, y in ((0, 0), (5, -5), (-8, 8), (8, 0)):  # (in the pit)
        r, c = u["world_to_px"](x, y)
        assert not walk[r, c], ((x, y), float(top[r, c]))
    for x, y in ((20, 0), (-20, 0), (0, 20), (0, -20)):  # (on the ring)
        r, c = u["world_to_px"](x, y)
        assert walk[r, c] and abs(top[r, c] - 10) < 1, (x, y)
