"""A guard's map marker as a stop (item 97, Kooki3z 2026-11-26, live: Orgrimmar's Hunter's Hall). A guard's "Orgrimmar
Hunter's Hall" isn't our place's name ("Orgrimmar Hunter Trainer", Data/CityPlaces.lua), so the stop it made had no
height, no NPC and no Target button, and standing among the hunter trainers it said "Below you, 50 yd down": its height
was taken from the map's ground, the rock 9 yd high under the hall's floor at 59 (Nav.LandHeightHint).

Now the marker is matched to the shipped place it marks (Layers.GuardPlace) and its stop goes to that place's NPC
(Layers.GuardStop, as a place's icon clicked does), and a stop with no height of its own in a capital is never given
the map's ground's."""

import pytest

HALL_PLAYER = (2085.9, -4609.1)  # (Orgrimmar map 66.2, 20.1: among the hunter trainers, on the hall's floor, 59)
HUNTER_TRAINERS = {3352, 3406, 3407}  # (Ormak Grimshot, Xor'juul, Sian'dur: 58.7 to 58.8)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


@pytest.fixture()
def clean(game):
    lua, ns = game
    ns.Nav.ResetTrack()
    ns.Nav.Clear()
    yield lua, ns
    lua.execute("C_GossipInfo = AGPS_OLD_GOSSIP AGPS_OLD_GOSSIP = nil")
    ns.Nav.Clear()
    ns.Nav.ResetTrack()


def _world(lua, ui, u, v):
    x, y, cont = lua.eval(f"function() return AGPS_NS.Layers.MapToWorld({ui}, {u}, {v}) end")()
    return x, y, cont


def test_the_guards_names_are_matched_to_the_shipped_places(game):
    lua, ns = game
    Lay = ns.Layers
    x, y, cont = _world(lua, 1454, 0.672, 0.188)  # (by the hunter trainers' place, 67.0 18.5)
    assert Lay.GuardPlace(cont, x, y, "Orgrimmar Hunter's Hall") == "Orgrimmar Hunter Trainer"
    assert Lay.GuardPlace(cont, x, y, "Orgrimmar Hunter Trainer") == "Orgrimmar Hunter Trainer"
    bx, by, _ = _world(lua, 1454, 0.497, 0.693)
    assert Lay.GuardPlace(cont, bx, by, "Bank of Orgrimmar") == "Orgrimmar Bank"
    ux, uy, ucont = _world(lua, 1458, 0.475, 0.158)
    assert Lay.GuardPlace(ucont, ux, uy, "Undercity Warrior Trainers") == "Undercity Warrior Trainer"
    # (nothing shipped of that kind near: none, not the nearest other place)
    assert Lay.GuardPlace(cont, x, y, "Orgrimmar Mailbox") is None
    # (in another language's client: the only place close by)
    px, py, _ = _world(lua, 1454, 0.670, 0.185)
    assert Lay.GuardPlace(cont, px + 3, py, "Halle der Jäger") is None
    lua.execute("AGPS_OLD_LOCALE = AGPS_NS.LOCALE AGPS_NS.LOCALE = 'deDE'")
    try:
        assert Lay.GuardPlace(cont, px + 3, py, "Halle der Jäger") == "Orgrimmar Hunter Trainer"
        assert Lay.GuardPlace(cont, px + 40, py, "Halle der Jäger") is None
    finally:
        lua.execute("AGPS_NS.LOCALE = AGPS_OLD_LOCALE")


def test_in_the_hunters_hall_the_guards_stop_is_on_its_floor_with_the_target_button(clean):
    lua, ns = clean
    N, G = ns.Nav, ns.GPS
    px, py = HALL_PLAYER
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {px}, {py}, 1")
    u, v = 0.672, 0.188
    # (the guard's marker, as the game gives it: C_GossipInfo's)
    lua.execute(f"""
      AGPS_OLD_GOSSIP = C_GossipInfo
      C_GossipInfo = {{
        GetPoiForUiMapID = function() return 7 end,
        GetPoiInfo = function() return {{ name = "Orgrimmar Hunter's Hall", position = {{ x = {u}, y = {v} }} }} end,
      }}
      AGPS_OLD_BEST = C_Map.GetBestMapForUnit
      C_Map.GetBestMapForUnit = function() return 1454 end
    """)
    try:
        ns.Layers.OnGossipPoi(True)
    finally:
        lua.execute("C_Map.GetBestMapForUnit = AGPS_OLD_BEST")
    d = N.dest
    assert d is not None and d.name == "Orgrimmar Hunter's Hall"
    assert d.npcId in HUNTER_TRAINERS and d.z == pytest.approx(58.75, abs=0.1)
    for t in range(8):  # (the floor followed on the hall's)
        lua.execute(f"AGPS_T = {500 + t}")
        N.TrackCityZ(1, px, py)
    assert N.HeightHint(px, py, 1) is None
    assert "Below you" not in str(N.Status(px, py, 1) or "")
    # (the Target button: by the NPC)
    lua.execute("AGPS_T = 600")
    G.Update()
    G.navPanel.Show(G.navPanel)
    G.UpdateTargetButton()
    b = G.targetBtn
    assert b._shown and "/targetexact" in b._attr["macrotext"]


def test_a_stop_in_a_capital_with_no_height_of_its_own_is_never_given_the_rock_under_it(clean):
    lua, ns = clean
    N = ns.Nav
    px, py = HALL_PLAYER
    x, y, cont = _world(lua, 1454, 0.672, 0.188)
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {px}, {py}, 1")
    assert N.GroundAt(1, x, y) < 20  # (the map's ground there: the rock under the hall)
    N.SetStops(lua.eval(f"{{ {{ x = {x}, y = {y}, cont = 1, name = 'a spot in the hall' }} }}"), False, "red")
    d = N.dest
    assert d.z is None and d.guessZ == pytest.approx(59, abs=1.5)
    for t in range(8):
        lua.execute(f"AGPS_T = {700 + t}")
        N.TrackCityZ(1, px, py)
    assert N.HeightHint(px, py, 1) is None
