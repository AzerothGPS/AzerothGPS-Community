"""Floors, stairs, bridges, lifts and jumps found in our own Recast meshes (navfeatures.py; asked 2026-11-22: "detect
stairs/bridges/floors automatically for route data ... When creating the city grid, automatically determine bridges,
stairs, lifts, etc.", and "consider marking jump spots too for directions, that would show orange arrow and directions
to jump"): baked into Data/CityGrid.lua (the road links' kinds, the found jumps' links, the stairs' and bridges' lines),
said by Turns along the grid's walks, the arrow orange at a jump."""

import math
import re

import pytest

from azerothgps import citygrid as C
from azerothgps import navfeatures as F
from azerothgps.paths import ADDON_DIR

pytest.importorskip("lupa.lua51")

DATA = ADDON_DIR / "Data" / "CityGrid.lua"

# (known spots; Data/Npcs.lua's spawns: level, x, y, z)
# Thunder Bluff's rope bridge from the central mesa east (Router.BridgeAt agrees: a raised deck over the capital's own
# cells): its middle, and spots 12 yd off each of its ends
TB_ROPE_BRIDGE = (-1069.0, 161.0, 142.0)
TB_BRIDGE_WEST, TB_BRIDGE_EAST = (1, -1105.9, 129.0, 146.0), (1, -1032.2, 193.3, 138.7)
# Orgrimmar's ledge by the Valley of Strength's bank, a drop the city's roads already have (Router's drops, one way)
ORG_DROP_TOP, ORG_DROP_FOOT = (1635.0, -4301.0, 28.0), (1627.0, -4307.0, 20.0)
# Orgrimmar's gate from Durotar: the incline in (a smooth ramp, no risers; it said "Stairs up", Kooki3z 2026-11-22)
ORG_GATE_RAMP = (1360.0, -4384.0)
ORG_OUTSIDE, ORG_BANK = (1, 1320.0, -4385.0, None), (1, 1627.3, -4376.1, 11.8)
# Orgrimmar's spiral stairs by the Valley of Honor (a flight the old stairs roads have too, source 6)
ORG_STAIRS = (1960.0, -4466.0)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    yield lua, ns
    ns.settings.gps.cityGrid = False


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else None


def _entries():
    txt = DATA.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'ns\.CityGridData\["([^"]+)"\] = \{(.*?)\n\}', txt, re.S):
        out[m.group(1)] = dict(re.findall(r'\b(\w+) = "([^"]*)"', m.group(2)))
    return out


def _links(name):
    out = []
    for item in _entries()[name]["links"].split(";"):
        v = [float(x) for x in item.split(",")]
        out.append({"a": int(v[0]), "b": int(v[1]), "cost": v[2], "kind": int(v[3]),
                    "pts": [tuple(v[k:k + 3]) for k in range(4, len(v) - 2, 3)]})
    return out


def _feats(name):
    out = []
    for item in _entries()[name].get("feat", "").split(";"):
        if item:
            v = [float(x) for x in item.split(",")]
            out.append((int(v[0]), v[1], [tuple(v[k:k + 3]) for k in range(2, len(v) - 2, 3)]))
    return out


def _route(lua, ns, a, b, on=True):
    ns.settings.gps.cityGrid = on
    try:
        return ns.Router.Route(a[0], a[1], a[2], b[1], b[2], lua.table(z=a[3], tz=b[3]))
    finally:
        ns.settings.gps.cityGrid = False


def _said(lua, ns, r, cont):
    T = ns.Turns
    part = lua.table(pts=r.pts, kinds=r.kinds, cont=cont, stop=1, fz=r.fz, zs=r.zs)
    path = T.Path(lua.table(parts=lua.table(part)))
    ms = T.Maneuvers(path, "the stop")
    return path, [(str(ms[i].kind), str(ms[i].text), ms[i].dist) for i in range(1, len(ms) + 1)]


# --- the bake ---------------------------------------------------------------------------------------------------------

def test_the_found_stairs_bridges_and_jumps_are_numbers_in_every_city():
    for city in C.CITIES:
        e = _entries()[city.name]
        assert re.fullmatch(r"[\d.,;-]*", e.get("feat", "")), city.name  # (numbers only)
        feats = _feats(city.name)
        assert any(k == F.FEAT_STAIRS for k, _w, _p in feats), city.name
        kinds = {L["kind"] for L in _links(city.name)}
        if city.found_jumps:
            assert C.KIND_DROP in kinds, city.name  # (the roads' drops and the jumps found)
    assert any(k == F.FEAT_BRIDGE for k, _w, _p in _feats("Thunder Bluff"))


def test_the_bake_stamp_has_the_detectors_parameters():
    """A change to navfeatures' parameters without `agps city-grid --write` fails test_city_grid's staleness test."""
    was = F.JUMP_SAVE
    try:
        before = C.bake_stamp()
        F.JUMP_SAVE = was + 1
        assert C.bake_stamp() != before
    finally:
        F.JUMP_SAVE = was


def test_found_jumps_are_never_past_the_big_drop():
    """Every drop of the grid is at most BIG_DROP (a fall spell's) down; past SAFE_DROP (Nav.FALL_FREE) they're taken
    only while a fall spell is ready (CityGrid.MaxDrop)."""
    for city in C.CITIES:
        for L in _links(city.name):
            if L["kind"] == C.KIND_DROP:
                assert L["pts"][0][2] - L["pts"][-1][2] <= F.BIG_DROP + 0.5, (city.name, L)


# --- known spots ------------------------------------------------------------------------------------------------------

