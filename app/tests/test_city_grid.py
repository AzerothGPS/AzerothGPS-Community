"""1.4.0's city routing, being tested (CityGrid.lua, Data/CityGrid.lua, citygrid.py; docs/city-rework-1.4.0.md): routes
inside the six capitals on each city's layered walk grid while the option is on, the player's floor from the grid and
the height band; with it off, everything as before."""

import hashlib
import math
import re
from pathlib import Path

import pytest

from azerothgps import citygrid as C
from azerothgps.paths import ADDON_DIR

pytest.importorskip("lupa.lua51")

DATA = ADDON_DIR / "Data" / "CityGrid.lua"

# (shipped NPCs' spawns, Data/Npcs.lua: level, x, y, z)
GRYSHKA = (1, 1634.0, -4439.4, 15.5)  # Orgrimmar's inn, the Valley of Strength
KARUS = (1, 1627.3, -4376.1, 11.8)  # its bank
ZEVROST = (1, 1849.0, -4360.4, -14.8)  # the Cleft of Shadow, under the Drag
THRALL = (1, 1920.1, -4125.7, 43.0)  # Grommash Hold (no road goes in)
GARRETT = (10001, 1567.1, 266.3, -43.0)  # Undercity's bat handler, up on the Trade Quarter's ring
FARANELL = (10001, 1434.5, 404.9, -85.2)  # the Apothecarium, at the bottom
MONTAGUE = (10001, 1600.0, 240.7, -52.1)  # the bank
LAURENA = (0, -8512.4, 862.4, 109.9)  # Stormwind's cathedral
DUNGAR = (0, -8835.8, 490.1, 109.7)  # its gryphon master
FIREBREW = (0, -4840.7, -857.1, 502.0)  # Ironforge's inn, the Commons
HULFDAN = (0, -4648.0, -1124.0, 502.0)  # the Forlorn Cavern
NISSA = (0, -4876.6, -1149.1, 512.5)  # Ironforge's First Aid Trainer, in a room off the Great Forge's hall
IF_GATE = (0, -5023.0, -829.0, None)  # Ironforge's gate, from Dun Morogh
SAELIENNE = (1, 10127.9, 2224.8, 1328.8)  # Darnassus's inn, the Craftsmen's Terrace
FANDRAL = (1, 10173.0, 2569.9, 1367.0)  # up the Cenarion Enclave's tree, by its spiral stairs
IDRIANA = (1, 9939.0, 2522.0, 1318.0)  # Darnassus's bank, behind its round counter
PALA = (1, -1300.3, 38.5, 129.3)  # Thunder Bluff's inn, up on the central mesa
KARY = (1, -1465.0, -94.0, 159.0)  # the Hunter Rise, over a rope bridge
MULGORE = (1, -1334.0, 176.0, None)  # the land under the mesas, by the west lifts' feet


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    yield lua, ns
    ns.settings.gps.cityGrid = False


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else None


def _route(lua, ns, a, b, on=True):
    ns.settings.gps.cityGrid = on
    try:
        return ns.Router.Route(a[0], a[1], a[2], b[1], b[2], lua.table(z=a[3], tz=b[3]))
    finally:
        ns.settings.gps.cityGrid = False


def _heights(r):
    return _list(r.zs if r.zs is not None else r.fz)


# --- the data -------------------------------------------------------------------------------------------------------

def _entries():
    txt = DATA.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'ns\.CityGridData\["([^"]+)"\] = \{(.*?)\n\}', txt, re.S):
        body = m.group(2)
        num = {k: float(v) for k, v in re.findall(r"\b(\w+) = (-?[\d.]+)", body)}
        strs = dict(re.findall(r'\b(\w+) = "([^"]*)"', body))
        out[m.group(1)] = (num, strs)
    return out


def test_the_grids_are_numbers_only_and_whole():
    entries = _entries()
    assert set(entries) == {c.name for c in C.CITIES}
    for name, (num, s) in entries.items():
        w, h, n, block = int(num["w"]), int(num["h"]), int(num["n"]), int(num["block"])
        assert len(s["cells"]) == w * h, name
        assert sum(C.ALPHA.index(ch) for ch in s["cells"]) == n, name
        assert len(s["s"]) == n * 7, name
        assert len(s["base"].split(",")) == math.ceil(w * h / block), name
        assert set(s["cells"] + s["s"]) <= set(C.ALPHA), name
        assert re.fullmatch(r"[\d.,;-]*", s["links"]), name  # (road links: numbers only)


