"""Names in the game's language on every client (a German player, 1.3.6: "Geradeaus weiter, dann in 20 m nach
Menethil Harbor, Wetlands fliegen"; a French player asked the same for cities and places).

The shipped data's names are the client's English ones. Each is looked up in the game by its id (ns.TaxiName,
ns.ZoneName, ns.AreaName, ns.RideEndName, ns.ItemName, ns.NpcName in Core.lua), the English only the fallback, and
the search finds both. On an English client nothing changes."""

import pytest

pytest.importorskip("lupa.lua51")

SENTINEL_HILL, MENETHIL = 4, 7
MENETHIL_AREA, BRILL_AREA = 150, 159  # (Data/Pois.lua's place labels' AreaTable ids)
WETLANDS, TIRISFAL, STORMWIND = 1437, 1420, 1453  # (uiMaps)

NAMES = {
    "deDE": {
        "taxi": {SENTINEL_HILL: "Späherkuppe, Westfall", MENETHIL: "Hafen von Menethil, Sumpfland", 2: "Sturmwind, Elwynn",
                 6: "Eisenschmiede, Dun Morogh"},
        "maps": {WETLANDS: "Sumpfland", TIRISFAL: "Tirisfal", STORMWIND: "Sturmwind"},
        "areas": {MENETHIL_AREA: "Hafen von Menethil", BRILL_AREA: "Brill"},
    },
    "frFR": {
        "taxi": {SENTINEL_HILL: "Colline des sentinelles, Marche de l'Ouest", MENETHIL: "Port de Menethil, Les Paluns",
                 2: "Hurlevent, Elwynn", 6: "Forgefer, Dun Morogh"},
        "maps": {WETLANDS: "Les Paluns", TIRISFAL: "Clairières de Tirisfal", STORMWIND: "Hurlevent"},
        "areas": {MENETHIL_AREA: "Port de Menethil", BRILL_AREA: "Brill"},
    },
}


def _lua_map(d):
    return "{ " + ", ".join(f'[{k}] = "{v}"' for k, v in d.items()) + " }"


def _start(locale):
    from azerothgps.gameharness import start
    lua, ns = start(locale=locale)
    ns.Nav.FUN = False
    n = NAMES.get(locale) or NAMES["deDE"]
    # (the game's own names: the flight masters on the continents' maps, the uiMaps' and areas' names)
    lua.execute(f"""
      AGPS_TAXI_NAMES = {_lua_map(n["taxi"])}
      AGPS_MAP_NAMES = {_lua_map(n["maps"])}
      AGPS_AREA_NAMES = {_lua_map(n["areas"])}
      C_TaxiMap.GetTaxiNodesForMap = function(mapID)
        if mapID ~= 1415 then return {{}} end
        local out = {{}}
        for node, name in pairs(AGPS_TAXI_NAMES) do out[#out + 1] = {{ nodeID = node, name = name }} end
        return out
      end
      local info = C_Map.GetMapInfo
      C_Map.GetMapInfo = function(id)
        local i = info(id)
        if i and AGPS_MAP_NAMES[id] then i.name = AGPS_MAP_NAMES[id] end
        return i
      end
      C_Map.GetAreaInfo = function(id) return AGPS_AREA_NAMES[id] end
      if AGPS_NS.names then AGPS_NS.names.zone, AGPS_NS.names.area = {{}}, {{}} end
    """)
    ns.Taxi.Refresh("test")
    return lua, ns


@pytest.fixture(scope="module", params=["deDE", "frFR"])
def game(request):
    lua, ns = _start(request.param)
    return request.param, lua, ns


def _plan_flight(lua, ns):
    N, G = ns.Nav, ns.GPS
    cdb = ns.CharDB()
    cdb.faction = "Alliance"
    for e in cdb.taxiNodes[1415].nodes.values():
        e.known = True
    N.FlightsChanged()
    lua.execute("AGPS_MAP = 1436; AGPS_POS = { -10628.9, 1036.7, 0 }")  # (at Sentinel Hill's flight master)
    N.SetStops(lua.eval("{ { x = -3792.3, y = -783.3, cont = 0 } }"), False, "red")  # (Menethil's)
    for _ in range(30):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    return str(N.StepsText(99))


def _search(ns, text, max=30):
    res = ns.GPS.SearchPlaces(text, max)
    return [res[i] for i in range(1, len(res) + 1)]


def test_the_flight_is_to_the_flight_masters_name_in_the_games_language(game):
    locale, lua, ns = game
    steps = _plan_flight(lua, ns)
    assert NAMES[locale]["taxi"][MENETHIL] in steps, steps
    assert "Menethil Harbor" not in steps, steps


