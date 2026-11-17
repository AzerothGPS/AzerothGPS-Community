"""A building in a city in the open (Stormwind's: one model with its streets) shows its inside map with the player in it,
as the mouse over it does. Reported 2026-11-15 in Stormwind's Trade District (65.0, 65.6): the terrain showed, the
hover the building's map. WoW Forever says outdoors in those halls (IsIndoors false, as in Ironforge's), and only
indoors were an open city's rooms taken."""

import pytest


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def _spot(ns, map_id, u, v):
    b = ns.Maps[map_id].bounds
    return b[3] - v / 100 * (b[3] - b[1]), b[4] - u / 100 * (b[4] - b[2])


def _shown(lua, ns, x, y):
    G = ns.GPS
    ns.Nav.Clear()
    lua.execute(f"AGPS_MAP = 1453; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0; IsIndoors = function() return false end")
    G.Follow()
    for _ in range(3):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    lt = G.laidTiles
    return G.shownInside, str(lt.laidSig) if lt and lt.laidSig else ""


def test_standing_in_a_stormwind_building_shows_its_inside_map(game):
    lua, ns = game
    x, y = _spot(ns, 1453, 65.0, 65.6)  # (in the Trade District, the user's screenshot)
    hover = ns.GPS.InteriorUnder(x, y, 0)
    assert hover[0] is not None, "no building under the spot to hover"
    inside, sig = _shown(lua, ns, x, y)
    assert inside == hover[0][1], "standing in the building, its inside map didn't show"
    assert sig.startswith("in:")


def test_out_in_stormwinds_streets_the_terrain_still_shows(game):
    lua, ns = game
    # (a spot of the Trade District's streets near the building: none of the city's rooms over it)
    x, y = next(_spot(ns, 1453, 65.0 + du, 65.6 + dv) for du in range(-8, 9) for dv in range(-8, 9)
                if ns.GPS.InteriorUnder(*_spot(ns, 1453, 65.0 + du, 65.6 + dv), 0)[0] is None)
    inside, sig = _shown(lua, ns, x, y)
    assert inside is None and not sig.startswith("in:")
