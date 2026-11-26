"""The hearthstone's landing is the bind's place (item 51b, Kooki3z 2026-11-24: "Use your Hearthstone (to Valley of
Trials)" and the route went on from Undercity). The spot recorded after a hearth had been read before the teleport (the
loading screen outlasting a fixed 4 s) and was kept under the new bind's name. Teleports.Home now takes a recorded spot
only near where the bind's name says (HOME_CHECK_YD), and the record waits until the player has moved."""

from test_map_redraw import game  # noqa: F401


def test_a_recorded_spot_elsewhere_than_the_binds_place_isnt_taken(game):  # noqa: F811
    lua, ns = game
    T = ns.Teleports
    cdb = ns.CharDB()
    lua.execute('AGPS_BL = GetBindLocation; GetBindLocation = function() return "Valley of Trials" end')
    try:
        named = T.Home()
        assert named and named.cont == 1  # (Durotar's: Kalimdor)
        # (a spot in Undercity recorded under the Valley of Trials' name: not taken, forgotten)
        cdb.bind = lua.eval('{ cont = 0, x = 1633.0, y = 240.0, name = "Valley of Trials" }')
        home = T.Home()
        assert home.cont == 1 and abs(home.x - named.x) < 1 and cdb.bind is None
        # (a spot near the Valley of Trials' inn recorded: kept, the exact one)
        cdb.bind = lua.eval(f'{{ cont = 1, x = {named.x + 40}, y = {named.y - 30}, name = "Valley of Trials" }}')
        home = T.Home()
        assert abs(home.x - (named.x + 40)) < 0.1 and cdb.bind is not None
    finally:
        lua.execute("GetBindLocation = AGPS_BL")
        cdb.bind = None
