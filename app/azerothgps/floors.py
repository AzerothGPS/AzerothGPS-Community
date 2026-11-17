"""NPCs and quest objectives off the ground floor: upstairs in a building, down in a cellar, up a tower (asked
2026-10-06: "trainers in Brill being upstairs in the inn and quest turn-ins downstairs ... locate all places with NPCs
on different levels or quest objectives higher or lower on the Z axis").

From the CMaNGOS dump (data/thirdparty): every NPC that offers something (quests, training, a vendor, the inn, the
bank, flights; NpcFlags, or a quest's giver or ender) and every quest objective's creatures and objects (the quest's
ReqCreatureOrGOId: a creature's spawns, or a game object's), each spawn's height against the terrain under it (the
ADTs: caves.Ground), and the building it's in (buildings.buildings: the placed models, not the capitals' or caves').

- **Up:** at least FLOOR_YD over the terrain, inside a building (upstairs, a tower's top).
- **Down:** at least FLOOR_YD under it, inside a building (a cellar) or not (under the ground: a crypt, a cave).
- Undercity (its own level, Data/Cities.lua) and the capitals' models (their own floors, Data/Capitals.lua) are counted
  apart: their floors are known already.

`agps floors` writes data/debug/floors/report.md and floors.json. For finding them and planning only: nothing here goes
into the addon's data.
"""

from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from .hostile import DUMP, _rows

FLOOR_YD = 3.0  # this far over or under the terrain: another floor (a floor is 3-5 yd in an inn)
NPC_FLAGS = {1: "gossip", 2: "quests", 4: "vendor", 8: "flight master", 16: "trainer", 32: "spirit healer",
             64: "spirit guide", 128: "innkeeper", 256: "banker", 512: "petition", 1024: "tabard",
             2048: "battlemaster", 4096: "auctioneer", 8192: "stable master", 16384: "repair"}  # (1.12's NpcFlags)
# around Undercity (its own level) and the capitals: counted apart
UNDERCITY = (0, 1150.0, -300.0, 2000.0, 800.0, 20.0)  # cont, x0, y0, x1, y1, under this height


def _roles(flags: int, quest: bool) -> list[str]:
    """What an NPC offers, by its flags (1.12's) and whether it gives or takes quests; gossip alone isn't anything."""
    out = {v for k, v in NPC_FLAGS.items() if flags & k and v != "gossip"}
    if quest:
        out.add("quests")
    return sorted(out)


def load(data_dir: Path) -> dict:
    """The dump's NPCs that offer something, quest objectives' creatures and objects, and their spawns on 0 and 1."""
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    tmpl = {int(r["Entry"]): r for r in _rows(txt, "creature_template")}
    gives, ends = defaultdict(set), defaultdict(set)
    for r in _rows(txt, "creature_questrelation"):
        gives[int(r["id"])].add(int(r["quest"]))
    for r in _rows(txt, "creature_involvedrelation"):
        ends[int(r["id"])].add(int(r["quest"]))
    quests = {}
    for r in _rows(txt, "quest_template"):
        objs = []
        for k in range(1, 5):
            v = int(r.get(f"ReqCreatureOrGOId{k}") or 0)
            if v:
                objs.append(v)
        quests[int(r["entry"])] = {"title": r["Title"], "level": int(r.get("QuestLevel") or 0), "objectives": objs}
    cspawns, gspawns = defaultdict(list), defaultdict(list)
    for r in _rows(txt, "creature"):
        if int(r["map"]) in (0, 1):
            cspawns[int(r["id"])].append((int(r["map"]), float(r["position_x"]), float(r["position_y"]),
                                          float(r["position_z"])))
    for r in _rows(txt, "gameobject"):
        if int(r["map"]) in (0, 1):
            gspawns[int(r["id"])].append((int(r["map"]), float(r["position_x"]), float(r["position_y"]),
                                          float(r["position_z"])))
    gnames = {int(r["entry"]): r["name"] for r in _rows(txt, "gameobject_template")} if "gameobject_template" in txt else {}
    return {"tmpl": tmpl, "gives": gives, "ends": ends, "quests": quests, "cspawns": cspawns, "gspawns": gspawns,
            "gnames": gnames}


def _in_undercity(cont, x, y, z) -> bool:
    c, x0, y0, x1, y1, zmax = UNDERCITY
    return cont == c and x0 < x < x1 and y0 < y < y1 and z < zmax


