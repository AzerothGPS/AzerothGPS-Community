"""Hovering a big cave or cavern shows its inside map (reported 2026-11-15: "This is about the only thing that shows
mousing over blackrock": Blackrock Mountain's model, 1,053 yd across, was left out as city-sized, with every model 300 yd
and over). Ironforge too ("allow ironforge to show from zoom in"), its NPCs not dotted (the whole city's map)."""

import pytest

BLACKROCK_MOUNTAIN = 7952336


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def _spot(ns, map_id, u, v):
    b = ns.Maps[map_id].bounds
    return b[3] - v / 100 * (b[3] - b[1]), b[4] - u / 100 * (b[4] - b[2])


def test_hovering_blackrock_mountain_shows_its_inside_map(game):
    lua, ns = game
    G = ns.GPS
    for x, y in ((-7527.0, -1226.0), _spot(ns, 1428, 31.8, 26.9)):  # (its middle; the user's screenshot's spot)
        hit = G.InteriorUnder(x, y, 0)
        assert hit[0] is not None and hit[0][1] == BLACKROCK_MOUNTAIN, (x, y)
        assert not G.WholeCityPlace(hit[0], 0)  # (its NPCs dotted, as a building's)


def test_hovering_ironforge_shows_its_map_without_npc_dots(game):
    lua, ns = game
    G = ns.GPS
    hit = G.InteriorUnder(-4840.0, -1100.0, 0)  # (the Great Forge)
    assert hit[0] is not None and hit[0][1] == 7801267
    assert G.WholeCityPlace(hit[0], 0)


@pytest.mark.parametrize("city, x, y, mapid, px, py, model", [
    ("Undercity", 1586.0, 239.0, 1420, 2250.0, 250.0, 7675285),
    ("Ironforge", -4840.0, -1000.0, 1426, -5600.0, -500.0, 7801267),
])
def test_zoomed_in_over_a_city_youre_not_in_its_whole_map_shows(game, city, x, y, mapid, px, py, model):
    # (asked 2026-11-15: "should the whole city map also come up for a city you're not in as soon as you zoom in over
    # it, without hovering? yes")
    lua, ns = game
    G = ns.GPS
    lua.execute(f"""
      AGPS_REAL_SEAMLESS = AGPS_REAL_SEAMLESS or AGPS_NS.GPS.Seamless
      AGPS_NS.GPS.Seamless = function() return true end
      AGPS_MAP = {mapid}; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {px}, {py}, 0
    """)
    try:
        G.Follow()
        shown = {}
        for zoom in (2000, 450):
            G.LookAt(0, x, y, zoom)
            lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
            G.Update()
            shown[zoom] = G.zoomedInside
        assert shown[2000] is None, f"{city}'s map zoomed out at the zone's view"
        assert shown[450] == model, f"{city}'s map didn't show zoomed in over it"
        assert str(G.laidTiles.laidSig).startswith(f"in:{model}:")
    finally:
        lua.execute("AGPS_NS.GPS.Seamless = AGPS_REAL_SEAMLESS")
        G.Follow()
