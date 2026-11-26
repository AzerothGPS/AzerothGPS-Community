"""Unstuck and rejoin (item 117, 1.4.1, the grid ideas).

(a) Pushing forward into a wall the grid knows (Unstuck.lua): the nearest way round it is offered on the directions'
line; never on a flight, a boat, at a dock or a lift, in a vehicle, flying, falling, swimming, casting, or standing
still. Every stuck spot goes to the dev tools' hook (Nav.StuckHook); the shipped addon keeps none.
(b) A reroute off the route (and the short way back onto a long walk) starts on the floor the player is on, out on the
land too (Nav.StartFloor, Nav.GridStartZ).
(c) A corpse run ends on the floor the player died on (Nav.NoteDeath, Nav.DeathFloor): a body in a cave under a hill
is walked to in the cave, not on the hill over it."""

import math

import pytest

from test_map_redraw import game  # noqa: F401

INN = (1, -402.0, -2644.0)  # (the Crossroads' inn: its walls on the world grid, test_building_doors)
OPEN = (1, -520.0, -2700.0)  # (the Barrens' open ground west of the Crossroads)
MARAUDON = (1, -1244.0, 2896.0)  # (Maraudon's outer cave: passages 73.5 and 87.5 under the hill's 128.5)
MARAUDON_EAST = (-1191.3, 2896.0, 86.5)  # (along the 87.5 passage)
HILL_OVER = (-1244.0, 2856.0, 120.0)  # (the hill's top 40 yd south: from the passage, out by the cave's mouth)
MENETHIL_DOCK = (0, -3925.2, -621.8)  # (Menethil Harbor's docks: the boats to Theramore and Auberdine)


@pytest.fixture
def world(game):  # noqa: F811
    lua, ns = game
    st, WG, R = ns.settings.gps, ns.WorldGrid, ns.Router
    was = (st.worldGrid, st.cityGrid, R.SYNC_WALKS)
    st.worldGrid = st.cityGrid = True
    WG.Set(True)
    R.SYNC_WALKS = True
    lua.execute("""
      AGPS_US = { moving = true, speed = 7, facing = 0, taxi = false, cast = nil, flying = false, fall = false,
        swim = false, indoors = false, vehicle = false }
      AGPS_US_SAVED = { IsPlayerMoving = rawget(_G, 'IsPlayerMoving'), GetUnitSpeed = GetUnitSpeed,
        GetPlayerFacing = GetPlayerFacing, UnitOnTaxi = UnitOnTaxi, UnitCastingInfo = rawget(_G, 'UnitCastingInfo'),
        IsFlying = IsFlying, IsFalling = rawget(_G, 'IsFalling'), IsSwimming = rawget(_G, 'IsSwimming'),
        IsIndoors = rawget(_G, 'IsIndoors'), UnitInVehicle = rawget(_G, 'UnitInVehicle') }
      IsPlayerMoving = function() return AGPS_US.moving end
      GetUnitSpeed = function() return AGPS_US.speed, 7, 7, 4.7 end
      GetPlayerFacing = function() return AGPS_US.facing end
      UnitOnTaxi = function() return AGPS_US.taxi end
      UnitCastingInfo = function() return AGPS_US.cast end
      IsFlying = function() return AGPS_US.flying end
      IsFalling = function() return AGPS_US.fall end
      IsSwimming = function() return AGPS_US.swim end
      IsIndoors = function() return AGPS_US.indoors end
      UnitInVehicle = function() return AGPS_US.vehicle end
    """)
    hooked = []
    ns.Nav.StuckHook = lambda info: hooked.append(dict(wall=info.wall, side=info.side, deg=info.deg))
    _fresh(lua, ns)
    yield lua, ns, hooked
    ns.Nav.StuckHook = None
    lua.execute("""
      local s = AGPS_US_SAVED
      IsPlayerMoving, GetUnitSpeed, GetPlayerFacing, UnitOnTaxi = s.IsPlayerMoving, s.GetUnitSpeed, s.GetPlayerFacing,
        s.UnitOnTaxi
      UnitCastingInfo, IsFlying, IsFalling, IsSwimming, IsIndoors, UnitInVehicle = s.UnitCastingInfo, s.IsFlying,
        s.IsFalling, s.IsSwimming, s.IsIndoors, s.UnitInVehicle
    """)
    _fresh(lua, ns)
    ns.Nav.Clear()
    st.worldGrid, st.cityGrid, R.SYNC_WALKS = was
    WG.Set(bool(was[0]))


