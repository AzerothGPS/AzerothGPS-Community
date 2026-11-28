"""Every friendly NPC, for the search (asked 2026-11-14: "the search function for repairs/trainers/etc should always
show for any NPC"; the user chose "Ship all NPCs": every friendly NPC searchable from the start, the old "NPCs are
player finds, never shipped" rule dropped; pins, herbs and ore still never ship).

From the CMaNGOS dump (hostile.py's DUMP): each creature spawn on the two continents whose NPC is friendly to the
Alliance or the Horde (the client's FactionTemplate against the players' own, 1 and 2), or neutral to both and
interactive (npcflag: a goblin town's vendor). Left out: the hostile ones, the ones nobody can talk to (no npcflag:
townsfolk, soldiers), guards and patrols with nothing to offer but gossip (the city places and the guards' own
directions cover those), critters, the unselectable and invisible ones (triggers), the ones a seasonal event spawns,
placeholders by name, and camp NPCs players put down (the Reagent Bot: camp_npc, from every source). A spawn within SAME_YD of one of its NPC's kept is the same.

Each NPC: its creature id (Layers' `ns.db.npcs` key: the one learned by talking to it is the same NPC), its name and
subname as the game's English (names from the game stay untranslated), its services (npcflag: SERVICES), its trainer
kind (a class's file name, "MAGE"; a profession, "Mining"; "Weapon", "Riding", "Pet"), its side ("A", "H" or "B":
both), and its spawns: level (the continent, or Undercity's 10001 down there as Data/NpcFloors.lua tells it), x, y, z.
Search only: nothing routed or drawn. Packed into one string (`ns.NpcsPacked`) the addon reads at its first search
(Layers' `L.ShippedNpcs`), so the login costs nothing but the string.

What the 1.12 dump lacks comes from SERVER_FILE, a snapshot of a WoW Forever world database's creature spawns with
something to offer on the two continents and Zephras Isle (SERVER_SQL; numbers and names only), read by the same
rules with that database's newer npcflag bits (SERVER_SERVICES):
- Zephras Isle (level 2991, WoW Forever's own island in the sky): all its NPCs. Without them the search found nothing
  of a kind on the isle and "nearest" sent the player off it (a player's report, 1.3.14).
- the continents: a spawn whose NPC (by id, or by name) the dump has within MATCH_YD on the same level is the dump's;
  the rest ship too (WoW Forever's own: Elwynn's junior profession trainers, Stormwind's PvP quartermasters; a
  scan for missing NPCs, 2026-11-23). Npcs.lua's last line lists the NPCs that came from the snapshot.
Riverglades (WoW Forever's own zone) has none in either: the client data's flight masters and places there ship
as points of interest (gen-addon-data's Data/Pois.lua), and its quest POI/vignette tables have nothing there.

Which NPCs stand still (item 104, 1.4.1): `ns.NpcsStill` lists the NPCs every spawn of which, in the dump and the
snapshot, has MovementType 0 (idle: no wander, no patrol). The height band (HeightBand.lua) measures the player's
height only against those; the logged and stand-in NPCs, whose movement isn't known, aren't listed.

`agps npcs` reports; `--write` writes Data/Npcs.lua. Run it again when the dump or the snapshot changes.
"""
from __future__ import annotations

import gzip
import math
import re
from collections import defaultdict
from pathlib import Path

from .hostile import DUMP, GUARD_FLAG, GUARD_NAME, _rows
from .paths import ADDON_DIR

FILE = ADDON_DIR / "Data" / "Npcs.lua"
SAME_YD = 1.0
UNDER_Z = 20  # (as npcfloors: Undercity's spawns are under this, the ruins' ground over it about 60)
UNDERCITY = 10001
ALLIANCE_FT, HORDE_FT = 1, 2  # (FactionTemplate: a human's, an orc's)
# creature_template.NpcFlags (1.12) -> the services' letters
SERVICES = ((0x1, "g"), (0x2, "q"), (0x4, "v"), (0x8, "f"), (0x10, "t"), (0x20, "h"), (0x80, "i"), (0x100, "b"),
            (0x200, "p"), (0x400, "d"), (0x800, "m"), (0x1000, "a"), (0x2000, "s"), (0x4000, "r"))
