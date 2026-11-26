"""Water and stops (item 116, Kooki3z 2026-11-26's grid ideas), with the whole addon (gameharness).

(a) Swimming with no route: the nearest shore the player can walk up onto (the world grid's water links to the land
only within its SHORE_Z of the water's top, so never a steep bank), an arrow and its yards ("Swim to the shore") and a
wavy line to it on the map (Shore.lua). With a route its own way out wins: none of it shown.
(b) A stop made in rock, a wall or on a roof goes to the nearest walkable cell on its most likely floor (StopSnap.lua,
through Nav's Copy): the NPC's floor for an NPC's stop, the stop's own height (a cave's floor clicked), else the
ground's; a stop already on walkable ground stays where it is.
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401

LAKE = (1050.0, 350.0)  # (Lordamere Lake, 20 yd off its north-east shore)
LAKE_FAR = (900.0, 300.0)  # (out in the lake, 90 yd swum to the Dawning Isles' shore)
ROAD = (-9464.0, 62.0)  # (Goldshire's road: walkable ground)
GORGE = (-2380.0, -2520.0)  # (the river under Thandol Span: its banks a cliff a yard off, the gorge's walls)
WAILING = (-569.8, -2291.7)  # (over the Wailing Caverns, north of Lushwater Oasis)


@pytest.fixture
def swimmer(game):  # noqa: F811
    """swimmer(x, y, swimming=True): the dev tools' simulated player there on the Eastern Kingdoms."""
    lua, ns = game
    Geo, N = ns.Geo, ns.Nav
    old = Geo.override
    ns.WorldGrid.Set(True)
    N.Clear()

    def put(x, y, swimming=True, cont=0):
        Geo.override = lua.eval(f"{{ x = {x}, y = {y}, cont = {cont}, swimming = {'true' if swimming else 'false'} }}")
        ns.Shore.last = None
        lua.execute("AGPS_T = AGPS_T + 1")
        return ns.Shore.Current()

    try:
        yield put
    finally:
        Geo.override = old
        ns.Shore.last = None
        N.Clear()
        ns.GPS.Follow()


def test_swimming_with_no_route_points_to_the_nearest_shore(game, swimmer):  # noqa: F811
    lua, ns = game
    e = swimmer(*LAKE)
    assert e is not None
    assert e.dist < 40 and abs(e.x - LAKE[0]) < 40 and abs(e.y - LAKE[1]) < 40
    assert "Swim to the shore" in ns.Shore.Text(e) and "yd" in ns.Shore.Text(e)
    far = swimmer(*LAKE_FAR)
    assert far is not None and 60 < far.yd < 150  # (out in the lake: the isles' shore, swum)


