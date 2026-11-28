"""Pause routing (asked 2026-11-16: "the ability for routing to be paused. This would make the direction arrow look like
it does on flight paths and the directions just say Routing is paused ... to save on compute when the player doesnt plan
to follow the route but they dont want to remove it just yet"): by hand (the Pause Routing quick button, /agps pause),
and on its own when the route isn't followed (Options > Performance, its own option; the low-end settings turn it on),
with a one-time question when the addon is working hard for a route not followed."""

import pytest

BRILL = (2260.0, 290.0)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_COMBAT = false; InCombatLockdown = function() return AGPS_COMBAT end")
    lua.execute("AGPS_REAL_PERF = AGPS_NS.PerfTotal")
    return lua, ns


@pytest.fixture(autouse=True)
def fresh(game):
    lua, ns = game
    st = ns.settings.gps
    N = ns.Nav
    N.Clear()
    N.SetPaused(False)
    N.ResetStutter()
    N.STUTTER_WATCH = False
    st.stutterPause = True
    lua.execute("GetFramerate = function() return 60 end; GetCVar = nil")
    lua.execute("AGPS_T = (AGPS_T or 1000) + 10")
    N.BackgroundCap()  # (read again: no cap)
    st.autoPauseRouting, st.autoPauseSeconds, st.autoPauseDeclined = False, 120, None
    N.autoPauseOffered = None
    N.ResetCompute()
    lua.execute("AGPS_COMBAT = false; AGPS_NS.PerfTotal = AGPS_REAL_PERF")
    box = ns.GPS.confirmBox
    if box:
        box.Hide(box)
    yield
    N.Clear()
    box = ns.GPS.confirmBox
    if box:
        box.Hide(box)


def _at(lua, x, y):
    lua.execute(f"AGPS_MAP = 1420; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0")


def _tick(lua, ns, n=1, secs=0.5):
    for _ in range(n):
        lua.execute(f"AGPS_T = (AGPS_T or 1000) + {secs}")
        ns.GPS.Update()


def _route(lua, ns, stop=(BRILL[0] + 260, BRILL[1] + 40)):
    _at(lua, *BRILL)
    ns.Nav.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = 0 }} }}"), False, "red")
    _tick(lua, ns, 4)
    assert ns.Nav.route, "no route"


def _status(lua, ns):
    return str(lua.eval("AGPS_NS.Nav.Status(AGPS_NS.Geo.PlayerWorld())"))


def _count_router(lua):
    lua.execute("""
      AGPS_ROUTER_CALLS = {}
      AGPS_ROUTER_REAL = {}
      for k, v in pairs(AGPS_NS.Router) do
        if type(v) == "function" then
          AGPS_ROUTER_REAL[k] = v
          AGPS_NS.Router[k] = function(...) AGPS_ROUTER_CALLS[k] = (AGPS_ROUTER_CALLS[k] or 0) + 1 return v(...) end
        end
      end
    """)


def _uncount_router(lua):
    lua.execute("for k, v in pairs(AGPS_ROUTER_REAL or {}) do AGPS_NS.Router[k] = v end AGPS_ROUTER_REAL = nil")
    return dict(lua.eval("AGPS_ROUTER_CALLS").items())


# (the route's work: the search, its pieces, smoothing, the checks along it; a few floor and cave lookups for the
# player's spot still run, paused or not)
ROUTE_WORK = {"Route", "Pieces", "Smooth", "NearestEdges", "BendPts", "HostileYards", "ZoneYards", "RedZones",
              "OnBridgeModel", "HostileAt", "ZoneAt"}


def _slot(ns, qid):
    for t in ns.GPS.QuickSlots().values():
        if str(t.id) == qid:
            return t
    return None


# -- by hand -----------------------------------------------------------------------------------------------------


def test_paused_nothing_is_worked_out_or_drawn_and_the_stops_are_kept(game):
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    _route(lua, ns)
    assert G.UpdateMinimapRoute(True) > 0

    def walk():
        _count_router(lua)
        try:
            for k in range(12):  # (walking about: off the route, a new spot each tick)
                _at(lua, BRILL[0] - 10 * k, BRILL[1] + 15 * k)
                _tick(lua, ns)
        finally:
            calls = _uncount_router(lua)
        return {k: v for k, v in calls.items() if k in ROUTE_WORK}

    assert walk().get("Route", 0) > 0  # (not paused: worked out again off it)
    _at(lua, *BRILL)
    N.TogglePaused()
    assert N.paused == "manual" and N.route is None and len(N.stops) == 1 and N.dest
    assert walk() == {}, "the route worked out while paused"
    assert N.route is None and N.Route(*lua.eval("{AGPS_NS.Geo.PlayerWorld()}").values()) is None
    assert G.UpdateMinimapRoute(True) == 0, "the minimap drew the last route while paused"


