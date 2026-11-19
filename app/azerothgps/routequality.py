"""Route quality (`agps route-quality`): the routes the whole addon chooses on random trips, weighed as it weighs them
(the zones too high counted extra, blocked ground at the router's cost, the rides' times), with the working tree and
with an older version (a git ref): which trips got better, which worse, which found a way where there was none.

The trips are the trip sweep's kind (a random faction, level and share of the flight paths known; a town or place to
another 1,500 to 9,000 yd off), one stop each, worked out settled (the searches at once). The older version's addon
files that differ are loaded in their place (gameharness.start's `replace`), from `git show`; nothing is checked out.
The overnight check that found tonight's one trip made worse, 2026-10-07: run it before and after routing changes.

A trip slower only because the roads it goes along were redrawn (drawn roads are truth) isn't worse: its route changed
only on roads the two versions' Data/Roads.lua don't share, with the same rides (`redrawn`: a player's
Stonetalon redraw was 48 yd longer than the road it replaced, two trips 27 s slower and the PR held). A detour onto
roads that didn't change is still worse (#168's 10 km way round a new join). A new road the router takes over the open
ground it walked before is `redrawn` too, when at least ALONG_SHARE of the stretch that changed runs along the roads
that changed and the trip is at most ALONG_MAX or ALONG_MAX_S slower, whichever is more (the roads cost less than open
ground to the router: a player's Desolace roads, two trips 13 and 34 s slower; a short trip's few
hundred yards of new road are a bigger share of it: his Ashenvale road from Splintertree Post east, 964 yd of road for
667 of open ground, made a 735 s trip 40 s slower, 5.4%). More than that is fair too while the
stretch that changed is at most ALONG_STRETCH times the yards it replaced (the yards the planner expects a walk by the
roads to take for each straight one) and the trip slower by no greater share than that stretch grew (its rides and its
other walks as they were: slower by the yards walked alone). The router keeps to the roads unless they're about twice
as long (Router.ROAD_DIRECT_PENALTY): #359, a player's road from Thelsamar south toward the Badlands, where the older
routes walked 2,050 yd of open ground from Kargath, the stretch 1.22 times as long, two trips 6 and 7.5% slower. A
stretch within those bounds that walks to a changed road's end and on to the roads from there (the join the router makes
at a loose end), where the older one never came near it, is `redrawn` too, none of it along the new road: the road's
end is a nearer way onto the roads (`at_changed_road_end`). A player's road by Wellspring Lake, AzerothGPS#424
a trip that walked 700 yd of open ground to the roads went 283 yd to the new road's end, 66 yd on
its join and along the old roads, 942 yd, 26 s (3.8%) slower. The roads are Data/Roads.lua's and the
caves' roads in Data/Caves.lua (#349: PR #332 rebuilt the stacked caves' roads, a ramp where a road had dropped 13 yd).

The yardstick is time; the router also keeps away from the other faction's guards (Router.HOSTILE_FACTOR), which time
doesn't see. A slower trip that walks at least GUARD_YD less within their reach is `safer`, listed but not worse: new
roads round the Barrens gave three Alliance trips a way past the Crossroads and Camp Taurajo, 850 to 1,150 yd of the
Horde's guards gone for 50 to 340 s more. Each trip's `guard` is those yards (the towns at the walks'
own ends left out, as the router leaves them).

Walls drawn in game are truth too: a slower trip with the same rides whose older route went through a wall only the
working tree has (`new_walls`) on a step its new route no longer takes is `walled`, listed but not worse (a player's
walls by Splintertree Post: nine trips that had walked through its palisade 70 to 190 s slower; their
new routes still pass the wall's line, on his recorded road through the gate, which the router cuts a yard either side).

A slower trip whose older route's walks, routed again by the working tree, go at least HOP_YD less straight over
blocked ground (the router's `blocked` yards: a hop, closed ground with no walk round it found) is `unhopped`, listed
but not worse, whatever its rides: no wall hopping (#339) takes a way round a hop at any length, and the planner may
then fly rather than walk it (its other walks hopping as they did before). #349: from Loch Modan to the Badlands the
older routes hopped a 195 yd cliff by Stonesplinter Valley (its sides at 400 and 260, 76 yd down in 20); the Slag
Pit's floors (PR #332) gave the walk round by Searing Gorge, five trips 300 to 4,400 s slower.

A slower trip the game asks the player about is `asking`, listed but not worse: the ride check found one way
Nav.HOSTILE_RIDE_YD or more nearer the other faction's guards and the safe one Nav.HOSTILE_SLOWER or more slower, so it
shows the safe way and asks "risk it?" (asked 2026-11-14), the faster way a "yes" away. Its own walks (from the spot
rounded, N.RIDE_CHECK_ROUND) can count the guards' yards apart where this check's `guard` doesn't reach GUARD_YD:
a player's 32 yd road into North Gate Pass gave a level 10 Horde trip from North Gate Outpost to
Terral's Watch a walk to Flame Crest's flight past 844 yd of the Alliance's guards (914 before) to the walk's 983 by
the check (69 fewer here, 716 -> 647), 1,787 s -> 2,820 s, the walk asked about.

The client's fatigue water is truth too: a slower trip whose older route's walks swam DEEP_YD or more through deep water
far out that only the working tree's Data/Terrain.lua closes (`new_deep`, the grids' `deep` cells), and whose new walks
swim no more of it, is `deep`, listed but not worse, whatever its rides: a way round it (by land, a boat or a flight),
or, with an end out at sea or over a strait, the same swim weighed now as closed ground. AzerothGPS#687 (the Wetlands
to Southshore swum over the strait into fatigue): 13 trips 20 to 4,250 s slower, among them a 3,105 yd straight line
down Feralas' coast that cut 17 yd out to sea off a headland (now 70 yd longer, along the coast), ten trips to or from
"The Great Sea" and the like, and Sun Rock Retreat to Dolanaar over Teldrassil's strait (the same route).
"""

