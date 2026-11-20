"""Stairs drawn with their icon (asked 2026-11-19 for 1.3.10: "Shouldn't the Stairs icon tool place the stairs icon from
start to finish? Also use another color for the stairs path."): with the road tools on, a stairs road gets the stairs
glyph (Media/Tools/Stairs<d>, toolicons.py) at its foot, at its top and evenly between, no closer than
G.STAIR_GLYPH_GAP on the screen whatever the zoom, each pointing the way the stairs climb (one file per 45 degrees, drawn
turned: never turned or scaled in the game). Stairs and ramps have colors of their own. On both maps."""

import math

import pytest

from azerothgps import toolicons

FOOT = (2600.0, 700.0, 20.0)
TOP = (2640.0, 700.0, 30.0)


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
def stairs(game):
    """Stairs drawn with the Stairs tool from FOOT up to TOP, the road tools on."""
    lua, ns = game
    G, R = ns.GPS, ns.Router
    saved = ns.db.tracks
    ns.db.tracks = lua.table()
    R.Reset()
    G.roadMode = True
    try:
        assert G.SaveStairs(0, FOOT[0], FOOT[1], FOOT[2], TOP[0], TOP[1], TOP[2])
        yield lua, ns
    finally:
        G.roadMode = None
        ns.Record.pending = None
        ns.db.tracks = saved
        R.Reset()
        G.stairGlyphN = 0


def same(lua, a, b):
    return lua.eval("rawequal")(a, b)


def glyphs(G):
    return [tuple(G.stairGlyphs[i][k] for k in (1, 2, 3)) for i in range(1, G.stairGlyphN + 1)]


def layout(G, px, py, zoom, half=200, rot=0.0):
    G.stairGlyphN = 0
    segs = G.LayoutRoads(px, py, 0, rot, zoom, half)
    return segs, glyphs(G)


def screen(lua, px, py, x, y, s, rot=0.0):
    f = lua.eval("""function(px, py, x, y, s, rot)
      local dx, dy = AGPS_NS.Geo.ScreenOffset(px, py, x, y)
      return AGPS_NS.Geo.Rotate(dx * s, dy * s, rot)
    end""")
    return f(px, py, x, y, s, rot)


def test_glyphs_along_a_line_from_foot_to_top_ends_included(game):
    lua, ns = game
    G = ns.GPS
    gap = G.STAIR_GLYPH_GAP
    pts = lua.table(0.0, 0.0, 70.0, 0.0, 70.0, 100.0)  # (right, then up: 170 long)
    G.stairGlyphN = 0
    G.StairGlyphsAlong(pts, 6, 1000)
    got = glyphs(G)
    assert len(got) == math.floor(170 / gap) + 1
    assert got[0][:2] == (0, 0) and got[-1][:2] == pytest.approx((70, 100))
    # evenly along it, never closer than the gap
    along = [x + y if y else x for x, y, _ in got]  # (the way along the bend)
    steps = [b - a for a, b in zip(along, along[1:])]
    assert min(steps) >= gap - 1e-6 and max(steps) - min(steps) < 1e-6
    # pointing the way it climbs: right (2) on the first leg, then up (0)
    assert [d for x, y, d in got if y == 0 and x < 70] == [2] * len([1 for x, y, _ in got if y == 0 and x < 70])
    assert got[-1][2] == 0
    # (shorter on the screen than the glyph: one, in its middle)
    G.stairGlyphN = 0
    G.StairGlyphsAlong(lua.table(0.0, 0.0, 0.0, 8.0), 4, 1000)
    assert glyphs(G) == [(0, 4, 0)]
    # (only those in view)
    G.stairGlyphN = 0
    G.StairGlyphsAlong(lua.table(0.0, 0.0, 400.0, 0.0), 4, 100)
    assert all(abs(x) <= 100 for x, _, _ in glyphs(G)) and 0 < G.stairGlyphN < 400 / gap
    G.stairGlyphN = 0


def test_eight_ways_clockwise_from_up(game):
    _, ns = game
    G = ns.GPS
    ways = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
    assert [G.StairGlyphDir(x, y) for x, y in ways] == list(range(8))
    assert G.StairGlyphDir(0.2, 1) == 0 and G.StairGlyphDir(1, 0.3) == 2  # (the nearest)


