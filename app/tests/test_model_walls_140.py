"""The whole map's thin tall walls from the client's models, hard barriers (item 78 for the whole map; Kooki3z
2026-11-25: the CurseForge page promises fences, palisades and barricades are walls).

`agps world-grid model-walls --write` (app/azerothgps/modelwalls.py) ships every palisade, fence, barricade and railing
the walk mesh lost, on Kalimdor, the Eastern Kingdoms and Zephras Isle (Data/ModelWalls.lua), each one's outline a
barrier for every route piece (Passability.CrossesModelWall, CrossesWall), and the bake drops the grid's links across
them. A wall never closes a real gap: every road and recorded walk goes through (the generator opens it there), the
capitals are their city grids', and a gate's arch the mesh walks under isn't a wall.

- The data: all three continents, its parameters the generator's (a change unshipped fails here), decoded a square at a
  time.
- No shipped road crosses a model wall (the Router's roads are cut by walls at load without them).
- The known places: Red Cloud Mesa's palisade one piece; Cragpool Lake's barricade across the pass (its road taken out
  in game, #996); the Crossroads' and Razor Hill's fences; no wall in Thunder Bluff (its city grid's); Southshore and
  Dun Algaz (their walls the buildings' and the mesh's) no wall across their roads.
- The shipped world grid links nothing across a model wall in the tiles round those places.
"""

import math
import random

import pytest

from test_map_redraw import game  # noqa: F401

pytest.importorskip("lupa")

from azerothgps import modelwalls  # noqa: E402


def _outlines(ns, cont):
    out = []
    for w in ns.Passability.ModelWallOutlines(cont).values():
        p = [w[i] for i in range(1, len(w) + 1)]
        out.append([(p[i], p[i + 1]) for i in range(0, len(p) - 1, 2)])
    return out


def _near(outs, x, y, r):
    return [w for w in outs if any(abs(px - x) <= r and abs(py - y) <= r for px, py in w)]


def test_the_whole_map_is_shipped_with_its_parameters(game):  # noqa: F811
    lua, ns = game
    assert str(ns.ModelWalls.stamp) == modelwalls.stamp(), "modelwalls.py's parameters changed: write the data again"
    P = ns.Passability
    counts = {c: len(_outlines(ns, c)) for c in (0, 1, 2991)}
    assert counts[0] > 500 and counts[1] > 500 and counts[2991] > 10, counts
    for c in (0, 1, 2991):
        assert P.HasModelWalls(c)
        for w in _outlines(ns, c):
            assert len(w) >= 3 and w[0] == w[-1]  # (closed; a thin wall's simplified to a line there and back)


def test_a_square_is_decoded_the_first_time_a_piece_comes_over_it(game):  # noqa: F811
    lua, ns = game
    st = ns.ModelWalls[1]
    # (an outline's numbers: the first point, then each step, in half yards)
    pts = ns.Passability.DecodeModelOutline("10,-4,2,0,0,2,-2,-2")
    assert [pts[i] for i in range(1, len(pts) + 1)] == [5, -2, 6, -2, 6, -1, 5, -2]
    assert len(list(st.r.keys())) > 50


def test_no_shipped_road_crosses_a_model_wall(game):  # noqa: F811
    lua, ns = game
    R, P = ns.Router, ns.Passability
    for cont in (0, 1, 2991):
        R.NearestEdges(cont, 0, 0)
        g = R.DebugGraph(cont)
        bad, n = [], 0
        for eid in g.e.keys():
            e = g.e[eid]
            pts = [(e[k], e[k + 1]) for k in range(5, len(e) + 1, 2) if e[k] is not None and e[k + 1] is not None]
            for a, b in zip(pts, pts[1:]):
                n += 1
                if P.CrossesModelWall(cont, a[0], a[1], b[0], b[1]):
                    bad.append((int(eid), a, b))
                    break
        assert n > 500, (cont, n)
        assert not bad, f"cont {cont}: {len(bad)} roads through a model wall: {bad[:5]}"


def test_the_known_places(game):  # noqa: F811
    lua, ns = game
    P = ns.Passability
    k1, k0 = _outlines(ns, 1), _outlines(ns, 0)
    # Red Cloud Mesa: the palisade one piece, west cliffs to east rocks
    rc = [w for w in _near(k1, -2826, -456, 450) if max(p[1] for p in w) - min(p[1] for p in w) > 600]
    assert len(rc) == 1
    assert P.CrossesModelWall(1, -2740, -579, -2712, -562)
    # Cragpool Lake (Stonetalon): the barricade across the pass, north-west to south-east of it
    assert _near(k1, 1704, 91, 20)
    assert P.CrossesModelWall(1, 1712, 82, 1697, 100) or P.CrossesModelWall(1, 1715, 86, 1694, 96)
    # the Crossroads and Razor Hill: their fences
    assert len(_near(k1, -450, -2650, 150)) >= 6
    assert len(_near(k1, 320, -4700, 180)) >= 3
    # Thunder Bluff: none (the capital's city grid has its walls)
    assert not [w for w in _near(k1, -1280, 120, 250) if ns.Router.CapitalAt(1, w[0][0], w[0][1])]
    # Southshore and Dun Algaz: their roads open (no road crosses one: test_no_shipped_road_crosses_a_model_wall), and
    # no wall over the towns' streets
    for x, y in ((-810, -530), (-4230, -2420)):
        assert len(_near(k0, x, y, 200)) <= 4, (x, y)


