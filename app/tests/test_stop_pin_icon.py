"""A new stop's marker from the first redraw (Kooki3z, 2026-11-23, a video by Loch Modan's lake: "sometimes when marking a
stop its a cog wheel then the correct icon"). The map's stop pins are reused, and one last drawn as a ride's (a lift's
gear) and set by SetTexture for the new stop kept the gear as the icon's source: G.RoundIcon's G.ScaledIcon put the
gear's file drawn at its size back over the marker. Each pin's icon is set by ns.SetIcon now."""

import pytest

GEAR = "Interface\\Icons\\INV_Misc_Gear_01"


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def test_a_reused_pin_shows_the_new_stops_marker_on_the_first_redraw(game):
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))

    def pins():
        lua.execute("AGPS_T = (AGPS_T or 0) + 1")
        G.Redraw()
        G.Update()
        return [b for b in G.stopPins.values() if b._shown and b.stopIndex]

    # (the gear drawn at its size: a file of its own, as the shipped scaled icons are)
    lua.execute(f"""AGPS_OLD_SIF = AGPS_NS.GPS.ScaledIconFile
      AGPS_NS.GPS.ScaledIconFile = function(src, px, round)
        if src == {GEAR!r} then return "Interface\\\\AddOns\\\\AzerothGPS\\\\Media\\\\Icons\\\\gear_scaled", false end
        return AGPS_OLD_SIF(src, px, round)
      end""")
    try:
        N.SetStops(lua.eval(f"{{ {{ x = {x + 40}, y = {y + 40}, cont = 0, name = 'One' }} }}"), False, "red")
        (b,) = pins()
        # (the pin last drawn as a lift's: its gear, set as ns.SetIcon sets a ride's)
        ns.SetIcon(b.icon, GEAR)
        G.ScaledIcon(b, b.icon, False)
        N.SetStops(lua.eval(f"""{{ {{ x = {x + 40}, y = {y + 40}, cont = 0, name = 'One' }},
          {{ x = {x + 60}, y = {y + 30}, cont = 0, name = 'Two' }} }}"""), False, "red")
        shown = pins()
        assert len(shown) == 2
        for p in shown:
            d = N.stops[p.stopIndex]
            assert str(p.icon._tex) == str(N.StopIcon(d)), (p.stopIndex, p.icon._tex)
            assert str(p.icon.agpsSrc) == str(N.StopIcon(d))
            assert "Raid" in str(p.icon._tex)
    finally:
        lua.execute("AGPS_NS.GPS.ScaledIconFile = AGPS_OLD_SIF")
        N.Clear()
