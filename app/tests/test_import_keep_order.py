"""An import routed in the order its stops are listed (asked for 1.3.9: "add option when importing a route to ignore
doing the fastest order and just route them in the order they are listed"): the Import and Share window's "Route in
the listed order" box, remembered in gps.importKeepOrder (Options > Routing too). Nav.keepOrder keeps that order on
the way: no reorder, a stop added later goes at the end, the rolling window of stops brings them in as listed."""
import pytest

pytest.importorskip("lupa.lua51")

from test_keep_data import SERIALIZE  # noqa: E402  (the saved file written as the game does)

BRILL = (2254.0, 293.0, 0)
# Around Brill, listed far, near, far, near: the fastest order from Brill takes the near ones first.
SPOTS = [(2754.0, 293.0, "A"), (2304.0, 343.0, "B"), (2774.0, 323.0, "C"), (2314.0, 253.0, "D")]


def _start(saved=None):
    from azerothgps.gameharness import start

    lua, ns = start(saved=saved)
    lua.execute(SERIALIZE)
    return lua, ns


def _stops(lua, spots=SPOTS):
    return lua.table(*[lua.table(x=x, y=y, cont=0, name=n) for x, y, n in spots])


def _names(ns):
    N = ns.Nav
    return [N.stops[i].name for i in range(1, len(N.stops) + 1)]


@pytest.fixture
def game():
    return _start()


def _notice(lua):
    f = lua.eval("AGPS_NS.Import.orderTold")  # (the one-time popup, while it's up)
    return f if f is not None and f._shown else None


def test_the_option_is_on_by_default_and_imports_keep_their_order(game):
    lua, ns = game
    assert ns.DEFAULTS.gps.importKeepOrder is True and ns.settings.gps.importKeepOrder is True
    assert ns.settings.gps.fastestOrder is True
    assert ns.Import.Apply(_stops(lua), False) == 4
    assert _names(ns) == ["A", "B", "C", "D"] and ns.Nav.keepOrder is True


def test_turned_off_imports_go_in_the_fastest_order_as_before(game):
    lua, ns = game
    ns.settings.gps.importKeepOrder = False
    assert ns.Import.Apply(_stops(lua), False) == 4
    got = _names(ns)
    assert sorted(got) == ["A", "B", "C", "D"] and got != ["A", "B", "C", "D"]  # (reordered)
    assert set(got[:2]) == {"B", "D"}  # (the near ones first)
    assert ns.Nav.keepOrder is False
    assert _notice(lua) is None  # (nothing to tell: the fastest order, as the player chose)


def test_a_test_builds_saved_off_is_turned_on_once():
    # (the option was off by default in a test build, saved so: on once for every profile, then the player's own)
    lua, ns = _start("AzerothGPSDB = { settings = { gps = { importKeepOrder = false } }, "
                     "profiles = { Alt = { gps = { importKeepOrder = false } } } }")
    assert ns.settings.gps.importKeepOrder is True and ns.db.profiles.Alt.gps.importKeepOrder is True
    assert ns.db.importOrderOn is True
    ns.settings.gps.importKeepOrder = False  # (turned off afterward: stays off)
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua.globals().AzerothGPSDB)
    lua2, ns2 = _start(text)
    assert ns2.settings.gps.importKeepOrder is False


