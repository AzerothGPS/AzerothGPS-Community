"""Delete in Edit Road and Edit Wall (asked 2026-11-19 for 1.3.10): a red Delete Road / Delete Wall button at the window's
bottom left, the map's own lines (read-only) too, that asks first ("Delete this road section?" Delete / Cancel) and then
takes out exactly the stretch highlighted. The player's own road or wall comes off the drawn list (a wall's section:
the rest kept as its own walls); the map's own is erased the way Shift + right-drag erases ("remove" along the road,
its ends kept off the roads it meets; "unwall" at the wall's point furthest from the others), saved, shared and read
back by the import like any erase. The window closes and routes take it at once. On both maps."""

import pytest

from azerothgps.roads.tracks import parse_shared


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()
    return lua, ns


@pytest.fixture()
def tools(game):
    lua, ns = game
    G = ns.GPS
    saved = ns.db.tracks
    ns.db.tracks = lua.table()
    ns.Router.Reset()
    ns.Passability.RefreshWalls()
    ns.settings.gps.recordHint = False
    lua.execute("""
      AGPS_SHIFT_REAL, AGPS_CURSOR_REAL = IsShiftKeyDown, GetCursorPosition
      IsShiftKeyDown = function() return false end
      GetCursorPosition = function() return 300, 300 end
      AGPS_TOOLCURSOR_REAL = AGPS_NS.GPS.ToolCursor
    """)
    try:
        yield lua, ns
    finally:
        for w in ("AzerothGPSRoadEdit", "AzerothGPSWallEdit"):
            f = lua.globals()[w]
            if f:
                f.Hide(f)
        if G.askBox:
            G.askBox.Hide(G.askBox)
        G.SetRoadMode(False)
        G.SetWallMode(False)
        ns.db.tracks = saved
        ns.Router.Reset()
        ns.Passability.RefreshWalls()
        ns.settings.gps.recordHint = True
        lua.execute("""IsShiftKeyDown, GetCursorPosition = AGPS_SHIFT_REAL, AGPS_CURSOR_REAL
          AGPS_NS.GPS.ToolCursor = AGPS_TOOLCURSOR_REAL""")


def cursor_at(lua, x, y):
    lua.execute(f"AGPS_NS.GPS.ToolCursor = function() return {x}, {y} end")


def click_map(lua, x, y):
    cursor_at(lua, x, y)
    f = lua.eval("AzerothGPSFrame")
    f._scripts.OnMouseDown(f, "LeftButton")
    f._scripts.OnMouseUp(f, "LeftButton")


def press(b):
    b._scripts.OnClick(b)


def ops(ns):
    return [t.op for t in ns.db.tracks.values()]


def ask_delete(lua, ns, win, text):
    """Delete pressed: the question shown, its buttons Delete and Cancel. The question's box."""
    assert win.delete._shown is not False and win.delete._enabled is not False
    assert "|cffff6060" in str(win.delete._text)  # (red, as a warning)
    press(win.delete)
    box = ns.GPS.askBox
    assert box and box._shown and str(box.text._text) == text
    assert str(box.yes._text) == "Delete" and str(box.no._text) == "Cancel"
    # (over the window, as the options' questions are: never under it)
    assert box.GetFrameStrata(box) == ns.POPUP_OVER_STRATA
    return box


# a road of the map's own: one between two junctions, long, nothing else near its middle
FIND_ROAD = """function(cont)
  local R = AGPS_NS.Router
  R.NearestEdges(cont, 2254, 293)
  local g = R.DebugGraph(cont)
  local deg = {}
  for _, e in ipairs(g.e) do deg[e[1]] = (deg[e[1]] or 0) + 1 deg[e[2]] = (deg[e[2]] or 0) + 1 end
  for ei, e in ipairs(g.e) do
    if e[3] > 80 and e[3] < 400 and e[1] ~= e[2] and deg[e[1]] >= 3 and deg[e[2]] >= 3 and not (g.kind and g.kind[ei]) then
      local x, y = R.EdgeMiddle(e)
      local ok = AGPS_NS.Record.TrackAt(cont, x, y) == nil
      for _, c in ipairs(R.NearestEdges(cont, x, y)) do
        if c.edge ~= ei and c.dist < 30 then ok = false end
      end
      if ok then
        -- (the roads that meet it: their points)
        local nb = {}
        for ej, o in ipairs(g.e) do
          if ej ~= ei and (o[1] == e[1] or o[2] == e[1] or o[1] == e[2] or o[2] == e[2]) then
            for k = 5, #o - 1, 2 do nb[#nb + 1] = o[k] nb[#nb + 1] = o[k + 1] end
          end
        end
        return ei, x, y, nb
      end
    end
  end
end"""


