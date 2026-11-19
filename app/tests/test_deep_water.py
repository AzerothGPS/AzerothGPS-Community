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
