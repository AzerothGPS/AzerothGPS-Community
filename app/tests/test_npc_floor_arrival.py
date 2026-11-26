"""An NPC stop up a floor (Kooki3z, 2026-11-22, Stormwind's Canals: "the routing is ending too early and I don't see the
target NPC button. The route should tell me to continue in and up the stairs, if NPC is above or below route isn't
finished"). Acolyte Dellis stands upstairs in the library (104.8 yd high; the streets' roads by it 98 to 100, and
Stormwind's buildings off its streets have no insides in Data/Indoors.lua): the route said "Arrived" at the door.

Now such a stop (Nav.StopOffGround) isn't arrived at by x and y alone: only within OFF_FLOOR_ARRIVE_YD, on its floor
followed, or with its NPC targeted within interact range (CheckInteractDistance, read only) or talked to; the
directions say "Go into the building, then up the stairs" and "Above you". The Target button stays after an NPC stop
is reached until the NPC is targeted or talked to. A quest's turn-in stop goes to the NPC who takes it in
(Data/QuestNpcs.lua: its spawn, height and Target button)."""

import pytest

DELLIS = 5386
DELLIS_XYZ = (-8850.8, 829.8, 104.8)
DELLIS_QUEST = 1363  # (turned in to Acolyte Dellis)
GILROY = 1316  # (Adair Gilroy, Librarian: the same library's ground floor, 98.4)
GILROY_XYZ = (-8865.5, 822.3, 98.4)
ARRIVED = "Arrived"


def guid(npc):
    return f"Creature-0-1-0-1-{npc}-0000ABCDEF"


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
    lua.execute("AGPS_GUIDS = nil AGPS_OLD_CID = rawget(_G, 'CheckInteractDistance') "
                "CheckInteractDistance = function() return AGPS_NEAR == true end AGPS_NEAR = nil")
    ns.Nav.ResetTrack()
    yield lua, ns
    lua.execute("AGPS_GUIDS = nil AGPS_NEAR = nil CheckInteractDistance = AGPS_OLD_CID")
    ns.Nav.Clear()
    ns.settings.gps.targetNpcButton = True
    ns.GPS.UpdateTargetButton()


def _at(lua, x, y):
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0")


def _stop(lua, ns, npc, xyz, name):
    x, y, z = xyz
    ns.Nav.SetStops(lua.eval(f"{{ {{ x = {x}, y = {y}, z = {z}, cont = 0, name = '{name}', npcId = {npc}, "
                             f"npcName = '{name}' }} }}"), False, "red")


def _status(lua, ns, x, y):
    _at(lua, x, y)
    return ns.Nav.Status(x, y, 0) or ""


def _button(lua, ns, t):
    G = ns.GPS
    lua.execute(f"AGPS_T = {t}")
    G.Update()
    G.navPanel.Show(G.navPanel)
    G.UpdateTargetButton()
    return G.targetBtn


def test_an_npc_upstairs_in_a_building_without_insides_is_a_floor_up(clean):
    lua, ns = clean
    N = ns.Nav
    x, y, z = DELLIS_XYZ
    assert not N.InBuilding(0, x, y) and N.InCapital(0, x, y)  # (Stormwind's library: no inside roads)
    way, dz = N.StopOffGround(lua.eval(f"{{ x = {x}, y = {y}, z = {z}, cont = 0 }}"))
    assert way == "up" and dz > N.OFF_FLOOR_Z
    # (the same building's ground floor: its own floor, as before)
    gx, gy, gz = GILROY_XYZ
    assert N.StopOffGround(lua.eval(f"{{ x = {gx}, y = {gy}, z = {gz}, cont = 0 }}"))[0] is None


