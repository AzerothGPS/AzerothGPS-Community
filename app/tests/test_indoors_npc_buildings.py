"""Phase 7 of the buildings' insides (asked 2026-11-21: "Typically the whole building is a wall, and if routing to an NPC
in the building you just get a dotted line to it through walls, not directions to go around to the entrance then
inside"): every building with a shipped NPC (Data/Npcs.lua) standing inside it on a cell Data/Buildings.lua blocks
gets its inside as phase 6's (indoors.shipped_npc_buildings, `agps indoors --splice`), spliced onto the shipped
Data/Indoors.lua (indoors.splice_lua: every building in it left as it was). A route to such an NPC goes to the door
by the roads and in along the inside's roads, its last stretch off them short, not straight through the walls."""

import math

import pytest

from azerothgps import buildings as BL
from azerothgps import indoors as D

# (NPC, continent, its spawn (Data/Npcs.lua), the land road the route starts on, 100-300 yd out). Before: the route's
# last leg off the roads went straight in through the walls, 22 to 127 yd, 7 to 36 yd of it over the building's cells.
NPCS = [
    ("Pyrewood Armorer", 0, (-346.0, 1501.4, 19.0), (-203.1, 1486.5)),  # (Pyrewood's smithy: 73 yd, 36 over it)
    ("Magistrate Henry Maleb", 0, (-861.0, -473.7, 13.4), (-658.1, -558.0)),  # (Southshore's town hall: 59, 30)
    ("Kayla Smithe", 0, (1836.8, 1641.0, 97.7), (2021.3, 1645.6)),  # (Deathknell's chapel: 73, 32)
    ("Morhan Coppertongue", 0, (-5343.7, -2932.1, 324.4), (-5155.2, -2842.7)),  # (Thelsamar's smithy hut: 22, 7)
    ("Mahani", 1, (-2400.3, -1929.8, 96.8), (-2348.5, -1820.5)),  # (a Mulgore hut: 127, 36)
    ("Brant Jasperbloom", 1, (-3697.0, -4335.3, 11.5), (-3525.9, -4282.4)),  # (a Dustwallow farmhouse: 58, 47)
    ("Dirge Quikcleave", 1, (-7168.3, -3850.3, 8.8), (-6890.8, -3771.1)),  # (Gadgetzan: 77, 33)
]
LAST_YD = D.CHECK_NPC_LAST_YD  # (the inside's roads are pruned to COVER_YD: the NPC stands off them a little)
FLOOR_Z = D.CHECK_FLOOR_Z


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    return start()


def _over_cells(cont, pts, cells, frame) -> float:
    """Yards of the polyline `pts` over the buildings' blocked cells."""
    yd = 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        seg = math.hypot(bx - ax, by - ay)
        m = max(1, int(seg))
        for j in range(m):
            t = (j + 0.5) / m
            r, c = BL.to_cell(frame, ax + (bx - ax) * t, ay + (by - ay) * t)
            if int(r) * 65536 + int(c) in cells:
                yd += seg / m
    return yd


@pytest.mark.parametrize("name,cont,spot,start", NPCS, ids=[n[0] for n in NPCS])
def test_a_route_to_an_npc_in_a_building_goes_in_by_its_door_not_through_its_walls(game, name, cont, spot, start):
    lua, ns = game
    R = ns.Router
    px, py, pz = spot
    r = R.Route(cont, start[0], start[1], px, py, lua.table_from({"tz": pz}))
    n = len(r.pts) // 2
    pts = [(float(r.pts[2 * i + 1]), float(r.pts[2 * i + 2])) for i in range(n)]
    kinds = [r.kinds[i] for i in range(1, n)]
    i = n - 1
    while i >= 1 and kinds[i - 1] == R.KIND_OFFROAD:
        i -= 1
    last = pts[i:]
    last_yd = sum(math.dist(a, b) for a, b in zip(last, last[1:]))
    assert last_yd <= LAST_YD, f"{name}: {last_yd:.0f} yd off the roads at the end"
    fz = r.fz and r.fz[n]
    assert fz is not None and abs(float(fz) - pz) <= FLOOR_Z, f"{name}: ends on the {fz} floor, not {pz}"
    cells = D.blocked_building_cells()[cont]
    assert _over_cells(cont, last, cells, BL.grid_frames()[cont]) <= LAST_YD


def test_every_npc_building_in_the_data_is_a_building_with_an_inside():
    # (the shipped data: ns.Indoors names every building the routes go into; phase 7's are among them)
    middles = D.shipped_middles()
    for _name, cont, (px, py, _pz), _start in NPCS:
        assert any(c == cont and math.hypot(x - px, y - py) <= 40 for c, x, y in middles), _name


