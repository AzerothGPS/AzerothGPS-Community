"""The map's route panel, the bar across the map's top with the route's distance and times (1.3.9, asked 2026-11-18:
"make this section's width resizable and its position like left, right, or middle ... add an option to 'detach this' as
a separate window similar to the direction's text box and this stays open even when map in collapsed"): its width
(`navPanelWidth`, a share of the map's), its side (`navPanelAlign`), both in the map's own window and in the game's world
map; detached (`navPanelDetached`) in its own window, kept up to date and open while the map is closed, minimized or
the world map closed, dragged where it's kept (`navPanelPoint`), and put back on the map."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

KEYS = ("useWorldMap", "replaceMinimap", "shown", "minimized", "windowFrame", "navPanelWidth", "navPanelAlign",
        "navPanelDetached", "navPanelPoint", "navPanelDetachedWidth")


@pytest.fixture
def rp(game):  # noqa: F811
    lua, ns = game
    lua.execute(SETUP)
    st = ns.settings.gps
    was = {k: st[k] for k in KEYS}
    st.shown, st.minimized = True, None
    frame = lua.eval("AzerothGPSFrame")
    yield lua, ns
    lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
    for k, v in was.items():
        st[k] = v
    frame.Show(frame)
    ns.Nav.Clear()
    ns.GPS.WorldMapChanged()
    ns.GPS.ApplySettings()


def _route(lua, ns):
    x0, y0 = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    ns.Nav.Clear()
    ns.Nav.SetStops(lua.eval("{ { x = %f, y = %f, cont = 0, name = 'Far' } }" % (x0 + 300.0, y0 + 200.0)), False, "red")
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()


def _seen(lua, f):
    # (shown with every frame it hangs from: the stand-in's IsVisible is the frame's own flag)
    n = 0
    while f is not None and n < 50:
        if not f._shown:
            return False
        if lua.eval("rawequal")(f, lua.eval("UIParent")):
            return True
        f = f.GetParent(f)
        n += 1
    return True


def _placed(lua, ns):
    G = ns.GPS
    p = G.navPanel
    pts = {k: (v[1], v[2], v[3]) for k, v in p._pts.items()}
    return p, pts


def test_the_panels_width_and_side_on_the_maps_own_window(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    # (by default as before: the whole width right of the inset)
    st.navPanelWidth, st.navPanelAlign = None, None
    G.ApplySettings()
    p, pts = _placed(lua, ns)
    inset = G.topInset
    assert pts == {"TOPLEFT": ("TOPLEFT", inset, -4), "TOPRIGHT": ("TOPRIGHT", -4, -4)}
    assert G.NavWidthPct() == 100 and G.NavAlign() == "left"
    room = G.NavRoom()
    assert room == G.navHome.GetWidth(G.navHome) - inset - 4
    st.navPanelWidth = 50
    for align, want in (("left", {"TOPLEFT": ("TOPLEFT", inset, -4)}),
                        ("center", {"TOP": ("TOP", (inset - 4) / 2, -4)}),
                        ("right", {"TOPRIGHT": ("TOPRIGHT", -4, -4)})):
        st.navPanelAlign = align
        G.ApplySettings()
        p, pts = _placed(lua, ns)
        assert pts == want and p._w == pytest.approx(room * 0.5)
        # (its free edge: the right one, the left one while it's on the right)
        e = G.navEdge
        assert set(e._pts) == ({"TOPRIGHT", "BOTTOMRIGHT"} if align == "right" else {"TOPLEFT", "BOTTOMLEFT"})
    # (never narrower than its buttons need, nor past the room)
    st.navPanelWidth = 5
    G.ApplySettings()
    assert G.NavWidthPct() == G.NAV_MIN_PCT and G.navPanel._w == max(G.NAV_MIN_W, room * G.NAV_MIN_PCT / 100)


def test_dragging_the_panels_edge_sets_its_width(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    G.ApplySettings()
    room = G.NavRoom()
    st.navPanelAlign = "left"
    G.DragNavEdge(room, -room / 2)  # (the right edge dragged half way in)
    assert st.navPanelWidth == 50
    st.navPanelAlign = "right"
    G.DragNavEdge(room * 0.5, -room * 0.2)  # (its left edge dragged out: wider)
    assert st.navPanelWidth == 70
    st.navPanelAlign = "center"
    G.DragNavEdge(room * 0.7, -room * 0.1)  # (in the middle: both sides come in)
    assert st.navPanelWidth == 50
    G.DragNavEdge(room * 0.5, room)
    assert st.navPanelWidth == 100


def test_the_panels_width_and_side_in_the_world_map_too(rp):
    # (CLAUDE.md "Both maps, same features": the world map's panel is the same panel, right of its corner buttons)
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    st.navPanelWidth, st.navPanelAlign = 60, "right"
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()
    assert G.WorldMapHosted() and G.topInset == G.WORLD_MAP_INSET
    p, pts = _placed(lua, ns)
    assert pts == {"TOPRIGHT": ("TOPRIGHT", -4, -4)} and p._w == pytest.approx(G.NavRoom() * 0.6)
    st.navPanelAlign = "left"
    G.ApplySettings()
    p, pts = _placed(lua, ns)
    assert pts == {"TOPLEFT": ("TOPLEFT", G.WORLD_MAP_INSET, -4)}


def test_the_detached_panel_stays_open_with_the_map_closed_and_goes_back(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    frame = lua.eval("AzerothGPSFrame")
    ui = lua.eval("UIParent")
    st.navPanelPoint = None
    G.ApplySettings()
    _route(lua, ns)
    p = G.navPanel
    assert p._shown and _seen(lua, p) and str(G.navText._text) != ""
    assert lua.eval("rawequal")(p.GetParent(p), G.navHome)
    # (its button on the panel: detached, a panel of its own on the screen, dragged anywhere)
    G.navDetach._scripts.OnClick(G.navDetach, "LeftButton")
    assert st.navPanelDetached is True and G.navDetached
    assert lua.eval("rawequal")(p.GetParent(p), ui) and p._strata == G.NAV_DETACHED_STRATA
    assert p._pts["TOP"][1] == "TOP" and lua.eval("rawequal")(p._pts["TOP"][2], ui)
    assert p._w == G.NAV_DETACHED_W and not G.NavOnMap()
    # (the map closed: the panel stays, its text kept up by the pump frame)
    frame.Hide(frame)
    assert not G.IsVisible()
    G.navText._text = ""
    G.navPanelSig = None
    lua.execute("AGPS_T = AGPS_T + 1")
    G.pumpFrame._scripts.OnUpdate(G.pumpFrame, G.NAV_DETACHED_EVERY)
    assert _seen(lua, p) and str(G.navText._text) != ""
    # (minimized: the same)
    frame.Show(frame)
    G.SetMinimized(True)
    assert not frame._shown and _seen(lua, p)
    G.SetMinimized(False)
    # (dragged: where it's kept)
    p._scripts.OnDragStop(p)
    assert list(st.navPanelPoint.values()) == ["TOPLEFT", "UIParent", "BOTTOMLEFT", 100, 500]
    G.ApplySettings()
    tl = p._pts["TOPLEFT"]
    assert lua.eval("rawequal")(tl[2], ui) and (tl[3], tl[4], tl[5]) == ("BOTTOMLEFT", 100, 500)
    # (its edge sizes it, kept)
    G.DragNavEdge(G.NAV_DETACHED_W, 80)
    assert st.navPanelDetachedWidth == G.NAV_DETACHED_W + 80 and p._w == G.NAV_DETACHED_W + 80
    # (no route: gone, with the map closed too)
    frame.Hide(frame)
    ns.Nav.Clear()
    G.pumpFrame._scripts.OnUpdate(G.pumpFrame, G.NAV_DETACHED_EVERY)
    assert not p._shown
    _route(lua, ns)
    G.pumpFrame._scripts.OnUpdate(G.pumpFrame, G.NAV_DETACHED_EVERY)
    assert p._shown
    # (attached again, the map minimized: on the map, hidden with it)
    frame.Show(frame)
    G.SetMinimized(True)
    assert _seen(lua, p)
    G.navDetach._scripts.OnClick(G.navDetach, "LeftButton")
    assert st.navPanelDetached is False and not G.navDetached
    assert lua.eval("rawequal")(p.GetParent(p), G.navHome)
    assert not _seen(lua, p)
    G.SetMinimized(False)
    G.Update()
    assert _seen(lua, p) and G.NavOnMap()


def test_the_detached_panel_stays_open_with_the_world_map_closed(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap, st.navPanelDetached = True, True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()  # (the world map open, the map in it)
    assert G.WorldMapHosted()
    _route(lua, ns)
    p = G.navPanel
    assert _seen(lua, p) and lua.eval("rawequal")(p.GetParent(p), lua.eval("UIParent"))
    # (the world map's levels kept for the map's frames: the detached panel isn't the map's)
    p._level = 10
    G.WorldMapTick()
    G.SetLevelTree(G.WorldMapLevel(), None, True)
    assert p._level == 10
    lua.globals().AzerothGPS_ToggleMap()  # (closed)
    assert not G.WorldMapHosted() and not G.IsVisible()
    lua.execute("AGPS_T = AGPS_T + 1")
    G.pumpFrame._scripts.OnUpdate(G.pumpFrame, G.NAV_DETACHED_EVERY)
    assert _seen(lua, p) and str(G.navText._text) != ""
    # (the option off: back in the world map's map)
    st.navPanelDetached = False
    G.ApplySettings()
    assert lua.eval("rawequal")(p.GetParent(p), G.navHome) and not _seen(lua, p)


def test_the_route_panel_options_are_on_the_map_window_page(game):  # noqa: F811
    lua, ns = game
    st = ns.settings.gps
    d = ns.DEFAULTS.gps
    assert d.navPanelWidth == 100 and d.navPanelAlign == "left" and d.navPanelDetached is False
    ns.Options.Show()
    pages = {c.key: c.page for c in ns.Options.settingControls.values() if not c.mirror}
    assert {k: pages.get(k) for k in ("navPanelWidth", "navPanelAlign", "navPanelDetached")} == {
        "navPanelWidth": "Window", "navPanelAlign": "Window", "navPanelDetached": "Window"}
    assert st is not None