def test_the_grids_are_baked_from_the_meshes_and_parameters_there_now():
    """Stale data fails: the bake's parameters changed without `agps city-grid --write`, or (where the meshes are, not
    on CI) a mesh rebuilt since."""
    txt = DATA.read_text(encoding="utf-8")
    assert f'bake = "{C.bake_stamp()}"' in txt, "Data/CityGrid.lua is stale: agps city-grid --write"
    for city in C.CITIES:
        p = C.RM.mesh_path(city.mesh)
        if p.exists():
            assert f'mesh = "{C.mesh_stamp(city)}"' in txt.split(f'ns.CityGridData["{city.name}"]')[1].split("}")[0], \
                f"{city.name}'s mesh changed since the grid was baked: agps city-grid --write"


# --- off: as before ---------------------------------------------------------------------------------------------------

def test_with_the_option_off_the_grid_is_never_asked(game):
    lua, ns = game
    CG = ns.CityGrid
    was = CG.Leg
    CG.Leg = lua.eval("function() error('asked with the option off') end")
    try:
        r = _route(lua, ns, GRYSHKA, ZEVROST, on=False)
        assert r.cityGrid is None and len(r.pts) >= 4
    finally:
        CG.Leg = was


# --- routes over floors -----------------------------------------------------------------------------------------------

def test_undercity_from_the_ring_to_the_bottom(game):
    lua, ns = game
    r = _route(lua, ns, GARRETT, FARANELL)
    assert r.cityGrid == "Undercity" and r.zs is not None
    zs = _heights(r)
    assert abs(zs[0] - GARRETT[3]) < 3 and abs(zs[-1] - FARANELL[3]) < 3, (zs[0], zs[-1])
    pts = _list(r.pts)
    assert (pts[0], pts[1]) == (GARRETT[1], GARRETT[2]) and (pts[-2], pts[-1]) == (FARANELL[1], FARANELL[2])
    own = _route(lua, ns, GARRETT, FARANELL, on=False)
    assert r.length < own.length  # (straight where the floors let it, not the roads' zig-zag)
    assert len(pts) < len(_list(own.pts))


def test_orgrimmar_down_into_the_cleft_of_shadow_under_the_drag(game):
    lua, ns = game
    for a in (GRYSHKA, KARUS):
        r = _route(lua, ns, a, ZEVROST)
        assert r.cityGrid == "Orgrimmar" and r.fz is not None
        fz = _heights(r)
        assert abs(fz[-1] - ZEVROST[3]) < 3, fz[-1]
        back = _route(lua, ns, ZEVROST, a)
        assert back.cityGrid == "Orgrimmar" and abs(_heights(back)[0] - ZEVROST[3]) < 3


def test_a_hall_no_road_goes_into_is_walked_into(game):
    lua, ns = game
    r = _route(lua, ns, GRYSHKA, THRALL)
    assert r.cityGrid == "Orgrimmar"
    assert abs(_heights(r)[-1] - THRALL[3]) < 3


def test_stormwind_across_the_city(game):
    lua, ns = game
    r = _route(lua, ns, DUNGAR, LAURENA)
    own = _route(lua, ns, DUNGAR, LAURENA, on=False)
    assert r.cityGrid == "Stormwind City" and r.length < own.length


def test_a_place_the_grid_cannot_reach_is_the_routers_own(game):
    # (the Wizard's Sanctum, up the mage tower by its portal: no walk there)
    lua, ns = game
    maginor = (0, -9012.5, 867.1, 29.7)
    r = _route(lua, ns, DUNGAR, maginor)
    own = _route(lua, ns, DUNGAR, maginor, on=False)
    assert r.cityGrid is None and _list(r.pts) == _list(own.pts)


def test_a_trip_into_the_city_from_outside_is_cut_in_at_the_gate(game):
    lua, ns = game
    outside = (1, 1360.0, -4380.0, None)  # (Durotar, before Orgrimmar's gate)
    ns.settings.gps.cityGrid = True
    try:
        r = ns.Router.Route(1, outside[1], outside[2], ZEVROST[1], ZEVROST[2], lua.table(tz=ZEVROST[3]))
    finally:
        ns.settings.gps.cityGrid = False
    pts = _list(r.pts)
    assert r.cityGrid == "Orgrimmar" and (pts[0], pts[1]) == (outside[1], outside[2])
    assert abs(_heights(r)[-1] - ZEVROST[3]) < 3