CRITTER = 8  # (CreatureType)
NOT_SELECTABLE = 0x2000000  # (UnitFlags)
INVISIBLE = 0x80  # (ExtraFlags)
WAYPOINTS = 2  # (MovementType: a patrol)
CLASSES = {1: "WARRIOR", 2: "PALADIN", 3: "HUNTER", 4: "ROGUE", 5: "PRIEST", 7: "SHAMAN", 8: "MAGE", 9: "WARLOCK",
           11: "DRUID"}
# a tradeskill trainer's subname -> its profession (the first that matches; "Journeyman Blacksmith", "Physician")
PROFESSIONS = (("alchem", "Alchemy"), ("blacksmith", "Blacksmithing"), ("armor crafter", "Blacksmithing"),
               ("weapon crafter", "Blacksmithing"), ("cook", "Cooking"), ("chef", "Cooking"), ("butcher", "Cooking"),
               ("enchant", "Enchanting"), ("engineer", "Engineering"), ("first aid", "First Aid"),
               ("physician", "First Aid"), ("surgeon", "First Aid"), ("fish", "Fishing"), ("herbal", "Herbalism"),
               ("leather", "Leatherworking"), ("miner", "Mining"), ("mining", "Mining"), ("skinn", "Skinning"),
               ("tailor", "Tailoring"))
SERVER_FILE = Path(__file__).parent / "data" / "server_npcs.tsv"
ISLE = 2991
TOWN_YD = 150.0  # (a snapshot NPC "both sides" stands with the dump's NPCs this near: their town's side, if one)
MATCH_YD = 40.0  # (a snapshot spawn this near one of the dump's same NPC is that one: the two databases' spots differ)
# (the query the snapshot was made with, read-only on a TrinityCore-style server's world database; its
# columns named as SERVER_FILE's header, "NULL" subnames written empty)
SERVER_SQL = ("SELECT c.guid AS guid, c.id AS id, c.map AS map, c.position_x AS x, c.position_y AS y, "
              "c.position_z AS z, c.MovementType AS movement, t.name AS name, t.subname AS subname, "
              "t.faction AS faction, IF(c.npcflag <> 0, c.npcflag, t.npcflag) AS npcflag, t.type AS type, "
              "t.unit_flags AS unit_flags, t.flags_extra AS flags_extra, "
              "IFNULL((SELECT MAX(e.eventEntry) FROM game_event_creature e WHERE e.guid = c.guid), 0) AS event "
              "FROM creature c JOIN creature_template t ON t.entry = c.id "
              "WHERE c.map IN (0, 1, 2991) AND (t.npcflag <> 0 OR c.npcflag <> 0) ORDER BY c.map, c.id, c.guid")
# that database's NPCFlags (newer than 1.12's) -> the services' letters
SERVER_SERVICES = ((0x1, "g"), (0x2, "q"), (0x80, "v"), (0x2000, "f"), (0x10, "t"), (0x4000, "h"), (0x10000, "i"),
                 (0x20000, "b"), (0x40000, "p"), (0x80000, "d"), (0x100000, "m"), (0x200000, "a"), (0x400000, "s"),
                 (0x1000, "r"))
SERVER_GUARD_FLAG = 0x8000  # (its flags_extra: a guard)
CLASS_TRAINER = re.compile(r"^(Warrior|Paladin|Hunter|Rogue|Priest|Shaman|Mage|Warlock|Druid) Trainer$", re.I)
NOISE = re.compile(r"\b(Trigger|DND|UNUSED|PH|Dummy|Visual|Invisible|Placeholder|Test|Bunny|Spawner)\b|Only GM|\[|\]",
                   re.I)
# Camp NPCs: put down by players, not the world's (Kooki3z, 1.4.2: "reagent bot needs to be drop as vendor locations
# these are camp vendors created by players and aren't always available"). Their spawns aren't marked apart in the
# world database (the Reagent Bot's guid is in the isle's own run, 7010001 the Spirit Healer's, 7010003 on the
# isle's quest NPCs), so they are told by what they are:
# - a mechanical "Bot" (CreatureType MECHANICAL, "Bot" a word of its name): an engineer's or a camp's device, the
#   Reagent Bot, the Field Repair Bot 74A (none of the world's own: the OOX homing robots, Fishbot 5000, Techbot);
# - a player's own minion (Wowhead's "Someone's Minion" for the owner's name: Pexmit, an imp vendor; an NPC's own,
#   "Zardeth's Minion", stays);
# - and CAMP_NPCS by id, the backstop for one the two tests miss (the stand-ins and logged NPCs: no CreatureType).
MECHANICAL = 9  # (CreatureType)
CAMP_BOT = re.compile(r"\bBot\b")
PLAYER_MINION = "Someone's Minion"
CAMP_NPCS = {242498: "Reagent Bot", 14337: "Field Repair Bot 74A", 266901: "Pexmit"}