def test_orgrimmars_ledge_drop_is_a_jump_on_the_grid(game):
    """A drop the city's roads have (Router's drops: one way down a ledge by the bank) is the grid's KIND_DROP link (it
    was a plain walk link before), so a grid route down it says "Jump down here" and turns the arrow orange."""
    near = [L for L in _links("Orgrimmar") if L["kind"] == C.KIND_DROP
            and math.dist(L["pts"][0][:2], ORG_DROP_TOP[:2]) < 8 and math.dist(L["pts"][-1][:2], ORG_DROP_FOOT[:2]) < 8]
    assert near and all(L["pts"][0][2] > L["pts"][-1][2] + F.JUMP_MIN for L in near)
    lua, ns = game
    top, foot = (1, 1643.0, -4295.0, 27.0), (1, 1622.0, -4312.0, 20.0)  # (from the top's floor to the foot's)
    # (Kooki3z 2026-11-23: no hop in a city without Expert jumper, the walkway walked; an Expert jumper jumps)
    r = _route(lua, ns, top, foot)
    assert r.cityGrid == "Orgrimmar" and ns.Router.KIND_DROP not in _list(r.kinds)
    ns.settings.gps.expertJumper = True
    try:
        r = _route(lua, ns, top, foot)
    finally:
        ns.settings.gps.expertJumper = None
    assert r.cityGrid == "Orgrimmar" and ns.Router.KIND_DROP in _list(r.kinds)
    # (Kooki3z 2026-11-23, "saying jump here really should be like 25 yd or more": this ~7 yd one is just walked)
    _path, said = _said(lua, ns, r, 1)
    assert not [t for k, t, _d in said if k == "drop"], said
    ns.Router.JUMP_CALLOUT_YD = 0
    try:
        _path, said = _said(lua, ns, r, 1)
    finally:
        ns.Router.JUMP_CALLOUT_YD = 25
    # (said though the stop is just past it: a jump near the end isn't left out as the turns there are)
    # (with its fall where known, item 113a: "Jump down here (7 yd)")
    drops = [t for k, t, _d in said if k == "drop"]
    assert len(drops) == 1 and re.fullmatch(r"Jump down here( \(\d+ yd\))?", drops[0]), said


def test_a_known_stair_is_found_and_said_on_a_grid_walk(game):
    """Orgrimmar's spiral stairs: a flight found in the mesh (the old stairs roads have it too), so the grid's
    walk up them (kind 1, no road) says "Take the stairs up" (Turns.Stairs by CityGrid.StairAt); with the option off,
    StairAt is never asked."""
    lua, ns = game
    CG = ns.CityGrid
    st = [f for f in _feats("Orgrimmar") if f[0] == F.FEAT_STAIRS
          and min(math.dist(p[:2], ORG_STAIRS) for p in f[2]) < 6]
    assert st, "no stairs found there"
    _k, _w, pts = st[0]
    lo, hi = pts[0], pts[-1]
    assert hi[2] - lo[2] >= F.STAIR_RISE
    ns.settings.gps.cityGrid = True
    try:
        assert CG.StairAt(1, lo[0], lo[1], hi[0], hi[1]) == 1 and CG.StairAt(1, hi[0], hi[1], lo[0], lo[1]) == -1
    finally:
        ns.settings.gps.cityGrid = False
    was = ns.settings.gps.worldGrid
    ns.settings.gps.worldGrid = False  # (on by default since b17a8f8c, and it takes the capitals' grids with it)
    try:
        assert CG.StairAt(1, lo[0], lo[1], hi[0], hi[1]) is None  # (the options off)
    finally:
        ns.settings.gps.worldGrid = was
    # (the directions: a grid walk up the flight's line, its floors rising, is a flight up)
    flat = [v for p in pts for v in p[:2]]
    part = lua.table(pts=lua.table(*flat), kinds=lua.table(*([ns.Router.KIND_OFFROAD] * (len(pts) - 1))), cont=1,
                     stop=1, fz=lua.table(*[p[2] for p in pts]))
    path = ns.Turns.Path(lua.table(parts=lua.table(part)))
    ns.settings.gps.cityGrid = True
    try:
        flights = ns.Turns.Stairs(path)
        assert len(flights) == 1 and flights[1].dir == 1
    finally:
        ns.settings.gps.cityGrid = False
    was = ns.settings.gps.worldGrid
    ns.settings.gps.worldGrid = False  # (on by default since b17a8f8c: the capitals' grids with it)
    try:
        assert len(ns.Turns.Stairs(path)) == 0
    finally:
        ns.settings.gps.worldGrid = was


def test_thunder_bluffs_rope_bridge_is_found_and_crossed(game):
    """Thunder Bluff's rope bridge to the Elder Rise: a deck found in the mesh (narrow, open both sides, a long drop
    under it), so a grid walk over it says "Cross the bridge" (Turns.Places by CityGrid.BridgeAt); the Router's own
    capital overlay calls it a bridge too."""
    lua, ns = game
    CG = ns.CityGrid
    x, y, z = TB_ROPE_BRIDGE
    ns.settings.gps.cityGrid = True
    try:
        assert CG.BridgeAt(1, x, y, z) and not CG.BridgeAt(1, x, y, z - 40)  # (not the land under it)
    finally:
        ns.settings.gps.cityGrid = False
    was = ns.settings.gps.worldGrid
    ns.settings.gps.worldGrid = False  # (on by default since b17a8f8c, and it takes the capitals' grids with it)
    try:
        assert not CG.BridgeAt(1, x, y, z)  # (the options off)
    finally:
        ns.settings.gps.worldGrid = was
    r = _route(lua, ns, TB_BRIDGE_WEST, TB_BRIDGE_EAST)
    assert r.cityGrid == "Thunder Bluff"
    ns.settings.gps.cityGrid = True
    try:
        path, said = _said(lua, ns, r, 1)
    finally:
        ns.settings.gps.cityGrid = False
    bridges = [d for k, _t, d in said if k == "bridge"]
    assert bridges, said
    assert any(math.dist(ns.Turns.PointAt(path, d + 10), (x, y)) < 60 for d in bridges)