def test_the_door_below_an_npc_upstairs_is_not_arrived(clean):
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    text = _status(lua, ns, x + 7, y - 2)  # (at the door, 7 yd off: within the old 10 yd circle)
    assert ARRIVED not in text and N.dest is not None
    # (the street's floor followed in through the door: the way on said, into the building and up its stairs, and how
    # far up. With the city grid on, the street's floor is followed already (CityGrid.TrackFloor: 99 at the door, the
    # acolyte at 105): the hint at once; with no floor known it says nothing, Nav.PlayerHeightNear)
    if N.FollowedZ(0) is None:
        assert N.IntoBuildingText(x + 7, y - 2, 0) is None and N.HeightHint(x + 7, y - 2, 0) is None
    else:
        assert "Go into the building, then up the stairs" in N.IntoBuildingText(x + 7, y - 2, 0)
    lua.execute("AGPS_T = 3000")
    N.AnchorFloor(0, x + 7, y - 2, 100.0)
    assert "Go into the building, then up the stairs" in N.IntoBuildingText(x + 7, y - 2, 0)
    # (4.8 yd up: under the "Above you" line's HEIGHT_HINT_YD, the stairs line says it)
    # (its Target button shows meanwhile)
    b = _button(lua, ns, 2000)
    assert b._shown and "/targetexact Acolyte Dellis" in b._attr["macrotext"]


def test_targeting_an_npc_a_floor_off_in_range_does_not_arrive_on_its_own_floor_it_does(clean):
    # (the game's interact range is 3D, about 10 yd, and reaches through a floor: from the door under Acolyte Dellis
    # she's in range. So a floor off, only her window or her floor followed)
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    lua.execute(f"AGPS_GUIDS = {{ target = '{guid(DELLIS)}' }} AGPS_NEAR = false")
    assert ARRIVED not in _status(lua, ns, x + 7, y - 2)  # (targeted, out of range: not yet)
    lua.execute("AGPS_NEAR = true")
    assert ARRIVED not in _status(lua, ns, x + 2.5, y + 4)  # (in range, no floor known: not either)
    N.AnchorFloor(0, x + 2.5, y + 4, 104.8)  # (her floor followed: there)
    assert ARRIVED in (N.Status(x + 2.5, y + 4, 0) or "") and N.dest is None
    # (a ground floor NPC targeted in range: there, as before)
    N.ResetTrack()
    _stop(lua, ns, GILROY, GILROY_XYZ, "Adair Gilroy")
    lua.execute(f"AGPS_GUIDS = {{ target = '{guid(GILROY)}' }}")
    gx, gy, _ = GILROY_XYZ
    assert ARRIVED in _status(lua, ns, gx + 12, gy)


def test_another_target_in_range_or_a_hidden_one_does_not_arrive(clean):
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    lua.execute(f"AGPS_GUIDS = {{ target = '{guid(GILROY)}' }} AGPS_NEAR = true")
    assert ARRIVED not in _status(lua, ns, x + 7, y - 2)
    lua.execute("AGPS_GUIDS = { target = AGPS_SECRET }")
    assert ARRIVED not in _status(lua, ns, x + 7, y - 2)
    assert N.dest is not None


def test_talking_to_the_npc_arrives(clean):
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    assert ARRIVED not in _status(lua, ns, x + 7, y - 2)
    N.OnNpcWindow(DELLIS)
    assert ARRIVED in _status(lua, ns, x + 4, y)


def test_right_by_a_stop_a_floor_off_with_no_npc_arrives_by_an_npc_it_does_not(clean):
    lua, ns = clean
    N = ns.Nav
    x, y, z = DELLIS_XYZ
    N.SetStops(lua.eval(f"{{ {{ x = {x}, y = {y}, z = {z}, cont = 0, name = 'Upstairs' }} }}"), False, "red")
    assert ARRIVED not in _status(lua, ns, x + 7, y)
    assert ARRIVED in _status(lua, ns, x + N.OFF_FLOOR_ARRIVE_YD - 1, y)  # (no NPC to talk to: 3 yd)
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    assert ARRIVED not in _status(lua, ns, x + N.OFF_FLOOR_ARRIVE_YD - 0.5, y)  # (2.5 yd: past NPC_BY_YD)


