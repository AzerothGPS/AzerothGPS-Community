"""The Quest Route button's menu of other ways with a controller (1.3.14; QuestWays.lua, Pad.lua; the whole addon,
gameharness).

Kooki3z 2026-11-22: "add controller support for quest route sub menu, just fade between the 2 buttons for activating and
opening the submenu in 1.3.14".

- The Quest Route button in the map menu's focus: its hint goes from Set Stop's button (A, which presses it) to
  Remove's (X, its right-click: the menu) and back, each Pad.SWAP_SECONDS, cross-fading; only while it has the focus.
- X opens the menu; the D-pad's up and down move a highlight over its entries (round at the ends), starting on the
  first; A toggles the highlighted one (saved, as a click does) and the menu stays open; B shuts it, the focus back on
  the button.

The quest log is test_quest_route_choices.py's stub; the pad test_controller.py's.
"""

import pytest

from test_controller import PAD_STUBS, _frames, _plain, _press
from test_quest_route_choices import _names, game, quests  # noqa: F401
from test_quest_route_menu import menu  # noqa: F401


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


def test_x_opens_the_menu_and_the_d_pad_moves_its_highlight_from_the_first(padmenu):
    lua, ns = padmenu
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    st.questLevelOrder = "gray"  # (whatever is on: the highlight starts on the first)
    qr = _focus_qr(lua, ns)
    _press(lua, "PAD3")
    assert G.QuestWaysOpen() and len(ns.Nav.stops) == 0
    m = G.questWays
    same = lua.eval("rawequal")
    assert m.at == 1 and str(G.QuestWaysSelRow().id) == "fastest"
    assert m.sel._shown and same(m.sel.row, m.rows[1])  # (the highlight over it)
    # the hints now: A's over the highlighted entry, B's over the button it goes back to
    _tick_hints(lua, P, 0.1)
    assert set(_hints_on(lua, ns, m.rows[1])) == {"select"} and set(_hints_on(lua, ns, qr)) == {"back"}
    # down and up, round at the ends (8 entries: the seven toggles and Quest Route options...)
    _press(lua, "PADDDOWN")
    _press(lua, "PADDDOWN")
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


def test_a_toggles_the_highlighted_entry_and_the_menu_stays_open(padmenu):
    lua, ns = padmenu
    G, P, N, st = ns.GPS, ns.Pad, ns.Nav, ns.settings.gps
    same = lua.eval("rawequal")
    qr = _focus_qr(lua, ns)
    _press(lua, "PAD3")
    for _ in range(5):
        _press(lua, "PADDDOWN")
    assert str(G.QuestWaysSelRow().id) == "tracked"
    _press(lua, "PAD1")
    m = G.questWays
    assert G.QuestWaysOpen() and st.questTrackedOnly is True and m.rows[6].check._shown
    assert str(G.QuestWaysSelRow().id) == "tracked" and same(P.focus, qr) and P.MenuOpen()
    # another of its group: the first one off, shown at once
    _press(lua, "PADDUP")
    _press(lua, "PADDUP")
    assert str(G.QuestWaysSelRow().id) == "turnins"
    _press(lua, "PAD1")
    assert st.questTurninsOnly is True and st.questTrackedOnly is False and not m.rows[6].check._shown
    assert len(N.stops) == 0  # (no quest route: only saved)
    # on a quest route: A remakes it at once, the menu still open
    _press(lua, "PAD2")
    G.QuestRoute()
    assert _names(ns) == ["Turn in: Letter"]
    _focus_qr(lua, ns)
    _press(lua, "PAD3")
    for _ in range(3):
        _press(lua, "PADDDOWN")
    _press(lua, "PAD1")  # (Turn-ins only off: every quest again)
    assert G.QuestWaysOpen() and st.questTurninsOnly is False and len(_names(ns)) == 4
    # B: shut, the focus back on the button
    _press(lua, "PAD2")
    assert not G.QuestWaysOpen() and same(P.focus, qr)


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
    assert not G.QuestWaysOpen() and len(_names(ns)) == 4
