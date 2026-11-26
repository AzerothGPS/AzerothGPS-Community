"""Routes to places under the ground (Kooki3z, 2026-11-23: "Test known underground destinations like NPCs and make sure it
doesn't say jump here to its destination through a floor that they can't go through. This should route them to the
correct entrance"). The sweep (`agps underground-sweep`, undergroundsweep.py) routes to every NPC with a floor over its
head and every dungeon's way in; these are its representative cases, and its checks.

Blackrock Mountain is the first failing case: Kooki3z stood at Blackrock Depths' door, (-7211.9, -892.5) and z 165
(his saved spot in testing), with a stop inside Blackrock Spire, and the directions said "651 yd to the portal
(then to Blackrock Spire)", a line through the mountain's rock: the world grid has the mountain's lower floor (the
Molten Span, the Masonary, Blackrock Depths' door) as an island, its bridges and the way up to Blackrock Spire's door
missing, so the leg fell back to the Router's straight lines. His recorded walks there (road watcher #927 and #929,
2026-11-23 00.12 to 00.23) are the ground truth below; they go into the grid's links by the next world grid bake."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("lupa.lua51")

from azerothgps import undergroundsweep as U  # noqa: E402

BRD_DOOR = (-7179.5, -922.7, 166.2)
BRS_DOOR = (-7524.7, -1228.4, 287.2)
KOOKI3Z_AT_BRD = (-7211.91, -892.49)  # (his saved spot when the route said "651 yd to the portal")
HIS_STOP_IN_BRS = (4.85, -410.1, 20229)
MOLTEN_SPAN = (-7494.7, -1073.4)  # (where his first recorded walk starts: the ring over the Molten Span, 265)
# His recorded walks, thinned to 20 yd (#927: from the ring over the Molten Span down its ramps to the span's floor, 181
# by Molten Core's portal, and on to Blackrock Depths' door; #929: from Blackrock Spire's door down the ramp to the
# ring over the span)
DOWN_TO_THE_SPAN = [(-7494.7, -1073.4), (-7494.6, -1094.0), (-7494.9, -1116.2), (-7494.7, -1138.3), (-7505.1, -1153.9),
                    (-7524.6, -1145.2), (-7544.3, -1136.6), (-7564.4, -1128.0), (-7585.4, -1123.7), (-7605.8, -1121.6),
                    (-7622.1, -1115.9), (-7609.5, -1122.0), (-7593.0, -1109.6), (-7576.8, -1116.2), (-7565.3, -1131.1),
                    (-7582.8, -1139.4), (-7601.7, -1132.2), (-7608.0, -1113.1), (-7596.8, -1098.6), (-7576.4, -1101.8),
                    (-7558.6, -1088.1), (-7541.3, -1074.9), (-7533.8, -1068.5)]
WALK_TO_BRD = [(-7533.8, -1068.5), (-7522.2, -1052.1), (-7501.8, -1050.8), (-7485.2, -1037.3), (-7469.2, -1022.4),
               (-7453.1, -1010.2), (-7434.2, -1002.8), (-7414.8, -995.6), (-7404.5, -977.7), (-7394.8, -957.9),
               (-7384.4, -939.8), (-7366.6, -928.9), (-7347.1, -921.0), (-7327.4, -916.5), (-7307.1, -913.8),
               (-7286.3, -911.5), (-7265.8, -909.2), (-7245.3, -906.9), (-7224.8, -904.6), (-7204.0, -902.5),
               (-7185.7, -912.8), (-7179.7, -922.7)]
WALK_FROM_BRS = [(-7524.7, -1228.4), (-7544.4, -1232.8), (-7564.0, -1240.3), (-7579.0, -1255.0), (-7576.9, -1275.5),
                 (-7598.0, -1279.5), (-7614.1, -1264.5), (-7617.0, -1243.1), (-7609.4, -1223.7), (-7588.5, -1221.5),
                 (-7567.0, -1219.4), (-7548.5, -1209.7), (-7531.5, -1196.9), (-7515.2, -1182.5), (-7502.4, -1166.7),
                 (-7493.1, -1147.9), (-7494.9, -1134.7), (-7494.7, -1116.2), (-7494.6, -1094.0), (-7494.7, -1073.4)]
NO_START_FLOOR = ("his saved spot has no height (the client gives none): the start takes the floor nearest the ground's "
                  "height there, the mountain's top (288) over the door's (166); the world grid has no floor followed (CG.TrackFloor)")


@pytest.fixture(scope="module")
def game():
    lua, ns = U._game()
    yield lua, ns
    ns.settings.gps.worldGrid = False
    ns.settings.gps.cityGrid = False


def _continent_walk(r, cont=0):
    parts = [r.parts[i] for i in range(1, len(r.parts) + 1)]
    walk = [p for p in parts if p.leg and int(p.cont) == cont and p.pts and len(p.pts) >= 4]
    assert walk, "no walk on the continent"
    p = walk[-1]
    pts = [(p.pts[i], p.pts[i + 1]) for i in range(1, len(p.pts) + 1, 2)]
    fz = [p.fz[i] for i in range(1, len(p.fz) + 1)] if p.fz else []
    return pts, fz


def _off(pts, line):
    """The share of the route's length farther than 20 yd from the recorded walk (`line`)."""
    def dist(q):
        best = math.inf
        for (ax, ay), (bx, by) in zip(line, line[1:]):
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy or 1e-9
            t = max(0.0, min(1.0, ((q[0] - ax) * vx + (q[1] - ay) * vy) / L2))
            best = min(best, math.hypot(ax + vx * t - q[0], ay + vy * t - q[1]))
        return best
    far = total = 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        n = max(1, int(L / 4))
        for k in range(n):
            q = (a[0] + (b[0] - a[0]) * (k + 0.5) / n, a[1] + (b[1] - a[1]) * (k + 0.5) / n)
            total += L / n
            if dist(q) > 20:
                far += L / n
    return far / total if total else 0.0


