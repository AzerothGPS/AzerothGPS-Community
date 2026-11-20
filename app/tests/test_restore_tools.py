"""The road and wall tools' restoring (asked 2026-11-14): the magic eraser takes the player's own changes of the tools
on out under its circle (a stroke running on past it cut at its edge), Restore Zone those in the zone under the
crosshair, Restore Continent all on the continent (asked twice); Undo puts them back. And Shift-click drawing, always since 2026-11-19 (its option gone): the
tools draw only with Shift held, a plain drag pans the map."""

import pytest


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()
    return lua, ns


@pytest.fixture()
def tools(game):
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    ns.db.tracks = lua.eval("{}")
    lua.execute("""
      AGPS_ASKED = {}
      AGPS_ASK_REAL = AGPS_NS.GPS.Ask
      AGPS_NS.GPS.Ask = function(name, text, yes, no, onYes)
        table.insert(AGPS_ASKED, text)
        if AGPS_ANSWER ~= false then onYes(false) end
      end
      AGPS_SHIFT_REAL, AGPS_CTRL_REAL = IsShiftKeyDown, IsControlKeyDown
      AGPS_SHIFT, AGPS_CTRL, AGPS_ANSWER = true, false, nil -- (Shift held: the tools draw)
      IsShiftKeyDown = function() return AGPS_SHIFT end
      IsControlKeyDown = function() return AGPS_CTRL end
      AGPS_NS.Record.restores = {}
    """)
    try:
        yield lua, ns
    finally:
        G.SetEraserMode(False)
        G.SetRoadMode(False)
        G.SetWallMode(False)
        st.eraserYd = None
        ns.db.tracks = lua.eval("{}")
        lua.execute("""AGPS_NS.GPS.Ask = AGPS_ASK_REAL
          IsShiftKeyDown, IsControlKeyDown = AGPS_SHIFT_REAL, AGPS_CTRL_REAL""")


def _track(lua, op, cont, t, pts, **kw):
    extra = "".join(f", {k} = {v}" for k, v in kw.items())
    return lua.eval(f"{{ op = '{op}', drawn = true, continent = {cont}, zone = 'x', time = {t}, "
                    f"pts = {{ {', '.join(str(p) for p in pts)} }}{extra} }}")


def _tracks(ns):
    return [(str(t.op), _pts(t)) for t in ns.db.tracks.values()]


def _pts(t):
    return [float(t.pts[i]) for i in range(1, len(t.pts) + 1)]


def _circle(x0, y0, r):
    return lambda x, y: (x - x0) ** 2 + (y - y0) ** 2 <= r * r


def test_the_eraser_cuts_a_road_at_its_edge_and_undo_puts_it_back(tools):
    lua, ns = tools
    Rec = ns.Record
    road = _track(lua, "add", 0, 1000, [2200, 300, 2220, 300, 2240, 300, 2260, 300, 2280, 300, 2300, 300])
    wall = _track(lua, "wall", 0, 1001, [2240, 290, 2260, 310])
    loop = _track(lua, "remove", 0, 1002, [2245, 295, 2255, 295, 2255, 305, 2245, 305, 2245, 295], area="true")
    far = _track(lua, "add", 0, 1003, [2400, 300, 2450, 300])
    for t in (road, wall, loop, far):
        Rec.Save(t)
    near = lua.eval("function(x0, y0, r) return function(x, y) return (x - x0)^2 + (y - y0)^2 <= r * r end end")
    whole, cut, kept = Rec.Restore("road", 0, near(2250, 300, 15), lua.eval("{ 2235, 285, 2265, 315 }"), 5)
    assert (whole, cut, kept) == (1, 1, 2)  # (the erased loop whole; the road cut in two)
    got = _tracks(ns)
    assert ("wall", [2240, 290, 2260, 310]) in got  # (the wall tools' changes: not the road tools' to restore)
    assert ("add", [2400, 300, 2450, 300]) in got  # (far away: kept)
    a, b = [p for op, p in got if op == "add" and p[0] < 2350]
    # (cut at the circle's edge: points put in along the stretches it crosses, 5 yd apart)
    assert a[:4] == [2200, 300, 2220, 300] and 2230 <= a[-2] < 2235 and b[-2:] == [2300, 300] and 2265 < b[0] <= 2270
    assert not any(op == "remove" for op, _ in got)
    times = [t.time for t in ns.db.tracks.values()]
    assert len(set(times)) == len(times)  # (a part a stroke of its own: a time, its key, of its own)
    # Undo: all as it was, in the same order
    Rec.Undo()
    assert _tracks(ns) == [("add", [2200, 300, 2220, 300, 2240, 300, 2260, 300, 2280, 300, 2300, 300]),
                           ("wall", [2240, 290, 2260, 310]),
                           ("remove", [2245, 295, 2255, 295, 2255, 305, 2245, 305, 2245, 295]),
                           ("add", [2400, 300, 2450, 300])]