from __future__ import annotations

import math
import random
import re
import subprocess
from pathlib import Path

from . import tripsweep as ts
from .paths import ADDON_DIR, REPO

NOISE_S = 10  # seconds: a difference under this is the same route weighed a hair apart
ON_ROAD_YD = 1.0  # a route point this near a road's line is on it (the data's tenths, Smooth keeps the road's points)
ALONG_SHARE = 0.25  # a slower trip onto changed roads: at least this share of the changed stretch's yards along them
ALONG_MAX = 0.05  # ... and at most this much slower
ALONG_MAX_S = 60  # ... or this many seconds, whichever is more (a short trip)
ALONG_STRETCH = 1.35  # ... or more slower, its changed stretch at most this many times the yards it replaced (Nav's
# WALK_FACTOR: the yards a walk is expected to take by the roads for each straight one) and the trip no more times slower
# than that stretch got longer
GUARD_YD = 100  # yards fewer within reach of the other faction's guards that make a slower trip `safer`
LIGHT_YD = 100  # ... or of their other NPCs that would flag a player (Data/Hostile.lua's a/h, 2026-11-16)
UNGUARDED_YD = 25  # yards nearer the older version's guards that make it `unguarded` (a few HOSTILE_STEP samples)
HOP_YD = 100  # yards fewer straight over blocked ground (the router's `blocked`) on the older route's walks: `unhopped`
DEEP_YD = 10  # yards an older route's walks swam through deep water the working tree closes (new_deep, more than a
# cell's 8.33) that make a slower trip `deep`
TILE = 1600 / 3
ROADS_FILE = "addon/AzerothGPS/Data/Roads.lua"
TERRAIN_FILE = "addon/AzerothGPS/Data/Terrain.lua"
_GRID = re.compile(r"^  \[(\d+)\] = \{ tx0 = (-?\d+), ty0 = (-?\d+), cell = ([\d.]+), w = \d+, h = \d+, deep = (\d+), "
                   r"rows = \{\n(.*?)\n  \} \},", re.S | re.M)
