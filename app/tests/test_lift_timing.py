"""Lift timing (item 118, 1.4.1; SPF parity without the player's height): each lift car's loop from the client's
TransportAnimation (Data/LiftTimes.lua, `agps lifts --times`), phased in game from the rides the player is seen taking
(Lifts.lua: on a car's shaft from one floor, off it onto the other), and the next car said on the directions' line
("Take the lift up (lift arrives in 12s)") once a phase is known; nothing said otherwise (the route's fixed lift time
as before)."""

import re
from pathlib import Path

import pytest

from azerothgps import lifts

lupa = pytest.importorskip("lupa")

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"


# --- the timetable (Python) -------------------------------------------------------------------------------------------

def _rows(seq_frames):
    return [{"SequenceID": seq, "TimeIndex": t, "Pos": [0.0, 0.0, z]} for seq, t, z in seq_frames]


def test_a_cars_loop_merges_its_sequences_by_time_and_finds_one_stop_at_each_end():
    # (Undercity's 20652 as the client has it: sequences 0, 162 and 164, one loop only with all three merged by time)
    period, track = lifts.car_track(_rows([(0, 0, 0.0), (162, 167, 0.0), (162, 8500, 96.5), (164, 3667, 96.5),
                                           (164, 11833, 0.0), (164, 16667, 0.0)]))
    assert period == pytest.approx(16.667)
    assert [t for t, _ in track] == pytest.approx([0, 0.167, 3.667, 8.5, 11.833, 16.667])
    top = lifts.dock_window(track, period, lambda dz: dz >= 96.5 - lifts.DOCK_Z)
    bottom = lifts.dock_window(track, period, lambda dz: dz <= lifts.DOCK_Z)
    assert top[0] == pytest.approx(3.6, abs=0.05) and top[1] == pytest.approx(8.57, abs=0.05)
    # (the bottom's stop wraps the loop's end: 11.8 s in to 0.2 s into the next)
    assert bottom[0] == pytest.approx(11.77, abs=0.05) and bottom[1] == pytest.approx(16.91, abs=0.05)


def test_a_loop_with_two_stops_at_one_end_is_refused():
    period, track = lifts.car_track(_rows([(0, 0, 0.0), (0, 2000, 10.0), (0, 4000, 0.0), (0, 6000, 10.0),
                                           (0, 8000, -5.0)]))
    with pytest.raises(ValueError):
        lifts.dock_window(track, period, lambda dz: dz >= 10.0 - lifts.DOCK_Z)


def _shipped_cars():
    text = (ADDON / "Data" / "LiftTimes.lua").read_text(encoding="utf-8")
    cars = []
    for m in re.finditer(r"\{ entry = (\d+), place = \"([^\"]+)\", station = (\d+).*?period = ([\d.]+)", text):
        cars.append((int(m.group(1)), m.group(2), int(m.group(3)), float(m.group(4))))
    return cars


def test_the_shipped_lifts_are_every_one_players_ride():
    cars = _shipped_cars()
    by = {}
    for entry, place, station, period in cars:
        by.setdefault(place, []).append((entry, station, period))
    # Undercity's three (one car a shaft), Thunder Bluff's two lifts of two cars, the Great Lift's and Freewind Post's
    assert len(by["Undercity"]) == 3 and len({s for _, s, _ in by["Undercity"]}) == 3
    assert len(by["Thunder Bluff"]) == 4 and len({s for _, s, _ in by["Thunder Bluff"]}) == 2
    assert len(by["Thousand Needles"]) == 4 and len({s for _, s, _ in by["Thousand Needles"]}) == 2
    assert all(p == pytest.approx(16.667) for _, _, p in by["Undercity"])
    assert all(p in (30.0, 30.033) for _, _, p in by["Thunder Bluff"] + by["Thousand Needles"])


# --- the rides seen (Lua) -------------------------------------------------------------------------------------------

@pytest.fixture
def lt():
    lua = lupa.LuaRuntime()
    ns = lua.table()
    lua.execute("AGPS_T = 1000 GetTime = function() return AGPS_T end GetServerTime = function() return math.floor(AGPS_T + 5000) end")
    loader = lua.eval("function(src, name) return assert(load(src, '@' .. name)) end")
    for name in ("Locales/Locales.lua", "Data/LiftTimes.lua", "Lifts.lua"):
        loader((ADDON / name).read_text(encoding="utf-8"), name)("AzerothGPS", ns)
    ns.db = lua.table()
    ns.RealmName = lua.eval("function() return 'Test' end")
    ns.Nav = lua.table(FormatTime=lua.eval("function(s) return string.format('%ds', math.floor(s + 0.5)) end"))
    # (the floor followed, as the tests set it: AGPS_Z)
    ns.Lifts.PlayerFloorZ = lua.eval("function() return AGPS_Z end")
    return lua, ns


def _first(r):
    return r[0] if isinstance(r, tuple) else r


def _car(ns, entry, x=None):
    for i in range(1, len(ns.LiftCars) + 1):
        c = ns.LiftCars[i]
        if c.entry == entry and (x is None or abs(c.x - x) < 1):
            return c
    raise KeyError(entry)


