"""Names in the game's language on every client (a German player, 1.3.6: "Geradeaus weiter, dann in 20 m nach
Menethil Harbor, Wetlands fliegen"; a French player asked the same for cities and places).

The shipped data's names are the client's English ones. Each is looked up in the game by its id (ns.TaxiName,
ns.ZoneName, ns.AreaName, ns.RideEndName, ns.ItemName, ns.NpcName in Core.lua), the English only the fallback, and
the search finds both. Dungeons and raids by their map id (ns.InstanceName: GetRealZoneText), the shipped NPCs
never met by their translations (Data/NpcNames, AzerothCore's). On an English client nothing changes."""

import pytest

pytest.importorskip("lupa.lua51")

SENTINEL_HILL, MENETHIL = 4, 7
MENETHIL_AREA, BRILL_AREA = 150, 159  # (Data/Pois.lua's place labels' AreaTable ids)
WETLANDS, TIRISFAL, STORMWIND = 1437, 1420, 1453  # (uiMaps)
WESTFALL, SM_LIBRARY = 1436, 303  # (uiMaps: a zone, the Scarlet Monastery's Library floor)
DEADMINES, SM = 36, 189  # (instance map ids: Data/Instances.lua's levels 20036, 20189)
BROG = 151  # (Brog Hamfist, General Supplies in Goldshire: shipped, never met in these tests)