_SECTION = re.compile(r"^  \[(\d+)\] = \{")
_EDGE = re.compile(r"^\s*\{\d+,\d+,[\d.]+,\d+,([-\d.,]+)\},?\s*$")
CAVES_FILE = "addon/AzerothGPS/Data/Caves.lua"
_CAVE_CONT = re.compile(r"^\s*local overlays = ns\.RoadOverlays\[(\d+)\]")
_CAVE_EDGE = re.compile(r"^\s*\{(\d+),\d+,[\d.]+,\d+,(\"[^\"]*\"|[-\d.,]+)\},?\s*$")
_PACK = {ch: i for i, ch in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_")}
_WALL = re.compile(r"^\s*\{([-\d.,]+?)(?:,\s*z = [-\d.]+)?(?:,\s*kind = \"cliff\", cl = \{[^}]*\}, cr = \{[^}]*\})?\},?\s*$")


def road_lines(text: str) -> dict:
    """ns.Roads' edges in a Roads.lua's text: {cont: {(x1, y1, x2, y2, ...), ...}}, by their points alone (new nodes
    renumbering the edges don't change them). Only ns.Roads: the walls and tracks after it are left out."""
    lines, cont = {}, None
    for line in text.splitlines():
        if line.startswith("ns.") and not line.startswith("ns.Roads"):
            if lines:
                break
            continue
        m = _SECTION.match(line)
        if m:
            cont = int(m.group(1))
            continue
        m = _EDGE.match(line)
        if m and cont is not None:
            lines.setdefault(cont, set()).add(tuple(float(v) for v in m.group(1).split(",")))
    return lines


def _unpack(s: str, x: float, y: float) -> list:
    """A cave road's packed points (caves.pack_points) after its first, (x, y): every point, the first too."""
    pts = [x, y]
    for i in range(0, len(s) - 3, 4):
        x += _PACK[s[i]] * 64 + _PACK[s[i + 1]] - 2048
        y += _PACK[s[i + 2]] * 64 + _PACK[s[i + 3]] - 2048
        pts += [x, y]
    return pts


def cave_road_lines(text: str) -> dict:
    """The caves' roads in a Caves.lua's text (each continent's ns.RoadOverlays entries, their points packed): as
    road_lines, {cont: {(x1, y1, x2, y2, ...), ...}}, by their points alone."""
    lines, cont, nodes = {}, None, None
    for line in text.splitlines():
        m = _CAVE_CONT.match(line)
        if m:
            cont, nodes = int(m.group(1)), None
            continue
        if cont is None:
            continue
        s = line.strip()
        if s.startswith("n = {"):
            nodes = [float(v) for v in s[5:s.index("}")].split(",") if v.strip()]
            continue
        m = _CAVE_EDGE.match(line)
        if m and nodes is not None:
            a, rest = int(m.group(1)), m.group(2)
            if rest.startswith('"'):
                pts = _unpack(rest.strip('"'), nodes[a * 2 - 2], nodes[a * 2 - 1])
            else:
                pts = [float(v) for v in rest.split(",")]
            lines.setdefault(cont, set()).add(tuple(float(v) for v in pts))
    return lines


def _lines_at(ref: str | None, path: str, read) -> dict:
    """read() of `path`'s text at `ref` (None: the working tree's); {} when it isn't there."""
    if ref is None:
        p = REPO / path
        return read(p.read_text(encoding="utf-8")) if p.exists() else {}
    shown = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO, capture_output=True, check=False)
    return read(shown.stdout.decode("utf-8")) if shown.returncode == 0 else {}


def rejoined(old: set, new: set) -> set:
    """The roads (lines as road_lines') in both `old` and `new` whose ends meet other roads in one than in the other: a
    road the same yard for yard that leads somewhere else now."""
    def ends(lines):
        at = {}
        for line in lines:
            for end in (line[:2], line[-2:]):
                at.setdefault(end, set()).add(line)
        return at

    eo, en = ends(old), ends(new)
    return {line for line in old & new if any(eo.get(e) != en.get(e) for e in (line[:2], line[-2:]))}


def changed_roads(ref: str) -> dict:
    """The roads (as road_lines) in only one of `ref`'s data and the working tree's: removed and added. Data/Roads.lua's
    ns.Roads and the caves' roads in Data/Caves.lua (#349: a cave's roads rebuilt are redrawn roads too), and a cave's
    road kept as it was but joined at an end to other roads (`rejoined`: the Slag Pit's south mouth's 438 yd road, a
    dead end before PR #332's floors, a way into the pit after)."""
    out = {}
    for path, read in ((ROADS_FILE, road_lines), (CAVES_FILE, cave_road_lines)):
        old, new = _lines_at(ref, path, read), _lines_at(None, path, read)
        for c in set(old) | set(new):
            if old.get(c) != new.get(c):
                ch = old.get(c, set()) ^ new.get(c, set())
                if path == CAVES_FILE:
                    ch |= rejoined(old.get(c, set()), new.get(c, set()))
                out.setdefault(c, set()).update(ch)
    return out


def wall_lines(text: str) -> dict:
    """ns.Walls' walls in a Roads.lua's text: {cont: {(x1, y1, x2, y2, ...), ...}} (their heights left out)."""
    lines, cont, inside = {}, None, False
    for line in text.splitlines():
        if line.startswith("ns."):
            if inside:
                break
            inside = line.startswith("ns.Walls ")
            continue
        if not inside:
            continue
        m = _SECTION.match(line)
        if m:
            cont = int(m.group(1))
            continue
        m = _WALL.match(line)
        if m and cont is not None:
            lines.setdefault(cont, set()).add(tuple(float(v) for v in m.group(1).split(",")))
    return lines


def new_walls(ref: str) -> dict:
    """The walls (as wall_lines) the working tree's Data/Roads.lua has and `ref`'s hasn't."""
    shown = subprocess.run(["git", "show", f"{ref}:{ROADS_FILE}"], cwd=REPO, capture_output=True, check=False)
    old = wall_lines(shown.stdout.decode("utf-8")) if shown.returncode == 0 else {}
    new = wall_lines((ADDON_DIR / "Data" / "Roads.lua").read_text(encoding="utf-8"))
    return {c: new[c] - old.get(c, set()) for c in new if new[c] - old.get(c, set())}