def camp_npc(entry, name: str, sub: str = "", ctype=None) -> bool:
    """Whether an NPC is a camp NPC players put down (CAMP_NPCS's note): not shipped."""
    if entry is not None and int(entry) in CAMP_NPCS:
        return True
    if (sub or "").strip() == PLAYER_MINION:
        return True
    return ctype is not None and str(ctype).strip() != "" and int(ctype) == MECHANICAL and bool(CAMP_BOT.search(name))


def _drop_camp(npcs: dict, report) -> None:
    """Take the camp NPCs (camp_npc) out of `npcs`, whichever source added them (the stand-ins and logged ones too)."""
    for i in [i for i, n in npcs.items() if camp_npc(i, n["name"], n.get("sub", ""))]:
        del npcs[i]
        report["camp"] += 1


def _has(ids, faction: int) -> bool:
    return any(e and e == faction for e in ids)


def hostile(npc: dict, player: dict) -> bool:
    """The game's FactionTemplate IsHostileTo, the NPC's way round."""
    if _has(npc["Enemies"], player["Faction"]):
        return True
    if _has(npc["Friend"], player["Faction"]):
        return False
    return bool(npc["EnemyGroup"] & player["FactionGroup"]) or bool(player["EnemyGroup"] & npc["FactionGroup"])


def friendly(npc: dict, player: dict) -> bool:
    if _has(npc["Enemies"], player["Faction"]):
        return False
    if _has(npc["Friend"], player["Faction"]):
        return True
    return bool(npc["FriendGroup"] & player["FactionGroup"]) or bool(npc["FactionGroup"] & player["FriendGroup"])


def side(npc: dict, alliance: dict, horde: dict) -> str | None:
    """"A", "H", "B" (both), or None (hostile to both). Friendly to one only: that one's (an Alliance town's vendor
    a Horde player may see as neutral is still theirs); friendly to neither: by who it isn't hostile to."""
    fa, fh = friendly(npc, alliance), friendly(npc, horde)
    if fa and fh:
        return "B"
    if fa or fh:
        return "A" if fa else "H"
    ha, hh = hostile(npc, alliance), hostile(npc, horde)
    if ha and hh:
        return None
    return "B" if not (ha or hh) else ("A" if hh else "H")


def services(flags: int) -> str:
    return "".join(c for bit, c in SERVICES if flags & bit)


def trainer_kind(t: dict) -> str:
    """A trainer's kind: its class's file name, its profession, "Weapon", "Riding", "Pet"; "" for the rest."""
    if not int(t["NpcFlags"]) & 0x10:
        return ""
    sub = (t["SubName"] if t["SubName"] != "NULL" else "").lower()
    tt = int(t["TrainerType"] or 0)
    if "weapon master" in sub:
        return "Weapon"
    if tt == 0:
        return CLASSES.get(int(t["TrainerClass"] or 0), "")
    if tt == 1:
        return "Riding"
    if tt == 3:
        return "Pet"
    for word, prof in PROFESSIONS:
        if word in sub:
            return prof
    return ""


def faction_templates() -> dict[int, dict]:
    """The client's FactionTemplate rows by id (the WoW Forever client, as gen-addon-data reads it)."""
    from .extract.spike import ClientData
    from .paths import DEFAULT_WOW, data_dir

    cd = ClientData(DEFAULT_WOW, "wowf", data_dir() / "ref")
    return {r["ID"]: r for r in cd.table("FactionTemplate")}


