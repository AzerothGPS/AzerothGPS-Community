"""The grid system always on (item 74, Kooki3z 2026-11-25: "it's much more reliable than the previous system"): no
option, no slash switch for players, and anyone who turned Cities or World off gets them back on at load."""

from azerothgps.gameharness import start


def test_a_profile_with_the_grids_off_gets_them_back_on():
    lua, ns = start(saved='AzerothGPSDB = { setup = { shown = 1, done = "1.3.14" }, settings = { gps = { cityGrid = false, '
                          'worldGrid = false, cityGridDefaultOn = true, worldGridDefaultOn = true } }, chars = {} }')
    st = ns.settings.gps
    assert st.cityGrid is True and st.worldGrid is True


def test_no_slash_switch_for_players():
    lua, ns = start()
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    for cmd in ("worldgrid off", "worldgrid", "citygrid off", "citygrid"):
        lua.globals().SlashCmdList.AZEROTHGPS(cmd)
    assert ns.WorldGrid.On() and ns.CityGrid.On()
