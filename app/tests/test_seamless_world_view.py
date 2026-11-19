"""The seamless map's wheel at the cursor and its world view (1.3.9, asked by Kooki3z 2026-11-18: "on the seamless map,
support zoom where the mouse is and zooming out eventually shows both continents, panning at max zoom out wouldn't be
necessary"): the spot under the mouse stays under it as the wheel turns (G.WheelAt), the controller's, keys' and
buttons' zoom stays about the middle (G.WheelZoom); the furthest zoom fits Azeroth's whole map in the window, centered
on it, with nothing to pan (G.WorldZoom, G.ClampToWorld); the route across both continents, the other continent's
icons and a stop clicked there; the GPS window and the game's world map alike; the redraw's cost out there."""

import time

import pytest

from test_atlas import _seamless
from test_world_map_host import SETUP as WM_SETUP

ORGRIMMAR = (1, 1676.0, -4315.0)
RAZOR_HILL = (1, 304.0, -4724.0)  # (out of Orgrimmar: a capital keeps the wheel to its own map)
BRILL = (0, 2250.0, 250.0)
STORMWIND = (0, -8840.6, 489.7)


def _frame(lua):
    return lua.eval("AzerothGPSFrame")


def _cursor(lua, dx, dy):
    """The mouse `dx`, `dy` UI units right of and up from the map's middle (its canvas's center at scale 1)."""
    lua.execute(f"""
      local c = AGPS_NS.GPS.Canvas and AGPS_NS.GPS.Canvas() or nil
      local cx, cy = 300, 300
      if c and c.GetCenter then cx, cy = c:GetCenter() end
      GetCursorPosition = function() return cx + ({dx}), cy + ({dy}) end""")


def _wheel(lua, delta):
    f = _frame(lua)
    f._scripts.OnMouseWheel(f, delta)


def _under(G, dx, dy):
    v = G.shownView
    return G.ScreenToWorld(v.x, v.y, dx, dy, v.rot, v.s)


def _at(lua, ns, cont, x, y, zoom):
    lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}")
    ns.settings.gps.zoom = zoom
    ns.GPS.Follow()
    ns.GPS.Update()


@pytest.mark.parametrize("zoom", [200, 600, 2500, 4000])
def test_the_spot_under_the_cursor_stays_put_as_the_wheel_turns(zoom):
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *BRILL, zoom)
    dx, dy = 120, -70
    _cursor(lua, dx, dy)
    spot = _under(G, dx, dy)
    for delta in (1, 1, 1, -1, -1, -1, -1, 1):
        _wheel(lua, delta)
        G.Update()
        assert G.shownView.cont == 0
        assert _under(G, dx, dy) == pytest.approx(spot, abs=max(1.0, 0.002 * zoom))
    # (zoomed at the cursor off the middle: no longer following, as a drag; "Back to your position" shows)
    assert G.BrowseState()[1] is not None


def test_the_cursor_on_the_middle_zooms_in_place_and_keeps_following():
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *BRILL, 600)
    _cursor(lua, 2, -3)  # (within CURSOR_ZOOM_STILL_PX)
    _wheel(lua, 1)
    G.Update()
    assert G.BrowseState()[1] is None and ns.settings.gps.zoom == pytest.approx(600 / G.ZOOM_STEP)
    assert (G.shownView.x, G.shownView.y) == pytest.approx(BRILL[1:], abs=1)


def test_the_controller_keys_and_buttons_zoom_about_the_middle_and_keep_following():
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *BRILL, 600)
    _cursor(lua, 150, 90)  # (wherever the mouse is: G.WheelZoom has no cursor)
    for f in (G.ZOOM_STEP, G.ZOOM_STEP, 1 / G.ZOOM_STEP):
        G.WheelZoom(f)
        G.Update()
        assert G.BrowseState()[1] is None
        assert (G.shownView.x, G.shownView.y) == pytest.approx(BRILL[1:], abs=1)


def test_the_minimap_square_zooms_about_the_player():
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *BRILL, 600)
    lua.execute("AGPS_MMODE = AGPS_NS.GPS.MinimapMode AGPS_NS.GPS.MinimapMode = function() return true end")
    try:
        _cursor(lua, 120, -70)
        assert G.WheelAt(G.ZOOM_STEP, 120, -70) == pytest.approx(600 * G.ZOOM_STEP)
        assert G.BrowseState()[1] is None  # (the square is always on the player)
    finally:
        lua.execute("AGPS_NS.GPS.MinimapMode = AGPS_MMODE")