def build(data_dir: Path, ft: dict[int, dict] | None = None, undercity=None):
    """(npcs {id: {name, sub, svc, trainer, side, spawns [(level, x, y, z)]}}, report {why left out: count}).
    `undercity(x, y, z)`: whether a spot on Eastern Kingdoms is down in Undercity (default: the addon's own, under
    the game harness)."""
    ft = ft if ft is not None else faction_templates()
    alliance, horde = ft[ALLIANCE_FT], ft[HORDE_FT]
    if undercity is None:
        undercity = _undercity()
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    tpl = {r["Entry"]: r for r in _rows(txt, "creature_template")}
    entries = defaultdict(list)  # (a spawn of one of several NPCs: creature id 0)
    for r in _rows(txt, "creature_spawn_entry"):
        entries[r["guid"]].append(r["entry"])
    events = {r["guid"]: int(r["event"]) for r in _rows(txt, "game_event_creature")}
    report: dict[str, int] = defaultdict(int)
    npcs: dict[int, dict] = {}
    for s in _rows(txt, "creature"):
        m = int(s["map"])
        if m not in (0, 1):
            continue
        for e in ([s["id"]] if s["id"] != "0" else entries.get(s["guid"], [])):
            t = tpl.get(e)
            f = t and ft.get(int(t["Faction"]))
            why = _left_out(t, f, s, events, alliance, horde)
            if why:
                report[why] += 1
                continue
            x, y, z = (round(float(s[k]), 1) for k in ("position_x", "position_y", "position_z"))
            level = UNDERCITY if m == 0 and z < UNDER_Z and undercity(x, y, z) else m
            n = npcs.get(int(e))
            if n is None:
                sub = t["SubName"] if t["SubName"] not in ("NULL", "") else ""
                svc = services(int(t["NpcFlags"]))
                if "innkeeper" not in (t["Name"] + " " + sub).lower():
                    svc = svc.replace("i", "")  # (the mount vendors have the flag too: "innkeeper" isn't them)
                n = npcs[int(e)] = {"name": t["Name"], "sub": sub, "svc": svc,
                                    "trainer": trainer_kind(t), "side": side(f, alliance, horde), "spawns": []}
            _moves(n, s["MovementType"])
            if any(sl == level and math.hypot(sx - x, sy - y) <= SAME_YD for sl, sx, sy, _ in n["spawns"]):
                report["same spot"] += 1
                continue
            n["spawns"].append((level, x, y, z))
            report["kept"] += 1
    _add_server(npcs, report, ft, alliance, horde, undercity=undercity)
    _add_logged(npcs, report)
    _add_standin(npcs, report)
    _drop_camp(npcs, report)
    return npcs, dict(report)


def _moves(n: dict, movement) -> None:
    """Note a spawn's MovementType on NPC `n`: `moves` False while every spawn seen stands still (0), True once one
    wanders, patrols or follows a path (lua_text's `ns.NpcsStill`)."""
    n["moves"] = n.get("moves", False) or str(movement).strip() not in ("0", "")


def still_ids(npcs: dict) -> list[int]:
    """The NPCs known to stand still at their spawns (every spawn MovementType 0; unknown movement: not listed)."""
    return sorted(i for i, n in npcs.items() if n.get("moves") is False and n.get("from") != "standin")


def _add_standin(npcs, report, doc=None):
    """WoW Forever's own NPCs none of the above has, from Wowhead's pages as stand-ins (overrides/standin_npcs.json:
    standin.py), marked `"from": "standin"`; last, so real data always wins."""
    from . import standin

    for _ in standin.add_standin(npcs, doc if doc is not None else standin.load(), log=print):
        report["stand-in"] += 1


def _add_logged(npcs, report, doc=None):
    """The NPCs logged in game that neither the dump nor the server snapshot has (overrides/logged_npcs.json:
    npcspots.py)."""
    from . import npcspots

    for nid in npcspots.add_logged(npcs, doc if doc is not None else npcspots.load_logged(), dump_ids=set(npcs),
                                   log=print):
        report["logged"] += 1


