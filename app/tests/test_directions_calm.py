"""Calmer directions (1.4.1, Kooki3z: "clean up the message display, seems to change a lot between join road, leave road,
etc"; worker item 101). The arrow window's line, "Continue straight, then <maneuver> in <yd>", changed every few yards:

- the maneuvers were worked out again on what was left of the route at every trim (every couple of yards), so the bends
  near its new start were measured on half a window and a turn came and went, "Turn right" became "Slight right now";
  now they're worked out once on the walk's untrimmed first part (Turns.AheadFull) and only moved along;
- every road joined or left was said, the world grid's walks touching a road for a few yards included; now a short
  touch says nothing, a join or leave near a turn is that turn's ("Turn right onto the road"), and a bare one is said
  only before and after a long stretch (Turns.FoldRoads);
- the route worked out again every few seconds put a new kink first now and then; the one shown stays first while it's
  still ahead (Turns.Steady);
- and Red Cloud Mesa's road down said "Stairs down in 879 yd": an outdoor ramp is never stairs (Turns.GridStairs).

The walks replayed here: the player follows the route shown, a couple of yards to either side of it, at a run's pace,
the route trimmed and worked out again as in game, and every change of the line counted (the distance's digits not).
Measured with this replay on 277c4e23 (the 1.4.1 base): Camp Narache to Bloodhoof Village on the world grid 29 changes,
Razor Hill to the Crossroads on the roads 18, Brill to Tarren Mill on the world grid 55; now 6, 9 and 19. The test also
works the old way out alongside (TRIMMED_LUA: what's left of the route at every trim, the old road rules) as the before."""

import math

import pytest

from test_map_redraw import game  # noqa: F401

STEP_LUA = """function(px, py, step, wob)
  -- the player `step` yards on toward the route shown 6 yd past where they are along it, `wob` yards to its side
  local r = AGPS_NS.Nav.route
  local p = r and r.parts and r.parts[1]
  if not p or #p.pts < 4 then return false end
  local pts = p.pts
  local best, bs, acc = math.huge, 0, 0
  for i = 1, #pts - 3, 2 do
    local ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and math.max(0, math.min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
    local d = (ax + vx * t - px) ^ 2 + (ay + vy * t - py) ^ 2
    local L = math.sqrt(L2)
    if d < best then best, bs = d, acc + L * t end
    acc = acc + L
    if acc > bs + 200 and best < 100 then break end
  end
  local left = bs + 6
  local tx, ty, nx, ny = pts[#pts - 1], pts[#pts], 0, 0
  for i = 1, #pts - 3, 2 do
    local ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
    local L = math.sqrt((bx - ax) ^ 2 + (by - ay) ^ 2)
    if L >= left and L > 0 then
      local t = left / L
      tx, ty, nx, ny = ax + (bx - ax) * t, ay + (by - ay) * t, -(by - ay) / L, (bx - ax) / L
      break
    end
    left = left - L
  end
  tx, ty = tx + nx * wob, ty + ny * wob
  local dx, dy = tx - px, ty - py
  local d = math.sqrt(dx * dx + dy * dy)
  if d <= step then return tx, ty end
  return px + dx / d * step, py + dy / d * step
end"""

# (the old way, for the before: the maneuvers of what's left of the route, worked out again at every trim, every road
# join and leave said but a hop on and off within HOP_YD, folded into a turn within 15 yd, as 277c4e23 did)
TRIMMED_LUA = """function(r, label)
  local T = AGPS_NS.Turns
  local was = { T.ROAD_TOUCH_YD, T.JOIN_TURN_YD, T.ROAD_KEEP_YD }
  T.ROAD_TOUCH_YD, T.JOIN_TURN_YD, T.ROAD_KEEP_YD = T.HOP_YD, 15, 0
  local path = T.Path(r)
  local ms = T.Maneuvers(path, label, T.HORIZON_YD)
  local horizon = T.HORIZON_YD
  while #ms <= 1 and path.total > horizon and horizon < T.HORIZON_YD * T.HORIZON_STEPS do
    horizon = horizon * 2
    ms = T.Maneuvers(path, label, horizon)
  end
  T.ROAD_TOUCH_YD, T.JOIN_TURN_YD, T.ROAD_KEEP_YD = was[1], was[2], was[3]
  return ms[1]
end"""


