"""From Cut-Throat Alley to the Cathedral of Light in Stormwind (issue #560): the alley's way out is its west door at
about (-8544.5, 615.5), onto a landing at z 101, then over the plaza at z 100 to the bridge's east end by (-8506, 656)
and over it at z 102-104. Stormwind's capital grid closes the alley's west part, so with no road there the route left
by the alley's east end and looped round the canal ring (893 yd for a 262 yd straight line; 651 after the roads of
#567). Both ways were walked on foot in testing and ship as floor tracks:
the alley to the landing, and the landing over the plaza and the bridge. The city road beside the plaza by
(-8524, 654) is a ramp down to the canal walkway at z 94: walked, it stuck under the bridge. The whole addon
(gameharness)."""
import math

import pytest

pytest.importorskip("lupa.lua51")

ALLEY = (-8537.2, 575.2, 102.0)  # (Cut-Throat Alley, on its street road)
DOOR_OUT = (-8547.7, 618.5, 102.0)  # (just outside the alley's west door)
CATHEDRAL = (-8539.1, 837.5, 106.0)  # (the Cathedral of Light)
DOOR = (-8544.4, 615.5)  # (the alley's west door, walked)
BRIDGE_EAST = (-8506.4, 655.0)  # (the bridge's east end on the plaza, walked)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def _route(lua, ns, s, t):
    r = ns.Router.Route(0, s[0], s[1], t[0], t[1], lua.table_from({"z": s[2], "tz": t[2]}))
    assert r is not None and r.pts
    f = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    return r, list(zip(f[0::2], f[1::2]))


def _near(pts, spot):
    """The route's nearest approach to `spot`, over its segments."""
    best = math.inf
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((spot[0] - ax) * vx + (spot[1] - ay) * vy) / L2))
        best = min(best, math.dist((ax + vx * t, ay + vy * t), spot))
    return best


def test_cut_throat_alley_to_the_cathedral_leaves_by_the_alleys_west_door(game):
    lua, ns = game
    r, pts = _route(lua, ns, ALLEY, CATHEDRAL)
    assert pts[-1] == pytest.approx(CATHEDRAL[:2], abs=1)
    assert (r.blocked or 0) == 0
    assert r.length <= 500, r.length  # (467: not 651 out by the alley's east end, nor 893 round the canal ring)
    assert _near(pts, DOOR) <= 3, _near(pts, DOOR)
    assert min(x for x, _ in pts) > -8700  # (the canal ring's loop went south to x -8742)


def test_from_the_alleys_door_over_the_plaza_to_the_bridge_not_down_to_the_canal(game):
    lua, ns = game
    r, pts = _route(lua, ns, DOOR_OUT, CATHEDRAL)
    assert (r.blocked or 0) == 0
    assert not r.swum
    assert r.length <= 450, r.length  # (415)
    assert _near(pts, BRIDGE_EAST) <= 4, _near(pts, BRIDGE_EAST)