def test_undercitys_lifts_are_found_on_its_mesh():
    """Undercity's three lifts to the Ruins (Data/Cities.lua's lifts): each found on the city's mesh, a floor at its
    foot and one 100 yd and more over it, no walk between. Needs the mesh (dev data: not on CI)."""
    from azerothgps import recastmesh as RM
    p = RM.mesh_path("undercity")
    if not p.exists():
        pytest.skip("needs the local WoW install (its navmesh, data/navmesh: agps navmesh build)")
    mesh = C.Mesh(RM.load(p), 0)
    feats = F.Features("Undercity", 2.0)
    known = [("west", (1595.0, 290.3, -41.5), None, 25), ("east", (1596.4, 190.1, -41.5), None, 25),
             ("north", (1545.7, 239.6, -41.5), None, 25)]
    F.find_lifts(mesh, feats, known)
    assert [L["found"] for L in feats.lifts] == [True, True, True]
    for L in feats.lifts:
        assert abs(L["foot"] - -41.5) < 3 and L["rise"] > 90 and not L["walked"] and L["conf"] >= F.USE_CONF


# --- the jump said and shown ----------------------------------------------------------------------------------------

def _hop_path(lua, ns, kind):
    """A walk with a jump of `kind` in its middle: 40 yd on, the jump, 40 yd on."""
    part = lua.table(pts=lua.table(0.0, 0.0, 40.0, 0.0, 43.0, 0.0, 83.0, 0.0),
                     kinds=lua.table(ns.Router.KIND_OFFROAD, kind, ns.Router.KIND_OFFROAD), cont=1, stop=1)
    return ns.Turns.Path(lua.table(parts=lua.table(part)))


def test_a_jump_across_is_said_there_and_ahead(game):
    lua, ns = game
    T, R = ns.Turns, ns.Router
    path = _hop_path(lua, ns, R.KIND_JUMP)
    ms = T.Maneuvers(path, "the stop")
    said = [(str(ms[i].kind), str(ms[i].text), ms[i].dist) for i in range(1, len(ms) + 1)]
    jumps = [(t, d) for k, t, d in said if k == "jump"]
    assert jumps == [("Jump across here", 40.0)], said
    assert not [k for k, _t, _d in said if k in ("join", "leave")], said  # (no road joined or left at it)
    m = [ms[i] for i in range(1, len(ms) + 1) if str(ms[i].kind) == "jump"][0]
    m.dist = 10
    fmt = lua.eval("function(d) return string.format('%d yd', d) end")
    assert str(T.NowText(m, fmt)) == "Continue straight, then jump across in 10 yd"
    m.dist = 3
    assert str(T.NowText(m, fmt)) == "Jump across here"
    # (a drop the same way: "Jump down here", and no "Leave the road" at a walk's drop)
    ms = T.Maneuvers(_hop_path(lua, ns, R.KIND_DROP), "the stop")
    said = [(str(ms[i].kind), str(ms[i].text)) for i in range(1, len(ms) + 1)]
    assert ("drop", "Jump down here") in said and not [k for k, _t in said if k in ("join", "leave")], said


def test_the_arrow_turns_orange_near_a_jump_and_back_after(game):
    lua, ns = game
    A = ns.Arrow
    for kind in ("drop", "jump"):
        near = lua.table(kind=kind, dist=A.JUMP_ORANGE_YD - 2)
        color, icon = A.ColorFor(near, 0.0)
        assert color == 4 and icon is False, kind  # (orange; no pulsing jump icon: Kooki3z, "might confuse with ... slow fall")
        far = lua.table(kind=kind, dist=A.JUMP_ICON_YD + 20)
        color, icon = A.ColorFor(far, 0.0)
        assert color == 1 and icon is False, kind  # (back to green heading the right way)
    color, icon = A.ColorFor(lua.table(kind="turn", dist=3), math.radians(60))
    assert color == 2 and icon is False
    assert A.ColorFor(None, math.radians(150))[0] == 3


def test_a_jump_has_no_icon_on_the_map(game):
    """Kooki3z 2026-11-22: "don't show the jump down here icon on the map, directions is enough": the map's route icons
    (G.AddRouteStairs) have none at a jump."""
    lua, ns = game
    G, R = ns.GPS, ns.Router
    route = lua.table(parts=lua.table(lua.table(pts=lua.table(0.0, 0.0, 40.0, 0.0, 43.0, 0.0, 83.0, 0.0),
                                                kinds=lua.table(R.KIND_OFFROAD, R.KIND_JUMP, R.KIND_OFFROAD),
                                                cont=1, stop=1)))
    pois = lua.table()
    G.AddRouteStairs(pois, route, 1, 40.0, 0.0, 0.0, 1.0, 200.0)
    got = [pois[i] for i in range(1, len(pois) + 1)]
    assert not [p for p in got if "Jump" in str(p[4])], [dict(p) for p in got]


# --- at a jump: held until it's taken -------------------------------------------------------------------------------

ORG_LEDGE_TOP, ORG_LEDGE_FOOT = (1633.0, -4301.0), (1627.0, -4306.0)  # (the drop link by the bank: test above)
ORG_ABOVE, ORG_BELOW = (1643.0, -4295.0, 27.0), (1622.0, -4312.0, 20.0)


def _jump_trip(lua, ns):
    """Nav's route from above Orgrimmar's ledge to below it, the city grid on: (N, G, the step text function)."""
    G, N, CG = ns.GPS, ns.Nav, ns.CityGrid
    CG.Set(True)
    ns.settings.gps.expertJumper = True  # (a city's hops only for an Expert jumper; the callers' finally turns it off)
    # (the ledge's ~7 yd is under Router.JUMP_CALLOUT_YD, no step since 2026-11-23: called out here to test the hold;
    # _jump_done puts it back)
    ns.Router.JUMP_CALLOUT_YD = 0
    N.Clear()
    lua.execute("IsFalling = function() return false end")
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = %.1f, %.1f, 1" % ORG_ABOVE[:2])
    N.SetStops(lua.eval("{ { x = %.1f, y = %.1f, cont = 1, name = 'Stop', z = %.1f } }" % ORG_BELOW), False, "red")
    G.Follow()

    def step(x, y, n=6):
        lua.execute("AGPS_POS[1], AGPS_POS[2] = %.2f, %.2f" % (x, y))
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        r = N.route
        _path, ms = ns.Turns.Ahead(r, "the stop")
        return r, [ms[i] for i in range(1, len(ms) + 1)] if ms is not None else []
    return N, G, step


