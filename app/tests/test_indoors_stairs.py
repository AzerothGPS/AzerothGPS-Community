"""Buildings' stairs roads climb stairs, not ledges (issue #842): Brill inn's stairs road went from the ground floor's
passage straight onto the side of the stair landing, 3 yd up in 1.4 yd, and the QA walk following it stayed on the
ground floor. A building's walk is built with steps on foot of at most indoors.STEP_CAP between neighboring cells (as
Undercity's), and its roads keep off the foot of a bigger step (layers.build's `step_lip`).

Only Brill's inn was rebuilt so (spliced into Data/Indoors.lua, as the caves were): a fresh `agps indoors --write`
changes much else too (the client and the roads moved since it was last written) and needs its own route-quality look.
The other buildings' steep stairs roads, STEEP_LEFT of them, wait for that (a follow-up issue); none may be added."""

import math
from pathlib import Path

from lupa import LuaRuntime

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
STEEP = 1.6  # yards up a yard of road: no stair is that steep
RISE = 2.0  # (and at least this much in all: a road between two spots of one floor a yard apart isn't judged)
STEEP_LEFT = 166  # (the other buildings' still: 171 before, Brill's inn's gone)
INN = (2267.0, 241.0, 40.0)  # (Brill: duskwood_inn, its doors' joins too)


def _indoors():
    lua = LuaRuntime()
    ns = lua.eval("{}")
    run = lua.eval('function(src, ns) local f = assert(load(src, "Indoors", "t", setmetatable({}, {__index=_G}))); '
                   'return f("AzerothGPS", ns) end')
    run((ADDON / "Data" / "Indoors.lua").read_text(encoding="utf-8"), ns)
    return ns


def _steep(ns):
    """The stairs roads rising more than STEEP a yard, RISE at least: [(cont, x, y, z, z2, yards)]."""
    steep = []
    for cont in (0, 1):
        for ov in ns.RoadOverlays[cont].values():
            if not ov.indoor:
                continue
            n, nz = ov.n, ov.nz
            for e in ov.e.values():
                a, b, length, src = e[1], e[2], e[3], e[4]
                if src != 6:
                    continue
                d = max(math.hypot(n[2 * b - 1] - n[2 * a - 1], n[2 * b] - n[2 * a]), float(length))
                rise = abs(nz[b] - nz[a])
                if rise >= RISE and rise / max(d, 0.1) > STEEP:
                    steep.append((cont, round(n[2 * a - 1], 1), round(n[2 * a], 1), nz[a], nz[b], round(d, 1)))
    return steep


def test_no_indoor_stairs_road_climbs_a_ledge():
    steep = _steep(_indoors())
    inn = [s for s in steep if s[0] == 0 and math.hypot(s[1] - INN[0], s[2] - INN[1]) <= INN[2]]
    assert not inn, f"Brill's inn: {inn}"
    assert len(steep) <= STEEP_LEFT, f"{len(steep)} stairs roads steeper than a stair: {steep[:10]}"


def test_brill_inns_stairs_start_at_the_first_flights_foot():
    # (the model's walkable faces: the first flight's foot at about 2261.5, 231 (z 35), up east to the landing (38),
    # then the second flight back west along y 235-238 onto the upstairs floor (41))
    ns = _indoors()
    ov = next(o for o in ns.RoadOverlays[0].values() if o.indoor)
    n, nz = ov.n, ov.nz
    feet = []
    for e in ov.e.values():
        a, b, src = e[1], e[2], e[4]
        if src != 6:
            continue
        pa, pb = (n[2 * a - 1], n[2 * a]), (n[2 * b - 1], n[2 * b])
        if math.dist(pa, (2265.0, 236.0)) > 12 and math.dist(pb, (2265.0, 236.0)) > 12:
            continue
        lo = pa if nz[a] < nz[b] else pb
        if min(nz[a], nz[b]) < 36:  # (the flight up from the ground floor)
            feet.append(lo)
    assert feet and all(math.dist(f, (2261.5, 231.0)) <= 3 for f in feet), feet