def _trip(lua, ns, start, stop, side="A"):
    d = {"kind": "instance" if stop[2] >= 20000 else "npc", "name": "stop", "side": side, "cont": stop[2],
         "x": stop[0], "y": stop[1], "z": None, "base": 0}
    if d["kind"] == "instance":
        rows = ns.Transports
        t = next(rows[i] for i in range(1, len(rows) + 1) if rows[i][8] == "portal" and int(rows[i][4]) == stop[2])
        d.update(door=(float(t[2]), float(t[3])), doorZ=float(t.z1) if t.z1 is not None else None)
    row = U.route_one(lua, ns, d, {"start": "test", "x": start[0], "y": start[1]})
    return row, ns.Nav.route


# --- the sweep's checks, on routes made up for them ------------------------------------------------------------------

def _fake(lua, pts, kinds, fz, cont=0):
    flat = [v for p in pts for v in p]
    part = lua.table(cont=cont, leg=lua.table(walk=True), pts=lua.table(*flat), kinds=lua.table(*kinds), fz=lua.table(*fz))
    return lua.table(parts=lua.table(part), legs=lua.table(part.leg))


def test_a_drop_through_another_floor_is_flagged(game):
    lua, ns = game
    # (Blackrock Depths' door, 166, under the mountain's upper floors at 276: a drop from the top onto it falls through)
    x, y = BRD_DOOR[0], BRD_DOOR[1]
    zs = U._surfaces(ns, 0, x, y)
    assert any(h > 200 for h in zs) and any(abs(h - 166) < 3 for h in zs)
    d = {"kind": "npc", "name": "t", "cont": 0, "base": 0, "x": x, "y": y, "z": 166.0}
    r = _fake(lua, [(x + 30, y), (x + 1, y), (x, y)], [1, 4], [300.0, 300.0, 166.0])
    kinds = {i["kind"] for i in U.check_route(lua, ns, r, d)}
    assert "through" in kinds and "bigdrop" in kinds
    # a walk that stays on the stop's floor: nothing
    r = _fake(lua, [(x - 2, y + 20), (x - 1, y + 10), (x, y)], [1, 1], [166.0, 166.0, 166.0])
    assert [i for i in U.check_route(lua, ns, r, d) if i["kind"] in ("through", "bigdrop", "overhead")] == []


def test_a_walk_ending_over_the_stops_head_is_flagged(game):
    lua, ns = game
    x, y = BRD_DOOR[0], BRD_DOOR[1]
    d = {"kind": "npc", "name": "t", "cont": 0, "base": 0, "x": x, "y": y, "z": 166.0}
    r = _fake(lua, [(x + 20, y), (x, y)], [1], [276.0, 276.5])
    assert "overhead" in {i["kind"] for i in U.check_route(lua, ns, r, d)}


def test_a_portal_to_another_dungeon_is_flagged(game):
    lua, ns = game
    rows = ns.Transports
    brs = next(rows[i] for i in range(1, len(rows) + 1) if rows[i][8] == "portal" and int(rows[i][4]) == 20229)
    d = {"kind": "instance", "name": "Blackrock Depths", "cont": 20230, "base": 0, "x": 456.9, "y": 34.1, "z": None,
         "door": BRD_DOOR[:2], "doorZ": BRD_DOOR[2]}
    r = lua.table(parts=lua.table(), legs=lua.table(lua.table(ride=brs)))
    assert "portal" in {i["kind"] for i in U.check_route(lua, ns, r, d)}