# --- Ironforge, Thunder Bluff, Darnassus: their ways in and up ------------------------------------------------------

def _transport(ns, kind, name):
    for t in ns.Transports.values():
        if t[8] == kind and (name in str(t[9]) or name in str(t[10])):
            return t
    raise AssertionError(f"no {kind} at {name}")


def _trip(lua, ns, faction, start, stop):
    """The whole trip as Nav plans and routes it with the option on: its parts."""
    G, N, CG = ns.GPS, ns.Nav, ns.CityGrid
    fac = ns.CharDB().faction
    ns.CharDB().faction = faction
    try:
        CG.Set(True)
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = %.1f, %.1f, %d" % (start[1], start[2], start[0]))
        N.SetStops(lua.eval("{ { x = %.1f, y = %.1f, cont = %d, name = 'Stop', z = %.1f } }"
                            % (stop[1], stop[2], stop[0], stop[3])), False, "red")
        G.Follow()
        for _ in range(30):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        parts = N.route.parts
        return str(N.StepsText(6)), [parts[i] for i in range(1, len(parts) + 1)]
    finally:
        ns.CharDB().faction = fac
        CG.Set(False)
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_ironforge_from_the_tram_s_end_walks_the_grid(game):
    """Ironforge is under a mountain (a capital laid like a cave, its `zsplit`; IsIndoors says outdoors in its halls):
    from the Deeprun Tram's end in Tinker Town (Data/Transports.lua's tram, its Ironforge end and height) to the inn,
    the grid's walk on the halls' floor, never the mountain over them, and no longer than the roads'."""
    lua, ns = game
    t = _transport(ns, "tram", "Ironforge")
    tram = (0, t[5], t[6], t.z2)
    r = _route(lua, ns, tram, FIREBREW)
    own = _route(lua, ns, tram, FIREBREW, on=False)
    assert r.cityGrid == "Ironforge" and not r.noWay
    fz = [z for z in _heights(r) if z is not False]
    assert max(fz) < 520 and min(fz) > 495  # (the halls' floor, never the mountain's top over them)
    assert abs(fz[-1] - FIREBREW[3]) < 3
    assert r.length <= own.length


def test_ironforge_s_gate_to_nissa_firestone_s_room_walks_the_grid(game):
    """Ironforge's capital cells are its halls and leave out the shops and rooms off them: Nissa Firestone's First Aid
    room by the Great Forge was the Router's own, to the hall's edge and a straight line on through the wall. Ironforge's
    grid is `whole` (CityGrid.CityFor: any floor of its grid within the capital's rectangle), so from the gate the walk
    is the grid's into her room, ending on her floor, and no longer than the Router's own."""
    lua, ns = game
    CG = ns.CityGrid
    assert not ns.Router.CapitalAt(0, NISSA[1], NISSA[2])  # (her room: not among the capital's cells)
    assert CG.CityFor(0, NISSA[1], NISSA[2]) == "Ironforge" and CG.CityFor(0, IF_GATE[1], IF_GATE[2]) == "Ironforge"
    r = _route(lua, ns, IF_GATE, NISSA)
    own = _route(lua, ns, IF_GATE, NISSA, on=False)
    assert r.cityGrid == "Ironforge" and not r.noWay and not r.pending
    pts, fz = _list(r.pts), [z for z in _heights(r) if z is not False]
    assert math.hypot(pts[-2] - NISSA[1], pts[-1] - NISSA[2]) < 1
    assert abs(fz[-1] - NISSA[3]) < 2
    assert max(fz) < 520 and min(fz) > 490  # (the halls' floor, never the mountain over them)
    assert r.length <= own.length


def test_every_shipped_npc_in_ironforge_s_rooms_is_in_its_grid(game):
    """Every shipped NPC spawn (Data/Npcs.lua) within Ironforge's capital rectangle over a floor of its grid is in the
    city for the grid (CityGrid.CityFor): 34 of them stood in shops and rooms the capital's cells leave out."""
    lua, ns = game
    CG, P = ns.CityGrid, ns.Passability
    c = CG.City("Ironforge")
    txt = (ADDON_DIR / "Data" / "Npcs.lua").read_text(encoding="utf-8")
    seen, missed = 0, []
    for line in txt.splitlines():
        parts = line.split("|")
        if len(parts) < 7:
            continue
        for spawn in parts[6].split(";"):
            q = spawn.split()
            if len(q) != 4 or q[0] != "0":
                continue
            x, y, z = map(float, q[1:])
            if not P.CapitalGridAt(0, x, y):
                continue
            ci = CG.CellAt(c, x, y)
            if ci is None or CG.Count(c, ci) == 0:
                continue
            seen += 1
            if CG.CityFor(0, x, y) != "Ironforge":
                missed.append((parts[1], x, y, z))
    assert seen >= 150 and not missed, missed