def test_paused_the_directions_say_so(game):
    lua, ns = game
    _route(lua, ns)
    ns.Nav.SetPaused(True, "manual")
    text = _status(lua, ns)
    assert "Routing is paused" in text and "Resume Routing" in text and "/agps pause" in text
    assert "Continue" not in text and "Turn" not in text


def test_paused_the_arrow_is_as_on_a_flight(game):
    lua, ns = game
    A = ns.Arrow
    assert A.frame, "the arrow wasn't made"
    _route(lua, ns)
    lua.execute("""
      AGPS_ROT = {}
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._kind == "Texture" then w.SetRotation = function(s, a) AGPS_ROT[s] = a end end
      end
    """)
    ns.Nav.SetPaused(True, "manual")
    A.frame._scripts.OnUpdate(A.frame, 1)
    blue = lua.eval("""(function()
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._kind == "Texture" and w._vc == "0.60,0.80,1.00" and AGPS_ROT[w] == 0 then return true end
      end
      return false
    end)()""")
    assert blue, "no arrow pointing up in the flight's blue"
    texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text and w._shown]
    assert any("Routing is paused" in t for t in texts)


def test_resume_works_the_route_out_again_from_where_you_are(game):
    lua, ns = game
    N = ns.Nav
    _route(lua, ns)
    N.SetPaused(True)
    _at(lua, BRILL[0] + 60, BRILL[1] - 30)
    _tick(lua, ns, 2)
    assert N.route is None
    N.TogglePaused()
    assert N.paused is None
    _tick(lua, ns, 4)
    r = N.route
    assert r
    assert abs(r.pts[1] - (BRILL[0] + 60)) < 40 and abs(r.pts[2] - (BRILL[1] - 30)) < 40  # (from here)
    assert "paused" not in _status(lua, ns)


def test_a_new_route_is_not_paused_and_clearing_ends_the_pause(game):
    lua, ns = game
    N = ns.Nav
    _route(lua, ns)
    N.SetPaused(True)
    _route(lua, ns, (BRILL[0] - 200, BRILL[1] + 100))
    assert N.paused is None
    N.SetPaused(True)
    N.Clear()
    assert N.paused is None
    assert not N.SetPaused(True)  # (no route: nothing to pause)
    assert N.paused is None


def test_paused_is_kept_over_a_reload(game):
    lua, ns = game
    N = ns.Nav
    _route(lua, ns)
    N.SetPaused(True, "manual")
    assert ns.CharDB().paused == "manual"
    N.paused = None
    N.Restore()
    assert N.paused == "manual" and len(N.stops) == 1
    N.SetPaused(False)
    assert ns.CharDB().paused is None
    N.Restore()
    assert N.paused is None


def test_the_slash_command_pauses_and_resumes(game):
    lua, ns = game
    N = ns.Nav
    lua.execute("AGPS_REAL_PRINT = AGPS_NS.Print; AGPS_SAID = {}; AGPS_NS.Print = function(s) AGPS_SAID[#AGPS_SAID + 1] = tostring(s) end")
    try:
        lua.eval("SlashCmdList.AZEROTHGPS")("pause")
        assert "No route to pause." in list(lua.eval("AGPS_SAID").values())
        _route(lua, ns)
        lua.eval("SlashCmdList.AZEROTHGPS")("pause")
        assert N.paused == "manual"
        lua.eval("SlashCmdList.AZEROTHGPS")("pause")
        assert N.paused is None
        said = list(lua.eval("AGPS_SAID").values())
        assert any("Routing paused" in s for s in said) and "Routing resumed." in said
    finally:
        lua.execute("AGPS_NS.Print = AGPS_REAL_PRINT")


