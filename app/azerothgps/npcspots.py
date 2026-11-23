"""Hand fixes to the shipped NPCs' spots (some of the dump's spawns aren't where the NPC stands in this game, and the
search sent players there): overrides/npc_spots.json, applied to Data/Npcs.lua by `agps npcs --write` and
`agps npc-spots --write`.

A fix is a spot marked in game: the player stood next to the NPC with it targeted and marked it (the game gives no
NPC's position, so the player's own is the NPC's). The marks come in as JSON (`agps npc-spots --import FILE`), a list
of {id, name, level, cont, x, y, z?, zone, time, client?}: `level` the player's level (Undercity's 10001 down there),
`cont` the continent, `z` the floor followed there when known (WoW Forever's own height is always 0), `time` the
mark's key (epoch seconds), `client` "live" for one made in the live game. Kept per NPC id:

    {"npcs": {"<id>": [{"name", "level", "x", "y", "z"?, "zone", "time", "live"}]}}

Applied to an NPC's spawns: each spot takes the place of the NPC's spawn nearest it on its level (or continent), so
an NPC with spawns in two towns has only the one it was marked by moved; the spawn keeps its height unless the mark
has one. Live-game marks win over the others for the same spawn (another server may place NPCs differently), then
the newest. A spot on a level the NPC has no spawn on is added as one; an NPC that isn't shipped is skipped.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .paths import ADDON_DIR, RESOURCES

FILE = RESOURCES / "overrides" / "npc_spots.json"
NPCS_LUA = ADDON_DIR / "Data" / "Npcs.lua"
LEVELS = (0, 1, 2991, 10001)  # (the shipped spawns' levels: Data/Npcs.lua; Zephras Isle's since 1.3.14)


def load(path: Path = FILE) -> dict:
    p = Path(path)
    if not p.exists():
        return {"npcs": {}}
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc.setdefault("npcs", {})
    return doc


def save(doc: dict, path: Path = FILE) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ordered = {"npcs": {k: sorted(v, key=lambda s: s["time"]) for k, v in
                        sorted(doc["npcs"].items(), key=lambda kv: int(kv[0]))}}
    p.write_text(json.dumps(ordered, indent=1) + "\n", encoding="utf-8", newline="\n")


def times(path: Path = FILE) -> set[int]:
    """The marks' times the overrides have (the watcher hands over only marks not in them)."""
    return {int(s["time"]) for spots in load(path)["npcs"].values() for s in spots}


def _level(m: dict) -> int | None:
    """The shipped level a mark is on: its own (Undercity's 10001), else its continent."""
    for k in ("level", "cont"):
        v = m.get(k)
        if v is not None and int(v) in LEVELS:
            return int(v)
    return None


def spot_of(m: dict) -> dict | None:
    """A mark (the import's JSON) as an override spot, or None when it isn't one (no id, no spot, a level the data
    hasn't)."""
    try:
        nid, x, y, t = int(m["id"]), float(m["x"]), float(m["y"]), int(m["time"])
        z = float(m["z"]) if m.get("z") is not None else None
    except (KeyError, TypeError, ValueError):
        return None
    level = _level(m)
    if level is None or nid <= 0:
        return None
    s = {"name": str(m.get("name") or ""), "level": level, "x": round(x, 1), "y": round(y, 1)}
    if z:  # (the floor followed there; the game's own height is always 0 here: none)
        s["z"] = round(z, 1)
    s["zone"] = str(m.get("zone") or "")
    s["time"] = t
    s["live"] = m.get("client") == "live"
    return nid, s


def merge_marks(marks: list[dict], path: Path = FILE) -> list[tuple[int, dict]]:
    """Marks into the overrides (by their time: one already there is skipped). The new ones, (id, spot)."""
    doc = load(path)
    have = {int(s["time"]) for spots in doc["npcs"].values() for s in spots}
    new = []
    for m in marks:
        got = spot_of(m)
        if not got:
            continue
        nid, s = got
        if s["time"] in have:
            continue
        have.add(s["time"])
        doc["npcs"].setdefault(str(nid), []).append(s)
        new.append((nid, s))
    if new:
        save(doc, path)
    return new


def _order(s: dict):
    return (bool(s.get("live")), int(s["time"]))  # (live last: it wins; then the newest)


def apply(npcs: dict, doc: dict, log=None) -> dict:
    """The override spots put into `npcs` ({id: {..., spawns [(level, x, y, z)]}}, npcs.build's) in place. Returns
    {id: [(spot, yards moved or None when added)]} for those applied."""
    out: dict[int, list] = {}
    for key, spots in doc.get("npcs", {}).items():
        nid = int(key)
        n = npcs.get(nid)
        if n is None:
            if log:
                log(f"npc {nid} ({spots[0].get('name', '?')}): not in the shipped data, skipped")
            continue
        spawns = list(n["spawns"])
        orig = list(spawns)
        taken: dict[int, dict] = {}  # (spawn index -> the spot that moves it)
        for s in sorted(spots, key=_order):
            best, bd = None, math.inf
            for i, (lv, x, y, _) in enumerate(orig):
                if lv == s["level"]:
                    d = math.hypot(x - s["x"], y - s["y"])
                    if d < bd:
                        best, bd = i, d
            if best is None:
                orig.append((s["level"], s["x"], s["y"], s.get("z", 0.0)))
                spawns.append(orig[-1])
                taken[len(orig) - 1] = s
                out.setdefault(nid, []).append((s, None))
                continue
            taken[best] = s  # (a later one for the same spawn wins: live ones come last)
            lv, x, y, z = orig[best]
            spawns[best] = (lv, s["x"], s["y"], s.get("z", z))
            out.setdefault(nid, []).append((s, round(bd, 1)))
        n["spawns"] = spawns
    return out


def parse_lua(text: str) -> tuple[str, dict]:
    """Data/Npcs.lua's NPCs ({id: {name, sub, svc, trainer, side, spawns}}), and its text before the packed lines."""
    head, rest = text.split("ns.NpcsPacked = [==[\n", 1)
    body = rest.split("]==]", 1)[0]
    npcs = {}
    for line in body.splitlines():
        if not line:
            continue
        i, name, sub, svc, trainer, side, spawns = line.split("|", 6)
        sp = []
        for one in spawns.split(";"):
            lv, x, y, z = one.split(" ")
            sp.append((int(lv), float(x), float(y), float(z)))
        npcs[int(i)] = {"name": name, "sub": sub, "svc": svc, "trainer": trainer, "side": side, "spawns": sp}
    return head, npcs


def patch_lua(text: str, doc: dict, log=None) -> tuple[str, dict]:
    """Data/Npcs.lua's text with the override spots put in (the dump not needed: only the spawns marked change).
    Spots already in are moved onto themselves, so patching again changes nothing."""
    from .npcs import lua_text

    _, npcs = parse_lua(text)
    applied = apply(npcs, doc, log=log)
    return lua_text(npcs), applied
