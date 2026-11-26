"""Orgrimmar's Wind Rider tower (Doras, the Wind Rider Master, up top in the Valley of Strength): its spiral ramp walked
up and down with city routing on (item 110, Kooki3z 2026-11-26: "the arrow is chaotic and yd up doesn't change", where
the other spirals worked).

The cause: the city's stairs road up the ramp was the old roads' (capitals.py's walk net, from before the city grid), a
tight coil round the tower's core with its heights straight from foot to top over four turns, where the ramp has three
(about 9.5 yd a turn) and runs up to 8 yd out from the core. The city grid can't tell the floor on the ramp by itself (its
turns stack, and a floor at -3 runs under the whole tower), so the floor followed is the roads' (Nav.TrackCityZ): a yard
or two off that coil, or a turn round, the coil's height there was another turn's, and the floor followed was let go
(unknown: no "yd up", the route and arrow from any turn) or kept a turn low on the way down. The coil is erased now and
the ramp shipped as a stairs road drawn up its middle at the navigation mesh's heights (overrides/roads_1.geojson,
ns.FloorTracks[1]: RAMP_TIME, a half turn a part).

Walked a yard inside, on and outside the ramp's middle: the floor followed is the ramp's all the way (never unknown,
never a turn off), the height readout counts down, and the arrow never points back the way the player came.
(Hugging the ramp's outer wall, where the grid's 3 yd cells miss a turn, the grid's own tracking can still drop to the
floor under the tower: item 106's, floor candidates kept until there's evidence.)"""

import math
import re

import pytest

pytest.importorskip("lupa.lua51")

RAMP_TIME = 1795651210  # (the ramp's stairs road: its parts, ns.FloorTracks[1])
ERASED = (1795651200, 1795651201, 1795651202, 1795651203, 1795651204)  # (the old coil's erasures)
CORE = (1673.44, -4334.12)  # (the ramp's turns' middle, from the mesh)
DORAS = (1676.2, -4313.4, 61.7)  # (Wind Rider Master, his shipped spawn: Data/Npcs.lua)
FOOT = (1647.2, -4357.3, 24.0)  # (the street by the tower's foot, where its way up starts: a stop there)
STREET = [(1640.0, -4380.0), (1645.7, -4363.3), (1647.2, -4361.1), (1647.2, -4357.3), (1650.2, -4354.3)]  # (to its foot)
TOP = [(1676.2, -4313.4), (1672.7, -4321.3), (1668.6, -4325.8), (1669.7, -4333.3), (1673.0, -4341.0)]  # (Doras to it)
STEP_YD, LOOK_S = 1.75, 0.26  # (at a run, a look every TRACK_EVERY or so)
OFFSETS = (-1.0, 0.0, 1.0)  # (yards out from the ramp's middle: inside, on it, outside)
HINT = re.compile(r"(Above|Below) you, (\d+) yd (up|down)")


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.settings.gps.cityGrid = True
    ns.CharDB().faction = "Horde"
    lua.execute("""
      C_Map.GetBestMapForUnit = function() return 1454 end -- (Orgrimmar)
      IsIndoors = function() return false end
      AGPS_T = (AGPS_T or 0) + 5000
    """)
    return lua, ns


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []


def _ramp(ns):
    """The shipped ramp's points (x, y, z) from the street to the top, its parts in order, and the part each starts."""
    parts = sorted((t for t in _list(ns.FloorTracks[1]) if t.time == RAMP_TIME), key=lambda t: t.part)
    pts, first = [], []
    for t in parts:
        p, z = _list(t.pts), _list(t.zs)
        q = [(p[2 * i], p[2 * i + 1], z[i]) for i in range(len(z))]
        if pts and math.dist(pts[-1][:2], q[0][:2]) < 0.05:
            q = q[1:]
        first.append(len(pts))
        pts += q
    return pts, first


