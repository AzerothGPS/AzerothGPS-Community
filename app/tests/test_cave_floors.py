"""Caves with floors over floors (asked 2026-11-14: "add cave floor data so cave routes use heights"): Data/Caves.lua's
`layered` caves have roads on every floor with their heights (`nz`), so a stop with a height routes to its floor and a
route between floors takes the cave's ramps; a cave's floor under walkable ground has `under`, so a stop with a height
on the ground over a mine stays up there. One-level caves are as before. The whole addon (gameharness)."""
import math
import re

import pytest

pytest.importorskip("lupa.lua51")

# Fargodeep Mine (Elwynn Forest): its lower floor and its upper one over it, and a kobold's spot up there
LOWER, UPPER = (-9802.0, 127.0, 6.5), (-9804.0, 125.0, 25.5)
KOBOLD = (-9822.7, 180.4)  # (23.0, Data/NpcFloors.lua)
MOUTH = (-9838.0, 171.0)
DOWN_IN = (-9822.0, 179.0, 11.5)  # (the lower floor, under the kobold)
HILL = (-9790.0, 140.0, 51.4)  # (the ground on the hill over the mine: the terrain's height there)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def _route(lua, ns, a, b, **opts):
    r = ns.Router.Route(0, a[0], a[1], b[0], b[1], lua.table(offroad=False, **opts))
    fz = [r.fz[i] for i in range(1, len(r.fz) + 1)] if r.fz else []
    return r, fz


def test_a_route_between_two_stacked_cave_floors_takes_the_ramp(game):
    lua, ns = game
    r, fz = _route(lua, ns, LOWER, UPPER, z=LOWER[2], tz=UPPER[2])
    # (2.8 yd apart in a straight line, one over the other: round by the ramp, climbing a little at a time)
    assert r.length > 100, r.length
    hs = [h for h in fz if h]
    assert hs[0] == pytest.approx(LOWER[2], abs=2) and hs[-1] == pytest.approx(UPPER[2], abs=2)
    assert max(abs(b - a) for a, b in zip(hs, hs[1:])) < 4, hs


def test_a_stop_on_the_upper_floor_routes_there_and_one_under_it_below(game):
    lua, ns = game
    z = ns.Nav.SpawnZ(0, *KOBOLD)
    assert z == pytest.approx(23.0)
    _, fz = _route(lua, ns, MOUTH, KOBOLD, tz=z)
    assert fz[-1] == pytest.approx(z, abs=2)
    _, fz = _route(lua, ns, MOUTH, KOBOLD, tz=DOWN_IN[2])
    assert fz[-1] == pytest.approx(DOWN_IN[2], abs=2)