def _fresh(lua, ns):
    N = ns.Nav
    N.ResetGridTrack()
    N.ResetTrack()
    N.ResetCityTrack()
    N.fellAt = None
    N.deathFloor = None
    ns.Unstuck.Reset()
    lua.execute("AGPS_T = AGPS_T + 30")


def _us(lua, **kw):
    for k, v in kw.items():
        val = "nil" if v is None else ("true" if v is True else "false" if v is False else repr(v))
        lua.execute(f"AGPS_US.{k} = {val}")


def _push(lua, ns, x, y, cont, seconds=3.2, step=0.2):
    U = ns.Unstuck
    for _ in range(int(seconds / step) + 1):
        U.Watch(x, y, cont)
        lua.execute(f"AGPS_T = AGPS_T + {step}")


def _probe(ns, cont, x, y):
    got = ns.Unstuck.Probe(cont, x, y, None)
    return got[0] if isinstance(got, tuple) else got


def _wall_spot(ns):
    """A spot just outside the Crossroads' inn with its wall ahead (the grid walks no way on) and open ground behind."""
    U, WG = ns.Unstuck, ns.WorldGrid
    cont, cx, cy = INN
    c = WG.Cont(cont)
    WG.SurfacesAt(c, cx, cy)  # (its tile decoded)
    for a in range(0, 360, 10):
        rad = math.radians(a)
        for r in range(50, 8, -1):
            x, y = cx + math.cos(rad) * r, cy + math.sin(rad) * r
            if not WG.Decoded(c, x, y):
                continue
            open_ = _probe(ns, cont, x, y)
            if not open_:
                continue
            facing = (rad + math.pi) % (2 * math.pi)  # (toward the inn)
            if not open_(facing, U.PROBE_YD) and open_(facing + math.pi, U.ROUND_YD):
                return x, y, facing
            if not open_(facing, U.PROBE_YD):
                break
    pytest.fail("no wall found round the Crossroads' inn")


# --- (a) stuck against a wall ----------------------------------------------------------------------------------------

def test_pushing_into_the_inns_wall_offers_the_nearest_way_round(world):
    lua, ns, hooked = world
    U = ns.Unstuck
    x, y, facing = _wall_spot(ns)
    _us(lua, facing=facing)
    _push(lua, ns, x, y, 1)
    look = U.last
    assert look and look.wall is True and look.grid == "world"
    assert U.state and U.state.side in ("left", "right", "back")
    # (the way offered is one the grid walks, the smallest turn that does with no route)
    open_ = _probe(ns, 1, x, y)
    assert open_(facing + math.radians(look.deg), U.ROUND_YD)
    for k in range(1, int(abs(look.deg) / U.ROUND_STEP)):
        for sgn in (1, -1):
            assert not open_(facing + math.radians(sgn * k * U.ROUND_STEP), U.ROUND_YD)
    text = U.Text(x, y, 1)
    assert text and text.startswith("Blocked ahead:")
    assert hooked == [{"wall": True, "side": look.side, "deg": look.deg}]
    # (once a spot: pushing on there says nothing more to the dev tools)
    _push(lua, ns, x, y, 1)
    assert len(hooked) == 1
    # (moved off it: gone)
    assert U.Text(x + U.CLEAR_YD + 1, y, 1) is None
    U.Watch(x + U.CLEAR_YD + 1, y, 1)
    assert U.state is None


def test_the_way_round_nearest_the_routes_way_on_is_offered(world):
    lua, ns, _ = world
    U = ns.Unstuck
    x, y, facing = _wall_spot(ns)
    open_ = _probe(ns, 1, x, y)
    ways = [d for d in range(-150, 181, U.ROUND_STEP) if d and open_(facing + math.radians(d), U.ROUND_YD)]
    assert ways
    # (the route's way on straight back: "turn back" when it walks, else the open way nearest it)
    look = U.Look(1, x, y, facing, facing + math.pi)
    want = min(ways, key=lambda d: (abs(((math.radians(d) - math.pi) + math.pi) % (2 * math.pi) - math.pi), abs(d)))
    assert look.deg == want


