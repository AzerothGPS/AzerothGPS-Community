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
        "navPanelDetached", "navPanelPoint", "navPanelDetachedWidth", "navPanelHideButtons", "navPanelAlpha",
        "navPanelDetachedHeight", "stepsAll", "stepsCollapsed")


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


# The detached panel's own looks (1.3.9, asked 2026-11-18: "for the detached route panel, add options to hide all
# buttons in it and set the opacity of the background") and its corner grip ("add a corner resizer for the window so
# text would only stay within that, steps that would go past it show as '... X more steps'").

def _detach(lua, ns, **kw):
    G, st = ns.GPS, ns.settings.gps
    st.navPanelPoint, st.navPanelDetachedHeight, st.navPanelDetachedWidth = None, None, None
    st.navPanelDetached, st.stepsCollapsed = True, False  # (collapsed: no use button)
    for k, v in kw.items():
        st[k] = v
    G.ApplySettings()
    _route(lua, ns)
    G.navPanelSig = None
    G.Update()
    return G.navPanel


def _buttons_shown(ns):
    G = ns.GPS
    return [b._shown for b in (G.navCancel, G.navDetach, G.stepsToggle, G.stepsMore, G.shareButton)]


def test_hide_the_buttons_leaves_only_the_text_and_attaching_brings_them_back(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    old = ns.Nav.UseNow
    # (the route's first step a hearthstone: the use button; in a group: Share)
    ns.Nav.UseNow = lua.eval("function() return { item = 6948, [8] = 'Hearthstone', [10] = 'Far' } end")
    lua.execute("IsInGroup = function() return true end")
    try:
        p = _detach(lua, ns, navPanelHideButtons=False)
        assert G.navCancel._shown and G.navDetach._shown and G.shareButton._shown and G.useBtn._shown
        assert G.navGrip._shown and G.navGrip._alpha == 1
        st.navPanelHideButtons = True
        G.ApplySettings()
        G.Update()
        assert G.NavBare() and p._shown and str(G.navText._text) != ""
        assert not any(_buttons_shown(ns)) and not G.useBtn._shown
        assert (G.navText._pts["TOPRIGHT"][2], G.navText._pts["TOPRIGHT"][3]) == (-6, -6)  # (the text out to the edge)
        # (the corner grip: there, seen only under the mouse)
        assert G.navGrip._shown and G.navGrip._alpha == 0
        p._scripts.OnEnter(p)
        assert G.navGrip._alpha == 1
        p._scripts.OnLeave(p)
        assert G.navGrip._alpha == 0
        # (still dragged anywhere)
        p._scripts.OnDragStop(p)
        assert list(st.navPanelPoint.values())[0] == "TOPLEFT"
        # (a right-click: back on the map, with every button)
        p._scripts.OnMouseUp(p, "RightButton")
        assert st.navPanelDetached is False and not G.navDetached and not G.NavBare()
        assert lua.eval("rawequal")(p.GetParent(p), G.navHome) and not G.navGrip._shown
        G.Update()
        assert G.navCancel._shown and G.navDetach._shown and G.shareButton._shown and G.useBtn._shown
        assert (G.navText._pts["TOPRIGHT"][2], G.navText._pts["TOPRIGHT"][3]) == (-58, -6)
        # (the option kept: detached again, bare again)
        G.navDetach._scripts.OnClick(G.navDetach, "LeftButton")
        G.Update()
        assert G.NavBare() and not any(_buttons_shown(ns)) and not G.useBtn._shown
        # (a left click does nothing of the sort)
        p._scripts.OnMouseUp(p, "LeftButton")
        assert G.navDetached
    finally:
        ns.Nav.UseNow = old
        lua.execute("IsInGroup = nil")


def test_the_background_opacity_is_the_detached_panels_alone(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    assert ns.DEFAULTS.gps.navPanelAlpha == 70 and ns.DEFAULTS.gps.navPanelHideButtons is False
    p = _detach(lua, ns, navPanelAlpha=25)
    assert p._bg[4] == pytest.approx(0.25)
    st.navPanelAlpha = 0
    G.ApplySettings()
    assert p._bg[4] == 0 and str(G.navText._text) != ""  # (only the text)
    st.navPanelAlpha = 250  # (clamped)
    G.ApplySettings()
    assert p._bg[4] == 1
    # (on the map: the usual box, whatever it's set to)
    st.navPanelAlpha = 10
    st.navPanelDetached = False
    G.ApplySettings()
    assert p._bg[4] == pytest.approx(0.7)


STEPS = "\n".join(("|cffffffff" if i == 1 else "|cffb0b0b0") + "%d. Step %d|r" % (i, i) for i in range(1, 11))


def test_the_more_steps_line_counts_what_is_left_out(rp):
    lua, ns = rp
    G = ns.GPS
    lines = STEPS.split("\n")
    out, more = G.FitSteps(STEPS, 4, 10)  # (3 steps and the line saying the rest)
    assert out.split("\n") == lines[:3] + ["|cff808080... 7 more steps|r"] and more == 7
    out, more = G.FitSteps(STEPS, 10, 10)
    assert out == STEPS and more == 0
    out, more = G.FitSteps(STEPS, 9, 10)  # (8 and "2 more": a line never says "1 more" in place of the step itself)
    assert out.split("\n")[-1] == "|cff808080... 2 more steps|r" and more == 2
    out, more = G.FitSteps("\n".join(lines[:2]), 1, 2)
    assert out == "|cff808080... 2 more steps|r" and more == 2
    # (singular: a list already cut short, one step past it)
    out, more = G.FitSteps("\n".join(lines[:3] + ["|cff808080... 7 more steps|r"]), 4, 4)
    assert more == 0
    out, more = G.FitSteps("\n".join(lines[:3]), 3, 4)  # (3 of 4 listed, all fit: nothing said here)
    assert more == 0 and out == "\n".join(lines[:3])
    # (a list already cut at 3, "... 7 more steps", 10 in all: what's left out counted from the whole route)
    cut = "\n".join(lines[:3] + ["|cff808080... 7 more steps|r"])
    out, more = G.FitSteps(cut, 3, 10)
    assert out.split("\n") == lines[:2] + ["|cff808080... 8 more steps|r"] and more == 8
    out, more = G.FitSteps(cut, 4, 10)
    assert out == cut and more == 0
    # (the walk's turns with no count: "... more turns further on")
    out, more = G.FitSteps(cut, 2, False)
    assert out.split("\n") == lines[:1] + ["|cff808080... more turns further on|r"]
    # (no room at all: none of them)
    assert G.FitSteps(STEPS, 0, 10)[0] == ""
    assert G.MoreStepsLine(1) == "|cff808080... 1 more step|r"
    assert G.MoreStepsLine(2) == "|cff808080... 2 more steps|r"
    # (in the player's language: the locale's own words, the step lines still told apart)
    assert G.IsStepLine("|cffb0b0b012. Нажмите|r") and not G.IsStepLine("|cff808080... 3 more steps|r")


def test_a_sized_panel_keeps_its_text_inside_it(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    p = _detach(lua, ns)
    assert not G.NavFixed() and G.navText._wrap is not False  # (not sized yet: as tall as its text)
    G.SizeNavDetached(300, 200)
    status = "Walk 4m 35s\nAll stops 9m"
    # (the stand-in's lines: 12 high; the steps' 12 and 2 between: 14 a line)
    def fit(h):
        st.navPanelDetachedHeight = h
        G.navText._text = status
        G.FitNavPanel(STEPS, 10, 0)
        return str(G.stepsText._text).split("\n"), G.navMore

    base = 12 + 2 * 12 + 4 - 2
    lines, more = fit(base + 14 * 4)
    assert len(lines) == 4 and lines[-1] == "|cff808080... 7 more steps|r" and more == 7
    assert p._h == base + 14 * 4 and str(G.navText._text) == status
    lines, more = fit(base + 14 * 10)
    assert more == 0 and "\n".join(lines) == STEPS
    lines, more = fit(base + 14 * 9 + 13)  # (not quite room for the last: the line says the 2)
    assert more == 2 and lines[-1] == "|cff808080... 2 more steps|r"
    # (the smallest: the status lines, no room for a step)
    lines, more = fit(G.NAV_DETACHED_MIN_H)
    assert str(G.navText._text) == "Walk 4m 35s\nAll stops 9m" and lines == [""] and not G.stepsText._shown
    st.navPanelDetachedHeight = None
    # (through the panel's own update: the route's text, the height kept, no line wrapped)
    G.SizeNavDetached(300, 60)
    G.Update()
    assert G.NavFixed() and p._h == 60 and G.navText._wrap is False and G.stepsText._wrap is False


def test_the_corner_grip_sizes_it_clamped_and_kept_over_a_reload(rp):
    lua, ns = rp
    G, st = ns.GPS, ns.settings.gps
    p = _detach(lua, ns)
    g = G.navGrip
    assert g._shown
    try:
        # (the stand-in panel is 400 x 400: dragged 100 right and 250 down, then far up and left)
        lua.execute("AGPS_CUR = { 0, 0 } GetCursorPosition = function() return AGPS_CUR[1], AGPS_CUR[2] end")
        g._scripts.OnMouseDown(g, "LeftButton")
        assert p._pts["TOPLEFT"][2] is not None and p._pts["TOPLEFT"][3] == "BOTTOMLEFT"
        lua.execute("AGPS_CUR = { 100, -150 }")
        g._scripts.OnUpdate(g, 0.01)
        assert (st.navPanelDetachedWidth, st.navPanelDetachedHeight) == (500, 550)
        assert (p._w, p._h) == (500, 550)
        lua.execute("AGPS_CUR = { -5000, 5000 }")
        g._scripts.OnUpdate(g, 0.01)
        assert (st.navPanelDetachedWidth, st.navPanelDetachedHeight) == (G.NAV_MIN_W, G.NAV_DETACHED_MIN_H)
        lua.execute("AGPS_CUR = { 5000, -5000 }")
        g._scripts.OnUpdate(g, 0.01)
        assert (st.navPanelDetachedWidth, st.navPanelDetachedHeight) == (G.NAV_DETACHED_MAX_W, G.NAV_DETACHED_MAX_H)
        lua.execute("AGPS_CUR = { -100, 100 }")
        g._scripts.OnUpdate(g, 0.01)
        g._scripts.OnMouseUp(g, "LeftButton")
        lua.execute("AGPS_CUR = { 0, 0 }")
        g._scripts.OnUpdate(g, 0.01)  # (let go: no more sizing)
        assert (st.navPanelDetachedWidth, st.navPanelDetachedHeight) == (300, 300)
        # (kept: in the saved variables, and set again as it's detached after a reload)
        assert lua.eval("rawequal")(ns.db, lua.eval("AzerothGPSDB"))
        saved = ns.settings.gps
        assert (saved.navPanelDetachedWidth, saved.navPanelDetachedHeight) == (300, 300)
        st.navPanelDetached = False
        G.ApplySettings()
        p._w, p._h = None, None
        st.navPanelDetached = True
        G.ApplySettings()
        assert (p._w, p._h) == (300, 300) and G.NavFixed()
        # (a saved size out of range: clamped as it's read)
        st.navPanelDetachedHeight = 3
        assert G.NavDetachedHeight() == G.NAV_DETACHED_MIN_H
    finally:
        lua.execute("GetCursorPosition = function() return 0, 0 end")