def test_a_stop_on_the_ground_over_a_mine_stays_on_the_ground(game):
    lua, ns = game
    R = ns.Router
    x, y, z = HILL
    assert not R.CaveDown(0, x, y, None, z)
    assert R.CaveDown(0, x, y, None, DOWN_IN[2]) and R.CaveDown(0, x, y)  # (under it, or with no height: down)
    # from down in the mine: out of its mouth and up the hill, not along the mine's roads under the spot
    r, _ = _route(lua, ns, DOWN_IN, HILL, z=DOWN_IN[2], indoors=True, tz=z)
    places = [R.PlaceAt(0, r.pts[2 * k - 1], r.pts[2 * k]) for k in range(1, len(r.pts) // 2 + 1)]
    assert False in places, places  # (on the land's roads)
    down, _ = _route(lua, ns, DOWN_IN, HILL, z=DOWN_IN[2], indoors=True)
    assert all(p == "cave" for p in [R.PlaceAt(0, down.pts[2 * k - 1], down.pts[2 * k])
                                     for k in range(1, len(down.pts) // 2 + 1)])
    # an NPC's spot on the ground over the Dawning Wood Catacombs: its shipped height keeps it up there
    x, y = -10387.7, 399.9
    assert ns.Nav.SpawnZ(0, x, y) == pytest.approx(29.1)
    assert not R.CaveDown(0, x, y, None, ns.Nav.SpawnZ(0, x, y)) and R.CaveDown(0, x, y)


def test_a_one_level_cave_is_as_before(game):
    # Jasperlode Mine: its floors stack only by its mouth (the rock over it), so no heights; a stop's changes nothing
    lua, ns = game
    R = ns.Router
    x, y = -9155.0, -594.0
    assert not R.InLayeredCave(0, x, y)
    hs = R.HeightsNear(0, x, y, 30)
    assert not hs or len(hs) == 0
    a, _ = _route(lua, ns, (-9200.0, -700.0), (x, y), tz=100.0)
    b, _ = _route(lua, ns, (-9200.0, -700.0), (x, y))
    assert a.length == pytest.approx(b.length)


def test_the_cave_floors_data():
    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "Caves.lua").read_text(encoding="utf-8")
    layered = re.findall(r'ns\.Terrain\["(cave\d+)"\] = \{[^\n]*layered = true', text)
    assert len(layered) >= 40
    names = {k: n for n, k in re.findall(r'\{ "([^"]*)", "(cave\d+)"', text)}
    got = {names[k] for k in layered}
    assert {"Fargodeep Mine", "The Wailing Caverns", "Defias Hideout", "Gold Coast Quarry"} <= got
    # (one entry a continent (a second's ways out were joined onto the first's roads), every node's height in it: the
    # layered caves' (nearly all with one), 0 for the others)
    entries = re.findall(r"overlays\[#overlays \+ 1\] = \{ cave = true,\n  n = \{([^}]*)\},(.*?)\n  \}\n", text, re.S)
    assert len(entries) == 2
    for n, rest in entries:
        nz = re.search(r"\n  nz = \{([^}]*)\}", rest).group(1).split(",")
        assert len(nz) * 2 == len(n.split(","))
        assert 0.3 * len(nz) < sum(1 for v in nz if v != "0") < len(nz)
    # `under` only on caves with a floor under walkable ground, a height
    for m in re.finditer(r"under = (-?[\d.]+),", text):
        assert math.isfinite(float(m.group(1)))


def test_from_the_slag_pits_rim_to_its_floor_not_down_the_wall(game):
    # #349: the Slag Pit's north mouth on its rim (242.5) was tied to its floor (185.5) by a road 11 yd long: the route
    # from the land there fell 57 yd in 93 yd of route, and the way through the pit was a way up that wall too
    lua, ns = game
    rim, floor = (-6721.0, -1054.0, 240.5), (-6724.0, -1121.0, 185.5)
    r, fz = _route(lua, ns, rim, floor, z=rim[2], tz=floor[2])
    pts = [(r.pts[2 * k - 1], r.pts[2 * k]) for k in range(1, len(r.pts) // 2 + 1)]
    assert r.length > 300, r.length  # (round by a mouth on the floor's level: the west one)
    for (p, a), (q, b) in zip(zip(pts, fz), zip(pts[1:], fz[1:])):
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        assert not (a and b and d >= 1 and abs(b - a) > max(20, d)), (p, a, q, b)  # (0 yd: one road's end to the next's)
    assert fz[-1] == pytest.approx(floor[2], abs=2)


def test_no_cave_road_climbs_a_cliff():
    # #349: the Slag Pit's north mouth, an old way out tied onto the new floors by the nearest node, from its rim at
    # 242.5 down to the floor at 185.5 in 11 yd: a road up a 57 yd wall (stairs and ramps climb a few yards a step; a
    # fall is a drop, one way). The way through by its south and west mouths walked up it.
    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "Caves.lua").read_text(encoding="utf-8").replace("\r\n", "\n")
    entries = re.findall(r"overlays\[#overlays \+ 1\] = \{ cave = true,\n  n = \{([^}]*)\},\n  e = \{\n(.*?)\n  \},(.*?)\n  \}\n",
                         text, re.S)
    assert len(entries) == 2
    cliffs = []
    for n, e, rest in entries:
        n = [float(v) for v in n.split(",")]
        nz = [float(v) for v in re.search(r"\n  nz = \{([^}]*)\}", rest).group(1).split(",")]
        drops = {int(k) for k in re.findall(r"\[(\d+)\] = \d+", re.search(r"\n  drops = \{([^}]*)\}", rest).group(1))}
        for i, line in enumerate(e.splitlines(), 1):
            a, b, yards = re.match(r"\s*\{(\d+),(\d+),([\d.]+),", line).groups()
            a, b, yards = int(a), int(b), float(yards)  # (the road's own yards: a spiral's ends are close)
            if i in drops or not (nz[a - 1] and nz[b - 1]):  # (a drop falls; a node of a one-level cave has no height)
                continue
            if abs(nz[b - 1] - nz[a - 1]) > max(20, yards) and yards >= 1:  # (0 yd: two floors' roads meeting)
                cliffs.append((a, b, n[2 * a - 2], n[2 * a - 1], nz[a - 1], nz[b - 1], yards))
    assert not cliffs


# (every way out the 69 stacked caves had in the data before their floors, 2026-11-14: (continent, cave, the end of a
# mouth's road on a land road, that mouth); the coordinator's ask after the Venture Co. Mine's way out by its near mouth)
OLD_JOINS = [
    (0, "cave10001", -8183, -2569, -7805, -2712),
    (0, "cave10001", -8183, -2569, -7918, -2623),
    (0, "cave35530", -11066, 1526, -11063, 1534),
    (0, "cave35530", -11074, 1493, -11079, 1488),
    (0, "cave53025", -6017, -2979, -6024, -2981),
    (0, "cave72860", -8679, -2309, -8683, -2314),
    (0, "cave72860", -8675, -2250, -8665, -2274),
    (0, "cave101741", -2907, -2376, -2868, -2230),
    (0, "cave117279", -11623, -741, -11553, -700),
    (0, "cave126417", 2975, 626, 3011, 652),
    (0, "cave127328", 1892, -2407, 2216, -2378),
    (0, "cave127328", 1876, -2366, 2228, -2358),
    (0, "cave170486", -10426, 1910, -10429, 1909),
    (0, "cave170822", 320, -3634, 486, -3782),
    (0, "cave194844", -1391, -2141, -1199, -2147),
    (0, "cave209515", -659, 143, -839, 232),
    (0, "cave209515", -659, 143, -859, 166),
    (0, "cave210351", -9700, 296, -9822, 211),
    (0, "cave210351", -9725, 336, -9856, 175),
    (0, "cave53025", -6017, -2979, -6020, -2975),
    (0, "cave349103", -5334, 567, -5510, 575),
    (0, "cave350747", -5617, -481, -5627, -325),
    (0, "cave350748", -5774, -1674, -5761, -1665),
    (0, "cave398079", -3423, -3533, -3077, -3257),
    (0, "cave398079", -3423, -3533, -3149, -3265),
    (0, "cave398079", -3423, -3533, -3111, -3285),
    (0, "cave398368", -9241, -2303, -8976, -2007),
    (0, "cave398381", -10818, -2993, -10825, -3017),
    (0, "cave398381", -10983, -3242, -10909, -3185),
    (0, "cave398483", -10617, -3781, -10763, -3729),
    (0, "cave404723", -7191, -1079, -6718, -1097),
    (0, "cave404723", -6682, -1823, -6750, -1463),
    (0, "cave404723", -7191, -1079, -6912, -1235),
    (0, "cave475912", -449, -457, -293, -426),
    (0, "cave493789", -1617, -3192, -1919, -3333),
    (0, "cave574091", 217, -666, 21, -328),
    (0, "cave66782694", -8393, -3242, -8672, -3359),
    (0, "cave67551018", 2401, -5860, 2434, -5878),
    (0, "cave68463626", 2105, 2066, 1862, 2434),
    (1, "cave170819", -2422, -1051, -1904, -1131),
    (1, "cave173805", 10080, 1624, 9875, 1549),
    (1, "cave209084", 1078, 65, 978, -398),
    (1, "cave236739", 1569, -2442, 1785, -2664),
    (1, "cave236739", 1569, -2442, 1725, -2698),
    (1, "cave250582", 1355, -4659, 1484, -4868),
    (1, "cave250582", 1355, -4659, 1450, -4886),
    (1, "cave282171", -5314, -2433, -5075, -2360),
    (1, "cave309455", 7568, -2909, 7622, -3080),
    (1, "cave322975", -6807, 667, -6508, 875),
    (1, "cave322975", -6807, 667, -6510, 833),
    (1, "cave322975", -6908, 892, -6540, 923),
    (1, "cave322975", -6807, 667, -6628, 865),
    (1, "cave322979", -6908, 892, -6629, 961),
    (1, "cave322979", -6908, 892, -6709, 985),
    (1, "cave322979", -6908, 892, -6671, 957),
    (1, "cave322979", -6908, 892, -6671, 1007),
    (1, "cave335495", -7026, 1250, -7257, 1623),
    (1, "cave335762", -6887, 1649, -7410, 1771),
    (1, "cave335762", -6917, 1362, -7436, 1869),
    (1, "cave337630", -4659, 623, -5158, 194),
    (1, "cave349081", 6426, -5029, 6535, -5139),
    (1, "cave361332", 10449, 801, 10783, 919),
    (1, "cave361332", 10449, 801, 10735, 923),
    (1, "cave371662", -409, -1934, -765, -1984),
    (1, "cave371662", -927, -2491, -813, -2090),
    (1, "cave372018", 7400, -2185, 7378, -2197),
    (1, "cave372018", 6893, -2306, 6896, -2313),
    (1, "cave372018", 6818, -2095, 6824, -2091),
    (1, "cave398076", -2355, 109, -2394, 266),
    (1, "cave398484", 6591, -1586, 6518, -1587),
    (1, "cave398484", 6633, -1511, 6502, -1553),
    (1, "cave398484", 6633, -1511, 6444, -1585),
    (1, "cave462620", 7258, -629, 6854, -674),
    (1, "cave494932", 3498, -500, 3493, -493),
    (1, "cave497832", -2233, 2406, -2267, 2509),
    (1, "cave559408", 7157, -3912, 7138, -3888),
    (1, "cave371662", -927, -2491, -835, -2052),
    (1, "cave681641", -6800, 510, -6296, 986),
    (1, "cave681641", -6807, 667, -6320, 962),
    (1, "cave681641", -6908, 892, -6418, 1030),
    (1, "cave24646128", -7026, 1250, -7375, 1613),
    (1, "cave24646128", -7054, 1217, -7477, 1551),
    (1, "cave24646307", -7652, 1049, -7904, 575),
    (1, "cave24646307", -7652, 1049, -7932, 639),
    (1, "cave24646307", -7684, 1064, -7988, 659),
    (1, "cave24646307", -7684, 1064, -8064, 602),
    (1, "cave24647172", -6441, -3712, -6436, -3398),
    (1, "cave24647172", -6485, -3725, -6488, -3430),
    (1, "cave24647172", -6485, -3725, -6530, -3406),
    (1, "cave66604799", -303, 150, -132, 214),
    (1, "cave68204033", 4465, -3444, 4441, -3467),
    (1, "cave66604799", -309, 159, -52, 434),
    (1, "cave66604799", -309, 159, -26, 446),
    (1, "cave70049859", 2435, 1776, 2435, 1780),
    (1, "cave70612836", 1802, 958, 1819, 644),
]


def test_every_mouth_of_the_stacked_caves_is_still_joined_to_a_land_road():
    # (each way out the old data had: its road's end on a land road kept, or its mouth (within 10 yd) joined by a new
    # one to a nearer road; either way onto the cave's floors' roads)
    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "Caves.lua").read_text(encoding="utf-8").replace("\r\n", "\n")
    entries = re.findall(r"overlays\[#overlays \+ 1\] = \{ cave = true,\n  n = \{([^}]*)\},\n  e = \{\n(.*?)\n  \},\n"
                         r"(.*?)\n  \}\n", text, re.S)
    layered = [e for e in entries if "nz = {" in e[2]]
    assert len(layered) == 2  # (continent 0's, then 1's)
    for cont, (nodes, edges, rest) in enumerate(layered):
        n = [float(v) for v in nodes.split(",")]
        pos = [(n[i], n[i + 1]) for i in range(0, len(n), 2)]
        nz = [float(v) for v in re.search(r"nz = \{([^}]*)\}", rest).group(1).split(",")]
        joins = [int(v) for v in re.search(r"joins = \{([^}]*)\}", rest).group(1).split(",") if v]
        ends = [tuple(int(v) for v in re.match(r"\s*\{(\d+),(\d+),", ln).groups()) for ln in edges.splitlines()]
        parent = list(range(len(pos)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a, b in ends:
            parent[find(a - 1)] = find(b - 1)
        floors = {find(i) for i, z in enumerate(nz) if z}  # (the pieces with the cave's floors on them)
        mouth_of = {j: [pos[(b if a == j else a) - 1] for a, b in ends if j in (a, b)] for j in joins}
        for c, key, jx, jy, mx, my in OLD_JOINS:
            if c != cont:
                continue
            ok = [j for j in joins if math.dist(pos[j - 1], (jx, jy)) <= 15
                  or any(math.dist(m, (mx, my)) <= 10 for m in mouth_of[j])]
            assert ok, (key, (jx, jy), (mx, my))
            assert any(find(j - 1) in floors for j in ok), (key, (jx, jy))
