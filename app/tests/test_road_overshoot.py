"""Road preference never overshoots the stop (item 83, Kooki3z on b84cff45 at "Roads or shortcuts" -10: Thorn Hill west
to the Dry Hills, the route followed the road west, then north round the hills on his recorded road, past the stop and
back, about twice the open way; and it settled slowly). A road yard costs at least WorldGrid.ROAD_PRICE_MIN of one off
it (1/1.5: a road buys a detour of at most 1.5 times the open way), and a route past its stop and back is searched again
with no road preference, at any tolerance."""

import pytest

from test_map_redraw import game  # noqa: F401


def _route(lua, ns, tol):
    R, WG, st = ns.Router, ns.WorldGrid, ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    st.roadTolerance = tol
    R.Reset()
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    a = ns.Layers.MapToWorld(1413, 0.585, 0.252)  # (Thorn Hill, Barrens map 58.5, 25.2)
    b = ns.Layers.MapToWorld(1413, 0.438, 0.149)  # (his stop at the Dry Hills)
    return R.Route(1, a[0], a[1], b[0], b[1], lua.table()), a, b


@pytest.mark.parametrize("tol", [-10, 0, 10])
def test_the_dry_hills_route_never_goes_past_the_stop(game, tol):  # noqa: F811
    lua, ns = game
    st = ns.settings.gps
    was = st.roadTolerance
    try:
        open_way, _, _ = _route(lua, ns, 10)
        r, a, b = _route(lua, ns, tol)
        assert r and r.pts
        assert not ns.WorldGrid.Overshoots(r, a[0], a[1], b[0], b[1])
        assert r.length <= 1.5 * open_way.length, (r.length, open_way.length)
    finally:
        st.roadTolerance = was