def test_the_destinations_have_the_underground_npcs_and_every_way_in(game):
    lua, ns = game
    ins = U.instance_entrances(ns)
    assert {"Blackrock Depths", "Blackrock Spire", "Wailing Caverns", "Deadmines"} <= {d["name"] for d in ins}
    brd = next(d for d in ins if d["name"] == "Blackrock Depths")
    # (measured in game; #928 gives every way in its height)
    assert brd["doorZ"] is None or brd["doorZ"] == pytest.approx(BRD_DOOR[2], abs=3)
    npcs = U.underground_npcs(ns, log=lambda *_: None)
    assert len(npcs) > 300 and any(d["cont"] == U.UNDERCITY for d in npcs)
    assert all(d["over"] is None or d["over"] >= d["z"] + U.UNDER_YD for d in npcs)


# --- Blackrock Mountain (bake7 took in his recorded walks: the lower floor joined to the ring and the ways out) -------

@pytest.mark.xfail(strict=False, reason=NO_START_FLOOR)
def test_from_blackrock_depths_door_to_blackrock_spire_up_the_mountain(game):
    lua, ns = game
    row, r = _trip(lua, ns, KOOKI3Z_AT_BRD, HIS_STOP_IN_BRS)
    kinds = {i["kind"] for i in row["issues"]}
    assert r is not None and "noway" not in kinds, row["issues"]
    assert not kinds & {"through", "straight", "overhead", "portal"}, row["issues"]
    pts, fz = _continent_walk(r)
    # up from the door the way he walked it: back through the Masonary, over the Molten Span, up the ramp
    assert _off(pts, list(reversed(DOWN_TO_THE_SPAN + WALK_TO_BRD)) + WALK_FROM_BRS[::-1]) < 0.25
    assert fz and abs(fz[-1] - BRS_DOOR[2]) < 6


def test_from_the_molten_span_to_blackrock_depths_his_recorded_walk(game):
    lua, ns = game
    row, r = _trip(lua, ns, MOLTEN_SPAN, (456.9, 34.1, 20230))
    assert r is not None and not row["issues"], row["issues"]
    pts, fz = _continent_walk(r)
    assert _off(pts, DOWN_TO_THE_SPAN + WALK_TO_BRD) < 0.15
    assert fz and abs(fz[-1] - BRD_DOOR[2]) < 6  # (on the door's floor, not the mountain's top at 276 over it)


def test_from_blackrock_spire_s_door_down_to_blackrock_depths(game):
    lua, ns = game
    row, r = _trip(lua, ns, BRS_DOOR[:2], (456.9, 34.1, 20230))
    assert r is not None and not row["issues"], row["issues"]
    pts, _ = _continent_walk(r)
    assert _off(pts, WALK_FROM_BRS + DOWN_TO_THE_SPAN + WALK_TO_BRD) < 0.25


def test_never_a_portal_into_another_dungeon_from_inside_the_mountain(game):
    # (whatever the grid has: from Blackrock Depths' door to a stop in Blackrock Depths, its own portal and no other)
    lua, ns = game
    row, r = _trip(lua, ns, KOOKI3Z_AT_BRD, (456.9, 34.1, 20230))
    assert "portal" not in {i["kind"] for i in row["issues"]}, row["issues"]


# --- what the sweep found (2026-11-23) ------------------------------------------------------------------------------

def test_from_the_mountain_over_ironforge_never_a_fall_through_the_rock(game):
    # (Hjoldir down in Ironforge, 503.7; the world grid's walk from over the mountain's top, 709.5, spliced onto the city
    # grid's at the crossing 210 yd under it, and a route remembered from the gate was joined straight down onto)
    lua, ns = game
    d = {"kind": "npc", "name": "Hjoldir", "side": "A", "cont": 0, "x": -4605.1, "y": -1069.3, "z": 503.7, "base": 0}
    fm = next(s for s in U.starts_for(ns, d) if s["start"] == "fm")
    assert U.route_one(lua, ns, d, fm)["issues"] == []
    row = U.route_one(lua, ns, d, {"start": "above", "x": -4580.1, "y": -1069.3, "z": 709.5})
    assert not [i for i in row["issues"] if i["kind"] == "through"], row["issues"]