class _Player:
    """The half-second looks: GetTime and the server's time (whole seconds) going on together, the true loop's start
    `phase0` (server time) the car runs on."""

    def __init__(self, lua, ns, server0=5000.0):
        self.lua, self.LT, self.t = lua, ns.Lifts, server0 - 5000.0

    def at(self, level, x, y, z=None, secs=0.5):
        end = self.t + secs
        while self.t < end - 1e-9:
            self.t += 0.5
            self.lua.globals().AGPS_T = self.t
            self.lua.globals().AGPS_Z = z
            self.LT.Tick(self.t, int(self.t + 5000), level, x, y)

    def server(self):
        return self.t + 5000


def test_a_ride_down_undercitys_lift_phases_its_car_and_the_next_one_is_said(lt):
    lua, ns = lt
    LT = ns.Lifts
    c = _car(ns, 20652)
    P = c.period
    phase0 = 5003.0  # (the car's loop began at server time 5003: it's at the top 3.6-8.57 s into each loop)
    p = _Player(lua, ns)
    # walking up to the shaft in the Ruins (level 0: the top), on at 5.5 s into the loop, the level going to
    # Undercity's on the way down; the car stops at the bottom 11.77 s in, stepped off a moment later
    p.at(0, c.x + 20, c.y, secs=2.0)  # (-> 5002)
    p.at(0, c.x + 12, c.y, secs=6.0)  # (-> 5008: 5 s in)
    p.at(0, c.x + 1, c.y, secs=6.0)  # (on it -> 5014: 11 s in)
    p.at(10001, c.x + 1, c.y, secs=1.5)  # (down, standing on it -> 5015.5: 12.5 s in)
    assert LT.Sightings()[LT.CarKey(c)] is None
    p.at(10001, c.x + 12, c.y, secs=1.0)  # (stepped off: the floor's Undercity's)
    s = LT.Sightings()[LT.CarKey(c)]
    assert s is not None and s.n == 1
    d = (s.phase - phase0 + P / 2) % P - P / 2
    assert abs(d) <= 1.0, s.phase
    # a while later, down in Undercity: the next car at the bottom, and at the top
    t = phase0 + 40 * P + 8.0  # (8 s into a loop: at the top, at the bottom 11.77 s in)
    w, left = LT.LiftWait(10001, c.x, c.y, "bottom", t)
    assert w == pytest.approx(3.77, abs=1.1)
    w, left = LT.LiftWait(0, c.x, c.y, "top", t)
    assert w == 0 and left == pytest.approx(0.57, abs=1.1)
    assert "lift arrives in" in LT.WaitWords(10001, c.x, c.y, "bottom", t)
    # (the other lifts' cars aren't known from it: Undercity's shafts are one car each)
    other = _car(ns, 20649)
    assert _first(LT.LiftWait(0, other.x, other.y, "top", t)) is None


def test_no_ride_seen_nothing_is_said(lt):
    lua, ns = lt
    LT = ns.Lifts
    c = _car(ns, 4170)
    assert _first(LT.LiftWait(1, c.x, c.y, "bottom", 6000)) is None
    assert LT.WaitWords(1, c.x, c.y, "bottom", 6000) is None
    m = lua.table(dist=20, lift=lua.table(level=1, x=c.x, y=c.y, floor="bottom"))
    assert LT.ManeuverWords(m) is None


def test_a_fall_down_the_shaft_is_not_a_ride(lt):
    # (the car away at the bottom, walked into the shaft at Thunder Bluff's top: down in 2 s, quicker than the car)
    lua, ns = lt
    LT = ns.Lifts
    c = _car(ns, 4170)
    p = _Player(lua, ns)
    p.at(1, c.x + 15, c.y, z=c.hi, secs=2.0)
    p.at(1, c.x, c.y, z=None, secs=2.0)
    p.at(1, c.x + 15, c.y, z=c.lo, secs=1.0)
    assert LT.Sightings()[LT.CarKey(c)] is None
    assert "not a ride" in ns.db.liftLog[len(ns.db.liftLog)]


def test_a_ride_up_thunder_bluffs_lift_by_the_floor_followed(lt):
    lua, ns = lt
    LT = ns.Lifts
    c = _car(ns, 4171, x=-1308.4)  # (at the bottom 28.97-36.08 s into its loop, at the top 14.06-21.01)
    P = c.period
    phase0 = 4990.0
    p = _Player(lua, ns)  # (server 5000: 10 s into the loop)
    p.at(1, c.x, c.y - 20, z=c.lo, secs=20.0)  # (waiting at the foot -> 5020: 30 s in)
    p.at(1, c.x, c.y, z=None, secs=14.5)  # (on it, up: the floor followed opens up at the lift -> 5034.5, 14.5 s in)
    p.at(1, c.x, c.y - 15, z=c.hi, secs=1.0)  # (off at the top)
    s = LT.Sightings()[LT.CarKey(c)]
    assert s is not None
    assert abs((s.phase - phase0 + P / 2) % P - P / 2) <= 1.0
    # the station's other car isn't known: its own loop (30.033 s) drifts from this one's; this car is said
    w, _ = LT.LiftWait(1, c.x, c.y, "bottom", phase0 + 10 * P + 20.0)
    assert w == pytest.approx(8.97, abs=1.1)
    # a second ride sharpens it, one far off replaces it
    LT.Rode(c, "top", phase0 + 100 * P + 1.0, phase0 + 100 * P + 14.06 + 0.5 + 1.0)  # (on at the foot 1 s in)
    s = LT.Sightings()[LT.CarKey(c)]
    assert s.n == 2
    LT.Rode(c, "top", phase0 + 200 * P + 1.0 + 9, phase0 + 200 * P + 14.06 + 9 + 1.0)  # (the server restarted: 9 s on)
    s = LT.Sightings()[LT.CarKey(c)]
    assert s.n == 1 and abs((s.phase - phase0 - 9 + P / 2) % P - P / 2) <= 1.0


