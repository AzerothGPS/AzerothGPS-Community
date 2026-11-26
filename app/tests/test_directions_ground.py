"""Directions from the ground (1.4.1, worker item 113, Kooki3z's grid ideas: "do all except the L ones ..."):

(a) lines from what the route walks on: "Take the ramp down" where it goes down a built ramp (a dock's, a capital's
    walkway; not a hillside or a mesa's path, which is just the walk), a drop with its fall ("Jump down here (34 yd)"),
    "Enter the cave" at the mouth of a cave walked into off the roads (by the ground over it), and no "Join the road" /
    "Leave the cave, Enter the cave" chatter at a cave's mouth or inside it;
(b) "Over the ridge, round to the left": a stop close by the player can't see for the ground between (or, on the world
    grid, a wall), and which way round the route goes;
(c) "Leave the cave, then mount up": out of a cave or a building onto a long walk outdoors, while not mounted.

Item 101's calmer line is kept: the replayed walks in test_directions_calm.py change their line no more often than
before (8 / 9 on this base; Brill to Tarren Mill 21)."""

import math

import pytest

from test_cave_inside_routes import START as WC_START, STOP as WC_STOP, floor_inside, settle


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    lua.execute("AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    yield lua, ns
    st.worldGrid, st.cityGrid = False, False


def _said(ns, path, horizon=math.inf):
    ms = ns.Turns.Maneuvers(path, "Stop 1", horizon)
    return [(str(ms[i].kind), str(ms[i].text), ms[i].dist) for i in range(1, len(ms) + 1)], ms


def _route_path(lua, ns, start, stop, z=None, cont=1):
    _, r, _ = settle(lua, ns, start, stop, "nil" if z is None else z, cont=cont, ticks=400)
    assert r is not None and r.parts, "no route"
    return ns.Turns.Path(r)


# (a) ramps

@pytest.mark.parametrize("start,stop,z,cont,want", [
    # (Booty Bay: from the upper boardwalk down to the lower dock. The stop's height is given: with none, its end is
    # the dry surface first (item 106's floor evidence), the upper boardwalk there, and the route never goes down)
    ((-14300.0, 450.0), (-14450.0, 500.0), 0, 0, "Take the ramp down"),
    # (Orgrimmar: the Valley of Strength's walkway up toward the Drag)
    ((1625.0, -4376.0), (1640.0, -4220.0), None, 1, "Take the ramp up"),
], ids=["booty_bay_down_to_the_dock", "orgrimmar_walkway_up"])
def test_a_built_ramp_is_a_ramp(game, start, stop, z, cont, want):
    lua, ns = game
    path = _route_path(lua, ns, start, stop, z, cont=cont)
    if z is not None:  # (the route does go from the boardwalk down to the dock)
        assert path.fz[1] - path.fz[len(path.cum)] > 15, (path.fz[1], path.fz[len(path.cum)])
    said, _ = _said(ns, path)
    ramps = [(t, d) for k, t, d in said if k == "ramp"]
    assert ramps and ramps[0][0] == want, said
    assert not [d for k, t, d in said if k == "stairs" and abs(d - ramps[0][1]) < 5], said


@pytest.mark.parametrize("start,stop,z", [
    ((-2917.0, -257.0), (-2324.0, -395.0), None),  # (Red Cloud Mesa's road down: the mesa's own side)
    (WC_STOP, WC_START, None),  # (down the hill over the Wailing Caverns, 70 yd in 150)
], ids=["red_cloud_mesa", "wailing_caverns_hill"])
def test_a_hillside_is_no_ramp(game, start, stop, z):
    lua, ns = game
    path = _route_path(lua, ns, start, stop, z)
    fz = [path.fz[i] for i in range(1, len(path.cum) + 1) if path.fz[i] is not False]
    assert max(fz) - min(fz) > 50  # (it does go a long way down)
    said, _ = _said(ns, path)
    assert not [t for k, t, _d in said if k in ("ramp", "stairs")], said


def _hand_path(lua, ns, pts, kinds, fz, cont=0):
    flat = []
    for x, y in pts:
        flat += [x, y]
    part = lua.table(cont=cont, pts=lua.table(*flat), kinds=lua.table(*kinds), fz=lua.table(*fz), stop=1)
    return ns.Turns.Path(lua.table(parts=lua.table(part), legs=lua.table(lua.table(walk=True))))


X0, Y0 = -11500.0, 2500.0  # (out at sea, west of Westfall: no roads, junctions, bridges or places)


def test_a_ramp_is_said_only_on_something_built_and_its_bends_are_the_ramps(game):
    lua, ns = game
    N = ns.Nav
    # (flat 100 yd, then 30 yd down 14 over a bend, then flat 200 yd on)
    pts = [(X0, Y0), (X0 + 100, Y0), (X0 + 115, Y0 + 2), (X0 + 125, Y0 + 15), (X0 + 125, Y0 + 215)]
    fz = [20, 20, 13, 6, 6]
    was = N.GroundAt
    swims = N.SwimSpans
    N.SwimSpans = None
    try:
        lua.execute("AGPS_NS.Nav.GroundAt = function() return -30 end")  # (the sea floor far under it: built)
        said, ms = _said(ns, _hand_path(lua, ns, pts, [1, 1, 1, 1], fz))
        assert [t for k, t, _d in said if k == "ramp"] == ["Take the ramp down"], said
        assert not [t for k, t, _d in said if k == "turn"], said  # (the bend on it is the ramp's)
        m = [ms[i] for i in range(1, len(ms) + 1) if str(ms[i].kind) == "ramp"][0]
        m.dist = 40
        fmt = lua.eval("function(d) return string.format('%d yd', d) end")
        assert str(ns.Turns.NowText(m, fmt)) == "Continue straight, then take the ramp down in 40 yd"
        # (the ground itself going down so: a hillside, the walk)
        lua.execute("""AGPS_NS.Nav.GroundAt = function(c, x, y)
          if x <= -11400 then return 20 elseif x >= -11375 then return 6 end
          return 20 - (x + 11400) / 25 * 14
        end""")
        said, _ = _said(ns, _hand_path(lua, ns, pts, [1, 1, 1, 1], fz))
        assert not [t for k, t, _d in said if k == "ramp"], said
        # (and a bump, 6 yd: nothing)
        lua.execute("AGPS_NS.Nav.GroundAt = function() return -30 end")
        said, _ = _said(ns, _hand_path(lua, ns, pts, [1, 1, 1, 1], [20, 20, 17, 14, 14]))
        assert not [t for k, t, _d in said if k == "ramp"], said
    finally:
        N.GroundAt = was
        N.SwimSpans = swims


# (a) drops with their fall

def test_a_drop_says_how_far_it_falls(game):
    lua, ns = game
    T, R = ns.Turns, ns.Router
    m = T.DropWords(lua.table(dist=0, kind="drop", dropYd=33.6))
    assert str(m.text) == "Jump down here (34 yd)" and str(m.mid) == "jump down (34 yd)"
    m.dist = 120
    fmt = lua.eval("function(d) return string.format('%d yd', d) end")
    was = ns.FallSpells
    ns.FallSpells = None  # (no fall spell in the way: the words as they are)
    try:
        assert str(T.NowText(m, fmt)) == "Continue straight, then jump down (34 yd) in 120 yd"
        m.dist = 3
        assert str(T.NowText(m, fmt)) == "Jump down here (34 yd)"
    finally:
        ns.FallSpells = was
    # (its fall unknown: as before)
    assert str(T.DropWords(lua.table(dist=0, kind="drop")).text) == "Jump down here"
    # (on a route: the drop off the Wailing Caverns' hill, its fall noted where the grid made it)
    path = _route_path(lua, ns, WC_STOP, WC_START)
    said, _ = _said(ns, path)
    drops = [t for k, t, _d in said if k == "drop"]
    assert drops and all(t.startswith("Jump down here (") and t.endswith(" yd)") for t in drops), said
    assert R.KIND_DROP


# (a) caves by the ground, and no chatter at their mouths

def test_into_the_wailing_caverns_the_mouth_says_enter_the_cave_once(game):
    lua, ns = game
    z = floor_inside(ns, *WC_STOP)
    path = _route_path(lua, ns, WC_START, WC_STOP, z)
    said, _ = _said(ns, path)
    places = [t for k, t, _d in said if k == "place"]
    # (once: no "Leave the cave", "Enter the cave" 3 yd apart deep inside, nor "Join the road" with it at the mouth)
    assert places == ["Enter the cave"], said
    at = [d for k, t, d in said if t == "Enter the cave"][0]
    assert not [t for k, t, d in said if k in ("join", "leave") and abs(d - at) < 20], said


def test_a_walk_off_the_roads_into_a_cave_says_so_at_its_mouth(game):
    """A walk on the world grid's own floors (no cave road) from the land into a cave: in where its floor goes under the
    ground over the cave's grid, out where it comes up again."""
    lua, ns = game
    T, WG = ns.Turns, ns.WorldGrid
    # (the Wailing Caverns' way in, as walked: its points from the route in, all as grid walks)
    z = floor_inside(ns, *WC_STOP)
    road = _route_path(lua, ns, WC_START, WC_STOP, z)
    pts, fz = [], []
    for i in range(1, len(road.cum) + 1):
        if road.cum[i] > 420:
            break
        pts.append((road.pts[2 * i - 1], road.pts[2 * i]))
        fz.append(road.fz[i])
    path = _hand_path(lua, ns, pts, [1] * (len(pts) - 1), fz, cont=1)
    said, _ = _said(ns, path)
    assert [t for k, t, _d in said if k == "place"] == ["Enter the cave"], said
    d = [d for k, t, d in said if k == "place"][0]
    x, y = T.PointAt(path, d + 15)
    assert WG.CaveAt(1, x, y), (x, y)
    # (and back out the same way: "Leave the cave", and with a long walk outdoors after it, mount up)
    back = list(reversed(pts)) + [(pts[0][0] - 150.0, pts[0][1])]
    path = _hand_path(lua, ns, back, [1] * (len(back) - 1), list(reversed(fz)) + [fz[0]], cont=1)
    said, ms = _said(ns, path)
    assert [t for k, t, _d in said if k == "place"] == ["Leave the cave"], said
    m = [ms[i] for i in range(1, len(ms) + 1) if str(ms[i].kind) == "place"][0]
    assert m.mountAfter


# (c) mount after the door

def test_out_of_a_cave_onto_a_long_walk_says_to_mount_while_on_foot(game):
    lua, ns = game
    T, N = ns.Turns, ns.Nav
    m = lua.table(dist=30, kind="place", place="cave", enter=False, mountAfter=True)
    T.Words(m, "leave_cave")
    fmt = lua.eval("function(d) return string.format('%d yd', d) end")
    rank = N.RidingRank
    try:
        lua.execute("AGPS_NS.Nav.RidingRank = function() return 75 end; IsMounted = function() return false end")
        assert str(T.NowText(m, fmt)) == "Continue straight, then leave the cave, then mount up in 30 yd"
        m.dist = 2
        assert str(T.NowText(m, fmt)) == "Leave the cave, then mount up"
        # (on a mount already, or no riding: just the way out)
        lua.execute("IsMounted = function() return true end")
        assert str(T.NowText(m, fmt)) == "Leave the cave"
        lua.execute("IsMounted = function() return false end; AGPS_NS.Nav.RidingRank = function() return 0 end")
        assert str(T.NowText(m, fmt)) == "Leave the cave"
        # (a short walk out to the stop: no mounting for it)
        lua.execute("AGPS_NS.Nav.RidingRank = function() return 75 end")
        m.mountAfter = None
        assert str(T.NowText(m, fmt)) == "Leave the cave"
    finally:
        N.RidingRank = rank
        lua.execute("IsMounted = function() return false end")


def test_starting_indoors_the_way_out_of_the_building_is_said(game):
    """The game says the player's indoors, in one of Data/Indoors.lua's buildings, and the grid's own walk leads out
    (no inside road): "Leave the building" where it goes out of the building's walls, mount up after it."""
    lua, ns = game
    T, N = ns.Turns, ns.Nav
    b = None
    lst = ns.Indoors[1]
    for i in range(1, len(lst) + 1):
        if lst[i].x and str(lst[i][1]).startswith("Bloodhoof Village: taurenlonghouse"):
            b = lst[i]
    assert b is not None
    pts = [(b.x, b.y), (b.x + b.r * 0.5, b.y), (b.x + b.r + 10, b.y), (b.x + b.r + 250, b.y)]
    fz = [b.floors[1]] * 4
    was = N.Indoors
    try:
        lua.execute("AGPS_NS.Nav.Indoors = function() return true end")
        said, ms = _said(ns, _hand_path(lua, ns, pts, [1, 1, 1], fz, cont=1))
        assert [t for k, t, _d in said if k == "place"] == ["Leave the building"], said
        d = [d for k, t, d in said if k == "place"][0]
        assert b.r * 0.4 <= d <= b.r + 10, (d, b.r)
        m = [ms[i] for i in range(1, len(ms) + 1) if str(ms[i].kind) == "place"][0]
        assert m.mountAfter
        # (not indoors: nothing said, the walk starts outside it)
        lua.execute("AGPS_NS.Nav.Indoors = function() return false end")
        said, _ = _said(ns, _hand_path(lua, ns, pts, [1, 1, 1], fz, cont=1))
        assert not [t for k, t, _d in said if k == "place"], said
    finally:
        N.Indoors = was


# (b) over the ridge

RX, RY = -1000.0, -2400.0  # (the Barrens, open land)


def _ridge(lua, ns, hill, route_pts, walk=None):
    """The hint for a stop 100 yd north of the player, a hill `hill` yd high halfway (the ground made up), the route as
    given."""
    N = ns.Nav
    flat = []
    for x, y in route_pts:
        flat += [x, y]
    lua.execute(f"""AGPS_NS.Nav.GroundAt = function(c, x, y)
      local d = math.abs(x - ({RX} + 50))
      return 10 + math.max(0, {hill} * (1 - d / 25))
    end""")
    if not (N.dest and N.dest.x == RX + 100 and N.dest.y == RY):  # (the same stop kept: its hint held, N.ridgeKept)
        N.dest = lua.eval(f"{{ x = {RX + 100}, y = {RY}, cont = 1 }}")
    N.route = lua.table(parts=lua.table(lua.table(pts=lua.table(*flat), cont=1)), walkYards=walk or 300,
                        legs=lua.table(lua.table(walk=True)))
    return N.RidgeHint(RX, RY, 1)


def test_a_stop_hidden_over_a_ridge_says_which_way_round(game):
    lua, ns = game
    N = ns.Nav
    saved = (N.GroundAt, N.PlayerHeightNear, N.dest, N.route)
    try:
        lua.execute("AGPS_NS.Nav.PlayerHeightNear = function(c, x, y) return AGPS_NS.Nav.GroundAt(c, x, y) end")
        N.ridgeKept = None
        # (round by the west: Y is west, the left looking north)
        left = [(RX, RY), (RX + 20, RY + 60), (RX + 80, RY + 60), (RX + 100, RY)]
        assert tuple(_ridge(lua, ns, 12, left)) == ("ridge", "left")
        assert "Over the ridge, round to the left" in str(N.RidgeText(RX + 0.5, RY, 1))
        N.ridgeKept = None
        right = [(RX, RY), (RX + 20, RY - 60), (RX + 80, RY - 60), (RX + 100, RY)]
        assert tuple(_ridge(lua, ns, 12, right)) == ("ridge", "right")
        N.ridgeKept = None
        over = [(RX, RY), (RX + 100, RY)]
        kind, side = _ridge(lua, ns, 12, over, walk=105)
        assert (kind, side) == ("ridge", None)
        assert "Over the ridge, up and over" in str(N.RidgeText(RX, RY, 1))
        # (flat between: nothing)
        N.ridgeKept = None
        assert _ridge(lua, ns, 0, left)[0] is None
        # (a low crest, 2 yd over the line of sight: shown from RIDGE_SHOW_Z, kept down to RIDGE_KEEP_Z, no flicking
        # on the way up it)
        N.ridgeKept = None
        assert _ridge(lua, ns, 4, left)[0] is None
        N.ridgeKept = None
        assert _ridge(lua, ns, 12, left)[0] == "ridge"
        lua.execute("AGPS_T = (AGPS_T or 0) + 5")
        assert _ridge(lua, ns, 4, left)[0] == "ridge"
        # (too far, or right there: nothing)
        N.ridgeKept = None
        N.dest = lua.eval(f"{{ x = {RX + 400}, y = {RY}, cont = 1 }}")
        assert N.RidgeHint(RX, RY, 1)[0] is None
    finally:
        N.GroundAt, N.PlayerHeightNear, N.dest, N.route = saved
        N.ridgeKept = None


def test_the_ridge_hint_shows_with_the_height_hint(game):
    lua, ns = game
    N = ns.Nav
    saved = (N.GroundAt, N.PlayerHeightNear, N.dest, N.route, N.HeightHint, N.SlopeText)
    try:
        lua.execute("AGPS_NS.Nav.PlayerHeightNear = function(c, x, y) return AGPS_NS.Nav.GroundAt(c, x, y) end")
        lua.execute("AGPS_NS.Nav.HeightHint = function() return 'up', 20 end")
        N.ridgeKept = None
        _ridge(lua, ns, 12, [(RX, RY), (RX + 20, RY + 60), (RX + 80, RY + 60), (RX + 100, RY)])
        N.ridgeKept = None
        t = str(N.HeightText(RX, RY, 1))
        assert "Over the ridge, round to the left" in t and "Above you, 20 yd up" in t, t
        assert t.index("Over the ridge") < t.index("Above you")
    finally:
        N.GroundAt, N.PlayerHeightNear, N.dest, N.route, N.HeightHint, N.SlopeText = saved
        N.ridgeKept = None


def test_a_stop_behind_a_wall_on_the_world_grid_says_which_way_round(game):
    """Level ground (no ridge), the world grid has no straight walk to the stop (WorldGrid.Clear: a wall's cell sides
    have no links) and the route goes well round: behind a wall."""
    lua, ns = game
    N, WG = ns.Nav, ns.WorldGrid
    saved = (N.GroundAt, N.PlayerHeightNear, N.dest, N.route, WG.Clear)
    try:
        lua.execute("AGPS_NS.Nav.PlayerHeightNear = function(c, x, y) return AGPS_NS.Nav.GroundAt(c, x, y) end")
        lua.execute("AGPS_NS.WorldGrid.Clear = function() return false end")
        N.ridgeKept = None
        right = [(RX, RY), (RX + 10, RY - 50), (RX + 70, RY - 50), (RX + 60, RY)]
        flat = []
        for x, y in right:
            flat += [x, y]
        lua.execute("AGPS_NS.Nav.GroundAt = function() return 10 end")
        N.dest = lua.eval(f"{{ x = {RX + 60}, y = {RY}, cont = 1 }}")
        N.route = lua.table(parts=lua.table(lua.table(pts=lua.table(*flat), cont=1)), walkYards=180,
                            legs=lua.table(lua.table(walk=True)))
        assert tuple(N.RidgeHint(RX, RY, 1)) == ("wall", "right")
        assert "Behind a wall, round to the right" in str(N.RidgeText(RX, RY, 1))
        # (the route about straight there: no wall said)
        N.ridgeKept = None
        N.route.walkYards = 70
        assert N.RidgeHint(RX, RY, 1)[0] is None
        # (open across on the grid: none either)
        N.ridgeKept = None
        N.route.walkYards = 180
        lua.execute("AGPS_NS.WorldGrid.Clear = function() return true end")
        assert N.RidgeHint(RX, RY, 1)[0] is None
    finally:
        N.GroundAt, N.PlayerHeightNear, N.dest, N.route, WG.Clear = saved
        N.ridgeKept = None