def test_the_first_import_tells_once_with_the_box_glowing():
    lua, ns = _start()
    I, T = ns.Import, ns.Tutorial
    assert not ns.db.importOrderTold
    I.Toggle()
    win = lua.eval("AzerothGPSImport")
    win._scripts.OnShow(win)  # (the game runs it on Show)
    assert win._shown and win.keep._checked is True  # (on by default)
    win.edit._text = "/way Tirisfal Glades 61 52 E\n/way Tirisfal Glades 60 51 F"
    win.go._scripts.OnClick(win.go)
    assert _names(ns) == ["E", "F"]  # (the import done, in its order, the notice beside it)
    pop = _notice(lua)
    assert pop is not None and ns.db.importOrderTold is True
    assert "Route in the listed order" in pop.text._text and pop.yes._text == "Got It"
    assert pop.top in (-28, -30)  # (a popup with the title bar and the corner logo: ns.Ask's ns.Window)
    assert win._shown  # (kept open while it shows)
    # the tutorial's glow on the box while the notice shows
    glow = T.glow
    assert glow is not None and glow._shown and lua.eval("function(a, b) return a == b end")(T.pointed, win.keep)
    pop.yes._scripts.OnClick(pop.yes)  # Got It
    assert _notice(lua) is None and not glow._shown and T.pointed is None
    # never again: another import, the window or chat
    I.Apply(_stops(lua), False)
    I.AddWays("/way Tirisfal Glades 61 52 G")
    assert _notice(lua) is None
    # nor after a /reload
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua.globals().AzerothGPSDB)
    lua2, ns2 = _start(text)
    assert ns2.db.importOrderTold is True
    ns2.Import.Apply(_stops(lua2), False)
    assert _notice(lua2) is None and _names(ns2) == ["A", "B", "C", "D"]


def test_the_glow_goes_with_escape_or_the_window_closing():
    lua, ns = _start()
    I, T = ns.Import, ns.Tutorial
    I.Toggle()
    win = lua.eval("AzerothGPSImport")
    I.Apply(_stops(lua), False)
    pop = _notice(lua)
    assert pop is not None and T.glow._shown
    pop.Hide(pop)  # (Escape, the close button, the time out: the game runs its OnHide)
    pop._scripts.OnHide(pop)
    assert not T.glow._shown and T.pointed is None
    # the window closing takes it too
    ns.db.importOrderTold = False
    I.Apply(_stops(lua), False)
    assert _notice(lua) is not None and T.glow._shown
    win.Hide(win)
    win._scripts.OnHide(win)
    assert not T.glow._shown


def test_from_chat_it_tells_without_opening_the_window_and_not_after_a_choice():
    lua, ns = _start()
    I, T = ns.Import, ns.Tutorial
    I.AddWays("/way Tirisfal Glades 61 52 E /way Tirisfal Glades 60 51 F")
    assert _notice(lua) is not None  # (a /way list: told, the window not opened, nothing glows)
    win = lua.eval("AzerothGPSImport")
    assert (win is None or not win._shown) and not (T.glow is not None and T.glow._shown)
    # a player who ticked or unticked the box is never told
    lua2, ns2 = _start()
    ns2.Import.Toggle()
    w = lua2.eval("AzerothGPSImport")
    w.keep._checked = True
    w.keep._scripts.OnClick(w.keep)
    ns2.Import.Apply(_stops(lua2), False)
    assert _notice(lua2) is None and _names(ns2) == ["A", "B", "C", "D"]


def test_keep_order_import_routes_the_stops_as_listed(game):
    lua, ns = game
    N, I = ns.Nav, ns.Import
    ns.settings.gps.importKeepOrder = True
    assert I.Apply(_stops(lua), False) == 4
    assert _names(ns) == ["A", "B", "C", "D"] and N.keepOrder is True
    # /way lines (typed or pasted in chat) too, added after the route's stops in their order
    I.AddWays("/way Tirisfal Glades 61 52 E /way Tirisfal Glades 60 51 F")
    assert _names(ns) == ["A", "B", "C", "D", "E", "F"]


