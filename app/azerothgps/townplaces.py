"""The starting zones' towns' service locations (ns.TownPlaces, at the end of Data/CityPlaces.lua).

Outside the capitals, the guards who give directions are the six starting zones' (asked 2026-10-04: "some places have
guards outside of major cities for directions to trainers, for example in Dolanaar"): Elwynn's Stormwind Guards
(Goldshire), Dun Morogh's Mountaineers (Kharanos), Teldrassil's Sentinels (Dolanaar), Tirisfal's Deathguards (Brill),
Mulgore's Braves (Bloodhoof Village), Durotar's Razor Hill Grunts (Razor Hill). Each one's directions menu (the
CMaNGOS dump's gossip_menu_option, its submenus) marks a point of interest for each place: those spots, in world yards,
each named by its service and the town it's in ("Dolanaar Hunter Trainer"), the height of its NPC (the spawn nearest
that says the service). A spot in a capital (the Goldshire guard's way to Stormwind's bank) is left to the capital's
places. Written with `agps city-places --towns`.
"""

from __future__ import annotations

import gzip
import math
import re
from pathlib import Path

from .cityplaces import CITIES, NEAR_YD, matches
from .hostile import DUMP, _rows
from .paths import ADDON_DIR

# the zone guards' directions menus: menu -> (the zone's uiMap, continent, its town, faction)
MENUS = {
    3506: (1429, 0, "Goldshire", "Alliance"),
    3533: (1426, 0, "Kharanos", "Alliance"),
    3580: (1438, 1, "Dolanaar", "Alliance"),
    3356: (1420, 0, "Brill", "Horde"),
    3331: (1412, 1, "Bloodhoof Village", "Horde"),
    3285: (1411, 1, "Razor Hill", "Horde"),
}
TOWN_YD = 350.0  # a spot this close to the guard's town is in it; further, the nearest town on the map
# the menu's words for a place -> its service as named in the capitals' places
SERVICE = {"inn": "Inn", "the inn": "Inn", "bank": "Bank", "the bank": "Bank", "stable master": "Stable Master",
           "the stable master": "Stable Master", "gryphon master": "Gryphon Master", "guild master": "Guild Master"}


def _labels(kinds: str) -> dict[int, list[tuple[float, float, str]]]:
    """The map's labels of those kinds (Data/Pois.lua: 2 towns, 3 every named place): {continent: [(x, y, name)]}."""
    text = (ADDON_DIR / "Data" / "Pois.lua").read_text(encoding="utf-8")
    out: dict[int, list] = {}
    for block in re.finditer(r"\[(\d+)\] = \{(.*?)\n  \},", text, re.S):
        cont = int(block.group(1))
        for x, y, name in re.findall(r"\{[%s],(-?[\d.]+),(-?[\d.]+),\"([^\"]+)\"" % kinds, block.group(2)):
            out.setdefault(cont, []).append((float(x), float(y), name))
    return out


def height(cont: int, x: float, y: float, svc: str, spawns) -> float | None:
    """The height of the nearest NPC whose title says the service, within NEAR_YD; None when none."""
    best = None
    for m, sx, sy, sz, t in spawns:
        if m == cont and matches(svc, t):
            d = math.hypot(sx - x, sy - y)
            if d <= NEAR_YD and (best is None or d < best[0]):
                best = (d, sz)
    return best[1] if best else None


def service_of(path: list[str]) -> str:
    """'Class Trainer > Mage' -> 'Mage Trainer'; 'The inn' -> 'Inn'."""
    last = path[-1].strip()
    key = last.lower()
    if key in SERVICE:
        return SERVICE[key]
    if len(path) > 1 and "trainer" in path[0].lower():
        return f"{last} Trainer"
    return last


def town_places(data_dir: Path, spawns) -> dict[int, dict]:
    """{uiMap: {town, cont, faction, places: [(x, y, name, z|None)]}}."""
    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    opts: dict[int, list] = {}
    for r in _rows(txt, "gossip_menu_option"):
        opts.setdefault(int(r["menu_id"]), []).append(r)
    pois = {int(r["entry"]): r for r in _rows(txt, "points_of_interest")}
    towns, labels = _labels("2"), _labels("23")
    out = {}
    for menu, (ui, cont, town, faction) in MENUS.items():
        found: list[tuple[list[str], dict]] = []

        def walk(m, path, seen):
            if m in seen:
                return
            seen.add(m)
            for o in opts.get(m, []):
                poi = pois.get(int(o["action_poi_id"] or 0))
                if poi:
                    found.append((path + [o["option_text"]], poi))
                sub = int(o["action_menu_id"] or 0)
                if sub > 0:
                    walk(sub, path + [o["option_text"]], seen)
        walk(menu, [], set())
        center = next((t for t in towns.get(cont, []) if t[2] == town), None)
        places = []
        for path, poi in found:
            x, y = float(poi["x"]), float(poi["y"])
            if min(towns.get(cont, []), key=lambda t: (t[0] - x) ** 2 + (t[1] - y) ** 2)[2] in CITIES:
                continue  # (in a capital: the capital's own places have it)
            if center and math.hypot(x - center[0], y - center[1]) <= TOWN_YD:
                where = town
            else:  # (named by the nearest place, a small one too: "Eastvale Logging Camp", not "Jasperlode Mine")
                where = min(labels.get(cont, []), key=lambda t: (t[0] - x) ** 2 + (t[1] - y) ** 2)[2]
            svc = service_of(path)
            places.append((x, y, f"{where} {svc}", height(cont, x, y, svc, spawns)))
        out[ui] = {"town": town, "cont": cont, "faction": faction, "places": places}
    return out