def test_the_door_right_under_her_is_not_arrived_even_once_the_floor_goes_stale(clean):
    # (Kooki3z's debug line at the library's door, 2026-11-22: "arrived Acolyte Dellis (within 3 yd): 2.9 yd, stop z
    # 104.8, off up 4.8, ..., floor 99.0, target -": her spot is over the doorway. Standing there the floor followed
    # goes stale (no road within TRACK_YD), and that's the same as upstairs by her)
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    px, py = x + 2.9, y
    _at(lua, px, py)
    lua.execute("AGPS_T = 300")
    N.AnchorFloor(0, px, py, 99.0)
    assert N.FollowedZ(0) == 99.0
    assert ARRIVED not in (N.Status(px, py, 0) or "")
    lua.execute("AGPS_T = 310")  # (10 s at the door: the floor followed let go)
    assert N.FollowedZ(0) is None
    assert ARRIVED not in (N.Status(px, py, 0) or "") and N.dest is not None
    lua.execute(f"AGPS_GUIDS = {{ target = '{guid(DELLIS)}' }} AGPS_NEAR = true")  # (targeted from the door: in range)
    assert ARRIVED not in (N.Status(px, py, 0) or "")
    # (upstairs by her: her window opens, there)
    N.OnNpcWindow(DELLIS)
    assert ARRIVED in (N.Status(x + 1, y + 1, 0) or "")


def test_a_ground_floor_npc_still_arrives_as_before_and_its_button_goes_then(clean):
    # (Kooki3z, 2026-11-22: "after destination to the NPC is reached, hide the 'target npc' button")
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, GILROY, GILROY_XYZ, "Adair Gilroy")
    x, y, _ = GILROY_XYZ
    _at(lua, x + 15, y)
    assert _button(lua, ns, 2100)._shown  # (on the way: shown)
    assert ARRIVED in _status(lua, ns, x + 8, y)  # (within the 10 yd circle, as before)
    assert N.dest is None
    assert not _button(lua, ns, 2101)._shown  # (arrived: gone)


def test_after_an_npc_stop_the_next_npc_stops_button_shows(clean):
    lua, ns = clean
    N = ns.Nav
    gx, gy, gz = GILROY_XYZ
    dx, dy, dz = DELLIS_XYZ
    N.SetStops(lua.eval(f"""{{ {{ x = {gx}, y = {gy}, z = {gz}, cont = 0, name = 'Adair Gilroy', npcId = {GILROY},
      npcName = 'Adair Gilroy' }}, {{ x = {dx}, y = {dy}, z = {dz}, cont = 0, name = 'Acolyte Dellis',
      npcId = {DELLIS}, npcName = 'Acolyte Dellis' }} }}"""), False, "red")
    assert ARRIVED not in _status(lua, ns, gx + 8, gy) and N.dest.npcId == DELLIS  # (Gilroy reached: on to Dellis)
    b = _button(lua, ns, 2200)
    assert b._shown and "Acolyte Dellis" in b._attr["macrotext"]


def test_a_quest_turn_in_stop_goes_to_its_npc_with_its_height_and_target_button(clean):
    lua, ns = clean
    N, Lay = ns.Nav, ns.Layers
    x, y, z = DELLIS_XYZ
    assert DELLIS in list(Lay.QuestEnders(DELLIS_QUEST).values())
    # (the quest's map spot, out by the building: the stop moves to the NPC upstairs)
    stop = lua.eval(f"{{ x = {x + 25}, y = {y - 10}, cont = 0, name = 'Turn in: Q', quest = {DELLIS_QUEST}, "
                    "turnin = true, questRoute = true }")
    Lay.AtQuestNpc(stop)
    assert (stop.x, stop.y, stop.z, stop.cont) == (x, y, z, 0)
    assert stop.npcId == DELLIS and stop.npcName == "Acolyte Dellis"
    # (a stop made from the quest's icon on the map, its quest complete: the same, N.QuestStop)
    lua.execute(f"AGPS_OLD_QC = C_QuestLog.IsComplete C_QuestLog.IsComplete = function(id) return id == {DELLIS_QUEST} end")
    try:
        s2 = N.QuestStop(lua.eval(f"{{ x = {x + 25}, y = {y - 10}, cont = 0, name = 'Q' }}"), DELLIS_QUEST)
    finally:
        lua.execute("C_QuestLog.IsComplete = AGPS_OLD_QC")
    assert s2.turnin and s2.npcId == DELLIS and s2.z == z
    # (too far from any NPC who takes it in, or not a turn-in: left where it is)
    far = lua.eval(f"{{ x = {x + 500}, y = {y}, cont = 0, quest = {DELLIS_QUEST}, turnin = true }}")
    Lay.AtQuestNpc(far)
    assert far.npcId is None and far.x == x + 500
    todo = lua.eval(f"{{ x = {x + 25}, y = {y}, cont = 0, quest = {DELLIS_QUEST} }}")
    Lay.AtQuestNpc(todo)
    assert todo.npcId is None
    # (its route: the Target button by it, and not arrived at the door)
    N.SetStops(lua.eval("function(s) return { s } end")(stop), False, "red")
    b = _button(lua, ns, 2300)
    _at(lua, x + 7, y - 2)
    b = _button(lua, ns, 2301)
    assert b._shown and "Acolyte Dellis" in b._attr["macrotext"]


