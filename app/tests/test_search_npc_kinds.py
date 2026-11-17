"""The search's generic words for the NPCs talked to (asked 2026-11-14: "doesnt search already show closest
profession/class trainer/repair/vendor? if not add this"): a vendor's window open records that the NPC sells and
whether it repairs (Layers.NoteMerchant, CanMerchantRepair); "repair" and "vendor" (and their other words, and the
game's language's) list those NPCs nearest first, common ones too; "class trainer" and "mining trainer" find the
trainers talked to as well as the cities' places. These are the learned ones, the shipped NPCs
(Data/Npcs.lua, test_shipped_npcs.py) left out: nothing learned, nothing found."""

import pytest

pytest.importorskip("lupa.lua51")

BRILL = (2254.0, 293.0, 0)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.CharDB().faction = "Horde"
    return lua, ns


def _search(ns, text, max=30):
    res = ns.GPS.SearchPlaces(text, max)
    return [res[i] for i in range(1, len(res) + 1)]


def _npcs(ns, text):
    return [str(e.name) for e in _search(ns, text) if e.npc]


def _at(lua, x, y, cont=0):
    lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}")


def _merchant(lua, ns, npc_id, name, x, y, repairs):
    """The player at (x, y) opens NPC `npc_id`'s vendor window; `repairs`: CanMerchantRepair's answer (None: the
    client has no such function)."""
    _at(lua, x, y)
    can = "nil" if repairs is None else f"function() return {'1' if repairs else 'nil'} end"
    lua.execute(f"""
      AGPS_OLDM = AGPS_OLDM or {{ guid = UnitGUID, name = UnitName, can = CanMerchantRepair }}
      UnitGUID = function(u) if u == "npc" then return "Creature-0-1-2-3-{npc_id}-00000ABC" end return AGPS_OLDM.guid(u) end
      UnitName = function(u) if u == "npc" then return "{name}" end return AGPS_OLDM.name(u) end
      CanMerchantRepair = {can}
    """)
    try:
        ns.Layers.OnNpcWindow("MERCHANT_SHOW")
    finally:
        lua.execute("UnitGUID, UnitName, CanMerchantRepair = AGPS_OLDM.guid, AGPS_OLDM.name, AGPS_OLDM.can "
                    "AGPS_OLDM = nil")
        _at(lua, *BRILL)


@pytest.fixture
def npcs(game):
    lua, ns = game
    was, shipped = ns.db.npcs, ns.NpcsPacked
    ns.db.npcs = lua.eval("{}")
    ns.NpcsPacked = ""  # (the learned NPCs alone: the shipped ones are test_shipped_npcs.py's)
    yield lua, ns
    ns.db.npcs, ns.NpcsPacked = was, shipped
    ns.settings.gps.searchCommonNpcs = False
    _at(lua, *BRILL)


def test_nothing_learned_finds_no_npc_by_repair_or_vendor(npcs):
    lua, ns = npcs
    for text in ("repair", "vendor", "armorer", "merchants"):
        assert _npcs(ns, text) == []


def test_a_vendor_window_learns_the_vendor_and_whether_it_repairs(npcs):
    lua, ns = npcs
    _merchant(lua, ns, 6741, "Near Smith", 2300.0, 300.0, True)
    _merchant(lua, ns, 6742, "Far Smith", 2600.0, 300.0, True)
    _merchant(lua, ns, 6743, "Grocer", 2280.0, 290.0, False)
    _merchant(lua, ns, 6744, "Old Client Vendor", 2350.0, 290.0, None)
    db = ns.db.npcs
    assert db[6741].vendor and db[6741].repair is True
    assert db[6743].vendor and db[6743].repair is False
    assert db[6744].vendor and db[6744].repair is None  # (no CanMerchantRepair: unknown, no error)
    # "repair" and its other words: the repairing ones, nearest first; the grocer not
    for text in ("repair", "Repairs", "armorer", "repair vendor", "REPAIR"):
        assert _npcs(ns, text) == ["Near Smith", "Far Smith"], text
    # "vendor": every one, nearest first
    for text in ("vendor", "vendors", "merchant"):
        assert _npcs(ns, text) == ["Grocer", "Near Smith", "Old Client Vendor", "Far Smith"], text
    res = [e for e in _search(ns, "repair") if e.npc]
    assert res[0].yd < res[1].yd
    # learned again elsewhere (a repair learned once stays; a window that says no repair now says so)
    _merchant(lua, ns, 6743, "Grocer", 2280.0, 290.0, True)
    assert _npcs(ns, "repair") == ["Grocer", "Near Smith", "Far Smith"]


