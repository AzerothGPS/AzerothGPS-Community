"""Riverglades (uiMap 2548, WoW Forever's own zone) and the NPCs the 1.12 dump lacks (a scan, 2026-11-23).

Riverglades has no NPCs in the dump nor in the server snapshot, and the live client's quest POI, vignette and map-pin
tables have nothing there: what the client does have (its two flight masters and its places) ships as points of
interest, derived by the extract step (pipeline.taxi_pois, the area grid's town labels) into Data/Pois.lua. Its two
Powderfuse Port nodes have neither faction's map flag (not on either flight map yet), so they stay out, as the
retired "zzOLD" ones do.

Elsewhere the server snapshot (npcs.py's SERVER_FILE) had a dozen NPCs the dump lacks (Elwynn's
junior profession trainers, Stormwind's PvP quartermasters): they ship from the snapshot by the same rules, and
Npcs.lua's last line names them."""
import re
from collections import defaultdict

from azerothgps.paths import ADDON_DIR

POIS = ADDON_DIR / "Data" / "Pois.lua"
NPCS = ADDON_DIR / "Data" / "Npcs.lua"
RIVERGLADES = 16591
BOUNDS = (-9700.0, -6741.67, -6466.67, -1891.67)  # (Maps.lua's [2548]: x from, y from, x to, y to)


def _in_riverglades(x, y):
    return BOUNDS[0] <= x <= BOUNDS[2] and BOUNDS[1] <= y <= BOUNDS[3]


def test_riverglades_has_shipped_destinations():
    text = POIS.read_text(encoding="utf-8")
    flights = {(name, side) for x, y, name, side in
               re.findall(r'\{1,(-?[\d.]+),(-?[\d.]+),"([^"]+)",\d+,"(\w+)"', text) if _in_riverglades(float(x), float(y))}
    assert {("Rog'mar, Riverglades", "H"), ("Farholde Keep, Riverglades", "A")} <= flights
    places = re.findall(r'\{3,-?[\d.]+,-?[\d.]+,"([^"]+)",%d,\d+\}' % RIVERGLADES, text)
    assert len(places) >= 15 and {"Rog'mar", "Farholde Keep", "Eastwind Shore", "Powderfuse Port"} <= set(places)


class _Client:
    def __init__(self, taxi):
        self.taxi = taxi

    def table(self, name):
        assert name == "TaxiNodes"
        return self.taxi


def test_the_extract_step_derives_the_riverglades_flight_masters():
    from azerothgps.extract.pipeline import taxi_pois

    def node(i, name, flags, pos):
        return {"ID": i, "Name_lang": name, "Flags": flags, "ContinentID": 0, "Pos": [pos[0], pos[1], 20.0]}

    pois = taxi_pois(_Client([
        node(3203, "Rog'mar, Riverglades", 1026, (-7923.74, -4782.96)),
        node(3276, "Farholde Keep, Riverglades", 1025, (-9104.1, -4830.47)),
        node(3207, "zzOLDRiverglades, Farholde Keep", 1025, (-711.48, -515.48)),
        node(3274, "Powderfuse Port, Riverglades", 1024, (-8157.2, -5724.67))]))
    assert [(p["id"], p["factions"], p["wx"]) for p in pois] == [(3203, ["horde"], -7923.7),
                                                                 (3276, ["alliance"], -9104.1)]


def test_the_npcs_the_dump_lacks_ship_from_the_server_snapshot():
    text = NPCS.read_text(encoding="utf-8")
    server = set(text.rstrip().splitlines()[-1].split(": ", 1)[1].split())
    for nid, line in ((247226, "247226|Kelsey Fargo|Junior Mining Trainer|"), (248415, "248415|Tordrin Sternblade|"),
                      (12777, "12777|Captain Dirgehammer|Armor Quartermaster|")):
        assert str(nid) in server and re.search(r"^" + re.escape(line), text, re.M)
    assert "54" not in server  # (Corina Steele: the dump's)


def test_a_snapshot_spawn_the_dump_has_is_the_dumps():
    from azerothgps.npcs import _add_server

    side_both = {"Faction": 35, "FactionGroup": 0, "FriendGroup": 0, "EnemyGroup": 0, "Enemies": [0], "Friend": [1, 2]}
    alliance = {"Faction": 1, "FactionGroup": 3, "FriendGroup": 2, "EnemyGroup": 12, "Enemies": [0], "Friend": [0]}
    horde = {"Faction": 2, "FactionGroup": 5, "FriendGroup": 4, "EnemyGroup": 10, "Enemies": [0], "Friend": [0]}

    def row(i, name, x, event=0):
        return {"guid": str(i * 10 + int(x) % 7), "id": str(i), "map": "0", "x": str(x), "y": "100", "z": "50",
                "movement": "0", "name": name, "subname": "", "faction": "35", "npcflag": "128", "type": "7",
                "unit_flags": "0", "flags_extra": "0", "event": str(event)}

    npcs = {54: {"name": "Corina Steele", "sub": "", "svc": "v", "trainer": "", "side": "A",
                 "spawns": [(0, 1000.0, 100.0, 50.0)]}}
    report = defaultdict(int)
    _add_server(npcs, report, {35: side_both}, alliance, horde, rows=[
        row(54, "Corina Steele", 1030.0),  # (the dump's, its spot 30 yd off)
        row(99, "Corina Steele", 1020.0),  # (another id, the same name and place: the dump's)
        row(7, "New Vendor", 2000.0),
        row(8, "Fair Vendor", 3000.0, event=3)])  # (a seasonal one)
    assert report["in the dump"] == 2 and report["seasonal"] == 1 and report["kept"] == 1
    assert npcs[54]["spawns"] == [(0, 1000.0, 100.0, 50.0)] and 99 not in npcs and 8 not in npcs
    assert npcs[7]["from"] == "server" and npcs[7]["spawns"] == [(0, 2000.0, 100.0, 50.0)]


def test_a_both_sides_snapshot_npc_in_a_one_faction_town_takes_its_side():
    from azerothgps.npcs import _town_side

    stormwind = [(0, -8770.0, 420.0, "A"), (0, -8800.0, 450.0, "A"), (0, -8760.0, 400.0, "B")]
    assert _town_side(stormwind, 0, -8769.1, 402.6) == "A"
    assert _town_side(stormwind + [(0, -8790.0, 410.0, "H")], 0, -8769.1, 402.6) == "B"  # (a mixed town)
    assert _town_side(stormwind, 0, -5000.0, 400.0) == "B"  # (nobody near)
    text = NPCS.read_text(encoding="utf-8")
    assert "\n12777|Captain Dirgehammer|Armor Quartermaster|vr||A|" in text
