"""The road and wall tools' legend and click-to-edit (asked 2026-11-19 for 1.3.10): the hint at the map's top, a wall of
colored text, is now a list on the map's left like the controller's box, one action a row with pixel icons for its input
(Media/Tools/, toolicons.py, drawn at each size and shown pixel for pixel), and the hover tooltip keeps off it. A plain
left click on a road or wall opens Edit Road or Edit Wall with it (the map's own lines read-only, and why); a Shift-drag
still draws, a plain drag pans, and a click on no line is the map's own click as before. On both maps."""

import struct

import numpy as np
import pytest

from azerothgps import toolicons


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
    ns.settings.gps.recordHint = False
    lua.execute("""
      AGPS_SHIFT_REAL, AGPS_CURSOR_REAL = IsShiftKeyDown, GetCursorPosition
      AGPS_SHIFT, AGPS_CX, AGPS_CY = false, 300, 300
      IsShiftKeyDown = function() return AGPS_SHIFT end
      GetCursorPosition = function() return AGPS_CX, AGPS_CY end
      AGPS_TOOLCURSOR_REAL = AGPS_NS.GPS.ToolCursor
    """)
    try:
        yield lua, ns
    finally:
        for w in ("AzerothGPSRoadEdit", "AzerothGPSWallEdit"):
            f = lua.globals()[w]
            if f:
                f.Hide(f)
        G.SetEraserMode(False)
        G.SetRoadMode(False)
        G.SetWallMode(False)
        G.lasso = None
        ns.db.tracks = saved
        ns.Router.Reset()
        ns.settings.gps.recordHint = True
        lua.execute("""IsShiftKeyDown, GetCursorPosition = AGPS_SHIFT_REAL, AGPS_CURSOR_REAL
          AGPS_NS.GPS.ToolCursor = AGPS_TOOLCURSOR_REAL""")


def rows(G):
    header, rs, state = G.ToolLegendRows()
    out = [(tuple(r.icons.values()), str(r.text)) for r in rs.values()]
    return str(header), out, state


def cursor_at(lua, x, y):
    lua.execute(f"AGPS_NS.GPS.ToolCursor = function() return {x}, {y} end")


def click(lua, f, button="LeftButton"):
    f._scripts.OnMouseDown(f, button)
    f._scripts.OnMouseUp(f, button)


# ---------------------------------------------------------------- the legend

def test_the_legend_rows_for_each_tool(tools):
    lua, ns = tools
    G = ns.GPS
    G.SetRoadMode(True)
    header, rs, _ = rows(G)
    assert header == "Road Tools"
    assert rs[:4] == [(("MouseLeft",), "Click a road: edit it"), (("Shift", "MouseLeft"), "Draw a road"),
                      (("Shift", "MouseRight"), "Erase (circle an area to erase all)"),
                      (("MouseLeft",), "Drag: pan the map")]
    assert G.ToolLegendShown() and not G.drawHint._shown  # (no line at the map's top any more)
    G.SetWallMode(True)
    header, rs, _ = rows(G)
    assert header == "Wall Tools"
    assert [t for _, t in rs][:4] == ["Click a wall: edit it", "Draw a wall", "Erase walls (circle an area to erase all)",
                                      "Drag: pan the map"]
    G.SetEraserMode(True)
    header, rs, _ = rows(G)
    assert header == f"Magic Eraser: {int(G.EraserYd())} yd"
    assert rs[1] == (("Ctrl", "MouseWheel"), "Circle size")
    G.SetEraserMode(False)
    G.SetEditWallMode(True)
    header, rs, _ = rows(G)
    assert header == "Edit Wall" and [t for _, t in rs][:2] == ["Click a wall: edit it", "Drag: pan the map"]
    G.SetEditWallMode(False)
    G.SetRoadMode(True)
    G.SetStairMode(True)
    assert rows(G)[0] == "Stairs" and rows(G)[1][0][1] == "Click the stairs' foot"
    G.SetStairMode(False)
    # where floors lie over each other: Shift + wheel picks one, the floor edited under the rows
    real = G.FloorText
    G.FloorText = lambda: "Editing: up top"
    try:
        G.RoadHint()
        _, rs, state = rows(G)
        assert rs[-1] == (("Shift", "MouseWheel"), "Pick a floor") and state == "Editing: up top"
        assert str(G.toolLegend.state._text) == "Editing: up top" and G.toolLegend.state._shown
    finally:
        G.FloorText = real
    # every row placed, its icons and label
    G.RoadHint()
    lg = G.toolLegend
    assert lg.fit == len(lg.shownRows)
    for i in range(1, lg.fit + 1):
        fr = lg.rows[i]
        assert fr.text._shown and str(fr.text._text) == str(lg.shownRows[i].text)
        assert [t.name for t in fr.icons.values() if t._shown] == list(lg.shownRows[i].icons.values())
    G.SetRoadMode(False)
    assert not G.ToolLegendShown()


