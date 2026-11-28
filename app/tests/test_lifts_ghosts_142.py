"""1.4.2 items 141, 135a, 126 and 138a, with the whole addon.

141: Thunder Bluff's north lift as a lift road (Data/Capitals.lua's source 5, top to foot, "Take the lift up/down"), the
mesa's cliff by its foot no longer climbed by gap links (Router.JoinedHeights), and a trip from Mulgore's north side up
into the city spliced in where the grid can walk to (WorldGrid.OtherCrossings).
135a: the lifts' waits in the routes' costs when a car's phase is known (Lifts.CostSeconds), kept for the trip.
126: a ghost takes no fall damage: the jump shortcuts an Expert jumper with a fall spell gets, with no drop limit.
138a: a walk with no way (`noWay`) is no walk in the ride check (Nav.Unwalkable).
"""

import math
import re
from pathlib import Path

import pytest

from test_map_redraw import game  # noqa: F401

pytest.importorskip("lupa")

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"

NORTH_SHAFTS = ((-1037.3, -49.2), (-1028.0, -28.4))  # (Data/LiftTimes.lua's station 7)
SW_SHAFTS = ((-1308.4, 185.3), (-1286.2, 189.7))  # (station 6)
NORTH_TOP = (1, -1060.0, -30.0, 142.0)  # (the mesa's top by the north lift)
MULGORE_NORTH = (1, -900.0, -20.0, None)  # (the plain north of the mesas)
NORTH_FOOT_ROAD = (1, -960.0, 0.0, None)  # (on the way up to the north lift's foot)
PALA = (1, -1300.3, 38.5, 129.3)  # (Thunder Bluff's inn, up on the central mesa)


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []


def _grids(ns, on):
    ns.settings.gps.cityGrid = on
    ns.settings.gps.worldGrid = on
    ns.WorldGrid.Set(on)


def _route(lua, ns, a, b, grids):
    _grids(ns, grids)
    return ns.Router.Route(a[0], a[1], a[2], b[1], b[2], lua.table(z=a[3], tz=b[3]))


def _lift_points(ns, r, kind):
    pts, kinds = _list(r.pts), _list(r.kinds)
    return [(pts[2 * i], pts[2 * i + 1]) for i in range(len(kinds)) if kinds[i] == kind]


def _near(p, shafts, yd):
    return min(math.dist(p, s) for s in shafts) <= yd


@pytest.fixture
def clean(game):  # noqa: F811
    lua, ns = game
    yield lua, ns
    _grids(ns, False)
    lua.execute("UnitIsGhost = function() return false end "
                "C_DeathInfo = { GetCorpseMapPosition = function() return nil end }")
    ns.Lifts.ResetCosts()
    ns.db.lifts = None
    ns.Nav.Clear()
    ns.settings.gps.expertJumper = False


# --- 141: Thunder Bluff's north lift ----------------------------------------------------------------------------------

def _capitals_lifts():
    """The capitals' lift roads (source 5), Data/Capitals.lua: ((x, y, z) top, (x, y, z) foot)."""
    lines = (ADDON / "Data" / "Capitals.lua").read_text(encoding="utf-8").split("\n")
    out = []
    for i, line in enumerate(lines):
        if "overlays[#overlays + 1] = { capital = \"capitals\"," not in line:
            continue
        n = [int(v) for v in re.search(r"\bn = \{([^}]*)\}", lines[i + 1]).group(1).split(",")]
        nz = [int(v) for v in re.search(r"\bnz = \{([^}]*)\}", lines[i + 2]).group(1).split(",")]
        j = i + 4
        while lines[j].strip().startswith("{"):
            m = re.match(r"\s*\{(\d+),(\d+),(\d+),(\d+),", lines[j])
            if m and m.group(4) == "5":
                a, b = int(m.group(1)), int(m.group(2))
                pa = (n[2 * a - 2], n[2 * a - 1], nz[a - 1])
                pb = (n[2 * b - 2], n[2 * b - 1], nz[b - 1])
                out.append(tuple(sorted((pa, pb), key=lambda p: -p[2])))
            j += 1
    return out


def test_the_north_lift_is_a_lift_road_from_its_top_to_its_foot():
    lifts = _capitals_lifts()
    north = [(top, foot) for top, foot in lifts if _near(top[:2], NORTH_SHAFTS, 30)]
    assert len(north) == 2, lifts  # (one a car)
    for top, foot in north:
        assert top[2] > 130 and foot[2] < 80, (top, foot)  # (the mesa's top, the foot's ground: 69-140.5)
        assert _near(foot[:2], NORTH_SHAFTS, 30)  # (not a land road 90 yd off under a bridge, as before)


