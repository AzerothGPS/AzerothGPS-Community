"""The game's place names in the client's language matched with the data's English ones (Data/PlaceNames/<locale>.lua,
`agps place-names`). Reported 2026-11-19 from a German client: in Gnomeregan's Train Depot, which the game says is
outdoors, the inside map went and Dun Morogh's terrain showed: the room was found by its name alone, and the minimap's
"Zugdepot" never matched the data's "Train Depot". The same comparison: Undercity's halls up top ("Ruinen von
Lordaeron", N.CityHere) and the hearthstone's inn (GetBindLocation, Teleports' T.Home). On an English client nothing
changes."""

import pytest

from azerothgps.place_names import build, lua_text

DEPOT = (-5059.0, 802.0)  # (Gnomeregan's Train Depot, outside the instance: Dun Morogh 20.3, 36.0, the report's)
GNOMEREGAN_WMO = 109593
LIONS_PRIDE = (0, -9464.3, 24.4)  # (Data/Pois.lua's ns.AreaSpots["Lion's Pride Inn"], Goldshire)


def _start(locale):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale=locale)
    ns.Nav.FUN = False
    ns.GPS.INTERIOR_MAX_ZOOM = 1e9  # (the inside map at the map's zoom: only which room is found is asked here)
    return lua, ns


@pytest.fixture(scope="module")
def german():
    return _start("deDE")


@pytest.fixture(scope="module")
def english():
    return _start("enUS")


def _laid(lua, ns, x, y, zone, map_id=1426):
    lua.execute(f"""
      AGPS_MAP = {map_id}; AGPS_POS = {{ {x}, {y}, 0 }}
      IsIndoors = function() return false end
      IsOutdoors = function() return true end
      GetMinimapZoneText = function() return "{zone}" end
      GetSubZoneText = GetMinimapZoneText
    """)
    for _ in range(4):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        ns.GPS.Update()
    return ns.GPS.laidTiles and ns.GPS.laidTiles.laidSig or ""


def test_the_train_depots_inside_map_on_a_german_client(german):
    lua, ns = german
    assert _laid(lua, ns, *DEPOT, "Zugdepot").startswith(f"in:{GNOMEREGAN_WMO}:")
    # (a name that's none of its rooms': the terrain, as before)
    assert not _laid(lua, ns, *DEPOT, "Eisklamm").startswith("in:")


def test_the_train_depot_on_an_english_client_as_before(english):
    lua, ns = english
    assert _laid(lua, ns, *DEPOT, "Train Depot").startswith(f"in:{GNOMEREGAN_WMO}:")
    assert not _laid(lua, ns, *DEPOT, "Zugdepot").startswith("in:")


def test_the_rooms_labels_in_the_clients_language(german, english):
    assert german[1].PlaceName("Train Depot") == "Zugdepot"
    assert english[1].PlaceName("Train Depot") == "Train Depot"


@pytest.mark.parametrize("sub,down", [("Ruinen von Lordaeron", False), ("Die Ruinen von Lordaeron", False),
                                      ("Unterstadt", True)])
def test_undercitys_halls_up_top_on_a_german_client(german, sub, down):
    lua, ns = german
    lua.execute(f'AGPS_MAP = 1458; GetSubZoneText = function() return "{sub}" end; GetMinimapZoneText = GetSubZoneText')
    here = ns.Nav.CityHere()
    assert (here == 10001) == down, (sub, here)


def test_the_hearthstones_inn_on_a_german_client(german):
    lua, ns = german
    lua.execute('GetBindLocation = function() return "Gasthaus Zur Höhle des Löwen" end')
    home = ns.Teleports.Home()
    assert home is not None and (home.cont, home.x, home.y) == LIONS_PRIDE


def test_the_names_by_the_tables_row_ids(tmp_path):
    src = tmp_path / "thirdparty" / "wago" / "1"
    src.mkdir(parents=True)
    rows = {"enUS": ["Train Depot", "Gnomeregan", "Other"], "deDE": ["Zugdepot", "Gnomeregan", "Anderes"]}
    for loc in ("enUS", "deDE", "esES", "esMX", "frFR", "koKR", "ptBR", "ruRU", "zhCN", "zhTW"):
        names = rows.get(loc, rows["enUS"])
        (src / f"WMOAreaTable_{loc}.csv").write_text(
            "AreaName_lang,ID\n" + "".join(f'"{n}",{i}\n' for i, n in enumerate(names, 1)), encoding="utf-8")
        (src / f"AreaTable_{loc}.csv").write_text("AreaName_lang,ID\n", encoding="utf-8")
    out, rep = build(tmp_path, "1", names={"Train Depot", "Gnomeregan", "Shaper's Terrace "})
    # (only the data's names, and only where they differ from the English)
    assert out["deDE"] == {"Train Depot": ["Zugdepot"]} and out["frFR"] == {}
    assert rep["not found"] == ["Shaper's Terrace "]
    assert "Train Depot|Zugdepot" in lua_text("deDE", out["deDE"])