def test_the_button_only_with_a_route_last_in_the_bottom_row_and_on_the_bar_while_paused(game):
    # ("showing in the map menu bottom right without expanding the map menu is a new pause/unpause button only when
    # the route is paused. Otherwise it's only shown in the map menu when expanded wherever the user places it,
    # defaults to bottom row all the way to the right")
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    G.LayoutQuick()
    assert _slot(ns, "pauseRoute") is None  # (no route)
    _route(lua, ns)
    _tick(lua, ns, 2)  # (G.WatchQuickOn: laid out again)
    t = _slot(ns, "pauseRoute")
    assert t and str(G.QuickPlace("pauseRoute")) == "menuRight" and str(t.where) == "menuRight"
    row = [str(s.id) for s in G.QuickSlots().values() if str(s.where) == "menuRight" and not s.tail]
    assert row[-1] == "pauseRoute", row  # (the bottom row, all the way to the right: but for Import and Share and the
    # companions' buttons, the row's end since 1.4.2, Kooki3z 2026-11-27)
    assert str(t.labelNow()) == "Pause Routing"
    if G.mapMenu:
        G.mapMenu.Hide(G.mapMenu)
    t.action()
    assert N.paused == "manual"
    _tick(lua, ns, 2)
    assert str(t.where) == "barRight" and t.button._shown  # (on the bar, the menu shut)
    assert str(t.labelNow()) == "Resume Routing"
    t.action()
    assert N.paused is None
    _tick(lua, ns, 2)
    assert str(t.where) == "menuRight"
    assert str(G.QuickPlace("pauseRoute")) == "menuRight"  # (its own place unchanged)


# -- on its own, the route not followed --------------------------------------------------------------------------


def _wander_off(lua, ns, steps=40, step=25):
    """Walk away from the stop (west of Brill, it east): the time to it grows; ticks of 1 s."""
    for k in range(1, steps + 1):
        _at(lua, BRILL[0] - step * k, BRILL[1])
        _tick(lua, ns, 1, secs=1)
        if ns.Nav.paused or ns.GPS.confirmBox and ns.GPS.confirmBox._shown:
            return k
    return None


def test_auto_pause_with_low_performance_off(game):
    # ("they can use this with out it")
    lua, ns = game
    st, N = ns.settings.gps, ns.Nav
    O = ns.Options
    O.PerfDefaults()
    assert not O.IsLowEnd()
    st.autoPauseRouting, st.autoPauseSeconds = True, 30
    _route(lua, ns)
    for _ in range(8):  # (following it, standing: not paused)
        _tick(lua, ns, 1, secs=1)
    assert N.paused is None
    assert _wander_off(lua, ns), "never paused walking away"
    assert N.paused == "auto"
    text = _status(lua, ns)
    assert "you're not following the route" in text


def test_auto_pause_waits_out_the_hold(game):
    lua, ns = game
    st, N = ns.settings.gps, ns.Nav
    st.autoPauseRouting, st.autoPauseSeconds = True, 30
    _route(lua, ns)
    lua.execute("AGPS_SECS = 0")
    N.pauseWatch = None
    r = lua.eval("{ walkYards = 0, rideSeconds = 0 }")
    lua.execute("AGPS_NS.Nav.Speeds = (function(real) AGPS_REAL_SPEEDS = real return function() return 7, 7, 14, false end end)(AGPS_NS.Nav.Speeds)")
    try:
        N.WatchFollowing(r, 0)  # (the best: 0 s)
        r.walkYards = 7 * 40  # (40 s further)
        for k in range(4):
            lua.execute("AGPS_T = AGPS_T + 1")
            N.WatchFollowing(r, 0)
            assert N.paused is None, f"paused after {k} s, before the {N.AUTO_PAUSE_HOLD} s hold"
        lua.execute("AGPS_T = AGPS_T + 2")
        N.WatchFollowing(r, 0)
        assert N.paused == "auto"
        # back on it within the hold: not paused
        N.SetPaused(False)
        N.pauseWatch = None
        r.walkYards = 0
        N.WatchFollowing(r, 0)
        r.walkYards = 7 * 40
        lua.execute("AGPS_T = AGPS_T + 3")
        N.WatchFollowing(r, 0)
        r.walkYards = 7 * 10
        lua.execute("AGPS_T = AGPS_T + 3")
        N.WatchFollowing(r, 0)
        lua.execute("AGPS_T = AGPS_T + 3")
        N.WatchFollowing(r, 0)
        assert N.paused is None
    finally:
        lua.execute("AGPS_NS.Nav.Speeds = AGPS_REAL_SPEEDS")


