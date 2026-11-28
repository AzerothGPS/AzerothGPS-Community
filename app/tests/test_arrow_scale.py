"""The arrow's distances scaled to the grid's cell size (1.4.2, item 144, Kooki3z 2026-11-27: "in cities (make it anywhere
using the smaller grid size tiles) the arrow distance for correcting should be halved or scaled to the tile size, the
forecast is too far for cities"). On a stretch of the route over a finer grid than the world's 8.33 yd cells (a
capital's 3 yd, Undercity's and Thunder Bluff's 2, a cave's 2, a building's) the look-ahead, "now", the off-the-route
distance and the unstuck aim are the cell's share of the world's (at most half: Turns.CellScale); out on the land
they're as before; and over a city's gate the look-ahead grows along the route (Turns.AheadAlong), no jump."""

import math

import pytest

pytest.importorskip("lupa.lua51")

GRYSHKA = (1, 1634.0, -4439.4, 15.5)  # Orgrimmar's inn, the Valley of Strength
THRALL = (1, 1920.1, -4125.7, 43.0)  # Grommash Hold
ZEVROST = (1, 1849.0, -4360.4, -14.8)  # the Cleft of Shadow
DUNGAR = (0, -8835.8, 490.1, 109.7)  # Stormwind's gryphon master
LAURENA = (0, -8512.4, 862.4, 109.9)  # its cathedral
DUROTAR = (1, 1250.0, -4400.0, None)  # Durotar, west of Orgrimmar's gate
ELWYNN = (0, -9200.0, 330.0, None)  # the road to Stormwind's gate, by the lake
WORLD = 25 / 3


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    yield lua, ns
    ns.settings.gps.cityGrid = False
    ns.settings.gps.worldGrid = False


def _route(lua, ns, a, b):
    return ns.Router.Route(a[0], a[1], a[2], b[1], b[2], lua.table(z=a[3], tz=b[3]))


def _part(lua, r, cont):
    return lua.table(cont=cont, pts=r.pts, kinds=r.kinds, fz=r.fz, zs=r.zs, stop=1)


def _path(lua, ns, part):
    return ns.Turns.Path(lua.table(parts=lua.table(part), legs=lua.table(lua.table(walk=True))))


# (the walk from `s` yards along a part on, as Nav trims it under the player: its point there first)
TRIM = """function(path, s)
  local T = AGPS_NS.Turns
  local x, y = T.PointAt(path, s)
  local pts, kinds, fz = { x, y }, {}, {}
  local f0 = false
  for i = 2, #path.cum do
    if path.cum[i] > s then
      if #fz == 0 then
        local a, b = path.fz[i - 1], path.fz[i]
        local seg = path.cum[i] - path.cum[i - 1]
        f0 = type(a) == "number" and type(b) == "number" and seg > 0 and a + (b - a) * (s - path.cum[i - 1]) / seg or a
        fz[1] = f0
      end
      pts[#pts + 1], pts[#pts + 2] = path.pts[2 * i - 1], path.pts[2 * i]
      kinds[#kinds + 1] = path.kinds[i - 1] or 1
      fz[#fz + 1] = path.fz[i]
    end
  end
  local part = { cont = path.cont, pts = pts, kinds = kinds, fz = fz, stop = 1 }
  return T.Path({ parts = { part }, legs = { { walk = true } } }), x, y
end"""


def _inside(ns, cont, path, name, s0, s1):
    T, CG = ns.Turns, ns.CityGrid
    s = s0
    while s <= s1:
        x, y = T.PointAt(path, s)
        if CG.CityFor(cont, x, y) != name:
            return False
        s += 2
    return True


def _city_stretch(ns, cont, path, name, need):
    """The first spot along the path with `need` yards of the route on in the city."""
    s = 0.0
    while s + need <= path.total:
        if _inside(ns, cont, path, name, max(0, s - 16), s + need):
            return s
        s += 4
    return None