def test_something_drawn_after_a_restore_is_undone_first(tools):
    lua, ns = tools
    Rec = ns.Record
    Rec.Save(_track(lua, "wall", 0, 1000, [2200, 300, 2300, 300]))
    near = lua.eval("function(x, y) return x > 2240 and x < 2260 end")
    assert Rec.Restore("wall", 0, near, None, 5)[1] == 1
    Rec.Save(_track(lua, "wall", 0, 2000, [2500, 300, 2600, 300]))
    Rec.Undo()  # (the wall drawn last)
    a, b = [p for _, p in _tracks(ns)]
    assert (a[0], a[-2], b[0], b[-2]) == (2200, 2240, 2260, 2300)
    Rec.Undo()  # (then the restore)
    assert [p for _, p in _tracks(ns)] == [[2200, 300, 2300, 300]]


def test_a_long_stretch_through_the_circle_is_cut_though_its_points_are_outside(tools):
    # (a road drawn zoomed out: points far apart; the eraser between two of them still takes it out there)
    lua, ns = tools
    Rec = ns.Record
    Rec.Save(_track(lua, "add", 0, 1000, [2000, 300, 2500, 300]))
    near = lua.eval("function(x, y) return (x - 2250)^2 + (y - 300)^2 <= 400 end")
    whole, cut, kept = Rec.Restore("road", 0, near, None, 10)
    assert (whole, cut, kept) == (0, 1, 2)
    a, b = [p for _, p in _tracks(ns)]
    assert a[0] == 2000 and 2220 <= a[-2] < 2230 and 2270 < b[0] <= 2280 and b[-2] == 2500


def test_a_recorded_walk_cut_keeps_its_notes_for_each_part(tools):
    lua, ns = tools
    Rec = ns.Record
    walk = lua.eval("""{ op = 'add', drawn = true, recorded = true, continent = 0, zone = 'x', time = 1000,
      pts = { 0, 0, 2, 0, 4, 0, 6, 0, 8, 0, 10, 0 }, zs = { 1, 1, 2, 2, 3, 3 }, z = 1,
      rec = { ind = '001111', ts = '0,5,5,5,5,5', zt = { 1, 'Road', 5, 'Cellar' }, pk = { 2, 9 } },
      stairs = { 5, 6 } }""")
    Rec.Save(walk)
    near = lua.eval("function(x, y) return x > 3 and x < 5 end")  # (point 3, at x 4)
    assert Rec.Restore("road", 0, near, None, None)[1] == 1
    a, b = list(ns.db.tracks.values())
    assert _pts(a) == [0, 0, 2, 0] and _pts(b) == [6, 0, 8, 0, 10, 0]
    assert a.rec.ind == "00" and b.rec.ind == "111" and b.rec.ts == "5,5,5"
    assert list(a.zs.values()) == [1, 1] and list(b.zs.values()) == [2, 3, 3] and b.z == 2
    assert list(b.rec.zt.values()) == [1, "Road", 2, "Cellar"]  # (the room's name at the part's start, then its own)
    assert list(b.rec.pk.values()) == [1, 9]
    assert list(b.stairs.values()) == [2, 3] and a.stairs is None


