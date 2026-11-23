"""Zephras Isle's NPCs in the search and Quick Find (a player's report for 1.3.14: in Valanaar, at about 65, 79, the
"nearest" vendor, class trainer or innkeeper routed off the island instead of to the NPCs right there, e.g. the mage
trainer Anathamaas Aetherwind at about 65.9, 80.6). The isle (level 2991, WoW Forever's own) isn't in the 1.12 dump
the shipped NPCs came from, so none of its NPCs were known before talking to them, and Quick Find took the first
mainland one when none was on the player's continent. Now: the isle's NPCs ship (npcs.py's ISLE_FILE, `agps npcs`),
the nearest of a kind is the one on the player's own land, and with none there Quick Find says so instead of routing
off it."""
from collections import defaultdict

import pytest

from azerothgps.paths import ADDON_DIR

NPCS = ADDON_DIR / "Data" / "Npcs.lua"
VALANAAR = (2026.7, 615.6, 2991)  # (Zephras Isle 65, 79: map 2521's bounds)
ANATHAMAAS = 252373  # (Mage Trainer, Valanaar: 65.9, 80.6)


def test_the_isles_npcs_are_shipped():
    text = NPCS.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if "|2991 " in ln or ";2991 " in ln]
    assert len(lines) > 80
    (mage,) = [ln for ln in lines if ln.startswith(f"{ANATHAMAAS}|")]
    assert mage.startswith(f"{ANATHAMAAS}|Anathamaas Aetherwind|Mage Trainer|") and "|MAGE|B|2991 1974.8 571.1" in mage
    inns = [ln for ln in lines if "|Innkeeper|" in ln]
    assert len(inns) == 2 and all("i" in ln.split("|")[3] for ln in inns)


def test_the_generator_reads_the_isles_rows_by_the_same_rules():
    from azerothgps.npcs import ISLE, _add_isle, isle_rows, isle_services, isle_trainer_kind

    rows = isle_rows()
    assert any(r["name"] == "Anathamaas Aetherwind" for r in rows) and all(int(r["map"]) == ISLE for r in rows)
    assert isle_services(65536 | 128 | 1) == "gvi" and isle_services(4096 | 128) == "vr"
    assert isle_trainer_kind(19, "Mage Trainer") == "MAGE" and isle_trainer_kind(145, "Miner") == "Mining"
    assert isle_trainer_kind(2, "Mage Trainer") == ""  # (no trainer flag: not a trainer)
    alliance = {"Faction": 1, "FactionGroup": 3, "FriendGroup": 2, "EnemyGroup": 12, "Enemies": [0], "Friend": [0]}
    horde = {"Faction": 2, "FactionGroup": 5, "FriendGroup": 4, "EnemyGroup": 10, "Enemies": [0], "Friend": [0]}
    ft = {35: {"Faction": 35, "FactionGroup": 0, "FriendGroup": 0, "EnemyGroup": 0, "Enemies": [0], "Friend": [1, 2]},
          14: {"Faction": 14, "FactionGroup": 8, "FriendGroup": 0, "EnemyGroup": 1, "Enemies": [0], "Friend": [0]}}

    def row(i, name, sub, flags, faction=35, x=2000.0, extra=0, mv=0):
        return {"guid": str(i), "id": str(i), "map": "2991", "x": str(x), "y": "600", "z": "650", "movement": str(mv),
                "name": name, "subname": sub, "faction": str(faction), "npcflag": str(flags), "type": "7",
                "unit_flags": "0", "flags_extra": str(extra)}

    npcs = {6491: {"name": "Spirit Healer", "sub": "", "svc": "gh", "trainer": "", "side": "B",
                   "spawns": [(0, 1.0, 1.0, 1.0)]}}
    report = defaultdict(int)
    _add_isle(npcs, report, ft, alliance, horde, rows=[
        row(1, "Inna", "Innkeeper", 65665), row(2, "Mage", "Mage Trainer", 19),
        row(3, "Hostile", "", 2, faction=14), row(4, "Guard", "", 1, extra=0x8000),
        row(6491, "Spirit Healer", "", 16385), row(2, "Mage", "Mage Trainer", 19, x=2000.4)])
    assert npcs[1]["svc"] == "gvi" and npcs[2]["trainer"] == "MAGE" and npcs[2]["side"] == "B"
    assert 3 not in npcs and 4 not in npcs and report["guard"] == 1
    assert npcs[6491]["spawns"] == [(0, 1.0, 1.0, 1.0), (2991, 2000.0, 600.0, 650.0)]  # (the isle's spawn too)
    assert npcs[2]["spawns"] == [(2991, 2000.0, 600.0, 650.0)] and report["same spot"] == 1


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