def test_the_way_out_is_onto_land_that_leads_on(game, swimmer):  # noqa: F811
    lua, ns = game
    WG = ns.WorldGrid
    e = swimmer(*LAKE)
    c = WG.Cont(0)
    land = [s for s in WG.SurfacesAt(c, e.x, e.y, e.z).values() if abs(s.z - e.z) < 0.5]
    assert land and land[0].f % 2 == 0 and (land[0].f // 4) % 2 == 1  # (land the player reaches, not water)
    water = WG.SurfacesAt(c, *LAKE).values()
    wz = next(s.z for s in water if s.f % 2 == 1)
    assert abs(e.z - wz) <= 2  # (at the water's top: walked up out of it, not a bank to climb)


def test_a_steep_bank_is_never_the_way_out(game, swimmer):  # noqa: F811
    # (the gorge's wall is a yard or two off, 40 yd up: the way out is down the river where it meets the land)
    lua, ns = game
    WG = ns.WorldGrid
    c = WG.Cont(0)
    wz = next(s.z for s in WG.SurfacesAt(c, *GORGE).values() if s.f % 2 == 1)
    wall = min(math.hypot(s.x - GORGE[0], s.y - GORGE[1])
               for dx in (-1, 0, 1) for dy in (-1, 0, 1)
               for s in WG.SurfacesAt(c, GORGE[0] + dx * 8.33, GORGE[1] + dy * 8.33).values()
               if s.f % 2 == 0 and s.z > wz + 5)
    assert wall < 10
    e = swimmer(*GORGE)
    assert e is not None and e.yd > 100 and abs(e.z - wz) <= 2


def test_no_shore_when_not_swimming_or_with_a_route(game, swimmer):  # noqa: F811
    lua, ns = game
    assert swimmer(*LAKE, swimming=False) is None
    ns.Nav.SetStops(lua.eval("{ { x = 1200.0, y = 400.0, cont = 0, name = 'stop' } }"), False, "red")
    assert swimmer(*LAKE) is None  # (the route's own way out)
    ns.Nav.Clear()
    assert swimmer(*LAKE) is not None


def test_the_shore_is_drawn_on_the_map_and_said_by_the_arrow(game, swimmer):  # noqa: F811
    lua, ns = game
    G, S, A = ns.GPS, ns.Shore, ns.Arrow
    e = swimmer(*LAKE)
    G.Follow()
    G.Update()
    same = lua.eval("function(a, b) return rawequal(a, b) end")
    segs, n = G.DrawnSegs()
    blue = [segs[i] for i in range(1, n + 1) if same(segs[i][5], S.COLOR)]
    assert blue and math.hypot(blue[0][1], blue[0][2]) < 1  # (from the player, the map's middle)
    assert S.label._shown and "yd" in str(S.label._text)
    st = ns.settings.gps
    st.arrow, st.arrowShown, st.dirShown = True, True, True
    A.Apply()
    arrow = lua.globals().AzerothGPSArrow
    for _ in range(3):
        lua.execute("AGPS_T = AGPS_T + 1")
        arrow._scripts.OnUpdate(arrow, 1)
    texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values()
             if w._text and w._shown and w._parent is not None and w._parent._name == "AzerothGPSDirections"]
    assert any("Swim to the shore" in t for t in texts), texts
    assert A.shore is not None and abs(A.shore.x - e.x) < 1
    # (out of the water: gone from both)
    swimmer(*LAKE, swimming=False)
    G.Update()
    segs, n = G.DrawnSegs()
    assert not any(same(segs[i][5], S.COLOR) for i in range(1, n + 1))
    assert not S.label._shown


# ---------------------------------------------------------------------------------------------------- (b) the stops


def _spot(lua, ns, **d):
    def lua_value(v):
        return ("true" if v else "false") if isinstance(v, bool) else f"'{v}'" if isinstance(v, str) else repr(v)
    fields = ", ".join(f"{k} = {lua_value(v)}" for k, v in d.items())
    got = ns.StopSnap.Spot(lua.eval(f"{{ {fields} }}"))
    return tuple(got) if isinstance(got, tuple) and got[0] is not None else None


def _empty_cell_by_land(lua, ns, cont, x0, y0, r=400):
    """A cell with no surface at all (rock: a mountain's side) within r yd of (x0, y0) with walkable ground 2 cells off."""
    return lua.eval(r"""
    function(cont, x0, y0, r)
      local WG = AGPS_NS.WorldGrid
      local c = WG.Cont(cont)
      for dx = -r, r, 8.33 do
        for dy = -r, r, 8.33 do
          local x, y = x0 + dx, y0 + dy
          local key, ci = WG.CellKey(c, math.floor(x / c.cell), math.floor(y / c.cell))
          local t = key and WG.Tile(c, key)
          if t and WG.Count(t, ci) == 0 then
            local k2, c2 = WG.CellKey(c, math.floor(x / c.cell) + 2, math.floor(y / c.cell))
            local t2 = k2 and WG.Tile(c, k2)
            if t2 and WG.Count(t2, c2) > 0 then return x, y end
          end
        end
      end
    end""")(cont, x0, y0, r)


def test_a_stop_on_walkable_ground_stays_where_it_is(game):  # noqa: F811
    lua, ns = game
    ns.WorldGrid.Set(True)
    assert _spot(lua, ns, x=ROAD[0], y=ROAD[1], cont=0) is None
    assert _spot(lua, ns, x=LAKE[0], y=LAKE[1], cont=0) is None  # (water: the route swims to it)