def test_the_magic_eraser_on_the_map_restores_under_its_circle(tools):
    lua, ns = tools
    G, st = ns.GPS, ns.settings.gps
    f = lua.eval("AzerothGPSFrame")
    G.SetRoadMode(True)
    st.eraserYd = 10
    G.SetEraserMode(True)
    assert G.eraserMode
    # (where the pointer is on the map: the eraser's stroke starts there)
    f._scripts.OnMouseDown(f, "LeftButton")
    x, y = G.lasso.pts[1], G.lasso.pts[2]
    G.lasso = None
    ns.Record.Save(_track(lua, "add", 0, 1000, [x - 50, y, x, y, x + 50, y]))
    ns.Record.Save(_track(lua, "wall", 0, 1001, [x - 50, y, x + 50, y]))
    f._scripts.OnMouseDown(f, "LeftButton")
    assert G.lasso.eraser
    f._scripts.OnMouseUp(f, "LeftButton")
    got = _tracks(ns)
    assert len([1 for op, _ in got if op == "add"]) == 2 and ("wall", [x - 50, y, x + 50, y]) in got
    # Ctrl + wheel: its size
    lua.execute("AGPS_CTRL = true")
    f._scripts.OnMouseWheel(f, 1)
    assert G.EraserYd() == 13
    for _ in range(80):
        f._scripts.OnMouseWheel(f, 1)
    assert G.EraserYd() == G.ERASER_MAX_YD >= 3000  # (big enough to sweep a stroke across zones)
    for _ in range(80):
        f._scripts.OnMouseWheel(f, -1)
    assert G.EraserYd() == G.ERASER_MIN_YD
    lua.execute("AGPS_CTRL = false")
    G.Redraw()
    G.Update()  # (its circle drawn without a failure)
    # the tools off: the eraser too
    G.SetRoadMode(False)
    assert not G.eraserMode


def test_the_eraser_needs_the_road_or_wall_tools(tools):
    lua, ns = tools
    G = ns.GPS
    assert G.SetEraserMode(True) is False and not G.eraserMode


def test_restore_zone_restores_the_zone_under_the_crosshair_after_asking(tools):
    lua, ns = tools
    G = ns.GPS
    Rec = ns.Record
    # (the map follows the player, in Brill: Tirisfal Glades)
    Rec.Save(_track(lua, "add", 0, 1000, [2254, 293, 2264, 293]))
    Rec.Save(_track(lua, "wall", 0, 1001, [2254, 293, 2264, 293]))
    Rec.Save(_track(lua, "add", 0, 1002, [-8800, 600, -8810, 600]))  # (Stormwind)
    G.RestoreZone()
    assert not ns.db.tracks or len(ns.db.tracks) == 3  # (neither tools on: nothing, said in chat)
    G.SetRoadMode(True)
    lua.execute("AGPS_ANSWER = false")
    G.RestoreZone()
    assert len(ns.db.tracks) == 3  # (not answered yes)
    assert "Tirisfal Glades" in lua.eval("AGPS_ASKED[1]")
    lua.execute("AGPS_ANSWER = nil")
    G.RestoreZone()
    assert _tracks(ns) == [("wall", [2254, 293, 2264, 293]), ("add", [-8800, 600, -8810, 600])]
    ns.Record.Undo()
    assert len(ns.db.tracks) == 3