def test_a_stairs_road_gets_glyphs_foot_to_top_and_more_zoomed_in(stairs):
    lua, ns = stairs
    G = ns.GPS
    px, py = 2620.0, 700.0
    counts = {}
    for zoom in (200, 60, 30):
        segs, got = layout(G, px, py, zoom)
        s = 200 / zoom
        fx, fy = screen(lua, px, py, FOOT[0], FOOT[1], s)
        tx, ty = screen(lua, px, py, TOP[0], TOP[1], s)
        length = math.hypot(tx - fx, ty - fy)
        assert len(got) == max(2, math.floor(length / G.STAIR_GLYPH_GAP) + 1), (zoom, got)
        # the foot first, the top last, all pointing from the foot to the top
        assert got[0][:2] == pytest.approx((fx, fy), abs=0.01) and got[-1][:2] == pytest.approx((tx, ty), abs=0.01)
        assert {d for _, _, d in got} == {G.StairGlyphDir(tx - fx, ty - fy)}
        counts[zoom] = len(got)
        # the line itself in the stairs' color
        assert any(same(lua, sg[5], G.KIND_COLORS.stairs) for sg in segs.values())
    assert counts[200] < counts[60] < counts[30]
    # turned with the map: still from the foot up
    rot = math.pi / 2
    _, got = layout(G, px, py, 60, rot=rot)
    fx, fy = screen(lua, px, py, FOOT[0], FOOT[1], 200 / 60, rot)
    tx, ty = screen(lua, px, py, TOP[0], TOP[1], 200 / 60, rot)
    assert got[0][:2] == pytest.approx((fx, fy), abs=0.01)
    assert {d for _, _, d in got} == {G.StairGlyphDir(tx - fx, ty - fy)}
    # the tools off: none (the kinds' colors and icons are the tools')
    G.roadMode = None
    _, got = layout(G, px, py, 60)
    assert got == []


def test_stairs_drawn_top_first_still_point_up(game):
    lua, ns = game
    G, R = ns.GPS, ns.Router
    saved = ns.db.tracks
    ns.db.tracks = lua.table()
    R.Reset()
    G.roadMode = True
    try:
        # clicked top first: the foot is the lower end by the heights
        assert G.SaveStairs(0, TOP[0], TOP[1], TOP[2], FOOT[0], FOOT[1], FOOT[2])
        _, got = layout(G, 2620.0, 700.0, 60)
        fx, fy = screen(lua, 2620.0, 700.0, FOOT[0], FOOT[1], 200 / 60)
        assert got and got[0][:2] == pytest.approx((fx, fy), abs=0.01) and {d for _, _, d in got} == {0}
    finally:
        G.roadMode = None
        ns.db.tracks = saved
        R.Reset()
        G.stairGlyphN = 0


def test_stairs_not_built_in_yet_drawn_with_their_kind_and_glyphs(stairs):
    lua, ns = stairs
    G = ns.GPS
    # (a floor road with a stairs stretch on part of it, as Edit Road saves it: its pieces, the stretch its own)
    ns.db.tracks[2] = lua.eval("""{ op = "add", drawn = true, edit = true, continent = 0, time = 99, kind = "floor",
      pts = { 2600, 760, 2610, 760, 2620, 760, 2630, 760 }, zs = { 20, 20, 30, 30 }, stairs = { 2, 3 } }""")
    idx = G.DrawnTrackIndex(0)
    kinds = [(b[5].kind, len(b[5]) // 2 - 2) for b in idx.values()]
    # (the Stairs tool's, and the edit's three pieces: floor, its stairs stretch, floor)
    assert sorted(kinds) == [("floor", 2), ("floor", 2), ("stairs", 2), ("stairs", 2)]
    layout(G, 2620.0, 730.0, 60)  # (the network built)
    ns.Record.pending = True  # (the tools on with edits: drawn over the roads as they were)
    segs, got = layout(G, 2620.0, 730.0, 60)
    s = 200 / 60
    fx, fy = screen(lua, 2620.0, 730.0, 2610, 760, s)
    tx, ty = screen(lua, 2620.0, 730.0, 2620, 760, s)
    mine = [g for g in got if abs(g[1] - fy) < 0.01 or abs(g[1] - ty) < 0.01 or abs(g[0] - fx) < 0.01]
    assert any(g[:2] == pytest.approx((fx, fy), abs=0.01) for g in got)
    assert any(g[:2] == pytest.approx((tx, ty), abs=0.01) for g in got)
    assert mine and any(same(lua, sg[5], G.KIND_COLORS.stairs) for sg in segs.values())
    assert any(same(lua, sg[5], G.KIND_COLORS.floor) for sg in segs.values())


def color_distance(a, b):
    return math.dist(tuple(a), tuple(b))


def test_stairs_and_ramps_have_colors_of_their_own(game):
    lua, ns = game
    G = ns.GPS
    kinds = {k: tuple(v.values()) for k, v in G.KIND_COLORS.items()}
    others = [v for k, v in kinds.items() if k not in ("stairs", "ramp")]
    # (the route's, the roads' and walls' by source, the player's own, the tools' and the map's other marks)
    roads = lua.eval("""function()
      local out = {}
      for _, name in ipairs({ "STAIRS_COLOR", "EDIT_ROAD_COLOR", "JUNCTION_COLOR", "ROAD_END_COLOR", "ERASER_COLOR",
          "CLIFF_LEFT_COLOR", "CLIFF_RIGHT_COLOR", "CLIFF_SHADE_COLOR", "DETOUR_COLOR", "PARTY_COLOR",
          "MINIMAP_ROUTE_COLOR", "NPC_DOT_COLOR", "EDIT_GLOW_COLOR" }) do
        local c = AGPS_NS.GPS[name]
        if c then out[#out + 1] = c end
      end
      return out
    end""")()
    named = [tuple(c.values()) for c in roads.values()]
    assert len(named) >= 10
    fixed = [(1, 0.35, 0.1), (0.1, 0.9, 1), (0.3, 1, 0.3), (0.05, 0.28, 0.85), (0.25, 0.85, 1), (0.65, 0.65, 0.7),
             (0.45, 0.6, 1), (0.55, 0.02, 0.02), (0.85, 0.78, 0.6), (1, 0.85, 0.1),  # (GPSFrame's ROAD_COLORS)
             (1, 0.82, 0), (0.3, 1, 0.3), (1, 0.2, 0.2), (0.6, 0.6, 0.6)]  # (lasso, draw, erase, unwall)
    for k in ("stairs", "ramp"):
        c = kinds[k]
        for o in others + named + fixed + [kinds["ramp" if k == "stairs" else "stairs"]]:
            assert color_distance(c, o) >= 0.35, (k, c, o)
    # (Edit Road's and Set Heights' kind buttons show the same colors)
    G.roadMode = True
    try:
        lua.globals().AGPS_NS.db.tracks = lua.table()
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 900.0, 2615.0, 900.0, 2630.0, 900.0), cont=0), False, False)
        G.SetEditRoadMode(True)
        assert G.EditRoadClick(0, 2615.0, 901.0)
        win = lua.globals().AzerothGPSRoadEdit
        sw = {b.kind: b for b in win.kinds.values()}
        assert same(lua, sw["stairs"].swatchColor, G.KIND_COLORS.stairs)
        assert same(lua, sw["bridge"].swatchColor, G.KIND_COLORS.bridge) and sw["ground"].swatch is None
        assert sw["stairs"].swatch._tex == "color:%.2f,%.2f,%.2f" % kinds["stairs"]
    finally:
        w = lua.globals().AzerothGPSRoadEdit
        if w:
            w.Hide(w)
        G.SetEditRoadMode(False)
        G.roadMode = None
        ns.Router.Reset()