def test_no_gap_link_climbs_the_mesa_by_the_north_lift(clean):
    """The land's road split at the lift's foot takes the foot's height (Router.JoinedHeights): no gap link from it up
    the cliff to the city's road 27 yd across; the Router's own way up is the lift."""
    lua, ns = clean
    r = _route(lua, ns, NORTH_FOOT_ROAD, NORTH_TOP, False)
    R = ns.Router
    ups = _lift_points(ns, r, R.KIND_LIFT_UP)
    assert ups and all(_near(p, NORTH_SHAFTS, 15) for p in ups), ups
    hs, kinds = _list(r.zs if r.zs is not None else r.fz), _list(r.kinds)
    for i in range(len(kinds)):
        if kinds[i] != R.KIND_LIFT_UP and type(hs[i]) in (int, float) and type(hs[i + 1]) in (int, float):
            assert abs(hs[i + 1] - hs[i]) < 30, (i, hs[i], hs[i + 1])
    back = _route(lua, ns, NORTH_TOP, NORTH_FOOT_ROAD, False)
    downs = _lift_points(ns, back, R.KIND_LIFT_DOWN)
    assert downs and all(_near(p, NORTH_SHAFTS, 15) for p in downs), downs


def test_joined_heights_spread_over_zero_length_joins_only(clean):
    lua, ns = clean
    edges = lua.eval("{ { 1, 2, 0 }, { 2, 3, 0.5 }, { 3, 4, 20 } }")
    nz = lua.eval("{ [1] = 60 }")
    out = ns.Router.JoinedHeights(edges, nz)
    assert out[2] == 60 and out[3] == 60 and out[4] is None
    assert nz[2] is None  # (a copy: the graph's own heights unchanged)


@pytest.mark.parametrize("stop", [NORTH_TOP, PALA], ids=["north_top", "inn"])
def test_from_mulgore_s_north_side_up_the_north_lift(clean, stop):
    """Kooki3z 2026-11-27 (item 141): from Mulgore's north side up into Thunder Bluff by the north lift, the quicker way
    up from there: the grids' route (always on), spliced where the world grid walks to the foot's rise by its road."""
    lua, ns = clean
    R = ns.Router
    r = _route(lua, ns, MULGORE_NORTH, stop, True)
    assert r is not None and not r.noWay and r.cityGrid == "Thunder Bluff", (r and r.noWay)
    ups = _lift_points(ns, r, R.KIND_LIFT_UP)
    assert ups and all(_near(p, NORTH_SHAFTS, 15) for p in ups), ups
    assert not any(_near(p, SW_SHAFTS, 60) for p in _lift_points(ns, r, R.KIND_LIFT_UP))
    hs = _list(r.fz)
    assert abs(hs[-1] - stop[3]) < 4, hs[-1]


def test_the_north_lift_is_timed_as_its_own_station(clean):
    """Lifts.lua's station matching (STATION_YD): the north lift's ride, boarded at its foot or top, is station 7's,
    never the southwest lift's (station 6, 330 yd off)."""
    lua, ns = clean
    LT = ns.Lifts
    for x, y in ((-1026.0, -30.0), (-1023.0, -25.0), (-1044.0, -52.0), (-1033.0, -25.0)):
        assert LT.CarAt(1, x, y, LT.STATION_YD).station == 7
    for x, y in SW_SHAFTS:
        assert LT.CarAt(1, x, y, LT.STATION_YD).station == 6
    # (and the route's own lift: boarded where station 7's cars are)
    r = _route(lua, ns, MULGORE_NORTH, NORTH_TOP, True)
    ups = _lift_points(ns, r, ns.Router.KIND_LIFT_UP)
    assert ups and {LT.CarAt(1, x, y, LT.STATION_YD).station for x, y in ups} == {7}


# --- 135a: the lifts' waits in the costs ------------------------------------------------------------------------------

def _cars(ns, station):
    cars = ns.LiftCars
    return [cars[i] for i in range(1, len(cars) + 1) if cars[i].station == station]


def _wait(c, floor, t, phase):
    """Lifts.CarWait's (the test's own): the wait for car c at `floor` at server time t."""
    p = c.period
    w = c[floor]
    a = (t - phase) % p
    into = (a - w[1]) % p
    if into < w[2] - w[1]:
        return 0.0
    return (w[1] - a) % p