def _jump_done(lua, ns):
    ns.Router.JUMP_CALLOUT_YD = 25
    ns.CityGrid.Set(False)
    ns.Nav.Clear()
    lua.execute("IsFalling = nil")
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
    ns.GPS.Follow()


def test_at_a_ledges_top_the_jump_step_stays_until_the_player_falls(game):
    """Kooki3z 2026-11-22: "when at a jump down location, don't clear until jump happens or rerouting is needed". At
    the ledge's top (its foot only a few yards off across) the next step is still "Jump down here" and the arrow orange,
    aiming at the path past the drop; IsFalling there takes it, and the next step shows."""
    lua, ns = game
    N, G, step = _jump_trip(lua, ns)
    try:
        r, ms = step(*ORG_ABOVE[:2])
        assert ms and str(ms[0].kind) == "drop", [str(m.kind) for m in ms]
        for _ in range(3):  # (standing at the top, a few updates on)
            r, ms = step(ORG_LEDGE_TOP[0] + 0.5, ORG_LEDGE_TOP[1] + 0.5)
            assert str(ms[0].kind) == "drop" and str(ms[0].text).startswith("Jump down here"), [str(m.text) for m in ms]
            assert ns.Arrow.ColorFor(ms[0], 0.0)[0] == 4
        # (the arrow aims at the path past the drop, not at the ledge)
        path = ns.Turns.Path(r)
        tx, ty = ns.Turns.Target(path, ORG_LEDGE_TOP[0] + 0.5, ORG_LEDGE_TOP[1] + 0.5)
        foot = ns.Turns.JumpAhead(path, 0)
        assert foot is not None and ns.Turns.AlongNear(path, tx, ty) > foot + 5
        # (falling there: taken, the next step on)
        lua.execute("IsFalling = function() return true end")
        r, ms = step(ORG_LEDGE_TOP[0] - 1.0, ORG_LEDGE_TOP[1] - 1.0, 2)
        lua.execute("IsFalling = function() return false end")
        r, ms = step(ORG_LEDGE_FOOT[0], ORG_LEDGE_FOOT[1])
        assert not [m for m in ms if str(m.kind) == "drop"], [str(m.text) for m in ms]
    finally:
        ns.settings.gps.expertJumper = None
        _jump_done(lua, ns)


def test_walking_away_from_a_ledges_top_reroutes(game):
    """At the top, walking off from the ledge (back the way they came, past JUMP_LEAVE_YD) works the route out again
    instead of keeping the jump held."""
    lua, ns = game
    N, G, step = _jump_trip(lua, ns)
    try:
        r0, ms = step(ORG_LEDGE_TOP[0] + 0.5, ORG_LEDGE_TOP[1] + 0.5)
        assert str(ms[0].kind) == "drop"
        top, _leave = ns.Nav.JumpHold(r0, ORG_LEDGE_TOP[0] + 0.5, ORG_LEDGE_TOP[1] + 0.5)
        assert top is not None and r0.atJump == top  # (at the top: held there)
        _i, leave = ns.Nav.JumpHold(r0, ORG_LEDGE_TOP[0] + 14.0, ORG_LEDGE_TOP[1] + 9.0)
        assert leave is True  # (walked off from it)
        r1, _ms = step(ORG_LEDGE_TOP[0] + 14.0, ORG_LEDGE_TOP[1] + 9.0)
        assert r1 is not r0 or r1.atJump is None  # (worked out again: not the held route)
    finally:
        ns.settings.gps.expertJumper = None
        _jump_done(lua, ns)


# --- stairs or a ramp -------------------------------------------------------------------------------------------------

def test_orgrimmars_gate_ramp_says_no_stairs(game):
    """The incline in through Orgrimmar's gate is a smooth ramp: no stairs line there in the data, CityGrid.StairAt
    finds none, and a grid walk up it with its heights rising (the generic slope rule's case: 5 yd up in 12) says no
    stairs; the route in from Durotar says none near it."""
    near = [f for f in _feats("Orgrimmar") if f[0] == F.FEAT_STAIRS
            and min(math.dist(p[:2], ORG_GATE_RAMP) for p in f[2]) < 15]
    assert not near, near
    lua, ns = game
    T, R, CG = ns.Turns, ns.Router, ns.CityGrid
    part = lua.table(pts=lua.table(1355.4, -4384.4, 1360.5, -4384.5, 1366.5, -4384.5),
                     kinds=lua.table(R.KIND_OFFROAD, R.KIND_OFFROAD), cont=1, stop=1, zs=lua.table(5.4, 9.2, 13.7))
    path = T.Path(lua.table(parts=lua.table(part)))
    ns.settings.gps.cityGrid = True
    try:
        assert CG.StairAt(1, 1355.4, -4384.4, 1366.5, -4384.5) is None
        assert len(T.Stairs(path)) == 0
    finally:
        ns.settings.gps.cityGrid = False
    r = _route(lua, ns, ORG_OUTSIDE, ORG_BANK)
    assert r.cityGrid == "Orgrimmar"
    ns.settings.gps.cityGrid = True
    try:
        p2, said = _said(lua, ns, r, 1)
    finally:
        ns.settings.gps.cityGrid = False
    st = [d for k, _t, d in said if k == "stairs"]
    assert not [d for d in st if math.dist(T.PointAt(p2, d), ORG_GATE_RAMP) < 40], said