@pytest.mark.parametrize("cont,box", [
    (1, (-500.0, -400.0, -2750.0, -2550.0)),  # (the Crossroads)
    (1, (1650.0, 1750.0, 30.0, 130.0)),  # (Cragpool Lake's barricade)
    (1, (200.0, 450.0, -4850.0, -4550.0)),  # (Razor Hill)
])
def test_the_shipped_grid_links_nothing_across_a_model_wall(game, cont, box):  # noqa: F811
    lua, ns = game
    WG, P = ns.WorldGrid, ns.Passability
    ns.settings.gps.worldGrid = True
    WG.Set(True)
    c = WG.Cont(cont)
    cell = c.cell
    checked, bad = 0, []
    for gx in range(int(box[0] // cell), int(box[1] // cell) + 1):
        for gy in range(int(box[2] // cell), int(box[3] // cell) + 1):
            key, ci = WG.CellKey(c, gx, gy)
            if not key:
                continue
            WG.LoadRegion(c, key // 64 // c.rb, (key % 64) // c.rb)
            t = WG.Tile(c, key)
            if not t:
                continue
            n = WG.Count(t, ci)
            f0 = WG.First(t, ci) if n else 0
            for k in range(n):
                s = f0 + k
                sx, sy = WG.Pt(c, t, s, ci)
                for d in range(1, 9):
                    kk = WG.Link(t, s, d)
                    if kk and kk > 0:
                        nkey, nci = WG.Step(c, key, ci, d)
                        nt = nkey and WG.Tile(c, nkey)
                        if nt:
                            px, py = WG.Pt(c, nt, WG.First(nt, nci) + kk - 1, nci)
                            checked += 1
                            if P.CrossesModelWall(cont, sx, sy, px, py):
                                bad.append((round(sx), round(sy), round(px), round(py)))
    assert checked > 200, checked
    assert not bad, f"{len(bad)} of {checked} shipped links cross a model wall: {bad[:5]}"


def test_the_router_s_own_ways_go_past_a_model_wall_as_its_terrain_knows(game):  # noqa: F811
    """The Router's terrain searches don't know the model walls (its cells and prepared blocks don't have them): its
    segment costs and road joins leave them out (Passability.SegmentCost, the road graph's bridges), else its walks
    went through one and were refused. route-quality against the bake before: four Horde trips into the Hinterlands
    from the west had no route at all (a small wall by the road's end at (0, -2791))."""
    lua, ns = game
    P, R, N, st = ns.Passability, ns.Router, ns.Nav, ns.settings.gps
    assert P.CrossesModelWall(0, -10, -2791, 10, -2791)
    assert P.SegmentCost(0, -10, -2791, 10, -2791) is not None
    saved = (st.worldGrid, ns.CharDB().faction)
    st.worldGrid = False
    ns.WorldGrid.Set(False)
    try:
        lua.execute("AGPS_RQ = { UnitFactionGroup }; AGPS_LEVEL = 20; UnitFactionGroup = function() return 'Horde' end")
        ns.CharDB().faction = "Horde"
        a, b = (383.3, -3850.0), (1816.7, -1216.7)  # (Skulk Rock -> Felstone Field)
        N.Clear()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {a[0]}, {a[1]}, 0")
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        R.WallsChanged()
        assert N.Route(a[0], a[1], 0)
    finally:
        N.Clear()
        lua.execute("UnitFactionGroup = AGPS_RQ[1]")
        st.worldGrid, ns.CharDB().faction = saved
        ns.WorldGrid.Set(bool(st.worldGrid))


def test_a_piece_is_checked_only_against_the_buckets_it_passes_through(game):  # noqa: F811
    # (item 108: CrossesModelWall looked at every bucket in a piece's box, 900 for a 500 yd diagonal, 13 ms a check on
    # the slow client in WorldGrid's road merges. Only the buckets along the piece now: the same answers as every
    # outline piece tested whole, on random pieces round the Crossroads' and Razor Hill's fences, short and long, any
    # direction, through corners and along bucket lines)
    lua, ns = game
    P = ns.Passability
    brute = lua.eval("""function(cont, x1, y1, x2, y2)
      for _, p in ipairs(AGPS_NS.Passability.ModelWallOutlines(cont)) do
        for i = 1, #p - 3, 2 do
          local ax, ay, bx, by = p[i], p[i + 1], p[i + 2], p[i + 3]
          local dx, dy = x2 - x1, y2 - y1
          local d1 = dx * (ay - y1) - dy * (ax - x1)
          local d2 = dx * (by - y1) - dy * (bx - x1)
          if (d1 <= 0 and d2 >= 0) or (d1 >= 0 and d2 <= 0) then
            local ex, ey = bx - ax, by - ay
            local d3 = ex * (y1 - ay) - ey * (x1 - ax)
            local d4 = ex * (y2 - ay) - ey * (x2 - ax)
            if ((d3 <= 0 and d4 >= 0) or (d3 >= 0 and d4 <= 0)) and not (d1 == 0 and d2 == 0) then return true end
          end
        end
      end
      return false
    end""")
    rng = random.Random(108)
    hits = 0
    B = P.MODEL_BUCKET
    for cx, cy in ((-450.0, -2650.0), (320.0, -4700.0)):
        for k in range(300):
            x1, y1 = cx + rng.uniform(-200, 200), cy + rng.uniform(-200, 200)
            if k % 3 == 0:  # (along a bucket line, or straight up or across)
                x1 = round(x1 / B) * B
            length = rng.choice((5.0, 40.0, 150.0, 500.0))
            a = rng.choice((0.0, 90.0, 45.0, rng.uniform(0, 360)))
            x2, y2 = x1 + length * math.cos(math.radians(a)), y1 + length * math.sin(math.radians(a))
            want = bool(brute(1, x1, y1, x2, y2))
            hits += want
            assert bool(P.CrossesModelWall(1, x1, y1, x2, y2)) == want, (x1, y1, x2, y2)
    assert hits > 30