def _ride(c, floor):
    other = "top" if floor == "bottom" else "bottom"
    return (c[other][1] - c[floor][2]) % c.period


def test_no_phase_known_keeps_the_data_s_fixed_lift_time(clean):
    lua, ns = clean
    LT = ns.Lifts
    assert LT.CostSeconds(1, -1026.0, -30.0, "bottom") == 0
    assert LT.CostSeconds(0, 1595.0, 290.3, "top") == 0
    assert LT.CostSeconds(1, -800.0, -20.0, "bottom") == 0  # (no lift there)


def test_a_known_phase_prices_the_wait_at_arrival_and_keeps_it_for_the_trip(clean):
    lua, ns = clean
    LT = ns.Lifts
    lua.execute("AGPS_POS = { -1026.0, -30.0, 1 }")  # (at the north lift's foot: arriving now)
    now = LT.Now()
    seen = LT.Sightings()
    cars = _cars(ns, 7)
    for c, ph in zip(cars, (3.0, 11.0)):
        seen[LT.CarKey(c)] = lua.table(phase=ph, at=now, n=1)
    LT.ResetCosts()
    got = LT.CostSeconds(1, -1026.0, -30.0, "bottom")
    waits = [(_wait(c, "bottom", now, ph), _ride(c, "bottom")) for c, ph in zip(cars, (3.0, 11.0))]
    w, ride = min(waits)
    assert got == pytest.approx(w + ride - LT.AVG_SECONDS["Thunder Bluff"], abs=0.6)
    # (the cars come and go; the cost stays for the trip: no reroute churn)
    lua.execute("AGPS_T = AGPS_T + 9")
    assert LT.CostSeconds(1, -1026.0, -30.0, "bottom") == got
    # (as yards: the Router's, the grids')
    assert LT.CostYards(1, -1026.0, -30.0, "bottom") == pytest.approx(got * LT.YD_PER_SECOND)
    # (another trip: worked out again, from now)
    ns.Nav.SetStops(lua.eval("{ { x = -1060, y = -30, cont = 1, name = 'Top' } }"), False, "red")
    later = LT.Now()
    waits = [(_wait(c, "bottom", later, ph), _ride(c, "bottom")) for c, ph in zip(cars, (3.0, 11.0))]
    w, ride = min(waits)
    assert LT.CostSeconds(1, -1026.0, -30.0, "bottom") == pytest.approx(w + ride - LT.AVG_SECONDS["Thunder Bluff"],
                                                                        abs=0.6)


def test_every_lift_the_routes_take_is_priced(clean):
    """Thunder Bluff's (the Router's lift roads, the city grid's links), the Great Lift's and Freewind's (the world
    grid's links) and Undercity's (the planner's rides): each search adds the lift's cost over the data's when a phase
    is known, nothing when none is."""
    lua, ns = clean
    LT = ns.Lifts
    seen = LT.Sightings()
    now = LT.Now()
    for st in (1, 4, 5, 7):
        for c in _cars(ns, st):
            seen[LT.CarKey(c)] = lua.table(phase=0.0, at=now, n=1)
    LT.ResetCosts()
    # (the city grid's lift link at the north lift, its foot to its top)
    c = ns.CityGrid.City("Thunder Bluff")
    links = [c.links[i] for i in range(1, len(c.links) + 1) if c.links[i].kind == 5]
    north = [L for L in links
             if _near((L.pts[1][1], L.pts[1][2]), NORTH_SHAFTS, 15) and L.pts[len(L.pts)][3] > L.pts[1][3]]
    assert north
    L = north[0]
    want = LT.CostYards(1, L.pts[1][1], L.pts[1][2], "bottom", L.cost - 1)
    assert want != 0 and ns.CityGrid.LiftYards(c, L) == want
    # (the world grid's, at the Great Lift: a link from its foot up)
    gl = _cars(ns, 4)[0]
    WG = ns.WorldGrid
    link = lua.eval("{ pts = { { %f, %f, %f }, { %f, %f, %f } } }" % (gl.x + 3, gl.y, gl.lo, gl.x + 3, gl.y, gl.hi))
    assert WG.LiftYards(WG.Cont(1), link, 210) == LT.CostYards(1, gl.x + 3, gl.y, "bottom", 209) != 0
    # (Undercity's, the planner's ride rows)
    seen2 = LT.Sightings()
    for c in _cars(ns, 1):
        seen2[LT.CarKey(c)] = lua.table(phase=0.0, at=now, n=1)
    LT.ResetCosts()
    rows = [ns.Transports[i] for i in range(1, len(ns.Transports) + 1) if ns.Transports[i][8] == "lift"]
    uc = [t for t in rows if abs(t[2] - 1545.7) < 1][0]
    assert ns.Nav.LiftRideExtra(uc, 1, 0) != 0 and ns.Nav.LiftRideExtra(uc, 1, 0) >= -uc[7]
    # (and no phase: nothing)
    ns.db.lifts = None
    LT.ResetCosts()
    assert ns.CityGrid.LiftYards(c, L) == 0 and ns.Nav.LiftRideExtra(uc, 1, 0) == 0