def deep_cells(text: str) -> dict:
    """A Terrain.lua's text's deep water far out (each grid's `deep` cells: fatigue, closed): {cont: (tx0, ty0, cell
    yards, mask (h, w) bool; row = south, col = east)}; none in a version without them."""
    import numpy as np

    from .roads.terrain import decode_row

    out = {}
    for m in _GRID.finditer(text[:text.find("ns.Hills")]):
        cells = np.array([decode_row(r.strip().strip('",')) for r in m.group(6).splitlines()], np.uint8)
        out[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), float(m.group(4)), cells == int(m.group(5)))
    return out


def new_deep(ref: str) -> dict:
    """The deep water far out (as deep_cells) the working tree's Data/Terrain.lua has and `ref`'s hasn't."""
    old, new = _lines_at(ref, TERRAIN_FILE, deep_cells), _lines_at(None, TERRAIN_FILE, deep_cells)
    out = {}
    for c, (tx0, ty0, cell, mask) in new.items():
        o = old.get(c)
        if o and o[:3] == (tx0, ty0, cell) and o[3].shape == mask.shape:
            mask = mask & ~o[3]
        if mask.any():
            out[c] = (tx0, ty0, cell, mask)
    return out


def walk_deep_yards(walks: list, deep: dict) -> float:
    """deep_yards of a trip's walks (walk_parts: [[cont, [x, y, ...]], ...]; its rides over the sea left out)."""
    return sum(deep_yards([[c, p[i], p[i + 1]] for i in range(0, len(p) - 1, 2)], deep) for c, p in walks or ())


def deep_yards(route: list, deep: dict) -> float:
    """Yards of a route's steps (from one of its points, [cont, x, y], to the next) in `deep` water (new_deep), each
    step looked at a cell apart (Passability's cell: row from x, column from y)."""
    yards = 0.0
    for (c1, x1, y1), (c2, x2, y2) in zip(route or (), (route or ())[1:]):
        if c1 != c2 or c1 not in deep:
            continue
        tx0, ty0, cell, mask = deep[c1]
        k, d = TILE / cell, math.hypot(x2 - x1, y2 - y1)
        n = max(1, math.ceil(d / cell))
        for i in range(n):
            x, y = x1 + (i + 0.5) / n * (x2 - x1), y1 + (i + 0.5) / n * (y2 - y1)
            row, col = math.floor((32 - x / TILE - ty0) * k), math.floor((32 - y / TILE - tx0) * k)
            if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1] and mask[row, col]:
                yards += d / n
    return yards


def _cross(a, b, c, d) -> bool:
    """Whether segments a-b and c-d ((x, y) each) cross or touch."""
    def side(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 0) - (v < 0)

    def on(p, q, r):
        return min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])

    s1, s2, s3, s4 = side(a, b, c), side(a, b, d), side(c, d, a), side(c, d, b)
    if s1 != s2 and s3 != s4:
        return True
    return ((s1 == 0 and on(a, b, c)) or (s2 == 0 and on(a, b, d)) or (s3 == 0 and on(c, d, a))
            or (s4 == 0 and on(c, d, b)))


def wall_steps(route: list, walls: dict) -> set:
    """A route's steps (from one of its points, [cont, x, y], to the next) that cross one of `walls` (wall_lines)."""
    steps = set()
    if not walls or not route:
        return steps
    for (c1, x1, y1), (c2, x2, y2) in zip(route, route[1:]):
        if c1 != c2 or c1 not in walls:
            continue
        if any(_cross((x1, y1), (x2, y2), (w[i], w[i + 1]), (w[i + 2], w[i + 3]))
               for w in walls[c1] for i in range(0, len(w) - 3, 2)):
            steps.add((c1, x1, y1, x2, y2))
    return steps


def _near_line(x: float, y: float, pts: tuple, reach: float) -> bool:
    for i in range(0, len(pts) - 3, 2):
        ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        if math.hypot(x - ax - t * dx, y - ay - t * dy) <= reach:
            return True
    return False


def only_on_changed_roads(before: list, after: list, changed: dict) -> bool:
    """True when two routes' points ([cont, x, y] each) differ only on changed roads: the points between their common
    start and end all lie on a road one version has and the other hasn't (`changed`, changed_roads)."""
    if not changed or not before or not after:
        return False
    i = 0
    while i < min(len(before), len(after)) and before[i] == after[i]:
        i += 1
    j = 0
    while j < min(len(before), len(after)) - i and before[-1 - j] == after[-1 - j]:
        j += 1
    differ = before[i:len(before) - j] + after[i:len(after) - j]
    return bool(differ) and all(any(_near_line(x, y, pts, ON_ROAD_YD) for pts in changed.get(c, ()))
                                for c, x, y in differ)