def test_stairs_have_risers_and_a_ramp_has_none():
    """The detector tells stairs from a ramp by the collision's height profile (stepped: risers steeper than a walk);
    Orgrimmar's gate ramp is smooth, its spiral stairs stepped. Needs the triangles (dev data: not on CI)."""
    tris = F.Tris.load("orgrimmar")
    if tris is None:
        pytest.skip("needs the local WoW install (its collision triangles, data/navmesh: agps navmesh tris)")
    st = [f for f in _feats("Orgrimmar") if f[0] == F.FEAT_STAIRS
          and min(math.dist(p[:2], ORG_STAIRS) for p in f[2]) < 6]
    assert st and F.is_stairs(tris, st[0][2])
    ramp = [(1355.4, -4384.4, 5.4), (1360.5, -4384.5, 9.2), (1366.5, -4384.5, 13.7)]  # (up the incline: the grid's)
    share, _risers = F.stepped(tris, ramp)
    assert share < F.RISER_SHARE and not F.is_stairs(tris, ramp)


# --- bridges on the grids' walks ------------------------------------------------------------------------------------

# Stormwind, from the Canals into the Trade District (Kooki3z's video, 2026-11-22: "bridge detection was after the
# bridge not on it"): an open stone canal bridge, then the gatehouse's covered passage over the canal
SW_OPEN_BRIDGE = (-8722.0, 525.0, 100.2)  # (its middle; the walk crosses it heading west)
SW_GATE_PASSAGE = [(-8748.0, 581.0, 98.0), (-8752.0, 585.0, 98.0), (-8756.0, 589.0, 98.0)]
SW_CANALS, SW_TRADE = (0, -8690.0, 470.0, None), (0, -8790.0, 640.0, None)


def test_stormwinds_open_canal_bridge_is_said_at_its_start_and_the_gate_passage_is_not_a_bridge(game):
    """The open canal bridge is said where it starts (not after it), and the covered passage through the Trade
    District's gatehouse (a vault over the body: the models' ceilings) is no bridge."""
    lua, ns = game
    CG = ns.CityGrid
    ns.settings.gps.cityGrid = True
    try:
        assert CG.BridgeAt(0, *SW_OPEN_BRIDGE)
        for p in SW_GATE_PASSAGE:
            assert not CG.BridgeAt(0, *p), p
    finally:
        ns.settings.gps.cityGrid = False
    r = _route(lua, ns, SW_CANALS, SW_TRADE)
    assert r.cityGrid == "Stormwind City"
    ns.settings.gps.cityGrid = True
    try:
        path, said = _said(lua, ns, r, 0)
    finally:
        ns.settings.gps.cityGrid = False
    T = ns.Turns
    at = [(d, T.PointAt(path, d)) for k, _t, d in said if k == "bridge"]
    # (said where it starts: the walk's first yards on its arch, (-8720, 520), not on its top or after it)
    near = [(d, p) for d, p in at if math.dist(p, SW_OPEN_BRIDGE[:2]) < 20]
    assert len(near) == 1, said
    d0 = near[0][0]
    foot = min(range(0, int(path.total)), key=lambda s: math.dist(T.PointAt(path, s), (-8720.0, 520.0)))
    assert foot - 6 <= d0 <= foot + 2, (d0, foot)
    # (nothing said as a bridge in the passage)
    assert not [p for _d, p in at if min(math.dist(p, q[:2]) for q in SW_GATE_PASSAGE) < 8], said


SW_PARK_PASSAGE = [(-8774.0, 971.0, 100.5), (-8780.0, 963.0, 100.5), (-8786.0, 957.0, 100.5)]  # (map 43, 66: vaulted)


def test_stormwinds_park_gate_passage_is_not_a_bridge(game):
    """Kooki3z 2026-11-22, standing in The Park at its east gate's vaulted passage over the canal: "still showing this as
    a bridge crossing in addition to the actual bridge". A deck under a barrel vault (up to 15 yd over it, probed round
    each cell) or between a passage's tall walls is no bridge; the walk out of the Park east says none there."""
    lua, ns = game
    CG = ns.CityGrid
    ns.settings.gps.cityGrid = True
    try:
        for p in SW_PARK_PASSAGE:
            assert not CG.BridgeAt(0, *p), p
    finally:
        ns.settings.gps.cityGrid = False
    r = _route(lua, ns, (0, -8764.0, 990.0, None), (0, -8770.0, 880.0, None))
    ns.settings.gps.cityGrid = True
    try:
        path, said = _said(lua, ns, r, 0)
    finally:
        ns.settings.gps.cityGrid = False
    at = [ns.Turns.PointAt(path, d) for k, _t, d in said if k == "bridge"]
    assert not [p for p in at if min(math.dist(p, q[:2]) for q in SW_PARK_PASSAGE) < 12], said


# Ironforge's stone flights (Kooki3z 2026-11-22: "not seeing take stairs in ironforge"): collision ramps over their steps,
# so the riser test alone called them ramps; the city's stairs roads (source 6) running up them make them stairs
IF_FIRST_AID_STAIRS = [(-4887.8, -1153.1, 507.0), (-4885.5, -1147.5, 511.3), (-4883.2, -1146.5, 512.7)]  # (Nissa)
IF_OTHER_STAIRS = [(-5017.8, -1198.7, 502.0), (-5025.9, -1203.3, 508.3)]


@pytest.mark.parametrize("flight", [IF_FIRST_AID_STAIRS, IF_OTHER_STAIRS], ids=["first_aid", "great_forge_side"])
def test_ironforges_stone_stairs_are_said_on_a_grid_walk(game, flight):
    lua, ns = game
    CG, T, R = ns.CityGrid, ns.Turns, ns.Router
    lo, hi = flight[0], flight[-1]
    flat = [v for p in flight for v in p[:2]]
    part = lua.table(pts=lua.table(*flat), kinds=lua.table(*([R.KIND_OFFROAD] * (len(flight) - 1))), cont=0, stop=1,
                     fz=lua.table(*[p[2] for p in flight]))
    path = T.Path(lua.table(parts=lua.table(part)))
    ns.settings.gps.cityGrid = True
    try:
        assert CG.StairAt(0, lo[0], lo[1], hi[0], hi[1]) is not None
        flights = T.Stairs(path)
        assert len(flights) == 1 and flights[1].dir == 1
        ms = T.Maneuvers(path, "the stop")
        assert [str(ms[i].text) for i in range(1, len(ms) + 1) if str(ms[i].kind) == "stairs"] == ["Take the stairs up"]
    finally:
        ns.settings.gps.cityGrid = False