@pytest.fixture
def isle(game):
    lua, ns = game
    was_npcs, was_pins = ns.db.npcs, ns.db.pins
    ns.db.npcs, ns.db.pins = lua.eval("{}"), lua.eval("{}")
    cdb = ns.CharDB()
    was_fac = cdb.faction
    cdb.faction = "Alliance"
    lua.execute(f"""
      AGPS_ZI = {{ pos = AGPS_POS, map = AGPS_MAP, class = UnitClass, packed = AGPS_NS.NpcsPacked, print = AGPS_NS.Print }}
      AGPS_MAP = 2521
      AGPS_POS = {{ {VALANAAR[0]}, {VALANAAR[1]}, {VALANAAR[2]} }}
      UnitClass = function() return "Mage", "MAGE" end
      AGPS_SAID = {{}}
      AGPS_NS.Print = function(t) AGPS_SAID[#AGPS_SAID + 1] = t end
    """)
    yield lua, ns
    lua.execute("""
      AGPS_POS, AGPS_MAP, UnitClass = AGPS_ZI.pos, AGPS_ZI.map, AGPS_ZI.class
      AGPS_NS.NpcsPacked, AGPS_NS.Print = AGPS_ZI.packed, AGPS_ZI.print
    """)
    ns.db.npcs, ns.db.pins = was_npcs, was_pins
    cdb.faction = was_fac


def _said(lua):
    t = lua.eval("AGPS_SAID")
    return [str(t[i]) for i in range(1, len(t) + 1)]


def test_on_the_isle_the_nearest_of_each_kind_is_the_isles(isle):
    lua, ns = isle
    G = ns.GPS
    for kind in ("vendor", "repair", "innkeeper", "class trainer"):
        e = G.QuickFindNearest(kind)
        assert e and e.cont == 2991 and e.yd is not None and e.yd < 400, kind
    assert str(G.QuickFindNearest("class trainer").name) == "Anathamaas Aetherwind"
    assert str(G.QuickFindNearest("innkeeper").name) == "Donaal Downbreeze"
    # the search box's list the same: the isle's first, nearest first
    res = G.SearchPlaces("class trainer", 8)
    assert str(res[1].name) == "Anathamaas Aetherwind" and res[1].cont == 2991
    # a custom search button's top result too
    assert ns.Searches.Top("innkeeper").cont == 2991


def test_none_of_a_kind_on_the_isle_is_said_and_never_routed_off_it(isle):
    lua, ns = isle
    G, N = ns.GPS, ns.Nav
    N.Clear()
    # (no flight master on the isle: the mainland's are elsewhere)
    found, elsewhere = G.QuickFindNearest("flight master")
    assert found is None and elsewhere and elsewhere.cont != 2991
    assert tuple(ns.Searches.Top("flight master")) == (None, True)
    lua.execute("AGPS_PICKED = nil AGPS_ZI.pick = AGPS_NS.GPS.PickSearchEntry "
                "AGPS_NS.GPS.PickSearchEntry = function(e) AGPS_PICKED = e end")
    try:
        assert G.QuickFindClick(lua.eval("{ kind = 'flight master', label = 'Flight Master' }")) is None
        assert lua.eval("AGPS_PICKED") is None and len(N.stops) == 0
        said = _said(lua)
        assert said and "no Flight Master known on Zephras Isle" in said[-1]
        # the isle's NPCs left out (as before 1.3.14): an innkeeper only elsewhere is never the stop either
        lua.execute("""
          local keep = {}
          for line in AGPS_ZI.packed:gmatch("[^\\n]+") do
            if not line:find("2991 ", 1, true) then keep[#keep + 1] = line end
          end
          AGPS_NS.NpcsPacked = table.concat(keep, "\\n")
        """)
        found, elsewhere = G.QuickFindNearest("innkeeper")
        assert found is None and elsewhere and elsewhere.cont != 2991
        assert G.QuickFindClick(lua.eval("{ kind = 'innkeeper', label = 'Innkeeper' }")) is None
        assert lua.eval("AGPS_PICKED") is None
        # one talked to there is found: the learned NPC on the isle
        ns.db.npcs = lua.eval("""{ [999001] = { name = "Innkeeper Breeze", title = "Innkeeper", cont = 2991,
          x = 2100.0, y = 700.0, z = 660.0, faction = "Alliance" } }""")
        e = G.QuickFindNearest("innkeeper")
        assert e and str(e.name) == "Innkeeper Breeze" and e.cont == 2991
    finally:
        lua.execute("AGPS_NS.GPS.PickSearchEntry = AGPS_ZI.pick")


def test_on_the_mainland_quick_find_is_as_before(isle):
    lua, ns = isle
    lua.execute("AGPS_MAP = 1420 AGPS_POS = { 2254.0, 293.0, 0 }")  # (Brill)
    ns.CharDB().faction = "Horde"
    e = ns.GPS.QuickFindNearest("innkeeper")
    assert e and str(e.name) == "Innkeeper Renee" and e.cont == 0
