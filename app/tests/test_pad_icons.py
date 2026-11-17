"""The controller's buttons as pixel-art icons on the map, and Options > Controller's gold diagram (asked 2026-11-16:
"generate a set of pixel like controller icons to use on the map for controls instead of just using the letter";
"convert the Controller option page to look something like this ... transparent background with gold controller drawn
lines"). padicons.py draws them (`agps padicons`); Pad.lua shows them (Pad.KeyIcon, Pad.LegendText(true),
Pad.BoxLines(true), Pad.DiagramLabel); Options.lua lays the diagram out (O.LayoutPadDiagram)."""
import struct

import pytest

from azerothgps import padicons
from azerothgps.paths import ADDON_DIR

from test_controller import pad  # noqa: F401 (the fixture)

PAD_PATH = "Interface\\AddOns\\AzerothGPS\\Media\\Pad\\"


def _tga_size(path):
    head = path.read_bytes()[:18]
    return struct.unpack("<HH", head[12:16])


def _file(lua_path):
    """The addon's file a Lua path names."""
    rel = str(lua_path).replace(PAD_PATH, "")
    return ADDON_DIR / "Media" / "Pad" / rel


def _icon(name, px=14):
    return "|T%s%s_%d.tga:14:14|t" % (PAD_PATH, name, px)


def test_the_icons_and_diagrams_are_ours_up_to_date_and_drawn_at_the_size_shown(pad):
    lua, ns = pad
    P = ns.Pad
    assert list(P.ICON_PX.values()) == list(padicons.ICON_PX)
    names = set(P.ICONS.values()) | set(P.SHAPE_ICONS.values())
    assert names <= set(padicons.ICONS)
    for name in sorted(names):
        for n in padicons.ICON_PX:
            f = padicons.icon_file(name, n)
            assert f.parent == ADDON_DIR / "Media" / "Pad" and f.is_file(), f
            assert _tga_size(f) == (n, n), f  # (pixel for pixel at the size it's shown)
            assert f.read_bytes() == padicons.tga_rgba(padicons.icon(name, n)), f
    D = P.DIAGRAM
    assert (D.w, D.h, D.row0, D.step) == (padicons.DIAGRAM_W, padicons.DIAGRAM_H, padicons.DIAGRAM_ROW0,
                                          padicons.DIAGRAM_ROW_STEP)
    assert list(D.scales.values()) == list(padicons.DIAGRAM_SCALES)
    assert list(D.left.values()) == [k for k, _ in padicons.DIAGRAM_LEFT]
    assert list(D.right.values()) == [k for k, _ in padicons.DIAGRAM_RIGHT]
    for s in padicons.DIAGRAM_SCALES:
        f = padicons.diagram_file(s)
        assert _tga_size(f) == (round(D.w * s), round(D.h * s)), f
        assert f.read_bytes() == padicons.tga_rgba(padicons.diagram(s)), f
    # (nothing else in the folder: stale sizes removed)
    shipped = {p.name for p in (ADDON_DIR / "Media" / "Pad").iterdir()}
    want = {padicons.icon_file(n, px).name for n in padicons.ICONS for px in padicons.ICON_PX}
    want |= {padicons.diagram_file(s).name for s in padicons.DIAGRAM_SCALES}
    assert shipped == want


