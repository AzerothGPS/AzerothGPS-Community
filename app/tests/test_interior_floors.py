"""The floors' heights in the buildings' inside maps and editing a building there (1.3.10, asked 2026-11-19: "When
mousing over an interior the road data is hidden when really we should fade all the lines out and only show the road
data for that interior for editing. Also should try to get floor data height for each of those floors").

- interiorfloors.py: a room's floors from its flat floor faces; the shipped data matches ns.WMOs's rooms; the survey's
  list out and its heights back (only the rooms measured change; nothing measured twice).
- In game: over a building's inside map the roads show, the building's own whole and the rest faded; the hover says
  its floors' heights; a road drawn there takes the floor's height as `gz` (never `zs`)."""

import json
import re
from pathlib import Path

import pytest

from azerothgps import interiorfloors as F

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
GOLDSHIRE_INN = 7952345  # (the Lion's Pride Inn's model)


def tri(z, x0=0.0, y0=0.0, side=4.0, dz=0.0):
    return ((x0, y0, z), (x0 + side, y0, z + dz), (x0, y0 + side, z))


def test_a_rooms_floors_are_its_flat_faces_by_height():
    tris = []
    for i in range(4):  # (the ground floor: 4 faces of 8 sq yd, a little uneven)
        tris.append((0, tri(0.1 * i, x0=4 * i)))
    for i in range(3):  # (upstairs, 6 yd up)
        tris.append((6, tri(6.0, x0=4 * i)))
    for k in range(10):  # (the stairs between: small, steep faces)
        tris.append((k * 0.6, tri(k * 0.6, side=1.0, dz=0.5)))
    tris.append((3.0, tri(3.0, side=1.5)))  # (a table: too small for a floor)
    tris.append((0.9, tri(0.9, side=3.0)))  # (a dais 0.9 up: the ground floor)
    got = F.room_floors(tris)
    assert len(got) == 2 and got[0][0] == pytest.approx(0.15, abs=0.2) and got[1][0] == pytest.approx(6.0, abs=0.1)


def test_a_faces_height_under_a_point():
    t = ((0, 0, 0), (10, 0, 10), (0, 10, 0))
    assert F.face_z_at(t, 5, 1) == pytest.approx(5.0)
    assert F.face_z_at(t, 9, 9) is None


def shipped_floors():
    text = (ADDON / "Data" / "InteriorFloors.lua").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^  \[(\d+)\] = \{ (.*) \},$", text, re.M):
        out[int(m.group(1))] = re.findall(r'"([^"]*)"', m.group(2))
    return out


def test_the_shipped_floors_match_the_models_rooms():
    wmos, places = F.shipped_interiors()
    floors = shipped_floors()
    assert len(floors) > 250
    for fid, rooms in floors.items():
        assert fid in wmos and len(rooms) == len(wmos[fid]), fid
        for cell in rooms:
            hs = [float(v) for v in cell.split()]
            assert hs == sorted(hs)
    # the Lion's Pride Inn: the cellar, the ground floor, upstairs (the model's own heights; placed at 56.5)
    inn = {float(v) for cell in floors[GOLDSHIRE_INN] for v in cell.split()}
    assert {0.4, 7.3} <= {round(h, 1) for h in inn}, inn
    # every placed building's model is there (or has no floor at all)
    used = {p[0] for c in (0, 1) for p in places[c] if p[0] in wmos}
    assert len(used - set(floors)) < 10


def test_the_survey_list_is_short_and_says_where_to_go():
    todo = F.load_todo()
    assert len(todo) <= 80  # (empty once every room is surveyed)
    ids = [e["id"] for e in todo]
    assert len(ids) == len(set(ids))
    for e in todo:
        assert e["map"] in (0, 1) and e["go"].startswith(".go xyz ") and len(e["place"]) == 4
        assert re.match(r"^\d+:\d+$", e["id"])


