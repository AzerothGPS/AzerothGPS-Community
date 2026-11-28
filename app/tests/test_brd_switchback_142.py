"""1.4.2: Blackrock Mountain's switchback down to Blackrock Depths (Kooki3z 2026-11-27: "you able to fix the switchback to
BRD as well?", after the Hall of Thanes' one).

His recorded walk from the ring over the Molten Span down the switchback's turns to the span's floor and on to Blackrock
Depths' door (#927: pieces 1795410704 to 1795410792, Roads.lua's FloorTracks) was put on the roads in game as one road
per piece with its end heights only, straight between (Router.WithTracks): the switchback's piece runs 259 at its top
to 213 at its foot, but its turns climb, fall and lie over each other (264 on the top turn over the second's 250, over
the third's 226). The floor followed down it (Nav.TrackCityZ: the roads near, their heights) was that straight line's,
8-12 yd under the turn walked, and every route worked out again from it went from the turn under the player: "Jump down
here (31 yd)", "Make a U-turn". A recorded walk's road has a node now wherever its heights leave the straight line
(Router.ZBends), so its heights are the walk's.
"""

import json
import math
from pathlib import Path

import pytest

pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[2]
WALK = (1795410704, 1795410730, 1795410740, 1795410783, 1795410792)  # (#927's pieces, the ring to Blackrock Depths' door)
SWITCHBACK = 1795410740  # (the piece down the switchback's turns: 259 to 213)
BRD = 20230


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    st = ns.settings.gps
    st.cityGrid, st.worldGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    ns.Nav.FUN = False
    ns.CharDB().faction = "Horde"
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end')
    lua.execute("IsIndoors = function() return true end")  # (the game says so in the mountain's halls)
    lua.execute("AGPS_LEVEL = 60")
    yield lua, ns
    lua.execute("IsIndoors = function() return false end")


def _pieces():
    d = json.loads((ROOT / "overrides" / "roads_0.geojson").read_text(encoding="utf-8"))
    by = {f["properties"].get("time"): f for f in d["features"] if f["properties"].get("time") in WALK}
    return {t: [(x, y, z) for (x, y), z in zip(by[t]["geometry"]["coordinates"], by[t]["properties"]["zs"])]
            for t in WALK}


def _dense(pts, step=2.0):
    out = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a[:2], b[:2]) / step))
        out += [tuple(a[j] + (b[j] - a[j]) * k / n for j in range(3)) for k in range(n)]
    return out + [pts[-1]]


def test_the_roads_along_the_switchback_have_the_walk_s_heights(game):
    """At every point of the switchback's piece a road within 2 yd is at the walk's height (within 3 yd): before, the
    top turn's road was 253 where the walk is 264."""
    lua, ns = game
    R = ns.Router
    off = []
    for x, y, z in _pieces()[SWITCHBACK]:
        hs = R.HeightsNear(0, x, y, 2.0)
        near = [hs[i].z for i in range(1, len(hs) + 1)] if hs else []
        if not any(abs(h - z) <= 3 for h in near):
            off.append((round(x), round(y), round(z, 1), sorted(round(h) for h in near)))
    assert not off, off[:8]


def test_walking_down_the_switchback_the_floor_followed_and_the_reroutes_are_the_walk_s(game):
    """Walked down the recorded walk from the ring (the stop: Blackrock Depths' icon), the floor followed is the walk's at
    every step of the switchback, and every route worked out again starts on the walk's floor (before: 8-12 yd under
    it from the top turn on, "Jump down here (31 yd)" and "Make a U-turn" from the turn under the player)."""
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    p = _pieces()
    top = _dense(p[1795410704] + p[1795410730][1:])
    walk = top + _dense(p[1795410740] + p[1795410783][1:])[1:]
    x0, y0, _ = walk[0]  # (on the ring by the span's head, his walk's start)
    N.Clear()
    N.ResetGridTrack()
    N.ResetRouteTrack()
    N.ResetTrack()
    lua.execute(f"AGPS_T = (AGPS_T or 1000) + 60; AGPS_MAP = 1428; AGPS_POS = {{ {x0}, {y0}, 0 }}")
    ents = G.InstanceEntrances(0)
    e = next(ents[i] for i in range(1, len(ents) + 1) if ents[i].level == BRD)
    assert G.AddStopAt(e.x, e.y, e.name, e.cont)
    G.ConfirmRoute()
    lua.execute("""
      AGPS_STARTS = {}
      local N = AGPS_NS.Nav
      AGPS_REAL_START_FLOOR = N.StartFloor
      N.StartFloor = function(cont, px, py)
        local z, zs = AGPS_REAL_START_FLOOR(cont, px, py)
        AGPS_STARTS[#AGPS_STARTS + 1] = { px, py, z or false }
        return z, zs
      end
    """)
    try:
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        floor, starts = [], []
        for i, (x, y, z) in enumerate(walk):
            lua.execute(f"AGPS_T = AGPS_T + 0.3; AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
            n0 = len(lua.eval("AGPS_STARTS"))
            G.Update()
            if i < len(top):  # (on the ring: the route from it, once its floor is known)
                continue
            assert N.route, ("no route at the switchback's top", i)
            got = N.TrackCityZ(0, x, y)
            if got is None or abs(got - z) > 4:
                floor.append((i, round(x), round(y), round(z, 1), got and round(got, 1)))
            ss = lua.eval("AGPS_STARTS")
            for k in range(n0 + 1, len(ss) + 1):
                sz = ss[k][3]
                if sz is False or abs(sz - z) > 5:
                    starts.append((i, round(x), round(y), round(z, 1), sz if sz is False else round(sz, 1)))
        assert not floor, floor[:8]
        assert not starts, starts[:8]
        assert N.route
    finally:
        lua.execute("AGPS_NS.Nav.StartFloor = AGPS_REAL_START_FLOOR")
        N.Clear()