def test_the_quest_enders_file_is_numbers_for_shipped_npcs_only():
    import re

    from azerothgps.questnpcs import FILE, lua_text, shipped_ids

    text = FILE.read_text(encoding="utf-8")
    assert text.startswith("-- GENERATED by `agps quest-npcs --write`")
    body = re.search(r"ns\.QuestEndersPacked = \[==\[\n(.*?)\]==\]", text, re.S).group(1)
    ids = shipped_ids()
    lines = body.strip().split("\n")
    assert len(lines) > 2000
    for line in lines:
        q, npcs = line.split(" ")
        assert q.isdigit() and all(n.isdigit() and int(n) in ids for n in npcs.split(",")), line
    assert lua_text({7: [3, 2]}).count("\n7 3,2\n") == 1


def test_roads_not_ready_yet_is_not_arrived(clean):
    # (in game the roads' index is made in the background: Router.HeightsNear gave nil at the door, and that was taken
    # as "not a floor off": "Arrived" again in Kooki3z's test of #904)
    lua, ns = clean
    N = ns.Nav
    lua.execute("AGPS_OLD_HN = AGPS_NS.Router.HeightsNear AGPS_NS.Router.HeightsNear = function() return nil end")
    try:
        _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
        x, y, _ = DELLIS_XYZ
        assert N.StopOffGround(N.dest)[2] is True
        assert ARRIVED not in _status(lua, ns, x + 7, y - 2) and N.dest is not None
        gx, gy, _ = GILROY_XYZ  # (a ground floor NPC too: not until a floor's known; city routing on (1.4.0's
        # default), the city grid's floor followed tells it without the roads: there, on his floor)
        _stop(lua, ns, GILROY, GILROY_XYZ, "Adair Gilroy")
        text = _status(lua, ns, gx + 8, gy)
        assert (ARRIVED in text) == ns.CityGrid.On(), text
    finally:
        lua.execute("AGPS_NS.Router.HeightsNear = AGPS_OLD_HN")
    _stop(lua, ns, GILROY, GILROY_XYZ, "Adair Gilroy")
    assert ARRIVED in _status(lua, ns, GILROY_XYZ[0] + 8, GILROY_XYZ[1])  # (ready: as before)


def test_a_search_picked_npc_needs_no_quest_data(clean):
    # (Data/QuestNpcs.lua is a new file: after a /reload alone the game hasn't loaded it. The search's NPC stop, its
    # arrival and its Target button don't use it, and quest turn-ins without it stay where they were)
    lua, ns = clean
    N, Lay = ns.Nav, ns.Layers
    lua.execute("AGPS_OLD_QE = AGPS_NS.QuestEndersPacked AGPS_NS.QuestEndersPacked = nil")
    try:
        x, y, z = DELLIS_XYZ
        stop = lua.eval(f"{{ x = {x + 25}, y = {y}, cont = 0, quest = {DELLIS_QUEST}, turnin = true }}")
        Lay.AtQuestNpc(stop)
        assert stop.x == x + 25 and stop.npcId is None
        e = lua.eval(f"{{ name = 'Acolyte Dellis', sub = '', npc = true, id = {DELLIS}, cont = 0, x = {x}, y = {y}, "
                     f"z = {z} }}")
        _at(lua, x + 40, y)
        ns.GPS.PickSearchEntry(e)
        ns.GPS.ConfirmPendingOnClose()
        assert N.dest.npcId == DELLIS and N.dest.z == z
        assert ARRIVED not in _status(lua, ns, x + 7, y - 2)
        b = _button(lua, ns, 2400)
        assert b._shown
    finally:
        lua.execute("AGPS_NS.QuestEndersPacked = AGPS_OLD_QE AGPS_NS.Layers.questEnders = nil")