def _replay(lua, ns, cont, start, stop, grid, step=2.0):
    """The arrow's line along the walk, each time it changed: [(yards walked, line)], for T.Ahead's maneuvers and for
    the maneuvers of what's left of the route worked out again at every trim (the before)."""
    N, T, R = ns.Nav, ns.Turns, ns.Router
    st = ns.settings.gps
    was = st.worldGrid
    st.worldGrid = grid
    move = lua.eval(STEP_LUA)
    trimmed = lua.eval(TRIMMED_LUA)
    yd = lua.eval("function() return '#' end")
    lines = {"now": [], "trimmed": []}
    try:
        R.Reset()
        lua.execute(f"AGPS_T = 1000; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {start[0]}, {start[1]}, {cont}")
        N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = {cont} }} }}"), False, "red")
        x, y = start
        walked = 0.0
        for i in range(4000):
            r = N.Route(x, y, cont)
            if not r or not r.parts or not r.parts[1] or r.walkYards < 3:
                break
            for kind, m in (("now", T.Ahead(r, "Stop 1")[1][1]), ("trimmed", trimmed(r, "Stop 1"))):
                if m:
                    text = str(T.NowText(m, yd))
                    if not lines[kind] or lines[kind][-1][1] != text:
                        lines[kind].append((walked, text))
            res = move(x, y, step, 1.5 * math.sin(i / 7.0))
            if not res:
                break
            x, y = res
            walked += step
            lua.execute(f"AGPS_T = AGPS_T + {step / 7.0}; AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
        assert walked > 300, walked
    finally:
        st.worldGrid = was
        N.Clear()
    return lines["now"], lines["trimmed"]


@pytest.mark.parametrize("cont,start,stop,grid,most", [
    (1, (-2917.0, -257.0), (-2324.0, -395.0), True, 8),  # (Camp Narache, down off Red Cloud Mesa to Bloodhoof Village)
    (1, (328.0, -4710.0), (-440.0, -2600.0), False, 12),  # (Razor Hill to the Crossroads, the roads)
], ids=["narache_bloodhoof_grid", "razorhill_crossroads_roads"])
def test_walking_a_route_the_directions_line_changes_far_less(game, cont, start, stop, grid, most):  # noqa: F811
    lua, ns = game
    now, before = _replay(lua, ns, cont, start, stop, grid)
    said = "\n".join(f"{d:6.0f}  {t}" for d, t in now)
    assert len(now) - 1 <= most, said
    assert len(now) - 1 <= (len(before) - 1) * 0.6, (len(now) - 1, len(before) - 1, said)
    # (no "Join the road" / "Leave the road" said twice within a short way: a road touched for a few yards isn't said)
    roads = [d for d, t in now if ("join the road" in t.lower() or "leave the road" in t.lower())
             and not t.endswith(" now")]
    assert all(b - a > 100 for a, b in zip(roads, roads[1:])), said
    assert now[-1][1].startswith("Arrive at"), said


def test_red_cloud_mesas_road_down_is_no_stairs(game):  # noqa: F811
    # (Kooki3z for 1.4.1: "Stairs down in 879 yd" from Camp Narache: the world grid's walk down the mesa's ramp, its floor
    # yards over the shipped ground along the cliff, and a road's heights meeting the grid's at its foot, were "stairs")
    lua, ns = game
    N, T, R = ns.Nav, ns.Turns, ns.Router
    st = ns.settings.gps
    was = st.worldGrid
    st.worldGrid = True
    try:
        for stop in ((-2500.0, -100.0), (-2324.0, -395.0), (-2200.0, -700.0)):
            R.Reset()
            lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -2917.0, -257.0, 1")
            N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 1 }} }}"), False, "red")
            r = N.Route(-2917.0, -257.0, 1)
            path = T.Path(r)
            assert path.total > 900
            # (down the mesa: the route goes down 60 yd and more)
            fz = [path.fz[i] for i in range(1, len(path.cum) + 1) if path.fz[i] is not False]
            assert max(fz) - min(fz) > 60
            assert len(T.Stairs(path)) == 0, [(f.s0, f.dir) for f in T.Stairs(path).values()]
            ms = T.Maneuvers(path, "Stop 1", math.inf)
            said = [str(ms[i].text) for i in range(1, len(ms) + 1)]
            assert not [t for t in said if "stairs" in t.lower()], said
    finally:
        st.worldGrid = was
        N.Clear()


def _path(lua, ns, pts, kinds):
    """A hand-made walk in the open sea off Westfall (no roads, junctions, bridges or places near it)."""
    flat = []
    for x, y in pts:
        flat += [x, y]
    part = lua.table(cont=0, pts=lua.table(*flat), kinds=lua.table(*kinds), stop=1)
    return ns.Turns.Path(lua.table(parts=lua.table(part), legs=lua.table(lua.table(walk=True))))


def _said(ns, path):
    N = ns.Nav
    swims = N.SwimSpans
    N.SwimSpans = None  # (no swims: it's all water out there)
    try:
        ms = ns.Turns.Maneuvers(path, "Stop 1", math.inf)
    finally:
        N.SwimSpans = swims
    return [str(ms[i].text) for i in range(1, len(ms) + 1)]


X0, Y0 = -11500.0, 2500.0  # (out at sea, west of Westfall)


def test_a_short_road_touch_says_nothing(game):  # noqa: F811
    lua, ns = game
    # (off the road 300 yd, on it 50, off it again 300, all straight on: nothing to say but the arrival)
    pts = [(X0 + s, Y0) for s in (0, 300, 350, 650)]
    assert _said(ns, _path(lua, ns, pts, [1, 0, 1])) == ["Arrive at Stop 1"]
    # (and on a road, off it for 40 yd and back on)
    pts = [(X0 + s, Y0) for s in (0, 300, 340, 650)]
    assert _said(ns, _path(lua, ns, pts, [0, 1, 0])) == ["Arrive at Stop 1"]


