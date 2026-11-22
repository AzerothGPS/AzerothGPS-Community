"""Cliff walls (1.3.10, issue #685, phase 3): a wall's sections can be cliffs with a ground height on each side. Same
height both sides (within a step): open. Low side to high side: blocked, routes go round. High side to low side: a
safe drop (within the safe-jump limit) is walked, an unsafe one blocks both ways. The sides ride along in exports and
imports, and the wall tools' Edit Wall sets them, filled in from the map's ground."""

import json

import pytest

from test_addon_lua import env, load, nav_env  # noqa: F401 (fixtures)

pytest.importorskip("lupa")

# open ground in Durotar (test_a_drawn_wall_blocks_walking_but_not_roads): a wall along y = -3975 from x = -1030 to
# -870 (drawn toward +x: its left is +y, `b`'s side; its right -y, `a`'s side)
A, B = (-945.0, -4050.0), (-945.0, -3900.0)
WALL = "{ -1030,-3975, -950,-3975, -870,-3975 }"


def cliff(lua, ns, left, right):
    ns.db = lua.eval("{ tracks = { { op = 'wall', drawn = true, continent = 1, time = 1, pts = %s, kind = 'cliff', "
                     "cl = { %s, %s, %s }, cr = { %s, %s, %s } } } }" % (WALL, left, left, left, right, right, right))
    ns.Passability.RefreshWalls()


@pytest.fixture
def walls(nav_env):
    lua, ns = nav_env
    load(lua, ns, "Data/Terrain.lua", "Passability.lua")
    yield lua, ns
    ns.db = lua.eval("{}")
    ns.Passability.RefreshWalls()


def test_a_cliff_with_a_safe_drop_is_walked_down_but_not_up(walls):
    lua, ns = walls
    P = ns.Passability
    cliff(lua, ns, 30, 20)  # (b's side 10 yd over a's)
    assert P.SegmentCost(1, *B, *A) is not None  # (down: the drop is safe)
    assert P.CrossesWall(1, *A, *B) and P.SegmentCost(1, *A, *B) is None  # (up: no)
    c, path = P.FindPath(1, *A, *B)
    assert c is not None and c > 150  # (round its end)
    pts = [(path[i], path[i + 1]) for i in range(1, len(path), 2)]
    assert not any(P.CrossesWall(1, *p, *q) for p, q in zip(pts, pts[1:]))


def test_an_unsafe_drop_blocks_both_ways_and_the_same_height_is_open(walls):
    lua, ns = walls
    P = ns.Passability
    cliff(lua, ns, 45, 20)  # (25 yd: more than the safe-jump limit)
    assert P.CrossesWall(1, *A, *B) and P.CrossesWall(1, *B, *A)
    assert P.SegmentCost(1, *B, *A) is None
    cliff(lua, ns, 21, 20)  # (within a step: no cliff at all there)
    assert not P.CrossesWall(1, *A, *B) and not P.CrossesWall(1, *B, *A)
    assert P.SegmentCost(1, *A, *B) is not None
    # one section a cliff, one plain: the plain one still blocks both ways
    ns.db = lua.eval("{ tracks = { { op = 'wall', drawn = true, continent = 1, time = 1, pts = %s, kind = 'cliff', "
                     "cl = { 21, 21, false }, cr = { 20, 20, false } } } }" % WALL)
    P.RefreshWalls()
    assert not P.CrossesWall(1, -990.0, -4050.0, -990.0, -3900.0)
    assert P.CrossesWall(1, -910.0, -4050.0, -910.0, -3900.0) and P.CrossesWall(1, -910.0, -3900.0, -910.0, -4050.0)


def test_routes_go_round_a_cliff_from_its_low_side_and_drop_from_its_high_side(env):
    lua, ns = env
    lua.execute("GetTime = function() return 0 end")
    ns.db = lua.eval("{}")
    load(lua, ns, "Data/Terrain.lua", "Passability.lua", "Data/Maps.lua", "Data/Roads.lua", "Router.lua")
    R = ns.Router
    R.WARM = False
    pump = lua.eval("function(R) while R.HasWork() do R.Pump(math.huge, function() return 0 end) end end")

    def route(a, b):
        for _ in range(20):
            r = R.Route(1, a[0], a[1], b[0], b[1], lua.table(offroad=True))
            if not r.pending:
                return r
            pump(R)
        return r

    try:
        cliff(lua, ns, 30, 20)
        R.Reset()
        down, up = route(B, A), route(A, B)
        assert not down.pending and not up.pending and not up.noWay
        assert down.length < 160 < 200 < up.length, (down.length, up.length)
        cliff(lua, ns, 45, 20)  # (an unsafe drop: round it both ways)
        R.Reset()
        assert route(B, A).length > 200
    finally:
        ns.db = lua.eval("{}")
        ns.Passability.RefreshWalls()
        R.Reset()


def test_a_cliffs_sides_ride_along_in_the_share_lines_and_the_import(walls, tmp_path):
    lua, ns = walls
    load(lua, ns, "MapText.lua")
    cliff(lua, ns, 30, 20)
    t = ns.db.tracks[1]
    line = ns.MapText.RoadLine(t)
    assert line.startswith("R wall ") and " kind=cliff" in line and " cl=30.0,30.0,30.0" in line
    kind, rec = ns.MapText.ParseLine(line)
    assert kind == "wall" and rec.kind == "cliff" and [rec.cr[k] for k in range(1, 4)] == [20, 20, 20]
    from azerothgps.roads.tracks import import_tracks, load_overrides, parse_shared, walls as walls_of

    shared = parse_shared(line)
    assert shared[0]["kind"] == "cliff" and shared[0]["cl"] == [30, 30, 30]
    wtf = tmp_path / "WTF" / "ACC" / "SavedVariables"
    wtf.mkdir(parents=True)
    (wtf / "AzerothGPS.lua").write_text(
        'AzerothGPSDB = { tracks = { { op = "wall", drawn = true, continent = 1, zone = "Durotar", time = 1700000000, '
        'pk = "-1030 -3975 -950 -3975 -870 -3975", kind = "cliff", cl = { 30, 30, false }, cr = { 20, 20, false } } } }\n',
        encoding="utf-8")
    ov = tmp_path / "overrides"
    assert import_tracks(tmp_path / "WTF", ov) == 1
    p = load_overrides(ov / "roads_1.geojson")["features"][0]["properties"]
    assert p["kind"] == "cliff" and p["cl"] == [30, 30, None] and p["cr"] == [20, 20, None]
    w = walls_of(ov)[1][0]
    assert w.kind == "cliff" and w.cl == [30, 30, None]
    json.dumps(p)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def click(b):
    b.GetScript(b, "OnClick")(b)
