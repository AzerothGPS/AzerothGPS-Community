"""1.4.0, Kooki3z: "when 'working out the route...' have the '...' cycle from 1 to 3 dots indicating its working and have
the random message change every 5 seconds", and "on a multi stop route, go ahead and work out and plot the closest
stop's route then continue working out the rest in the background"."""

import pytest

BRILL = (2260.0, 290.0)
# (five stops round Lordaeron from Brill: the fastest order's second stop far from the first)
FIVE = ("{ { x = -427.7, y = -1909.3, cont = 0, name = 'Hillsbrad' }, { x = 1800, y = 1000, cont = 0, name = 'A' },"
        " { x = 1700, y = 700, cont = 0, name = 'Fields' }, { x = 1993.0, y = -967.0, cont = 0, name = 'B' },"
        " { x = 0.0, y = -860.0, cont = 0, name = 'C' } }")


def _start():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end; AGPS_LEVEL = 30')
    ns.CharDB().faction = "Horde"
    ns.settings.gps.fastestOrder = True
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {BRILL[0]}, {BRILL[1]}, 0")
    lua.execute("""
      AGPS_FRAME = function(dt)
        AGPS_T = AGPS_T + dt
        for _, w in ipairs(AGPS_WIDGETS) do
          local f = w._scripts.OnUpdate
          if f and w._shown then f(w, dt) end
        end
      end""")
    return lua, ns


@pytest.fixture(scope="module")
def game():
    return _start()


def test_the_dots_cycle_while_the_route_is_worked_out_and_stop_when_it_is_in(game):
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    N.Clear()
    ns.settings.gps.shown, ns.settings.gps.minimized = True, None
    frame = lua.eval("AzerothGPSFrame")
    frame.Show(frame)
    # (the roads still being built: "Working out the route..." until AGPS_BUSY goes)
    lua.execute("AGPS_BUSY = true; AGPS_WARMUP = AGPS_NS.Router.WarmUp; "
                "AGPS_NS.Router.WarmUp = function(...) if AGPS_BUSY then return true end return AGPS_WARMUP(...) end")
    lua.execute("""
      AGPS_LAYOUTS = 0
      local G = AGPS_NS.GPS
      local lay = G.LayoutGroupRows
      G.LayoutGroupRows = function(...) AGPS_LAYOUTS = AGPS_LAYOUTS + 1 return lay(...) end""")
    run = lua.eval("AGPS_FRAME")
    try:
        N.SetStops(lua.eval(f"{{ {{ x = {BRILL[0] + 260}, y = {BRILL[1] + 40}, cont = 0, name = 'There' }} }}"), False,
                   "red")
        seen = []
        for _ in range(120):  # (4 s at 30 frames a second)
            run(1 / 30)
            t = str(G.navText.GetText(G.navText))
            if "Working out the route" in t and (not seen or seen[-1] != t):
                seen.append(t)
        assert N.warming and not N.route
        dots = [t.split("route", 1)[1] for t in seen]
        # (one, two, three, one again ..., every WORKING_DOTS_EVERY: about ten changes in 4 s)
        assert dots[:4] == [".", "..", "...", "."], dots
        assert 8 <= len(dots) <= 12, dots
        for a, b in zip(dots, dots[1:]):
            assert len(b) == len(a) % 3 + 1, dots
        # (the dots alone set: the panel laid out once or twice, not with every change)
        assert int(lua.eval("AGPS_LAYOUTS")) <= 3
        lua.execute("AGPS_BUSY = false")
        for _ in range(60):
            run(1 / 30)
            if N.route:
                break
        assert N.route
        run(1 / 30)  # (the next frame: the dots stop, the panel laid out again with the route)
        assert G.navWorking is None
        G.Update()
        assert "Working out the route" not in str(G.navText.GetText(G.navText))
    finally:
        lua.execute("AGPS_NS.Router.WarmUp = AGPS_WARMUP")
        N.Clear()