def test_auto_pause_off_by_default_and_not_on_a_flight_or_while_worked_out(game):
    lua, ns = game
    st, N = ns.settings.gps, ns.Nav
    assert lua.eval("AGPS_NS.DEFAULTS.gps.autoPauseRouting") is False
    assert lua.eval("AGPS_NS.DEFAULTS.gps.autoPauseSeconds") == 120
    lua.execute("AGPS_NS.Nav.Speeds = (function(real) AGPS_REAL_SPEEDS = real return function() return 7, 7, 14, false end end)(AGPS_NS.Nav.Speeds)")
    try:
        _route(lua, ns)
        for kind in ("flying", "pending"):
            st.autoPauseRouting, st.autoPauseSeconds = True, 30
            N.pauseWatch = None
            r = lua.eval("{ walkYards = 0, rideSeconds = 0 }")
            N.WatchFollowing(r, 0)
            r.walkYards = 7 * 400
            r[kind] = lua.eval("{ kind = 'taxi' }") if kind == "flying" else True
            for _ in range(10):
                lua.execute("AGPS_T = AGPS_T + 1")
                N.WatchFollowing(r, 0)
            assert N.paused is None, kind
        st.autoPauseRouting = False  # (off: never on its own; no question either, the work low)
        N.pauseWatch = None
        r = lua.eval("{ walkYards = 0, rideSeconds = 0 }")
        N.WatchFollowing(r, 0)
        r.walkYards = 7 * 400
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 1")
            N.WatchFollowing(r, 0)
        assert N.paused is None and not N.autoPauseOffered
    finally:
        lua.execute("AGPS_NS.Nav.Speeds = AGPS_REAL_SPEEDS")


def test_the_low_end_settings_turn_it_on_and_the_defaults_dont_turn_it_off(game):
    # ("enabling low performance mode would automatically enable this setting")
    lua, ns = game
    st, O = ns.settings.gps, ns.Options
    O.PerfDefaults()
    st.autoPauseRouting = False
    O.UseLowEnd()
    assert O.IsLowEnd() and st.autoPauseRouting is True
    O.PerfDefaults()
    assert not O.IsLowEnd() and st.autoPauseRouting is True
    st.autoPauseRouting = False
    assert not N_auto(ns)


def N_auto(ns):
    return bool(ns.Nav.AutoPauseOn())


# -- the question: a lot of work for a route not followed --------------------------------------------------------


def _busy(lua, on=True):
    # (the addon's measured work: 40 ms a second, or 1)
    rate = 40 if on else 1
    lua.execute(f"AGPS_NS.PerfTotal = function() return GetTime() * {rate} end")


def _not_following(lua, ns, n=12):
    """The route set and followed for over a minute (the work measured), then walked away from: True once asked."""
    N, st = ns.Nav, ns.settings.gps
    lua.execute("AGPS_NS.Nav.Speeds = (function(real) AGPS_REAL_SPEEDS = real return function() return 7, 7, 14, false end end)(AGPS_NS.Nav.Speeds)")
    try:
        st.autoPauseSeconds = 30
        N.pauseWatch = None
        r = lua.eval("{ walkYards = 0, rideSeconds = 0 }")
        for _ in range(14):  # (70 s following it)
            lua.execute("AGPS_T = AGPS_T + 5")
            N.WatchFollowing(r, 0)
        r.walkYards = 7 * 60
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 1")
            N.WatchFollowing(r, 0)
    finally:
        lua.execute("AGPS_NS.Nav.Speeds = AGPS_REAL_SPEEDS")
    box = ns.GPS.confirmBox
    return bool(box and box._shown and "Pause routing automatically" in str(box.text._text))


def _answer(ns, yes):
    box = ns.GPS.confirmBox
    b = box.yes if yes else box.no
    b._scripts.OnClick(b, "LeftButton")


def test_asked_when_the_work_is_high_and_the_route_not_followed(game):
    lua, ns = game
    _route(lua, ns)
    _busy(lua)
    assert _not_following(lua, ns)
    assert "Pause routing automatically" in str(ns.GPS.confirmBox.text._text)


def test_not_asked_when_only_one_is_true(game):
    lua, ns = game
    N = ns.Nav
    _route(lua, ns)
    _busy(lua, False)  # (not followed, the work low)
    assert not _not_following(lua, ns) and not N.autoPauseOffered
    _busy(lua)  # (the work high, followed)
    N.ResetCompute()
    lua.execute("AGPS_NS.Nav.Speeds = (function(real) AGPS_REAL_SPEEDS = real return function() return 7, 7, 14, false end end)(AGPS_NS.Nav.Speeds)")
    try:
        N.pauseWatch = None
        r = lua.eval("{ walkYards = 7 * 200, rideSeconds = 0 }")
        for k in range(40):
            r.walkYards = 7 * (200 - 4 * k)  # (getting closer)
            lua.execute("AGPS_T = AGPS_T + 5")
            N.WatchFollowing(r, 0)
    finally:
        lua.execute("AGPS_NS.Nav.Speeds = AGPS_REAL_SPEEDS")
    assert not N.autoPauseOffered
    box = ns.GPS.confirmBox
    assert not (box and box._shown)