def test_never_while_carried_cast_flying_falling_swimming_or_standing_still(world):
    lua, ns, hooked = world
    U = ns.Unstuck
    x, y, facing = _wall_spot(ns)
    _us(lua, facing=facing)
    for kw in ({"taxi": True}, {"cast": "Hearthstone"}, {"flying": True}, {"fall": True}, {"swim": True},
               {"vehicle": True}, {"speed": 0}, {"moving": False}):
        _fresh(lua, ns)
        _us(lua, **kw)
        _push(lua, ns, x, y, 1)
        assert U.last is None and U.state is None, kw
        _us(lua, taxi=False, cast=None, flying=False, fall=False, swim=False, vehicle=False, speed=7, moving=True)
    assert hooked == []
    # (a lift or a teleporter's end: the car carries them up and down on one spot)
    N = ns.Nav
    was = N.AtLift
    N.AtLift = lambda level, px, py: True
    try:
        _fresh(lua, ns)
        _push(lua, ns, x, y, 1)
        assert U.last is None
    finally:
        N.AtLift = was
    # (a gap in the looks: the map and arrow closed, a loading screen)
    _fresh(lua, ns)
    for _ in range(6):
        U.Watch(x, y, 1)
        lua.execute("AGPS_T = AGPS_T + 1.5")
    assert U.last is None
    assert hooked == []


def test_at_a_boats_dock_nothing_is_said(world):
    lua, ns, hooked = world
    U, T = ns.Unstuck, ns.Taxi
    cont, x, y = MENETHIL_DOCK
    assert T.DockAt(cont, x, y)
    assert U.NotNow(cont, x, y) == "dock"
    _push(lua, ns, x, y, cont)
    assert U.last is None and hooked == []


def test_walking_on_or_stuck_where_the_grid_sees_no_wall_offers_nothing(world):
    lua, ns, hooked = world
    U = ns.Unstuck
    cont, x, y = OPEN
    # (walking: the spot changes)
    for k in range(20):
        U.Watch(x + k * 1.4, y, cont)
        lua.execute("AGPS_T = AGPS_T + 0.2")
    assert U.last is None
    # (stuck on open ground, a rock or a tree the grid doesn't have: the dev tools hear of it, the player nothing)
    _fresh(lua, ns)
    _push(lua, ns, x, y, cont)
    assert U.last and U.last.wall is False
    assert U.state is None and U.Text(x, y, cont) is None
    assert hooked == [{"wall": False, "side": None, "deg": None}]


def test_the_offer_shows_on_the_directions_line(world):
    lua, ns, _ = world
    N, U = ns.Nav, ns.Unstuck
    x, y, facing = _wall_spot(ns)
    N.SetStops(lua.table(lua.table(x=-520.0, y=-2700.0, cont=1, name="West")), False, "red")
    first = N.Status(x, y, 1)
    assert first and "Blocked ahead" not in first
    _us(lua, facing=facing)
    status = None
    for _ in range(18):
        lua.execute("AGPS_T = AGPS_T + 0.2")
        status = N.Status(x, y, 1)
    assert U.state and status and "Blocked ahead:" in status


def test_the_shipped_addon_keeps_no_stuck_spots(world):
    # (flagging is the dev tools': Nav.StuckHook is theirs to set; nothing saved here)
    lua, ns, _ = world
    src = open(__file__.replace("app\\tests\\test_unstuck.py", "addon\\AzerothGPS\\Unstuck.lua")
               .replace("app/tests/test_unstuck.py", "addon/AzerothGPS/Unstuck.lua"), encoding="utf-8").read()
    assert "CharDB" not in src and "ns.db" not in src and "SavedVariables" not in src


# --- (b) a reroute from the player's floor ---------------------------------------------------------------------------

def test_a_reroute_out_on_the_land_starts_on_the_floor_followed(world):
    lua, ns, _ = world
    N, WG = ns.Nav, ns.WorldGrid
    cont, x, y = MARAUDON
    _us(lua, indoors=False)
    # (nothing followed: no floor of the grid's for the start, the walk's own guess)
    assert N.GridStartZ(cont, x, y) is None
    # (followed down the passage at 87.5, the game calling it outdoors: the reroute starts there, not on the hill)
    N.SetGridTrackForTests(cont, x, y, lua.table(87.5), True)
    assert N.GridStartZ(cont, x, y) == pytest.approx(87.5)
    z, zs = N.StartFloor(cont, x, y)
    assert z == pytest.approx(87.5) and zs is None
    assert N.GridStartZ(cont, x + 20, y) is None  # (only where it was followed)
    tx, ty, tz = MARAUDON_EAST
    r = WG.Walk(WG.Cont(cont), x, y, z, tx, ty, tz, lua.table())
    assert r and r.fz[1] == pytest.approx(87.5, abs=0.5)
    # (unsure: the candidates, as item 106)
    N.SetGridTrackForTests(cont, x, y, lua.table(73.5, 87.5, 128.5))
    z, zs = N.StartFloor(cont, x, y)
    assert z is None and zs is not None and len(zs) == 3