def test_the_controller_box_gives_way_to_the_legend(tools):
    lua, ns = tools
    G, P = ns.GPS, ns.Pad
    G.SetRoadMode(True)
    P.used = True
    try:
        P.ShowMarks(True)
        assert not (P.box and P.box._shown)  # (the legend has its room: the controller's line at the bottom instead)
        G.SetRoadMode(False)
        P.ShowMarks(True)
    finally:
        P.ShowMarks(False)
        P.used = False


def test_the_icons_are_drawn_to_scale_in_power_of_two_canvases(tools):
    lua, ns = tools
    G = ns.GPS
    assert list(G.TOOL_ICON_PX.values()) == list(toolicons.ICON_PX)
    assert dict(G.TOOL_ICON_WIDE.items()) == toolicons.WIDE
    for name in toolicons.ICONS:
        for n in toolicons.ICON_PX:
            f = toolicons.icon_file(name, n)
            data = f.read_bytes()
            assert data == toolicons.tga_rgba(toolicons.on_canvas(name, n)), f
            w, h = struct.unpack("<HH", data[12:16])
            side = toolicons.canvas_side(name, n)
            assert w == h == side and side & (side - 1) == 0 and side < 2 * toolicons.WIDE.get(name, 1) * n
            art = toolicons.icon(name, n)
            assert art.shape[:2] == (n, toolicons.WIDE.get(name, 1) * n)
            px = np.frombuffer(data[18:], np.uint8).reshape(h, w, 4)[::-1]  # (stored bottom up)
            assert not px[n:, :, 3].any() and not px[:, art.shape[1]:, 3].any()  # (only its top-left corner drawn)
    stray = {p.name for p in toolicons.TOOLS_DIR.glob("*")} - {toolicons.icon_file(a, n).name for a in toolicons.ICONS
                                                               for n in toolicons.ICON_PX}
    assert not stray
    # shown pixel for pixel: the size drawn nearest, only the drawing, at its pixels' size, no filter above LINEAR
    G.SetRoadMode(True)
    ppu = ns.PixelsPerUnit(G.toolLegend.GetEffectiveScale(G.toolLegend))
    shown = 0
    for fr in G.toolLegend.rows.values():
        for t in fr.icons.values():
            if not t._shown:
                continue
            shown += 1
            px = t.agpsArtPx
            assert px in toolicons.ICON_PX and str(t._tex).endswith(f"\\Media\\Tools\\{t.name}_{px}")
            assert (toolicons.TOOLS_DIR / f"{t.name}_{px}.tga").exists()
            wide = toolicons.WIDE.get(t.name, 1)
            side = toolicons.canvas_side(t.name, px)
            assert list(t._coords.values()) == pytest.approx([0, px * wide / side, 0, px / side])
            assert (t._w, t._h) == pytest.approx((px * wide / ppu, px / ppu))
            assert t._filter in (None, "LINEAR", "NEAREST")
    assert shown >= 6