def test_the_other_map_styles_zoom_at_the_cursor_too():
    # (the code is the map's own: the Terrain style's view and a browsed world map alike)
    lua, ns = _seamless(on=False)
    G = ns.GPS
    assert not G.Seamless()
    _at(lua, ns, *BRILL, 800)
    dx, dy = -110, 60
    _cursor(lua, dx, dy)
    spot = _under(G, dx, dy)
    for delta in (1, 1, -1):
        _wheel(lua, delta)
        G.Update()
        assert _under(G, dx, dy) == pytest.approx(spot, abs=1)


def _corners_on_screen(G, cont):
    """Azeroth's map's corners on the canvas (px from its middle, y up), the view's half width and height."""
    v = G.shownView
    b = G.WorldBounds(cont)
    out = []
    for x, y in ((b[1], b[2]), (b[1], b[4]), (b[3], b[2]), (b[3], b[4])):
        dx, dy = (y - v.y) * -1, x - v.x  # (east is -y, north +x: G.ScreenToWorld's inverse at rot 0)
        out.append((dx * v.s, dy * v.s))
    return out


def _canvas_half(lua):
    lua.execute("""local c = AGPS_NS.GPS.Canvas and AGPS_NS.GPS.Canvas()
      AGPS_CW, AGPS_CH = c and c:GetWidth() or 400, c and c:GetHeight() or 400""")
    return lua.eval("AGPS_CW") / 2, lua.eval("AGPS_CH") / 2


def _check_world_view(lua, ns):
    G = ns.GPS
    v = G.shownView
    assert v.world and v.artOnly and v.seamFar and v.rot == 0
    cont = ns.Geo.Base(v.cont)
    b = G.WorldBounds(cont)
    assert (v.x, v.y) == pytest.approx(((b[1] + b[3]) / 2, (b[2] + b[4]) / 2))  # (centered on Azeroth's map)
    hw, hh = _canvas_half(lua)
    pts = _corners_on_screen(G, cont)
    # the whole of it in the window, fitting it: one side edge to edge
    assert all(abs(x) <= hw + 0.5 and abs(y) <= hh + 0.5 for x, y in pts)
    assert max(abs(x) for x, _ in pts) == pytest.approx(hw, abs=1) or max(abs(y) for _, y in pts) == pytest.approx(hh, abs=1)
    # both continents in view: Orgrimmar and Stormwind on the map
    for c, x, y in (ORGRIMMAR, STORMWIND):
        mx, my = ns.Geo.ToContinent(c, x, y, v.cont)
        dx, dy = ns.Geo.ScreenOffset(v.x, v.y, mx, my)
        assert abs(dx * v.s) < hw and abs(dy * v.s) < hh, (c, x, y)


@pytest.mark.parametrize("start", [BRILL, ORGRIMMAR])
def test_zoomed_all_the_way_out_both_continents_fit_and_there_is_nothing_to_pan(start):
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *start, 600)
    _cursor(lua, 140, 80)  # (wherever the mouse: the world view's middle is Azeroth's map's)
    for _ in range(60):
        if ns.settings.gps.zoom >= G.MaxZoom() * 0.999:
            break
        _wheel(lua, -1)
        G.Update()
    assert ns.settings.gps.zoom == pytest.approx(G.MaxZoom())
    _check_world_view(lua, ns)
    shown = (G.shownView.x, G.shownView.y)
    # a drag out there: nothing moves, and following isn't let go
    f = _frame(lua)
    lua.execute("AGPS_FREE0 = select(2, AGPS_NS.GPS.BrowseState())")
    lua.execute("GetCursorPosition = function() return 300, 300 end")
    f._scripts.OnMouseDown(f, "LeftButton")
    lua.execute("GetCursorPosition = function() return 520, 140 end")
    f._scripts.OnUpdate(f, 0.05)
    G.Update()
    assert (G.shownView.x, G.shownView.y) == pytest.approx(shown)
    f._scripts.OnMouseUp(f, "LeftButton")
    assert lua.eval("select(2, AGPS_NS.GPS.BrowseState()) == AGPS_FREE0")
    G.PadPan(200, -150)  # (the controller's stick too)
    G.Update()
    assert (G.shownView.x, G.shownView.y) == pytest.approx(shown)