def test_a_flight_recorded_under_the_games_names_is_matched_on_its_route(game):
    # (Taxi.lua records flights as "from > to" by the game's names, in its language; the flight being flown is named
    # so too: the data's English names never matched them, and on a non-English client a flight's landing was unknown)
    locale, lua, ns = game
    a, b = NAMES[locale]["taxi"][SENTINEL_HILL], NAMES[locale]["taxi"][MENETHIL]
    ns.CharDB().flights = lua.eval(f'{{ ["{a} > {b}"] = {{ from = "{a}", to = "{b}", seconds = 777, samples = 1 }} }}')
    ns.Nav.FlightsChanged()
    lua.execute("AGPS_POS = { -10628.9, 1036.7, 0 }")
    f = lua.eval(f'{{ from = "{a}", to = "{b}", start = AGPS_T or 1000 }}')
    r = ns.Nav.FlyingRoute(-10628.9, 1036.7, 0, 7, False, f)
    assert r is not None, "the landing wasn't found by the game's name"
    assert r.flying.seconds > 700, r.flying.seconds  # (the recorded 777 s, not the estimate)
    ns.CharDB().flights = lua.eval("{}")


def test_the_search_finds_the_flight_master_by_either_name_shown_in_the_games_language(game):
    locale, lua, ns = game
    shown = NAMES[locale]["taxi"][MENETHIL]
    for typed in (shown.split(",")[0].lower(), "menethil harbor, wet"):
        hits = [str(e.name) for e in _search(ns, typed) if str(e.sub) == str(ns.L["Flight master"])]
        assert shown in hits, (typed, hits)


def test_zones_and_cities_in_the_games_language_found_by_either(game):
    locale, lua, ns = game
    city = NAMES[locale]["maps"][STORMWIND]
    for typed in (city.lower(), "stormwind city"):
        hits = [str(e.name) for e in _search(ns, typed)]
        assert city in hits, (typed, hits)
    assert ns.ZoneName(WETLANDS, "Wetlands") == NAMES[locale]["maps"][WETLANDS]
    # (the zone's name over the map, its levels still read by the English: "Sumpfland / Stufe 20-30")
    text, levels = ns.GPS.ZoneHoverText(WETLANDS, "Wetlands", 20)[:2]
    assert text == NAMES[locale]["maps"][WETLANDS], text
    assert levels and "20-30" in levels, levels


def test_place_labels_on_the_map_by_their_area(game):
    locale, lua, ns = game
    pois = ns.GPS.LayoutPois(-3716.7, -783.3, 0, 0, 300, 200, lua.eval("{ [3] = true }"), None)
    names = [str(pois[i][4]) for i in range(1, len(pois) + 1)]
    assert NAMES[locale]["areas"][MENETHIL_AREA] in names, names
    assert "Menethil Harbor" not in names or NAMES[locale]["areas"][MENETHIL_AREA] == "Menethil Harbor", names


def test_a_docks_name_by_its_town_and_zone(game):
    locale, lua, ns = game
    row = next(t for t in ns.Transports.values()
               if t[9] == "Menethil Harbor, Wetlands" and t[10] == "Theramore Isle, Dustwallow Marsh")
    n = NAMES[locale]
    assert ns.RideEndName(row, 1) == f"{n['areas'][MENETHIL_AREA]}, {n['maps'][WETLANDS]}"
    # (Theramore's names not given by this mock: the English, never half of each)
    assert ns.RideEndName(row, 2) == "Theramore Isle, Dustwallow Marsh"


def test_vendor_items_by_the_games_name_and_the_english(game):
    locale, lua, ns = game
    lua.execute('AGPS_OLD_ITEM = GetItemInfo; GetItemInfo = function(id) if id == 2512 then return "Raue Pfeile" end end')
    try:
        ns.GPS.vendorIndex = None
        for typed in ("raue pfeile", "rough arrow"):
            words = lua.eval("{" + ", ".join(f'"{w}"' for w in typed.split()) + "}")
            sold = ns.GPS.VendorItemsTyped(typed, words)
            assert sold is not None, typed
            assert "Raue Pfeile" in list(sold.values()), (typed, list(sold.values()))
    finally:
        lua.execute("GetItemInfo = AGPS_OLD_ITEM")
        ns.GPS.vendorIndex = None
        ns.names.item = lua.eval("{}")


def test_npc_names_seen_in_game_are_shown_and_both_found(game):
    locale, lua, ns = game
    lua.execute("""
      AGPS_OLDU = { guid = UnitGUID, name = UnitName }
      UnitGUID = function(u) if u == "target" then return "Creature-0-1-2-3-2118-00000ABC" end return AGPS_OLDU.guid(u) end
      UnitName = function(u) if u == "target" then return "Abigail Schild" end return AGPS_OLDU.name(u) end
    """)
    try:
        ns.LearnNpcName("target")
    finally:
        lua.execute("UnitGUID, UnitName = AGPS_OLDU.guid, AGPS_OLDU.name")
    ns.CharDB().faction = "Horde"
    lua.execute("AGPS_MAP = 1420; AGPS_POS = { 2254.0, 293.0, 0 }")
    for typed in ("abigail schild", "abigail shiel"):
        hits = [str(e.name) for e in _search(ns, typed) if e.npc]
        assert "Abigail Schild" in hits, (typed, hits)


def test_an_english_client_keeps_the_datas_names():
    lua, ns = _start("enUS")
    assert not ns.GameLocalized()
    assert ns.ZoneName(WETLANDS, "Wetlands") == "Wetlands"
    assert ns.TaxiName(MENETHIL, "Menethil Harbor, Wetlands") == "Menethil Harbor, Wetlands"
    steps = _plan_flight(lua, ns)
    assert "Menethil Harbor, Wetlands" in steps, steps
