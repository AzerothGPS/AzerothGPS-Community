"""Stand-in NPCs from Wowhead's WoW Forever pages (Kooki3z, 2026-11-25: WoW Forever's own content our data lacks,
Riverglades first, filled from Wowhead as stand-in data, to be replaced by in-game recordings). They ship in
Data/Npcs.lua like any other NPC (searchable: Search Places, Quick Find, NPC stops), each listed in
`ns.NpcsStandIn` and kept in overrides/standin_npcs.json marked `"source": "wowhead-standin"`, `"verified": false`
(standin.py, `agps standin-npcs`); real data (the dump, the server snapshot, an NPC logged in game) wins by id."""
import json
import re

import pytest

from azerothgps import standin
from azerothgps.npcspots import NPCS_LUA, parse_lua
from azerothgps.npcs import lua_text

HARLAN = 257595  # (Barracks Master Harlan <Innkeeper>, Farholde Keep: Wowhead 64.6, 84.0)
BRAKKIT = 257292  # (Brakkit <Banker>, Powderfuse Port)
RIVERGLADES = (-9700.0, -6741.67, -6466.67, -1891.67)  # (Maps.lua's [2548])


def _standin_ids(text):
    m = re.search(r'^ns\.NpcsStandIn = "([\d ]*)"$', text, re.M)
    return {int(i) for i in m.group(1).split()} if m else set()


def test_the_stand_ins_ship_flagged_and_match_their_overrides():
    text = NPCS_LUA.read_text(encoding="utf-8")
    ids = _standin_ids(text)
    assert {HARLAN, BRAKKIT} <= ids
    _, npcs = parse_lua(text)
    doc = json.loads(standin.FILE.read_text(encoding="utf-8"))
    for i in ids:
        n, o = npcs[i], doc["npcs"][str(i)]
        assert n["from"] == "standin" and n["name"] == o["name"]
        assert o["source"] == "wowhead-standin" and o["verified"] is False and o["url"].endswith(f"npc={i}")
    # every stand-in in the overrides ships, unless real data has that NPC or it's a camp NPC players put down
    # (npcs.camp_npc: Pexmit, "Someone's Minion")
    from azerothgps.npcs import camp_npc
    camp = {int(i) for i, o in doc["npcs"].items() if camp_npc(int(i), o["name"], o.get("sub", ""))}
    assert 266901 in camp and not camp & ids
    assert set(map(int, doc["npcs"])) - ids - camp <= {i for i, n in npcs.items() if n.get("from") != "standin"}
    # the file reads back to itself (`agps standin-npcs --write` and `agps npc-spots --write` keep the flag)
    assert lua_text(npcs) == text
    h = npcs[HARLAN]
    assert h["sub"] == "Innkeeper" and "i" in h["svc"] and "v" in h["svc"] and h["side"] == "A"
    lv, x, y, z = h["spawns"][0]
    assert lv == 0 and RIVERGLADES[0] <= x <= RIVERGLADES[2] and RIVERGLADES[1] <= y <= RIVERGLADES[3] and z > 0