def _dense(pts, step):
    """The points every `step` yards or so along the line (each with its height between)."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, round(math.dist(a[:2], b[:2]) / step))
        out += [tuple(a[k] + (b[k] - a[k]) * j / n for k in range(len(a))) for j in range(1, n + 1)]
    return out


def _out(p, off):
    """(x, y, z) moved `off` yards out from the tower's core."""
    dx, dy = p[0] - CORE[0], p[1] - CORE[1]
    r = math.hypot(dx, dy) or 1
    return (p[0] + dx / r * off, p[1] + dy / r * off, p[2])


def _walk(lua, ns, to, start, way, name):
    """The route to `to` from `start`, then the player along `way` [(x, y, z or None)]: each look's floor followed,
    height readout and arrow (its turn from the way walked, degrees), the height there."""
    N, T = ns.Nav, ns.Turns
    N.ResetCityTrack()
    ns.CityGrid.track = None
    lua.execute(f"AGPS_T = AGPS_T + 30 AGPS_POS = {{ {start[0]}, {start[1]}, 1 }}")
    N.SetStops(lua.eval("{}"), False, True)
    N.AddStop(lua.table(x=to[0], y=to[1], cont=1, name=name, z=to[2]), False, True)
    for _ in range(20):
        if N.Route(start[0], start[1], 1):
            break
        lua.execute("AGPS_T = AGPS_T + 0.3")
    rows, prev = [], None
    for x, y, z in way:
        lua.execute(f"AGPS_POS = {{ {x}, {y}, 1 }} AGPS_T = AGPS_T + {LOOK_S}")
        N.Status(x, y, 1)
        r = N.Route(x, y, 1)
        fz, hint = N.FollowedZ(1), N.HeightText(x, y, 1)
        m = HINT.search(str(hint or ""))
        turn = None
        tgt = r and T.Target(T.Path(r), x, y)
        if tgt and prev and math.dist(prev, (x, y)) > 0.3:
            walked = math.atan2(y - prev[1], x - prev[0])
            aim = math.atan2(tgt[1] - y, tgt[0] - x)
            turn = math.degrees((aim - walked + math.pi) % (2 * math.pi) - math.pi)
        prev = (x, y)
        rows.append(dict(x=x, y=y, z=z, fz=fz, yd=m and int(m.group(2)), way=m and m.group(3), turn=turn))
    N.SetStops(lua.eval("{}"), False, True)
    N.ResetCityTrack()
    return rows


def test_the_old_coil_is_erased_and_the_ramp_climbs_from_the_street_to_the_top(game):
    lua, ns = game
    R = ns.Router
    pts, first = _ramp(ns)
    times = {t.time for t in _list(ns.FloorTracks[1])}
    assert set(ERASED) <= times and len(first) >= 6, (sorted(times)[-8:], len(first))
    assert math.dist(pts[0][:2], (1653.0, -4351.0)) < 1 and abs(pts[0][2] - 27) < 1  # (the street's road, at its foot)
    assert math.dist(pts[-1][:2], (1673.0, -4341.0)) < 1 and abs(pts[-1][2] - 60) < 1  # (the top, by the walkway)
    assert all(b[2] >= a[2] - 0.2 for a, b in zip(pts, pts[1:]))  # (up all the way)
    # three turns round the core, not four
    ang = [math.atan2(p[1] - CORE[1], p[0] - CORE[0]) for p in pts[first[1]:]]
    turned = sum((b - a + math.pi) % (2 * math.pi) - math.pi for a, b in zip(ang, ang[1:]))
    assert 2.6 < abs(turned) / (2 * math.pi) < 3.0, turned
    # every stairs road round the core is the ramp's, at its height there (the old coil's ran up to a turn off it)
    R.Route(1, STREET[0][0], STREET[0][1], DORAS[0], DORAS[1], lua.table(tz=DORAS[2]))
    for p in _dense(pts[first[1]:], 1.0):
        for h in _list(R.HeightsNear(1, p[0], p[1], 1.5)):
            if h.stair:
                near = [q[2] for q in pts if math.dist(q[:2], (p[0], p[1])) < 4]
                assert min(abs(h.z - z) for z in near) < 2.5, (p, h.z)