def test_not_asked_in_combat_but_after_it(game):
    lua, ns = game
    N = ns.Nav
    _route(lua, ns)
    _busy(lua)
    lua.execute("AGPS_COMBAT = true")
    assert not _not_following(lua, ns) and not N.autoPauseOffered
    lua.execute("AGPS_COMBAT = false")
    for _ in range(2):  # (still not followed)
        lua.execute("AGPS_T = AGPS_T + 1")
        r = lua.eval("{ walkYards = 7 * 60, rideSeconds = 0 }")
        N.WatchFollowing(r, 0)
    box = ns.GPS.confirmBox
    assert N.autoPauseOffered and box and box._shown


def test_not_asked_over_another_question(game):
    lua, ns = game
    N = ns.Nav
    _route(lua, ns)
    _busy(lua)
    ns.GPS.Confirm("Something else?", lua.eval("function() end"))
    assert not _not_following(lua, ns) and not N.autoPauseOffered


def test_yes_turns_only_the_option_on_and_pauses(game):
    lua, ns = game
    st, N, O = ns.settings.gps, ns.Nav, ns.Options
    O.PerfDefaults()
    before = {k: st[k] for k in O.PERF_KEYS.values()}
    _route(lua, ns)
    _busy(lua)
    assert _not_following(lua, ns)
    _answer(ns, True)
    assert st.autoPauseRouting is True and N.paused == "auto"
    assert {k: st[k] for k in O.PERF_KEYS.values()} == before and not O.IsLowEnd()  # (the rest as it was)


def test_no_is_remembered_and_asked_once_a_session(game):
    lua, ns = game
    st, N = ns.settings.gps, ns.Nav
    _route(lua, ns)
    _busy(lua)
    assert _not_following(lua, ns)
    _answer(ns, False)
    assert st.autoPauseDeclined is True and st.autoPauseRouting is False and N.paused is None
    N.autoPauseOffered = None  # (a new session)
    N.ResetCompute()
    assert not _not_following(lua, ns)
    # closed without an answer (Escape): not remembered, but not asked again this session
    st.autoPauseDeclined = None
    N.ResetCompute()
    assert _not_following(lua, ns)
    box = ns.GPS.confirmBox
    box.Hide(box)
    assert not st.autoPauseDeclined
    N.ResetCompute()
    assert not _not_following(lua, ns)


def test_a_no_is_forgotten_when_the_options_are_reset(game):
    # ("No is remembered (never asked again unless the settings are reset)")
    lua, ns = game
    ns.settings.gps.autoPauseDeclined = True
    ns.Options.ResetToDefaults()
    st = ns.settings.gps
    assert not st.autoPauseDeclined and st.autoPauseRouting is False
    _route(lua, ns)
    _busy(lua)
    assert _not_following(lua, ns)


# -- stutter from routing (asked 2026-11-18) -------------------------------------------------------------------------
# (Kooki3z's 1.3.8 perf capture, 17 minutes on a three-stop trip across continents: "route calculation", in the frame,
# 42 times, every one a slow frame, 350 ms on average and 571 at worst; "terrain search" slices over 16 ms 52 times.
# Nothing noticed: the auto-pause is about a route not followed, off by default, and skips a route still searched;
# ComputeHigh averages a minute's work for it. Now the routing work in a frame is watched: three slow route frames in
# a minute cut routing back to the first stop, three more pause it and say so; a quiet minute and a half: full again.)
TRIP = "{ { x = 2560, y = 330, cont = 0 }, { x = 1800, y = 1000, cont = 0 }, { x = 2800, y = -400, cont = 0 } }"


def _slow(lua, ns, ms=40.0, secs=10.0):
    """A frame `secs` after the last with `ms` of routing work in it (N.RouteWork, as N.Route and the pump report)."""
    ns.Nav.STUTTER_WATCH = True
    lua.execute(f"AGPS_T = (AGPS_T or 1000) + {secs}")
    ns.Nav.RouteWork(ms)


