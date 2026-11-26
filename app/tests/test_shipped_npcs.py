"""Every friendly NPC shipped for the search (asked 2026-11-14: "the search function for repairs/trainers/etc should
always show for any NPC, only the icons in cities require to talk to a guard first but those should still be able to
be searchable beforehand. Also, add an option beside searched NPCs to a custom pin for its location permanently";
the user's choice, "Ship all NPCs"). Data/Npcs.lua (`agps npcs`, npcs.py, the CMaNGOS dump): found by name, title
and the generic words before talking to anyone, nearest first, the player's faction's and neutral ones only; one
talked to is the same NPC, once; the search list's Pin button pins one for good with an icon by what it does."""
import re

import pytest

from azerothgps.paths import ADDON_DIR

NPCS = ADDON_DIR / "Data" / "Npcs.lua"
BRILL = (2254.0, 293.0, 0)
ABE_WINTERS = 2135  # (Apprentice Armorer, Brill: repairs)
LINE = re.compile(r"^(\d+)\|([^|]+)\|([^|]*)\|([gqvfthibpdmasr]*)\|([A-Za-z ]*)\|([AHB])\|(.+)$")


def _body():
    text = NPCS.read_text(encoding="utf-8")
    return text.split("ns.NpcsPacked = [==[", 1)[1].split("]==]", 1)[0].strip().splitlines()


def test_the_data_file_is_one_packed_string_of_friendly_npcs():
    lines = _body()
    assert 2000 < len(lines) < 6000
    assert NPCS.stat().st_size < 400 * 1024  # (read at the first search: no login cost but the string)
    ids, sides = set(), {}
    for line in lines:
        m = LINE.match(line)
        assert m, line
        ids.add(int(m.group(1)))
        sides[m.group(2)] = m.group(6)
        for spawn in m.group(7).split(";"):
            lv, x, y, z = spawn.split(" ")
            assert int(lv) in (0, 1, 2991, 10001), line
            float(x), float(y), float(z)
    assert len(ids) == len(lines)  # (one line an NPC)
    assert sides["Innkeeper Renee"] == "H" and sides["Innkeeper Farley"] == "A" and sides["Thrall"] == "H"
    assert sides["Jazzik"] == "B"  # (a neutral goblin vendor: both)
    assert "Hogger" not in sides and "Kobold Vermin" not in sides  # (hostile)
    # read only by the search (Layers' L.ShippedNpcs) and, one NPC's line at a time, the height band (HeightBand.lua,
    # item 104: an NPC named near the player)
    readers = sorted(f.name for f in ADDON_DIR.rglob("*.lua") if "NpcsPacked" in f.read_text(encoding="utf-8",
                                                                                               errors="replace"))
    assert readers == ["HeightBand.lua", "Layers.lua", "Npcs.lua"]


def test_the_generator_tells_sides_by_the_faction_templates():
    from azerothgps.npcs import lua_text, services, side, trainer_kind

    alliance = {"Faction": 1, "FactionGroup": 3, "FriendGroup": 2, "EnemyGroup": 12, "Enemies": [0], "Friend": [0]}
    horde = {"Faction": 2, "FactionGroup": 5, "FriendGroup": 4, "EnemyGroup": 10, "Enemies": [0], "Friend": [0]}
    sw = {"Faction": 72, "FactionGroup": 3, "FriendGroup": 2, "EnemyGroup": 12, "Enemies": [0], "Friend": [0]}
    org = {"Faction": 76, "FactionGroup": 5, "FriendGroup": 4, "EnemyGroup": 10, "Enemies": [0], "Friend": [0]}
    goblin = {"Faction": 21, "FactionGroup": 0, "FriendGroup": 0, "EnemyGroup": 0, "Enemies": [0], "Friend": [21]}
    monster = {"Faction": 14, "FactionGroup": 8, "FriendGroup": 0, "EnemyGroup": 1, "Enemies": [0], "Friend": [0]}
    assert [side(f, alliance, horde) for f in (sw, org, goblin, monster)] == ["A", "H", "B", None]
    assert services(0x4 | 0x4000 | 0x80) == "vir"
    t = {"NpcFlags": "16", "SubName": "Journeyman Blacksmith", "TrainerType": "2", "TrainerClass": "0"}
    assert trainer_kind(t) == "Blacksmithing"
    assert trainer_kind(dict(t, SubName="Mage Trainer", TrainerType="0", TrainerClass="8")) == "MAGE"
    assert trainer_kind(dict(t, SubName="Weapon Master")) == "Weapon"
    text = lua_text({7: {"name": "Smith", "sub": "Armorer", "svc": "vr", "trainer": "", "side": "H",
                         "spawns": [(0, 1.0, 2.0, 3.0), (10001, 4.0, 5.0, -6.0)]}})
    assert "7|Smith|Armorer|vr||H|0 1.0 2.0 3.0;10001 4.0 5.0 -6.0" in text


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


