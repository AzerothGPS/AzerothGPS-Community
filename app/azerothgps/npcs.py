"""Every friendly NPC, for the search (asked 2026-11-14: "the search function for repairs/trainers/etc should always
show for any NPC"; the user chose "Ship all NPCs": every friendly NPC searchable from the start, the old "NPCs are
player finds, never shipped" rule dropped; pins, herbs and ore still never ship).

From the CMaNGOS dump (hostile.py's DUMP): each creature spawn on the two continents whose NPC is friendly to the
Alliance or the Horde (the client's FactionTemplate against the players' own, 1 and 2), or neutral to both and
interactive (npcflag: a goblin town's vendor). Left out: the hostile ones, the ones nobody can talk to (no npcflag:
townsfolk, soldiers), guards and patrols with nothing to offer but gossip (the city places and the guards' own
directions cover those), critters, the unselectable and invisible ones (triggers), the ones a seasonal event spawns,
and placeholders by name. A spawn within SAME_YD of one of its NPC's kept is the same.

Each NPC: its creature id (Layers' `ns.db.npcs` key: the one learned by talking to it is the same NPC), its name and
subname as the game's English (names from the game stay untranslated), its services (npcflag: SERVICES), its trainer
kind (a class's file name, "MAGE"; a profession, "Mining"; "Weapon", "Riding", "Pet"), its side ("A", "H" or "B":
both), and its spawns: level (the continent, or Undercity's 10001 down there as Data/NpcFloors.lua tells it), x, y, z.
Search only: nothing routed or drawn. Packed into one string (`ns.NpcsPacked`) the addon reads at its first search
(Layers' `L.ShippedNpcs`), so the login costs nothing but the string.

Zephras Isle (level 2991, WoW Forever's own island in the sky) isn't in the 1.12 dump: its NPCs come from ISLE_FILE,
a snapshot of a WoW Forever world database's creature spawns there with something to offer (ISLE_SQL; numbers and
names only), read by the same rules with that database's newer npcflag bits (ISLE_SERVICES). Without them the
search found nothing of a kind on the isle and "nearest" sent the player off it (a player's report, 1.3.14).

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
ISLE_FILE = Path(__file__).parent / "data" / "isle_npcs.tsv"
ISLE = 2991
# (the query the snapshot was made with, on a TrinityCore-style world database; its columns renamed as ISLE_FILE's)
ISLE_SQL = ("SELECT c.guid, c.id, c.map, c.position_x, c.position_y, c.position_z, c.MovementType, t.name, t.subname, "
            "t.faction, IF(c.npcflag <> 0, c.npcflag, t.npcflag), t.type, t.unit_flags, t.flags_extra "
            "FROM creature c JOIN creature_template t ON t.entry = c.id "
            "WHERE c.map = 2991 AND (t.npcflag <> 0 OR c.npcflag <> 0)")
# that database's NPCFlags (newer than 1.12's) -> the services' letters
ISLE_SERVICES = ((0x1, "g"), (0x2, "q"), (0x80, "v"), (0x2000, "f"), (0x10, "t"), (0x4000, "h"), (0x10000, "i"),
                 (0x20000, "b"), (0x40000, "p"), (0x80000, "d"), (0x100000, "m"), (0x200000, "a"), (0x400000, "s"),
                 (0x1000, "r"))
ISLE_GUARD_FLAG = 0x8000  # (its flags_extra: a guard)
CLASS_TRAINER = re.compile(r"^(Warrior|Paladin|Hunter|Rogue|Priest|Shaman|Mage|Warlock|Druid) Trainer$", re.I)
NOISE = re.compile(r"\b(Trigger|DND|UNUSED|PH|Dummy|Visual|Invisible|Placeholder|Test|Bunny|Spawner)\b|Only GM|\[|\]",
                   re.I)


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
            if any(sl == level and math.hypot(sx - x, sy - y) <= SAME_YD for sl, sx, sy, _ in n["spawns"]):
                report["same spot"] += 1
                continue
            n["spawns"].append((level, x, y, z))
            report["kept"] += 1
    _add_isle(npcs, report, ft, alliance, horde)
    return npcs, dict(report)


def isle_rows(path: Path = ISLE_FILE) -> list[dict]:
    """ISLE_FILE's rows (tab-separated, a header line)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    keys = lines[0].split("	")
    return [dict(zip(keys, ln.split("	"))) for ln in lines[1:] if ln.strip()]


def isle_services(flags: int) -> str:
    return "".join(c for bit, c in ISLE_SERVICES if flags & bit)


def isle_trainer_kind(flags: int, sub: str) -> str:
    """A trainer's kind on the isle by its subname (the snapshot's trainer_class is 0 for all): "Mage Trainer" its
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


def _add_isle(npcs, report, ft, alliance, horde, rows=None):
    """Zephras Isle's NPCs (isle_rows) into `npcs`, by _left_out's rules: one already shipped (the Spirit Healer)
    gets the isle's spawns too."""
    for r in (rows if rows is not None else isle_rows()):
        if int(r["map"]) != ISLE:
            continue
        f = ft.get(int(r["faction"]))
        flags = int(r["npcflag"])
        extra = int(r["flags_extra"])
        t = {"Name": r["name"], "SubName": r["subname"] or "NULL", "NpcFlags": str(flags),
             "CreatureType": r["type"], "UnitFlags": r["unit_flags"],
             "ExtraFlags": str((GUARD_FLAG if extra & ISLE_GUARD_FLAG else 0) | (extra & INVISIBLE))}
        why = _left_out(t, f, {"guid": r["guid"], "MovementType": r["movement"]}, {}, alliance, horde)
        if why:
            report[why] += 1
            continue
        x, y, z = (round(float(r[k]), 1) for k in ("x", "y", "z"))
        n = npcs.get(int(r["id"]))
        if n is None:
            sub = r["subname"]
            svc = isle_services(flags)
            if "innkeeper" not in (r["name"] + " " + sub).lower():
                svc = svc.replace("i", "")
            n = npcs[int(r["id"])] = {"name": r["name"], "sub": sub, "svc": svc,
                                      "trainer": isle_trainer_kind(flags, sub), "side": side(f, alliance, horde),
                                      "spawns": []}
        if any(sl == ISLE and math.hypot(sx - x, sy - y) <= SAME_YD for sl, sx, sy, _ in n["spawns"]):
            report["same spot"] += 1
            continue
        n["spawns"].append((ISLE, x, y, z))
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
    out = ["-- GENERATED by `agps npcs --write` from the CMaNGOS dump's creatures and Zephras Isle's (isle_npcs.tsv).",
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
    return "\n".join(out) + "\n"
