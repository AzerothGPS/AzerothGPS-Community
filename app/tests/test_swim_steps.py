"""A walk's swims as their own steps (asked for 1.3.10): the route's directions split a walk by what's done along it,
"Walk 290 yd", "Swim 154 yd", "Walk 2.8k yd", each timed at its own speed (the swim speed for a swim, Nav.TripSecs),
pieces under Nav.SWIM_STEP_MIN_YD folded into their neighbors; the arrow's words say "Swim" while swimming."""

import re

import pytest

from test_map_redraw import game  # noqa: F401
from test_swim_routes import DUN_MODR, MALEB, trip, water  # noqa: F401


def _plain(s):
    return re.sub(r"\|c[0-9a-fA-F]{8}|\|r|\|T[^|]*\|t", "", str(s)).strip()


def _steps(ns):
    return [_plain(s) for s in ns.Nav.Steps().values()]


def _pieces(ns, r, done=None):
    st = r.stretches[1]
    leg = st.legs[1]
    ps = ns.Nav.LegPieces(st, leg, r.consumed if done is None else done)
    return leg, ([] if ps is None else [ps[i] for i in range(1, len(ps) + 1)])


def _main_swim(ps):
    """The index of the trip's longest swim (the coast's: since the water pricing fixes the trip also crosses a marsh
    channel first, so it isn't the first piece)."""
    return max((i for i, p in enumerate(ps) if p.swim), key=lambda i: ps[i].yd)


def test_the_coast_trip_lists_walk_swim_walk_adding_up_to_the_leg(game, trip):
    lua, ns = game
    N = ns.Nav
    r = trip(DUN_MODR, MALEB)
    assert r.swimYards > 100
    leg, ps = _pieces(ns, r)
    k = _main_swim(ps)
    assert k >= 1 and [p.swim for p in ps[k - 1:k + 2]] == [False, True, False]
    assert sum(p.yd for p in ps) == pytest.approx(leg.yards - r.consumed)
    assert sum(p.sw for p in ps) == pytest.approx(r.swimYards, rel=0.02)
    assert all(p.yd >= N.SWIM_STEP_MIN_YD for p in ps)
    steps = _steps(ns)
    assert [s.split(" ")[0] for s in steps[:len(ps)]] == ["Swim" if p.swim else "Walk" for p in ps], steps
    assert steps[k].startswith("Swim " + N.FormatDistance(ps[k].yd))
    # the panel lists them numbered, the first highlighted
    text = str(N.StepsText(len(ps)))
    assert f"{k}. Walk " in text and f"{k + 1}. Swim " in text and f"{k + 2}. Walk " in text
    assert "|cffffffff1. " in text


def test_tiny_pieces_fold_into_their_neighbors(game):
    lua, ns = game
    N = ns.Nav

    def pieces(runs, a, b):
        out = N.SwimPieces(lua.table(*runs), a, b)
        return [(bool(out[i].swim), round(out[i].s1 - out[i].s0, 3), round(out[i].sw, 3)) for i in range(1, len(out) + 1)]

    # (a bit of land between two swims: one swim, the land in it walked)
    assert pieces([100, 300, 310, 500], 0, 800) == [(False, 100, 0), (True, 400, 390), (False, 300, 0)]
    # (a puddle on a walk: the walk)
    assert pieces([200, 215], 0, 600) == [(False, 600, 15)]
    # (a few yards to go to the water: the swim from here)
    assert pieces([20, 400], 0, 900) == [(True, 400, 380), (False, 500, 0)]
    # (land and water alternating in small bits along a coast: whole, never a list of crumbs)
    runs = []
    for k in range(10):
        runs += [100 + 60 * k, 130 + 60 * k]
    out = pieces(runs, 0, 1000)
    assert all(yd >= N.SWIM_STEP_MIN_YD for _, yd, _ in out)
    assert sum(yd for _, yd, _ in out) == pytest.approx(1000)
    assert sum(sw for _, _, sw in out) == pytest.approx(300)
    # (no swim: one walk)
    assert pieces([], 0, 50) == [(False, 50, 0)]


def test_each_piece_is_timed_at_its_own_speed(game, trip, water):
    lua, ns = game
    N = ns.Nav
    r = trip(DUN_MODR, MALEB)
    _, walk, mount, mounted = list(N.Speeds())[:4]
    speed = mount if mounted else walk
    _, ps = _pieces(ns, r)
    steps = _steps(ns)
    for p, s in zip(ps[:2], steps[:2]):  # (the walk after: cut where it passes a flight master to learn)
        want = (p.yd - p.sw) / speed + p.sw / min(speed, N.SwimSpeed())
        assert s.endswith(str(N.FormatTime(want))), (s, want)
    k = _main_swim(ps)
    swim = ps[k]
    assert swim.sw / N.SwimSpeed() > swim.yd / speed + 5  # (slower than walking it)
    # water as fast as land (Water Walking on): still "Swim", timed as walking
    water(aura=546)
    steps = _steps(ns)
    assert steps[k].startswith("Swim ") and steps[k].endswith(str(N.FormatTime(swim.yd / speed)))


def test_the_steps_advance_across_a_swim_and_the_arrow_says_swim(game, trip):
    lua, ns = game
    N, T = ns.Nav, ns.Turns
    r = trip(DUN_MODR, MALEB)
    before = _steps(ns)
    _, ps = _pieces(ns, r)
    k = _main_swim(ps)
    swim = ps[k]
    # approaching it: "start swimming" ahead
    _, ms = T.Ahead(r, "stop")
    m = next(ms[i] for i in range(1, len(ms) + 1) if ms[i].kind == "swim")
    assert m.dist == pytest.approx(swim.s0, abs=2) and not m.swimNow
    # in the middle of the swim: it's step 1, the walk before it gone
    path = T.Path(r)
    x, y = T.PointAt(path, (swim.s0 + swim.s1) / 2)
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
    trip.settle()
    r = N.route
    assert r.consumed > swim.s0, r.consumed
    steps = _steps(ns)
    assert steps[0].startswith("Swim ") and steps[1].startswith("Walk "), steps
    assert len(steps) == len(before) - k
    assert "|cffffffff1. Swim " in str(N.StepsText(3))
    _, ms = T.Ahead(r, "stop")
    m = ms[1]
    assert m.kind == "shore" and m.swimNow
    assert str(T.NowText(m, N.FormatDistance)).startswith("Swim, then leave the water in ")
    # out of the water, on along the coast: the walk is step 1
    x, y = T.PointAt(path, swim.s1 + 60)
    lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
    trip.settle()
    steps = _steps(ns)
    assert steps[0].startswith("Walk ") and len(steps) == len(before) - k - 1, steps
    _, ms = T.Ahead(N.route, "stop")
    assert not ms[1].swimNow and not str(T.NowText(ms[1], N.FormatDistance)).startswith("Swim")