NAMES = {
    "deDE": {
        "taxi": {SENTINEL_HILL: "Späherkuppe, Westfall", MENETHIL: "Hafen von Menethil, Sumpfland", 2: "Sturmwind, Elwynn",
                 6: "Eisenschmiede, Dun Morogh"},
        "maps": {WETLANDS: "Sumpfland", TIRISFAL: "Tirisfal", STORMWIND: "Sturmwind"},
        "areas": {MENETHIL_AREA: "Hafen von Menethil", BRILL_AREA: "Brill"},
        "instances": {DEADMINES: "Die Todesminen", SM: "Scharlachrotes Kloster"},
        "floors": {SM_LIBRARY: "Bibliothek"},
        "brog": ("Brog Grobschlacht", "Gemischtwaren"),  # (Data/NpcNames/deDE.lua's, AzerothCore's)
    },
    "frFR": {
        "taxi": {SENTINEL_HILL: "Colline des sentinelles, Marche de l'Ouest", MENETHIL: "Port de Menethil, Les Paluns",
                 2: "Hurlevent, Elwynn", 6: "Forgefer, Dun Morogh"},
        "maps": {WETLANDS: "Les Paluns", TIRISFAL: "Clairières de Tirisfal", STORMWIND: "Hurlevent"},
        "areas": {MENETHIL_AREA: "Port de Menethil", BRILL_AREA: "Brill"},
        "instances": {DEADMINES: "Les Mortemines", SM: "Monastère Écarlate"},
        "floors": {SM_LIBRARY: "Bibliothèque", WESTFALL: "Marche de l'Ouest"},
        "brog": ("Brog Lacouenne", "Fournitures générales"),
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
      AGPS_INSTANCE_NAMES = {_lua_map(n.get("instances", {}))}
      for id, name in pairs({_lua_map(n.get("floors", {}))}) do AGPS_MAP_NAMES[id] = name end
      -- (GetRealZoneText(mapID): an instance map's name, Map.db's, in the client's language; "" for none)
      GetRealZoneText = function(id) return AGPS_INSTANCE_NAMES[id] or "" end
      C_TaxiMap.GetTaxiNodesForMap = function(mapID)
        if mapID ~= 1415 then return {{}} end
        local out = {{}}
        for node, name in pairs(AGPS_TAXI_NAMES) do out[#out + 1] = {{ nodeID = node, name = name }} end
        return out
      end
      local info = C_Map.GetMapInfo
      C_Map.GetMapInfo = function(id)
        local i = info(id)
        if AGPS_MAP_NAMES[id] then i = i or {{ mapID = id }}; i.name = AGPS_MAP_NAMES[id] end
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


# Dungeons and raids (Data/Instances.lua): by their map id, GetRealZoneText; a wing by its dungeon map floor's uiMap.
def test_dungeon_entrances_on_the_map_in_the_games_language(game):
    locale, lua, ns = game
    n = NAMES[locale]
    names = [str(e.name) for e in ns.GPS.InstanceEntrances(0).values() if e.level in (20036, 20189)]
    assert n["instances"][DEADMINES] in names, names
    assert f'{n["instances"][SM]}: {n["floors"][SM_LIBRARY]}' in names, names  # (a wing's: by its floor's uiMap)
    assert f'{n["instances"][SM]}: Graveyard' in names, names  # (a floor the game didn't name: the English)
    assert "Deadmines" not in names, names
    # (its map's title and the info line: the dungeon's name)
    assert ns.InstanceName(20036) == n["instances"][DEADMINES]


def test_the_search_finds_a_dungeon_by_either_name_shown_in_the_games_language(game):
    locale, lua, ns = game
    shown = NAMES[locale]["instances"][DEADMINES]
    for typed in (shown.split()[-1].lower(), "deadmines"):
        hits = [str(e.name) for e in _search(ns, typed) if str(e.sub) == str(ns.L["Instance entrance"])]
        assert hits == [shown], (typed, hits)


def test_directions_to_a_dungeon_name_it_in_the_games_language(game):
    locale, lua, ns = game
    n = NAMES[locale]
    N, G = ns.Nav, ns.GPS
    ns.CharDB().faction = "Alliance"
    lua.execute("AGPS_MAP = 1436; AGPS_POS = { -10628.9, 1036.7, 0 }")  # (Sentinel Hill)
    N.SetStops(lua.eval("{ { x = -14.6, y = -385.5, cont = 20036 } }"), False, "red")  # (inside the Deadmines)
    for _ in range(40):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    steps = str(N.StepsText(99))
    assert n["instances"][DEADMINES] in steps, steps
    assert "Deadmines" not in steps, steps
    # (the walk ends at the portal, named by the dungeon: the walk inside is its map's once in)
    assert f'({n["instances"][DEADMINES]})' in steps, steps
    # (the portal's other end, the zone: by its uiMap, found by its English name; the way out says it)
    portal = next(ns.Transports[i] for i in range(1, len(ns.Transports) + 1) if ns.Transports[i][4] == 20036)
    assert str(ns.RideEndName(portal, 1)) == n["floors"].get(WESTFALL, "Westfall")
    N.SetStops(lua.eval("{}"), False, True)


# The shipped NPCs in the client's language (Data/NpcNames/<locale>.lua, AzerothCore's): found and shown before
# they're met, by either name.
def test_a_never_met_npc_is_found_by_its_name_in_the_games_language_and_the_english(game):
    locale, lua, ns = game
    name, title = NAMES[locale]["brog"]
    learned = ns.db.npcNames and ns.db.npcNames[locale]
    assert not (learned and learned[BROG])  # (never met)
    ns.CharDB().faction = "Alliance"
    lua.execute("AGPS_MAP = 1429; AGPS_POS = { -9460.0, 30.0, 0 }")  # (Goldshire)
    for typed in (name.lower(), "brog hamfist"):
        hits = [e for e in _search(ns, typed) if e.npc and e.id == BROG]
        assert hits and str(hits[0].name) == name, (typed, [str(e.name) for e in _search(ns, typed)])
        assert str(hits[0].sub).startswith(title or "General Supplies"), str(hits[0].sub)
    # (picked: the stop and the directions say its name)
    e = [e for e in _search(ns, "brog hamfist") if e.npc and e.id == BROG][0]
    N = ns.Nav
    N.SetStops(lua.eval("{}"), False, True)
    lua.execute("AGPS_POS = { -9300.0, 120.0, 0 }")  # (up the road from Goldshire)
    N.AddStop(lua.table(x=e.x, y=e.y, cont=e.cont, name=e.name, z=e.z), False, True)
    for _ in range(30):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        ns.GPS.Update()
    st = N.Steps()  # (one step, the walk to it: StepsText lists two or more)
    steps = " ".join(str(st[i]) for i in range(1, len(st) + 1))
    assert name in steps, steps
    N.SetStops(lua.eval("{}"), False, True)


def test_a_name_learned_in_game_overrides_the_shipped_one(game):
    locale, lua, ns = game
    lua.execute(f"""
      AGPS_OLDU = {{ guid = UnitGUID, name = UnitName }}
      UnitGUID = function(u) if u == "target" then return "Creature-0-1-2-3-{BROG}-00000ABC" end return AGPS_OLDU.guid(u) end
      UnitName = function(u) if u == "target" then return "Brog im Spiel" end return AGPS_OLDU.name(u) end
    """)
    try:
        ns.LearnNpcName("target")
        assert ns.NpcName(BROG, "Brog Hamfist") == "Brog im Spiel"
    finally:
        lua.execute("UnitGUID, UnitName = AGPS_OLDU.guid, AGPS_OLDU.name")
        ns.db.npcNames[locale][BROG] = None
    assert ns.NpcName(BROG, "Brog Hamfist") == NAMES[locale]["brog"][0]


def test_only_the_clients_own_npc_names_are_loaded(game):
    locale, lua, ns = game
    assert ns.NpcNamesLocale == locale
    other = "frFR" if locale == "deDE" else "deDE"
    assert ns.ShippedNpcNames()[0][BROG] == NAMES[locale]["brog"][0] != NAMES[other]["brog"][0]


def test_npc_name_files_are_small_and_credit_azerothcore():
    from azerothgps.gameharness import toc_files
    from azerothgps.npc_names import LOCALES, OUT_DIR
    files = sorted(OUT_DIR.glob("*.lua"))
    assert [f.stem for f in files] == sorted(LOCALES)
    toc = [t.replace(chr(92), "/") for t in toc_files()]
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert f.stat().st_size < 160 * 1024, f
        assert "AzerothCore" in text and "GPL-2" in text, f
        assert f'GetLocale() == "{f.stem}"' in text.splitlines()[6], f  # (another client returns at once)
        assert any(t.endswith(f"Data/NpcNames/{f.name}") for t in toc), f


def test_an_italian_client_has_no_shipped_npc_names_and_keeps_the_english():
    lua, ns = _start("itIT")
    assert ns.GameLocalized()
    assert ns.NpcNamesLoc is None
    assert ns.NpcName(BROG, "Brog Hamfist") == "Brog Hamfist"


def test_an_english_client_keeps_the_dungeons_and_npcs_english_names():
    lua, ns = _start("enUS")
    assert ns.InstanceName(20036) == "Deadmines"
    assert ns.InstanceName(20189, "Library") == "Scarlet Monastery: Library"
    assert ns.NpcName(BROG, "Brog Hamfist") == "Brog Hamfist"
    names = [str(e.name) for e in ns.GPS.InstanceEntrances(0).values() if e.level == 20036]
    assert names == ["Deadmines"], names


def test_the_generator_reads_the_dump_and_keeps_only_what_differs(tmp_path):
    from azerothgps import npc_names as M
    src = tmp_path / "thirdparty" / "azerothcore"
    src.mkdir(parents=True)
    (src / "creature_template.sql").write_text(
        "INSERT INTO `creature_template` VALUES\n"
        "(7,0,0,0,0,0,'Smith','Armorer',NULL,0),\n(8,0,0,0,0,0,'Not The Same',NULL,NULL,0);\n", encoding="utf-8")
    (src / "creature_template_locale.sql").write_text(
        "INSERT INTO `creature_template_locale` VALUES\n"
        "(7,'deDE','Schmied','Rüstungsschmied',1),\n(7,'frFR','Smith','Fabricant d\\'armures',1),\n"
        "(8,'deDE','Anders',NULL,1),\n(9,'deDE','Nicht geliefert',NULL,1);\n", encoding="utf-8")
    npcs = tmp_path / "Npcs.lua"
    npcs.write_text("ns.NpcsPacked = [==[\n7|Smith|Armorer|vr||A|0 1 2 3\n8|Other|||q||A|0 1 2 3\n]==]\n",
                    encoding="utf-8")
    names, rep = M.build(tmp_path, npcs)
    assert names["deDE"] == {7: ("Schmied", "Rüstungsschmied")}  # (8: another English name there; 9: not shipped)
    assert names["frFR"] == {7: (None, "Fabricant d'armures")}  # (the name the same: only the title)
    text = M.lua_text("frFR", names["frFR"])
    assert '"Fabricant d\'armures",' in text and "\n7||1\n" in text


def test_way_lines_take_the_zone_in_the_games_language(game):
    # (a German player, 2026-11-19: "/way Silberwald 63.4 64.3 Leylinienfokus" from a German guide was "unknown zone";
    # TomTom takes the client's names, and the search here finds both)
    locale, lua, ns = game
    parse = lua.eval("function(line) return { AGPS_NS.MapText.ParseWay(line) } end")  # (its nil and why, as a list)
    shown = NAMES[locale]["maps"][WETLANDS]
    for line in (f"/way {shown} 50 60 Here", f"/way {shown.lower()} 50 60 Here", f"/way {shown[:5]} 50 60 Here",
                 "/way Wetlands 50 60 Here"):
        r = parse(line)
        wp, why = r[1], r[2]
        assert wp is not None and wp.mapID == WETLANDS and (wp.x, wp.y, wp.name) == (50, 60, "Here"), (line, why)
    r = parse("/way Nirgendwo 50 60")
    wp, why = r[1], r[2]
    assert wp is None and "Nirgendwo" in str(why)