def test_an_old_phase_isnt_used(lt):
    lua, ns = lt
    LT = ns.Lifts
    c = _car(ns, 11898, x=-4665.4)
    LT.Rode(c, "bottom", 1000.0, 1000.0 + 20.0)
    assert _first(LT.LiftWait(1, c.x, c.y, "top", 1100.0)) is not None
    assert _first(LT.LiftWait(1, c.x, c.y, "top", 1020.0 + LT.KEEP_HOURS * 3600 + 1)) is None


def test_the_clock_is_the_servers_to_a_fraction_of_a_second(lt):
    lua, ns = lt
    LT = ns.Lifts
    LT.ResetClock()
    # (GetServerTime ticks over at GetTime 10.3: the server's time is GetTime + 4999.7)
    for now in (10.0, 10.2, 10.4, 10.6, 11.25, 11.35):
        LT.NoteClock(now, int(now + 4989.7))
    assert LT.Now(12.0, int(12.0 + 4989.7)) == pytest.approx(12.0 + 4989.7, abs=0.06)


def test_riding_the_wait_isnt_said(lt):
    # (on the car, gone from the floor it was boarded at: the next car there is no use)
    lua, ns = lt
    LT = ns.Lifts
    c = _car(ns, 20655)
    P = c.period
    LT.Rode(c, "bottom", 5000.0 - 8, 5000.0)  # (stopped at the bottom 15.1 s in: about 4999)
    phase = LT.Sightings()[LT.CarKey(c)].phase
    p = _Player(lua, ns, server0=phase + 3 * P + 7.5)  # (at the top 6.93-11.91 s in)
    p.at(0, c.x, c.y, secs=1.0)  # (on it at the top, standing)
    t = p.server()
    assert LT.WaitWords(0, c.x, c.y, "top", t) is not None  # (here: "lift here, leaves in")
    assert LT.WaitWords(0, c.x, c.y, "top", t + 6) is None  # (it's left with them on it)


# --- the directions' line (the whole addon) --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    return start()


def test_the_directions_line_says_the_next_car_at_a_lift(game):
    lua, ns = game
    LT, T, R = ns.Lifts, ns.Turns, ns.Router
    c = _car(ns, 4171, x=-1308.4)
    # a walk to Thunder Bluff's lift at its foot, up it, and on
    part = lua.table(pts=lua.table(c.x + 40, c.y, c.x, c.y, c.x, c.y - 6, c.x, c.y - 106),
                     kinds=lua.table(0, R.KIND_LIFT_UP, 0), cont=1, stop=1)
    path = T.Path(lua.table(parts=lua.table(part)))
    ms = T.Maneuvers(path, "the stop")
    m = next(ms[i] for i in range(1, len(ms) + 1) if ms[i].kind == "lift")
    assert m.lift.floor == "bottom" and m.lift.level == 1
    fmt = lua.eval("function(d) return string.format('%d yd', d) end")
    plain = str(T.NowText(m, fmt))
    assert "lift" in plain and "arrives" not in plain  # (no phase known: as before)
    # a ride seen: the car stops at the foot 28.97 s into its loop
    t = LT.Now()
    P = c.period
    LT.Sightings()[LT.CarKey(c)] = lua.table(phase=(t - 20.0) % P, at=t, n=1)  # (20 s into its loop now)
    said = str(T.NowText(m, fmt))
    assert said.startswith(plain) and "(lift arrives in 9s)" in said
    # far from it, nothing more
    m.dist = LT.NOTE_YD + 1
    assert "arrives" not in str(T.NowText(m, fmt))
    LT.Sightings()[LT.CarKey(c)] = None


def test_undercitys_lift_ride_is_boarded_at_its_floor(game):
    lua, ns = game
    LT = ns.Lifts
    rows = [ns.Transports[i] for i in range(1, len(ns.Transports) + 1) if ns.Transports[i][8] == "lift"
            and ns.Transports[i][9] == "Undercity"]
    assert len(rows) == 3
    for t in rows:
        down, up = LT.RideLift(t, 2), LT.RideLift(t, 1)  # (from the Ruins, down; from the city, up)
        assert down.floor == "top" and up.floor == "bottom"
        assert LT.CarAt(down.level, down.x, down.y, 3) is not None
