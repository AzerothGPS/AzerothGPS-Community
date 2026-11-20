"""Picking a building's floor with the road and wall tools (1.3.10, asked 2026-11-19: "When road or wall tools are on,
editing, and the crosshair is over a building, keep the floors showing, and if possible when scrolling to the floor to
edit, show the appropriate floor's interior").

- The building's floors listed under the legend, the one picked highlighted, kept while the pointer moves over it and a
  moment (FLOOR_BUILDING_GRACE) past it; its inside map too (G.BuildingHover).
- Shift + mouse wheel picks the floor and the inside map shows that floor's rooms (G.FloorArtRoom); a building whose one
  room holds every floor keeps its map. The pick is remembered per building: back over it, picked again.
- The hover's floors: at most FLOOR_TIP_MAX heights with no floor picked (Blackrock Mountain's hall has 47), only the
  floor picked otherwise.
- Never the player's height (WoW Forever has none): the floor is the player's pick. On both maps."""

import pytest

GOLDSHIRE_INN = 7952345  # (the Lion's Pride Inn: a cellar, the ground floor, upstairs, each its own rooms)
INN_X, INN_Y = -9464.0, 36.0
ONE_ROOM = 106800  # (a house whose one room holds both its floors, 4.1 and 8.7 up)
ONE_ROOM_AT = (2912.34, 379.73)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


@pytest.fixture()
def tools(game):
    lua, ns = game
    G = ns.GPS
    lua.execute("""
      AGPS_REAL_SEAMLESS = AGPS_REAL_SEAMLESS or AGPS_NS.GPS.Seamless
      AGPS_NS.GPS.Seamless = function() return true end
    """)
    G.floorPicks = lua.table()
    G.SetRoadMode(True)
    try:
        yield lua, ns
    finally:
        G.SetRoadMode(False)
        G.hoverInside, G.hoverInsideKey = None, None
        G.editFloor, G.lastFloorZ = None, None
        lua.execute("AGPS_NS.GPS.Seamless = AGPS_REAL_SEAMLESS")
        G.Follow()


def tick(lua, secs):
    lua.execute("AGPS_T = (AGPS_T or 1000) + %f" % secs)


def place_of(ns, model, x, y, cont=0):
    for p in ns.Interiors[cont].values():
        if p[1] == model and abs(p[2] - x) < 1 and abs(p[3] - y) < 1:
            return p
    raise AssertionError("no placement of %d" % model)


def hover(lua, ns, x, y, cont=0, secs=0.1):
    """The mouse over the building at world (x, y) (G.BuildingHover's result), the map zoomed in there, redrawn."""
    G = ns.GPS
    p, w, room = G.InteriorUnder(x, y, cont)
    assert p is not None
    G.hoverInside = lua.table_from({1: p, 2: w, 3: room, "cont": cont})
    G.hoverInsideKey = "test:" + str(p[1]) + ":" + str(room)
    G.hoverDismissKey = None
    G.LookAt(cont, x, y, 80)
    tick(lua, secs)
    G.Update()
    return p


def unhover(lua, ns, secs):
    G = ns.GPS
    G.hoverInside, G.hoverInsideKey = None, None
    tick(lua, secs)
    G.Update()


def fids(quads):
    return {q[1] for q in quads.values()}


def art_of(G, p, w, room):
    return fids(G.LayoutInterior(p[2], p[3], p, w, room, 0, 80, 200))


def test_the_floors_stay_listed_over_the_building_and_a_moment_past_it(tools):
    lua, ns = tools
    G = ns.GPS
    hover(lua, ns, INN_X, INN_Y)
    fb = G.floorBuilding
    assert fb is not None and fb.place[1] == GOLDSHIRE_INN and len(fb.floors) >= 3
    state = str(G.FloorStateText())
    assert "Floors: " in state and "(top)" in state and "(ground)" in state, state
    _, rows, _ = G.ToolLegendRows()
    assert any(str(r.text) == "Pick a floor" for r in rows.values())
    fb.marker = 7  # (the same table kept: not made again)
    # moving over it, room to room: the same building, the same list
    hover(lua, ns, -9458.0, 30.0)
    assert G.floorBuilding.marker == 7
    # off its rooms a moment (a gap, its edge): still listed
    unhover(lua, ns, 0.2)
    assert G.editInterior is None and G.floorBuilding.marker == 7
    assert "(top)" in str(G.FloorStateText())
    # gone past the grace: no more
    unhover(lua, ns, G.FLOOR_BUILDING_GRACE + 0.2)
    assert G.floorBuilding is None