def test_a_view_looked_at_elsewhere_never_goes_past_the_maps_edge():
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *BRILL, 9000)
    x, y = ns.Geo.ToContinent(1, 9850.0, 960.0, 0)  # (Teldrassil, at the map's top)
    G.LookAt(0, x, y, 12000)
    G.Update()
    v = G.shownView
    hw, hh = _canvas_half(lua)
    pts = _corners_on_screen(G, ns.Geo.Base(v.cont))
    # (the map's top edge at or over the window's: no paper past it)
    assert max(y for _, y in pts) >= hh - 0.5 and min(y for _, y in pts) <= -hh + 0.5
    # zoomed back in, the spot looked at is the middle again (only the drawing was kept on the map)
    for _ in range(25):
        G.WheelZoom(1 / G.ZOOM_STEP)
        G.Update()
    v = G.shownView
    assert v.cont == 1 and (v.x, v.y) == pytest.approx((9850.0, 960.0), abs=2)


def test_zooming_in_from_the_world_view_at_the_other_continent_shows_it():
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *BRILL, 600)
    ns.settings.gps.zoom = G.MaxZoom()
    G.Update()
    assert G.shownView.world and G.shownView.cont == 0
    # the mouse on Orgrimmar (Kalimdor, the other continent)
    v = G.shownView
    mx, my = ns.Geo.ToContinent(*ORGRIMMAR, 0)
    dx, dy = ns.Geo.ScreenOffset(v.x, v.y, mx, my)
    dx, dy = dx * v.s, dy * v.s
    _cursor(lua, dx, dy)
    for _ in range(30):
        _wheel(lua, 1)
        G.Update()
        assert _under(G, dx, dy) == pytest.approx(ns.Geo.ToContinent(*ORGRIMMAR, G.shownView.cont), abs=60)
    v = G.shownView
    assert not v.world and v.cont == 1  # (Kalimdor's own yards: its terrain, roads and icons as zoomed in there)
    assert _under(G, dx, dy) == pytest.approx(ORGRIMMAR[1:], abs=40)  # (Azeroth's map's two yards: a hair apart)


def test_a_double_click_on_the_other_continent_in_the_world_view_is_a_stop_there():
    lua, ns = _seamless()
    G = ns.GPS
    _at(lua, ns, *BRILL, 600)
    ns.settings.gps.zoom = G.MaxZoom()
    G.Update()
    v = G.shownView
    mx, my = ns.Geo.ToContinent(*ORGRIMMAR, v.cont)
    dx, dy = ns.Geo.ScreenOffset(v.x, v.y, mx, my)
    G.AddPending(dx * v.s, dy * v.s)
    p = G.PendingStop(1)
    assert p and p.cont == 1 and (p.x, p.y) == pytest.approx(ORGRIMMAR[1:], abs=60)


def _route_across_the_sea(lua, ns):
    lua.execute(f"AGPS_POS = {{ {RAZOR_HILL[1]}, {RAZOR_HILL[2]}, {RAZOR_HILL[0]} }}")
    ns.CharDB().faction = "Horde"
    ns.Nav.SetStops(lua.eval(f"{{ {{ x = {BRILL[1]}, y = {BRILL[2]}, cont = {BRILL[0]}, name = 'Brill' }} }}"), False,
                    "red")
    ns.GPS.Update()
    r = ns.Nav.route
    assert r and {p.cont for p in r.parts.values()} == {0, 1}  # (the zeppelin from Orgrimmar to Tirisfal)
    return r


def _drawn_near(G, sx, sy, px=3.0):
    segs, n = G.DrawnSegs()
    for i in range(1, n + 1):
        sg = segs[i]
        if sg[8] and ((sg[1] - sx) ** 2 + (sg[2] - sy) ** 2 <= px * px or (sg[3] - sx) ** 2 + (sg[4] - sy) ** 2 <= px * px):
            return True
    return False


