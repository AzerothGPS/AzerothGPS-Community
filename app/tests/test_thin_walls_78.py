"""Item 78 (Kooki3z's hand test of the thin-wall bake, 1e503bf8): routes through Red Cloud Mesa's palisade and Cragpool
Lake's barricade.

a. Red Cloud Mesa (Mulgore): a 3.5 yd drop link off the rim at (-2779, -245) went through the palisade, which the walk
   mesh knows (a gap along it), so the model-wall cut kept it: a drop is now cut by a wall on its edge whatever the mesh
   knows (worldgrid.cut_wall_links). From spots inside the palisade no route jumps off the mesa: it leaves by the
   road gaps.
b. Cragpool Lake (Stonetalon): the road through the barricade, taken out in game (#996), left two road ends 20 yd apart
   that Router.JoinDrawnEnds joined again straight through his drawn wall there: joins never cross a drawn wall now."""

import pytest

from test_map_redraw import game  # noqa: F401


def _route(lua, ns, cont, sx, sy, sz, tx, ty):
    """The Router's route on both grids, nothing remembered from before."""
    R, WG, st = ns.Router, ns.WorldGrid, ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    ns.CityGrid.Set(True)
    R.Reset()
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    return R.Route(cont, sx, sy, tx, ty, lua.table(sz=sz))


def _pieces(r):
    n = len(r.pts) // 2
    for i in range(1, n):
        yield (r.pts[2 * i - 1], r.pts[2 * i], r.fz[i] if r.fz else None, r.pts[2 * i + 1], r.pts[2 * i + 2],
               r.fz[i + 1] if r.fz else None, r.kinds[i] if r.kinds else None)


def _palisade(ns):
    """The palisade's footprint (Data/ModelWalls.lua, from the client's models: test_palisade_140.py). The 84 segments
    here before were Camp Narache's posts, not the wall."""
    out = []
    for w in ns.Passability.ModelWallOutlines(1).values():
        p = [w[i] for i in range(1, len(w) + 1)]
        if not any(-3000 < p[i] < -2650 and -950 < p[i + 1] < 100 for i in range(0, len(p) - 1, 2)):
            continue  # (Red Cloud Mesa's only: the whole map's walls are shipped since)
        out.extend(p[i:i + 4] for i in range(0, len(p) - 3, 2))
    return out


def _cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


@pytest.mark.parametrize("start", [(-2806.0, -241.0, 55.0), (-2905.6, -458.6, 50.0), (-2840.0, -380.0, 55.0)],
                         ids=["his_spot", "item_43_spot", "mid_rim"])
def test_no_route_crosses_red_cloud_mesa_s_palisade(game, start):  # noqa: F811
    lua, ns = game
    tx, ty, _ = ns.Layers.MapToWorld(1412, 0.478, 0.611)  # (his stop, "/way Mulgore 47.8 61.1")
    r = _route(lua, ns, 1, start[0], start[1], start[2], tx, ty)
    assert r and r.pts
    palisade = _palisade(ns)
    for ax, ay, az, bx, by, bz, k in _pieces(r):
        for s in palisade:  # (whatever the piece's heights: a drop's top past the rim crosses it too)
            assert not _cross((ax, ay), (bx, by), (s[0], s[1]), (s[2], s[3])),                 f"through the palisade: ({ax:.0f}, {ay:.0f}) {az} -> ({bx:.0f}, {by:.0f}) {bz}"


def test_cragpool_s_route_never_crosses_his_drawn_wall(game):  # noqa: F811
    lua, ns = game
    sx, sy, _ = ns.Layers.MapToWorld(1442, 0.650, 0.378)  # (beside the barricade, Stonetalon 65.0, 37.8)
    tx, ty, _ = ns.Layers.MapToWorld(1442, 0.470, 0.610)
    r = _route(lua, ns, 1, sx, sy, ns.Ground.Sample(1, sx, sy), tx, ty)
    assert r and r.pts
    P = ns.Passability
    for ax, ay, _az, bx, by, _bz, _k in _pieces(r):
        if abs(ax - 1705) < 80 and abs(ay - 90) < 80:  # (by the barricade)
            assert not P.CrossesWall(1, ax, ay, bx, by), f"through his wall: ({ax:.0f}, {ay:.0f}) -> ({bx:.0f}, {by:.0f})"


def test_no_road_join_crosses_a_drawn_wall(game):  # noqa: F811
    # (the joins of drawn roads' loose ends, Router.JoinDrawnEnds: the one through Cragpool's barricade gone)
    lua, ns = game
    R = ns.Router
    R.NearestEdges(1, 1705.0, 88.0)
    g = R.DebugGraph(1)
    P = ns.Passability
    for eid in g.e.keys():
        e = g.e[eid]
        pts = [(e[k], e[k + 1]) for k in range(5, len(e) + 1, 2) if e[k] is not None and e[k + 1] is not None]
        if len(pts) == 2 and any(abs(x - 1705) < 40 and abs(y - 90) < 40 for x, y in pts):
            (ax, ay), (bx, by) = pts
            assert not P.CrossesWall(1, ax, ay, bx, by), (eid, pts)