def test_the_scrape_converts_by_the_maps_bounds_and_the_tags():
    maps = {2548: (0, RIVERGLADES)}

    class Flat(standin.Heights):
        def at(self, cont, x, y):
            return 12.0, "terrain"

    def row(i, name, tag, react, coords=((50.0, 50.0),), quests=False, tabs=()):
        return {"id": i, "name": name, "tag": tag, "react": react, "hasQuests": quests, "tabs": list(tabs),
                "zone": "Riverglades", "uiMap": 2548,
                "map": {"16591": [{"coords": [list(c) for c in coords], "uiMapId": 2548}]}}

    got = standin.from_scrape([
        row(1, "Inn", "Innkeeper", [0, None], coords=((0, 0), (100, 100))),
        row(2, "Smith", "Weaponsmith & Armorcrafter", [None, 1]),
        row(3, "Teacher", "Journeyman Blacksmith", [0, 0], quests=True),
        row(4, "Bandit", "", [-1, -1], quests=True),
        row(5, "Townsfolk", "", [1, 1]),
        row(6, "Flyer", "Gryphon Master", [1, -1]), row(10, "Bluebell", "Flight Mistress", [0, 0]),
        row(11, "Jarael", "Leatherworking", [0, 0]),
        row(7, "Elsewhere", "Banker", [0, 0], coords=()),
    ], maps, Flat(), log=lambda *_: None)
    assert set(got) == {1, 2, 3, 6, 10, 11} and got[10]["svc"] == "gf"
    assert got[11]["svc"] == "gt" and got[11]["trainer"] == "Leatherworking"
    # x% runs west to east (Y falls), y% north to south (X falls): 0,0 the map's north-west corner
    s0, s1 = got[1]["spawns"]
    assert (s0["x"], s0["y"]) == (-6466.7, -1891.7) and (s1["x"], s1["y"]) == (-9700.0, -6741.7)
    assert got[1]["svc"] == "gvi" and got[1]["side"] == "A" and s0["z"] == 12.0 and s0["pct"] == [0.0, 0.0]
    assert got[2]["svc"] == "gvr" and got[2]["side"] == "H"
    assert got[3]["svc"] == "gqt" and got[3]["trainer"] == "Blacksmithing" and got[3]["side"] == "B"
    assert got[6]["svc"] == "gf" and got[6]["side"] == "A"
    assert all(n["source"] == "wowhead-standin" and n["verified"] is False for n in got.values())
    # a wanderer's spots one spawn per group; a tag offering nothing (a companion) left out; another zone's spots too
    assert standin.clusters([[10, 10], [11, 10.5], [12, 11], [40, 40]]) == [(11.0, 10.5), (40.0, 40.0)]
    more = standin.from_scrape([
        row(8, "Pet", "Scoutmaster's Companion", [1, -1]),
        dict(row(9, "Chicken", "", [0, 0], quests=True), map={
            "12": [{"coords": [[50, 50]], "uiMapId": 1429}], "16591": [{"coords": [[20, 20]], "uiMapId": 2548}]}),
    ], {**maps, 1429: (0, (-10000.0, -1000.0, -9000.0, 0.0))}, Flat(), log=lambda *_: None)
    assert set(more) == {9} and [s["pct"] for s in more[9]["spawns"]] == [[20.0, 20.0]]
    # real data wins by id; a stand-in already in is written again
    npcs = {2: {"name": "Smith", "sub": "", "svc": "v", "trainer": "", "side": "H", "spawns": [(0, 1.0, 1.0, 1.0)]}}
    added = standin.add_standin(npcs, {"npcs": {str(k): v for k, v in got.items()}})
    assert added == [1, 3, 6, 10, 11] and "from" not in npcs[2] and npcs[1]["from"] == "standin"
    assert standin.add_standin(npcs, {"npcs": {str(k): v for k, v in got.items()}}) == [1, 3, 6, 10, 11]


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


@pytest.fixture
def farholde(game):
    lua, ns = game
    was_npcs, was_pins = ns.db.npcs, ns.db.pins
    ns.db.npcs, ns.db.pins = lua.eval("{}"), lua.eval("{}")
    cdb = ns.CharDB()
    was_fac = cdb.faction
    cdb.faction = "Alliance"
    lua.execute("""
      AGPS_SI = { pos = AGPS_POS, map = AGPS_MAP }
      AGPS_MAP = 2548
      AGPS_POS = { -9170.0, -5010.0, 0 }
    """)
    yield lua, ns
    lua.execute("AGPS_POS, AGPS_MAP = AGPS_SI.pos, AGPS_SI.map")
    ns.db.npcs, ns.db.pins = was_npcs, was_pins
    cdb.faction = was_fac


def test_riverglades_innkeeper_vendor_and_banker_are_found(farholde):
    lua, ns = farholde
    G = ns.GPS
    _, by_id, _ = ns.Layers.ShippedNpcs()
    assert by_id[HARLAN].standin is True and by_id[BRAKKIT].standin is True
    assert by_id[54].standin is None  # (Corina Steele: the dump's)
    inn = G.QuickFindNearest("innkeeper")
    assert inn and str(inn.name) == "Barracks Master Harlan" and inn.yd < 100
    vendor = G.QuickFindNearest("vendor")  # (Farholde's: Harlan, Martha Wellsworth, Cassandra Wheeler...)
    standins = {str(by_id[i].name) for i in _standin_ids(NPCS_LUA.read_text(encoding="utf-8"))}
    assert vendor and vendor.yd < 100 and str(vendor.name) in standins
    res = G.SearchPlaces("Brakkit", 5)
    assert res[1] and str(res[1].name) == "Brakkit"
    res = G.SearchPlaces("Barracks Master", 5)
    assert res[1] and str(res[1].name) == "Barracks Master Harlan" and res[1].cont == 0