def test_an_older_record_is_a_vendor_by_its_windows_title(npcs):
    # (learned before 1.2.9: no `vendor`; its title the window's kind when it had none, L["Vendor"])
    lua, ns = npcs
    ns.db.npcs = lua.eval("""{
      [501] = { name = "Old Vendor", title = "Vendor", cont = 0, x = 2270, y = 300, faction = "Horde" },
      [502] = { name = "Old Innkeeper", title = "Innkeeper", cont = 0, x = 2260, y = 300, faction = "Horde" },
    }""")
    assert _npcs(ns, "vendor") == ["Old Vendor"]
    assert _npcs(ns, "repair") == []  # (whether it repairs: unknown until its window opens again)


def test_common_npcs_are_found_by_a_generic_word_with_the_option_off(npcs):
    # (a vendor in every town is "common": met far apart; left out of the search by name unless searchCommonNpcs is
    # on, as before, but found by "repair" and "vendor", at its spot nearest the player)
    lua, ns = npcs
    ns.db.npcs = lua.eval("""{
      [601] = { name = "Wandering Smith", title = "Armorer", cont = 0, x = -9460, y = 30, faction = "Horde",
                common = true, vendor = true, repair = true,
                spots = { { cont = 0, x = 2290, y = 295, place = "Brill" } } },
      [602] = { name = "Plain Smith", cont = 0, x = 2400, y = 300, faction = "Horde", vendor = true, repair = true },
    }""")
    ns.settings.gps.searchCommonNpcs = False
    assert _npcs(ns, "repair") == ["Wandering Smith", "Plain Smith"]
    assert _npcs(ns, "vendor") == ["Wandering Smith", "Plain Smith"]
    (e,) = [e for e in _search(ns, "repair") if str(e.name) == "Wandering Smith"]
    assert (e.x, e.y) == (2290, 295)  # (its spot nearest the player)
    assert _npcs(ns, "Wandering") == []  # (by its name or title: as before, only with the option)
    ns.settings.gps.searchCommonNpcs = True
    assert _npcs(ns, "Wandering") == ["Wandering Smith"]
    assert _npcs(ns, "repair") == ["Wandering Smith", "Plain Smith"]


def test_learned_trainers_are_found_by_the_generic_trainer_words_nearest_first(npcs):
    # (the cities' places were found by "class trainer"; a trainer talked to wasn't: its kind was only its title)
    lua, ns = npcs
    ns.db.npcs = lua.eval("""{
      [701] = { name = "Brill Mage", title = "Mage Trainer", cont = 0, x = 2260, y = 300, faction = "Horde" },
      [702] = { name = "Brill Miner", title = "Mining Trainer", cont = 0, x = 2262, y = 296, faction = "Horde" },
      [703] = { name = "Brill Rogue", title = "Rogue Trainer", cont = 0, x = 2258, y = 296, faction = "Horde" },
    }""")
    lua.execute("AGPS_OLDC = UnitClass UnitClass = function() return 'Mage', 'MAGE' end")
    try:
        for text in ("class trainer", "class trainers"):
            res = _search(ns, text)
            assert res and str(res[0].name) == "Brill Mage", (text, [str(e.name) for e in res])
            assert "Brill Rogue" not in [str(e.name) for e in res]  # (another class's)
            yds = [e.yd for e in res if e.yd is not None]
            assert yds == sorted(yds)
        res = _search(ns, "profession trainer")
        assert res and str(res[0].name) == "Brill Miner", [str(e.name) for e in res]
        # (a specific one: the places named so first, as before, then the NPCs of that title)
        assert "Brill Miner" in _npcs(ns, "mining trainer") and "Brill Mage" in _npcs(ns, "mage trainer")
    finally:
        lua.execute("UnitClass = AGPS_OLDC")


@pytest.mark.parametrize("code, words", [("deDE", ("Reparatur", "Händler")), ("frFR", ("réparation", "marchand")),
                                         ("ruRU", ("Ремонт", "торговец")), ("zhCN", ("修理", "商人"))])
def test_repair_and_vendor_in_the_games_language(code, words):
    from azerothgps.gameharness import start
    lua, ns = start(locale=code)
    ns.CharDB().faction = "Horde"
    ns.NpcsPacked = ""
    ns.db.npcs = lua.eval("""{
      [801] = { name = "Smith", cont = 0, x = 2300, y = 300, faction = "Horde", vendor = true, repair = true },
      [802] = { name = "Grocer", cont = 0, x = 2270, y = 300, faction = "Horde", vendor = true, repair = false },
    }""")
    repair, vendor = words
    assert _npcs(ns, repair) == ["Smith"]
    assert _npcs(ns, vendor) == ["Grocer", "Smith"]
    assert _npcs(ns, "repair") == ["Smith"]  # (the English as well)