def _stretches(before: list, after: list) -> tuple:
    """The stretches of `before` and `after` that differ: from the last point they share to the first again."""
    i = 0
    while i < min(len(before), len(after)) and before[i] == after[i]:
        i += 1
    j = 0
    while j < min(len(before), len(after)) - i and before[-1 - j] == after[-1 - j]:
        j += 1
    return before[max(i - 1, 0):len(before) - j + 1], after[max(i - 1, 0):len(after) - j + 1]


def _yards(pts: list) -> float:
    return sum(math.hypot(x2 - x1, y2 - y1) for (c1, x1, y1), (c2, x2, y2) in zip(pts, pts[1:]) if c1 == c2)


def stretch_yards(before: list, after: list) -> tuple:
    """The yards of the stretch that differs between two routes, `before`'s and `after`'s (_stretches)."""
    if not before or not after:
        return 0.0, 0.0
    old, new = _stretches(before, after)
    return _yards(old), _yards(new)


def share_along_changed_roads(before: list, after: list, changed: dict) -> float:
    """The share of the yards of `after`'s stretch that differs from `before` (from the last point they share to the
    first again) whose pieces lie along a changed road (`changed`, changed_roads): their middles on one."""
    if not changed or not before or not after:
        return 0.0
    stretch = _stretches(before, after)[1]
    total = along = 0.0
    for (c1, x1, y1), (c2, x2, y2) in zip(stretch, stretch[1:]):
        if c1 != c2:
            continue
        d = math.hypot(x2 - x1, y2 - y1)
        total += d
        if any(_near_line((x1 + x2) / 2, (y1 + y2) / 2, pts, ON_ROAD_YD) for pts in changed.get(c1, ())):
            along += d
    return along / total if total else 0.0


def at_changed_road_end(before: list, after: list, changed: dict) -> bool:
    """True when `after`'s stretch that differs from `before` (_stretches) passes the end of a changed road (`changed`,
    changed_roads) that `before`'s stretch doesn't: a new road's loose end taken as the way onto the roads."""
    if not changed or not before or not after:
        return False
    old, new = _stretches(before, after)

    def ends(stretch):
        return {(c, line[k], line[k + 1]) for c, x, y in stretch for line in changed.get(c, ()) for k in (0, len(line) - 2)
                if math.hypot(x - line[k], y - line[k + 1]) <= ON_ROAD_YD}

    return bool(ends(new) - ends(old))


def light_yards(ns, walks: list) -> float:
    """Yards of the walks (walk_parts) within reach of the other faction's other NPCs that would flag a player
    (Router.HostileLightYards, Data/Hostile.lua's a/h; none in an older version without them)."""
    R = ns.Router
    side = R.HostileSide() if R.HostileSide else None
    if not (side and R.HostileLightYards):
        return 0.0
    yards = 0.0
    for cont, pts in walks or ():
        for k in range(0, len(pts) - 3, 2):
            yards += R.HostileLightYards(cont, pts[k], pts[k + 1], pts[k + 2], pts[k + 3], side)
    return yards


def walk_parts(ns, r) -> list:
    """Route `r`'s walks (its parts with no ride): [[cont, [x, y, ...]], ...], for guard_yards."""
    N = ns.Nav
    out = []
    for part in (r.parts.values() if r and r.parts else ()):
        pts, kinds = part.pts, part.kinds
        if not pts or len(pts) < 4 or any(kinds[k] == N.KIND_TRANSPORT for k in range(1, len(kinds) + 1)):
            continue
        out.append([part.cont, [round(pts[i], 1) for i in range(1, len(pts) + 1)]])
    return out


def guard_yards(ns, walks: list) -> float:
    """Yards of the walks (walk_parts) within reach of the other faction's guards (Router.HostileYards), the towns at
    each walk's own ends left out as the router leaves them (HostileTownsNear: a trip from Mor'shan starts among its
    guards). By this version's guards: an older route's walks measured by the newer one's too (`old_guard`)."""
    R = ns.Router
    side = R.HostileSide() if R.HostileSide and R.HostileTownsNear else None  # (an older ref without them: none)
    if not side:
        return 0.0
    yards = 0.0
    for cont, pts in walks or ():
        n = len(pts)
        exempt = R.HostileTownsNear(cont, side, pts[0], pts[1], pts[n - 2], pts[n - 1])
        for k in range(0, n - 3, 2):
            yards += R.HostileYards(cont, pts[k], pts[k + 1], pts[k + 2], pts[k + 3], side, exempt)
    return yards