def _trip(lua, ns):
    ns.Nav.STUTTER_WATCH = False  # (worked out at once here, as the tests do: not watched)
    _at(lua, *BRILL)
    ns.Nav.SetStops(lua.eval(TRIP), False, "red")
    _tick(lua, ns, 4)
    r = ns.Nav.route
    assert r and r.stretches[2] and r.stretches[3], "no trip"
    return r


def test_one_slow_frame_now_and_then_cuts_nothing_back(game):
    lua, ns = game
    N = ns.Nav
    _trip(lua, ns)
    for _ in range(6):  # (one a minute and more apart: a hitch now and then, not a stutter)
        _slow(lua, ns, 200.0, 61.0)
        assert not N.degraded and not N.paused
    _slow(lua, ns, 10.0)  # (and work under STUTTER_MS: not a slow frame at all)
    _slow(lua, ns, 10.0)
    _slow(lua, ns, 10.0)
    assert not N.degraded


def test_routing_work_in_one_frame_adds_up(game):
    lua, ns = game
    N = ns.Nav
    _trip(lua, ns)
    N.STUTTER_WATCH = True
    for _ in range(3):  # (each frame's work in pieces under STUTTER_MS: N.Route, the pump's slice)
        lua.execute("AGPS_T = AGPS_T + 10")
        for _ in range(3):
            N.RouteWork(10.0)
    assert N.degraded


def test_stutter_cuts_routing_back_to_the_first_stop_then_pauses_and_says_why(game):
    lua, ns = game
    N = ns.Nav
    said = lua.eval("{}")
    old_print = ns.Print
    ns.Print = lua.eval("function(t) return function(msg) t[#t + 1] = msg end end")(said)
    try:
        r = _trip(lua, ns)
        later2, later3 = r.stretches[2], r.stretches[3]
        for _ in range(3):  # (the capture's rate: a slow route frame every 10 s)
            _slow(lua, ns)
        assert N.degraded and not N.paused
        # cut back: a search between stops finishing redoes nothing after the first stop; the way to it still is
        N.SearchDone(True)
        N.STUTTER_WATCH = False  # (the tests' routes, worked out at once: not counted)
        _tick(lua, ns, 3, 3.0)
        r = N.route
        same = lua.eval("rawequal")
        assert r and same(r.stretches[2], later2) and same(r.stretches[3], later3)
        assert r.legs and r.legs[1].x1 is not None
        # still stuttering after the grace: paused, said in chat and in the directions
        for _ in range(3):
            _slow(lua, ns)
        assert N.paused == "perf" and not N.degraded
        msgs = [str(said[i]) for i in range(1, len(said) + 1)]
        assert any("making your game stutter" in m and "/agps pause" in m for m in msgs), msgs
        assert "making your game stutter" in _status(lua, ns)
        assert len(N.stops) == 3  # (the stops kept)
        N.TogglePaused()  # (resumed by the player: full routing, the watch started over)
        assert not N.paused and not N.degraded
    finally:
        ns.Print = old_print


def test_quiet_frames_bring_full_routing_back(game):
    lua, ns = game
    N = ns.Nav
    r = _trip(lua, ns)
    for _ in range(3):
        _slow(lua, ns)
    assert N.degraded
    later2 = r.stretches[2]
    for _ in range(8):  # (quiet for a while, not long enough: still cut back)
        _slow(lua, ns, 1.0)
    assert N.degraded
    for _ in range(4):  # (past STUTTER_RECOVER without a slow frame: full routing again, quietly)
        _slow(lua, ns, 1.0)
    assert not N.degraded and not N.paused
    N.STUTTER_WATCH = False
    _tick(lua, ns, 6)
    assert not lua.eval("rawequal")(N.route.stretches[2], later2)  # (the stretches after the first stop worked out again)
    # (and a single slow frame after it doesn't cut it back again)
    _slow(lua, ns)
    assert not N.degraded


def test_a_slow_reroute_in_the_frame_is_seen_by_the_watch(game):
    # (N.Route timed itself: three in a minute, each over STUTTER_MS by the clock, cut it back)
    lua, ns = game
    N = ns.Nav
    _trip(lua, ns)
    N.STUTTER_WATCH = True
    lua.execute("AGPS_DPS = debugprofilestop; local t = 0; debugprofilestop = function() t = t + 20 return t end")
    try:
        for k in range(3):
            lua.execute("AGPS_T = AGPS_T + 10")
            N.Route(BRILL[0] + k, BRILL[1], 0)
            N.Route(BRILL[0] + k, BRILL[1], 0)  # (40 ms in the frame by this clock)
        assert N.degraded
    finally:
        lua.execute("debugprofilestop = AGPS_DPS")