FLOOR_YD = 5.0  # a place's NPC this far over or under its building's ground floor, by every guess: upstairs, the cellar
AROUND_YD = 4.0  # the ground floor: the terrain this far out round the building's walls (its doors)


def _around(ground, bounds) -> list[float]:
    """The terrain's heights round a building (its bounds, AROUND_YD out): its lowest, the 10th and 25th percentiles
    and the median, the guesses at its ground floor's. On flat ground they agree; a building on a slope or dug into a
    hillside (Kharanos's) has them yards apart."""
    import numpy as np

    x0, y0, x1, y1 = bounds
    x0, y0, x1, y1 = x0 - AROUND_YD, y0 - AROUND_YD, x1 + AROUND_YD, y1 + AROUND_YD
    t = np.linspace(0, 1, 9)
    X = np.concatenate([x0 + (x1 - x0) * t, np.full(9, x1), x1 - (x1 - x0) * t, np.full(9, x0)])
    Y = np.concatenate([np.full(9, y0), y0 + (y1 - y0) * t, np.full(9, y1), y1 - (y1 - y0) * t])
    h, _walkable = ground.sample(X, Y)
    h = h[np.isfinite(h)]
    if not len(h):
        return []
    return [float(h.min()), float(np.percentile(h, 10)), float(np.percentile(h, 25)), float(np.median(h))]


def floors(cd, towns: dict[int, dict]) -> int:
    """Each place's floor in its building (asked 2026-10-06: Brill's trainers upstairs in the inn): +1 when its NPC
    stands FLOOR_YD or more over the building's ground floor by every guess at it (the terrain round its walls, where
    the doors are: not the terrain under the NPC, which a building dug into a hillside has over it), -1 under it (a
    cellar); None on the ground floor, outside, or where the guesses disagree (a hillside, Kharanos: better no floor
    than a wrong one). Adds it as each place's fifth value; returns how many are off the ground floor."""
    from .buildings import buildings
    from .caves import Ground

    per: dict = {}
    n = 0
    for t in towns.values():
        cont = t["cont"]
        if cont not in per:
            per[cont] = (Ground(cd, cont), [p.bounds for p in buildings(cd, cont)])
        ground, bl = per[cont]
        out = []
        for x, y, name, z, *_ in t["places"]:
            fl = None
            inside = [b for b in bl if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
            if z is not None and inside:
                b = min(inside, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))  # (the smallest: the building itself)
                offs = [z - g for g in _around(ground, b)]
                if offs and min(offs) >= FLOOR_YD:
                    fl = 1
                elif offs and max(offs) <= -FLOOR_YD:
                    fl = -1
            n += fl is not None
            out.append((x, y, name, z, fl))
        t["places"] = out
    return n


def towns_lua(towns: dict[int, dict]) -> str:
    lines = ["", "-- The starting zones' towns' places (agps city-places --towns, app/azerothgps/townplaces.py): world yards,",
             "-- shown once a guard there gave directions (Layers.lua), as a capital's.", "ns.TownPlaces = {"]
    for ui, t in towns.items():
        lines.append(f'  [{ui}] = {{ town = "{t["town"]}", cont = {t["cont"]}, faction = "{t["faction"]}",')
        for x, y, name, z, *rest in t["places"]:
            zs = f", z = {z:.1f}" if z is not None else ""
            fl = rest[0] if rest else None
            fs = f", fl = {fl}" if fl else ""  # (upstairs 1, the cellar -1: Nav.StopFloor)
            lines.append(f'    {{ x = {x:.1f}, y = {y:.1f}, "{name}"{zs}{fs} }},')
        lines.append("  },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def with_towns(text: str, towns: dict[int, dict]) -> str:
    """CityPlaces.lua's text with its ns.TownPlaces block (re)written at the end."""
    cut = text.find("\n-- The starting zones' towns' places")
    if cut >= 0:
        text = text[:cut + 1]
    return text.rstrip("\n") + "\n" + towns_lua(towns)
