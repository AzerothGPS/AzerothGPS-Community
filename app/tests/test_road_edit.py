"""Editing a drawn or recorded road afterwards (asked 2026-11-18 for 1.3.10, issue #640): its floor or height, its kind
(ground, floor, bridge, stairs, lift) and a stairs stretch on part of it, saved as a new track that replaces the old one;
stacked roads (a bridge over a road) kept apart and joined only at their ends; a route from under a bridge going round
to its end; safe jumps off a raised road onto a road under it with a known height."""

import math

import pytest

from test_addon_lua import env, load, nav_env  # noqa: F401 (fixtures)

pytest.importorskip("lupa")

CONT = 777  # (a continent of the tests' own: only the roads below)


def flat(lua, *vals):
    return lua.table(*vals)


def edges_of(e):
    return [e[i] for i in range(1, len(e) + 1)]


def ends_at(n, ed, x, y, r=0.6):
    return any(math.hypot(n[2 * ed[k] - 1] - x, n[2 * ed[k]] - y) <= r for k in (1, 2))


def land(lua):
    # one land road, north to south through (0, 0), and one along the bridge's way at its west end (no heights: the land)
    return lua.eval("""{ n = { 0,-200, 0,200, -200,0, -60,0 }, nz = {},
      e = { { 1,2,400,0, 0,-200, 0,200 }, { 3,4,140,0, -200,0, -60,0 } } }""")


def bridge(lua, z=15.0, time=1, kind="bridge", w=60):
    # a bridge from the land road's end at (-w, 0) east over the north-south road, ending on the ground at (w, 0)
    pts = flat(lua, -w, 0, -w + 20, 0, w - 20, 0, w, 0)
    return lua.table(op="add", continent=CONT, time=time, drawn=True, kind=kind, pts=pts,
                     zs=flat(lua, 0, z, z, 0))


def test_a_track_with_a_stairs_stretch_goes_on_as_its_pieces_and_an_edit_replaces_the_old_one(nav_env):
    lua, ns = nav_env
    R = ns.Router
    t = lua.table(op="add", continent=CONT, time=5, kind="floor", pts=flat(lua, 0, 0, 10, 0, 20, 0, 30, 0, 40, 0),
                  zs=flat(lua, 10, 10, 15, 20, 20), stairs=flat(lua, 2, 4))
    pieces = list(R.TrackPieces(t).values())
    assert [p.part for p in pieces] == [0, 1, 2]
    assert [list(p.zs.values()) for p in pieces] == [[10, 10], [10, 15, 20], [20, 20]]
    assert [bool(p.stair) for p in pieces] == [False, True, False]
    assert [p.kind for p in pieces] == ["floor", "stairs", "floor"]
    # (no stretch, or one off its points: the track itself)
    assert len(R.TrackPieces(lua.table(pts=flat(lua, 0, 0, 1, 1), zs=flat(lua, 1, 1)))) == 1
    bad = lua.table(pts=flat(lua, 0, 0, 1, 1), zs=flat(lua, 1, 1), stairs=flat(lua, 1, 5))
    assert len(R.TrackPieces(bad)) == 1
    # an edit replaces the track it edited (all of it, or one piece: `rpart`); its own pieces go on
    old = lua.table(op="add", continent=CONT, time=1, pts=flat(lua, 0, 0, 40, 0))
    walk = [lua.table(op="add", continent=CONT, time=2, part=k, pts=flat(lua, 0, k, 40, k), zs=flat(lua, 1, 1))
            for k in range(3)]
    e1 = lua.table(op="add", continent=CONT, time=3, replaces=1, pts=flat(lua, 0, 0, 40, 0), zs=flat(lua, 9, 9))
    e2 = lua.table(op="add", continent=CONT, time=4, replaces=2, rpart=1, pts=flat(lua, 0, 1, 40, 1),
                   zs=flat(lua, 9, 9))
    out = list(R.ExpandTracks(lua.table(old, *walk, e1, e2, t)).values())
    assert [(o.time, o.part) for o in out] == [(2, 0), (2, 2), (3, None), (4, None), (5, 0), (5, 1), (5, 2)]