def _older_files(ref: str) -> dict:
    """The addon's Lua files (as the toc names them) that differ between `ref` and the working tree: ref's text."""
    out = subprocess.run(["git", "diff", "--name-only", ref, "--", "addon/AzerothGPS"], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout.split()
    files = {}
    for path in out:
        if not path.endswith(".lua"):
            continue
        name = Path(path).relative_to("addon/AzerothGPS").as_posix()
        shown = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO, capture_output=True, check=False)
        if shown.returncode == 0:  # (a file new since ref has nothing to put back)
            files[name] = shown.stdout.decode("utf-8")
    return files


def weigh_trips(count: int, seed: int, replace: dict | None = None, log=print,
                older: list[dict] | None = None, shard: tuple[int, int] = (0, 1)) -> list[dict]:
    """`count` random trips from `seed`: each { trip, secs (None: no way), walk, rides } as the addon chooses it. With the
    `older` version's rows, each row also has `old_walks_blocked`: that row's walks (`walks`) routed by this version,
    their yards straight over blocked ground (after every trip: their searches don't change the trips' own).
    `shard` (i, n): only the trips k with k % n == i, every trip still drawn from `seed` (the same trips as one run);
    `older` then that shard's rows."""
    from .gameharness import start

    rnd = random.Random(seed)
    lua, ns = start(replace=replace)
    ns.Nav.FUN = False
    N = ns.Nav
    ns.settings.gps.fastestOrder = False
    out = []
    for k in range(count):
        cont = rnd.choice((0, 1))
        faction = rnd.choice(("Horde", "Alliance"))
        level = rnd.choice(ts.LEVELS)
        places = ts._places(ns, cont)
        for _ in range(200):
            a, b = rnd.choice(places), rnd.choice(places)
            if ts.TRIP_MIN_YD <= math.hypot(a[0] - b[0], a[1] - b[1]) <= ts.TRIP_MAX_YD:
                break
        masters = ts._masters(ns, cont, faction[0])
        known = [m for m in masters if rnd.random() < rnd.uniform(0.2, 0.9)] or masters[:1]
        if k % shard[1] != shard[0]:  # (another shard's trip: drawn, so the ones after it are the same, not routed)
            continue
        lua.execute(f"AGPS_LEVEL = {level}; UnitFactionGroup = function() return '{faction}' end")
        cdb = ns.CharDB()
        cdb.faction = faction
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { " + "".join(f"{{ nodeID = {n}, known = true }}," for n in known)
                                 + " } } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {a[0]}, {a[1]}, {cont}")
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        # (each trip from the Router's walks as new: they're remembered 256 at a time, by rough place where none was
        # found, and joined onto from a walk to the same spot, so a trip came out by what the trips before it searched.
        # #349: one 27 s apart at sea off Theramore, the same alone, as another version's earlier trips searched more)
        ns.Router.WallsChanged()
        row = {"k": k, "trip": f"{faction[0]}{level} {a[2]} -> {b[2]}", "cont": cont, "from": list(a[:2]), "to": list(b[:2]),
               "level": level, "side": faction}
        try:
            r = N.Route(a[0], a[1], cont)
            secs = ts._weighed(lua, ns, r, cont, a, b) if r else None
            row.update(secs=None if secs in (None, math.inf) else round(secs), walk=round(r.walkYards or 0) if r else None,
                       rides=[f"{r.legs[i].ride[8]}:{r.legs[i].ride[10] or r.legs[i].ride[9]}"
                              for i in range(1, len(r.legs) + 1) if r.legs[i].ride] if r and r.legs else [],
                       pts=[[part.cont, round(part.pts[i], 1), round(part.pts[i + 1], 1)] for part in r.parts.values()
                            for i in range(1, len(part.pts), 2)] if r and r.parts else [],
                       guard_walks=walk_parts(ns, r),
                       blocked=round(sum(part.blocked or 0 for part in r.parts.values())) if r and r.parts else 0,
                       walks=[[lg.cont, lg.x1, lg.y1, lg.x2, lg.y2] for lg in (r.legs[i] for i in range(1, len(r.legs) + 1))
                              if lg.walk] if r and r.legs else [])
            row["guard"] = round(guard_yards(ns, row["guard_walks"]))
            row["light"] = round(light_yards(ns, row["guard_walks"]))
            # (the ride check took the safe way round the other faction's guards and asks the player "risk it?",
            # N.riskQuestion: this trip's own, N.Clear forgot the last one's; none in an older version without it)
            row["asking"] = bool(N.riskQuestion)
        except Exception as e:  # (a failure in the addon's Lua: a finding too)
            row["error"] = str(e)[:300]
        out.append(row)
        if (k + 1) % 50 == 0:
            log(f"  {k + 1} of {count}")
    for row, old in zip(out, older or ()):
        try:  # (as the trip's character: the zones too high and the guards as they were for it)
            lua.execute(f"AGPS_LEVEL = {row['level']}; UnitFactionGroup = function() return '{row['side']}' end")
            ns.CharDB().faction = row["side"]
            ns.Router.WallsChanged()
            # (and the older route's walks past this version's guards: a change to who they are moves the yardstick,
            # 2026-11-16 the PvP-flagged NPCs, so both routes are weighed by the same ones)
            row["old_guard"] = round(guard_yards(ns, old.get("guard_walks")))
            row["old_light"] = round(light_yards(ns, old.get("guard_walks")))
            row["old_walks_blocked"] = round(sum(ns.Router.Route(c, x1, y1, x2, y2, lua.table()).blocked or 0
                                                 for c, x1, y1, x2, y2 in old.get("walks") or ()))
        except Exception as e:
            row.setdefault("error", f"older walks: {str(e)[:280]}")
    return out