@pytest.mark.parametrize("npc", [(0, -5030.4, -1147.3, 512.1), (0, -4617.6, -906.7, 501.2), (0, -4723.9, -1056.5, 510.9)],
                         ids=["olthran", "braenna", "eric"])
def test_from_ironforge_s_inn_with_world_routing_on_the_rooms_off_its_halls_are_the_city_grid_s(game, npc):
    """1.4.0 with the world grid on: the world grid's no-way handed most legs into the rooms off Ironforge's halls to the
    city's grid (WorldGrid.CityWalk), but from the inn Olthran Craghelm was "no way" and the walks to Braenna Flintcrag
    and Outfitter Eric ended a floor off them (504.5). With Ironforge's grid `whole` (PR #923) they're the city's legs
    (CityGrid.Leg), each ending on the NPC's floor."""
    lua, ns = game
    ns.settings.gps.worldGrid = True
    try:
        r = _route(lua, ns, FIREBREW, npc)
    finally:
        ns.settings.gps.worldGrid = False
    assert r.cityGrid == "Ironforge" and not r.noWay and not r.pending
    pts, fz = _list(r.pts), [z for z in _heights(r) if z is not False]
    assert math.hypot(pts[-2] - npc[1], pts[-1] - npc[2]) < 3
    assert abs(fz[-1] - npc[3]) < 3


def test_ironforge_by_the_tram_from_stormwind(game):
    """The whole trip: from Stormwind's tram station to Ironforge's inn it takes the tram, and the walk on from its
    end in Ironforge is the grid's (no road's kind in it)."""
    lua, ns = game
    t = _transport(ns, "tram", "Ironforge")
    steps, parts = _trip(lua, ns, "Alliance", (0, -8350.0, 520.0), FIREBREW)
    assert "Take the tram to Ironforge" in steps
    last = parts[-1]
    assert (round(last.pts[1]), round(last.pts[2])) == (round(t[5]), round(t[6]))
    assert set(_list(last.kinds)) == {ns.Router.KIND_OFFROAD}


def test_thunder_bluff_up_a_lift_and_down_another(game):
    """Thunder Bluff's lifts (Data/Capitals.lua's source 5 roads, their length the wait and the ride) are road links of
    the grid: from Mulgore under the mesas up to the inn the route rides a lift up, and from the Hunter Rise down to
    Mulgore it rides one down. Never off a mesa's edge: no step of the walk drops more than a stair's height."""
    lua, ns = game
    R = ns.Router
    up = _route(lua, ns, MULGORE, PALA)
    assert up.cityGrid == "Thunder Bluff" and R.KIND_LIFT_UP in _list(up.kinds)
    assert abs(_heights(up)[-1] - PALA[3]) < 3
    down = _route(lua, ns, KARY, (1, MULGORE[1], MULGORE[2], 60.0))
    kinds, hs, link, pts = _list(down.kinds), _heights(down), down.onLink, _list(down.pts)
    assert down.cityGrid == "Thunder Bluff" and R.KIND_LIFT_DOWN in kinds
    for i in range(len(kinds)):
        if not link[i + 1] and hs[i] is not False and hs[i + 1] is not False:
            run = math.hypot(pts[2 * i + 2] - pts[2 * i], pts[2 * i + 3] - pts[2 * i + 1])
            # (walked down, not off the edge: a mesa's are 70 yd; a 2 yd step down by the inn's door is walked)
            assert hs[i] - hs[i + 1] <= run + 2.5, (i, hs[i], hs[i + 1], run)
    # (the ride costs the Router's own yards for it, the wait and the ride: not its few yards up the shaft)
    c = ns.CityGrid.City("Thunder Bluff")
    lifts = [c.links[i] for i in range(1, len(c.links) + 1) if c.links[i].kind == 5]
    assert lifts and all(L.cost >= 140 for L in lifts)