def test_the_hover_tooltip_keeps_off_the_legend(tools):
    lua, ns = tools
    G = ns.GPS
    # beside the legend, whatever the cursor: its left never left of the legend's right
    for mx in (0, 50, 120, 199, 200, 260, 900):
        for ts in (0.64, 1.0, 1.5):
            x, y = G.TipBesideLegend(mx, 400, 200, 600, ts)
            assert x >= G.TOOL_TIP_GAP  # (offset from the legend's right edge: right of it)
            if mx > 260:
                assert x == pytest.approx((mx - 200) / ts + G.TOOL_TIP_OFF)  # (far from it: at the cursor as before)
    # the tools' hover with the legend shown: anchored by the legend's right, not the cursor
    G.SetRoadMode(True)
    tip = lua.eval("GameTooltip")
    assert G.KeepTipOffLegend()
    pt = list(tip._pt.values())
    same = lua.eval("function(a, b) return rawequal(a, b) end")
    assert pt[0] == "BOTTOMLEFT" and same(pt[1], G.toolLegend) and pt[2] == "TOPRIGHT" and pt[3] >= G.TOOL_TIP_GAP
    G.SetRoadMode(False)
    assert not G.KeepTipOffLegend()


def test_the_legend_on_the_world_map_too(game):
    from test_world_map_host import SETUP
    lua, ns = game
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
        assert G.ToolLegendShown() and G.toolLegend.fit >= 4
        G.SetWallMode(True)
        assert str(G.ToolLegendRows()[0]) == "Wall Tools" and G.ToolLegendShown()
        G.SetWallMode(False)
        assert not G.ToolLegendShown()
    finally:
        G.SetRoadMode(False)
        G.SetWallMode(False)
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()


# ---------------------------------------------------------------- a click on a line

def test_a_click_on_a_road_opens_edit_road_with_it_and_a_shift_drag_still_draws(tools):
    lua, ns = tools
    G = ns.GPS
    f = lua.eval("AzerothGPSFrame")
    G.SetRoadMode(True)
    G.FinishRoad(lua.table(pts=lua.table(2600.0, 700.0, 2615.0, 700.0, 2630.0, 700.0, 2645.0, 700.0), cont=0),
                 False, False)
    mine = ns.db.tracks[1]
    win = lua.globals().AzerothGPSRoadEdit
    assert not (win and win._shown)
    cursor_at(lua, 2615.0, 700.5)
    click(lua, f)  # (a plain click, no drag, no Shift)
    win = lua.globals().AzerothGPSRoadEdit
    assert win._shown and G.roadEdit.sel.t.time == mine.time and not win.readOnly
    assert win.save._enabled is not False and win.pickFoot._shown
    # its kind and height changed and saved as Edit Road saves (an edit replacing it)
    [b for b in win.kinds.values() if b.kind == "bridge"][0]._scripts.OnClick(None)
    win.height.box.SetText(win.height.box, "20")
    win.save._scripts.OnClick(win.save)
    ed = ns.db.tracks[2]
    assert ed.kind == "bridge" and ed.replaces == mine.time and not win._shown
    # Pick Foot from a window a click opened: the next plain click picks it on the road
    click(lua, f)
    win.pickFoot._scripts.OnClick(win.pickFoot)
    cursor_at(lua, 2629.0, 700.0)
    click(lua, f)
    assert G.roadEdit.foot == 3 and win._shown
    win.Hide(win)
    # a Shift-drag still draws a road
    n = len(ns.db.tracks)
    lua.execute("AGPS_SHIFT = true AGPS_CX, AGPS_CY = 200, 300")
    f._scripts.OnMouseDown(f, "LeftButton")
    for step in range(1, 6):
        lua.execute(f"AGPS_CX = {200 + step * 40} AGPS_T = AGPS_T + 0.05")
        f._scripts.OnUpdate(f, 0.05)
    f._scripts.OnMouseUp(f, "LeftButton")
    lua.execute("AGPS_SHIFT = false")
    assert len(ns.db.tracks) == n + 1 and ns.db.tracks[n + 1].op == "add"