@pytest.fixture
def horde(game):
    lua, ns = game
    was_npcs, was_pins = ns.db.npcs, ns.db.pins
    ns.db.npcs, ns.db.pins = lua.eval("{}"), lua.eval("{}")
    ns.CharDB().faction = "Horde"
    lua.execute(f"AGPS_POS = {{ {BRILL[0]}, {BRILL[1]}, {BRILL[2]} }}")
    yield lua, ns
    ns.db.npcs, ns.db.pins = was_npcs, was_pins
    ns.CharDB().faction = "Horde"


def _search(ns, text, max=30):
    res = ns.GPS.SearchPlaces(text, max)
    return [res[i] for i in range(1, len(res) + 1)]


def _shipped(ns, text, max=30):
    return [e for e in _search(ns, text, max) if e.shipped]


def test_repair_finds_the_nearest_repair_vendors_before_talking_to_anyone(horde):
    lua, ns = horde
    assert len(ns.db.npcs) == 0
    res = _shipped(ns, "repair")
    assert len(res) >= 5
    assert "Abe Winters" in [str(e.name) for e in res[:3]]  # (Brill's armorer, 25 yd off)
    yds = [e.yd for e in res if e.yd is not None]
    assert yds == sorted(yds) and yds[0] < 40
    assert all(ns.Layers.NpcOffers(e.shipped, "r") for e in res)
    (abe,) = [e for e in res if str(e.name) == "Abe Winters"]
    assert abe.cont == 0 and abs(abe.x - 2237.8) < 0.1 and abs(abe.z - 36.8) < 0.1
    assert "Brill" in str(abe.sub) and "Apprentice Armorer" in str(abe.sub)
    # the other generic words: their services
    assert str(_shipped(ns, "innkeeper")[0].name) == "Innkeeper Renee"
    assert str(_shipped(ns, "class trainer")[0].name) != ""
    assert any(str(e.name) == "Michael Garrett" and e.cont == 10001 for e in _shipped(ns, "flight master"))
    assert any(str(e.name) == "Randolph Montague" for e in _shipped(ns, "bank"))


def test_an_enemy_faction_npc_is_never_found(horde):
    lua, ns = horde
    assert _shipped(ns, "Innkeeper Farley") == []
    for text in ("repair", "vendor", "innkeeper", "flight master", "Innkeeper"):
        assert all(str(e.shipped.side) in ("H", "B") for e in _shipped(ns, text, 60)), text
    ns.CharDB().faction = "Alliance"
    assert [str(e.name) for e in _shipped(ns, "Innkeeper Farley")] == ["Innkeeper Farley"]
    assert _shipped(ns, "Innkeeper Renee") == []
    assert [str(e.name) for e in _shipped(ns, "Jazzik")] == ["Jazzik"]  # (neutral: both)


def test_found_by_name_and_by_title(horde):
    lua, ns = horde
    assert str(_shipped(ns, "Thrall")[0].name) == "Thrall"
    assert "Abe Winters" in [str(e.name) for e in _shipped(ns, "Apprentice Armorer")]
    assert "Abe Winters" in [str(e.name) for e in _shipped(ns, "armorer")]
    lua.execute("AGPS_OLDC = UnitClass UnitClass = function() return 'Mage', 'MAGE' end")
    try:
        res = _shipped(ns, "class trainer")
        assert str(res[0].name) == "Cain Firesong"  # (Brill's mage trainer)
        assert all(str(e.shipped.trainer) == "MAGE" for e in res)
        # a profession's trainer by its profession, whatever the title ("Journeyman Blacksmith")
        res = _shipped(ns, "blacksmithing trainer")
        assert res and all(str(e.shipped.trainer) == "Blacksmithing" for e in res)
    finally:
        lua.execute("UnitClass = AGPS_OLDC")


def test_one_talked_to_is_the_same_npc_once_on_the_floor_learned(horde):
    lua, ns = horde
    ns.db.npcs = lua.eval(f"""{{
      [{ABE_WINTERS}] = {{ name = "Abe Winters", title = "Apprentice Armorer", cont = 0, x = 2236, y = 311, z = 40.5,
        faction = "Horde", vendor = true, repair = true }},
    }}""")
    res = [e for e in _search(ns, "Abe Winters") if str(e.name) == "Abe Winters"]
    assert len(res) == 1 and res[0].shipped
    assert res[0].z == 40.5  # (the learned floor first)
    ns.db.npcs[ABE_WINTERS].z = None
    (e,) = [e for e in _search(ns, "Abe Winters") if str(e.name) == "Abe Winters"]
    assert abs(e.z - 36.8) < 0.1  # (else the spawn's own height)


