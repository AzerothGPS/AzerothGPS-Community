"""Roads or shortcuts shapes how a route merges onto a road (item 57, Kooki3z on 0c5f60b9: the Barrens from the north,
map 51, 8, south to a stop on the road at 52.6, 21.5, at +10 a straight line over the open ground beside the road the
whole way, joining it only at the stop). The road is taken wherever it runs the way to the stop, at +10 too (a small
road bonus there, WorldGrid.ROAD_PRICE_TOP), and the slider sets where and how the way joins it: toward "Stick to
roads" early and steep, toward "Cut across" later and flatter (WorldGrid.SnapRun: the cheapest straight walk onto the
road, ride and walk off, a road yard at the search's road price). A merge never points back against the way to the stop
(the old road snapping), and the way rides the road only toward the stop."""

import math

import pytest

from test_map_redraw import game  # noqa: F401

NORTH = (0.51, 0.08)  # (the Barrens: his start, map 51, 8)
WEST = (0.496, 0.176)  # (item 57b: on the open ground west of the main road, two-thirds of the way down)
STOP = (157.88, -2702.15)  # (on the main road at map 52.6, 21.5, where his stop by the road is)
TOLS = (2, 4, 7, 10)


def _route(lua, ns, start, tol):
    R, WG, st = ns.Router, ns.WorldGrid, ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    st.roadTolerance = tol
    R.Reset()
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    a = ns.Layers.MapToWorld(1413, start[0], start[1])
    r = R.Route(1, a[0], a[1], STOP[0], STOP[1], lua.table())
    assert r and r.pts and not r.pending
    pts = [(r.pts[i], r.pts[i + 1]) for i in range(1, len(r.pts), 2)]
    kinds = [r.kinds[i] for i in range(1, len(pts))]
    return pts, kinds, R.KIND_ROAD


def _merge(pts, kinds, road):
    """Yards along the route to its first road piece, and the turn there (degrees) from the walk into it."""
    yd = 0.0
    for m, k in enumerate(kinds):
        if k == road:
            (ax, ay), (bx, by), (cx, cy) = pts[m - 1], pts[m], pts[m + 1]
            u, v = (bx - ax, by - ay), (cx - bx, cy - by)
            cos = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
            return yd, math.degrees(math.acos(max(-1.0, min(1.0, cos))))
        yd += math.dist(pts[m], pts[m + 1])
    return None, None


def _road_yd(pts, kinds, road):
    return sum(math.dist(pts[m], pts[m + 1]) for m, k in enumerate(kinds) if k == road)


def _backward(pts, kinds, road):
    """Pieces that go back against the way to the stop: a walk onto a road, or a run along one."""
    bad = []
    tx, ty = STOP
    for m, k in enumerate(kinds):
        (ax, ay), (bx, by) = pts[m], pts[m + 1]
        if math.dist((ax, ay), (bx, by)) < 5:
            continue
        onto = k != road and m + 1 < len(kinds) and kinds[m + 1] == road
        if (onto or k == road) and (bx - ax) * (tx - ax) + (by - ay) * (ty - ay) < 0:
            bad.append((m, k, (round(ax), round(ay)), (round(bx), round(by))))
    return bad


@pytest.fixture
def tol_back(game):  # noqa: F811
    st = game[1].settings.gps
    was = (st.roadTolerance, st.worldGrid, st.cityGrid)
    yield
    st.roadTolerance, st.worldGrid, st.cityGrid = was


def test_the_merge_comes_later_and_flatter_toward_cut_across(game, tol_back):  # noqa: F811
    lua, ns = game
    got = {}
    for tol in TOLS:
        pts, kinds, road = _route(lua, ns, NORTH, tol)
        got[tol] = (*_merge(pts, kinds, road), _road_yd(pts, kinds, road))
        assert not _backward(pts, kinds, road), (tol, _backward(pts, kinds, road))
    at = {t: g[0] for t, g in got.items()}
    turn = {t: g[1] for t, g in got.items()}
    # (the road taken at every setting, "Cut across" too: it runs the way to the stop)
    assert all(g[0] is not None and g[2] > 100 for g in got.values()), got
    # (joined later the further right (+2 and +4 both by the junction, within a few cells), its last stretch only at +10)
    assert at[2] <= at[4] + 30 and at[4] < at[7] < at[10] and at[10] > at[2] + 150, got
    # (and flatter: the turn onto the road no sharper at +10 than at +4)
    assert turn[10] <= turn[4], got


def test_from_the_open_ground_west_of_the_road(game, tol_back):  # noqa: F811
    """57b: from the west, the way onto the main road comes later the further right, and never back."""
    lua, ns = game
    road_yd = {}
    for tol in (-10, 0, 2, 10):
        pts, kinds, road = _route(lua, ns, WEST, tol)
        assert not _backward(pts, kinds, road), (tol, _backward(pts, kinds, road))
        road_yd[tol] = _road_yd(pts, kinds, road)
    assert road_yd[-10] >= road_yd[0] >= road_yd[2] >= road_yd[10], road_yd
    assert road_yd[-10] > road_yd[10] + 50, road_yd


def test_a_road_bonus_at_cut_across_small_but_not_none(game, tol_back):  # noqa: F811
    lua, ns = game
    WG = ns.WorldGrid
    ns.settings.gps.roadTolerance = 10
    c = WG.Cont(1)
    x = WG.Costs(c, 0, 0, 100, 0, lua.table())
    assert x.road == pytest.approx(WG.ROAD_PRICE_TOP) and 0.9 <= x.road < 1
    ns.settings.gps.roadTolerance = 0
    assert WG.Costs(c, 0, 0, 100, 0, lua.table()).road == pytest.approx(c.road)
