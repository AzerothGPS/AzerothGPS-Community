"""Inside maps on a client in another language (AzerothGPS#426, reported 2026-11-15 from a German client, 1.3.0).

In Ironforge's Mystic Ward the map showed the mountain's terrain over the city. With no height (WoW Forever's z is 0)
and the game saying outdoors there, a room counted only when the minimap's zone text named it; the rooms' names are the
client's English ones ("The Mystic Ward") and the zone text is the player's language ("Die Große Schmiede"), so none
did. The city the game's map says the player is in (map 1455) is the same in every language."""

import pytest

SPOTS = [  # (world, the room there)
    ("Mystic Ward", -4653.0, -943.0, "Der Mystische Bezirk"),  # (29.0 / 15.9 on map 1455, the report's)
    ("Great Forge", -4890.0, -950.0, "Die Große Schmiede"),
]


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def _laid(lua, ns, x, y, zone, map_id):
    G = ns.GPS
    lua.execute(f"""
      AGPS_MAP = {map_id}; AGPS_POS = {{ {x}, {y}, 0 }}
      IsIndoors = function() return false end
      IsOutdoors = function() return true end
      GetMinimapZoneText = function() return "{zone}" end
      GetSubZoneText = GetMinimapZoneText
    """)
    for _ in range(4):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    return G.laidTiles and G.laidTiles.laidSig or ""


@pytest.mark.parametrize("name,x,y,zone", SPOTS)
def test_ironforges_inside_map_on_a_german_client(game, name, x, y, zone):
    lua, ns = game
    sig = _laid(lua, ns, x, y, zone, 1455)
    assert sig.startswith("in:7801267:"), f"{name}: {sig} (the mountain's terrain, not the city)"
    for line in ns.GPS.DebugInterior().values():
        if line.startswith("result:"):
            assert "wmo 7801267" in line, line


def test_out_of_the_city_by_the_games_map_the_terrain_as_before(game):
    lua, ns = game
    # (the same spot with the game's map Dun Morogh's and no room named: not taken for the city's)
    sig = _laid(lua, ns, -4653.0, -943.0, "Dun Morogh", 1426)
    assert not sig.startswith("in:"), sig