def test_a_bridge_keeps_apart_from_the_roads_under_it_and_joins_only_at_its_ends(nav_env):
    lua, ns = nav_env
    R = ns.Router
    roads = land(lua)
    n, e = R.WithTracks(roads, lua.table(bridge(lua)), CONT)[:2]
    mine = [ed for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED]
    assert mine
    # (never split where it passes over the north-south road, nor that road split under it)
    assert not any(ends_at(n, ed, 0, 0, 3) for ed in edges_of(e))
    # (its west end on the land road's end there)
    assert any(ends_at(n, ed, -60, 0) for ed in mine)
    info = R.WithTracks(roads, lua.table(bridge(lua)), CONT)[5]
    assert info and len(list(info.raised.keys())) == len(mine)
    assert set(info.kind.values()) == {"bridge"}
    # a road drawn later under it, flat (no floor picked): it crosses under the bridge, joined to it only at the
    # bridge's ends, never where it passes under; it does join the land road it meets (a junction, as always)
    under = lua.table(op="add", continent=CONT, time=2, drawn=True, pts=flat(lua, -30, -60, -30, 60))
    n, e = R.WithTracks(roads, lua.table(bridge(lua), under), CONT)[:2]
    raised_nodes = {ed[k] for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED and abs(ed[6]) < 1 and abs(ed[len(ed)]) < 1
                    for k in (1, 2)}
    crossing = [ed for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED and abs(ed[5] + 30) < 1]
    assert crossing and not any(ed[k] in raised_nodes and abs(n[2 * ed[k]]) < 3 for ed in crossing for k in (1, 2))
    # (a plain road, no kind: as before, joined where it crosses)
    plain = lua.table(op="add", continent=CONT, time=1, drawn=True, pts=flat(lua, -60, 0, -20, 0, 20, 0, 60, 0))
    n, e = R.WithTracks(roads, lua.table(plain), CONT)[:2]
    assert any(ends_at(n, ed, 0, 0, 3) for ed in edges_of(e))


def test_a_road_under_a_bridge_with_its_own_height_stays_on_its_floor(nav_env):
    lua, ns = nav_env
    R = ns.Router
    roads = land(lua)
    under = lua.table(op="add", continent=CONT, time=2, drawn=True, kind="ground", pts=flat(lua, -30, -60, -30, 60),
                      zs=flat(lua, 3, 3))
    n, e, _, nz = R.WithTracks(roads, lua.table(bridge(lua, 25.0), under), CONT)[:4]
    low = [ed for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED and abs(ed[5] + 30) < 1]
    assert low and all(abs(nz[ed[k]] - 3) < 0.5 for ed in low for k in (1, 2) if nz[ed[k]] is not None)
    top = [ed for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED and abs(ed[6]) < 1 and abs(ed[len(ed)]) < 1]
    assert not any(ed[k] == lo[j] for ed in top for lo in low for k in (1, 2) for j in (1, 2))


@pytest.mark.parametrize("z,want", [(15.0, True), (25.0, False), (6.0, False)])
def test_a_safe_jump_off_a_bridge_onto_a_road_under_it_is_a_drop(nav_env, z, want):
    # (12 yd down: a drop, one way; 22 yd: too far to jump; 3 yd: the same floor near enough, no drop)
    lua, ns = nav_env
    R = ns.Router
    roads = land(lua)
    under = lua.table(op="add", continent=CONT, time=2, drawn=True, kind="ground", pts=flat(lua, -30, -60, -30, 60),
                      zs=flat(lua, 3, 3))
    drops = lua.table()
    roads.drop = drops
    n, e, _, nz = R.WithTracks(roads, lua.table(bridge(lua, z), under), CONT)[:4]
    got = [ed for ed in edges_of(e) if ed[4] == 3]
    assert bool(got) == want
    for ed in got:
        assert drops[ed] is not None and 0 < drops[ed] <= R.TRACK_DROP_MAX
        assert nz[ed[1]] > nz[ed[2]]  # (from the bridge down)
        assert math.hypot(ed[5] + 30, ed[6]) <= R.TRACK_DROP_STEP  # (where the bridge passes over the road)
    # (onto the land's roads, whose heights the addon doesn't know: never)
    drops = lua.table()
    roads = land(lua)
    roads.drop = drops
    _, e = R.WithTracks(roads, lua.table(bridge(lua, 12.0)), CONT)[:2]
    assert not [ed for ed in edges_of(e) if ed[4] == 3]