def test_darnassus_from_the_teleporter_walks_the_grid(game):
    """Darnassus's Temple Gardens teleporter (Data/Transports.lua's TELEPORTERS row): from Rut'theran Village up to the
    inn the trip takes it, and the walk on from its Darnassus end is the grid's."""
    lua, ns = game
    t = _transport(ns, "teleporter", "Darnassus")
    r = _route(lua, ns, (1, t[2], t[3], t.z1), SAELIENNE)
    assert r.cityGrid == "Darnassus" and abs(_heights(r)[-1] - SAELIENNE[3]) < 3
    steps, parts = _trip(lua, ns, "Alliance", (1, 8605.0, 1000.0), SAELIENNE)
    assert "Take the teleporter to The Temple Gardens, Darnassus" in steps
    last = parts[-1]
    assert (round(last.pts[1]), round(last.pts[2])) == (round(t[2]), round(t[3]))
    assert set(_list(last.kinds)) == {ns.Router.KIND_OFFROAD}


def test_darnassus_up_a_tree_s_spiral_stairs(game):
    """Up the Cenarion Enclave's tree to the Arch Druid by its spiral stairs (issue #65's): on the grid all the way up
    (his treetop is outside the capital's cells: Darnassus's grid is all its own, `whole`), each straight stretch a
    few yards of climb at most (round the spiral, not straight up the trunk), ending on his floor; and back down."""
    lua, ns = game
    r = _route(lua, ns, SAELIENNE, FANDRAL)
    assert r.cityGrid == "Darnassus"
    hs, pts, link = _heights(r), _list(r.pts), r.onLink
    assert abs(hs[-1] - FANDRAL[3]) < 2, hs[-1]
    for i in range(len(hs) - 1):
        if not link[i + 1]:
            run = math.hypot(pts[2 * i + 2] - pts[2 * i], pts[2 * i + 3] - pts[2 * i + 1])
            assert abs(hs[i + 1] - hs[i]) <= run * 1.5 + 1.5, (i, hs[i], hs[i + 1], run)
    assert sum(1 for z in hs if 1345 < z < 1365) >= 4  # (points all the way up the spiral)
    back = _route(lua, ns, FANDRAL, SAELIENNE)
    assert back.cityGrid == "Darnassus" and abs(_heights(back)[0] - FANDRAL[3]) < 2


def test_darnassus_s_bank_counter_and_the_temple_s_balcony(game):
    """The bankers stand behind the bank's round counter, and Tyrande on the Temple of the Moon's balcony (its ramps
    climb 25 yd between the roads' floors: Darnassus's near_z): both on the grid, ending on their floors."""
    lua, ns = game
    tyrande = (1, 9662.5, 2524.6, 1360.1)
    for b in (IDRIANA, tyrande):
        r = _route(lua, ns, SAELIENNE, b)
        assert r.cityGrid == "Darnassus" and abs(_heights(r)[-1] - b[3]) < 2, (b, _heights(r)[-1])


# --- the lines --------------------------------------------------------------------------------------------------------

TRIPS = [(GRYSHKA, ZEVROST), (KARUS, THRALL), (GARRETT, FARANELL), (MONTAGUE, FARANELL), (DUNGAR, LAURENA),
         (FIREBREW, HULFDAN), (IF_GATE, NISSA), (PALA, KARY), (SAELIENNE, FANDRAL)]


@pytest.mark.parametrize("a, b", TRIPS)
def test_each_straight_line_is_walked_on_the_grid(game, a, b):
    """Every straight stretch of a grid route (not a road link's) is one the grid walks cell to cell (CG.Line)."""
    lua, ns = game
    CG = ns.CityGrid
    r = _route(lua, ns, a, b)
    c = CG.City(r.cityGrid)
    pts, hs, link, bends = _list(r.pts), _heights(r), r.onLink, r.bends
    n = len(pts) // 2
    for i in range(n - 1):
        if link[i + 1] or bends[i + 1]:
            continue  # (a road link's; a line's height point: the line from its start is walked whole)
        j = i + 1
        while j < n - 1 and bends[j + 1]:
            j += 1  # (to the line's end, past the points kept for its heights)
        ax, ay, bx, by = pts[2 * i], pts[2 * i + 1], pts[2 * j], pts[2 * j + 1]
        if any(CG.Count(c, CG.CellAt(c, x, y)) == 0 for x, y in ((ax, ay), (bx, by))):
            continue  # (an NPC behind a counter, off the floor: the last yards to it, as to any stop off the floor)
        # (the surfaces at its ends at their heights: two at one height in a cell, a thin wall between, are both tried)
        s0s = [f for f in CG.SurfacesAt(c, ax, ay, hs[i]).values() if abs(f.z - hs[i]) < 0.5]
        s1s = [f for f in CG.SurfacesAt(c, bx, by, hs[j]).values() if abs(f.z - hs[j]) < 0.5]
        h = int(c.h)

        def walked(s0, s1):
            if CG.Line(c, s0.s, s0.ci, ax, ay, bx, by, s1.s) is not None:
                return True
            # (else one step of the search's own: a link to a neighbor cell, a diagonal round a corner)
            di, dj = s1.ci // h - s0.ci // h, s1.ci % h - s0.ci % h
            if (di, dj) not in C.DIRS:
                return False
            d = C.DIRS.index((di, dj)) + 1
            return CG.Link(c, s0.s, d) > 0 and CG.First(c, s1.ci) + CG.Link(c, s0.s, d) - 1 == s1.s
        assert any(walked(s0, s1) for s0 in s0s for s1 in s1s), (i, ax, ay, bx, by)


