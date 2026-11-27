"""A route's jumps and swims with a controller (item 96, 1.4.1; Pad.lua's picking, Nav.UndoAvoid; the whole addon).

Kooki3z for 1.4.1: "controller support for the right-click avoids on jumps and swims ... cycling through the route's
jumps/swims ... a highlight on the selected one with its tooltip, and a button (X or Y, matching the existing controller
hints) for the same action as right-click: avoid spell jumps / avoid jumps / avoid swimming for this stop, and undo.
Controller hint text on screen; 10 locales; works in the GPS map and world-map mode."

LB + A picks the route's jumps and swims one at a time: the view's middle on the one picked, a ring round it and its
tooltip (the avoid's line by the pad's button); the D-pad (or LB + A again) the next and the one before; X asks the
right-click's question there, A takes it; Y takes the last avoid back; B is done. The legend and box name these.
The pad is test_controller.py's fake; the jump is test_jump_lines.py's Barrens cliff, the swim test_swim_routes.py's lake.
"""

import pytest

from test_controller import PAD_STUBS, _fake_buttons, _hold, _plain, _press
from test_jump_lines import _route_kinds, jump_trip  # noqa: F401 (the fixture)
from test_map_redraw import game  # noqa: F401
from test_swim_routes import ISLE, SHORE, trip  # noqa: F401 (the fixture)
from test_world_map_host import SETUP as WM_SETUP


@pytest.fixture
def pad(game):  # noqa: F811
    lua, ns = game
    lua.execute(PAD_STUBS)
    _fake_buttons(lua)
    ns.db.padOffered = True
    ns.settings.gps.padControl = True
    ns.Pad.used = True
    # (the tooltip's lines, recorded: the mock's AddLine keeps none)
    lua.execute("""
      AGPS_TIP = {}
      GameTooltip.SetText = function(s, t) s._text = t AGPS_TIP = { t } end
      GameTooltip.AddLine = function(s, t) AGPS_TIP[#AGPS_TIP + 1] = t end
    """)
    try:
        yield lua, ns
    finally:
        lua.execute("AGPS_LOCK = false")
        ns.Pad.EndPick()
        ns.Pad.Clear()
        ns.Pad.used = False
        lua.execute("AGPS_PAD.enabled = false")


def _pair(lua, mod, key):
    """`mod` held, `key` pressed and let go (a pair: LB + A)."""
    _hold(lua, mod)
    _hold(lua, key)
    _press(lua, key)
    _press(lua, key, False)
    _hold(lua, key, False)
    _hold(lua, mod, False)


def _tap(lua, key):
    _hold(lua, key)
    _press(lua, key)
    _press(lua, key, False)
    _hold(lua, key, False)


def _tip(lua):
    return [_plain(t) for t in lua.eval("AGPS_TIP").values()]


def _same(lua, a, b):
    return lua.eval("rawequal")(a, b)


def _hints(lua, ns):
    return [(t[1], str(t[2])) for t in ns.Pad.HintTargets().values()]


def _jumping(ns, r):
    if ns.Router.KIND_DROP not in _route_kinds(r):
        pytest.skip("the whole addon's route here doesn't jump the test cliff")