def round_about(lua, ns, z=15.0):
    # the land: a road north to south at x = -30 (under the bridge), and a way round from it to the bridge's west end:
    # south to y = -100, west to x = -200, north to y = 0, east to x = -160; the bridge east from there over the road
    ns.Roads[CONT] = lua.eval("""{ n = { -30,-200, -30,200, -30,-100, -200,-100, -200,0, -160,0 },
      e = { { 1,3,100,0, -30,-200, -30,-100 }, { 3,2,300,0, -30,-100, -30,200 }, { 3,4,170,0, -30,-100, -200,-100 },
            { 4,5,100,0, -200,-100, -200,0 }, { 5,6,40,0, -200,0, -160,0 } } }""")
    ns.db.tracks = lua.table(bridge(lua, z, w=160))
    ns.Router.Reset()


def route_len(r):
    p = r.pts
    return sum(math.hypot(p[i + 2] - p[i], p[i + 3] - p[i + 1]) for i in range(1, len(p) - 2, 2))


def test_from_under_a_bridge_the_route_goes_round_to_its_end(nav_env):
    lua, ns = nav_env
    R = ns.Router
    saved = ns.Roads[CONT], ns.db.tracks
    try:
        round_about(lua, ns)
        g = R.DebugGraph(CONT) or (R.NearestEdges(CONT, 0, 0) and R.DebugGraph(CONT))
        assert g.raised and g.kind
        # on the ground under it (no floor followed): up onto the bridge only by its end, the long way round
        r = R.Route(CONT, -30.0, 4.0, 0.0, 0.0, lua.table_from({"tz": 15.0}))
        assert r and not r.unconnected
        assert route_len(r) > 450, route_len(r)
        xs = [r.pts[i] for i in range(1, len(r.pts) + 1, 2)]
        assert min(xs) < -190  # (by x = -200)
        # on the bridge (its floor followed, Nav.TrackRaisedZ): along it
        r = R.Route(CONT, -30.0, 1.0, 0.0, 0.0, lua.table_from({"z": 15.0, "tz": 15.0}))
        assert r and route_len(r) < 60, route_len(r)
        # from the bridge to the road under it: never straight down (no drop onto a road with no height)
        r = R.Route(CONT, 0.0, 0.0, -30.0, 40.0, lua.table_from({"z": 15.0}))
        assert r and route_len(r) > 450, route_len(r)
    finally:
        ns.Roads[CONT], ns.db.tracks = saved
        R.Reset()


def test_the_floor_is_followed_onto_a_bridge_from_its_end_never_from_under_it(nav_env):
    lua, ns = nav_env
    R, N = ns.Router, ns.Nav
    saved = ns.Roads[CONT], ns.db.tracks
    try:
        round_about(lua, ns)
        R.NearestEdges(CONT, 0, 0)
        N.ResetRaisedTrack()
        assert N.TrackRaisedZ(CONT, -30.0, 3.0) is None  # (under it: the ground)
        assert N.TrackRaisedZ(CONT, -158.0, 1.0) is not None  # (onto it at its west end)
        z = N.TrackRaisedZ(CONT, -30.0, 1.0)
        assert z is not None and abs(z - 15) < 0.5  # (followed along it, over the road)
        assert N.FollowedZ(CONT) == z
        assert N.TrackRaisedZ(CONT, -30.0, 30.0) is None  # (off it: the ground again)
        assert N.TrackRaisedZ(CONT, -30.0, 1.0) is None  # (and back under it, not taken again)
    finally:
        N.ResetRaisedTrack()
        ns.Roads[CONT], ns.db.tracks = saved
        R.Reset()


@pytest.mark.parametrize("max_drop,dropped", [(14.0, True), (8.0, False)])
def test_a_route_off_a_bridge_jumps_down_only_when_the_fall_is_safe(nav_env, max_drop, dropped):
    # a road under the bridge edited with its height (3), the bridge 12 yd over it: off the bridge onto it by the drop
    # when the player's health takes a 12 yd fall (RouteOne's maxDrop, Nav.SafeDrop), else round by the bridge's end
    lua, ns = nav_env
    R = ns.Router
    saved = ns.Roads[CONT], ns.db.tracks
    try:
        round_about(lua, ns)
        under = lua.table(op="add", continent=CONT, time=2, drawn=True, kind="ground", pts=flat(lua, -80, -60, -80, 60),
                          zs=flat(lua, 3, 3))
        ns.db.tracks = lua.table(bridge(lua, 15.0, w=160), under)
        R.Reset()
        r = R.Route(CONT, 0.0, 0.0, -80.0, 40.0, lua.table_from({"z": 15.0, "tz": 3.0, "maxDrop": max_drop}))
        assert r and not r.unconnected
        g = R.DebugGraph(CONT)
        assert any(g.drops[ei] and 0 < g.drops[ei] <= R.TRACK_DROP_MAX for ei in range(1, len(g.e) + 1))
        assert (route_len(r) < 150) == dropped, route_len(r)  # (down where it passes over, or 300 yd round)
    finally:
        ns.Roads[CONT], ns.db.tracks = saved
        R.Reset()


