"""Map data as text (MapText.lua) and the Import and Share window (asked 2026-10-06: herbs, ore, NPCs, pins, roads and
walls imported and exported in game): every line read strictly as data within limits, imports only into the player's
own data, and the parser loadable outside the game (an outside checker runs it in a bare Lua)."""

import pytest

from azerothgps.paths import ADDON_DIR

lua51 = pytest.importorskip("lupa.lua51")


def sandbox(maps=False):
    # (a bare Lua 5.1, no os, io, package, require, dofile or loadfile: as an outside checker runs it)
    lua = lua51.LuaRuntime()
    lua.execute("os, io, package, require, dofile, loadfile = nil, nil, nil, nil, nil, nil")
    ns = lua.table()
    load = lua.eval("function(src, name) return assert(loadstring(src, '@' .. name)) end")
    if maps:
        load((ADDON_DIR / "Data" / "Maps.lua").read_text(encoding="utf-8"), "Data/Maps.lua")("AzerothGPS", ns)
    load((ADDON_DIR / "MapText.lua").read_text(encoding="utf-8"), "MapText.lua")("AzerothGPS", ns)
    return lua, ns


def items(t):
    return [t[i] for i in range(1, len(t) + 1)]


EVERY_KIND = "\n".join([
    "AzerothGPS map data 1",
    "R add 0 1790000001 2000.0,300.0 2010.0,300.0 2020.0,310.0",
    "",
    "R wall 0 1790000002 z=41.5 2000.0,300.0 2000.0,320.0",
    "P add 0 1790000003 2250.5,230.0 z=41.2 down=0 icon=134400 name=Trainer up here",
    "H 0 2100.0,400.0 name=Peacebloom",
    "O 1 -900.5,-4500.0 name=Copper Vein",
    "N 0 2266.0,243.0 name=Innkeeper Renee <Innkeeper>",
    "[12:00] [Bob]: look [AzerothGPS Pin: Old Tree (Tirisfal Glades) @0:2300.0,300.0 #134400]",
    "T 0 1790000000 300 200 1 to=1.0,2.0,0 0,0 30,0",
    "E 36 0 -11208.0,1672.0",
    "P remove 1790000009",
])


def test_every_kind_is_read_and_lines_are_numbered_as_seen():
    lua, ns = sandbox()
    d = ns.MapText.Parse(EVERY_KIND)
    assert len(d.rejected) == 0 and d.skipped == 3 and d.lines == 12  # (T, E, P remove; blank and header: neither)
    (road,) = items(d.roads)
    assert (road.op, road.level, road.time, road.line, len(road.pts)) == ("add", 0, 1790000001, 2, 6)
    (wall,) = items(d.walls)
    assert (wall.op, wall.z, wall.line) == ("wall", 41.5, 4)  # (line 3 blank: counted)
    pin, tag = items(d.pins)
    assert (pin.time, pin.z, pin.down, pin.icon, pin.name, pin.line) == (1790000003, 41.2, False, 134400, "Trainer up here", 5)
    assert (tag.name, tag.place, tag.icon, tag.x, tag.line) == ("Old Tree", "Tirisfal Glades", 134400, 2300.0, 9)
    assert [(h.name, h.level) for h in items(d.herbs)] == [("Peacebloom", 0)]
    assert [(o.name, o.level, o.x) for o in items(d.ore)] == [("Copper Vein", 1, -900.5)]
    (npc,) = items(d.npcs)
    assert (npc.name, npc.title, npc.line) == ("Innkeeper Renee", "Innkeeper", 8)


BAD = [
    ("R add 0 1790000001 2000.0,300.0", "fewer than 2 points"),
    ("R add 77 1790000001 1,1 2,2", "unknown level"),
    ("R add 0 abc 1,1 2,2", "not a time"),
    ("R add 0 1790000001 1e5,1 2,2", "not a point"),
    ("R add 0 1790000001 40000,1 2,2", "not a point"),
    ("R add 0 1790000001 z=1e9 1,1 2,2", "not a height"),
    ("R fly 0 1790000001 1,1 2,2", "not a road or wall"),
    ("P add 0 1790000001 nan,1 name=x", "no position"),
    ("H 0 1,1", "no name"),
    ("H 0 1,1 name=  |  ", "no name"),
    ("O 99 1,1 name=Copper Vein", "unknown level"),
    ("N 0 1,1 extra name=Bob", "not 'N <level> <x,y> name=...'"),
    ("[AzerothGPS Pin: Nowhere @77:1.0,1.0]", "a pin AzerothGPS can't read"),
    ("hello there", "not a line AzerothGPS reads"),
    ("/way Nowhere Land 50 50 X", "unknown zone"),
]


