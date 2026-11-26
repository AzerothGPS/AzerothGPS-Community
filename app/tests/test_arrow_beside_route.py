"""The arrow beside the route (item 69, Kooki3z 2026-11-24 in Stranglethorn: a few yards off a world-grid route the arrow
snapped between the route and ahead and flipped white/green). Out in the open world the arrow aims the averaged
look-ahead (Turns.Target), not the corners' aim of the capitals and insides; and its color holds a margin
(Arrow.COLOR_HOLD). A player walking 3-6 yd beside a gently curving grid route, facing along it: the angle changes
smoothly and the color stays green."""

import math

from test_map_redraw import game  # noqa: F401


def test_walking_beside_a_curving_grid_route_the_arrow_is_steady_and_green(game):  # noqa: F811
    lua, ns = game
    T, A, st = ns.Turns, ns.Arrow, ns.settings.gps
    st.worldGrid = True
    # (a gently curving route on the grid: a wiggle of a few yards a cell, as the grid's paths through woods have)
    route = []
    for i in range(0, 81):
        s0 = i * 5.0
        route.append((s0, 30 * math.sin(s0 / 120) + (1.5 if i % 2 else -1.5)))
    angles, colors, last = [], [], None
    for k in range(10, 40):
        s0 = k * 5.0
        x, y = s0, 30 * math.sin(s0 / 120)
        dx, dy = 1.0, 30 / 120 * math.cos(s0 / 120)
        n = math.hypot(dx, dy)
        off = 3 + 3 * ((k * 7) % 5) / 4  # (3-6 yd beside it, back and forth)
        px, py = x - dy / n * off, y + dx / n * off
        facing = math.atan2(dy, dx)
        # (the route as the game follows it: from the player onto the line, then on: Nav trims what's behind them)
        ahead = [p for p in route if p[0] > s0]
        pts, fz = [px, py], [40.0]
        for q in ahead:
            pts += [q[0], q[1]]
            fz.append(40.0)
        part = lua.table(cont=0, pts=lua.table(*pts), kinds=lua.table(*([1] * (len(fz) - 1))), stop=1, fz=lua.table(*fz))
        path = T.Path(lua.table(parts=lua.table(part), legs=lua.table(lua.table(walk=True))))
        tx, ty = T.Target(path, px, py)
        rel = T.RelativeAngle(px, py, facing, tx, ty)
        color = A.ColorFor(None, rel, last)[0]
        last = color
        angles.append(rel)
        colors.append(color)
    jumps = [abs(b - a) for a, b in zip(angles, angles[1:])]
    assert max(jumps) < math.radians(8), [round(math.degrees(j), 1) for j in jumps]
    assert all(c == 1 for c in colors), colors