def nearest(ns, cont, x, y):
    c = ns.Router.NearestEdges(cont, x, y)[1]
    return c.dist if c else 1e9


def test_delete_takes_out_exactly_the_maps_own_road_section(tools):
    lua, ns = tools
    G, R = ns.GPS, ns.Router
    G.SetRoadMode(True)
    found = lua.eval(FIND_ROAD)(0)
    ei, x, y, nb = found
    nb = list(nb.values())
    assert len(nb) >= 4
    click_map(lua, x, y)
    win = lua.globals().AzerothGPSRoadEdit
    assert win._shown and win.readOnly
    note = str(win.note._text)
    assert "erase it with Delete, then draw your own" in note and "Shift + right-drag" not in note
    # Cancel on the question: nothing happens
    box = ask_delete(lua, ns, win, "Delete this road section?")
    press(box.no)
    assert len(ns.db.tracks) == 0 and win._shown and not box._shown
    # Delete: an erase saved as Shift + right-drag saves one, the window closed
    box = ask_delete(lua, ns, win, "Delete this road section?")
    press(box.yes)
    assert ops(ns) == ["remove"] and not win._shown and G.roadEdit is None
    er = ns.db.tracks[1]
    assert er.drawn and er.continent == 0 and er.area is None
    # routes: the section gone, the roads it met whole (none of their points cut)
    assert nearest(ns, 0, x, y) > 20
    for k in range(0, len(nb), 2):
        assert nearest(ns, 0, nb[k], nb[k + 1]) < 1, (nb[k], nb[k + 1])
    # shared like any erase, and read back by the import
    lines = [str(v) for v in ns.Feedback.Lines().roads.values()]
    mine = [ln for ln in lines if ln.startswith(f"R remove 0 {er.time} ")]
    assert len(mine) == 1
    tr = parse_shared(mine[0])
    assert len(tr) == 1 and tr[0]["op"] == "remove" and not tr[0]["area"]
    # kept over a /reload: packed for the saved file and back, the section still gone
    pts = list(er.pts.values())
    ns.PackSaved(ns.db)
    ns.UnpackSaved(ns.db)
    assert ops(ns) == ["remove"] and list(ns.db.tracks[1].pts.values()) == pts
    R.Reset()
    assert nearest(ns, 0, x, y) > 20
    # and Undo puts it back
    ns.Record.Undo()
    assert len(ns.db.tracks) == 0 and nearest(ns, 0, x, y) < 1


def test_delete_takes_a_road_of_your_own_off_the_list(tools):
    lua, ns = tools
    G = ns.GPS
    G.SetRoadMode(True)
    G.FinishRoad(lua.table(pts=lua.table(2600.0, 700.0, 2615.0, 700.0, 2630.0, 700.0, 2645.0, 700.0), cont=0),
                 False, False)
    assert ops(ns) == ["add"]
    click_map(lua, 2615.0, 700.5)
    win = lua.globals().AzerothGPSRoadEdit
    assert win._shown and not win.readOnly
    box = ask_delete(lua, ns, win, "Delete this road section?")
    press(box.no)
    assert ops(ns) == ["add"] and win._shown
    box = ask_delete(lua, ns, win, "Delete this road section?")
    press(box.yes)
    assert len(ns.db.tracks) == 0 and not win._shown
    assert ns.Record.TrackAt(0, 2615.0, 700.0) is None
    # an edit of one (it replaces the road it was): erased, so the road it replaced doesn't come back
    G.FinishRoad(lua.table(pts=lua.table(2600.0, 700.0, 2615.0, 700.0, 2630.0, 700.0, 2645.0, 700.0), cont=0),
                 False, False)
    click_map(lua, 2615.0, 700.5)
    [b for b in win.kinds.values() if b.kind == "bridge"][0]._scripts.OnClick(None)
    win.height.box.SetText(win.height.box, "20")
    press(win.save)
    assert ops(ns) == ["add", "add"]
    click_map(lua, 2615.0, 700.5)
    press(ask_delete(lua, ns, win, "Delete this road section?").yes)
    assert ops(ns) == ["add", "add", "remove"]
    assert ns.Record.TrackAt(0, 2615.0, 700.0) is not None  # (still listed for editing: the erase is over it)
    assert nearest(ns, 0, 2622.0, 700.0) > 5