def test_a_bad_line_of_each_kind_is_rejected_with_its_line_and_why():
    lua, ns = sandbox()
    d = ns.MapText.Parse("\n".join(line for line, _ in BAD))
    got = [(r.line, str(r.why)) for r in items(d.rejected)]
    assert [n for n, _ in got] == list(range(1, len(BAD) + 1))
    for (n, why), (line, want) in zip(got, BAD):
        assert want in why, (n, line, why)
    for kind in ("roads", "walls", "pins", "herbs", "ore", "npcs", "ways"):
        assert len(d[kind]) == 0, kind
    assert ns.MapText.Why(d.rejected[1]) == "Line 1: fewer than 2 points"


def test_the_limits():
    lua, ns = sandbox()
    M = ns.MapText
    pts = " ".join(f"{i}.0,1.0" for i in range(2001))
    (r,) = items(M.Parse(f"R add 0 1790000001 {pts}").rejected)
    assert "more than 2000 points" in r.why
    assert len(M.Parse("R add 0 1790000001 " + " ".join(f"{i}.0,1.0" for i in range(2000))).roads) == 1
    # past 5,000 lines: the rest left out, said once (blank lines after it aren't)
    d = M.Parse("\n".join(["H 0 1.0,1.0 name=Peacebloom"] * 5003) + "\n\n\n")
    assert len(d.herbs) == 5000 and d.lines == 5000
    assert [(r.line, "past 5000 lines" in r.why) for r in items(d.rejected)] == [(5001, True)]
    # names: no "|" codes or control characters, at most 160 bytes, not cut in the middle of a letter
    long = "a" + "é" * 100
    (h,) = items(M.Parse(f"H 0 1.0,1.0 name={long}").herbs)
    name = h.name.encode("utf-8") if isinstance(h.name, str) else h.name  # (lupa: a str when it's whole UTF-8)
    assert len(name) <= 160 and name.decode("utf-8") == "a" + "é" * 79
    (h,) = items(M.Parse("H 0 1.0,1.0 name=|cffff0000Red|r\tPeacebloom").herbs)
    assert str(h.name) == "cffff0000Redr Peacebloom"
    # icons: a file id or a plain path; anything else the default
    icons = ["icon=Interface\\Icons\\INV_Misc_Map02", "icon=../x|y", "icon=12.5", "icon=-3", "icon=" + "a" * 201]
    got = [items(M.Parse(f"P add 0 1790000001 1.0,1.0 {i} name=P").pins)[0].icon for i in icons]
    assert got == ["Interface\\Icons\\INV_Misc_Map02", None, None, None, None]
    # times: a whole number of seconds, before 2100
    assert "not a time" in items(M.Parse("P add 0 9999999999 1.0,1.0 name=P").rejected)[0].why
    # levels: AzerothGPS's own
    assert [bool(M.KnownLevel(v)) for v in (0, 1, 2991, 10001, 20036, 5, 1.5)] == [True] * 5 + [False] * 2


def test_way_lines_read_with_the_maps_alone():
    # (the outside checker loads Data/Maps.lua, then MapText.lua: nothing else)
    lua, ns = sandbox(maps=True)
    d = ns.MapText.Parse("/way Elwynn Forest 43.2 65.1 First Stop\n\n/way Elwin Forest 10 10 Typo\nDurotar 50 50")
    (a, b) = items(d.ways)
    assert (a.name, a.x, a.y, a.line) == ("First Stop", 43.2, 65.1, 1) and b.line == 4 and b.name is None
    assert [(r.line, str(r.why)) for r in items(d.rejected)] == [(3, "unknown zone 'Elwin Forest'")]
    assert ns.MapText.KnownLevel(0) and ns.MapText.KnownLevel(1) and ns.MapText.KnownLevel(10001)
    assert not ns.MapText.KnownLevel(77)
    # (the user's 1.1.5 test, 2026-10-06: their own export pasted back, "unknown level '2991'" on Zephras Isle's lines:
    # an isle with zone maps only, none of the continent type) every level the export writes is taken back in
    assert ns.MapText.KnownLevel(2991) and not ns.MapText.KnownLevel(30)  # (a battleground's map isn't a level)
    d = ns.MapText.Parse("H 2991 3960.6,1734.6 name=Peacebloom\nO 2991 4023.4,1753.1 name=Copper Vein")
    assert [str(h.name) for h in items(d.herbs)] == ["Peacebloom"] and [str(o.name) for o in items(d.ore)] == ["Copper Vein"]
    assert not items(d.rejected)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start

    lua, ns = start()
    return lua, ns