def test_a_stop_in_rock_goes_to_the_nearest_walkable_ground(game):  # noqa: F811
    lua, ns = game
    ns.WorldGrid.Set(True)
    x, y = _empty_cell_by_land(lua, ns, 0, -5400.0, -1700.0)  # (Dun Morogh's mountains, by Gol'Bolar Quarry)
    got = _spot(lua, ns, x=x, y=y, cont=0)
    assert got is not None
    nx, ny, nz = got
    assert 0 < math.hypot(nx - x, ny - y) <= 30
    WG = ns.WorldGrid
    c = WG.Cont(0)
    s = [s for s in WG.SurfacesAt(c, nx, ny, nz).values() if abs(s.z - nz) < 0.01]
    assert s and ((s[0].f // 4) % 2 == 1 or s[0].f % 2 == 1)  # (ground the player reaches)
    # (through Nav: the stop made there is moved, once, and remembers where it was made)
    N = ns.Nav
    N.Clear()
    try:
        N.AddStop(lua.eval(f"{{ x = {x}, y = {y}, cont = 0, name = 'rock' }}"), False, "red")
        d = N.stops[1]
        assert d.snapped and abs(d.x - nx) < 0.01 and abs(d.y - ny) < 0.01
        assert abs(d.snapFrom[1] - x) < 0.01 and abs(d.snapFrom[2] - y) < 0.01
    finally:
        N.Clear()


def test_a_click_on_the_land_over_a_cave_never_goes_down_to_its_floor(game):  # noqa: F811
    # (the cave's own rule, item 82g, kept: a ground click's floor is the ground's, never the cave's under the hill;
    # one clicked on the cave's shown floor stays on that floor)
    lua, ns = game
    G, WG = ns.GPS, ns.WorldGrid
    WG.Set(True)
    ground = G.ClickFloorZ(1, *WAILING)
    got = _spot(lua, ns, x=WAILING[0], y=WAILING[1], cont=1, z=ground)
    if got is not None:
        assert got[2] > ground - G.CAVE_UNDER_YD - 8
    floor = G.CaveFloorZ(1, WAILING[0], WAILING[1], ns.Ground.Sample(1, *WAILING))
    got = _spot(lua, ns, x=WAILING[0], y=WAILING[1], cont=1, z=floor)
    assert got is None or abs(got[2] - floor) < 10  # (on the cave's floor)


def test_an_npcs_stop_keeps_its_npc_and_moves_a_few_yards_at_most(game):  # noqa: F811
    lua, ns = game
    ns.WorldGrid.Set(True)
    # (Cenarion Hold's flight master, on a platform the grid lacks, 24 yd from its nearest cell: left at the NPC)
    assert _spot(lua, ns, x=-6758.6, y=775.6, cont=1, z=89.1, npcId=15177) is None
    # (one 2 yd off the grid, in the water by Meridith the Mermaiden: on to it, its height kept)
    N = ns.Nav
    N.Clear()
    try:
        N.AddStop(lua.eval("{ x = -10293.1, y = -4319.4, cont = 1, z = -37.3, npcId = 1, name = 'npc' }"), False, "red")
        d = N.stops[1]
        assert d.snapped and d.z == pytest.approx(-37.3) and math.hypot(d.x + 10293.1, d.y + 4319.4) <= 10
    finally:
        N.Clear()


def test_no_stop_moves_in_a_capital_or_off_the_continents(game):  # noqa: F811
    lua, ns = game
    ns.WorldGrid.Set(True)
    assert _spot(lua, ns, x=-8830.0, y=630.0, cont=0) is None  # (Stormwind: its city grid's)
    assert _spot(lua, ns, x=1600.0, y=-4400.0, cont=1) is None  # (Orgrimmar)
    assert _spot(lua, ns, x=-5400.0, y=-1700.0, cont=0, corpse=True) is None  # (where you died)


def test_a_stop_goes_where_its_route_ended_not_onto_a_rim_or_a_pocket(game):  # noqa: F811
    # (route-quality 2026-11-26, two trips lost to the first cut: Drygulch Ravine's label went 9 yd onto the ravine's
    # rim, which a corridor search from Ratchet found no way up to, its route ending on the bed 15 yd off before; and
    # Timbermaw Hold's 8 yd onto a ledge of 4 surfaces in the mountain. Now: the surfaces its route ends on first
    # (WorldGrid's Ends), only ground that leads on both ways)
    lua, ns = game
    ns.WorldGrid.Set(True)
    got = _spot(lua, ns, x=983.3, y=-4750.0, cont=1)
    assert got is not None and got[2] < 40  # (the ravine's bed, about 30; its rim is 59)
    got = _spot(lua, ns, x=6750.0, y=-2116.7, cont=1)
    assert got is not None and not (628 <= got[2] <= 634)  # (not the pocket at 629-633)