def test_the_inside_map_stays_a_moment_as_the_pointer_crosses_a_gap(tools):
    lua, ns = tools
    G = ns.GPS
    lua.execute("""
      AGPS_REAL_CW, AGPS_REAL_ZOK = AGPS_NS.GPS.CursorWorld, AGPS_NS.GPS.InteriorZoomOK
      AGPS_CW = { %f, %f, 0 }
      AGPS_NS.GPS.CursorWorld = function() return AGPS_CW[1], AGPS_CW[2], AGPS_CW[3] end
      AGPS_NS.GPS.InteriorZoomOK = function() return true end
    """ % (INN_X, INN_Y))
    try:
        tick(lua, 1)
        G.BuildingHover()
        hit = G.hoverInside
        assert hit is not None and hit[1][1] == GOLDSHIRE_INN
        lua.execute("AGPS_CW[1], AGPS_CW[2] = -9300, 200")  # (off it: the road outside)
        tick(lua, 0.2)
        G.BuildingHover()
        assert G.hoverInside is not None and G.hoverInside[1][1] == GOLDSHIRE_INN  # (kept: the grace)
        tick(lua, G.FLOOR_BUILDING_GRACE + 0.2)
        G.BuildingHover()
        assert G.hoverInside is None
        # the tools off: gone at once, as ever
        G.SetRoadMode(False)
        lua.execute("AGPS_CW[1], AGPS_CW[2] = %f, %f" % (INN_X, INN_Y))
        tick(lua, 0.2)
        G.BuildingHover()
        assert G.hoverInside is not None
        lua.execute("AGPS_CW[1], AGPS_CW[2] = -9300, 200")
        tick(lua, 0.2)
        G.BuildingHover()
        assert G.hoverInside is None
    finally:
        lua.execute("AGPS_NS.GPS.CursorWorld, AGPS_NS.GPS.InteriorZoomOK = AGPS_REAL_CW, AGPS_REAL_ZOK")


def test_shift_wheel_steps_the_floors_and_shows_each_floors_inside_map(tools):
    lua, ns = tools
    G = ns.GPS
    p = hover(lua, ns, INN_X, INN_Y)
    w = ns.WMOs[GOLDSHIRE_INN]
    floors = G.EditFloors(G.shownLevel, INN_X, INN_Y)
    n = len(floors)
    assert n >= 2
    seen = {}
    for _ in range(n):
        assert G.StepEditFloor(1)
        f = G.editFloor
        assert f is not None and f.z is not None
        tick(lua, 0.1)
        G.Update()
        assert G.artRoom is not None and G.artRoom.floorPick
        # the legend: that floor highlighted
        assert "|cffffd100" in str(G.FloorStateText())
        seen[round(f.z)] = art_of(G, p, w, G.artRoom)
    assert len(seen) == n  # (each floor in turn: none skipped, close as a building's lie)
    # the floors' maps differ: upstairs isn't the ground floor's rooms
    arts = list(seen.values())
    assert len({frozenset(a) for a in arts}) >= 2, seen
    top = seen[max(seen)]
    upstairs = {b[1] for k in range(1, len(w.groups) + 1) if w.groups[k][3] > 6
                for b in w.groups[k].blocks.values()}
    assert top and top <= upstairs, (top, upstairs)
    # past the top: all floors again, the room under the pointer's map as ever
    assert G.StepEditFloor(1)
    assert G.editFloor is None
    tick(lua, 0.1)
    G.Update()
    assert G.artRoom is None


def test_a_building_with_one_room_for_its_floors_keeps_its_map(tools):
    lua, ns = tools
    G = ns.GPS
    x, y = ONE_ROOM_AT
    p = place_of(ns, ONE_ROOM, x, y)
    w = ns.WMOs[ONE_ROOM]
    room = [w.groups[k] for k in range(1, len(w.groups) + 1) if w.groups[k]["in"] and w.groups[k].blocks][0]
    whole = art_of(G, p, w, room)
    floors = G.InteriorFloorsAt(p, w, room)
    assert len(floors) == 2
    G.floorBuilding = lua.table_from({"key": G.FloorBuildingKey(p, room, 0), "place": p, "wmo": w, "room": room,
                                      "cont": 0, "floors": floors, "at": 0})
    try:
        for k in (1, 2):
            G.editFloor = lua.table_from({"z": floors[k], "gz": True})
            r, band = G.FloorArtRoom(p, w, room, 0)
            assert r is not None and band[1] == pytest.approx(floors[k])
            assert art_of(G, p, w, r) == whole
    finally:
        G.floorBuilding, G.editFloor = None, None