@pytest.fixture
def mine(game):
    # (the player's own map data, put back after each test)
    lua, ns = game
    keys = ("tracks", "pins", "nodes", "npcs")
    saved = {k: ns.db[k] for k in keys}
    for k in keys:
        ns.db[k] = lua.table()
    yield lua, ns
    for k in keys:
        ns.db[k] = saved[k]


def test_importing_every_kind_into_the_players_own_data(mine):
    lua, ns = mine
    I = ns.Import
    before = ns.unsavedOwn or 0
    res = I.ImportText(EVERY_KIND, "stops", False)
    A = res.added
    # (roads and walls: not imported here since 1.3.14, with the map editor gone; the dev addon takes them in)
    assert (A.roads, A.walls, A.pins, A.herbs, A.ore, A.npcs) == (0, 0, 2, 1, 1, 1)
    assert res.had == 0 and len(res.rejected) == 0 and res.skipped == 5 and res.stops is None
    assert str(I.ImportSummary(res)) == ("Added 2 pins, 1 herb, 1 ore, 1 NPC. "
                                         "5 lines not imported here (faster trips, dungeons' ways in, roads, walls).")
    assert len(list(ns.db.tracks.values())) == 0
    # pins: the player's own, marked imported, never shared
    pins = {str(p.name): p for p in ns.Pins.Own().values()}
    assert set(pins) == {"Trainer up here", "Old Tree"}
    assert all(p.imported and not p.shared for p in pins.values()) and pins["Trainer up here"].time == 1790000003
    # herbs and ore: unconfirmed until gathered; NPCs: until talked to
    (herb,) = items(ns.db.nodes[0])
    (ore,) = items(ns.db.nodes[1])
    assert (herb[3], herb[4], herb[6]) == ("Peacebloom", "herb", True) and (ore[3], ore[4], ore[6]) == ("Copper Vein", "ore", True)
    npc = ns.db.npcs["imp:innkeeper renee"]
    assert (npc.name, npc.title, npc.imported, npc.cont) == ("Innkeeper Renee", "Innkeeper", True, 0)
    # one unsaved change for all of it (Save Now)
    assert (ns.unsavedOwn or 0) == before + 1
    # again: all of it known
    again = I.ImportText(EVERY_KIND, "stops", False)
    assert sum(again.added[k] for k in ("roads", "walls", "pins", "herbs", "ore", "npcs")) == 0 and again.had == 5
    assert str(I.ImportSummary(again)).startswith("Nothing new added. 5 you had already.")


def test_my_map_data_copies_and_imports_back(mine):
    lua, ns = mine
    I = ns.Import
    lua.execute("""
      local db = AGPS_NS.db
      db.nodes[0] = { { 2100.0, 400.0, "Peacebloom", "herb", 3 }, { 2150.0, 410.0, "Silverleaf", "herb", 1, true } }
      db.nodes[1] = { { -900.5, -4500.0, "Copper Vein", "ore", 2 } }
      db.npcs[3934] = { name = "Innkeeper Renee", title = "Innkeeper", cont = 0, x = 2266.0, y = 243.0 }
      db.npcs[68] = { name = "Stormwind City Guard", cont = 0, x = 1, y = 1, common = true }
      db.npcs["imp:bob"] = { name = "Bob", cont = 0, x = 5, y = 5, imported = true }
      db.pins[1] = { level = 0, x = 2250.5, y = 230.0, z = 41.2, icon = 134400, name = "Up here", time = 1790000003 }
      db.tracks[1] = { op = "add", drawn = true, continent = 0, time = 1790000001, pts = { 2000, 300, 2010, 300 } }
    """)
    kinds = lua.eval("{ herbs = true, ore = true, npcs = true, pins = true, roads = true, walls = true }")
    text, n = I.MapDataText(kinds)
    lines = str(text).split("\n")
    assert lines[0] == "AzerothGPS map data 1" and n == len(lines) - 1 == 5
    assert "H 0 2100.0,400.0 name=Peacebloom" in lines and "O 1 -900.5,-4500.0 name=Copper Vein" in lines
    assert "N 0 2266.0,243.0 name=Innkeeper Renee <Innkeeper>" in lines
    assert "P add 0 1790000003 2250.5,230.0 z=41.2 icon=134400 name=Up here" in lines
    assert "R add 0 1790000001 2000.0,300.0 2010.0,300.0" in lines
    assert not any(w in text for w in ("Silverleaf", "Guard", "Bob"))  # (not theirs: unconfirmed, common, imported)
    only = I.MapDataText(lua.eval("{ pins = true }"))
    assert str(only[0]).split("\n")[1:] == ["P add 0 1790000003 2250.5,230.0 z=41.2 icon=134400 name=Up here"]
    # another player's map, empty: the text brings it all in
    for k in ("tracks", "pins", "nodes", "npcs"):
        ns.db[k] = lua.table()
    res = I.ImportText(text, "stops", False)
    A = res.added
    assert (A.roads, A.walls, A.pins, A.herbs, A.ore, A.npcs) == (0, 0, 1, 1, 1, 1) and len(res.rejected) == 0
    assert res.skipped == 1 and len(list(ns.db.tracks.values())) == 0  # (the road: not imported here since 1.3.14)
    (pin,) = ns.Pins.Own().values()
    assert (pin.name, pin.z, pin.icon, pin.time) == ("Up here", 41.2, 134400, 1790000003)
    assert ns.db.npcs["imp:innkeeper renee"].title == "Innkeeper"