def test_the_survey_goes_out_to_the_addon_that_loads_it_and_its_heights_come_back(tmp_path, monkeypatch):
    addons = tmp_path / "Interface" / "AddOns"
    other = addons / "Something"
    other.mkdir(parents=True)
    (other / "Something.toc").write_text("## Interface: 16001\nSomething.lua\n", encoding="utf-8")
    sv = addons / "Survey"
    sv.mkdir()
    (sv / "Survey.toc").write_text("## Interface: 16001\n## SavedVariables: SurveyDB\nFloorSurvey.lua\nSurvey.lua\n",
                                   encoding="utf-8")
    todo = [{"id": "100:2", "map": 0, "x": 1.0, "y": 2.0, "z": 30.5, "name": "Hall", "need": 'a "floor"',
             "known": [1.5], "place": [0.0, 0.0, 20.0, 1.0], "go": ".go xyz 1 2 30.5 0"},
            {"id": "100:3", "map": 1, "x": 5.0, "y": 6.0, "z": 7.0, "name": "", "need": "x", "known": [],
             "place": [0.0, 0.0, 20.0, 1.0], "go": ".go xyz 5 6 7 1"}]
    assert F.export_survey([addons], todo, log=lambda *_: None) == 1
    text = (sv / "FloorSurvey.lua").read_text(encoding="utf-8")
    assert not (other / "FloorSurvey.lua").exists()
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    ns = lua.table()
    lua.eval("function(src, ns) assert(load(src))('Survey', ns) end")(text, ns)
    assert ns.FloorSurvey[1].id == "100:2" and ns.FloorSurvey[1].need == 'a "floor"' and ns.FloorSurvey[2].map == 1
    # measured: one room, in the saved variables of the addon's account
    wtf = tmp_path / "WTF" / "Account" / "ACC" / "SavedVariables"
    wtf.mkdir(parents=True)
    (wtf / "Survey.lua").write_text(
        'SurveyDB = { ["floorSurvey"] = { ["100:2"] = { ["z"] = 27.3, ["place"] = { 0, 0, 20, 1 } } } }\n',
        encoding="utf-8")
    doc = F.read_survey([addons])
    assert doc["rooms"]["100:2"]["zs"] == [27.3]
    path = tmp_path / "survey.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    over = tmp_path / "interior_floors.json"
    assert F.import_survey(path, over) == 1
    got = F.load_overrides(over)
    assert got == {(100, 2): [7.3]}
    # into the Lua: only that room changes; a model with no line yet gets one
    lua_text = '-- x\nlocal _, ns = ...\nns.InteriorFloors = {\n  [100] = { "1", "", "1.5", "" },\n}\n'
    out = F.patch_lua(lua_text, {**got, (200, 1): [3.0]}, {200: 3})
    assert '  [100] = { "1", "", "1.5 7.3", "" },' in out  # (added: the room's other floors kept)
    assert '  [200] = { "", "3", "" },' in out
    assert F._merged([0.1, 5, 8], [7.6]) == [0.1, 5, 7.6]  # (a floor near the measured one gives way to it)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def inn_place(ns):
    for p in ns.Interiors[0].values():
        if p[1] == GOLDSHIRE_INN and abs(p[2] + 9464.25) < 1:
            return p
    raise AssertionError("no Lion's Pride Inn")


def test_a_buildings_floors_at_a_spot(game):
    lua, ns = game
    G = ns.GPS
    p = inn_place(ns)
    w = ns.WMOs[GOLDSHIRE_INN]
    every = G.InteriorFloorsAt(p, w, None)
    hs = [every[k] for k in range(1, len(every) + 1)]
    assert any(abs(h - 56.9) < 0.6 for h in hs) and any(abs(h - 63.8) < 0.6 for h in hs), hs


def hover(lua, ns, x, y):
    """The mouse over the building at world (x, y) of Elwynn (G.BuildingHover's result), the map zoomed in there."""
    G = ns.GPS
    p, w, room = G.InteriorUnder(x, y, 0)
    assert p is not None
    G.hoverInside = lua.table_from({1: p, 2: w, 3: room, "cont": 0})
    G.hoverInsideKey = "test:" + str(p[1])
    G.hoverDismissKey = None
    G.LookAt(0, x, y, 80)
    lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
    G.Update()
    return p