def classify(cd, d: dict, log=print) -> dict:
    """Each interesting spawn's place against the terrain and the buildings: {"npcs": [...], "objectives": [...]}."""
    from .buildings import buildings
    from .capitals import CAPITALS
    from .caves import Ground
    from .interiors import placements

    B = 100.0  # (the buildings' bounds bucketed by this many yards, for the lookups)
    capital_uids = {uid for c in CAPITALS for uid in c.wmos}
    out_npcs, out_obj = [], []
    for cont in (0, 1):
        ground = Ground(cd, cont)
        index: dict = defaultdict(list)
        for p in buildings(cd, cont):
            x0, y0, x1, y1 = p.bounds
            for i in range(int(math.floor(x0 / B)), int(math.floor(x1 / B)) + 1):
                for j in range(int(math.floor(y0 / B)), int(math.floor(y1 / B)) + 1):
                    index[(i, j)].append((x0, y0, x1, y1, p.uid))
        caps = [p.bounds for p in placements(cd, cont) if p.uid in capital_uids]

        def where_all(pts):
            """[(kind, off, building)] for [(x, y, z)]: the terrain sampled at once."""
            if not pts:
                return []
            X = np.array([p[0] for p in pts])
            Y = np.array([p[1] for p in pts])
            h, _walkable = ground.sample(X, Y)
            res = []
            for (x, y, z), gz in zip(pts, h):
                gz = float(gz) if np.isfinite(gz) else None
                inb = next((uid for x0, y0, x1, y1, uid in index.get((int(math.floor(x / B)), int(math.floor(y / B))), ())
                            if x0 <= x <= x1 and y0 <= y <= y1), None)
                cap = any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in caps)
                off = None if gz is None else z - gz
                if _in_undercity(cont, x, y, z):
                    kind = "undercity"
                elif cap:
                    kind = "capital"
                elif off is None:
                    kind = "unknown"
                elif off >= FLOOR_YD and inb is not None:
                    kind = "up"
                elif off <= -FLOOR_YD:
                    kind = "down"
                else:
                    kind = "ground"
                res.append((kind, off, inb))
            return res

        rows = []
        for e, t in d["tmpl"].items():
            roles = _roles(int(t.get("NpcFlags") or 0), e in d["gives"] or e in d["ends"])
            if not roles:
                continue
            for c, x, y, z in d["cspawns"].get(e, ()):
                if c == cont:
                    rows.append((e, t, roles, x, y, z))
        for (e, t, roles, x, y, z), (kind, off, inb) in zip(rows, where_all([(r[3], r[4], r[5]) for r in rows])):
            out_npcs.append({"npc": e, "name": t["Name"], "title": t.get("SubName") or "", "roles": roles,
                             "cont": cont, "x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                             "off": None if off is None else round(off, 1), "kind": kind, "building": inb,
                             "gives": len(d["gives"].get(e, ())), "ends": len(d["ends"].get(e, ()))})
        log(f"  [{cont}] {len(rows)} NPC spawns that offer something")
        nq = 0
        for q, info in d["quests"].items():
            for o in info["objectives"]:
                spawns = d["cspawns"].get(o, ()) if o > 0 else d["gspawns"].get(-o, ())
                spawns = [s for s in spawns if s[0] == cont][:200]
                if not spawns:
                    continue
                nq += 1
                kinds: dict = defaultdict(int)
                offs = []
                for kind, off, _ in where_all([(s[1], s[2], s[3]) for s in spawns]):
                    kinds[kind] += 1
                    if off is not None:
                        offs.append(off)
                name = d["tmpl"][o]["Name"] if o > 0 and o in d["tmpl"] else d["gnames"].get(-o, str(o))
                out_obj.append({"quest": q, "title": info["title"], "level": info["level"], "cont": cont,
                                "target": name, "creature": o > 0, "spawns": len(spawns), "kinds": dict(kinds),
                                "median_off": round(float(np.median(offs)), 1) if offs else None})
        log(f"  [{cont}] {nq} quest objectives with spawns")
    return {"npcs": out_npcs, "objectives": out_obj}


def report(res: dict, out: Path) -> str:
    """The report (Markdown): counts, then the NPCs upstairs and downstairs by town, then the quests whose objectives
    are mostly up or down."""
    from .townplaces import _labels

    labels = _labels("23")
    npcs = res["npcs"]
    lines = ["# NPCs and quest objectives off the ground floor", "",
             f"From the CMaNGOS dump; `agps floors` (app/azerothgps/floors.py). A floor: {FLOOR_YD} yd over or under "
             "the terrain.", ""]
    count = defaultdict(int)
    for o in npcs:
        count[o["kind"]] += 1
    lines += ["## NPCs that offer something", "",
              ", ".join(f"{k}: {v}" for k, v in sorted(count.items(), key=lambda kv: -kv[1])), ""]

    def town(o):
        best = None
        for x, y, name in labels.get(o["cont"], ()):
            dd = math.hypot(x - o["x"], y - o["y"])
            if best is None or dd < best[0]:
                best = (dd, name)
        return best[1] if best and best[0] < 400 else "(the wilds)"

    for kind, head in (("up", "Upstairs (or up a tower)"), ("down", "Down (a cellar, a crypt, under the ground)")):
        group = defaultdict(list)
        for o in npcs:
            if o["kind"] == kind:
                group[(o["cont"], town(o))].append(o)
        lines += [f"### {head}: {sum(len(v) for v in group.values())} in {len(group)} places", ""]
        for (cont, name), lst in sorted(group.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            who = "; ".join(f"{o['name']}{' <' + o['title'] + '>' if o['title'] and o['title'] != 'NULL' else ''}"
                            f" ({', '.join(o['roles'])}, {o['off']:+.0f} yd)" for o in lst[:8])
            more = f" and {len(lst) - 8} more" if len(lst) > 8 else ""
            lines.append(f"- **{name}** ({'Kalimdor' if cont == 1 else 'Eastern Kingdoms'}): {who}{more}")
        lines.append("")
    obj = res["objectives"]
    up = [o for o in obj if o["kinds"].get("up", 0) > o["spawns"] / 2]
    down = [o for o in obj if o["kinds"].get("down", 0) > o["spawns"] / 2]
    lines += ["## Quest objectives", "",
              f"{len(obj)} objectives with spawns on the continents; mostly upstairs: {len(up)}, mostly under the "
              f"ground or in a cellar: {len(down)}.", ""]
    for head, lst in (("Mostly upstairs", up), ("Mostly down", down)):
        lines += [f"### {head}", ""]
        for o in sorted(lst, key=lambda o: o["level"])[:80]:
            lines.append(f"- {o['title']} (level {o['level']}): {o['target']}, {o['spawns']} spawn(s), "
                         f"{o['median_off']:+.0f} yd")
        if len(lst) > 80:
            lines.append(f"- ... and {len(lst) - 80} more (floors.json)")
        lines.append("")
    text = "\n".join(lines)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(text, encoding="utf-8")
    (out / "floors.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return text