def test_a_way_line_with_no_name_is_not_a_node(mine):
    # (found reading the code, 2026-10-06: "/way Elwynn Forest 43.2 65.1" named itself "Elwynn Forest 43.2, 65.1", whose
    # "Forest" has "ore" in it: an ore node; Darkshore's too, and Stranglethorn's "thorn" a herb)
    lua, ns = mine
    I, L = ns.Import, ns.Layers
    res = I.ImportText("/way Elwynn Forest 43.2 65.1\n/way Stranglethorn Vale 50 50\n"
                       "/way Elwynn Forest 40 60 Copper Vein", "nodes", False)
    assert (res.added.ore, res.added.herbs) == (1, 0)
    assert [str(r) for r in res.rejected.values()] == ["Line 1: a herb or ore needs its name",
                                                       "Line 2: a herb or ore needs its name"]
    assert L.NodeKind("Elwynn Forest 43.2, 65.1") is None and L.NodeKind("Darkshore 50.0, 50.0") is None
    # (only the herbs and veins there are: "Copper Ore" is the vein's item, 2026-11-05)
    assert L.NodeKind("Copper Ore") is None and L.NodeKind("Rich Thorium Vein") == "ore"
    added, skipped, errors = L.ImportNodes("/way Elwynn Forest 43.2 65.1")
    assert (added, skipped, list(errors.values())) == (0, 0, ["a line with no herb or ore name"])


def test_the_window_imports_and_copies(mine):
    lua, ns = mine
    I = ns.Import
    I.Toggle()
    f = lua.globals().AzerothGPSImport
    try:
        # (the boxes' words tick them too: their hit area over the label, the 1.1.5 test pass, v115-imp-d)
        for box in (f.asNodes, f.asNpcs):
            assert box._hitInsets and box._hitInsets[2] <= -(box.label.GetStringWidth(box.label))
        assert f._shown and str(f._title if f._title else "") in ("", "Import and Share")
        f.edit.SetText(f.edit, "H 0 2100.0,400.0 name=Peacebloom\nH 0 1,1\nN 0 2266.0,243.0 name=Innkeeper Renee")
        f.go.GetScript(f.go, "OnClick")(f.go)
        status = str(f.status.GetText(f.status))
        assert "Added 1 herb, 1 NPC." in status and "1 line rejected:" in status and "Line 2: no name" in status
        assert f._shown  # (map data: what happened stays in view)
        # copy: only what's ticked
        for key, c in f.kinds.items():
            c.SetChecked(c, key == "herbs")
        f.mine.GetScript(f.mine, "OnClick")(f.mine)
        assert "Nothing of yours to copy" in str(f.status.GetText(f.status))  # (the herb is imported: not theirs)
        lua.execute("AGPS_NS.db.nodes[0][1][6] = nil")  # (gathered there: confirmed)
        f.mine.GetScript(f.mine, "OnClick")(f.mine)
        assert str(f.edit.GetText(f.edit)) == "AzerothGPS map data 1\nH 0 2100.0,400.0 name=Peacebloom"
        assert "1 line selected above" in str(f.status.GetText(f.status))
    finally:
        f.Hide(f)