def test_the_pin_button_pins_an_npc_with_its_icon_and_floor_once(horde):
    lua, ns = horde
    (abe,) = [e for e in _shipped(ns, "Abe Winters")]
    pin, _ = ns.GPS.PinSearchEntry(abe)
    assert pin is not None
    assert str(pin.icon) == "Interface\\Icons\\Trade_BlackSmithing"
    assert str(pin.name) == "Abe Winters <Apprentice Armorer>"
    assert pin.level == 0 and abs(pin.x - 2237.8) < 0.1 and abs(pin.z - 36.8) < 0.1
    again, have = ns.GPS.PinSearchEntry(abe)
    assert again is None and have.time == pin.time and len(ns.db.pins) == 1  # (pinned already: said, no second)
    # each kind its icon; down in Undercity on its level and floor
    icons = {"Innkeeper Renee": "Interface\\Icons\\INV_Misc_Rune_01",
             "Cain Firesong": "Interface\\Icons\\INV_Staff_13",
             "Michael Garrett": "Interface\\Icons\\Ability_Mount_Wyvern_01",
             "Randolph Montague": "Interface\\Icons\\INV_Misc_Bag_10_Blue",
             "Mrs. Winters": "Interface\\Icons\\INV_Misc_Bag_10",
             "Executor Zygand": "Interface\\GossipFrame\\AvailableQuestIcon"}
    for name, icon in icons.items():
        (e,) = [e for e in _shipped(ns, name) if str(e.name) == name]
        p, _ = ns.GPS.PinSearchEntry(e)
        assert p is not None and str(p.icon) == icon, name
        if name in ("Michael Garrett", "Randolph Montague"):
            assert p.level == 10001 and p.z < 0, name
    assert len(ns.db.pins) == 1 + len(icons)
    # the pins are searched too, at their spot and floor
    assert any(e.pin for e in _search(ns, "Abe Winters"))


def test_a_city_place_and_a_learned_npc_can_be_pinned_too(horde):
    lua, ns = horde
    ns.NpcsPacked, was = "", ns.NpcsPacked
    try:
        ns.db.npcs = lua.eval("""{
          [99001] = { name = "Learned Smith", title = "Armorer", cont = 0, x = 2300, y = 300, faction = "Horde",
            vendor = true, repair = true },
        }""")
        (e,) = [e for e in _search(ns, "Learned Smith") if e.npc]
        p, _ = ns.GPS.PinSearchEntry(e)
        assert str(p.icon) == "Interface\\Icons\\Trade_BlackSmithing" and str(p.name) == "Learned Smith <Armorer>"
    finally:
        ns.NpcsPacked = was
    places = [e for e in _search(ns, "Mage Trainer") if e.place]
    assert places
    p, _ = ns.GPS.PinSearchEntry(places[0])
    assert p is not None and str(p.icon) == str(places[0].tex) and str(p.name) == str(places[0].place)


def test_each_npc_row_in_the_search_box_has_a_pin_button(horde):
    lua, ns = horde
    G = ns.GPS
    panel = G.searchPanel
    assert panel is not None
    same = lua.eval("rawequal")
    box = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "EditBox" and same(w._parent, panel))
    try:
        box._text = "Abe Winters"
        box._scripts.OnTextChanged(box)
        rows = [w for w in lua.eval("AGPS_WIDGETS").values()
                if same(w._parent, panel) and w.entry is not None and w._shown and w.entry.shipped]
        assert rows and rows[0].pin is not None and rows[0].pin._shown
        # (a pixel-art map pin since 2026-11-19, test_search_keys.py; the word "Pin" only till a relog)
        assert rows[0].pin.art._shown and str(rows[0].pin.art._tex).endswith("Pin_" + str(rows[0].pin.art.agpsArtPx))
        assert str(rows[0].pin.label._text) == "Pin"
        rows[0].pin._scripts.OnClick(rows[0].pin)
        assert len(ns.db.pins) == 1 and str(ns.db.pins[1].name) == "Abe Winters <Apprentice Armorer>"
        rows[0].pin._scripts.OnClick(rows[0].pin)  # (again: said, no second)
        assert len(ns.db.pins) == 1
        # a pin's own row has none
        box._scripts.OnTextChanged(box)
        pins = [w for w in lua.eval("AGPS_WIDGETS").values()
                if same(w._parent, panel) and w.entry is not None and w._shown and w.entry.pin]
        assert pins and not pins[0].pin._shown
    finally:
        for w in lua.eval("AGPS_WIDGETS").values():
            if w.entry is not None and same(w._parent, panel) and w.text is not None:
                w.text._text = ""


def test_one_talked_to_by_another_creature_id_is_the_same_npc_by_its_name_and_spot(horde):
    # (the game's creature id may not be the data's: the same name within Layers.NPC_SAME_YD of a spawn is that NPC)
    lua, ns = horde
    ns.db.npcs = lua.eval("""{
      [99002] = { name = "Abe Winters", title = "Apprentice Armorer", cont = 0, x = 2240, y = 310, z = 39.5,
        faction = "Horde" },
      [99003] = { name = "Abe Winters", title = "Apprentice Armorer", cont = 0, x = 2600, y = 310, faction = "Horde" },
    }""")
    res = [e for e in _search(ns, "Abe Winters") if e.npc]
    assert len(res) == 2  # (the shipped one, on the floor learned there; and one far away: another NPC of that name)
    (shipped,) = [e for e in res if e.shipped]
    assert shipped.z == 39.5