def test_a_click_on_the_maps_own_road_shows_it_read_only(tools):
    lua, ns = tools
    G, R = ns.GPS, ns.Router
    f = lua.eval("AzerothGPSFrame")
    G.SetRoadMode(True)
    c = R.NearestEdges(0, 2254.0, 293.0)[1]
    g = R.DebugGraph(0)
    mx = lua.eval("function(e) local x, y = AGPS_NS.Router.EdgeMiddle(e) return x, y end")
    x, y = mx(g.e[c.edge])
    assert ns.Record.TrackAt(0, x, y) is None  # (no track of its own there)
    cursor_at(lua, x, y)
    click(lua, f)
    win = lua.globals().AzerothGPSRoadEdit
    assert win._shown and win.readOnly and G.roadEdit.sel.readOnly
    assert win.save._enabled is False and not win.pickFoot._shown and not win.setHeights._shown
    assert "can't be changed here" in str(win.note._text)
    assert G.SaveRoadEdit() is None
    # an editable road next: the window editable again
    G.FinishRoad(lua.table(pts=lua.table(2600.0, 700.0, 2615.0, 700.0, 2630.0, 700.0), cont=0), False, False)
    cursor_at(lua, 2615.0, 700.0)
    click(lua, f)
    assert not win.readOnly and win.save._enabled is not False and win.pickFoot._shown


def test_a_click_on_a_wall_opens_edit_wall_and_the_maps_own_read_only(tools):
    lua, ns = tools
    G, P = ns.GPS, ns.Passability
    f = lua.eval("AzerothGPSFrame")
    G.SetWallMode(True)
    G.FinishRoad(lua.table(pts=lua.table(2600.0, 760.0, 2615.0, 760.0, 2630.0, 760.0), cont=0), False, True)
    mine = ns.db.tracks[1]
    assert mine.op == "wall"
    cursor_at(lua, 2614.0, 760.5)
    click(lua, f)
    win = lua.globals().AzerothGPSWallEdit
    assert win._shown and G.wallEdit.sel.t.time == mine.time and not win.readOnly
    win.left.SetText(win.left, "30")
    win.right.SetText(win.right, "10")
    win.save._scripts.OnClick(win.save)
    assert ns.db.tracks[2].kind == "cliff" and ns.db.tracks[2].replaces == mine.time
    # the map's own wall: its details, read-only
    ns.Record.Apply()
    P.RefreshWalls()
    own = None
    for w in P.WallLines(0).values():
        if len(w) >= 4 and abs(w[2] - 760) > 50:
            own = w
            break
    assert own is not None
    x, y = (own[1] + own[3]) / 2, (own[2] + own[4]) / 2
    assert ns.Record.WallAt(0, x, y, 1) is None
    cursor_at(lua, x, y)
    click(lua, f)
    assert win._shown and win.readOnly and win.save._enabled is False and not win.pickA._shown
    assert "can't be changed here" in str(win.note._text)
    assert G.SaveWallEdit() is None


def test_a_click_on_no_line_is_the_maps_own_click(tools):
    lua, ns = tools
    G = ns.GPS
    f = lua.eval("AzerothGPSFrame")
    G.SetRoadMode(True)
    # a spot with no road or wall in reach
    spot = None
    for dx in range(0, 3000, 150):
        for dy in range(0, 3000, 150):
            x, y = 1000.0 + dx, -1500.0 + dy
            if G.ToolClick(0, x, y, 0.01) is False and G.RoadHoverInfo(0, x, y, 30) is None:
                spot = (x, y)
                break
        if spot:
            break
    assert spot
    cursor_at(lua, *spot)
    lua.execute("""AGPS_HOOKED = 0 AGPS_HOOK_REAL = AGPS_NS.GPS.MapClickHook
      AGPS_NS.GPS.MapClickHook = function(...) AGPS_HOOKED = AGPS_HOOKED + 1 return AGPS_HOOK_REAL(...) end""")
    try:
        click(lua, f)
        assert lua.eval("AGPS_HOOKED") == 1  # (the map's own click, as with the tools off)
        win = lua.globals().AzerothGPSRoadEdit
        assert not (win and win._shown)
        assert len(ns.db.tracks) == 0
    finally:
        lua.execute("AGPS_NS.GPS.MapClickHook = AGPS_HOOK_REAL")