@pytest.mark.parametrize("a, b", TRIPS)
def test_the_lines_stay_on_the_walkable_ground(game, a, b):
    """Against our own Recast mesh (local only: data/navmesh, not on CI): no stretch of the line off the walkable
    floors past CHECK_OFF_YD (through a wall, over a gap)."""
    lua, ns = game
    name = _route(lua, ns, a, b).cityGrid
    city = next(c for c in C.CITIES if c.name == name)
    if not C.RM.mesh_path(city.mesh).exists():
        pytest.skip("needs the local WoW install (its navmesh, data/navmesh: agps navmesh build)")
    from azerothgps.navcompare import PolyIndex
    index = PolyIndex(C.RM.RecastMesh(C.RM.load(C.RM.mesh_path(city.mesh)), city.cont))
    r = _route(lua, ns, a, b)
    kinds, link = _list(r.kinds), r.onLink
    _total, _off, worst = C.walk_on_mesh(index, _list(r.pts), _heights(r),
                                         skip=lambda i: kinds[i] not in (0, 1) or link[i + 1])
    assert worst < C.CHECK_OFF_YD


# --- the height band and the floor ------------------------------------------------------------------------------------

def _readings(lua, rows):
    return lua.eval("function(rows) local out = {} for i, r in ipairs(rows) do out[i] = r end return out end")(
        lua.table(*[lua.table(**r) for r in rows]))


def test_the_band_from_in_and_out_of_range(game):
    lua, ns = game
    CG = ns.CityGrid
    slack = CG.RANGE_SLACK + CG.WANDER_YD
    # (in range 9.9 yd of an NPC at 10, straight under it: within 9.9 + slack)
    band = CG.Band(_readings(lua, [dict(x=0, y=0, z=10, r=9.9, inside=True)]), 0, 0)
    assert band[1][1] == pytest.approx(10 - 9.9 - slack) and band[1][2] == pytest.approx(10 + 9.9 + slack)
    # (out of range of it, 3 yd across: farther than sqrt(9.9^2 - (3 + wander)^2) up or down)
    band = CG.Band(_readings(lua, [dict(x=0, y=0, z=10, r=9.9, inside=False)]), 3, 0)
    h = math.sqrt(9.9 ** 2 - (3 + CG.WANDER_YD) ** 2)
    assert len(band) == 2 and band[1][2] == pytest.approx(10 - h) and band[2][1] == pytest.approx(10 + h)
    # (in range of 28 and out of 9.9: a shell)
    band = CG.Band(_readings(lua, [dict(x=0, y=0, z=0, r=28, inside=True), dict(x=0, y=0, z=0, r=9.9, inside=False)]), 0, 0)
    h = math.sqrt(9.9 ** 2 - CG.WANDER_YD ** 2)  # (the NPC up to WANDER_YD off its spawn: nearer across)
    assert [(round(iv[1], 1), round(iv[2], 1)) for iv in band.values()] == [(-33.0, -round(h, 1)), (round(h, 1), 33.0)]
    # (far across: no bound from an in-range reading's height, none from an out-of-range one)
    assert CG.Band(_readings(lua, [dict(x=0, y=0, z=0, r=9.9, inside=False)]), 30, 0)[1][1] == -math.inf
    assert CG.Band(lua.table(), 0, 0) is None


