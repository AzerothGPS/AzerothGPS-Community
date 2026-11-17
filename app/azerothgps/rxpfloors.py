"""The floors of RestedXP's and Zygor's guide steps where floors lie over each other (asked 2026-11-08, RestedXP Route;
Zygor's too, 2026-11-09: "use it for both").

RestedXP's waypoints have no height, and over stacked floors (Undercity's rings under its walkways, the Cleft of Shadow
under the Drag, upstairs in Aldrassil, an inn's upper floor) a stop with none goes on the wrong floor: "Talk to Neeru
Fireblade" was routed 600 yd round by the Drag over her from 55 yd off. Guessing by the player's own floor is wrong one
time in four along the guides, so each such waypoint's height is shipped: the height of its step's NPC (`.target`, by
name or `Name::id`) from the CMaNGOS dump's spawns, within TRUTH_YD of the waypoint. Heights only, keyed by RestedXP's
own waypoints (the user, 2026-11-08: an exception to "no shipped NPC data", for RestedXP Route only: no names, nothing
drawn); read by RestedXP.lua's X.Height and Zygor.lua's Tick.

`agps rxp-floors` reports; `--write` writes Data/GuideFloors.lua. Run it again when RestedXP's or Zygor's guides change.
Zygor's guides (Guides-Forever, plain text): each `step`'s lines, `talk Name##id` (and `kill`, `clicknpc`) its NPCs,
`accept`/`turnin Title##qid` its quests, `|goto Zone[/floor] x,y` its waypoints (the same zone-percent kind).
"""
from __future__ import annotations

import gzip
import math
import re
from pathlib import Path

from .cityplaces import map_bounds
from .hostile import DUMP, _rows
from .paths import ADDON_DIR, DEFAULT_FLAVOR, DEFAULT_WOW

FILE = ADDON_DIR / "Data" / "GuideFloors.lua"
DEFAULT_RXP = DEFAULT_WOW / DEFAULT_FLAVOR / "Interface" / "AddOns" / "RXPGuides"
DEFAULT_ZYGOR = DEFAULT_WOW / DEFAULT_FLAVOR / "Interface" / "AddOns" / "ZygorGuidesViewerForever"
GUIDE_LIST = "Guides/GuideList-forever.xml"  # (the guides WoW Forever loads: RXPGuides.toc's camelot list)
STACK_YD, STACK_Z = 15, 8  # (roads within STACK_YD on floors STACK_Z apart: floors over each other there)
TRUTH_YD = 25  # (the step's NPC this near its waypoint)

GOTO = re.compile(r"^\s*\.(?:goto|waypoint)\s+(\S+)")
TARGET = re.compile(r"^\s*\.target\s+\+?(.+?)\s*$")
QUEST = re.compile(r"^\s*\.(accept|turnin)\s+(\d+)")
WORLD = re.compile(r"(\d+)/(\d+),(-?\d+(?:\.\d+)?)[\d.]*,(-?\d+(?:\.\d+)?)")
Z_GOTO = re.compile(r"\bgoto\s+([A-Za-z'][^/|\d]*?)(?:/\d+)?\s+(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)")
Z_NPC = re.compile(r"^\s*(?:talk|kill|clicknpc)\s+([^#|]+?)##(\d+)")
Z_QUEST = re.compile(r"^\s*(accept|turnin)\s+[^#|]*##(\d+)")


def guide_files(rxp: Path) -> list[Path]:
    text = (rxp / GUIDE_LIST).read_text(encoding="utf-8", errors="replace")
    return [rxp / f.replace("\\", "/") for f in re.findall(r'<Script file="([^"]+)"', text) if (rxp / f).is_file()]


def _map_names() -> dict:
    import lupa

    lua = lupa.LuaRuntime()
    lua.execute("ns = {}")
    lua.eval("function(src) return assert(load(src)) end")((ADDON_DIR / "Data" / "Maps.lua").read_text(encoding="utf-8"))(
        "AzerothGPS", lua.globals().ns)
    M = lua.globals().ns.Maps
    out = {}
    for k in M.keys():
        if M[k].bounds:
            out.setdefault(str(M[k].name), int(k))
    return out


def where(arg: str, maps: dict, names: dict):
    """A .goto's (uiMap, x, y) in AzerothGPS's world yards, or None: "map/instance,Y,X" (HereBeDragons' world: its
    second number is AzerothGPS's y), else "Zone or uiMap,x%,y%"."""
    arg = arg.split("--")[0]
    m = WORLD.match(arg)
    if m:
        return int(m.group(1)), float(m.group(4)), float(m.group(3))
    parts = arg.split(",")
    if len(parts) < 3:
        return None
    ui = int(parts[0]) if parts[0].isdigit() else names.get(parts[0])
    if ui not in maps:
        return None
    try:
        px, py = float(parts[1]), float(parts[2])
    except ValueError:
        return None
    _, b = maps[ui]
    return ui, b[2] - py / 100 * (b[2] - b[0]), b[3] - px / 100 * (b[3] - b[1])


def guide_steps(rxp: Path, maps: dict) -> list[dict]:
    """Each step of the guides: its waypoints and its NPCs (`targets`)."""
    names = _map_names()
    steps = []
    for f in guide_files(rxp):
        cur = None
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\s*step\b", ln):
                cur = {"file": f.name, "gotos": [], "targets": [], "quests": []}
                steps.append(cur)
            elif cur is not None:
                g = GOTO.match(ln)
                w = g and where(g.group(1), maps, names)
                if w:
                    cur["gotos"].append(w)
                t = TARGET.match(ln)
                if t:
                    cur["targets"] += [s.strip() for s in t.group(1).split("<<")[0].split(",") if s.strip()]
                q = QUEST.match(ln)
                if q:
                    cur["quests"].append((q.group(1), q.group(2)))
    return steps


