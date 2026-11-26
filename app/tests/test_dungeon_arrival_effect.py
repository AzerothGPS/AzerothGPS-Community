"""Arriving at a dungeon plays the arrival effect (item 44, Kooki3z 2026-11-24: no confetti at a dungeon). A stop at a
dungeon's way in is arrived at once the player is through it and inside (Nav.EnteredStopInstance), and the effect plays
then; when the map is hidden at that moment (the loading screen into the dungeon), it plays once it shows again
(Looks' LK.pending)."""

import pytest

from test_map_redraw import game  # noqa: F401

ORANGE = (-1468.2, 2614.2)  # (Maraudon's Orange way in, in Desolace)
INSIDE = (1016.8, -458.5)  # (and its end inside, on Maraudon's own level 20349)


@pytest.mark.parametrize("hidden", [False, True], ids=["map_shown", "map_hidden_then_shown"])
def test_through_a_dungeon_s_way_in_it_is_arrived_and_the_effect_plays_once(game, hidden):  # noqa: F811
    lua, ns = game
    N, LK, st = ns.Nav, ns.Looks, ns.settings.gps
    was = st.arrivalEffect
    st.arrivalEffect = "confetti"
    lua.execute("AGPS_PLAYS = 0; AGPS_PLAY0 = AGPS_PLAY0 or AGPS_NS.Looks.Play; "
                "AGPS_NS.Looks.Play = function(e) local ok = AGPS_HIDE ~= true and AGPS_PLAY0(e) or false; "
                "if ok then AGPS_PLAYS = AGPS_PLAYS + 1 end; return ok end")
    try:
        lua.execute("AGPS_LEVEL = 45")
        N.Clear()
        N.SetStops(lua.eval(f"{{ {{ x = {ORANGE[0]}, y = {ORANGE[1]}, cont = 1, name = 'Maraudon: Orange' }} }}"))
        assert N.EnteredStopInstance(N.stops[1], 20349) and not N.EnteredStopInstance(N.stops[1], 20036)
        lua.execute(f"AGPS_HIDE = {'true' if hidden else 'false'}")
        lua.execute(f"AGPS_POS = {{ {INSIDE[0]}, {INSIDE[1]}, 20349 }}")
        status = str(N.Status(INSIDE[0], INSIDE[1], 20349))
        assert "Arrived" in status and N.dest is None, status
        if hidden:
            assert lua.eval("AGPS_PLAYS") == 0 and LK.pending is not None
            lua.execute("AGPS_HIDE = false")
            LK.waiter._scripts.OnUpdate(LK.waiter, 0.5)  # (the map shown again)
        assert lua.eval("AGPS_PLAYS") == 1 and LK.pending is None
        N.Status(INSIDE[0], INSIDE[1], 20349)
        assert lua.eval("AGPS_PLAYS") == 1  # (once)
    finally:
        st.arrivalEffect = was
        lua.execute("AGPS_NS.Looks.Play = AGPS_PLAY0; AGPS_HIDE = nil; AGPS_LEVEL = nil; AGPS_POS = { 2254.0, 293.0, 0 }")
        N.Clear()