# (asked 2026-11-18, Kooki3z: routing paused "due to stutter" with the game's window not focused. In the background the
# client runs at its background frame cap (maxFPSBk) at a lower priority: the clock around a few milliseconds of our
# work reads tens. Frames at that cap don't count, nor the first seconds back from it; and the watch has its option.)
def _background(lua, ns, fps, cap=8, on="1", reread=True):
    """The client's frame rate now and its background frame cap (the CVars useMaxFPSBk / maxFPSBk)."""
    lua.execute(f'GetFramerate = function() return {fps} end; GetCVar = function(k) '
                f'if k == "maxFPSBk" then return "{cap}" elseif k == "useMaxFPSBk" then return "{on}" end end')
    if reread:
        lua.execute(f"AGPS_T = AGPS_T + {ns.Nav.BG_CAP_EVERY}")  # (the cap read again)
    ns.Nav.BackgroundCap()


def test_long_frames_in_the_background_never_cut_routing_back(game):
    lua, ns = game
    N = ns.Nav
    _trip(lua, ns)
    _background(lua, ns, 8)  # (unfocused: held at the 8 fps cap)
    for _ in range(10):  # (its slow clock round a little routing work, frame after frame)
        _slow(lua, ns, 60.0, 2.0)
    assert not N.degraded and not N.paused
    _background(lua, ns, 100, reread=False)  # (focused again: the first seconds back don't count)
    _slow(lua, ns, 60.0, 1.0)
    _slow(lua, ns, 60.0, 1.0)
    _slow(lua, ns, 60.0, 1.0)
    assert not N.degraded
    for _ in range(3):  # (past them, routing's own spikes count again)
        _slow(lua, ns)
    assert N.degraded


def test_a_low_frame_rate_away_from_the_cap_is_still_watched(game):
    # (routing's own stutter at a low frame rate, the cap off or the rate far from it: still counted)
    lua, ns = game
    N = ns.Nav
    _trip(lua, ns)
    _background(lua, ns, 9, cap=30)
    for _ in range(3):
        _slow(lua, ns)
    assert N.degraded
    N.ResetStutter()
    _background(lua, ns, 8, cap=8, on="0")  # (the background cap turned off: these frames are the game's own)
    for _ in range(3):
        _slow(lua, ns)
    assert N.degraded


def test_the_option_off_never_cuts_back_or_pauses(game):
    lua, ns = game
    N = ns.Nav
    st = ns.settings.gps
    _trip(lua, ns)
    for _ in range(3):
        _slow(lua, ns)
    assert N.degraded
    st.stutterPause = False  # (turned off while cut back: full routing again)
    _slow(lua, ns)
    assert not N.degraded
    for _ in range(12):
        _slow(lua, ns, 500.0)
    assert not N.degraded and not N.paused



def test_resuming_starts_the_count_over_and_its_re_plan_isnt_stutter(game):
    # (asked 2026-11-18, Kooki3z: "keeps pausing" on a trip through Dun Algaz, the chat line over and over. Resumed, the
    # trip worked out again was read as stutter and paused it again. Now a resume, a new trip or a pause starts the
    # count over, its first STUTTER_RESUME_GRACE seconds not counted; the chat line at most every STUTTER_SAY_EVERY.)
    lua, ns = game
    N = ns.Nav
    said = lua.eval("{}")
    old_print = ns.Print
    ns.Print = lua.eval("function(t) return function(msg) t[#t + 1] = msg end end")(said)
    try:
        _trip(lua, ns)
        for _ in range(6):
            _slow(lua, ns)
        assert N.paused == "perf"
        N.TogglePaused()
        assert not N.paused
        for _ in range(4):  # (the re-plan's frames just after the resume)
            _slow(lua, ns, 300.0, 1.5)
        assert not N.degraded and not N.paused
        for _ in range(6):  # (stutter for real again, past the grace: paused again, the chat not told twice so soon)
            _slow(lua, ns)
        assert N.paused == "perf"
        msgs = [str(said[i]) for i in range(1, len(said) + 1) if "making your game stutter" in str(said[i])]
        assert len(msgs) <= 1, msgs
        assert "making your game stutter" in _status(lua, ns)
    finally:
        ns.Print = old_print
        N.SetPaused(False)  # (the quick button's glow is refreshed on the way out)
        _tick(lua, ns, 2)