def test_a_stairs_road_makes_a_ramp_shaped_flight_stairs_and_not_the_gate_incline():
    feats = F.Features("t", 3.0)
    feats.stairs = [{"kind": "ramp", "width": 3.0, "rise": 6.0, "pts": [(0.0, 0.0, 0.0), (10.0, 0.0, 6.0)]},
                    {"kind": "ramp", "width": 3.0, "rise": 6.0, "pts": [(0.0, 50.0, 0.0), (10.0, 50.0, 6.0)]}]
    roads = [(1, 6, False, [(1.0, 0.5, 0.6), (5.0, 0.5, 3.0), (9.0, 0.5, 5.4)]),
             (2, 0, False, [(1.0, 50.5, 0.6), (9.0, 50.5, 5.4)])]  # (a plain road up the second: no stairs)
    assert F.stairs_roads(feats, roads) == 1
    assert [s["kind"] for s in feats.stairs] == ["stairs", "ramp"]


# --- Undercity: no jumps off its rings, no walk through its slime -----------------------------------------------------

UC_TRADE_RING_TOP = (10001, 1577.1, 210.3, -43.0)  # (map 69.1, 47.0: the Trade Quarter ring's top floor)
UC_FIRST_AID = (10001, 1525.0, 171.4, -62.1)  # (Mary Edras, 19 yd below)


def test_undercity_routes_down_from_the_ring_take_no_found_jump(game):
    """Kooki3z 2026-11-22: "from the top floor in UC, routing to anything lower wants me to go through the wall then
    jump". Undercity's rings' railings aren't in the collision read, so no jump found in its mesh is a link
    (City.found_jumps); the way down is the ramps and stairs."""
    lua, ns = game
    assert not [c for c in C.CITIES if c.name == "Undercity"][0].found_jumps
    found = [L for L in _links("Undercity") if L["kind"] == C.KIND_DROP and L["cost"] >= F.JUMP_COST
             and len(L["pts"]) == 2]
    assert not found
    r = _route(lua, ns, UC_TRADE_RING_TOP, UC_FIRST_AID)
    assert r.cityGrid == "Undercity"
    assert ns.Router.KIND_DROP not in _list(r.kinds)


UC_CANAL_SOUTH = (10001, 1728.0, 332.0, -49.0)  # (map 56.4, 23.4: the walkway south of the War Quarter's canal)
UC_CANAL_NORTH = (10001, 1768.0, 332.0, None)


def test_undercity_routes_cross_its_canals_by_a_bridge_not_through_the_slime(game):
    """Kooki3z 2026-11-22, the War Quarter's canal: the route went straight across the green slime, "the actual
    bridge here" a little west. The grid has no surface under the slime (City.dry), so no stretch of the route is in it."""
    lua, ns = game
    from azerothgps import navfeatures as NF
    r = _route(lua, ns, UC_CANAL_SOUTH, UC_CANAL_NORTH)
    assert r.cityGrid == "Undercity"
    tris = NF.Tris.load("undercity")
    if tris is None:
        return  # (CI: no liquids to look at; the data's no surface in it holds the same)
    pts, zs = _list(r.pts), _list(r.zs)
    for i in range(len(zs) - 1):
        (ax, ay), (bx, by) = pts[2 * i:2 * i + 2], pts[2 * i + 2:2 * i + 4]
        L = max(1, int(math.dist((ax, ay), (bx, by))))
        for k in range(L + 1):
            u = k / L
            x, y, z = ax + (bx - ax) * u, ay + (by - ay) * u, zs[i] + (zs[i + 1] - zs[i]) * u
            assert not tris.wet(x, y, z + 0.5, 0.0), (x, y, z)


def test_stormwinds_cathedral_steps_are_said_on_the_way_to_the_paladin_trainer(game):
    """Kooki3z 2026-11-22 at the foot of the Cathedral of Light's steps: "Straight, then arrive at Stormwind Paladin
    Trainer in 122 yd / 9 yd up", no "Take the stairs up", "clearly steps here". The steps' slope area joined the square
    and the plaza, a piece of open ground with its median height at the square's: the flight is now found between
    the heights where the area meets each, and has risers."""
    lua, ns = game
    spots = C.npc_spots({"Lord Grayson Shadowbreaker"})
    lord = spots["Lord Grayson Shadowbreaker"]
    r = _route(lua, ns, (0, -8556.0, 893.0, 97.0), lord)
    assert r.cityGrid == "Stormwind City"
    ns.settings.gps.cityGrid = True
    try:
        _path, said = _said(lua, ns, r, 0)
    finally:
        ns.settings.gps.cityGrid = False
    assert "Take the stairs up" in [t for k, t, _d in said if k == "stairs"], said


SPIRIT_RISE_TOP = (1, -969.7, 235.9, 134.0)  # (map 26.9, 17.2)
MILES_WELSH = (1, -956.2, 252.4, 97.9)  # (the Pools of Vision, 37 yd under the rise)