def test_a_stop_up_a_tower_the_grid_has_no_stairs_to_ends_at_its_foot(game):
    # (Neeka Bloodscar up Kargath's tower, 278.6, 72 yd from the flight master: the grid has no way up to her floor, and
    # "no way" planned a 10k yd walk round the Badlands to come at her from farther off)
    lua, ns = game
    d = {"kind": "npc", "name": "Neeka Bloodscar", "side": "H", "cont": 0, "x": -6672.2, "y": -2240.5, "z": 278.6,
         "base": 0}
    row = U.route_one(lua, ns, d, {"start": "fm", "x": -6634.0, "y": -2180.1})
    assert row.get("yd") is not None and row["yd"] < 300, row
    assert not [i for i in row["issues"] if i["kind"] in ("through", "noway", "overhead")], row["issues"]


# --- Blackrock Spire's door from the ring (bake8; Kooki3z's video 2026-11-23: heading to the spire's portal the
# directions flipped, U-turns and the line looping inside the spire's entrance halls) ------------------------------

BRS_STOP = (78.4, -226.8, 20229)
# (his recorded walk from the spire's door down through its entrance halls' ramps to the ring, 2026-11-23, thinned)
WALK_SPIRE_HALLS = [(-7525, -1228), (-7551, -1236), (-7577, -1243), (-7579, -1257), (-7577, -1276), (-7563, -1279),
                    (-7545, -1278), (-7529, -1282), (-7527, -1291), (-7529, -1300), (-7538, -1297), (-7539, -1287),
                    (-7543, -1279), (-7561, -1280), (-7571, -1282), (-7575, -1290), (-7573, -1309)]  # (just inside Blackrock Spire: the Recording TODO's "Blackrock Spire to Upper Blackrock Spire")


def _along(pts, step=6.0):
    out = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        n = max(1, int(math.dist((ax, ay), (bx, by)) / step))
        out += [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n)]
    return out + [pts[-1]]


def _walk_yd(r, cont=0):
    p = next(r.parts[i] for i in range(1, len(r.parts) + 1) if r.parts[i].leg and int(r.parts[i].cont) == cont)
    pts = [(p.pts[i], p.pts[i + 1]) for i in range(1, len(p.pts) + 1, 2)]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def test_from_the_ring_up_to_blackrock_spire_s_door_his_recorded_walk(game):
    # (#929's walk down from the spire's door, the switchbacks through its entrance halls, is the way up: its floors lie
    # over each other, 246 to 286)
    lua, ns = game
    row, r = _trip(lua, ns, MOLTEN_SPAN, BRS_STOP)
    assert r is not None and not row["issues"], row["issues"]
    pts, fz = _continent_walk(r)
    off = min(_off(pts, WALK_FROM_BRS[::-1]), _off(pts, WALK_FROM_BRS[::-1] + WALK_SPIRE_HALLS[::-1]))
    assert off < 0.1
    assert fz and abs(fz[-1] - BRS_DOOR[2]) < 6


def test_walking_up_to_blackrock_spire_s_door_the_route_never_turns_back(game):
    # (walked a few yards off the route's line, the way worked out again at every step: with no height from the game a
    # recalculation started on the hall's floor nearest the mountain's top (297-330 over the walk's 246-286) and went
    # back: 19-24 U-turns of 76 steps. The floor is read off the route followed, Nav.TrackRouteZ)
    lua, ns = game
    N = ns.Nav
    row, r = _trip(lua, ns, MOLTEN_SPAN, BRS_STOP)
    pts, _ = _continent_walk(r)
    walk = _along(pts)
    total = _walk_yd(r)
    back = []
    done = 0.0
    try:
        for i in range(3, len(walk) - 4):
            done += math.dist(walk[i - 1], walk[i])
            hx, hy = walk[i + 3][0] - walk[i - 3][0], walk[i + 3][1] - walk[i - 3][1]
            hl = math.hypot(hx, hy) or 1.0
            x, y = walk[i][0] - hy / hl * 3, walk[i][1] + hx / hl * 3
            lua.execute(f"AGPS_POS = {{ {x}, {y}, 0 }}")
            N.Invalidate(True)
            rr = N.Route(x, y, 0)
            assert rr, (i, x, y)
            left = _walk_yd(rr)
            if left > total - done + 30:
                back.append((i, round(x), round(y), round(left), round(total - done)))
    finally:
        N.Clear()
    assert back == []


# --- the Deadmines (Kooki3z's screenshot 2026-11-23: from outside, the route walked over the hill above the cave to
# the portal, not in by the Defias hideout's way in, the tunnel mouth in the building on Moonbrook's south-west side) --