def test_the_pick_comes_back_with_the_building(tools):
    lua, ns = tools
    G = ns.GPS
    hover(lua, ns, INN_X, INN_Y)
    assert G.editFloor is None  # (first time over it: every floor)
    G.StepEditFloor(1)
    G.StepEditFloor(1)
    picked = G.editFloor.z
    unhover(lua, ns, G.FLOOR_BUILDING_GRACE + 0.5)
    assert G.floorBuilding is None and G.editFloor is None  # (left: the pick before it, none)
    hover(lua, ns, INN_X, INN_Y)
    assert G.floorBuilding is not None and G.editFloor is not None and G.editFloor.z == pytest.approx(picked)
    tick(lua, 0.1)
    G.Update()
    assert G.artRoom is not None


def test_the_hover_lists_three_floors_at_most_and_only_the_one_picked(tools):
    lua, ns = tools
    G = ns.GPS
    hs = lua.table(*[100.0 + 5 * k for k in range(47)])
    got = G.TipFloorHeights(hs, None)
    assert [got[k] for k in range(1, len(got) + 1)] == [100.0, 100.0 + 5 * 23, 330.0]  # (lowest, middle, top)
    got = G.TipFloorHeights(hs, 201.0)
    assert [got[k] for k in range(1, len(got) + 1)] == [195.0, 200.0, 205.0]  # (round the floor picked last)
    # Blackrock Mountain's hall (one room 272 yd tall, 47 floors' heights), the pointer in it
    lua.execute("""
      AGPS_REAL_EIFA = AGPS_NS.GPS.EditInteriorFloorsAt
      AGPS_NS.GPS.EditInteriorFloorsAt = function() return AGPS_HS end
    """)
    lua.globals().AGPS_HS = hs
    try:
        G.editFloor, G.lastFloorZ = None, None
        text = str(G.FloorHeightText(0, 0))
        lines = text.split("\n")
        assert lines[0] == "Floors: 100, 215, 330 yd (+44 more)", text
        assert lines[1] == "Shift + mouse wheel: pick a floor"
        assert all(len(line) <= 60 for line in lines)
        G.editFloor = lua.table_from({"z": 240.0, "gz": True})
        assert str(G.FloorHeightText(0, 0)) == "Floor 29 of 47: 240 yd"
        G.editFloor = lua.table_from({"z": 1000.0, "gz": True})
        assert str(G.FloorHeightText(0, 0)) == "Floor picked: 1000 yd"
    finally:
        lua.execute("AGPS_NS.GPS.EditInteriorFloorsAt = AGPS_REAL_EIFA")
        G.editFloor = None
    # the legend's list: the top, the ground and those round the pick, "..." between
    floors = lua.table(*[lua.table_from({"z": 100.0 + 5 * k, "gz": True}) for k in range(47)])
    text = str(G.FloorListText(floors, lua.table_from({"z": 240.0})))
    assert text.count("|cffffd100") == 1 and "29: 240 yd" in text and "47 (top): 330 yd" in text
    assert "1 (ground): 100 yd" in text and text.count("...") == 2
    assert G.FloorListText(lua.table(lua.table_from({"z": 1.0})), None) is None


def test_on_the_world_map_too(tools):
    from test_world_map_host import SETUP
    lua, ns = tools
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    was = {k: st[k] for k in ("useWorldMap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.execute("WorldMapFrame:Show()")
        G.WorldMapChanged()
        assert G.WorldMapHosted()
        G.SetRoadMode(True)
        p = hover(lua, ns, INN_X, INN_Y)
        assert G.floorBuilding is not None and G.floorBuilding.place[1] == GOLDSHIRE_INN
        G.RoadHint()
        assert G.ToolLegendShown() and "(top)" in str(G.toolLegend.shownState)
        assert G.StepEditFloor(-1)  # (down from all floors: the top one)
        tick(lua, 0.1)
        G.Update()
        assert G.artRoom is not None
        w = ns.WMOs[GOLDSHIRE_INN]
        assert art_of(G, p, w, G.artRoom)
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