def _text(n_old: int) -> str:
    nodes = ",".join(f"{i}.0,{i}.0" for i in range(n_old))
    nz = ",".join("10.0" for _ in range(n_old))
    return "\n".join([
        "local _, ns = ...", "ns.RoadOverlays = ns.RoadOverlays or {}", "ns.Indoors = ns.Indoors or {}",
        "ns.Indoors[0] = {", '  { "Town: old", x = 1, y = 1, r = 5, floors = { 10.0 } },', "}", "do",
        "  local overlays = ns.RoadOverlays[0] or {}", "  ns.RoadOverlays[0] = overlays",
        "  overlays[#overlays + 1] = { indoor = true,", "  n = {" + nodes + "},", "  nz = {" + nz + "},", "  e = {",
        '    {1,2,1,0,"x"},', "  },", "  joins = {2},", "  bridge = {},", "  }", "end", ""])


def test_splice_adds_attached_buildings_and_leaves_the_shipped_ones_as_they_were():
    old = _text(3)
    b = {"cont": 0, "town": "Nowhere", "name": "hut", "bounds": (90, 90, 110, 110), "floors": [20.0],
         "nodes": [(100.0, 100.0), (104.0, 100.0), (120.0, 100.0)], "zs": [20.0, 20.0, None],
         "edges": [(0, 1, [(100.0, 100.0), (104.0, 100.0)], 0), (1, 2, [(104.0, 100.0), (120.0, 100.0)], 0)],
         "doors": [1], "joins": [2], "bridge": []}
    new = D.splice_lua(old, [b])
    lines, was = new.split("\n"), old.split("\n")
    # (the shipped building's line and its entry kept as they were; the new one's line `attach`, its roads an entry of
    # their own after, numbered from 1, its joins listed but not joined into the land's road: R.AttachTrip)
    assert lines[4] == was[4] and '"Nowhere: hut", x = 100, y = 100, r = 10, attach = true' in lines[5] and lines[6] == "}"
    assert lines[7:20] == was[6:19]  # (its entry, do ... end)
    i = lines.index("  overlays[#overlays + 1] = { indoor = true, attach = true,")
    assert lines[i + 1] == "  n = {100.0,100.0,104.0,100.0,120.0,100.0}," and lines[i + 2] == "  nz = {20.0,20.0,0},"
    assert lines[i + 4].startswith("    {1,2,4,0,") and lines[i + 5].startswith("    {2,3,16,0,")
    assert lines[i + 7] == "  joins = {3}," and lines[i + 8] == "  bridge = {},"
    assert D.splice_lua(old, []) == old
    assert D.shipped_middles(new) == [(0, 1.0, 1.0), (0, 100.0, 100.0)]


def _without_attached(text: str) -> str:
    """Data/Indoors.lua's text with its attached buildings (phase 7) taken out: as main's, before them."""
    out, skip = [], False
    lines = text.split("\n")
    for k, line in enumerate(lines):
        if "attach = true, floors" in line:
            continue
        if line == "do" and k + 3 < len(lines) and "attach = true," in lines[k + 3]:
            skip = True
        if not skip:
            out.append(line)
        if skip and line == "end":
            skip = False
    return "\n".join(out)


# (trips past attached buildings: the land's roads as without them. With their joins tied into the land's road, by
# splitting it, these came out longer: by Splintertree Post's flight master 1,329 to 1,668 yd, round the road the inn's
# door's join cut off; and so on for 12 sample trips, route-quality, 2026-11-21)
THROUGH = [
    (1, (2880.3, -3287.5), (2302.4, -2524.6)),  # (to Splintertree Post's flight master, by its inn and hut)
    (0, (-711.5, -515.5), (183.3, 283.3)),  # (from Southshore's flight master, by its town hall)
    (1, (-3216.7, -483.3), (-4450.0, -3116.7)),  # (Red Cloud Mesa, by Camp Narache's huts)
    (1, (-944.8, -3649.0), (-840.9, -3727.2)),  # (Ratchet, by its huts)
]


@pytest.mark.parametrize("cont,a,b", THROUGH)
def test_a_trip_past_attached_buildings_is_on_the_land_roads_as_without_them(cont, a, b):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "Indoors.lua").read_text(encoding="utf-8")
    assert "attach = true" in text
    lens = []
    for t in (text, _without_attached(text)):
        lua, ns = start(replace={"Data/Indoors.lua": t})
        r = ns.Router.Route(cont, a[0], a[1], b[0], b[1], lua.table_from({}))
        lens.append(round(r.length, 1))
    assert lens[0] == lens[1], lens