# Undercity, 2026-11-14 (reported, a screenshot): "I searched repair from here ... the route jumps to thinking im not
# low enough (target 14yd down) yet im right in front of that NPC". By the Rogues' Quarter, on the ring (71.5, 60.5 on
# its map) under the walkways over it: "repair" picked Gillian Moore on the ring 18 yd off, and the route went 559 yd
# up round by the Trade Quarter and back, "Below you, 14 yd down": the floor followed had started on the walkways.
GILLIAN_MOORE = 5820  # (Leather Armor Merchant, repairs; on the ring at -62.1)


@pytest.fixture
def undercity(horde):
    lua, ns = horde
    lua.execute("""
      AGPS_OLDUC = { best = C_Map.GetBestMapForUnit, t = AGPS_T }
      C_Map.GetBestMapForUnit = function() return 1458 end
      AGPS_T = 5000
    """)
    x, y, _ = ns.Layers.MapToWorld(1458, 0.715, 0.605)
    ns.Nav.ResetCityTrack()
    yield lua, ns, (x, y)
    ns.Nav.SetStops(lua.eval("{}"), False, True)
    ns.Nav.ResetCityTrack()
    lua.execute("C_Map.GetBestMapForUnit, AGPS_T = AGPS_OLDUC.best, AGPS_OLDUC.t AGPS_OLDUC = nil")


def _walk(lua, ns, a, b):
    n = max(1, int(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 / 0.7))
    for k in range(n + 1):
        x, y = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
        lua.execute(f"AGPS_T = AGPS_T + 0.3 AGPS_POS = {{ {x}, {y}, 0 }}")
        ns.Nav.TrackCityZ(10001, x, y)


def _repair_route(lua, ns, at):
    (e,) = _shipped(ns, "repair", 1)
    N = ns.Nav
    N.SetStops(lua.eval("{}"), False, True)
    N.AddStop(lua.table(x=e.x, y=e.y, cont=e.cont, name=e.name, z=e.z), False, True)
    r = None
    for _ in range(20):
        r = N.Route(at[0], at[1], 0)
        if r:
            break
    return e, r, N.HeightText(at[0], at[1], 0)


def test_by_a_merchant_on_undercitys_ring_repair_is_a_few_yards_along_it(undercity):
    lua, ns, at = undercity
    # walked in from the walkways' side: under them no floor is taken (only roads above within reach), the route
    # starts on the ring by the merchant's floor
    _walk(lua, ns, (at[0] - 15, at[1] + 9), at)
    e, r, hint = _repair_route(lua, ns, at)
    assert str(e.name) == "Gillian Moore" and e.cont == 10001 and abs(e.z - -62.1) < 0.1 and e.yd < 25
    assert r.totalYards < 40, r.totalYards  # (was 559: up round by the Trade Quarter)
    assert hint is None, hint  # (was "Below you, 16 yd down")
    # the floor not followed yet, just there: the hint as the route goes, not by the walkway overhead
    ns.Nav.ResetCityTrack()
    lua.execute("AGPS_T = AGPS_T + 30")
    assert ns.Nav.CityHeight(10001, *at) > -110  # (the top floor there: the walkway)
    e, r, hint = _repair_route(lua, ns, at)
    assert r.totalYards < 40 and hint is None, (r.totalYards, hint)  # (was "Below you, 17 yd down")


def test_a_merchants_window_tells_the_floor_down_in_undercity(undercity):
    lua, ns, at = undercity
    N = ns.Nav
    by = (1503.0, 196.5)  # (in front of Gillian Moore, on the ring)
    N.AnchorFloor(10001, by[0], by[1], -50.0)  # (the floor followed wrong: the walkway over the ring)
    assert abs(N.FollowedZ(10001) - -50) < 1
    lua.execute(f"""
      AGPS_POS = {{ {by[0]}, {by[1]}, 0 }}
      AGPS_OLDN = {{ guid = UnitGUID, name = UnitName }}
      UnitGUID = function(u) if u == "npc" then return "Creature-0-1-2-3-{GILLIAN_MOORE}-00000ABC" end
        return AGPS_OLDN.guid(u) end
      UnitName = function(u) if u == "npc" then return "Gillian Moore" end return AGPS_OLDN.name(u) end
    """)
    try:
        ns.Layers.OnNpcWindow("MERCHANT_SHOW")
    finally:
        lua.execute("UnitGUID, UnitName = AGPS_OLDN.guid, AGPS_OLDN.name AGPS_OLDN = nil")
    assert abs(N.FollowedZ(10001) - -62.1) < 1.5  # (her height: the ring)
    assert abs(ns.db.npcs[GILLIAN_MOORE].z - -62.1) < 0.1  # (and the floor learned for her)
    e, r, hint = _repair_route(lua, ns, by)
    assert str(e.name) == "Gillian Moore" and r.totalYards < 10 and hint is None, (str(e.name), r.totalYards, hint)