def test_a_keep_order_route_is_not_reshuffled_later(game):
    lua, ns = game
    N, I, G = ns.Nav, ns.Import, ns.GPS
    ns.settings.gps.importKeepOrder = True
    I.Apply(_stops(lua), False)
    ns.settings.gps.importKeepOrder = False  # (the box unticked afterward: this route keeps its order)
    px, py, cont = BRILL
    # the reorder look on the way (after the wait, moved)
    lua.execute("AGPS_T = (AGPS_T or 0) + 100")
    assert not N.MaybeReorder(px + 40, py + 40, cont)
    assert _names(ns) == ["A", "B", "C", "D"]
    # a route option changed (worked out again, the fastest order again before)
    N.OptionsChanged()
    assert _names(ns) == ["A", "B", "C", "D"]
    # a stop added by hand: at the end, with the fastest order on
    assert N.AddStop(lua.table(x=2264.0, y=300.0, cont=0, name="Near"), True)
    assert _names(ns) == ["A", "B", "C", "D", "Near"]
    # more /way lines and a pasted list added to it: after it, in their order
    I.Apply(_stops(lua, [(2260.0, 290.0, "P"), (2800.0, 290.0, "Q")]), True)
    assert _names(ns) == ["A", "B", "C", "D", "Near", "P", "Q"]
    # one reached (removed): the rest as they were, with the reorder look after it
    N.RemoveStop(1)
    lua.execute("AGPS_T = AGPS_T + 100")
    N.MaybeReorder(px - 60, py, cont)
    assert _names(ns) == ["B", "C", "D", "Near", "P", "Q"]
    # turning the fastest order on in Options doesn't reorder it either (Options.lua's check)
    assert N.keepOrder is True
    # a new route (not an import) is back to the fastest order
    N.SetStops(_stops(lua), True)
    assert N.keepOrder is False and _names(ns) != ["A", "B", "C", "D"]


def test_the_rolling_window_brings_stops_in_as_listed(game):
    lua, ns = game
    N, I = ns.Nav, ns.Import
    ns.settings.gps.importKeepOrder = True
    ns.settings.gps.stopsAhead = 8
    # 20 stops zigzagging round Brill, far and near in turn
    spots = [(2254.0 + (400 if i % 2 else 30) + i, 293.0 + 10 * i, f"S{i}") for i in range(20)]
    assert I.Apply(_stops(lua, spots), False) == 20
    want = [n for _, _, n in spots]
    assert _names(ns) == want
    assert N.PlannedStops() == 8
    for k in range(12):  # reached one by one: the next listed comes in each time
        N.RemoveStop(1)
        lua.execute("AGPS_T = (AGPS_T or 0) + 100")
        N.MaybeReorder(BRILL[0] + 5 * k, BRILL[1], 0)
        assert _names(ns) == want[k + 1:]
        assert N.PlannedStops() == min(8, len(want) - k - 1)


def test_the_box_and_the_route_survive_a_reload():
    lua, ns = _start()
    ns.Import.Toggle()
    win = lua.eval("AzerothGPSImport")
    win._scripts.OnShow(win)
    keep = win.keep
    assert keep._checked is True  # (on by default)
    keep._checked = True
    keep._scripts.OnClick(keep)
    assert ns.settings.gps.importKeepOrder is True
    ns.Import.Apply(_stops(lua), False)
    assert _names(ns) == ["A", "B", "C", "D"]
    # a /reload: the saved file written and loaded again
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua.globals().AzerothGPSDB)
    lua2, ns2 = _start(text)
    assert ns2.settings.gps.importKeepOrder is True
    assert _names(ns2) == ["A", "B", "C", "D"] and ns2.Nav.keepOrder is True
    ns2.Nav.AddStop(lua2.table(x=2264.0, y=300.0, cont=0, name="Near"), True)
    assert _names(ns2) == ["A", "B", "C", "D", "Near"]
    ns2.Import.Toggle()
    win2 = lua2.eval("AzerothGPSImport")
    win2._scripts.OnShow(win2)
    assert win2.keep._checked is True  # (the box as last left)
    # unticked: remembered off
    win2.keep._checked = False
    win2.keep._scripts.OnClick(win2.keep)
    assert ns2.settings.gps.importKeepOrder is False


# ---- Reaching the stops (reported in game: after the first stop the rest went in the fastest order) ----------------

# Six stops around Brill, listed so the fastest order from any of them is another: far, near, far, near...
TRIP = [(2754.0, 293.0, "A"), (2304.0, 343.0, "B"), (2774.0, 323.0, "C"), (2314.0, 253.0, "D"),
        (2600.0, 600.0, "E"), (2280.0, 300.0, "F")]


def _game_like(lua, ns):
    """The game's way: route work in the background, pumped as the frames go by."""
    ns.Router.WARM, ns.Router.SYNC_WALKS = True, False


