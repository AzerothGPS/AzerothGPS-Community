"""The Quest Route button's menu of other ways with a controller (1.3.14; QuestWays.lua, Pad.lua; the whole addon,
gameharness).

Kooki3z 2026-11-22: "add controller support for quest route sub menu, just fade between the 2 buttons for activating and
opening the submenu in 1.3.14".

- The Quest Route button in the map menu's focus: its hint goes from Set Stop's button (A, which presses it) to
  Remove's (X, its right-click: the menu) and back, each Pad.SWAP_SECONDS, cross-fading; only while it has the focus.
- X opens the menu; the D-pad's up and down move a highlight over its entries (round at the ends), starting on the
  "(default)" one; A picks it (that way's route, the saved options untouched); B shuts it, the focus back on the button.

The quest log is test_quest_route_choices.py's stub; the pad test_controller.py's.
"""

import pytest

from test_controller import PAD_STUBS, _frames, _plain, _press
from test_quest_route_choices import _names, game, quests  # noqa: F401
from test_quest_route_menu import _saved, menu  # noqa: F401


@pytest.fixture
def padmenu(menu):
    lua, ns = menu
    G, P = ns.GPS, ns.Pad
    lua.execute(PAD_STUBS)
    ns.db.padOffered = True
    ns.settings.gps.padControl = True
    P.used = True
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert P.Apply()
    _press(lua, "PAD4")  # (the map menu)
    G.LayoutQuick()
    _frames(lua)
    assert P.MenuOpen()
    yield lua, ns
    G.CloseQuestWays()
    if P.MenuOpen():
        P.CloseMenu()
    lua.execute("AGPS_LOCK = false")
    P.Clear()


def _focus_qr(lua, ns):
    P, qr = ns.Pad, ns.GPS.questRouteButton
    same = lua.eval("rawequal")
    assert any(same(b, qr) for b in P.MenuButtons().values())  # (one of the map menu's buttons)
    P.SetFocus(qr)
    return qr


def _hints_on(lua, ns, frame):
    """{control id: alpha} of the hints shown over `frame`."""
    same = lua.eval("rawequal")
    return {str(h.id): h.alpha for h in ns.Pad.hints.values() if h._shown and same(h.target, frame)}


def _tick_hints(lua, P, dt):
    lua.execute("AGPS_NS.Pad.hintTargets = nil")  # (looked at again now)
    P.HintTick(dt)


def test_the_focused_quest_route_buttons_hint_fades_between_a_and_x(padmenu):
    lua, ns = padmenu
    P = ns.Pad
    qr = _focus_qr(lua, ns)
    assert _plain(P.HintText("select")) == "A" and _plain(P.HintText("remove")) == "X"
    P.hintT = 0
    _tick_hints(lua, P, 0.5)  # (A's turn)
    h = _hints_on(lua, ns, qr)
    assert set(h) == {"select", "remove"} and h["select"] == 1 and h["remove"] == 0
    _tick_hints(lua, P, 0.5)  # (the change: half each)
    h = _hints_on(lua, ns, qr)
    assert abs(h["select"] - 0.5) < 1e-9 and abs(h["remove"] - 0.5) < 1e-9
    _tick_hints(lua, P, 0.5)  # (X's turn)
    h = _hints_on(lua, ns, qr)
    assert h["select"] == 0 and h["remove"] == 1
    _tick_hints(lua, P, 1.0)  # (A's again: steady between the changes, not the 1-in-3-seconds pulse)
    h = _hints_on(lua, ns, qr)
    assert h["select"] == 1 and h["remove"] == 0
    # both icons at the button's middle, over each other
    same = lua.eval("rawequal")
    for hint in P.hints.values():
        if hint._shown and same(hint.target, qr):
            assert hint._pts.CENTER[3] == "CENTER"
    # the focus moved on: the plain pulse of A over the next button, nothing over Quest Route
    other = next(b for b in P.MenuButtons().values() if not same(b, qr))
    P.SetFocus(other)
    _tick_hints(lua, P, 0.1)
    assert _hints_on(lua, ns, qr) == {}
    assert set(_hints_on(lua, ns, other)) == {"select"}
    # the controller put down (the mouse used): no hints at all
    P.SetFocus(qr)
    P.SawInput(False)
    _tick_hints(lua, P, 0.1)
    assert _hints_on(lua, ns, qr) == {}


def test_the_swap_follows_the_players_buttons(padmenu):
    lua, ns = padmenu
    P = ns.Pad
    qr = _focus_qr(lua, ns)
    try:
        assert P.Assign("remove", "PADRSHOULDER+PAD3", False) is True
        P.Apply()
        _focus_qr(lua, ns)
        assert "RB" in _plain(P.HintText("remove"))
        _tick_hints(lua, P, 0.1)
        assert set(_hints_on(lua, ns, qr)) == {"select", "remove"}
        # Remove on no button: A's hint alone, the usual pulse
        P.Unbind("remove")
        P.hintT = 0
        _tick_hints(lua, P, 0.25)
        assert set(_hints_on(lua, ns, qr)) == {"select"}
    finally:
        P.ResetBinds()