def test_the_map_shows_the_buttons_as_icons_with_text_where_there_is_none(pad):
    lua, ns = pad
    P = ns.Pad
    P.Apply()
    legend = str(P.LegendText(True))
    assert legend.startswith(_icon("A") + ": Set Stop")
    assert _icon("X") + ": Remove" in legend and _icon("B") + ": Back" in legend
    assert _icon("LT") + "/" + _icon("RT") + ": Zoom" in legend and _icon("DPad") + ": Pan" in legend
    assert _icon("LStickPress") + ": Recenter" in legend
    assert str(P.LegendText()).startswith("A: Set Stop")  # (the text form, as before)
    lines = [str(t) for t in P.BoxLines(True).values()]
    assert lines[0] == _icon("A") + ": Set Stop" and not any(": Map Menu" in t for t in lines)
    shown = P.box if P.box and P.box._shown else None
    if shown:  # (what the box shows: the icons)
        assert str(shown.shownLines[1]).startswith("|T")
    else:
        assert str(P.legend._text).startswith("|T")
    # a pair: two icons; a held control keeps its "(hold)"
    assert P.SetBind("clear", "PADLTRIGGER+PAD3") is True
    assert P.ActionIcon("clear") == _icon("LT") + "+" + _icon("X")
    assert P.SetHold("clear", True) is True
    assert P.ActionIcon("clear") == _icon("LT") + "+" + _icon("X") + " (hold)"
    assert not any("Clear Route" in str(t) for t in P.BoxLines(True).values())  # (off the box: asked 2026-11-16)
    # no icon: the text (a paddle; a button's icon gone; a file the client doesn't know yet, before a /reload)
    assert P.IconLabel("PADPADDLE1") == "Paddle 1"
    lua.execute("AGPS_NS.Pad.ICONS.PAD1 = nil")
    assert str(P.LegendText(True)).startswith("A: Set Stop")
    P.iconKnown[PAD_PATH + "X_14.tga"] = False
    assert P.ActionIcon("remove") == "X"
    # a pad with shapes: PlayStation's
    lua.execute("AGPS_PAD.style = 'Shapes'")
    assert P.ActionIcon("back") == _icon("Circle") and P.ActionIcon("zoomIn") == _icon("R2")


def test_the_icons_are_the_size_nearest_their_pixels_on_the_screen(pad):
    lua, ns = pad
    P = ns.Pad
    assert P.IconPx(14, 1) == 14  # (no screen size: a pixel a unit)
    lua.execute("GetPhysicalScreenSize = function() return 3840, 2160 end")
    assert P.IconPx(14, 1) == 40  # (4K: 14 units are 39 pixels)
    lua.execute("GetPhysicalScreenSize = function() return 1920, 1080 end")
    assert P.IconPx(14, 1) == 20 and P.IconPx(14, 0.64) == 12


def _labels(O):
    return {str(b.key): b for b in O.padDiagram.labels.values()}