# Orgrimmar, 2026-11-15 (reported, a screenshot): "another case of GPS thinking the NPC is below me". By Innkeeper
# Gryshka in the inn (54.1, 68.6 on its map), routed to her: "Make a U-turn now / Below you, 9 yd down", 113 yd. The
# road down from the Valley of Strength's rise ends at 24 north of the inn's door, its floor 16 with no road between:
# walked down there off the roads, the floor followed stayed 24 the whole way in, and the route went out and round.
GRYSHKA = (1634.0, -4439.4, 15.5)  # (her shipped spawn)
BY_GRYSHKA = (1632.2, -4439.4)
# from the rise's road (24 at its end, 1635, -4395) down to the inn's door and along its roads to her
INTO_THE_INN = [(1629.0, -4383.0), (1629.0, -4389.0), (1635.0, -4395.0), (1629.0, -4408.0), (1623.0, -4407.0),
                (1623.0, -4423.0), (1631.0, -4431.0), (1629.0, -4435.0), BY_GRYSHKA]


@pytest.fixture
def orgrimmar_inn(horde):
    lua, ns = horde
    lua.execute("""
      AGPS_OLDOI = { indoors = IsIndoors, t = AGPS_T, best = C_Map.GetBestMapForUnit }
      C_Map.GetBestMapForUnit = function() return 1454 end -- (Orgrimmar)
      AGPS_IN = false IsIndoors = function() return AGPS_IN end
      AGPS_T = (AGPS_T or 0) + 5000
    """)
    ns.Nav.ResetCityTrack()
    yield lua, ns
    ns.Nav.SetStops(lua.eval("{}"), False, True)
    ns.Nav.ResetCityTrack()
    lua.execute("IsIndoors, AGPS_T, C_Map.GetBestMapForUnit = AGPS_OLDOI.indoors, AGPS_OLDOI.t, AGPS_OLDOI.best"
                " AGPS_OLDOI = nil AGPS_IN = nil")


def _walk_in(lua, ns, pts, off=0.6, step=0.5):
    """Along the points `off` yards to their left at a run (a look every TRACK_EVERY), indoors past the inn's door."""
    zs = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 or 1
        n = max(1, round(L / step))
        for j in range(n + 1):
            x = ax + (bx - ax) * j / n - (by - ay) / L * off
            y = ay + (by - ay) * j / n + (bx - ax) / L * off
            inside = "true" if y < -4410 else "false"
            lua.execute(f"AGPS_POS = {{ {x}, {y}, 1 }} AGPS_T = AGPS_T + 0.26 AGPS_IN = {inside}")
            zs.append(ns.Nav.TrackCityZ(1, x, y))
    return zs


def _to_gryshka(lua, ns, at):
    N = ns.Nav
    lua.execute(f"AGPS_POS = {{ {at[0]}, {at[1]}, 1 }}")
    N.SetStops(lua.eval("{}"), False, True)
    N.AddStop(lua.table(x=GRYSHKA[0], y=GRYSHKA[1], cont=1, name="Innkeeper Gryshka", z=GRYSHKA[2]), False, True)
    r = None
    for _ in range(20):
        r = N.Route(at[0], at[1], 1)
        if r:
            break
    return r, N.HeightText(at[0], at[1], 1)


def test_walked_down_into_orgrimmars_inn_its_innkeeper_is_a_few_yards_off_not_below(orgrimmar_inn):
    lua, ns = orgrimmar_inn
    zs = _walk_in(lua, ns, INTO_THE_INN)
    (e,) = [e for e in _shipped(ns, "innkeeper", 5) if str(e.name) == "Innkeeper Gryshka"]
    assert e.cont == 1 and abs(e.x - GRYSHKA[0]) < 0.1 and abs(e.z - GRYSHKA[2]) < 0.1 and e.yd < 5
    assert any(z is not None and z > 23 for z in zs[:40]), zs[:40]  # (on the rise's road: its floor, 24 and up)
    assert abs(ns.Nav.FollowedZ(1) - GRYSHKA[2]) < 2, ns.Nav.FollowedZ(1)  # (was 24: the rise's, kept all the way in)
    r, hint = _to_gryshka(lua, ns, BY_GRYSHKA)
    assert r.totalYards < 10, r.totalYards  # (was 116: out of the inn and round)
    assert hint is None, hint  # (was "Below you, 9 yd down")


def test_logged_in_by_orgrimmars_innkeeper_she_is_a_few_yards_off_not_below(orgrimmar_inn):
    lua, ns = orgrimmar_inn
    lua.execute("AGPS_IN = true")
    r, hint = _to_gryshka(lua, ns, BY_GRYSHKA)
    assert abs(ns.Nav.FollowedZ(1) - GRYSHKA[2]) < 2, ns.Nav.FollowedZ(1)
    assert r.totalYards < 10 and hint is None, (r.totalYards, hint)