def test_the_floor_picked_by_the_band_and_the_walk(game):
    """Standing on the Drag over the Cleft of Shadow (two floors in the cell): the walk from the Cleft keeps the Cleft;
    from scratch, an NPC in the Cleft in reach (9.9 yd) picks the Cleft and out of it the Drag."""
    lua, ns = game
    CG = ns.CityGrid
    c = CG.City("Orgrimmar")
    # a cell with the Cleft and the Drag over it, near Zevrost
    spot = None
    for dx in range(-30, 31, 3):
        for dy in range(-30, 31, 3):
            here = CG.SurfacesAt(c, ZEVROST[1] + dx, ZEVROST[2] + dy)
            zs = sorted(f.z for f in here.values())
            if len(zs) >= 2 and abs(zs[0] - ZEVROST[3]) < 4 and zs[-1] - zs[0] > 15:
                spot = (ZEVROST[1] + dx, ZEVROST[2] + dy, zs[0], zs[-1])  # (the Cleft's floor, the Drag's)
                break
        if spot:
            break
    assert spot, "no stacked cell by the Cleft"
    x, y, low, high = spot
    ns.settings.gps.cityGrid = True
    lua.execute("AGPS_T = (AGPS_T or 0) + 100")
    look = CG.Look
    try:
        CG.track = None
        CG.readings = lua.table()
        assert CG.TrackFloor(1, x, y, None) is None  # (two floors, nothing else known: can't tell)
        CG.readings = lua.table(lua.table(x=x, y=y, z=low, r=9.9, inside=True, at=lua.eval("GetTime()"), px=x, py=y,
                                          level=1, src="interact3"))
        CG.Look = lua.eval("function() return AGPS_NS.CityGrid.readings end")
        CG.track = None
        assert CG.TrackFloor(1, x, y, None) == pytest.approx(low, abs=0.3)
        CG.readings[1].inside = False
        CG.track = None
        assert CG.TrackFloor(1, x, y, None) == pytest.approx(high, abs=0.3)
        # (no reading: walked there from Zevrost along the grid's way, down in the Cleft (one floor where he stands):
        # the Cleft kept under the Drag)
        CG.readings = lua.table()
        # (followed from Zevrost's own floor: an NPC's window there sets it, as Nav.AnchorFloor does)
        f = CG.SurfacesAt(c, ZEVROST[1], ZEVROST[2], ZEVROST[3])[1]
        CG.track = lua.eval("function(s, ci, x, y) return { name = 'Orgrimmar', level = 1, x = x, y = y, at = GetTime(),"
                            " set = { [s] = ci }, n = 1 } end")(f.s, f.ci, ZEVROST[1], ZEVROST[2])
        zl = f.z
        assert abs(zl - ZEVROST[3]) < 3
        r = ns.Router.Route(1, ZEVROST[1], ZEVROST[2], x, y, lua.table(z=ZEVROST[3], tz=low))
        assert r.cityGrid == "Orgrimmar"
        pts = _list(r.pts)
        z = zl
        for i in range(len(pts) // 2 - 1):
            ax, ay, bx, by = pts[2 * i:2 * i + 4]
            n = max(1, int(math.hypot(bx - ax, by - ay) / 2))
            for k in range(1, n + 1):
                lua.execute("AGPS_T = AGPS_T + 1")
                z = CG.TrackFloor(1, ax + (bx - ax) * k / n, ay + (by - ay) * k / n, None)
                assert z is None or z < high - 5, (i, k, z)  # (never up on the Drag)
        z = z if z is not None else CG.track.pick
        assert CG.track.n == 1 and abs(CG.track.z - low) < 1, (CG.track.n, CG.track.z, low, high)
    finally:
        CG.Look = look
        ns.settings.gps.cityGrid = False
        CG.track = None


def test_the_floor_command_reports_without_errors(game):
    lua, ns = game
    CG = ns.CityGrid
    lines = CG.FloorReport()
    assert len(lines) >= 1


# --- the frame budget -------------------------------------------------------------------------------------------------

FRAME_MS = 40  # (test_frame_budget.py's)


def test_the_search_runs_in_short_slices_in_the_background(game):
    lua, ns = game
    R, CG = ns.Router, ns.CityGrid
    lua.execute("AGPS_CLOCK_WAS = GetTime; GetTime = function() return os.clock() end")
    R.SYNC_WALKS = False
    ns.settings.gps.cityGrid = True
    try:
        CG.routes, CG.order = lua.table(), lua.table()
        r = R.Route(GARRETT[0], GARRETT[1], GARRETT[2], FARANELL[1], FARANELL[2], lua.table(z=GARRETT[3], tz=FARANELL[3]))
        assert r.pending  # (the Router's own meanwhile)
        clock = lua.eval("function() return os.clock() * 1000 end")
        worst, n = 0.0, 0
        while R.HasWork():
            a = clock()
            R.Pump(clock() + 1, clock)
            worst = max(worst, clock() - a)
            n += 1
        assert n > 3, "the search ran in one go"
        assert worst < FRAME_MS, f"a slice of the search ran {worst:.0f} ms"
        r = R.Route(GARRETT[0], GARRETT[1], GARRETT[2], FARANELL[1], FARANELL[2], lua.table(z=GARRETT[3], tz=FARANELL[3]))
        assert r.cityGrid == "Undercity" and not r.pending
    finally:
        R.SYNC_WALKS = True
        ns.settings.gps.cityGrid = False
        lua.execute("GetTime = AGPS_CLOCK_WAS")


def test_a_reroute_from_a_few_yards_on_joins_the_route_found(game):
    lua, ns = game
    CG = ns.CityGrid
    CG.routes, CG.order = lua.table(), lua.table()
    r = _route(lua, ns, GARRETT, FARANELL)
    pts = _list(r.pts)
    n = CG.stats.searches
    # (5 yd along its first stretch)
    ax, ay, bx, by = pts[:4]
    L = math.hypot(bx - ax, by - ay)
    t = min(1.0, 5 / L)
    here = (GARRETT[0], ax + (bx - ax) * t, ay + (by - ay) * t, GARRETT[3])
    r2 = _route(lua, ns, here, FARANELL)
    assert CG.stats.searches == n and r2.reused
    assert r2.length < r.length


def test_a_stop_with_no_height_over_the_cleft_of_shadow_is_on_its_floor_not_the_rock_top(game):
    # (the coordinator 2026-11-24, item 16 (b): a map click on the Cleft of Shadow's trainers, Mirket's spot, with no
    # height: the Drag's road over it, 46, was taken and the walk ended on the rock top over the Cleft. The road nearest
    # the terrain's height (the Cleft's, -12; the terrain -25): its floor, reached through the tunnel)
    lua, ns = game
    CG = ns.CityGrid
    valley, mirket = (1778.0, -4354.0, 42.0), (1834.7, -4362.5)
    ns.settings.gps.cityGrid = True
    try:
        CG.routes, CG.order = lua.table(), lua.table()
        r = CG.Leg(1, valley[0], valley[1], mirket[0], mirket[1], lua.table(z=valley[2]))
        if r == "pending":
            pytest.skip("searched in the background")
        assert r and r.pts, r
        zs = r.zs or r.fz
        z = [zs[i] for i in range(1, len(zs) + 1)]
        assert z[-1] < 0, z[-1]  # (the Cleft's floor, about -14; not the rock top at 45)
    finally:
        ns.settings.gps.cityGrid = False


def test_the_floor_followed_is_held_from_the_great_forge_on(game):
    # (item 18, the coordinator 2026-11-24: Ironforge's Forge to the Hall of Thanes, the route flipped between a 100 yd
    # and a 640 yd way as the start's floor was guessed again: the track was dropped at the Forge's edge, outside the
    # capital's outline. Held there, and walking on through the hall the floor followed stays the hall's)
    lua, ns = game
    CG = ns.CityGrid
    ns.settings.gps.cityGrid = True
    try:
        CG.track = None
        x, y = -4826.0, -1138.0  # (the Forge's edge: the city grid's floor, 502.8, outside the outline)
        lua.execute("AGPS_T = (AGPS_T or 0) + 1")
        CG.TrackFloor(0, x, y, 502.8)
        assert CG.track is not None and abs((CG.track.z or CG.track.pick) - 502.8) <= 4
        zs = []
        for k in range(12):  # (on toward the Hall of Thanes, 5 yd a step)
            y += 5
            lua.execute("AGPS_T = AGPS_T + 1")
            CG.TrackFloor(0, x, y, None)
            t = CG.track
            zs.append(CG.TrackFloor(0, x, y, None) or (t and (t.z or t.pick)))
        assert all(z is not None and abs(z - 502.8) <= 6 for z in zs), zs
    finally:
        CG.track = None
        ns.settings.gps.cityGrid = False