def test_the_route_s_jumps_are_picked_avoided_and_the_avoid_undone_with_the_pad(game, jump_trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pad
    r = jump_trip()
    _jumping(ns, r)
    G.Update()
    assert P.Apply()
    assert str(P.Key("avoids")) == "PADLSHOULDER+PAD1" and _plain(P.ActionLabel("avoids")) == "LB + A"
    # (on the map's box with its other controls)
    assert any("LB + A: Jumps and Swims" in _plain(l) for l in P.BoxLines(False).values())
    items = P.AvoidItems()
    assert len(items) >= 1 and str(items[1].kind) == "jump"
    it = items[1]
    _pair(lua, "PADLSHOULDER", "PAD1")
    assert P.Picking() and P.pick.at == 1
    # (the view's middle on it)
    G.Update()
    vx, vy, vc = G.PadView()[0], G.PadView()[1], G.PadView()[2]
    assert vc == it.cont and abs(vx - it.x) < 0.5 and abs(vy - it.y) < 0.5
    # (its ring, and its tooltip as the mouse's hover shows it, the avoid by the pad's X)
    P.Tick(0.2)
    assert P.pickMark._shown and _same(lua, lua.eval("GameTooltip")._owner, P.pickMark)
    tip = _tip(lua)
    assert tip[0].startswith("Spell jump") and "1/" in tip[0], tip
    assert tip[-1] == "X: avoid spell jumps for this stop", tip
    # (the on-screen hint: picking's own controls; X's icon over the ring)
    legend = _plain(P.LegendText(False))
    assert "D-pad: Next" in legend and "X: Avoid" in legend and "Y: Undo" in legend and "B: Done" in legend, legend
    box = [_plain(l) for l in P.BoxLines(False).values()]
    assert box[:4] == ["D-pad: Next/Previous", "X: Avoid", "Y: Undo", "B: Done"], box
    assert any(_same(lua, b, P.pickMark) and i == "remove" for b, i in _hints(lua, ns))
    # X: the right-click's question there; A takes it
    _tap(lua, "PAD3")
    ask = G.jumpAsk
    assert ask._shown and str(ask["items"][1].text) == "Avoid Spell Jumps"
    assert any(_same(lua, b, ask.buttons[1]) and i in ("yes", "select") for b, i in _hints(lua, ns))
    _tap(lua, "PAD1")
    assert not ask._shown and N.stops[1].avoidJumps == "spell"
    jump_trip.settle()
    assert ns.Router.KIND_DROP not in _route_kinds(N.route)
    P.Tick(0.2)
    assert P.PickItem() is None and not P.pickMark._shown  # (gone from the route: none picked)
    assert P.Picking()
    # Y: the avoid taken back, the route jumps again
    _tap(lua, "PAD4")
    assert N.stops[1].avoidJumps is None
    jump_trip.settle()
    assert ns.Router.KIND_DROP in _route_kinds(N.route)
    _tap(lua, "PADDRIGHT")  # (the next: the one nearest the last picked)
    assert P.PickItem() is not None and str(P.PickItem().kind) == "jump"
    # B: done, the map's own controls again
    _tap(lua, "PAD2")
    assert not P.Picking() and not P.pickMark._shown
    assert "Set Stop" in _plain(P.LegendText(False))


def test_b_lets_the_question_go_and_a_with_none_asks_it(game, jump_trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pad
    _jumping(ns, jump_trip())
    G.Update()
    assert P.Apply()
    assert P.StartPick()
    _tap(lua, "PAD1")  # (A with no question up: asks, as X)
    assert G.jumpAsk._shown
    _tap(lua, "PAD2")  # (B: the question let go, still picking)
    assert not G.jumpAsk._shown and P.Picking() and N.stops[1].avoidJumps is None
    # (the left stick press: done, and back on the player)
    _tap(lua, "PADLSTICK")
    assert not P.Picking()


def test_the_mouse_s_right_click_question_is_taken_by_a_too(game, jump_trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pad
    _jumping(ns, jump_trip())
    G.Update()
    assert P.Apply()
    G.AskJump(G.JumpInfo(G.jumpSegs[1]), 0, 0)
    assert G.jumpAsk._shown
    assert any(_same(lua, b, G.jumpAsk.buttons[1]) for b, _ in _hints(lua, ns))
    _tap(lua, "PAD1")
    assert N.stops[1].avoidJumps == "spell"


def test_a_swim_is_picked_avoided_and_undone(game, trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pad
    r = trip(ISLE, SHORE)
    swum = r.swimYards
    assert swum > 200
    G.Update()
    assert P.Apply()
    items = [i for i in P.AvoidItems().values() if str(i.kind) == "swim"]
    assert len(items) >= 1
    assert P.StartPick()
    k = next(n for n, i in P.pick.list.items() if str(i.kind) == "swim")
    while P.pick.at != k:
        _tap(lua, "PADDRIGHT")
    P.Tick(0.2)
    tip = _tip(lua)
    assert tip[0].startswith("Swim") and tip[-1] == "X: avoid swimming for this stop", tip
    _tap(lua, "PAD3")
    ask = G.removeAsk
    assert ask._shown and ask.swim
    _tap(lua, "PAD1")
    trip.settle()
    assert N.noSwim or N.stops[1].avoidSwim
    assert N.route.swimYards < swum / 3, N.route.swimYards
    _tap(lua, "PAD4")  # (Y: taken back)
    trip.settle()
    assert not N.noSwim and not N.stops[1].avoidSwim and len(N.swimBans) == 0
    assert N.route.swimYards == pytest.approx(swum, rel=0.05)
    _tap(lua, "PAD4")  # (nothing more to take back: said, still picking)
    assert P.Picking()


def test_picking_works_in_the_world_map_too(game, jump_trip, pad):  # noqa: F811
    lua, ns = game
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    _jumping(ns, jump_trip())
    lua.execute(WM_SETUP)
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
        assert P.Apply()
        it = P.AvoidItems()[1]
        _pair(lua, "PADLSHOULDER", "PAD1")
        assert P.Picking()
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
        assert abs(G.PadView()[0] - it.x) < 0.5 and abs(G.PadView()[1] - it.y) < 0.5
        P.Tick(0.2)
        assert P.pickMark._shown and _same(lua, P.pickMark._parent, G.Canvas())
        _tap(lua, "PAD3")
        assert G.jumpAsk._shown
        _tap(lua, "PAD2")
        _tap(lua, "PAD2")
        assert not P.Picking()
    finally:
        P.EndPick()
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()


def test_no_jumps_or_swims_nothing_to_pick(game, pad):  # noqa: F811
    lua, ns = game
    N, P = ns.Nav, ns.Pad
    N.Clear()
    ns.GPS.Update()
    assert P.Apply()
    assert P.StartPick() is False and not P.Picking()


def test_undo_takes_the_last_avoid_back_first_and_skips_a_stop_gone(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    N.Clear()
    try:
        N.SetStops(lua.eval("{ { x = -1500.0, y = -2100.0, cont = 1, name = 'a' }, { x = -1450.0, y = -2150.0, cont = 1, name = 'b' } }"),
                   False, "red")
        assert N.CanUndoAvoid() is False and N.UndoAvoid() is False
        N.AvoidLegJumps(1, "spell")
        N.AvoidLegJumps(1, "all")
        N.AvoidLegSwim(2)
        assert N.CanUndoAvoid()
        assert N.UndoAvoid() and not N.stops[2].avoidSwim
        assert N.UndoAvoid() and N.stops[1].avoidJumps == "spell"
        assert N.UndoAvoid() and N.stops[1].avoidJumps is None
        assert N.UndoAvoid() is False
        # (the stops set again without it: nothing to take back)
        N.AvoidLegJumps(2, "all")
        N.SetStops(lua.eval("{ { x = -1500.0, y = -2100.0, cont = 1, name = 'a' }, { x = -1450.0, y = -2150.0, cont = 1, name = 'b' } }"),
                   False, "red")
        assert N.stops[2].avoidJumps is None and N.CanUndoAvoid() is False
        # (a stop gone: its avoid isn't taken back on another)
        N.AvoidLegJumps(1, "all")
        N.RemoveStop(1)
        assert N.CanUndoAvoid() is False and N.UndoAvoid() is False
    finally:
        N.Clear()


# --- The crosshair on a jump or swim (item 121, Kooki3z 2026-11-26: "add crosshair hover for spell jumps and swimming to
# press X like how we do with stops to remove them for controller"): the mouse's own hit-tests at the crosshair, shown as
# a stop under it is (a ring, its tooltip with X's avoid, X's icon over it); X asks the right-click's question, A takes
# it, Y takes it back while the crosshair is still there. LB + A's picking is as it was.

def _look(lua, ns, it):
    """The crosshair on route item `it` (Pad.AvoidItems'): the view's middle there, redrawn, the hover looked at."""
    G, P = ns.GPS, ns.Pad
    G.PadLookAt(it.cont, it.x, it.y)
    for _ in range(2):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
    P.Tick(0.2)


def test_the_crosshair_on_a_jump_shows_it_x_avoids_it_and_y_undoes(game, jump_trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pad
    r = jump_trip()
    _jumping(ns, r)
    G.Update()
    assert P.Apply()
    it = P.AvoidItems()[1]
    assert str(it.kind) == "jump"
    _look(lua, ns, it)
    h = P.routeHover
    assert h is not None and str(h.kind) == "jump"
    # (the mouse's own hit-test at that spot: the same jump its right-click would take)
    sg = G.JumpAt(*G.CrosshairSpot())[2]
    assert _same(lua, sg, h.sg) and _same(lua, G.JumpInfo(sg).stop, G.JumpInfo(h.sg).stop)
    # (shown as a stop under it is: the ring, its tooltip with X's avoid, X's icon over it)
    assert P.pickMark._shown and _same(lua, lua.eval("GameTooltip")._owner, P.pickMark)
    tip = _tip(lua)
    assert tip[0].startswith("Spell jump") and tip[-1] == "X: avoid spell jumps for this stop", tip
    assert any(_same(lua, b, P.pickMark) and i == "remove" for b, i in _hints(lua, ns))
    assert not P.Picking()
    # X: the right-click's question there; A takes it
    _tap(lua, "PAD3")
    ask = G.jumpAsk
    assert ask._shown and str(ask["items"][1].text) == "Avoid Spell Jumps"
    _tap(lua, "PAD1")
    assert not ask._shown and N.stops[1].avoidJumps == "spell"
    jump_trip.settle()
    assert ns.Router.KIND_DROP not in _route_kinds(N.route)
    # Y, the crosshair still there: taken back (not the map menu), and its hint is Y's
    P.Tick(0.2)
    assert P.routeHover is None and P.UndoHere()
    assert any(_same(lua, b, P.pickMark) and i == "menu" for b, i in _hints(lua, ns))
    assert _tip(lua)[0] == "Y: Undo"
    _tap(lua, "PAD4")
    assert N.stops[1].avoidJumps is None and not P.MenuOpen()
    jump_trip.settle()
    assert ns.Router.KIND_DROP in _route_kinds(N.route)
    # (nothing left to take back: Y is the map menu's again)
    assert not P.UndoHere()
    # LB + A still picks them one by one, the hover giving way
    _look(lua, ns, P.AvoidItems()[1])
    assert P.routeHover is not None
    _pair(lua, "PADLSHOULDER", "PAD1")
    assert P.Picking() and P.pick.at == 1
    P.Tick(0.2)
    assert P.routeHover is None and P.pickMark._shown and "1/" in _tip(lua)[0]
    _tap(lua, "PAD2")
    assert not P.Picking()
    # (panned off it: nothing hovered, the ring gone)
    G.PadPan(400, 400)
    lua.execute("AGPS_T = AGPS_T + 0.5")
    G.Update()
    P.Tick(0.2)
    assert P.routeHover is None and not P.pickMark._shown
    assert P.Press("X", True) is False  # (nothing under it: nothing happens)


def test_the_crosshair_on_a_swim_x_avoids_it_and_y_undoes(game, trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pad
    r = trip(ISLE, SHORE)
    swum = r.swimYards
    assert swum > 200
    G.Update()
    assert P.Apply()
    it = next(i for i in P.AvoidItems().values() if str(i.kind) == "swim")
    _look(lua, ns, it)
    h = P.routeHover
    assert h is not None and str(h.kind) == "swim"
    assert _same(lua, G.SwimAt(*G.CrosshairSpot())[2], h.sg)
    tip = _tip(lua)
    assert tip[0].startswith("Swim") and tip[-1] == "X: avoid swimming for this stop", tip
    assert any(_same(lua, b, P.pickMark) and i == "remove" for b, i in _hints(lua, ns))
    _tap(lua, "PAD3")
    ask = G.removeAsk
    assert ask._shown and ask.swim
    _tap(lua, "PAD1")
    trip.settle()
    assert N.noSwim or N.stops[1].avoidSwim
    assert N.route.swimYards < swum / 3, N.route.swimYards
    P.Tick(0.2)
    assert P.UndoHere()
    _tap(lua, "PAD4")  # (Y: taken back)
    trip.settle()
    assert not N.noSwim and not N.stops[1].avoidSwim and len(N.swimBans) == 0
    assert N.route.swimYards == pytest.approx(swum, rel=0.05)


def test_b_lets_the_crosshairs_question_go(game, jump_trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pad
    _jumping(ns, jump_trip())
    G.Update()
    assert P.Apply()
    _look(lua, ns, P.AvoidItems()[1])
    _tap(lua, "PAD3")
    assert G.jumpAsk._shown
    _tap(lua, "PAD2")
    assert not G.jumpAsk._shown and N.stops[1].avoidJumps is None and not P.UndoHere()


def test_the_crosshair_on_a_jump_works_in_the_world_map_too(game, jump_trip, pad):  # noqa: F811
    lua, ns = game
    N, G, P, st = ns.Nav, ns.GPS, ns.Pad, ns.settings.gps
    _jumping(ns, jump_trip())
    lua.execute(WM_SETUP)
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
        assert P.Apply()
        _look(lua, ns, P.AvoidItems()[1])
        assert P.routeHover is not None and str(P.routeHover.kind) == "jump"
        assert P.pickMark._shown and _same(lua, P.pickMark._parent, G.Canvas())
        _tap(lua, "PAD3")
        assert G.jumpAsk._shown
        _tap(lua, "PAD1")
        assert N.stops[1].avoidJumps == "spell"
        P.Tick(0.2)
        _tap(lua, "PAD4")
        assert N.stops[1].avoidJumps is None
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