@pytest.mark.parametrize("grid", [False, True])
def test_with_the_grids_on_or_off_the_door_is_not_arrived_and_the_button_shows(clean, grid):
    # (1.4.0's city and world grids, `cityGrid`/`worldGrid` (unused settings before them): the same with them on, for
    # an NPC picked in the search and a quest's turn-in, the GPS map as the minimap too)
    lua, ns = clean
    N, G, A, st = ns.Nav, ns.GPS, ns.Arrow, ns.settings.gps
    was = st.cityGrid, st.worldGrid
    st.cityGrid, st.worldGrid = grid, grid
    lua.execute("AGPS_OLD_MM = AGPS_NS.GPS.MinimapMode AGPS_NS.GPS.MinimapMode = function() return true end")
    try:
        x, y, z = DELLIS_XYZ
        e = lua.eval(f"{{ name = 'Acolyte Dellis', sub = '', npc = true, id = {DELLIS}, cont = 0, x = {x}, y = {y}, "
                     f"z = {z} }}")
        _at(lua, x + 40, y)
        G.PickSearchEntry(e)
        G.ConfirmPendingOnClose()
        for i, (px, py) in enumerate([(x + 30, y), (x + 15, y - 2), (x + 7, y - 2), (x + 5, y - 1)]):
            assert ARRIVED not in _status(lua, ns, px, py) and N.dest is not None and N.dest.npcId == DELLIS
            A.dir.Show(A.dir)
            b = _button(lua, ns, 2500 + i)
            assert b._shown and lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.Arrow.dir")
        # (by her upstairs: her window opened)
        N.OnNpcWindow(DELLIS)
        assert ARRIVED in _status(lua, ns, x + 1.5, y + 1.5)
        # (a quest's turn-in to her: at her, the same)
        stop = lua.eval(f"{{ x = {x + 25}, y = {y - 10}, cont = 0, name = 'Turn in: Q', quest = {DELLIS_QUEST}, "
                        "turnin = true, questRoute = true }")
        ns.Layers.AtQuestNpc(stop)
        N.SetStops(lua.eval("function(s) return { s } end")(stop), False, "red")
        assert ARRIVED not in _status(lua, ns, x + 7, y - 2)
        A.dir.Show(A.dir)
        b = _button(lua, ns, 2510)
        assert b._shown and "Acolyte Dellis" in b._attr["macrotext"]
    finally:
        lua.execute("AGPS_NS.GPS.MinimapMode = AGPS_OLD_MM")
        st.cityGrid, st.worldGrid = was


def test_with_arrival_reasons_on_each_arrival_says_why_once(clean):
    # (Kooki3z, 2026-11-22: "still arrived too early", no video: `/agps debug arrival` or the debug log on)
    lua, ns = clean
    N = ns.Nav
    lua.execute("AGPS_SAID = {} AGPS_OLD_PRINT = AGPS_NS.Print "
                "AGPS_NS.Print = function(t) AGPS_SAID[#AGPS_SAID + 1] = t end")
    try:
        N.debugArrival = False
        _stop(lua, ns, GILROY, GILROY_XYZ, "Adair Gilroy")
        x, y, _ = GILROY_XYZ
        assert ARRIVED in _status(lua, ns, x + 8, y)
        assert not list(lua.eval("AGPS_SAID").values())  # (off: nothing)
        N.debugArrival = True
        _stop(lua, ns, GILROY, GILROY_XYZ, "Adair Gilroy")
        assert ARRIVED in _status(lua, ns, x + 8, y)
        _status(lua, ns, x + 8, y)
        said = list(lua.eval("AGPS_SAID").values())
        # (by the city grid's floor followed with city routing on, 1.4.0's default: "floor"; else by "distance")
        assert len(said) == 1 and (said[0].startswith("arrived Adair Gilroy (distance): 8.0 yd, stop z 98.4, off no")
                                   or said[0].startswith("arrived Adair Gilroy (floor): 8.0 yd, stop z 98.4, off no")), said
        assert "roads 98" in said[0] or "roads 100" in said[0] or "roads " in said[0]
        lua.execute("AGPS_SAID = {}")
        _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
        lua.execute(f"AGPS_GUIDS = {{ target = '{guid(DELLIS)}' }} AGPS_NEAR = true")
        assert ARRIVED not in _status(lua, ns, DELLIS_XYZ[0] + 2.5, DELLIS_XYZ[1] + 4)
        N.OnNpcWindow(DELLIS)
        assert ARRIVED in _status(lua, ns, DELLIS_XYZ[0] + 2.5, DELLIS_XYZ[1] + 4)
        said = list(lua.eval("AGPS_SAID").values())
        assert len(said) == 1 and "(npc window)" in said[0] and f"target {DELLIS} in range" in said[0]
    finally:
        N.debugArrival = False
        lua.execute("AGPS_NS.Print = AGPS_OLD_PRINT")


