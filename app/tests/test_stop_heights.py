"""Every stop gets a height when it's made (1.4.0, Kooki3z 2026-11-23). On Thunder Bluff's main mesa, at its east rim,
a stop placed on the map on the Mulgore ground below had no height, and the route was a straight 126 yd line off the
cliff ("4 s"). Now: its own height, else the best guess in range (Nav.GuessStopZ): an NPC's spot's, its town place's
floor, the grid's floor at the spot (the ground's on a zone's map), a building's ground floor, the map's ground, a
road's, NPC's or place's within STOP_Z_YD; beyond that "height unknown" (never the player's), said to a listening
hook. Down from the rim: the lift without a fall spell, a Slow Fall jump with one."""

import pytest

pytest.importorskip("lupa")

RIM = (-1235.0, -145.0, 163.0)  # (Thunder Bluff's main mesa, its east rim)
BELOW = (-1250.0, -230.0)  # (the Mulgore ground under it, about 17)
ELDER_RISE = (-1046.9, -283.9)  # (the druid trainers' rise: its mesa, about 159)
IRONFORGE = (-4900.0, -950.0)  # (the Great Forge's floor, about 502; the mountain over it 807)
BRILL_INN = (2262.0, 238.0)  # (in the inn, by no place: its ground floor 34, its trainers' floor 41)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.settings.gps.cityGrid = True
    return lua, ns


def guess(lua, ns, cont, x, y, **k):
    d = {"x": x, "y": y, "cont": cont}
    d.update(k)
    return tuple(ns.Nav.GuessStopZ(lua.table_from(d)))


def made(lua, ns, cont, x, y):
    """The stop as the route keeps it, set with no height (a map double-click's)."""
    ns.Nav.SetStops(lua.eval(f"{{ {{ x = {x}, y = {y}, cont = {cont} }} }}"), False, "red")
    s = ns.Nav.stops[1]
    return ns.Nav.StopZ(s), s.zSource  # (the route's height for it: its own, else the guess, `guessZ`)


def test_the_ground_below_thunder_bluff_gets_the_ground_s_height(game):
    lua, ns = game
    z, src = made(lua, ns, 1, *BELOW)
    assert src == "terrain" and abs(z - 17) < 3, (z, src)


def test_a_stop_on_elder_rise_gets_the_mesa_s_height(game):
    lua, ns = game
    z, src = guess(lua, ns, 1, *ELDER_RISE)
    assert src == "grid" and abs(z - 159) < 3, (z, src)


def test_a_way_in_ironforge_gets_the_city_s_floor_not_the_mountain_over_it(game):
    lua, ns = game
    z, src = guess(lua, ns, 0, *IRONFORGE)
    assert src == "grid" and 495 < z < 510, (z, src)


def test_open_ground_gets_the_ground_s_height(game):
    lua, ns = game
    z, src = guess(lua, ns, 1, -2000.0, -500.0)
    assert src == "terrain" and z == pytest.approx(ns.Nav.GroundAt(1, -2000.0, -500.0)), (z, src)
    # (kept aside as the stop's ground in the open land, its routes as before; by a city's grid it's the stop's height)
    ns.Nav.SetStops(lua.eval("{ { x = -2000, y = -500, cont = 1 } }"), False, "red")
    s = ns.Nav.stops[1]
    assert s.z is None and s.zSource == "terrain" and s.groundZ == pytest.approx(z) and ns.Nav.StopZ(s) is None


def test_a_spot_in_a_building_with_floors_on_the_zone_map_gets_its_ground_floor(game):
    lua, ns = game
    z, src = guess(lua, ns, 0, *BRILL_INN)
    assert src == "building" and abs(z - 34) < 2, (z, src)


def test_its_own_height_is_kept_and_none_in_range_is_unknown_and_said(game):
    lua, ns = game
    assert guess(lua, ns, 1, *BELOW, z=40.0) == (40.0, "own")
    seen = []
    ns.Nav.heightUnknownHook = lambda stop: seen.append(dict(stop))
    try:
        # (far out at sea off the map's ground: no grid, no ground, nothing within range)
        z, src = guess(lua, ns, 1, -20000.0, -20000.0, name="Nowhere")
    finally:
        ns.Nav.heightUnknownHook = None
    assert z is None and src == "unknown"
    assert seen and seen[0]["name"] == "Nowhere" and seen[0]["x"] == -20000.0 and seen[0]["why"]


def _route(lua, ns):
    z, _src = made(lua, ns, 1, *BELOW)
    ns.Router.Reset()
    return ns.Router.Route(1, *RIM[:2], *BELOW, lua.table_from({"z": RIM[2], "tz": z}))


def _kinds(r):
    return [r.kinds[i] for i in range(1, len(r.pts) // 2)]


def test_from_thunder_bluff_s_east_rim_to_the_ground_the_lift_without_a_fall_spell(game):
    lua, ns = game
    lua.execute("IsPlayerSpell = function() return false end")
    ns.FallSpells.Refresh()
    r = _route(lua, ns)
    R = ns.Router
    assert r.length > 200, r.length  # (not 87 yd off the cliff)
    assert R.KIND_DROP not in _kinds(r) and R.KIND_LIFT_DOWN in _kinds(r), _kinds(r)


def test_from_thunder_bluff_s_east_rim_to_the_ground_a_slow_fall_jump_with_one(game):
    lua, ns = game
    lua.execute("IsPlayerSpell = function(id) return id == 130 end")
    lua.execute("GetItemCount = function(id) return id == 17056 and 5 or 0 end")
    ns.FallSpells.Refresh()
    try:
        r = _route(lua, ns)
        assert r.length < 150, r.length
        assert ns.Router.KIND_DROP in _kinds(r)
    finally:
        lua.execute("IsPlayerSpell = function() return false end")
        lua.execute("GetItemCount = function() return 0 end")
        ns.FallSpells.Refresh()