def test_the_message_changes_every_five_seconds_never_to_the_same_one(game):
    lua, ns = game
    N = ns.Nav
    N.Clear()
    N.SetStops(lua.eval(f"{{ {{ x = {BRILL[0] + 260}, y = {BRILL[1] + 40}, cont = 0 }} }}"), False, "red")
    random = N.Random
    lua.execute("AGPS_BUSY = true; AGPS_WARMUP = AGPS_NS.Router.WarmUp; "
                "AGPS_NS.Router.WarmUp = function(...) if AGPS_BUSY then return true end return AGPS_WARMUP(...) end")
    try:
        N.FUN = True
        # (the worst case: every roll the same, the Murloc line each time)
        lua.execute("AGPS_NS.Nav.Random = function(n) if n then return 1 end return 0.01 end")
        status = lua.eval("function() return AGPS_NS.Nav.Status(AGPS_NS.Geo.PlayerWorld()) end")
        shown = [str(status())]
        for _ in range(60):  # (30 s, a look every half second)
            lua.execute("AGPS_T = AGPS_T + 0.5")
            shown.append(str(status()))
        changes = [i for i in range(1, len(shown)) if shown[i] != shown[i - 1]]
        assert len(changes) == 6, shown  # (every 5 s)
        assert all(b - a == 10 for a, b in zip(changes, changes[1:])), changes
        assert changes[0] == 10
        # (a real roll too: never the same twice in a row, from a pool of more than one)
        lua.execute("math.randomseed(7); AGPS_NS.Nav.Random = math.random")
        last = None
        for _ in range(40):
            lua.execute("AGPS_T = AGPS_T + 5")
            t = str(status())
            assert t != last
            last = t
        # (N.FUN = false: the plain one, kept)
        N.FUN = False
        lua.execute("AGPS_T = AGPS_T + 5")
        t = str(status())
        lua.execute("AGPS_T = AGPS_T + 5")
        assert str(status()) == t
    finally:
        N.FUN = False
        N.Random = random
        lua.execute("AGPS_NS.Router.WarmUp = AGPS_WARMUP")
        N.Clear()


def _settle(lua, ns, budget_ms=10, frames=4000, on_frame=None):
    N, R = ns.Nav, ns.Router
    clock = lua.eval("function() return os.clock() * 1000 end")
    quiet = 0
    for f in range(frames):
        lua.execute("AGPS_T = AGPS_T + 0.05")
        N.Status(*BRILL, 0)
        if R.HasWork():
            R.Pump(clock() + budget_ms, clock)
        if on_frame:
            on_frame(f)
        if N.route and not R.HasWork() and not N.StretchesPending() and not N.Checking():
            quiet += 1
            if quiet > 40:
                return f
        else:
            quiet = 0
    raise AssertionError("the trip never settled")


def _trip(ns):
    N = ns.Nav
    r = N.route
    return [str(N.stops[i].name) for i in range(1, len(N.stops) + 1)], round(r.totalYards), round(r.totalRide)


def _game_trip(first_stop_first, look=None):
    """The trip worked out the game's way (its work in background slices), the roads built first."""
    lua, ns = _start()
    N, R = ns.Nav, ns.Router
    N.FIRST_STOP_FIRST = first_stop_first
    R.WARM, R.SYNC_WALKS = True, False
    try:
        N.SetStops(lua.eval("{ { x = 2000, y = 300, cont = 0 } }"), False, "red")
        _settle(lua, ns)  # (the roads built)
        N.Clear()
        N.SetStops(lua.eval(FIVE), True, "red")
        _settle(lua, ns, on_frame=look and (lambda f: look(ns, f)))
        return lua, ns, _trip(ns)
    finally:
        R.WARM, R.SYNC_WALKS = False, True


def test_a_trip_draws_the_way_to_its_first_stop_before_the_rest_and_ends_with_the_same_route():
    firsts, times = [], []

    def look(ns, f):
        N = ns.Nav
        r = N.route
        if r and not firsts:
            firsts.append((N.StretchesIn(r), N.StretchesPending(), f))
        if r and N.StretchesPending() and not times:
            times.append(str(N.Status(*BRILL, 0)).splitlines()[-1])

    lua, ns, got = _game_trip(True, look)
    N = ns.Nav
    assert firsts and firsts[0][0] == 0 and firsts[0][1], firsts  # (the first stop's way alone, the rest to come)
    assert times and times[0].endswith("..."), times  # (the times so far, "..." after them)
    assert N.StretchesIn(N.route) == N.PlannedStops() - 1
    assert not str(N.Status(*BRILL, 0)).endswith("...")
    # (the whole first route at once, as before: the same order and route in the end)
    _, _, want = _game_trip(False)
    assert got[0] == want[0]
    assert abs(got[1] - want[1]) <= max(20, want[1] * 0.01) and got[2] == want[2], (got, want)