# Another addon's Shift-click on NPCs (API 20, issue #383: StreetView's NPC street views): offered with kind "npc" and
# the NPC's creature id for an inside map's NPC dot, a search row and a pin made from one; a click it doesn't use does
# what it did; its hint shows only when hint(info) gives a string.
SHIFT_SETUP = """
  AGPS_OLD_SHIFTNPC = { IsShiftKeyDown, GameTooltip.SetText, GameTooltip.AddLine, GameTooltip.Show }
  AGPS_SHIFT, AGPS_GOT, AGPS_TIP, AGPS_TIP_SHOWN = true, {}, {}, false
  IsShiftKeyDown = function() return AGPS_SHIFT end
  GameTooltip.SetText = function(_, t) AGPS_TIP[#AGPS_TIP + 1] = t end
  GameTooltip.AddLine = function(_, t) AGPS_TIP[#AGPS_TIP + 1] = t end
  GameTooltip.Show = function() AGPS_TIP_SHOWN = true end
  AGPS_USE = true
  AGPS_SHIFT_FN = function(info) AGPS_GOT[#AGPS_GOT + 1] = info return AGPS_USE end
  AGPS_SHIFT_HINT = function(info) if info.kind == "npc" and info.id == AGPS_HINT_ID then return "its street view" end end
"""
SHIFT_TEARDOWN = """
  IsShiftKeyDown, GameTooltip.SetText, GameTooltip.AddLine, GameTooltip.Show =
    AGPS_OLD_SHIFTNPC[1], AGPS_OLD_SHIFTNPC[2], AGPS_OLD_SHIFTNPC[3], AGPS_OLD_SHIFTNPC[4]
  AzerothGPS.OnIconShiftClick("Test", nil)
"""


def _npc_id(ns, name):
    _, _, by_name = ns.Layers.ShippedNpcs()
    return int(by_name[name.lower()][1].id)


def test_a_shift_click_on_an_npcs_search_row_goes_to_another_addon(horde):
    lua, ns = horde
    G, A = ns.GPS, lua.globals().AzerothGPS
    assert A.version >= 20
    abe = _npc_id(ns, "Abe Winters")
    assert abe == ABE_WINTERS
    panel = G.searchPanel
    same = lua.eval("rawequal")
    box = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "EditBox" and same(w._parent, panel))
    lua.execute(SHIFT_SETUP)
    try:
        lua.execute("AGPS_ADDSTOP = AGPS_NS.GPS.AddStopAt AGPS_ADDED = {} "
                    "AGPS_NS.GPS.AddStopAt = function(x, y, name) AGPS_ADDED[#AGPS_ADDED + 1] = name end")
        box._text = "Abe Winters"
        box._scripts.OnTextChanged(box)
        (row,) = [w for w in lua.eval("AGPS_WIDGETS").values()
                  if same(w._parent, panel) and w.entry is not None and w._shown and w.entry.shipped][:1]
        # none registered: a Shift-click is a stop, as before; no tooltip
        row._scripts.OnEnter(row)
        assert not lua.eval("AGPS_TIP_SHOWN")
        row._scripts.OnClick(row)
        assert list(lua.eval("AGPS_ADDED").values()) == ["Abe Winters"]
        A.OnIconShiftClick("Test", lua.eval("AGPS_SHIFT_FN"), lua.eval("AGPS_SHIFT_HINT"))
        # no view of that NPC (hint nil): no tooltip line
        lua.execute("AGPS_HINT_ID = -1")
        row._scripts.OnEnter(row)
        assert not lua.eval("AGPS_TIP_SHOWN")
        lua.execute(f"AGPS_HINT_ID = {abe}")
        row._scripts.OnEnter(row)
        assert lua.eval("AGPS_TIP_SHOWN") and "Shift-click: its street view" in list(lua.eval("AGPS_TIP").values())
        # used: the addon has it, with the NPC's id, and no stop is made
        row._scripts.OnClick(row)
        got = lua.eval("AGPS_GOT[#AGPS_GOT]")
        assert str(got.kind) == "npc" and got.id == abe and str(got.name) == "Abe Winters"
        assert got.cont == 0 and got.floor is None and abs(got.x - 2237.8) < 0.1 and got.z is not None
        assert len(lua.eval("AGPS_ADDED")) == 1
        # not used: a stop as before
        lua.execute("AGPS_USE = false")
        row._scripts.OnClick(row)
        assert len(lua.eval("AGPS_ADDED")) == 2
        # a plain click: never offered
        lua.execute("AGPS_SHIFT, AGPS_GOT = false, {}")
        row._scripts.OnClick(row)
        assert len(lua.eval("AGPS_GOT")) == 0 and len(lua.eval("AGPS_ADDED")) == 3
        # a pin made from the row keeps the NPC: its Shift-click is offered too, else shared in chat as before
        lua.execute("AGPS_SHIFT, AGPS_USE = true, true")
        p, _ = G.PinSearchEntry(row.entry)
        assert p.npc == abe and str(p.npcName) == "Abe Winters"
        info = G.PinNpcInfo(p)
        assert str(info.kind) == "npc" and info.id == abe and str(info.name) == "Abe Winters"
    finally:
        lua.execute("AGPS_NS.GPS.AddStopAt = AGPS_ADDSTOP")
        lua.execute(SHIFT_TEARDOWN)
        G.Follow()  # (a row picked shows its NPC: the map panned there)
        for w in lua.eval("AGPS_WIDGETS").values():
            if w.entry is not None and same(w._parent, panel) and w.text is not None:
                w.text._text = ""