def test_over_a_buildings_inside_map_its_roads_show_and_the_rest_fade(game):
    lua, ns = game
    G = ns.GPS
    lua.execute("""
      AGPS_REAL_SEAMLESS = AGPS_REAL_SEAMLESS or AGPS_NS.GPS.Seamless
      AGPS_NS.GPS.Seamless = function() return true end
    """)
    try:
        G.SetRoadMode(True)
        p = hover(lua, ns, -9464.0, 36.0)  # (the Lion's Pride Inn, Goldshire: its east end, both floors)
        assert G.zoomedInside == GOLDSHIRE_INN
        assert G.editInterior is not None and G.editInterior[1][1] == GOLDSHIRE_INN and G.editInterior[1][2] == p[2]
        assert G.InEditInterior(-9464.0, 36.0) and not G.InEditInterior(-9400.0, 100.0)
        segs = G.LayoutRoads(-9464.0, 36.0, 0, 0, 80, 200, G.InEditInterior)
        alphas = [segs[k][6] for k in range(1, len(segs) + 1)]
        assert any(a == pytest.approx(G.INTERIOR_FADE_ALPHA) for a in alphas if a is not None)  # (Goldshire's roads)
        assert any(a is None for a in alphas)  # (the inn's own)
        # the hover: its floors' heights there, with the ground's
        text = G.FloorHeightText(-9464.0, 36.0)
        assert text is not None and text.startswith("Floors: ") and "57" in text and "64" in text, text
        # the floors offered to Shift + mouse wheel: Goldshire's inn has roads on its floors (Data/Indoors.lua): theirs,
        # as ever (a floor road's `zs`); a building with none offers its floors' heights, as ground heights (`gz`)
        floors = G.EditFloors(0, -9464.0, 36.0)
        assert len(floors) >= 2
        lua.execute("AGPS_REAL_DEBUGGRAPH = AGPS_NS.Router.DebugGraph; AGPS_NS.Router.DebugGraph = function() return nil end")
        try:
            floors = G.EditFloors(0, -9464.0, 36.0)
        finally:
            lua.execute("AGPS_NS.Router.DebugGraph = AGPS_REAL_DEBUGGRAPH")
        n = len(floors)
        assert n >= 2 and all(floors[k].gz for k in range(1, n + 1))
        upstairs = [floors[k] for k in range(1, n + 1) if abs(floors[k].z - 63.8) < 0.6][0]
        G.editFloor = upstairs
        assert G.EditFloor(0, None) is None
        # a road drawn in it: the floor picked as its ground height there, the land's outside
        saved = ns.db.tracks
        try:
            ns.db.tracks = lua.table()
            G.FinishRoad(lua.table(pts=lua.table(-9464.0, 36.0, -9463.0, 35.0, -9420.0, 60.0), cont=0), False, False)
            t = ns.db.tracks[1]
            assert t.zs is None and t.z is None
            assert t.gz[1] == pytest.approx(63.8, abs=0.6) and t.gz[2] == pytest.approx(63.8, abs=0.6)
            assert t.gz[3] is not False and abs(t.gz[3] - 63.8) > 2  # (out in Goldshire: the ground's)
            # no floor picked: the lowest floor there
            G.editFloor = None
            G.FinishRoad(lua.table(pts=lua.table(-9464.0, 36.0, -9460.0, 36.5, -9456.0, 37.0), cont=0), False, False)
            low = ns.db.tracks[2].gz[1]
            assert low < 63.8 - 2
        finally:
            ns.db.tracks = saved
        # the mouse gone off it: nothing edited, the roads as ever
        G.hoverInside, G.hoverInsideKey = None, None
        G.Update()
        assert G.editInterior is None
    finally:
        G.editFloor = None
        G.SetRoadMode(False)
        lua.execute("AGPS_NS.GPS.Seamless = AGPS_REAL_SEAMLESS")
        G.Follow()


ROW = {"id": "100:2", "map": 0, "x": 100.0, "y": 200.0, "z": 31.5, "expect": 30.0, "band": [20.0, 35.0],
       "ground": 21.0, "place": [90.0, 190.0, 20.0, 1.0], "need": "x", "go": ".go xyz 100 200 31.5 0"}


def test_a_height_measured_is_checked_against_the_room():
    ok, msg = F.check_reading(ROW, 0, 102.0, 199.0, 30.4)
    assert ok and msg == "Captured: 30.4 yd"
    assert F.check_reading(ROW, 1, 100.0, 200.0, 30.0) == (False, "Not it: you're on another map. Teleport there first.")
    assert "from the spot" in F.check_reading(ROW, 0, 140.0, 200.0, 30.0)[1]
    ok, msg = F.check_reading(ROW, 0, 100.0, 200.0, 21.2)  # (on the ground floor: the terrain's height)
    assert not ok and "ground outside" in msg
    ok, msg = F.check_reading(ROW, 0, 100.0, 200.0, 25.0)
    assert not ok and msg.endswith("Go up.")
    ok, msg = F.check_reading(ROW, 0, 100.0, 200.0, 40.0)
    assert not ok and msg.endswith("Go down.")
    ok, _ = F.check_reading({**ROW, "expect": None}, 0, 100.0, 200.0, 26.0)  # (no height known: any in the room)
    assert ok