def test_the_router_prices_its_lift_roads(clean):
    lua, ns = clean
    R, LT = ns.Router, ns.Lifts
    _route(lua, ns, NORTH_FOOT_ROAD, NORTH_TOP, False)
    g = R.DebugGraph(1)
    ei = next(i for i in range(1, len(g.e) + 1) if g.e[i][4] == R.SOURCE_LIFT
              and _near((g.n[g.e[i][1] * 2 - 1], g.n[g.e[i][1] * 2]), NORTH_SHAFTS, 20))
    e = g.e[ei]
    top = e[1] if g.nz[e[1]] > g.nz[e[2]] else e[2]
    assert R.LiftYards(g, 1, ei, e[1] == top, top, e[3]) == 0
    seen = LT.Sightings()
    for c in _cars(ns, 7):
        seen[LT.CarKey(c)] = lua.table(phase=5.0, at=LT.Now(), n=1)
    LT.ResetCosts()
    got = R.LiftYards(g, 1, ei, e[1] == top, top, e[3])
    assert got == LT.CostYards(1, g.n[top * 2 - 1], g.n[top * 2], "top", e[3] - 1) != 0


def test_a_ride_that_changes_the_phase_reroutes_once(clean):
    lua, ns = clean
    LT, N = ns.Lifts, ns.Nav
    lua.execute("AGPS_N_INV = 0")
    was = N.Invalidate
    N.stops = lua.eval("{ { x = -1060, y = -30, cont = 1, name = 'Top' } }")
    N.Invalidate = lua.eval("function(...) AGPS_N_INV = AGPS_N_INV + 1 end")
    try:
        c = _cars(ns, 7)[0]
        t = LT.Now()
        assert LT.Rode(c, "top", t - 20, t) is not None
        assert lua.eval("AGPS_N_INV") == 1
        # (the same ride again, its phase within SAME_TOL: sharpened, the phase's stamp changes: one more, never more)
        LT.Rode(c, "top", t + c.period - 20, t + c.period)
        assert lua.eval("AGPS_N_INV") <= 2
    finally:
        N.Invalidate = was
        N.stops = lua.eval("{}")