def test_an_undercity_npcs_info_has_its_continent_and_its_level(horde):
    lua, ns = horde
    G = ns.GPS
    info = G.NpcClickInfo(4551, "Michael Garrett", "Bat Handler", 10001, 1566.0, 268.0, -43.1)
    assert str(info.kind) == "npc" and info.id == 4551 and info.cont == 0 and info.floor == 10001
    assert G.NpcClickInfo(None, "Nobody", None, 0, 1.0, 2.0, 3.0) is None  # (no id: nothing offered)


def test_a_shift_click_on_an_inside_maps_npc_dot_goes_to_another_addon(horde):
    lua, ns = horde
    G, N, A, st = ns.GPS, ns.Nav, lua.globals().AzerothGPS, ns.settings.gps
    renee = _npc_id(ns, "Innkeeper Renee")
    lua.execute(SHIFT_SETUP)
    lua.execute("""
      AGPS_INDOORS_NPC = { IsIndoors, GetMinimapZoneText }
      IsIndoors = function() return true end
      GetMinimapZoneText = function() return "Gallows' End Tavern" end
      AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2269.5, 244.9, 0
    """)
    zoom = st.zoom

    def dot():
        lua.execute("AGPS_T = AGPS_T + 6")
        G.Redraw()
        G.Update()
        b = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.npc and w.npc.id == renee]
        return b[0] if b else None

    try:
        st.zoom = 60.0
        G.Follow()
        A.OnIconShiftClick("Test", lua.eval("AGPS_SHIFT_FN"), lua.eval("AGPS_SHIFT_HINT"))
        lua.execute("AGPS_HINT_ID = -1")
        b = dot()
        assert b is not None, "no dot for Innkeeper Renee in Brill's inn"
        assert "Shift-click" not in str(b.note or "")  # (no view: no hint)
        lua.execute(f"AGPS_HINT_ID = {renee}")
        b = dot()
        assert "Shift-click: its street view" in str(b.note)
        N.Clear()
        b._scripts.OnClick(b, "LeftButton")
        got = lua.eval("AGPS_GOT[#AGPS_GOT]")
        assert str(got.kind) == "npc" and got.id == renee and str(got.name) == "Innkeeper Renee" and got.cont == 0
    finally:
        st.zoom = zoom
        N.Clear()
        lua.execute(SHIFT_TEARDOWN)
        lua.execute("IsIndoors, GetMinimapZoneText = AGPS_INDOORS_NPC[1], AGPS_INDOORS_NPC[2] "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 6")
        G.Redraw()


def test_what_and_where_typed_together_finds_the_npcs_there(horde):
    # (asked 2026-11-14, a screenshot: "tailor tarren mill" found nothing, Daryl Stack the Master Tailor there; "consider
    # any search like this") a place's name at the end or the start narrows the rest's results to that place
    lua, ns = horde
    res = _shipped(ns, "tailor tarren mill")
    assert "Daryl Stack" in [str(e.name) for e in res] and all("Tarren Mill" in str(e.sub) for e in res), [str(e.sub) for e in res]
    assert "Daryl Stack" in [str(e.name) for e in _shipped(ns, "tarren mill tailor")]
    assert all("Tarren Mill" in str(e.sub) for e in _shipped(ns, "repair tarren mill")[:1])
    rep = _shipped(ns, "repair tarren")
    assert rep and "Tarren Mill" in str(rep[0].sub) and ns.Layers.NpcOffers(rep[0].shipped, "r"), [str(e.sub) for e in rep]
    inn = _shipped(ns, "innkeeper undercity")
    assert inn and inn[0].cont == 10001, [(str(e.name), str(e.sub)) for e in inn]


def test_a_generic_word_begun_finds_its_kind(horde):
    # (asked 2026-11-14: "for like repair shouldn't need the full word, vendor, etc") three letters or more
    lua, ns = horde
    for begun, whole in (("rep", "repair"), ("vend", "vendor"), ("innk", "innkeeper"), ("bank", "banker")):
        a = [str(e.name) for e in _shipped(ns, begun)[:5]]
        assert a and a == [str(e.name) for e in _shipped(ns, whole)[:5]], (begun, a)
    yds = [e.yd for e in _shipped(ns, "vend") if e.yd is not None]
    assert yds and yds == sorted(yds)  # (nearest first, as "vendor")


# Orgrimmar, 2026-11-15 (reported with #402's fix in, a screenshot): on top of the Wind Rider tower by Doras (45.6, 64.1
# on its map), Quick Find's Flight Master: "Take the stairs up / Above you, 36 yd up / Orgrimmar Wind Rider Master
# 100 yd". Flown in, the floor had been followed on the flight, along the streets under the wind rider, and kept on
# landing (no road at that height up on the tower): routed from the streets, up the tower. Walked up its ramp, or
# logged in up there, it was right.
DORAS = (1676.2, -4313.4, 61.7)  # (Wind Rider Master, his shipped spawn: the tower's top)
LANDED = (1677.6, -4315.7)  # (Orgrimmar's flight path's node)


@pytest.fixture
def wind_rider_tower(orgrimmar_inn):
    lua, ns = orgrimmar_inn
    lua.execute("AGPS_OLDTX = UnitOnTaxi AGPS_TAXI = false UnitOnTaxi = function() return AGPS_TAXI end")
    x, y, _ = ns.Layers.MapToWorld(1454, 0.456, 0.641)
    yield lua, ns, (x, y)
    lua.execute("UnitOnTaxi = AGPS_OLDTX AGPS_OLDTX = nil AGPS_TAXI = nil")


def _flight_master_stop(lua, ns, at, near=10):
    """The nearest flight master picked as Quick Find's Flight Master does (G.QuickFindNearest, then the search's Pick:
    a city place by its name, icon and height), routed to from `at`."""
    G, N = ns.GPS, ns.Nav
    lua.execute(f"AGPS_POS = {{ {at[0]}, {at[1]}, 1 }}")
    res = G.SearchPlaces("flight master", 30)
    e = min((res[i] for i in range(1, len(res) + 1) if res[i].yd is not None), key=lambda e: e.yd)
    assert str(e.place) == "Orgrimmar Wind Rider Master" and abs(e.z - DORAS[2]) < 0.1 and e.yd < near
    N.Clear()
    G.AddStopAt(e.x, e.y, e.place, e.cont, e.tex, e.z)
    G.ConfirmRoute()
    assert str(N.dest.name) == "Orgrimmar Wind Rider Master" and abs(N.dest.z - DORAS[2]) < 0.1
    r = None
    for _ in range(20):
        r = N.Route(at[0], at[1], 1)
        if r:
            break
    return r, N.HeightText(at[0], at[1], 1)


def test_flown_in_to_orgrimmar_the_wind_rider_master_by_you_is_not_above(wind_rider_tower):
    lua, ns, at = wind_rider_tower
    # in from the south-east over the city on the wind rider, a look every quarter second
    sx, sy = LANDED[0] - 350, LANDED[1] + 200
    lua.execute("AGPS_TAXI = true")
    for j in range(61):
        x, y = sx + (LANDED[0] - sx) * j / 60, sy + (LANDED[1] - sy) * j / 60
        lua.execute(f"AGPS_POS = {{ {x}, {y}, 1 }} AGPS_T = AGPS_T + 0.25")
        assert ns.Nav.TrackCityZ(1, x, y) is None  # (on the flight: nothing followed; was the streets')
    lua.execute("AGPS_TAXI = false AGPS_T = AGPS_T + 1")
    _walk_in(lua, ns, [LANDED, at], off=0)
    assert abs(ns.Nav.FollowedZ(1) - DORAS[2]) < 3, ns.Nav.FollowedZ(1)  # (was 24.6: the streets under the flight)
    r, hint = _flight_master_stop(lua, ns, at)
    assert r.totalYards < 25, r.totalYards  # (was 375: down the tower and back up)
    assert hint is None, hint  # (was "Above you, 37 yd up")


def test_walked_up_or_logged_in_on_orgrimmars_wind_rider_tower_its_master_is_not_above(wind_rider_tower):
    lua, ns, at = wind_rider_tower
    N = ns.Nav
    # logged in up there: nothing followed yet
    r, hint = _flight_master_stop(lua, ns, at)
    assert abs(N.FollowedZ(1) - DORAS[2]) < 3 and r.totalYards < 25 and hint is None, (N.FollowedZ(1), r.totalYards, hint)
    # walked up from the street below to the stop picked there, along its route: the floor followed up the tower's
    # stairs road, and arrived. The tower's stairs road coils tight (its turns stacked, a few yards across) and the ramp
    # walked runs a couple of yards inside it: 2.5 yd in, the floor followed was lost on a turn (46) or at the stairs'
    # foot (25: "Above you, 36 yd up" the whole climb, reported) and kept to the top, the stop never arrived at
    foot = (1640.0, -4380.0)
    for off in (0.8, -2.5):
        N.ResetCityTrack()
        lua.execute("AGPS_T = AGPS_T + 30")
        up, _ = _flight_master_stop(lua, ns, foot, near=80)
        pts = [(up.pts[i], up.pts[i + 1]) for i in range(1, len(up.pts) + 1, 2)]
        arrived, zs = False, []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 or 1
            n = max(1, round(L / 0.7))
            for j in range(n + 1):
                x, y = ax + (bx - ax) * j / n - (by - ay) / L * off, ay + (by - ay) * j / n + (bx - ax) / L * off
                lua.execute(f"AGPS_POS = {{ {x}, {y}, 1 }} AGPS_T = AGPS_T + 0.1")
                arrived = arrived or "Arrived" in str(N.Status(x, y, 1))
                zs.append(N.FollowedZ(1))
        assert arrived, (off, zs[-1])  # (was never: the floor followed under the stop's)
        assert zs[-1] is None or abs(zs[-1] - DORAS[2]) < 3, (off, zs[-1])  # (was 46.3 2.5 yd in; unknown: no hint)
        assert any(z is not None and z < 30 for z in zs), off  # (from the street's floor)