def test_the_watcher_reads_the_servers_log_and_the_chat_log():
    from azerothgps import floorsurvey as W
    log = [
        "2026-11-19_13:56:54 Command: go xyz 1 2 [Player: Testy (Player-1-0000000E) (Account: 3) X: -8835.532 Y: "
        "621.922 Z: 93.414345 Map: 0 (Eastern Kingdoms) Area: 1519 (Stormwind City) Zone: Unknown Selected:  (0)]",
        "2026-11-19_13:57:01 Command: gps [Player: Testy (Player-1-0000000E) (Account: 3) X: 100.5 Y: 200.25 Z: 30.5 "
        "Map: 0 (Eastern Kingdoms) Area: 1 (x) Zone: y Selected:  (0)]",
        "2026-11-19_13:57:02 Command: gps [Player: Bot (Player-1-00000004) (Account: 1) X: 1 Y: 2 Z: 3 Map: 1 (K)]",
    ]
    got = W.parse_lines(log, account=3)
    assert got == [{"map": 0, "x": 100.5, "y": 200.25, "z": 30.5, "who": "Testy"}]
    assert len(W.parse_lines(log)) == 2
    chat = ["11/19 13:57:01.123  Map: 1 (Kalimdor) Zone: 14 (Durotar) Area: 1",
            "11/19 13:57:01.123  X: 1633.4 Y: -4439.4 Z: 15.4 Orientation: 3.1",
            "11/19 13:57:01.123  GroundZ: 15.4 FloorZ: 15.4 have height 1 have vmap 1"]
    assert W.parse_lines(chat) == [{"map": 1, "x": 1633.4, "y": -4439.4, "z": 15.4}]


def test_the_watcher_follows_a_file_and_keeps_each_height_at_once(tmp_path):
    from azerothgps import floorsurvey as W
    log = tmp_path / "GM.log"
    log.write_text("old line\n", encoding="utf-8")
    src = W.FileSource(log)
    assert src.poll() == []  # (from its end: nothing old)
    with open(log, "a", encoding="utf-8") as f:
        f.write("2026 Command: gps [Player: T (P) (Account: 3) X: 100 Y: 200 Z: 25 Map: 0 (E)]\n2026 part")
    lines = src.poll()
    assert len(lines) == 1 and src.rest == "2026 part"
    rows = [ROW, {**ROW, "id": "100:3", "expect": None}]
    caps = tmp_path / "captures.json"
    s = W.Survey(rows, caps)
    ok, msg = s.reading(W.parse_lines(lines, 3)[0])
    assert not ok and msg.endswith("Go up.") and s.current()["id"] == "100:2"
    assert s.accept_anyway() and s.current()["id"] == "100:3"
    assert json.loads(caps.read_text(encoding="utf-8"))["rooms"]["100:2"]["accepted"] is True
    ok, msg = s.reading({"map": 0, "x": 100.0, "y": 200.0, "z": 30.0})
    assert ok and s.current() is None
    # opened again: what's kept is done, nothing measured twice
    s2 = W.Survey(rows, caps)
    assert s2.current() is None and s2.left() == 0
    # the import reads the window's file first
    doc = F.read_survey([], caps)
    assert doc["rooms"]["100:3"]["zs"] == [30.0] and doc["rooms"]["100:3"]["place"] == ROW["place"]


def test_the_watcher_follows_a_command_from_its_offset(tmp_path):
    import sys
    from azerothgps import floorsurvey as W
    data = tmp_path / "log.txt"
    data.write_bytes(b"abc\n")
    script = tmp_path / "tail.py"
    script.write_text("import sys\nb = open(sys.argv[1], 'rb').read()\no = int(sys.argv[2])\n"
                      "print('@@%d' % len(b))\nsys.stdout.write(b[o:].decode() if o >= 0 else '')\n", encoding="utf-8")
    src = W.CommandSource([sys.executable, str(script), str(data), "{offset}"])
    assert src.poll() == [] and src.offset == 4
    with open(data, "ab") as f:
        f.write(b"one\ntwo\n")
    assert src.poll() == ["one", "two"]