def test_the_ramp_is_at_the_meshs_height():
    """The ramp's points on the city's navigation mesh at their heights (dev data: not on CI)."""
    from azerothgps import citygrid as C
    from azerothgps import navmesh as NM
    from azerothgps import recastmesh as RM
    from azerothgps.paths import RESOURCES
    import json
    p = RM.mesh_path("orgrimmar")
    if not p.exists():
        pytest.skip("needs the local WoW install (its navmesh, data/navmesh: agps navmesh build)")
    mesh = C.Mesh(RM.load(p), 1)
    near = [i for i, vs in enumerate(mesh.vs) if math.dist(vs[0][:2], CORE) < 30]
    doc = json.loads((RESOURCES / "overrides" / "roads_1.geojson").read_text(encoding="utf-8"))
    for f in doc["features"]:
        if f["properties"].get("time") != RAMP_TIME:
            continue
        for (x, y), z in zip(f["geometry"]["coordinates"], f["properties"]["zs"]):
            hs = [NM._height_on(mesh.vs[i], x, y) for i in near if NM._in_poly(mesh.vs[i], x, y)]
            assert hs and min(abs(h - z) for h in hs) < 1.0, (x, y, z, hs)


@pytest.mark.parametrize("off", OFFSETS)
def test_up_the_ramp_to_doras_the_floor_is_followed_and_the_yards_up_count_down(game, off):
    lua, ns = game
    pts, first = _ramp(ns)
    way = [(x, y, None) for x, y, _ in _dense([(x, y, 0) for x, y in STREET], STEP_YD)]
    way += _dense(pts[:first[1] + 1], STEP_YD)  # (up from the street onto the tower's platform)
    on = len(way)
    way += [_out(p, off) for p in _dense(pts[first[1]:], STEP_YD)][1:]
    rows = _walk(lua, ns, DORAS, STREET[0], way, "Orgrimmar Wind Rider Master")
    ramp = rows[on:]
    lost = [(round(r["x"], 1), round(r["y"], 1), r["z"], r["fz"]) for r in ramp
            if r["fz"] is None or abs(r["fz"] - r["z"]) > 4]
    assert not lost, lost  # (was: unknown up most of it, or a turn off)
    yds = [r["yd"] for r in ramp if r["way"] == "up"]
    assert len(yds) >= len(ramp) // 2 and yds[0] >= 20 and yds[-1] <= 10, yds
    assert all(b <= a + 1 for a, b in zip(yds, yds[1:])), yds  # (counts down as you climb)
    turns = [r["turn"] for r in ramp if r["turn"] is not None]
    assert turns and max(abs(t) for t in turns) < 150, turns  # (never back down the ramp)
    swings = sum(1 for a, b in zip(turns, turns[1:]) if abs((b - a + 180) % 360 - 180) > 120)
    assert swings <= 4, turns  # (at most about one a turn round the core)


@pytest.mark.parametrize("off", OFFSETS)
def test_down_the_ramp_from_doras_the_floor_is_followed_and_the_yards_down_count_down(game, off):
    lua, ns = game
    pts, first = _ramp(ns)
    way = [(x, y, None) for x, y, _ in _dense([(x, y, 0) for x, y in TOP], STEP_YD)]
    on = len(way)
    way += [_out(p, off) for p in _dense(pts[first[1]:], STEP_YD)[::-1]][1:]
    rows = _walk(lua, ns, FOOT, DORAS, way, "the tower's foot")
    ramp = rows[on:]
    lost = [(round(r["x"], 1), round(r["y"], 1), r["z"], r["fz"]) for r in ramp
            if r["fz"] is None or abs(r["fz"] - r["z"]) > 4]
    assert not lost, lost  # (was: a turn low from the top, "Below you, 27 yd down" up there)
    yds = [r["yd"] for r in ramp if r["way"] == "down"]
    assert len(yds) >= len(ramp) // 2 and yds[0] >= 30 and yds[-1] <= 12, yds
    assert all(b <= a + 1 for a, b in zip(yds, yds[1:])), yds
    turns = [r["turn"] for r in ramp if r["turn"] is not None]
    assert turns and max(abs(t) for t in turns) < 150, turns