def compare(before: list[dict], after: list[dict], changed: dict | None = None, walls: dict | None = None,
            deep: dict | None = None) -> dict:
    """Trip by trip: same, better, worse (by more than NOISE_S), a way found where there was none, or lost; a slower
    one with the same rides whose route changed only on `changed` roads (changed_roads), or mostly along them and a
    little slower (share_along_changed_roads, ALONG_MAX, ALONG_MAX_S, ALONG_STRETCH) or onto the roads at a changed
    road's end (at_changed_road_end), is `redrawn`; one whose older route went through `walls`
    (new_walls) on a step the new one doesn't take, with the same rides, is `walled`; one walking GUARD_YD less past the other
    faction's guards (its older route's by either version's guards, `old_guard`) is `safer`; one whose older route's walks, routed by the newer version (`old_walks_blocked`), go
    HOP_YD less straight over blocked ground (a hop gone) is `unhopped`; one the game asks "risk it?" about, the safe way
    shown meanwhile (`asking`) and no nearer the guards, is `asking`; one whose older route's walks swam DEEP_YD or more
    through `deep` water (new_deep, fatigue) and its new ones no more is `deep`; none of them is worse."""
    res = {"same": 0, "better": [], "worse": [], "redrawn": [], "walled": [], "safer": [], "unguarded": [], "unhopped": [],
           "asking": [], "deep": [], "found": [], "lost": [], "errors": []}
    for x, y in zip(before, after):
        if x.get("error") or y.get("error"):
            res["errors"].append({"trip": x["trip"], "before": x.get("error"), "after": y.get("error")})
            continue
        sx, sy = x.get("secs"), y.get("secs")
        row = {"trip": x["trip"], "before": sx, "after": sy, "rides_before": x.get("rides"), "rides_after": y.get("rides"),
               "guard_before": x.get("guard", 0), "guard_after": y.get("guard", 0), "old_guard": y.get("old_guard"),
               "blocked_before": x.get("blocked", 0), "blocked_after": y.get("blocked", 0),
               "old_walks_blocked": y.get("old_walks_blocked"), "new_old_guard": y.get("new_old_guard"),
               "light_after": y.get("light"), "old_light": y.get("old_light"),
               "from": x["from"], "to": x["to"], "cont": x["cont"]}
        if sx is None and sy is None:
            res["same"] += 1
        elif sx is None:
            res["found"].append(row)
        elif sy is None:
            res["lost"].append(row)
        elif sy < sx - NOISE_S:
            res["better"].append(row)
        elif sy > sx + NOISE_S:
            bp, ap = x.get("pts"), y.get("pts")
            old_yd, new_yd = stretch_yards(bp, ap)
            redrawn = x.get("rides") == y.get("rides") and (
                only_on_changed_roads(bp, ap, changed)
                or ((sy <= max(sx * (1 + ALONG_MAX), sx + ALONG_MAX_S)
                     or (old_yd > 0 and new_yd <= old_yd * ALONG_STRETCH and sy * old_yd <= sx * new_yd))
                    and (share_along_changed_roads(bp, ap, changed) >= ALONG_SHARE
                         or at_changed_road_end(bp, ap, changed))))
            walled = x.get("rides") == y.get("rides") and bool(wall_steps(bp, walls) - wall_steps(ap, walls))
            safer = (max(x.get("guard") or 0, y.get("old_guard") or 0) - (y.get("guard") or 0) >= GUARD_YD
                     or (y.get("old_light") or 0) - (y.get("light") or 0) >= LIGHT_YD)
            # (its route GUARD_YD or more nearer the older version's guards than the older route went: past posts the
            # change dropped, the roads by them free now; listed, not worse. 2026-11-16: "Accept them")
            unguarded = (y.get("new_old_guard") or 0) - (x.get("guard") or 0) >= UNGUARDED_YD
            unhopped = "old_walks_blocked" in y and (x.get("blocked") or 0) - y["old_walks_blocked"] >= HOP_YD
            # (the game asks the player "risk it?" and shows the safe way meanwhile, the faster one a "yes" away, its
            # route no nearer the guards than the older one went: Nav's own check counts HOSTILE_RIDE_YD fewer, by its
            # walks from the rounded spot, where `guard` here may count fewer)
            asking = bool(y.get("asking")) and (y.get("guard") or 0) <= max(x.get("guard") or 0, y.get("old_guard") or 0)
            # (the older route's walks swam out into the fatigue water this change closes and the new ones no more: a
            # way round it, or the same swim to an end out at sea weighed as closed ground; whatever the rides)
            row["deep_before"] = round(walk_deep_yards(x.get("guard_walks"), deep or {}))
            row["deep_after"] = round(walk_deep_yards(y.get("guard_walks"), deep or {}))
            swum = row["deep_before"] >= DEEP_YD and row["deep_after"] <= row["deep_before"]
            res["redrawn" if redrawn else "walled" if walled else "safer" if safer else "unguarded" if unguarded
                else "unhopped" if unhopped else "asking" if asking else "deep" if swum
                else "worse"].append(row)
        else:
            res["same"] += 1
    res["better"].sort(key=lambda r: r["after"] - r["before"])
    res["worse"].sort(key=lambda r: r["before"] - r["after"])
    res["redrawn"].sort(key=lambda r: r["before"] - r["after"])
    res["walled"].sort(key=lambda r: r["before"] - r["after"])
    res["safer"].sort(key=lambda r: r["before"] - r["after"])
    res["unhopped"].sort(key=lambda r: r["before"] - r["after"])
    res["unguarded"].sort(key=lambda r: r["before"] - r["after"])
    res["asking"].sort(key=lambda r: r["before"] - r["after"])
    res["deep"].sort(key=lambda r: r["before"] - r["after"])
    return res