def test_the_fixed_lift_times_match_the_data_s():
    from azerothgps import capitals, cities, lifts
    text = (ADDON / "Lifts.lua").read_text(encoding="utf-8")
    m = re.search(r'LT\.AVG_SECONDS = \{ \["Undercity"\] = (\d+), \["Thunder Bluff"\] = (\d+), '
                  r'\["Thousand Needles"\] = (\d+) \}', text)
    assert m and (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (
        cities.LIFT_SECONDS, capitals.LIFT_SECONDS, lifts.LIFT_SECONDS)


# --- 126: ghosts ------------------------------------------------------------------------------------------------------

NOXIOUS_RIM, BELOW_IRONSTONE = (-7663.8, -2641.3), (-6539.0, -1464.7)
SOUTH_BARRENS, BELOW_DUSTWALLOW_RIDGE = (-2262.2, -2152.1), (-2482.6, -2920.0)
GHOST = "UnitIsGhost = function(u) return u == 'player' end"


def _trip(lua, ns, a, b, corpse=False):
    N, st = ns.Nav, ns.settings.gps
    st.zoom, st.fastestOrder = 300, False
    ns.CharDB().faction = "Horde"
    N.Clear()
    ns.FallSpells.Refresh()
    ns.Router.Reset()
    lua.execute(f"AGPS_MAP = 1413 AGPS_POS = {{ {a[0]}, {a[1]}, 1 }}")
    if corpse:
        # (the body's spot on Kalimdor's map, as the game gives it: the corpse run's stop, N.DeathCheck)
        b0, b1 = b
        lua.execute(f"""
          local b = AGPS_NS.Maps[1414].bounds
          C_DeathInfo = {{ GetCorpseMapPosition = function(id) if id ~= 1414 then return nil end
            return {{ x = (b[4] - ({b1})) / (b[4] - b[2]), y = (b[3] - ({b0})) / (b[3] - b[1]) }} end }}""")
        lua.execute("AGPS_T = AGPS_T + 2")
        N.DeathCheck()
        assert N.stops[1].corpse
    else:
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
    N.Invalidate(True, True)
    ns.GPS.Follow()
    for _ in range(16):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        ns.GPS.Update()
    return N.route


def _drops(ns, r):
    n = 0
    for p in range(1, len(r.parts) + 1):
        ks = _list(r.parts[p].kinds)
        drop = ns.Router.KIND_DROP
        n += sum(1 for i, k in enumerate(ks) if k == drop and (i == 0 or ks[i - 1] != drop))
    return n


def test_a_ghost_gets_the_jump_shortcuts_with_no_drop_limit(clean):
    lua, ns = clean
    R = ns.Router
    lua.execute(GHOST)
    assert R.Ghost() and R.ExpertJumper()
    low, top = R.JumpDrops(lua.table())
    assert low <= R.WG_BAKED_DROP and top == R.GHOST_DROP
    lua.execute("UnitIsGhost = function() return false end")
    assert not R.Ghost() and R.JumpDrops(lua.table()) is None  # (alive, no fall spell: none)


@pytest.mark.parametrize("a,b", [(NOXIOUS_RIM, BELOW_IRONSTONE), (SOUTH_BARRENS, BELOW_DUSTWALLOW_RIDGE)],
                         ids=["un_goro_rim", "dustwallow_ridge"])
def test_a_ghost_jumps_straight_down_where_the_living_walk_round(clean, a, b):
    """The Router's own way (where the grids leave a leg to it): a ghost, no fall spell, goes off the rim straight down
    as an Expert jumper with one does; alive with no spell, the long way round."""
    lua, ns = clean
    _grids(ns, False)
    straight = math.dist(a, b)
    alive = _trip(lua, ns, a, b)
    lua.execute(GHOST)
    ghost = _trip(lua, ns, a, b)
    assert _drops(ns, ghost) >= 1 and ghost.totalYards < straight * 1.15 + 60, (ghost.totalYards, straight)
    assert alive.totalYards > ghost.totalYards * 2


def test_a_corpse_run_on_the_grids_jumps_down_the_ridge(clean):
    """A corpse run (the body the stop, N.DeathCheck) on the world grid: down Dustwallow's ridge to the body, no fall
    damage, as a spell jumper's way; its stop is the body's, still first."""
    lua, ns = clean
    _grids(ns, True)
    lua.globals().AGPS_NS = ns
    lua.execute(GHOST)
    r = _trip(lua, ns, SOUTH_BARRENS, BELOW_DUSTWALLOW_RIDGE, corpse=True)
    straight = math.dist(SOUTH_BARRENS, BELOW_DUSTWALLOW_RIDGE)
    assert ns.Nav.corpse and _drops(ns, r) >= 1 and r.totalYards < straight * 1.15 + 60, r.totalYards


def test_a_ghost_s_city_drops_cost_no_hurt(clean):
    lua, ns = clean
    lua.execute(GHOST)
    assert ns.Router.ExpertJumper()
    # (the city grid's hurt-drop cost goes by castDrop, unlimited for a ghost: CG.Search reads Router.Ghost)
    src = (ADDON / "CityGrid.lua").read_text(encoding="utf-8")
    assert "if Rt.Ghost and Rt.Ghost() then castDrop = math.huge end" in src


# --- 138a: no way is no walk ------------------------------------------------------------------------------------------

def test_a_no_way_line_is_no_walk(clean):
    lua, ns = clean
    N = ns.Nav
    assert N.Unwalkable(lua.table(noWay=True)) and N.Unwalkable(lua.table(unconnected=True))
    assert not N.Unwalkable(lua.table(pts=lua.table(0, 0, 10, 10)))
    line = lua.table(pts=lua.table(8753, 960, 5322, -655), kinds=lua.table(1), length=3800, noWay=True, gridGap=True)
    legs = lua.eval("{ { cont = 1, x1 = 8753, y1 = 960, x2 = 5322, y2 = -655 } }")
    assert N.PlanWeighed(legs, lua.table(line), 7, None) == math.inf
    assert not N.WalkDetour(legs[1], line, None)
    assert N.WalkLonger(legs[1], line, None, True) == 0