def test_x_opens_the_menu_and_the_d_pad_moves_its_highlight_from_the_default(padmenu):
    lua, ns = padmenu
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    st.questLevelOrder = "gray"  # (the default entry: About to turn gray first, the third)
    qr = _focus_qr(lua, ns)
    _press(lua, "PAD3")
    assert G.QuestWaysOpen() and len(ns.Nav.stops) == 0
    m = G.questWays
    same = lua.eval("rawequal")
    assert m.at == 3 and str(G.QuestWaysSelRow().id) == "gray"
    assert m.sel._shown and same(m.sel.row, m.rows[3])  # (the highlight over it)
    # the hints now: A's over the highlighted entry, B's over the button it goes back to
    _tick_hints(lua, P, 0.1)
    assert set(_hints_on(lua, ns, m.rows[3])) == {"select"} and set(_hints_on(lua, ns, qr)) == {"back"}
    # down and up, round at the ends (8 entries: the seven ways and Quest Route options...)
    _press(lua, "PADDDOWN")
    assert str(G.QuestWaysSelRow().id) == "turnins" and same(m.sel.row, m.rows[4])
    _press(lua, "PADDUP")
    _press(lua, "PADDUP")
    _press(lua, "PADDUP")
    assert str(G.QuestWaysSelRow().id) == "fastest"
    _press(lua, "PADDUP")
    assert str(G.QuestWaysSelRow().id) == "options"
    _press(lua, "PADDDOWN")
    assert str(G.QuestWaysSelRow().id) == "fastest"
    # left and right: nothing (the map menu's focus stays on the button, the menu open)
    _press(lua, "PADDRIGHT")
    assert G.QuestWaysOpen() and same(P.focus, qr) and str(G.QuestWaysSelRow().id) == "fastest"
    # the view never panned meanwhile
    assert len(ns.Nav.stops) == 0


def test_with_the_saved_options_the_highlight_starts_on_the_first(padmenu):
    lua, ns = padmenu
    G, st = ns.GPS, ns.settings.gps
    st.questLevelOrder, st.questTrackedOnly = "off", True  # (default: Tracked quests only, the sixth)
    _focus_qr(lua, ns)
    _press(lua, "PAD3")
    assert str(G.QuestWaysSelRow().id) == "tracked"
    _press(lua, "PAD2")
    st.questTrackedOnly = False  # (Fastest order the default: the first)
    _press(lua, "PAD3")
    assert str(G.QuestWaysSelRow().id) == "fastest"


def test_a_picks_the_highlighted_way_and_leaves_the_options_alone(padmenu):
    lua, ns = padmenu
    G, P, N, st = ns.GPS, ns.Pad, ns.Nav, ns.settings.gps
    was = _saved(st)
    qr = _focus_qr(lua, ns)
    _press(lua, "PAD3")
    _press(lua, "PADDDOWN")
    _press(lua, "PADDDOWN")
    _press(lua, "PADDDOWN")
    assert str(G.QuestWaysSelRow().id) == "turnins"
    _press(lua, "PAD1")
    assert not G.QuestWaysOpen()
    assert _names(ns) == ["Turn in: Letter"] and str(N.questWay.id) == "turnins"
    assert _saved(st) == was
    same = lua.eval("rawequal")
    if P.MenuOpen():  # (the map menu still open: the focus back on the button)
        assert same(P.focus, qr)


def test_b_shuts_the_menu_and_the_focus_is_back_on_the_button(padmenu):
    lua, ns = padmenu
    G, P = ns.GPS, ns.Pad
    same = lua.eval("rawequal")
    qr = _focus_qr(lua, ns)
    _press(lua, "PAD3")
    _press(lua, "PADDDOWN")
    _press(lua, "PAD2")
    assert not G.QuestWaysOpen() and P.MenuOpen() and same(P.focus, qr) and len(ns.Nav.stops) == 0
    # X again shuts it too (as a second right-click)
    _press(lua, "PAD3")
    assert G.QuestWaysOpen()
    _press(lua, "PAD3")
    assert not G.QuestWaysOpen() and P.MenuOpen() and same(P.focus, qr)
    # the map menu's button: both shut
    _press(lua, "PAD3")
    _press(lua, "PAD4")
    assert not G.QuestWaysOpen() and not P.MenuOpen()


def test_x_on_another_button_does_nothing(padmenu):
    lua, ns = padmenu
    G, P = ns.GPS, ns.Pad
    same = lua.eval("rawequal")
    qr = G.questRouteButton
    other = next(b for b in P.MenuButtons().values() if not same(b, qr) and not b.agpsRightClick)
    P.SetFocus(other)
    _press(lua, "PAD3")
    assert not G.QuestWaysOpen() and P.MenuOpen() and same(P.focus, other)


def test_the_mouse_sees_no_highlight(padmenu):
    lua, ns = padmenu
    G, P = ns.GPS, ns.Pad
    P.SawInput(False)  # (the mouse used)
    qr = G.questRouteButton
    qr._scripts.OnClick(qr, "RightButton")
    m = G.questWays
    assert G.QuestWaysOpen() and not m.sel._shown
    # the controller picked up again: the highlight shows on the frame's next update
    _press(lua, "PADDDOWN")
    P.SawInput(True)
    m._scripts.OnUpdate(m, 0.05)
    assert m.sel._shown
    # left-click: the saved route, as ever
    qr._scripts.OnClick(qr, "LeftButton")
    assert not G.QuestWaysOpen() and len(_names(ns)) == 4 and ns.Nav.questWay is None