def test_a_join_near_a_turn_is_that_turn(game):  # noqa: F811
    lua, ns = game
    # (300 yd north off the road, then the road joined and 20 yd on a right turn on it: one instruction, at the turn)
    pts = [(X0, Y0), (X0 + 300, Y0), (X0 + 320, Y0), (X0 + 320, Y0 - 400)]
    said = _said(ns, _path(lua, ns, pts, [1, 0, 0]))
    assert said == ["Turn right onto the road", "Arrive at Stop 1"], said


def test_a_bare_leave_is_said_only_before_a_long_walk(game):  # noqa: F811
    lua, ns = game
    # (on the road, straight on off it for 400 yd: said; off it for 150 yd to the stop: not, the arrival says it)
    pts = [(X0 + s, Y0) for s in (0, 400, 800)]
    assert _said(ns, _path(lua, ns, pts, [0, 1])) == ["Leave the road", "Arrive at Stop 1"]
    pts = [(X0 + s, Y0) for s in (0, 400, 550)]
    assert _said(ns, _path(lua, ns, pts, [0, 1])) == ["Arrive at Stop 1"]
    # (and the walk from the player to the road, straight on along it: not said either)
    pts = [(X0 + s, Y0) for s in (0, 30, 800)]
    assert _said(ns, _path(lua, ns, pts, [1, 0])) == ["Arrive at Stop 1"]


def test_the_shown_maneuver_stays_first_over_a_new_kink_for_a_moment(game):  # noqa: F811
    lua, ns = game
    T = ns.Turns
    mk = lua.eval("""function(list)
      local out = {}
      for i, m in ipairs(list) do out[i] = { words = m[1], kind = m[2], x = m[3], y = m[4], dist = m[5] } end
      return out
    end""")
    T.held, T.pending = None, None
    first = mk(lua.eval("{ { 'turn_left', 'turn', 100, 0, 80 }, { nil, 'arrive', 500, 0, 480 } }"))
    assert T.Steady(first, 10.0, 7)[1].words == "turn_left"
    # (the route worked out again: a slight right a few yards ahead first now; the turn left still ahead, 3 yd off)
    again = mk(lua.eval("{ { 'slight_right', 'turn', 25, 0, 6 }, { 'turn_left', 'turn', 102, 1, 78 },"
                        " { nil, 'arrive', 500, 0, 476 } }"))
    assert T.Steady(again, 10.5, 7)[1].words == "turn_left"
    assert T.Steady(again, 11.0, 7)[1].words == "turn_left"
    # (still there after STEADY_SECS: said)
    assert T.Steady(again, 10.5 + T.STEADY_SECS + 0.1, 7)[1].words == "slight_right"
    # (the one shown gone from the new route: the next at once)
    T.held, T.pending = None, None
    T.Steady(first, 20.0, 7)
    gone = mk(lua.eval("{ { 'slight_right', 'turn', 25, 0, 6 }, { nil, 'arrive', 500, 0, 476 } }"))
    assert T.Steady(gone, 20.1, 7)[1].words == "slight_right"
    # (another trip: nothing held from the last one)
    T.held, T.pending = None, None
    T.Steady(first, 30.0, 7)
    assert T.Steady(again, 30.1, 8)[1].words == "slight_right"
    T.held, T.pending = None, None


def test_the_maneuvers_ahead_dont_change_as_the_route_is_trimmed(game):  # noqa: F811
    # (the same maneuvers at the same spots as the player goes on along a route, until it's worked out again)
    lua, ns = game
    N, T, R = ns.Nav, ns.Turns, ns.Router
    try:
        R.Reset()
        lua.execute("AGPS_T = 2000; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 328.0, -4710.0, 1")
        N.SetStops(lua.eval("{ { x = -440.0, y = -2600.0, cont = 1 } }"), False, "red")
        r = N.Route(328.0, -4710.0, 1)
        _, ms = T.Ahead(r, "Stop 1")
        spots = [(str(ms[i].text), round(ms[i].x), round(ms[i].y)) for i in range(1, len(ms) + 1)]
        move = lua.eval(STEP_LUA)
        x, y = 328.0, -4710.0
        for i in range(40):
            x, y = move(x, y, 2.0, 1.5 * math.sin(i / 7.0))
            lua.execute(f"AGPS_T = AGPS_T + 0.25; AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
            r2 = N.Route(x, y, 1)
            assert lua.eval("function(a, b) return rawequal(a, b) end")(r, r2)  # (followed, not worked out again)
            _, ms = T.Ahead(r2, "Stop 1")
            now = [(str(ms[i].text), round(ms[i].x), round(ms[i].y)) for i in range(1, len(ms) + 1)]
            assert now == spots[len(spots) - len(now):], (now, spots)
        assert r.consumed > 40
    finally:
        N.Clear()
