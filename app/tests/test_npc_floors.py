"""The heights of the NPCs' spots in the capitals, down in Undercity and in the caves (asked 2026-11-14: "all NPCs in
every major city to have the height data stored so any path leading to those are mapped to the appropriate height ...
Do this for any NPC in caves as well"): Data/NpcFloors.lua (`agps npc-floors`, npcfloors.py), heights only, and Nav's
N.SpawnZ, the one lookup for a stop with no height of its own at an NPC's spot. The whole addon (gameharness)."""
import math
import re

import pytest

pytest.importorskip("lupa.lua51")

NEERU = (1800.66, -4374.51)  # (Neeru Fireblade, down in Orgrimmar's Cleft of Shadow under the Drag: about -17)
CLEFT = (1846.4, -4405.7)  # (the player in the Cleft too)
BENIJAH = (1667.8, 308.9)  # (Benijah Fenner, on Undercity's Trade Quarter ring under a walkway: -62.1)
EDRIS, BRUUK = (-4969.0, -1285.0), (-4975.2, -1287.0)  # (Ironforge, the Barleybeards: upstairs 510.4, under 502.1)
FARGODEEP = (-9822.7, 180.4)  # (a kobold's spot on Fargodeep Mine's upper floor: 23.0)


def _game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    cdb = ns.CharDB()
    cdb.rxpFollow, cdb.zygorFollow = False, False
    return lua, ns


def _stop(lua, ns, cont, x, y, **kw):
    """A plain stop put in (a /way point, a map click's): the route's first stop as Nav keeps it."""
    N = ns.Nav
    N.SetStops(lua.table_from([lua.table_from(dict(x=x, y=y, cont=cont, name="there", **kw))]), False, True)
    return N.stops[1]


def test_a_stop_at_neeru_fireblade_in_the_cleft_goes_to_the_cleft():
    lua, ns = _game()
    N, R = ns.Nav, ns.Router
    d = _stop(lua, ns, 1, *NEERU)
    assert d.z == pytest.approx(-17.3) and N.StopZ(d) == pytest.approx(-17.3)
    r = R.Route(1, CLEFT[0], CLEFT[1], NEERU[0], NEERU[1], lua.table(offroad=False, z=-14.0, tz=N.StopZ(d)))
    assert r.length < 2.5 * math.dist(CLEFT, NEERU), r.length


def test_a_stop_at_an_undercity_ring_npc_is_on_its_ring():
    lua, ns = _game()
    d = _stop(lua, ns, 10001, *BENIJAH)
    assert d.z == pytest.approx(-62.1) and ns.Nav.StopZ(d) == pytest.approx(-62.1)


def test_a_stop_at_an_upstairs_npc_is_upstairs_and_the_one_under_it_downstairs():
    lua, ns = _game()
    assert _stop(lua, ns, 0, *EDRIS).z == pytest.approx(510.4)
    assert _stop(lua, ns, 0, *BRUUK).z == pytest.approx(502.1)


def test_a_stop_at_a_cave_npc_takes_its_height():
    lua, ns = _game()
    d = _stop(lua, ns, 0, *FARGODEEP)
    assert d.z == pytest.approx(23.0)
    assert ns.Router.CaveDown(0, FARGODEEP[0], FARGODEEP[1], None, d.z)


def test_a_stop_away_from_any_npc_gets_no_height():
    lua, ns = _game()
    N = ns.Nav
    assert N.SpawnZ(1, NEERU[0] + 1, NEERU[1]) == pytest.approx(-17.3)  # (within SPAWN_YD)
    assert N.SpawnZ(1, NEERU[0] + 9, NEERU[1]) is None
    # (not the NPC's: the grid's floor there, Nav.GuessStopZ, 2026-11-23)
    assert _stop(lua, ns, 1, NEERU[0] + 9, NEERU[1]).zSource != "npc"
    # (out in the open land: the ground's, kept aside, no height; and a level with none shipped)
    assert _stop(lua, ns, 1, -2000.0, -500.0).z is None and N.SpawnZ(1440, 0.0, 0.0) is None


def test_the_order_heights_are_taken_in():
    lua, ns = _game()
    N, X = ns.Nav, ns.RestedXP
    # a stop's own height first (a city place's, Polestar's for its NPC)
    assert _stop(lua, ns, 1, *NEERU, z=5.0).z == pytest.approx(5.0)
    # a guide's: its shipped waypoint height first, then the spot's, then an NPC talked to there, then the followed floor
    ns.db.npcs = lua.eval("{ [1] = { name = 'Someone', cont = 1, x = %r, y = %r, z = 40.0 } }" % NEERU)
    ns.GuideFloors = lua.eval("{ [1] = { %r, %r, -20.0 } }" % NEERU)
    assert X.HeightXY(1, *NEERU) == pytest.approx(-20.0)
    ns.GuideFloors = lua.table()
    assert X.HeightXY(1, *NEERU) == pytest.approx(-17.3)
    ns.NpcFloors = lua.table()
    assert X.HeightXY(1, *NEERU) == pytest.approx(40.0)
    # (a guide's stop is left to the guide: Copy doesn't put the spot's in first)
    ns.NpcFloors = lua.eval("{ [1] = { %r, %r, -17.3 } }" % NEERU)
    assert _stop(lua, ns, 1, *NEERU, rxp="1:x").z is None
    assert _stop(lua, ns, 1, *NEERU, corpse=True).z is None
    # a quest stop, a searched NPC: the spot's before the floor learned there
    assert _stop(lua, ns, 1, *NEERU).z == pytest.approx(-17.3)


def test_the_npc_floors_ship_heights_only():
    # (the user, 2026-11-14: an exception to "no shipped NPC data", as Data/GuideFloors.lua: no names, no creature
    # ids, nothing drawn or searched; read only by Nav's N.SpawnZ)
    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "NpcFloors.lua").read_text(encoding="utf-8")
    body = text.split("ns.NpcFloors = {", 1)[1]
    assert re.fullmatch(r"(\[\d+\]=\{(-?\d+\.\d,)*\},)*\}", re.sub(r"\s", "", body)), "only numbers"
    assert not re.search(r"[A-Za-z]", body)
    readers = [f.name for f in ADDON_DIR.rglob("*.lua") if "NpcFloors" in f.read_text(encoding="utf-8", errors="replace")]
    assert sorted(readers) == ["Nav.lua", "NpcFloors.lua"]
    # (the levels: the two continents and Undercity's own; every capital and some caves on each)
    lua, ns = _game()
    levels = sorted(k for k in ns.NpcFloors.keys())
    assert levels == [0, 1, 10001]
    for level, (x, y) in ((1, NEERU), (10001, BENIJAH), (0, EDRIS), (0, FARGODEEP)):
        assert ns.Nav.SpawnZ(level, x, y) is not None
    assert all(len(ns.NpcFloors[k]) % 3 == 0 for k in levels)


def test_npc_floors_text():
    from azerothgps.npcfloors import lua_text

    text = lua_text([(0, 1.0, 2.0, 3.04), (10001, -5.55, 6.0, -7.0), (0, 8.0, 9.0, 10.0)])
    assert "[0] = {\n    1.0,2.0,3.0, 8.0,9.0,10.0,\n  }," in text
    assert "[10001] = {\n    -5.5,6.0,-7.0,\n  }," in text or "[10001] = {\n    -5.6,6.0,-7.0,\n  }," in text
