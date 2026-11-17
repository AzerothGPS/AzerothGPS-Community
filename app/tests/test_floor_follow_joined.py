"""The floor followed down in Undercity keeps to the roads joined to the one walked on (asked 2026-11-15: "need better
support from starting positions because this is a constant issue"). Walked down the stairs from the Cooking Trainer
three yards off their middle, the walkway overhead was nearer at about the height, and the floor followed went up onto
it: at the bridge's foot "Take the stairs down, Below you, 10 yd down" for the Enchanting Trainer."""

import math

import pytest

COOKING = (1593.1, 274.5, -55.3)
BRIDGE = (1611.7, 252.5)  # (64.7, 41.6 on Undercity's map: the user's screenshot)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    ns.CharDB().faction = "Horde"
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end')
    return lua, ns


@pytest.mark.parametrize("off", [0.0, -3.0, 3.0])
def test_down_the_stairs_from_the_cooking_trainer_the_floor_followed_goes_down(game, off):
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    N.ResetCityTrack()
    res = G.SearchPlaces("cooking trainer", 8)
    e = next(res[i] for i in range(1, len(res) + 1) if res[i].cont == 10001)
    cx, cy, cz = e.x, e.y, e.z
    assert abs(cx - COOKING[0]) < 1 and abs(cy - COOKING[1]) < 1
    lua.execute(f"AGPS_MAP = 1458; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {cx}, {cy}, 0; "
                "AGPS_T = (AGPS_T or 5000) + 100")
    assert N.AnchorFloor(10001, cx, cy, cz)  # (the trainer's window: their floor)
    N.SetStops(lua.eval(f"{{ {{ x = {BRIDGE[0]}, y = {BRIDGE[1]}, cont = 10001, z = -62, name = 'Bridge' }} }}"),
               False, "red")
    for _ in range(6):
        lua.execute("AGPS_T = AGPS_T + 0.3")
        G.Update()
    r = N.route
    pts = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    path = list(zip(pts[0::2], pts[1::2]))
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        L = math.hypot(bx - ax, by - ay) or 1
        nx, ny = -(by - ay) / L * off, (bx - ax) / L * off  # (beside the road's middle)
        n = max(1, int(L / 1.5))
        for k in range(1, n + 1):
            lua.execute(f"AGPS_T = AGPS_T + 0.2; AGPS_POS[1], AGPS_POS[2] = {ax + (bx - ax) * k / n + nx}, "
                        f"{ay + (by - ay) * k / n + ny}")
            G.Update()
    z = N.FollowedZ(10001)
    assert z is not None and z < -59, f"walked {off} yd off the stairs' middle: the floor followed is {z}"
    N.Clear()


def test_dropped_into_the_trade_quarter_the_floor_followed_is_taken_again(game):
    # (2026-11-15: in the Trade Quarter at 61.3, 52.4 "Below you, 17 yd down" for the Enchanting Trainer stayed after
    # the player dropped down, and the route said turn around: "never reconsidered")
    lua, ns = game
    N, G, R = ns.Nav, ns.GPS, ns.Router
    b = ns.Maps[1458].bounds
    x, y = b[3] - 52.4 / 100 * (b[3] - b[1]), b[4] - 61.3 / 100 * (b[4] - b[2])
    hs = R.HeightsNear(10001, x, y, N.TRACK_YD)
    floors = sorted({round(hs[i].z) for i in range(1, len(hs) + 1)})
    N.ResetCityTrack()
    N.Clear()
    lua.execute(f"AGPS_MAP = 1458; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0; AGPS_T = (AGPS_T or 5000) + 100")
    high = floors[-1] + 17  # (the floor followed before the drop: none of its roads near)
    lua.execute(f"AGPS_FAKE_Z = {high}")
    N.TrackCityZ(10001, x, y)
    lua.execute("AGPS_NS.Nav.SetTrackForTests(10001, AGPS_POS[1], AGPS_POS[2], AGPS_FAKE_Z)")
    assert N.FollowedZ(10001) == high
    for k in range(1, 9):
        lua.execute(f"AGPS_T = AGPS_T + 0.3; AGPS_POS[1] = {x + k * 0.5}")
        N.TrackCityZ(10001, x + k * 0.5, y)
    z = N.FollowedZ(10001)
    assert z is None or abs(z - high) > N.TRACK_STEP, f"the floor followed stayed {z} with no road of it near ({floors})"