def test_delete_a_wall_of_your_own_whole_or_a_section(tools):
    lua, ns = tools
    G, P = ns.GPS, ns.Passability
    G.SetWallMode(True)
    G.FinishRoad(lua.table(pts=lua.table(2600.0, 760.0, 2615.0, 760.0, 2630.0, 760.0, 2645.0, 760.0, 2660.0, 760.0),
                           cont=0), False, True)
    assert ops(ns) == ["wall"]
    click_map(lua, 2614.0, 760.5)
    win = lua.globals().AzerothGPSWallEdit
    assert win._shown and not win.readOnly
    box = ask_delete(lua, ns, win, "Delete this wall section?")
    press(box.no)
    assert ops(ns) == ["wall"] and win._shown
    press(ask_delete(lua, ns, win, "Delete this wall section?").yes)
    assert len(ns.db.tracks) == 0 and not win._shown
    # a section picked (Pick Start, Pick End): only it goes, the rest kept as walls of their own
    G.FinishRoad(lua.table(pts=lua.table(2600.0, 760.0, 2615.0, 760.0, 2630.0, 760.0, 2645.0, 760.0, 2660.0, 760.0),
                           cont=0), False, True)
    click_map(lua, 2614.0, 760.5)
    G.wallEdit.a, G.wallEdit.b = 2, 4
    press(ask_delete(lua, ns, win, "Delete this wall section?").yes)
    walls = [[t.pts[k] for k in range(1, len(t.pts) + 1)] for t in ns.db.tracks.values()]
    assert ops(ns) == ["wall", "wall"]
    assert walls == [[2600.0, 760.0, 2615.0, 760.0], [2645.0, 760.0, 2660.0, 760.0]]
    assert P.WallHit(0, 2630.0, 750.0, 2630.0, 770.0) is None  # (the gap: through)
    assert P.WallHit(0, 2607.0, 750.0, 2607.0, 770.0) is not None
    assert P.WallHit(0, 2652.0, 750.0, 2652.0, 770.0) is not None


FIND_WALL = """function(cont)
  local P = AGPS_NS.Passability
  local ws = P.WallLines(cont)
  for wi, w in ipairs(ws) do
    if #w >= 6 then
      local far = true
      for wj, o in ipairs(ws) do
        if wj ~= wi then
          for k = 1, #o - 1, 2 do
            for m = 1, #w - 1, 2 do
              if (o[k] - w[m]) ^ 2 + (o[k + 1] - w[m + 1]) ^ 2 < 60 * 60 then far = false end
            end
          end
        end
        if not far then break end
      end
      if far and AGPS_NS.Record.WallAt(cont, (w[1] + w[3]) / 2, (w[2] + w[4]) / 2, 1) == nil then
        return wi, (w[1] + w[3]) / 2, (w[2] + w[4]) / 2, #ws, w[1], w[2]
      end
    end
  end
end"""


def test_delete_erases_the_maps_own_wall_and_no_other(tools):
    lua, ns = tools
    G, P = ns.GPS, ns.Passability
    G.SetWallMode(True)
    wi, x, y, n, x1, y1 = lua.eval(FIND_WALL)(0)
    before = [(w[1], w[2]) for w in P.WallLines(0).values()]
    click_map(lua, x, y)
    win = lua.globals().AzerothGPSWallEdit
    assert win._shown and win.readOnly
    assert "erase it with Delete, then draw your own" in str(win.note._text)
    box = ask_delete(lua, ns, win, "Delete this wall section?")
    press(box.no)
    assert len(ns.db.tracks) == 0
    press(ask_delete(lua, ns, win, "Delete this wall section?").yes)
    assert ops(ns) == ["unwall"] and not win._shown
    er = ns.db.tracks[1]
    assert len(er.pts) == 4 and er.area is None
    after = [(w[1], w[2]) for w in P.WallLines(0).values()]
    assert len(after) == n - 1 and (x1, y1) not in after
    assert sorted(after) == sorted(b for b in before if b != (x1, y1))
    # shared like any wall erase, kept over a /reload
    lines = [str(v) for v in ns.Feedback.Lines().walls.values()]
    mine = [ln for ln in lines if ln.startswith(f"R unwall 0 {er.time} ")]
    assert len(mine) == 1 and parse_shared(mine[0])[0]["op"] == "unwall"
    ns.PackSaved(ns.db)
    ns.UnpackSaved(ns.db)
    P.RefreshWalls()
    assert len(P.WallLines(0)) == n - 1


def test_delete_on_the_world_map_too(tools):
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
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 700.0, 2615.0, 700.0, 2630.0, 700.0), cont=0), False, False)
        assert G.ToolClick(0, 2615.0, 700.0, 2)
        win = lua.globals().AzerothGPSRoadEdit
        assert win._shown
        box = ask_delete(lua, ns, win, "Delete this road section?")
        press(box.yes)
        assert len(ns.db.tracks) == 0 and not win._shown
    finally:
        G.SetRoadMode(False)
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