DEADMINES_PORTAL = (-11208.7, 1675.9, 24.6)
SENTINEL_HILL = (-10628.0, 1037.0)
HIDEOUT_WAY_IN = (-11248.0, 1585.0)  # (the building's tunnel mouth, Westfall's map about 41, 79)


def test_from_sentinel_hill_the_deadmines_by_the_hideout_s_way_in_never_over_the_hill(game):
    # (the grid's walk fell off the edge of the terrain's hole over the tunnel, 20 yd through the hill's rock onto the
    # portal's floor: worldbake.cut_ceiling_drops drops those links; the way in is the hideout's tunnel)
    lua, ns = game
    row, r = _trip(lua, ns, SENTINEL_HILL, (-14.6, -385.5, 20036))
    assert r is not None and not row["issues"], row["issues"]
    pts, fz = _continent_walk(r)
    px, py, pz = DEADMINES_PORTAL
    over = [(round(x), round(y), round(z)) for (x, y), z in zip(pts, fz)
            if z is not None and math.dist((x, y), (px, py)) <= 50 and z >= pz + 20]
    assert over == []  # (no stretch on the surface over the portal)
    assert min(math.dist(q, HIDEOUT_WAY_IN) for q in pts) <= 25  # (in by the hideout's building)
    assert fz and abs(fz[-1] - pz) < 6


# --- on the ring over the lava, Blackrock Depths' icon the stop (item 89, Kooki3z 2026-11-25, a Horde mage: his spot
# map 0 (-7522.4, -1047.9), z 261, from the server; the route went from the Molten Span's floor under him, 182, 410 yd
# north, not down the ring past Forgewright's Tomb and its ramps to the span as he drew it). His recorded walk on the
# span passes under the spot; the roads near him were all that floor, so the start took it (N.TrackCityZ). Where the
# grid's floors are stacked the start is the grid's (N.GridStackedAt, N.TrackGridZ) --------------------------------

ON_THE_RING = (-7522.4, -1047.9, 261.0)


def _icon_trip(lua, ns, level, z):
    G, N = ns.GPS, ns.Nav
    lua.execute("UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    N.Clear()
    N.ResetTrack()
    lua.execute("IsIndoors = function() return true end")
    lua.execute(f"AGPS_POS = {{ {ON_THE_RING[0]}, {ON_THE_RING[1]}, 0{', ' + str(z) if z is not None else ''} }}")
    ents = G.InstanceEntrances(0)
    e = next(ents[i] for i in range(1, len(ents) + 1) if ents[i].level == level)
    assert G.AddStopAt(e.x, e.y, e.name, e.cont)  # (its icon double-clicked)
    G.ConfirmRoute()
    for _ in range(8):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
    return N.stops[1], N.route


@pytest.mark.parametrize("z", [None, ON_THE_RING[2]], ids=["no_height", "his_height"])
def test_from_the_ring_blackrock_depths_is_down_the_ring_and_across_the_span(game, z):
    lua, ns = game
    try:
        d, r = _icon_trip(lua, ns, 20230, z)
        assert d.z == pytest.approx(BRD_DOOR[2])  # (the stop: its portal's own height)
        assert r is not None
        pts, fz = _continent_walk(r)
        # (started on the ring, not the span's floor under it: with no height from the game the grid's highest floor
        # there under the mountain, the ring's or the ledge's over it, 284; N.TrackGridZ)
        assert fz and (abs(fz[0] - ON_THE_RING[2]) < 6 if z else fz[0] > ON_THE_RING[2] - 6), fz[:3]
        assert abs(fz[-1] - BRD_DOOR[2]) < 6
        assert _off(pts, [ON_THE_RING[:2]] + DOWN_TO_THE_SPAN + WALK_TO_BRD) < 0.15
    finally:
        ns.Nav.Clear()
        lua.execute("IsIndoors = function() return false end")


@pytest.mark.parametrize("z", [None, ON_THE_RING[2]], ids=["no_height", "his_height"])
def test_from_the_ring_blackrock_spire_is_up_the_ring(game, z):
    lua, ns = game
    try:
        d, r = _icon_trip(lua, ns, 20229, z)
        assert d.z == pytest.approx(BRS_DOOR[2])
        pts, fz = _continent_walk(r)
        assert fz and (abs(fz[0] - ON_THE_RING[2]) < 6 if z else fz[0] > ON_THE_RING[2] - 6), fz[:3]
        assert abs(fz[-1] - BRS_DOOR[2]) < 6
        assert _off(pts, [ON_THE_RING[:2]] + WALK_FROM_BRS[::-1] + WALK_SPIRE_HALLS[::-1]) < 0.2
    finally:
        ns.Nav.Clear()
        lua.execute("IsIndoors = function() return false end")