def test_a_bridge_with_no_height_keeps_apart_from_the_roads_under_it(nav_env):
    # (Kooki3z 2026-11-20: a bridge between mesas with no height known is raised all the same)
    lua, ns = nav_env
    R = ns.Router
    roads = land(lua)
    b = bridge(lua)
    b.zs = None
    out = R.WithTracks(roads, lua.table(b), CONT)
    n, e, info = out[0], out[1], out[5]
    mine = [ed for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED]
    assert mine and not any(ends_at(n, ed, 0, 0, 3) for ed in edges_of(e))
    assert info and len(list(info.raised.keys())) == len(mine)


def test_a_recorded_lift_is_one_ride_and_its_top_meets_the_bridge(nav_env):
    # (Kooki3z 2026-11-20, Freewind Post: a recorded lift, every 2 yd with ramped heights, went on as short steep roads
    # whose top ones were dropped; its top never met the bridge at the tower)
    lua, ns = nav_env
    R = ns.Router
    roads = lua.eval("{ n = {}, nz = {}, e = {} }")
    br = lua.table(op="add", continent=CONT, time=1, drawn=True, kind="bridge",
                   pts=flat(lua, -40, 0, -20, 0, 0, 0), zs=flat(lua, 86, 86, 86))
    xs = [0, 2, 4, 6, 8, 10, 12, 14]
    pts, zs = [], []
    for k, x in enumerate(xs):
        pts += [x, -0.5 * k]
        zs.append(86 - (86 + 45) * k / (len(xs) - 1))
    lift = lua.table(op="add", continent=CONT, time=2, drawn=True, recorded=True, kind="lift",
                     pts=flat(lua, *pts), zs=flat(lua, *zs))
    n, e = R.WithTracks(roads, lua.table(br, lift), CONT)[:2]
    lifts = [ed for ed in edges_of(e) if ed[4] == R.SOURCE_LIFT]
    assert len(lifts) == 1, len(lifts)
    top = lifts[0]
    # its top on the bridge's end: the same node
    bridge_ends = {ed[k] for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED for k in (1, 2) if ends_at(n, ed, 0, 0, 0.6)}
    assert top[1] in bridge_ends or top[2] in bridge_ends
    assert not any(ed[4] == 3 for ed in edges_of(e))  # (no drop off the bridge onto it)


def test_bridges_ends_join_only_what_touches_them(nav_env):
    # (Kooki3z 2026-11-20: Freewind Post's two rope bridges, their ends 16 yd apart, were joined; "why are the ends of
    # the bridges being connected? I didn't do this")
    lua, ns = nav_env
    R = ns.Router
    roads = lua.eval("{ n = {}, nz = {}, e = {} }")
    a = bridge(lua, time=1)
    b = lua.table(op="add", continent=CONT, time=2, drawn=True, kind="bridge",
                  pts=flat(lua, -60, 16, -40, 16, 40, 16, 60, 16), zs=flat(lua, 15, 15, 15, 15))
    # a land road ending 10 yd off the first bridge's west end
    c = lua.table(op="add", continent=CONT, time=3, drawn=True, pts=flat(lua, -150, -10, -70, -10))
    n, e = R.WithTracks(roads, lua.table(a, b, c), CONT)[:2]
    edges = edges_of(e)

    def joins(p, q):
        return any(ends_at(n, ed, *p, 1) and ends_at(n, ed, *q, 1) for ed in edges)

    assert not joins((-60, 0), (-60, 16)) and not joins((60, 0), (60, 16))
    assert not any(ends_at(n, ed, -70, -10, 1) and ends_at(n, ed, -60, 0, 1) for ed in edges)
    # (a land road's end 2 yd off it: joined, as ever)
    d = lua.table(op="add", continent=CONT, time=4, drawn=True, pts=flat(lua, -150, 2, -62, 2))
    n, e = R.WithTracks(roads, lua.table(a, d), CONT)[:2]
    assert any(ends_at(n, ed, -60, 0, 3) for ed in edges_of(e) if ed[4] == R.SOURCE_RECORDED and ends_at(n, ed, -150, 2, 1)) \
        or any(ends_at(n, ed, -60, 0, 3) for ed in edges_of(e))