def shown_glyphs(G):
    return [t for t in G.stairGlyphTex.values() if t._shown]


def test_the_glyphs_drawn_pixel_for_pixel_and_pooled(stairs):
    lua, ns = stairs
    G = ns.GPS
    st = ns.settings.gps
    zoom = st.zoom
    st.zoom = 60.0
    G.Follow()
    lua.execute("AGPS_POS[1], AGPS_POS[2] = 2620.0, 700.0")
    G.Redraw()
    G.Update()
    shown = shown_glyphs(G)
    assert len(shown) >= 2 and len(shown) == G.stairGlyphUsed
    ppu = ns.PixelsPerUnit(shown[0].GetEffectiveScale(shown[0]))
    for t in shown:
        px = t.agpsArtPx
        assert px in toolicons.ICON_PX
        d = int(str(t._tex).rsplit("Stairs", 1)[1].split("_")[0])
        assert str(t._tex).endswith(f"\\Media\\Tools\\Stairs{d}_{px}")
        assert (toolicons.TOOLS_DIR / f"Stairs{d}_{px}.tga").exists()
        side = toolicons.canvas_side(f"Stairs{d}", px)
        assert list(t._coords.values()) == pytest.approx([0, px / side, 0, px / side])
        assert (t._w, t._h) == pytest.approx((px / ppu, px / ppu))
        assert t._filter in (None, "LINEAR", "NEAREST")
    made = len(G.stairGlyphTex)
    G.Redraw()
    G.Update()
    assert len(G.stairGlyphTex) == made  # (the same textures again)
    # the tools off: hidden, none made
    G.roadMode = None
    G.Redraw()
    G.Update()
    assert not shown_glyphs(G) and len(G.stairGlyphTex) == made
    st.zoom = zoom
    lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")


def test_the_glyphs_on_the_world_map_too(stairs):
    from test_world_map_host import SETUP
    lua, ns = stairs
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    was = {k: st[k] for k in ("useWorldMap", "shown", "minimized", "zoom")}
    try:
        st.shown, st.minimized, st.useWorldMap, st.zoom = True, None, True, 60.0
        G.ApplySettings()
        lua.execute("WorldMapFrame:Show()")
        G.WorldMapChanged()
        assert G.WorldMapHosted()
        G.Follow()
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2620.0, 700.0")
        G.roadMode = True
        G.Redraw()
        G.Update()
        assert len(shown_glyphs(G)) >= 2
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