def server_rows(path: Path = SERVER_FILE) -> list[dict]:
    """SERVER_FILE's rows (tab-separated, a header line)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    keys = lines[0].split("	")
    return [dict(zip(keys, ln.split("	"))) for ln in lines[1:] if ln.strip()]


def server_services(flags: int) -> str:
    return "".join(c for bit, c in SERVER_SERVICES if flags & bit)


def server_trainer_kind(flags: int, sub: str) -> str:
    """A snapshot NPC's trainer kind by its subname (the snapshot's trainer_class is 0 for all): "Mage Trainer" its
    class's file name, a profession's by its word ("Alchemist", "Miner"), "Riding", "Pet"; "" for the rest."""
    if not flags & 0x10:
        return ""
    m = CLASS_TRAINER.match(sub)
    if m:
        return m.group(1).upper()
    low = sub.lower()
    if "weapon master" in low:
        return "Weapon"
    if "pet trainer" in low:
        return "Pet"
    if "riding" in low:
        return "Riding"
    for word, prof in PROFESSIONS + (("herbalist", "Herbalism"), ("skinner", "Skinning"), ("medic", "First Aid")):
        if word in low:
            return prof
    return ""


def _in_dump(npcs, by_name, i, name, level, x, y) -> bool:
    """Whether the dump's NPCs have this one (its id, else its name) within MATCH_YD on the same level."""
    base = lambda lv: 0 if lv == UNDERCITY else lv
    cands = ([npcs[i]] if i in npcs else []) + by_name.get(name, [])
    return any(base(sl) == base(level) and math.hypot(sx - x, sy - y) <= MATCH_YD
               for n in cands for sl, sx, sy, _ in n["spawns"])


def _town_side(town, level, x, y) -> str:
    """The side of the town or capital at a spot: "A" or "H" when the dump's NPCs within TOWN_YD are all of one
    faction (the server's "both" for Stormwind's PvP officers: Alliance's, a Horde player can't use them), else "B"."""
    sides = {sd for sl, sx, sy, sd in town if sl == level and math.hypot(sx - x, sy - y) <= TOWN_YD} - {"B"}
    return sides.pop() if len(sides) == 1 else "B"


def _add_server(npcs, report, ft, alliance, horde, rows=None, undercity=None):
    """SERVER_FILE's NPCs (server_rows) into `npcs`, by _left_out's rules: the isle's all (one already shipped, the
    Spirit Healer, gets the isle's spawns too), the continents' those the dump lacks (_in_dump); a new one is marked
    `"from": "server"`."""
    by_name = defaultdict(list)
    town = []  # (the dump's spawns with their side: a capital's or town's side around a spot)
    for n in npcs.values():
        by_name[n["name"]].append(n)
        town += [(sl, sx, sy, n["side"]) for sl, sx, sy, _ in n["spawns"]]
    for r in (rows if rows is not None else server_rows()):
        m = int(r["map"])
        f = ft.get(int(r["faction"]))
        flags = int(r["npcflag"])
        extra = int(r["flags_extra"])
        t = {"Entry": r["id"], "Name": r["name"], "SubName": r["subname"] or "NULL", "NpcFlags": str(flags),
             "CreatureType": r["type"], "UnitFlags": r["unit_flags"],
             "ExtraFlags": str((GUARD_FLAG if extra & SERVER_GUARD_FLAG else 0) | (extra & INVISIBLE))}
        why = _left_out(t, f, {"guid": r["guid"], "MovementType": r["movement"]},
                        {r["guid"]: int(r.get("event") or 0)}, alliance, horde)
        if why:
            report[why] += 1
            continue
        x, y, z = (round(float(r[k]), 1) for k in ("x", "y", "z"))
        level = UNDERCITY if m == 0 and z < UNDER_Z and undercity and undercity(x, y, z) else m
        i = int(r["id"])
        if m != ISLE and _in_dump(npcs, by_name, i, r["name"], level, x, y):
            report["in the dump"] += 1
            if i in npcs:  # (the server's word on its movement counts too: either moving, not still)
                _moves(npcs[i], r["movement"])
            continue
        n = npcs.get(i)
        if n is None:
            sub = r["subname"]
            svc = server_services(flags)
            if "innkeeper" not in (r["name"] + " " + sub).lower():
                svc = svc.replace("i", "")
            n = npcs[i] = {"name": r["name"], "sub": sub, "svc": svc, "trainer": server_trainer_kind(flags, sub),
                           "side": side(f, alliance, horde), "spawns": [], "from": "server"}
            if n["side"] == "B" and m != ISLE:
                n["side"] = _town_side(town, level, x, y)
        _moves(n, r["movement"])
        if any(sl == level and math.hypot(sx - x, sy - y) <= SAME_YD for sl, sx, sy, _ in n["spawns"]):
            report["same spot"] += 1
            continue
        n["spawns"].append((level, x, y, z))
        report["kept"] += 1