def test_the_options_diagram_labels_each_button_with_its_controls_and_follows_a_rebind(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    O.Show()
    O.Refresh()
    d = O.padDiagram
    assert d is not None and d.tex._shown
    tex = str(d.tex._tex)
    assert tex == PAD_PATH + "Diagram_10.tga" and _file(tex).is_file()
    assert (d.tex._w, d.tex._h) == (P.DIAGRAM.w, P.DIAGRAM.h)  # (1:1: a pixel a unit here, the 1x one)
    lab = _labels(O)

    def icon_of(b):  # (the button's icon beside its text, pixel for pixel: 16 units at a pixel a unit, the 16 one)
        return str(b.icon._tex) if b.icon._shown else None

    H = "|cffffd100(H)|r"
    assert str(lab["PAD1"].text._text) == "Set Stop"  # (Yes on A too: one entry, as the box)
    assert icon_of(lab["PAD1"]) == PAD_PATH + "A_16.tga" and (lab["PAD1"].icon._w, lab["PAD1"].icon._h) == (16, 16)
    assert str(lab["PAD3"].text._text) == "Remove" and lab["PAD3"]._shown and icon_of(lab["PAD3"]).endswith("X_16.tga")
    assert str(lab["PADLTRIGGER"].text._text) == "Zoom out" and icon_of(lab["PADLTRIGGER"]).endswith("LT_16.tga")
    assert str(lab["PADDUP"].text._text) == "Pan up"
    # (nothing on it: listed greyed, a click gives it a control)
    assert lab["PADLSHOULDER"].empty and "Not bound" in str(lab["PADLSHOULDER"].text._text)
    # the labels fit beside the drawing, each at its line's row, left of it and right of it
    for b in lab.values():
        assert b._w <= (O.padDiagram._w - P.DIAGRAM.w) / 2 and b.text._wrap is False
    # Change: the button's label moves
    assert P.SetBind("remove", "PADRSHOULDER") is True
    O.Refresh()
    lab = _labels(O)
    assert str(lab["PADRSHOULDER"].text._text) == "Remove" and not lab["PADRSHOULDER"].empty
    assert lab["PAD3"].empty
    # Hold: after a yellow (H), past the pressed ones (asked 2026-11-16: "(A [the icon]) Set Stop : (H) Remove Stop")
    assert P.SetBind("clear", "PAD3") is True and P.SetHold("clear", True) is True
    O.Refresh()
    lab = _labels(O)
    assert str(lab["PAD3"].text._text) == H + " Clear Route"
    assert [str(t) for t in lab["PAD3"].tip.values()] == ["X (hold): Clear Route"]  # (in full in its tooltip)
    assert P.SetHold("remove", True) is True and P.SetBind("remove", "PAD1") is True
    O.Refresh()
    lab = _labels(O)
    assert str(lab["PAD1"].text._text) == "Set Stop : " + H + " Remove"
    assert [str(i) for i in lab["PAD1"].ids.values()] == ["select", "remove"]
    # (clicked: the button's own window)
    lab["PAD1"]._scripts.OnClick(lab["PAD1"])
    assert O.padButton._shown and O.padButton.key == "PAD1" and O.padButton.base.padGet() == "select"
    O.padButton.Hide(O.padButton)
    # a pair is listed at its button, its modifier's icon first
    assert P.SetBind("menu", "PADLTRIGGER+PAD4") is True
    O.Refresh()
    # (a pair: "+LT Map Menu", the other button first with a +, as big as the label's own icon looks; asked 2026-11-16)
    assert str(_labels(O)["PAD4"].text._text) == "+|T" + PAD_PATH + "LT_16.tga:16:16|t Map Menu"
    # Reset: back as it was
    assert P.ResetBinds() is True
    O.Refresh()
    lab = _labels(O)
    assert str(lab["PAD3"].text._text) == "Remove" and lab["PADRSHOULDER"].empty


def test_the_diagram_is_drawn_nearest_the_screens_pixels_and_fits_the_page(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    lua.execute("GetPhysicalScreenSize = function() return 2560, 1440 end")  # (1.875 pixels a unit)
    O.Show()
    O.Refresh()
    d = O.padDiagram
    assert str(d.tex._tex).endswith("Diagram_20.tga")
    k = 2 / (1440 / 768)
    assert d.tex._w == pytest.approx(P.DIAGRAM.w * k) and d.tex._h <= d._h  # (1:1 on the screen)
    assert d.tex._w <= d._w - 2 * O.PAD_LABEL_MIN


# ---------------------------------------------------------------- hints: a control's icon pulsing over what it acts on
def _hints(P):
    return [h for h in P.hints.values() if h._shown]


def _byid(P):
    return {str(h.id): h for h in _hints(P)}


def test_the_hints_pulse_the_buttons_icons_over_what_they_act_on(pad):
    """(asked 2026-11-16: "use the assigned button icon and overlay fade it where that control would "click" and it fades
    in and out in 1sec every 3sec. So controller opens map, currently "Y" button icon would fade over the map menu
    button ... When over other menu item it'd fade the A button")"""
    from test_controller import _frames, _press

    lua, ns = pad
    same = lua.eval("rawequal")
    G, P = ns.GPS, ns.Pad
    P.Apply()
    P.HintTick(0)
    hs = [h for h in _hints(P) if h.id == "menu"]  # (and A's over an icon under the crosshair, if one is)
    assert len(hs) == 1 and same(hs[0].target, G.mapButton) and same(hs[0]._parent, G.mapButton)
    assert str(hs[0].text._text) == "|T%sY_20.tga:20:20|t" % PAD_PATH  # (the menu control's button: Y)
    # its alpha: up and down in the first second of every three, clear the rest
    seen = []
    for _ in range(30):
        P.HintTick(0.1)
        seen.append(round(float(hs[0].alpha), 3))
    assert seen[4] == 1.0 and seen[0] == pytest.approx(0.2) and seen[8] == pytest.approx(0.2)
    assert all(a == 0 for a in seen[10:29]) and seen[29] == 0  # (1.0 s to 2.9 s: clear)
    P.HintTick(0.5)
    assert float(hs[0].alpha) == pytest.approx(1.0)  # (3.5 s: the next pulse at its top)
    # the menu open: the focused button gets the select control's icon (A); the menu's button still Y
    _press(lua, "PAD4")
    G.LayoutQuick()
    _frames(lua)
    P.Apply()
    P.HintTick(1)
    on = {str(h.id): h for h in _hints(P)}
    assert set(on) == {"menu", "select"}
    assert same(on["select"].target, P.focus) and str(on["select"].text._text) == "|T%sA_20.tga:20:20|t" % PAD_PATH
    first = P.focus
    # a group open (a submenu): B's icon over the button that opened it (asked 2026-11-16, "we should fade the button to
    # go back when in a map menu sub menu")
    lua.execute("AGPS_OGS = AGPS_NS.GPS.OpenGroupSlot AGPS_NS.GPS.OpenGroupSlot = function() return { button = AGPS_NS.Pad.focus, members = {} } end")
    P.HintTick(1)
    on = {str(h.id): h for h in _hints(P)}
    assert "back" in on and same(on["back"].target, first) and str(on["back"].text._text) == "|T%sB_20.tga:20:20|t" % PAD_PATH
    lua.execute("AGPS_NS.GPS.OpenGroupSlot = AGPS_OGS")
    P.HintTick(1)
    assert "back" not in {str(h.id) for h in _hints(P)}
    _press(lua, "PADDUP")
    P.HintTick(1)
    on = {str(h.id): h for h in _hints(P)}
    assert same(on["select"].target, P.focus) and not same(P.focus, first)  # (it moves with the focus)
    # a rebind: a pair shows both icons; a held control no "(hold)" (asked 2026-11-16: "don't show (hold) here")
    _press(lua, "PAD4")
    assert P.SetBind("menu", "PADLSHOULDER+PAD4") is True and P.SetHold("menu", True) is True
    P.HintTick(1)
    assert str(_byid(P)["menu"].text._text) == "|T%sLB_20.tga:20:20|t+|T%sY_20.tga:20:20|t" % (PAD_PATH, PAD_PATH)
    # the controller not in use (the mouse): none
    P.SawInput(False)
    P.HintTick(1)
    assert _hints(P) == []
    P.SawInput(True)
    P.HintTick(1)
    assert "menu" in _byid(P)
    # in combat: none (the marks hidden with the bindings)
    lua.execute("AGPS_LOCK = true")
    P.Apply()
    P.HintTick(1)
    assert _hints(P) == []
    lua.execute("AGPS_LOCK = false")


def test_a_question_and_the_crosshair_get_their_controls_hints(pad):
    lua, ns = pad
    same = lua.eval("rawequal")
    G, N, P = ns.GPS, ns.Pad and ns.Nav, ns.Pad
    P.Apply()
    G.Confirm("Keep this route?", lua.eval("function() end"), lua.eval("function() end"))
    P.HintTick(1)
    on = {str(h.id): h for h in _hints(P)}
    q = P.Question()
    assert set(on) == {"yes", "back"} and same(on["yes"].target, q.yes) and same(on["back"].target, q.no)
    assert str(on["back"].text._text) == "|T%sB_20.tga:20:20|t" % PAD_PATH
    q.Hide(q)
    # a stop under the crosshair: X's
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    N.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'Spot' } }" % (x + 300, y + 300)), False, "red")
    G.LookAt(0, x + 300, y + 300)
    for _ in range(3):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
    P.HintTick(1)
    on = {str(h.id): h for h in _hints(P)}
    assert "remove" in on and same(on["remove"].target, P.StopAt())
    assert str(on["remove"].text._text) == "|T%sX_20.tga:20:20|t" % PAD_PATH
