"""Camp NPCs players put down aren't shipped (Kooki3z, 1.4.2: "reagent bot needs to be drop as vendor locations these
are camp vendors created by players and aren't always available"). The Reagent Bot on Zephras Isle (entry 242498,
guid 7010002) was in the search as a vendor, and the imp Pexmit (266901, "Someone's Minion": a player's own) as one
on Mount Hyjal. npcs.py's camp_npc tells them by what they are (a mechanical "Bot", a player's minion, CAMP_NPCS by
id) and `agps npcs` leaves them out of Data/Npcs.lua from every source."""
from collections import defaultdict

from azerothgps.npcs import CAMP_NPCS, _add_server, _drop_camp, _left_out, camp_npc, server_rows
from azerothgps.paths import ADDON_DIR

NPCS = ADDON_DIR / "Data" / "Npcs.lua"
DROPPED = {242498: "Reagent Bot", 266901: "Pexmit"}  # (the ones the data had: the snapshot's and a stand-in)


def _shipped():
    text = NPCS.read_text(encoding="utf-8")
    body = text.split("ns.NpcsPacked = [==[", 1)[1].split("]==]", 1)[0]
    return {int(ln.split("|", 1)[0]): ln.split("|") for ln in body.splitlines() if ln.strip()}, text


def test_no_camp_npc_ships():
    shipped, text = _shipped()
    for i, name in {**CAMP_NPCS, **DROPPED}.items():
        assert i not in shipped, name
        assert name not in text, name
    assert not [ln for ln in shipped.values() if camp_npc(int(ln[0]), ln[1], ln[2])]
    for key in ("ns.NpcsStill", "ns.NpcsStandIn", "-- From the server snapshot"):
        for ln in text.splitlines():
            if ln.startswith(key):
                assert not set(ln.replace('"', " ").split()) & {str(i) for i in DROPPED}, key


def test_the_world_npcs_like_them_still_ship():
    shipped, _ = _shipped()
    # (an NPC's own minion, a camp's trader, the world's own mechanical ones)
    for i, name in ((1733, "Zggi"), (734, "Corporal Bluth"), (7806, "Homing Robot OOX-09/HL")):
        assert shipped[i][1] == name


def test_the_rule():
    assert camp_npc(242498, "Reagent Bot") and camp_npc(None, "Reagent Bot", "", 9)
    assert camp_npc(None, "Field Repair Bot 74A", "", "9") and camp_npc(None, "Pexmit", "Someone's Minion")
    assert not camp_npc(None, "Reagent Bot", "", 7)  # (not a device: the name alone isn't it)
    for name, ctype in (("Fishbot 5000", 9), ("Techbot", 9), ("Homing Robot OOX-17/TN", 9), ("Cenarion Botanist", 7)):
        assert not camp_npc(None, name, "", ctype), name
    assert not camp_npc(1733, "Zggi", "Zardeth's Minion", 3)


def test_the_snapshots_reagent_bot_is_left_out_at_build_time():
    (bot,) = [r for r in server_rows() if r["guid"] == "7010002"]
    assert bot["id"] == "242498" and bot["name"] == "Reagent Bot" and bot["map"] == "2991"
    ft = {35: {"Faction": 35, "FactionGroup": 0, "FriendGroup": 0, "EnemyGroup": 0, "Enemies": [0], "Friend": [1, 2]}}
    alliance = {"Faction": 1, "FactionGroup": 3, "FriendGroup": 2, "EnemyGroup": 12, "Enemies": [0], "Friend": [0]}
    horde = {"Faction": 2, "FactionGroup": 5, "FriendGroup": 4, "EnemyGroup": 10, "Enemies": [0], "Friend": [0]}
    npcs, report = {}, defaultdict(int)
    renamed = dict(bot, id="999999", name="Spare Bot")  # (the rule, not only the list: another camp bot)
    _add_server(npcs, report, ft, alliance, horde, rows=[bot, renamed])
    assert npcs == {} and report["camp"] == 2
    t = {"Entry": "242498", "Name": "Reagent Bot", "SubName": "NULL", "NpcFlags": "4", "CreatureType": "9",
         "UnitFlags": "0", "ExtraFlags": "0"}  # (the dump's columns)
    assert _left_out(t, ft[35], {"guid": "1", "MovementType": "0"}, {}, alliance, horde) == "camp"


def test_stand_ins_and_logged_ones_are_dropped_too():
    npcs = {266901: {"name": "Pexmit", "sub": "Someone's Minion", "svc": "gv", "spawns": [], "from": "standin"},
            242498: {"name": "Reagent Bot", "sub": "", "svc": "v", "spawns": []},
            251537: {"name": "Uualia Suncrest", "sub": "General Goods", "svc": "v", "spawns": []}}
    report = defaultdict(int)
    _drop_camp(npcs, report)
    assert set(npcs) == {251537} and report["camp"] == 2