def _walk_to(lua, ns, x, y, frames=30):
    import time

    G, R = ns.GPS, ns.Router
    for _ in range(frames):
        lua.execute(f"AGPS_T = (AGPS_T or 0) + 0.5; AGPS_POS = {{ {x}, {y}, 0 }}")
        G.Update()
        while R.HasWork():
            R.Pump(time.perf_counter() + 5, time.perf_counter)


def _fastest_differs(lua, ns, spots):
    # (the same stops set in the fastest order: another order, so keeping the listed one is what's tested)
    N = ns.Nav
    saved = [N.stops[i] for i in range(1, len(N.stops) + 1)]
    keep = N.keepOrder
    N.SetStops(_stops(lua, spots), True)
    fastest = _names(ns)
    N.SetStops(lua.table(*saved), False, None, keep)
    return fastest != [n for _, _, n in spots]


def test_reaching_stops_never_reorders_a_listed_trip(game):
    lua, ns = game
    N, I = ns.Nav, ns.Import
    assert I.Apply(_stops(lua, TRIP), False) == 6
    want = [n for _, _, n in TRIP]
    assert _names(ns) == want and _fastest_differs(lua, ns, TRIP[1:]) and _fastest_differs(lua, ns, TRIP[2:])
    _game_like(lua, ns)
    for k in range(3):  # stop 1, 2 and 3 reached in turn
        x, y, _ = TRIP[k]
        _walk_to(lua, ns, x - 1, y)
        assert _names(ns) == want[k + 1:], k
        # then walking off toward the far side (off the route: rerouted, reorder looks): still as listed
        _walk_to(lua, ns, x - 60, y + 80, frames=20)
        assert _names(ns) == want[k + 1:], k
    assert N.keepOrder is True and all(N.stops[i].listed for i in range(1, len(N.stops) + 1))
    # whoever asks for the fastest order now gets no reorder
    assert not N.OrderStops(*BRILL)
    assert _names(ns) == want[3:]


def test_a_listed_trip_keeps_its_order_after_a_reload_mid_trip(game):
    lua, ns = game
    N = ns.Nav
    ns.Import.Apply(_stops(lua, TRIP), False)
    _game_like(lua, ns)
    _walk_to(lua, ns, TRIP[0][0] - 1, TRIP[0][1])  # stop 1 reached
    assert _names(ns) == ["B", "C", "D", "E", "F"]
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua.globals().AzerothGPSDB)
    lua2, ns2 = _start(text)
    _game_like(lua2, ns2)
    assert _names(ns2) == ["B", "C", "D", "E", "F"] and ns2.Nav.keepOrder is True
    _walk_to(lua2, ns2, TRIP[1][0] - 1, TRIP[1][1])  # stop 2
    assert _names(ns2) == ["C", "D", "E", "F"]
    _walk_to(lua2, ns2, TRIP[2][0] - 1, TRIP[2][1])  # stop 3
    assert _names(ns2) == ["D", "E", "F"]
    # (a save from before the trip flag: its stops say so)
    text2 = text.replace('["keepOrder"] = true,', "")
    assert text2 != text
    lua3, ns3 = _start(text2)
    assert ns3.Nav.keepOrder is True and not ns3.Nav.OrderStops(*BRILL)
    assert _names(ns3) == ["B", "C", "D", "E", "F"]


def test_the_window_brings_in_the_next_listed_stop_as_each_is_reached(game):
    lua, ns = game
    N = ns.Nav
    ns.settings.gps.stopsAhead = 8
    spots = [(2254.0 + (400 if i % 2 else 40) + 3 * i, 293.0 + 12 * i, f"S{i}") for i in range(12)]
    ns.Import.Apply(_stops(lua, spots), False)
    want = [n for _, _, n in spots]
    _game_like(lua, ns)
    for k in range(4):
        planned = [N.stops[i].name for i in range(1, N.PlannedStops() + 1)]
        assert planned == want[k:k + 8], k  # (the window: the next 8 as listed)
        x, y, _ = spots[k]
        _walk_to(lua, ns, x - 1, y)
        assert _names(ns) == want[k + 1:], k