# -- the glow (1.3.9, asked 2026-11-18: "when the route gets paused, on the GPS menu make the button glow") -----------


def _glowing(lua, ns):
    _tick(lua, ns, 2)  # (G.WatchQuickOn: laid out and refreshed again)
    t = _slot(ns, "pauseRoute")
    on = bool(ns.GPS.GlowingIds()["pauseRoute"])
    shown = bool(t and t.glow and t.glow._shown and t.button._shown)
    assert on == shown, (on, shown)
    return shown


def test_the_pause_button_glows_while_paused_by_hand_and_stops_on_resume(game):
    lua, ns = game
    N = ns.Nav
    _route(lua, ns)
    assert not _glowing(lua, ns)
    N.TogglePaused()
    assert N.paused == "manual" and _glowing(lua, ns)
    t = _slot(ns, "pauseRoute")
    assert str(t.where) == "barRight"  # (on the bar, seen without opening the menu)
    N.TogglePaused()
    assert N.paused is None and not _glowing(lua, ns)
    # (cleared while paused: no button, no glow, nothing broken)
    N.SetPaused(True, "manual")
    N.Clear()
    _tick(lua, ns, 2)
    assert _slot(ns, "pauseRoute") is None and not ns.GPS.GlowingIds()["pauseRoute"]


def test_the_pause_button_glows_when_the_auto_pause_pauses(game):
    lua, ns = game
    st, N = ns.settings.gps, ns.Nav
    st.autoPauseRouting, st.autoPauseSeconds = True, 30
    _route(lua, ns)
    assert _wander_off(lua, ns) and N.paused == "auto"
    assert _glowing(lua, ns)
    N.SetPaused(False)
    assert not _glowing(lua, ns)


def test_the_pause_button_glows_when_the_stutter_watch_pauses(game):
    lua, ns = game
    N = ns.Nav
    _trip(lua, ns)
    for _ in range(6):
        _slow(lua, ns)
    assert N.paused == "perf"
    N.STUTTER_WATCH = False
    assert _glowing(lua, ns)
    N.TogglePaused()
    assert not N.paused and not _glowing(lua, ns)


def test_the_glowing_pause_button_hidden_breaks_nothing(game):
    lua, ns = game
    N, G, st = ns.Nav, ns.GPS, ns.settings.gps
    old = st.quick
    try:
        st.quick = lua.eval("{ pauseRoute = 'hidden' }")
        G.LayoutQuick()
        _route(lua, ns)
        N.SetPaused(True, "manual")
        _tick(lua, ns, 2)
        G.RefreshQuick()
        assert N.paused == "manual"
    finally:
        st.quick = old
        N.SetPaused(False)
        G.LayoutQuick()


def test_the_minimap_resume_option_is_kept_over_a_reload():
    # (1.3.9: "Show a Resume button on the minimap square while paused", on by default; turned off, it stays off)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    from test_keep_data import SERIALIZE  # (the saved file written as the game does)

    def start_(saved=None):
        lua, ns = start(saved=saved)
        lua.execute(SERIALIZE)
        return lua, ns
    lua, ns = start_()
    assert ns.settings.gps.replaceMinimapResume is True
    ns.settings.gps.replaceMinimapResume = False
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua.globals().AzerothGPSDB)
    lua2, ns2 = start_(text)
    assert ns2.settings.gps.replaceMinimapResume is False
    ns2.settings.gps.replaceMinimapResume = True
    lua2.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua2.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua2.globals().AzerothGPSDB)
    _, ns3 = start_(text)
    assert ns3.settings.gps.replaceMinimapResume is True



def test_a_route_cleared_while_paused_leaves_no_glow_on_the_next(game):
    # (paused by the stutter watch, the route cleared, then a new one: its Pause button was still lit, though routing
    # wasn't paused; found merging #634 with the watch's tests, 2026-11-18. N.Clear and a new route lay them out again)
    lua, ns = game
    N = ns.Nav
    _trip(lua, ns)
    for _ in range(6):
        _slow(lua, ns)
    assert N.paused == "perf"
    N.Clear()
    N.STUTTER_WATCH = False
    _route(lua, ns)
    assert not N.paused and not _glowing(lua, ns)
    N.SetPaused(True, "manual")  # (and a different route set while paused: not paused, not lit)
    _at(lua, *BRILL)
    N.SetStops(lua.eval("{ { x = 2400, y = 100, cont = 0 } }"), False, "red")
    assert not N.paused and not _glowing(lua, ns)