def test_targeted_in_range_from_the_floor_below_is_not_arrived(clean):
    # (Kooki3z's debug line, 2026-11-22: "arrived Acolyte Dellis (npc reached): 7.4 yd, stop z 104.8, off up 4.8, ...,
    # floor 100.0, target 5386 in range": the game's interact range is 3D and reaches through the floor)
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    px, py = x + 7.4, y
    lua.execute(f"AGPS_GUIDS = {{ target = '{guid(DELLIS)}' }} AGPS_NEAR = true")
    _at(lua, px, py)
    N.AnchorFloor(0, px, py, 100.0)  # (the ground floor followed)
    assert N.FollowedZ(0) == 100.0 and N.StopOffGround(N.dest)[0] == "up"
    assert ARRIVED not in (N.Status(px, py, 0) or "") and N.dest is not None
    # (its window opened: there)
    N.OnNpcWindow(DELLIS)
    N.AnchorFloor(0, px, py, 100.0)
    assert ARRIVED in (N.Status(px, py, 0) or "")
    # (on its own floor, followed there: targeted in range arrives)
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    N.AnchorFloor(0, x + 4, y, 104.8)
    assert ARRIVED in (N.Status(x + 4, y, 0) or "")



def test_by_nissa_on_her_balcony_no_hint_from_the_mountain_over_ironforge(clean):
    # (Kooki3z, 2026-11-23, 2 yd from Nissa Firestone on her balcony: "Below you, 251 yd down" and "Go into the building,
    # then up the stairs": the ground over Ironforge (760) taken for the player's height, no floor followed)
    lua, ns = clean
    N = ns.Nav
    x, y, z = -4876.6, -1149.1, 512.5
    N.SetStops(lua.eval(f"""{{ {{ x = {x}, y = {y}, z = {z}, cont = 0, name = 'Ironforge First Aid Trainer',
      npcId = 5150, npcName = 'Nissa Firestone' }} }}"""), False, "red")
    px, py = x + 2, y
    _at(lua, px, py)
    assert N.FollowedZ(0) is None and N.PlayerHeightNear(0, px, py) is None
    assert N.HeightHint(px, py, 0) is None
    assert N.IntoBuildingText(px, py, 0) is None
    text = N.Status(px, py, 0) or ""
    assert "251" not in text and "Below you" not in text and "Go into the building" not in text, text


def test_right_by_an_npc_a_floor_off_with_no_other_floor_known_arrives(clean):
    # (Kooki3z, 2026-11-23, 1 yd from Nissa Firestone on her balcony, no floor followed: "this should count as arrived")
    lua, ns = clean
    N = ns.Nav
    x, y, z = -4876.6, -1149.1, 512.5
    N.SetStops(lua.eval(f"""{{ {{ x = {x}, y = {y}, z = {z}, cont = 0, name = 'Ironforge First Aid Trainer',
      npcId = 5150, npcName = 'Nissa Firestone' }} }}"""), False, "red")
    assert ARRIVED not in _status(lua, ns, x + 2.5, y)  # (2.5 yd: not yet)
    assert ARRIVED in _status(lua, ns, x + 1, y)