def _left_out(t, f, s, events, alliance, horde) -> str | None:
    """Why spawn `s` of NPC `t` (faction template `f`) isn't searchable, or None."""
    if not t or not f:
        return "unknown"
    sd = side(f, alliance, horde)
    if sd is None:
        return "hostile"
    flags = int(t["NpcFlags"])
    if not flags:
        return "nothing to talk about"
    if events.get(s["guid"], 0) > 0:
        return "seasonal"
    if int(t["CreatureType"]) == CRITTER:
        return "critter"
    if int(t["UnitFlags"]) & NOT_SELECTABLE or int(t["ExtraFlags"]) & INVISIBLE:
        return "unselectable"
    if NOISE.search(t["Name"]) or "|" in t["Name"] or "|" in t["SubName"]:
        return "placeholder"
    if camp_npc(t.get("Entry"), t["Name"], "" if t["SubName"] == "NULL" else t["SubName"], t["CreatureType"]):
        return "camp"
    if not flags & ~0x1:  # (gossip alone)
        if int(t["ExtraFlags"]) & GUARD_FLAG or GUARD_NAME.search(t["Name"]):
            return "guard"
        if int(s["MovementType"]) == WAYPOINTS:
            return "patrol"
    return None


_LUA = """
local ns = AGPS_NS
local N = ns.Nav
return function(x, y) return N.CityFloor(%d, x, y) ~= nil end
""" % UNDERCITY


def _undercity():
    from .gameharness import start

    lua, _ = start({"Data/Npcs.lua": ""})  # (not its own output: none yet, or an old one)
    at = lua.execute(_LUA)
    return lambda x, y, z: bool(at(x, y))


def lua_text(npcs: dict) -> str:
    """Data/Npcs.lua: one line an NPC in one long string, `id|name|sub|services|trainer|side|spawns`, its spawns
    `level x y z` split by ";"."""
    lines = []
    for i in sorted(npcs):
        n = npcs[i]
        spawns = ";".join(f"{lv} {x:.1f} {y:.1f} {z:.1f}" for lv, x, y, z in sorted(n["spawns"]))
        lines.append("|".join((str(i), n["name"], n["sub"], n["svc"], n["trainer"], n["side"], spawns)))
    body = "\n".join(lines)
    assert "]==]" not in body
    out = ["-- GENERATED by `agps npcs --write` from the CMaNGOS dump's creatures and a WoW Forever server snapshot's",
           "-- (server_npcs.tsv: Zephras Isle's, and the continents' the dump lacks).",
           "-- Do not edit by hand.",
           "-- Every friendly NPC (or neutral one with something to offer), for the search only (asked 2026-11-14,",
           "-- \"Ship all NPCs\"): one line each, id|name|subname|services|trainer|side|spawns, its spawns",
           "-- \"level x y z\" split by \";\". Services: g gossip, q quests, v vendor, f flight master, t trainer, h spirit",
           "-- healer, i innkeeper, b banker, p guild charters, d tabards, m battlemaster, a auctioneer, s stable master,",
           "-- r repairs. Side: A, H, or B (both). Read at the first search (Layers.lua's L.ShippedNpcs).",
           "local _, ns = ...",
           "ns.NpcsPacked = [==[",
           body,
           "]==]"]
    standin = sorted(i for i, n in npcs.items() if n.get("from") == "standin")
    if standin:  # (Wowhead's WoW Forever pages, unverified: overrides/standin_npcs.json, Layers' n.standin)
        out.append("-- Stand-ins (Wowhead's WoW Forever pages, unverified; real data replaces them by id):")
        out.append('ns.NpcsStandIn = "' + " ".join(map(str, standin)) + '"')
    # (item 104: the NPCs that stand still at their spawns, for the height band, HeightBand.lua)
    out.append("-- Standing still at their spawns (MovementType 0 everywhere; the height band's, HeightBand.lua):")
    out.append('ns.NpcsStill = "' + " ".join(map(str, still_ids(npcs))) + '"')
    server = sorted(i for i, n in npcs.items() if n.get("from") == "server")  # (the last line: tests read it)
    out.append("-- From the server snapshot: " + " ".join(map(str, server)))
    return "\n".join(out) + "\n"
