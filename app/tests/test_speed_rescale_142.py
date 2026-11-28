"""Item 128a (1.4.2, SPF parity): a walk's weighed yards are kept with its points apart from the speed (Nav's Weighed,
N.weighedYards), so the ride check at another run speed (GetUnitSpeed: a speed buff, Travel Form) divides the same yards
again instead of weighing the walk's pieces again; its answer is kept in yards too (N.rideScale) and weighed again from
them at a new speed, no walk searched again."""

from test_map_redraw import game  # noqa: F401


def test_a_walk_s_weighed_yards_are_kept_apart_from_the_speed(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    pts = lua.eval("{ -441.8, -2596.1, -600, -2700, -800, -2900, -1000, -3100 }")
    a = N.WeighedWalk(1, pts, 7, None, 0)
    h0 = N.weighedHits
    b = N.WeighedWalk(1, pts, 14, None, 0)
    assert N.weighedHits == h0 + 1  # (the second speed: the same yards, not weighed again)
    assert abs(a - 2 * b) < 1e-6
    # (another ground blocked: weighed again)
    N.WeighedWalk(1, pts, 7, None, 100)
    assert N.weighedHits == h0 + 1


def test_the_walks_are_weighed_again_after_the_costs_change(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    pts = lua.eval("{ -441.8, -2596.1, -600, -2700, -800, -2900 }")
    N.WeighedWalk(1, pts, 7, None, 0)
    h0 = N.weighedHits
    st = ns.settings.gps
    was = st.roadTolerance
    st.roadTolerance = (was or 0) + 5  # (in the costs' key, WorldGrid.CostKey)
    try:
        N.WeighedWalk(1, pts, 7, None, 0)
        assert N.weighedHits == h0
    finally:
        st.roadTolerance = was


def test_a_ride_check_s_answer_is_kept_in_yards(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    assert N.RIDE_RESCALE > 0
    assert N.rideScale is not None