def test_the_door_under_dellis_stays_not_arrived_floor_known_or_stale(clean):
    # (2.9 yd from her spot: over 2 yd, and with the street's floor followed (99 against her 104.8) another floor)
    lua, ns = clean
    N = ns.Nav
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    px, py = x + 2.9, y
    _at(lua, px, py)
    lua.execute("AGPS_T = 4000")
    N.AnchorFloor(0, px, py, 99.0)
    assert ARRIVED not in (N.Status(px, py, 0) or "")
    lua.execute("AGPS_T = 4010")
    assert N.FollowedZ(0) is None and ARRIVED not in (N.Status(px, py, 0) or "")
    # (and 1.5 yd off her spot with the street's floor still followed: another floor known, not there)
    lua.execute("AGPS_T = 4020")
    N.AnchorFloor(0, x + 1.5, y, 99.0)
    assert ARRIVED not in (N.Status(x + 1.5, y, 0) or "")


def test_bankers_and_auctioneers_arrive_from_across_their_counter(clean):
    # (Kooki3z, 2026-11-23: "except for auctioneers and bankers, they are sometimes further away like in orgrimmar")
    lua, ns = clean
    N = ns.Nav
    for npc, name, (x, y, z) in ((3309, "Karus", (1627.3, -4376.1, 11.8)),
                                 (8673, "Auctioneer Thathung", (1687.3, -4464.7, 20.1))):
        N.SetStops(lua.eval(f"""{{ {{ x = {x}, y = {y}, z = {z}, cont = 1, name = '{name}', npcId = {npc},
          npcName = '{name}' }} }}"""), False, "red")
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x + 6}, {y}, 1")
        assert ARRIVED in (N.Status(x + 6, y, 1) or ""), name  # (from the customer side: as any stop, 10 yd)
    # (one a floor off with no road of its floor (a banker's id at the Canals library's upstairs spot): from 5 yd, no
    # other floor known, there; a stocky NPC's 2 yd would not be; with another floor followed, not there)
    dx, dy, dz = DELLIS_XYZ
    assert N.NpcByYd(lua.eval("{ npcId = 3309 }")) == N.NPC_COUNTER_YD
    assert N.NpcByYd(lua.eval(f"{{ npcId = {DELLIS} }}")) == N.NPC_BY_YD
    N.SetStops(lua.eval(f"""{{ {{ x = {dx}, y = {dy}, z = {dz}, cont = 0, name = 'Banker', npcId = 3309,
      npcName = 'Karus' }} }}"""), False, "red")
    assert ARRIVED in _status(lua, ns, dx + 5, dy)
    N.SetStops(lua.eval(f"""{{ {{ x = {dx}, y = {dy}, z = {dz}, cont = 0, name = 'Banker', npcId = 3309,
      npcName = 'Karus' }} }}"""), False, "red")
    lua.execute("AGPS_T = 5000")
    N.AnchorFloor(0, dx + 5, dy, 99.0)
    assert ARRIVED not in (N.Status(dx + 5, dy, 0) or "")
def test_at_the_routes_end_a_floor_off_shows_the_floor_not_0_yd(clean):
    # (Kooki3z 2026-11-23: "if player gets to the entrance or anything and it says 0 yds 0 s then we arrived (assuming
    # floor is correct)": at the route's end on a floor known to be another, not arrived, and the floor said, not "0 yd")
    lua, ns = clean
    N, G = ns.Nav, ns.GPS
    _stop(lua, ns, DELLIS, DELLIS_XYZ, "Acolyte Dellis")
    x, y, _ = DELLIS_XYZ
    _at(lua, x + 7, y - 2)
    for t in range(4):
        lua.execute(f"AGPS_T = {400 + t}")
        G.Update()
    p = N.route.parts[len(N.route.parts)]
    ex, ey = p.pts[len(p.pts) - 1], p.pts[len(p.pts)]
    _at(lua, ex, ey)
    lua.execute("AGPS_T = 405")
    G.Update()
    text = N.Status(ex, ey, 0) or ""
    assert ARRIVED not in text and N.dest is not None, text
    first = text.split("\n")[0]
    assert "0 yd" not in first and ("Above you" in first or "Upstairs" in first), text