def test_thunder_bluffs_spirit_rise_to_the_pools_takes_no_jump_past_the_safe_drop(game):
    """Kooki3z 2026-11-22: "Jump down here / Below you, 37 yd down", "should be routing to the entrance underneath here,
    not telling me to jump". The roads' 36 yd drop there is left out (the grid has a way down: a drop past SAFE_DROP is
    kept only where there's none, and only with a clear take-off and landing), and
    Thunder Bluff's mesh jumps aren't links (its rails and fences, as Undercity's); the way down is the Pools' tunnel."""
    lua, ns = game
    r = _route(lua, ns, SPIRIT_RISE_TOP, MILES_WELSH)
    assert r.cityGrid == "Thunder Bluff"
    assert ns.Router.KIND_DROP not in _list(r.kinds)
    hs = _list(r.fz)
    assert abs(hs[0] - SPIRIT_RISE_TOP[3]) < 4 and abs(hs[-1] - MILES_WELSH[3]) < 4, (hs[0], hs[-1])
    assert r.length > 60  # (down the rise and in by the tunnel, not 12 yd straight down)


def test_off_undercitys_lifts_the_walk_leaves_by_the_landings_arch(game):
    """Kooki3z 2026-11-22, off the east lift at the bottom: "Slight left now" and the route through the landing
    corridor's wall. Each of the three lifts has its way off over the mesh to the grid (`exits`), and a walk from a lift's
    end goes by it: its first stretch is that way, not a straight line to the nearest floor."""
    lua, ns = game
    CG = ns.CityGrid
    c = CG.City("Undercity")
    lifts = [t for t in ns.Transports.values() if t[1] == 10001 and t[8] == "lift"]
    assert len(lifts) == 3
    rogue = (10001, 1430.0, 75.0, -62.0)  # (toward the Rogues' Quarter)
    for t in lifts:
        e = CG.LiftExit(c, t[2], t[3])
        assert e is not None, (t[2], t[3])
        r = _route(lua, ns, (10001, t[2], t[3], t.z1), rogue)
        assert r.cityGrid == "Undercity"
        pts = _list(r.pts)
        ex = [e[k] for k in range(1, len(e) + 1)]
        # (its first points follow the way off: the route reaches the way's end before it goes anywhere else)
        assert min(math.dist((pts[2 * i], pts[2 * i + 1]), (ex[-1][1], ex[-1][2])) for i in range(min(len(pts) // 2, len(ex) + 1))) < 1.0


# --- the player's own walks: the grid follows them ------------------------------------------------------------------

def test_the_city_grid_follows_the_players_recorded_walk(game):
    """Kooki3z 2026-11-22, Ironforge: "use my fixed routing ... on city grid routing"; recorded walks (ns.db.tracks, not yet
    in the data) are links along their whole length, cheaper than the grid's ground: a route between two spots on a
    walk the player recorded the long way round (by the bank) keeps to it, not the grid's own shortest. As an Alliance
    character, as he walked it: the harness's Horde one passed only by Ironforge's guards' costs, hiding the search's
    streets heuristic cutting across past the walk's corner (a quarter of the route off it) until their circles moved."""
    lua, ns = game
    cdb = ns.CharDB()
    fac = cdb.faction
    cdb.faction = "Alliance"
    ns.Router.HostileChanged()
    ns.CityGrid.routes, ns.CityGrid.order = lua.table(), lua.table()
    spots = C.npc_spots({"Innkeeper Firebrew", "Barnum Stonemantle", "Gryth Thurden"})
    a, via, b = spots["Innkeeper Firebrew"], spots["Barnum Stonemantle"], spots["Gryth Thurden"]
    own = _route(lua, ns, a, b)
    assert own.cityGrid == "Ironforge"
    pts0 = _list(own.pts)
    assert min(math.dist((pts0[2 * i], pts0[2 * i + 1]), via[1:3]) for i in range(len(pts0) // 2)) > 15
    leg1, leg2 = _route(lua, ns, a, via), _route(lua, ns, via, b)
    walk, zs = [], []
    for r in (leg1, leg2):
        p, h = _list(r.pts), _list(r.fz)
        for i in range(len(p) // 2):
            if walk and math.dist(walk[-2:], p[2 * i:2 * i + 2]) < 0.1:
                continue
            walk += p[2 * i:2 * i + 2]
            zs.append(h[i] if h[i] is not False else zs[-1])
    track = lua.table(op="road", recorded=True, continent=0, time=1763800001, pts=lua.table(*walk), zs=lua.table(*zs))
    ns.db.tracks = lua.table(track)
    ns.CityGrid.routes, ns.CityGrid.order = lua.table(), lua.table()
    try:
        r = _route(lua, ns, a, b)
        pts = _list(r.pts)
        assert r.cityGrid == "Ironforge"

        def near_walk(x, y):
            best = math.inf
            for i in range(0, len(walk) - 2, 2):
                ax, ay, bx, by = walk[i:i + 4]
                vx, vy = bx - ax, by - ay
                L2 = vx * vx + vy * vy
                t = 0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
                best = min(best, math.hypot(ax + vx * t - x, ay + vy * t - y))
            return best
        on = total = 0.0
        for i in range(len(pts) // 2 - 1):
            (ax, ay), (bx, by) = pts[2 * i:2 * i + 2], pts[2 * i + 2:2 * i + 4]
            L = math.dist((ax, ay), (bx, by))
            for k in range(max(1, int(L))):
                u = (k + 0.5) / max(1, int(L))
                total += L / max(1, int(L))
                if near_walk(ax + (bx - ax) * u, ay + (by - ay) * u) <= 4:
                    on += L / max(1, int(L))
        assert on / total > 0.8, on / total  # (along the walk; its spur into the bank and out left aside)
    finally:
        cdb.faction = fac
        ns.Router.HostileChanged()
        ns.db.tracks = lua.table()
        ns.CityGrid.routes, ns.CityGrid.order = lua.table(), lua.table()
        c = ns.CityGrid.City("Ironforge")
        c.trackKey = None


def test_a_stop_far_under_the_halls_is_reached_on_its_own_floor(game):
    """Ironforge's Hall of Thanes portal (z 399, under the halls at 500). The bake's inputs now have a road at z 399 at
    the portal, so the city grid has its floor and walks down to it: the route ends at the portal on that floor, and
    never under it (the coordinator, 2026-11-23: the premise "no floor of the grid near it" no longer holds)."""
    lua, ns = game
    portal = (0, -4822.3, -932.4, 399.0)
    spots = C.npc_spots({"Innkeeper Firebrew"})
    r = _route(lua, ns, spots["Innkeeper Firebrew"], portal)
    assert r.cityGrid == "Ironforge"
    pts, zs = _list(r.pts), _list(r.zs) or _list(r.fz)
    assert math.dist(pts[-2:], portal[1:3]) < 3 and abs(zs[-1] - portal[3]) <= 3, (pts[-2:], zs[-1])
    assert min(z for z in zs if z) >= portal[3] - 3, min(zs)  # (never under the portal's floor)


def test_off_undercitys_lifts_the_way_to_the_ring_crosses_no_wall(game):
    """Kooki3z 2026-11-22: "its really just the path from the lift to the top floor circle path, once at the rim of the top
    floor routing is correct". From each lift's end the route runs its way off over the mesh to the Trade Quarter ring's
    rim, and that stretch crosses no wall at body height. Needs the triangles (dev data) for the walls."""
    tris = F.Tris.load("undercity")
    if tris is None:
        pytest.skip("needs the local WoW install (its collision triangles, data/navmesh: agps navmesh tris)")
    lua, ns = game
    c = ns.CityGrid.City("Undercity")
    garrett = (10001, 1567.1, 266.3, -43.0)  # (on the ring)
    for t in [t for t in ns.Transports.values() if t[1] == 10001 and t[8] == "lift"]:
        e = ns.CityGrid.LiftExit(c, t[2], t[3])
        ex = [e[k] for k in range(1, len(e) + 1)]
        rim = (ex[-1][1], ex[-1][2])
        r = _route(lua, ns, (10001, t[2], t[3], t.z1), garrett)
        pts, zs = _list(r.pts), _list(r.zs)
        route = [(pts[2 * i], pts[2 * i + 1], zs[i]) for i in range(len(zs))]
        k = min(range(len(route)), key=lambda i: math.dist(route[i][:2], rim))
        assert math.dist(route[k][:2], rim) < 1.0, (t[2], t[3])
        assert not F.crosses_wall(tris, route[:k + 1]), (t[2], t[3], route[:k + 1])



def test_off_undercitys_lifts_the_walks_road_links_stay_marked_as_links(game):
    """`agps city-grid --check`'s gates from Undercity's lifts flagged the walk 12 yd off the mesh by the Magic Quarter:
    an old road's link over a gap the mesh lacks, judged as the grid's own walk because the lift's way off spliced in
    front of the walk dropped its links' marks (onLink) and shifted its bends. Spliced, they're the walk's own still."""
    lua, ns = game
    t = next(t for t in ns.Transports.values() if t[1] == 10001 and t[8] == "lift")
    stop = (10001, 1707.1, 115.1, -64.0)  # (past the old road's link, toward Kaal Soulreaper)
    ns.settings.gps.cityGrid = True
    try:
        c = ns.CityGrid.City("Undercity")
        e = ns.CityGrid.LiftExit(c, t[2], t[3])
        assert e is not None
        spliced = ns.CityGrid.Walk(c, t[2], t[3], t.z1, stop[1], stop[2], stop[3])
        rim = e[len(e)]
        ns.CityGrid.routes, ns.CityGrid.order = lua.table(), lua.table()  # (searched afresh, not reused)
        own = ns.CityGrid.Walk(c, rim[1], rim[2], rim[3], stop[1], stop[2], stop[3])
    finally:
        ns.settings.gps.cityGrid = False
    assert spliced and own and spliced.onLink is not None
    assert any(own.onLink[k] for k in range(1, len(_list(own.kinds)) + 1))  # (the case: a link on the way)
    shift = len(_list(spliced.pts)) // 2 - len(_list(own.pts)) // 2
    assert shift >= 1
    n = len(_list(own.kinds))
    assert [bool(own.onLink[k]) for k in range(1, n + 1)] == [bool(spliced.onLink[k + shift]) for k in range(1, n + 1)]
    ob = own.bends or {}
    assert [k + shift for k in range(1, n + 2) if ob[k]] == [k for k in range(1, n + 2 + shift) if spliced.bends[k]]

# --- Thunder Bluff's tents at its rope bridges' ends --------------------------------------------------------------

TB_CENTRAL = (1, -1180.0, 100.0, 135.5)  # (the central mesa, by the inn)
TB_SPIRIT_SIDE = (1, -1030.0, 195.0, 139.0)  # (past the rope bridge to the Spirit Rise)


def test_thunder_bluffs_spirit_rise_bridge_is_reached_by_the_tents_doorway_not_through_its_wall(game):
    """Kooki3z 2026-11-22: every rope bridge's end on the central mesa is inside a tent, and the routes went through the
    tents' walls ("should be colliding with the building's wall for routing"). Neither the old roads' links nor the
    grid's own (joined by the doorway's polys beside the wall) go through a wall now: no level stretch of the route
    from the central mesa over the Spirit Rise's bridge crosses one at body height. Needs the triangles (dev data)."""
    tris = F.Tris.load("thunder_bluff")
    if tris is None:
        pytest.skip("needs the local WoW install (its collision triangles, data/navmesh: agps navmesh tris)")
    lua, ns = game
    r = _route(lua, ns, TB_CENTRAL, TB_SPIRIT_SIDE)
    assert r.cityGrid == "Thunder Bluff"
    pts, hs = _list(r.pts), _list(r.fz)
    route = [(pts[2 * i], pts[2 * i + 1], hs[i]) for i in range(len(hs))]
    level = [(a, b) for a, b in zip(route, route[1:]) if abs(b[2] - a[2]) < F.WALL_LEVEL_DZ]
    assert not [ab for ab in level if F.crosses_wall(tris, list(ab))], level
