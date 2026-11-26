"""The arrow and the directions text each on or off on its own (Kooki3z 2026-11-24: "the directions text on screen but
not the direction arrow"; turning the arrow off took the text away too). `arrowShown` the arrow's panel, `dirShown`
the text's, any combination; `arrow` (the window) either of them. Saved settings carried over once (`arrowSplit`) so
nobody's look changes: the window off is both off; Arrow side "Hide" (the old way to hide the arrow alone) is the
arrow off."""

import pytest


def _start(saved=None):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    return start(saved=saved)


def _texts(lua):
    return [str(w._text) for w in lua.eval("AGPS_WIDGETS").values()
            if w._text and w._shown and w._parent is not None and w._parent._name == "AzerothGPSDirections"]


def test_the_text_alone_shows_and_follows_the_route_and_both_off_show_neither():
    lua, ns = _start()
    st, A, N, G = ns.settings.gps, ns.Arrow, ns.Nav, ns.GPS
    arrow, dirs = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections
    N.SetStops(lua.eval("{ { x = 2000.0, y = 300.0, cont = 0, name = 'there' } }"), False, "red")
    st.arrow, st.arrowShown, st.dirShown = True, False, True  # (the text alone)
    A.Apply()
    for _ in range(3):
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        arrow._scripts.OnUpdate(arrow, 1)
    assert dirs._shown and A.Hidden()  # (the text shown; the arrow's panel hidden, its place at alpha 0)
    first = _texts(lua)
    assert any("there" in t or "yd" in t for t in first), first
    # (its steps go on: the player moved, the text with them)
    lua.execute("AGPS_POS[1], AGPS_POS[2] = AGPS_POS[1] + 40, AGPS_POS[2] + 40; AGPS_T = AGPS_T + 2")
    G.Update()
    arrow._scripts.OnUpdate(arrow, 1)
    assert _texts(lua) != first
    st.arrow, st.arrowShown, st.dirShown = False, False, False  # (both off)
    A.Apply()
    assert not arrow._shown and not dirs._shown


@pytest.mark.parametrize("saved, arrow_on, text_on, side", [
    ("AzerothGPSDB = { settings = { gps = { arrow = false } } }", False, False, "left"),
    ("AzerothGPSDB = { settings = { gps = { arrow = true, arrowSide = 'hide' } } }", False, True, "left"),
    ("AzerothGPSDB = { settings = { gps = { arrow = true, dirShown = false } } }", True, False, "left"),
    ("AzerothGPSDB = { settings = { gps = { arrow = true, arrowSide = 'right' } } }", True, True, "right"),
])
def test_saved_settings_carry_over_with_the_same_look(saved, arrow_on, text_on, side):
    lua, ns = _start(saved=saved)
    st = ns.db.settings.gps
    assert (st.arrowShown is not False, st.dirShown is not False, st.arrowSide) == (arrow_on, text_on, side)
    assert st.arrow == (arrow_on or text_on) and st.arrowSplit
