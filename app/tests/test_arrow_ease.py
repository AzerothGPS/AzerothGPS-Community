"""Smooth arrow turns (Kooki3z 2026-11-20: "every direction arrow change starts slow, speeds up, then slows down again to
its final position ... sudden jumps on direction change like approaching stairs aren't so violent"): Arrow.lua
A.EaseStep."""

import math

import pytest


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


def test_a_big_jump_eases_slow_fast_slow(game):
    lua, ns = game
    A = ns.Arrow
    st = lua.table()
    assert A.EaseStep(st, 0.0, 0.016) == 0.0
    target = math.radians(120)
    shown, steps = [], 0
    while steps < 200:
        shown.append(A.EaseStep(st, target, 0.016))
        steps += 1
        if abs(shown[-1] - target) < 1e-9:
            break
    assert abs(shown[-1] - target) < 1e-9
    dur = A.EASE_TIME * math.radians(120) / math.pi
    assert abs(steps * 0.016 - dur) < 0.05
    moves = [b - a for a, b in zip([0.0] + shown, shown)]
    n = len(moves)
    first, mid, last = moves[1], moves[n // 2], moves[-2]
    assert first < mid and last < mid  # (slow, fast, slow)


def test_small_changes_follow_at_once_and_the_ease_follows_the_route(game):
    lua, ns = game
    A = ns.Arrow
    st = lua.table()
    A.EaseStep(st, 0.0, 0.016)
    assert A.EaseStep(st, math.radians(10), 0.016) == pytest.approx(math.radians(10))  # (turning yourself: at once)
    # a jump eases; meanwhile the route turns 15 degrees more: it ends there, not where it was going
    A.EaseStep(st, math.radians(100), 0.016)
    for _ in range(100):
        a = A.EaseStep(st, math.radians(115), 0.016)
    assert a == pytest.approx(math.radians(115))
    # the short way round: from 170 to -170 degrees is 20 degrees, not 340
    st2 = lua.table()
    A.EaseStep(st2, math.radians(170), 0.016)
    assert A.EaseStep(st2, math.radians(-170), 0.016) == pytest.approx(math.radians(-170))


def test_the_option_off_turns_at_once(game):
    lua, ns = game
    A = ns.Arrow
    ns.settings.gps.arrowEase = False
    try:
        st = lua.table()
        A.EaseStep(st, 0.0, 0.016)
        assert A.EaseStep(st, math.radians(150), 0.016) == pytest.approx(math.radians(150))
    finally:
        ns.settings.gps.arrowEase = True