def _weigh_shard(count: int, seed: int, replace: dict | None, i: int, n: int, older: list[dict] | None) -> list[dict]:
    return weigh_trips(count, seed, replace, lambda *_: None, older, (i, n))


def _weigh(count: int, seed: int, replace: dict | None, log, older: list[dict] | None, jobs: int) -> list[dict]:
    """weigh_trips in `jobs` processes, each a shard of the trips (each its own game harness), rows back in trip order.
    (2026-11-16, asked "find a faster way for PRs to run tests": CI's runners have 3 CPUs, one route-quality used one.)"""
    if jobs <= 1:
        return weigh_trips(count, seed, replace, log, older)
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    shards = [[r for r in older if r["k"] % jobs == i] for i in range(jobs)] if older else [None] * jobs
    with ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("spawn")) as pool:
        parts = list(pool.map(_weigh_shard, [count] * jobs, [seed] * jobs, [replace] * jobs, range(jobs), [jobs] * jobs,
                              shards))
    rows = sorted((r for part in parts for r in part), key=lambda r: r["k"])
    log(f"  {len(rows)} of {count} ({jobs} processes)")
    return rows


def guards_by(replace: dict | None, rows: list[dict]) -> list[int]:
    """Each row's walks (`guard_walks`) past the guards of the version `replace` gives (the older one): a change to who
    the guards are opens roads past posts it dropped (2026-11-16, the enemy areas from the NPCs that would flag a player:
    Ambermill's Dalaran Protectors flag no one, and the road by them, now free, beat a walk across at road mode's 2x)."""
    from .gameharness import start

    lua, ns = start(replace=replace)
    out = []
    for row in rows:
        try:
            lua.execute(f"AGPS_LEVEL = {row['level']}; UnitFactionGroup = function() return '{row['side']}' end")
            ns.CharDB().faction = row["side"]
            out.append(round(guard_yards(ns, row.get("guard_walks"))))
        except Exception:
            out.append(None)
    return out


def run(count: int, seed: int, against: str, log=print, jobs: int = 1) -> dict:
    older = _older_files(against)
    log(f"route-quality: {count} trips (seed {seed}); {against}: {len(older)} addon files differ"
        + (f" ({', '.join(sorted(older)[:6])}{'...' if len(older) > 6 else ''})" if older else ""))
    log(f"  {against}:")
    before = _weigh(count, seed, older or None, log, None, jobs)
    log("  the working tree:")
    after = _weigh(count, seed, None, log, before, jobs)
    if older:  # (the newer routes past the older version's guards: `unguarded`)
        for row, yd in zip(after, guards_by(older, after)):
            row["new_old_guard"] = yd
    res = compare(before, after, changed_roads(against), new_walls(against), new_deep(against))
    res.update(seed=seed, trips=count, against=against, differing=sorted(older))
    return res