def test_the_route_worked_out_off_the_route_starts_on_the_floor_followed(world):
    lua, ns, _ = world
    N = ns.Nav
    cont, x, y = MARAUDON
    tx, ty, tz = HILL_OVER
    _us(lua, indoors=False)
    N.SetStops(lua.table(lua.table(x=tx, y=ty, z=tz, cont=cont, name="Hill")), False, "red")  # (Desolace: no "too high?")
    # (followed down the passage at 87.5: the stop on the hill 40 yd off is out by the cave's mouth, not 40 yd straight
    # over the hill's top the walk's own guess would start on)
    N.SetGridTrackForTests(cont, x, y, lua.table(87.5), True)
    N.Invalidate(True, True)
    r = None
    for _ in range(10):
        lua.execute("AGPS_T = AGPS_T + 0.3")
        r = N.Route(x, y, cont)
        if r and not r.pending:
            break
    assert r and r.fullFirst and r.fullFirst.fz
    assert r.fullFirst.fz[1] == pytest.approx(87.5, abs=0.5)
    assert r.length > 300


# --- (c) the corpse run to the floor died on -------------------------------------------------------------------------

def test_the_body_in_a_cave_is_walked_to_on_the_floor_died_on(world):
    lua, ns, _ = world
    N, Geo = ns.Nav, ns.Geo
    cont, x, y = MARAUDON
    N.SetGridTrackForTests(cont, x, y, lua.table(87.5), True)
    Geo.override = lua.table(x=x, y=y, cont=cont, z=0)
    try:
        assert N.NoteDeath() == pytest.approx(87.5, abs=0.5)
    finally:
        Geo.override = None
    assert N.DeathFloor(cont, x + 6, y - 4) == pytest.approx(87.5, abs=0.5)
    assert N.DeathFloor(cont, x + N.CORPSE_FLOOR_YD + 5, y) is None
    assert N.DeathFloor(0, x, y) is None
    # (released: the body's stop, at its spot on the map, takes that floor as its route's height)
    lua.globals().AGPS_NSREF = ns
    lua.execute(f"""
      AGPS_US_GHOST = true
      AGPS_US_SAVED.UnitIsGhost, AGPS_US_SAVED.C_DeathInfo = UnitIsGhost, C_DeathInfo
      UnitIsGhost = function() return AGPS_US_GHOST end
      local id
      for mid, m in pairs(AGPS_NSREF.Maps) do
        if m.type == 2 and m.continent == 1 and m.bounds then id = mid end
      end
      local b = AGPS_NSREF.Maps[id].bounds
      local v, u = (b[3] - ({x})) / (b[3] - b[1]), (b[4] - ({y})) / (b[4] - b[2])
      C_DeathInfo = {{ GetCorpseMapPosition = function(m) if m == id then return {{ x = u, y = v }} end end }}
    """)
    try:
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 2")
        N.DeathCheck()
        body = N.stops[1]
        assert body and body.corpse and body.zSource == "death"
        assert body.guessZ == pytest.approx(87.5, abs=0.5) and N.StopZ(body) == pytest.approx(87.5, abs=0.5)
        assert body.z is None  # (arriving still by the yards alone)
        # (alive again: the body's stop gone, the floor forgotten)
        lua.execute("AGPS_US_GHOST = false AGPS_T = AGPS_T + 2")
        N.DeathCheck()
        assert len(N.stops) == 0 and N.deathFloor is None
    finally:
        lua.execute("UnitIsGhost, C_DeathInfo = AGPS_US_SAVED.UnitIsGhost, AGPS_US_SAVED.C_DeathInfo")
        N.Clear()


def test_no_floor_known_at_death_leaves_the_body_as_before(world):
    lua, ns, _ = world
    N, Geo = ns.Nav, ns.Geo
    cont, x, y = OPEN
    Geo.override = lua.table(x=x, y=y, cont=cont, z=0)
    try:
        N.NoteDeath()
    finally:
        Geo.override = None
    # (open ground: one floor, or none followed; nothing kept that a body elsewhere would take)
    assert N.DeathFloor(cont, x + 100, y) is None