@pytest.mark.parametrize("a, b, name, cell", [(GRYSHKA, THRALL, "Orgrimmar", 3), (DUNGAR, LAURENA, "Stormwind City", 3)])
def test_in_a_capital_the_aim_and_off_route_are_the_cell_s_share(game, a, b, name, cell):
    lua, ns = game
    T, N = ns.Turns, ns.Nav
    st = ns.settings.gps
    st.cityGrid = True
    try:
        r = _route(lua, ns, a, b)
        assert r.cityGrid == name
        part = _part(lua, r, a[0])
        path = _path(lua, ns, part)
        k = cell / WORLD
        s = _city_stretch(ns, a[0], path, name, T.OPEN_LOOKAHEAD * k + 20)
        assert s is not None, "no stretch of the route in the city"
        assert T.AheadAlong(path, s, T.OPEN_LOOKAHEAD) - s == pytest.approx(T.OPEN_LOOKAHEAD * k, rel=0.02)
        assert T.AheadAlong(path, s, T.LOOKAHEAD) - s == pytest.approx(T.LOOKAHEAD * k, rel=0.02)
        assert T.ScaleAt(path, s + 5) == pytest.approx(k, rel=0.02)
        # (Nav's off-the-route distance there: its piece's)
        cum = [0.0]
        pts = [r.pts[i] for i in range(1, len(r.pts) + 1)]
        for i in range(2, len(pts) // 2 + 1):
            cum.append(cum[-1] + math.hypot(pts[2 * i - 2] - pts[2 * i - 4], pts[2 * i - 1] - pts[2 * i - 3]))
        i = max(j for j in range(1, len(cum)) if cum[j - 1] <= s + 5)
        fake = lua.table(fullFirst=part, cum=lua.table(*cum))
        assert N.OffRouteYd(fake, i, 0) == pytest.approx(N.OFF_ROUTE_YD * k, rel=0.05)
        assert N.OffRouteYd(fake, i, 0) < N.OFF_ROUTE_YD / 2
        # (the arrow's own aim: no further than the look-ahead's share along the route from the player)
        trim, px, py = lua.eval(TRIM)(path, s)
        tx, ty = T.Target(trim, px, py)
        assert math.hypot(tx - px, ty - py) <= T.OPEN_LOOKAHEAD * k * 1.4 + 1
        # ("now" there: half NOW_YD at the least)
        m = lua.table(dist=0)
        T.MarkScale(path, lua.table(lua.table(dist=s)))
        assert T.NowYd(lua.table(nowK=k)) == pytest.approx(T.NOW_YD * 0.5)
        assert T.NowYd(m) == T.NOW_YD
    finally:
        st.cityGrid = False


def test_undercity_and_caves_two_yard_cells(game):
    lua, ns = game
    T = ns.Turns
    st = ns.settings.gps
    st.cityGrid = True
    try:
        assert T.CellAt(10001, 1567.1, 266.3, -43.0) == 2
        assert T.CellScale(2) == pytest.approx(2 / WORLD)
        assert T.CellScale(3) == pytest.approx(3 / WORLD)
        assert T.CellScale(5) == 0.5  # (at least halved)
        assert T.CellScale(None) == 1 and T.CellScale(WORLD) == 1
        line = lua.table(cont=10001, pts=lua.table(1560.0, 200.0, 1480.0, 304.0), kinds=lua.table(1), stop=1)
        path = _path(lua, ns, line)
        assert T.AheadAlong(path, 10, T.OPEN_LOOKAHEAD) - 10 == pytest.approx(T.OPEN_LOOKAHEAD * 2 / WORLD, rel=0.01)
        # (a building's grid, when the game has one there: WorldGrid.BuildingCellAt)
        WG = ns.WorldGrid
        WG.BuildingCellAt = lua.eval("function(cont, x, y) if cont == 1 and x > 0 and x < 10 then return 2 end end")
        try:
            assert T.CellAt(1, 5.0, 5.0, 0.0) == 2
        finally:
            WG.BuildingCellAt = None
    finally:
        st.cityGrid = False


def test_out_on_the_land_nothing_changes(game):
    lua, ns = game
    T = ns.Turns
    st = ns.settings.gps
    # (a gently curving walk in Durotar, east of Orgrimmar's gate)
    pts = []
    for i in range(0, 61):
        s = i * 5.0
        pts += [900.0 + s, -4600.0 + 25 * math.sin(s / 90)]
    part = lua.table(cont=1, pts=lua.table(*pts), kinds=lua.table(*([1] * 60)), stop=1)
    aims = []
    for on in (False, True):
        st.cityGrid, st.worldGrid = on, on
        try:
            path = _path(lua, ns, part)
            assert T.AheadAlong(path, 7, T.OPEN_LOOKAHEAD) == pytest.approx(7 + T.OPEN_LOOKAHEAD, abs=1e-6)
            assert T.ScaleAt(path, 40) == 1
            aims.append(tuple(T.Target(path, 900.0, -4600.0)))
        finally:
            st.cityGrid, st.worldGrid = False, False
    assert aims[0] == pytest.approx(aims[1], abs=1e-6)


def _bearing_jumps(lua, ns, path, step=2.0):
    T = ns.Turns
    trim = lua.eval(TRIM)
    out, aims, last, s = [], [], None, 0.0
    while s < path.total - 40:
        p, px, py = trim(path, s)
        tx, ty = T.Target(p, px, py)
        b = math.atan2(ty - py, tx - px)
        if last is not None:
            d = abs((b - last + math.pi) % (2 * math.pi) - math.pi)
            out.append(math.degrees(d))
        aims.append(T.AheadAlong(p, 0, T.OPEN_LOOKAHEAD))
        last = b
        s += step
    return out, aims


@pytest.mark.parametrize("a, b, name", [(DUROTAR, ZEVROST, "Orgrimmar"), (ZEVROST, DUROTAR, "Orgrimmar"),
                                         (ELWYNN, DUNGAR, "Stormwind City"), (DUNGAR, ELWYNN, "Stormwind City")])
def test_crossing_a_city_gate_the_arrow_doesnt_jump(game, a, b, name):
    lua, ns = game
    T = ns.Turns
    st = ns.settings.gps
    st.cityGrid = True
    try:
        r = _route(lua, ns, a, b)
        path = _path(lua, ns, _part(lua, r, a[0]))
        CG = ns.CityGrid
        ins = []
        s = 0.0
        while s < path.total:
            x, y = T.PointAt(path, s)
            ins.append(CG.CityFor(a[0], x, y) == name)
            s += 4
        assert any(ins) and not all(ins), "the route doesn't cross the gate"
        jumps, aims = _bearing_jumps(lua, ns, path)
        was = T.WORLD_CELL_YD
        T.WORLD_CELL_YD = 0.001  # (every cell the world's: the look-ahead as before 1.4.2)
        try:
            before, _ = _bearing_jumps(lua, ns, path)
        finally:
            T.WORLD_CELL_YD = was
    finally:
        st.cityGrid = False
    big = sum(1 for j in jumps if j > 25)
    big_before = sum(1 for j in before if j > 25)
    print(name, "aims", round(min(aims), 1), round(max(aims), 1), "steps", round(max(abs(q - p) for p, q in
          zip(aims, aims[1:])), 2), "swings over 25 deg", big, big_before, "largest", round(max(jumps), 1),
          round(max(before), 1))
    # (the look-ahead's reach along the route moves on smoothly: a 2 yd step moves it at most a city cell's worth)
    steps = [abs(q - p) for p, q in zip(aims, aims[1:])]
    assert max(steps) <= 2.0 * WORLD / 3, max(steps)
    assert min(aims) < T.OPEN_LOOKAHEAD * 0.6  # (in the city: nearer)
    # (and the arrow swings no more than it did with the world's look-ahead everywhere)
    assert big <= big_before + 1, (jumps, before)
    assert max(jumps) <= max(before) + 10, (max(jumps), max(before))