def test_the_route_across_both_continents_draws_in_the_world_view():
    lua, ns = _seamless()
    G = ns.GPS
    r = _route_across_the_sea(lua, ns)
    G.Follow()
    ns.settings.gps.zoom = G.MaxZoom()
    G.Update()
    _check_world_view(lua, ns)
    v = G.shownView
    # each leg (Kalimdor's walk, the zeppelin, Tirisfal's walk) drawn where Azeroth's map has it
    for part in r.parts.values():
        pts = list(part.pts.values())
        k = (len(pts) // 4) * 2  # (a point along it)
        x, y = ns.Geo.ToContinent(part.cont, pts[k], pts[k + 1], v.cont)
        dx, dy = ns.Geo.ScreenOffset(v.x, v.y, x, y)
        assert _drawn_near(G, dx * v.s, dy * v.s), (part.cont, len(pts))


def test_the_world_view_shows_the_other_continents_flight_masters_and_docks():
    lua, ns = _seamless()
    G = ns.GPS
    _route_across_the_sea(lua, ns)
    ns.Nav.Clear()
    G.Follow()
    ns.settings.gps.zoom = G.MaxZoom()
    G.Update()
    v = G.shownView
    assert v.world and v.cont == 1
    levels = {(v.cont if b.level is None else b.level) for b in G.poiButtons.values() if b.IsShown(b)}
    assert 0 in levels and 1 in levels  # (both continents' icons)
    docks = [b for b in G.poiButtons.values() if b.IsShown(b) and b.dock]
    assert {b.level for b in docks} >= {0, 1}
    # a dock on the other continent: its stop is there, in its own yards
    other = next(b for b in docks if b.level == 0)
    assert ns.Geo.Base(other.level) == 0 and -16000 < other.wx < 7000


def test_the_world_view_redraw_stays_cheap():
    """The frame budget at the world zoom: no tiles laid, the route's look at only its own segments, and a redraw
    about what the continent stage's costs (lupa's CPU ms; the bound leaves room for a busy machine)."""
    lua, ns = _seamless()
    G = ns.GPS
    _route_across_the_sea(lua, ns)
    G.Follow()

    def cost(zoom, n=6):
        ns.settings.gps.zoom = zoom
        G.Update()
        best = float("inf")
        for _ in range(n):
            G.Redraw()
            t = time.perf_counter()
            G.Update()
            best = min(best, time.perf_counter() - t)
        return best * 1000

    continent = cost(9000)
    world = cost(G.MaxZoom())
    assert G.shownView.world
    lua.execute("AGPS_Q = AGPS_NS.GPS.laidTiles.quads == AGPS_NS.GPS.NO_QUADS")
    assert lua.eval("AGPS_Q")  # (the art alone: no terrain tiles)
    before = G.segsSeen
    G.Redraw()
    G.Update()
    assert G.segsSeen - before < 2000
    assert world < continent * 2 + 8, (world, continent)


def test_the_world_view_in_the_games_world_map_is_the_same():
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute(WM_SETUP)
    st.shown, st.minimized = True, None
    st.useWorldMap = True
    lua.execute("WorldMapFrame:Show()")
    G.WorldMapChanged()
    G.ApplySettings()
    try:
        assert G.WorldMapHosted()
        _at(lua, ns, *BRILL, 600)
        # the wheel at the cursor: the same frame's, the spot under it kept
        dx, dy = 90, 50
        _cursor(lua, dx, dy)
        spot = _under(G, dx, dy)
        for delta in (1, -1, -1):
            _wheel(lua, delta)
            G.Update()
            assert _under(G, dx, dy) == pytest.approx(spot, abs=2)
        # out to the world: Azeroth's whole map in the world map's box
        st.zoom = G.MaxZoom()
        G.Update()
        _check_world_view(lua, ns)
    finally:
        lua.execute("WorldMapFrame:Hide()")
        st.useWorldMap = False
        G.WorldMapChanged()
        G.ApplySettings()


def test_the_world_zoom_comes_back_after_a_reload():
    # (the zoom is the saved setting `zoom`: saved out at the world, read back at login, the world view again;
    # nothing else of it is saved: it's Azeroth's map's middle, not a spot)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    from test_atlas import STITCH_PROJECTION, WORLD_MAPS
    lua, ns = start(saved="AzerothGPSDB = { settings = { gps = { style = 'seamless', zoom = 30000 } }, "
                          "seamlessDefault60 = true, mapStyles75 = true }")
    lua.execute(WORLD_MAPS)
    lua.execute(STITCH_PROJECTION)
    ns.Nav.FUN = False
    G = ns.GPS
    lua.execute(f"AGPS_POS = {{ {BRILL[1]}, {BRILL[2]}, {BRILL[0]} }}")
    G.Update()
    assert ns.settings.gps.zoom == 30000 and G.AtWorldZoom()
    _check_world_view(lua, ns)