def test_restore_continent_asks_twice(tools):
    lua, ns = tools
    G = ns.GPS
    Rec = ns.Record
    Rec.Save(_track(lua, "wall", 0, 1000, [2254, 293, 2264, 293]))
    Rec.Save(_track(lua, "wall", 0, 1001, [-8800, 600, -8810, 600]))
    Rec.Save(_track(lua, "wall", 1, 1002, [1500, -4400, 1510, -4400]))  # (Kalimdor)
    Rec.Save(_track(lua, "add", 0, 1003, [2254, 293, 2264, 293]))
    G.SetWallMode(True)
    G.RestoreContinent()
    asked = list(lua.eval("AGPS_ASKED").values())
    assert len(asked) == 2 and "Eastern Kingdoms" in asked[0] and "Are you sure" in asked[1]
    assert _tracks(ns) == [("wall", [1500, -4400, 1510, -4400]), ("add", [2254, 293, 2264, 293])]
    Rec.Undo()
    assert len(ns.db.tracks) == 4


def test_shift_click_drawing_always_a_plain_drag_pans(tools):
    # (asked 2026-11-19: the option gone, its behavior always; an old saved "off" changes nothing)
    lua, ns = tools
    G, st = ns.GPS, ns.settings.gps
    f = lua.eval("AzerothGPSFrame")
    G.SetRoadMode(True)
    st.recordHint = False
    st.toolShiftClick = False  # (a saved value from before: ignored)
    tracks = len(ns.db.tracks)
    try:
        lua.execute("AGPS_SHIFT = false")
        # a plain left-drag pans (the map's own drag), no stroke, nothing drawn
        lua.execute("AGPS_CX, AGPS_CY = 300, 300 AGPS_OLDC = GetCursorPosition "
                    "GetCursorPosition = function() return AGPS_CX, AGPS_CY end")
        f._scripts.OnMouseDown(f, "LeftButton")
        assert G.lasso is None
        lua.execute("AGPS_CX, AGPS_CY = 380, 340 AGPS_T = AGPS_T + 0.1")
        f._scripts.OnUpdate(f, 0.1)
        f._scripts.OnMouseUp(f, "LeftButton")
        lua.execute("GetCursorPosition = AGPS_OLDC")
        assert len(ns.db.tracks) == tracks and G.IsFree()  # (dragged: the map's free view)
        # a plain right-drag erases nothing either
        f._scripts.OnMouseDown(f, "RightButton")
        assert G.lasso is None
        f._scripts.OnMouseUp(f, "RightButton")
        # Shift + left-drag draws, Shift + right-drag erases
        lua.execute("AGPS_SHIFT = true")
        f._scripts.OnMouseDown(f, "LeftButton")
        assert G.lasso is not None and not G.lasso.erase
        G.lasso = None
        f._scripts.OnMouseDown(f, "RightButton")
        assert G.lasso is not None and G.lasso.erase
        G.lasso = None
        lua.execute("AGPS_SHIFT = false")
        # and the eraser with Shift too
        G.SetEraserMode(True)
        f._scripts.OnMouseDown(f, "LeftButton")
        assert G.lasso is None
        f._scripts.OnMouseUp(f, "LeftButton")
        lua.execute("AGPS_SHIFT = true")
        f._scripts.OnMouseDown(f, "LeftButton")
        assert G.lasso is not None and G.lasso.eraser
        f._scripts.OnMouseUp(f, "LeftButton")
        assert G.ToggleShiftClick is None  # (no option, no toggle)
    finally:
        st.recordHint = True
        st.toolShiftClick = None
        G.lasso = None
        lua.execute("AGPS_SHIFT = true")


def test_the_restoring_buttons_are_in_the_map_editing_menu(tools):
    lua, ns = tools
    G = ns.GPS
    ids = [str(m.id) for m in G.groupOf["mapEdit"].members.values()]
    for i in ("magicEraser", "restoreZone", "restoreContinent"):
        assert i in ids and ids.index(i) > ids.index("roadUndo")
    assert "shiftClick" not in ids  # (Shift-click drawing always: no button, 2026-11-19)