INBOX = r"""AzerothGPS_ImportInbox = {
  { made = 1791000001, text = "H 0 2100.0,400.0 name=Peacebloom\n/way Elwynn Forest 50 50 X\nnot a line" },
  { made = 1791000002, text = "P add 0 1790000003 2250.5,230.0 icon=134400 name=Up here" },
  { made = "x", text = "H 0 1.0,1.0 name=Bad" }, "a string", { made = 1791000003 }, { made = 1.5, text = "" },
  { made = 1791000002, text = "H 0 9.0,9.0 name=Twice" },
}"""


def test_an_import_inbox_is_offered_once_and_acknowledged(mine):
    # (asked 2026-10-06: map data a tool on the player's PC leaves in a global, AzerothGPS_ImportInbox, read as data at
    # login and offered once; each entry handled acknowledged in AzerothGPSDB.importInbox[made] for that tool to read)
    lua, ns = mine
    I = ns.Import
    saved = ns.db.importInbox
    try:
        ns.db.importInbox = None
        lua.execute(INBOX)
        assert I.CheckInbox()
        box = I.inboxBox
        q = str(box.text._text)
        assert "1 pin, 1 herb" in q and "2 lines can't be read" in q  # (the /way line and the bad one)
        box.yes.GetScript(box.yes, "OnClick")(box.yes)
        acks = ns.db.importInbox
        assert sorted(acks.keys()) == [1791000001, 1791000002]  # (the malformed ones passed over, the twice-made once)
        a1, a2 = acks[1791000001], acks[1791000002]
        assert (a1.added.herbs, a1.rejected, a1.had, a1.declined) == (1, 2, 0, None) and a1.at
        assert a2.added.pins == 1 and a2.added.herbs == 0
        (herb,) = items(ns.db.nodes[0])
        assert herb[3] == "Peacebloom" and herb[6]  # (unconfirmed, as any import)
        assert len(ns.Nav.stops) == 0  # (an inbox never changes the route)
        assert not I.CheckInbox()  # (handled: not asked again)
        # a new one declined: never asked again
        lua.execute('table.insert(AzerothGPS_ImportInbox, { made = 1791000009, text = "O 1 1.0,1.0 name=Copper Vein" })')
        assert I.CheckInbox()
        box = I.inboxBox
        box.no.GetScript(box.no, "OnClick")(box.no)
        assert acks[1791000009].declined and ns.db.nodes[1] is None
        assert not I.CheckInbox()
        # unanswered (Escape, the time out): offered again next time
        lua.execute('table.insert(AzerothGPS_ImportInbox, { made = 1791000010, text = "O 1 1.0,1.0 name=Tin Vein" })')
        assert I.CheckInbox()
        box = I.inboxBox
        box.GetScript(box, "OnHide")(box)
        assert acks[1791000010] is None
        assert I.CheckInbox()
    finally:
        lua.execute("AzerothGPS_ImportInbox = nil")
        ns.db.importInbox = saved


def test_an_import_inbox_with_nothing_readable_is_acknowledged_without_asking(mine):
    lua, ns = mine
    I = ns.Import
    saved = ns.db.importInbox
    try:
        ns.db.importInbox = None
        lua.execute(r'AzerothGPS_ImportInbox = { { made = 7, text = "garbage\n/way Elwynn Forest 1 1 Stop" } }')
        I.inboxBox = None
        assert not I.CheckInbox() and I.inboxBox is None
        a = ns.db.importInbox[7]
        assert a.rejected == 2 and not a.declined
    finally:
        lua.execute("AzerothGPS_ImportInbox = nil")
        ns.db.importInbox = saved


def test_inbox_acknowledgments_are_kept_for_good(game):
    # (asked 2026-10-06: keep data forever) however many and however old, the inbox's acknowledgments stay: one let go
    # was offered again while its entry was still in an inbox
    lua, ns = game
    I = ns.Import
    saved = ns.db.importInbox
    try:
        acks = lua.table()
        for made in range(1, 206):
            acks[made] = lua.table_from({"at": 1000 + made})  # (years old)
        acks["junk"] = 5  # (not one: left as it is too)
        ns.db.importInbox = acks
        lua.execute("AzerothGPS_ImportInbox = nil")
        assert not I.CheckInbox()
        assert len(list(ns.db.importInbox.keys())) == 206
    finally:
        ns.db.importInbox = saved
