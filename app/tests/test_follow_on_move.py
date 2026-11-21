"""Follow me again when I move (Kooki3z 2026-11-20: "add an option to auto follow on when you start moving again in
Map > Following and zooming. This just does the same as Back to Your Position"): GPSFrame's G.AutoFollowCheck."""

import pytest

X0, Y0 = 2254.0, 293.0  # (Brill, the harness's start)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def at(lua, x, y):
    lua.execute(f"AGPS_POS = {{ {x}, {y}, 0 }}")


def test_moving_after_looking_around_follows_again_only_with_the_option(game):
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    try:
        at(lua, X0, Y0)
        # off (the default): the view stays where it was looked at
        st.followOnMove = False
        G.LookAt(0, X0 + 300, Y0, 200)
        G.Update()
        at(lua, X0 + 10, Y0)
        G.Update()
        assert G.IsFree()
        # on: standing still keeps the view; a few yards of walking follows again
        st.followOnMove = True
        G.LookAt(0, X0 + 300, Y0, 200)
        G.Update()
        at(lua, X0 + 11, Y0)
        G.Update()
        assert G.IsFree()  # (moved 1 yd: not yet)
        at(lua, X0 + 16, Y0)
        G.Update()
        assert not G.IsFree()
        # a stop placed and waiting to be confirmed: not followed (Follow would drop it)
        G.LookAt(0, X0 + 300, Y0, 200)
        G.Update()
        assert G.AddStopAt(X0 + 300, Y0, "a stop")
        at(lua, X0 + 40, Y0)
        G.Update()
        assert G.IsFree()
    finally:
        st.followOnMove = False
        ns.Nav.Clear()
        G.Follow()
        at(lua, X0, Y0)