def test_the_eraser_shows_its_whole_circle_filled(tools):
    # (asked 2026-11-14: "magic eraser circle should cover the entirety of the circle not just drawing a line with a
    # circle cursor") a filled disc under its ring at the pointer, and its stroke as wide as the circle
    lua, ns = tools
    G, st = ns.GPS, ns.settings.gps
    lua.execute("AGPS_OVER_REAL = AGPS_NS.GPS.Canvas().IsMouseOver AGPS_NS.GPS.Canvas().IsMouseOver = function() return true end")
    try:
        G.SetRoadMode(True)
        st.eraserYd = 20
        G.SetEraserMode(True)
        G.Redraw()
        G.Update()
        disc = G.eraserDisc
        s = G.shownView.s
        assert disc is not None and disc._shown and abs(disc._w - 40 * s) < 1 and abs(disc._h - 40 * s) < 1
        G.SetEraserMode(False)
        G.Redraw()
        G.Update()
        assert not disc._shown
    finally:
        lua.execute("AGPS_NS.GPS.Canvas().IsMouseOver = AGPS_OVER_REAL")


def test_road_and_wall_tools_glow_in_the_open_menu_until_one_is_on(tools):
    # (asked 2026-11-14: "make road and wall tools glow when neither is enabled and map editor is expanded")
    lua, ns = tools
    G = ns.GPS
    glow = lambda i: (lambda t: bool(t.glow and t.glow._shown))(  # noqa: E731
        next(t for t in G.QUICK.values() if t.id == i))
    try:
        G.SetMapEditOpen(False)
        assert not glow("roadTools") and not glow("wallTools")
        G.SetMapEditOpen(True)
        assert glow("roadTools") and glow("wallTools")
        G.SetRoadMode(True)
        assert not glow("roadTools") and not glow("wallTools")
        G.SetRoadMode(False)  # (the menu still open, neither on: glowing again)
        assert G.mapEditOpen and glow("roadTools") and glow("wallTools")
        G.SetWallMode(True)
        assert not glow("wallTools")
    finally:
        G.SetMapEditOpen(False)
        assert not glow("roadTools")


def test_find_herbs_and_ore_glows_and_warns_while_a_filter_is_on(tools):
    # (asked 2026-11-16: "if there is an active filter on for "Find Herbs and Ore" make it glow like the map editor
    # buttons and show warning in tooltip filter is on") the button glows, and its group's (Herbs, Ore and Farming)
    # while it's tucked in there; both tooltips say a filter is on; Show All (no filter) puts both out
    lua, ns = tools
    G, Lay = ns.GPS, ns.Layers
    find = next(t for t in G.QUICK.values() if t.id == "nodeFind")
    grp = G.groupOf["gather"]
    glow = lambda t: bool(t.glow and t.glow._shown)  # noqa: E731
    warning = "A filter is on: only the herbs and ore you picked show on the map."

    def tip(button):
        lua.execute("""AGPS_TIP_LINES = {}
          GameTooltip.SetText = function(_, t) AGPS_TIP_LINES = { t } end
          GameTooltip.AddLine = function(_, t) AGPS_TIP_LINES[#AGPS_TIP_LINES + 1] = t end""")
        button.GetScript(button, "OnEnter")(button)
        lines = lua.eval("AGPS_TIP_LINES")
        return [lines[i] for i in range(1, len(lines) + 1)]

    try:
        Lay.SetNodeFilter("Peacebloom", True)
        assert glow(find) and glow(grp)
        assert warning in tip(find.button) and warning in tip(grp.button)
        G.SetMapEditOpen(True)  # (with the map editing tools' glow too)
        assert glow(find) and next(t for t in G.QUICK.values() if t.id == "roadTools").glow._shown
        G.SetMapEditOpen(False)
        assert glow(find)
        Lay.SetNodeFilter("Peacebloom", False)
        assert not glow(find) and not glow(grp)
        assert warning not in tip(find.button) and warning not in tip(grp.button)
    finally:
        Lay.SetNodeFilter("Peacebloom", False)
