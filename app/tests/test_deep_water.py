"""Deep water (the client's fatigue water) is never swum: the terrain grid closes it as steep ground."""

import math

import pytest

from test_enemy_territory import _pts

WETLANDS_COAST = (-2969.3, -1030.6)  # (the Wetlands 15.5, 29.8: its north-west coast)
MALEB = (-861.0, -473.7)  # (Magistrate Henry Maleb, Southshore)


@pytest.fixture(scope="module")
def alliance_router():
    from azerothgps.routecheck import ADDON_DIR, _runtime

    lua, ns = _runtime("A")
    loader = lua.eval("function(src, name) return assert(load(src, '@' .. name)) end")
    loader((ADDON_DIR / "Data/Bridges.lua").read_text(encoding="utf-8"), "Data/Bridges.lua")("AzerothGPS", ns)
    return lua, ns


def test_the_wetlands_to_southshore_never_swims_the_strait(alliance_router):
    # (reported 2026-11-19, 1.3.9: from the Wetlands' north-west coast to Southshore the route swam 2 km straight over
    # the strait, 2.3 km "on foot"; 200 yd out the fatigue bar came up. The client marks the open sea deep (MH2O's
    # deep mask, none given: all deep), which the terrain grid now closes: the way is by land, over Thandol Span)
    lua, ns = alliance_router
    R = ns.Router
    R.Reset()
    r = R.Route(0, *WETLANDS_COAST, *MALEB, lua.table(offroad=False))
    pts, kinds = _pts(r), [r.kinds[i] for i in range(1, len(r.kinds) + 1)]
    longest_off = max((math.dist(pts[i], pts[i + 1]) for i, k in enumerate(kinds) if k != R.KIND_ROAD), default=0)
    assert r.road > 0.7 * r.length and longest_off < 1000, (r.road, r.length, longest_off)

# (the Wetlands' north-west coast, more starts: the client's deep mask leaves a 270 yd "shallow" band of open sea down
# Arathi's coast, so after the deep-water fix routes from these still swam 1.7-2.3 km over the strait, 2026-11-19)
COAST_STARTS = [(-2860.0, -1400.0), (-2700.0, -1300.0), (-2740.0, -1200.0), (-2900.0, -1200.0)]


@pytest.fixture(scope="module")
def ground():
    """The Eastern Kingdoms grid as the coast masks read it: 0 open, 1 water (the sea closed far out too), 2 steep."""
    from azerothgps import coast

    return coast.grids()[0]


def _far_out(ground, x, y, reach=170.0):
    """In the sea with no ground (open or steep: rocks, cliffs) within `reach` yd in 16 directions: the open sea."""
    tx0, ty0, cells = ground
    k = 64  # (cells per tile)

    def at(x, y):
        return cells[int((32 - x / 533.3333 - ty0) * k), int((32 - y / 533.3333 - tx0) * k)]

    return at(x, y) == 1 and all(at(x + reach * math.cos(a), y + reach * math.sin(a)) == 1
                                 for a in (i * math.pi / 8 for i in range(16)))


@pytest.mark.parametrize("offroad", [False, True])
@pytest.mark.parametrize("start", COAST_STARTS)
def test_from_the_wetlands_coast_no_route_swims_out_into_the_open_sea(alliance_router, ground, start, offroad):
    lua, ns = alliance_router
    R = ns.Router
    R.Reset()
    r = R.Route(0, *start, *MALEB, lua.table(offroad=offroad))
    pts = _pts(r)
    out = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        n = max(1, int(d / 10))
        out += sum(d / n for i in range(n)
                   if _far_out(ground, a[0] + (b[0] - a[0]) * (i + 0.5) / n, a[1] + (b[1] - a[1]) * (i + 0.5) / n))
    assert out < 50, (start, offroad, round(out), round(r.length))