def zygor_steps(zdir: Path, maps: dict) -> list[dict]:
    """Each step of Zygor's guides (every file under Guides-Forever): its waypoints, NPCs (`targets`, as
    "Name::id") and quests, as guide_steps'."""
    names = _map_names()
    steps = []
    for f in sorted((zdir / "Guides-Forever").rglob("*.lua")):
        cur = None
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\s*step\b", ln):
                cur = {"file": f.name, "gotos": [], "targets": [], "quests": []}
                steps.append(cur)
            elif cur is not None:
                for g in Z_GOTO.finditer(ln):
                    w = where(f"{g.group(1).strip()},{g.group(2)},{g.group(3)}", maps, names)
                    if w:
                        cur["gotos"].append(w)
                t = Z_NPC.match(ln)
                if t:
                    cur["targets"].append(f"{t.group(1).strip()}::{t.group(2)}")
                q = Z_QUEST.match(ln)
                if q:
                    cur["quests"].append((q.group(1), q.group(2)))
    return [s for s in steps if s["gotos"]]


def npc_spawns(data_dir: Path) -> dict:
    """Every NPC's spawns (map, x, y, z), by its name (lower case) and by "#entry"; and the quests' NPCs: "accept <id>"
    (who gives it) and "turnin <id>" (who takes it), their entries."""
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    name = {r["Entry"]: r["Name"] for r in _rows(txt, "creature_template")}
    out: dict = {}
    for r in _rows(txt, "creature"):
        v = (int(r["map"]), float(r["position_x"]), float(r["position_y"]), float(r["position_z"]))
        out.setdefault("#" + r["id"], []).append(v)
        if r["id"] in name:
            out.setdefault(name[r["id"]].lower(), []).append(v)
    for table, kind in (("creature_questrelation", "accept"), ("creature_involvedrelation", "turnin")):
        for r in _rows(txt, table):
            out.setdefault(f"{kind} {r['quest']}", []).append(r["id"])
    return out


def build(rxp: Path | None, data_dir: Path, zygor: Path | None = None):
    """(entries [(level, x, y, z)], report): each waypoint over stacked floors with its NPC's height (RestedXP's
    guides, and Zygor's when `zygor` is its addon folder)."""
    from .gameharness import start

    maps = map_bounds()
    steps = guide_steps(rxp, maps) if rxp and rxp.is_dir() else []
    if zygor and (zygor / "Guides-Forever").is_dir():
        steps += zygor_steps(zygor, maps)
    spawns = npc_spawns(data_dir)  # (before the spots: their quests' NPCs)
    lua, ns = start()
    R, X = ns.Router, ns.RestedXP
    spots: dict = {}
    for s in steps:
        for ui, x, y in s["gotos"]:
            sp = spots.setdefault((ui, round(x, 1), round(y, 1)), {"targets": set()})
            sp["targets"].update(s["targets"])
            if not s["targets"]:  # (a step naming no NPC: its quests' givers and takers)
                for kind, qid in s["quests"]:
                    sp["targets"].update("::" + e for e in spawns.get(f"{kind} {qid}", []))
    entries, stacked, untold = [], 0, []
    for (ui, x, y), sp in sorted(spots.items()):
        cont = maps[ui][0]
        level = X.Cont(lua.table(wx=y, wy=x, instance=cont, zone=ui))
        hs = R.HeightsNear(level, x, y, STACK_YD)
        zs = [h.z for h in hs.values()] if hs else []
        if not zs or max(zs) - min(zs) <= STACK_Z:
            continue
        stacked += 1
        best = None
        for t in sp["targets"]:
            nm, _, tid = t.partition("::")
            for m, sx, sy, sz in spawns.get(nm.strip().lower(), []) + spawns.get("#" + tid.strip(), []):
                d = math.hypot(sx - x, sy - y)
                if m == cont and d <= TRUTH_YD and (best is None or d < best[0]):
                    best = (d, sz)
        if best:
            entries.append((int(level), x, y, round(best[1], 1)))
        else:
            untold.append((ui, x, y, sorted(sp["targets"])))
    report = {"steps": len(steps), "spots": len(spots), "stacked": stacked, "heights": len(entries), "untold": untold}
    return entries, report


def lua_text(entries, rxp_version: str, zygor_version: str | None = None) -> str:
    src = f"RestedXP Guides {rxp_version}" + (f" and Zygor Guides Viewer {zygor_version}" if zygor_version else "")
    out = [f"-- GENERATED by `agps rxp-floors --write` from {src}. Do not edit by hand.",
           "-- RestedXP's and Zygor's guide waypoints over stacked floors and their heights (the game's): RestedXP.lua's X.Height, Zygor.lua.",
           "-- Per level, x, y, z each.",
           "local _, ns = ...",
           "ns.GuideFloors = {"]
    by: dict = {}
    for level, x, y, z in entries:
        by.setdefault(level, []).append(f"{x:.1f},{y:.1f},{z:.1f}")
    for level in sorted(by):
        out.append(f"  [{level}] = {{ " + ", ".join(by[level]) + " },")
    out.append("}")
    return "\n".join(out) + "\n"


def rxp_version(rxp: Path) -> str:
    m = re.search(r"^## Version:\s*(\S+)", (rxp / "RXPGuides.toc").read_text(encoding="utf-8", errors="replace"), re.M)
    return m.group(1) if m else "?"


def zygor_version(zdir: Path) -> str | None:
    tocs = sorted(zdir.glob("*.toc")) if zdir and zdir.is_dir() else []
    for t in tocs:
        m = re.search(r"^## Version:\s*(\S+)", t.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            return m.group(1)
    return None
