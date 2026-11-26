"""The map's setup and redraw run offline, under the game's Lua 5.1, with a stand-in for the game's UI
(wowmock.lua): every addon file loaded in the toc's order, the addon's start-up events fired, a route
set, and the map redrawn. A redraw failing (caught in the game: nothing drawn after the failing line,
the route and the directions panel gone) fails here. (The flight-path detour line: `x, y = a and f()`
left y nil, and every redraw failed.)"""

import math
import re
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start  # (the same harness `agps trip-sweep` runs)
    lua, ns = start()
    ns.Nav.FUN = False  # (always "Working out the route...", not now and then in Murloc)
    return lua, ns


def _redraw(lua, ns):
    G = ns.GPS
    G.Update()  # (not the frame's pcall: a failure fails the test)


def test_the_map_redraws_without_a_route(game):
    lua, ns = game
    ns.Nav.Clear()
    _redraw(lua, ns)


def test_the_map_redraws_with_a_route_by_a_flight_master_to_learn(game):
    # (reported) the route passing Tarren Mill's flight master, not learned: its detour line drawn,
    # and the rest of the redraw (the route, the directions panel) not lost to a failure there
    lua, ns = game
    cdb = ns.CharDB()
    cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { { nodeID = 10, known = true }, { nodeID = 11, known = true } } } }")
    cdb.faction = "Horde"
    ns.Nav.FlightsChanged()
    ns.Nav.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    for t in range(3):
        lua.execute(f"AGPS_T = {200 + t}")
        _redraw(lua, ns)
    r = ns.Nav.route
    assert r and ns.Nav.LearnOnRoute(r)
    assert "Detour" in ns.Nav.StepsText(9)


def test_a_flight_masters_detour_follows_the_roads(game):
    # (asked 2026-11-08: "flight path detour suggestions don't follow roads/paths, they should still do this if
    # possible") the detour to Tarren Mill's flight master is routed as a walk (Nav.DetourPath), not a straight line
    import math
    lua, ns = game
    N = ns.Nav
    cdb = ns.CharDB()
    cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { { nodeID = 10, known = true }, { nodeID = 11, known = true } } } }")
    cdb.faction = "Horde"
    N.FlightsChanged()
    N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    path = None
    for t in range(20):
        lua.execute(f"AGPS_T = {400 + t}")
        _redraw(lua, ns)
        h = N.route and N.LearnOnRoute(N.route)
        path = h and N.DetourPath(h[1])
        if path:
            break
    assert path, "the detour was never worked out"
    pts = [path[i] for i in range(1, len(path) + 1)]
    h = N.LearnOnRoute(N.route)[1]
    assert len(pts) > 4  # (more than the straight line's two ends)
    assert math.dist(pts[-2:], (h.x, h.y)) < 5
    walked = sum(math.dist(pts[i:i + 2], pts[i + 2:i + 4]) for i in range(0, len(pts) - 2, 2))
    assert walked > math.dist((h.rx, h.ry), (h.x, h.y))


def test_a_flight_masters_detour_is_never_routed_in_the_frame(game):
    # (reported for 1.2.5 and 1.2.6: "spikes and stuttering of around 130 ms when a route is active", trip-sweep's
    # Tor'kren Farm to Bloodtooth Camp: the redraw routed the detour's walk itself, Nav.DetourPath, each time the route
    # moved where the detour leaves it) in the game the walk is worked out in the background, drawn straight meanwhile
    lua, ns = game
    N, R = ns.Nav, ns.Router
    cdb = ns.CharDB()
    cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { { nodeID = 10, known = true }, { nodeID = 11, known = true } } } }")
    cdb.faction = "Horde"
    N.FlightsChanged()
    N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    h = None
    for t in range(20):
        lua.execute(f"AGPS_T = {600 + t}")
        _redraw(lua, ns)
        hs = N.route and N.LearnOnRoute(N.route)
        if hs:
            h = hs[1]
            break
    assert h, "no detour on the route"
    lua.execute("""
      AGPS_FRAME_ROUTES = 0
      local route = AGPS_NS.Router.Route
      AGPS_REAL_ROUTE = route
      AGPS_NS.Router.Route = function(...)
        if not coroutine.running() then AGPS_FRAME_ROUTES = AGPS_FRAME_ROUTES + 1 end
        return route(...)
      end
    """)
    was = (R.WARM, R.SYNC_WALKS)
    try:
        R.WARM, R.SYNC_WALKS = True, False
        h.rx = h.rx + 40  # (the route moved: the detour leaves it somewhere new, not worked out yet)
        assert N.DetourPath(h) is None and int(lua.eval("AGPS_FRAME_ROUTES")) == 0
        for _ in range(2000):
            if not R.HasWork():
                break
            R.Pump(1e12, lua.eval("function() return 0 end"))
        lua.execute(f"AGPS_T = {700}")
        path = N.DetourPath(h)
        assert path and len(path) > 4 and int(lua.eval("AGPS_FRAME_ROUTES")) == 0
    finally:
        R.WARM, R.SYNC_WALKS = was
        lua.execute("AGPS_NS.Router.Route = AGPS_REAL_ROUTE")


def _detour_pins(lua):
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w.learnNode and w._shown]


def test_a_detour_is_removed_for_this_route_by_its_pin(game):
    # (asked) the detour to a flight master to learn: a pin on the map; right-click, Remove: not
    # suggested again on this route (rerouting, a /reload), back with a new route
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    cdb = ns.CharDB()
    cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { { nodeID = 10, known = true }, { nodeID = 11, known = true } } } }")
    cdb.faction = "Horde"
    N.FlightsChanged()
    stop = lua.eval("{ { x = -1441, y = -2332, cont = 0 } }")
    ns.settings.gps.zoom = 2400  # (out far enough to show Tarren Mill's flight master from Brill)
    # (the walk past Tarren Mill into Arathi passes 355 yd of the Alliance's guards: with "Avoid the other faction's
    # towns" on, the ride round them by Orgrimmar wins since 2026-11-14 (test_enemy_territory.py); this test is about
    # the walk's detour pin, so with it off)
    had = ns.settings.gps.avoidHostile
    ns.settings.gps.avoidHostile = False
    try:
        _detour_removed(lua, ns, N, G, stop)
    finally:
        ns.settings.gps.avoidHostile = had


def _detour_removed(lua, ns, N, G, stop):
    N.SetStops(stop, False, "red")
    lua.execute("AGPS_T = 300")
    G.Update()
    pins = _detour_pins(lua)
    assert len(pins) == 1 and pins[0].learnNode == 13 and "Tarren Mill" in pins[0].title
    # (the flight master's own icon, not a new marker; the map's icon under it left out, as under a
    # stop made from a map icon)
    assert pins[0].icon._tex == r"Interface\TaxiFrame\UI-Taxi-Icon-Gray"
    taxi = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.icon and w.icon._tex
            and "UI-Taxi-Icon" in str(w.icon._tex) and not w.learnNode and w.name and "Tarren Mill" in w.name]
    assert not taxi
    G.AskRemove(pins[0])
    ask = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._text == "Remove?")
    ask._scripts.OnClick(ask)
    lua.execute("AGPS_T = 301")
    G.Update()
    assert not N.LearnOnRoute(N.route) and not _detour_pins(lua)
    assert [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.icon and w.icon._tex  # (the map's icon back)
            and "UI-Taxi-Icon" in str(w.icon._tex) and w.name and "Tarren Mill" in w.name]
    assert "Detour" not in N.StepsText(9)
    N.skipLearn = lua.eval("{}")  # (a /reload: back from the saved stops)
    N.Restore()
    lua.execute("AGPS_T = 302")
    G.Update()
    assert not N.LearnOnRoute(N.route)
    N.SetStops(stop)  # (a new route: asked about Arathi first, the detours back...)
    N.SetStops(stop, False, "red")  # (...and the yes to it)
    lua.execute("AGPS_T = 303")
    G.Update()
    assert N.LearnOnRoute(N.route) and N.LearnOnRoute(N.route)[1].node == 13


def _ride_pins(lua):
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w.ride and w._shown]


def test_a_ride_is_left_out_of_this_route_by_its_pin(game):
    # (asked) right-click "Remove?" on a ride's pin (the zeppelin from Brill): not taken again on this
    # route, rerouting or after a /reload; a new route takes it again
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    ns.settings.gps.zoom = 2400
    stop = lua.eval("{ { x = 1600, y = -4400, cont = 1 } }")
    N.SetStops(stop, False, "red")
    lua.execute("AGPS_T = 400")
    G.Update()
    zep = [p for p in _ride_pins(lua) if p.ride[8] == "zeppelin" and p.ride[10].startswith("Brill")]
    assert len(zep) == 1 and zep[0].title == "Zeppelin to Jaggedswine Farm, Durotar"
    assert str(zep[0].icon._tex).endswith(r"Media\Zeppelin")
    zep[0]._scripts.OnEnter(zep[0])  # (its tooltip: the dock's timetable and the hint)
    key = N.RideKey(zep[0].ride)
    G.AskRemove(zep[0])
    ask = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._text == "Remove?")
    ask._scripts.OnClick(ask)
    assert N.skipRides[key]
    lua.execute("AGPS_T = 401")
    G.Update()
    r = N.route
    assert r and all(not r.legs[i].ride or N.RideKey(r.legs[i].ride) != key for i in range(1, len(r.legs) + 1))
    assert all(N.RideKey(p.ride, p.hop) != key for p in _ride_pins(lua))
    N.skipRides = lua.eval("{}")  # (a /reload: back from the saved stops)
    N.Restore()
    assert N.skipRides[key]
    N.SetStops(stop)  # (a new route: asked about the zones on the way first, the rides back...)
    N.SetStops(stop, False, "red")  # (...and the yes to it)
    lua.execute("AGPS_T = 402")
    G.Update()
    assert not N.skipRides[key]
    assert any(N.RideKey(p.ride) == key for p in _ride_pins(lua))

def _shown(lua, test):
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and test(w)]


def test_a_pin_is_made_with_shift_click_and_used_like_a_city_location(game):
    # (asked) pinning (on by default): Shift + left-click on the map, "Create Pin", a name and an icon from
    # the game's (as a macro's); the pin on the map, double-click for a stop like a city location,
    # right-click to remove it; the option to hide pins
    lua, ns = game
    N, G, P = ns.Nav, ns.GPS, ns.Pins
    N.Clear()
    assert ns.settings.gps.pinning and ns.settings.gps.showCustomPins
    lua.execute("AGPS_OLD_SHIFT, AGPS_OLD_CURSOR = IsShiftKeyDown, GetCursorPosition\n"
                "IsShiftKeyDown = function() return true end\n"
                "GetCursorPosition = function() return 300, 300 end")  # (the map's middle: the stand-in's canvas)
    try:
        frame = lua.globals().AzerothGPSFrame
        frame._scripts.OnMouseDown(frame, "LeftButton")
        frame._scripts.OnMouseUp(frame, "LeftButton")
    finally:
        lua.execute("IsShiftKeyDown, GetCursorPosition = AGPS_OLD_SHIFT, AGPS_OLD_CURSOR")
    ask = _shown(lua, lambda w: w._text == "Create Pin" and w._scripts.OnUpdate)
    assert len(ask) == 1
    ask[0]._scripts.OnClick(ask[0])
    dlg = lua.globals().AzerothGPSPinDialog
    assert dlg._shown and len(P.Icons()) == 55  # (the game's macro icons: the stand-in's 30 and 25)
    cells = [c for c in dlg.cells.values()]
    cells[3]._scripts.OnClick(cells[3])  # (the fourth icon)
    dlg.name._text = "Herb spot"
    P.Confirm()
    assert not dlg._shown
    own = P.Own()
    assert len(own) == 1 and own[1].name == "Herb spot" and own[1].icon == P.Icons()[4] and own[1].level == 0
    lua.execute("AGPS_T = 500")
    G.Update()
    pins = _shown(lua, lambda w: w.pin is not None and w.pin.name == "Herb spot")
    assert len(pins) == 1 and pins[0].icon._tex == P.Icons()[4] and pins[0].name == "Herb spot"
    pins[0]._scripts.OnEnter(pins[0])  # (its tooltip)
    # double-click: a stop there, with its name and icon (as a city location)
    pins[0]._scripts.OnDoubleClick(pins[0])
    lua.execute("AGPS_T = 501")
    G.Update()
    stop = _shown(lua, lambda w: w.pendingIndex == 1)
    assert len(stop) == 1 and stop[0].icon._tex == P.Icons()[4]
    G.RemovePending(1)
    G.Follow()  # (the map back on the player: removing the last stop leaves it where it is since 1.3.5)
    # right-click: "Remove?"
    pins[0]._scripts.OnClick(pins[0], "RightButton")
    ask = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._text == "Remove?")
    ask._scripts.OnClick(ask)
    assert len(P.Own()) == 0
    lua.execute("AGPS_T = 502")
    G.Update()
    assert not _shown(lua, lambda w: w.pin is not None)
    # the option: pins hidden
    P.Add(lua.eval("{ level = 0, x = 2254, y = 293, name = 'Brill' }"))
    ns.settings.gps.showCustomPins = False
    G.ApplySettings()  # (as the options checkbox does: the kept icons are placed again)
    lua.execute("AGPS_T = 503")
    G.Update()
    assert not _shown(lua, lambda w: w.pin is not None)
    ns.settings.gps.showCustomPins = True
    G.ApplySettings()
    lua.execute("AGPS_T = 504")
    G.Update()
    assert _shown(lua, lambda w: w.pin is not None)
    P.Remove(P.Own()[1])
    G.Follow()  # (the stop made from the pin left the map looking at it: back to following, for the tests after)
    lua.execute("AGPS_T = 505")
    G.Update()


def test_a_pin_on_a_dungeons_floor_and_in_the_copied_map_data(game):
    # (asked) a pin minds the floor it's made on: in a dungeon whose floors lie over each other, the dialog
    # picks one (the floor the map shows first), the pin keeps its height and is faint on the other floors;
    # it goes out with the map data (Copy Map Data...)
    lua, ns = game
    G, P = ns.GPS, ns.Pins
    level = None
    for lvl in sorted(int(k) for k in ns.Instances.keys()):
        bosses = ns.Instances[lvl].bosses
        if len(G.InstanceFloors(lvl)) >= 2 and bosses and bosses[1] and bosses[1][3]:
            level = lvl
            break
    assert level, "no dungeon with floors over floors"
    bands = G.InstanceFloors(level)
    b = ns.Instances[level].bosses[1]
    floors, pick = G.PinFloors(level, b[3], b[4])
    assert len(floors) == len(bands) and floors[1].label == f"floor 1 of {len(bands)}, counting up"
    spot = lua.eval("{}")
    spot.level, spot.x, spot.y, spot.floors, spot.pick = level, b[3], b[4], floors, 0
    P.OpenEditor(spot)
    dlg = lua.globals().AzerothGPSPinDialog
    assert dlg.floorText._shown and dlg.floorText._text == "Floor: every floor here"
    P.StepFloor(1)
    P.StepFloor(1)
    assert dlg.floorText._text == f"Floor: floor 2 of {len(bands)}, counting up"
    dlg.name._text = "Second floor"
    p = P.Confirm()
    assert p.level == level and bands[2][1] - 2 <= p.z <= bands[2][2]
    far = lua.eval("{}")
    far[1], far[2] = p.z + 40, p.z + 50  # (a floor well over it)
    assert G.PinOffFloor(p, far) and not G.PinOffFloor(p, bands[2])
    assert G.PinFloorLabel(p) == f"floor 2 of {len(bands)}, counting up"
    text = ns.Feedback.RoadsText()[0]  # (the text, and its count of lines)
    assert f"P add {level} {p.time} " in text and "name=Second floor" in text
    P.Remove(p)
    assert "Second floor" not in ns.Feedback.RoadsText()[0]


def test_the_copy_window_leaves_out_what_is_unticked(game):
    # (asked) the Copy Map Data window: Roads, Walls, Routes and Pins ticked by default, with how many of
    # each; unticked, that kind leaves the text at once (and stays unticked: a setting)
    lua, ns = game
    P, O = ns.Pins, ns.Options
    pin = P.Add(lua.eval("{ level = 0, x = 2254, y = 293, name = 'Copy me' }"))
    try:
        O.ShowRoadsText()
        f = lua.globals().AzerothGPSRoadsCopy
        assert f._shown and "name=Copy me" in f.edit._text
        boxes = {cb.kind: cb for cb in f.kinds.values()}
        assert set(boxes) == {"roads", "walls", "routes", "pins"} and all(cb._checked for cb in boxes.values())
        assert boxes["pins"].text._text == "Pins (1)"
        boxes["pins"]._checked = False
        boxes["pins"]._scripts.OnClick(boxes["pins"])
        assert ns.settings.gps.copyPins is False and "Copy me" not in f.edit._text
        boxes["pins"]._checked = True
        boxes["pins"]._scripts.OnClick(boxes["pins"])
        assert ns.settings.gps.copyPins is True and "name=Copy me" in f.edit._text
    finally:
        P.Remove(pin)
        lua.globals().AzerothGPSRoadsCopy._shown = False


def test_an_overlay_draws_icons_until_removed(game):
    # (API 10, for the dev tools' import preview: a shared pin with its own icon) ctx.Icon on the map
    lua, ns = game
    G, A = ns.GPS, lua.globals().AzerothGPS
    A.SetOverlay("test icons", lua.eval("""function(ctx)
      ctx.Icon(2254, 293, 136777, 20, 0.5)
      ctx.Icon(99999, 99999, 136778, 20)
    end"""))
    lua.execute("AGPS_T = 720")
    G.Update()
    shown = _shown(lua, lambda w: w._tex == 136777)
    assert len(shown) == 1 and not _shown(lua, lambda w: w._tex == 136778)  # (one off the map: not drawn)
    A.SetOverlay("test icons", None)
    lua.execute("AGPS_T = 721")
    G.Update()
    assert not _shown(lua, lambda w: w._tex == 136777)

def test_an_overlay_is_told_the_level_the_map_shows(game):
    # (API 21, for the dev tools' road and navmesh views: down in Undercity the map shows its level, 10001, while
    # ctx.cont is still the continent) ctx.level: the city's level on its map, the continent on the land
    lua, ns = game
    G, A = ns.GPS, lua.globals().AzerothGPS
    lua.execute("AGPS_LEVELS = {} AGPS_MAP_REAL = AGPS_MAP AGPS_T = AGPS_T + 1000")
    A.SetOverlay("test level", lua.eval("""function(ctx)
      AGPS_LEVELS[#AGPS_LEVELS + 1] = { ctx.cont, ctx.level }
    end"""))
    try:
        lua.execute("AGPS_MAP = 1458 AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 1593.5, 157.3, 0 AGPS_T = AGPS_T + 1")
        G.Follow()
        G.Update()
        last = lua.eval("AGPS_LEVELS[#AGPS_LEVELS]")
        assert (last[1], last[2]) == (0, 10001)  # (down in Undercity: its level on the continent's coordinates)
        lua.execute("AGPS_MAP = AGPS_MAP_REAL AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()
        G.Update()
        last = lua.eval("AGPS_LEVELS[#AGPS_LEVELS]")
        assert (last[1], last[2]) == (0, 0)  # (the land)
    finally:
        A.SetOverlay("test level", None)
        lua.execute("AGPS_MAP = AGPS_MAP_REAL AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()
        G.Update()


def test_a_route_starting_with_the_hearthstone_says_so_in_both_windows(game):
    # (reported, screenshot) the route's step 1 "Use your Hearthstone" while the arrow window gave the turns
    # of the walk after it; asked: its button in the arrow window too, and the map's hidden while the
    # steps are collapsed
    lua, ns = game
    N, G, st = ns.Nav, ns.GPS, ns.settings.gps
    N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    lua.execute("AGPS_T = 800")
    G.Update()
    # (it walks through Hillsbrad, too high for the character: "Keep this route?", yes; until then it isn't
    # drawn or followed, N.RedAsking)
    lua.execute("AGPS_T = 800.5")
    G.Update()
    if N.RedAsking():
        G.confirmBox.yes._scripts.OnClick(G.confirmBox.yes)
    assert not N.RedAsking()
    real = N.UseNow
    hearth = lua.eval("{ 0, 2254, 293, 0, -8900, -160, 10, 'your Hearthstone', '', 'Northshire Valley', 'your Hearthstone', use = true, item = 6948 }")
    N.UseNow = lua.eval("function(t) return function() return t end end")(hearth)
    arrowWin = lua.globals().AzerothGPSArrow
    try:
        st.stepsCollapsed = False
        st.arrowLocked = True  # (asked: clickable with the arrow locked too, its window click-through)
        lua.execute("AGPS_T = 801")
        G.Update()
        assert G.useBtn._shown
        btn = lua.globals().AzerothGPSArrowUseButton
        # (anchored to the arrow window itself, as the map's to its panel: on a texture there it wasn't
        # over the icon in the game, 2026-10-01; its own frame, so the window's click-through leaves it)
        lua.execute("""AGPS_ANCHOR = nil
          AzerothGPSArrowUseButton.SetPoint = function(self, p, rel) AGPS_ANCHOR = rel end""")
        btn.key = None
        arrowWin._scripts.OnUpdate(arrowWin, 1)
        assert btn._shown and btn._attr["item"] == "item:6948"
        assert lua.eval("AGPS_ANCHOR")._name == "AzerothGPSArrow" and btn._parent._name == "UIParent"
        # (asked: the item's icon where the arrow was, glowing like the quest route's remake button; the
        # window's own texture, the clear button over it)
        tex = G.UseTexture(hearth)
        glow = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w._tex and "UI-ActionButton-Border" in str(w._tex)]
        assert _shown(lua, lambda w: w._tex == tex and w._parent is not None and w._parent._name == "AzerothGPSArrow") and len(glow) == 1
        texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString" or w._text]
        assert "Use your Hearthstone" in texts and "to Northshire Valley" in texts
        assert not any(t.startswith("Straight") or t.startswith("Continue straight") for t in texts if t)
        # (issue #46) on its cooldown after the route was planned: the time left over the icon, nothing to use;
        # ready again, it uses it
        lua.execute("""AGPS_REAL_CD = C_Container.GetItemCooldown
          C_Container.GetItemCooldown = function() return AGPS_T - 3600 + 270, 3600, 1 end""")
        lua.execute("AGPS_T = 801.5")
        G.Update()
        assert G.useBtn._shown and G.useBtn._attr["type"] is None and str(G.useBtn.cd._text) == "4:30"
        lua.execute("C_Container.GetItemCooldown = AGPS_REAL_CD")
        lua.execute("AGPS_T = 801.8")
        G.Update()
        assert G.useBtn._attr["type"] == "item" and G.useBtn._attr["item"] == "item:6948" and not G.useBtn.cd._text
        st.stepsCollapsed = True  # (the map's steps collapsed: its button hidden; the arrow's stays)
        lua.execute("AGPS_T = 802")
        G.Update()
        assert not G.useBtn._shown and btn._shown
    finally:
        N.UseNow = real
        st.stepsCollapsed, st.arrowLocked = False, False
        lua.execute("AGPS_T = 803")
        G.Update()
        arrowWin._scripts.OnUpdate(arrowWin, 1)
    assert not lua.globals().AzerothGPSArrowUseButton._shown and not G.useBtn._shown
    N.Clear()


def test_in_a_quest_area_the_arrow_still_shows_the_hearthstone_to_click(game):
    # (issue #733, Hillsbrad, a RestedXP step: in a quest's area with the route's next step "Use your Hearthstone"
    # (to Tarren Mill), the arrow stuck pointing straight up and the hearthstone's icon was hidden; its button's
    # tooltip still said "Use your Hearthstone") the quest-area directions returned before the icon was shown,
    # leaving the arrow up with nothing to turn it (no path while a teleport is step 1)
    lua, ns = game
    N, G, Lay = ns.Nav, ns.GPS, ns.Layers
    N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    lua.execute("AGPS_T = 1800")
    G.Update()
    lua.execute("AGPS_T = 1800.5")
    G.Update()
    if N.RedAsking():
        G.confirmBox.yes._scripts.OnClick(G.confirmBox.yes)
    real_use, real_at, real_obj = N.UseNow, Lay.QuestsAt, Lay.QuestObjectives
    hearth = lua.eval("{ 0, 2254, 293, 0, -8900, -160, 10, 'your Hearthstone', '', 'Tarren Mill', 'your Hearthstone', use = true, item = 6948 }")
    N.UseNow = lua.eval("function(t) return function() return t end end")(hearth)
    # (the player in another open quest's area, not the stop's: Souvenirs of Death's, 21/30 skulls)
    Lay.QuestsAt = lua.eval("""function(cont, x, y)
      if math.abs(x - 2254) < 50 and math.abs(y - 293) < 50 then return { 546 } end
      return {}
    end""")
    Lay.QuestObjectives = lua.eval("""function(id)
      return 'Souvenirs of Death', { { text = 'Hillsbrad Human Skull: 21/30', finished = false } }
    end""")
    arrowWin = lua.globals().AzerothGPSArrow
    try:
        lua.execute("AGPS_T = 1830")
        G.Update()
        arrowWin._scripts.OnUpdate(arrowWin, 1)
        assert list(N.areaQuests.values()) == [546] and not N.questing
        btn = lua.globals().AzerothGPSArrowUseButton
        assert btn._shown and btn._attr["item"] == "item:6948"
        tex = G.UseTexture(hearth)
        # (the hearthstone's icon in the arrow's place, glowing, the arrow itself hidden: not stuck pointing up)
        assert _shown(lua, lambda w: w._tex == tex and w._parent is not None and w._parent._name == "AzerothGPSArrow")
        assert not ns.Arrow.arrowTex._shown
        texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString" or w._text]
        # (the quest's objectives still listed, then what to do now: the hearthstone)
        assert any("Souvenirs of Death" in t for t in texts) and any("Hillsbrad Human Skull: 21/30" in t for t in texts)
        assert any("Use your Hearthstone" in t for t in texts)
    finally:
        N.UseNow, Lay.QuestsAt, Lay.QuestObjectives = real_use, real_at, real_obj
        lua.execute("AGPS_T = 1900")
        G.Update()
        arrowWin._scripts.OnUpdate(arrowWin, 1)
        N.Clear()


def test_collapsed_steps_say_the_hearthstone_kept_for_after_a_stop(game):
    # (asked 2026-11-05) in Silverpine, home Brill: the hearthstone is kept for after the Sepulcher, and with the
    # steps collapsed only the trip's times showed: it looked not planned. Said under them.
    lua, ns = game
    N, G, st, T = ns.Nav, ns.GPS, ns.settings.gps, ns.Teleports
    real = T.Available
    T.Available = lua.eval("""function(cont, px, py)
      return { { cont, px, py, 0, 2270.0, 245.0, 25, "your Hearthstone", "", "Brill", "your Hearthstone", use = true, item = 6948 } }
    end""")
    pos = lua.eval("{ AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] }")
    old = (pos[1], pos[2], pos[3])
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 560.0, 1560.0, 0")
    try:
        N.SetStops(lua.eval("{ { x = 522, y = 1652, cont = 0, name = 'The Sepulcher' }, { x = 2250, y = 250, cont = 0, name = 'Brill' } }"),
                   False, "red")
        st.stepsCollapsed = True
        for t in range(4):
            lua.execute(f"AGPS_T = {810 + t}")
            G.Update()
        shown = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString" and w._shown and w._text]
        panel = [t for t in shown if "All stops" in t]
        assert len(panel) == 1
        times, ahead = panel[0].split("\n")
        assert times.startswith("All stops") and "Use your Hearthstone after" in ahead and "The Sepulcher" in ahead
        assert ahead.endswith("(to Brill)")
    finally:
        T.Available = real
        st.stepsCollapsed = False
        N.Clear()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {old[0]}, {old[1]}, {old[2]}")
        lua.execute("AGPS_T = 815")
        G.Update()


def test_yes_no_questions_are_azerothgps_popups(game):
    # (asked, screenshot: "route there anyway?" a plain box) the questions in AzerothGPS's popup
    # (ns.Ask; with the title bar and logo since 2026-11-11): on the map, mid-screen while it's hidden, and a route someone shares
    lua, ns = game
    G, I = ns.GPS, ns.Import
    said = lua.eval("{}")
    yes = lua.eval("function(t) return function() t.yes = true end end")(said)
    no = lua.eval("function(t) return function() t.no = true end end")(said)
    assert G.Confirm("That stop is in Badlands (level 35-45): too high for your level 1.\n\nRoute there anyway?", yes, no)
    box = G.confirmBox
    assert box._shown and box.top in (-28, -30) and "Badlands" in box.text._text
    assert (box.yes._text, box.no._text) == ("Yes", "No")
    box.yes._scripts.OnClick(box.yes)
    assert said.yes and not said.no and not box._shown
    G.Confirm("Again?", yes, no)
    box._scripts.OnHide(box)  # (hidden with the map it's on, itself still shown: still waiting, the "?" shows it)
    assert not said.no
    box.Hide(box)  # (closed unanswered, Escape or the time out: as no; the mock's Hide sends no OnHide)
    box._scripts.OnHide(box)
    assert said.no
    # a shared route: its own question, "Use Route" / "Ignore"
    stops = lua.eval("{ { x = 2250, y = 250, cont = 0, name = 'Brill' }, { x = 1600, y = 240, cont = 0, name = 'Ruins' } }")
    I.Offer("Friend-Realm", stops)
    offer = I.offerBox
    assert offer.onMap and offer._shown and "Friend" in offer.text._text and "1. Brill" in offer.text._text
    assert (offer.yes._text, offer.no._text) == ("Use Route", "Ignore")
    offer.yes._scripts.OnClick(offer.yes)
    assert len(ns.Nav.stops) == 2
    ns.Nav.Clear()
    G.Follow()


def test_clear_route_leaves_the_view_where_it_is(game):
    # (asked 2026-11-19) Clear Route doesn't move the map back to the player: the view stays where it was
    # (following the player again, G.Follow, still shows the city's inside map: test above)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    G.outsideOf = "Ironforge"
    G.Follow()
    assert G.outsideOf is None
    N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    lua.execute("AGPS_T = 900")
    G.Update()
    G.outsideOf = "Ironforge"
    clear = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._text == "Clear Route")
    clear._scripts.OnClick(clear)
    assert len(N.stops) == 0 and G.outsideOf == "Ironforge"
    G.Follow()
    assert G.outsideOf is None


def test_every_popup_window_is_made_with_ns_window():
    # (asked) every popup in the map window's art style without its logo, by default: none built by hand
    # (only the map, the arrow's two panels and the options window, which has the logo, make their own)
    import re

    own = {"AzerothGPSFrame", "AzerothGPSArrow", "AzerothGPSDirections", "AzerothGPSOptions"}
    found = []
    # (every file, in folders too: the modules in their own folders; not the generated data)
    for f in sorted(p for p in ADDON.rglob("*.lua") if "Data" not in p.relative_to(ADDON).parts):
        for name in re.findall(r'CreateFrame\(\s*"Frame"\s*,\s*"(AzerothGPS\w*)"\s*,\s*UIParent', f.read_text(encoding="utf-8")):
            if name not in own:
                found.append((f.name, name))
    assert not found, f"popups to build with ns.Window: {found}"


def test_a_popup_window_has_the_map_windows_frame_and_a_small_logo(game):
    # ns.Window: the client's PortraitFrameTemplate with the no-portrait border, its own background hidden
    # for the dark inside, the portrait hidden, the title set; a plain box where the template is missing
    lua, ns = game
    lua.execute("""
      AGPS_REAL_CF = CreateFrame
      CreateFrame = function(kind, name, parent, template)
        local w = AGPS_REAL_CF(kind, name, parent, template)
        if template == "PortraitFrameTemplate" then
          w.NineSlice, w.Bg, w.PortraitContainer = AGPS_REAL_CF("Frame"), w:CreateTexture(), AGPS_REAL_CF("Frame")
          w.PortraitContainer.portrait = w:CreateTexture()
          w.TitleContainer = AGPS_REAL_CF("Frame")
          w.TitleContainer.TitleText = w:CreateFontString()
          w.CloseButton = AGPS_REAL_CF("Button")
          w.SetBorder = function(self, layout) self.agpsBorder = layout end
          w.SetTitle = function(self, text) self.TitleContainer.TitleText:SetText(text) end
        end
        return w
      end""")
    try:
        f = ns.Window("AzerothGPSTestPopup", 300, 200, "Hello")
    finally:
        lua.execute("CreateFrame = AGPS_REAL_CF")
    c = f.chrome
    assert c is not None and f.top == -30 and not f._shown
    assert c.agpsBorder == "ButtonFrameTemplateNoPortrait" and not c.Bg._shown and not c.PortraitContainer._shown
    assert c.TitleContainer.TitleText._text == "Hello"
    # (asked 2026-11-10: the addon's logo on every popup, smaller than the map window's; not on a window another
    # addon asked for)
    assert f.logo is not None and f.logo.units == ns.POPUP_LOGO_UNITS and f.logo.plate._shown
    lua.execute("""
      AGPS_REAL_CF = CreateFrame
      CreateFrame = function(kind, name, parent, template)
        local w = AGPS_REAL_CF(kind, name, parent, template)
        if template == "PortraitFrameTemplate" then
          w.NineSlice, w.PortraitContainer = AGPS_REAL_CF("Frame"), AGPS_REAL_CF("Frame")
          w.PortraitContainer.portrait = w:CreateTexture()
        end
        return w
      end""")
    try:
        theirs = lua.globals().AzerothGPS.Window(None, 300, 200, "Theirs")
    finally:
        lua.execute("CreateFrame = AGPS_REAL_CF")
    assert theirs.chrome is not None and theirs.logo is None
    f._shown = True
    c.CloseButton._scripts.OnClick(c.CloseButton)
    assert not f._shown
    assert "AzerothGPSTestPopup" in list(lua.globals().UISpecialFrames.values())
    plain = ns.Window("AzerothGPSTestPlain", 300, 200, "Plain")  # (the stand-in has no template parts: the box)
    assert plain.chrome is None and plain.top == -28

def test_the_style_buttons_and_command_leave_a_held_style(game):
    # (API 9) while a game holds the map with a style, the Map Style buttons and /agps style don't change
    # it (they say why); the map draws it at every zoom; let go, the player's own is back
    lua, ns = game
    G, A = ns.GPS, lua.globals().AzerothGPS
    said = lua.eval("{}")
    old_print = ns.Print
    ns.Print = lua.eval("function(t) return function(msg) t[#t + 1] = msg end end")(said)
    was = ns.settings.gps.style
    try:
        ns.settings.gps.style = "minimap"
        A.HoldMap("game", True, None, lua.eval('{ style = "unrevealed" }'))
        lua.execute("AGPS_T = 700")
        G.Update()
        zone = next(t for t in G.QUICK.values() if t.style == "zone")
        zone.button._scripts.OnClick(zone.button)
        assert ns.settings.gps.style == "minimap" and G.Style() == "unrevealed"
        assert said[1] == G.HELD_STYLE_TEXT
        assert not G.QuickOn(zone) and G.QuickOn(next(t for t in G.QUICK.values() if t.style == "minimap")) is False
        lua.globals().SlashCmdList.AZEROTHGPS("style zone")
        assert ns.settings.gps.style == "minimap"
        assert [m for m in said.values() if m == G.HELD_STYLE_TEXT] == [G.HELD_STYLE_TEXT] * 2
        A.HoldMap("game", False)
        assert G.Style() == "minimap"
        lua.globals().SlashCmdList.AZEROTHGPS("style zone")
        assert ns.settings.gps.style == "zone"
    finally:
        ns.Print = old_print
        A.HoldMap("game", False)
        ns.settings.gps.style = was
        lua.execute("AGPS_T = 701")
        G.Update()

def test_the_dev_hooks_for_sharing(game):
    # (a developer addon: AzerothGPS_Extend runs its setup with ns; the one way
    # out, Import.io.send; messages in, Import.OnAddonMessage; the popup, Import.Offer)
    lua, ns = game
    lua.globals().AzerothGPS_Extend(lua.eval("function(n) AGPS_EXTENDED = n end"))
    assert lua.eval("rawequal")(lua.eval("AGPS_EXTENDED"), ns)  # (after login: at once)
    I = ns.Import
    sent, offered = [], []
    real_send, real_offer = I.io.send, I.Offer
    try:
        I.io.send = lambda prefix, msg, channel, target: sent.append((prefix, msg, channel, target))
        I.Offer = lambda sender, stops: offered.append((sender, [stops[i].name for i in range(1, len(stops) + 1)]))
        ns.Nav.SetStops(lua.eval("{ { x = 2250, y = 250, cont = 0, name = 'Brill' }, { x = 1600, y = 240, cont = 0, name = 'Ruins' } }"), False, "red")
        lua.execute("AGPS_OLD_OC = ChatFrame_OpenChat ChatFrame_OpenChat = function(t) AGPS_OPENED = t end")
        n, rid = I.Send("WHISPER", "Friend-Realm")
        assert n == 2 and not sent  # (a link in the chat box: nothing sent)
        I.OnAddonMessage("AzerothGPS", "?\t" + rid, "WHISPER", "Friend-Realm")  # (they clicked it)
        assert len(sent) == 2 and sent[0][0] == "AzerothGPS" and all(t == "Friend-Realm" for _, _, _, t in sent)
        I.Expect("Friend-Realm", rid)  # (and back in as another player's, asked for)
        for _, msg, _, _ in sent:
            I.OnAddonMessage("AzerothGPS", msg, "WHISPER", "Friend-Realm")
        assert offered == [("Friend-Realm", ["Brill", "Ruins"])]
    finally:
        I.io.send, I.Offer = real_send, real_offer
        lua.execute("ChatFrame_OpenChat = AGPS_OLD_OC")


def test_route_links_in_chat_are_wired_up_at_login(game):
    # (Import.Init) a route's line in whisper, party or raid chat becomes a link; clicking it (the game hands
    # "addon:" links to EventRegistry's SetItemRef) asks its author for the route, once per click
    lua, ns = game
    I = ns.Import
    sent, real_send = [], I.io.send
    try:
        I.io.send = lambda prefix, msg, channel, target: sent.append((msg, channel, target))
        for event in ("CHAT_MSG_WHISPER", "CHAT_MSG_PARTY", "CHAT_MSG_RAID"):
            (f,) = lua.eval("AGPS_CHAT_FILTERS")[event].values()
            hide, msg, author = f(None, event, "go [AzerothGPS Route a1b2c3: 3 stops]", "Ann-Realm")
            assert not hide and author == "Ann-Realm"
            assert msg == "go |cff33ff99|Haddon:AzerothGPS:route:a1b2c3:Ann-Realm|h[AzerothGPS Route: 3 stops]|h|r"
            assert f(None, event, "nothing to link", "Ann-Realm") is None
        # your own whisper out: the link is yours (nothing asked when clicked)
        (f,) = lua.eval("AGPS_CHAT_FILTERS")["CHAT_MSG_WHISPER_INFORM"].values()
        assert ":route:a1b2c3:Tester|h" in f(None, "CHAT_MSG_WHISPER_INFORM", "[AzerothGPS Route a1b2c3: 1 stop]", "Ann")[1]
        (click,) = lua.eval("AGPS_CALLBACKS")["SetItemRef"].values()
        click(None, "addon:AzerothGPS:route:a1b2c3:Tester")
        assert not sent
        click(None, "addon:AzerothGPS:route:a1b2c3:Ann-Realm")
        click(None, "addon:AzerothGPS:route:a1b2c3:Ann-Realm")  # (the same click by SetItemRef's hook)
        assert sent == [("?\ta1b2c3", "WHISPER", "Ann-Realm")]
    finally:
        I.io.send = real_send


def test_no_dev_tool_ships_with_the_addon():
    # (developer tools are kept out of the shipped addon)
    files = [p.name.lower() for p in ADDON.rglob("*")]
    assert not any("dev" in f and f.endswith((".lua", ".toc", ".xml")) and f != "devnull" for f in files), \
        [f for f in files if "dev" in f]
    toc = (ADDON / "AzerothGPS.toc").read_text(encoding="utf-8").lower()
    assert not re.search(r"^\s*[^#].*_dev\b", toc, re.M)  # (no developer files listed)
    # (asked 2026-10-06) the simulated player and the map-click hook are the dev tools' only: AzerothGPS never sets them,
    # but for the tutorial's spell-jump demo (Kooki3z 2026-11-25), which sets and ends it in Tutorial.lua alone
    src = "\n".join(p.read_text(encoding="utf-8") for p in ADDON.rglob("*.lua") if p.name != "Tutorial.lua")
    assert len(re.findall(r"SetOverride\(", src)) == 1  # (its definition)
    tut = (ADDON / "Tutorial.lua").read_text(encoding="utf-8")
    assert len(re.findall(r"SetOverride\(", tut)) == 2  # (T.JumpDemoStart's and T.JumpDemoStop's)
    assert not re.search(r"mapClickHook\s*=[^=]", src) and not re.search(r"override\s*=\s*\{", src)
    assert not re.search(r"mapModClickHook\s*=[^=]", src)  # (another addon's modified clicks: never set here)


def test_no_map_editor_ships_with_the_addon(game):
    # (Kooki3z, 2026-11-22, for 1.3.14: the map editor is the dev addon's only) no road or wall tools, magic eraser,
    # stairs tool, Edit Road / Edit Wall, Record or its window, their buttons, key or slash commands in the shipped addon;
    # what's left is the player's own roads and walls as routes use them (Record.Tracks, Archive, Prune) and the hooks
    lua, ns = game
    G, R = ns.GPS, ns.Record
    for name in ("SetRoadMode", "SetWallMode", "ToggleRoadMode", "ToggleWallMode", "SetEraserMode", "RestoreZone",
                 "RestoreContinent", "FinishRoad", "SetStairMode", "SetEditRoadMode", "SetEditWallMode", "AskRoadEdit",
                 "AskWallEdit", "AskSetHeights", "ToolClick", "ShowToolLegend", "RoadHover", "StepEditFloor",
                 "MapToolDown", "EditorDraw"):
        assert G[name] is None, name
    for name in ("Save", "Undo", "List", "Delete", "AddShared", "EditTrack", "EditWall", "Restore", "StartRecording",
                 "ShowWindow", "ToggleWindow", "MarkStairs", "OnEnteringWorld", "OnLogout"):
        assert R[name] is None, name
    assert R.Tracks is not None and R.Prune is not None and R.Archive is not None
    for gone in ("roadTools", "wallTools", "roadUndo", "magicEraser", "restoreZone", "restoreContinent", "roadStairs",
                 "roadRecord", "roadEdit", "wallEdit"):
        assert not any(t.id == gone for t in G.QUICK.values()), gone
    assert G.groupOf["mapEdit"] is None and ns.Import.TakeTracks is None
    assert [k[1] for k in ns.Import.EXPORT_KINDS.values()] == ["herbs", "ore", "npcs", "pins"]
    for api in ("ShowRecorder", "Recording", "RecordedWalks"):
        assert lua.globals().AzerothGPS[api] is None, api
    assert ns.COMMANDS.dev is None and ns.COMMANDS.draw is None
    src = "\n".join(p.read_text(encoding="utf-8") for p in ADDON.glob("*.lua"))
    assert "AZEROTHGPS_RECORD_STAIRS" not in src
    assert "AZEROTHGPS_RECORD_STAIRS" not in (ADDON / "Bindings.xml").read_text(encoding="utf-8")
    assert not (ADDON / "Media" / "Tools" / "MouseLeft_14.tga").exists()  # (the tools' legend's own icons)
    assert "roads" not in [str(s.id) for s in ns.Tutorial.SECTIONS.values()]


def test_a_simulated_player_is_the_dev_tools_only_and_nothing_is_learned_from_it(game):
    # (asked 2026-10-06 for route testing: put the player anywhere on the map, or drive them) unset by
    # default: the game's position, as before. Set (Geo.SetOverride), the map, routing and the arrow go by it (where,
    # facing, an underground city's level, moving), while companions (the public API) keep the game's own, the
    # minimap's route waits (the minimap is round the real player) and nothing is learned from it (an NPC talked to).
    # A plain click on the map goes to the dev tools' hook when there is one; a double-click still makes a stop
    lua, ns = game
    G, Geo, N, L, A = ns.GPS, ns.Geo, ns.Nav, ns.Layers, lua.globals().AzerothGPS
    real = tuple(Geo.RealPlayerWorld())
    assert Geo.override is None and not Geo.Simulated() and G.mapClickHook is None
    assert tuple(Geo.PlayerWorld()) == real and Geo.Facing() == Geo.RealFacing()
    frame = lua.globals().AzerothGPSFrame
    lua.execute("""
      AGPS_OLD = { cur = GetCursorPosition, guid = UnitGUID, name = UnitName }
      GetCursorPosition = function() return 300, 300 end -- (the stand-in canvas's middle)
      UnitGUID = function(u) if u == "npc" then return "Creature-0-1-2-3-6741-00000ABC" end return AGPS_OLD.guid(u) end
      UnitName = function(u) if u == "npc" then return "Innkeeper Renee" end return AGPS_OLD.name(u) end
    """)
    npcs = ns.db.npcs
    try:
        Geo.SetOverride(lua.eval("{ x = 1700, y = 500, cont = 0, facing = 1.2, moving = true }"))
        assert tuple(Geo.PlayerWorld())[:3] == (1700, 500, 0) and Geo.Facing() == 1.2 and Geo.Simulated()
        assert tuple(A.PlayerWorld()) == real and A.Facing() == Geo.RealFacing()
        assert G.PlayerMoving() is True
        Geo.SetOverride(lua.eval("{ x = 1600, y = 240, cont = 0, level = 10001 }"))  # (down in Undercity)
        assert N.PlayerLevel(0) == 10001
        Geo.SetOverride(lua.eval("{ x = 2250, y = 250, cont = 0 }"))
        assert N.PlayerLevel(0) == 0 and G.PlayerMoving() is False
        # nothing learned: an NPC's window while simulated
        ns.db.npcs = None
        assert not L.OnNpcWindow("GOSSIP_SHOW", lua.eval("{}")) and not ns.db.npcs
        # the route from the simulated spot, not on the game's minimap
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        G.Update()
        r = N.route
        assert r and (r.pts[1] - 2250) ** 2 + (r.pts[2] - 250) ** 2 < 30 ** 2
        assert G.UpdateMinimapRoute(True) == 0
        # a plain click to the dev tools' hook, at the map's own projection; a double-click's second one passed on
        got = []
        G.mapClickHook = lambda x, y, level, double: got.append((x, y, level, double)) or True
        vx, vy = tuple(G.ViewState())[:2]
        frame._scripts.OnMouseDown(frame, "LeftButton")
        frame._scripts.OnMouseUp(frame, "LeftButton")
        assert len(got) == 1 and got[0][:2] == pytest.approx((vx, vy)) and got[0][2:] == (0, False)
        frame._scripts.OnMouseDown(frame, "LeftButton")
        frame._scripts.OnMouseUp(frame, "LeftButton")
        assert len(got) == 2 and got[1][3] is True
    finally:
        G.mapClickHook = None
        Geo.SetOverride(None)
        ns.db.npcs = npcs
        lua.execute("GetCursorPosition, UnitGUID, UnitName = AGPS_OLD.cur, AGPS_OLD.guid, AGPS_OLD.name")
        N.Clear()
        G.Follow()
    assert tuple(Geo.PlayerWorld()) == real and N.PlayerLevel(0) == 0


def test_a_modified_click_goes_to_another_addons_hook_before_the_map_pin(game):
    # (a map click hook for other addons, 2026-11-22) with no hook, Ctrl + left-click is the map pin as always and Alt +
    # left-click a plain click; with one, a left click with Ctrl or Alt held goes to it first (world yards through the
    # map's projection, the level shown, the modifiers): taken, no map pin and no plain click; not taken, as before.
    # A plain click never reaches it
    lua, ns = game
    G, I = ns.GPS, ns.Import
    frame = lua.globals().AzerothGPSFrame
    lua.execute("""
      AGPS_OLD_MOD = { IsControlKeyDown, IsAltKeyDown, GetCursorPosition }
      AGPS_CTRL, AGPS_ALT = false, false
      IsControlKeyDown = function() return AGPS_CTRL end
      IsAltKeyDown = function() return AGPS_ALT end
      GetCursorPosition = function() return 300, 300 end
    """)
    got, plain = [], []

    def click(ctrl=False, alt=False):
        lua.execute("AGPS_CTRL, AGPS_ALT = %s, %s" % ("true" if ctrl else "false", "true" if alt else "false"))
        frame._scripts.OnMouseDown(frame, "LeftButton")
        frame._scripts.OnMouseUp(frame, "LeftButton")
        lua.execute("AGPS_CTRL, AGPS_ALT = false, false")

    try:
        ns.CharDB().mapPin = None
        assert G.mapModClickHook is None
        click(alt=True)  # (no hook: Alt + click is a plain click, no map pin)
        assert I.MapPin() is None
        click(ctrl=True)  # (no hook: the map pin)
        assert I.MapPin() is not None
        I.ClearMapPin()
        x, y, c = G.ClickWorld()
        G.mapModClickHook = lambda x, y, level, z, ctrl, alt: got.append((x, y, level, z, ctrl, alt)) or (ctrl and alt)
        G.mapClickHook = lambda x, y, level, double: plain.append((x, y)) or True
        click(ctrl=True, alt=True)  # (taken: nothing else happens)
        assert len(got) == 1 and got[0][:2] == pytest.approx((x, y)) and got[0][2:] == (c, None, True, True)
        assert I.MapPin() is None and not plain
        click(ctrl=True)  # (not taken: the map pin, as before)
        assert len(got) == 2 and got[1][4:] == (True, False) and I.MapPin() is not None and not plain
        I.ClearMapPin()
        click()  # (a plain click: not to it)
        assert len(got) == 2 and len(plain) == 1
    finally:
        G.mapModClickHook = None
        G.mapClickHook = None
        ns.CharDB().mapPin = None
        lua.execute("IsControlKeyDown, IsAltKeyDown, GetCursorPosition = unpack(AGPS_OLD_MOD, 1, 3)")
        G.Follow()


def test_the_search_offers_only_your_factions_npcs_and_neutral_ones(game):
    # (the user's 1.1.6 test pass, 2026-10-07: "routing to an opposing faction NPC shouldn't show up in the list") the
    # NPCs met are account-wide: an NPC's faction is recorded from its window (UnitFactionGroup), the search lists the
    # player's faction's and neutral ones; an old or imported record (no faction) goes by where it stands: within the
    # other faction's guards' reach is theirs (Data/Hostile.lua), elsewhere neutral
    lua, ns = game
    L, N = ns.Layers, ns.Nav
    cdb = ns.CharDB()
    faction, npcs = cdb.faction, ns.db.npcs
    lua.execute("""
      AGPS_OLDF = { guid = UnitGUID, name = UnitName, fg = UnitFactionGroup }
      UnitGUID = function(u) if u == "npc" then return "Creature-0-1-2-3-6741-00000ABC" end return AGPS_OLDF.guid(u) end
      UnitName = function(u) if u == "npc" then return "Innkeeper Farley" end return AGPS_OLDF.name(u) end
      UnitFactionGroup = function(u) if u == "npc" then return "Alliance" end return AGPS_OLDF.fg(u) end
    """)

    def names():
        return {str(n.name) for n in L.KnownNpcs().values()}

    try:
        ns.db.npcs = lua.eval("""{
          [101] = { name = "Test Alliance Vendor", cont = 0, x = -8900, y = 600, faction = "Alliance" },
          [102] = { name = "Test Goblin", cont = 1, x = -7100, y = -3800, faction = "Neutral" },
          [103] = { name = "Test Old Goldshire", cont = 0, x = -9459, y = 42 },
          [104] = { name = "Test Old Brill", cont = 0, x = 2266, y = 243 },
        }""")
        cdb.faction = "Horde"
        assert names() == {"Test Goblin", "Test Old Brill"}
        cdb.faction = "Alliance"
        assert names() == {"Test Alliance Vendor", "Test Goblin", "Test Old Goldshire"}
        # its window records what the game says
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -9459.0, 42.0, 0")
        L.OnNpcWindow("MERCHANT_SHOW", lua.eval("{}"))
        assert str(ns.db.npcs[6741].faction) == "Alliance"
    finally:
        lua.execute("UnitGUID, UnitName, UnitFactionGroup = AGPS_OLDF.guid, AGPS_OLDF.name, AGPS_OLDF.fg")
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")
        cdb.faction = faction
        ns.db.npcs = npcs


def test_heading_up_puts_the_player_low_on_the_map(game):
    # (asked) with "Turn the map with me" on, following: the player's icon low on the map (more of
    # the way ahead shown), not in the middle; north-up keeps them in the middle
    lua, ns = game
    G, Geo = ns.GPS, ns.Geo
    st = ns.settings.gps
    lua.execute("GetPlayerFacing = function() return 0.7 end")

    def player_on_screen():
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        x, y, cont, rot, s, half = G.ViewState()
        dx, dy = Geo.ScreenOffset(x, y, lua.eval("AGPS_POS[1]"), lua.eval("AGPS_POS[2]"))
        ax, ay = Geo.Rotate(dx * s, dy * s, rot)
        return ax / half, ay / half
    try:
        st.rotate = True
        ax, ay = player_on_screen()
        assert abs(ax) < 0.01 and abs(ay + ns.GPS.HEADING_UP_LOW) < 0.01, (ax, ay)
        st.rotate = False
        ax, ay = player_on_screen()
        assert abs(ax) < 0.01 and abs(ay) < 0.01
    finally:
        st.rotate = False
        lua.execute("GetPlayerFacing = function() return 0 end")


@pytest.mark.timing
def test_running_a_route_with_a_flight_stays_within_the_frame(game):
    # (reported: lag spikes rerouting along a route with a flight in it) the walk-vs-ride check in
    # the background, its slices short; in the frame, once the flight is the route, only the walk
    # from the player (crossing into another square: the last answer, not the whole walk routed)
    lua, ns = game
    R, N, G = ns.Router, ns.Nav, ns.GPS
    cdb = ns.CharDB()
    cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { { nodeID = 10, known = true }, { nodeID = 11, known = true } } } }")
    cdb.faction = "Horde"
    N.FlightsChanged()
    lua.execute("""
      AGPS_LONG = 0
      local route = AGPS_NS.Router.Route
      AGPS_NS.Router.Route = function(cont, sx, sy, tx, ty, opts)
        local r = route(cont, sx, sy, tx, ty, opts)
        if not coroutine.running() and r and r.length > 3000 then AGPS_LONG = AGPS_LONG + 1 end
        return r
      end
      AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0
    """)
    clock = lua.eval("function() return os.clock() * 1000 end")

    def flies():
        return N.route and any(N.route.legs[i].ride for i in range(1, len(N.route.legs) + 1))
    try:
        R.Reset()
        R.WARM, R.SYNC_WALKS = True, False
        N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
        t = 600.0
        # (the roads built, the first route, the comparison: the flight; about 600 frames of 5 ms here, so the cap is
        # far past that: a loaded CI runner needed more and the test failed before the setup was done)
        for _ in range(4000):
            t += 0.05
            lua.execute(f"AGPS_T = {t}")
            G.Update()
            if R.HasWork():
                R.Pump(clock() + 5, clock)
            if flies() and not R.HasWork():
                break
        assert flies()
        lua.execute("AGPS_LONG = 0")
        x, y, worst = 2254.0, 293.0, 0.0
        for step in range(400):  # (about 20 s running toward the lift, weaving)
            t += 0.05
            x, y = x - 0.33, y + (0.25 if step % 60 < 30 else -0.25)
            lua.execute(f"AGPS_T = {t}; AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
            G.Update()
            if R.HasWork():
                a = clock()
                R.Pump(clock() + 1, clock)
                worst = max(worst, clock() - a)
        assert lua.eval("AGPS_LONG") == 0, "the whole walk was routed in the frame while running"
        assert worst < 40, f"a background slice ran {worst:.0f} ms"
        assert flies()
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")


def test_riding_a_zeppelin_doesnt_work_the_route_out_again(game):
    # (reported: a CPU spike with a route set, riding a zeppelin) carried along standing still, the
    # route isn't worked out again (as on a flight); walking again, it is
    lua, ns = game
    T, N, R = ns.Taxi, ns.Nav, ns.Router
    N.SetStops(lua.eval("{ { x = 1600, y = 240, cont = 0, name = 'Ruins' } }"), False, "red")
    lua.execute("""
      AGPS_ROUTES = 0
      local route = AGPS_NS.Router.Route
      AGPS_NS.Router.Route = function(...) AGPS_ROUTES = AGPS_ROUTES + 1 return route(...) end
    """)
    x, y = 2254.0, 293.0
    t0 = float(lua.eval("AGPS_T")) + 10  # (the game's clock: on from where the other tests left it)
    lua.execute(f"AGPS_T = {t0}")
    assert N.Route(x, y, 0)
    for k in range(4):  # (standing on the deck, carried 10 yd a check)
        x -= 10
        T.TransportTick(100 + k * 0.5, 1000 + k, x, y, 0, 0)
    assert T.Riding()
    lua.execute("AGPS_ROUTES = 0")
    for k in range(6):  # (far off the route: at a ride's speed every check was)
        x, y = x - 60, y + 90
        lua.execute(f"AGPS_T = {t0 + 5 + k * 5}")
        T.TransportTick(102 + k * 0.5, 1004 + k, x, y, 0, 0)
        assert N.Route(x, y, 0)
    assert lua.eval("AGPS_ROUTES") == 0
    T.TransportTick(106, 1010, x - 1, y, 0, 7)  # (walking off it)
    assert not T.Riding()
    lua.execute(f"AGPS_T = {t0 + 100}")
    N.Route(x, y, 0)
    assert lua.eval("AGPS_ROUTES") > 0


def test_every_stop_has_its_marker_though_the_route_is_drawn_a_few_ahead(game):
    # (asked) the option "stops routed and drawn ahead" limits the route worked out and drawn; the
    # stops' markers all show (only those in the map's view are placed)
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    st = ns.settings.gps
    zoom, ahead = st.zoom, st.stopsAhead
    try:
        st.zoom, st.stopsAhead = 1500, 2
        N.SetStops(lua.eval("""{ { x = 2300, y = 250, cont = 0 }, { x = 2350, y = 150, cont = 0 },
          { x = 2200, y = 100, cont = 0 }, { x = 2150, y = 350, cont = 0 }, { x = 2400, y = 400, cont = 0 },
          { x = -9000, y = 400, cont = 0 } }"""), False, "red")
        lua.execute("AGPS_T = AGPS_T + 100")
        G.Update()
        assert N.PlannedStops() == 2
        shown = sorted(int(w.stopIndex) for w in lua.eval("AGPS_WIDGETS").values() if w.stopIndex and w._shown)
        assert shown == [1, 2, 3, 4, 5]  # (not the 6th: far off the map)
    finally:
        st.zoom, st.stopsAhead = zoom, ahead
        N.Clear()


def test_debug_probes_party_members_positions(game):
    # (asked: showing party members on the map, with or without the addon on their side) /agps debug
    # says what the game gives an addon for each member: by unit, no names saved
    lua, ns = game
    lua.execute("""
      AGPS_PARTY = { party1 = { 2200, 300 }, party2 = { 2100, 250 } }
      UnitExists = function(u) return AGPS_PARTY[u] ~= nil end
      UnitIsUnit = function(a, b) return a == b end
      UnitIsConnected = function(u) return AGPS_PARTY[u] ~= nil end
      IsInRaid = function() return false end
      local pos = UnitPosition
      UnitPosition = function(u)
        local p = AGPS_PARTY[u]
        if p then return p[1], p[2], 0, 0 end
        return pos(u)
      end
    """)
    try:
        ns.RunProbe("test")
        rec = ns.db.probes[len(ns.db.probes)]
        party = next(r for r in rec.results.values() if r.name == "party positions")
        assert party.ok and "party1: UnitPosition=2200,300" in party.value and "party2:" in party.value
        assert "Tester" not in party.value
    finally:
        lua.execute("AGPS_PARTY = {}")


def test_party_members_are_dots_on_the_map(game):
    # (asked) party members on the map where the game gives their position: a dot each in their
    # class's color; the option off: none
    lua, ns = game
    G = ns.GPS
    st = ns.settings.gps
    lua.execute("""
      AGPS_PARTY = { party1 = { 2260, 300 } }
      UnitExists = function(u) return AGPS_PARTY[u] ~= nil end
      UnitIsUnit = function(a, b) return a == b end
      IsInRaid = function() return false end
      UnitClass = function(u) return "Mage", "MAGE" end
      RAID_CLASS_COLORS = { MAGE = { r = 0.25, g = 0.78, b = 0.92 } }
      AGPS_POS_REAL = UnitPosition
      UnitPosition = function(u)
        local p = AGPS_PARTY[u]
        if p then return p[1], p[2], 0, 0 end
        return AGPS_POS_REAL(u)
      end
    """)
    try:
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        dots = [w for w in lua.eval("AGPS_WIDGETS").values() if w.dot and w._shown]
        assert len(dots) == 1 and dots[0].name == "Tester"  # (the mock's UnitName)
        assert dots[0].dot._tex == "color:0.25,0.78,0.92"  # (the mage's class color, not the fallback)
        st.showParty = False
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert not [w for w in lua.eval("AGPS_WIDGETS").values() if w.dot and w._shown]
    finally:
        st.showParty = True
        lua.execute("AGPS_PARTY = {} UnitPosition = AGPS_POS_REAL")


def test_party_members_show_their_class_icon(game):
    # (asked) a round class icon, not a plain dot: the game's own (atlas), else the class sheet cut to the
    # class; the dot's color only when neither is there
    lua, ns = game
    G = ns.GPS
    lua.execute("""
      AGPS_PARTY = { party1 = { 2260, 300 } }
      UnitExists = function(u) return AGPS_PARTY[u] ~= nil end
      UnitIsUnit = function(a, b) return a == b end
      IsInRaid = function() return false end
      UnitClass = function(u) return "Mage", "MAGE" end
      CLASS_ICON_TCOORDS = { MAGE = { 0.25, 0.5, 0, 0.25 } }
      AGPS_POS_REAL = UnitPosition
      UnitPosition = function(u)
        local p = AGPS_PARTY[u]
        if p then return p[1], p[2], 0, 0 end
        return AGPS_POS_REAL(u)
      end
    """)
    try:
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        (pin,) = [w for w in lua.eval("AGPS_WIDGETS").values() if w.dot and w._shown]
        assert pin.dot._tex == G.CLASS_SHEET
        # (never a filter mode above LINEAR: the client crashes on one, wowmock.lua fails the same way)
        assert pin.dot._filter in (None, "LINEAR")
        # (asked: the icon at a quarter of its art, G.ICON_PX, in a 2-pixel ring; times Icon size, as the map's other
        # icons, asked 2026-11-14 "should match the current icons scale with small/med/large")
        st = ns.settings.gps
        was = st.iconSize
        try:
            for size, k in (("small", 1), ("medium", 1.25), ("large", 1.5), ("xlarge", 2)):
                st.iconSize = size
                lua.execute("AGPS_T = AGPS_T + 1")
                G.Update()
                assert pin._w == round((16 + 2 * 2) * k), (size, pin._w)
        finally:
            st.iconSize = was
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        lua.execute("AGPS_OLD_CT = C_Texture C_Texture = { GetAtlasInfo = function() return {} end }")
        try:
            t = lua.eval("CreateFrame('Frame'):CreateTexture()")
            assert G.ClassIcon(t, "MAGE") and t._atlas == "classicon-mage" and t._filter in (None, "LINEAR")
        finally:
            lua.execute("C_Texture = AGPS_OLD_CT")
        # (asked) round: the icon cut to a circle by the portrait mask, under the round icons' ring drawn at its size
        # (asked 2026-11-14: "do the scaling change for the party icons as well"), in the class's color
        assert pin.dot._masks and pin.dot._masks[1]._tex == G.ROUND_MASK
        assert str(pin.edge.ringTex).startswith(G.ICON_RING) and str(pin.edge._tex).startswith(G.ICON_RING)
    finally:
        lua.execute("AGPS_PARTY = {} UnitPosition = AGPS_POS_REAL CLASS_ICON_TCOORDS = nil")


def _texts(lua):
    return [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text]


def test_a_walk_lists_its_turns_numbered_down_to_the_arrival(game):
    # (asked 2026-11-15, a screenshot: "why is the directions just the current directions at the top of the map and not
    # the list of steps/whole distance?") one walk, no rides: its turns numbered as a trip's legs are, each with how
    # far after the one before; the first 3 and "... n more steps", all of them with the list's "+", the last the
    # arrival
    lua, ns = game
    N, G, st = ns.Nav, ns.GPS, ns.settings.gps
    # (on Durotar's shore: from the water just off it the walk swims, and its pieces are listed as steps instead,
    # test_swim_steps.py)
    lua.execute("AGPS_MAP = 1411; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -56, -5139, 1; AGPS_T = 900")
    N.SetStops(lua.eval("{ { x = 1000, y = -4400, cont = 1, name = 'the Den' } }"), False, "red")
    try:
        for _ in range(40):
            lua.execute("AGPS_T = AGPS_T + 0.6")
            G.Update()
            if N.route and not N.route.pending:
                break
        r = N.route
        assert r and len(N.Steps()) < 2  # (one walk: no legs to list)
        st.stepsCollapsed, st.stepsAll = False, False
        # (2 shown: since 1.4.1's calmer directions this walk has 3 steps, no road joined or left without its turn)
        G.WALK_TURNS_SHOWN = 2
        text, count = G.WalkTurnsText(r, "the Den", False)
        lines = str(text).split("\n")
        assert lines[0].startswith("|cffffffff1. ") and lines[1].startswith("|cffb0b0b02. "), lines
        assert count and count > 2 and len(lines) == 3 and ("more step" in lines[2] or "more turns" in lines[2]), lines
        everything, n = G.WalkTurnsText(r, "the Den", True)
        rows = str(everything).split("\n")
        assert len(rows) == n == count and rows[-1].startswith(f"|cffb0b0b0{n}. Arrive at the Den in "), rows
        # (the panel: the list in it, the "+" for all of them)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Redraw()
        G.Update()
        assert any(t.startswith("|cffb0b0b02. ") for t in _texts(lua) if "\n" not in t) or             any("|cffb0b0b02. " in t for t in _texts(lua))
        assert G.stepsMore._shown
    finally:
        G.WALK_TURNS_SHOWN = 3
        st.stepsAll = False
        N.Clear()


def test_the_options_window_builds_with_its_performance_page(game):
    # (asked) a Performance page in the options: lighter settings for low-end PCs, a preset for them
    # and back; the whole window built under the game's Lua 5.1 (a failure there: no options window)
    lua, ns = game
    ns.Options.Show()
    texts = _texts(lua)
    for label in ("Performance", "Use Low-End Settings", "Restore Defaults", "Map redraws per second",
                  "Work out a route you've left at most every", "Gentle background work", "Turn the arrow every frame",
                  "Other settings to improve performance"):
        assert label in texts, label
    # (asked) the stops routed ahead on the Performance page only, not Routing's too
    assert texts.count("Stops routed and drawn ahead") == 1


def test_section_notes_in_the_options_wrap_to_the_page(game):
    # (seen 2026-10-03: "Unticked ones are never used in routes. Right-clicking a dock on the map does the" ran off the
    # page) every section's note is as wide as the page and wraps
    lua, ns = game
    ns.Options.Show()
    notes = [w for w in lua.eval("AGPS_WIDGETS").values()
             if w._kind == "FontString" and str(w._text).startswith("Unticked ones are never used in routes")]
    assert notes and notes[0]._w and notes[0]._w > 300


def test_the_options_pages_in_order(game):
    # (asked) the options' pages in this order; Help says a /reload saves every edit before copying
    lua, ns = game
    ns.Options.Show()
    # (asked later: the road and wall tools' pages one "Tools" page; 1.2.0, asked 2026-11-10: the pages by what a
    # player wants to do, Help improve part of Help: test_options.py)
    order = ["General", "Map", "Map icons", "GPS Map", "Opacity", "Routing",
             "Directions", "Keys and buttons", "Performance", "Tools", "Help"]
    ws = lua.eval("AGPS_WIDGETS")
    ws = [ws[i] for i in range(1, len(ws) + 1)]  # (in the order made)
    # (the list on the left: a button per page, its name a font string on it)
    tabs = [str(w._text) for w in ws if w._kind == "FontString" and w._parent and w._parent._kind == "Button"
            and str(w._text) in order]
    assert tabs == order
    notes = [str(w._text) for w in ws if "/reload" in str(w._text) and "Copy Map Data" in str(w._text)]
    assert notes, "the note on Help"


def test_low_end_settings_and_back(game):
    lua, ns = game
    O, st, N = ns.Options, ns.settings.gps, ns.Nav
    try:
        O.UseLowEnd()
        for k in ("hz", "rerouteSeconds", "stopsAhead", "gentleBackground", "arrowHz"):
            assert st[k] == O.LOW_END[k], k
        assert O.IsLowEnd()
        assert st.hz < 20 and st.stopsAhead < 3 and st.gentleBackground and st.arrowHz > 0
        O.PerfDefaults()
        for k in ("hz", "rerouteSeconds", "stopsAhead", "gentleBackground", "arrowHz"):
            assert st[k] == ns.DEFAULTS.gps[k], k
        assert not O.IsLowEnd()
    finally:
        O.PerfDefaults()


def _frames(lua, seconds, fps=60, move=None):
    """The game's frames: every OnUpdate script run, `seconds` of them at `fps`."""
    lua.execute("""
      AGPS_TICK = function(dt)
        for _, w in pairs(AGPS_WIDGETS) do
          local f = w._scripts and w._scripts.OnUpdate
          if f then f(w, dt) end
        end
      end
    """)
    tick = lua.eval("AGPS_TICK")
    t = float(lua.eval("AGPS_T"))
    for i in range(int(seconds * fps)):
        t += 1 / fps
        lua.execute(f"AGPS_T = {t}")
        if move:
            move(i)
        tick(1 / fps)


def test_the_map_redraws_at_most_as_often_as_set(game):
    # (Performance: "Map redraws per second") moving, the map redraws that many times a second, no more
    lua, ns = game
    st = ns.settings.gps
    lua.execute("""
      AGPS_REDRAWS = 0
      local update = AGPS_NS.GPS.Update
      AGPS_NS.GPS.Update = function(...) AGPS_REDRAWS = AGPS_REDRAWS + 1 return update(...) end
    """)
    x = [2254.0]

    def run(i):
        x[0] -= 0.12
        lua.execute(f"AGPS_POS[1] = {x[0]}")
    zoom, glide = st.zoom, ns.GPS.GLIDE_HZ
    try:
        # (the move alone waits for G.GLIDE_HZ while the layers glide, issue #316: test_walking_zoomed_in_on_a_long_off_
        # road_leg_redraws_at_the_glide_rate; here the cap is what's tested)
        ns.GPS.GLIDE_HZ = 1000
        st.zoom = 100.0  # (in close: every frame's move is over half a pixel, G.MoveStep; the cap is what's tested)
        counts = {}
        for hz in (20, 10, 5):
            st.hz = hz
            _frames(lua, 0.2, move=run)  # (settled)
            # (background searches left by earlier tests finish on the real clock, and each one done forces a redraw
            # (G.PumpSearches): finished first, or the count depended on the machine's speed, 2026-10-06)
            lua.execute("""
              local R = AGPS_NS.Router
              for _ = 1, 1000 do
                if not R.HasWork() then break end
                R.Pump(debugprofilestop() + 1000, debugprofilestop)
              end
            """)
            lua.execute("AGPS_REDRAWS = 0")
            _frames(lua, 3, move=run)
            counts[hz] = int(lua.eval("AGPS_REDRAWS"))
        for hz, n in counts.items():
            assert hz * 3 * 0.8 <= n <= hz * 3 + 1, (hz, n)
    finally:
        st.hz = ns.DEFAULTS.gps.hz
        st.zoom = zoom
        ns.GPS.GLIDE_HZ = glide
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")


def test_the_arrow_turns_every_frame_or_as_often_as_set(game):
    # (Performance: "Turn the arrow every frame") off: 20 times a second, whatever the frame rate. (Turning: a still
    # player's arrow is looked at A.IDLE_HZ, test_a_still_players_arrow_and_map_frame_checks_run_less_often)
    lua, ns = game
    st = ns.settings.gps
    lua.execute("GetPlayerFacing = function() return AGPS_T % 6 end")

    def turns(seconds):
        p = ns.perf["arrow window"]
        n0 = p.n if p else 0
        _frames(lua, seconds, fps=100)
        return ns.perf["arrow window"].n - n0
    try:
        st.arrowHz = 0
        assert turns(1) >= 95
        st.arrowHz = 20
        n = turns(2)
        assert 36 <= n <= 41, n
    finally:
        lua.execute("GetPlayerFacing = function() return 0 end")
        st.arrowHz = ns.DEFAULTS.gps.arrowHz


def test_gentle_background_work_takes_smaller_slices(game):
    # (Performance: "Gentle background work") smaller slices of each frame for the searches and the
    # road data being built (smoother on a slow PC, done a little later)
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    try:
        st.gentleBackground = False
        assert G.PumpBudget(16, False) == 1
        assert G.PumpBudget(40, False) == 1
        # (issue #316: keeping a route up, no more ms a second at 144 frames a second than at 60)
        assert G.PumpBudget(1000 / 144, False) * 144 == pytest.approx(1000 / 16)
        assert G.PumpBudget(40, True) == G.WARM_MS  # (the road data: up to 5 ms, a quarter of the frame)
        assert G.PumpBudget(8, True) == 2
        st.gentleBackground = True
        assert G.PumpBudget(16, False) == G.GENTLE_MS < 1
        assert G.PumpBudget(40, True) == G.GENTLE_WARM_MS < G.WARM_MS
        assert G.PumpBudget(4, True) == G.GENTLE_MS  # (a tenth of a fast frame is less than the least)
    finally:
        st.gentleBackground = False


def test_a_route_left_is_worked_out_again_as_often_as_set(game):
    # (Performance: "Work out a route you've left at most every") off the route, it's worked out
    # again from the player at most that often (less work; it catches up a little later)
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps

    def recalcs(secs):
        st.rerouteSeconds = secs
        N.SetStops(lua.eval("{ { x = 1600, y = 240, cont = 0, name = 'Ruins' } }"), False, "red")
        t = float(lua.eval("AGPS_T")) + 60
        lua.execute(f"AGPS_T = {t}")
        x, y = 2254.0, 293.0
        assert N.Route(x, y, 0)
        n0 = ns.perf["route calculation"].n
        for k in range(24):  # (12 s drifting sideways off the route, 40 yd every half second)
            t += 0.5
            y += 40
            lua.execute(f"AGPS_T = {t}; AGPS_POS[1], AGPS_POS[2] = {x}, {y}")
            N.Route(x, y, 0)
        return ns.perf["route calculation"].n - n0
    try:
        often, seldom = recalcs(2), recalcs(6)
        assert 5 <= often <= 7, often
        assert 1 <= seldom <= 2, seldom
    finally:
        st.rerouteSeconds = ns.DEFAULTS.gps.rerouteSeconds
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")


def test_the_performance_page_tells_the_addons_share_of_the_time(game):
    lua, ns = game
    O = ns.Options
    assert O.UsageText() == "AzerothGPS's work: measuring..."
    assert O.UsageText(200, 10) == "AzerothGPS's work: 20.0 ms a second, 2.0% of the time"
    # (only the timings that don't overlap: a redraw's parts are in it already)
    lua.execute("""
      local p = AGPS_NS.perf
      AGPS_SAVED = p
      AGPS_NS.perf = {
        redraw = { total = 10 }, ["redraw: icons"] = { total = 4 }, ["arrow window"] = { total = 2 },
        ["terrain search"] = { total = 3 }, ["router: build roads"] = { total = 3 }, ["route calculation"] = { total = 5 },
      }
    """)
    try:
        assert ns.PerfTotal() == 15
    finally:
        lua.execute("AGPS_NS.perf = AGPS_SAVED")


def test_ironforge_s_roads_show_on_its_inside_map(game):
    # (reported: drawn roads over Ironforge showed on the mountain in the outside view, and went once
    # the map showed the city's inside) a capital's inside map is its streets: its roads show there
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_ROADS = 0
      local lay = AGPS_NS.GPS.LayoutRoads
      AGPS_NS.GPS.LayoutRoads = function(...) AGPS_ROADS = AGPS_ROADS + 1 return lay(...) end
      AGPS_INDOORS_REAL = IsIndoors
      IsIndoors = function() return true end
      AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -4840.0, -1100.0, 0
    """)
    zoom = st.zoom
    try:
        st.showRoads, st.zoom = True, 200.0
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.inside is not None  # (the city's inside map shown)
        assert lua.eval("AGPS_ROADS") > 0
    finally:
        st.showRoads, st.zoom = False, zoom
        lua.execute("IsIndoors = AGPS_INDOORS_REAL AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")


def test_capitals_show_their_districts_names(game):
    # (asked: like Undercity's Trade Quarter, the other capitals' districts named on the map) zoomed in on
    # Stormwind (terrain view, no inside map there): "Trade District" and the others as place labels
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    names = {str(l[3]) for l in ns.CityLabels[0].values()} | {str(l[3]) for l in ns.CityLabels[1].values()}
    for n in ("Trade District", "Old Town", "The Drag", "Valley of Strength", "Tinker Town"):
        assert n in names, n
    assert any("Rise" in n for n in names)  # (Thunder Bluff's, from the ground's subzones)
    assert "Stormwind City" not in names and "Orgrimmar" not in names
    pois = lua.table()
    G.CityLabelPois(pois, 0, -8832.0, 625.0, 0, 1.0, 200.0, 300.0)
    near = [str(pois[i][4]) for i in range(1, len(pois) + 1)]
    assert "Trade District" in near
    pois = lua.table()
    G.CityLabelPois(pois, 0, -8832.0, 625.0, 0, 0.1, 200.0, 2000.0)
    assert len(pois) == 0  # (zoomed far out: none)


def test_a_zeppelin_dock_that_is_a_stop_still_shows_its_timer(game):
    # (asked) a stop on a dock hid the dock with its icon, and its countdown went with it: the countdown
    # stays under the stop's marker
    import math
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    brill = (2254.0, 293.0)
    docks = [(math.hypot(t[2 + 3 * k] - brill[0], t[3 + 3 * k] - brill[1]), t[2 + 3 * k], t[3 + 3 * k])
             for t in ns.Transports.values() for k in (0, 1) if t[8] == "zeppelin" and t[1 + 3 * k] == 0]
    _, x, y = min(docks)
    lua.execute("AGPS_TT = AGPS_NS.Taxi.TransportTimes AGPS_NS.Taxi.TransportTimes = function() return 130, 200, 10 end")
    zoom = st.zoom

    def shown():  # (that dock's button: its timer, its icon; a tower has a dock for each zeppelin)
        b = [w for w in lua.eval("AGPS_WIDGETS").values() if w.dock and w._shown and w.wx == x and w.wy == y]
        if not b:
            return False, None
        return bool(b[0].timer and b[0].timer._shown and b[0].timer._text == "2:10"), bool(b[0].icon._shown)

    try:
        st.zoom = 900.0
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert shown() == (True, True)
        N.SetStops(lua.eval(f"{{ {{ x = {x}, y = {y}, cont = 0, name = 'Zeppelin', tex = 'Interface\\AddOns\\AzerothGPS\\Media\\Zeppelin' }} }}"))
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert shown() == (True, False)  # (its countdown under the stop's marker; its icon hidden there)
    finally:
        st.zoom = zoom
        N.Clear()
        lua.execute("AGPS_NS.Taxi.TransportTimes = AGPS_TT AGPS_T = AGPS_T + 1")


def test_a_docks_countdown_still_ticks_while_the_icon_gather_is_skipped(game):
    # (the 2026-10-07 draw profile: every ICON_REFRESH the same icons were gathered and placed again, the docks'
    # countdowns the only live content) with the signature unchanged the gather is skipped (ICON_FULL_REFRESH),
    # and the countdown under the dock still ticks (G.RefreshDockTimers)
    import math
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    brill = (2254.0, 293.0)
    docks = [(math.hypot(t[2 + 3 * k] - brill[0], t[3 + 3 * k] - brill[1]), t[2 + 3 * k], t[3 + 3 * k])
             for t in ns.Transports.values() for k in (0, 1) if t[8] == "zeppelin" and t[1 + 3 * k] == 0]
    _, x, y = min(docks)
    # (the arrival counts down with the test's clock, so a refresh shows a new time)
    lua.execute("AGPS_T0 = AGPS_T AGPS_TT = AGPS_NS.Taxi.TransportTimes "
                "AGPS_NS.Taxi.TransportTimes = function() return 130 - math.floor(AGPS_T - AGPS_T0), 200, 10 end")
    lua.execute("AGPS_POIS = { n = 0 } AGPS_REALP = AGPS_NS.GPS.LayoutPois "
                "AGPS_NS.GPS.LayoutPois = function(...) AGPS_POIS.n = AGPS_POIS.n + 1 return AGPS_REALP(...) end")
    zoom = st.zoom

    def timer_text():
        b = [w for w in lua.eval("AGPS_WIDGETS").values() if w.dock and w._shown and w.wx == x and w.wy == y]
        assert b and b[0].timer and b[0].timer._shown
        return b[0].timer._text

    try:
        st.zoom = 900.0
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert timer_text() == "2:09"  # (130 - 1)
        n0 = lua.eval("AGPS_POIS.n")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert lua.eval("AGPS_POIS.n") == n0  # (nothing changed: no gather)
        assert timer_text() == "2:08"  # (the countdown ticked anyway)
    finally:
        st.zoom = zoom
        N.Clear()
        lua.execute("AGPS_NS.Taxi.TransportTimes = AGPS_TT AGPS_NS.GPS.LayoutPois = AGPS_REALP AGPS_T = AGPS_T + 1")


def test_the_laid_layers_slide_with_the_player_between_redraws(game):
    # (reported 2026-10-07: boats and flight-path icons hopped every few seconds while the route's lines
    # slid smoothly under them) the laid tile and icon layers glide with the player every frame
    # (G.GlidePan in the frame's OnUpdate), not only at redraws: panning is as smooth as the frame rate
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    frame = lua.globals().AzerothGPSFrame
    hz, zoom, x0 = st.hz, st.zoom, float(lua.eval("AGPS_POS[1]"))
    try:
        N.Clear()
        G.ClearEdges()  # (a walls outline still worked out from an earlier test: its redraw as it ends isn't a glide's)
        st.zoom = 420.0
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()  # (tiles and icons laid at the player's spot)
        st.hz = 1  # (a redraw a second at most: the frames below glide with no redraw between)
        offs = []
        for k in range(6):
            lua.execute(f"AGPS_POS[1] = {x0 + 2.0 * (k + 1)} AGPS_T = AGPS_T + 0.05")
            frame._scripts.OnUpdate(frame, 0.05)
            offs.append((G.quadLayer._pt[4], G.quadLayer._pt[5], G.poiLayer._pt[4], G.poiLayer._pt[5]))
        # (the first tick may absorb a pending redraw, laying the layers afresh at zero: from the second
        # on, every frame slides both layers — world +x is the screen's y axis here)
        for a, b in zip(offs[1:], offs[2:]):
            assert b[1] < a[1] and b[3] < a[3], (a, b)
            assert abs(b[0] - b[2]) < 0.01 and abs(b[1] - b[3]) < 0.01  # (laid at one center: together)
    finally:
        st.hz, st.zoom = hz, zoom
        lua.execute(f"AGPS_POS[1] = {x0} AGPS_T = AGPS_T + 1")
        G.Update()


def test_walking_zoomed_in_on_a_long_off_road_leg_redraws_at_the_glide_rate(game):
    # (issue #316, QA c116-rt-c: from Brill's square to the Agamand Family Crypt's hills, zoomed in to 60, walked for
    # 30 s: 120-130 ms a second of AzerothGPS's work in the game against a limit of 50, the map redrawn 20 times a
    # second for the player's move alone, every redraw 4-10 ms there) while the layers glide with the player
    # (G.GlidePan), a redraw for the move and the turn alone waits for G.GLIDE_HZ; the arrow turns every frame; anything
    # else (here the zoom) still redraws at once
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    frame = lua.globals().AzerothGPSFrame
    zoom, hz = st.zoom, st.hz
    x0, y0 = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    lua.execute("AGPS_REAL_FACING, AGPS_FACING = GetPlayerFacing, 0 GetPlayerFacing = function() return AGPS_FACING end")
    fps = 60

    def tick(x=None, y=None, facing=None):
        set_pos = f"AGPS_POS[1], AGPS_POS[2] = {x}, {y} " if x is not None else ""
        set_face = f"AGPS_FACING = {facing} " if facing is not None else ""
        lua.execute(f"{set_pos}{set_face}AGPS_T = AGPS_T + {1 / fps}")
        frame._scripts.OnUpdate(frame, 1 / fps)

    def redraws():
        p = ns.perf["redraw"]
        return p.n if p else 0

    try:
        st.hz = 20
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2300.0, 300.0 AGPS_T = AGPS_T + 1")
        G.Follow()
        G.SetZoom(60)
        N.SetStops(lua.eval("{ { x = 2867, y = 792, cont = 0, name = 'Hills' } }"), False, "red")
        for _ in range(30):
            tick()
        r = N.route
        assert r and r.totalYards > 1000
        assert any(k != 0 for k in r.kinds.values())  # (a leg off the roads: dotted)
        # walking toward the stop at 7 yd a second, turning a little this way and that as a tester steers
        x, y, n0, secs = 2300.0, 300.0, redraws(), 10
        d = math.hypot(2867 - x, 792 - y)
        ux, uy = (2867 - x) / d, (792 - y) / d
        base = math.atan2(-uy, ux)  # (the game's facing: 0 north, counter-clockwise)
        arrow = G.MapArrow()
        for k in range(fps * secs):
            x, y = x + ux * 7 / fps, y + uy * 7 / fps
            f = base + 0.2 * math.sin(k / 9)
            tick(x, y, f)
            assert arrow.agpsRot == pytest.approx(f)  # (turned this very frame, redraw or not)
        per_s = (redraws() - n0) / secs
        assert G.GLIDE_HZ - 1 <= per_s <= G.GLIDE_HZ + 1, per_s  # (20 a second before)
        # a zoom is no move alone: drawn on the next frame
        n1 = redraws()
        G.SetZoom(80)
        tick(x + ux * 7 / fps, y + uy * 7 / fps)
        assert redraws() == n1 + 1
    finally:
        N.Clear()
        st.zoom, st.hz = zoom, hz
        lua.execute(f"GetPlayerFacing = AGPS_REAL_FACING AGPS_POS[1], AGPS_POS[2] = {x0}, {y0} AGPS_T = AGPS_T + 1")
        G.Update()


def test_the_stops_marks_stay_on_their_world_spot_every_frame(game):
    # (reported twice 2026-10-07: "the boats and flight path icons are repositioning every 2-3 secs while
    # moving", "the destination icons are jumping during routing as well") the stops', rides' and detours'
    # pins were placed each redraw round the view's center but anchored to the icon layer, which carries its
    # own pan (up to ICON_PAN_PX): they moved twice, ahead of the map, until each re-gather put them back.
    # Now they hang off G.markLayer: on their world spot at every redraw AND every frame between
    lua, ns = game
    G, N, Geo, st = ns.GPS, ns.Nav, ns.Geo, ns.settings.gps
    frame = lua.globals().AzerothGPSFrame
    hz, zoom = st.hz, st.zoom
    x0, y0 = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    wx, wy = x0 + 150.0, y0 + 60.0

    def pin():
        b = [w for w in lua.eval("AGPS_WIDGETS").values() if w.stopIndex == 1 and w._shown]
        assert len(b) == 1
        return b[0]

    def absolute(b):  # (where its BOTTOM sits, from the canvas's middle: its anchor's offset + its own)
        pt = b._pt
        a = pt[2]._pt
        ax, ay = (a[4] or 0, a[5] or 0) if a and a[1] == "CENTER" else (0, 0)
        return ax + pt[4], ay + pt[5]

    def fresh():  # (its world spot projected from where the player is now: north-up, the view on them)
        px, py = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
        vx, vy, vcont, vrot, vs, vhalf = G.ViewState()
        s = vhalf / st.zoom
        dx, dy = Geo.ScreenOffset(px, py, wx, wy)
        x, y = Geo.Rotate(dx * s, dy * s, 0)
        return x, y - 4

    try:
        N.Clear()
        st.zoom = 420.0
        N.SetStops(lua.eval(f"{{ {{ x = {wx}, y = {wy}, cont = 0, name = 'mark' }} }}"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        # walking with the redraws: the icon layer pans between its re-gathers, the pin mustn't ride it
        for k in range(8):
            lua.execute(f"AGPS_POS[2] = {y0 + 3.0 * (k + 1)} AGPS_T = AGPS_T + 0.1")
            G.Update()
            (ax, ay), (fx, fy) = absolute(pin()), fresh()
            assert abs(ax - fx) < 0.6 and abs(ay - fy) < 0.6, (k, (ax, ay), (fx, fy), G.poiLayer._pt[4], G.poiLayer._pt[5])
        # frames between redraws (one a second at most): it glides with the map
        st.hz = 1
        for k in range(6):
            lua.execute(f"AGPS_POS[2] = {y0 + 24 + 2.0 * (k + 1)} AGPS_T = AGPS_T + 0.05")
            frame._scripts.OnUpdate(frame, 0.05)
            (ax, ay), (fx, fy) = absolute(pin()), fresh()
            assert abs(ax - fx) < 0.6 and abs(ay - fy) < 0.6, ("glide", k, (ax, ay), (fx, fy))
    finally:
        st.hz, st.zoom = hz, zoom
        N.Clear()
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x0}, {y0} AGPS_T = AGPS_T + 1")
        G.Update()


@pytest.mark.timing
def test_the_first_route_shown_off_teldrassil_takes_the_teleporter():
    # (reported 2026-10-07: "Still getting path off Teldrassil without taking portal... after about 20
    # secs the route just corrected", then after a first fix "corrects after a few seconds now but still
    # initially showing incorrect") from the top of the tree every way down is the Darnassus teleporter, so
    # NO route shown, first or later, may leave without it. Two ways the walk down the side was drawn:
    # provisional while its walk searches ran (a 984-yd straight piece, pending), and once that search had
    # failed earlier in the session, settled straight while the ride check was still out (the planner kept
    # the blocked walk as weighing least; only the check found the teleporter faster). The planner takes neither:
    # a walk still searched is judged by its line (N.ProvisionalBlockedYards) and never kept (N.walkKept) for it.
    # A harness of its own for each case: the module's shared one carries other tests' searches, which hid the
    # second case.
    import time
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    clock = lambda: time.perf_counter() * 1000.0
    # (to Rut'theran's dock, and on to Darkshore by the boat: there the plan rides anyway, and walked down the side to it)
    dests = ((8532.0, 1023.7, "the dock"), (5888.0, -831.0, "Darkshore"))
    for (sx, sy), (dx, dy, dname), warmed in [(st, de, w) for st in ((9821.0, 960.0), (10197.5, 2380.0))  # (Dolanaar; Darnassus)
                                              for de in dests for w in (False, True)]:
        if True:
            lua, ns = start()
            G, N, R = ns.GPS, ns.Nav, ns.Router
            ns.CharDB().faction = "Alliance"  # (the stand-in player is Horde; the teleporter is Alliance's)
            N.FlightsChanged()
            R.WARM, R.SYNC_WALKS = True, False  # (game mode: routes and walks in the background)
            if warmed:  # (the walk down routed earlier in the session, as the ride check routes it: its search failed)
                R.Route(1, sx, sy, dx, dy, lua.table(offroad=False))
                while R.HasWork():
                    R.Pump(clock() + 50, clock)
            lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = %f, %f, 1" % (sx, sy))
            N.SetStops(lua.eval("{ { x = %f, y = %f, cont = 1, name = '%s' } }" % (dx, dy, dname)), False, "red")
            shown = 0
            # (up to 200 s of game time: the first route comes after about 430 frames of 5 ms here, and a loaded CI
            # runner showed none by 600; every route shown is checked, however late)
            for f in range(2000):
                lua.execute("AGPS_T = AGPS_T + 0.1")
                G.Update()
                R.Pump(clock() + 5, clock)
                r = N.route
                if r is not None:
                    shown += 1
                    legs = [leg.ride[8] if leg.ride is not None else "walk" for leg in r.legs.values()]
                    assert "teleporter" in legs, ((sx, sy), dname, warmed, f, legs, "a route off the tree without the teleporter")
                    if not r.pending and not R.HasWork():
                        break
            assert shown, ((sx, sy), dname, warmed, "no route was ever shown")
            # (each harness holds a continent's routing graph: freed here, not collected in the middle of a
            # later test's timed slice — the frame-budget tests measure wall time)
            del lua, ns, G, N, R, r
            import gc
            gc.collect()


def test_zoomed_out_a_move_under_a_pixel_doesnt_redraw_the_map(game):
    # (reported 2026-11-13: 30% CPU spikes walking with the map in the world map and the square on) a tenth of a yard
    # moved counted as a new view: zoomed out to 4-5 yd a pixel both maps redrew their whole route at their full rate
    # while walking. Now a move counts from half a pixel at the zoom drawn (G.MoveStep).
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    zoom = st.zoom
    lua.execute("""
      AGPS_REDRAWS = 0
      AGPS_UPD_REAL = AGPS_NS.GPS.Update
      AGPS_NS.GPS.Update = function(...) AGPS_REDRAWS = AGPS_REDRAWS + 1 return AGPS_UPD_REAL(...) end
    """)
    x = [2254.0]

    def run(i):
        x[0] -= 0.12  # (7 yd a second at 60 frames)
        lua.execute(f"AGPS_POS[1] = {x[0]}")
    try:
        assert G.MoveStep(None) == 0.1 and G.MoveStep(10.0) == 0.1  # (zoomed in: a tenth of a yard, as before)
        assert G.MoveStep(0.05) == 10.0
        st.zoom = 6000.0
        _frames(lua, 0.5, move=run)  # (settled at that zoom)
        lua.execute("""
          local R = AGPS_NS.Router
          for _ = 1, 1000 do
            if not R.HasWork() then break end
            R.Pump(debugprofilestop() + 1000, debugprofilestop)
          end
        """)
        lua.execute("AGPS_REDRAWS = 0")
        _frames(lua, 3, move=run)
        n = int(lua.eval("AGPS_REDRAWS"))
        # 21 yd walked at many yards a pixel: a few redraws, not 20 a second
        assert n <= 8, n
    finally:
        lua.execute("AGPS_NS.GPS.Update = AGPS_UPD_REAL")
        st.zoom = zoom
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")


def test_a_quiet_idle_map_redraws_every_few_seconds_not_every_second(game):
    # (the 2026-10-07 idle profile: a full redraw every second with no route and nothing moving on the map)
    # with no route or stop, no dock countdown, no party dots and the mouse off it, the idle redraw waits
    # REDRAW_IDLE_QUIET; with a route too (issue #191), only the directions panel's text refreshed every second (ETAs)
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    frame = lua.globals().AzerothGPSFrame
    zoom = st.zoom
    try:
        N.Clear()
        st.zoom = 200.0  # (in close: no dock countdowns in view)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        G.QuietIdle()  # (settles the layers signature)
        assert G.QuietIdle() is True
        lua.execute("AGPS_UPD = { n = 0 } AGPS_UPD_REAL = AGPS_NS.GPS.Update\n"
                    "AGPS_NS.GPS.Update = function(...) AGPS_UPD.n = AGPS_UPD.n + 1 return AGPS_UPD_REAL(...) end")
        for _ in range(30):  # (3 s standing still)
            lua.execute("AGPS_T = AGPS_T + 0.1")
            frame._scripts.OnUpdate(frame, 0.1)
        quiet = lua.eval("AGPS_UPD.n")
        assert quiet <= 1, quiet  # (stretched: not one a second)
        N.SetStops(lua.eval("{ { x = 2600.0, y = 293.0, cont = 0, name = 's' } }"), False, "red")
        for _ in range(100):  # (the route worked out and drawn, settled)
            lua.execute("AGPS_T = AGPS_T + 0.1")
            frame._scripts.OnUpdate(frame, 0.1)
        assert N.route is not None
        lua.execute("AGPS_PANEL = { n = 0 } AGPS_PANEL_REAL = AGPS_NS.GPS.UpdateNavPanel "
                    "AGPS_NS.GPS.UpdateNavPanel = function(...) AGPS_PANEL.n = AGPS_PANEL.n + 1 "
                    "return AGPS_PANEL_REAL(...) end")
        before = lua.eval("AGPS_UPD.n")
        for _ in range(30):  # (3 s standing still with the route)
            lua.execute("AGPS_T = AGPS_T + 0.1")
            frame._scripts.OnUpdate(frame, 0.1)
        with_route = lua.eval("AGPS_UPD.n") - before
        assert with_route <= 1, with_route  # (a route as drawn: no full redraw a second)
        assert lua.eval("AGPS_PANEL.n") >= 2, lua.eval("AGPS_PANEL.n")  # (its text still every second: the ETAs)
        # (the route changed: drawn again at once)
        N.Invalidate()
        lua.execute("AGPS_T = AGPS_T + 0.1")
        frame._scripts.OnUpdate(frame, 0.1)
        for _ in range(20):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            frame._scripts.OnUpdate(frame, 0.1)
        assert lua.eval("AGPS_UPD.n") - before > with_route
    finally:
        lua.execute("if AGPS_PANEL_REAL then AGPS_NS.GPS.UpdateNavPanel = AGPS_PANEL_REAL end")
        lua.execute("AGPS_NS.GPS.Update = AGPS_UPD_REAL")
        st.zoom = zoom
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()


def test_a_still_maps_tiles_arent_laid_again(game):
    # (issue #191: an idle redraw laid the same tiles again every TILE_REFRESH, 4.4 ms of a 5 ms redraw) the view where
    # the tiles were laid: kept TILE_REFRESH_STILL; moved, laid again as before
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    zoom = st.zoom
    same = lua.eval("function(a, b) return rawequal(a, b) end")
    try:
        N.Clear()
        st.zoom = 200.0
        G.Redraw()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        lt = G.laidTiles
        assert lt is not None
        for _ in range(3):  # (idle redraws 5 s apart, standing still)
            lua.execute("AGPS_T = AGPS_T + 5")
            G.Update()
            assert same(G.laidTiles, lt)
        lua.execute("AGPS_T = AGPS_T + %f" % (G.TILE_REFRESH_STILL + 1))
        G.Update()
        assert not same(G.laidTiles, lt)  # (refreshed in the end)
    finally:
        st.zoom = zoom
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()


def test_a_still_players_arrow_and_map_frame_checks_run_less_often(game):
    # (issue #191: the arrow and the map's fade and tooltip checks ran every frame with nothing moving) standing still
    # with a route, a second at 60 frames: the arrow looked at about A.IDLE_HZ times, the fade checks every
    # SETTLED_EVERY; a turn is looked at on the next frame
    lua, ns = game
    N, G, A = ns.Nav, ns.GPS, ns.Arrow
    af = lua.globals().AzerothGPSArrow
    frame = lua.globals().AzerothGPSFrame
    try:
        N.SetStops(lua.eval("{ { x = 2600.0, y = 293.0, cont = 0, name = 's' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        af._scripts.OnUpdate(af, 0.3)
        af._scripts.OnUpdate(af, 0.3)  # (the second look sees the player still)
        assert A.still
        perf = ns.perf
        def runs(name):
            p = perf[name]
            return p.n if p is not None else 0
        a0, f0 = runs("arrow window"), runs("every frame: fade, tooltip")
        for _ in range(60):
            lua.execute("AGPS_T = AGPS_T + 1/60")
            af._scripts.OnUpdate(af, 1 / 60)
            frame._scripts.OnUpdate(frame, 1 / 60)
        arrow_runs, fade_runs = runs("arrow window") - a0, runs("every frame: fade, tooltip") - f0
        assert arrow_runs <= A.IDLE_HZ + 1, arrow_runs
        assert fade_runs <= 1 / G.SETTLED_EVERY + 1, fade_runs
        lua.execute("GetPlayerFacing = function() return 0.7 end")  # (a turn)
        a1 = runs("arrow window")
        af._scripts.OnUpdate(af, 1 / 60)
        assert runs("arrow window") == a1 + 1  # (at once)
    finally:
        lua.execute("GetPlayerFacing = function() return 0 end")
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()


def test_event_handlers_and_other_frames_are_timed_without_counting_twice(game):
    # (issue #191: the Performance page's figure left out the event handlers and the other OnUpdates) each is a top
    # timing of its own (PERF_TOP), and a top timing run inside one isn't counted in it too
    lua, ns = game
    top = set(lua.eval("AGPS_NS.PERF_TOP").values())
    for name in ("events (core)", "events (quests, NPCs, herbs and ore)", "events (routes)", "map frame, other work",
                 "pump frame (map hidden)", "map text"):
        assert name in top, name
    lua.execute("""
      local ns = AGPS_NS
      local spin = function(ms) local t = debugprofilestop() while debugprofilestop() - t < ms do end end
      AGPS_TIMED = ns.Timed("test outer", function()
        local t0 = ns.PerfStart()
        spin(30)
        ns.PerfEnd("redraw", t0)
        spin(5)
      end)
      AGPS_TIMED()
    """)
    p = ns.perf["test outer"]
    assert p.n == 1
    assert p.total < 20, p.total  # (its own 5 ms, not the redraw's 30)


def test_the_arrow_isnt_set_again_while_nothing_changes(game):
    # (the 2026-10-07 idle profile: with arrowHz 0 the arrow's rotation, color and jump icon were set every
    # frame unchanged, most of the arrow's cost) running straight, nothing is set again; a turn sets it at once
    lua, ns = game
    N, G, A = ns.Nav, ns.GPS, ns.Arrow
    af = lua.globals().AzerothGPSArrow
    try:
        N.SetStops(lua.eval("{ { x = 2600.0, y = 293.0, cont = 0, name = 's' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert N.route is not None
        af._scripts.OnUpdate(af, 0.3)  # (the first look: the arrow set)
        lua.execute("AGPS_ROT = { n = 0 }")
        A.arrowTex.SetRotation = lua.eval("function(s, r) AGPS_ROT.n = AGPS_ROT.n + 1 end")
        for _ in range(5):
            af._scripts.OnUpdate(af, 0.016)
        assert lua.eval("AGPS_ROT.n") == 0  # (still running the same way: nothing set)
        lua.execute("GetPlayerFacing = function() return 0.7 end")  # (a turn)
        af._scripts.OnUpdate(af, 0.016)
        assert lua.eval("AGPS_ROT.n") == 1  # (set at once)
    finally:
        lua.execute("GetPlayerFacing = function() return 0 end")
        A.arrowTex.SetRotation = None
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()


_ARROW_KEYS = ("arrowSnap", "arrowSide", "arrowShown", "dirShown", "dirStopsOnly", "arrowPx", "dirTextScale", "arrowLocked", "dirLocked", "dirPoint",
               "dirSize", "arrowFreePoint", "arrowPoint", "arrowSize", "arrowBg", "dirBg")


def _arrow_settings(st):
    # (the arrow's settings as they were, for the test's end; the defaults meanwhile)
    saved = {k: st[k] for k in _ARROW_KEYS}
    st.arrowSnap, st.arrowSide, st.dirShown, st.dirStopsOnly = True, "left", True, False
    st.arrowShown = True
    st.arrowPx, st.dirTextScale, st.arrowLocked, st.dirLocked = 58, 1, True, True
    return saved


def _arrow_restore(ns, saved):
    for k, v in saved.items():
        ns.settings.gps[k] = v
    ns.Arrow.Apply()


def test_the_arrow_and_the_directions_are_two_panels_snapped_on_a_side(game):
    # (asked 2026-10-30: "separate these into two separate panels, one for arrow and another for direction... an option to
    # snap together and which side the arrow goes") snapped, the arrow against the directions' side, as tall or as wide
    # as them, the pair kept on the screen as one (the directions' clamp takes the arrow's side in); apart, each its own
    lua, ns = game
    A, st = ns.Arrow, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections
    same = lua.eval("function(a, b) return rawequal(a, b) end")
    assert same(A.frame, af) and same(A.dir, dirf)
    saved = _arrow_settings(st)
    try:
        want = {"left": (("TOPRIGHT", "TOPLEFT"), ("BOTTOMRIGHT", "BOTTOMLEFT"), (-74, 0, 0, 0)),
                "right": (("TOPLEFT", "TOPRIGHT"), ("BOTTOMLEFT", "BOTTOMRIGHT"), (0, 74, 0, 0)),
                "top": (("BOTTOMLEFT", "TOPLEFT"), ("BOTTOMRIGHT", "TOPRIGHT"), (0, 0, 74, 0)),
                "bottom": (("TOPLEFT", "BOTTOMLEFT"), ("TOPRIGHT", "BOTTOMRIGHT"), (0, 0, 0, -74))}
        for side, (p1, p2, clamp) in want.items():
            st.arrowSide = side
            A.Apply()
            for p, rp in (p1, p2):
                pt = af._pts[p]
                assert pt is not None and same(pt[2], dirf) and pt[3] == rp, (side, p)
            assert len(list(af._pts.keys())) == 2
            assert (af._w if side in ("left", "right") else af._h) == 74  # (the arrow's 58 and its margins)
            assert tuple(dirf._clamp.values()) == clamp, side
        # the directions dragged while snapped: they move, carrying the arrow
        st.arrowLocked, st.dirLocked, st.arrowSide = False, False, "left"
        A.Apply()
        lua.execute("AGPS_MOVED = nil AzerothGPSDirections.StartMoving = function(s) AGPS_MOVED = s end")
        dirf._scripts.OnDragStart(dirf)
        dirf._scripts.OnDragStop(dirf)
        assert same(lua.eval("AGPS_MOVED"), dirf) and A.Snapped() and st.arrowFreePoint is None
        # apart: a box round the arrow where it was, moved and saved on its own
        st.arrowSnap = False
        A.Apply()
        assert st.arrowFreePoint is not None and same(af._pts["TOPLEFT"][2], lua.globals().UIParent)
        assert (af._w, af._h) == (74, 74) and tuple(dirf._clamp.values()) == (0, 0, 0, 0)
        lua.execute("AGPS_MOVED = nil AzerothGPSArrow.StartMoving = function(s) AGPS_MOVED = s end")
        af._scripts.OnDragStart(af)
        af._scripts.OnDragStop(af)
        assert same(lua.eval("AGPS_MOVED"), af) and st.arrowFreePoint[1] == "CENTER"  # (the mock's GetPoint)
        # the directions hidden: the arrow alone, on its own
        st.arrowSnap, st.dirShown = True, False
        A.Apply()
        assert not dirf._shown and af._shown and not A.Snapped()
    finally:
        lua.execute("AzerothGPSDirections.StartMoving = nil AzerothGPSArrow.StartMoving = nil")
        _arrow_restore(ns, saved)


def test_the_arrow_drags_off_the_directions_and_snaps_back_against_a_side(game):
    # (asked 2026-10-30: "I want the arrow section itself to be a separate moveable window, individually from the text
    # area", "support snapping and detaching") dragged, the arrow comes off the directions where it is, on its own; dropped
    # against a side of them (within SNAP_PX, beside them) it snaps there; dropped anywhere else it stays on its own
    lua, ns = game
    A, st = ns.Arrow, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections
    same = lua.eval("function(a, b) return rawequal(a, b) end")

    def place(name, left, right, top, bottom):
        lua.execute(f"{name}.GetLeft = function() return {left} end {name}.GetRight = function() return {right} end "
                    f"{name}.GetTop = function() return {top} end {name}.GetBottom = function() return {bottom} end")
    saved = _arrow_settings(st)
    try:
        st.arrowLocked = st.dirLocked = False
        A.Apply()
        assert A.Snapped()
        place("AzerothGPSDirections", 300, 600, 500, 400)
        place("AzerothGPSArrow", 226, 300, 500, 426)  # (snapped on its left)
        lua.execute("AGPS_MOVED = nil AzerothGPSArrow.StartMoving = function(s) AGPS_MOVED = s end")
        af._scripts.OnDragStart(af)  # (detached, from where it is)
        assert same(lua.eval("AGPS_MOVED"), af) and not A.Snapped()
        assert tuple(st.arrowFreePoint.values())[:5] == ("TOPLEFT", "UIParent", "BOTTOMLEFT", 226, 500)
        place("AzerothGPSArrow", 900, 974, 800, 726)  # (dropped far off)
        af._scripts.OnDragStop(af)
        assert not A.Snapped() and st.arrowFreePoint is not None
        for side, rect in (("right", (610, 684, 480, 406)), ("top", (320, 394, 574, 510)), ("bottom", (350, 424, 395, 321)),
                           ("left", (210, 284, 470, 396))):
            st.arrowSnap = False
            A.Apply()
            place("AzerothGPSArrow", *rect)  # (dropped within SNAP_PX of that side, beside the directions)
            af._scripts.OnDragStart(af)
            af._scripts.OnDragStop(af)
            assert A.Snapped() and st.arrowSide == side, side
        # (beside a side but too far off it, or level with it but not beside it: none)
        assert A.SnapSide(lua.eval("{ left = 200, right = 260, top = 480, bottom = 420 }"),
                          lua.eval("{ left = 300, right = 600, top = 500, bottom = 400 }")) is None
        assert A.SnapSide(lua.eval("{ left = 226, right = 300, top = 900, bottom = 826 }"),
                          lua.eval("{ left = 300, right = 600, top = 500, bottom = 400 }")) is None
    finally:
        for n in ("AzerothGPSDirections", "AzerothGPSArrow"):
            lua.execute(f"{n}.GetLeft, {n}.GetRight, {n}.GetTop, {n}.GetBottom, {n}.StartMoving = nil, nil, nil, nil, nil")
        _arrow_restore(ns, saved)


def test_the_arrow_and_the_directions_have_their_own_backgrounds(game):
    # (asked 2026-10-30: "Update arrow background to only do the arrow detached, make another slider for the text window")
    # Arrow background the arrow's panel alone; the directions' its own slider, the arrow's until that's set
    lua, ns = game
    A, st = ns.Arrow, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections

    def alpha(f):
        return round(f.GetBackdropColor(f)[3], 2)
    saved = _arrow_settings(st)
    try:
        st.arrowBg, st.dirBg = 0.3, None
        A.Apply()
        assert (alpha(af), alpha(dirf)) == (0.3, 0.3)  # (the directions' not set yet: the arrow's)
        st.dirBg = 0.8
        A.Apply()
        assert (alpha(af), alpha(dirf)) == (0.3, 0.8)
        st.arrowBg = 0.0
        A.Apply()
        assert (alpha(af), alpha(dirf)) == (0.0, 0.8)
        # the options: a slider each
        ns.Options.Show()
        titles = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString" and w._text]
        assert "Arrow background" in titles and "Directions background" in titles
    finally:
        _arrow_restore(ns, saved)


def _text_px(w):
    # (a text's size as shown: its font's, times its text scale where the client has SetTextScale, as Arrow.lua uses:
    # SetFont lost the other alphabets, 2026-11-09)
    return round((w._font[2] if w._font else 12) * (w._textScale or 1), 6)


def test_the_arrow_and_text_sizes_follow_the_options(game):
    # (asked 2026-10-30: "a size adjustment for the arrow and text sizes in the settings") the arrow's panel round it,
    # the directions at least as tall as the arrow's column beside them; every line and row of the text scaled
    lua, ns = game
    A, st = ns.Arrow, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections
    same = lua.eval("function(a, b) return rawequal(a, b) end")
    texts = [w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString" and same(w._parent, dirf)]
    assert len(texts) >= 4
    saved = _arrow_settings(st)
    try:
        st.dirSize = lua.eval("{ 296, 97 }")
        st.arrowPx, st.dirTextScale = 120, 1.5
        A.Apply()
        assert af._w == 136 and A.arrowTex._w == 120
        assert dirf._h == 136  # (97 tall saved: the arrow's column beside them is taller)
        assert all(_text_px(w) == 18 for w in texts)  # (12 at 100%)
        st.arrowPx, st.dirTextScale = 58, 1
        A.Apply()
        assert af._w == 74 and A.arrowTex._w == 58 and dirf._h == 97 and all(_text_px(w) == 12 for w in texts)
    finally:
        _arrow_restore(ns, saved)


def test_the_directions_can_list_only_the_stops(game):
    # (asked 2026-10-30: "toggle the direction panel current step text so it can also just be a list of stops")
    lua, ns = game
    N, G, A, st = ns.Nav, ns.GPS, ns.Arrow, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections

    same = lua.eval("function(a, b) return rawequal(a, b) end")

    def shown_texts():
        return [str(w._text) for w in lua.eval("AGPS_WIDGETS").values()
                if w._kind == "FontString" and same(w._parent, dirf) and w._shown and w._text]
    saved = _arrow_settings(st)
    try:
        A.Apply()
        lua.execute("AzerothGPSDirections.GetBottom = function() return 0 end")  # (room for rows)
        N.SetStops(lua.eval("{ { x = 2600.0, y = 293.0, cont = 0, name = 'Stop one' },"
                            " { x = 2700.0, y = 320.0, cont = 0, name = 'Stop two' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert N.route is not None
        af._scripts.OnUpdate(af, 1)
        before = shown_texts()
        assert any("Stop one" in t and "(1/2)" in t for t in before)  # (the stop line under the turns)
        st.dirStopsOnly = True
        A.Apply()
        af._scripts.OnUpdate(af, 1)
        after = [t for t in shown_texts() if t.strip()]
        assert any(t.startswith("1. ") and "Stop one" in t for t in after), after
        assert any(t.startswith("2. ") and "Stop two" in t for t in after), after
        assert not any("Then:" in t or "toward" in t or "(1/2)" in t for t in after), after
        assert len(after) == 2, after
    finally:
        lua.execute("AzerothGPSDirections.GetBottom = nil")
        for w in lua.eval("AGPS_WIDGETS").values():  # (the rows made here: no stale yards for later tests' text checks)
            if w._kind == "FontString" and same(w._parent, dirf):
                w._text = ""  # (the next update writes them again)
        _arrow_restore(ns, saved)
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()


def test_resizing_the_directions_isnt_set_back_while_dragging(game):
    # (bug, 2026-10-30: "Dragging the resize handle it does some weird sticky behavior") the text update (4 times a
    # second) set the window back to its saved height while its corner was dragged: nothing is sized meanwhile, and the
    # size it's let go at is saved
    lua, ns = game
    N, G, A, st = ns.Nav, ns.GPS, ns.Arrow, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections
    saved = _arrow_settings(st)
    try:
        st.arrowLocked = st.dirLocked = False
        st.dirSize = lua.eval("{ 296, 97 }")
        A.Apply()
        N.SetStops(lua.eval("{ { x = 2600.0, y = 293.0, cont = 0, name = 's' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert N.route is not None
        lua.execute("IsMouseButtonDown = function() return true end")
        A.grip._scripts.OnMouseDown(A.grip)
        assert A.sizing
        dirf._h = None
        af._scripts.OnUpdate(af, 1)
        assert dirf._h is None  # (the drag's height left alone)
        A.grip._scripts.OnMouseUp(A.grip)
        assert not A.sizing and tuple(st.dirSize.values()) == (400, 400)  # (the mock's size, as let go)
        # the button let go where the corner didn't hear it (hidden meanwhile): ended at the next update
        A.grip._scripts.OnMouseDown(A.grip)
        lua.execute("IsMouseButtonDown = function() return false end")
        st.dirSize = lua.eval("{ 296, 97 }")
        af._scripts.OnUpdate(af, 1)
        assert not A.sizing and tuple(st.dirSize.values()) == (400, 400)
    finally:
        lua.execute("IsMouseButtonDown = function() return false end")
        A.sizing = None
        _arrow_restore(ns, saved)
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()


def test_the_old_arrow_window_becomes_the_directions_beside_the_arrow(game):
    # the one window's place and size (arrowPoint, arrowSize) the first time: the directions take the text's part, so
    # the two snapped on the left stand where the window was (its arrow column 74 wide on the left)
    lua, ns = game
    A, st = ns.Arrow, ns.settings.gps

    def old(point, size):
        p, s = A.FromOld(lua.eval(point), lua.eval(size))
        return tuple(p.values()), tuple(s.values())
    assert old('{ "CENTER", "UIParent", "CENTER", 15, 267 }', "{ 370, 97 }") == (("CENTER", "UIParent", "CENTER", 52, 267), (296, 97))
    assert old('{ "TOPLEFT", "UIParent", "BOTTOMLEFT", 100, 700 }', "{ 300, 120 }")[0][3] == 174
    assert old('{ "BOTTOMRIGHT", "UIParent", "BOTTOMRIGHT", -20, 40 }', "{ 300, 120 }") == (("BOTTOMRIGHT", "UIParent", "BOTTOMRIGHT", -20, 40), (226, 120))
    saved = _arrow_settings(st)
    try:
        st.dirPoint, st.dirSize = None, None
        st.arrowPoint, st.arrowSize = lua.eval('{ "CENTER", "UIParent", "CENTER", 15, 267 }'), lua.eval("{ 370, 97 }")
        A.Apply()
        assert tuple(st.dirPoint.values()) == ("CENTER", "UIParent", "CENTER", 52, 267)
        assert tuple(st.dirSize.values()) == (296, 97)
    finally:
        _arrow_restore(ns, saved)


def test_the_route_is_kept_up_with_the_map_hidden_and_the_arrow_off(game):
    # (the user's 1.1.6 test pass, 2026-10-07: "with both off minimap path stops updating, but just arrow on it works")
    # the route's upkeep (following, trimming, recalculating, a stop reached and passed: Nav.Status) was the arrow's text
    # update; with the map hidden AND the arrow off only the searches ran. The pump frame keeps the route up then too
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    pf, frame = G.pumpFrame, lua.globals().AzerothGPSFrame
    arrow_on = st.arrow
    x0, y0 = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    was_shown = bool(frame._shown)
    try:
        N.Clear()
        N.SetStops(lua.eval("{ { x = %f, y = %f, cont = 0, name = 'Near' } }" % (x0 + 40.0, y0)), False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert N.dest is not None
        st.arrow = False
        ns.Arrow.Apply()  # (the arrow off: its window hidden)
        assert not lua.globals().AzerothGPSArrow._shown
        frame.Hide(frame)  # (the map hidden)
        lua.execute("AGPS_POS[1] = %f AGPS_T = AGPS_T + 1" % (x0 + 40.0))  # (walked onto the stop)
        for _ in range(4):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            pf._scripts.OnUpdate(pf, 0.1)
        assert N.dest is None  # (reached and passed, as with the arrow on)
    finally:
        st.arrow = arrow_on
        ns.Arrow.Apply()
        (frame.Show if was_shown else frame.Hide)(frame)
        N.Clear()
        lua.execute("AGPS_POS[1] = %f AGPS_T = AGPS_T + 1" % x0)
        G.Update()


def test_searches_are_pumped_with_the_map_hidden_and_the_arrow_off(game):
    # (the 2026-10-07 idle profile's side finding) the arrow's OnUpdate pumped the route's searches while the
    # map was hidden — but a hidden frame gets no OnUpdate, so with the arrow option off too nothing pumped:
    # the first route never finished and the minimap's route froze. A bare always-shown frame (G.pumpFrame)
    # pumps whenever the map isn't; the arrow's OnUpdate no longer does.
    lua, ns = game
    G = ns.GPS
    pf = G.pumpFrame
    assert pf is not None and pf._shown
    frame = lua.globals().AzerothGPSFrame
    lua.execute("AGPS_PUMPN = { n = 0 } AGPS_PUMP_REAL2 = AGPS_NS.GPS.PumpSearches\n"
                "AGPS_NS.GPS.PumpSearches = function(...) AGPS_PUMPN.n = AGPS_PUMPN.n + 1 "
                "return AGPS_PUMP_REAL2(...) end")
    was_shown = bool(frame._shown)
    try:
        frame.Show(frame)
        pf._scripts.OnUpdate(pf, 0.016)
        assert lua.eval("AGPS_PUMPN.n") == 0  # (the map shows: its own OnUpdate pumps, not this frame)
        frame.Hide(frame)
        pf._scripts.OnUpdate(pf, 0.016)
        assert lua.eval("AGPS_PUMPN.n") == 1  # (hidden: this frame pumps, the arrow shown or not)
    finally:
        (frame.Show if was_shown else frame.Hide)(frame)
        lua.execute("AGPS_NS.GPS.PumpSearches = AGPS_PUMP_REAL2")


def test_shift_click_on_a_dock_pastes_its_times_in_chat(game):
    # (asked 2026-10-02) Shift + left-click on a zeppelin's dock with its timetable known: a line with its times
    # in the chat box (the one being typed in, else a new one), never sent by itself; on the route's ride icon
    # there too; with no timetable yet, nothing pasted
    import math
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    brill = (2254.0, 293.0)
    docks = [(math.hypot(t[2 + 3 * k] - brill[0], t[3 + 3 * k] - brill[1]), t[2 + 3 * k], t[3 + 3 * k], i, k + 1)
             for i, t in ns.Transports.items() for k in (0, 1) if t[8] == "zeppelin" and t[1 + 3 * k] == 0]
    _, x, y, i, side = min(docks)
    t = ns.Transports[i]
    here, there = (t[9], t[10]) if side == 1 else (t[10], t[9])
    want = f"Zeppelin from {here.split(',')[0]} to {there.split(',')[0]}: arrives in 2:10, leaves in 3:20"
    lua.execute("""AGPS_TT = AGPS_NS.Taxi.TransportTimes AGPS_NS.Taxi.TransportTimes = function() return 130, 200, 10 end
      AGPS_OLD_CHAT = { ChatFrame_OpenChat, IsShiftKeyDown, C_ChatInfo and C_ChatInfo.SendChatMessage, SendChatMessage }
      AGPS_PASTED, AGPS_SENT = {}, 0
      ChatFrame_OpenChat = function(text) table.insert(AGPS_PASTED, text) end
      SendChatMessage = function() AGPS_SENT = AGPS_SENT + 1 end
      IsShiftKeyDown = function() return AGPS_SHIFT end""")
    zoom = st.zoom
    pasted = lambda: list(lua.eval("AGPS_PASTED").values())  # noqa: E731

    def button():
        b = [w for w in lua.eval("AGPS_WIDGETS").values() if w.dock and w._shown and w.wx == x and w.wy == y]
        return b[0] if b else None

    try:
        st.zoom = 900.0
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        b = button()
        assert b is not None
        lua.execute("AGPS_SHIFT = false")
        b._scripts.OnClick(b, "LeftButton")
        assert pasted() == []  # (a plain click: nothing)
        lua.execute("AGPS_SHIFT = true")
        b._scripts.OnClick(b, "LeftButton")
        assert pasted() == [want] and lua.eval("AGPS_SENT") == 0 and "|" not in want
        # the route's ride icon on that dock (a route to Grom'gol takes it): the same
        N.SetStops(lua.eval("{ { x = -12420.0, y = 200.0, cont = 0, name = 'Grom' } }"), False, "red")
        _frames(lua, 4, fps=10)
        r = [w for w in lua.eval("AGPS_WIDGETS").values() if w.dock and w.title is not None and w._shown]
        assert r, "no ride icon on the dock"
        lua.execute("AGPS_PASTED = {}")
        r[0]._scripts.OnClick(r[0], "LeftButton")
        assert len(pasted()) == 1 and pasted()[0].startswith("Zeppelin from ")
        # no timetable yet: nothing pasted
        lua.execute("AGPS_NS.Taxi.TransportTimes = function() return nil end AGPS_PASTED = {}")
        b._scripts.OnClick(b, "LeftButton")
        assert pasted() == [] and G.DockShareText(i, side) is None
    finally:
        st.zoom = zoom
        N.Clear()
        lua.execute("""AGPS_NS.Taxi.TransportTimes = AGPS_TT
          ChatFrame_OpenChat, IsShiftKeyDown, SendChatMessage = AGPS_OLD_CHAT[1], AGPS_OLD_CHAT[2], AGPS_OLD_CHAT[4]
          AGPS_T = AGPS_T + 1""")


def test_right_click_a_dock_to_keep_it_out_of_routes(game):
    # (asked 2026-10-03) right-click a zeppelin's dock: "Don't use ... in routes?"; yes: never in a route, the dock
    # still shown, faded, saying so; right-click again to use it again. Options → Routing lists every zeppelin, boat
    # and the tram by kind, all on, a checkbox each
    import math
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    brill = (2254.0, 293.0)
    docks = [(math.hypot(t[2 + 3 * k] - brill[0], t[3 + 3 * k] - brill[1]), t[2 + 3 * k], t[3 + 3 * k], i)
             for i, t in ns.Transports.items() for k in (0, 1) if t[8] == "zeppelin" and t[1 + 3 * k] == 0]
    _, x, y, i = min(docks)
    t = ns.Transports[i]
    zoom = st.zoom

    def button():
        b = [w for w in lua.eval("AGPS_WIDGETS").values() if w.dock and w._shown and w.wx == x and w.wy == y]
        return b[0] if b else None

    try:
        st.zoom = 900.0
        ns.Nav.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        b = button()
        assert b is not None and not (b.note and "Not used in routes" in str(b.note))
        b._scripts.OnClick(b, "RightButton")
        ask = G.askBox  # (over the map, the map showing: asked 2026-10-04)
        assert ask.onMap and ask._shown and "Don't use the zeppelin between" in str(ask.text._text)
        assert (ask.yes._text, ask.no._text) == ("Don't Use", "Cancel")
        ask.yes._scripts.OnClick(ask.yes)
        assert not ns.Nav.RideAllowed(t)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        b = button()
        assert b is not None and "Not used in routes" in str(b.note)  # (still shown, saying so)
        b._scripts.OnClick(b, "RightButton")
        assert "Use the zeppelin between" in str(ask.text._text) and ask.yes._text == "Use It"
        ask.yes._scripts.OnClick(ask.yes)
        assert ns.Nav.RideAllowed(t)
        # Options → Routing: the sections and a checkbox per ride, ticked; unticking turns the ride off
        ns.Options.Show()
        texts = _texts(lua)
        for label in ("Zeppelins, boats and the tram", "Zeppelins", "Boats"):
            assert label in texts, label
        assert "The Deeprun Tram" not in texts  # (a Horde character: only its faction's rides are listed)
        town = lambda n: str(n).split(",")[0]  # noqa: E731
        label = f"{town(t[9])} - {town(t[10])}"
        fs = [w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString" and str(w._text) == label]
        assert fs, label
        cb = fs[0]._parent
        cb._checked = False
        cb._scripts.OnClick(cb)
        assert not ns.Nav.RideAllowed(t)
        cb._checked = True
        cb._scripts.OnClick(cb)
        assert ns.Nav.RideAllowed(t)
    finally:
        st.zoom = zoom
        st.ridesOff = None
        lua.execute("AGPS_T = AGPS_T + 1")


def test_pins_are_found_by_the_search_with_where_they_are(game):
    # (asked 2026-10-03) an "Auction House" pin in Stormwind and one in Ironforge: the search finds both, each with
    # its city in grey (kept on the pin when it's made) and its icon; picking one is a stop at that pin
    lua, ns = game
    G, P, N = ns.GPS, ns.Pins, ns.Nav
    own = P.Own()
    before = len(own)
    try:
        sw = P.Add(lua.eval("{ level = 0, x = -8811.0, y = 660.0, name = 'Auction House' }"))
        iff = P.Add(lua.eval("{ level = 0, x = -4957.0, y = -911.0, name = 'Auction House' }"))
        assert sw.place == "Stormwind City" and iff.place == "Ironforge"  # (kept when made)
        res = G.SearchPlaces("auction", 8)
        found = sorted((str(res[i].name), str(res[i].sub)) for i in range(1, len(res) + 1) if res[i].pin)
        assert found == [("Auction House", "Ironforge"), ("Auction House", "Stormwind City")]
        e = next(res[i] for i in range(1, len(res) + 1) if res[i].pin and str(res[i].sub) == "Stormwind City")
        assert e.tex and e.cont == 0
        # an older pin without its place: worked out when searched, then kept
        sw.place = None
        res = G.SearchPlaces("auction house", 8)
        assert any(res[i].pin and str(res[i].sub) == "Stormwind City" for i in range(1, len(res) + 1))
        assert sw.place == "Stormwind City"
        # the search box: the row shows the icon, the name and the place; clicking it makes a stop there
        N.Clear()
        panel = G.searchPanel
        same = lua.eval("rawequal")
        assert panel is not None
        box = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "EditBox" and same(w._parent, panel))
        box._text = "auction"
        box._scripts.OnTextChanged(box)
        rows = [w for w in lua.eval("AGPS_WIDGETS").values()
                if same(w._parent, panel) and w.entry is not None and w._shown and w.entry.pin]
        assert rows and "|T" in str(rows[0].text._text) and "Auction House" in str(rows[0].text._text)
        assert "|cff9d9d9d" in str(rows[0].text._text)  # (the place in grey)
        rows[0]._scripts.OnClick(rows[0])
        G.ConfirmRoute()
        assert len(N.stops) == 1 and str(N.stops[1].name) == "Auction House"
    finally:
        while len(own) > before:
            own[len(own)] = None
        N.Clear()
        G.Follow()


def test_a_pin_made_where_you_stand_keeps_what_the_game_says_of_there(game):
    # (asked 2026-10-03) a pin made where the player stands keeps whether they were indoors, the subzone and their
    # height when the game gives one (WoW Forever: never, its height is 0); one made elsewhere on the map doesn't
    lua, ns = game
    P = ns.Pins
    own = P.Own()
    before = len(own)
    lua.execute("AGPS_OLD_HERE = { IsIndoors, GetMinimapZoneText } IsIndoors = function() return true end "
                """GetMinimapZoneText = function() return "Gallows' End Tavern" end""")
    try:
        here = P.Add(lua.eval("{ level = 0, x = 2260.0, y = 290.0, name = 'Upstairs' }"))  # (Brill, by the player)
        assert here.indoors is True and str(here.subzone) == "Gallows' End Tavern" and here.playerZ is None
        far = P.Add(lua.eval("{ level = 0, x = 1600.0, y = 240.0, name = 'Far' }"))
        assert far.indoors is None and far.subzone is None
        lua.execute("AGPS_POS[4] = 41.5")  # (a client that gives the height)
        high = P.Add(lua.eval("{ level = 0, x = 2254.0, y = 293.0, name = 'High' }"))
        assert high.playerZ == 41.5
    finally:
        while len(own) > before:
            own[len(own)] = None
        lua.execute("IsIndoors, GetMinimapZoneText = AGPS_OLD_HERE[1], AGPS_OLD_HERE[2] AGPS_POS[4] = nil")


def test_known_city_places_are_found_by_several_words(game):
    # (asked 2026-10-03) "Inn Ir": Ironforge's inn ("Inn" in white, "Ironforge" in grey), once a guard there was talked
    # to; only the player's faction's capitals; picked, a stop named "Ironforge Inn"
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    db = ns.db
    was = db.cityRevealed
    lua.execute("AGPS_OLD_FACTION = UnitFactionGroup")
    try:
        db.cityRevealed = lua.eval("{ [1455] = true, [1454] = true }")  # (Ironforge, Orgrimmar)
        lua.execute("UnitFactionGroup = function() return 'Alliance' end")
        res = G.SearchPlaces("Inn Ir", 8)
        assert len(res) >= 1 and (str(res[1].name), str(res[1].sub)) == ("Inn", "Ironforge"), \
            [(str(res[i].name), str(res[i].sub)) for i in range(1, len(res) + 1)]
        assert str(res[1].place) == "Ironforge Inn" and res[1].tex
        found = [(str(r.name), str(r.sub)) for r in G.SearchPlaces("inn", 8).values()]
        assert ("Inn", "Ironforge") in found and ("Inn", "Orgrimmar") not in found  # (not the other faction's)
        N.Clear()
        e = res[1]
        G.AddStopAt(e.x, e.y, e.place, e.cont, e.tex, e.z)
        G.ConfirmRoute()
        assert str(N.stops[1].name) == "Ironforge Inn"
        # a Horde character: Orgrimmar's inn, not Ironforge's
        lua.execute("UnitFactionGroup = function() return 'Horde' end")
        found = [(str(r.name), str(r.sub)) for r in G.SearchPlaces("inn", 8).values()]
        assert ("Inn", "Orgrimmar") in found and ("Inn", "Ironforge") not in found
        # no guard talked to: found all the same (asked 2026-10-30, test_trainers_and_services_are_found_without_a_guard)
        db.cityRevealed = lua.eval("{}")
        assert any(str(r.sub) == "Orgrimmar" for r in G.SearchPlaces("inn or", 8).values())
    finally:
        db.cityRevealed = was
        lua.execute("UnitFactionGroup = AGPS_OLD_FACTION")
        N.Clear()
        G.Follow()


def test_trainers_and_services_are_found_without_a_guard_nearest_first(game):
    # (asked 2026-10-30, with the game's own list of a town's trainers and services: "a generic search for something
    # like "Class Trainer" or "Rogue Trainer" or "Skinning Trainer"... without having to talk to the guard first") every
    # capital's and starting town's places of the player's faction, no guard talked to; the same name nearest first with
    # its yards; "Class Trainer" the player's class's, "Profession Trainer" and "Flight master" by what they are
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    db = ns.db
    was, packed = db.cityRevealed, ns.NpcsPacked
    ns.NpcsPacked = ""  # (the places alone: the shipped NPCs among them are test_shipped_npcs.py's)
    lua.execute("AGPS_OLD_WHO = { UnitFactionGroup, UnitClass, AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] } "
                "UnitFactionGroup = function() return 'Horde' end UnitClass = function() return 'Rogue', 'ROGUE' end "
                "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")  # (in Brill)
    alliance = {"Stormwind City", "Ironforge", "Darnassus", "Goldshire", "Kharanos", "Dolanaar"}

    def search(text):
        res = G.SearchPlaces(text, 8)
        return [res[i] for i in range(1, len(res) + 1)]

    def show(res):
        return [(str(e.name), str(e.sub), e.yd) for e in res]
    try:
        db.cityRevealed = lua.eval("{}")  # (no guard talked to anywhere)
        for text, name in (("Rogue Trainer", "Rogue Trainer"), ("skinning trainer", "Skinning Trainer"),
                           ("Class Trainer", "Rogue Trainer"), ("class tr", "Rogue Trainer")):
            res = search(text)
            assert len(res) >= 3 and all(str(e.name).endswith(name) for e in res), (text, show(res))
            assert not any(str(e.sub) in alliance for e in res), (text, show(res))  # (only the player's faction's)
            yds = [e.yd for e in res if e.yd is not None]
            assert len(yds) >= 2 and yds == sorted(yds), (text, show(res))  # (nearest first)
            assert str(res[0].place) == "Brill " + name, (text, show(res))  # (Brill's, where the player stands)
        res = search("Profession Trainer")
        assert len(res) == 8 and all(str(e.name).endswith("Trainer") and "Rogue" not in str(e.name) for e in res), show(res)
        assert [e.yd for e in res] == sorted(e.yd for e in res), show(res)
        res = search("Flight master")
        assert any(str(e.name) == "Bat Handler" for e in res) and [e.yd for e in res] == sorted(e.yd for e in res), show(res)
        # (two letters: names with them, not every flight master, profession trainer and NPC title by what it is)
        assert all("fl" in str(e.name).lower() for e in search("fl")), show(search("fl"))
        # the search box: each row with its yards
        panel = G.searchPanel
        same = lua.eval("rawequal")
        box = next(w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "EditBox" and same(w._parent, panel))
        box._text = "rogue trainer"
        box._scripts.OnTextChanged(box)
        rows = [w for w in lua.eval("AGPS_WIDGETS").values() if same(w._parent, panel) and w.entry is not None and w._shown]
        first = next(r for r in rows if str(r.entry.place) == "Brill Rogue Trainer")
        assert str(N.FormatDistance(first.entry.yd)) in str(first.text._text), str(first.text._text)
    finally:
        same = lua.eval("rawequal")
        for w in lua.eval("AGPS_WIDGETS").values():  # (the rows' yards: none left for later tests' text checks)
            if w.entry is not None and same(w._parent, G.searchPanel) and w.text is not None:
                w.text._text = ""
        db.cityRevealed, ns.NpcsPacked = was, packed
        lua.execute("UnitFactionGroup, UnitClass = AGPS_OLD_WHO[1], AGPS_OLD_WHO[2] "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = AGPS_OLD_WHO[3], AGPS_OLD_WHO[4], AGPS_OLD_WHO[5]")


def test_a_weapons_trainer_is_found_and_routed_to_in_orgrimmar(game):
    # (reported 2026-11-05: "can't seem to route to weapons trainer in ogrimmar") the place is "Weapon Master", and
    # "weapons trainer" or "weapon trainer" found nothing: a capital's Weapon Master is a "weapon trainer" now, and the
    # generic words match singular or plural ("flight masters", "class trainers" too); picked, the route gets there
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    packed = ns.NpcsPacked
    ns.NpcsPacked = ""  # (the places alone: Orgrimmar's Weapon Master NPC, Hanashi, is test_shipped_npcs.py's)
    lua.execute("AGPS_OLD_WHO = { UnitFactionGroup, UnitClass, AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] } "
                "UnitFactionGroup = function() return 'Horde' end UnitClass = function() return 'Warrior', 'WARRIOR' end "
                "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 1630.0, -4420.0, 1")  # (Orgrimmar's Valley of Strength)

    def search(text):
        res = G.SearchPlaces(text, 8)
        return [res[i] for i in range(1, len(res) + 1)]
    try:
        for text in ("weapons trainer", "Weapon Trainer", "weapons", "weapon tr"):
            res = search(text)
            assert res and str(res[0].name) == "Weapon Master" and str(res[0].sub) == "Orgrimmar", \
                (text, [(str(e.name), str(e.sub)) for e in res])
            assert all(str(e.name) == "Weapon Master" for e in res)
            yds = [e.yd for e in res if e.yd is not None]
            assert yds == sorted(yds), text  # (nearest first: Orgrimmar's, then Thunder Bluff's)
        assert any(str(e.name) == "Wind Rider Master" for e in search("flight masters"))
        assert all(str(e.name) == "Warrior Trainer" for e in search("class trainers"))
        assert not search("weaponsmith trainer")  # (no such place: no kind match by a longer word)
        e = search("weapons trainer")[0]
        N.SetStops(lua.eval(f"{{ {{ x = {e.x}, y = {e.y}, cont = {e.cont}, z = {e.z}, name = 'Weapon Master' }} }}"),
                   False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        r = N.Route(1630.0, -4420.0, 1)
        assert r and not r.noWay and r.totalYards < 1500, r and r.totalYards
    finally:
        ns.NpcsPacked = packed
        N.Clear()
        lua.execute("UnitFactionGroup, UnitClass = AGPS_OLD_WHO[1], AGPS_OLD_WHO[2] "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = AGPS_OLD_WHO[3], AGPS_OLD_WHO[4], AGPS_OLD_WHO[5]")


def test_the_portrait_logo_is_shown_one_to_one_from_its_sizes(game):
    # (asked: the logo in the round portrait looked soft, one 128-pixel picture shrunk by the graphics card)
    # the pre-scaled size nearest the pixels the 62-unit portrait covers, shown 1:1
    import numpy as np
    from PIL import Image

    from azerothgps.media import PORTRAIT_PX, SMALL_LOGO_PX, corner_master, on_canvas, scaled

    lua, ns = game
    assert list(ns.PORTRAIT_PX.values()) == list(PORTRAIT_PX)
    assert list(ns.SMALL_LOGO_PX.values()) == list(SMALL_LOGO_PX)
    for (w, h), scale, want in (((2560, 1440), 0.64, 72), ((1920, 1080), 1.0, 80), ((3840, 2160), 1.0, 176)):
        lua.execute(f"GetPhysicalScreenSize = function() return {w}, {h} end")
        assert ns.PortraitPx(62, scale)[0] == want
    lua.execute("GetPhysicalScreenSize = nil")
    assert ns.PortraitPx(62, 1.0) == (64, 1)  # (unknown: a pixel a unit)
    # the files: each size as made from assets/logo.png (`agps media`); the round portrait's gone (asked)
    media, logo = ADDON / "Media", ADDON.parents[1] / "assets" / "logo.png"
    corner = corner_master(logo)
    for px in SMALL_LOGO_PX + PORTRAIT_PX:
        f = media / f"CornerLogo{px}.tga"
        assert f.exists(), f"{f.name} missing: run `agps media`"
        same = np.array_equal(np.asarray(Image.open(f).convert("RGBA")), np.asarray(on_canvas(scaled(corner, px))))
        assert same, f"{f.name} is stale: run `agps media`"
    assert not list(media.glob("Portrait*.tga")) and ns.FitPortrait is None


def test_map_icons_never_crash_the_client_and_labels_sit_on_whole_pixels(game):
    # (reported: city places and custom pins looked low-resolution; then the place names and city labels too)
    # The icons' fix, the "TRILINEAR" filter mode, crashed client 1.60.1.70124 (an assert: the filter at most
    # LINEAR), so no icon is set with a filter above LINEAR (wowmock.lua fails on one as the client does);
    # a label's top-left goes on a whole screen pixel (the map scrolls smoothly, and text between pixels is
    # smeared), its shadow one pixel off. (asked, after the crash) a pin's and a stop's game icon instead drawn at
    # an exact quarter of its 64 pixels (G.ICON_PX, 16 on the screen; asked: half was too large) on whole pixels
    lua, ns = game
    G, P, N = ns.GPS, ns.Pins, ns.Nav
    N.Clear()
    ppu = 1440 / 768  # (the stand-in's frames: effective scale 1)
    lua.execute("AGPS_OLD_PSS0 = GetPhysicalScreenSize\nGetPhysicalScreenSize = function() return 2560, 1440 end")

    def whole_px(v, middle=300):  # (the stand-in's frames' middle: 300, 300)
        px = (middle + v) * ppu
        return abs(px - round(px)) < 1e-6

    pin = P.Add(lua.eval("{ level = 0, x = 2254, y = 293, name = 'Sharp', icon = 136777 }"))
    try:
        lua.execute("AGPS_T = 900")
        G.Update()
        pins = _shown(lua, lambda w: w.pin is not None and w.pin.name == "Sharp")
        assert len(pins) == 1 and pins[0].icon._tex == 136777 and pins[0].icon._filter in (None, "LINEAR")
        b = pins[0]
        # (medium, a quarter bigger, by default since 2026-11-14, `iconSize`: "render them in multiple sizes")
        px = G.ICON_PX * G.PoiScale()
        assert px == 20 and abs(b._w * ppu - px) < 1e-9 and abs(b._h * ppu - px) < 1e-9
        assert b._pt[1] == "CENTER" and whole_px(b._pt[4]) and whole_px(b._pt[5])
        b._scripts.OnDoubleClick(b)  # (as a stop: its marker too)
        lua.execute("AGPS_T = 901")
        G.Update()
        stop = _shown(lua, lambda w: w.pendingIndex == 1)
        assert len(stop) == 1 and stop[0].icon._filter in (None, "LINEAR")
        assert abs(stop[0]._w * ppu - 16) < 1e-9 and whole_px(stop[0]._pt[4]) and whole_px(stop[0]._pt[5])
        G.RemovePending(1)
        G.Follow()  # (the map back on the player: removing the last stop leaves it where it is since 1.3.5)
        # a city place's icon too; a game icon is a file id or an Interface\Icons path, other art isn't
        assert G.IsGameIcon(136777) and G.IsGameIcon("Interface\\Icons\\Trade_Alchemy")
        assert not G.IsGameIcon("Interface\\AddOns\\AzerothGPS\\Media\\Ship") and not G.IsGameIcon("atlas:poi-door")
    finally:
        P.Remove(pin)
        lua.execute("GetPhysicalScreenSize = AGPS_OLD_PSS0")
    t = lua.eval("CreateFrame('Frame'):CreateTexture()")  # (city places, POIs, overlays: ns.SetIcon)
    ns.SetIcon(t, "Interface\\Icons\\INV_Misc_Bag_10_Blue")
    assert t._filter in (None, "LINEAR")

    with pytest.raises(Exception, match="GxTex_Linear"):  # (the stand-in crashes as the client does)
        lua.eval("function(t) t:SetTexture(136777, nil, nil, 'TRILINEAR') end")(t)
    lua.execute("AGPS_OLD_PSS = GetPhysicalScreenSize\nGetPhysicalScreenSize = function() return 2560, 1440 end")
    try:
        fs = lua.eval("""(function()
          local parent = CreateFrame('Frame')
          parent.GetCenter = function() return 300.3, 200.7 end
          parent.GetEffectiveScale = function() return 0.64 end
          AGPS_PARENT = parent
          local fs = parent:CreateFontString()
          fs.GetStringWidth = function() return 41.3 end
          fs.GetStringHeight = function() return 12.2 end
          fs.SetPoint = function(self, ...) self.pt = { ... } end
          fs.SetShadowOffset = function(self, x, y) self.sh = { x, y } end
          return fs
        end)()""")
        ppu = 1440 / 768 * 0.64
        for point, x, y in (("CENTER", 12.37, -40.91), ("BOTTOM", -3.5, 7.25)):
            G.PinText(fs, lua.eval("AGPS_PARENT"), point, x, y)
            assert fs.pt[1] == "TOPLEFT" and fs.pt[3] == "CENTER"
            left, top = fs.pt[4], fs.pt[5]
            want = (x - 41.3 / 2, y + (12.2 if point == "BOTTOM" else 6.1))
            for got, wanted, middle in ((left, want[0], 300.3), (top, want[1], 200.7)):
                px = (middle + got) * ppu
                assert abs(px - round(px)) < 1e-6  # (a whole pixel)
                assert abs(got - wanted) <= 0.5 / ppu + 1e-9  # (the nearest one)
            assert abs(fs.sh[1] * ppu - 1) < 1e-9 and abs(fs.sh[2] * ppu + 1) < 1e-9
    finally:
        lua.execute("GetPhysicalScreenSize = AGPS_OLD_PSS")


def test_the_corner_logo_without_the_circle(game):
    # (asked: the logo without the circle, as StreetView's viewer has it; later the round portrait's option
    # removed) the plate logo, the window's border without the portrait's ring; dragging the plate moves
    # the window
    lua, ns = game
    st = ns.settings.gps
    assert st.roundLogo is None
    lua.execute("""
      GetPhysicalScreenSize = function() return 2560, 1440 end
      AGPS_W = CreateFrame("Frame", nil, UIParent)
      AGPS_W.PortraitContainer = { portrait = AGPS_W:CreateTexture() }
      function AGPS_W:GetPortrait() return self.PortraitContainer.portrait end
      function AGPS_W.PortraitContainer.portrait:GetWidth() return 62 end -- (the template's)
      function AGPS_W:SetBorder(name) self.border = name end
      AGPS_MOVES = {}
    """)
    win = lua.eval("AGPS_W")
    try:
        w = ns.SetLogoPortrait(win, None, lua.eval("function(s) AGPS_MOVES[#AGPS_MOVES + 1] = s end"))
        portrait = win.PortraitContainer.portrait
        assert str(win.border) == "ButtonFrameTemplateNoPortrait" and not portrait._shown
        assert w.plate and w.plate._shown and str(w.plate.tex._tex).endswith("CornerLogo112")  # (62 units at 1440p)
        w.plate._scripts.OnDragStart(w.plate)
        w.plate._scripts.OnDragStop(w.plate)
        assert list(lua.eval("AGPS_MOVES").values()) == [True, False]
        st.roundLogo = True  # (an old saved setting: no round portrait any more)
        ns.ApplyLogoLook()
        assert str(win.border) == "ButtonFrameTemplateNoPortrait" and w.plate._shown and not portrait._shown
    finally:
        st.roundLogo = None
        lua.execute("GetPhysicalScreenSize = nil AGPS_W:Hide()")


def test_the_place_is_in_the_title_bar_and_the_coordinates_at_the_bottom(game):
    # (asked) with the window frame, the place's name ("Undercity") in its title bar in place of
    # "AzerothGPS", the X, Y at the map's bottom as before; without the frame, both at the bottom
    lua, ns = game
    G = ns.GPS
    chrome = G.chrome
    lua.execute("""
      AGPS_CHROME = CreateFrame("Frame", nil, UIParent)
      AGPS_CHROME.TitleContainer = { TitleText = AGPS_CHROME:CreateFontString() }
      AGPS_CHROME.TitleContainer.TitleText:SetText("AzerothGPS")
    """)
    fake = lua.eval("AGPS_CHROME")
    title = fake.TitleContainer.TitleText
    # (the shown texts but the title: the line at the bottom)
    shown = lua.eval("""function()
      local out = {}
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._shown and w._text ~= "" and w ~= AGPS_CHROME.TitleContainer.TitleText then out[#out + 1] = w._text end
      end
      return out
    end""")
    try:
        G.chrome = fake
        G.UpdateInfo()
        name, xy = str(G.infoName), str(G.infoXY)
        assert name and "," in xy
        assert str(title._text) == name  # (the place alone)
        texts = [str(t) for t in shown().values()]
        assert xy in texts and not any(name in t for t in texts if xy in t)  # (the X, Y alone, at the bottom)
        # (asked 2026-11-17: "add option to general to hide X,Y display on pop out map": the place's name stays)
        ns.settings.gps.showCoords = False
        G.PlaceInfo()
        assert str(title._text) == name and not any(xy in str(t) for t in shown().values())
        ns.settings.gps.showCoords = True
        fake.Hide(fake)
        G.PlaceInfo()
        assert f"{name}  {xy}" in [str(t) for t in shown().values()]  # (no title bar: the whole line)
        ns.settings.gps.showCoords = False
        G.PlaceInfo()
        texts = [str(t) for t in shown().values()]
        assert name in texts and not any(xy in t for t in texts)
    finally:
        ns.settings.gps.showCoords = True
        G.chrome = chrome
        G.UpdateInfo()


def test_in_a_city_the_wheel_doesnt_zoom_out_past_its_map(game):
    # (reported: in Ironforge, zooming out turned the city's map into the terrain around it) in a city
    # whose inside map shows, its map at any zoom (zoomed in to it on the way in), the wheel no further
    # out than CITY_MAX_ZOOM; outside a city, zooming out as before
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    zoom = st.zoom
    # (the Terrain style, not the seamless map: on, the wheel goes on out to the world, issue #62: test_atlas.py's
    # test_out_of_a_citys_map_to_the_world_and_back_in)
    seamless, st.style = st.style, "minimap"
    # (Ironforge, the Great Forge: its floor's height, its name)
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4840.0, -1100.0, 0, 501.7 "
                "AGPS_ZONE_REAL = GetMinimapZoneText GetMinimapZoneText = function() return 'The Great Forge' end")
    try:
        for indoors in ("true", "false"):  # (Ironforge's halls: indoors or not, the city's map)
            lua.execute(f"AGPS_INDOORS_REAL = AGPS_INDOORS_REAL or IsIndoors IsIndoors = function() return {indoors} end")
            G.Follow()
            st.zoom = 2000.0
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
            assert G.inside is not None and G.cityMap, indoors
            assert str(G.LocateWorld(0, -4840.0, -1100.0)[1]) == "Ironforge"  # (the city's name, not Dun Morogh's over it)
            assert st.zoom == G.CITY_MAX_ZOOM  # (zoomed in to the city's map)
            G.WheelZoom(1.25)
            assert st.zoom == G.CITY_MAX_ZOOM  # (no further out: right-click for the land around)
            G.WheelZoom(0.8)
            assert st.zoom < G.CITY_MAX_ZOOM
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil "
                    "GetMinimapZoneText = AGPS_ZONE_REAL AGPS_T = AGPS_T + 1")
        G.Update()
        assert not G.cityMap
        before = st.zoom
        G.WheelZoom(1.25)
        assert st.zoom > before  # (outside a city: out as before)
    finally:
        st.zoom, st.style = zoom, seamless
        lua.execute("IsIndoors = AGPS_INDOORS_REAL or IsIndoors GetMinimapZoneText = AGPS_ZONE_REAL or GetMinimapZoneText "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()


def test_panning_in_a_city_keeps_its_map(game):
    # (reported, a video: panning in Ironforge flipped between the city's map and the snow outside) in a
    # capital with an inside map, its map while the view is over the city, wherever in it; off the city,
    # the land around
    lua, ns = game
    G, st, R = ns.GPS, ns.settings.gps, ns.Router
    zoom = st.zoom
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4840.0, -1100.0, 0, 501.7 "
                "AGPS_ZONE_REAL = GetMinimapZoneText GetMinimapZoneText = function() return 'The Great Forge' end")
    try:
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.inside is not None
        spots = [(-4840.0 + dx, -1100.0 + dy) for dx, dy in ((0, 160), (-150, 120), (120, -80), (-180, -60))]
        spots = [s for s in spots if R.CapitalAt(0, s[0], s[1])]
        assert len(spots) >= 2
        # (and over the rock between its halls: not the city's own cells, but in its grid; the map flipped
        # to the outside there, a second video)
        P = ns.Passability
        grid = P.CapitalGridAt(0, -4840.0, -1100.0)
        rock = [(-4840.0 + dx, -1100.0 + dy) for dx in range(-240, 241, 40) for dy in range(-240, 241, 40)]
        same = lua.eval("rawequal")
        rock = [s for s in rock if not R.CapitalAt(0, s[0], s[1]) and same(P.CapitalGridAt(0, s[0], s[1]), grid)]
        assert grid is not None and len(rock) >= 3
        spots += rock[:4]
        for x, y in spots:  # (looked at from the player: the view's middle there, further than its 1.5 zooms)
            G.LookAt(0, x, y, 60.0)
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
            assert G.inside is not None, (x, y)
        G.LookAt(0, -5600.0, -400.0, 60.0)  # (Dun Morogh's snow, far off the city: the land)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.inside is None
    finally:
        st.zoom = zoom
        lua.execute("GetMinimapZoneText = AGPS_ZONE_REAL or GetMinimapZoneText "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_routes_overview_out_of_a_city_shows_the_land_then_the_city(game):
    # (asked) in Ironforge, a route out to Kharanos: its overview zooms out over the land (not the city's
    # map shrinking into the black), then back to the player, the city's map again
    lua, ns = game
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    zoom = st.zoom
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4840.0, -1100.0, 0, 501.7 "
                "AGPS_ZONE_REAL = GetMinimapZoneText GetMinimapZoneText = function() return 'The Great Forge' end")
    try:
        N.Clear()
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.inside is not None
        G.AddStopAt(-5590.0, -480.0, "Kharanos")
        G.ConfirmRoute()
        assert len(N.stops) == 1
        seen = []
        _frames(lua, 3 + 1.5 + 2, fps=10)  # (the tour: hold, out, a while shown)
        seen.append((G.inside is None, G.IsFree()))
        assert G.inside is None and G.IsFree()  # (the land around, zoomed out)
        _frames(lua, 4 + 1.5 + 1, fps=10)  # (the rest shown, back to the player)
        assert not G.IsFree() and G.inside is not None, seen  # (following: the city's map again)
    finally:
        N.Clear()
        st.zoom = zoom
        lua.execute("GetMinimapZoneText = AGPS_ZONE_REAL or GetMinimapZoneText "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()


def test_dragging_in_a_city_keeps_its_map_until_right_click(game):
    # (reported, a third video: Ironforge's map dragged off the city flipped to the land, and zoomed out from
    # there the city's map shrank into the black) in a city, its map wherever the view is dragged, zoomed
    # out no further than CITY_MAX_ZOOM; right-click for the land around
    lua, ns = game
    G, st, R = ns.GPS, ns.settings.gps, ns.Router
    zoom = st.zoom
    seamless, st.style = st.style, "minimap"  # (on, the wheel goes on out to the world: issue #62)
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4840.0, -1100.0, 0, 501.7 "
                "AGPS_ZONE_REAL = GetMinimapZoneText GetMinimapZoneText = function() return 'The Great Forge' end "
                "AGPS_OLD_CURSOR = GetCursorPosition AGPS_CX, AGPS_CY = 300, 300 "
                "GetCursorPosition = function() return AGPS_CX, AGPS_CY end")
    frame = lua.globals().AzerothGPSFrame
    try:
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.inside is not None
        frame._scripts.OnMouseDown(frame, "LeftButton")
        lua.execute("AGPS_CX = 300 + 2500")
        frame._scripts.OnUpdate(frame, 1)
        frame._scripts.OnMouseUp(frame, "LeftButton")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        x, y = G.ViewState()[0:2]
        assert math.dist((x, y), (-4840.0, -1100.0)) > G.CITY_VIEW_YD and not R.CapitalAt(0, x, y)  # (far off the city)
        assert G.inside is not None and G.cityMap
        for _ in range(6):  # (the wheel: no further out than the city's map)
            G.WheelZoom(2.0)
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        assert st.zoom <= G.CITY_MAX_ZOOM and G.inside is not None
        frame._scripts.OnMouseDown(frame, "RightButton")  # (the land around)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.inside is None
    finally:
        st.zoom, st.style = zoom, seamless
        lua.execute("GetMinimapZoneText = AGPS_ZONE_REAL or GetMinimapZoneText GetCursorPosition = AGPS_OLD_CURSOR "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()


def test_right_click_in_a_city_shows_the_land_to_look_around(game):
    # (asked 2026-10-02, a video: down in Undercity, right-click went to the continent's map art, and the land
    # past the city stayed black when dragged or zoomed; Ironforge the same) in a city's map with the terrain
    # style, right-click: the land's terrain around it, zoomed out; dragged and zoomed in anywhere, the land
    # (not the city's map over a black land); following again, the city's map
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    zoom = st.zoom
    # (the Terrain style, not the seamless map: from the land, right-click goes on to the continent's map; on, the default since issue #60,
    # a few notches out on its art: test_atlas.py's test_right_click_zooms_out_a_few_notches_in_place_up_to_the_world)
    seamless, st.style = st.style, "minimap"
    frame = lua.globals().AzerothGPSFrame
    lua.execute("AGPS_MAP_REAL = AGPS_MAP AGPS_OLD_CURSOR = GetCursorPosition AGPS_CX, AGPS_CY = 300, 300 "
                "GetCursorPosition = function() return AGPS_CX, AGPS_CY end "
                "AGPS_ZONE_REAL = GetMinimapZoneText AGPS_T = AGPS_T + 1000")  # (past the player level's cache time)

    def tick():
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()

    def drag(dx):
        frame._scripts.OnMouseDown(frame, "LeftButton")
        lua.execute(f"AGPS_CX = 300 + {dx}")
        frame._scripts.OnUpdate(frame, 1)
        frame._scripts.OnMouseUp(frame, "LeftButton")
        lua.execute("AGPS_CX = 300")
        tick()

    cities = (  # (down in Undercity: its level; Ironforge's Great Forge: a capital in a mountain)
        ("AGPS_MAP = 1458 AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 1593.5, 157.3, 0, nil", (1593.5, 157.3)),
        ("AGPS_MAP = AGPS_MAP_REAL AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4840.0, -1100.0, 0, 501.7 "
         "GetMinimapZoneText = function() return 'The Great Forge' end", (-4840.0, -1100.0)),
    )
    try:
        for setup, (px, py) in cities:
            lua.execute(setup)
            G.Follow()
            tick()
            assert G.inside is not None and G.cityMap, setup
            frame._scripts.OnMouseDown(frame, "RightButton")
            tick()
            assert G.inside is None and G.IsFree() and not G.cityMap, setup  # (the land)
            assert G.SaveView().browse is None and G.SaveView().land  # (the terrain, not the continent's map art)
            assert st.zoom > G.CITY_MAX_ZOOM and st.zoom >= min(G.MaxZoom(), G.LAND_ZOOM) - 1
            assert G.ViewState()[2] == 0  # (the continent's land, not the city's level)
            drag(-150)  # (looked around: still the land)
            assert G.inside is None and G.SaveView().land, setup
            for _ in range(8):  # (zoomed in: the land, not the city's map over black)
                G.WheelZoom(0.6)
                tick()
            assert st.zoom <= G.INTERIOR_MAX_ZOOM and G.inside is None, setup
            G.Follow()  # (following again: the city's map)
            tick()
            assert G.inside is not None and G.cityMap, setup
            frame._scripts.OnMouseDown(frame, "RightButton")  # (and once more from the land: the continent's map)
            tick()
            frame._scripts.OnMouseDown(frame, "RightButton")
            tick()
            assert G.SaveView().browse is not None, setup
            G.Follow()
            tick()
    finally:
        st.zoom, st.style = zoom, seamless
        lua.execute("AGPS_MAP = AGPS_MAP_REAL GetCursorPosition = AGPS_OLD_CURSOR GetMinimapZoneText = AGPS_ZONE_REAL "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_stop_picked_in_a_dungeons_map_goes_to_its_entrance(game):
    # (asked: a stop picked in a dungeon's map kept "Working out the route..." going) a spot, a boss or a pin
    # in a dungeon's or raid's map: a stop at its entrance's icon on the continent instead; of a dungeon's
    # several ways in, the wing picked
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    # (the Scarlet Monastery's four wings: the second's way in is at (853, 1319) inside)
    e = G.InstanceStopEntrance(20189, 860.0, 1310.0)
    assert (e.cont, e.x, e.y, e.name) == (0, 2915.1, -823.6, "Scarlet Monastery: Cathedral")
    N.Clear()
    try:
        G.ShowInstance(20036)  # (the Deadmines' map, opened from its icon)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        boss = ns.Instances[20036].bosses[1]
        G.AddStopAt(boss[3], boss[4], boss[1], 20036, r"Interface\Icons\Spell_Shadow_Skull", boss[5])  # (its icon)
        G.AddStopAt(boss[3] + 20.0, boss[4])  # (a double-click on the map there)
        G.ConfirmRoute()
        # (the Deadmines from outside: the Defias Hideout's way in, G.ENTRANCE_VIA; asked 2026-10-01)
        hideout = next(c for c in ns.Caves[0].values() if c[2] == "cave35530")
        mouths = [(hideout[5][k], hideout[5][k + 1]) for k in range(1, len(hideout[5]), 2)]
        assert len(N.stops) == 2
        for d in N.stops.values():
            assert d.cont == 0 and (d.x, d.y) in mouths and "Defias Hideout" in d.name and d.z is None
        _frames(lua, 3, fps=10)
        assert N.route is not None and N.Status(2254.0, 293.0, 0) != N.WORKING_TEXT  # (worked out)
    finally:
        N.Clear()
        G.Follow()


def test_a_bigger_window_shows_more_of_the_map_not_the_map_bigger(game):
    # (asked: at the most zoomed out, a bigger map window only made the map bigger) the size changed keeps the
    # scale (more or less of the map shown), and a window bigger than 450 zooms out further, on the terrain
    # view's tiles still
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    size, zoom = st.size, st.zoom
    try:
        st.size = 450
        G.ApplySettings()
        for _ in range(12):
            G.WheelZoom(2.0)
        top = st.zoom
        assert top == pytest.approx(2500.0)
        st.size = 800
        G.ApplySettings()
        assert st.zoom == pytest.approx(top * 800 / 450)  # (the same yards to a pixel: more of the map)
        for _ in range(4):
            G.WheelZoom(2.0)
        assert st.zoom == pytest.approx(top * 800 / 450) and st.zoom < G.MinimapMaxZoom()  # (its limit; tiles)
        st.size = 450
        G.ApplySettings()
        assert st.zoom == pytest.approx(top)
        G.SetZoom(300.0)
        st.size = 600
        G.ApplySettings()
        assert st.zoom == pytest.approx(400.0)  # (not only at the limit)
    finally:
        st.size, st.zoom = size, zoom
        G.ApplySettings()
        st.zoom = zoom


def test_a_dungeons_wings_each_have_their_icon_map_bosses_and_way(game):
    # (asked: the Scarlet Monastery's four icons with their wing, the bosses and routes each its own; "do
    # this for any dungeon/raid that does this") an icon per wing, named; its map that wing's: its bosses,
    # its usual way from its way in, its boss route; inside, the wing gone in by
    lua, ns = game
    G, T = ns.GPS, ns.Taxi
    SM = 20189
    info = ns.Instances[SM]
    assert list(info.wings.values()) == ["Graveyard", "Library", "Armory", "Cathedral"]
    icons = sorted(e.name for e in G.InstanceEntrances(0).values() if e.level == SM)
    assert icons == ["Scarlet Monastery: Armory", "Scarlet Monastery: Cathedral", "Scarlet Monastery: Graveyard",
                     "Scarlet Monastery: Library"]
    want = {"Graveyard": {"Interrogator Vishas", "Bloodmage Thalnos", "Azshir the Sleepless", "Fallen Champion", "Ironspine"},
            "Library": {"Houndmaster Loksey", "Arcanist Doan"}, "Armory": {"Herod"},
            "Cathedral": {"Scarlet Commander Mograine", "High Inquisitor Fairbanks", "High Inquisitor Whitemane"}}
    assert {w: {b[1] for b in info.bosses.values() if b.wing == w} for w in want} == want
    try:
        for wing, bosses in want.items():
            G.ShowInstance(SM, wing)  # (its icon clicked)
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
            assert G.InstanceWing(SM) == wing
            assert _shown(lua, lambda w: w._text is not None and f"Scarlet Monastery: {wing}" in str(w._text))  # (the title)
            assert {b[1] for b in G.BossOrder(SM).values()} <= bosses
            assert {d.name for d in G.BossStops(SM)[0].values()} <= bosses
            e = G.WingEntrance(SM, wing)
            path = G.SuggestedPath(SM)[0]
            assert e[7] == wing and (path[1], path[2]) == pytest.approx((e[4], e[5]), abs=30)  # (from its way in)
        # inside: the wing gone in by, where the player last stood outside (the Library's door)
        G.Follow()
        lib = G.WingEntrance(SM, "Library")
        T.NoteOutside(1000.0, lib[2] + 3.0, lib[3], 0)
        assert T.NoteWing(189, 1005.0) == "Library" and G.InstanceWing(SM) == "Library"
        assert {b[1] for b in G.BossOrder(SM).values()} <= want["Library"]
        assert {b[1] for b in G.BossOrder(SM, False).values()} > want["Library"]  # (false: the whole of it)
    finally:
        ns.CharDB().enteredWing = None
        G.Follow()
    # the others: each wing its own door on the continent (Stratholme's back door and Uldaman's back way in
    # at their own, not the main gate's)
    wings = {20429: ["East", "West", "North"], 20329: ["Main Gate", "Service Entrance"], 20349: ["Orange", "Purple"],
             20070: ["Front Entrance", "Back Entrance"], 20090: ["Front Entrance", "Train Depot"]}
    for lvl, ws in wings.items():
        assert list(ns.Instances[lvl].wings.values()) == ws, lvl
    dm = sorted(e.name for e in G.InstanceEntrances(1).values() if e.level == 20429)
    assert dm == ["Dire Maul: East", "Dire Maul: East (Back Door)", "Dire Maul: North", "Dire Maul: West",
                  "Dire Maul: West (Side Door)"]  # (not the plain "Dire Maul" way in, its wing a guess, at West's door)
    bosses = {lvl: {b[1]: b for b in ns.Instances[lvl].bosses.values()} for lvl in wings}
    assert bosses[20429]["Prince Tortheldrin"].wing == "West" and bosses[20429]["King Gordok"].wing == "North"
    assert bosses[20329]["The Unforgiven"].wing == "Main Gate" and bosses[20329]["Baron Rivendare"].wing == "Service Entrance"
    theradras = bosses[20349]["Princess Theradras"]  # (Maraudon's inner bosses: from either side)
    assert theradras.wing is None and list(theradras.wings.values()) == ["Orange", "Purple"]
    assert G.InWing(theradras, "Purple") and G.InWing(theradras, "Orange")
    # Uldaman's back way in, Gnomeregan's Train Depot: doors into the whole dungeon, every boss from each
    assert all(b.wing is None and b.wings is None for lvl in (20070, 20090) for b in bosses[lvl].values())
    G.ShowInstance(20070, "Back Entrance")
    try:
        assert G.WingBounds(20070, "Back Entrance") is None and len(G.BossOrder(20070)) == len(G.BossOrder(20070, False))
    finally:
        G.Follow()
    service, gate = G.WingEntrance(20329, "Service Entrance"), G.WingEntrance(20329, "Main Gate")
    assert (service[2], service[3]) == pytest.approx((3233.0, -4048.0), abs=5) and abs(gate[3] - service[3]) > 300
    back = G.WingEntrance(20070, "Back Entrance")
    assert (back[2], back[3]) == pytest.approx((-6620.0, -3766.0), abs=5)


def test_removing_the_tram_asks_about_the_walk_through_zones_too_high(game):
    # (reported: the tram works now, but removed from the route, no popup) Ironforge to Goldshire at level 1:
    # by the tram, nothing asked; the tram removed, the walk round goes through zones too high: "Keep this
    # route?", and it isn't drawn until kept
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    fac = ns.CharDB().faction
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4944.0, -1232.0, 0, nil "
                "AGPS_LEVEL_REAL = UnitLevel UnitLevel = function() return 1 end "
                "AGPS_ZONE_REAL = GetMinimapZoneText GetMinimapZoneText = function() return 'The Military Ward' end")
    ns.CharDB().faction = "Alliance"
    try:
        N.Clear()
        N.SetStops(lua.eval("{ { x = -9460, y = 60, cont = 0, name = 'Goldshire' } }"))
        for _ in range(3):
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        tram = [p for p in N.RidePins(N.route).values() if p.kind == "tram"]
        assert tram and not N.RedAsking()  # (by the tram: no zone too high)
        N.SkipRide(tram[0].ride, tram[0].hop, tram[0].title)
        for _ in range(3):
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        assert N.RedAsking()
        assert _shown(lua, lambda w: w._text is not None and "too high for your level 1" in str(w._text))
        G.confirmBox.no._scripts.OnClick(G.confirmBox.no)
        assert len(N.stops) == 0
    finally:
        ns.CharDB().faction = fac
        N.Clear()
        lua.execute("UnitLevel = AGPS_LEVEL_REAL or UnitLevel GetMinimapZoneText = AGPS_ZONE_REAL or GetMinimapZoneText "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()


def test_the_deeprun_tram_has_its_map(game):
    # (reported: in the Deeprun Tram the map was blank) the game puts you on a map of its own there (369):
    # its art, as a dungeon's (Data/Transit.lua), and its name in the title; no dungeon features
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    assert ns.Instances[20369].transit and len(ns.Instances[20369].entrances) == 0
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 0.0, 270.0, 369, 0 AGPS_T = AGPS_T + 1")
    try:
        assert N.PlayerLevel(369) == 20369
        G.Follow()
        G.Update()
        assert str(G.infoName) == "Deeprun Tram"
        quads = int(str(G.Describe()).split("quads=")[1].split()[0])
        assert quads > 0  # (its art drawn)
        assert not any(e.level == 20369 for c in (0, 1) for e in G.InstanceEntrances(c).values())  # (no dungeon icon)
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil AGPS_T = AGPS_T + 1")
        G.Follow()


def test_the_route_stays_shown_while_a_finished_search_works_it_out_again(game):
    # (reported, a video: riding in Mulgore, "Working out the route..." and no route every few seconds) a
    # finished background search drops the route for a recalculation; a long one is worked out in the
    # background, and the player still on the old one sees it meanwhile, not nothing
    lua, ns = game
    N, R = ns.Nav, ns.Router
    x, y = 2254.0, 293.0  # (Brill; the Sepulcher, 2.2k yd: a walk the background works out)
    try:
        N.SetStops(lua.eval("{ { x = 507, y = 1594, cont = 0, name = 'Sepulcher' } }"), False, "red")
        assert N.Route(x, y, 0)  # (the road data and the first route, at once)
        R.WARM, R.SYNC_WALKS = True, False
        assert N.route and not N.warming
        N.SearchDone()  # (a search from the player finished)
        lua.execute("AGPS_T = AGPS_T + 10")
        assert N.Route(x, y, 0) is not None and not N.warming
        assert "Working out" not in str(N.StepsText())
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        N.Clear()


def test_resizing_from_the_corner_turns_on_once_for_1_1_0_saves(game):
    # (asked 2026-10-03) 1.1.0 saved "Lock map size" on for everyone (its default): logging in with 1.1.1 turns
    # resizing from the corner on once; a later choice to turn it off is kept
    lua, ns = game
    db = ns.db
    try:
        lua.execute("AzerothGPSDB = { settings = { gps = { lockSize = true } } }")  # (a 1.1.0 save)
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")
        saved = lua.eval("AzerothGPSDB")
        assert saved.settings.gps.lockSize is False and saved.resizeDefault111
        saved.settings.gps.lockSize = True  # (turned off by the player since)
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")
        assert lua.eval("AzerothGPSDB").settings.gps.lockSize is True
    finally:
        lua.globals().AzerothGPSDB = db
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")


def test_minimap_icons_turn_off_once_for_1_1_7_saves(game):
    # (issue #31) the map's icons on the minimap are off by default; 1.1.7 saved them on for everyone (its default):
    # logging in with 1.1.8 turns them off once; turning them on since is kept, and so is an explicit off
    lua, ns = game
    db = ns.db
    fire = lua.eval("AGPS_FIRE")
    try:
        lua.execute("AzerothGPSDB = { settings = { gps = {} } }")  # (a new player)
        fire("ADDON_LOADED", "AzerothGPS")
        assert lua.eval("AzerothGPSDB").settings.gps.minimapIcons is False
        lua.execute("AzerothGPSDB = { settings = { gps = { minimapIcons = true } } }")  # (a 1.1.7 save)
        fire("ADDON_LOADED", "AzerothGPS")
        saved = lua.eval("AzerothGPSDB")
        assert saved.settings.gps.minimapIcons is False and saved.minimapIconsDefault118
        saved.settings.gps.minimapIcons = True  # (turned on by the player since)
        fire("ADDON_LOADED", "AzerothGPS")
        assert lua.eval("AzerothGPSDB").settings.gps.minimapIcons is True
        lua.execute("AzerothGPSDB = { settings = { gps = { minimapIcons = false } } }")  # (turned off in 1.1.7)
        fire("ADDON_LOADED", "AzerothGPS")
        assert lua.eval("AzerothGPSDB").settings.gps.minimapIcons is False
    finally:
        lua.globals().AzerothGPSDB = db
        fire("ADDON_LOADED", "AzerothGPS")


def test_a_character_whose_name_isnt_known_yet_isnt_saved_as_unknown(game):
    # (seen 2026-10-01 in testing: right after logging in UnitName said "Unknown", and the
    # character's flight paths and faction were saved under "<realm>-Unknown") until the name is known a
    # stand-in for this session; then what went there moves into the character's own record
    lua, ns = game
    lua.execute("AGPS_UN = UnitName\nUnitName = function() return 'Unknown' end")
    try:
        assert ns.CharKey().endswith("-Unknown")
        c = ns.CharDB()
        c.faction = "Alliance"
        c.taxiNodes[1463] = lua.eval("{ nodes = { { nodeID = 5, known = true } } }")
        ns.db.lastChar = ns.CharKey()
        lua.execute("UnitName = function() return 'Newbie' end")
        own = ns.CharDB()
        key = ns.CharKey()
        assert key.endswith("-Newbie") and own.faction == "Alliance" and own.taxiNodes[1463].nodes[1].known
        assert not any(str(k).endswith("-Unknown") for k in ns.db.chars.keys()) and ns.db.lastChar == key
    finally:
        lua.execute("UnitName = AGPS_UN")
        ns.db.chars[lua.eval("GetRealmName and GetRealmName() or '?'") + "-Newbie"] = None


def test_characters_sharing_a_first_name_are_saved_apart_by_their_surnames(game):
    # (2026-11-05, the user's saved file: three characters "Kookies Resto", "Kookies Rlife" and "Kookies Ryummy" were
    # all "<realm>-Kookies", one record of stops, flight paths and hearthstone home) each saved by the whole name; the
    # first-name record from before is copied into each of them the first time, and kept as it was
    lua, ns = game
    realm = lua.eval("GetRealmName and GetRealmName() or '?'")
    lua.execute("AGPS_UN = UnitName")
    old = lua.eval("{ faction = 'Horde', bind = { cont = 0, x = 2268.8, y = 243.4, name = \"Gallows' End Tavern\" },"
                   " taxiNodes = { [1415] = { nodes = { { nodeID = 11, known = true } } } }, flights = {},"
                   " stops = { { x = 100, y = 200, cont = 0 } } }")
    try:
        ns.db.chars[realm + "-Kookies"] = old
        lua.execute("UnitName = function() return 'Kookies', 'Ryummy' end")
        assert ns.CharKey() == realm + "-Kookies Ryummy"
        ryummy = ns.CharDB()
        assert ryummy.bind.name == "Gallows' End Tavern" and ryummy.taxiNodes[1415].nodes[1].known
        assert ryummy.stops[1].x == 100 and ryummy.copiedTo is None
        ryummy.bind = lua.eval("{ cont = 1, x = 1, y = 2, name = 'Razor Hill' }")
        ryummy.stops = None
        lua.execute("UnitName = function() return 'Kookies', 'Resto' end")
        resto = ns.CharDB()
        assert resto.bind.name == "Gallows' End Tavern" and resto.stops[1].x == 100  # (its own copy, not Ryummy's)
        assert ns.db.chars[realm + "-Kookies Ryummy"].bind.name == "Razor Hill"
        kept = ns.db.chars[realm + "-Kookies"]  # (the old record as it was, keep data forever)
        assert kept.bind.name == "Gallows' End Tavern" and kept.stops[1].x == 100
        assert kept.copiedTo[realm + "-Kookies Ryummy"] and kept.copiedTo[realm + "-Kookies Resto"]
        resto.faction = "Alliance"
        assert ns.CharDB().faction == "Alliance"  # (a second call: its own record, not copied again)
        # (no surname, as on a realm without them: the first name alone, as before)
        lua.execute("UnitName = function() return 'Kookies' end")
        assert ns.CharKey() == realm + "-Kookies" and ns.CharDB().bind.name == "Gallows' End Tavern"
    finally:
        lua.execute("UnitName = AGPS_UN")
        for k in ("-Kookies", "-Kookies Ryummy", "-Kookies Resto"):
            ns.db.chars[realm + k] = None


def test_an_empty_realm_name_never_forgets_a_characters_flight_paths(game):
    # (players' reports, 2026-11-21: "AzerothGPS forgot all my unlocked flight paths since the latest update"; Kooki3z's
    # saved file had "-Bowna Lisa", a record with no realm and no flight paths known, beside his realm's own: the
    # client gave an empty realm name at that login) the character's own record by its realm, and a no-realm record
    # already saved taken into it, every flight path either knew kept
    lua, ns = game
    realm = lua.eval("GetRealmName and GetRealmName() or '?'")
    lua.execute("AGPS_UN, AGPS_RN = UnitName, GetRealmName")
    try:
        ns.db.chars[realm + "-Bowna Lisa"] = lua.eval(
            "{ faction = 'Alliance', bind = { name = 'Razor Hill' }, quiet = true, taxiNodes = { [1415] = { time = 100,"
            " nodes = { { nodeID = 11, known = true }, { nodeID = 12, known = false } } } }, flights = {} }")
        ns.db.chars["-Bowna Lisa"] = lua.eval(
            "{ faction = 'Alliance', bind = { name = 'The Crossroads' }, taxiNodes = { [1415] = { time = 200,"
            " nodes = { { nodeID = 11, known = false }, { nodeID = 12, known = true } } },"
            " [1464] = { time = 200, nodes = { { nodeID = 30, known = true } } } } }")
        ns.db.transports = ns.db.transports or lua.table()
        ns.db.transports[""] = lua.eval("{ ['Boat | Dock'] = { side = 1, at = 5 } }")
        ns.db.lastChar = "-Bowna Lisa"
        lua.execute("UnitName = function() return 'Bowna', 'Lisa' end; GetRealmName = function() return '' end")
        # (the realm's name empty: the character's own record, by its realm)
        assert ns.CharKey() == realm + "-Bowna Lisa"
        own = ns.CharDB()
        nodes = own.taxiNodes[1415].nodes
        assert nodes[1].known and nodes[2].known  # (known in either record: known)
        assert own.taxiNodes[1464].nodes[1].known  # (learned while saved under no realm)
        assert ns.db.chars["-Bowna Lisa"] is None and ns.db.lastChar == realm + "-Bowna Lisa"
        # (since the issue started: the record used last wins, the other fills in what it lacks)
        assert own.bind.name == "The Crossroads" and own.quiet is True
        # (a boat's time learned meanwhile: the realm's)
        assert ns.db.transports[""] is None and ns.db.transports[realm]["Boat | Dock"].at == 5
        # (no record of its own and no realm named yet this session: the last realm the client named)
        lua.execute("UnitName = function() return 'Brand', 'New' end")
        assert ns.CharKey() == realm + "-Brand New"
        # (the boats' and zeppelins' timetables too: by the realm, never "")
        assert lua.eval("function(ns, r) return ns.Taxi.Sightings() == ns.db.transports[r] end")(ns, realm)
    finally:
        lua.execute("UnitName, GetRealmName = AGPS_UN, AGPS_RN")
        for k in (realm + "-Bowna Lisa", "-Bowna Lisa", realm + "-Brand New"):
            ns.db.chars[k] = None
        if ns.db.transports and ns.db.transports[realm]:
            ns.db.transports[realm]["Boat | Dock"] = None


def test_a_dungeon_entrance_shows_on_the_inside_map_it_is_in(game):
    # (asked 2026-10-01: the Deadmines' entrance on the Defias Hideout's map too) indoors down in the hideout,
    # by the dungeon's door: its inside map, and the Deadmines' entrance icon on it (click for its map)
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_INDOORS_REAL, AGPS_MZT_REAL = IsIndoors, GetMinimapZoneText
      IsIndoors = function() return true end
      GetMinimapZoneText = function() return "Defias Hideout" end
      AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -11210.0, 1680.0, 0
    """)
    zoom = st.zoom
    try:
        st.zoom = 150.0
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.inside is not None  # (the hideout's inside map)
        icons = _shown(lua, lambda w: w.instance == 20036)
        assert icons, "no Deadmines entrance on the hideout's map"
    finally:
        st.zoom = zoom
        lua.execute("IsIndoors, GetMinimapZoneText = AGPS_INDOORS_REAL, AGPS_MZT_REAL "
                    "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")


def test_the_map_pin_works_as_on_the_games_world_map(game):
    # (asked 2026-10-01) Ctrl + left-click on the map: the map pin there (the game's waypoint, a diamond on the
    # map); Shift + left-click on it: its link in chat; Ctrl + left-click on it: gone. Not a custom pin (not in the
    # shared map data); kept per character, put back as the game's waypoint at login; the game's waypoint set or
    # cleared elsewhere moves it
    lua, ns = game
    G, I = ns.GPS, ns.Import
    lua.execute("""
      AGPS_OLD_MP = { IsControlKeyDown, IsShiftKeyDown, GetCursorPosition, ChatEdit_GetActiveWindow, ChatEdit_InsertLink,
        ChatFrame_OpenChat, UiMapPoint, C_Map.SetUserWaypoint, C_Map.ClearUserWaypoint, C_Map.HasUserWaypoint,
        C_Map.GetUserWaypoint, C_Map.GetUserWaypointHyperlink }
      AGPS_CTRL, AGPS_SHIFT, AGPS_BOX, AGPS_LINK, AGPS_OPENED, AGPS_WP = false, false, nil, nil, nil, nil
      IsControlKeyDown = function() return AGPS_CTRL end
      IsShiftKeyDown = function() return AGPS_SHIFT end
      GetCursorPosition = function() return 300, 300 end
      ChatEdit_GetActiveWindow = function() return AGPS_BOX end
      ChatEdit_InsertLink = function(l) AGPS_LINK = l return true end
      ChatFrame_OpenChat = function(l) AGPS_OPENED = l end
      UiMapPoint = { CreateFromCoordinates = function(m, x, y) return { uiMapID = m, position = { x = x, y = y } } end }
      C_Map.SetUserWaypoint = function(p) AGPS_WP = p end
      C_Map.ClearUserWaypoint = function() AGPS_WP = nil end
      C_Map.HasUserWaypoint = function() return AGPS_WP ~= nil end
      C_Map.GetUserWaypoint = function() return AGPS_WP end
      C_Map.GetUserWaypointHyperlink = function()
        return string.format("|cffffff00|Hworldmap:%d:%d:%d|h[Map Pin Location]|h|r", AGPS_WP.uiMapID,
          math.floor(AGPS_WP.position.x * 10000), math.floor(AGPS_WP.position.y * 10000))
      end
    """)
    frame = lua.globals().AzerothGPSFrame

    def pins():
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        return _shown(lua, lambda w: w.mapPin)

    try:
        ns.CharDB().mapPin = None
        assert not pins()
        x, y, c = G.ClickWorld()
        lua.execute("AGPS_CTRL = true")
        frame._scripts.OnMouseDown(frame, "LeftButton")
        frame._scripts.OnMouseUp(frame, "LeftButton")
        lua.execute("AGPS_CTRL = false")
        mp = I.MapPin()
        assert mp and abs(mp.x - x) < 1 and abs(mp.y - y) < 1
        wp = lua.eval("AGPS_WP")
        assert wp and wp.uiMapID == G.LocateWorld(c, x, y)[0]  # (the game's waypoint too)
        (b,) = pins()
        assert "Shift-click" in b.note and "Ctrl-click" in b.note
        # Shift-click: into the chat box being typed in, else a chat box opened with it
        lua.execute("AGPS_SHIFT, AGPS_BOX = true, {}")
        b._scripts.OnClick(b, "LeftButton")
        assert "worldmap:" in lua.eval("AGPS_LINK")
        lua.execute("AGPS_BOX = nil")
        b._scripts.OnClick(b, "LeftButton")
        assert "worldmap:" in lua.eval("AGPS_OPENED")
        lua.execute("AGPS_SHIFT = false")
        assert I.MapPin()  # (linking doesn't take it away)
        # Ctrl-click on it: gone, from the game too
        lua.execute("AGPS_CTRL = true")
        b._scripts.OnClick(b, "LeftButton")
        lua.execute("AGPS_CTRL = false")
        assert I.MapPin() is None and lua.eval("AGPS_WP") is None and not pins()
        # the game's waypoint set elsewhere (its world map, a link clicked): the pin follows; cleared: gone
        lua.execute("AGPS_WP = UiMapPoint.CreateFromCoordinates(1411, 0.5, 0.5)")
        I.OnUserWaypoint()
        assert I.MapPin() and I.MapPin().cont == 1  # (Durotar: off this map, so not drawn here)
        lua.execute("AGPS_WP = nil")
        I.OnUserWaypoint()
        assert I.MapPin() is None
        # saved per character: at login, put back as the game's waypoint when the game has none
        ns.CharDB().mapPin = lua.eval("{ cont = 1, x = -500, y = -4000 }")
        I.RestoreMapPin()
        assert lua.eval("AGPS_WP") is not None and I.MapPin().x == -500
        # not in the shared map data
        text = ns.Feedback.RoadsText() if ns.Feedback and ns.Feedback.RoadsText else ""
        assert "-500" not in str(text)
    finally:
        ns.CharDB().mapPin = None
        lua.execute("""IsControlKeyDown, IsShiftKeyDown, GetCursorPosition, ChatEdit_GetActiveWindow, ChatEdit_InsertLink,
          ChatFrame_OpenChat, UiMapPoint, C_Map.SetUserWaypoint, C_Map.ClearUserWaypoint, C_Map.HasUserWaypoint,
          C_Map.GetUserWaypoint, C_Map.GetUserWaypointHyperlink = unpack(AGPS_OLD_MP, 1, 12)""")


def test_a_boss_seen_dead_counts_without_encounter_or_combat_log_events(game):
    # (reported 2026-10-01 in testing: Oggleflint dead at the player's feet, targeted, and the boss
    # route still said "Next: Oggleflint"; no encounter events came, and the combat log's kill didn't count)
    # a boss's corpse targeted (or moused over, looted, still targeted when combat ends): its kill counted
    lua, ns = game
    N = ns.Nav
    DM = 20036
    lua.execute("""
      AGPS_OLD_U = { GetInstanceInfo, time, UnitExists, UnitIsDead, UnitGUID, UnitName }
      GetInstanceInfo = function() return "Deadmines", "party", 1, "Normal", 5, 0, false, 36 end
      time = function() return 50000 end
      UnitExists = function(u) return u == "target" end
      UnitIsDead = function(u) return AGPS_DEAD end
      UnitGUID = function(u) return "Creature-0-5250-36-12-644-00001A2B3C" end
      UnitName = function(u) return "Rhahk'Zor" end
      AGPS_DEAD = false
    """)
    try:
        assert ns.CheckDeadUnit("target") == 0  # (alive)
        assert ns.CheckDeadUnit("mouseover") == 0  # (no such unit)
        lua.execute("AGPS_DEAD = true")
        assert ns.CheckDeadUnit("target") == 1 and ns.CheckDeadUnit("target") == 0  # (once)
        assert N.BossDead(lua.table(cont=DM, boss=644))
        lua.execute('GetInstanceInfo = function() return "Elwynn Forest", "none", 0, "", 0, 0, false, 0 end')
        assert ns.CheckDeadUnit("target") == 0  # (not in a dungeon)
    finally:
        lua.execute("GetInstanceInfo, time, UnitExists, UnitIsDead, UnitGUID, UnitName = unpack(AGPS_OLD_U, 1, 6)")
        ns.CharDB().bossKills = lua.table()


def test_a_stop_at_the_deadmines_from_outside_goes_to_the_defias_hideouts_way_in(game):
    # (asked 2026-10-01) routing to the Deadmines from outside: the stop is the Defias Hideout's way in (the
    # house in Moonbrook), and the hideout's map takes it from there; from down in the hideout, the door
    lua, ns = game
    G = ns.GPS
    door = next(e for e in ns.Instances[20036].entrances.values() if e[1] == 0)
    hideout = next(c for c in ns.Caves[0].values() if c[2] == "cave35530")
    mouths = [(hideout[5][k], hideout[5][k + 1]) for k in range(1, len(hideout[5]), 2)]
    via = G.ApproachEntrance(0, door[2], door[3], 0, 2254.0, 293.0)  # (from Brill)
    assert via and (via.x, via.y) in mouths and "Defias Hideout" in via.name and via.cont == 0
    assert G.ApproachEntrance(0, door[2] + 200, door[3], 0, 2254.0, 293.0) is None  # (not the door: as it is)
    # down in the hideout already: the door
    real = ns.Nav.Indoors
    ns.Nav.Indoors = lua.eval("function() return true end")
    try:
        assert G.ApproachEntrance(0, door[2], door[3], 0, door[2] + 3.0, door[3] + 3.0) is None
    finally:
        ns.Nav.Indoors = real
    # a stop made at the door (its icon double-clicked) from outside, onto a route: at the way in
    N = ns.Nav
    N.Clear()
    N.SetStops(lua.eval("{ { x = 2300, y = 300, cont = 0, name = 'Brill road' } }"), False, "red")
    try:
        assert G.AddStopAt(door[2], door[3], "Deadmines", 0)
        added = [N.stops[i] for i in range(1, len(N.stops) + 1) if N.stops[i].name != "Brill road"]
        assert len(added) == 1 and (added[0].x, added[0].y) in mouths
    finally:
        N.Clear()


def test_a_boss_is_marked_defeated_by_hand_with_a_right_click(game):
    # (reported 2026-10-01: Rhahk'Zor dead and looted, still "Next") the game may hide who died from addons:
    # a right-click on a boss's icon in the dungeon's map marks it defeated, and again, not; and a kill check
    # that only gets hidden values says so in the saved log (and counts nothing)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    DM = 20036
    try:
        G.ShowInstance(DM)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        (b,) = _shown(lua, lambda w: w.bossKey == 644)
        assert not N.BossDead(lua.table(cont=DM, boss=644)) and "mark defeated" in b.note
        b._scripts.OnClick(b, "RightButton")
        assert N.BossDead(lua.table(cont=DM, boss=644))
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        (b,) = _shown(lua, lambda w: w.bossKey == 644)
        assert b.dead and "not defeated" in b.note
        b._scripts.OnClick(b, "RightButton")
        assert not N.BossDead(lua.table(cont=DM, boss=644))
        # hidden values: nothing counted, and the log says why
        lua.execute("""
          AGPS_OLD_U = { GetInstanceInfo, UnitExists, UnitIsDead, UnitGUID, UnitName, issecretvalue }
          GetInstanceInfo = function() return "Deadmines", "party", 1, "Normal", 5, 0, false, 36 end
          UnitExists = function() return true end
          UnitIsDead = function() return true end
          AGPS_SECRET = {}
          UnitGUID = function() return AGPS_SECRET end
          UnitName = function() return AGPS_SECRET end
          issecretvalue = function(v) return v == AGPS_SECRET end
        """)
        try:
            assert ns.CheckDeadUnit("target") == 0
            log = ns.db.killLog
            assert "guid hidden, name hidden -> 0" in log[len(log)]
        finally:
            lua.execute("GetInstanceInfo, UnitExists, UnitIsDead, UnitGUID, UnitName, issecretvalue = unpack(AGPS_OLD_U, 1, 6)")
    finally:
        ns.CharDB().bossKills = lua.table()
        G.Follow()


def test_in_a_dungeon_a_double_click_marks_where_you_are(game):
    # (asked 2026-10-01) the game hides the player's position in a dungeon: a double-click on its map, inside it,
    # puts their class icon there (not a stop); a right-click on it clears it; leaving the dungeon clears it.
    # The panel at the top says how (the boss's right-click too)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      AGPS_OLD_D = { UnitPosition, GetInstanceInfo, UnitClass, CLASS_ICON_TCOORDS }
      UnitPosition = function() return nil end
      GetInstanceInfo = function() return "Deadmines", "party", 1, "Normal", 5, 0, false, 36 end
      UnitClass = function() return "Mage", "MAGE" end
      CLASS_ICON_TCOORDS = { MAGE = { 0.25, 0.5, 0, 0.25 } }
    """)
    try:
        N.Clear()
        ns.CharDB().youHere = None
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text and w._shown]
        assert any("Double-click: mark where you are" in t and "Right-click a boss" in t for t in texts)
        G.AddPending(10.0, -20.0)
        me = G.YouHere()
        assert me and me.level == 20036 and len(N.stops) == 0  # (no stop made)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        (pin,) = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.dot and w.edge and w._scripts.OnClick]
        assert pin.dot._tex == G.CLASS_SHEET
        pin._scripts.OnClick(pin, "RightButton")
        assert G.YouHere() is None
        G.AddPending(0.0, 0.0)
        assert G.YouHere()
        # out of the dungeon: gone
        lua.execute('UnitPosition = AGPS_OLD_D[1] GetInstanceInfo = function() return "Tirisfal Glades", "none", 0, "", 0, 0, false, 0 end')
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.YouHere() is None
    finally:
        lua.execute("UnitPosition, GetInstanceInfo, UnitClass, CLASS_ICON_TCOORDS = unpack(AGPS_OLD_D, 1, 4)")
        ns.CharDB().youHere = None
        G.Follow()


def test_a_flights_clock_starts_without_the_control_events(game):
    # (reported 2026-10-01, a video: "lands in 3m 00s" for a whole minute) this client doesn't fire
    # PLAYER_CONTROL_LOST/GAINED for flights, so the flight's start was "now" at every redraw: the clock starts
    # the first time the flight is seen, and ends the first time the player's seen off it
    lua, ns = game
    T = ns.Taxi
    lua.execute("""
      AGPS_OLD_T = { UnitOnTaxi, GetTime }
      AGPS_TAXI, AGPS_NOW = true, 1000
      UnitOnTaxi = function() return AGPS_TAXI end
      GetTime = function() return AGPS_NOW end
    """)
    try:
        f = T.Current()
        assert f.start == 1000
        lua.execute("AGPS_NOW = 1060")
        assert T.Current().start == 1000  # (60 s into the flight: still from take-off)
        lua.execute("AGPS_TAXI = false")
        assert T.Current() is None  # (landed)
        lua.execute("AGPS_TAXI, AGPS_NOW = true, 2000")
        assert T.Current().start == 2000  # (the next flight: its own clock)
    finally:
        lua.execute("AGPS_TAXI = false")
        T.Current()
        lua.execute("UnitOnTaxi, GetTime = unpack(AGPS_OLD_T, 1, 2)")


def test_the_map_is_resized_by_its_corner_when_the_size_isnt_locked(game):
    # (asked 2026-10-02) a grip in the map window's bottom-right corner; a left-drag on it sizes the window (square,
    # its top-left staying put), within the slider's range. (asked 2026-10-03) on by default ("Resize from the
    # corner"); off while the map's position is locked, and back when it's unlocked, the option itself unchanged
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    size, point = st.size, st.point
    lua.execute("AGPS_OLD_CUR = GetCursorPosition\nGetCursorPosition = function() return AGPS_CX, AGPS_CY end")
    lua.execute("UIParent.GetWidth = function() return 1920 end UIParent.GetHeight = function() return 1080 end")
    try:
        assert st.lockSize is False and not st.locked  # (on by default)
        G.ApplySettings()
        grip = G.sizeGrip
        assert grip and grip._shown
        st.locked = True  # (the map's position locked: no resizing either)
        G.ApplySettings()
        assert not grip._shown and st.lockSize is False
        st.locked = False  # (unlocked: back)
        G.ApplySettings()
        assert grip._shown
        st.lockSize = True  # (the option off)
        G.ApplySettings()
        assert not grip._shown
        st.lockSize = False
        G.ApplySettings()
        assert grip._shown
        # (the stand-in's frames: left 100, top 500, scale 1) the corner dragged to (700, 0): 600 across
        lua.execute("AGPS_CX, AGPS_CY = 700, 0")
        grip._scripts.OnMouseDown(grip, "LeftButton")
        grip._scripts.OnUpdate(grip, 0.02)
        assert st.size == 600 and st.point[1] == "TOPLEFT" and st.point[4] == 100 and st.point[5] == 500
        lua.execute("AGPS_CX, AGPS_CY = 5000, -4000")  # (past the slider's top: the screen's height less the title bar)
        grip._scripts.OnUpdate(grip, 0.02)
        assert st.size == 1030
        grip._scripts.OnMouseUp(grip, "LeftButton")
        lua.execute("AGPS_CX, AGPS_CY = 300, 300")
        grip._scripts.OnUpdate(grip, 0.02)
        assert st.size == 1030  # (let go: no more sizing)
    finally:
        st.lockSize, st.locked, st.size, st.point = False, False, size, point
        lua.execute("GetCursorPosition = AGPS_OLD_CUR UIParent.GetWidth = nil UIParent.GetHeight = nil")
        G.ApplySettings()


def test_zeppelin_timetables_seen_before_1_1_2_are_cleared_once(game):
    # (2026-10-04) the departures 1.1.1 and before saved were mostly a ride's arrival taken for a departure at the far
    # dock: cleared once on logging in with 1.1.2 (no timer until the next ride, not a wrong one); later ones kept
    lua, ns = game
    db = ns.db
    try:
        lua.execute("AzerothGPSDB = { transports = { Realm = { ['A | B'] = { side = 1, at = 5 } } } }")  # (a 1.1.1 save)
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")
        saved = lua.eval("AzerothGPSDB")
        assert saved.transports is None and saved.transports112
        lua.execute("AzerothGPSDB.transports = { Realm = { ['A | B'] = { side = 2, at = 9 } } }")  # (seen since)
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")
        assert lua.eval("AzerothGPSDB").transports.Realm["A | B"].at == 9
    finally:
        lua.globals().AzerothGPSDB = db
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")


def test_every_question_shows_over_the_map_while_it_shows(game):
    # (asked 2026-10-04, a screenshot: "Don't use the zeppelin ...?" in the middle of the screen) every question
    # (G.Ask: the map's yes / no, a ride left out, a route someone shares) over the map's middle while it shows, with
    # it; mid-screen only while the map is hidden
    lua, ns = game
    G, I = ns.GPS, ns.Import
    frame = lua.globals().AzerothGPSFrame
    assert frame._shown
    for ask in (lambda: G.Confirm("Route there anyway?", None, None) and G.confirmBox,
                lambda: G.Ask("AzerothGPSRideOff", "Don't use the zeppelin?", "Don't Use", "Cancel", None, None,
                              lua.eval("{ timeout = 30 }")),
                lambda: (I.Offer("Friend-Realm", lua.eval("{ { x = 2250, y = 250, cont = 0, name = 'Brill' } }")),
                         I.offerBox)[1]):
        box = ask()
        assert box.onMap and box._shown
        assert box._pt[0 + 1] == "CENTER" and box._pt[2] is not None and box._pt[2] != lua.globals().UIParent
        box.no._scripts.OnClick(box.no)
    frame._shown = False
    dir = ns.Arrow.dir
    was = dir._shown
    dir._shown = False
    try:
        box = G.Ask("AzerothGPSRideOff", "Don't use the zeppelin?", "Don't Use", "Cancel", None, None)
        assert not box.onMap and box._shown and lua.eval("rawequal")(box, lua.globals().AzerothGPSRideOff)
        box.no._scripts.OnClick(box.no)
    finally:
        frame._shown = True
        dir._shown = was


def test_a_question_pops_up_next_to_the_directions_with_the_map_closed_or_the_minimap(game):
    # (asked 2026-11-12 for 1.2.4: "when clicking reroute for quest route on directions and there is a elite quest
    # question, it doesn't pop up when using just the mini map and the map isn't open and blocks the reroute. This
    # should pop up next to the directions in this condition")
    lua, ns = game
    G = ns.GPS
    frame, dir = lua.globals().AzerothGPSFrame, ns.Arrow.dir
    was = (frame._shown, dir._shown, G.MinimapMode)
    same = lua.eval("rawequal")
    try:
        dir._shown = True
        for shown, square in ((False, False), (True, True)):  # (the map closed; the map only the minimap square)
            frame._shown = shown
            lua.globals().AGPS_SQUARE = square
            G.MinimapMode = lua.eval("function() return AGPS_SQUARE end")
            box = G.Ask("AzerothGPSGroupQuest", "Elite quest. Keep it in your route?", "Keep", "Leave Out", None, None)
            assert box._shown and box.byDirections and not box.onMap
            assert same(box._pt[2], dir) and box._pt[1] in ("TOPLEFT", "TOPRIGHT")
            assert box._strata == "DIALOG"
            box.no._scripts.OnClick(box.no)
        # the map open as itself: over its middle, as before
        frame._shown = True
        lua.globals().AGPS_SQUARE = False
        box = G.Ask("AzerothGPSGroupQuest", "Elite quest. Keep it in your route?", "Keep", "Leave Out", None, None)
        assert box.onMap and not box.byDirections
        box.no._scripts.OnClick(box.no)
    finally:
        frame._shown, dir._shown, G.MinimapMode = was


def test_a_one_button_message_has_no_no_button_over_the_map_too(game):
    # (2026-11-18, Kooki3z: the import order notice showed "Got It" and "No" over the open map: "No shouldn't be an
    # option, just Got It". The map's own placement dropped `single`.)
    lua, ns = game
    G = ns.GPS
    frame, dir = lua.globals().AzerothGPSFrame, ns.Arrow.dir
    was = (frame._shown, dir._shown, G.MinimapMode)
    try:
        G.MinimapMode = lua.eval("function() return false end")
        for shown, by_dir in ((True, False), (False, True), (False, False)):  # (over the map; by the directions; alone)
            frame._shown, dir._shown = shown, by_dir
            box = G.Ask("AzerothGPSTestTold", "Something told.", "Got It", None, None, None, lua.table(single=True))
            assert box._shown and box.yes._shown and not box.no._shown, (shown, by_dir)
            box.yes._scripts.OnClick(box.yes)
    finally:
        frame._shown, dir._shown, G.MinimapMode = was

def test_the_map_is_square_or_any_shape_up_to_a_4k_screen(game):
    # (asked 2026-10-04: big maps "up to 4k display", then "just support free sizing? just make square default and have
    # a check box available to enable the window sizing via corner pull to freely size the map however") square by
    # default, up to the screen's shorter side; "Any shape" on: the corner sets the width and the height apart, each up
    # to the screen; the slider keeps the shape; off again: square at its height; the map redraws at any shape
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    size, point = st.size, st.point
    lua.execute("AGPS_OLD_CUR = GetCursorPosition\nGetCursorPosition = function() return AGPS_CX, AGPS_CY end")
    lua.execute("UIParent.GetWidth = function() return 3840 end UIParent.GetHeight = function() return 2160 end")
    try:
        assert not st.freeSize and tuple(G.MapSize(450)) == (450, 450)  # (square by default, as before)
        assert G.SizeMax() == 2110  # (a 4K screen's whole height, less the title bar and logo over the map)
        st.lockSize, st.locked = False, False
        G.ApplySettings()
        grip = G.sizeGrip
        # square: the corner 1600 across, 500 down (the stand-in's left 100, top 500): a 1600 square
        lua.execute("AGPS_CX, AGPS_CY = 1700, 0")
        grip._scripts.OnMouseDown(grip, "LeftButton")
        grip._scripts.OnUpdate(grip, 0.02)
        grip._scripts.OnMouseUp(grip, "LeftButton")
        assert st.size == 1600 and tuple(G.MapSize()) == (1600, 1600)
        # any shape: the same drag, 1600 wide and 500 tall
        st.freeSize, st.width = True, st.size
        grip._scripts.OnMouseDown(grip, "LeftButton")
        grip._scripts.OnUpdate(grip, 0.02)
        grip._scripts.OnMouseUp(grip, "LeftButton")
        assert (st.width, st.size) == (1600, 500) and tuple(G.MapSize()) == (1600, 500)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.ApplySettings()
        G.Update()  # (wide: not the frame's pcall, a failure fails the test)
        # past the screen: 3840 x 2110 at most (the title bar and logo over it on the screen too)
        lua.execute("AGPS_CX, AGPS_CY = 9000, -9000")
        grip._scripts.OnMouseDown(grip, "LeftButton")
        grip._scripts.OnUpdate(grip, 0.02)
        grip._scripts.OnMouseUp(grip, "LeftButton")
        assert (st.width, st.size) == (3840, 2110)
        st.width, st.size = 1600, 500
        assert tuple(G.MapSize(1000)) == (3200, 1000)  # (at another height: the shape kept)
        st.freeSize, st.width = False, None  # (off: square again, at its height)
        assert tuple(G.MapSize()) == (500, 500)
    finally:
        st.size, st.point, st.freeSize, st.width = size, point, False, None
        lua.execute("GetCursorPosition = AGPS_OLD_CUR UIParent.GetWidth = nil UIParent.GetHeight = nil")
        G.ApplySettings()


def test_a_narrow_any_shape_map_never_grows_taller_and_its_title_bar_stays_on_the_screen(game):
    # (2026-10-06, a screenshot: "Any shape" dragged about 150 wide ran the screen's whole height, its title bar off the
    # top, and it couldn't be moved any more) the width and the height each have their own minimum (the quick buttons
    # going right need the width, those going up the height): narrowing stops at the width's and never makes the map
    # taller; it's never taller than the screen less its title bar and logo, which are kept on the screen with it; a
    # size saved that way shows in range
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    frame = lua.globals().AzerothGPSFrame
    saved = (st.size, st.point, st.freeSize, st.width, st.locked, st.windowFrame, st.quick)
    chrome = G.chrome
    lua.execute("AGPS_OLD_CUR = GetCursorPosition\nGetCursorPosition = function() return AGPS_CX, AGPS_CY end")
    try:
        st.lockSize, st.locked, st.quick = False, False, None  # (the default quick buttons: two going right)
        st.freeSize, st.width, st.size = True, 450, 450
        G.ApplySettings()
        assert G.ScreenKnown() and tuple(G.Screen()) == (1920, 1080)  # (the stand-in's screen)
        minw = G.QuickMinWidth()
        assert minw == 360 and G.QuickCapacityAt(minw, 450)[1] >= 2 > G.QuickCapacityAt(minw - 10, 450)[1]
        grip = G.sizeGrip
        # (the stand-in's frames: left 100, top 500) the corner 450 down, narrower and narrower
        for w in (400, 360, 350, 300, 250, 200, 150):
            lua.execute(f"AGPS_CX, AGPS_CY = {100 + w}, 50")
            grip._scripts.OnMouseDown(grip, "LeftButton")
            for _ in range(3):  # (each tick reads the shape the last one set)
                grip._scripts.OnUpdate(grip, 0.02)
            grip._scripts.OnMouseUp(grip, "LeftButton")
            assert (st.width, st.size) == (max(w, minw), 450), w  # (it grew to 470, 650, 930, then 1080 tall)
            assert (frame._w, frame._h) == (max(w, minw), 450)
        # the Width slider and /agps size too
        st.width = 450
        ns.Options.Show()
        widgets = list(lua.eval("AGPS_WIDGETS").values())
        width_s = next(w for w in widgets if w.title and w.slider and w.title._text == "Width")
        width_s.slider._scripts.OnValueChanged(width_s.slider, 150)
        assert st.width == minw and st.size == 450
        lua.globals().SlashCmdList.AZEROTHGPS("size 500")
        assert (st.width, st.size) == (minw, 500)
        # never taller than the screen with the title bar and logo over it
        assert G.TopRoom() >= 22 + 20 and G.SizeMax() == 1030
        assert G.SizeMax() + G.TopRoom() + G.BOTTOM_ROOM <= 1080
        lua.execute("AGPS_CX, AGPS_CY = 9000, -9000")
        grip._scripts.OnMouseDown(grip, "LeftButton")
        grip._scripts.OnUpdate(grip, 0.02)
        grip._scripts.OnMouseUp(grip, "LeftButton")
        assert (st.width, st.size) == (1920, 1030)
        # a size saved by the bug shows in range: as wide as the buttons need, the title bar's room left
        st.width, st.size = 150, 1080
        G.ApplySettings()
        assert (frame._w, frame._h) == (minw, 1030) and tuple(G.MapSize()) == (minw, 1030)
        # what's over the map's top is kept on the screen with it: the window frame's title bar and logo, else the
        # Move tab (unlocked), else nothing
        G.chrome = lua.eval("CreateFrame('Frame', nil, UIParent)")
        G.ApplySettings()
        assert tuple(frame.GetClampRectInsets(frame)) == (0, 0, G.TopRoom(), 0)
        G.chrome = chrome
        st.windowFrame = False
        G.ApplySettings()
        assert tuple(frame.GetClampRectInsets(frame)) == (0, 0, G.MOVE_TAB_ROOM, 0)
        st.locked = True
        G.ApplySettings()
        assert tuple(frame.GetClampRectInsets(frame)) == (0, 0, 0, 0)
    finally:
        G.chrome = chrome
        st.size, st.point, st.freeSize, st.width, st.locked, st.windowFrame, st.quick = saved
        lua.execute("GetCursorPosition = AGPS_OLD_CUR")
        G.ApplySettings()


def test_the_direction_window_is_wide_enough_for_a_turn_and_a_name(game):
    # (asked 2026-10-04, a screenshot at the default size: "Continue straight, then slight right in 180 yd" wrapped)
    # wider by default; a window still at the old default gets the new one once, a size the player chose stays
    lua, ns = game
    assert tuple(ns.DEFAULTS.gps.arrowSize.values()) == (370, 97)
    db = ns.db
    try:
        lua.execute("AzerothGPSDB = { settings = { gps = { arrowSize = { 289, 97 } } } }")
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")
        assert tuple(lua.eval("AzerothGPSDB").settings.gps.arrowSize.values()) == (370, 97)
        lua.execute("AzerothGPSDB = { settings = { gps = { arrowSize = { 300, 120 } } } }")
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")
        assert tuple(lua.eval("AzerothGPSDB").settings.gps.arrowSize.values()) == (300, 120)
    finally:
        lua.globals().AzerothGPSDB = db
        lua.eval("AGPS_FIRE")("ADDON_LOADED", "AzerothGPS")


def test_any_shape_splits_the_size_slider_into_height_and_width(game):
    # (asked 2026-10-04: "enabling this should split the Size slider into 2 sliders, to set width/height manually")
    # square: one Size slider; "Any shape" on: Height and, beside it, Width, each setting its own side
    lua, ns = game
    st = ns.settings.gps
    size = st.size
    lua.execute("UIParent.GetWidth = function() return 1920 end UIParent.GetHeight = function() return 1080 end")
    try:
        ns.Options.Show()
        widgets = list(lua.eval("AGPS_WIDGETS").values())
        holders = [w for w in widgets if w.title and w.slider]
        size_s = next(h for h in holders if h.title._text in ("Size", "Height"))
        width_s = next(h for h in holders if h.title._text == "Width")
        ns.Options.Refresh()
        assert size_s.title._text == "Size" and not width_s._shown
        st.freeSize, st.width = True, st.size
        ns.Options.Refresh()
        assert size_s.title._text == "Height" and width_s._shown
        # (asked 2026-10-04) and a note: the corner on the map sizes it too, while the map isn't locked
        note = next(w for w in widgets if w._kind == "FontString" and str(w._text).startswith("While Lock map position is off"))
        assert note._shown and "corner" in note._text
        width_s.slider._scripts.OnValueChanged(width_s.slider, 700)
        # (320: above the quick buttons' least height, 310 since Quick Find went up the column, 2026-11-14)
        size_s.slider._scripts.OnValueChanged(size_s.slider, 320)
        assert (st.width, st.size) == (700, 320)
        st.freeSize, st.width = False, None
        ns.Options.Refresh()
        assert size_s.title._text == "Size" and not width_s._shown and not note._shown
    finally:
        st.freeSize, st.width, st.size = False, None, size
        lua.execute("UIParent.GetWidth = nil UIParent.GetHeight = nil")
        ns.GPS.ApplySettings()


def test_a_still_view_keeps_its_tiles_and_icons_and_a_big_map_redraws_less(game):
    # (asked 2026-10-04, `agps perf` at size 1054 zoomed out: 10 ms a redraw, 691 over a frame, mostly placing the same
    # tiles and icons again) the view hardly moved (under STILL_PX): the tiles and icons kept, not laid out again;
    # placed again once it moves, TILE_REFRESH / ICON_REFRESH on anyway, or a forced redraw; a map over BIG_MAP
    # across redraws at most BIG_MAP_HZ a second
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    size, zoom, x0 = st.size, st.zoom, float(lua.eval("AGPS_POS[1]"))
    lua.execute("""
      AGPS_LAYOUT = { tiles = 0, icons = 0 }
      AGPS_REAL = { m = AGPS_NS.GPS.LayoutMinimap, z = AGPS_NS.GPS.LayoutZone, p = AGPS_NS.GPS.LayoutPois }
      AGPS_NS.GPS.LayoutMinimap = function(...) AGPS_LAYOUT.tiles = AGPS_LAYOUT.tiles + 1 return AGPS_REAL.m(...) end
      AGPS_NS.GPS.LayoutZone = function(...) AGPS_LAYOUT.tiles = AGPS_LAYOUT.tiles + 1 return AGPS_REAL.z(...) end
      AGPS_NS.GPS.LayoutPois = function(...) AGPS_LAYOUT.icons = AGPS_LAYOUT.icons + 1 return AGPS_REAL.p(...) end
    """)
    counts = lua.eval("AGPS_LAYOUT")
    try:
        st.zoom = 2000
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 5")
        G.Update()
        t0, i0 = counts.tiles, counts.icons
        for k in range(5):  # (a step of 0.2 yd at 2000 yd to the edge: well under half a pixel)
            lua.execute(f"AGPS_T = AGPS_T + 0.05 AGPS_POS[1] = {x0 + 0.2 * (k + 1)}")
            G.Update()
        assert (counts.tiles, counts.icons) == (t0, i0)  # (kept)
        lua.execute("AGPS_T = AGPS_T + 0.6")
        G.Update()
        # (an ICON_REFRESH with the signature unchanged: no gather, only the docks' countdowns reset)
        assert counts.tiles == t0 and counts.icons == i0
        lua.execute("AGPS_T = AGPS_T + 2.1")
        G.Update()
        assert counts.tiles == t0  # (still where they were laid: kept past TILE_REFRESH, issue #191)
        lua.execute(f"AGPS_T = AGPS_T + {G.TILE_REFRESH_STILL}")
        G.Update()
        assert counts.tiles == t0 + 1  # (the tiles after TILE_REFRESH_STILL)
        # moved within the tiles' overdraw (they're laid to 1.42 x the zoom): kept, the layer panned to fit
        # (laid afresh at one center first: the icons' laid center lags the tiles' otherwise, and the offsets
        # compared below are each from its own layer's center)
        G.drawVersion = G.drawVersion + 1
        lua.execute("AGPS_T = AGPS_T + 0.05")
        G.Update()
        t0, i0 = counts.tiles, counts.icons
        lua.execute(f"AGPS_T = AGPS_T + 0.05 AGPS_POS[1] = {x0 + 60}")
        G.Update()
        assert counts.tiles == t0 and counts.icons == i0  # (both panned, neither placed again)
        off = G.quadLayer._pt
        assert off[1] == "CENTER" and off[5] < -1  # (the player went north: the laid tiles sit south on the screen)
        # the icons' layer moved the same way (laid at the same center)
        poff = G.poiLayer._pt
        assert abs(poff[4] - off[4]) < 0.01 and abs(poff[5] - off[5]) < 0.01
        # the panned tiles sit exactly where a fresh layout would put them
        vx, vy, vcont, vrot, vs, vhalf = G.ViewState()
        fresh = {q[1]: (q[2], q[3], q[4], q[5]) for q in G.LayoutMinimap(vx, vy, 0, vrot, vhalf / vs, vhalf).values()}
        kept_quads = list(G.laidTiles.quads.values())
        matched = 0
        for q in kept_quads:
            f = fresh.get(q[1])
            # (a tile at the layout's own edge is cropped to it, outside the view either way: whole tiles only)
            if f is not None and abs(q[4] - f[2]) < 0.01 and abs(q[5] - f[3]) < 0.01:
                assert abs(q[2] + off[4] - f[0]) < 0.1 and abs(q[3] + off[5] - f[1]) < 0.1, (q[1], q[2], q[3], off[4], off[5], f)
                matched += 1
        assert matched >= 3  # (the same tiles, through the layer's offset)
        t1 = counts.tiles  # (the check's own fresh layout counted too)
        # moved past the overdraw: laid out afresh, the layer back at the middle
        lua.execute(f"AGPS_T = AGPS_T + 0.05 AGPS_POS[1] = {x0 + 900}")
        G.Update()
        assert counts.tiles == t1 + 1
        assert G.quadLayer._pt[4] == 0 and G.quadLayer._pt[5] == 0
        G.drawVersion = G.drawVersion + 1  # (a forced redraw: placed again)
        G.Update()
        assert counts.tiles == t1 + 2
        # an icon refresh with nothing changed skips the gather; gathered for real every ICON_FULL_REFRESH
        i1 = counts.icons
        lua.execute("AGPS_T = AGPS_T + 0.6")
        G.Update()
        assert counts.icons == i1
        lua.execute("AGPS_T = AGPS_T + %f" % (G.ICON_FULL_REFRESH + 0.1,))
        G.Update()
        assert counts.icons == i1 + 1
        # the redraw rate: the option on a normal map, at most 10 a second on one over 800 across
        st.hz, st.size = 20, 450
        assert G.RedrawHz() == 20
        st.size = 1054
        assert G.RedrawHz() == 10
        st.hz = 5
        assert G.RedrawHz() == 5
    finally:
        lua.execute(f"""
          AGPS_NS.GPS.LayoutMinimap, AGPS_NS.GPS.LayoutZone, AGPS_NS.GPS.LayoutPois = AGPS_REAL.m, AGPS_REAL.z, AGPS_REAL.p
          AGPS_POS[1] = {x0}
        """)
        st.size, st.zoom, st.hz = size, zoom, 20
        G.ApplySettings()


def test_unsaved_changes_are_counted_but_no_save_or_dismiss_shows(game):
    # (asked 2026-10-04: the game saves AzerothGPSDB only at logout, quitting and /reload) pins added or removed, roads
    # and walls drawn or taken back, dungeon entrances learned: counted (ns.unsaved, API.SetUnsaved); the pin dialog
    # says when a pin is saved. (asked 2026-11-17: "Don't show save/dismiss anymore and remove that setting") no Save or
    # Dismiss button over Clear Route with something unsaved, in or out of combat, and no "Remind me to save" setting
    lua, ns = game
    G, P, T = ns.GPS, ns.Pins, ns.Taxi
    lua.execute("AGPS_RELOADED = 0 ReloadUI = function() AGPS_RELOADED = AGPS_RELOADED + 1 end")

    def shown_save_dismiss():
        return {id(w) for w in lua.eval("AGPS_WIDGETS").values()
                if w._shown and w._text in ("Save", "Dismiss")}

    try:
        ns.ResetUnsaved()
        before = shown_save_dismiss()
        assert G.saveBtn is None and G.dismissBtn is None and G.RefreshSaveButton is None
        assert ns.DismissUnsaved is None and ns.DEFAULTS.gps.askToSave is None
        p = P.Add(lua.eval("{ level = 0, x = 2250, y = 250, name = 'Crash Pin' }"))
        G.ApplySettings()
        assert ns.unsaved == 1 and shown_save_dismiss() == before
        # (asked 2026-10-04: a pin made and removed again before a save: nothing to save)
        P.Remove(p)
        assert ns.unsaved == 0
        p = P.Add(lua.eval("{ level = 0, x = 2250, y = 250, name = 'Crash Pin 2' }"))
        P.Remove(p)
        # a pin saved before, removed now: one change
        old = lua.eval("{ level = 0, x = 2200, y = 260, name = 'Old Pin', time = 1700000000 }")
        own = P.Own()
        own[len(own) + 1] = old
        P.Remove(old)
        assert ns.unsaved == 1
        # (a way into a dungeon learned: where the player stood outside just before)
        ns.db.entrances = None
        now = float(lua.eval("AGPS_T")) + 1
        T.NoteOutside(now, 2250.0, 250.0, 0)
        assert T.NoteEntrance(36, now) and ns.unsaved == 2
        for combat in (True, False):
            ns.inCombat = combat
            G.ApplySettings()
            assert shown_save_dismiss() == before
        assert lua.eval("AGPS_RELOADED") == 0  # (nothing reloads by itself)
        P.OpenEditor(lua.eval("{ level = 0, x = 2250, y = 250 }"))
        dlg = [w for w in lua.eval("AGPS_WIDGETS").values() if w.saveNote]
        assert dlg and dlg[0].saveNote._text == "Saved at logout or /reload"
    finally:
        ns.ResetUnsaved()
        ns.inCombat = False


def test_a_companion_addon_adds_a_page_to_the_options(game):
    # (API 13, asked 2026-10-05 for a plugin) AzerothGPS.AddOptionsPage: a page after the built-in ones, built with
    # the same helpers (check, slider with a function for its text, choice, text, button, header, note); one added
    # after the window exists is added then; the same owner again replaces it; a plugin's error stays in its page;
    # RefreshOptions reads get() again; ShowOptions opens that page
    lua, ns = game
    A = lua.globals().AzerothGPS
    lua.execute("""
      ODO = { keep = 30, after = "simple", on = true, size = "2.3 MB" }
      ODO_STEPS = { [1] = "7 days", [2] = "30 days", [3] = "90 days", [4] = "1 year", [5] = "Always" }
      function ODO_BUILD(ui)
        ui.header("Travel history", "Kept per character.")
        ui.check("Record my travels", "On: paths are kept.", function() return ODO.on end, function(v) ODO.on = v end)
        ui.slider("Keep", 1, 5, 1, function(v) return ODO_STEPS[v] end, function() return ODO.step or 2 end,
          function(v) ODO.step = v end)
        ui.choice("After that", { { value = "simple", text = "Keep simplified" }, { value = "where", text = "Keep only where I've been" },
          { value = "delete", text = "Delete" } }, function() return ODO.after end, function(v) ODO.after = v end)
        ui.text(function() return "This character: " .. ODO.size .. " of paths" end)
        ui.button("Show Totals", 120, function() ODO.shown = true end)
      end
      function BAD_BUILD(ui) ui.note("half built") error("plugin broke") end
    """)
    ns.Options.Show()
    headers = lambda: {h._text for h in ns.Options.sectionHeaders.values() if h._shown}
    assert headers() == set()  # (no plugin yet: no section of one in the list)
    assert A.AddOptionsPage("Broken", "Broken Plugin", lua.globals().BAD_BUILD)
    # (asked 2026-10-05: each addon's pages under a section named after it, "AzerothGPS" dropped)
    assert headers() == {"Broken"}
    widgets = lambda: list(lua.eval("AGPS_WIDGETS").values())
    tab = lambda title: next((w for w in widgets() if w._kind == "FontString" and w._text == title and w._shown), None)
    assert tab("Broken Plugin") is not None  # (its page there; its error printed, the window built)
    assert A.AddOptionsPage("AzerothGPS_Example", "General", lua.globals().ODO_BUILD)  # (the window built: added now)
    assert A.AddOptionsPage("AzerothGPS_Example", "History", lua.globals().BAD_BUILD)  # (a second page of its own)
    assert headers() == {"Broken", "Example"}
    assert len([w for w in widgets() if w._kind == "FontString" and w._text == "General" and w._shown]) >= 2
    assert tab("History") is not None and tab("Example: General") is not None  # (its page's own heading)
    text = next(w for w in widgets() if w._kind == "FontString" and str(w._text).startswith("This character:"))
    assert text._text == "This character: 2.3 MB of paths"
    lua.execute('ODO.size = "4.0 MB"')
    A.RefreshOptions()
    assert text._text == "This character: 4.0 MB of paths"  # (read again)
    radios = [w for w in widgets() if w.value in ("simple", "where", "delete")]
    assert [r.value for r in radios if r._checked] == ["simple"]
    next(r for r in radios if r.value == "delete")._scripts.OnClick(next(r for r in radios if r.value == "delete"))
    assert lua.eval("ODO.after") == "delete" and [r.value for r in radios if r._checked] == ["delete"]
    keep = next(w for w in widgets() if w.title and w.slider and w.title._text == "Keep")
    keep.slider._scripts.OnValueChanged(keep.slider, 4)
    assert lua.eval("ODO.step") == 4
    values = [w for w in widgets() if w._kind == "FontString" and w._text == "1 year"]
    assert values  # (the slider's text from the plugin's function)
    lua.execute("ODO_FAIL = true")
    lua.execute("local f = ODO_BUILD; ODO_BUILD2 = function(ui) ui.check('Broken get', '', function() error('get broke') end, function() end) end")
    A.AddOptionsPage("AzerothGPS_Example", "General", lua.globals().ODO_BUILD2)  # (replaced; its get() failing doesn't stop the rest)
    A.RefreshOptions()
    assert A.ShowOptions("General", "AzerothGPS_Example") is True and A.ShowOptions("No Such Page") is False
    assert A.ShowOptions("History", "AzerothGPS_Example") is True
    assert A.ShowOptions("General") is True  # (AzerothGPS's own, no owner given)


def test_a_companion_page_has_the_games_dropdown(game):
    # (API 15, asked 2026-10-06 for a plugin: ui.dropdown, ui.choice's arguments and refresh as a dropdown; asked
    # 2026-11-04, "I'd rather all dropdowns look like this one": the client's own, WowStyle1DropdownTemplate) a radio
    # each, the one picked shown; picking one sets it; a long list scrolls; disabled, grayed; an option added to the
    # list since shows
    lua, ns = game
    A = lua.globals().AzerothGPS
    lua.execute("""
      DD = { place = "bottom", on = true }
      DD_ZONES = {}
      for i = 1, 15 do DD_ZONES[i] = { value = i, text = "Zone " .. i } end
      function DD_BUILD(ui)
        DD_PLACE = ui.dropdown("Meter place", { { value = "bottom", text = "Bottom of the map" },
          { value = "title", text = "Title bar", tip = "Beside the close button." } },
          function() return DD.place end, function(v) DD.place = v end, function() return DD.on end)
        DD_ZONE = ui.dropdown("Zone", DD_ZONES, function() return DD.zone or 1 end, function(v) DD.zone = v end)
      end
    """)
    ns.Options.Show()
    assert A.AddOptionsPage("AzerothGPS_GameDropTest", "General", lua.globals().DD_BUILD)
    place, zone = lua.globals().DD_PLACE, lua.globals().DD_ZONE
    assert place._kind == "DropdownButton" and zone._kind == "DropdownButton"
    assert list(lua.globals().AGPS_MENU(place).values()) == ["Bottom of the map", "Title bar"]
    assert place._choice == "Bottom of the map" and zone._choice == "Zone 1" and zone._scroll > 0
    tip = next(it for it in place._menu.values() if it.text == "Title bar").tooltip
    assert tip is not None  # (its tip on the radio)
    lua.globals().AGPS_PICK(place, "Title bar")
    assert lua.eval("DD.place") == "title" and place._choice == "Title bar"
    lua.globals().AGPS_PICK(zone, "Zone 15")
    assert lua.eval("DD.zone") == 15 and zone._choice == "Zone 15"
    lua.execute("DD_ZONES[16] = { value = 16, text = 'Zone 16' }")  # (added since: in the menu next time)
    assert list(lua.globals().AGPS_MENU(zone).values())[-1] == "Zone 16"
    lua.execute("DD.on = false")
    A.RefreshOptions()
    assert place._enabled is False
    lua.execute("DD.on = true")
    A.RefreshOptions()
    assert place._enabled is True


def test_a_companion_page_has_a_dropdown_where_the_client_has_none(game):
    # (API 15, asked 2026-10-06 for a plugin) a client without the game's dropdowns: our own box shows the one
    # picked; a click opens the list (the picked one marked), a row picks it and closes the list; a long list shows
    # DROP_ROWS and scrolls with the wheel; disabled, it doesn't open
    lua, ns = game
    A = lua.globals().AzerothGPS
    lua.execute("""
      AGPS_NO_MENUS = true
      DD = { place = "bottom", on = true }
      DD_ZONES = {}
      for i = 1, 15 do DD_ZONES[i] = { value = i, text = "Zone " .. i } end
      function DD_BUILD(ui)
        ui.dropdown("Meter place", { { value = "bottom", text = "Bottom of the map" },
          { value = "title", text = "Title bar", tip = "Beside the close button." } },
          function() return DD.place end, function(v) DD.place = v end, function() return DD.on end)
        ui.dropdown("Zone", DD_ZONES, function() return DD.zone or 1 end, function(v) DD.zone = v end)
      end
    """)
    try:
        ns.Options.Show()
        assert A.AddOptionsPage("AzerothGPS_DropTest", "General", lua.globals().DD_BUILD)
    finally:
        lua.execute("AGPS_NO_MENUS = nil")
    A.ShowOptions("General", "AzerothGPS_DropTest")
    widgets = lambda: list(lua.eval("AGPS_WIDGETS").values())
    place, zone = [w for w in widgets() if w.options is not None and w.text is not None][-2:]
    assert place.text._text == "Bottom of the map" and zone.text._text == "Zone 1"
    place._scripts.OnClick(place)
    rows = [w for w in widgets() if w.option is not None and w.mark is not None and w.GetParent and w._shown is not False]
    rows = [r for r in rows if r.option.value in ("bottom", "title")]
    assert [str(r.text._text) for r in rows] == ["Bottom of the map", "Title bar"]
    assert [r.mark._shown for r in rows] == [True, False]  # (the one picked marked)
    title = next(r for r in rows if r.value == "title")
    title._scripts.OnClick(title)
    assert lua.eval("DD.place") == "title" and place.text._text == "Title bar"
    assert not title.GetParent(title)._shown  # (picked: the list closed)
    # a long list: 12 rows at a time, the mouse wheel scrolls
    zone._scripts.OnClick(zone)
    zrows = [w for w in widgets() if w.option is not None and w.mark is not None and isinstance(w.option.value, int)]
    assert len(zrows) == 12 and str(zrows[0].text._text) == "Zone 1"
    zlist = zrows[0].GetParent(zrows[0])
    zlist._scripts.OnMouseWheel(zlist, -5)
    assert str(zrows[0].text._text) == "Zone 4" and str(zrows[-1].text._text) == "Zone 15"  # (no further than the end)
    zrows[-1]._scripts.OnClick(zrows[-1])
    assert lua.eval("DD.zone") == 15 and zone.text._text == "Zone 15"
    # disabled: grayed and not opened
    lua.execute("DD.on = false")
    A.RefreshOptions()
    assert place._enabled is False
    lua.execute("DD.on = true")
    A.RefreshOptions()
    assert place._enabled is True


def test_the_options_list_scrolls_when_its_pages_run_past_the_window(game):
    # (asked 2026-10-05: with two plugins' pages the list ran off the window's bottom) the tabs and
    # section headers in a scroll frame; its bar only when the list is longer than the window, the tabs narrowed for
    # it; a page opened further down (ShowOptions) scrolls its tab into view
    lua, ns = game
    A, O = lua.globals().AzerothGPS, ns.Options
    lua.execute("function NOOP_BUILD(ui) ui.note('page') end")
    O.Show()
    sc, child = O.listScroll, O.listChild
    lua.execute("AGPS_LIST_H = 2000")
    lua.globals().AGPS_LS = sc
    lua.execute("AGPS_LS.GetHeight = function() return AGPS_LIST_H end")
    lua.execute("AzerothGPSOptions._scripts.OnShow(AzerothGPSOptions)")  # (opened again)
    assert not sc.ScrollBar._shown and child._h < 2000  # (it fits: no bar)
    lua.execute("AGPS_LIST_H = 454")  # (the window's list: 560 tall less its top and footer)
    for title in ("Dashboard", "Charm", "Arrow", "Route", "Window frame", "Arrival", "Trip"):
        assert A.AddOptionsPage("AzerothGPS_Sparkle", title, lua.globals().NOOP_BUILD)
    assert child._h > 454 and sc.ScrollBar._shown
    tabs = [w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "Button" and w.listY]
    assert tabs and all(t._w < 142 for t in tabs)  # (narrowed for the bar)
    assert all(lua.globals().rawequal(t._parent, child) for t in tabs)  # (in the scrolling list)
    assert A.ShowOptions("Arrival", "AzerothGPS_Sparkle") is True
    last = next(t for t in tabs if t.text._text == "Arrival")
    vs = sc._vs or 0
    assert vs > 0 and -last.listY + 24 <= vs + 454  # (scrolled down to its tab)
    assert A.ShowOptions("General") is True and (sc._vs or 0) == 0  # (and back up to the first)


def test_a_companion_addon_shares_save_now_and_the_top_panel(game):
    # (API 13) SetUnsaved(owner, count, text): its count with AzerothGPS's own; SaveNow(): a reload, never in combat;
    # MapButton("toppanel"): the directions panel, to put a panel under it
    lua, ns = game
    A, G = lua.globals().AzerothGPS, ns.GPS
    lua.execute("AGPS_RELOADED = 0 ReloadUI = function() AGPS_RELOADED = AGPS_RELOADED + 1 end")
    try:
        ns.ResetUnsaved()
        A.SetUnsaved("Example", 2, "Example: 6.2 mi of paths and 1 death")
        assert ns.unsaved == 2
        ns.Pins.Add(lua.eval("{ level = 0, x = 2250, y = 250, name = 'Mine' }"))
        assert ns.unsaved == 3
        A.SetUnsaved("Example", 0)
        assert ns.unsaved == 1
        ns.inCombat = True
        assert A.SaveNow() is False and lua.eval("AGPS_RELOADED") == 0
        ns.inCombat = False
        assert A.SaveNow() is True and lua.eval("AGPS_RELOADED") == 1
        panel = A.MapButton("toppanel")
        assert panel is not None and panel.SetPoint is not None
    finally:
        ns.ResetUnsaved()
        ns.inCombat = False


def _lines(lua):
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "Line" and w._shown]


def _colors(lines):
    return {str(w._vc) if w._vc else str(w._tex).replace("color:", "") for w in lines}


def test_another_addons_route_look(game):
    # (API 14, asked 2026-10-05 for a plugin) the route's color, width, glow and rainbow from another addon;
    # the look set last shows; taken away, AzerothGPS's own blue again
    lua, ns = game
    N, G, A = ns.Nav, ns.GPS, lua.globals().AzerothGPS
    blue, gold = "0.05,0.28,0.85", "1.00,0.82,0.00"
    ns.settings.gps.zoom = 600
    N.Clear()
    N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
    try:
        for t in range(3):
            lua.execute(f"AGPS_T = {960 + t}")
            G.Update()
        assert N.route and blue in _colors(_lines(lua))
        A.SetRouteLook("Sparkle", lua.eval("{ color = { 1, 0.82, 0 }, width = 2, glow = true }"))
        lua.execute("AGPS_T = 964")
        G.Update()
        lines = _lines(lua)
        assert gold in _colors(lines) and blue not in _colors(lines)
        widths = {w._thick for w in lines if (w._vc or str(w._tex).replace("color:", "")) == gold}
        assert 10 in widths or 8 in widths  # (twice a road's 5 or an off-road leg's 4)
        assert any(t > 20 for t in widths)  # (the glow under it)
        A.SetRouteLook("Other", lua.eval("{ rainbow = true }"))  # (set last: shows)
        lua.execute("AGPS_T = 965")
        G.Update()
        assert gold not in _colors(_lines(lua))
        rainbow = {"%.2f,%.2f,%.2f" % tuple(G.RAINBOW[i][k] for k in (1, 2, 3)) for i in range(1, G.RAINBOW_STEPS + 1)}
        assert len(_colors(_lines(lua)) & rainbow) >= 3  # (the colors changing along it)
        A.SetRouteLook("Other", None)
        A.SetRouteLook("Sparkle", None)
        lua.execute("AGPS_T = 966")
        G.Update()
        assert blue in _colors(_lines(lua)) and gold not in _colors(_lines(lua))
    finally:
        A.SetRouteLook("Sparkle", None)
        A.SetRouteLook("Other", None)
        N.Clear()


def test_another_addons_player_arrow(game):
    # (API 14) another addon's picture for the player's arrow, with its size, texture coordinates and tint; the one
    # set last shows; all taken away (or a look with nothing usable), the game's minimap arrow again
    lua, ns = game
    G, A = ns.GPS, lua.globals().AzerothGPS
    arrow = next(w for w in lua.eval("AGPS_WIDGETS").values() if w.agpsTex)
    default = "Interface\\Minimap\\MinimapArrow"
    assert arrow._tex == default
    try:
        A.SetPlayerArrow("Sparkle", lua.eval(
            '{ texture = "Interface/AddOns/X/car", width = 20, height = 30, coords = { 0, 0.5, 0, 1 }, color = { 1, 0.5, 0.5 } }'))
        assert arrow._tex == "Interface/AddOns/X/car" and (arrow._w, arrow._h) == (20, 30)
        assert list(arrow._coords.values()) == [0, 0.5, 0, 1] and arrow._vc == "1.00,0.50,0.50"
        A.SetPlayerArrow("Other", lua.eval('{ texture = 136777 }'))
        assert arrow._tex == 136777 and (arrow._w, arrow._h) == (32, 32)
        A.SetPlayerArrow("Other", None)
        assert arrow._tex == "Interface/AddOns/X/car"
        A.SetPlayerArrow("Sparkle", None)
        assert arrow._tex == default and (arrow._w, arrow._h) == (32, 32) and arrow._vc == "1.00,1.00,1.00"
        assert list(arrow._coords.values()) == [0, 1, 0, 1]
        A.SetPlayerArrow("Sparkle", lua.eval("{ width = 'wide', coords = 7, color = 'red' }"))  # (nothing usable)
        assert arrow._tex == default and (arrow._w, arrow._h) == (32, 32)
    finally:
        A.SetPlayerArrow("Sparkle", None)
        A.SetPlayerArrow("Other", None)


def test_another_addons_window_frame_look(game):
    # (API 14) another addon's tint for the window frame's border pieces and its title bar's color; taken away,
    # untinted and AzerothGPS's dark title bar again
    lua, ns = game
    G, A = ns.GPS, lua.globals().AzerothGPS
    lua.execute("""
      AGPS_CHROME = CreateFrame("Frame")
      AGPS_CHROME.NineSlice = CreateFrame("Frame", nil, AGPS_CHROME)
      AGPS_PIECES = { AGPS_CHROME.NineSlice:CreateTexture(), AGPS_CHROME.NineSlice:CreateTexture() }
      function AGPS_CHROME.NineSlice:GetRegions() return AGPS_PIECES[1], AGPS_PIECES[2] end
      AGPS_STRIP = AGPS_CHROME:CreateTexture()
    """)
    old_chrome, old_strip = G.chrome, G.chromeStrip
    G.chrome, G.chromeStrip = lua.eval("AGPS_CHROME"), lua.eval("AGPS_STRIP")
    pieces = lua.eval("AGPS_PIECES")
    try:
        A.SetFrameLook("Sparkle", lua.eval("{ border = { 1, 0.8, 0.3 }, title = { 0.2, 0.1, 0 } }"))
        assert pieces[1]._vc == pieces[2]._vc == "1.00,0.80,0.30"
        assert pieces[1]._desat is pieces[2]._desat is True  # (grayed first: the color true, 2026-10-08)
        assert G.chromeStrip._tex == "color:0.20,0.10,0.00"
        A.SetFrameLook("Sparkle", None)
        assert pieces[1]._vc == pieces[2]._vc == "1.00,1.00,1.00"
        assert pieces[1]._desat is pieces[2]._desat is False  # (the game's own art)
        assert G.chromeStrip._tex == "color:0.06,0.06,0.07"
    finally:
        A.SetFrameLook("Sparkle", None)
        G.chrome, G.chromeStrip = old_chrome, old_strip


def test_another_addon_is_told_of_each_stop_reached(game):
    # (API 14, for a plugin's arrival effects) each stop reached, the last one said; told once; a failing
    # hook doesn't stop the trip
    lua, ns = game
    N, A = ns.Nav, lua.globals().AzerothGPS
    got = lua.eval("{}")
    A.OnArrive("Sparkle", lua.eval("function(t) return function(info) t[#t + 1] = info end end")(got))
    N.Clear()
    try:
        N.SetStops(lua.eval("{ { x = 2290, y = 293, cont = 0, name = 'One' }, { x = 2330, y = 320, cont = 0, name = 'Two' } }"),
                   False, "red")
        N.Status(2290, 293, 0)
        assert len(got) == 1 and got[1].name == "One" and got[1].last is False and got[1].kind == "stop"
        N.Status(2330, 320, 0)
        assert len(got) == 2 and got[2].name == "Two" and got[2].last is True
        assert (got[2].x, got[2].y, got[2].cont) == (2330, 320, 0)
        N.Status(2330, 320, 0)  # (arrived: not told again)
        assert len(got) == 2
        A.OnArrive("Sparkle", lua.eval("function() error('boom') end"))
        N.SetStops(lua.eval("{ { x = 2290, y = 293, cont = 0 } }"), False, "red")
        assert "Arrived" in N.Status(2290, 293, 0)
        A.OnArrive("Sparkle", None)
        assert not N.arriveHooks.Sparkle
    finally:
        A.OnArrive("Sparkle", None)
        N.Clear()


def test_the_logo_plate_for_companions(game):
    # (API 14, for a plugin's charm: hung from behind the logo, over the frame's border at level 500)
    # MapButton("logo") is the window frame's logo plate; nil without the frame (as in this stand-in)
    lua, ns = game
    G, A = ns.GPS, lua.globals().AzerothGPS
    assert A.MapButton("logo") is None
    old = G.mapButtons.logo
    plate = lua.eval("CreateFrame('Frame')")
    G.mapButtons.logo = plate
    try:
        assert lua.eval("rawequal")(A.MapButton("logo"), plate)
    finally:
        G.mapButtons.logo = old


def test_a_companion_widget_on_the_title_bar_moves_the_title_left(game):
    # (API 15, asked 2026-10-06: a plugin's meter on the title bar, left of the close button, and the place's name moved
    # left, right after the logo) a slot of the width asked at the title bar's right, over the frame's border; while one
    # shows, the name starts after the logo and stops before the slots (one line, cut short: never under them); a second
    # slot goes left of the first; hidden while the window frame is off or the title bar has no room (a narrow map) and
    # back after; let go, the name is centered again
    lua, ns = game
    G, A, st = ns.GPS, lua.globals().AzerothGPS, ns.settings.gps
    lua.execute("""
      AGPS_CHROME = CreateFrame("Frame", nil, AzerothGPSFrame)
      AGPS_CHROME.TitleContainer = CreateFrame("Frame", nil, AGPS_CHROME)
      AGPS_CHROME.TitleContainer.TitleText = AGPS_CHROME.TitleContainer:CreateFontString()
    """)
    chrome = lua.eval("AGPS_CHROME")
    tc, same = chrome.TitleContainer, lua.eval("rawequal")
    text = tc.TitleText
    old = G.chrome
    saved = (st.size, st.freeSize, st.width, st.windowFrame, st.quick)
    try:
        G.chrome = chrome
        st.freeSize, st.width, st.size, st.windowFrame = False, None, 450, True
        G.ApplySettings()
        assert not tc._pts  # (no slot: the title left as the frame has it)
        slot = A.TitleBarSlot("Example", 112)
        assert slot._shown and (slot._w, slot._h) == (112, 20) and same(slot.GetParent(slot), chrome)
        pt = tuple(slot._pt.values())
        assert pt[0] == "TOPRIGHT" and same(pt[1], chrome) and pt[2:] == ("TOPRIGHT", -26, -1)
        assert slot._level == 5 + 2  # (over the frame's highest part)
        left = G.TitleLeft()
        assert left == 62  # (the logo's right edge, 57, and a gap)
        assert tuple(tc._pts.TOPLEFT.values())[3:] == (left, 0)
        assert tuple(tc._pts.TOPRIGHT.values())[3:] == (-(26 + 112 + 4), 0)
        # (in the middle between the logo and the slot, one line: asked in the 1.1.5 test pass, it sat left against the
        # logo)
        assert text._justify == "CENTER" and text._wrap is False
        # a second slot: left of the first; the first resized, the same frame
        other = A.TitleBarSlot("Other", 60)
        assert other._shown and tuple(other._pt.values())[3] == -(26 + 112 + 4)
        assert same(A.TitleBarSlot("Example", 100), slot) and slot._w == 100
        assert tuple(other._pt.values())[3] == -(26 + 100 + 4)
        assert tuple(tc._pts.TOPRIGHT.values())[3] == -(26 + 100 + 4 + 60 + 4)
        # a narrow map: the title cut short before the slot that fits; the one that doesn't, hidden
        st.quick = lua.eval("{ questRoute = 'hidden', hearth = 'hidden' }")  # (no buttons going right: any width)
        st.freeSize, st.width = True, 260
        G.ApplySettings()
        assert slot._shown and not other._shown
        assert tuple(tc._pts.TOPRIGHT.values())[3] == -(26 + 100 + 4)
        assert 264 - (26 + 100 + 4) - left >= G.TITLE_TEXT_MIN  # (the title's room)
        st.width = 200  # (no room for either: the title centered again)
        G.ApplySettings()
        assert not slot._shown and not other._shown
        assert tuple(tc._pts.TOPLEFT.values())[3] == G.TITLE_MARGIN and text._justify == "CENTER"
        st.width = 450
        G.ApplySettings()
        assert slot._shown and other._shown and text._justify == "CENTER"
        assert tuple(tc._pts.TOPLEFT.values())[3] == left  # (between the logo and the slots: not the window's middle)
        # the window frame off: hidden; on: back
        st.windowFrame = False
        G.ApplySettings()
        assert not slot._shown and not other._shown
        st.windowFrame = True
        G.ApplySettings()
        assert slot._shown and other._shown
        # let go: hidden, the title centered again
        assert A.TitleBarSlot("Other", None) is None and not other._shown
        A.TitleBarSlot("Example", None)
        assert not slot._shown and text._justify == "CENTER" and not G.titleSlots.Example
        # no window frame yet (or none in this client): a slot hidden until there is one
        G.chrome = None
        early = A.TitleBarSlot("Early", 80)
        assert early and not early._shown
        G.chrome = chrome
        G.ApplySettings()
        assert early._shown and same(early.GetParent(early), chrome)
    finally:
        for owner in ("Example", "Other", "Early"):
            A.TitleBarSlot(owner, None)
        G.chrome = old
        st.size, st.freeSize, st.width, st.windowFrame, st.quick = saved
        G.ApplySettings()


def test_npcs_talked_to_are_searchable_but_not_common_ones_or_guards(game):
    # (asked 2026-10-05) the game doesn't tell addons where NPCs are, but one's window opening (gossip, a vendor, a
    # quest...) means the player stands by it: kept by its creature id, with its title and the subzone, for Search
    # Places (a stop when picked; never drawn on the map). Not a guard's directions menu, not an object's quest, and
    # one met in two far-apart places is common (a guard, a supplier in every town): left out. Imported ones (/way
    # lines, as herbs and ore) are searchable until talked to, which confirms them.
    lua, ns = game
    G, L = ns.GPS, ns.Layers
    lua.execute("""
      AGPS_NPC = { guid = nil, name = nil, title = nil, opts = {} }
      AGPS_REAL_UNIT = { guid = UnitGUID, name = UnitName, tip = C_TooltipInfo, gossip = C_GossipInfo.GetOptions }
      UnitGUID = function(u) if u == "npc" then return AGPS_NPC.guid end return AGPS_REAL_UNIT.guid(u) end
      UnitName = function(u) if u == "npc" then return AGPS_NPC.name end return AGPS_REAL_UNIT.name(u) end
      C_TooltipInfo = { GetUnit = function() return { lines = { { leftText = AGPS_NPC.name }, { leftText = AGPS_NPC.title } } } end }
      C_GossipInfo.GetOptions = function() return AGPS_NPC.opts end
      function AGPS_TALK(event, id, name, title, opts, kind)
        AGPS_NPC.guid = string.format("%s-0-1-2-3-%d-00000ABC", kind or "Creature", id)
        AGPS_NPC.name, AGPS_NPC.title, AGPS_NPC.opts = name, title, opts or {}
        AGPS_NS.Layers.frame._scripts.OnEvent(AGPS_NS.Layers.frame, event)
      end
    """)
    x0, y0 = lua.eval("AGPS_POS[1]"), lua.eval("AGPS_POS[2]")
    try:
        ns.db.npcs = None
        ns.ResetUnsaved()
        f = L.frame
        assert f._events["GOSSIP_SHOW"] and f._events["MERCHANT_SHOW"] and f._events["QUEST_DETAIL"]
        lua.execute("AGPS_TALK('GOSSIP_SHOW', 6741, 'Innkeeper Renee', '<Innkeeper>', { { name = 'Make this inn your home.' } })")
        n = ns.db.npcs[6741]
        assert n and n.name == "Innkeeper Renee" and n.title == "Innkeeper" and n.place == "Brill" and n.cont == 0
        assert abs(n.x - x0) < 0.2 and abs(n.y - y0) < 0.2 and ns.unsaved == 1
        hit = G.SearchPlaces("renee", 8)
        assert len(hit) == 1 and hit[1].npc and hit[1].sub == "Innkeeper, Brill"
        assert G.SearchPlaces("inn ren", 8)[1].name == "Innkeeper Renee"
        # (a window without a title: the kind of it)
        lua.execute("AGPS_TALK('TRAINER_SHOW', 4773, 'Velma Warnam', nil)")
        assert ns.db.npcs[4773].title == "Trainer"
        # a guard's directions: not kept
        lua.execute("AGPS_TALK('GOSSIP_SHOW', 5725, 'Deathguard Lundmark', nil, { { name = 'The bank' }, { name = 'The inn' }, "
                    "{ name = 'The stable master' }, { name = 'Class trainer' } })")
        assert ns.db.npcs[5725] is None
        # an object's quest (a board, a chest): not an NPC
        lua.execute("AGPS_TALK('QUEST_DETAIL', 1234, 'Wanted Poster', nil, nil, 'GameObject')")
        assert ns.db.npcs[1234] is None
        # one of many: met again 300 yd away, left out from then on
        lua.execute("AGPS_TALK('MERCHANT_SHOW', 2116, 'Blacksmith Rand', '<Blacksmithing Supplies>')")
        assert G.SearchPlaces("rand", 8)
        lua.execute(f"AGPS_POS[1] = {x0 + 300}")
        lua.execute("AGPS_TALK('MERCHANT_SHOW', 2116, 'Blacksmith Rand', '<Blacksmithing Supplies>')")
        assert ns.db.npcs[2116].common and not [e for e in G.SearchPlaces("rand", 8).values() if e.npc and not e.shipped]
        # (again by Renee: still one)
        lua.execute(f"AGPS_POS[1] = {x0}")
        lua.execute("AGPS_TALK('GOSSIP_SHOW', 6741, 'Innkeeper Renee', '<Innkeeper>')")
        assert not ns.db.npcs[6741].common
        # imported: searchable, "(imported)", until talked to by it
        added, skipped, errs = L.ImportNpcs("/way Tirisfal Glades 61.0 52.0 Apothecary Johaan\n/way Tirisfal Glades 60.0 51.0\n"
                                           "/way Tirisfal Glades 61.0 52.0 Innkeeper Renee")
        assert added == 1 and skipped == 1 and len(errs) == 1
        imp = ns.db.npcs["imp:apothecary johaan"]
        hit = G.SearchPlaces("johaan", 8)
        assert imp and imp.imported and hit[1].sub.endswith("(imported)")
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {imp.x + 20}, {imp.y}")
        lua.execute("AGPS_TALK('QUEST_GREETING', 1652, 'Apothecary Johaan', '<Royal Apothecary Society>')")
        assert ns.db.npcs["imp:apothecary johaan"] is None and ns.db.npcs[1652].title == "Royal Apothecary Society"
        assert not G.SearchPlaces("johaan", 8)[1].sub.endswith("(imported)")
    finally:
        lua.execute(f"""
          UnitGUID, UnitName, C_TooltipInfo = AGPS_REAL_UNIT.guid, AGPS_REAL_UNIT.name, AGPS_REAL_UNIT.tip
          C_GossipInfo.GetOptions = AGPS_REAL_UNIT.gossip
          AGPS_POS[1], AGPS_POS[2] = {x0}, {y0}
        """)
        ns.db.npcs = None
        ns.ResetUnsaved()


def test_quest_route_asks_before_keeping_a_group_quest(game):
    # (asked 2026-10-06) a group quest in the quest route (elite, or more than one player suggested): asked whether to
    # keep it; Leave Out leaves it out of the route, and it isn't asked again this session; a turn-in isn't asked about
    lua, ns = game
    G, L, N = ns.GPS, ns.Layers, ns.Nav
    lua.execute("""
      AGPS_QR = { stops = AGPS_NS.Layers.QuestStops, group = AGPS_NS.Layers.QuestGroup }
      AGPS_NS.Layers.QuestStops = function()
        return {
          { x = 2250, y = 250, cont = 0, name = "Wolves", questRoute = true, quest = 1 },
          { x = 2300, y = 300, cont = 0, name = "Ogre Mound", questRoute = true, quest = 2 },
          { x = 2200, y = 280, cont = 0, name = "Turn in: Raid", questRoute = true, quest = 3, turnin = true },
        }, { todo = 2, turnin = 1, missing = {}, elsewhere = 0 }
      end
      AGPS_NS.Layers.QuestGroup = function(id)
        if id == 2 then return { size = 3, elite = true, tag = "Elite" } end
        if id == 3 then return { size = 5, elite = true } end
      end
    """)
    names = lambda: sorted(N.stops[i].name for i in range(1, len(N.stops) + 1))
    try:
        N.Clear()
        G.groupChoice = lua.eval("{}")
        G.QuestRoute()
        ask = G.askBox
        assert ask._shown and "Ogre Mound" in ask.text._text and "elite, 3 players suggested" in ask.text._text
        assert ask.yes._text == "Keep" and ask.no._text == "Leave Out"
        assert len(N.stops) == 0  # (not set until answered)
        ask.no._scripts.OnClick(ask.no)
        assert names() == ["Turn in: Raid", "Wolves"]
        # again: not asked again this session, still left out
        N.Clear()
        G.QuestRoute()
        assert not G.askBox._shown and names() == ["Turn in: Raid", "Wolves"]
        # kept
        G.groupChoice = lua.eval("{}")
        N.Clear()
        G.QuestRoute()
        G.askBox.yes._scripts.OnClick(G.askBox.yes)
        assert names() == ["Ogre Mound", "Turn in: Raid", "Wolves"]
    finally:
        lua.execute("AGPS_NS.Layers.QuestStops, AGPS_NS.Layers.QuestGroup = AGPS_QR.stops, AGPS_QR.group")
        N.Clear()
        G.groupChoice = lua.eval("{}")



def test_with_the_option_on_the_quest_picked_in_the_log_is_the_route(game):
    # (asked 2026-11-13, a player: "when I select a quest and activate it, I'd like the route guidance to start as
    # well") the quest focused in the quest log or tracker (C_SuperTrack, SUPER_TRACKING_CHANGED) becomes the route:
    # its objectives and turn-in, nothing else; off by default
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    st = ns.settings.gps
    lua.execute("""
      AGPS_PK = { stops = AGPS_NS.Layers.QuestStops, after = C_Timer.After, st = C_SuperTrack, picked = 0,
                  print = AGPS_NS.Print }
      AGPS_NS.Layers.QuestStops = function()
        return {
          { x = 2250, y = 250, cont = 0, name = "Wolves", questRoute = true, quest = 1 },
          { x = 2300, y = 300, cont = 0, name = "Spiders", questRoute = true, quest = 2 },
          { x = 2350, y = 320, cont = 0, name = "Spider eggs", questRoute = true, quest = 2 },
          { x = 2200, y = 280, cont = 0, name = "Turn in: Spiders", questRoute = true, quest = 2, turnin = true },
          { x = 2150, y = 260, cont = 0, name = "Turn in: Bears", questRoute = true, quest = 3, turnin = true },
        }, { todo = 3, turnin = 2, missing = {}, elsewhere = 0 }
      end
      C_Timer.After = function(_, f) f() end
      C_SuperTrack = { GetSuperTrackedQuestID = function() return AGPS_PK.picked end }
    """)
    names = lambda: sorted(str(N.stops[i].name) for i in range(1, len(N.stops) + 1))
    pick = lambda q: lua.execute(f"AGPS_PK.picked = {q}") or G.pickEvents._scripts.OnEvent(G.pickEvents, "SUPER_TRACKING_CHANGED")
    try:
        assert G.pickEvents._events["SUPER_TRACKING_CHANGED"]
        assert st.questPickRoute is False  # (off by default)
        N.Clear()
        G.groupChoice = lua.eval("{}")
        pick(2)
        assert names() == []  # (off: picking a quest changes nothing)
        st.questPickRoute = True
        pick(2)
        assert names() == ["Spider eggs", "Spiders", "Turn in: Spiders"]
        # the same quest again: the route as it is; another: its stops
        N.RemoveStop(1)
        pick(2)
        assert len(names()) == 2
        pick(3)
        assert names() == ["Turn in: Bears"]
        # a quest with no location: said, the route left alone; none picked: nothing
        lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
        pick(99)
        assert names() == ["Turn in: Bears"]
        assert any("no location found for the quest you picked" in str(m) for m in lua.eval("AGPS_PRINTS").values())
        pick(0)
        assert names() == ["Turn in: Bears"]
    finally:
        st.questPickRoute = False
        lua.execute("AGPS_NS.Layers.QuestStops, C_Timer.After, C_SuperTrack = AGPS_PK.stops, AGPS_PK.after, AGPS_PK.st "
                    "AGPS_NS.Print = AGPS_PK.print")
        N.Clear()
        G.groupChoice = lua.eval("{}")
        N.questDropped = lua.eval("{}")  # (the stop removed stays out of quest routes since 1.3.13: let go)
        G.pickedQuest = None


def test_route_here_in_the_quest_details_and_the_quest_menus(game):
    # (asked 2026-11-13, a screenshot of the world map's quest details: "Put a Route Here button here, also can we
    # support right clicking a quest and adding Route Here option as well?") a button beside the details' Back, and an
    # entry in the quest log's and the objective tracker's right-click menus: each routes to that quest alone
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      AGPS_RH = { stops = AGPS_NS.Layers.QuestStops, hook = hooksecurefunc, cui = AGPS_NS.GPS.ControllerUI }
      AGPS_NS.Layers.QuestStops = function()
        return {
          { x = 2250, y = 250, cont = 0, name = "Wolves", questRoute = true, quest = 1 },
          { x = 2300, y = 300, cont = 0, name = "Spiders", questRoute = true, quest = 2 },
          { x = 2200, y = 280, cont = 0, name = "Turn in: Spiders", questRoute = true, quest = 2, turnin = true },
          { x = 2150, y = 260, cont = 0, name = "Turn in: Bears", questRoute = true, quest = 3, turnin = true },
        }, { todo = 2, turnin = 2, missing = {}, elsewhere = 0 }
      end
      local back = NewWidget("Frame", "AGPSTestQuestBack")
      local bf = NewWidget("Frame", "AGPSTestQuestBackFrame")
      bf.BackButton = NewWidget("Button", "AGPSTestQuestBackButton")
      QuestMapFrame = { DetailsFrame = { questID = 2, BackFrame = bf } }
      AGPS_MENUS = {}
      Menu = { ModifyMenu = function(tag, cb) AGPS_MENUS[tag] = AGPS_MENUS[tag] or {} table.insert(AGPS_MENUS[tag], cb) end }
      hooksecurefunc = function(t, k, post)
        local f = t[k]
        t[k] = function(...) f(...) post(...) end
      end
      QuestObjectiveTracker = { OnBlockHeaderClick = function() end }
      AGPS_ROOT = function()
        return { buttons = {}, CreateDivider = function() end,
                 CreateButton = function(self, text, fn) table.insert(self.buttons, { text = text, fn = fn }) end }
      end
      AGPS_MENU_CLICK = function(tag, owner)
        local root = AGPS_ROOT()
        for _, cb in ipairs(AGPS_MENUS[tag] or {}) do cb(owner, root) end
        for _, b in ipairs(root.buttons) do
          if b.text == "Route Here" then b.fn() return true end
        end
        return false
      end
    """)
    names = lambda: sorted(str(N.stops[i].name) for i in range(1, len(N.stops) + 1))
    try:
        G.routeHereBtn, G.questMenus, G.routeHereEvents = None, None, None
        G.groupChoice = lua.eval("{}")
        N.Clear()
        # never with the controller UI on
        lua.execute("AGPS_NS.GPS.ControllerUI = function() return true end")
        assert G.MakeRouteHere() is None
        # nor in the quest menus (issue #887: abandoning quests from them got AzerothGPS blocked there)
        G.InitRouteHere()
        assert not G.questMenus and not G.routeHereEvents
        assert not lua.eval("AGPS_MENU_CLICK")("MENU_QUEST_MAP_LOG_TITLE", lua.eval("{ questID = 3 }"))
        assert not lua.eval("AGPS_MENU_CLICK")("MENU_QUEST_OBJECTIVE_TRACKER", lua.eval("QuestObjectiveTracker"))
        assert names() == []
        lua.execute("AGPS_NS.GPS.ControllerUI = AGPS_RH.cui")
        G.InitRouteHere()
        b = G.routeHereBtn
        assert b and str(b._text) == "Route Here" and lua.eval("rawequal")(b._parent, lua.eval("QuestMapFrame.DetailsFrame.BackFrame"))
        b._scripts.OnClick(b)
        assert names() == ["Spiders", "Turn in: Spiders"]
        # the quest log's menu: the title button's quest
        assert lua.eval("AGPS_MENU_CLICK")("MENU_QUEST_MAP_LOG_TITLE", lua.eval("{ questID = 3 }"))
        assert names() == ["Turn in: Bears"]
        # the objective tracker's: the quest right-clicked there
        lua.execute("QuestObjectiveTracker:OnBlockHeaderClick({ id = 2 }, 'RightButton')")
        assert lua.eval("AGPS_MENU_CLICK")("MENU_QUEST_OBJECTIVE_TRACKER", lua.eval("QuestObjectiveTracker"))
        assert names() == ["Spiders", "Turn in: Spiders"]
    finally:
        lua.execute("""AGPS_NS.Layers.QuestStops, hooksecurefunc = AGPS_RH.stops, AGPS_RH.hook
          AGPS_NS.GPS.ControllerUI = AGPS_RH.cui
          QuestMapFrame, Menu, QuestObjectiveTracker = nil, nil, nil""")
        G.routeHereBtn, G.questMenus, G.routeHereEvents = None, None, None
        N.Clear()
        G.groupChoice = lua.eval("{}")


def test_the_controller_ui_turned_on_after_login_keeps_route_here_out_of_the_quest_menus(game):
    # (a player's report for 1.3.14: an error abandoning a quest with the controller. The menus were hooked at login with
    # the controller UI off and kept getting Route Here once it was on, beside Abandon Quest, issue #887's way to be
    # blocked: now looked at each time a menu opens, and the details' button hidden while it's on)
    lua, ns = game
    G = ns.GPS
    lua.execute("""
      AGPS_RH2 = { hook = hooksecurefunc, cui = AGPS_NS.GPS.ControllerUI }
      local bf = NewWidget("Frame", "AGPSTestQuestBackFrame2")
      bf.BackButton = NewWidget("Button", "AGPSTestQuestBackButton2")
      QuestMapFrame = { DetailsFrame = { questID = 2, BackFrame = bf } }
      AGPS_MENUS = {}
      Menu = { ModifyMenu = function(tag, cb) AGPS_MENUS[tag] = AGPS_MENUS[tag] or {} table.insert(AGPS_MENUS[tag], cb) end }
      hooksecurefunc = function(t, k, post)
        local f = t[k]
        t[k] = function(...) f(...) post(...) end
      end
      QuestObjectiveTracker = { OnBlockHeaderClick = function() end }
      AGPS_ENTRIES = function(tag, owner)
        local root = { n = 0, CreateDivider = function() end,
                       CreateButton = function(self, text) if text == "Route Here" then self.n = self.n + 1 end end }
        for _, cb in ipairs(AGPS_MENUS[tag] or {}) do cb(owner, root) end
        return root.n
      end
      AGPS_CUI_ON = false
      AGPS_NS.GPS.ControllerUI = function() return AGPS_CUI_ON end
    """)
    entries = lua.eval("AGPS_ENTRIES")
    try:
        G.routeHereBtn, G.questMenus, G.routeHereEvents = None, None, None
        G.InitRouteHere()  # (logged in with the controller UI off: hooked)
        b = G.routeHereBtn
        assert G.questMenus and b and b.IsShown(b)
        assert entries("MENU_QUEST_MAP_LOG_TITLE", lua.eval("{ questID = 3 }")) == 1
        lua.execute("AGPS_CUI_ON = true")  # (turned on afterwards)
        assert entries("MENU_QUEST_MAP_LOG_TITLE", lua.eval("{ questID = 3 }")) == 0
        assert entries("MENU_QUEST_OBJECTIVE_TRACKER", lua.eval("QuestObjectiveTracker")) == 0
        G.SyncRouteHere()
        assert not b.IsShown(b)
        lua.execute("AGPS_CUI_ON = false")  # (off again: as before)
        G.SyncRouteHere()
        assert b.IsShown(b) and entries("MENU_QUEST_MAP_LOG_TITLE", lua.eval("{ questID = 3 }")) == 1
    finally:
        lua.execute("""hooksecurefunc, AGPS_NS.GPS.ControllerUI = AGPS_RH2.hook, AGPS_RH2.cui
          QuestMapFrame, Menu, QuestObjectiveTracker = nil, nil, nil""")
        G.routeHereBtn, G.questMenus, G.routeHereEvents = None, None, None


def test_quest_route_asks_before_keeping_a_red_quest(game):
    # (asked 2026-11-07: "do the same for red quests to offer leaving them out of the route") a quest 5 or more levels
    # over the player's (Layers.QuestRed) is asked about as a group quest is; Leave Out leaves it out
    lua, ns = game
    G, L, N = ns.GPS, ns.Layers, ns.Nav
    lua.execute("""
      AGPS_QR = { stops = AGPS_NS.Layers.QuestStops, group = AGPS_NS.Layers.QuestGroup, lvl = UnitLevel,
        diff = C_QuestLog.GetQuestDifficultyLevel }
      AGPS_NS.Layers.QuestStops = function()
        return {
          { x = 2250, y = 250, cont = 0, name = "Wolves", questRoute = true, quest = 1 },
          { x = 2300, y = 300, cont = 0, name = "Dragon Lair", questRoute = true, quest = 2 },
        }, { todo = 2, turnin = 0, missing = {}, elsewhere = 0 }
      end
      AGPS_NS.Layers.QuestGroup = function() return nil end
      UnitLevel = function() return 15 end
      C_QuestLog.GetQuestDifficultyLevel = function(id) return id == 2 and 20 or 16 end
    """)
    names = lambda: sorted(N.stops[i].name for i in range(1, len(N.stops) + 1))
    try:
        assert L.QuestRed(2) == 20 and L.QuestRed(1) is None
        N.Clear()
        G.groupChoice = lua.eval("{}")
        G.QuestRoute()
        ask = G.askBox
        assert ask._shown and "Dragon Lair" in ask.text._text and "red quest (level 20)" in ask.text._text
        ask.no._scripts.OnClick(ask.no)
        assert names() == ["Wolves"]
    finally:
        lua.execute("""AGPS_NS.Layers.QuestStops, AGPS_NS.Layers.QuestGroup = AGPS_QR.stops, AGPS_QR.group
          UnitLevel, C_QuestLog.GetQuestDifficultyLevel = AGPS_QR.lvl, AGPS_QR.diff""")
        N.Clear()
        G.groupChoice = lua.eval("{}")


def test_a_stop_made_from_a_quest_icon_carries_its_quest(game):
    # (the live game, 2026-10-08: a stop double-clicked on a quest's icon was a plain stop, tied to its quest only
    # through a traced area; with none, no objectives and not done by the quest) the quest's icon gives the stop its
    # quest (Nav.QuestStop: done by the quest, as the Quest Route's stops); a plain spot's stays a plain stop
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    N.Clear()
    try:
        N.SetStops(lua.eval("{ { x = 2290, y = 293, cont = 0, name = 'One' } }"), False, "red")
        assert G.AddStopAt(2300.0, 310.0, "The Balance of Nature", 0, None, None, False, 488)
        assert G.AddStopAt(2320.0, 330.0, "Somewhere", 0)
        by = {N.stops[i].name: N.stops[i] for i in range(1, len(N.stops) + 1)}
        assert by["The Balance of Nature"].quest == 488 and by["The Balance of Nature"].questRoute
        assert by["Somewhere"].quest is None
    finally:
        N.Clear()


def test_each_faction_gets_only_the_rides_it_can_take_search_too(game):
    # (asked 2026-10-08: "why does zeppelins show for alliance players?") the other faction's zeppelins (their docks
    # among its guards) are left out of Search too, as on the map, in the routes and the options; WoW Forever's own to
    # Zephras Isle carry a `faction` (Data/Transports.lua: Old Dalaran's the Alliance's (2026-11-23), Camp Gev'rek's the Horde's since
    # Kooki3z 2026-11-21, test_alliance_zephras_ride.py); a row's own faction wins over the guards
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    rows = {ns.Transports[i][9] + " | " + ns.Transports[i][10]: ns.Transports[i] for i in range(1, len(ns.Transports) + 1)}
    horde = rows["Grom'gol Base Camp, Stranglethorn Vale | Jaggedswine Farm, Durotar"]
    zephras = rows["Old Dalaran Ruins, Alterac Mountains | Valanaar Skydocks, Zephras Isle"]
    assert zephras.faction == "A" and rows["Camp Gev'rek, Mulgore | Fairweather Stables, Zephras Isle"].faction == "H"
    old = ns.CharDB().faction

    def found(text):
        res = G.SearchPlaces(text, 50)
        return {res[i].name for i in range(1, len(res) + 1)}

    try:
        ns.CharDB().faction = "Alliance"
        assert not N.TransportUsable(horde) and N.TransportUsable(zephras)
        assert "Grom'gol Base Camp, Stranglethorn Vale" not in found("grom'gol")
        assert "Old Dalaran Ruins, Alterac Mountains" in found("old dalaran")
        ns.CharDB().faction = "Horde"
        assert N.TransportUsable(horde) and not N.TransportUsable(zephras)  # (Dalaran's skycutter: the Alliance's)
        assert "Grom'gol Base Camp, Stranglethorn Vale" in found("grom'gol")
        assert "Old Dalaran Ruins, Alterac Mountains" not in found("old dalaran")
        # (a row's own faction wins over the guards)
        assert not N.TransportUsable(lua.eval('{ 0, 0, 0, 0, 10, 10, 60, "zeppelin", "a", "b", faction = "A" }'))
    finally:
        ns.CharDB().faction = old


def test_quest_areas_are_filled_faintly_under_their_outlines(game):
    # (asked 2026-10-08: "a faint fill", being inside a big quest area showed nothing zoomed in) each area's inside
    # rectangles drawn faintly on the outlines' layer, under them, sized and turned as the map's tiles; none with the
    # quest areas off
    lua, ns = game
    G, L = ns.GPS, ns.Layers
    st = ns.settings.gps
    real = L.EachArea
    keep = (st.layerQuests, st.layerQuestAreas)
    try:
        # (one area 40 x 20 yd around the player, as Layers hands it out)
        lua.execute("""
          local px, py = AGPS_NS.Geo.PlayerWorld()
          AGPS_FILL_AT = { px - 20, py - 10, px + 20, py + 10 }
        """)
        L.EachArea = lua.eval("""function(cont, cx, cy, reach, maps, fn, fillFn)
          local a = AGPS_FILL_AT
          fn(a[1], a[2], a[3], a[2])
          if fillFn then fillFn(a[1], a[2], a[3], a[4]) end
        end""")
        st.layerQuests, st.layerQuestAreas = True, True
        G.Redraw()
        lua.execute("AGPS_T = AGPS_T + 3")
        G.Update()
        assert G.areaFillUsed == 1
        t = G.areaFills[1]
        assert t._shown and str(t._tex).startswith("color:")
        w, h = t._w, t._h
        assert abs(w / h - 0.5) < 0.01  # (20 yd east-west across, 40 north-south: as a tile is laid)
        st.layerQuestAreas = False
        G.Redraw()
        lua.execute("AGPS_T = AGPS_T + 3")
        G.Update()
        assert G.areaFillUsed == 0
    finally:
        L.EachArea = real
        st.layerQuests, st.layerQuestAreas = keep
        G.Redraw()


def test_the_route_knows_when_the_player_is_swimming(game):
    # (q-117-canals, 2026-10-08) the player's route starts in a capital's water only while the game says they're
    # swimming (Nav.Swimming: IsSwimming; the dev tools' simulated player, its own `swimming`)
    lua, ns = game
    N, Geo = ns.Nav, ns.Geo
    lua.execute("AGPS_SWIMMING = true")
    assert N.Swimming() is True
    lua.execute("AGPS_SWIMMING = false")
    assert N.Swimming() is False
    old = Geo.override
    try:
        Geo.override = lua.eval("{ x = 0, y = 0, cont = 0, swimming = true }")
        assert N.Swimming() is True
    finally:
        Geo.override = old


def test_a_group_quest_left_out_shows_in_the_directions_with_a_button_to_put_it_back(game):
    # (asked 2026-10-07 for 1.1.6, about Keep / Leave Out after a reroute: "show my choice and let me change it") the
    # quest route's group quests show in the directions, kept or left out, with Leave Out or Put Back: the quest route is
    # made again with the change, and still not asked again. Every quest found left out: since 1.3.13 (Kooki3z
    # 2026-11-21: a quest left out "comes up again every time the route regenerates") not asked again, said with where
    # to put them back (Options > Routing > Quest Route); the route's only quest isn't offered to leave out
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      AGPS_QR = { stops = AGPS_NS.Layers.QuestStops, group = AGPS_NS.Layers.QuestGroup }
      AGPS_QR_LIST = {
        { x = 2250, y = 250, cont = 0, name = "Wolves", questRoute = true, quest = 1 },
        { x = 2300, y = 300, cont = 0, name = "Ogre Mound", questRoute = true, quest = 2 },
      }
      AGPS_NS.Layers.QuestStops = function()
        local out = {}
        for i, d in ipairs(AGPS_QR_LIST) do out[i] = CopyTable(d) end
        return out, { todo = #out, turnin = 0, missing = {}, elsewhere = 0 }
      end
      AGPS_NS.Layers.QuestGroup = function(id)
        if id == 2 then return { size = 3, elite = true } end
      end
    """)
    names = lambda: sorted(N.stops[i].name for i in range(1, len(N.stops) + 1))

    def rows():
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Redraw()
        G.Update()
        out = []
        for r in (G.groupRows or lua.table()).values():
            if r._shown:
                out.append((str(r.text._text), str(r.button.label._text), bool(r.button._shown), r.button))
        return out

    try:
        N.Clear()
        G.groupChoice = lua.eval("{}")
        G.QuestRoute()
        G.askBox.no._scripts.OnClick(G.askBox.no)  # (Leave Out)
        assert names() == ["Wolves"]
        (row,) = rows()
        assert "Left out:" in row[0] and "Ogre Mound" in row[0] and row[1] == "Put Back" and row[2]
        G.askBox._shown = False
        row[3]._scripts.OnClick(row[3])  # (Put Back)
        assert names() == ["Ogre Mound", "Wolves"] and G.groupChoice[2] == "keep"
        assert not G.askBox._shown  # (not asked again)
        (row,) = rows()
        assert "Group quest:" in row[0] and row[1] == "Leave Out" and row[2]
        row[3]._scripts.OnClick(row[3])  # (Leave Out again)
        assert names() == ["Wolves"] and G.groupChoice[2] == "leave"
        # (a route of other stops: no rows)
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        assert rows() == []
        # the group quest the only quest: Leave Out isn't offered; all left out: not asked again, said
        lua.execute("table.remove(AGPS_QR_LIST, 1)")
        G.groupChoice = lua.eval("{ [2] = 'keep' }")
        N.Clear()
        G.QuestRoute()
        assert names() == ["Ogre Mound"]
        (row,) = rows()
        assert row[1] == "Leave Out" and not row[2]
        G.groupChoice = lua.eval("{ [2] = 'leave' }")
        N.Clear()
        G.askBox._shown = False
        lua.execute("AGPS_QR.print = AGPS_NS.Print AGPS_PRINTS = {} "
                    "AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
        G.QuestRoute()
        assert not G.askBox._shown and names() == []
        said = [str(m) for m in lua.eval("AGPS_PRINTS").values()]
        assert any("every quest found is one you left out" in m and "Options > Routing > Quest Route" in m for m in said)
        N.PutBackQuest(2)  # (Options' Put Back All)
        G.QuestRoute()
        assert not G.askBox._shown and names() == ["Ogre Mound"]
    finally:
        lua.execute("if AGPS_QR.print then AGPS_NS.Print = AGPS_QR.print end")
        lua.execute("AGPS_NS.Layers.QuestStops, AGPS_NS.Layers.QuestGroup = AGPS_QR.stops, AGPS_QR.group")
        N.Clear()
        G.groupChoice = lua.eval("{}")
        G.groupQuests = lua.eval("{}")

def test_group_members_share_and_ask_for_routes(game):
    # (asked 2026-10-06) in a group: a Share button on the directions panel links the route in party chat (sent only
    # by pressing Enter); a right-click on a member's icon asks them for theirs (after a yes): they're asked whether
    # to send it; their stops come in and are offered as any shared route; "no" and "none" answers; strangers can't ask
    lua, ns = game
    G, I, N = ns.GPS, ns.Import, ns.Nav
    sent, offered = [], []
    real_send, real_offer, real_names = I.io.send, I.Offer, I.io.groupNames
    lua.execute("AGPS_OLD_OC = ChatFrame_OpenChat ChatFrame_OpenChat = function(t) AGPS_OPENED = t end")
    try:
        I.io.send = lambda prefix, msg, channel, target: sent.append((msg, channel, target))
        I.Offer = lambda sender, stops: offered.append((sender, [stops[i].name for i in range(1, len(stops) + 1)]))
        I.io.groupNames = lambda: lua.table("Friend-Realm")
        N.SetStops(lua.eval("{ { x = 2250, y = 250, cont = 0, name = 'Brill' }, { x = 1600, y = 240, cont = 0, name = 'Ruins' } }"), False, "red")
        G.Update()
        assert not G.shareButton._shown  # (not in a group)
        lua.execute("IsInGroup = function() return true end")
        G.Update()
        assert G.shareButton._shown and G.shareButton.label._text == "Share"
        G.shareButton._scripts.OnClick(G.shareButton)
        opened = lua.eval("AGPS_OPENED")
        assert opened.startswith("/p ") and "[AzerothGPS Route " in opened and not sent  # (nothing sent by itself)
        # asking a member for theirs: confirmed first, then a whisper
        assert I.AskForRoute("Stranger")[0] is False
        G.AskMemberForRoute("Friend-Realm")
        G.confirmBox.yes._scripts.OnClick(G.confirmBox.yes)
        assert sent == [("!\troute?", "WHISPER", "Friend-Realm")]
        # the asked side (here too): asked whether to send it; Send whispers the stops
        sent.clear()
        I.routeAskBox = None
        I.OnAddonMessage("AzerothGPS", "!\troute?", "WHISPER", "Friend-Realm")
        box = I.routeAskBox
        assert box._shown and "asks for your route (2 stops)" in box.text._text and not sent
        box.yes._scripts.OnClick(box.yes)
        assert len(sent) == 2 and all(c == "WHISPER" and t == "Friend-Realm" for _, c, t in sent)
        # their stops come in (any route id): offered
        for msg, _, _ in sent:
            I.OnAddonMessage("AzerothGPS", msg, "WHISPER", "Friend-Realm")
        assert offered == [("Friend-Realm", ["Brill", "Ruins"])]
        # asked again within ROUTE_ASK_GAP: not asked again
        I.routeAskBox = None
        I.OnAddonMessage("AzerothGPS", "!\troute?", "WHISPER", "Friend-Realm")
        assert I.routeAskBox is None
        # a stranger can't ask
        lua.execute("AGPS_T = AGPS_T + 60")
        I.OnAddonMessage("AzerothGPS", "!\troute?", "WHISPER", "Stranger")
        assert I.routeAskBox is None
        # "no": nothing taken in after it
        offered.clear()
        sent.clear()
        I.AskForRoute("Friend-Realm")
        I.OnAddonMessage("AzerothGPS", "!\tno", "WHISPER", "Friend-Realm")
        stop = I.ShareMessages(N.stops, "abc123")[1]
        I.OnAddonMessage("AzerothGPS", stop, "WHISPER", "Friend-Realm")
        assert not offered
        # no route: "none" back, not asked
        N.Clear()
        sent.clear()
        lua.execute("AGPS_T = AGPS_T + 60")
        I.OnAddonMessage("AzerothGPS", "!\troute?", "WHISPER", "Friend-Realm")
        assert sent == [("!\tnone", "WHISPER", "Friend-Realm")] and I.routeAskBox is None
    finally:
        I.io.send, I.Offer, I.io.groupNames = real_send, real_offer, real_names
        lua.execute("ChatFrame_OpenChat = AGPS_OLD_OC IsInGroup = nil")
        N.Clear()
        G.Update()


def test_asking_a_member_with_a_surname_whispers_their_whole_name(game):
    # (issue #854) on WoW Forever UnitName gives (first name, surname), not (name, realm): the ask went to "Stoveson"
    # alone ("No player named Stoveson is currently playing"), and their ask, from "Stoveson Borne-Realm", wasn't from
    # the group ("stoveson" there) and was dropped
    lua, ns = game
    G, I, N = ns.GPS, ns.Import, ns.Nav
    sent = []
    real_send = I.io.send
    lua.execute("""
        AGPS_854 = { UnitName = UnitName, UnitExists = UnitExists, IsInGroup = IsInGroup, R = RegionalUniqueNamesEnabled }
        UnitName = function(u)
          if u == "player" then return "Tester", "Smith" end
          if u == "party1" or u == "target" then return "Stoveson", "Borne" end
        end
        UnitExists = function(u) return u == "party1" end
        IsInGroup = function() return true end
        RegionalUniqueNamesEnabled = nil
    """)
    try:
        I.io.send = lambda prefix, msg, channel, target: sent.append((msg, channel, target))
        assert ns.UnitFullName("party1") == "Stoveson Borne"
        assert list(I.io.groupNames().values()) == ["Stoveson Borne"]
        assert I.AskForRoute("Stoveson Borne") is True
        assert sent == [("!\troute?", "WHISPER", "Stoveson Borne")]
        assert I.AskForRoute("Tester Smith")[0] is False  # (you)
        # their ask, the sender as the game gives it: from the group
        N.SetStops(lua.eval("{ { x = 2250, y = 250, cont = 0, name = 'Brill' } }"), False, "red")
        I.routeAskBox = None
        lua.execute("AGPS_T = AGPS_T + 600")
        I.OnAddonMessage("AzerothGPS", "!\troute?", "WHISPER", "Stoveson Borne-Realm")
        assert I.routeAskBox is not None and I.routeAskBox._shown
        # the game saying names are realm names: "Name-Realm" as before
        lua.execute("RegionalUniqueNamesEnabled = function() return false end")
        assert ns.UnitFullName("party1") == "Stoveson-Borne"
        lua.execute("RegionalUniqueNamesEnabled = function() return true end "
                    "Constants = Constants or {} Constants.CharacterNameSeparatorConsts = { CHARACTERNAME_SURNAME_SEPARATOR = ' ' }")
        assert ns.UnitFullName("party1") == "Stoveson Borne"
    finally:
        I.io.send = real_send
        lua.execute("""
            UnitName, UnitExists, IsInGroup = AGPS_854.UnitName, AGPS_854.UnitExists, AGPS_854.IsInGroup
            RegionalUniqueNamesEnabled = AGPS_854.R
            if Constants then Constants.CharacterNameSeparatorConsts = nil end
        """)
        if I.routeAskBox is not None:
            I.routeAskBox.Hide(I.routeAskBox)
        I.routeAskBox = None
        N.Clear()
        G.Update()


def test_a_pin_shift_clicked_goes_in_chat_and_adds_from_its_link(game):
    # (asked 2026-10-06) Shift-click a pin: a line in the chat box (nothing sent) that carries the pin whole; in an
    # AzerothGPS user's chat it's a link, and clicking it asks to add the pin to their map (as theirs, once)
    lua, ns = game
    G, I, P = ns.GPS, ns.Import, ns.Pins
    lua.execute("AGPS_OLD_OC = ChatFrame_OpenChat ChatFrame_OpenChat = function(t) AGPS_OPENED = t end")
    try:
        pin = P.Add(lua.eval("{ level = 0, x = 2250.25, y = 250.5, z = 61.3, down = true, icon = 134400, name = 'Hut (old)' }"))
        assert G.SharePin(pin)
        tag = lua.eval("AGPS_OPENED")
        assert tag.startswith("[AzerothGPS Pin: Hut (old)") and "@0:2250.2,250.5,z61.3,down #134400]" in tag.replace("2250.3", "2250.2")
        p = I.ParsePin(tag[len("[AzerothGPS Pin: "):-1])
        assert p.name == "Hut (old)" and p.level == 0 and abs(p.x - 2250.25) < 0.1 and p.z == 61.3 and p.down and p.icon == 134400
        # in someone's chat: a link (the name shown, the data in it)
        line = I.LinkifyRoutes("look at this " + tag, "Friend")
        assert "|Haddon:AzerothGPS:pin:0:" in line and "[AzerothGPS Pin: Hut (old)]|h" in line
        link = line.split("|H", 1)[1].split("|h", 1)[0]
        # one they have already: not offered again
        I.pinBox = None
        I.OnPinLink(link)
        assert I.pinBox is None
        P.Remove(pin)
        before = len(P.Own())
        assert I.OnPinLink(link)
        box = I.pinBox
        assert box._shown and "Add the pin" in box.text._text and "Hut (old)" in box.text._text
        box.yes._scripts.OnClick(box.yes)
        own = P.Own()
        got = own[len(own)]
        assert len(own) == before + 1 and got.name == "Hut (old)" and got.icon == 134400 and got.down and abs(got.z - 61.3) < 0.01
        # a made-up one (a level that doesn't exist, far off): left as text
        assert "|H" not in I.LinkifyRoutes("[AzerothGPS Pin: Bad @777:99999.0,1.0]", "Friend")
        P.Remove(got)
    finally:
        lua.execute("ChatFrame_OpenChat = AGPS_OLD_OC")


def test_a_long_dotted_line_is_clipped_to_the_map(game):
    # (asked 2026-10-06, errors in the player's saved data: "Line:SetTexCoord(): TexCoord out of range") a dotted
    # line far longer than the map (a long leg zoomed in on) is clipped to the map before drawing: its dashes repeat
    # only along what shows, and stay where they'd be on the whole line
    lua, ns = game
    G = ns.GPS
    x1, y1, x2, y2, cut = G.ClipSeg(-100000.0, 10.0, 100000.0, 10.0, 240.0)
    assert (x1, x2, y1, y2) == (-240.0, 240.0, 10.0, 10.0) and cut == pytest.approx(0.4988, abs=1e-4)
    assert G.ClipSeg(-500.0, 300.0, 500.0, 300.0, 240.0) is None  # (all outside)
    lua.execute("""
      AGPS_NS.GPS.overlays.longDots = function(ctx)
        local x, y = ctx.x, ctx.y
        ctx.Line(x - 50000, y, x + 50000, y, { 1, 1, 1 }, 3, 1, true)
      end
    """)
    try:
        G.Redraw()
        G.Update()
        dots = [w for w in lua.eval("AGPS_WIDGETS").values()
                if w._kind == "Line" and w._shown and w._coords and str(w._tex).endswith("Dash")]
        assert dots
        for d in dots:
            assert d._coords[2] - d._coords[1] <= G.MAX_DASH_REPEAT and 0 <= d._coords[1] < 1
    finally:
        lua.execute("AGPS_NS.GPS.overlays.longDots = nil")
        G.Redraw()
        G.Update()


def test_a_zoomed_in_redraw_looks_only_at_the_route_near_the_view(game):
    # (2026-10-06, the user: zoomed in on a long route, 15% of a CPU core, the same as zoomed all the way out) the route
    # is cut into chunks with their bounds (G.RouteChunks, once per part), and a redraw and the minimap's route go
    # through only the chunks near what they show (G.EachSegmentNear): zoomed in on a 21 km walk, a few dozen of its
    # segments a frame, not all of them; zoomed out, more
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    saved = (st.useFlights, st.avoidHighZones, st.avoidHostile, st.zoom)
    x0, y0 = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    try:
        st.useFlights, st.avoidHighZones, st.avoidHostile = False, False, False
        for t in list((ns.Transports or lua.eval("{}")).values()):  # (on foot all the way: rides left out)
            N.skipRides[N.RideKey(t)] = True
        N.SetStops(lua.eval("{ { x = -8913, y = 554, cont = 0, name = 'Stormwind' } }"), False, "red")  # (from Brill)
        for _ in range(60):
            lua.execute("AGPS_T = AGPS_T + 3.5")
            G.Update()
        r = N.route
        total = sum(len(p.pts) // 2 - 1 for p in r.parts.values())
        assert r and r.totalYards > 15000 and total > 400

        def segments_a_redraw(zoom):
            G.SetZoom(zoom)
            lua.execute("AGPS_T = AGPS_T + 0.05 AGPS_POS[2] = AGPS_POS[2] + 0.3")
            G.Update()  # (the chunks made)
            lua.execute("AGPS_T = AGPS_T + 0.05 AGPS_POS[2] = AGPS_POS[2] + 0.3")
            before = G.segsSeen
            G.Update()
            return G.segsSeen - before

        near = segments_a_redraw(60)
        assert 0 < near < total / 5, (near, total)
        before = G.segsSeen
        G.UpdateMinimapRoute(True)
        assert 0 < G.segsSeen - before < total / 5
        far = segments_a_redraw(2500)
        assert far > near
    finally:
        N.Clear()
        st.useFlights, st.avoidHighZones, st.avoidHostile = saved[:3]
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x0}, {y0} AGPS_T = AGPS_T + 1")
        G.SetZoom(saved[3])
        G.Update()


def test_the_route_on_the_games_minimap(game):
    # (asked 2026-10-06) the route on the game's minimap too: its lines around the player clipped to the minimap's
    # circle, the next stop's marker (on the edge while further); drawn again only when something it shows changed;
    # option minimapRoute
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    mm = G.minimapRoute
    assert mm.frame is not None  # (made at login)
    st = ns.settings.gps
    try:
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        G.Update()  # (the route worked out)
        assert N.route
        n = G.UpdateMinimapRoute(True)
        assert n > 0 and mm.stop._shown
        rad = 400 / 2 - 1
        for i in range(1, n + 1):
            l = mm.lines[i]
            assert l._shown
        draws = mm.draws
        assert G.UpdateMinimapRoute() == n and mm.draws == draws  # (nothing changed: not drawn again)
        lua.execute("AGPS_POS[2] = AGPS_POS[2] + 40")  # (the player moved)
        G.Update()
        G.UpdateMinimapRoute()
        assert mm.draws == draws + 1
        # where things go on it: west (+y in the world) to the left, north (+x) up; turned with the minimap
        assert G.MinimapPoint(2254.0, 293.0, 2254.0, 900.0, 400.0, 400.0, 0) == (-607.0, 0.0)
        assert G.MinimapPoint(0.0, 0.0, 100.0, 0.0, 400.0, 400.0, 0) == (0.0, 100.0)
        x, y = G.MinimapPoint(0.0, 0.0, 100.0, 0.0, 400.0, 400.0, math.pi / 2)  # (facing west: north on the right)
        assert x == pytest.approx(100.0) and y == pytest.approx(0.0, abs=1e-9)
        assert G.ClipCircle(0.0, 0.0, 0.0, 1000.0, 199.0)[3] == pytest.approx(199.0)
        st.minimapRoute = False
        assert G.UpdateMinimapRoute() == 0 and not mm.stop._shown and not mm.lines[1]._shown
    finally:
        st.minimapRoute = True
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        G.UpdateMinimapRoute(True)



def test_the_minimap_route_stays_while_the_route_is_worked_out_again(game):
    # (asked 2026-11-07, a recording in Ban'ethil Hollow: "fix this flicker") the minimap's line and the stop's marker
    # went off and on as the player walked: each background search done dropped the route (Nav.Invalidate) until the
    # next Nav.Route call, the arrow window's with the map closed, and the minimap (20 a second) drew none meanwhile
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    mm = G.minimapRoute
    try:
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        G.Update()
        n = G.UpdateMinimapRoute(True)
        assert n > 0 and mm.stop._shown
        N.Invalidate(True)  # (a search done)
        assert N.route is None
        assert G.UpdateMinimapRoute(True) == n and mm.stop._shown and mm.lines[1]._shown
        lua.execute("AGPS_POS[2] = AGPS_POS[2] + 40")  # (and followed as the player moves)
        assert G.UpdateMinimapRoute() > 0 and mm.stop._shown
        N.Clear()  # (no stop: none)
        assert G.UpdateMinimapRoute() == 0 and not mm.stop._shown and not mm.lines[1]._shown
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        G.UpdateMinimapRoute(True)


def test_the_minimap_draws_only_the_way_to_the_next_stop_on_the_players_level(game):
    # (asked 2026-11-05, with a screenshot down in Undercity: "the path outside the city is shown on the mini map ... just
    # show the same solid path from the gps map", "maybe even just to the current destination") the next stop's way out
    # of the city and its path on the land over it were drawn in the one color over the way to the stop in the city;
    # now only the way to the next stop, on the player's level
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    real = G.ClipCircle
    lua.execute("AGPS_MAP_REAL = AGPS_MAP AGPS_MAP = 1458 "
                "AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 1593.5, 157.3, 0 AGPS_T = AGPS_T + 1")
    try:
        assert N.PlayerLevel(0) == 10001  # (down in Undercity)
        N.SetStops(lua.eval("{ { x = 1560, y = 230, cont = 10001, name = 'In the city' }, "
                            "{ x = 522, y = 1652, cont = 0, name = 'The Sepulcher' } }"), False, "red")
        for t in range(8):
            lua.execute(f"AGPS_T = {900 + t}")
            G.Update()
        assert N.route
        # (the route near the minimap: the stop's way in the city, the next one's out of it and on the land over it)
        lua.execute("""
          local G = AGPS_NS.GPS
          AGPS_SEEN = {}
          local px, py, cont = AGPS_NS.Geo.PlayerWorld()
          G.EachSegmentNear(AGPS_NS.Nav.route, cont, px, py, AGPS_NS.Layers.MinimapYards(),
            function(x1, y1, x2, y2, kind, stop, pc)
              local k = stop .. ":" .. pc
              AGPS_SEEN[k] = (AGPS_SEEN[k] or 0) + 1
            end)
          AGPS_CLIPS = 0
        """)
        seen = dict(lua.eval("AGPS_SEEN").items())
        assert seen.get("1:10001", 0) > 0 and seen.get("2:10001", 0) > 0 and seen.get("2:0", 0) > 0
        G.ClipCircle = lua.eval("function(f) return function(...) AGPS_CLIPS = AGPS_CLIPS + 1 return f(...) end end")(real)
        n = G.UpdateMinimapRoute(True)
        assert n > 0 and lua.eval("AGPS_CLIPS") == seen["1:10001"]  # (was every one of them)
    finally:
        G.ClipCircle = real
        lua.execute("AGPS_MAP = AGPS_MAP_REAL AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        N.Clear()
        G.UpdateMinimapRoute(True)

def test_the_maps_icons_on_the_games_minimap(game):
    # (issue #10) the map's icons on the game's minimap too, each under its own show setting: a pin, a herb known, a
    # party member; where they are (turned with rotateMinimap), only those wholly on it; placed again only when
    # something they show changed; option minimapIcons
    lua, ns = game
    G, L = ns.GPS, ns.Layers
    mm = G.minimapRoute
    st = ns.settings.gps
    db = ns.db
    saved_pins, saved_nodes = db.pins, db.nodes
    saved = (st.showCustomPins, st.layerHerbs, st.showParty)
    others = ("poiPoi", "layerInstances", "layerCaves", "layerQuests", "layerCity", "layerOre")
    saved_others = {o: st[o] for o in others}
    lua.execute("""
        AGPS_MEMBERS = {}
        AGPS_OLD_FACING, AGPS_OLD_CVAR = GetPlayerFacing, GetCVar
    """)
    old_members = G.party.io.members
    try:
        db.pins = lua.eval("{}")
        db.nodes = lua.eval("{}")
        assert st.minimapIcons is False  # (off by default, issue #31)
        assert G.UpdateMinimapIcons(True) == 0
        st.minimapIcons = True
        st.showCustomPins, st.layerHerbs, st.showParty = True, True, True
        for o in others:
            st[o] = False  # (the kinds this test doesn't look at: the docks and entrances near are the data's)
        G.party.io.members = lua.eval("function() return AGPS_MEMBERS end")
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        px, py = 2254.0, 293.0
        yards = L.MinimapYards()
        k = 400 / yards
        ns.Pins.Add(lua.eval(f"{{ level = 0, x = {px + 60}, y = {py}, name = 'Mine' }}"))  # (60 yd north)
        L.AddNode(0, px, py + 40, "Peacebloom", "herb")  # (40 yd west)
        L.AddNode(0, px + 5000, py, "Silverleaf", "herb")  # (far off: not on it)
        L.version = L.version + 1
        n = G.UpdateMinimapIcons(True)
        assert n == 2, n
        spots = sorted((round(t._pt[4], 1), round(t._pt[5], 1)) for t in mm.icons.values() if t._shown)
        assert spots == sorted([(0.0, round(60 * k, 1)), (round(-40 * k, 1), 0.0)]), spots
        draws = mm.iconDraws
        assert G.UpdateMinimapIcons() == 2 and mm.iconDraws == draws  # (nothing changed: not placed again)
        # a party member: shown, and placed again when they move
        lua.execute(f"AGPS_MEMBERS = {{ {{ name = 'Pal', cont = 0, x = {px - 30}, y = {py}, class = 'MAGE' }} }}")
        assert G.UpdateMinimapIcons() == 3 and mm.iconDraws == draws + 1
        b = mm.partyIcons[1]
        assert b.edge._shown and round(b.edge._pt[5], 1) == round(-30 * k, 1)
        assert G.UpdateMinimapIcons() == 3 and mm.iconDraws == draws + 1
        lua.execute(f"AGPS_MEMBERS[1].x = {px - 20}")
        G.UpdateMinimapIcons()
        assert mm.iconDraws == draws + 2 and round(b.edge._pt[5], 1) == round(-20 * k, 1)
        # turned with the minimap: facing west, north is on the right
        lua.execute("GetPlayerFacing = function() return math.pi / 2 end "
                    "GetCVar = function(n) if n == 'rotateMinimap' then return '1' end end")
        G.UpdateMinimapIcons()
        pin = [t for t in mm.icons.values() if t._shown and abs(t._pt[4]) > 1]
        assert len(pin) == 1 and pin[0]._pt[4] == pytest.approx(60 * k) and pin[0]._pt[5] == pytest.approx(0, abs=1e-6)
        lua.execute("GetPlayerFacing, GetCVar = AGPS_OLD_FACING, AGPS_OLD_CVAR")
        # each kind hidden on the map stays off the minimap
        st.showParty = False
        assert G.UpdateMinimapIcons() == 2 and not b.edge._shown
        st.layerHerbs = False
        assert G.UpdateMinimapIcons() == 1
        st.showCustomPins = False
        assert G.UpdateMinimapIcons() == 0
        st.showCustomPins = True
        st.minimapIcons = False
        assert G.UpdateMinimapIcons() == 0 and not any(t._shown for t in mm.icons.values())
        st.minimapIcons = True
        # on the minimap's edge: only wholly inside its circle
        assert G.OnMinimap(0, 190, 12, 199, False) and not G.OnMinimap(0, 195, 12, 199, False)
        assert G.OnMinimap(190, 190, 12, 199, True) and not G.OnMinimap(140, 140, 12, 199, False)
    finally:
        lua.execute("GetPlayerFacing, GetCVar = AGPS_OLD_FACING, AGPS_OLD_CVAR")
        G.party.io.members = old_members
        db.pins, db.nodes = saved_pins, saved_nodes
        st.showCustomPins, st.layerHerbs, st.showParty = saved
        for o in others:
            st[o] = saved_others[o]
        st.minimapIcons = False
        L.version = L.version + 1
        G.UpdateMinimapIcons(True)


def _tip_lines(lua, G):
    # our hover tooltip, made here so its lines are recorded: SetText's and any AddLine's
    lua.execute("""
        AGPS_TIP_LINES = {}
        local tip = AzerothGPSMinimapTip or CreateFrame("GameTooltip", "AzerothGPSMinimapTip", UIParent, "GameTooltipTemplate")
        tip.SetText = function(s, t) s._text = t AGPS_TIP_LINES = { t } end
        tip.AddLine = function(_, t) AGPS_TIP_LINES[#AGPS_TIP_LINES + 1] = t end
    """)
    G.minimapTip = lua.eval("AzerothGPSMinimapTip")


def test_our_icons_on_the_games_minimap_are_named_on_hover(game):
    # (asked 2026-11-14: "on the minimap support mouse over for our icons to just show the NPC name. For example
    # "Koma (banker)" in org when mousing over the bank but also do this for all icons we put on the map, just no
    # "Double-click: add as a stop" line") hovering one of our icons on the game's minimap names it: a pin, a herb, a
    # party member, the next stop, a city place by its NPC; nothing off them, and only while the mouse is over it
    lua, ns = game
    G, L, N = ns.GPS, ns.Layers, ns.Nav
    mm = G.minimapRoute
    st = ns.settings.gps
    db = ns.db
    saved_pins, saved_nodes, saved_city, saved_revealed = db.pins, db.nodes, db.cityPois, db.cityRevealed
    kinds = ("showCustomPins", "layerHerbs", "showParty", "layerCity", "poiPoi", "layerInstances", "layerCaves",
             "layerQuests", "layerOre", "minimapIcons")
    saved = {k: st[k] for k in kinds}
    old_members = G.party.io.members
    lua.execute("AGPS_MEMBERS = {} AGPS_OLD_CURSOR = GetCursorPosition AGPS_CURSOR = { 0, 0 } "
                "GetCursorPosition = function() return AGPS_CURSOR[1], AGPS_CURSOR[2] end")
    try:
        db.pins, db.nodes, db.cityPois = lua.eval("{}"), lua.eval("{}"), lua.eval("{}")
        db.cityRevealed = None  # (no city's other places: an earlier test's guard)
        for k in kinds:
            st[k] = False
        st.minimapIcons = st.showCustomPins = st.layerHerbs = st.showParty = st.layerCity = True
        G.party.io.members = lua.eval("function() return AGPS_MEMBERS end")
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")
        px, py = 2254.0, 293.0
        ns.Pins.Add(lua.eval(f"{{ level = 0, x = {px + 60}, y = {py}, name = 'Mine' }}"))  # (60 yd north)
        L.AddNode(0, px, py + 40, "Peacebloom", "herb")  # (40 yd west)
        L.AddCityPoi(0, 2265.0, 250.0, "Brill Inn", 0)  # (a guard's: its innkeeper by it)
        lua.execute(f"AGPS_MEMBERS = {{ {{ name = 'Pal', cont = 0, x = {px - 30}, y = {py}, class = 'MAGE' }} }}")
        L.version = L.version + 1
        assert G.UpdateMinimapIcons(True) == 4
        _tip_lines(lua, G)
        f = mm.frame
        cx, cy = f.GetCenter(f)

        def hover(sx, sy):
            lua.execute(f"AGPS_CURSOR[1], AGPS_CURSOR[2] = {cx + sx}, {cy + sy}")
            return G.MinimapHover()

        def at(t):
            return t._pt[4], t._pt[5]

        icons = {}
        for t in mm.icons.values():
            if t._shown:
                icons[str(t.tipE.name)] = at(t)
        inn = G.PlaceNpc("Brill Inn", 0, 2265.0, 250.0)
        assert inn and inn.title == "Innkeeper"
        want = {"Mine": "Mine", "Peacebloom": "Peacebloom", "Brill Inn": f"{inn.name} (Innkeeper)"}
        assert sorted(icons) == sorted(want)
        for name, (sx, sy) in icons.items():
            assert hover(sx + 2, sy - 2) == want[name], name  # (anywhere on it)
            lines = list(lua.eval("AGPS_TIP_LINES").values())
            assert lines == [want[name]] and G.minimapTip._shown and lua.eval("AzerothGPSMinimapTip._owner == Minimap")
            assert not any("Double-click" in str(t) for t in lines)
        assert hover(*at(mm.partyIcons[1].edge)) == "Pal"
        # the next stop's marker, by its name
        N.SetStops(lua.eval(f"{{ {{ x = {px - 50}, y = {py + 10}, cont = 0, name = 'The Gallows' }} }}"), False, "red")
        G.Update()  # (the route worked out)
        assert N.route and G.UpdateMinimapRoute(True) > 0 and mm.stop._shown
        assert hover(*at(mm.stop)) == "The Gallows"
        # off our icons: none, and the tooltip hidden
        assert hover(150.0, -150.0) is None and not G.minimapTip._shown
        # a blip's own tooltip over the minimap (the game's): ours not over it
        sx, sy = icons["Mine"]
        lua.execute("GameTooltip._owner = Minimap GameTooltip._shown = true")
        assert hover(sx, sy) is None
        lua.execute("GameTooltip._owner = nil GameTooltip._shown = false")
        # (a screenshot 2026-11-20: the blip's tooltip owned by a frame in the Minimap, not the Minimap: two tooltips on
        # top of each other.) Ours goes into the game's as a line of its own, once.
        lua.execute("""
          AGPS_TIPLINES = {} AGPS_AL, AGPS_NL = GameTooltip.AddLine, GameTooltip.NumLines
          GameTooltip.NumLines = function() return 0 end -- (the game's tooltip: the blip's name only)
          GameTooltip.AddLine = function(_, t) AGPS_TIPLINES[#AGPS_TIPLINES + 1] = t end
          GameTooltip._owner = CreateFrame("Frame", nil, Minimap) GameTooltip._shown = true
        """)
        G.mergedTip = None  # (the tooltip hidden between: a new one)
        try:
            assert hover(sx, sy) is None and not G.minimapTip._shown
            assert hover(sx, sy) is None
            assert list(lua.eval("AGPS_TIPLINES").values()) == ["Mine"]
        finally:
            lua.execute("GameTooltip.AddLine, GameTooltip.NumLines = AGPS_AL, AGPS_NL GameTooltip._owner = nil GameTooltip._shown = false")
        assert hover(sx, sy) == "Mine" and G.minimapTip._shown
        # only while the mouse is over the Minimap: its OnEnter starts the watch, its OnLeave stops it and hides the tip
        w = G.minimapTipWatch
        assert w and not w._shown
        mmap = lua.eval("Minimap")
        mmap._scripts.OnEnter(mmap)
        assert w._shown
        assert hover(sx, sy) == "Mine"
        mmap._scripts.OnLeave(mmap)
        assert not w._shown and not G.minimapTip._shown
        # the game's minimap without our icons (the option off): nothing named
        st.minimapIcons = False
        G.UpdateMinimapIcons(True)
        assert hover(sx, sy) is None
    finally:
        N.Clear()
        G.UpdateMinimapRoute(True)
        lua.execute("GetCursorPosition = AGPS_OLD_CURSOR")
        G.party.io.members = old_members
        db.pins, db.nodes, db.cityPois, db.cityRevealed = saved_pins, saved_nodes, saved_city, saved_revealed
        for k in kinds:
            st[k] = saved[k]
        L.version = L.version + 1
        G.UpdateMinimapIcons(True)


def test_a_city_place_is_named_by_its_npc(game):
    # (asked 2026-11-14, "Koma (banker)" over Orgrimmar's bank) a city place's hover names the NPC there offering what
    # it's named for, with the game's title; a class trainer's place its trainer's, not the portal trainer by him
    lua, ns = game
    G, L = ns.GPS, ns.Layers

    def place(name):
        for p in ns.CityPlaces[1454].values():
            if p[3] == name:
                x, y, c = L.MapToWorld(1454, p[1] / 100, p[2] / 100)
                return G.MinimapTipText(name, None, True, c, x, y)

    bank = place("Orgrimmar Bank")
    assert bank in ("Koma (Banker)", "Karus (Banker)", "Soran (Banker)"), bank
    assert place("Orgrimmar Mage Trainer").endswith("(Mage Trainer)")
    assert place("Orgrimmar Skinning Trainer").endswith("(Skinning Trainer)")  # ("skinning" holds "inn")
    assert place("Orgrimmar Inn").endswith("(Innkeeper)")
    # no NPC of it near: the place's own name; an NPC's dot: "Name (Title)"; no title: the name alone
    assert G.MinimapTipText("Orgrimmar Bank", None, True, 0, 2254.0, 293.0) == "Orgrimmar Bank"
    assert G.MinimapTipText("Koma", "Banker") == "Koma (Banker)" and G.MinimapTipText("Koma") == "Koma"
    assert G.MinimapTipText(None) is None


def test_the_minimap_square_names_its_icons_on_hover(minimap):
    # (asked 2026-11-14) the GPS map as the minimap square: the game's Minimap over it takes the mouse, so the map's
    # buttons under the cursor are named by the hover: an NPC's dot "Name (Title)", a pin by its name, a stop by its
    # title, never their click hints; nothing off them
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    db = ns.db
    saved_pins, saved_show = db.pins, st.showCustomPins
    try:
        db.pins = lua.eval("{}")
        st.showCustomPins = True
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode()
        ns.Pins.Add(lua.eval("{ level = 0, x = 2264.0, y = 293.0, name = 'Mine' }"))
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        _tip_lines(lua, G)
        buttons = [b for b in G.poiButtons.values() if b._shown]
        pin = [b for b in buttons if b.kind == 12 and b.name == "Mine"]
        assert pin, [(b.kind, b.name) for b in buttons]
        lua.globals().AGPS_B = pin[0]
        lua.execute("AGPS_B.IsMouseOver = function() return true end")
        try:
            assert G.MinimapHover() == "Mine"
            assert list(lua.eval("AGPS_TIP_LINES").values()) == ["Mine"]
            # an NPC's dot (POI kind 16, its title in its note) as DrawPois leaves it
            lua.execute("AGPS_B.kind, AGPS_B.name, AGPS_B.note, AGPS_B.city = 16, 'Koma', 'Banker', nil")
            assert G.MinimapHover() == "Koma (Banker)"
            lines = list(lua.eval("AGPS_TIP_LINES").values())
            assert lines == ["Koma (Banker)"] and not any("Double-click" in str(t) for t in lines)
        finally:
            lua.execute("AGPS_B.IsMouseOver = nil")
        # off them: nothing
        assert G.MinimapHover() is None and not G.minimapTip._shown
        # a stop's marker (over the icons): its title
        ns.Nav.SetStops(lua.eval("{ { x = 2204, y = 303, cont = 0, name = 'The Gallows' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        stops = [b for b in G.stopPins.values() if b._shown and b.title == "The Gallows"]
        assert stops
        lua.globals().AGPS_B = stops[0]
        lua.execute("AGPS_B.IsMouseOver = function() return true end")
        try:
            assert G.MinimapHover() == "The Gallows"
        finally:
            lua.execute("AGPS_B.IsMouseOver = nil")
    finally:
        ns.Nav.Clear()
        db.pins, st.showCustomPins = saved_pins, saved_show


def test_only_real_herbs_and_ore_veins_are_saved(game):
    # (asked 2026-11-05, Tirisfal's Cult of the Damned) collecting a quest's ground pickups with a Dark Enforcer
    # targeted saved "Dark Enforcer" as a herb, again and again along the way; pickups like Doom Weed passed for herbs
    # by their words. Only the herbs and veins there are, and those saved before aren't shown or shared.
    lua, ns = game
    L, I = ns.Layers, ns.Import
    db = ns.db
    saved_nodes = db.nodes
    lua.execute("AGPS_HERB_POS = { AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] }; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2000.0, 300.0, 0")
    try:
        db.nodes = lua.eval("{}")
        ev = L.frame._scripts.OnEvent
        # a gathering cast that names the unit targeted, not what was gathered
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", "Dark Enforcer", "cast-1", 2366)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-1", 2366)
        assert db.nodes[0] is None
        # "Requires Herbalism" with the unit's tooltip the last shown (fading: no unit in it any more)
        L.NoteWorldObject("Dark Enforcer", 10.0)
        assert not L.OnGatherError("Requires Herbalism", 11.0, 2010.0, 300.0, 0) and db.nodes[0] is None
        # the quest's pickups and WoW Forever's own (their locks aren't gathering ones), and an ore's item
        for name in ("Doom Weed", "Gloom Weed", "Tirisfal Pumpkin", "Cattail", "Speargrass", "Dry Branch", "Copper Ore"):
            assert not L.AddNode(0, 2020.0, 300.0, name) and not L.AddNode(0, 2020.0, 300.0, name, "herb"), name
            assert L.NodeKind(name) is None, name
        assert not L.AddNode(0, 2020.0, 300.0, "Peacebloom", "ore")  # (a herb, said to be ore)
        assert db.nodes[0] is None
        # the real ones: gathered (the cast names it), and WoW Forever's poor veins
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", "Peacebloom", "cast-2", 2366)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-2", 2366)
        assert L.AddNode(0, 2100.0, 300.0, "Poor Copper Vein", "ore")
        kept = [(str(n[3]), str(n[4])) for n in db.nodes[0].values()]
        assert kept == [("Peacebloom", "herb"), ("Poor Copper Vein", "ore")]
        # one saved before: kept in the file, not shown, listed or shared
        db.nodes[0][3] = lua.eval("{ 2050.0, 300.0, 'Dark Enforcer', 'herb', 4 }")
        poly = lua.eval("{ 1900, 200, 2200, 200, 2200, 400, 1900, 400 }")
        assert sorted(str(n.name) for n in L.NodesInPolygon(0, poly).values()) == ["Peacebloom", "Poor Copper Vein"]
        marks = L.Marks(0, 2000.0, 300.0, 500.0, lua.table())
        assert "Dark Enforcer" not in [str(marks[i][4]) for i in range(1, len(marks) + 1)]
        text = I.MapDataText(lua.eval("{ herbs = true, ore = true }"))
        assert "Peacebloom" in str(text) and "Dark Enforcer" not in str(text)
        assert len(db.nodes[0]) == 3
    finally:
        db.nodes = saved_nodes
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = AGPS_HERB_POS[1], AGPS_HERB_POS[2], AGPS_HERB_POS[3]")
        L.version = L.version + 1


def test_wow_forevers_own_herbs_and_veins_are_saved_by_their_tooltips(game):
    # (a bug report, 2026-11-06, with a screenshot: Teldrassil) looting a Stunted Silverleaf, WoW Forever's own herb,
    # didn't show it on the map: only KNOWN_NODES' names were saved. Its tooltip says "Herbalism" under the name, as
    # every herb's does ("Mining" for a vein): a herb or vein hovered that way is saved when gathered, and
    # afterwards seen on the minimap. Units, items, spells and quest pickups aren't.
    lua, ns = game
    L = ns.Layers
    db = ns.db
    saved_nodes, saved_names = db.nodes, db.nodeNames
    lua.execute("AGPS_HERB_POS = { AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] }; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2000.0, 300.0, 0")
    lua.execute("""
      GameTooltipTextLeft1 = GameTooltipTextLeft1 or CreateFrame("Frame")
      GameTooltipTextLeft2 = GameTooltipTextLeft2 or CreateFrame("Frame")
      AGPS_HOVER = function(name, line2, what)
        GameTooltipTextLeft1._text, GameTooltipTextLeft2._text = name, line2
        GameTooltip.GetUnit = function() if what == "unit" then return name, "target" end end
        GameTooltip.GetItem = function() if what == "item" then return name, "item:1" end end
        GameTooltip._scripts.OnShow(GameTooltip)
        GameTooltip.GetUnit = function() return nil end
        GameTooltip.GetItem = function() return nil end
      end""")
    try:
        db.nodes, db.nodeNames = lua.eval("{}"), None
        ev = L.frame._scripts.OnEvent

        def gather(name, spell, n, x):
            lua.execute(f"AGPS_POS[1] = {x}")
            ev(L.frame, "UNIT_SPELLCAST_SENT", "player", name, f"cast-{n}", spell)
            ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", f"cast-{n}", spell)

        # the one in the report (now listed) and a made-up WoW Forever vein known only by its tooltip
        assert L.NodeKind("Stunted Silverleaf") == "herb"
        lua.globals().AGPS_HOVER("Stunted Silverleaf", "Herbalism")
        gather("Stunted Silverleaf", 2366, 1, 2000.0)
        assert L.NodeKind("Weathered Tin Vein") is None
        lua.globals().AGPS_HOVER("Weathered Tin Vein", "Mining")
        assert L.NodeKind("Weathered Tin Vein") == "ore"
        gather("Weathered Tin Vein", 2575, 2, 2100.0)
        kept = [(str(n[3]), str(n[4])) for n in db.nodes[0].values()]
        assert kept == [("Stunted Silverleaf", "herb"), ("Weathered Tin Vein", "ore")]
        # learned account-wide: the minimap's tooltip (names only) and imports know it now
        assert db.nodeNames["Weathered Tin Vein"] == "ore"
        # not herbs or veins: a unit, an item, a quest pickup, the profession's own name, a requirement
        lua.globals().AGPS_HOVER("Dark Enforcer", "Herbalism", "unit")
        lua.globals().AGPS_HOVER("Copper Ore", "Mining", "item")
        lua.globals().AGPS_HOVER("Doom Weed", "Requires Herbalism")
        lua.globals().AGPS_HOVER("Herbalism", "Herbalism")
        for name in ("Dark Enforcer", "Copper Ore", "Doom Weed", "Herbalism"):
            assert L.NodeKind(name) is None, name
        gather("Doom Weed", 2366, 3, 2200.0)
        assert len(db.nodes[0]) == 2
    finally:
        db.nodes, db.nodeNames = saved_nodes, saved_names
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = AGPS_HERB_POS[1], AGPS_HERB_POS[2], AGPS_HERB_POS[3]")
        L.version = L.version + 1


def test_each_node_shows_the_bag_icon_of_what_gathering_it_gives(game):
    # (asked 2026-11-06) a node's map icon is its item's (Peacebloom's, Copper Ore for a Copper Vein), not the
    # gathering spell's for all, drawn at its exact size. WoW Forever's own (no item listed) take the first item of
    # their loot right after a gathering cast, kept account-wide; the spell's until then.
    lua, ns = game
    L, G = ns.Layers, ns.GPS
    db = ns.db
    saved = db.nodes, db.nodeItems
    lua.execute("""
      AGPS_C_ITEM, AGPS_LOOT = C_Item, nil
      AGPS_HERB_POS = { AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] }
      C_Item = setmetatable({ GetItemIconByID = function(id) return 900000 + id end }, { __index = AGPS_C_ITEM or {} })
      GetNumLootItems = function() return AGPS_LOOT and #AGPS_LOOT or 0 end
      GetLootSlotType = function(i) return AGPS_LOOT[i].money and 2 or 1 end
      GetLootSlotInfo = function(i) local s = AGPS_LOOT[i] return s.icon, s.name, 1, nil, 1, false, s.quest end
    """)
    try:
        db.nodes, db.nodeItems = lua.eval("{}"), None
        L.itemIcons = lua.eval("{}")
        assert L.AddNode(0, 2000.0, 300.0, "Peacebloom") and L.AddNode(0, 2030.0, 300.0, "Copper Vein")
        assert L.AddNode(0, 2060.0, 300.0, "Stunted Silverleaf")

        def icons():
            marks = L.Marks(0, 2000.0, 300.0, 500.0, lua.table())
            return {str(marks[i][4]): (marks[i][3], marks[i][15]) for i in range(1, len(marks) + 1)}

        spell = L.NodeIcon("herb")
        got = icons()
        assert got["Peacebloom"] == (902447, True) and got["Copper Vein"] == (902770, True)
        assert got["Stunted Silverleaf"] == (spell, True)  # (nothing learned yet: the generic icon)
        assert L.NODE_ITEMS["Silver Vein"] == 2775 and L.NODE_ITEMS["Ooze Covered Silver Vein"] == 2775
        # every herb and vein listed has its item but WoW Forever's own
        for kind in ("herb", "ore"):
            for name in L.KNOWN_NODES[kind].values():
                assert L.NODE_ITEMS[name] or name in ("Stunted Silverleaf", "Poor Copper Vein"), name
        ev = L.frame._scripts.OnEvent
        # loot that isn't a gathering's (a mob's) teaches nothing
        lua.execute("AGPS_LOOT = { { icon = 111, name = 'Linen Cloth' } }")
        ev(L.frame, "LOOT_OPENED", False, False)
        assert db.nodeItems is None or db.nodeItems["Stunted Silverleaf"] is None
        # gathered: the money and a quest item skipped, the first item's icon is the node's from now
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", "Stunted Silverleaf", "cast-loot-1", 2366)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-loot-1", 2366)
        lua.execute("AGPS_LOOT = { { icon = 133784, name = '3 Copper', money = true }, "
                    "{ icon = 222, name = 'A Quest Thing', quest = true }, { icon = 134190, name = 'Stunted Silverleaf' }, "
                    "{ icon = 333, name = 'Something Else' } }")
        ev(L.frame, "LOOT_OPENED", False, False)
        assert db.nodeItems["Stunted Silverleaf"].icon == 134190
        assert str(db.nodeItems["Stunted Silverleaf"].item) == "Stunted Silverleaf"
        assert icons()["Stunted Silverleaf"] == (134190, True)
        # kept: a later loot doesn't change it, and a listed node's item stays its own
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", "Stunted Silverleaf", "cast-loot-2", 2366)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-loot-2", 2366)
        lua.execute("AGPS_LOOT = { { icon = 444, name = 'Other' } }")
        ev(L.frame, "LOOT_OPENED", False, False)
        assert db.nodeItems["Stunted Silverleaf"].icon == 134190
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", "Peacebloom", "cast-loot-3", 2366)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-loot-3", 2366)
        ev(L.frame, "LOOT_OPENED", False, False)
        assert db.nodeItems["Peacebloom"] is None and icons()["Peacebloom"][0] == 902447
        # a loot window long after the cast isn't that node's
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", "Poor Copper Vein", "cast-loot-4", 2575)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-loot-4", 2575)
        assert L.OnLootOpened(10 ** 9) is None and db.nodeItems["Poor Copper Vein"] is None
        # on the map: the item's icon, at a game icon's exact size; a stop made from it keeps it
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2000.0, 300.0, 0; AGPS_T = AGPS_T + 1")
        G.drawVersion = G.drawVersion + 1
        G.Update()
        b = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.stopTex == 902447]
        assert b, "Peacebloom's item icon on the map"
    finally:
        db.nodes, db.nodeItems = saved
        L.itemIcons = lua.eval("{}")
        lua.execute("C_Item = AGPS_C_ITEM; GetNumLootItems, GetLootSlotType, GetLootSlotInfo = nil, nil, nil")
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = AGPS_HERB_POS[1], AGPS_HERB_POS[2], AGPS_HERB_POS[3]")
        L.version = L.version + 1


def test_find_herbs_and_ore_shows_only_the_ones_picked(game):
    # (asked 2026-11-06) search for particular herbs or veins and only theirs show on the map: the map menu's Find Herbs
    # and Ore (the Herbs, Ore and Farming group) opens a window (ns.Window's) with a search box; a click on a name picks
    # it or puts it back, Show All shows every one again. A farming area takes only those picked too.
    lua, ns = game
    L, G = ns.Layers, ns.GPS
    db, st = ns.db, ns.settings.gps
    saved = db.nodes, st.nodeFilter, st.layerHerbs, st.layerOre
    try:
        db.nodes = lua.eval("{}")
        st.nodeFilter = lua.eval("{}")
        for i, name in enumerate(("Peacebloom", "Silverleaf", "Copper Vein", "Tin Vein", "Peacebloom")):
            assert L.AddNode(0, 2000.0 + 40 * i, 300.0, name)

        def shown():
            marks = L.Marks(0, 2000.0, 300.0, 500.0, lua.table())
            return sorted(str(marks[i][4]) for i in range(1, len(marks) + 1) if L.NodeKind(marks[i][4]))  # (the nodes alone)

        assert shown() == ["Copper Vein", "Peacebloom", "Peacebloom", "Silverleaf", "Tin Vein"]
        # the button: in the gather group, opening the finder
        find = next(t for t in G.QUICK.values() if t.id == "nodeFind")
        assert str(find.label) == "Find Herbs and Ore"
        gather = next(g for g in G.QUICK_GROUPS.values() if g.id == "gather")
        assert "nodeFind" in [str(m) for m in gather.members.values()]
        assert not G.QuickOn(find)
        find.action()
        f = L.finder
        assert f.IsShown(f) and f.SetWindowTitle is not None and f.top is not None and G.QuickOn(find)  # (ns.Window)
        # typing narrows the names (those with nodes known first); a click picks one
        f.box.SetText(f.box, "pea")
        f.box._scripts.OnTextChanged(f.box)
        row = f.rows[1]
        assert str(row.entry.name) == "Peacebloom" and row.entry.count == 2 and row.entry.icon is not None
        v = G.drawVersion
        row._scripts.OnClick(row)
        assert G.drawVersion > v  # (drawn again at once)
        assert shown() == ["Peacebloom", "Peacebloom"]
        assert "Peacebloom" in str(f.status.GetText(f.status))
        # Enter picks the first match too; a pick turns its kind's layer on
        st.layerOre = False
        f.box.SetText(f.box, "copper v")
        f.box._scripts.OnTextChanged(f.box)
        f.box._scripts.OnEnterPressed(f.box)
        assert st.layerOre is True and shown() == ["Copper Vein", "Peacebloom", "Peacebloom"]
        # the farming area uses those picked
        poly = lua.eval("{ 1900, 200, 2300, 200, 2300, 400, 1900, 400 }")
        inside = L.NodesInPolygon(0, poly, L.VisibleKinds(), L.NodeFilter())
        assert sorted(str(n.name) for n in inside.values()) == ["Copper Vein", "Peacebloom", "Peacebloom"]
        # (by skill needed, then name: both picked need 1, first); the Herbs layer off hides a picked herb
        f.box.SetText(f.box, "")
        f.box._scripts.OnTextChanged(f.box)
        assert [bool(f.rows[i].entry.picked) for i in (1, 2, 3)] == [True, True, False]
        st.layerHerbs = False
        assert shown() == ["Copper Vein"]
        st.layerHerbs = True
        f.rows[1]._scripts.OnClick(f.rows[1])  # (Copper Vein, put back)
        assert shown() == ["Peacebloom", "Peacebloom"]
        # Show All: every one again
        f.showAll._scripts.OnClick(f.showAll)
        assert L.NodeFilter() is None and len(shown()) == 5
        assert "all" in str(f.status.GetText(f.status))
        f.Hide(f)
        assert not G.QuickOn(find)
        assert len(L.NodeNames("zzz")) == 0  # (no herb or vein by that name)
    finally:
        db.nodes = saved[0]
        st.nodeFilter, st.layerHerbs, st.layerOre = saved[1] or lua.eval("{}"), saved[2], saved[3]
        if L.finder:
            L.finder.Hide(L.finder)
        L.version = L.version + 1


def test_a_square_minimap_without_getminimapshape_is_square_for_the_route(game):
    # (a bug report, 2026-10-30, with a screenshot: EllesmereUI's square minimap, "the path stops on the boundary where a
    # circular minimap would be") a minimap addon that masks the minimap square and defines no GetMinimapShape: the mask
    # it put on says square, and the route is drawn again at once, clipped to the square; the option says otherwise
    # when set, and an addon's GetMinimapShape is taken at its word
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    mm = G.minimapRoute
    st = ns.settings.gps
    real_seg, real_circle = G.ClipSeg, G.ClipCircle
    counted = lua.eval("function(k, f) return function(...) AGPS_CLIPS[k] = AGPS_CLIPS[k] + 1 return f(...) end end")

    def clips():
        lua.execute("AGPS_CLIPS = { seg = 0, circle = 0 }")
        G.UpdateMinimapRoute()
        return lua.eval("AGPS_CLIPS.seg"), lua.eval("AGPS_CLIPS.circle")
    try:
        assert lua.eval("GetMinimapShape") is None and not G.MinimapSquare()  # (no mask seen: the game's round one)
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        G.Update()
        assert N.route and G.UpdateMinimapRoute(True) > 0
        G.ClipSeg, G.ClipCircle = counted("seg", real_seg), counted("circle", real_circle)
        draws = mm.draws
        G.OnMinimapMask(130937)  # (EllesmereUI's square mask, Interface\Buttons\WHITE8X8, set through the hook)
        assert G.MinimapSquare()
        seg, circle = clips()
        assert mm.draws == draws + 1 and seg > 0 and circle == 0  # (drawn again at once, to the square's edges)
        G.OnMinimapMask(186178)  # (the game's round mask again)
        seg, circle = clips()
        assert not G.MinimapSquare() and seg == 0 and circle > 0
        st.minimapShape = "square"  # (the option over the mask)
        assert G.MinimapSquare() and clips()[0] > 0
        G.OnMinimapMask(130937)
        st.minimapShape = "round"
        assert not G.MinimapSquare() and clips()[1] > 0
        st.minimapShape = "auto"
        lua.execute("GetMinimapShape = function() return 'ROUND' end")  # (an addon that says: its word first)
        assert not G.MinimapSquare()
    finally:
        G.ClipSeg, G.ClipCircle = real_seg, real_circle
        lua.execute("GetMinimapShape = nil")
        G.minimapMask = None
        st.minimapShape = "auto"
        N.Clear()
        G.UpdateMinimapRoute(True)


def test_the_minimap_button_is_left_in_a_button_drawer_and_on_a_square_minimaps_edge(game):
    # (the same report: "The icon also jumps out of the addon button drawer I have and can be dragged in a circle in front
    # of the map") a drawer that took the button (its parent no longer the minimap, hidden while the drawer is shut) has it:
    # an options change neither puts it back on the minimap nor shows it, and it doesn't drag round the minimap. On the
    # minimap: round its edge, or on a square one's edge
    lua, ns = game
    O, st, mset = ns.Options, ns.settings.gps, ns.settings.minimap
    b, mmap = lua.globals().AzerothGPSMinimapButton, lua.globals().Minimap
    same = lua.eval("rawequal")
    assert b is not None and same(b.GetParent(b), mmap)
    angle, hide = mset.angle, mset.hide
    try:
        mset.angle, mset.hide = 45, False
        O.UpdateButton()
        r = 400 / 2 + 5  # (the stand-in minimap's width)
        assert same(b._pt[2], mmap) and (b._pt[4], b._pt[5]) == (pytest.approx(r * math.cos(math.pi / 4)),) * 2
        st.minimapShape = "square"
        O.UpdateButton()
        assert (b._pt[4], b._pt[5]) == (pytest.approx(r), pytest.approx(r))  # (the square's corner, at 45 degrees)
        drawer = lua.eval("CreateFrame('Frame', 'AGPSTestDrawer', UIParent)")
        b.SetParent(b, drawer)  # (a drawer takes it, and hides it while it's shut)
        b.Hide(b)
        b._pt = None
        O.Apply()  # (any options change)
        assert not b._shown and b._pt is None
        b._scripts.OnDragStart(b)
        assert b._scripts.OnUpdate is None  # (not dragged round the minimap)
        mset.hide = True  # (the setting itself still hides and shows it)
        O.UpdateButton()
        assert not b._shown
        mset.hide = False
        O.UpdateButton()
        assert b._shown
    finally:
        b.SetParent(b, mmap)
        mset.angle, mset.hide = angle, hide
        st.minimapShape = "auto"
        O.UpdateButton()


def test_a_still_map_doesnt_place_its_lines_again(game):
    # (asked 2026-10-06: a route that doesn't change isn't drawn again) redraws of a still map leave the lines where
    # they are: none placed again unless something moved
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    try:
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        G.Follow()  # (on the player: the route in view, whatever earlier tests left the map looking at)
        G.Redraw()
        G.Update()
        G.Update()
        before = G.lineMoves
        G.Redraw()
        G.Update()
        assert G.lineMoves == before  # (nothing moved: none placed)
        lua.execute("AGPS_POS[2] = AGPS_POS[2] + 60")
        G.Update()
        assert G.lineMoves > before
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        G.Update()


def test_an_undercity_quest_is_down_in_the_city_when_built_from_tirisfal(game):
    # (asked 2026-10-06: quest turn-ins in Undercity were routed outside) up in Tirisfal, an Undercity quest's marker
    # is on Tirisfal's map too: the city's own map is asked first, so its stop is down in the city (its level, 10001),
    # not on the surface over the NPC
    lua, ns = game
    L, G = ns.Layers, ns.GPS
    lua.execute("""
      AGPS_QL = C_QuestLog
      AGPS_BEST = C_Map.GetBestMapForUnit
      local function uv(map, x, y)
        local b = AGPS_NS.Maps[map].bounds
        return (b[4] - y) / (b[4] - b[2]), (b[3] - x) / (b[3] - b[1])
      end
      -- Jeremiah Payson, the Trade Quarter (the CMaNGOS dump's spawn): his quest's turn-in
      local tu, tv = uv(1420, 1595.3, 224.7)
      local cu, cv = uv(1458, 1595.3, 224.7)
      C_QuestLog = {
        GetNumQuestLogEntries = function() return 1, 1 end,
        GetInfo = function(i) return { questID = 501 } end,
        IsComplete = function(id) return true end,
        IsOnQuest = function() return true end,
        GetTitleForQuestID = function(id) return "The Jeremiah Blues" end,
        GetQuestsOnMap = function(map)
          if map == 1420 then return { { questID = 501, x = tu, y = tv } } end
          if map == 1458 then return { { questID = 501, x = cu, y = cv } } end
          return {}
        end,
      }
      C_Map.GetBestMapForUnit = function() return 1420 end
    """)
    try:
        stops, c = L.QuestStops()
        assert len(stops) == 1 and stops[1].name == "Turn in: The Jeremiah Blues"
        assert stops[1].cont == 10001  # (down in Undercity)
        assert abs(stops[1].x - 1595.3) < 1 and abs(stops[1].y - 224.7) < 1
    finally:
        lua.execute("C_QuestLog = AGPS_QL C_Map.GetBestMapForUnit = AGPS_BEST")


def test_a_stop_upstairs_says_so_and_its_last_yards_are_the_stairs_color(game):
    # (asked 2026-10-06: Brill's trainers upstairs in the inn) a stop at a town place upstairs (ns.TownPlaces' fl, from
    # its NPC's height): "(upstairs)" in the steps, "Upstairs: <it>" near it, a stairs badge on its marker, and the
    # route's last yards into the building dotted in the stairs color; Goldshire's Warlock trainer is downstairs
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    try:
        mage = lua.eval("{ x = 2259.0, y = 235.9, cont = 0, name = 'Brill Mage Trainer', z = 41.2 }")
        assert N.StopFloor(mage) == 1
        assert N.StopFloor(lua.eval("{ x = -9473.0, y = -4.1, cont = 0, name = 'Goldshire Warlock Trainer' }")) == -1
        assert N.StopFloor(lua.eval("{ x = 2266.0, y = 242.8, cont = 0, name = 'Brill Inn' }")) is None  # (the ground floor)
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2300.0, 300.0")  # (in Brill's square, 75 yd off)
        N.SetStops(lua.eval("{ { x = 2259.0, y = 235.9, cont = 0, name = 'Brill Mage Trainer', z = 41.2 }, "
                            "{ x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        G.Follow()
        G.Redraw()
        G.Update()
        assert N.route
        steps = N.StepsText(5)
        assert "Brill Mage Trainer (upstairs)" in steps
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2275.0, 250.0")  # (by the inn)
        text = N.Status(2275.0, 250.0, 0)
        assert "Upstairs: Brill Mage Trainer" in text
        G.Redraw()
        G.Update()
        pins = [w for w in lua.eval("AGPS_WIDGETS").values() if w.floorBadge and w._shown and w.title == "Brill Mage Trainer"]
        assert pins and pins[0].floorBadge._shown and pins[0].floor == 1
        stairs = [w for w in lua.eval("AGPS_WIDGETS").values()
                  if w._kind == "Line" and w._shown and w.agpsC is not None and lua.eval("rawequal")(w.agpsC, G.STAIRS_COLOR)]
        assert stairs  # (its last yards in the stairs color)
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        G.Update()


def _walk(lua, ns, path, upto, step=1.5, s0=0.0):
    # (along `path`, Nav's status every `step` yards with the clock on: the floor followed as the player goes)
    N, T = ns.Nav, ns.Turns
    s = s0
    while s <= upto:
        x, y = T.PointAt(path, s)
        lua.execute("AGPS_POS[1], AGPS_POS[2] = %f, %f AGPS_T = AGPS_T + 0.3" % (x, y))
        N.Status(x, y, 0)
        s += step
    return s


def test_a_route_to_an_upstairs_stop_goes_in_by_the_door_and_up_the_stairs(game):
    # (asked 2026-10-06, Brill: "the icon should actually be on the stairs like how undercity works, we need indoor routes
    # in all buildings like cities") the inn's inside (Data/Indoors.lua: its floors' roads, stairs and doors, from its
    # model) is part of the roads: a route to a trainer upstairs goes in by its door, along the ground floor and up its
    # stairs ("Take the stairs up"), the stairs icon on the stairs, not by the stop
    lua, ns = game
    G, N, R, T = ns.GPS, ns.Nav, ns.Router, ns.Turns
    inn = next(b for b in ns.Indoors[0].values() if "duskwood_inn" in str(b[1]))
    assert len(list(inn.floors.values())) >= 2
    ov = next(o for o in ns.RoadOverlays[0].values() if o.indoor)
    assert any(e[4] == 6 for e in ov.e.values()) and len(list(ov.joins.values())) >= 1  # (stairs; doors joined)
    try:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2300.0, 300.0")  # (in Brill's square)
        N.ResetCityTrack()
        N.SetStops(lua.eval("{ { x = 2259.0, y = 235.9, cont = 0, name = 'Brill Mage Trainer', z = 41.2 } }"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        r = N.route
        assert r and not r.noWay and not r.unconnected
        pts = [(r.pts[i], r.pts[i + 1]) for i in range(1, len(r.pts), 2)]
        ups = [i for i in range(len(pts) - 1) if R.StairAt(0, *pts[i], *pts[i + 1]) == 1]
        assert ups  # (up the stairs)
        n = list(ov.n.values())
        doors = [(n[2 * d - 2], n[2 * d - 1]) for d in ov.bridge.values()]
        assert any(min(math.dist(p, q) for q in doors) <= 3 for p in pts[:ups[0] + 1])  # (in by a door, before them)
        ms = T.Maneuvers(T.Path(r), "the trainer")
        assert "Take the stairs up" in [str(m.text) for m in ms.values()]
        # (asked 2026-11-12 for 1.2.4: "consider say when to enter a cave or cross a bridge or go into a building") in by
        # the inn's door: "Go into the building" there, before its stairs up (the start, on the town hall's floor in the
        # square: out of that one first, not into it)
        said = [(str(m.text), m.dist) for m in ms.values()]
        up = max(d for t, d in said if t == "Take the stairs up")
        into = [d for t, d in said if t == "Go into the building"]
        assert len(into) == 1 and into[0] < up, said
        assert [t for t, d in said if "building" in t] == ["Leave the building", "Go into the building"], said
        door = T.PointAt(T.Path(r), into[0])
        assert min(math.dist(door, q) for q in doors) <= 4, (door, said)
        pois = lua.eval("{}")
        assert G.AddRouteStairs(pois, r, 0, 2265.0, 245.0, 0, 3.0, 300) >= 1
        # (the inn's stairs up: one icon for the flight, its landing too; the start in the square is on the town hall's
        # open floor, whose front steps down are stairs of their own)
        inn_ups = [p for p in pois.values() if p.up and min(math.dist((p[5], p[6]), pts[i]) for i in ups) <= 1]
        (icon,) = inn_ups
        assert str(icon[4]) == "Stairs up"
        x, y = icon[5], icon[6]
        # (not by the stop: the first flight's foot, 3.5 yd from the trainer, a floor under her; issue #842)
        assert math.dist((x, y), (2261.5, 231.0)) <= 3 and math.dist((x, y), (2259.0, 235.9)) > 3
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()
        G.Update()


def test_brill_inns_route_upstairs_climbs_the_stairs_not_the_landings_side(game):
    # (issue #842: the route from the square to the Mage trainer went from the ground floor's passage straight up the
    # side of the stair landing, 3 yd in 1.4 yd, and the QA walk stayed on the ground floor) it climbs from the first
    # flight's foot (about 2261.5, 231) and never rises more than a yard and a half a yard
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    try:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2300.0, 300.0")  # (in Brill's square)
        N.ResetCityTrack()
        N.SetStops(lua.eval("{ { x = 2259.0, y = 235.9, cont = 0, name = 'Brill Mage Trainer', z = 41.2 } }"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        r = N.route
        assert r and not r.noWay
        part = next(p for p in r.parts.values() if p.fz)  # (the walk with its points' floors)
        pts = [(part.pts[i], part.pts[i + 1]) for i in range(1, len(part.pts), 2)]
        fz = [part.fz[i + 1] for i in range(len(pts))]
        inside = [i for i in range(len(pts)) if fz[i] is not None and fz[i] > 1 and math.dist(pts[i], (2265, 240)) < 25]
        climb = next(i for i in inside if fz[i] > 36)  # (the first point up off the inn's ground floor, 34.5)
        foot = max(i for i in inside if i < climb and fz[i] <= 36)
        assert math.dist(pts[foot], (2261.5, 231.0)) <= 3, (pts[foot], fz[foot])
        for i, j in zip(inside, inside[1:]):
            if j == i + 1:
                d = math.dist(pts[i], pts[j])
                assert fz[j] - fz[i] <= max(1.0, 1.5 * d), (pts[i], fz[i], pts[j], fz[j])
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()
        G.Update()


@pytest.mark.parametrize("cont,start,place", [
    (0, (-9400.0, 60.0), (-9471.0, 33.4, 63.9)),  # (Goldshire's Mage trainer, upstairs in the inn)
    (0, (-5560.0, -480.0), (-5589.0, -530.3, 399.7)),  # (Kharanos's Priest trainer, in the inn)
    (1, (-2250.0, -330.0), (-2301.0, -439.9, -5.4)),  # (Bloodhoof Village's Shaman trainer, in the tent)
    (1, (300.0, -4700.0), (312.0, -4824.7, 9.7)),  # (Razor Hill's Warrior trainer, in the barracks)
])
def test_the_towns_insides_take_the_route_to_their_trainers(game, cont, start, place):
    # (indoor routes phase 5, 2026-10-06: Goldshire, Kharanos, Dolanaar, Bloodhoof Village, Razor Hill and the
    # Crossroads with Brill; agps indoors --check: 45 of 49 places) from out in town: in by a door (walked to the road
    # on the terrain), on the trainer's floor, to the trainer by its spur, not a walk across the rooms or the ceiling
    lua, ns = game
    R = ns.Router
    px, py, pz = place
    r = R.Route(cont, start[0], start[1], px, py, lua.table_from({"tz": pz}))
    assert r and not r.unconnected and r.fz
    n = len(r.pts) // 2
    assert abs(r.fz[n] - pz) <= 3.5  # (on its floor)
    last = 0.0
    i = n - 1
    while i >= 1 and r.kinds[i] == R.KIND_OFFROAD:
        last += math.hypot(r.pts[2 * i + 1] - r.pts[2 * i - 1], r.pts[2 * i + 2] - r.pts[2 * i])
        i -= 1
    assert last <= 8.0  # (to the trainer on the roads)


@pytest.mark.parametrize("cont,start,npc", [
    (0, (-10443.0, 972.0), (-10504.8, 1033.2, 95.8)),  # (Sentinel Hill: the scout up on the guard tower's top)
    (0, (-10568.0, -1194.0), (-10552.2, -1108.8, 31.5)),  # (Darkshire: on the town hall's dais, a piece of its own)
    (0, (236.0, -2112.0), (333.7, -2091.5, 131.6)),  # (Wildhammer Keep: upstairs in the barracks, four floors)
])
def test_buildings_with_npcs_upstairs_take_the_route_up_to_them(game, cont, start, npc):
    # (indoor routes phase 6, 2026-10-06: every building with an NPC upstairs or in a cellar, merged and pruned, no NPC
    # data in the roads) from the road outside, with the NPC's floor learned (Layers' NPC floors): in by a door, never
    # straight onto a road inside through the walls (Sentinel Hill's tower's top floor was taken 79 yd straight from
    # the road), up the stairs, on the NPC's floor, the last stretch within CHECK_NPC_LAST_YD (no road to the NPC)
    lua, ns = game
    R, N = ns.Router, ns.Nav
    px, py, pz = npc
    r = R.Route(cont, start[0], start[1], px, py, lua.table_from({"tz": pz}))
    assert r and not r.unconnected and r.fz
    n = len(r.pts) // 2
    pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
    assert abs(r.fz[n] - pz) <= 3.5  # (on its floor)
    last, i = 0.0, n - 1
    while i >= 1 and r.kinds[i] == R.KIND_OFFROAD:
        last += math.dist(pts[i - 1], pts[i])
        i -= 1
    assert last <= 12.0
    # (but for the last stretch, the legs off the roads end on the ground: in by a door, not onto a floor up there)
    b = N.InBuilding(cont, px, py)
    ground = min(b.floors.values())
    for k in range(1, i + 1):
        if r.kinds[k] == R.KIND_OFFROAD and r.kinds[k + 1] != R.KIND_OFFROAD:
            assert r.fz[k + 1] <= ground + 3.5, (pts[k], r.fz[k + 1])
    assert any(R.StairAt(cont, *pts[k], *pts[k + 1]) == 1 for k in range(n - 1))  # (up the stairs)


def test_darnassus_rogue_trainer_is_down_the_spiral_stairs(game):
    # (issue #33: a recorded walk, 2026-10-14) the Rogue Trainer in the Cenarion Enclave is on a floor under the
    # ground, and the spiral stairs walked down to him are the only way there: from the Enclave's road the route goes
    # down them (Data/Roads.lua's FloorTracks) and ends on his floor, not over him on the ground (the walk's ends were
    # joined onto the land's road 23 yd overhead: WithTracks' LandHeightOK), and down the whole spiral (its second turn,
    # over its first, was judged at the first's height and dropped: a step of 6 yd down through it)
    lua, ns = game
    R, L = ns.Router, ns.Layers
    x, y = lua.eval("function(L) local x, y = L.MapToWorld(1457, 0.370, 0.219) return { x, y } end")(L).values()
    tz, road = 1295.1, (10089.9, 2537.3)  # (Data/CityPlaces.lua: his NPC's height; the Enclave's road over him)
    # (city routing, on by default: the spiral walked, no hop from turn to turn without Expert jumper; Kooki3z
    # 2026-11-23, "walk the walkway")
    assert ns.settings.gps.cityGrid and not ns.Router.ExpertJumper()
    for back in (False, True):
        opts = {"z": tz} if back else {"tz": tz}
        a, b = ((x, y), road) if back else (road, (x, y))
        r = R.Route(1, *a, *b, lua.table_from(opts))
        assert r and not r.unconnected and r.fz
        n = len(r.pts) // 2
        pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
        fz = [r.fz[i] for i in range(1, n + 1)]
        assert abs(fz[-1 if not back else 0] - tz) <= 3.5, fz  # (on his floor)
        assert min(fz) >= tz - 3.5  # (no lower than his floor on the way)
        CG = ns.CityGrid  # (the grid's walk keeps a yard or two off the stairs road's line: its stairs too)
        stairs = sum(math.dist(pts[k], pts[k + 1]) for k in range(n - 1)
                     if R.StairAt(1, *pts[k], *pts[k + 1]) or CG.StairAt(1, *pts[k], *pts[k + 1], (fz[k] + fz[k + 1]) / 2))
        assert R.KIND_DROP not in [r.kinds[i] for i in range(1, n)]  # (walked, no hop from turn to turn)
        assert stairs >= 70, stairs  # (the spiral's two turns: 88 yd)
        steep = [(pts[k], fz[k], fz[k + 1]) for k in range(n - 1)
                 if abs(fz[k + 1] - fz[k]) > 2 * max(math.dist(pts[k], pts[k + 1]), 1.0)]
        assert not steep, steep  # (no drop or climb through a floor)


def test_ironforge_first_aid_trainer_is_up_the_recorded_stairs(game):
    # (issue #65: a recorded walk, #38) the First Aid trainer is up two flights from the ground floor, on a
    # landing (3.6 yd over the ground floor) and a floor out of Ironforge's grid. The walk's pieces snapped their ends
    # onto the piece before's far end and were lost, the landing was taken for the ground floor, and the landing's and
    # the trainer's floor's pieces were the land's roads up on the mountain, never a stop's down in the city: the
    # route ended on the ground floor under him. Up both flights now, and down them the other way
    lua, ns = game
    R, L = ns.Router, ns.Layers
    x, y = lua.eval("function(L) local x, y = L.MapToWorld(1455, 0.540, 0.571) return { x, y } end")(L).values()
    tz = 512.5  # (Data/CityPlaces.lua: his NPC's height)
    flights = ((-4864.6, -1138.9, -4868.9, -1141.6), (-4887.7, -1151.4, -4886.3, -1148.0))
    assert all(R.StairAt(0, *f) for f in flights)
    for frm in ((-4821.8, -1155.4), (-5100.0, -741.0)):  # (the Gryphon Master; outside the gate)
        for back in (False, True):
            opts = {"z": tz} if back else {"tz": tz}
            a, b = ((x, y), frm) if back else (frm, (x, y))
            r = R.Route(0, *a, *b, lua.table_from(opts))
            assert r and not r.unconnected and r.fz
            n = len(r.pts) // 2
            pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
            fz = [r.fz[i] for i in range(1, n + 1)]
            assert abs(fz[0 if back else -1] - tz) <= 3.5, fz  # (on his floor)
            stairs = sum(math.dist(pts[k], pts[k + 1]) for k in range(n - 1) if R.StairAt(0, *pts[k], *pts[k + 1]))
            assert stairs >= 20, (frm, back, stairs)  # (both flights: 24 yd)
            assert any(505 <= z <= 506.5 for z in fz), fz  # (over the landing)


def test_from_partway_down_darnassus_spiral_the_route_goes_on_down(game):
    # (issue #40, a QA run: it stood on the spiral's first turn, 1 to 2 yd in from the stairs' line) the
    # spiral is one road whose turns lie over each other: its nearest point was the turn under the player's, off their
    # floor, so the start left the stairs for the land's road by the top landing and climbed back up (157 yd, to 1329.8)
    lua, ns = game
    R = ns.Router
    tz, stop = 1295.1, (10083.8, 2546.8)
    assert ns.settings.gps.cityGrid  # (city routing: the spiral walked on down, as above)
    for x, y, z in ((10114.0, 2604.0, 1325.0), (10113.0, 2604.0, 1325.0), (10115.0, 2604.0, 1325.5),
                    (10121.0, 2601.0, 1328.0), (10117.1, 2604.8, 1325.9)):
        r = R.Route(1, x, y, *stop, lua.table_from({"z": z, "tz": tz}))
        assert r and not r.unconnected and r.fz
        n = len(r.pts) // 2
        pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
        fz = [r.fz[i] for i in range(1, n + 1) if r.fz[i] is not None]
        # (no climb back up; the grid's floor under the player a yard or two off theirs on the spiral's slope)
        assert max(fz) <= z + (2.5 if r.cityGrid else 1.5), ((x, y, z), max(fz))
        assert math.dist(pts[0], pts[1]) <= 3, ((x, y), pts[:3])  # (onto the stairs where the player is)
        length = sum(math.dist(pts[k], pts[k + 1]) for k in range(n - 1))
        assert length <= 140, ((x, y, z), length)  # (on down: 127 to 135 yd; back up first, 146 to 158)


def _followed_in_to_the_stairs(lua, ns, up=False):
    # (in by the inn's door from Brill's square, along the ground floor to the stairs, or up them: the floor followed)
    G, N, T = ns.GPS, ns.Nav, ns.Turns
    lua.execute("AGPS_POS[1], AGPS_POS[2] = 2235.0, 260.0")
    N.ResetCityTrack()
    N.SetStops(lua.eval("{ { x = 2259.0, y = 235.9, cont = 0, name = 'Brill Mage Trainer', z = 41.2 } }"), False, "red")
    G.Follow()
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    path = T.Path(N.route)
    ups = [m.dist for m in T.Maneuvers(path, "the trainer").values() if str(m.kind) == "stairs"]
    _walk(lua, ns, path, path.total - 4 if up else ups[0] - 3)
    return float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))


def test_standing_still_the_floor_isnt_searched_for_every_quarter_second(game):
    # (the 2026-10-07 idle profile: Router.HeightsNear ran every 0.25 s while the player stood still, over half of
    # all the addon's idle cost) with the player on the exact same spot, an established track keeps its height
    # without searching the roads again until TRACK_STILL_EVERY (so a road rebuilt under a still player is still
    # picked up within it); a step searches at once
    lua, ns = game
    N = ns.Nav
    real = ns.Router.HeightsNear
    try:
        x, y = _followed_in_to_the_stairs(lua, ns, up=True)  # (upstairs in Brill's inn: a track established)
        lua.execute("AGPS_T = AGPS_T + %f" % (N.TRACK_STILL_EVERY + 0.1,))
        z = N.TrackCityZ(0, x, y)  # (a real look just now: the skip window starts here)
        assert z > 38
        lua.execute("AGPS_HN = { n = 0 }")
        ns.Router.HeightsNear = lua.eval(
            "function(f) return function(...) AGPS_HN.n = AGPS_HN.n + 1 return f(...) end end")(real)
        for _ in range(4):  # (4 looks 0.3 s apart: each past TRACK_EVERY, all within TRACK_STILL_EVERY)
            lua.execute("AGPS_T = AGPS_T + 0.3")
            assert N.TrackCityZ(0, x, y) == z
        assert lua.eval("AGPS_HN.n") == 0
        lua.execute("AGPS_T = AGPS_T + %f" % (N.TRACK_STILL_EVERY + 0.1,))
        assert N.TrackCityZ(0, x, y) == z  # (the real look, in case the roads changed)
        assert lua.eval("AGPS_HN.n") == 1
        lua.execute("AGPS_T = AGPS_T + 0.3")
        assert N.TrackCityZ(0, x + 1.0, y) > 38  # (a step: searched at once, as before, still upstairs)
        assert lua.eval("AGPS_HN.n") == 2
    finally:
        ns.Router.HeightsNear = real
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()


def test_a_stop_by_a_place_upstairs_isnt_reached_under_it_with_no_height_of_its_own(game):
    # (the 1.1.5 test pass, v115-inn-c: "in the inn, set destination enchanting trainer, walked towards without going
    # upstairs says arrived") a stop made by a click on the map by Brill's Enchanting trainer, upstairs, has no height of
    # its own: the place's is taken (Nav.StopHeight), and on the ground floor, followed in by the door, it isn't reached
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    try:
        x, y = _followed_in_to_the_stairs(lua, ns)
        assert N.TrackCityZ(0, x, y) < 37  # (the ground floor)
        N.SetStops(lua.eval("{ { x = 2280.0, y = 244.7, cont = 0 } }"), False, "red")
        G.Update()
        assert N.StopFloor(N.dest) == 1 and N.StopHeight(N.dest) == 41.2
        for x, y in ((2274.0, 243.0), (2277.0, 244.0)):
            lua.execute("AGPS_POS[1], AGPS_POS[2] = %f, %f AGPS_T = AGPS_T + 0.3" % (x, y))
            N.Status(x, y, 0)
            assert N.dest is not None, (x, y)  # (under it: not there)
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()


def test_a_stop_by_a_place_upstairs_with_no_height_of_its_own_is_routed_up_to_it(game):
    # (the QA runner's offline dry run of v115-r-inn, 2026-10-07) that stop, made by a click on the map by Brill's
    # Enchanting trainer: its arrival took the place's height (Nav.StopHeight), but its route was worked out without it
    # (Nav.StopZ) and ended on the floor under the trainer, going down toward the cellar; the place's height for both
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    try:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2235.0, 260.0")
        N.ResetCityTrack()
        N.SetStops(lua.eval("{ { x = 2280.0, y = 244.7, cont = 0 } }"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert N.StopZ(N.dest) == 41.2
        part = N.route.parts[len(N.route.parts)]
        n = len(part.pts) // 2
        assert part.fz and abs(part.fz[n] - 41.2) < 1.5, part.fz[n]  # (on the trainer's floor, upstairs)
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()


def test_after_a_hearthstone_into_the_inn_the_innkeepers_floor_is_followed(game):
    # (the 1.1.5 test pass: no height from the game, and by the innkeeper the roads near are on every floor, so the floor
    # wasn't known in there till the player walked out a door) a hearthstone lands on the innkeeper's floor (the bind
    # point): followed from there (Nav.Hearthed, from Teleports.lua's hearth). And a jump since the last look (a
    # teleport): followed again from scratch, not on with the old floor
    lua, ns = game
    N = ns.Nav
    try:
        N.ResetCityTrack()
        lua.execute("AGPS_T = AGPS_T + 10")
        assert N.TrackCityZ(0, 2266.0, 241.0) is None  # (by the innkeeper: no telling)
        N.Hearthed(0, 2266.0, 241.0)
        lua.execute("AGPS_T = AGPS_T + 1")
        assert abs(N.TrackCityZ(0, 2266.0, 241.0) - 34.5) < 1  # (Brill Inn's place: the innkeeper's floor)
        # (followed up the inn's stairs, then 50 yd off at once, in the town hall: its floor, not upstairs' carried on)
        x, y = _followed_in_to_the_stairs(lua, ns, up=True)
        assert N.TrackCityZ(0, x, y) > 38
        lua.execute("AGPS_T = AGPS_T + 0.3")
        assert abs(N.TrackCityZ(0, 2302.0, 284.0) - 36.5) < 1
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()


def test_from_upstairs_a_stop_on_the_ground_floor_is_down_the_stairs(game):
    # (the 1.1.5 test pass, v115-inn-a: "from upstairs navigating to first aid trainer downstairs still says to go up
    # stairs") followed up in Brill's inn, a route to its First Aid trainer on the ground floor goes down the stairs, not
    # straight down through the floor (RouteOne's offFloor), and says so: "Take the stairs down", the map's icon
    # "Stairs down" (a flight up or down as the route's floors go across it, not as its first piece reads on the map)
    lua, ns = game
    G, N, T = ns.GPS, ns.Nav, ns.Turns
    try:
        x, y = _followed_in_to_the_stairs(lua, ns, up=True)
        assert N.TrackCityZ(0, x, y) > 38
        N.SetStops(lua.eval("{ { x = 2247.0, y = 242.8, cont = 0, name = 'Brill First Aid Trainer', z = 34.3 } }"),
                   False, "red")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        r = N.route
        fz = [f for p in r.parts.values() for f in (p.fz.values() if p.fz else []) if f]
        assert fz and max(fz) > 40 and min(fz) < 36  # (down the stairs on the roads)
        stairs = [m for m in T.Maneuvers(T.Path(r), "the trainer").values() if str(m.kind) == "stairs"]
        assert stairs and all(str(m.text) == "Take the stairs down" for m in stairs)
        pois = lua.eval("{}")
        assert G.AddRouteStairs(pois, r, 0, x, y, 0, 3.0, 300) >= 1
        assert {str(p[4]) for p in pois.values()} == {"Stairs down"}
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()


def test_the_building_the_player_is_in_is_found_by_its_grid_cell(game):
    # (Nav.InBuilding, the floor tracker's check on a continent: by a grid of BUILDING_CELL yards, as every building
    # is meant to have its inside: the same answer as looking at them all, near a cell's edge and either side of 0)
    lua, ns = game
    N = ns.Nav
    saved = ns.Indoors[0]
    try:
        lua.execute("""
          AGPS_NS.Indoors[0] = { { "A", x = 2267, y = 241, r = 32 }, { "B", x = -100, y = -63, r = 6 },
            { "C", x = 63, y = 1, r = 2 } }
        """)
        def scan(x, y):
            for b in ns.Indoors[0].values():
                r = b.r + N.TRACK_YD
                if abs(b.x - x) <= r and abs(b.y - y) <= r:
                    return str(b[1])
            return None
        spots = [(2259, 236), (2267 + 32 + N.TRACK_YD, 241), (2267 + 33 + N.TRACK_YD, 241), (-100, -63), (-91, -70),
                 (-100 - 6 - N.TRACK_YD - 0.5, -63), (64, 0), (61.5, 0.5), (0, 0), (5000, -5000)]
        for x, y in spots:
            b = N.InBuilding(0, x, y)
            assert (str(b[1]) if b else None) == scan(x, y), (x, y)
        assert str(N.InBuilding(0, 2259, 236)[1]) == "A" and N.InBuilding(0, 0, 0) is None
    finally:
        ns.Indoors[0] = saved


def test_two_upstairs_stops_the_hint_goes_once_the_player_is_followed_up(game):
    # (asked 2026-10-06, Brill: "if I select 2 locations upstairs and go upstairs once on the same level the indicator to
    # go up stairs should go away") on the ground floor, "(upstairs)" and the hint show and the stop isn't reached under
    # it; once followed up the stairs (Nav.TrackCityZ along the inn's roads: no height from the game), both stops'
    # hints are gone. A /reload upstairs takes the floor up again (Nav.SaveTrack), elsewhere not
    lua, ns = game
    G, N, T = ns.GPS, ns.Nav, ns.Turns
    order = ns.settings.gps.fastestOrder
    # (in the inn's rooms the game says indoors: outdoors, the floor followed is let go away from its roads,
    # Nav.OutsideFloor)
    lua.execute("AGPS_IN_REAL = IsIndoors IsIndoors = function() return true end")
    try:
        ns.settings.gps.fastestOrder = False
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2235.0, 260.0")
        N.ResetCityTrack()
        N.SetStops(lua.eval("{ { x = 2259.0, y = 235.9, cont = 0, name = 'Brill Mage Trainer', z = 41.2 }, "
                            "{ x = 2264.0, y = 248.2, cont = 0, name = 'Brill Priest Trainer', z = 41.2 } }"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        path = T.Path(N.route)
        steps = N.StepsText(5)
        assert "Brill Mage Trainer (upstairs)" in steps and "Brill Priest Trainer (upstairs)" in steps
        ups = [m.dist for m in T.Maneuvers(path, "the trainer").values() if str(m.kind) == "stairs"]
        assert ups
        _walk(lua, ns, path, ups[0] - 2)  # (in by the door, along the ground floor to the stairs)
        z = N.TrackCityZ(0, float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]")))
        assert z is not None and z < 37  # (the ground floor)
        mage = N.dest
        assert str(mage.name) == "Brill Mage Trainer" and N.StopFloor(mage) == 1
        assert "Upstairs: Brill Mage Trainer" in N.Status(float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]")), 0)
        # (right under the trainer, on the ground floor: not arrived)
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2260.0, 237.0 AGPS_T = AGPS_T + 0.3")
        N.Status(2260.0, 237.0, 0)
        assert str(N.dest.name) == "Brill Mage Trainer"
        # up the stairs: on their floor, no hint for either
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        path = T.Path(N.route)
        _walk(lua, ns, path, path.total - 4)
        z = N.TrackCityZ(0, float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]")))
        assert z is not None and z > 38  # (followed up)
        for d in N.stops.values():
            assert N.StopFloor(d) is None, str(d.name)
        assert "(upstairs)" not in N.StepsText(5)
        # a /reload up here: the floor taken up again where the player was, not elsewhere (the roads there alone can't
        # tell: the floors over each other)
        def up_again():
            # (followed up again: in by the door and up the stairs, the same walk, the same spot; the roads near the
            # trainer are on both floors, so only a walk from the door knows it's up there)
            return _followed_in_to_the_stairs(lua, ns, up=True)
        x, y = up_again()
        N.ResetCityTrack()
        lua.execute("AGPS_T = AGPS_T + 10")
        assert N.TrackCityZ(0, x, y) is None  # (no save: no floor)
        assert up_again() == (x, y)
        N.SaveTrack()
        N.ResetCityTrack()
        lua.execute("AGPS_T = AGPS_T + 10")
        assert N.TrackCityZ(0, x, y) > 38  # (upstairs again)
        assert ns.CharDB().floorTrack is None  # (taken once)
        up_again()
        N.SaveTrack()
        N.ResetCityTrack()
        lua.execute("AGPS_T = AGPS_T + 10")
        assert N.TrackCityZ(0, x - 6, y) is None  # (elsewhere: not taken up)
    finally:
        lua.execute("IsIndoors = AGPS_IN_REAL")
        ns.settings.gps.fastestOrder = order
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()
        N.ResetCityTrack()
        G.Update()



def test_the_api_gives_the_players_level_and_the_shown_city_level(game):
    # (API 16, asked 2026-10-07 by StreetView: its Undercity street views are filed under level 10001, but
    # PlayerWorld gives continent 0 under the city and CursorWorld the view's continent) PlayerLevel() is the level
    # the player is on; ShownLevel() the underground city level whose art the map shows, else nil
    lua, ns = game
    A, G, N = lua.globals().AzerothGPS, ns.GPS, ns.Nav
    assert A.version >= 16
    try:
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()
        G.Update()
        assert A.PlayerLevel() == 0 and A.ShownLevel() is None  # (on the surface)
        lua.execute("""
          AGPS_API_UC = { best = C_Map.GetBestMapForUnit, sub = GetSubZoneText, mini = GetMinimapZoneText }
          C_Map.GetBestMapForUnit = function() return 1458 end
          GetSubZoneText = function() return 'Trade Quarter' end
          GetMinimapZoneText = function() return 'Trade Quarter' end
          AGPS_POS[1], AGPS_POS[2] = 1570.0, 270.0 AGPS_T = AGPS_T + 1
        """)
        G.Follow()
        G.Update()
        assert A.PlayerLevel() == 10001  # (down in the city)
        assert A.ShownLevel() == 10001  # (its art on the map)
        assert A.PlayerWorld() is not None  # (still the game's own continent coordinates)
    finally:
        lua.execute("""
          C_Map.GetBestMapForUnit, GetSubZoneText, GetMinimapZoneText = AGPS_API_UC.best, AGPS_API_UC.sub, AGPS_API_UC.mini
          AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1
        """)
        N.Clear()
        G.Follow()
        G.Update()

def test_down_in_undercity_a_stop_on_the_walkway_overhead_isnt_reached_from_the_ring(game):
    # (indoor routes phase 2, 2026-10-06) the player followed along the ring (-60) to under Grimsford's walkway (-43):
    # within the arrival distance in 2D, but not arrived (17 yd below: the floors' heights, as the hint's "above you");
    # and the route isn't trimmed to its last yards up on the walkway: its stairs are still ahead
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      AGPS_UC = { best = C_Map.GetBestMapForUnit, sub = GetSubZoneText, mini = GetMinimapZoneText }
      C_Map.GetBestMapForUnit = function() return 1458 end
      GetSubZoneText = function() return 'Trade Quarter' end
      GetMinimapZoneText = function() return 'Trade Quarter' end
    """)

    def at(x, y):
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x}, {y} AGPS_T = AGPS_T + 0.3")
        return N.TrackCityZ(10001, x, y)

    def walk(route):
        pts = [route.parts[1].pts[i] for i in range(1, len(route.parts[1].pts) + 1)]
        path = list(zip(pts[0::2], pts[1::2]))
        for (ax, ay), (bx, by) in zip(path, path[1:]):
            n = max(1, int(math.hypot(bx - ax, by - ay) / 2))
            for k in range(1, n + 1):
                at(ax + (bx - ax) * k / n, ay + (by - ay) * k / n)

    try:
        N.ResetCityTrack()
        lua.execute("AGPS_T = (AGPS_T or 0) + 10")
        at(1594.9, 290.8)  # (off a lift: the floor known)
        N.SetStops(lua.eval("{ { x = 1595.3, y = 224.7, cont = 10001, z = -62.0, name = 'Jeremiah Payson' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 0.3")
        walk(N.Route(1594.9, 290.8, 0))  # (down to the ring)
        N.SetStops(lua.eval("{ { x = 1570.0, y = 270.0, cont = 10001, z = -60.0, name = 'Under the walkway' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 0.3")
        walk(N.Route(1595.3, 224.7, 0))  # (along the ring)
        z = at(1570.0, 270.0)
        assert z is not None and z < -55  # (on the ring)
        N.SetStops(lua.eval("{ { x = 1572.6, y = 272.7, cont = 10001, z = -43.0, name = 'Grimsford' } }"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 0.3")
        G.Update()
        N.Status(1570.0, 270.0, 0)
        assert N.dest is not None and str(N.dest.name) == "Grimsford"  # (not arrived: 17 yd below)
        part = N.route.parts[1]
        assert part.zs and len(G.FloorChanges(part.pts, part.zs)) >= 1  # (the stairs up still ahead)
    finally:
        lua.execute("""
          C_Map.GetBestMapForUnit, GetSubZoneText, GetMinimapZoneText = AGPS_UC.best, AGPS_UC.sub, AGPS_UC.mini
          AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0
        """)
        N.ResetCityTrack()
        N.Clear()


def test_in_orgrimmar_a_stop_down_in_the_cleft_isnt_reached_from_the_drag_over_it(game):
    # (indoor routes phase 3, 2026-10-06) in a capital's own cells the player's floor is followed along its roads (their
    # floors, nz), started where the roads near are all one floor; on the Drag (about 28) over a trainer down in the
    # Cleft of Shadow (3): not arrived, and the hint says how far below
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("AGPS_MAP_REAL = AGPS_MAP AGPS_MAP = 1454")

    def at(x, y):
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 1 AGPS_T = AGPS_T + 0.3")
        return N.TrackCityZ(1, x, y)

    def walk(route):
        pts = [route.parts[1].pts[i] for i in range(1, len(route.parts[1].pts) + 1)]
        path = list(zip(pts[0::2], pts[1::2]))
        for (ax, ay), (bx, by) in zip(path, path[1:]):
            n = max(1, int(math.hypot(bx - ax, by - ay) / 2))
            for k in range(1, n + 1):
                at(ax + (bx - ax) * k / n, ay + (by - ay) * k / n)

    try:
        N.ResetCityTrack()
        lua.execute("AGPS_T = (AGPS_T or 0) + 10")
        z0 = at(1660.0, -4294.0)
        assert z0 is not None and 20 < z0 < 32  # (started: the roads near all on one floor, the Drag's)
        N.SetStops(lua.eval("{ { x = 1672.0, y = -4302.0, cont = 1, z = 26.2, name = 'On the Drag' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 0.3")
        walk(N.Route(1660.0, -4294.0, 1))
        z = at(1672.0, -4302.0)
        assert z is not None and z > 20  # (still on the Drag)
        N.SetStops(lua.eval("{ { x = 1672.0, y = -4302.0, cont = 1, z = 3.0, name = 'Down in the Cleft' } }"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 0.3")
        G.Update()
        N.Status(1672.0, -4302.0, 1)
        assert N.dest is not None and str(N.dest.name) == "Down in the Cleft"  # (not arrived: over it)
        assert "Below you" in str(N.HeightText(1672.0, -4302.0, 1))
    finally:
        lua.execute("AGPS_MAP = AGPS_MAP_REAL AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")
        N.ResetCityTrack()
        N.Clear()


def test_undercity_routes_show_their_stairs(game):
    # (asked 2026-10-06: a multi-floor plan for Undercity with stair indicators) down in Undercity, the route's next
    # floor changes get a stairs icon, up or down, on its map, as a dungeon's do
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      AGPS_UC = { best = C_Map.GetBestMapForUnit, sub = GetSubZoneText, mini = GetMinimapZoneText }
      C_Map.GetBestMapForUnit = function() return 1458 end
      GetSubZoneText = function() return 'Trade Quarter' end
      GetMinimapZoneText = function() return 'Trade Quarter' end
    """)
    try:
        # (Jeremiah Payson, the Trade Quarter; the clock on: the player's level is read again, not an earlier test's)
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 1595.3, 224.7 AGPS_T = (AGPS_T or 0) + 5")
        # Master Apothecary Faranell, down in the Apothecarium
        N.SetStops(lua.eval("{ { x = 1434.5, y = 404.9, cont = 10001, z = -85.2, name = 'Faranell' } }"), False, "red")
        G.Follow()
        G.Redraw()
        G.Update()
        r = N.route
        assert r and r.parts[1].cont == 10001 and r.parts[1].zs
        changes = G.FloorChanges(r.parts[1].pts, r.parts[1].zs)
        assert len(changes) >= 1
        st = ns.settings.gps
        zoom = st.zoom
        st.zoom = 600  # (out enough to see them)
        G.Redraw()
        G.Update()
        icons = [w for w in lua.eval("AGPS_WIDGETS").values()
                 if w._kind == "Button" and w._shown and w.name in ("Stairs up", "Stairs down")]
        assert icons
        st.zoom = zoom
    finally:
        lua.execute("""
          C_Map.GetBestMapForUnit, GetSubZoneText, GetMinimapZoneText = AGPS_UC.best, AGPS_UC.sub, AGPS_UC.mini
          AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0
        """)
        N.Clear()
        G.Update()


def test_the_players_floor_down_in_undercity_is_followed_along_its_roads(game):
    # (asked 2026-10-06: better ways to know the player's height; WoW Forever gives none) down in Undercity the floor is
    # followed along the roads: it starts at a lift's bottom when the player is there (else by the zone text's rooms,
    # else the nearest road), keeps to the road at about the last height (a walkway overhead isn't the player's
    # floor), and changes on the stairs; a route then starts on the player's floor
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      AGPS_UC = { best = C_Map.GetBestMapForUnit, sub = GetSubZoneText, mini = GetMinimapZoneText }
      C_Map.GetBestMapForUnit = function() return 1458 end
      GetSubZoneText = function() return 'Trade Quarter' end
      GetMinimapZoneText = function() return 'Trade Quarter' end
    """)

    def at(x, y):
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x}, {y} AGPS_T = AGPS_T + 0.3")
        return N.TrackCityZ(10001, x, y)

    try:
        N.ResetCityTrack()
        lua.execute("AGPS_T = (AGPS_T or 0) + 10")
        # off a lift (Undercity's lifts' bottoms, -41.5): that's the floor
        assert at(1594.9, 290.8) == pytest.approx(-41.5)
        # started where floors lie over each other (Jeremiah Payson's spot on the ring, a walkway near): not guessed
        N.ResetCityTrack()
        assert at(1595.3, 224.7) is None

        def walk(route):
            pts = [route.parts[1].pts[i] for i in range(1, len(route.parts[1].pts) + 1)]
            path = list(zip(pts[0::2], pts[1::2]))
            seen = []
            for (ax, ay), (bx, by) in zip(path, path[1:]):
                n = max(1, int(math.hypot(bx - ax, by - ay) / 2))
                for k in range(1, n + 1):
                    seen.append(at(ax + (bx - ax) * k / n, ay + (by - ay) * k / n))
            return seen

        # off the lift, walked down to Jeremiah on the ring (-62): followed down the stairs
        N.ResetCityTrack()
        at(1594.9, 290.8)
        N.SetStops(lua.eval("{ { x = 1595.3, y = 224.7, cont = 10001, z = -62.0, name = 'Jeremiah Payson' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 0.3")
        z = walk(N.Route(1594.9, 290.8, 0))[-1]
        assert z == pytest.approx(-62.0, abs=4)
        # a route from there to an NPC on the same ring: no floor to change
        N.SetStops(lua.eval("{ { x = 1696.7, y = 189.6, cont = 10001, z = -62.2, name = 'Mara Rennick' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 0.3")  # (not 5 s: the followed floor would go stale)
        r = N.Route(1595.3, 224.7, 0)
        assert r and r.parts[1].zs
        assert len(G.FloorChanges(r.parts[1].pts, r.parts[1].zs)) == 0
        # walked there round the ring, under walkways: the floor stays the ring's all the way
        seen = walk(r)
        assert min(seen) > -67 and max(seen) < -57
        # and back to Jeremiah, then on up to the walkway
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 1595.3, 224.7 AGPS_T = AGPS_T + 0.3")
        N.SetStops(lua.eval("{ { x = 1595.3, y = 224.7, cont = 10001, z = -62.0, name = 'Jeremiah Payson' } }"), False, "red")
        walk(N.Route(1696.7, 189.6, 0))
        # walked to Senior Sergeant Grimsford, up on the walkway (-43): followed up the stairs, along the route
        N.SetStops(lua.eval("{ { x = 1572.6, y = 272.7, cont = 10001, z = -43.0, name = 'Grimsford' } }"), False, "red")
        lua.execute("AGPS_T = AGPS_T + 0.3")  # (not 5 s: the followed floor would go stale)
        r = N.Route(1595.3, 224.7, 0)
        assert walk(r)[-1] == pytest.approx(-43.0, abs=3)
    finally:
        lua.execute("""
          C_Map.GetBestMapForUnit, GetSubZoneText, GetMinimapZoneText = AGPS_UC.best, AGPS_UC.sub, AGPS_UC.mini
          AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0
        """)
        N.ResetCityTrack()
        N.Clear()
        G.Update()


def test_the_tomb_under_shadowvale_is_a_cave(game):
    # (asked 2026-10-06: "tomb under Shadowvale (new area) needs road data and a cave entrance marker") WoW Forever's
    # tomb, Arathi's "Master's Cellar" placed in the Whispering Forest (caves.CAVE_PLACEMENTS): a cave of its own,
    # one entrance marker where the user's pin was, and a route to its far end goes in by it
    lua, ns = game
    G, N, R, P = ns.GPS, ns.Nav, ns.Router, ns.Passability
    near = [e for e in G.CaveEntrances(0).values() if math.hypot(e.x - 1857.4, e.y - 2453.9) < 60]
    assert [e.name for e in near] == ["Shadowvale Tomb"]
    way = (near[0].x, near[0].y)
    x0, x1, y0, y1 = P.GridBounds("cave68463626")
    edges, g = R.Edges(0)
    far = max(((math.hypot(edges[i][k] - way[0], edges[i][k + 1] - way[1]), edges[i][k], edges[i][k + 1])
               for i in range(1, len(edges) + 1) if g.cave[i]
               for k in range(5, len(edges[i]) + 1, 2) if x0 <= edges[i][k] <= x1 and y0 <= edges[i][k + 1] <= y1))
    assert far[0] > 150  # (deep in: its far end)
    try:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2060.0, 2125.0 AGPS_T = (AGPS_T or 0) + 10")
        N.SetStops(lua.eval(f"{{ {{ x = {far[1]}, y = {far[2]}, cont = 0, name = 'deep' }} }}"), False, "red")
        r = N.Route(2060.0, 2125.0, 0)
        path = [(r.pts[i], r.pts[i + 1]) for i in range(1, len(r.pts), 2)]
        assert min(math.hypot(x - way[0], y - way[1]) for x, y in path) < 15  # (in by its way in)
    finally:
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")
        N.Clear()


def _cave_key(ns, name, cont=0):
    caves = ns.Caves[cont]
    for i in range(1, len(caves) + 1):
        if caves[i][1] == name:
            return caves[i][2], caves[i]
    raise AssertionError(name)


def test_a_caves_map_opens_from_its_icon_like_a_dungeons_and_right_click_goes_back(game):
    # (asked 2026-10-06: "if a cave map exists I want to be able to left click and see it like how instances work,
    # right click to exit back to previous map") the client has no cave maps of their own (no uiMaps): a cave's map is
    # its models' minimap art, as a dungeon's; one cave of several models is one map
    lua, ns = game
    G = ns.GPS
    key, row = _cave_key(ns, "Dreadmaul Rock")
    art = G.CaveArt(0, key)
    assert art and len(art.list) == 3 and str(art.name) == "Dreadmaul Rock"
    w = row[5]  # (its ways in)
    try:
        G.ApplyView(lua.eval(f"{{ x = {w[1]}, y = {w[2]}, cont = 0, rot = 0, cross = true, zoom = 250 }}"))
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        icons = _shown(lua, lambda b: b.cave is not None)
        assert icons and "Click: show its map" in str(icons[0].note)
        icons[0]._scripts.OnClick(icons[0], "LeftButton")
        free = G.BrowseState()[1]
        assert free.cave and G.CaveArt(0, free.cave).key == art.key  # (lupa's proxies: compare a field)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        G.UpdateInfo()
        assert str(G.infoName) == "Dreadmaul Rock"  # (its name in the title)
        if len(G.InstanceFloors(art)) >= 2:  # (its floors stepped as a dungeon's)
            assert G.FloorStep(False)
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        # kept over a /reload
        saved = G.SaveView()
        assert saved.cave == free.cave
        # dragged, still its map (G.Update's drag keeps it)
        # right-click: back to the view it was opened from
        G.TerrainZoomOut()
        back = G.BrowseState()[1]
        assert not back.cave and (back.x, back.y) == pytest.approx((w[1], w[2]))
        G.ApplyView(saved)
        assert G.BrowseState()[1].cave == free.cave
    finally:
        G.Follow()


def test_a_cave_without_art_has_no_map_to_open(game):
    # (an animal's den: no minimap art in the client and too small for a map from its cells, its floor the land's
    # (item 115, Data/AutoMaps.lua): nothing changes there)
    lua, ns = game
    G = ns.GPS
    caves = ns.Caves[1]
    den = next(caves[i] for i in range(1, len(caves) + 1) if G.CaveArt(1, caves[i][2]) is None)
    before = G.BrowseState()[1]
    assert G.ShowCave(1, den[2]) is False and G.BrowseState()[1] == before


def test_a_click_on_a_cave_opens_its_map_unless_its_a_double_click(game):
    lua, ns = game
    G = ns.GPS
    frame = lua.globals().AzerothGPSFrame
    key, _row = _cave_key(ns, "Dreadmaul Rock")
    art = G.CaveArt(0, key)
    spot = next(((x, y) for x, y in ((art.x0 + (art.x1 - art.x0) * i / 40, art.y0 + (art.y1 - art.y0) * j / 40)
                                    for i in range(41) for j in range(41))
                 if G.CaveAt(0, x, y) is not None and G.CaveArt(0, G.CaveAt(0, x, y)).key == art.key), None)
    assert spot  # (a spot on the cave's own cells)
    lua.execute("AGPS_OLD_AFTER, AGPS_OLD_CUR = C_Timer.After, GetCursorPosition AGPS_TIMERS = {} "
                "C_Timer.After = function(_, f) AGPS_TIMERS[#AGPS_TIMERS + 1] = f end "
                "GetCursorPosition = function() return 300, 300 end")  # (the stand-in canvas's middle)

    def run_timers():
        lua.execute("for _, f in ipairs(AGPS_TIMERS) do f() end AGPS_TIMERS = {}")

    def click():
        frame._scripts.OnMouseDown(frame, "LeftButton")
        frame._scripts.OnMouseUp(frame, "LeftButton")

    try:
        G.ApplyView(lua.eval(f"{{ x = {spot[0]}, y = {spot[1]}, cont = 0, rot = 0, cross = true, zoom = 200 }}"))
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        click()
        click()  # (a double-click: a stop there, not the map)
        run_timers()
        assert not G.BrowseState()[1].cave
        G.RemovePending(1)
        G.Follow()  # (the map back on the player: removing the last stop leaves it where it is since 1.3.5)
        G.ApplyView(lua.eval(f"{{ x = {spot[0]}, y = {spot[1]}, cont = 0, rot = 0, cross = true, zoom = 200 }}"))
        lua.execute("AGPS_T = AGPS_T + 5")
        G.Update()
        click()  # (one click: the map, once it's clear no second came)
        assert not G.BrowseState()[1].cave
        run_timers()
        assert G.CaveArt(0, G.BrowseState()[1].cave).key == art.key
    finally:
        lua.execute("C_Timer.After, GetCursorPosition = AGPS_OLD_AFTER, AGPS_OLD_CUR")
        G.Follow()


def test_the_simulated_players_underground_switch_reaches_the_map(game):
    # (the dev tools' simulated player in a cave: `indoors` on the override is what the map goes by too, Nav.Indoors,
    # so the cave's inside map shows as it would for a player down in it)
    lua, ns = game
    G, Geo = ns.GPS, ns.Geo
    key, row = _cave_key(ns, "Dreadmaul Rock")
    p = G.InteriorAt(0, row[3], row[4])
    zoom = ns.settings.gps.zoom
    try:
        ns.settings.gps.zoom = G.INTERIOR_MAX_ZOOM + 200  # (zoomed out: an inside map only when indoors)
        for indoors in (False, True):
            Geo.SetOverride(lua.eval(f"{{ x = {p[2]}, y = {p[3]}, cont = 0, indoors = {str(indoors).lower()} }}"))
            assert ns.Nav.Indoors() is indoors
            G.Follow()
            ns.settings.gps.zoom = G.INTERIOR_MAX_ZOOM + 200
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
            assert (G.inside is not None) is indoors, (indoors, G.inside)  # (the game itself says outdoors)
    finally:
        ns.settings.gps.zoom = zoom
        Geo.SetOverride(None)
        G.Follow()


def test_a_route_with_no_height_doesnt_climb_onto_a_tents_roof(game):
    # (2026-10-06) a tent's canvas is walkable and reached up its side, so the insides' build made roads on it: a route
    # to Bloodhoof's Hunter trainer with no height (a quest stop, an NPC talked to) went up onto the hut's roof, 8.7 yd
    # over the ground. Roads on a roof (raised over the ground, nothing of the model over them) are left out, but for
    # the ways to a place (indoors.py: Razor Hill's Rogue trainer on the troll burrow's terrace)
    lua, ns = game
    R = ns.Router
    from azerothgps import indoors as D

    _n, px, py, pz = next(q for q in D.town_places(1) if q[0] == "Bloodhoof Village Hunter Trainer")
    try:
        R.Reset()
        r = R.Route(1, px + 80.0, py + 60.0, px, py, lua.table_from({}))
        fz = [r.fz[k] for k in range(1, len(r.pts) // 2 + 1)] if r.fz else []
        assert not fz or max(fz) < pz + 3, max(fz)
    finally:
        R.Reset()


def test_an_npc_talked_to_upstairs_is_routed_to_on_its_floor(game):
    # (asked 2026-10-06, "learn NPC floors": the game never gives the player's height, so an NPC talked to had no floor,
    # and a route to one upstairs could end on the ground floor under them) talked to while followed up the inn's stairs
    # (Nav.FollowedZ), the NPC keeps that floor, and its quests (the gossip's lists); the search's stop and the quest
    # route's stops for its quests (Layers.QuestNpcZ) go to that floor. Learned only, never shipped
    lua, ns = game
    G, N, L, T = ns.GPS, ns.Nav, ns.Layers, ns.Turns
    order = ns.settings.gps.fastestOrder
    lua.execute("""
      AGPS_NPC = { guid = nil, name = nil, title = nil, opts = {} }
      AGPS_REAL_UNIT = { guid = UnitGUID, name = UnitName, tip = C_TooltipInfo, gossip = C_GossipInfo.GetOptions,
        active = C_GossipInfo.GetActiveQuests }
      UnitGUID = function(u) if u == "npc" then return AGPS_NPC.guid end return AGPS_REAL_UNIT.guid(u) end
      UnitName = function(u) if u == "npc" then return AGPS_NPC.name end return AGPS_REAL_UNIT.name(u) end
      C_TooltipInfo = { GetUnit = function() return { lines = { { leftText = AGPS_NPC.name }, { leftText = AGPS_NPC.title } } } end }
      C_GossipInfo.GetOptions = function() return AGPS_NPC.opts end
      C_GossipInfo.GetActiveQuests = function() return { { questID = 1234, title = 'Return to the Mage' } } end
      function AGPS_TALK(event, id, name, title, opts)
        AGPS_NPC.guid = string.format("Creature-0-1-2-3-%d-00000ABC", id)
        AGPS_NPC.name, AGPS_NPC.title, AGPS_NPC.opts = name, title, opts or {}
        AGPS_NS.Layers.frame._scripts.OnEvent(AGPS_NS.Layers.frame, event)
      end
    """)
    try:
        ns.settings.gps.fastestOrder = False
        ns.db.npcs = None
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2235.0, 260.0")
        N.ResetCityTrack()
        N.SetStops(lua.eval("{ { x = 2259.0, y = 235.9, cont = 0, name = 'Brill Mage Trainer', z = 41.2 } }"), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        path = T.Path(N.route)
        _walk(lua, ns, path, path.total - 4)  # (in by the door, up the stairs, to the trainer)
        x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
        assert N.TrackCityZ(0, x, y) > 38
        lua.execute("AGPS_TALK('GOSSIP_SHOW', 2128, 'Cain Firesong', '<Mage Trainer>', { { name = 'I seek training.' } })")
        n = ns.db.npcs[2128]  # (his creature id: the shipped NPC's, 2026-11-14)
        assert n.z is not None and n.z > 38 and n.quests[1234]
        assert L.QuestNpcZ(1234, 0, n.x + 5, n.y) == n.z and L.QuestNpcZ(1234, 0, n.x + 60, n.y) is None
        # back outside: the search's stop for them goes up the stairs to their floor
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2235.0, 260.0 AGPS_T = AGPS_T + 30")
        N.ResetCityTrack()
        (e,) = [h for h in G.SearchPlaces("cain", 8).values() if h.npc and h.name == "Cain Firesong"]  # (once: the shipped
        # NPC and the one talked to are the same, 2026-11-14; Undercity's Auctioneer Cain too)
        assert e.z == n.z
        N.SetStops(lua.eval(f"{{ {{ x = {e.x}, y = {e.y}, cont = {e.cont}, name = 'Cain Firesong', z = {e.z} }} }}"),
                   False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        part = N.route.parts[1]
        fz = [part.fz[k] for k in range(1, len(part.pts) // 2 + 1)] if part.fz else []
        floors = [f for f in fz if f]  # (the last yards off the roads, to the spot: no floor of their own)
        assert floors and floors[-1] > 38  # (the route ends upstairs, by them)
    finally:
        lua.execute("""
          UnitGUID, UnitName, C_TooltipInfo = AGPS_REAL_UNIT.guid, AGPS_REAL_UNIT.name, AGPS_REAL_UNIT.tip
          C_GossipInfo.GetOptions, C_GossipInfo.GetActiveQuests = AGPS_REAL_UNIT.gossip, AGPS_REAL_UNIT.active
          AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0
        """)
        ns.settings.gps.fastestOrder = order
        ns.db.npcs = None
        N.Clear()
        N.ResetCityTrack()
        ns.ResetUnsaved()
        G.Update()


def test_dolanaar_to_ruttheran_takes_darnassus_s_teleporter_down(game):
    # (asked 2026-10-07, for 1.1.5: the portal between Darnassus and Rut'theran Village, "treated like a lift") from
    # Dolanaar, the walk down the tree is no way (weighed as blocked): the route walks to the teleporter in Darnassus
    # and takes it down, and the steps and the arrow window say "Take" (no boat to board)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    fac = ns.CharDB().faction
    ns.CharDB().faction = "Alliance"  # (by Darnassus's guards: the Alliance's)
    try:
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 9850.0, 950.0, 1")
        N.SetStops(lua.eval("{ { x = 8605.0, y = 1000.0, cont = 1, name = [[Rut'theran Village]] } }"), False, "red")
        G.Follow()
        for _ in range(20):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        steps = str(N.StepsText(6))  # (city routing, on by default: a swim across Darnassus's pond on the way)
        assert "to the teleporter (The Temple Gardens, Darnassus)" in steps
        assert "Take the teleporter to Rut'theran Village, Teldrassil" in steps
        assert N.route.rideSeconds == 5
        # (at the teleporter: the arrow window's head line)
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 9945.0, 2625.0 AGPS_T = AGPS_T + 1")
        G.Update()
        assert "Take the teleporter to Rut'theran Village, Teldrassil" in str(N.Status(9945.0, 2625.0, 1))
    finally:
        ns.CharDB().faction = fac
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_from_dolanaar_the_boat_at_ruttheran_is_reached_by_the_teleporter(game):
    # (reported 2026-10-07, 1.1.5, with a screenshot: "still no guide to portal") from Dolanaar to Darkshore by the boat
    # at Rut'theran Village: the plan's walk to the boat is a straight line down the side of Teldrassil (the router's way
    # there: Darnassus's edge, then 1.6k yd straight over blocked ground). Such a walk is left out (Nav.noWalk) and the
    # stretch planned again: by the teleporter in Darnassus, then the boat
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    fac = ns.CharDB().faction
    ns.CharDB().faction = "Alliance"
    try:
        N.Clear()
        N.Invalidate(True, True)  # (nothing left out from before)
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 9850.0, 950.0, 1")
        N.SetStops(lua.eval("{ { x = 5695.2, y = 300.6, cont = 1, name = 'Darkshore' } }"), False, "red")
        G.Follow()
        for _ in range(20):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        steps = str(N.StepsText(10))  # (city routing, on by default: a swim across Darnassus's pond on the way)
        assert "to the teleporter (The Temple Gardens, Darnassus)" in steps
        assert "Take the teleporter to Rut'theran Village, Teldrassil" in steps
        assert "Take the boat to Auberdine, Darkshore" in steps
        assert N.route.walkYards < 4000  # (not 3.7k yd down the tree to the boat, then the walk in Darkshore)
    finally:
        ns.CharDB().faction = fac
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


NO_WALK_LEFT = """function()
  for _, c in pairs(AGPS_NS.Nav.noWalk) do for _, f in pairs(c) do if next(f) then return false end end end
  return true
end"""


def test_a_walk_over_blocked_ground_to_the_stop_itself_isnt_planned_again(game):
    # (the overnight trip sweep, 2026-10-07: 250 ms redraws on the way to Rethress Sanctum, out in the sea off Azshara)
    # the walk straight there crosses 1.6k yd of water from the road's end: planned again once (the way by Orgrimmar's
    # flight master crosses less), and not again at each recalculation after, in the frame. (Where no plan gets round
    # it, every walk to that stop is kept, Nav.walkKept's "*": not planned again from each new place either)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      local N = AGPS_NS.Nav
      AGPS_WBW, AGPS_PLAN, AGPS_TRIES, AGPS_IN = N.WithoutBlockedWalks, N.Plan, 0, false
      N.WithoutBlockedWalks = function(...)
        AGPS_IN = true
        local legs, routes = AGPS_WBW(...)
        AGPS_IN = false
        return legs, routes
      end
      N.Plan = function(...)
        if AGPS_IN then AGPS_TRIES = AGPS_TRIES + 1 end
        return AGPS_PLAN(...)
      end
    """)
    try:
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2067.6, -4797.0, 1")
        N.SetStops(lua.eval("{ { x = 2183.3, y = -6416.7, cont = 1, name = 'Rethress Sanctum' } }"), False, "red")
        G.Follow()
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        r = N.route
        assert r and r.parts and int(lua.eval("AGPS_TRIES")) >= 1  # (planned again once: the walk straight there)
        # (the recalculations after it, while the searches finish and the player stands there: not planned again)
        lua.execute("AGPS_TRIES = 0")
        for _ in range(3):
            N.Invalidate(False)
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        assert N.route and int(lua.eval("AGPS_TRIES")) == 0
    finally:
        lua.execute("""
          local N = AGPS_NS.Nav
          N.WithoutBlockedWalks, N.Plan = AGPS_WBW, AGPS_PLAN
        """)
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_walk_to_the_stop_over_blocked_ground_another_plan_avoids_is_left_out(game):
    # (the overnight route-quality check, 2026-10-07) Horde 20, Bough Shadow to Lake Mennar: the way with a ride's last
    # walk, from Orgrimmar, crosses blocked ground to the stop; left out, the plan walks by Valormok's flight master
    # instead, 3.7k yd, 160 s quicker as weighed. A rule that never counted a piece to the stop itself (every plan walks
    # it, not so) kept the flight
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    cdb = ns.CharDB()
    fac, nodes = cdb.faction, cdb.taxiNodes
    known = (22, 23, 30, 38, 42, 44, 53, 69, 79, 80)
    try:
        lua.execute("AGPS_LEVEL = 20")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in known) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 3283.3, -3716.7, 1")
        N.SetStops(lua.eval("{ { x = 2650.0, y = -5283.3, cont = 1, name = 'Lake Mennar' } }"), False, "red")
        G.Follow()
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        st = N.route.stretches[1]
        assert not any(st.legs[i].ride for i in range(1, len(st.legs) + 1))
        assert st.walk < 4500
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = fac, nodes
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_walk_left_out_for_no_better_plan_is_put_back_and_kept(game):
    # (the overnight trip sweep, 2026-10-07) a walk over blocked ground whose plans without it all weigh more is put
    # back and kept (Nav.walkKept): the next recalculation neither plans again (each did, NO_WALK_TRIES times in the
    # frame: 250 ms redraws) nor settles for a worse plan without it (it stayed left out). Every walk weighed as over
    # blocked ground here
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      local N = AGPS_NS.Nav
      AGPS_BY, AGPS_WBW, AGPS_PLAN, AGPS_TRIES, AGPS_IN = N.BlockedYards, N.WithoutBlockedWalks, N.Plan, 0, false
      N.BlockedYards = function(cont, r) if r and r.noWay then return math.huge end return 700 end
      N.WithoutBlockedWalks = function(...)
        AGPS_IN = true
        local legs, routes = AGPS_WBW(...)
        AGPS_IN = false
        return legs, routes
      end
      N.Plan = function(...)
        if AGPS_IN then AGPS_TRIES = AGPS_TRIES + 1 end
        return AGPS_PLAN(...)
      end
    """)
    try:
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -442.0, -2596.0, 1")
        N.SetStops(lua.eval("{ { x = -300.0, y = -2350.0, cont = 1, name = 'stop' } }"), False, "red")
        G.Follow()
        for _ in range(6):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        assert N.route and int(lua.eval("AGPS_TRIES")) >= 1  # (planned again without it)
        steps = str(N.StepsText(4))
        assert lua.eval(NO_WALK_LEFT)() and not lua.eval("next(AGPS_NS.Nav.walkKept) == nil")
        lua.execute("AGPS_TRIES = 0")
        N.Invalidate(False)  # (a recalculation)
        for _ in range(6):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        assert N.route and int(lua.eval("AGPS_TRIES")) == 0
        assert str(N.StepsText(4)) == steps
    finally:
        lua.execute("""
          local N = AGPS_NS.Nav
          N.BlockedYards, N.WithoutBlockedWalks, N.Plan = AGPS_BY, AGPS_WBW, AGPS_PLAN
        """)
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_ride_whose_walk_is_a_long_way_round_is_planned_again(game):
    # (the overnight trip sweep, 2026-10-07) Horde, level 5, Lakeridge Highway to Kurzen's Compound: the way with a ride
    # walked to Stonard's flight master, 1.1k yd straight and 10k yd round, so the ride check (Nav's CompareRide) chose
    # the walk, 9.2k yd. It plans the way with a ride again past that walk (Nav.WalkDetour): by Rog'mar's flight to
    # Grom'gol, under half the walk's time. (Since Riverglades has its levels, 38-45 (Router.ZONE_LEVELS_BY_ID), it is
    # too high at level 5 like Burning Steppes: the way with a ride now learns Flame Crest's flight to Grom'gol instead)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    cdb = ns.CharDB()
    fac, nodes = cdb.faction, cdb.taxiNodes
    known = (10, 11, 13, 18, 20, 56, 68, 75, 76, 85, 86, 87, 3203)
    try:
        lua.execute("AGPS_LEVEL = 5")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in known) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -9716.7, -2450.0, 0")
        N.SetStops(lua.eval("{ { x = -11550.0, y = -716.7, cont = 0, name = [[Kurzen's Compound]] } }"), False, "red")
        G.Follow()
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        assert "planned again past a long way round): rides" in str(N.lastRideCheck)
        steps = str(N.StepsText(4))
        assert "flight master (" in steps and "flight to Grom'gol, Stranglethorn" in steps, steps
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = fac, nodes
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_ride_whose_walk_came_out_far_longer_than_planned_has_the_next_plan_looked_at(game):
    # (#359, route-quality on new Loch Modan roads) Alliance, level 30, The Dead Acre to Apocryphan's Rest: the plan
    # flies to Stormwind and takes the tram, then walks from Ironforge, 2.3k yd straight. His roads made that walk 7.5k yd
    # (13.8k before): no longer a long way round, so the ride check stopped at the tram's plan, slower than the walk, and
    # walked (1,318 s). A walk thousands of yards past the plan's (Nav.WalkLonger) gets the next plan looked at too: by
    # Farholde Keep's flight (919 s). (Level 34, not 30: Riverglades has its levels since, 38-45, and at 30 it is too
    # high to fly into (Router.LEVEL_RED); at 34 it isn't, as it wasn't when this was written)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    cdb = ns.CharDB()
    fac, nodes = cdb.faction, cdb.taxiNodes
    known = (2, 5, 6, 7, 14, 16, 45, 66, 67, 71, 84, 85, 86, 87, 3276)
    try:
        lua.execute("AGPS_LEVEL = 34")
        cdb.faction = "Alliance"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in known) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -10783.3, 816.7, 0")
        N.SetStops(lua.eval("{ { x = -6883.3, y = -2450.0, cont = 0, name = [[Apocryphan's Rest]] } }"), False, "red")
        G.Follow()
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        assert str(N.lastRideCheck).endswith(": rides"), N.lastRideCheck
        steps = str(N.StepsText(4))
        assert "Farholde Keep" in steps and "tram" not in steps.lower(), steps
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = fac, nodes
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_ride_whose_walk_came_out_far_longer_off_the_roads_has_the_next_plan_looked_at(game):
    # (#715, route-quality on Thunder Bluff's rebuilt roads) Horde, level 40, Valley of Bones to Hive'Ashi: the plan
    # walks to Camp Mojache's flight master, and past it to Thunder Bluff's, 4.9k yd round from 2.4k planned, a third of
    # it off the roads: no long way round, nor along the roads, so the check stopped there and flew from Camp Mojache
    # (1,187 s). Past the first plan, off the roads counts too: Shadowprey's flight (1,023 s)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    cdb = ns.CharDB()
    fac, nodes = cdb.faction, cdb.taxiNodes
    known = (22, 23, 25, 29, 30, 40, 44, 48, 53, 61, 63, 72, 77, 79, 80)
    try:
        lua.execute("AGPS_LEVEL = 40")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in known) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -2251.2, 1513.6, 1")
        N.SetStops(lua.eval("{ { x = -6450.0, y = 1150.0, cont = 1, name = [[Hive'Ashi]] } }"), False, "red")
        G.Follow()
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        assert str(N.lastRideCheck).endswith(": rides"), N.lastRideCheck
        steps = str(N.StepsText(4))
        assert "Shadowprey" in steps and "Mojache" not in steps, steps
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = fac, nodes
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_the_ride_the_check_chose_is_the_one_taken_from_a_stop(game):
    # (the overnight trip sweep, 2026-10-07) Horde, level 14, The Zoram Strand, Cliffspring Falls, then The Forgotten
    # Pools: the ride check worked out the stretch from Cliffspring Falls from a spot rounded 25 yd off it, out of the
    # cave the stop is down in, and the ride it chose (Zoram'gar's flight) wasn't the one taken: the stretch planned from
    # the stop walked 15.5k yd to Moonglade's flight master, slower than walking all the way. A stop's spot isn't
    # rounded, and the ride that won is the one taken
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    cdb = ns.CharDB()
    fac, nodes = cdb.faction, cdb.taxiNodes
    known = (22, 23, 25, 29, 30, 38, 40, 42, 53, 61, 77, 80, 3242)
    try:
        lua.execute("AGPS_LEVEL = 14")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in known) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        ns.settings.gps.fastestOrder = False
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 3516.7, 1550.0, 1")
        N.SetStops(lua.eval("{ { x = 6870.6, y = -662.4, cont = 1, name = 'Cliffspring Falls' }, "
                            "{ x = 50.0, y = -1916.7, cont = 1, name = 'The Forgotten Pools' } }"), False, "red")
        G.Follow()
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        st = N.route.stretches[2]
        rides = [str(st.legs[i].ride[9]) for i in range(1, len(st.legs) + 1) if st.legs[i].ride]
        assert rides and rides[0].startswith("Zoram'gar Outpost"), rides
        assert st.walk < 8000  # (not 15.5k yd to Moonglade's flight master)
    finally:
        ns.settings.gps.fastestOrder = ns.DEFAULTS.gps.fastestOrder
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = fac, nodes
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_stop_near_as_the_crow_flies_but_far_on_foot_gets_the_ride_check(game):
    # (the overnight trip sweep, 2026-10-07) Alliance, level 5, Blackrock Stronghold to Tanner Camp: 520 yd apart, under
    # the ride check's distance (RIDE_CHECK_MIN_YD), so the walk was taken without one: 9k yd round the mountains then. A
    # walk routed RIDE_CHECK_FAR_YD long gets the check. Now the walk goes through Blackrock Mountain (walked on foot by
    # walked in testing) and the Slag Pit, and beats the flight from Thorium Point
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    cdb = ns.CharDB()
    fac, nodes = cdb.faction, cdb.taxiNodes
    known = (4, 6, 7, 12, 14, 43, 45, 84, 85, 86, 87, 3276)
    try:
        lua.execute("AGPS_LEVEL = 5")
        cdb.faction = "Alliance"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in known) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        N.lastRideCheck = None
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -7650.0, -1416.7, 0")
        N.SetStops(lua.eval("{ { x = -7250.0, y = -1750.0, cont = 0, name = 'Tanner Camp' } }"), False, "red")
        G.Follow()
        for _ in range(10):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        st = N.route.stretches[1]
        rides = [str(st.legs[i].ride[9]) for i in range(1, len(st.legs) + 1) if st.legs[i].ride]
        # (through Blackrock Mountain, not 9k yd round by the Badlands: that stretch was walked on foot in testing,
        # its checkpoints below; then into the Slag Pit by its west mouth on the floor's level and
        # up its ramps to the south mouth, 4.5k yd in all. Client 70938's caves alone had 3.5k yd: down the 57 yd wall
        # from its rim mouth, #349. The check still runs, and the walk wins it)
        check = str(N.lastRideCheck)
        assert check.startswith("walk routed") and check.endswith(": walk"), check  # the check ran, and the walk won
        assert not rides and N.RIDE_CHECK_FAR_YD < st.walk < 5000, (rides, st.walk)
        part = N.route.parts[1]
        pts = [(part.pts[2 * k - 1], part.pts[2 * k]) for k in range(1, len(part.pts) // 2 + 1)]
        fz = [part.fz[k] if part.fz else None for k in range(1, len(pts) + 1)]

        def near(q):
            best = math.inf
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                dx, dy = bx - ax, by - ay
                t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / ((dx * dx + dy * dy) or 1)))
                best = min(best, math.hypot(ax + t * dx - q[0], ay + t * dy - q[1]))
            return best
        for q in ((-7661.5, -1038.25), (-7555.5, -1021.75), (-7430.25, -1061.5), (-7190.5, -1078.75), (-6954.0, -1038.0)):
            assert near(q) < 5, (q, near(q))
        for (p, a), (q, b) in zip(zip(pts, fz), zip(pts[1:], fz[1:])):  # (never down a wall)
            d = math.hypot(q[0] - p[0], q[1] - p[1])
            assert not (a and b and d >= 1 and abs(b - a) > max(20, d)), (p, a, q, b)
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = fac, nodes
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_out_of_a_capitals_gate_the_walk_crosses_the_river(game):
    # (seen in game 2026-11-14) Horde, from Orgrimmar to a stop on the Southfury River's west bank in the Northern
    # Barrens, 1.1k yd from the gate: no walk over the terrain to or from a capital's grid, so past the gate the walk
    # kept to the roads, 3.9k yd round by Razor Hill and Far Watch's bridge, and the flight to the Crossroads won (then
    # 2.9k yd up the west bank). The way out of the city kept, the rest routed as from outside (Router.OutOfCapital):
    # across the river, 1.5k yd, and the walk wins the ride check
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    cdb = ns.CharDB()
    fac, nodes = cdb.faction, cdb.taxiNodes
    try:
        lua.execute("AGPS_LEVEL = 20")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { { nodeID = 23, known = true }, { nodeID = 25, known = true } } } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        N.lastRideCheck = None
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 1677.6, -4315.7, 1")
        N.SetStops(lua.eval("{ { x = 1135.0, y = -3330.0, cont = 1, name = 'Southfury west bank' } }"), False, "red")
        G.Follow()
        for _ in range(20):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        st = N.route.stretches[1]
        rides = [str(st.legs[i].ride[9]) for i in range(1, len(st.legs) + 1) if st.legs[i].ride]
        check = str(N.lastRideCheck)
        assert check.endswith(": walk"), check
        assert not rides and st.walk < 2000, (rides, st.walk)
        part = N.route.parts[1]
        xs = [part.pts[2 * k - 1] for k in range(1, len(part.pts) // 2 + 1)]
        assert min(xs) > 1000, min(xs)  # (across north of Razor Hill, not by Far Watch's bridge at x 300)
    finally:
        lua.execute("AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes = fac, nodes
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_a_route_from_a_floor_in_a_building_walks_on_over_the_land(game):
    # (the overnight trip sweep, 2026-10-07) from inside Lakeshire's town hall, on the floor the player is followed on
    # (opts.z), to Darkshire: no straight line or walk over the terrain from a floor (RouteOne's `offFloor`), and the
    # whole trip went by the roads, 7.6k yd round by Westfall at level 5. Out by the building's own roads, then on as
    # from any spot outside (Router.ThroughDoors): 1.7k yd over the pass into Duskwood
    lua, ns = game
    R, N = ns.Router, ns.Nav
    try:
        lua.execute("AGPS_LEVEL = 5 AGPS_T = AGPS_T + 10")
        N.ResetCityTrack()  # (a floor followed by a test before: not carried here, 4,000 yd off)
        x, y = -9227.7, -2201.5
        z = N.TrackCityZ(0, x, y)
        assert z and N.InBuilding(0, x, y)
        r = R.Route(0, x, y, -10564.7, -1170.7, lua.eval(f"{{ offroad = false, z = {z} }}"))
        assert r.length < 2500, r.length
        assert r.fz and abs(r.fz[1] - z) < 3  # (out on its floor, by its own roads)
    finally:
        lua.execute("AGPS_LEVEL = nil")



def test_distances_in_meters_from_the_general_page_everywhere(game):
    # (asked 2026-10-07 for 1.1.6: European distances) Options > General, "Show distances in" (a dropdown): picked,
    # the steps, the map's directions and the arrow window give meters and kilometers, no yards; back to yards after
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    widgets = lambda: list(lua.eval("AGPS_WIDGETS").values())
    try:
        ns.Options.Show()
        ns.Options.ShowPage("General")
        ns.Options.Refresh()
        box = next(w for w in widgets() if w._kind == "DropdownButton" and w.options is not None
                   and any(o.value == "metric" for o in w.options.values()))
        assert str(box._choice) == "Yards (the game's)"
        assert list(lua.globals().AGPS_MENU(box).values()) == ["Yards (the game's)", "Meters and kilometers", "Feet and miles"]
        lua.globals().AGPS_PICK(box, "Meters and kilometers")
        assert st.distanceUnits == "metric" and str(box._choice) == "Meters and kilometers"
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil")
        G.Follow()
        N.SetStops(lua.eval("{ { x = 1600.0, y = 240.0, cont = 0, name = 'the Ruins' } }"), False, "red")
        for _ in range(5):
            lua.execute("AGPS_T = AGPS_T + 1")
            G.Update()
        assert N.Route(2254.0, 293.0, 0)
        head = str(N.Status(2254.0, 293.0, 0))  # (the map's directions: the distance first)
        assert re.search(r"\d+ m\b|\d\.\d km", head) and " yd" not in head, head
        steps = str(N.StepsText(3))
        assert " yd" not in steps, steps
        arrowWin = lua.globals().AzerothGPSArrow
        arrowWin._scripts.OnUpdate(arrowWin, 1)
        texts = [str(w._text) for w in widgets() if w._parent is not None and w._text is not None
                 and re.search(r"\d+ (m|km|yd)\b", str(w._text))]
        assert texts and not any(" yd" in t for t in texts), texts
    finally:
        st.distanceUnits = "yards"
        N.Clear()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()



def test_a_finished_searchs_recalculation_runs_in_the_background_while_on_the_route(game):
    # (the overnight trip sweeps, 2026-10-07: the remaining 50 to 170 ms frames) a background terrain search finishing
    # marks the route dirty (Nav.SearchDone), and the recalculation it forces ran the whole plan in the frame whenever
    # the walk from the player was short (the background path only took no route, or a first walk past REJOIN_MIN_YD).
    # Still on the route, it goes to the background too: the old route shown meanwhile, no "route calculation" timed in
    # the frame, and the recalculation applied when its slices are done
    lua, ns = game
    G, N, R = ns.GPS, ns.Nav, ns.Router
    R.WARM, R.SYNC_WALKS = True, False
    clock = lua.eval("function() return os.clock() * 1000 end")

    def runs():
        p = ns.perf["route calculation"]
        return p.n if p is not None else 0

    def pump_until_done(most=400):
        for _ in range(most):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            G.Update()
            if R.HasWork():
                R.Pump(clock() + 5, clock)
            elif N.route is not None:
                return True
        return False

    secs = ns.settings.gps.rerouteSeconds
    try:
        ns.settings.gps.rerouteSeconds = None  # (the default: a slower setting scales SEARCH_RECALC_SECONDS with it)
        # (a transport test before this one can leave the ride detector mid-ride, rideStreak >= 2: N.Route then keeps
        # the route as it is, as on a boat; this test is about the recalculation, so the player is plainly on foot)
        lua.execute("""AGPS_TAXI = { AGPS_NS.Taxi.Riding, AGPS_NS.Taxi.Current, AGPS_NS.Taxi.CurrentRide }
          AGPS_NS.Taxi.Riding = function() return false end
          AGPS_NS.Taxi.Current = function() return nil end
          AGPS_NS.Taxi.CurrentRide = function() return nil end""")
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 10")
        N.SetStops(lua.eval("{ { x = 1600.0, y = 240.0, cont = 0, name = 'the Ruins' } }"), False, "red")
        G.Follow()
        assert pump_until_done()  # (the first route: in the background, as in game)
        old = N.route
        full = old.fullFirst
        yd = 0.0
        if full is not None and old.cum is not None:
            yd = old.cum[len(list(old.cum.values()))] - (old.consumed or 0)
        assert yd < N.REJOIN_MIN_YD  # (a short walk from the player: the case that ran in the frame)
        # a search finished and the player has moved on along the route: the next look recomputes it
        # (the clock far forward: tests before this one jump AGPS_T by minutes and one puts it back, so the
        # recalculation rate limit's last stamp can sit in the future; the game's clock never goes backwards)
        N.SearchDone(False)
        x, y = ns.Turns.PointAt(ns.Turns.Path(old), 40.0)  # (40 yd along it: past the reroute's yards)
        lua.execute(f"""AGPS_T = AGPS_T + 1000
          AGPS_POS[1], AGPS_POS[2] = {x}, {y}
          AGPS_BG = {{}}
          AGPS_BG_REAL = AGPS_NS.Router.Background
          AGPS_NS.Router.Background = function(k, fn, done) AGPS_BG[#AGPS_BG + 1] = k return AGPS_BG_REAL(k, fn, done) end""")
        try:
            before = runs()
            assert N.Route(x, y, 0) is not None  # (the old route shown meanwhile)
            assert runs() == before, "the recalculation ran in the frame"
            queued = [str(k) for k in lua.eval("AGPS_BG").values()]
            assert any(k.startswith("route:") for k in queued), queued  # (queued for the background instead)
        finally:
            lua.execute("AGPS_NS.Router.Background = AGPS_BG_REAL")
        assert pump_until_done()
        assert N.route is not None
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        ns.settings.gps.rerouteSeconds = secs
        lua.execute("AGPS_NS.Taxi.Riding, AGPS_NS.Taxi.Current, AGPS_NS.Taxi.CurrentRide = unpack(AGPS_TAXI)")
        N.Clear()



def test_the_stretches_between_stops_fill_in_the_background(game):
    # (the overnight sweeps' replay, 2026-10-07: 52 and 85 ms frames on trips with a second stop) the stretches
    # between stops were worked out one per N.Route call in the frame ("route calculation: stops"); in the game
    # they go to the background (they don't depend on the player), and the route grows to the second stop when
    # the slices are done
    lua, ns = game
    G, N, R = ns.GPS, ns.Nav, ns.Router
    R.WARM, R.SYNC_WALKS = True, False
    import time
    clock = lambda: time.perf_counter() * 1000

    def stops_runs():
        p = ns.perf["route calculation: stops"]
        return p.n if p is not None else 0

    try:
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1000")
        N.SetStops(lua.eval("{ { x = 1600.0, y = 240.0, cont = 0, name = 'the Ruins' }, "
                            "{ x = 507.0, y = 1594.0, cont = 0, name = 'Sepulcher' }, "
                            "{ x = 2237.0, y = 1035.0, cont = 0, name = 'Brightwater' } }"), False, "red")
        G.Follow()
        before = stops_runs()

        def full():
            r = N.route
            return bool(r and r.length and r.stretches and len(list(r.stretches.values())) >= 3)

        def settle(most=600):
            for _ in range(most):
                lua.execute("AGPS_T = AGPS_T + 0.1")
                G.Update()
                if R.HasWork():
                    R.Pump(clock() + 5, clock)
                elif full():
                    return True
            return False

        assert settle()  # (the stretches between stops are in, from the background)
        assert stops_runs() == before, "a stretch between stops was worked out in the frame"
        # a search between fixed points finished: the stretches are done again, in the background too
        N.SearchDone(True)
        lua.execute("AGPS_T = AGPS_T + 1000")
        assert settle()
        assert stops_runs() == before, "a stretch between stops was worked out in the frame"
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        N.Clear()


def test_the_fastest_order_is_worked_out_in_the_background_while_moving(game):
    # (the sweeps' replay, 2026-10-07: 50 to 100 ms frames on trips with a second stop) with the fastest order on,
    # every reorder look planned from the player to each stop in the frame (those plans move with the player and
    # aren't remembered). In the game they go to the background; the order still applies when one is clearly faster
    lua, ns = game
    G, N, R = ns.GPS, ns.Nav, ns.Router
    R.WARM, R.SYNC_WALKS = True, False
    import time
    clock = lambda: time.perf_counter() * 1000
    order = ns.settings.gps.fastestOrder
    try:
        ns.settings.gps.fastestOrder = True
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1000")
        N.SetStops(lua.eval("{ { x = 1600.0, y = 240.0, cont = 0, name = 'the Ruins' }, "
                            "{ x = 507.0, y = 1594.0, cont = 0, name = 'Sepulcher' } }"), False, "red")
        G.Follow()
        for _ in range(600):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            G.Update()
            if R.HasWork():
                R.Pump(clock() + 5, clock)
            elif N.route is not None:
                break
        assert N.route is not None
        # moving on along the route, past the reorder's yards and seconds: the next look must not plan in the frame
        x, y = ns.Turns.PointAt(ns.Turns.Path(N.route), 40.0)
        lua.execute(f"""AGPS_T = AGPS_T + 1000 AGPS_POS[1], AGPS_POS[2] = {x}, {y}
          AGPS_PLANS = 0
          AGPS_PLAN_REAL = AGPS_NS.Nav.Plan
          AGPS_NS.Nav.Plan = function(...) AGPS_PLANS = AGPS_PLANS + 1 return AGPS_PLAN_REAL(...) end""")
        try:
            N.Status(x, y, 0)
            assert int(lua.eval("AGPS_PLANS")) == 0, "the reorder planned in the frame"
        finally:
            lua.execute("AGPS_NS.Nav.Plan = AGPS_PLAN_REAL")
        assert R.HasWork()  # (the reorder queued)
        for _ in range(200):
            if R.HasWork():
                R.Pump(clock() + 5, clock)
            else:
                break
        assert not R.HasWork()  # (and ran through)
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        ns.settings.gps.fastestOrder = order
        N.Clear()

def test_a_search_done_every_frame_doesnt_redraw_past_the_rate(game):
    # (the 1.1.5 test pass: 20% of a core zoomed in on a long dotted off-road leg) walking off a long off-road leg, the
    # walks searched from each new spot finished nearly every frame, and each one done forced a redraw at once: the map
    # redrew every frame, not at its rate. A search done is a new route for the next redraw at the rate to see. (The
    # map frame's OnUpdate alone, and a counter of its own: an earlier test leaves G.Update counted into AGPS_REDRAWS)
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    ns.Nav.Clear()
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 2254.0, 293.0, 0, nil")
    G.Follow()
    lua.execute("""
      AGPS_SEARCH_REDRAWS = 0
      AGPS_UPDATE_REAL, AGPS_PUMP_REAL = AGPS_NS.GPS.Update, AGPS_NS.GPS.PumpSearches
      AGPS_NS.GPS.Update = function(...) AGPS_SEARCH_REDRAWS = AGPS_SEARCH_REDRAWS + 1 return AGPS_UPDATE_REAL(...) end
      AGPS_NS.GPS.PumpSearches = function() return true end -- (a search done every frame)
    """)
    mapf = lua.globals().AzerothGPSFrame
    try:
        st.hz = 20
        t = float(lua.eval("AGPS_T"))
        x = 2254.0
        for i in range(190):
            t, x = t + 1 / 60, x - 0.12
            lua.execute(f"AGPS_T = {t} AGPS_POS[1] = {x}")
            if i == 10:
                lua.execute("AGPS_SEARCH_REDRAWS = 0")
            mapf._scripts.OnUpdate(mapf, 1 / 60)
        n = int(lua.eval("AGPS_SEARCH_REDRAWS"))
        assert n <= 20 * 3 + 1, n  # (180 frames: 3 s)
    finally:
        lua.execute("AGPS_NS.GPS.Update, AGPS_NS.GPS.PumpSearches = AGPS_UPDATE_REAL, AGPS_PUMP_REAL")
        st.hz = ns.DEFAULTS.gps.hz
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2254.0, 293.0")


@pytest.mark.timing
def test_a_route_from_beside_a_caves_roads_is_worked_out_in_short_slices(game):
    # (the overnight trip sweep, 2026-10-07: slices of background work up to 170 ms on Kalimdor) a trip from Dire Maul
    # (the roads near it all a cave's): the route's way onto the roads looked at every road on the continent, sorted
    # all 13,000 (Router.NearestEdgesAll, twice a route) in one piece of the background job. The nearest few now, with
    # a pause every 1,000 roads
    lua, ns = game
    G, N, R = ns.GPS, ns.Nav, ns.Router
    fac = ns.CharDB().faction
    clock = lua.eval("function() return os.clock() * 1000 end")
    try:
        lua.execute("AGPS_LEVEL = 60")
        ns.CharDB().faction = "Horde"
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4550.0, 1416.7, 1, nil")
        R.WARM, R.SYNC_WALKS = True, False
        N.SetStops(lua.eval("{ { x = -10616.7, y = -4016.7, cont = 1, name = 'South Seas' }, "
                            "{ x = -8050.0, y = 1616.7, cont = 1, name = 'The Scarab Dais' } }"), False, "red")
        t, worst = float(lua.eval("AGPS_T")) + 10, 0.0
        for f in range(900):
            t += 0.05
            lua.execute(f"AGPS_T = {t}")
            G.Update()
            if R.HasWork():
                c0 = clock()
                R.Pump(clock() + 5, clock)
                worst = max(worst, clock() - c0)
            if N.route and not R.HasWork() and f > 20:
                break
        assert N.route
        assert worst < 40, f"a slice of the route's background work ran {worst:.0f} ms"
        near = R.NearestEdgesAll(1, -4550.0, 1416.7)
        ds = [near[i].dist for i in range(1, len(near) + 1)]
        assert 0 < len(ds) <= R.NEAREST_ALL_KEEP and ds == sorted(ds)
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        lua.execute("AGPS_LEVEL = nil")
        ns.CharDB().faction = fac
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        G.Follow()


def test_the_nearest_roads_come_from_the_road_index_not_every_road(game):
    # (the overnight trip sweep, 2026-10-07: a plan's walks checked again called Router.NearestEdgesAll over and over in
    # the frame, every road on Kalimdor, 13,000, 7 to 12 ms a call: 250 ms redraws) the nearest roads from the segment
    # index's buckets, ring by ring out from the spot: the same as every road's nearest (by a road, out at sea, a cave's
    # roads only, the land's only), and by a road much quicker
    lua, ns = game
    R = ns.Router
    lua.execute("""
      local f, i = AGPS_NS.Router.NearestEdgesAll, 1
      while true do
        local name, v = debug.getupvalue(f, i)
        if not name then break end
        if name == 'Graph' or name == 'GraphQuery' then AGPS_GRAPH = v end
        if name == 'NearestAllScan' then AGPS_SCAN = v end
        i = i + 1
      end
    """)
    graph, scan = lua.eval("AGPS_GRAPH"), lua.eval("AGPS_SCAN")
    assert graph and scan
    # (Lua instructions counted, not CPU time: under a loaded CI runner the times came out 2.9 to 1, under the 3;
    # #1000, as #993 and #999)
    counted = lua.eval("""function(f, ...)
      local n = 0
      debug.sethook(function() n = n + 1 end, "", 100)
      local r = f(...)
      debug.sethook()
      return r, n
    end""")
    g = graph(1)
    oks = (None, lua.eval("function(g) return function(ei) return g.cave[ei] end end")(g),
           lua.eval("function(g) return function(ei) return not g.cave[ei] end end")(g))
    by_road = [(float(g.n[2 * j - 1]) + 40.0, float(g.n[2 * j]) - 25.0) for j in range(1, int(g.count) + 1, 997)]
    spots = by_road + [(-4550.0, 1416.7), (2183.3, -6416.7), (9850.0, 950.0), (-9000.0, -9000.0)]
    t_index = t_scan = 0.0
    for k, (x, y) in enumerate(spots):
        for ok in oks:
            a, n_index = counted(R.NearestEdgesAll, 1, x, y, ok)
            b, n_scan = counted(scan, g, x, y, ok)
            if k < len(by_road):
                t_index, t_scan = t_index + n_index, t_scan + n_scan
            da = [round(a[i].dist, 3) for i in range(1, len(a) + 1)]
            db = [round(b[i].dist, 3) for i in range(1, len(b) + 1)]
            assert da == db, (x, y, ok is None)
    assert t_index * 3 < t_scan, (t_index, t_scan)


def test_button_colors_only_on_the_map_window_and_windows_other_addons_register(game):
    # (API 17, asked 2026-10-07 for a plugin addon; asked 2026-11-04 with a screenshot, the options window's X and Reset
    # button colored: "setting the window options should only apply to the gps window itself") the frame look's
    # `buttons` and `close` on the map window's panel and close buttons (Options > Window's look or another addon's) and
    # on a window another addon registers (another addon's look only); never the options window or AzerothGPS's popups;
    # nothing else tinted (an icon button, the map's own layers); the X falls back to `buttons`; a state color
    # multiplied; no look: white again
    lua, ns = game
    A, G, st = lua.globals().AzerothGPS, ns.GPS, ns.settings.gps
    CF = lua.globals().CreateFrame
    assert A.version >= 19
    map_btn = CF("Button", None, lua.globals().AzerothGPSFrame, "UIPanelButtonTemplate")
    popup = ns.Window("AGPSLookTestPopup", 300, 120, "Test")
    ok_btn = CF("Button", None, popup, "UIPanelButtonTemplate")
    ns.Options.Show()
    opts = lua.globals().AzerothGPSOptions
    opt_btn = CF("Button", None, opts, "UIPanelButtonTemplate")
    theirs = CF("Frame", None, lua.globals().UIParent)
    their_btn = CF("Button", None, theirs, "UIPanelButtonTemplate")
    their_x = CF("Button", None, theirs, "UIPanelCloseButton")
    theirs.CloseButton = their_x
    icon = CF("Button", None, theirs)  # (an icon button: no pieces, not a close button)
    poi = CF("Button", None, G.poiLayer, "UIPanelButtonTemplate")  # (on the map's icon layer)
    assert A.RegisterLookFrame(theirs) is True

    def ours():  # (AzerothGPS's other windows: never)
        return (ok_btn.Left._vc, popup.closeButton.GetNormalTexture(popup.closeButton)._vc, opt_btn.Middle._vc,
                opts.closeButton.GetNormalTexture(opts.closeButton)._vc)
    try:
        A.SetFrameLook("Plugin", lua.eval("{ buttons = { 1, 0.5, 0.25 }, close = { 0.2, 1, 0.2 } }"))
        popup.Show(popup)
        G.ApplyButtonLooks()
        assert (map_btn.Left._vc, their_btn.Right._vc, their_x.GetPushedTexture(their_x)._vc) == \
            ("1.00,0.50,0.25", "1.00,0.50,0.25", "0.20,1.00,0.20")
        assert map_btn.Left._desat and their_btn.Right._desat  # (each grayed first: "True colors", 2026-10-08)
        assert set(ours()) == {None} and not ok_btn.Left._desat
        assert icon.GetNormalTexture(icon)._vc is None and poi.Left._vc is None  # (nothing else)
        look = A.FrameLook()
        assert list(look.buttons.values()) == [1, 0.5, 0.25] and list(look.close.values()) == [0.2, 1, 0.2]
        A.SetFrameLook("Plugin", lua.eval("{ buttons = { 0.5, 0.5, 1 } }"))  # (the X without its own: the buttons')
        assert their_x.GetNormalTexture(their_x)._vc == "0.50,0.50,1.00" and their_btn.Left._vc == "0.50,0.50,1.00"
        G.ButtonStateColor(their_btn.Left, 1, 0.5, 1)  # (a state color of core's: multiplied)
        assert their_btn.Left._vc == "0.50,0.25,1.00"
        G.ButtonStateColor(their_btn.Left, None)
        A.SetFrameLook("Plugin", None)
        assert map_btn.Left._vc == "1.00,1.00,1.00" and their_btn.Left._vc == "1.00,1.00,1.00" and A.FrameLook() is None
        assert not map_btn.Left._desat  # (no look: the game's own art again)
        # Options > Window's own colors: the map window alone, not another addon's window
        st.windowButtons, st.windowClose = "gold", "fel"
        ns.Looks.Apply()
        assert map_btn.Left._vc == "1.00,0.82,0.45" and their_btn.Left._vc == "1.00,1.00,1.00"
        assert set(ours()) == {None}
    finally:
        A.SetFrameLook("Plugin", None)
        st.windowButtons, st.windowClose = "default", "buttons"
        ns.Looks.Apply()
        popup.Hide(popup)
        opts.Hide(opts)


def test_the_window_options_tint_the_frame_and_color_the_route(game):
    # (asked 2026-11-04: "add the window frame options from the plugin here as well... a drop down... for the AzerothGPS
    # route color, default to blue and provide an option for rainbow, but only those 2") Options > Window: the frame's
    # tint, the buttons by it, the X's own; the route a rainbow; another addon's look shows over them while it's set
    lua, ns = game
    A, G, N, L, st = lua.globals().AzerothGPS, ns.GPS, ns.Nav, ns.Looks, ns.settings.gps
    blue = "0.05,0.28,0.85"
    rainbow = {"%.2f,%.2f,%.2f" % tuple(G.RAINBOW[i][k] for k in (1, 2, 3)) for i in range(1, G.RAINBOW_STEPS + 1)}
    defaults = (st.windowTint, st.windowButtons, st.windowClose, st.routeColor)
    assert defaults == ("default", "default", "buttons", "blue") and G.ownFrameLook is None and G.ownRouteLook is None
    lua.execute("AGPS_OLD_FACTION = UnitFactionGroup")
    try:
        st.windowTint = "fel"
        L.Apply()
        assert list(G.ShownFrameLook().border.values()) == [0.55, 1, 0.42]
        st.windowButtons, st.windowClose = "frame", "default"  # (the buttons the tint's; the X the game's own: white)
        L.Apply()
        look = A.FrameLook()
        assert list(look.buttons.values()) == [0.55, 1, 0.42] and list(look.close.values()) == [1, 1, 1]
        lua.execute("UnitFactionGroup = function() return 'Alliance' end")
        st.windowTint = "faction"
        L.Apply()
        assert list(A.FrameLook().border.values()) == [0.5, 0.65, 1]
        A.SetFrameLook("Plugin", lua.eval("{ border = { 0.1, 0.2, 0.3 } }"))  # (another addon's, over it)
        assert list(A.FrameLook().border.values()) == [0.1, 0.2, 0.3]
        A.SetFrameLook("Plugin", None)
        assert list(A.FrameLook().border.values()) == [0.5, 0.65, 1]
        # the route
        st.zoom = 600
        N.Clear()
        N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
        for t in range(3):
            lua.execute(f"AGPS_T = {1960 + t}")
            G.Update()
        assert N.route and blue in _colors(_lines(lua))
        st.routeColor = "rainbow"
        L.Apply()
        lua.execute("AGPS_T = 1964")
        G.Update()
        assert len(_colors(_lines(lua)) & rainbow) >= 3 and blue not in _colors(_lines(lua))
        A.SetRouteLook("Plugin", lua.eval("{ color = { 1, 0.82, 0 } }"))  # (another addon's, over it)
        lua.execute("AGPS_T = 1965")
        G.Update()
        assert "1.00,0.82,0.00" in _colors(_lines(lua))
        A.SetRouteLook("Plugin", None)
        st.routeColor = "blue"
        L.Apply()
        lua.execute("AGPS_T = 1966")
        G.Update()
        assert blue in _colors(_lines(lua)) and not (_colors(_lines(lua)) & rainbow - {blue})
    finally:
        lua.execute("UnitFactionGroup = AGPS_OLD_FACTION")
        A.SetFrameLook("Plugin", None)
        A.SetRouteLook("Plugin", None)
        st.windowTint, st.windowButtons, st.windowClose, st.routeColor = defaults
        L.Apply()
        N.Clear()


def test_arriving_at_the_last_stop_brings_confetti_or_fireworks(game):
    # (asked 2026-11-04: "integrate the options from the plugin for confetti and fireworks only into the base AzerothGPS. Put
    # a dropdown to select Confetti (default), Fireworks, or None") over the map at the trip's last stop only, then gone
    lua, ns = game
    L, N, st = ns.Looks, ns.Nav, ns.settings.gps
    E = L.Effects
    assert st.arrivalEffect == "confetti" and lua.eval("rawequal")(N.arriveHooks.AzerothGPS, L.OnArrive)
    while E.used > 0:  # (the earlier tests' trips reached their last stops too: their confetti put away first)
        E.Update(1)
    try:
        L.OnArrive(lua.eval("{ last = false }"))  # (a stop on the way: nothing)
        assert E.used == 0
        L.OnArrive(lua.eval("{ last = true }"))
        assert E.used == E.CONFETTI.n and E.frame._shown
        for _ in range(60):
            E.Update(0.1)
        assert E.used == 0 and not E.frame._shown  # (all fallen and faded: put away)
        st.arrivalEffect = "fireworks"
        L.OnArrive(lua.eval("{ last = true }"))
        assert E.used == E.FIREWORKS.bursts * E.FIREWORKS.n
        for _ in range(40):
            E.Update(0.1)
        assert E.used == 0
        st.arrivalEffect = "none"
        L.OnArrive(lua.eval("{ last = true }"))
        assert E.used == 0
        # (in the game a hidden frame sized only by its anchors reads 0 x 0, and the effect frame is
        # hidden until it plays: measured there, Try It and arriving showed nothing)
        E.frame.GetWidth = lua.eval("function(s) return s._shown and 400 or 0 end")
        E.frame.GetHeight = lua.eval("function(s) return s._shown and 400 or 0 end")
        try:
            assert not E.frame._shown
            assert L.Play("confetti") and E.used == E.CONFETTI.n and E.frame._shown
        finally:
            E.frame.GetWidth, E.frame.GetHeight = None, None
            while E.used > 0:
                E.Update(1)
        # (the options: the dropdown and Try It)
        ns.Options.Show()
        texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text]
        assert "Celebration" in texts and "Try It" in texts and "Route color" in texts and "Frame color" in texts
    finally:
        st.arrivalEffect = "confetti"
        while E.used > 0:
            E.Update(1)
        lua.globals().AzerothGPSOptions.Hide(lua.globals().AzerothGPSOptions)


def test_a_legendary_charm_hangs_from_the_logo_and_swings(game):
    # (asked 2026-11-04: "Add all weapon charms too, default off") a charm on a string from under the logo, its art ours
    # (Media\Charms), swinging out of a turn and settling; swinging off: still; none: gone. Another addon's charm (API
    # 19's AddCharm) joins the list, checked as data
    lua, ns = game
    A, L, st = lua.globals().AzerothGPS, ns.Looks, ns.settings.gps
    C, M = L.CharmState, L.Motion
    assert st.charm == "none" and not C.frame._shown
    keys = [c.key for c in L.Charms().values()]
    assert keys[:8] == ["ashbringer", "frostmourne", "warglaive", "thoridal", "gorehowl", "corruptedash", "quelserrar",
                        "queldelar"]
    assert "thunderfury" not in keys and "sulfuras" not in keys
    for key in keys[:8]:  # (every one's art there, at each scale)
        for k in (1, 2, 3):
            assert (ADDON / "Media" / "Charms" / f"charm_{key}_s_{k}x.tga").is_file(), (key, k)
    real, rand = M.Sample, L.Random
    try:
        L.Random = lua.eval("function() return 0.5 end")  # (no random bumps: math.random differs by OS)
        st.charm = "frostmourne"
        L.Apply()
        assert C.frame._shown and str(C.tex._tex) == r"Interface\AddOns\AzerothGPS\Media\Charms\charm_frostmourne_s_1x"
        assert C.angle == 0
        M.Sample = lua.eval("function() end")  # (the character's motion as set here)
        # (its bumps are math.random's, under Lua 5.1 the C library's rand() the whole test run shares: the tests run
        # before it decided whether it swung past 0.05, 0.048 once a new harness test came before it, #349)
        lua.execute("math.randomseed(349)")
        M.speed, M.turn, M.moving, M.kick = 7.0, 1.5, True, 0.0
        for _ in range(30):
            C.Update(1 / 30)
        assert C.angle > 0.05  # (turning left: swung out of the turn, to the right: + is right)
        M.speed, M.turn, M.moving = 0.0, 0.0, False
        for _ in range(600):
            C.Update(1 / 30)
        assert C.angle == 0 and C.vel == 0  # (settled)
        st.charmSwing = False
        M.speed, M.turn, M.moving = 7.0, 1.5, True
        for _ in range(30):
            C.Update(1 / 30)
        assert C.angle == 0
        st.charm = "none"
        L.Apply()
        assert not C.frame._shown
        # another addon's
        good = lua.eval("""{ key = 'testblade', name = 'Test Blade', file = 'Interface\\\\AddOns\\\\Other\\\\charm_testblade',
          art = { w = 10, h = 20, frames = 6, cols = 3, ax = 5, ay = 0, tex = { { 64, 64 }, { 128, 128 }, { 128, 128 } } } }""")
        assert A.AddCharm("Other", good) is True
        assert A.AddCharm("Other", lua.eval("{ key = 'frostmourne', file = 'x', art = good.art }") if False else
                          lua.eval("{ key = 'frostmourne', file = 'x', art = { w = 1, h = 1, frames = 1, tex = {} } }")) is False
        assert A.AddCharm("Other", lua.eval("{ key = 'broken', file = 'x', art = { w = 1, h = 1, frames = 1, tex = { { 2, 2 } } } }")) is False
        assert [c.key for c in L.Charms().values()][-1] == "testblade"
        st.charm = "testblade"
        L.Apply()
        assert C.frame._shown and str(C.tex._tex) == r"Interface\AddOns\Other\charm_testblade_1x"
    finally:
        M.Sample, L.Random = real, rand
        st.charm, st.charmSwing = "none", True
        L.added.testblade = None
        L.Apply()


def test_road_tolerance_keeps_to_the_roads_or_cuts_across(game):
    # (asked 2026-11-04: "a 'Road Tolerance' slider that defaults to 0 (the current amount)... below zero would prefer
    # the road more and more while a positive value will recommend more and more straight paths ignoring roads") the
    # road-keeping factors' extra over 1 scaled: exactly as before at 0, up to 5 times at -10, none at +10; the route
    # from Brill to the fields northwest of it off the roads more as the tolerance goes up
    lua, ns = game
    N, R, st = ns.Nav, ns.Router, ns.settings.gps
    assert st.roadTolerance == 3  # (the default since 1.4.0: +3, Core.lua's roadTolerance140)
    st.roadTolerance = 0
    assert R.RoadFactor(R.OFFROAD_PENALTY) == R.OFFROAD_PENALTY
    try:
        st.roadTolerance = 10
        assert R.RoadFactor(1.25) == 1 and R.RoadFactor(2) == 1
        st.roadTolerance = -10
        assert R.RoadFactor(1.25) == pytest.approx(2.25) and R.RoadFactor(2) == pytest.approx(6)
        st.roadTolerance = 5
        assert R.RoadFactor(2) == pytest.approx(1.5)
        st.roadTolerance = 99  # (kept in its range)
        assert R.RoadFactor(2) == 1

        def offroad(tol):
            st.roadTolerance = tol
            N.Clear()
            lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")
            N.SetStops(lua.eval("{ { x = 1700, y = 700, cont = 0, name = 'Fields' } }"), False, "red")
            r = N.Route(2254.0, 293.0, 0)
            off = 0.0
            for part in r.parts.values():
                pts, kinds = part.pts, part.kinds
                for i in range(1, len(kinds) + 1):
                    if kinds[i] == R.KIND_OFFROAD:
                        off += math.hypot(pts[2 * i + 1] - pts[2 * i - 1], pts[2 * i + 2] - pts[2 * i])
            return off
        keep, usual, cut = offroad(-10), offroad(0), offroad(10)
        assert keep < usual < cut and cut > 2 * usual, (keep, usual, cut)
    finally:
        st.roadTolerance = 3
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Update()


def test_a_route_just_asked_for_gets_the_warm_ups_bigger_slices(game):
    # (QA v116-ov-a, 2026-10-07: from Lakeshire's town hall to Darkshire the long way by the roads showed for about
    # 20 s before the walk across country landed: the walk search, about 1.5 s of work, had 1 ms a frame) for
    # FRESH_SECONDS after the stops change, the background searches get the warm-up's slices; then 1 ms again
    lua, ns = game
    G, N, R = ns.GPS, ns.Nav, ns.Router
    lua.execute("""
      AGPS_BUDGETS = {}
      local R = AGPS_NS.Router
      AGPS_REAL_PUMP, AGPS_REAL_WORK, AGPS_REAL_WARMING = R.Pump, R.HasWork, R.Warming
      AGPS_REAL_DPS, AGPS_DPS = debugprofilestop, 0
      debugprofilestop = function() return AGPS_DPS end -- (the frames' clock: 16 ms a frame, below)
      R.HasWork = function() return true end
      R.Warming = function() return false end
      R.Pump = function(deadline) AGPS_BUDGETS[#AGPS_BUDGETS + 1] = deadline - AGPS_DPS return false end
    """)

    def frame():
        lua.execute("AGPS_DPS = AGPS_DPS + 16")
        G.PumpSearches()
    try:
        N.SetStops(lua.eval("{ { x = -10564.7, y = -1170.7, cont = 0, name = 'Darkshire' } }"), False, "red")
        assert N.Fresh()
        frame()
        frame()  # (a frame since the last: its time known)
        lua.execute("AGPS_T = AGPS_T + %d" % (N.FRESH_SECONDS + 1))
        assert not N.Fresh()
        frame()
        b = lua.eval("AGPS_BUDGETS")
        assert b[2] > 1.5 and b[3] <= 1.01, list(b.values())  # (bigger while fresh; 1 ms after)
        N.Clear()
        assert not N.Fresh()
        # (issue #316) settled before FRESH_SECONDS (shown, no work left for CHECK_QUIET): a route kept up as the player
        # walks, 1 ms again
        lua.execute("AGPS_NS.Router.HasWork = function() return false end")
        N.SetStops(lua.eval("{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"), False, "red")
        N.Route(float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]")), 0)
        assert N.route and N.Fresh()
        lua.execute("AGPS_T = AGPS_T + %f" % (N.CHECK_QUIET + 0.1))
        assert not N.Checking()
        assert not N.Fresh()
        N.Clear()
    finally:
        lua.execute("""
          local R = AGPS_NS.Router
          R.Pump, R.HasWork, R.Warming = AGPS_REAL_PUMP, AGPS_REAL_WORK, AGPS_REAL_WARMING
          debugprofilestop = AGPS_REAL_DPS
        """)


def test_a_new_route_still_being_checked_shows_faded_with_a_line(game):
    # (asked 2026-10-08, "Show it, marked": from Lakeshire's town hall to Darkshire the long way by the roads, 7.6k yd,
    # shows first and the walk over the pass, 1.8k, lands a few seconds on, QA v116-ov-a) meanwhile the route is drawn
    # faded and the directions say it's being checked, in one of N.CHECKING_LINES; settled, neither, and not again for
    # these stops when a reroute's searches run
    import time
    lua, ns = game
    G, N, R = ns.GPS, ns.Nav, ns.Router
    clock = lambda: time.perf_counter() * 1000.0
    lines, warm, sync, fun = N.CHECKING_LINES, R.WARM, R.SYNC_WALKS, N.FUN
    try:
        N.FUN = True  # (the tests' default: the plain lines)
        lua.execute("AGPS_LEVEL = 60")  # (no zone too high: the route isn't held for the keep-it question)
        N.CHECKING_LINES = lua.eval('{ "Greasing the goblins for a shortcut..." }')
        R.WARM, R.SYNC_WALKS = True, False
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -9227.7, -2201.5, 0")
        N.ResetCityTrack()
        R.WarmUp(0, -9227.7, -2201.5)
        while R.HasWork():
            R.Pump(clock() + 50, clock)
        N.SetStops(lua.eval("{ { x = -10564.7, y = -1170.7, cont = 0, name = 'Darkshire' } }"), False, "red")
        seen_checking, seen_settled, faded = False, False, False
        for f in range(1, 60 * 15):
            lua.execute("AGPS_T = AGPS_T + 1/60")
            done, fixed = R.Pump(clock() + 5, clock)
            if done:
                N.SearchDone(fixed)
            if f % 15:
                continue
            status = N.Status(-9227.7, -2201.5, 0) or ""
            if N.route is not None and N.Checking():
                seen_checking = True
                assert "Greasing the goblins for a shortcut..." in status, status
                G.Follow()
                G.Update()
                faded = faded or G.routeFade == G.CHECKING_ALPHA
            elif N.route is not None and seen_checking:
                seen_settled = True
                assert "Greasing" not in status and N.route.totalYards < 2600, status
                G.Update()
                assert G.routeFade == 1
                break
        assert seen_checking and faded and seen_settled
        N.route.pending = True  # (a reroute's search as the player walks on: not faded again for these stops)
        assert not N.Checking()
        N.CHECKING_LINES = lua.eval("{}")
        N.SetStops(lua.eval("{ { x = -10564.7, y = -1170.7, cont = 0, name = 'Darkshire' } }"), False, "red")
        assert N.CheckingText() == N.CHECKING_TEXT  # (no lines picked: the plain one)
    finally:
        N.CHECKING_LINES, R.WARM, R.SYNC_WALKS, N.FUN = lines, warm, sync, fun
        lua.execute("AGPS_LEVEL = nil")
        N.Clear()
        while R.HasWork():
            R.Pump(clock() + 50, clock)


def _walk_route(lua, ns, x, y, tx, ty, tz=None, step=1.2, cont=0):
    """The player walked along the route from (x, y) to the stop, the floor followed at each step: [(s, z)]."""
    N, G, T = ns.Nav, ns.GPS, ns.Turns
    N.ResetCityTrack()
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, {cont}")
    zs = f", z = {tz}" if tz is not None else ""
    N.SetStops(lua.eval(f"{{ {{ x = {tx}, y = {ty}, cont = {cont}, name = 'there'{zs} }} }}"), False, "red")
    G.Follow()
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    path = T.Path(N.route)
    out, s = [], 0.0
    while s < path.total:
        s = min(s + step, path.total)
        px, py = T.PointAt(path, s)
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {px}, {py} AGPS_T = AGPS_T + 0.3")
        out.append((s, N.TrackCityZ(cont, px, py)))
    return out, path


def test_beside_the_cellar_stairs_the_ground_floor_is_kept(game):
    # (QA, 2026-10-07, c116-inn-c / v115-r-inn: by Brill inn's cellar stairwell the floor followed
    # stepped down the stairs' upper flight, 2.7 yd off, to the landing and the cellar, though the player stayed on
    # the ground floor; routes then planned from the cellar) in a building another floor's road is taken only
    # standing on it
    lua, ns = game
    N = ns.Nav
    try:
        # (Brill's square into the inn, its ground floor: the upstairs floor is over the spot, its road nearer since
        # issue #842's inn roads, which keep off the ground under the second flight)
        steps, _ = _walk_route(lua, ns, 2235.0, 260.0, 2262.0, 241.0, tz=34.5)
        assert abs(steps[-1][1] - 34.5) < 1
        lua.execute("AGPS_POS[1], AGPS_POS[2] = 2280.0, 244.7 AGPS_T = AGPS_T + 1")
        assert abs(N.TrackCityZ(0, 2280.0, 244.7) - 34.5) < 1  # (it went 30.7, the landing)
        lua.execute("AGPS_T = AGPS_T + 1")
        assert abs(N.TrackCityZ(0, 2280.0, 244.7) - 34.5) < 1  # (and then the cellar)
    finally:
        N.Clear()
        N.ResetCityTrack()


def test_up_a_spiral_stair_the_floor_is_followed_to_the_top(game):
    # (a test walk, 2026-10-08: twice 9 yd short of Orgrimmar's Wind Rider Master, the floor followed 38 under his
    # platform at 61.7) the tower's spiral stair is one road whose turns lie over each other; HeightsNear gave each road
    # its nearest point, always the lowest turn's, so the floor followed fell back down a turn and stayed there: the
    # arrow pointed back down the stairs and the master was never reached. Each stretch near gives its height now
    lua, ns = game
    N = ns.Nav
    try:
        steps, _ = _walk_route(lua, ns, 1653.0, -4354.3, 1676.1, -4317.4, tz=61.7, step=1.75, cont=1)
        zs = [z for _, z in steps if z is not None]
        assert zs and abs(zs[-1] - 61.7) < 3, zs[-10:]
        assert all(b > a - 3 for a, b in zip(zs, zs[1:])), zs  # (never down a turn on the way up)
    finally:
        N.Clear()
        N.ResetCityTrack()


def test_down_the_cellar_stairs_the_floor_is_followed(game):
    # (the rule above doesn't stop the floor following a player down a building's stairs for real: walked on them)
    lua, ns = game
    N = ns.Nav
    try:
        steps, path = _walk_route(lua, ns, 2235.0, 260.0, 2283.0, 247.0, tz=27.5)  # (the cellar, by its road)
        zs = [z for _, z in steps if z is not None]
        assert zs and abs(zs[0] - 34.5) < 1 and abs(zs[-1] - 27.5) < 1, zs
    finally:
        N.Clear()
        N.ResetCityTrack()


def _walk_off(lua, ns, pts, off, cont=0, step=0.5):
    """The player walked along the points `off` yards to the left of their line, the floor followed every `step` yards
    (at the game's pace: TRACK_EVERY's quarter second a look, at a run 1.75 yd)."""
    N = ns.Nav
    zs = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        n = max(1, round(math.hypot(bx - ax, by - ay) / step))
        L = math.hypot(bx - ax, by - ay) or 1
        for j in range(n):
            x = ax + (bx - ax) * j / n - (by - ay) / L * off
            y = ay + (by - ay) * j / n + (bx - ax) / L * off
            lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x}, {y} AGPS_T = AGPS_T + 0.26")
            zs.append(N.TrackCityZ(cont, x, y))
    return zs


def _route_pts(r):
    return [(r.pts[i], r.pts[i + 1]) for i in range(1, len(r.pts) + 1, 2)]


def test_down_brill_inns_stairs_a_yard_off_their_middle_the_ground_floor_is_followed(game):
    # (reported 2026-11-05, screenshot: outside Brill inn's door the route went in, up the stairs and back down; the
    # floor followed was its upstairs, the mage and priest trainers', 41.5) its stairs end 3 yd over the ground floor, a
    # yard from it, and the passage runs beside them: walked a yard off their middle, the floor followed stayed at their
    # foot, over TRACK_STEP from the passage, and went back up them beside it. Off stairs onto a floor stood on it's
    # taken up to TRACK_STAIR_OFF; outdoors with no road of the floor followed near, it's let go
    lua, ns = game
    N, R = ns.Nav, ns.Router
    lua.execute("AGPS_IN_REAL = IsIndoors AGPS_IN = true IsIndoors = function() return AGPS_IN end AGPS_T = AGPS_T + 10")
    try:
        outside, trainer = (2246.9, 263.3), (2259.0, 235.9)
        up = R.Route(0, outside[0], outside[1], trainer[0], trainer[1], lua.eval("{ z = 34.5, tz = 41.2 }"))
        down = R.Route(0, trainer[0], trainer[1], outside[0], outside[1], lua.eval("{ z = 41.2, tz = 34.5 }"))
        for off in (0.5, 0.8):
            for step in (0.5, 1.0, 1.75):
                N.ResetCityTrack()
                zs = _walk_off(lua, ns, _route_pts(up), 0.0)
                assert abs(zs[-1] - 41.3) < 1, (off, step, zs[-10:])  # (up on its middle: followed up)
                zs = _walk_off(lua, ns, _route_pts(down), off, step=step)
                assert abs(zs[-1] - 34.5) < 1, (off, step, zs[-30:])  # (it stayed 41.5)
        # outdoors by the door with the floor followed still upstairs (walked down 3 yd off the stairs' middle, which
        # still loses it; 2.5 did before issue #842's inn roads): let go there, and a route on west along the road
        # doesn't go into the inn
        N.ResetCityTrack()
        _walk_off(lua, ns, _route_pts(up), 0.0)
        zs = _walk_off(lua, ns, _route_pts(down), 3.0)
        assert zs[-1] > 40  # (the case this part is about)
        lua.execute("AGPS_IN = false AGPS_T = AGPS_T + 0.3")
        assert abs(N.TrackCityZ(0, outside[0], outside[1]) - 34.5) < 1
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {outside[0]}, {outside[1]}, 0")
        N.SetStops(lua.eval("{ { x = 2205.0, y = 330.0, cont = 0, name = 'west' } }"), False, "red")
        r = N.Route(outside[0], outside[1], 0)
        p1 = r.parts[1]
        fz = [p1.fz[i] for i in range(1, len(p1.fz) + 1)] if p1.fz else []
        assert not any(z and z > 36 for z in fz), fz  # (it went up to 41.5 and back down)
        # (indoors, upstairs: the floor followed stays there)
        N.ResetCityTrack()
        lua.execute("AGPS_IN = true")
        zs = _walk_off(lua, ns, _route_pts(up), 0.0)
        lua.execute("AGPS_T = AGPS_T + 0.3")
        assert abs(N.TrackCityZ(0, trainer[0], trainer[1]) - 41.3) < 1
    finally:
        lua.execute("IsIndoors = AGPS_IN_REAL")
        N.Clear()
        N.ResetCityTrack()


def test_a_dungeons_dotted_way_takes_the_color_picked_on_its_map(game):
    # (issue #16) a picker at the dungeon map's top right, not in Options: the route's colors (Nav.MARKER_COLORS)
    # and Gold, the old look, the default; the pick saved in the settings and the dotted usual way drawn in it
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    st = ns.settings.gps
    names = [e.name for e in G.DUNGEON_PATH_COLORS.values()]
    assert names[0] == "Gold" and {"Yellow", "Orange", "Green", "Blue"} <= set(names)
    assert len(names) == len(N.MARKER_COLORS) + 1
    assert G.DungeonPathColor("nonsense").key == "gold" and st.dungeonPathColor == "gold"
    box = G.pathColorBox
    N.Clear()
    G.Follow()
    G.Update()
    assert not box._shown  # (not on the land's map)

    def dotted(c):
        want = "%.2f,%.2f,%.2f" % (c[1], c[2], c[3])
        return _shown(lua, lambda w: getattr(w, "_vc", None) == want)

    try:
        G.ShowInstance(20036)  # (the Deadmines' map)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert box._shown
        gold = G.DungeonPathColor("gold")
        assert dotted(gold.color) or dotted(gold.next)
        assert any("|cffffc726Gold: the usual way through|r" in t for t in _texts(lua))
        box._scripts.OnClick(box)  # (the list opens)
        assert G.pathColorList._shown
        row = next(r for r in G.pathColorList.rows.values() if r.key == "blue")
        row._scripts.OnClick(row)
        assert not G.pathColorList._shown and st.dungeonPathColor == "blue"
        assert box.swatch._tex == "color:%.2f,%.2f,%.2f" % tuple(N.MARKER_COLORS[6][k] for k in (1, 2, 3))
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        blue = G.DungeonPathColor("blue")
        assert dotted(blue.color) or dotted(blue.next)
        assert not dotted(gold.color) and not dotted(gold.next)
        # (issue #18: the note under the map names the color picked, in it, not Gold)
        note = [t for t in _texts(lua) if "the usual way through" in t]
        assert note and all("Gold" not in t for t in note), note
        assert any(G.PathColorNote(blue) in t and "Blue: the usual way through" in t for t in note), note
        # (inside, where the game hides the position: the same map, the same picker)
        assert G.ShowsPathColorPicker(20036, None, st)
        assert not G.ShowsPathColorPicker(20036, 1429, st) and not G.ShowsPathColorPicker(None, None, st)
    finally:
        st.dungeonPathColor = "gold"
        G.Follow()
        G.Update()
    assert not box._shown


def test_show_routes_off_hides_a_dungeons_dotted_way(game):
    # (asked 2026-11-16: "remove the boss route button ... replace it with Show Routes and with this on shows routes in
    # dungeons like we do now (default) with it off it hides all the dotted path lines in the dungeon") the map menu's
    # Show Routes, on by default: off, no dotted way, its note or its color picker; Boss Route gone from the menu
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    st = ns.settings.gps
    ids = [t.id for t in G.QUICK.values()]
    assert "bossRoute" not in ids and "dungeonPaths" in ids
    t = next(t for t in G.QUICK.values() if t.id == "dungeonPaths")
    assert t.label == "Show Routes" and t.key == "showDungeonPaths" and st.showDungeonPaths is True
    gold = G.DungeonPathColor("gold")

    def dotted():
        return any(_shown(lua, lambda w, c=c: getattr(w, "_vc", None) == "%.2f,%.2f,%.2f" % (c[1], c[2], c[3]))
                   for c in (gold.color, gold.next))

    N.Clear()
    try:
        G.ShowInstance(20036)  # (the Deadmines' map)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert dotted() and G.pathColorBox._shown
        st.showDungeonPaths = False
        G.Redraw()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert not dotted() and not G.pathColorBox._shown
        assert not any("the usual way through" in x for x in _texts(lua))
    finally:
        st.showDungeonPaths = True
        G.Follow()
        G.Update()
def test_removing_the_only_stop_leaves_the_map_where_it_is(game):
    # (asked 2026-11-16 for 1.3.5: "when right click removing a stop and its the only stop, don't snap back to the
    # player's position") a stop double-clicked and not confirmed yet, removed: the map stays on the spot looked at
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))

    def tick(n):
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()

    N.Clear()
    try:
        G.LookAt(0, x + 300, y + 300)
        tick(2)
        G.AddStopAt(x + 300, y + 300, "Spot", 0)
        tick(1)
        G.RemovePending(1)
        tick(2)
        assert G.IsFree()
    finally:
        G.Follow()
        G.Update()


def test_a_stop_made_from_a_round_icon_is_round_too(game):
    # (asked 2026-11-16 for 1.3.5: "with double clicking and routing to a rounded icon, it 'selects' and shows a square
    # icon instead. change to a rounded icon when rounded is enabled") a stop with a game icon (a trainer's, a herb's):
    # its marker round with its ring, as the icon on the map; square with Round icons off; a plain marker as it was
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    st = ns.settings.gps
    herb = "Interface\Icons\INV_Misc_Herb_07"
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))

    def marker():
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Redraw()
        G.Update()
        return next(b for b in G.stopPins.values() if b._shown and b.stopIndex == 1)

    try:
        N.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'Peacebloom', tex = '%s' } }"
                            % (x + 40, y + 40, herb.replace("\\", "\\\\"))), False, "red")
        b = marker()
        assert b.icon.roundOn and b.icon.ring._shown
        st.roundIcons = False
        b = marker()
        assert not b.icon.roundOn and not (b.icon.ring and b.icon.ring._shown)
        st.roundIcons = True
        N.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'Spot' } }" % (x + 40, y + 40)), False, "red")
        b = marker()  # (a plain marker: no round icon's ring or crop left on the reused pin)
        assert not b.icon.roundOn and not (b.icon.ring and b.icon.ring._shown)
    finally:
        st.roundIcons = True
        N.Clear()


def test_the_show_hide_key_can_be_kept_from_showing_the_map_in_combat(game):
    # (issue #20) keyBlockedInCombat: in combat the key doesn't show the map (an accidental press mid-fight); it still
    # hides a map already showing, and out of combat, or with the option off, it toggles as before
    lua, ns = game
    gps = ns.settings.gps
    toggle = lua.globals().AzerothGPS_ToggleMap
    was = gps.shown, gps.keyBlockedInCombat
    try:
        assert gps.keyBlockedInCombat is True  # (on by default since 2026-11-14, asked)
        gps.keyBlockedInCombat = False
        ns.inCombat = True
        gps.shown = False
        toggle()
        assert gps.shown is True  # (off + combat: toggles)
        gps.keyBlockedInCombat = True
        gps.shown = False
        toggle()
        assert gps.shown is False  # (on + combat: stays hidden)
        gps.shown = True
        toggle()
        assert gps.shown is False  # (on + combat, showing: the key hides it)
        ns.inCombat = False
        toggle()
        assert gps.shown is True  # (on, out of combat: toggles)
        toggle()
        assert gps.shown is False
        # (the Quick Search key too, asked 2026-11-14: in combat it doesn't show the map)
        ns.inCombat = True
        assert ns.GPS.QuickSearch() is False and gps.shown is False
    finally:
        ns.inCombat = False
        gps.shown, gps.keyBlockedInCombat = was
        ns.Options.Apply()


def test_a_quest_areas_parts_from_its_fill(game):
    """Layers.AreaParts: rectangles touching (or within AREA_PART_GAP) are one part; a spot inside each part's largest
    rectangle, the biggest part first; one part: nil."""
    lua, ns = game
    L = ns.Layers
    r = lambda *v: lua.table(*v)
    one = lua.table(r(0.0, 0.0, 50.0, 50.0, 1), r(50.0, 0.0, 60.0, 20.0, 1))
    assert L.AreaParts(one) is None
    two = lua.table(r(0.0, 0.0, 50.0, 50.0, 1), r(55.0, 0.0, 60.0, 20.0, 1), r(500.0, 500.0, 520.0, 530.0, 1))
    parts = L.AreaParts(two)
    got = [(parts[i].x, parts[i].y, parts[i].cont) for i in (1, 2)]
    assert got == [(25.0, 25.0, 1), (510.0, 515.0, 1)] and parts[3] is None


# The GPS map as the game's minimap (1.2.0, asked 2026-11-08): the game's own Minimap kept over the map's canvas with
# its ground hidden, the map's view matching it. A stand-in Minimap that records what's done to it.
MM_SETUP = """
  AGPS_MM = { radius = 116.5, zoom = 1, ground = true, masks = {}, grounds = {} }
  MinimapContainer = NewWidget("Frame", "MinimapContainer")
  MinimapContainer.GetCenter = function() return 1800, 950 end -- (the screen's top right)
  Minimap._parent = MinimapContainer
  Minimap.GetCenter = function() return 1800, 950 end -- (in its container's middle, as the game has it)
  Minimap._w, Minimap._h = 198, 198
  Minimap._pts = { CENTER = { "CENTER", MinimapContainer, "CENTER", 0, 0 } }
  Minimap.GetNumPoints = function(s) local n = 0 for _ in pairs(s._pts) do n = n + 1 end return n end
  Minimap.GetPoint = function(s, i)
    local k = 0
    for _, p in pairs(s._pts) do k = k + 1 if k == i then return unpack(p) end end
  end
  Minimap.GetWidth = function(s) return s._w end
  Minimap.GetHeight = function(s) return s._h end
  Minimap.GetZoom = function() return AGPS_MM.zoom end
  Minimap.SetMaskTexture = function(_, t) table.insert(AGPS_MM.masks, t) AGPS_MM.mask = t end
  MinimapCompassTexture = NewWidget("Texture", "MinimapCompassTexture")
  AGPS_MM.blobs = {}
  for _, k in ipairs({ "Quest", "Task", "Arch" }) do
    for _, part in ipairs({ "Inside", "Outside", "Ring" }) do
      Minimap["Set" .. k .. "Blob" .. part .. "Alpha"] = function(_, a) AGPS_MM.blobs[k .. part] = a end
    end
  end
  C_Minimap.GetViewRadius = function() return AGPS_MM.radius end
  C_Minimap.GetDrawGroundTextures = function() return AGPS_MM.ground end
  C_Minimap.SetDrawGroundTextures = function(v) AGPS_MM.ground = v table.insert(AGPS_MM.grounds, v) end
  AGPS_MM_CVAR = "0"
  AGPS_OLD_GETCVAR = GetCVar
  GetCVar = function(n) if n == "rotateMinimap" then return AGPS_MM_CVAR end end
"""
def test_party_members_show_on_the_minimap_square(minimap):
    # (asked 2026-11-17: "party member icons don't show on our square minimap? they should", with the dev addon's fake
    # party) the GPS map as the minimap square draws our party dots too: members fed as the dev addon's fake party
    # feeds them (GPS.party.io.members swapped, no unit), named on hover; Show party off: none. One of the game's group
    # (read from a unit) has the game's blip over the square with its ground hidden: not ours too (no double); under
    # the all-clear mask, and opened out into the window, ours
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    old_members = G.party.io.members
    lua.execute("""
      AGPS_PARTY = { party1 = { 2250, 305 } }
      UnitExists = function(u) return AGPS_PARTY[u] ~= nil end
      UnitIsUnit = function(a, b) return a == b end
      IsInRaid = function() return false end
      UnitClass = function(u) return "Mage", "MAGE" end
      AGPS_POS_REAL = UnitPosition
      UnitPosition = function(u)
        local p = AGPS_PARTY[u]
        if p then return p[1], p[2], 0, 0 end
        return AGPS_POS_REAL(u)
      end
    """)

    def dots():
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        return sorted(w.name for w in lua.eval("AGPS_WIDGETS").values() if w.dot and w._shown)

    try:
        st.showParty = True
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode() and G.MinimapHideMode() == "ground"
        # the game's own group: its blip on the Minimap over the square, ours left off
        assert dots() == []
        # the dev addon's fake party: { name, class, cont, x, y } through the hook, on the square
        G.party.io.members = lua.eval("""function() return {
          { name = "Fakey", class = "PRIEST", cont = 0, x = AGPS_POS[1] + 20, y = AGPS_POS[2] - 10 },
          { name = "Faraway", class = "MAGE", cont = 0, x = AGPS_POS[1] + 5000, y = AGPS_POS[2] },
        } end""")
        assert dots() == ["Fakey"]  # (only those in the square's view)
        b = next(w for w in lua.eval("AGPS_WIDGETS").values() if w.dot and w._shown)
        lua.globals().AGPS_B = b
        lua.execute("AGPS_B.IsMouseOver = function() return true end")
        try:
            assert G.MinimapTipAt() == "Fakey"
        finally:
            lua.execute("AGPS_B.IsMouseOver = nil")
        st.showParty = False
        assert dots() == []
        st.showParty = True
        # the game's group under the all-clear mask (its blips may be clipped there): ours
        G.party.io.members = old_members
        st.replaceMinimapHide = "mask"
        G.ApplySettings()
        assert dots() == ["Tester"]
        # opened out into the usual window: the map's own dots, as ever
        st.replaceMinimapHide = "ground"
        G.ApplySettings()
        assert dots() == []
        G.SetMinimapExpanded(True)
        assert not G.MinimapMode() and dots() == ["Tester"]
        G.SetMinimapExpanded(False)
    finally:
        G.party.io.members = old_members
        st.showParty = True
        lua.execute("AGPS_PARTY = {} UnitPosition = AGPS_POS_REAL")


MM_TEARDOWN = """
  for _, k in ipairs({ "GetNumPoints", "GetPoint", "GetWidth", "GetHeight", "GetZoom", "SetMaskTexture", "SetAlpha" }) do Minimap[k] = nil end
  AzerothGPSFrame.SetFrameStrata, AzerothGPSFrame.IsMouseOver = nil, nil
  Minimap._parent, Minimap._w, Minimap._h, Minimap._pts = nil, nil, nil, {}
  for _, k in ipairs({ "Quest", "Task", "Arch" }) do
    for _, part in ipairs({ "Inside", "Outside", "Ring" }) do Minimap["Set" .. k .. "Blob" .. part .. "Alpha"] = nil end
  end
  C_Minimap.GetViewRadius, C_Minimap.GetDrawGroundTextures, C_Minimap.SetDrawGroundTextures = nil, nil, nil
  GetCVar = AGPS_OLD_GETCVAR
  InCombatLockdown = function() return false end
  GetPlayerFacing = function() return 0 end
"""


@pytest.fixture
def minimap(game):
    lua, ns = game
    st = ns.settings.gps
    lua.execute(MM_SETUP)
    # (the options closed: a test before it in the same process may have left them open (Options.Show), which keeps the
    # grown-out map in use and makes Options.Toggle close them; run in parallel, any test can come before)
    opts = lua.eval("AzerothGPSOptions")
    if opts:
        opts.Hide(opts)
    # (the minimap given back while the map's grown out of the square, as before 2026-11-15; the square kept as it is,
    # the option's default, in the tests that turn it on)
    st.replaceMinimapKeepSquare = False
    yield lua, ns
    st.replaceMinimap = False
    lua.execute("InCombatLockdown = function() return false end")
    ns.GPS.ApplySettings()
    st.replaceMinimapHide = "ground"
    st.replaceMinimapSize = "small"
    st.replaceMinimapKeepSquare = True
    lua.execute(MM_TEARDOWN)
    ns.GPS.ApplySettings()


def _view(lua, ns):
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()
    x, y, cont, rot, s, half = ns.GPS.ViewState()
    return x, y, rot, half / s


def test_the_minimap_option_puts_the_minimap_over_the_map_and_matches_its_view(minimap):
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    frame = lua.eval("AzerothGPSFrame")
    st.replaceMinimap = True
    G.ApplySettings()
    assert G.MinimapMode()
    # the Minimap over the map's canvas, its size (the square less the border), its ground off, a square mask
    p = lua.eval("Minimap._pts.CENTER")
    lua.globals().AGPS_A = G.mmAnchor
    assert p[1] == "CENTER" and p[3] == "CENTER" and lua.eval("Minimap._pts.CENTER[2] == AGPS_A")
    a = lua.eval("AGPS_A._pt")  # (the anchor: the square's place, as the window's)
    assert a[1] == "TOPRIGHT" and a[4] == 99 and a[5] == 99 and G.mmAnchor._w == G.MINIMAP_SIDES.small
    side = G.MINIMAP_SIDES.small
    assert lua.eval("Minimap._w") == side - 6 and lua.eval("Minimap._h") == side - 6
    assert lua.eval("AGPS_MM.ground") is False and lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE
    assert lua.eval("MinimapCompassTexture._shown") is False  # (the round border art)
    # (the user, 2026-11-09: the minimap's quest-area circle showed through) its quest, task, archaeology areas unseen
    blobs = dict(lua.eval("AGPS_MM.blobs").items())
    assert len(blobs) == 9 and set(blobs.values()) == {0}
    # the window: a square that size in the minimap's corner (the top right here), no frame, buttons or logo
    assert frame._w == side and frame._h == side
    corner = lua.eval("AzerothGPSFrame._pt")
    assert corner[1] == "TOPRIGHT" and lua.eval("AzerothGPSFrame._pt[2] == MinimapContainer") and corner[3] == "CENTER"
    assert corner[4] == 99 and corner[5] == 99  # (the old minimap's corner: half of its 198)
    assert frame._shown and G.moveTab._shown is False and G.sizeGrip._shown is False
    # the view: on the player, the minimap's radius, north up while the minimap doesn't turn
    lua.execute("GetPlayerFacing = function() return 0.7 end")
    x, y, rot, zoom = _view(lua, ns)
    assert abs(x - lua.eval("AGPS_POS[1]")) < 1e-6 and abs(y - lua.eval("AGPS_POS[2]")) < 1e-6
    assert abs(zoom - 116.5) < 1e-6 and rot == 0
    # a turning minimap: the map turns the same way, the player still in the middle (not low, as heading-up's)
    lua.execute('AGPS_MM_CVAR = "1"')
    x, y, rot, zoom = _view(lua, ns)
    assert abs(rot + 0.7) < 1e-6
    assert abs(x - lua.eval("AGPS_POS[1]")) < 1e-6 and abs(y - lua.eval("AGPS_POS[2]")) < 1e-6
    # the other way of hiding its ground: the transparent mask, the ground left on
    st.replaceMinimapHide = "mask"
    G.ApplySettings()
    assert lua.eval("AGPS_MM.mask") == G.MINIMAP_CLEAR and lua.eval("AGPS_MM.ground") is True
    # a size step: the window and the Minimap with it
    st.replaceMinimapSize = "large"
    G.ApplySettings()
    assert frame._w == G.MINIMAP_SIDES.large and lua.eval("Minimap._w") == G.MINIMAP_SIDES.large - 6


def test_the_minimap_as_the_map_follows_its_zoom(minimap):
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    st.replaceMinimap = True
    G.ApplySettings()
    assert abs(_view(lua, ns)[3] - 116.5) < 1e-6
    lua.execute("AGPS_MM.radius = 66.7; AGPS_MM.zoom = 3")
    lua.eval("AGPS_FIRE")("MINIMAP_UPDATE_ZOOM")
    assert abs(_view(lua, ns)[3] - 66.7) < 1e-6
    # (no radius from the client: the zoom's measured size, Layers.MinimapYards, half of it)
    lua.execute("C_Minimap.GetViewRadius = nil")
    assert abs(_view(lua, ns)[3] - ns.Layers.MinimapYards() / 2) < 1e-6
    # the player's own zoom setting is left alone (not scaled by the square's size)
    zoom = st.zoom
    st.replaceMinimap = False
    G.ApplySettings()
    assert st.zoom == zoom


def test_turning_the_minimap_option_off_puts_the_minimap_back(minimap):
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    frame = lua.eval("AzerothGPSFrame")
    G.OnMinimapMask("Interface\\Some\\SquareMask")  # (a minimap addon's mask, seen before)
    st.replaceMinimap = True
    G.ApplySettings()
    st.replaceMinimap = False
    G.ApplySettings()
    assert not G.MinimapMode()
    p = lua.eval("Minimap._pts.CENTER")
    assert p[1] == "CENTER" and lua.eval("Minimap._pts.CENTER[2] == MinimapContainer") and p[3] == "CENTER"
    assert p[4] == 0 and p[5] == 0
    assert lua.eval("Minimap._w") == 198 and lua.eval("Minimap._h") == 198
    assert lua.eval("Minimap._parent == MinimapContainer")
    assert lua.eval("AGPS_MM.mask") == "Interface\\Some\\SquareMask" and lua.eval("AGPS_MM.ground") is True
    assert lua.eval("MinimapCompassTexture._shown") is True
    blobs = dict(lua.eval("AGPS_MM.blobs").items())
    assert len(blobs) == 9 and set(blobs.values()) == {G.MINIMAP_BLOB_DEFAULT}  # (its quest areas back)
    # the window as it was: its own size and place, its frame and buttons
    assert frame._w == st.size and lua.eval("AzerothGPSFrame._pt")[1] == st.point[1]
    assert G.moveTab._shown is (not st.locked)
    # no mask seen before: the game's round one
    G.minimapMask = None
    st.replaceMinimap = True
    G.ApplySettings()
    st.replaceMinimap = False
    G.ApplySettings()
    assert lua.eval("AGPS_MM.mask") == G.MINIMAP_ROUND
    # (the user's test, 2026-11-09: the minimap given back drew nothing: "Textures\MinimapMask" has no name in this
    # client's files, a missing mask) the round one by its FileDataID; ground drawn, seen, shown
    assert G.MINIMAP_ROUND == 186178 and lua.eval("AGPS_MM.ground") is True
    assert lua.eval("Minimap._alpha == nil or Minimap._alpha == 1") and lua.eval("Minimap._shown")


def test_nothing_of_the_minimap_moves_in_combat(minimap):
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("InCombatLockdown = function() return true end")
    st.replaceMinimap = True
    G.ApplySettings()
    assert not G.MinimapMode()
    assert lua.eval("Minimap._pts.CENTER[2] == MinimapContainer") and lua.eval("#AGPS_MM.masks") == 0
    lua.execute("InCombatLockdown = function() return false end")
    lua.eval("AGPS_FIRE")("PLAYER_REGEN_ENABLED")
    assert G.MinimapMode() and lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE
    # taken, then a fight: off waits too, and the size isn't changed under it
    lua.execute("InCombatLockdown = function() return true end")
    masks = lua.eval("#AGPS_MM.masks")
    st.replaceMinimapSize = "large"
    G.ApplySettings()
    st.replaceMinimap = False
    G.ApplySettings()
    assert G.MinimapMode() and lua.eval("#AGPS_MM.masks") == masks
    assert lua.eval("Minimap._w") == G.MINIMAP_SIDES.small - 6
    assert lua.eval("AzerothGPSFrame._w") == G.MINIMAP_SIDES.small
    lua.execute("InCombatLockdown = function() return false end")
    lua.eval("AGPS_FIRE")("PLAYER_REGEN_ENABLED")
    assert not G.MinimapMode() and lua.eval("Minimap._w") == 198


def test_the_route_isnt_drawn_on_the_minimap_while_the_map_is_the_minimap(minimap):
    lua, ns = minimap
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    G.InitMinimapRoute()
    try:
        N.SetStops(lua.eval("{ { x = 2000, y = 400, cont = 0 } }"), False, "red")
        N.Route(lua.eval("AGPS_POS[1]"), lua.eval("AGPS_POS[2]"), 0)
        assert N.route and G.UpdateMinimapRoute(True) > 0
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.UpdateMinimapRoute(True) == 0  # (the map draws it: never twice)
    finally:
        N.Clear()



def test_the_minimap_buttons_go_round_the_square_and_back(minimap):
    # (asked 2026-11-09: "the addon icons still going in a circle not around the new square minimap") GetMinimapShape is
    # "SQUARE" while the map is the minimap, LibDBIcon's buttons placed again (its own update, SetButtonRadius), and
    # the global another addon had is put back
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_DBI = { radius = 5, calls = {} }
      function AGPS_DBI:SetButtonRadius(r)
        table.insert(self.calls, (GetMinimapShape and GetMinimapShape() or "ROUND") .. ":" .. r)
      end
      LibStub = function(name, silent) if name == "LibDBIcon-1.0" then return AGPS_DBI end end
      AGPS_OLD_SHAPE = function() return "ROUND" end
      GetMinimapShape = AGPS_OLD_SHAPE
    """)
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        assert lua.eval("GetMinimapShape()") == "SQUARE" and G.MinimapSquare()
        assert lua.eval("AGPS_DBI.calls[1]") == "SQUARE:5"
        st.replaceMinimapSize = "large"  # (a new size: placed again on the new square's edge)
        G.ApplySettings()
        assert lua.eval("#AGPS_DBI.calls") == 2
        st.replaceMinimap = False
        G.ApplySettings()
        assert lua.eval("GetMinimapShape == AGPS_OLD_SHAPE")
        assert lua.eval("AGPS_DBI.calls[#AGPS_DBI.calls]") == "ROUND:5"
    finally:
        lua.execute("LibStub = nil; GetMinimapShape = nil")


def _expand_setup(lua):
    lua.execute("AGPS_A = nil")
    lua.execute("""
      AzerothGPSFrame.SetFrameStrata = function(s, v) s._strata = v end
      Minimap.SetAlpha = function(s, a) s._alpha = a end
    """)


def _tick(lua, ns, dt=0.3, seconds=0):
    lua.execute(f"AGPS_T = AGPS_T + {seconds}")
    ns.GPS.MinimapTick(dt)


def test_the_minimap_square_grows_into_the_window_and_back(minimap):
    # (asked 2026-11-09: a button on the square opens the whole map window over everything to set a route; it goes back
    # after 5 s without use, by its back button, or Escape; the game's Minimap stays on the square meanwhile, unseen)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    frame = lua.eval("AzerothGPSFrame")
    top = G.mapButtons.recenter._parent
    st.replaceMinimap = True
    G.ApplySettings()
    b = G.mmButton
    assert b._shown and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT" and top._shown is False
    lua.globals().AGPS_A = G.mmAnchor
    assert lua.eval("Minimap._pts.CENTER[2] == AGPS_A")  # (on its own anchor in the square's place)
    # (asked 2026-11-09: "like how the top left usually is on expanded view") the window's corner logo, pixel for pixel,
    # not the arrow
    assert b.logo._shown and "CornerLogo" in b.logo._tex and b.icon._shown is False and "MinimapArrow" not in b.logo._tex
    assert b._w == b._h and b._w > 0
    # (asked 2026-11-09: as the window's top-left logo, over the square's bottom-left corner)
    pt = lua.eval("{ (function(b) return unpack(b._pt) end)(AGPS_NS.GPS.mmButton) }")
    assert pt[1] == "CENTER" and lua.eval("AGPS_NS.GPS.mmButton._pt[2] == AzerothGPSFrame") and pt[3] == "BOTTOMLEFT"
    assert abs(pt[4] - b._w * G.MINIMAP_LOGO_IN) < 1e-6
    assert abs(pt[5] - (ns.TITLE_MID - 2) * b._w / ns.CORNER_LOGO_UNITS) < 1e-6
    b._scripts.OnClick(b)
    assert G.mmState.expanded and not G.MinimapMode()
    assert b.icon._shown and b.logo._shown is False  # (on the window: the arrow back into the corner)
    _tick(lua, ns)  # (the animation: done)
    assert G.mmState.tween is None
    p = lua.eval("AzerothGPSFrame._pt")
    assert [p[i] for i in (1, 3, 4, 5)] == [st.point[i] for i in (1, 3, 4, 5)]
    assert frame._w == st.size and frame._h == st.size
    assert frame._strata == G.MINIMAP_EXPANDED_STRATA and top._shown is True and frame._shown
    # (asked 2026-11-09: "restore the minimap to original state while the map is expanded out")
    assert not G.MinimapTaken() and lua.eval("Minimap._pts.CENTER[2] == MinimapContainer")
    assert lua.eval("Minimap._w") == 198 and lua.eval("AGPS_MM.ground") is True and lua.eval("Minimap._alpha") == 1
    # the map's own view while it's out: not the minimap's (a route set as on the usual map)
    assert G.MinimapView(0) is None
    # its back button: the square again, the Minimap seen on it
    b._scripts.OnClick(b)
    _tick(lua, ns)
    assert not G.mmState.expanded and G.MinimapMode()
    assert lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT" and frame._w == G.MINIMAP_SIDES.small
    assert frame._strata == "BACKGROUND" and top._shown is False and lua.eval("Minimap._alpha") == 1
    assert G.MinimapTaken() and lua.eval("Minimap._pts.CENTER[2] == AGPS_A")  # (taken again, on the square)
    assert lua.eval("Minimap._w") == G.MINIMAP_SIDES.small - 6 and lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE
    # Escape (its stand-in in UISpecialFrames hidden) takes it back too
    G.SetMinimapExpanded(True)
    _tick(lua, ns)
    esc = G.mmEscape
    assert esc._shown and lua.eval("(function() for _, n in ipairs(UISpecialFrames) do if n == 'AzerothGPSMinimapBack' then return true end end end)()")
    esc._shown = False
    esc._scripts.OnHide(esc)
    _tick(lua, ns)
    assert not G.mmState.expanded and frame._strata == "BACKGROUND"


def test_the_map_grown_out_of_the_square_takes_the_map_opacity(minimap):
    # (asked 2026-11-14: "map opacity setting doesn't work when gps minimap is on for the pop out GPS map, this should
    # still work") the square stays solid; grown into the window, Options' Map opacity
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    frame = lua.eval("AzerothGPSFrame")
    old = st.alpha
    lua.execute("AGPS_SETA = AzerothGPSFrame.SetAlpha; AzerothGPSFrame.SetAlpha = function(s, a) s._alpha = a end")
    try:
        st.alpha = 0.5
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode() and frame._alpha == 1
        G.mmButton._scripts.OnClick(G.mmButton)
        _tick(lua, ns)
        assert G.mmState.expanded and abs(frame._alpha - 0.5) < 1e-6
        G.mmButton._scripts.OnClick(G.mmButton)
        _tick(lua, ns)
        assert G.MinimapMode() and frame._alpha == 1
    finally:
        st.alpha = old
        lua.execute("AzerothGPSFrame.SetAlpha = AGPS_SETA")


def test_the_expanded_minimap_goes_back_after_5_quiet_seconds(minimap):
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    frame = lua.eval("AzerothGPSFrame")
    st.replaceMinimap = True
    G.ApplySettings()
    G.SetMinimapExpanded(True)
    _tick(lua, ns)
    _tick(lua, ns, seconds=4)
    assert G.mmState.expanded  # (not yet)
    frame._scripts.OnMouseWheel(frame, 1)  # (a zoom on it: activity, the clock starts again)
    _tick(lua, ns, seconds=4)
    assert G.mmState.expanded
    # the mouse resting over it: busy, never back under the cursor
    lua.execute("AzerothGPSFrame.IsMouseOver = function() return true end")
    _tick(lua, ns, seconds=30)
    assert G.mmState.expanded
    lua.execute("AzerothGPSFrame.IsMouseOver = nil")
    _tick(lua, ns, seconds=2)
    assert G.mmState.expanded
    _tick(lua, ns, seconds=4)  # (5 s and more since the mouse left)
    assert not G.mmState.expanded
    _tick(lua, ns)
    assert G.MinimapMode() and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT"


def test_the_minimap_square_grows_and_shrinks_in_combat_without_moving_the_minimap(minimap):
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    st.replaceMinimap = True
    G.ApplySettings()
    lua.execute("AGPS_MM_PTS = Minimap._pts; InCombatLockdown = function() return true end")
    lua.execute("Minimap.SetPoint = function() error('the Minimap moved in combat') end")
    lua.execute("Minimap.ClearAllPoints = function() error('the Minimap moved in combat') end")
    lua.execute("Minimap.SetSize = function() error('the Minimap sized in combat') end")
    try:
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        assert G.mmState.expanded and lua.eval("AzerothGPSFrame._strata") == G.MINIMAP_EXPANDED_STRATA
        G.SetMinimapExpanded(False)
        _tick(lua, ns)
        assert not G.mmState.expanded and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT"
        assert lua.eval("Minimap._pts == AGPS_MM_PTS")
        G.SetMinimapExpanded(True)  # (out again as the fight ends: the minimap given back then)
        _tick(lua, ns)
        # (meanwhile the game's own minimap where the square was, its ground drawn: seen in game 2026-11-12, the
        # player had no minimap for the fight)
        assert G.MinimapTaken() and lua.eval("Minimap._alpha") == 1 and G.mmState.combatOut
        assert lua.eval("AGPS_MM.ground") is True and lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE
        G.SetMinimapExpanded(False)  # (and back into the square in the same fight: hidden again)
        _tick(lua, ns)
        assert not G.mmState.combatOut and lua.eval("AGPS_MM.ground") is False
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        lua.execute("Minimap.SetPoint, Minimap.ClearAllPoints, Minimap.SetSize = nil, nil, nil")
        lua.execute("InCombatLockdown = function() return false end")
        lua.eval("AGPS_FIRE")("PLAYER_REGEN_ENABLED")
        assert not G.MinimapTaken() and lua.eval("Minimap._pts.CENTER[2] == MinimapContainer")
        assert lua.eval("Minimap._w") == 198 and lua.eval("Minimap._alpha") == 1
        # back to the square asked for in another fight (its idle seconds): out till the fight ends, then back and
        # taken (seen in game 2026-11-12: shrunk mid-fight it kept the window's size with the square's look)
        lua.execute("InCombatLockdown = function() return true end")
        G.SetMinimapExpanded(False)
        _tick(lua, ns)
        assert G.mmState.expanded and not G.MinimapTaken() and lua.eval("Minimap._w") == 198
        lua.execute("InCombatLockdown = function() return false end")
        lua.eval("AGPS_FIRE")("PLAYER_REGEN_ENABLED")
        _tick(lua, ns)
        assert not G.mmState.expanded and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT"
        assert G.MinimapTaken() and lua.eval("Minimap._w") == G.MINIMAP_SIDES.small - 6
        # "Back to the minimap when combat starts": at the fight's start, before the lockdown, at once (no animation
        # left to run in the fight)
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        st.replaceMinimapCollapseOnCombat = True
        try:
            lua.eval("AGPS_FIRE")("PLAYER_REGEN_DISABLED")
            assert not G.mmState.expanded and G.mmState.tween is None
            assert G.MinimapTaken() and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT"
        finally:
            st.replaceMinimapCollapseOnCombat = False
    finally:
        lua.execute("Minimap.SetPoint, Minimap.ClearAllPoints, Minimap.SetSize = nil, nil, nil")
        lua.execute("InCombatLockdown = function() return false end")


def test_the_minimap_is_given_back_while_the_map_is_grown_into_the_window(minimap):
    # (asked 2026-11-09: "restore the minimap to original state while the map is expanded out") as it was before it was
    # taken: points, size, mask, ground, art, GetMinimapShape (the buttons round the circle), our route on it; taken
    # again on the square; quick out-in-out never leaves it half taken
    lua, ns = minimap
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    _expand_setup(lua)
    lua.execute("""
      AGPS_DBI = { radius = 5, calls = {} }
      function AGPS_DBI:SetButtonRadius(r)
        table.insert(self.calls, (GetMinimapShape and GetMinimapShape() or "ROUND") .. ":" .. r)
      end
      LibStub = function(name) if name == "LibDBIcon-1.0" then return AGPS_DBI end end
    """)
    G.OnMinimapMask(G.MINIMAP_ROUND)  # (the round one seen: put back)
    try:
        N.SetStops(lua.eval("{ { x = 2000, y = 400, cont = 0 } }"), False, "red")
        N.Route(lua.eval("AGPS_POS[1]"), lua.eval("AGPS_POS[2]"), 0)
        st.replaceMinimap = True
        G.ApplySettings()
        lua.globals().AGPS_A = G.mmAnchor
        assert G.MinimapTaken() and lua.eval("GetMinimapShape and GetMinimapShape()") == "SQUARE"
        assert G.UpdateMinimapRoute(True) == 0
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        assert not G.MinimapTaken()
        p = lua.eval("Minimap._pts.CENTER")
        assert lua.eval("Minimap._pts.CENTER[2] == MinimapContainer") and p[4] == 0 and p[5] == 0
        assert lua.eval("Minimap._w") == 198 and lua.eval("Minimap._h") == 198
        assert lua.eval("AGPS_MM.mask") == G.MINIMAP_ROUND and lua.eval("AGPS_MM.ground") is True
        assert lua.eval("MinimapCompassTexture._shown") is True and lua.eval("GetMinimapShape") is None
        assert set(dict(lua.eval("AGPS_MM.blobs").items()).values()) == {G.MINIMAP_BLOB_DEFAULT}  # (its quest areas)
        assert lua.eval("AGPS_DBI.calls[#AGPS_DBI.calls]") == "ROUND:5"  # (the buttons round the circle again)
        assert not G.MinimapSquare() and G.UpdateMinimapRoute(True) > 0  # (our route on it again)
        # quick: in, out, in, out (no animation waited for): ends taken on the square, then given back, whole
        for on in (False, True, False):
            G.SetMinimapExpanded(on)
        _tick(lua, ns)
        assert G.MinimapTaken() and lua.eval("Minimap._pts.CENTER[2] == AGPS_A")
        assert lua.eval("Minimap._w") == G.MINIMAP_SIDES.small - 6 and lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE
        assert lua.eval("AGPS_MM.ground") is False and lua.eval("MinimapCompassTexture._shown") is False
        assert lua.eval("GetMinimapShape()") == "SQUARE"
        G.SetMinimapExpanded(True)
        G.SetMinimapExpanded(False)
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        assert not G.MinimapTaken() and lua.eval("Minimap._w") == 198
        assert lua.eval("AGPS_MM.mask") == G.MINIMAP_ROUND and lua.eval("GetMinimapShape") is None
    finally:
        N.Clear()
        lua.execute("LibStub = nil")


def _keep_square_setup(lua, ns):
    """The option on (its default), the square taken; what the game's Minimap is now, to check it's never touched."""
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    st.replaceMinimapKeepSquare = True
    st.replaceMinimap = True
    G.ApplySettings()
    lua.globals().AGPS_A = G.mmAnchor
    lua.execute("AGPS_MM_PTS = Minimap._pts")
    seen = (lua.eval("#AGPS_MM.masks"), lua.eval("#AGPS_MM.grounds"))
    side = G.MinimapSquareSide()

    def unchanged():
        assert G.MinimapTaken() and not G.mmState.standIn and not G.mmState.combatOut
        assert lua.eval("Minimap._pts == AGPS_MM_PTS") and lua.eval("Minimap._pts.CENTER[2] == AGPS_A")
        assert (lua.eval("#AGPS_MM.masks"), lua.eval("#AGPS_MM.grounds")) == seen
        assert lua.eval("Minimap._w") == side - 6 and lua.eval("Minimap._alpha") == 1
        assert lua.eval("AGPS_MM.ground") is False and lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE
        assert lua.eval("GetMinimapShape()") == "SQUARE"
    return side, unchanged


def test_the_square_stays_as_it_is_while_the_map_is_out_of_it(minimap):
    # (asked 2026-11-15: "keep our square minimap as is and still animate show the GPS map and collapsing it without
    # ever changing the current minimap. Show both") the option on, its default: the window grows out of the square and
    # back, and meanwhile the square is the second map with the game's Minimap left taken on it, never given back
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    frame = lua.eval("AzerothGPSFrame")
    top = G.mapButtons.recenter._parent
    side, unchanged = _keep_square_setup(lua, ns)
    b = G.mmButton
    assert G.MinimapMode() and not G.SquareKeptOut()
    unchanged()
    b._scripts.OnClick(b)
    m = G.mmState
    assert m.expanded and m.tween is not None and G.SquareKeptOut()  # (animated out of the square)
    c = ns.mapClone
    cf = c.Canvas().GetParent(c.Canvas())
    assert cf._shown and (cf._w, cf._h) == (side, side) and c.MinimapMode()  # (the square: shown from the start)
    unchanged()
    _tick(lua, ns)
    assert m.tween is None and not G.MinimapMode() and G.MinimapView(0) is None
    p = lua.eval("AzerothGPSFrame._pt")
    assert [p[i] for i in (1, 3, 4, 5)] == [st.point[i] for i in (1, 3, 4, 5)]
    assert frame._w == st.size and frame._h == st.size and frame._shown and top._shown is True
    assert frame._strata == G.MINIMAP_EXPANDED_STRATA
    assert cf._shown and (cf._w, cf._h) == (side, side)  # (both shown)
    unchanged()
    # (the logo stays on the square's corner, the logo as ever: the window has its own close button and Escape)
    assert b._shown and b.logo._shown and b.icon._shown is False and lua.eval("rawequal")(b._pt[2], G.mmAnchor)
    assert G.mmEscape._shown
    # (and the arrow back on the window, beside its bottom-left corner, as before the square was kept: asked 2026-11-16
    # for 1.3.5, "the little arrow in the pop out map in the bottom left is gone ... lets add that back")
    back = G.mmBack
    assert back._shown and "MinimapArrow" in back.icon._tex and lua.eval("rawequal")(back._pt[2], frame)
    # back: animated into the square, the second map kept till it's there, then the first one the square again
    back._scripts.OnClick(back, "LeftButton")  # (the window's arrow: back as the logo sends it)
    assert not m.expanded and m.tween is not None and cf._shown and G.SquareKeptOut()
    unchanged()
    _tick(lua, ns)
    assert m.tween is None and G.MinimapMode() and not G.SquareKeptOut() and not cf._shown
    assert lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT" and frame._w == side and frame._strata == "BACKGROUND"
    assert top._shown is False and lua.eval("rawequal")(b._pt[2], frame) and b.logo._shown
    assert not back._shown  # (in the square: no arrow on it)
    unchanged()
    # quick: out, back, out, back with no animation waited for; then back by itself after its quiet seconds
    for on in (True, False, True, False):
        G.SetMinimapExpanded(on)
        unchanged()
    _tick(lua, ns)
    assert G.MinimapMode() and not cf._shown
    G.SetMinimapExpanded(True)
    _tick(lua, ns)
    # (no popup over it left by another test: that keeps it out)
    lua.execute("AGPS_POPS = AGPS_NS.PopupOverShown; AGPS_NS.PopupOverShown = function() return false end")
    try:
        _tick(lua, ns, seconds=G.MinimapIdleSeconds() + 1)
    finally:
        lua.execute("AGPS_NS.PopupOverShown = AGPS_POPS")
    assert not m.expanded
    _tick(lua, ns)
    assert G.MinimapMode() and not cf._shown and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT"
    unchanged()
    # with no animation (as G.MINIMAP_TWEEN 0): back at once, the second map put away at once
    tween = G.MINIMAP_TWEEN
    G.MINIMAP_TWEEN = 0
    try:
        G.SetMinimapExpanded(True)
        assert m.expanded and m.tween is None and cf._shown
        G.SetMinimapExpanded(False)
        assert G.MinimapMode() and not cf._shown and not G.SquareKeptOut()
        unchanged()
    finally:
        G.MINIMAP_TWEEN = tween


def test_the_square_kept_while_the_map_is_out_never_moves_in_combat(minimap):
    # (the option on: out of the square and back in a fight, nothing of the game's Minimap touched, its mask, ground and
    # alpha too; back to the square at once, no waiting for the fight's end; nothing done as it ends either)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    side, unchanged = _keep_square_setup(lua, ns)
    m = G.mmState
    lua.execute("InCombatLockdown = function() return true end")
    lua.execute("Minimap.SetPoint = function() error('the Minimap moved in combat') end")
    lua.execute("Minimap.ClearAllPoints = function() error('the Minimap moved in combat') end")
    lua.execute("Minimap.SetSize = function() error('the Minimap sized in combat') end")
    try:
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        assert m.expanded and lua.eval("AzerothGPSFrame._strata") == G.MINIMAP_EXPANDED_STRATA
        c = ns.mapClone
        cf = c.Canvas().GetParent(c.Canvas())
        assert cf._shown
        unchanged()
        G.SetMinimapExpanded(False)
        assert not m.backAfterCombat
        _tick(lua, ns)
        assert G.MinimapMode() and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT" and not cf._shown
        unchanged()
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        lua.execute("InCombatLockdown = function() return false end")
        lua.eval("AGPS_FIRE")("PLAYER_REGEN_ENABLED")  # (the fight's end: the Minimap still left as it is)
        assert m.expanded
        unchanged()
        st.replaceMinimapCollapseOnCombat = True
        try:
            lua.execute("InCombatLockdown = function() return true end")
            lua.eval("AGPS_FIRE")("PLAYER_REGEN_DISABLED")
            assert not m.expanded and m.tween is None and G.MinimapMode() and not cf._shown
            unchanged()
        finally:
            st.replaceMinimapCollapseOnCombat = False
    finally:
        lua.execute("Minimap.SetPoint, Minimap.ClearAllPoints, Minimap.SetSize = nil, nil, nil")
        lua.execute("InCombatLockdown = function() return false end")


def test_the_options_leave_the_minimap_square_as_it_is(minimap):
    # (a bug report, 2026-11-09: "opening options make the map do this and put a title bar at the top": the windows'
    # logo look gave the square its titled border back, and every settings change set the Minimap's mask, ground and
    # size again; a round white disc showed over the square) the options opened, each page, closed, applied: the
    # square's border look kept, the game's Minimap not touched
    lua, ns = minimap
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    lua.execute("""
      AGPS_CH = CreateFrame("Frame", nil, AzerothGPSFrame)
      AGPS_CH.NineSlice = CreateFrame("Frame", nil, AGPS_CH)
      AGPS_CH.TitleContainer = CreateFrame("Frame", nil, AGPS_CH)
      AGPS_CH.SetBorder = function(s, layout) s._border = layout end
    """)
    G.chrome = lua.eval("AGPS_CH")
    G.logo = ns.SetLogoPortrait(G.chrome, None, lua.eval("function() end"))
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        ch = G.chrome
        plate = G.logo.plate

        def square_look():
            assert ch._border == G.MINIMAP_BORDER and ch._shown
            assert ch.TitleContainer._shown is False and plate._shown is False and ch.NineSlice._shown
        square_look()
        lua.execute("""
          AGPS_TOUCHED = {}
          for _, k in ipairs({ "SetMaskTexture", "SetSize", "SetPoint", "ClearAllPoints", "SetAlpha", "SetScale" }) do
            local f = Minimap[k]
            Minimap[k] = function(...) table.insert(AGPS_TOUCHED, k) return f(...) end
          end
          AGPS_SET_GROUND = C_Minimap.SetDrawGroundTextures
          C_Minimap.SetDrawGroundTextures = function(v) table.insert(AGPS_TOUCHED, "ground") return AGPS_SET_GROUND(v) end
          MinimapCompassTexture.Show = function(s) table.insert(AGPS_TOUCHED, "art") s._shown = true end
        """)
        O.Show()
        for title in ("General", "Directions", "Map", "Window", "Routing", "Performance", "Quick buttons", "Tools"):
            O.ShowPage(title)
        O.Apply()
        O.Toggle()  # (closed)
        G.ApplySettings()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert list(lua.eval("AGPS_TOUCHED").values()) == []
        square_look()
        assert lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE and lua.eval("AGPS_MM.ground") is False
        assert lua.eval("MinimapCompassTexture._shown") is False and G.MinimapTaken()
        # the window's own size in the options' sliders, not the square's
        assert lua.eval('select(2, AGPS_NS.GPS.MapSize(nil, true))') == st.size
        # a logo look applied again (a scale change): still the square's
        lua.execute("AGPS_NS.ApplyLogoLook()")
        square_look()
    finally:
        lua.execute("""
          for _, k in ipairs({ "SetMaskTexture", "SetSize", "SetPoint", "ClearAllPoints", "SetAlpha", "SetScale" }) do
            Minimap[k] = nil
          end
          if AGPS_SET_GROUND then C_Minimap.SetDrawGroundTextures = AGPS_SET_GROUND end
          MinimapCompassTexture.Show = nil
        """)
        lua.execute("""Minimap.SetMaskTexture = function(_, t) table.insert(AGPS_MM.masks, t) AGPS_MM.mask = t end""")
        st.replaceMinimap = False
        G.ApplySettings()
        G.chrome, G.logo, G.mmChromeCompact = None, None, None


def test_the_minimap_square_can_hide_its_border(minimap):
    # (Kooki3z 2026-11-26 for 1.4.1, item 103: "an option to hide the minimap border", off by default) off: the square's
    # border shows, as before; on (the options' check box): hidden at once, the map the same size in the same place;
    # the map grown out of the square and the window out of minimap mode keep their own border
    lua, ns = minimap
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    _expand_setup(lua)
    lua.execute("""
      AGPS_CH = CreateFrame("Frame", nil, AzerothGPSFrame)
      AGPS_CH.NineSlice = CreateFrame("Frame", nil, AGPS_CH)
      AGPS_CH.TitleContainer = CreateFrame("Frame", nil, AGPS_CH)
      AGPS_CH.SetBorder = function(s, layout) s._border = layout; s.NineSlice:Show() end
      function AGPS_PLACE(f)
        local t = {}
        for k, p in pairs(f._pts or {}) do
          t[#t + 1] = table.concat({ tostring(k), tostring(p[2]), tostring(p[3]), tostring(p[4]), tostring(p[5]) }, ",")
        end
        table.sort(t)
        return table.concat(t, ";") .. "|" .. tostring(f._w) .. "x" .. tostring(f._h)
      end
    """)
    G.chrome = lua.eval("AGPS_CH")
    ch = G.chrome
    place = lua.eval("AGPS_PLACE")
    frame = lua.eval("AzerothGPSFrame")
    try:
        assert st.replaceMinimapNoBorder is False  # (the default)
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode() and ch._border == G.MINIMAP_BORDER and ch.NineSlice._shown
        where = place(frame), place(ch)
        # on, by its check box: hidden at once, no /reload; the map and the border's frame where they were
        O.Show()
        O.ShowPage("Minimap")
        cb = next(c.control for c in O.settingControls.values() if c.key == "replaceMinimapNoBorder")
        O.Refresh()
        assert cb.agpsOn is True and cb.GetChecked(cb) is False
        cb.SetChecked(cb, True)
        cb._scripts.OnClick(cb)
        O.Toggle()  # (closed)
        assert st.replaceMinimapNoBorder is True
        assert ch.NineSlice._shown is False and ch._shown and ch._border == G.MINIMAP_BORDER
        assert (place(frame), place(ch)) == where
        # kept hidden through the windows' logo look applied again (it gives every window its titled border back)
        lua.execute("AGPS_NS.ApplyLogoLook()")
        assert ch.NineSlice._shown is False and ch._border == G.MINIMAP_BORDER
        G.ApplySettings()
        assert ch.NineSlice._shown is False and (place(frame), place(ch)) == where
        # grown out of the square: the usual window's border; back in the square: hidden again
        G.SetMinimapExpanded(True)
        for _ in range(4):
            _tick(lua, ns)
        assert G.mmState.expanded and ch.NineSlice._shown and ch._border == "ButtonFrameTemplateNoPortrait"
        G.SetMinimapExpanded(False)
        for _ in range(4):
            _tick(lua, ns)
        assert not G.mmState.expanded and ch.NineSlice._shown is False and ch._border == G.MINIMAP_BORDER
        # off again: shown, the map still where it was
        st.replaceMinimapNoBorder = False
        G.ApplySettings()
        assert ch.NineSlice._shown and (place(frame), place(ch)) == where
        # on, then out of minimap mode: the window's own border back
        st.replaceMinimapNoBorder = True
        G.ApplySettings()
        assert ch.NineSlice._shown is False
        st.replaceMinimap = False
        G.ApplySettings()
        assert not G.MinimapMode() and ch.NineSlice._shown and ch._border == "ButtonFrameTemplateNoPortrait"
        lua.execute("AGPS_NS.ApplyLogoLook()")
        assert ch.NineSlice._shown
    finally:
        st.replaceMinimapNoBorder = False
        st.replaceMinimap = False
        G.ApplySettings()
        G.chrome, G.mmChromeCompact = None, None


def test_the_minimap_square_border_option_is_kept_over_a_reload():
    # (item 103: off by default; turned on, it stays on over a /reload or relog; off again, it stays off)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    from test_keep_data import SERIALIZE  # (the saved file written as the game does)

    def start_(saved=None):
        lua, ns = start(saved=saved)
        lua.execute(SERIALIZE)
        return lua, ns

    def saved(lua):
        lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
        return lua.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua.globals().AzerothGPSDB)
    lua, ns = start_()
    assert ns.settings.gps.replaceMinimapNoBorder is False
    ns.settings.gps.replaceMinimapNoBorder = True
    lua2, ns2 = start_(saved(lua))
    assert ns2.settings.gps.replaceMinimapNoBorder is True and ns2.GPS.SquareHidesBorder()
    ns2.settings.gps.replaceMinimapNoBorder = False
    _, ns3 = start_(saved(lua2))
    assert ns3.settings.gps.replaceMinimapNoBorder is False


def test_the_opened_minimap_goes_back_as_you_move_when_asked(minimap):
    # (asked 2026-11-09, off by default) the option on: starting to move takes it back; off: it stays; already moving as
    # it opened isn't a start
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    lua.execute("AzerothGPSFrame.IsMouseOver = function() return true end")  # (busy: only the moving counts)
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        assert not st.replaceMinimapCollapseOnMove
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        lua.execute("IsPlayerMoving = function() return true end")
        _tick(lua, ns, seconds=1)
        assert G.mmState.expanded  # (off)
        st.replaceMinimapCollapseOnMove = True
        G.SetMinimapExpanded(False)
        _tick(lua, ns)
        G.SetMinimapExpanded(True)  # (opened while moving)
        _tick(lua, ns)
        _tick(lua, ns, seconds=1)
        assert G.mmState.expanded
        lua.execute("IsPlayerMoving = function() return false end")
        _tick(lua, ns, seconds=1)
        assert G.mmState.expanded  # (standing, or turning in place)
        lua.execute("IsPlayerMoving = function() return true end")
        _tick(lua, ns, seconds=1)
        assert not G.mmState.expanded
        _tick(lua, ns)
        assert G.MinimapMode() and lua.eval("AzerothGPSFrame._pt[1]") == "TOPRIGHT"
        # its search open: back as well (asked 2026-11-15, "it doesn't close the map unless player actually picks
        # something from the search but it should anyway")
        lua.execute("IsPlayerMoving = function() return false end")
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        lua.execute("AGPS_REAL_SEARCH = AGPS_NS.GPS.searchPanel or false; AGPS_NS.GPS.searchPanel = AGPS_NS.GPS.searchPanel or NewWidget('Frame'); AGPS_NS.GPS.searchPanel._shown = true; if AGPS_NS.GPS.mapMenu then AGPS_NS.GPS.mapMenu:Show() end")
        _tick(lua, ns, seconds=1)
        assert G.mmState.expanded
        lua.execute("IsPlayerMoving = function() return true end")
        _tick(lua, ns, seconds=1)
        assert not G.mmState.expanded, "moving with the search open didn't put the map back"
        # (and the search and the map menu closed with it, asked 2026-11-15)
        assert lua.eval("not AGPS_NS.GPS.searchPanel:IsShown()")
        assert lua.eval("not (AGPS_NS.GPS.mapMenu and AGPS_NS.GPS.mapMenu:IsShown())")
    finally:
        lua.execute("if AGPS_REAL_SEARCH ~= nil then if AGPS_NS.GPS.searchPanel then AGPS_NS.GPS.searchPanel._shown = false end; AGPS_NS.GPS.searchPanel = AGPS_REAL_SEARCH or nil end; AGPS_REAL_SEARCH = nil")
        st.replaceMinimapCollapseOnMove = False
        lua.execute("IsPlayerMoving = nil")


def test_the_opened_minimap_goes_back_as_combat_starts_when_asked(minimap):
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        assert not st.replaceMinimapCollapseOnCombat
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        lua.eval("AGPS_FIRE")("PLAYER_REGEN_DISABLED")
        assert G.mmState.expanded  # (off)
        st.replaceMinimapCollapseOnCombat = True
        lua.eval("AGPS_FIRE")("PLAYER_REGEN_DISABLED")  # (before the lockdown: the Minimap taken again at once)
        _tick(lua, ns)
        assert not G.mmState.expanded and G.MinimapTaken() and lua.eval("Minimap._w") == G.MINIMAP_SIDES.small - 6
    finally:
        st.replaceMinimapCollapseOnCombat = False
        lua.eval("AGPS_FIRE")("PLAYER_REGEN_ENABLED")


def test_the_minimap_squares_logo_shrinks_with_the_square(minimap):
    # (asked 2026-11-09: "make it 80% its current size and depending on the size choice of the minimap the image should
    # shrink with it", and a bit to the left) 80% of the window's logo on the extra large square, by the side on the
    # others, from the pre-scaled sizes (the small ones too), pixel for pixel; its middle 0.3 of it in from the left
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    st.replaceMinimap = True
    b = G.mmButton
    got = {}
    for step in ("small", "medium", "large"):
        st.replaceMinimapSize = step
        G.ApplySettings()
        want = ns.CORNER_LOGO_UNITS * 0.8 * G.MINIMAP_SIDES[step] / G.MINIMAP_SIDES.large
        assert abs(G.MinimapLogoUnits() - want) < 1e-9
        # (a pixel a unit here: the nearest pre-scaled size, in pixels)
        assert b._w == b._h and abs(b._w - want) <= 4, (step, b._w, want)
        assert ("CornerLogo%d" % b._w) in b.logo._tex
        pt = lua.eval("{ unpack(AGPS_NS.GPS.mmButton._pt) }")
        assert pt[1] == "CENTER" and pt[3] == "BOTTOMLEFT" and abs(pt[4] - 0.3 * b._w) < 1e-9
        got[step] = b._w
    assert got == {"small": 32, "medium": 40, "large": 48}
    # (asked 2026-11-09) right-click: the options, as the minimap button's; left-click still opens the map
    lua.execute("AGPS_OPTS = 0; AGPS_OLD_TOGGLE = AGPS_NS.Options.Toggle; AGPS_NS.Options.Toggle = function() AGPS_OPTS = AGPS_OPTS + 1 end")
    try:
        b._scripts.OnClick(b, "RightButton")
        assert lua.eval("AGPS_OPTS") == 1 and not G.mmState.expanded
        b._scripts.OnClick(b, "LeftButton")
        assert G.mmState.expanded and lua.eval("AGPS_OPTS") == 1
        G.SetMinimapExpanded(False)
    finally:
        lua.execute("AGPS_NS.Options.Toggle = AGPS_OLD_TOGGLE")


def test_the_minimap_button_opens_the_map_out_of_the_square_and_reset_asks_first(minimap):
    # (asked 2026-11-11, for 1.2.2: "Add back the left click to open map function to the minimap AzerothGPS icon in
    # addition to the logo"; "add a confirm ... popup for resetting all options to defaults")
    lua, ns = minimap
    G, O, st = ns.GPS, ns.Options, ns.settings.gps
    b = lua.globals().AzerothGPSMinimapButton
    click = b._scripts.OnClick
    # the map a window: the click shows and hides it, as ever
    assert not G.mmState.on and st.shown
    click(b, "LeftButton")
    assert not st.shown
    click(b, "LeftButton")
    assert st.shown
    # the map as the minimap: the click opens it out and sends it back; the square is never hidden by it
    st.replaceMinimap = True
    G.ApplySettings()
    assert G.mmState.on and not G.mmState.expanded
    click(b, "LeftButton")
    assert G.mmState.expanded and st.shown and G.mmState.on
    click(b, "LeftButton")
    assert not G.mmState.expanded and st.shown and G.mmState.on
    # Reset to defaults: a question first, nothing changed until Yes
    st.replaceMinimap = False
    G.ApplySettings()
    was = st.replaceMinimapSize
    st.replaceMinimapSize = "large"
    try:
        ask = O.AskReset()
        assert ask._shown is True and ns.settings.gps.replaceMinimapSize == "large"
        ask.no._scripts.OnClick(ask.no)
        assert not ask._shown and ns.settings.gps.replaceMinimapSize == "large"
        ask = O.AskReset()
        ask.yes._scripts.OnClick(ask.yes)
        assert not ask._shown and ns.settings.gps.replaceMinimapSize == ns.DEFAULTS.gps.replaceMinimapSize
    finally:
        ns.settings.gps.replaceMinimapSize = was
        # (the reset put world routing back on, the players' default: off again for the tests after, which were
        # written for it off unless they turn it on; gameharness.start)
        ns.settings.gps.worldGrid = False


def test_the_opened_maps_wait_is_the_players_own_or_never(minimap):
    # (asked 2026-11-11: "add option to change the timer for map auto closing without activity, and turning it off
    # for minimap mode")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    assert st.replaceMinimapIdle == 5 and G.MinimapIdleSeconds() == 5
    st.replaceMinimap = True
    G.ApplySettings()
    lua.execute("AGPS_IMO = AzerothGPSFrame.IsMouseOver AzerothGPSFrame.IsMouseOver = function() return false end")

    def quiet(seconds):
        # (opened now, nothing done on it for `seconds`: still out?)
        G.SetMinimapExpanded(True)
        G.mmState.tween = None
        now = lua.eval("GetTime()")
        G.mmState.activeAt = now
        G.MinimapIdle(now + seconds)
        out = bool(G.mmState.expanded)
        G.SetMinimapExpanded(False)
        G.mmState.tween = None
        return out

    try:
        assert quiet(4) and not quiet(5.5)
        st.replaceMinimapIdle = 20
        assert G.MinimapIdleSeconds() == 20 and quiet(15) and not quiet(21)
        st.replaceMinimapIdle = 0  # (never)
        assert quiet(3600)
    finally:
        st.replaceMinimapIdle = 5
        lua.execute("AzerothGPSFrame.IsMouseOver = AGPS_IMO AGPS_IMO = nil")


def test_find_herbs_and_ore_open_keeps_the_opened_map_out(minimap):
    # (asked 2026-11-19: "if this is open on the popout map, this is considered active and doesn't auto close")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    st.replaceMinimap = True
    G.ApplySettings()
    lua.execute("AGPS_IMO = AzerothGPSFrame.IsMouseOver AzerothGPSFrame.IsMouseOver = function() return false end")

    def quiet(seconds):
        G.SetMinimapExpanded(True)
        G.mmState.tween = None
        now = lua.eval("GetTime()")
        G.mmState.activeAt = now
        G.MinimapIdle(now + seconds)
        out = bool(G.mmState.expanded)
        G.SetMinimapExpanded(False)
        G.mmState.tween = None
        return out

    try:
        assert not quiet(30)
        G.SetMinimapExpanded(True)
        G.mmState.tween = None
        f = ns.Layers.ShowNodeFinder()
        now = lua.eval("GetTime()")
        G.mmState.activeAt = now
        G.MinimapIdle(now + 30)
        assert G.mmState.expanded and f._shown  # (the finder open: in use, kept out)
        # (and back into the square, by hand or by itself: the finder closes with it, asked 2026-11-19)
        G.SetMinimapExpanded(False)
        G.mmState.tween = None
        assert not f._shown
        assert not quiet(30)
    finally:
        if ns.Layers.finder:
            ns.Layers.finder.Hide(ns.Layers.finder)
        lua.execute("AzerothGPSFrame.IsMouseOver = AGPS_IMO AGPS_IMO = nil")


def test_the_square_is_taken_again_when_the_games_controller_ui_is_switched(minimap):
    # (asked 2026-11-11: "test with controller beta UI enabled ... addon should work with and without this mode"; the
    # game changes its Edit Mode layout with it, the minimap somewhere else at another size)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    assert lua.eval("AzerothGPSFrame").smartNavigationIgnored is None  # (no mark of ours for the game's code to read)
    fire = lambda: G.mmEvents._scripts.OnEvent(G.mmEvents, "INPUT_DEVICE_INTERFACE_TRANSITION")  # noqa: E731
    # the option off: nothing
    fire()
    assert not G.mmState.on and st.replaceMinimap is not True
    st.replaceMinimap = True
    G.ApplySettings()
    assert G.mmState.on and G.mmState.applied
    lua.execute("""
      AGPS_LATER, AGPS_CTA = {}, C_Timer.After
      C_Timer.After = function(_, fn) AGPS_LATER[#AGPS_LATER + 1] = fn end
    """)
    try:
        fire()
        # given back to the game for the layout's change, the option still the player's
        assert st.replaceMinimap is True and not G.mmState.applied
        lua.execute("for _, fn in ipairs(AGPS_LATER) do fn() end AGPS_LATER = {}")
        assert G.mmState.on and G.mmState.applied and st.replaceMinimap is True
        # in a fight: left as it is, taken again after
        lua.execute("InCombatLockdown = function() return true end")
        fire()
        assert G.mmState.applied and st.replaceMinimap is True
        lua.execute("InCombatLockdown = function() return false end")
        lua.execute("for _, fn in ipairs(AGPS_LATER) do fn() end AGPS_LATER = {}")
        assert G.mmState.on and G.mmState.applied
    finally:
        lua.execute("C_Timer.After = AGPS_CTA AGPS_LATER, AGPS_CTA = nil, nil InCombatLockdown = function() return false end")


def test_the_arrow_and_directions_are_unlocked_by_default_and_a_right_click_locks_them(game):
    # (asked 2026-11-11, after a player found the directions "locked to the center screen" outside the tutorial: "new
    # default setting, don't lock the directions and the arrow and support right clicking either one with a popup next
    # to the mouse to confirm locking its position, then after locking it another popup telling them where in options
    # to unlock it in the future")
    lua, ns = game
    A, st = ns.Arrow, ns.settings.gps
    assert ns.DEFAULTS.gps.arrowLocked is False
    was = st.arrowLocked
    click = lambda b: b._scripts.OnClick(b)  # noqa: E731
    try:
        st.arrowLocked = False
        A.Apply()
        A.lockAsk = None
        A.frame._scripts.OnMouseUp(A.frame, "LeftButton")
        assert A.lockAsk is None
        # a right-click on the directions: asked first, by the mouse; No changes nothing
        A.dir._scripts.OnMouseUp(A.dir, "RightButton")
        ask = A.lockAsk
        assert ask._shown is True and ask.no._shown is not False and st.arrowLocked is False
        assert ask._pt[1] == "BOTTOMLEFT" and ask._pt[3] == "BOTTOMLEFT"
        click(ask.no)
        assert not ask._shown and st.arrowLocked is False
        # on the arrow, Yes: locked, and told where the lock is (one button)
        A.frame._scripts.OnMouseUp(A.frame, "RightButton")
        click(A.lockAsk.yes)
        assert st.arrowLocked is True
        told = A.lockTold
        assert told._shown is True and told.no._shown is False
        assert "Options > Directions" in lua.eval("AGPS_NS.Arrow.lockTold.text:GetText()")
        click(told.yes)
        assert not told._shown and st.arrowLocked is True
        # locked: nothing to ask
        assert A.AskLock() is None
    finally:
        st.arrowLocked = was
        A.Apply()


def test_the_minimap_squares_three_sizes_and_old_saves_keep_their_size():
    # (asked 2026-11-09: "remove the small size. make current medium new small, large is new medium, and extra large is
    # just large now") three steps, 200 260 320; a saved one moved by its size once, so no square changes size
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    for old, new in (("small", "small"), ("medium", "small"), ("large", "medium"), ("xlarge", "large"), (None, "small")):
        saved = "AzerothGPSDB = { settings = { gps = { replaceMinimapSize = %s } } }" % ('"%s"' % old if old else "nil")
        lua, ns = start(saved=saved)
        G, st = ns.GPS, ns.settings.gps
        assert dict(G.MINIMAP_SIDES.items()) == {"small": 200, "medium": 260, "large": 320}
        assert st.replaceMinimapSize == new and ns.db.minimapSizes3
        assert G.MinimapSquareSide() == G.MINIMAP_SIDES[new]
    # once: a later "small" stays small
    lua, ns = start(saved='AzerothGPSDB = { minimapSizes3 = true, settings = { gps = { replaceMinimapSize = "medium" } } }')
    assert ns.settings.gps.replaceMinimapSize == "medium"
    # the command takes the old extra large as large
    ns.settings.gps.replaceMinimap = False
    lua.globals().SlashCmdList.AZEROTHGPS("replace xlarge")
    assert ns.settings.gps.replaceMinimapSize == "large"


def test_popups_open_over_the_map_opened_out_of_the_minimap(minimap):
    # (asked 2026-11-09: "when the pop out view from minimap is used, any new popup like options or streetview windows
    # should go on top of that") the map out at FULLSCREEN (over the world map, quest log, bags), our popups (ns.Window,
    # API.Window, the options) lifted over it while they show, back to their own strata after; one open keeps it out
    lua, ns = minimap
    G, st, O = ns.GPS, ns.settings.gps, ns.Options
    order = dict(ns.STRATA_ORDER.items())
    frame = lua.eval("AzerothGPSFrame")
    st.replaceMinimap = True
    G.ApplySettings()
    before = ns.Window("AzerothGPSTestBefore", 200, 100, "Before")  # (open as the map opens out)
    before.Show(before)
    api = lua.eval("AzerothGPS").Window("AzerothGPSTestApi", 200, 100, "Companion", None)
    api.Hide(api)
    # (an addon's own window, StreetView's viewer at HIGH: API.RegisterPopup, asked 2026-11-15)
    own = lua.eval("CreateFrame('Frame', 'AzerothGPSTestOwn', UIParent)")
    own.SetFrameStrata(own, "HIGH")
    lua.eval("AzerothGPS").RegisterPopup(own)
    own.Hide(own)
    try:
        assert before._strata == "DIALOG"
        G.SetMinimapExpanded(True)
        G.MinimapTick(0.3)
        assert frame._strata == G.MINIMAP_EXPANDED_STRATA == "FULLSCREEN"
        assert order[before._strata] > order[frame._strata]
        api.Show(api)
        api._scripts.OnShow(api)  # (the mock's Show runs no scripts)
        assert order[api._strata] > order[frame._strata]
        own.Show(own)
        own._scripts.OnShow(own)
        assert order[own._strata] > order[frame._strata]
        O.Show()
        opts = lua.eval("AzerothGPSOptions")
        opts._scripts.OnShow(opts)
        assert order[opts._strata] > order[frame._strata]
        if G.searchPanel:
            assert order[G.searchPanel._strata] > order[frame._strata]  # (the search's own panel)
        # the options over it: in use, the map doesn't go back under it (another window only while pointed at)
        lua.execute("AGPS_T = AGPS_T + 30")
        G.MinimapTick(0.3)
        assert G.mmState.expanded
        G.SetMinimapExpanded(False)
        G.MinimapTick(0.3)
        assert frame._strata == "BACKGROUND"
        for f, mine in ((before, "DIALOG"), (api, "DIALOG"), (opts, "DIALOG"), (own, "HIGH")):
            assert f._strata == mine and not f.agpsLifted  # (nothing left raised)
        assert G.searchPanel is None or G.searchPanel._strata == "DIALOG"
    finally:
        O.Toggle() if lua.eval("AzerothGPSOptions:IsShown()") else None
        before.Hide(before)
        api.Hide(api)

def test_the_minimap_masks_textures_are_shipped():
    # (the spike's path had single backslashes: Lua dropped them and the game got a missing texture, and the whole
    # minimap went blank, 2026-11-09) the clear mask is a file of ours, by a path the game can load
    from lupa import lua51

    src = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    line = re.search(r'^G\.MINIMAP_CLEAR = (".*?")', src, re.M).group(1)
    path = lua51.LuaRuntime().eval(line)
    assert path.startswith("Interface\\AddOns\\AzerothGPS\\"), path
    rel = path[len("Interface\\AddOns\\AzerothGPS\\"):].replace("\\", "/")
    tga = ADDON / (rel + ".tga")
    assert tga.is_file(), tga
    data = tga.read_bytes()
    w, h, bits = int.from_bytes(data[12:14], "little"), int.from_bytes(data[14:16], "little"), data[16]
    assert data[2] == 2 and bits == 32 and len(data) >= 18 + w * h * 4
    assert not any(data[18 + 3: 18 + w * h * 4: 4])  # (every pixel's alpha 0: nothing of the ground shown)
def test_minimize_leaves_only_the_logo_and_a_double_click_brings_the_map_back():
    # (asked 2026-11-09: a double-click on the map window's logo hides the map and leaves only
    # the logo on screen; a double-click on that logo brings the map back) the map's window frame (the client's
    # PortraitFrameTemplate, a stand-in) made with the map, so it has its title bar, close button and logo
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start, toc_files
    from azerothgps.paths import ADDON_DIR
    chrome = '''
      local real = CreateFrame
      CreateFrame = function(kind, name, parent, template)
        local w = real(kind, name, parent, template)
        if template == "PortraitFrameTemplate" and not w.NineSlice then
          w.NineSlice, w.Bg, w.PortraitContainer = real("Frame"), w:CreateTexture(), real("Frame")
          w.PortraitContainer.portrait = w:CreateTexture()
          w.TitleContainer = real("Frame")
          w.TitleContainer.TitleText = w:CreateFontString()
          w.CloseButton = real("Button")
        end
        return w
      end
    '''
    first = toc_files()[0]
    lua, ns = start(replace={first: chrome + (ADDON_DIR / first).read_text(encoding="utf-8")})
    G, st = ns.GPS, ns.settings.gps
    frame = lua.globals().AzerothGPSFrame
    st.shown = True
    G.ApplySettings()
    assert frame.IsShown(frame)
    # no title-bar button (the user, 2026-11-09: "just use the logo"): a double-click on the logo minimizes
    assert G.minimizeButton is None
    plate = G.logo.plate
    lua.execute("AGPS_T = 50")
    plate._scripts.OnMouseUp(plate, "LeftButton")
    lua.execute("AGPS_T = 50.2")
    plate._scripts.OnMouseUp(plate, "LeftButton")
    icon = lua.globals().AzerothGPSMiniIcon
    assert st.minimized and not frame.IsShown(frame) and icon.IsShown(icon)
    # kept over a /reload (saved), and the logo's double-click brings it back
    G.ApplySettings()
    assert not frame.IsShown(frame) and icon.IsShown(icon)
    icon._scripts.OnDoubleClick(icon)
    assert not st.minimized and frame.IsShown(frame) and not icon.IsShown(icon)
    # a double-click on the window's own logo minimizes too (two clicks close together; one alone doesn't)
    plate = G.logo.plate
    up = plate._scripts.OnMouseUp
    lua.execute("AGPS_T = 100")
    up(plate, "LeftButton")
    assert frame.IsShown(frame)
    lua.execute("AGPS_T = 100.2")
    up(plate, "LeftButton")
    assert st.minimized and not frame.IsShown(frame)
    # /agps show and the key binding bring it back too; /agps hide hides it (the logo with it)
    lua.globals().SlashCmdList.AZEROTHGPS("show")
    assert not st.minimized and frame.IsShown(frame)
    G.SetMinimized(True)
    lua.globals().AzerothGPS_ToggleMap()
    assert not st.minimized and st.shown and frame.IsShown(frame)
    G.SetMinimized(True)
    lua.globals().SlashCmdList.AZEROTHGPS("hide")
    assert not st.shown and not icon.IsShown(icon)
    lua.globals().SlashCmdList.AZEROTHGPS("show")
    assert frame.IsShown(frame) and not icon.IsShown(icon)
    # a right-click on the logo opens the options, the window's and the minimized one (the user, 2026-11-09)
    lua.execute("AGPS_OPTS = 0 AGPS_NS.Options.Show = function() AGPS_OPTS = AGPS_OPTS + 1 end")
    plate._scripts.OnMouseUp(plate, "RightButton")
    assert lua.eval("AGPS_OPTS") == 1 and frame.IsShown(frame)
    G.SetMinimized(True)
    icon._scripts.OnClick(icon, "RightButton")
    assert lua.eval("AGPS_OPTS") == 2 and st.minimized


def test_the_minimap_given_back_never_keeps_one_of_our_masks_and_sets_its_own_again(game):
    # (seen in game 2026-11-10: "sometimes when standing still and expanding the map the minimap does this": the round
    # minimap back with square ground)
    lua, ns = game
    G = ns.GPS
    lua.execute(MM_SETUP)
    st = ns.settings.gps
    calls = lua.eval("{}")
    lua.execute("AGPS_AFTERS = {}; AGPS_REAL_AFTER = C_Timer.After; C_Timer.After = function(s, fn) AGPS_AFTERS[#AGPS_AFTERS + 1] = fn end")
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        m = G.mmState
        assert m.applied
        own = m.was.mask
        # taken again while one of our masks is still on it: its own is the one remembered, not ours
        G.OnMinimapMask(G.MINIMAP_SQUARE)
        G.CaptureMinimap()
        assert m.was.mask == own and m.was.mask not in (G.MINIMAP_SQUARE, G.MINIMAP_CLEAR)
        lua.execute("AGPS_AFTERS = {}")
        G.RestoreMinimap()
        back = G.minimapMask
        assert back not in (G.MINIMAP_SQUARE, G.MINIMAP_CLEAR)
        afters = list(lua.eval("AGPS_AFTERS").values())
        assert len(afters) == 2  # (set again a moment later, twice)
        assert G.MinimapMaskAgain(back) is True
        G.OnMinimapMask("Interface\\Other\\Mask")  # (another addon's since: theirs stays)
        assert G.MinimapMaskAgain(back) is False
        G.OnMinimapMask(back)
        # the square's border sits evenly round the frame
        assert list(G.MINIMAP_BORDER_FIT.values()) == [1.5, 3.5, 1.5, -0.5]
    finally:
        lua.execute("C_Timer.After = AGPS_REAL_AFTER")
        st.replaceMinimap = False
        G.ApplySettings()


def test_the_square_goes_where_the_minimap_was_under_a_minimap_addon(game):
    # (seen with EllesmereUI 2026-11-10: it parents the minimap to the whole screen and anchors it to a corner; the
    # square went by the container's middle and landed away from the minimap's place)
    lua, ns = game
    G = ns.GPS
    lua.execute(MM_SETUP)
    st = ns.settings.gps
    lua.execute("""
      AGPS_OLD_MM_PARENT, AGPS_OLD_MM_CENTER = Minimap._parent, Minimap.GetCenter
      Minimap._parent = UIParent
      local ux, uy = UIParent:GetCenter()
      Minimap.GetCenter = function() return ux + 700, uy + 380 end -- (near the top right, 99 from its own edges)
    """)
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        m = G.mmState
        assert m.on and abs(m.home.dx - 700) < 0.01 and abs(m.home.dy - 380) < 0.01
        corner, home, ox, oy = G.MinimapCorner(200)[0:4]
        # the square's top right corner on the old minimap's top right corner
        assert corner == "TOPRIGHT" and abs(ox - (700 + 99)) < 0.01 and abs(oy - (380 + 99)) < 0.01
    finally:
        st.replaceMinimap = False
        G.ApplySettings()
        lua.execute("Minimap._parent, Minimap.GetCenter = AGPS_OLD_MM_PARENT, AGPS_OLD_MM_CENTER")


def test_the_square_follows_the_minimap_when_another_addon_moves_it(game):
    # (issue #324: EllesmereUI moving the minimap after the square took its place; the square stayed where the minimap
    # first was. Hooked on the Minimap's SetPoint in the game; the stand-in's hooksecurefunc does nothing, so called)
    lua, ns = game
    G = ns.GPS
    lua.execute(MM_SETUP)
    st = ns.settings.gps
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        m = G.mmState
        assert m.on and m.applied and m.placedKey
        assert G.OnMinimapMoved() is False  # (only on our anchor: nothing of theirs)
        # their mover: the minimap on the whole screen, by its top right corner (the stand-in's UIParent: 100..500)
        lua.execute("""
          Minimap._parent = UIParent
          Minimap:ClearAllPoints()
          Minimap:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -20, -30)
        """)
        m.moves = None
        assert G.OnMinimapMoved() is True
        # its middle at its own size (198), not the square's, from UIParent's middle
        u = lua.eval("{ UIParent:GetLeft(), UIParent:GetBottom(), UIParent:GetWidth(), UIParent:GetHeight(), UIParent:GetCenter() }")
        dx, dy = u[1] + u[3] - 20 - 99 - u[5], u[2] + u[4] - 30 - 99 - u[6]
        assert lua.eval("rawequal")(m.home.parent, lua.eval("UIParent"))
        assert abs(m.home.dx - dx) < 0.01 and abs(m.home.dy - dy) < 0.01
        # the Minimap on the square's anchor again, theirs kept to give back
        pts = lua.eval("function() local t = {} for k, p in pairs(Minimap._pts) do t[#t + 1] = p end return t end")()
        assert len(pts) == 1 and pts[1][1] == "CENTER" and lua.eval("rawequal")(pts[1][2], G.mmAnchor)
        assert len(m.was.points) == 1 and m.was.points[1][1] == "TOPRIGHT" and m.was.points[1][4] == -20
        corner, home, ox, oy = G.MinimapCorner(200)[0:4]
        assert lua.eval("rawequal")(home, lua.eval("UIParent"))
        # (the square's corner on the moved minimap's corner)
        assert min(abs(ox - dx - 99), abs(ox - dx + 99)) < 0.01 and min(abs(oy - dy - 99), abs(oy - dy + 99)) < 0.01
        # our own placing is never taken for a move
        G.minimapPlacing = True
        assert G.OnMinimapMoved() is False
        G.minimapPlacing = None
        # a mover putting it back each time we place it isn't fought forever
        m.moves = None
        again = lua.eval("""function(G)
          Minimap:ClearAllPoints()
          Minimap:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -20, -30)
          return G.OnMinimapMoved()
        end""")
        n = sum(1 for _ in range(G.MINIMAP_MOVED_MAX + 3) if again(G))
        assert n == G.MINIMAP_MOVED_MAX
        # off: given back where they put it
        st.replaceMinimap = False
        G.ApplySettings()
        pts = lua.eval("function() local t = {} for k, p in pairs(Minimap._pts) do t[#t + 1] = p end return t end")()
        assert len(pts) == 1 and pts[1][1] == "TOPRIGHT" and pts[1][4] == -20 and pts[1][5] == -30
        assert G.OnMinimapMoved() is False  # (off: nothing to follow)
    finally:
        st.replaceMinimap = False
        G.ApplySettings()
        G.minimapPlacing = None


def test_orgrimmars_transmogrifier_is_down_in_the_cleft_of_shadow(game):
    # (seen in game 2026-11-10: "transmogifier is in cleft of shadows, not where this route is saying". A guard's
    # marker has no height, and with none the route ended on the ledge over the Cleft, 103 yd from the Valley of
    # Strength; the place is shipped now with the Cleft's floor, which a guard's marker of that name takes:
    # Layers' PlaceZ)
    lua, ns = game
    R, L = ns.Router, ns.Layers
    place = [p for p in ns.CityPlaces[1454].values() if hasattr(p, "values") and str(p[3]) == "Orgrimmar Transmogrifier"]
    assert len(place) == 1
    xy = lua.eval("function(L, u, v) local x, y = L.MapToWorld(1454, u, v) return { x, y } end")
    tx, ty = xy(L, place[0][1] / 100, place[0][2] / 100).values()
    px, py = xy(L, 0.490, 0.587).values()
    tz = L.PlaceZ(1, tx + 5, ty - 5, "Orgrimmar Transmogrifier")  # (the guard's marker there: the place's height)
    assert tz == place[0][4] and tz < 15
    r = R.Route(1, px, py, tx, ty, lua.table_from({"tz": tz}))
    assert r and not r.unconnected and r.fz
    n = len(r.pts) // 2
    pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
    assert abs(r.fz[n] - tz) <= 3.5  # (on the Cleft's floor, not the ledge 29 yd over it)
    # (round and down into it; or, out of combat with the health hidden (Nav.FALL_SECRET_HEALTH, Kooki3z 2026-11-20:
    # "you can safely jump down from areas in org"), by a jump down the ledge, a drop)
    kinds = [r.kinds[i] for i in range(1, n)]
    assert sum(math.dist(pts[k], pts[k + 1]) for k in range(n - 1)) > 400 or R.KIND_DROP in kinds


def test_the_minimap_square_is_always_the_seamless_map_whatever_the_style(minimap):
    # (asked 2026-11-10: "changing the map mode ... shouldn't change the minimap if enabled, should always be using
    # seamless view": the style picked is the opened map's)
    lua, ns = minimap
    G, st, A = ns.GPS, ns.settings.gps, ns.Atlas
    was = (st.style, G.artSpan, A.loaded, A.artFailed)
    try:
        st.style = "minimap"
        assert not A.Wanted()
        st.replaceMinimap = True
        assert A.Wanted()  # (its art loaded at login for the square)
        G.ApplySettings()
        assert G.MinimapMode()
        G.artSpan, A.loaded, A.artFailed = 0, False, None
        assert G.Style() == "minimap" and not G.Seamless()  # (not loaded this session: the style picked, till a /reload)
        G.artSpan, A.loaded = 12, True
        for style in ("minimap", "zone", "nospoiler", "seamless"):
            st.style = style
            assert G.Style() == "seamless" and G.Seamless()
        st.style = "zone"
        G.mmState.expanded = True  # (opened out of the square: the style picked)
        assert G.Style() == "zone" and not G.Seamless()
        G.mmState.expanded = None
        st.replaceMinimap = False
        G.ApplySettings()
        assert G.Style() == "zone" and not A.Wanted()
    finally:
        st.style, G.artSpan, A.loaded, A.artFailed = was
        G.mmState.expanded = None


def test_the_way_into_ungoro_is_the_pass_from_tanaris_not_over_the_craters_wall(game):
    # (seen in game 2026-11-10: "why is this route jumping across? this isn't accessible": Un'Goro's roads were joined
    # to the rest by one link alone, 1,192 yd over the crater's wall from Thousand Needles, and the open desert from
    # Gadgetzan to the pass was priced as blocked all its length for a building on its line)
    lua, ns = game
    R, L = ns.Router, ns.Layers
    xy = lua.eval("function(L, m, u, v) local x, y = L.MapToWorld(m, u, v) return { x, y } end")
    refuge = tuple(xy(L, 1449, 0.45, 0.08).values())
    gate = tuple(xy(L, 1446, 0.272, 0.582).values())  # (the pass's mouth in Tanaris)
    # (and for a low character too, Tanaris four times as dear a yard for them: "still doing the hop" at level 17,
    # the same day; a long jump over blocked ground is the last resort whatever the way round costs)
    lua.execute("AGPS_UL = UnitLevel")
    try:
        for level in (60, 17):
            lua.globals().AGPS_LVL = level
            lua.execute("UnitLevel = function() return AGPS_LVL end")
            R.Reset()
            # (Freewind Post, Gadgetzan, Camp Taurajo: from there the way round is 6,000 yd longer than the jump)
            for start in ((1441, 0.45, 0.50), (1446, 0.51, 0.28), (1413, 0.445, 0.59)):
                px, py = xy(L, *start).values()
                r = R.Route(1, px, py, *refuge)
                assert r and not r.unconnected and r.blocked is None, (level, start)
                n = len(r.pts) // 2
                pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
                assert min(math.dist(p, gate) for p in pts) < 300, (level, start)
        # (as in the game, the walks searched in the background: the jump only while its search runs, `pending`)
        import time
        clock = lambda: time.perf_counter() * 1000  # noqa: E731
        R.WARM, R.SYNC_WALKS = True, False
        R.Reset()
        px, py = xy(L, 1413, 0.445, 0.59).values()
        r = R.Route(1, px, py, *refuge)
        for _ in range(40):
            if not r.pending:
                break
            while R.HasWork():
                R.Pump(clock() + 50, clock)
            r = R.Route(1, px, py, *refuge)
        assert not r.pending and r.blocked is None
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        lua.execute("UnitLevel = AGPS_UL AGPS_UL, AGPS_LVL = nil, nil")
        R.Reset()


def test_the_games_minimap_dots_are_over_the_squares_icons(minimap):
    # (asked 2026-11-10: "for the herb/mine indicator shown by the game make those show on top of our icons so the
    # player knows if the node is actually there or not": the game's Minimap, its dots drawn by it, is never in the
    # map's own strata while it's on the square, and gets its own back after)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    order = ["BACKGROUND", "LOW", "MEDIUM", "HIGH"]
    frame = lua.eval("AzerothGPSFrame")
    for own in ("BACKGROUND", "LOW"):
        lua.execute("Minimap._strata = '%s'" % own)
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode()
        assert order.index(lua.eval("Minimap:GetFrameStrata()")) > order.index(frame.GetFrameStrata(frame))
        st.replaceMinimap = False
        G.ApplySettings()
        assert lua.eval("Minimap:GetFrameStrata()") == own
    lua.execute("Minimap._strata = nil")


def test_a_secret_cooldown_is_read_as_the_last_one_seen_not_an_error(game):
    # (in the saved errors 2026-11-06: "Teleports.lua:38: attempt to compare local 'start' (a secret number value",
    # which stopped the map's redraw)
    lua, ns = game
    T = ns.Teleports
    lua.execute("""
      AGPS_SECRET = {}
      AGPS_CD = { 0, 0 }
      AGPS_WAS = { secret = AGPS_NS.IsSecret, spell = C_Spell and C_Spell.GetSpellCooldown, old = GetSpellCooldown, time = GetTime,
        cspell = C_Spell }
      AGPS_NS.IsSecret = function(v) return v == AGPS_SECRET end
      C_Spell = nil
      GetSpellCooldown = function() return AGPS_CD[1], AGPS_CD[2] end
      GetTime = function() return 1000 end
    """)
    try:
        t = lua.eval("{ spell = 8690 }")
        assert T.CooldownLeft(t) == 0
        lua.execute("AGPS_CD = { AGPS_SECRET, AGPS_SECRET }")
        assert T.CooldownLeft(t) == 0  # (secret, none read before: ready)
        lua.execute("AGPS_CD = { 900, 600 }")
        assert T.CooldownLeft(t) == 500
        lua.execute("AGPS_CD = { AGPS_SECRET, AGPS_SECRET }")
        assert T.CooldownLeft(t) == 500  # (secret: the last one read)
        lua.execute("AGPS_CD = { 900, AGPS_SECRET }")
        assert T.CooldownLeft(t) == 500
    finally:
        lua.execute("""
          AGPS_NS.IsSecret, GetSpellCooldown, GetTime, C_Spell = AGPS_WAS.secret, AGPS_WAS.old, AGPS_WAS.time, AGPS_WAS.cspell
          AGPS_SECRET, AGPS_CD, AGPS_WAS = nil, nil, nil
        """)


def test_the_group_finder_eye_sits_outside_the_square_and_goes_back_with_the_minimap(minimap):
    # (seen in game 2026-11-10: "looking for group eyeball is center of minimap")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      QueueStatusButton = NewWidget("Button", "QueueStatusButton")
      AGPS_EYE = { pts = { { "TOPLEFT", Minimap, "TOPLEFT", 20, -100 } }, default = true }
      QueueStatusButton.GetNumPoints = function() return #AGPS_EYE.pts end
      QueueStatusButton.GetPoint = function(_, i) return unpack(AGPS_EYE.pts[i]) end
      QueueStatusButton.ClearAllPoints = function() AGPS_EYE.pts = {} end
      QueueStatusButton.SetPoint = function(_, ...) AGPS_EYE.pts[#AGPS_EYE.pts + 1] = { ... } end
      QueueStatusButton.IsInDefaultPosition = function() return AGPS_EYE.default end
    """)
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode()
        lua.globals().AGPS_A = G.mmAnchor
        p = lua.eval("AGPS_EYE.pts[1]")
        assert lua.eval("#AGPS_EYE.pts") == 1 and p[1] == "TOPRIGHT" and p[3] == "TOPLEFT"
        assert lua.eval("AGPS_EYE.pts[1][2] == AGPS_A")
        st.replaceMinimap = False
        G.ApplySettings()
        p = lua.eval("AGPS_EYE.pts[1]")
        assert p[1] == "TOPLEFT" and p[4] == 20 and p[5] == -100 and lua.eval("AGPS_EYE.pts[1][2] == Minimap")
        # (moved by the player in Edit Mode: left where they put it)
        lua.execute("AGPS_EYE.default = false AGPS_EYE.pts = { { \"CENTER\", UIParent, \"CENTER\", 300, 0 } }")
        st.replaceMinimap = True
        G.ApplySettings()
        assert lua.eval("AGPS_EYE.pts[1][1]") == "CENTER" and lua.eval("AGPS_EYE.pts[1][4]") == 300
        # (with the game's controller UI on: never moved, and put back if it was; a player's report 2026-11-16, "crashed
        # when joining dungeons with gamepad UI": the group finder's own protected code as its popups show)
        st.replaceMinimap = False
        G.ApplySettings()
        lua.execute("AGPS_EYE.default = true AGPS_EYE.pts = { { \"TOPLEFT\", Minimap, \"TOPLEFT\", 20, -100 } } "
                    "AGPS_CUI = AGPS_NS.GPS.ControllerUI AGPS_NS.GPS.ControllerUI = function() return AGPS_GAMEPAD end "
                    "AGPS_GAMEPAD = false")
        st.replaceMinimap = True
        G.ApplySettings()
        assert lua.eval("AGPS_EYE.pts[1][2] == AGPS_A")  # (moved: the controller UI off)
        lua.execute("AGPS_GAMEPAD = true")
        G.PlaceQueueEye(True)  # (as the square is taken again after the switch, G.MinimapInputChanged)
        assert lua.eval("AGPS_EYE.pts[1][2] == Minimap") and lua.eval("AGPS_EYE.pts[1][4]") == 20  # (put back)
        G.PlaceQueueEye(True)
        assert lua.eval("AGPS_EYE.pts[1][2] == Minimap")  # (and never moved again)
    finally:
        lua.execute("if AGPS_CUI then AGPS_NS.GPS.ControllerUI = AGPS_CUI end AGPS_CUI, AGPS_GAMEPAD = nil, nil")
        st.replaceMinimap = False
        G.ApplySettings()
        lua.execute("QueueStatusButton, AGPS_EYE, AGPS_A = nil, nil, nil")


def test_in_an_instance_the_games_minimap_fills_the_square_and_a_battleground_has_no_arrow_or_directions(minimap):
    # (seen in game 2026-11-10: "In battlegrounds and this is my map, this is a problem", the square showing
    # Orgrimmar from inside one; "in battlegrounds, pause routing and don't show arrow and directions while in there";
    # asked 2026-11-11: "is it possible to keep the shape and still use the game's map in instances so movement is
    # still tracked?")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    frame = lua.eval("AzerothGPSFrame")
    lua.execute("AGPS_INST = { false, \"none\" } AGPS_III = IsInInstance "
                "IsInInstance = function() return AGPS_INST[1], AGPS_INST[2] end")
    was = (st.shown, st.minimized, st.arrow, st.replaceMinimapHide)
    canvas = G.Canvas()
    try:
        st.shown, st.minimized, st.arrow = True, None, True
        for how in ("ground", "mask"):
            st.replaceMinimapHide = how
            st.replaceMinimap = True
            G.ApplySettings()
            ns.Arrow.Apply()
            assert G.MinimapMode() and not ns.InBattleground()
            arrow = lua.eval("AzerothGPSArrow")
            assert arrow is not None and arrow.IsShown(arrow)
            out = (lua.eval("AGPS_MM.mask"), lua.eval("AGPS_MM.ground"))
            assert out[0] == (G.MINIMAP_CLEAR if how == "mask" else G.MINIMAP_SQUARE)
            side = lua.eval("Minimap:GetWidth()")
            for kind in ("party", "pvp"):
                lua.execute("AGPS_INST = { true, \"%s\" }" % kind)
                G.mmEvents._scripts.OnEvent(G.mmEvents, "PLAYER_ENTERING_WORLD")
                # (the square still there, the game's minimap in it: square, the same size, its ground drawn, the
                # map's own picture not shown under it)
                assert G.MinimapMode() and G.mmState.on and G.mmState.applied
                assert frame._shown is True and st.replaceMinimap is True
                assert lua.eval("AGPS_MM.mask") == G.MINIMAP_SQUARE and lua.eval("AGPS_MM.ground") is True
                assert lua.eval("Minimap:GetWidth()") == side
                assert canvas._shown is False
                assert ns.InBattleground() == (kind == "pvp")
                assert bool(arrow.IsShown(arrow)) == (kind != "pvp")
                # (out again: the map in the square, the minimap's ground hidden as before)
                lua.execute("AGPS_INST = { false, \"none\" }")
                G.mmEvents._scripts.OnEvent(G.mmEvents, "PLAYER_ENTERING_WORLD")
                assert G.MinimapMode() and frame._shown is True and arrow.IsShown(arrow)
                assert canvas._shown is not False
                assert (lua.eval("AGPS_MM.mask"), lua.eval("AGPS_MM.ground")) == out
            # (the option turned off in there: the canvas back with the minimap)
            lua.execute("AGPS_INST = { true, \"party\" }")
            G.mmEvents._scripts.OnEvent(G.mmEvents, "PLAYER_ENTERING_WORLD")
            assert canvas._shown is False
            st.replaceMinimap = False
            G.ApplySettings()
            assert canvas._shown is not False and not G.mmState.applied
            lua.execute("AGPS_INST = { false, \"none\" }")
    finally:
        lua.execute("IsInInstance = AGPS_III AGPS_III, AGPS_INST = nil, nil")
        st.shown, st.minimized, st.arrow, st.replaceMinimapHide = was
        st.replaceMinimap = False
        G.ApplySettings()
        ns.Arrow.Apply()


def test_the_use_button_is_not_shown_over_the_minimap_square(minimap):
    # (asked 2026-11-10: "when route is suggesting hearthstone its on the minimap as well, don't show that")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("AGPS_USE = {} AGPS_SUB = AGPS_NS.GPS.SetUseButton "
                "AGPS_NS.GPS.SetUseButton = function(b, t) AGPS_USE.t = t AGPS_USE.n = (AGPS_USE.n or 0) + 1 end")
    try:
        t = lua.eval("{ 1, 2, 3, 4, 5, 6, 7, \"hearth\", 9, \"Orgrimmar\" }")
        G.UpdateUseButton(t)
        assert lua.eval("AGPS_USE.t ~= nil")
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode()
        G.UpdateUseButton(t)
        assert lua.eval("AGPS_USE.t == nil") and lua.eval("AGPS_USE.n") == 2
    finally:
        lua.execute("AGPS_NS.GPS.SetUseButton = AGPS_SUB AGPS_SUB, AGPS_USE = nil, nil")
        st.replaceMinimap = False
        G.ApplySettings()


def test_the_minimap_given_back_is_drawn_again_at_once(minimap):
    # (seen in game 2026-11-11: "still see this bug when standing still, opening the GPS map from minimap mode, if I'm
    # moving and I open it looks normal": the game draws its minimap again only as the player moves, so given back
    # to a player standing still it kept the square's picture. Its zoom to another level and back draws it now.)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_ZOOMS = {}
      Minimap.SetZoom = function(_, z) AGPS_MM.zoom = z AGPS_ZOOMS[#AGPS_ZOOMS + 1] = z end
      Minimap.GetZoomLevels = function() return 6 end
      AGPS_AFTERS = {} AGPS_REAL_AFTER = C_Timer.After
      C_Timer.After = function(s, fn) AGPS_AFTERS[#AGPS_AFTERS + 1] = fn end
    """)
    try:
        for zoom, other in ((1, 2), (5, 4), (0, 1)):
            lua.execute("AGPS_MM.zoom = %d" % zoom)
            st.replaceMinimap = True
            G.ApplySettings()
            assert G.mmState.applied
            lua.execute("AGPS_ZOOMS = {} AGPS_AFTERS = {}")
            G.SetMinimapExpanded(True)  # (opened out of the square: the game's minimap given back)
            assert not G.mmState.applied
            assert list(lua.eval("AGPS_ZOOMS").values()) == [other, zoom]
            # (and with its mask set once more a moment later)
            lua.execute("AGPS_ZOOMS = {}")
            for fn in list(lua.eval("AGPS_AFTERS").values()):
                fn()
            zs = list(lua.eval("AGPS_ZOOMS").values())
            assert zs and zs[-1] == zoom and lua.eval("AGPS_MM.zoom") == zoom
            # (back on the square: nothing of the kind, its ground isn't drawn)
            lua.execute("AGPS_ZOOMS = {}")
            G.SetMinimapExpanded(False)
            assert G.mmState.applied and lua.eval("#AGPS_ZOOMS") == 0
            st.replaceMinimap = False
            G.ApplySettings()
    finally:
        st.replaceMinimap = False
        G.ApplySettings()
        lua.execute("C_Timer.After = AGPS_REAL_AFTER Minimap.SetZoom, Minimap.GetZoomLevels = nil, nil "
                    "AGPS_ZOOMS, AGPS_AFTERS, AGPS_REAL_AFTER = nil, nil, nil")
def test_the_minimaps_zoom_buttons_sit_in_the_squares_corner_and_go_back_with_the_minimap(minimap):
    # (seen in game 2026-11-11: the + and - inside the map, "can these be moved?")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_Z = {}
      for _, key in ipairs({ "ZoomIn", "ZoomOut", "ZoomHitArea" }) do
        local b = NewWidget("Button", nil)
        local pts = { { "CENTER", Minimap, "CENTER", 88, -68 } }
        AGPS_Z[key] = function() return pts end
        b.GetNumPoints = function() return #pts end
        b.GetPoint = function(_, i) return unpack(pts[i]) end
        b.ClearAllPoints = function() pts = {} end
        b.SetPoint = function(_, ...) pts[#pts + 1] = { ... } end
        Minimap[key] = b
      end
    """)
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode()
        for key in ("ZoomIn", "ZoomOut", "ZoomHitArea"):
            p = lua.eval("AGPS_Z.%s()[1]" % key)
            assert lua.eval("#AGPS_Z.%s()" % key) == 1 and p[1] == "CENTER" and p[3] == "BOTTOMRIGHT"
            assert lua.eval("AGPS_Z.%s()[1][2] == Minimap" % key)
            assert p[4] == G.ZOOM_BUTTONS_AT[key][1] and p[5] == G.ZOOM_BUTTONS_AT[key][2]
        G.ApplySettings()  # (again: nothing remembered over their own places)
        st.replaceMinimap = False
        G.ApplySettings()
        for key in ("ZoomIn", "ZoomOut", "ZoomHitArea"):
            p = lua.eval("AGPS_Z.%s()[1]" % key)
            assert p[3] == "CENTER" and p[4] == 88 and p[5] == -68
    finally:
        st.replaceMinimap = False
        G.ApplySettings()
        lua.execute("Minimap.ZoomIn, Minimap.ZoomOut, Minimap.ZoomHitArea, AGPS_Z = nil, nil, nil, nil")


def test_the_day_and_night_button_sits_on_the_squares_top_right_corner_and_goes_back(minimap):
    # (seen in game 2026-11-11: the sun in the square's top edge, "what about this one? maybe top right corner")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_HAD_CLUSTER = MinimapCluster
      MinimapCluster = MinimapCluster or {}
      local b = NewWidget("Frame", nil)
      AGPS_DN = { pts = { { "CENTER", MinimapContainer, "CENTER", 55, 86 } } }
      b.GetNumPoints = function() return #AGPS_DN.pts end
      b.GetPoint = function(_, i) return unpack(AGPS_DN.pts[i]) end
      b.ClearAllPoints = function() AGPS_DN.pts = {} end
      b.SetPoint = function(_, ...) AGPS_DN.pts[#AGPS_DN.pts + 1] = { ... } end
      MinimapCluster.DielFrame = b
      -- (the game's own: its place again at each Edit Mode scale)
      MinimapCluster.SetEditModeScale = function() AGPS_DN.pts = { { "CENTER", MinimapContainer, "CENTER", 55, 86 } } end
      AGPS_HOOK = hooksecurefunc
      hooksecurefunc = function(t, name, fn)
        local was = t[name]
        t[name] = function(...) was(...) fn(...) end
      end
    """)
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode()
        lua.globals().AGPS_A = G.mmAnchor

        def on_corner():
            p = lua.eval("AGPS_DN.pts[1]")
            return (lua.eval("#AGPS_DN.pts") == 1 and p[1] == "CENTER" and p[3] == "TOPRIGHT"
                    and lua.eval("AGPS_DN.pts[1][2] == AGPS_A"))
        assert on_corner()
        lua.execute("MinimapCluster.SetEditModeScale(MinimapCluster, 1)")  # (the game places it again: ours after)
        assert on_corner()
        st.replaceMinimap = False
        G.ApplySettings()
        p = lua.eval("AGPS_DN.pts[1]")
        assert p[3] == "CENTER" and p[4] == 55 and p[5] == 86 and lua.eval("AGPS_DN.pts[1][2] == MinimapContainer")
        lua.execute("MinimapCluster.SetEditModeScale(MinimapCluster, 1)")  # (the minimap its own: left where the game puts it)
        assert lua.eval("AGPS_DN.pts[1][3]") == "CENTER"
    finally:
        st.replaceMinimap = False
        G.ApplySettings()
        lua.execute("hooksecurefunc = AGPS_HOOK MinimapCluster.DielFrame, MinimapCluster.SetEditModeScale = nil, nil "
                    "MinimapCluster = AGPS_HAD_CLUSTER AGPS_DN, AGPS_A, AGPS_HOOK, AGPS_HAD_CLUSTER = nil, nil, nil, nil")
        G.dayNightHooked = None


def test_the_square_is_never_a_dungeons_map_in_or_out_of_one_whatever_the_events_say(minimap):
    # (seen in game 2026-11-11, 1.2.0: "when I enter a dungeon the minimap is initially loaded with the GPS dungeon
    # map ... when leaving the dungeon the minimap is back on the dungeon map"; "Collapsing the map with dungeon map
    # up never replaces the minimap with the dungeon map". The game's events alone weren't enough: where the player
    # is is looked at again a few times a second.)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    lua.execute("AGPS_INST = { false, \"none\" } AGPS_III = IsInInstance "
                "IsInInstance = function() return AGPS_INST[1], AGPS_INST[2] end")
    canvas = G.Canvas()
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode() and canvas._shown is not False
        assert G.MinimapAwayCheck(1) is False  # (nothing to do)
        # into a dungeon with no event heard: the game's minimap in the square at the next look
        lua.execute("AGPS_INST = { true, \"party\" }")
        assert G.MinimapAwayCheck(0.1) is False  # (not yet: a few times a second)
        assert G.MinimapAwayCheck(0.2) is True
        assert canvas._shown is False and lua.eval("AGPS_MM.ground") is True and G.MinimapMode()
        assert G.MinimapAwayCheck(1) is False
        # in combat: left for after it
        lua.execute("AGPS_INST = { false, \"none\" } InCombatLockdown = function() return true end")
        assert G.MinimapAwayCheck(1) is False and canvas._shown is False
        lua.execute("InCombatLockdown = function() return false end")
        # out again with no event heard, the dungeon's map still the view: the map back, on the player
        some = next(iter(k for k, m in ns.Maps.items() if m.bounds))
        G.Browse(some)
        assert G.BrowseState()[0] == some
        assert G.MinimapAwayCheck(1) is True
        assert canvas._shown is not False and lua.eval("AGPS_MM.ground") is False
        assert G.BrowseState()[0] is None and G.BrowseState()[1] is None
        # opened out with a map looked at, sent back to the square: on the player again
        G.SetMinimapExpanded(True)
        G.Browse(some)
        assert G.BrowseState()[0] == some
        assert G.MinimapAwayCheck(1) is False  # (not while it's opened out)
        G.SetMinimapExpanded(False)
        assert G.BrowseState()[0] is None and G.BrowseState()[1] is None
    finally:
        lua.execute("IsInInstance = AGPS_III AGPS_III, AGPS_INST = nil, nil InCombatLockdown = function() return false end")
        st.replaceMinimap = False
        G.ApplySettings()


def test_the_square_is_the_games_minimap_wherever_there_is_no_position_and_it_draws_at_once(minimap):
    # (seen in game 2026-11-11, 1.2.1: "if routed to a dungeon and I reload I get this [the dungeon's map in the
    # square] and still after exiting the dungeon. When entering a dungeon i get a blank screen like this until I
    # start moving"; "also get dungeon map after reloads at the entrance but not in the dungeon or routed to it")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    canvas = G.Canvas()
    lua.execute("""
      AGPS_ZOOMS = {}
      Minimap.SetZoom = function(_, z) AGPS_MM.zoom = z AGPS_ZOOMS[#AGPS_ZOOMS + 1] = z end
      Minimap.GetZoomLevels = function() return 6 end
      AGPS_AFTERS = {} AGPS_REAL_AFTER = C_Timer.After
      C_Timer.After = function(s, fn) AGPS_AFTERS[#AGPS_AFTERS + 1] = fn end
      AGPS_REAL_PW = AGPS_NS.Geo.PlayerWorld
    """)
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode() and not G.MinimapAway() and canvas._shown is not False
        # the game gives no position (and says "not in an instance"): the game's minimap in the square
        lua.execute("AGPS_NS.Geo.PlayerWorld = function() return nil end AGPS_ZOOMS = {} AGPS_AFTERS = {}")
        assert G.MinimapAway() is True
        assert G.MinimapAwayCheck(1) is True
        assert canvas._shown is False and lua.eval("AGPS_MM.ground") is True
        # ... made to draw at once (its zoom to another level and back), and again a moment later
        assert list(lua.eval("AGPS_ZOOMS").values()) == [2, 1]
        afters = list(lua.eval("AGPS_AFTERS").values())
        assert len(afters) == len(list(G.MINIMAP_AWAY_AGAIN.values()))
        lua.execute("AGPS_ZOOMS = {}")
        afters[0]()
        assert list(lua.eval("AGPS_ZOOMS").values()) == [2, 1]
        # the position back: the map again, and the leftover timers do nothing
        lua.execute("AGPS_NS.Geo.PlayerWorld = AGPS_REAL_PW AGPS_ZOOMS = {}")
        assert G.MinimapAwayCheck(1) is True
        assert canvas._shown is not False and lua.eval("AGPS_MM.ground") is False
        afters[1]()
        assert lua.eval("#AGPS_ZOOMS") == 0
        # the player on a dungeon's own map with a position given: the game's minimap too
        lua.execute("AGPS_REAL_IL = AGPS_NS.Nav.InstanceLevel AGPS_NS.Nav.InstanceLevel = function() return 99999 end")
        assert G.MinimapAway() is True
        lua.execute("AGPS_NS.Nav.InstanceLevel = AGPS_REAL_IL")
        assert G.MinimapAway() is False
    finally:
        lua.execute("AGPS_NS.Geo.PlayerWorld = AGPS_REAL_PW if AGPS_REAL_IL then AGPS_NS.Nav.InstanceLevel = AGPS_REAL_IL end "
                    "C_Timer.After = AGPS_REAL_AFTER Minimap.SetZoom, Minimap.GetZoomLevels = nil, nil "
                    "AGPS_ZOOMS, AGPS_AFTERS, AGPS_REAL_AFTER, AGPS_REAL_PW, AGPS_REAL_IL = nil, nil, nil, nil, nil")
        st.replaceMinimap = False
        G.ApplySettings()


def test_a_player_with_the_arrow_locked_gets_it_unlocked_once_and_is_told_how_to_lock_it(game):
    # (asked 2026-11-11: "One time pop up for existing users to ask if they want to unlock the arrow and directions and
    # how they can lock it back", then: "preemptively set them to unlocked", the text "Directions and the arrow are now
    # unlocked by default. You can move them now if you wish.", the buttons "[Leave Unlocked] [Lock]", and "needs
    # azeroth standardizing for all windows, logo, color, etc just like tutorial pages")
    lua, ns = game
    A, st, db = ns.Arrow, ns.settings.gps, ns.db
    was = (st.arrowLocked, st.arrow, db.arrowUnlockOffered, ns.inCombat)
    click = lambda b: b._scripts.OnClick(b)  # noqa: E731
    try:
        # a new install, or unlocked already: never, now or later
        A.unlockAsk, db.arrowUnlockOffered = None, None
        st.arrow, st.arrowLocked, ns.inCombat = True, False, False
        assert A.OfferUnlock() is None and db.arrowUnlockOffered is True
        st.arrowLocked = True
        assert A.OfferUnlock() is None and A.unlockAsk is None and st.arrowLocked is True
        # locked from before: put off in a fight and with the arrow off (still locked), then unlocked and told
        db.arrowUnlockOffered = None
        ns.inCombat = True
        assert A.OfferUnlock() is None and db.arrowUnlockOffered is None and st.arrowLocked is True
        ns.inCombat, st.arrow = False, False
        assert A.OfferUnlock() is None and db.arrowUnlockOffered is None and st.arrowLocked is True
        st.arrow = True
        ask = A.OfferUnlock()
        assert ask is not None and ask._shown is True and db.arrowUnlockOffered is True
        assert st.arrowLocked is False  # (unlocked before any answer)
        text = lua.eval("AGPS_NS.Arrow.unlockAsk.text:GetText()")
        assert text.startswith("Directions and the arrow are now unlocked by default. You can move them now if you wish.")
        assert "right-click" in text and "Options > Directions > Lock arrow position" in text
        assert lua.eval("AGPS_NS.Arrow.unlockAsk.yes:GetText()") == "Leave Unlocked"
        assert lua.eval("AGPS_NS.Arrow.unlockAsk.no:GetText()") == "Lock"
        # Leave Unlocked: as it is, and not told again
        click(ask.yes)
        assert not ask._shown and st.arrowLocked is False
        st.arrowLocked = True
        assert A.OfferUnlock() is None and not ask._shown and st.arrowLocked is True
        # Escape or the close button: left unlocked too
        db.arrowUnlockOffered = None
        ask = A.OfferUnlock()
        ask.Hide(ask)
        assert st.arrowLocked is False
        # Lock: locked again
        st.arrowLocked, db.arrowUnlockOffered = True, None
        click(A.OfferUnlock().no)
        assert st.arrowLocked is True and db.arrowUnlockOffered is True
        # at login, a few seconds in
        src = (ADDON / "Core.lua").read_text(encoding="utf-8")
        assert "ns.Arrow.UNLOCK_OFFER_WAIT, function() pcall(ns.Arrow.OfferUnlock) end" in src
    finally:
        st.arrowLocked, st.arrow, db.arrowUnlockOffered, ns.inCombat = was
        if A.unlockAsk:
            A.unlockAsk.answered = True
            A.unlockAsk.Hide(A.unlockAsk)
        A.Apply()


def test_a_question_popup_has_the_title_bar_and_the_logo_like_every_window(game):
    # (asked 2026-11-11: "needs azeroth standardizing for all windows, logo, color, etc just like tutorial pages")
    lua, ns = game
    f = ns.Ask("AzerothGPSTestAskLook", "A question?")
    try:
        assert f.top in (-28, -30)  # (a title bar's room; the logo comes with it: ns.Window's own test)
        src = (ADDON / "Core.lua").read_text(encoding="utf-8")
        assert src.count("noTitle = true") == 0  # (no window of the addon's own without them)
    finally:
        f.answered = True
        f.Hide(f)


QUEST_STOPS = """{
  { x = -600, y = -4180, cont = 1, name = "Q1", questRoute = true, quest = 101 },
  { x = -800, y = -4400, cont = 1, name = "Turn in: Q2", questRoute = true, quest = 102, turnin = true },
  { x = -900, y = -4100, cont = 1, name = "Q3", questRoute = true, quest = 103 },
}"""


def test_the_quest_reroute_icons_first_click_asks_once_whether_to_reroute_by_itself(game):
    # (asked 2026-11-12: "For the reroute button on new quest or turn in, first click ask if the player would like for
    # rerouting to happen automatically. This will only be ever asked once. Tell them where the option is")
    lua, ns = game
    G, st, db = ns.GPS, ns.settings.gps, ns.db
    was = (G.QuestRoute, ns.Print, db.questAutoAsked, st.questAutoReroute)
    lua.execute("AGPS_QR, AGPS_SAID = 0, {}")
    G.QuestRoute = lua.eval("function() AGPS_QR = AGPS_QR + 1 end")
    ns.Print = lua.eval("function(m) AGPS_SAID[#AGPS_SAID + 1] = m end")
    try:
        db.questAutoAsked, st.questAutoReroute = None, False
        G.QuestRerouteClick()
        box = lua.globals().AzerothGPSQuestAuto
        assert box and box._shown and db.questAutoAsked and lua.eval("AGPS_QR") == 0
        box.yes._scripts.OnClick(box.yes)
        said = lua.eval("AGPS_SAID[1]")
        assert st.questAutoReroute is True and lua.eval("AGPS_QR") == 1 and "Options > Routing" in said
        # never asked again: the next click remakes the route at once
        box._shown = False
        G.QuestRerouteClick()
        assert not box._shown and lua.eval("AGPS_QR") == 2
        # answered No (or left unanswered): off, and still told where the option is
        db.questAutoAsked, st.questAutoReroute = None, True
        G.QuestRerouteClick()
        box.no._scripts.OnClick(box.no)
        assert st.questAutoReroute is False and lua.eval("AGPS_QR") == 3 and "Options > Routing" in lua.eval("AGPS_SAID[2]")
        G.QuestRerouteClick()
        assert lua.eval("AGPS_QR") == 4
    finally:
        G.QuestRoute, ns.Print, db.questAutoAsked, st.questAutoReroute = was


def test_with_the_option_on_a_quest_change_remakes_the_quest_route_out_of_combat(game):
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    was = (G.QuestRoute, st.questAutoReroute, lua.globals().InCombatLockdown)
    lua.execute("AGPS_QR = 0")
    G.QuestRoute = lua.eval("function() AGPS_QR = AGPS_QR + 1 end")
    try:
        N.SetStops(lua.eval(QUEST_STOPS))
        # off: the icon pulses, nothing more
        st.questAutoReroute = False
        N.MarkQuestRouteStale()
        assert N.questRouteStale and not G.autoQuestPending and lua.eval("AGPS_QR") == 0
        # on: after a moment (the timer), the route is made again; in combat it waits
        st.questAutoReroute = True
        N.MarkQuestRouteStale()
        assert G.autoQuestPending
        lua.execute("InCombatLockdown = function() return true end")
        G.AutoQuestTick()
        assert lua.eval("AGPS_QR") == 0 and G.autoQuestPending  # (tried again later)
        lua.execute("InCombatLockdown = function() return false end")
        G.AutoQuestTick()
        assert lua.eval("AGPS_QR") == 1 and not G.autoQuestPending
    finally:
        G.QuestRoute, st.questAutoReroute = was[0], was[1]
        lua.globals().InCombatLockdown = was[2]
        G.autoQuestPending, N.questRouteStale = None, None
        N.Clear()


def test_quest_stops_removed_stay_out_of_quest_routes_until_put_back(game):
    # (asked 2026-11-12: "Remember the quest stops they've dropped from the route and/or not included (like elite
    # quests) for this current route run"; since 1.3.13, players' request relayed by Kooki3z 2026-11-21: a quest left
    # out "comes up again every time the route regenerates") made again, by hand or by itself, the stops removed stay
    # out of every later quest route, a new route and the route cleared too, until put back
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    c = lua.eval("{ elsewhere = 0, missing = {} }")
    try:
        N.SetStops(lua.eval(QUEST_STOPS))
        i = next(k for k in range(1, len(N.stops) + 1) if N.stops[k].quest == 103)
        N.RemoveStop(i)
        assert len(N.questDropped) == 1
        G.SetQuestRoute(lua.eval(QUEST_STOPS), c)
        quests = sorted(N.stops[k].quest for k in range(1, len(N.stops) + 1))
        assert quests == [101, 102]
        # the same quest's other part (its turn-in, once done) isn't the stop removed
        assert not N.QuestDropped(lua.eval("{ x = -900, y = -4100, cont = 1, quest = 103, turnin = true }"))
        # kept over a /reload with the stops
        N.Restore()
        assert len(N.questDropped) == 1
        # another route, or the route cleared: still out of the next quest route
        N.SetStops(lua.eval('{ { x = -1000, y = -4000, cont = 1, name = "Mine" } }'))
        N.Clear()
        assert len(N.questDropped) == 1
        G.SetQuestRoute(lua.eval(QUEST_STOPS), c)
        assert sorted(N.stops[k].quest for k in range(1, len(N.stops) + 1)) == [101, 102]
        # its spot moved on (the next objective, far away): still the stop removed
        assert N.QuestDropped(lua.eval("{ x = 3000, y = 3000, cont = 0, quest = 103 }"))
        # put back: in the next one
        N.PutBackQuest(103)
        G.SetQuestRoute(lua.eval(QUEST_STOPS), c)
        assert sorted(N.stops[k].quest for k in range(1, len(N.stops) + 1)) == [101, 102, 103]
    finally:
        N.questDropped = lua.eval("{}")
        N.Clear()


def test_quiet_chat_keeps_azerothgps_out_of_the_chat_but_a_commands_answers(game):
    # (asked 2026-11-12: "an option in General to suppress all AzerothGPS chat information (unless they run
    # /azerothgps commands of course) in the chat window. Off by default.")
    lua, ns = game
    st = ns.settings.gps
    assert ns.DEFAULTS.gps.quietChat is False
    chat = lua.globals().DEFAULT_CHAT_FRAME
    was = (chat.AddMessage, st.quietChat)
    lua.execute("AGPS_CHAT = {}")
    chat.AddMessage = lua.eval("function(_, m) AGPS_CHAT[#AGPS_CHAT + 1] = m end")
    said = lambda: len(lua.eval("AGPS_CHAT"))  # noqa: E731
    try:
        st.quietChat = False
        ns.Print("Quest Route: 3 stops")
        assert said() == 1
        st.quietChat = True
        ns.Print("Quest Route: 3 stops")
        assert said() == 1  # (nothing more)
        lua.globals().SlashCmdList.AZEROTHGPS("status")
        assert said() > 1 and not ns.inSlash  # (a command's answers still show)
        n = said()
        ns.Print("after the command")
        assert said() == n
        # a command failing doesn't leave the chat open for good
        bad = lua.eval("function() error('boom') end")
        lua.execute("AGPS_OLD_DESCRIBE = nil")
        old = ns.GPS.Describe
        ns.GPS.Describe = bad
        try:
            lua.globals().SlashCmdList.AZEROTHGPS("status")
        except Exception:
            pass
        ns.GPS.Describe = old
        assert not ns.inSlash
    finally:
        chat.AddMessage, st.quietChat = was


def test_the_use_button_lets_go_of_the_map_as_a_fight_starts(game):
    # (seen in game 2026-11-12: the protected use button, anchored to the directions panel, made the whole map window
    # protected in combat: it couldn't grow out of the minimap square or shrink back mid-fight)
    lua, ns = game
    G = ns.GPS
    b = G.useBtn
    assert b is not None
    lua.execute("AzerothGPSUseButton:SetPoint('BOTTOMRIGHT', AzerothGPSUseButton.panel, 'BOTTOMRIGHT', -5, 5)")
    b.key = "x"
    lua.eval("AGPS_FIRE")("PLAYER_REGEN_DISABLED")
    assert not b._shown and b.key is None
    assert not lua.eval("next(AzerothGPSUseButton._pts)")  # (anchored to nothing of ours in the fight)
    lua.eval("AGPS_FIRE")("PLAYER_REGEN_ENABLED")


def test_in_a_fight_the_squares_logo_grows_the_map_with_the_world_map_option(minimap):
    # (seen in game 2026-11-12: the world map can't be opened by an addon in a fight; the map grows out of the square)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    st.replaceMinimap = True
    G.ApplySettings()
    saved = st.useWorldMap
    st.useWorldMap = True
    lua.execute("WorldMapFrame:Hide() AGPS_TOGGLES = 0 AGPS_OLD_TOGGLE = ToggleWorldMap")
    lua.execute("ToggleWorldMap = function() AGPS_TOGGLES = AGPS_TOGGLES + 1 end")
    try:
        lua.execute("InCombatLockdown = function() return true end")
        assert G.ToggleMapView() is True
        _tick(lua, ns)
        assert G.mmState.expanded and lua.eval("AGPS_TOGGLES") == 0 and lua.eval("AzerothGPSFrame._shown")
        assert G.ToggleMapView() is True
        _tick(lua, ns)
        assert not G.mmState.expanded
    finally:
        lua.execute("InCombatLockdown = function() return false end ToggleWorldMap = AGPS_OLD_TOGGLE")
        st.useWorldMap = saved
        G.ApplySettings()



def test_a_rides_dotted_line_keeps_its_light_blue_with_several_stops(game):
    # (asked 2026-11-14, screenshot: a route with a flight showed the flight's dotted line light blue, and once another
    # stop was added the flight's line took the darker shade of its stop's color) a ride (flight, zeppelin, boat, lift)
    # keeps its light blue however many stops; the walks take their stop's color as before
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    ride = "%.2f,%.2f,%.2f" % (0.25, 0.85, 1)
    ns.settings.gps.zoom = 4000
    N.Clear()
    try:
        for stops in ("{ { x = 1600, y = -4400, cont = 1 } }",
                      "{ { x = 1600, y = -4400, cont = 1 }, { x = 300, y = -4700, cont = 1 } }"):
            N.Clear()
            N.SetStops(lua.eval(stops), False, "red")
            for t in range(4):
                lua.execute("AGPS_T = AGPS_T + 1")
                G.Update()
            kinds = {N.route.parts[p].kinds[i] for p in range(1, len(N.route.parts) + 1)
                     for i in range(1, len(N.route.parts[p].kinds) + 1)} if N.route and N.route.parts else set()
            assert 2 in kinds, (stops, kinds)
            assert ride in _colors(_lines(lua)), (stops, _colors(_lines(lua)))
    finally:
        N.Clear()
        ns.settings.gps.zoom = 600


def test_quick_search_key_opens_the_map_with_its_search_box_ready():
    """Asked 2026-11-14: "a key binding to open the map and select the search function so player can immediately start
    typing", "call it quick search" (Bindings.xml's AZEROTHGPS_SEARCH, Options > General's "Quick search key")."""
    from azerothgps.gameharness import start
    lua, ns = start()
    G = ns.GPS
    assert "AZEROTHGPS_SEARCH" in (ADDON / "Bindings.xml").read_text(encoding="utf-8")
    assert lua.globals().BINDING_NAME_AZEROTHGPS_SEARCH
    ns.settings.gps.shown = False
    ns.Options.Apply()
    lua.execute("""C_Timer.After = function(_, f) f() end
      local box = AGPS_NS.GPS.searchPanel.box
      AGPS_FOCUSED = false
      local set = box.SetFocus
      box.SetFocus = function(self, ...) AGPS_FOCUSED = true if set then return set(self, ...) end end""")
    lua.globals().AzerothGPS_QuickSearch()
    assert ns.settings.gps.shown
    assert G.searchPanel.IsShown(G.searchPanel) and lua.eval("AGPS_FOCUSED")
    box = G.searchPanel.box
    assert box.GetText(box) == ""
    # (again with it open: still ready, emptied)
    lua.execute("AGPS_FOCUSED = false")
    box.SetText(box, "orgr")
    lua.globals().AzerothGPS_QuickSearch()
    assert G.searchPanel.IsShown(G.searchPanel) and lua.eval("AGPS_FOCUSED") and box.GetText(box) == ""
    # (in the map menu, its default place: the menu opened, and kept open while the search shows)
    assert G.QuickPlace("search").startswith("menu") and G.mapMenu.IsShown(G.mapMenu)
    # (its button hidden: said so, nothing opened)
    G.searchPanel.Hide(G.searchPanel)
    G.mapMenu.Hide(G.mapMenu)
    ns.settings.gps.quick = lua.eval("{ search = 'hidden' }")
    lua.execute("AGPS_SAID = nil local p = AGPS_NS.Print AGPS_NS.Print = function(m) AGPS_SAID = m end")
    assert lua.globals().AzerothGPS_QuickSearch() is False
    assert "turned off" in str(lua.eval("AGPS_SAID")) and not G.searchPanel.IsShown(G.searchPanel)


def test_double_click_a_quest_routes_to_it_or_adds_it(game):
    # (asked 2026-11-14: "support double click to route to a quest on the quest itself? either in game quest log or
    # questie ... (this should add a stop if route in progress)")
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    lua.execute("""
      AGPS_DC = { stops = AGPS_NS.Layers.QuestStops, hook = hooksecurefunc }
      AGPS_NS.Layers.QuestStops = function()
        return {
          { x = 2250, y = 250, cont = 0, name = "Wolves", questRoute = true, quest = 1 },
          { x = 2300, y = 300, cont = 0, name = "Spiders", questRoute = true, quest = 2 },
          { x = 2200, y = 280, cont = 0, name = "Turn in: Spiders", questRoute = true, quest = 2, turnin = true },
          { x = 2150, y = 260, cont = 0, name = "Turn in: Bears", questRoute = true, quest = 3, turnin = true },
        }, { todo = 2, turnin = 2, missing = {}, elsewhere = 0 }
      end
      hooksecurefunc = function(t, k, post)
        if type(t) == "string" then
          local f, after = _G[t], k
          _G[t] = function(...) f(...) after(...) end
          return
        end
        local f = t[k]
        t[k] = function(...) f(...) post(...) end
      end
      QuestObjectiveTracker = { OnBlockHeaderClick = function() end }
      QuestMapLogTitleButton_OnClick = function() end
      linePool1 = NewWidget("Button", "linePool1")
      linePool1.Quest = { Id = 1 }
      linePool1:SetScript("OnClick", function() end)
    """)
    names = lambda: sorted(str(N.stops[i].name) for i in range(1, len(N.stops) + 1))
    def tick(dt):
        lua.execute(f"AGPS_T = AGPS_T + {dt}")
    try:
        G.questLogDouble, G.trackerDouble = None, None
        G.groupChoice = lua.eval("{}")
        N.Clear()
        G.HookQuestDoubleClicks()
        # one click: nothing; two on the tracker's header, close together: the route to it
        lua.execute("QuestObjectiveTracker:OnBlockHeaderClick({ id = 2 }, 'LeftButton')")
        assert names() == []
        tick(0.2)
        lua.execute("QuestObjectiveTracker:OnBlockHeaderClick({ id = 2 }, 'LeftButton')")
        assert names() == ["Spiders", "Turn in: Spiders"]
        # a route on: the quest log's double-click adds the quest's stops
        tick(1)
        lua.execute("QuestMapLogTitleButton_OnClick({ questID = 3 }, 'LeftButton')")
        tick(0.2)
        lua.execute("QuestMapLogTitleButton_OnClick({ questID = 3 }, 'LeftButton')")
        assert names() == ["Spiders", "Turn in: Bears", "Turn in: Spiders"]
        # and Questie's tracker line; again: in it already, nothing doubled
        for _ in range(2):
            tick(1)
            lua.execute("linePool1:GetScript('OnClick')(linePool1, 'LeftButton')")
            tick(0.2)
            lua.execute("linePool1:GetScript('OnClick')(linePool1, 'LeftButton')")
        assert names() == ["Spiders", "Turn in: Bears", "Turn in: Spiders", "Wolves"]
        # too slow, or another quest between, or a right click: no double-click
        N.Clear()
        lua.execute("QuestObjectiveTracker:OnBlockHeaderClick({ id = 2 }, 'LeftButton')")
        tick(1)
        lua.execute("QuestObjectiveTracker:OnBlockHeaderClick({ id = 2 }, 'LeftButton')")
        tick(0.1)
        lua.execute("QuestObjectiveTracker:OnBlockHeaderClick({ id = 3 }, 'LeftButton')")
        tick(0.1)
        lua.execute("QuestObjectiveTracker:OnBlockHeaderClick({ id = 3 }, 'RightButton')")
        assert names() == []
    finally:
        lua.execute("""AGPS_NS.Layers.QuestStops, hooksecurefunc = AGPS_DC.stops, AGPS_DC.hook
          QuestObjectiveTracker, QuestMapLogTitleButton_OnClick, linePool1 = nil, nil, nil""")
        G.questLogDouble, G.trackerDouble = None, None
        N.Clear()
        G.groupChoice = lua.eval("{}")


def test_closing_the_map_with_stops_placed_starts_the_route(game):
    # (asked 2026-11-14: "how come I'm having to confirm route? If I set a destination and close the map routing should
    # just start") the map's window hidden did; the map as the minimap sent back to its square, and the game's world
    # map with the map in it closed, now do too
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    try:
        N.Clear()
        G.PendingStops(lua.eval("{ { x = 2250, y = 250, cont = 0, name = 'Brill' } }"))
        assert G.ConfirmPendingOnClose() and len(N.stops) == 1 and len(G.PendingStops()) == 0
        # the square: sent back, the stops placed meanwhile start the route
        N.Clear()
        G.PendingStops(lua.eval("{ { x = 2300, y = 300, cont = 0, name = 'Tirisfal' } }"))
        lua.execute("""AGPS_MM = AGPS_NS.GPS.mmState
          AGPS_NS.GPS.mmState = { on = true, expanded = true }""")
        try:
            lua.execute("pcall(AGPS_NS.GPS.SetMinimapExpanded, false)")
        finally:
            lua.execute("AGPS_NS.GPS.mmState = AGPS_MM")
        assert len(N.stops) == 1 and len(G.PendingStops()) == 0
    finally:
        N.Clear()
        G.PendingStops(lua.eval("{}"))
        G.Follow()


def test_the_other_factions_city_locations_are_hidden(game):
    # (asked 2026-11-14 with a screenshot of Teldrassil on a Horde character: "If player has opposing faction character
    # just hide the city guard locations that get marked") the places learned in Darnassus by an Alliance character
    # (account-wide) aren't shown to a Horde one; to an Alliance one they are
    lua, ns = game
    L, N = ns.Layers, ns.Nav
    lua.execute("""AGPS_FAC = AGPS_NS.Nav.Faction
      AGPS_REV = AGPS_NS.db.cityRevealed
      AGPS_NS.db.cityRevealed = { [1457] = true }""")
    try:
        lua.execute("AGPS_NS.Nav.Faction = function() return 'H' end")
        assert L.HiddenCity(1457) and not L.HiddenCity(1454)
        assert len(L.RevealedPlaces(1)) == 0
        lua.execute("AGPS_NS.Nav.Faction = function() return 'A' end")
        assert not L.HiddenCity(1457) and len(L.RevealedPlaces(1)) > 0
    finally:
        lua.execute("AGPS_NS.Nav.Faction = AGPS_FAC AGPS_NS.db.cityRevealed = AGPS_REV")


def test_the_minimaps_quest_circles_stay_hidden_when_the_game_shows_them_again(minimap):
    # (2026-11-15: "for quest areas this circle is still here from original wow minimap": hidden once when the square was
    # placed, the hatched circle was back over a quest's area; hidden again at each look while it's the square)
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    st.replaceMinimap = True
    G.ApplySettings()
    assert G.MinimapMode()
    was = (st.layerQuests, st.layerQuestAreasMinimap)
    try:
        st.layerQuests, st.layerQuestAreasMinimap = True, True
        lua.execute("for k in pairs(AGPS_MM.blobs) do AGPS_MM.blobs[k] = 1 end")  # (the game showing them again)
        G.MinimapAwayCheck(G.MINIMAP_AWAY_CHECK + 0.01)
        blobs = dict(lua.eval("AGPS_MM.blobs").items())
        assert len(blobs) == 9 and set(blobs.values()) == {0}
        # our Quest areas on the minimap off: the game's own instead (asked 2026-11-15)
        st.layerQuestAreasMinimap = False
        G.MinimapAwayCheck(G.MINIMAP_AWAY_CHECK + 0.01)
        assert set(dict(lua.eval("AGPS_MM.blobs").items()).values()) == {G.MINIMAP_BLOB_DEFAULT}
        st.layerQuestAreasMinimap = True
        G.MinimapAwayCheck(G.MINIMAP_AWAY_CHECK + 0.01)
        assert set(dict(lua.eval("AGPS_MM.blobs").items()).values()) == {0}
    finally:
        st.layerQuests, st.layerQuestAreasMinimap = was


def test_quest_areas_on_the_map_and_on_the_minimap_apart(minimap):
    # (asked 2026-11-15: "expand the option to 2 choices, one for the map and one for the minimap")
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    was = (st.layerQuests, st.layerQuestAreas, st.layerQuestAreasMinimap)
    try:
        st.layerQuests, st.layerQuestAreas, st.layerQuestAreasMinimap = True, False, True
        assert not G.QuestAreasOn()  # (the map: off)
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode() and G.QuestAreasOn()  # (the square: on)
        G.MinimapAwayCheck(G.MINIMAP_AWAY_CHECK + 0.01)
        assert set(dict(lua.eval("AGPS_MM.blobs").items()).values()) == {0}  # (ours there: the game's hidden)
        st.layerQuestAreas, st.layerQuestAreasMinimap = True, False
        assert not G.QuestAreasOn()
        G.MinimapAwayCheck(G.MINIMAP_AWAY_CHECK + 0.01)
        assert set(dict(lua.eval("AGPS_MM.blobs").items()).values()) == {G.MINIMAP_BLOB_DEFAULT}  # (the game's own)
    finally:
        st.layerQuests, st.layerQuestAreas, st.layerQuestAreasMinimap = was


def test_the_zoom_is_kept_when_the_maps_size_changes_by_itself(game):
    # (2026-11-15: "opening the map after reload ignores zoom level for seamless and shows incorrectly until i scroll",
    # "after I told you to make map style hidden by default it started having this issue": the saved zoom was the whole
    # continent's, 16,442 yd. The zoom followed every change of the window's size on the screen, so a bigger window
    # shows more of the map; the quick buttons' minimum size (G.QuickMinSides) changing by itself, a button hidden or
    # laid out at a /reload, multiplied it each time. Only the player's own resize keeps the scale now.)
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    was = (st.size, st.zoom)
    try:
        st.size = 200  # (under the quick buttons' minimum: the window is that minimum)
        G.ApplySettings()
        st.zoom = 500.0
        G.ApplySettings()
        if st.quick is None:
            st.quick = lua.eval("{}")
        keys = ("styles", "search", "questRoute", "dungeonsG", "gather", "questsG", "quickFind", "hearth")
        old = {k: st.quick[k] for k in keys}
        for k in keys:  # (the menu's buttons hidden one by one: its column shorter, the window's minimum with it)
            st.quick[k] = "hidden"
            G.ApplySettings()
            assert abs(st.zoom - 500.0) < 1e-6, f"{k} hidden: the zoom followed a size the player never set: {st.zoom}"
        for k in keys:
            st.quick[k] = old[k]
            G.ApplySettings()
        assert abs(st.zoom - 500.0) < 1e-6, f"the zoom followed a size the player never set: {st.zoom}"
        # the player's own resize: the same scale, more of the map
        st.size = 520
        G.ApplySettings()
        st.zoom = 500.0
        G.ApplySettings()
        st.size = 1040
        G.ApplySettings()
        assert abs(st.zoom - 500.0 * max(G.MapSize()) / 520) < 1.0, st.zoom
    finally:
        st.size, st.zoom = was[0], was[1]
        G.ApplySettings()


def test_a_cast_on_a_secret_target_in_combat_is_no_error(game):
    # (a player's report 2026-11-16, a mage in Blackfathom Deeps: "Layers.lua:135: attempted to index a table that
    # cannot be indexed with secret keys" on every spell cast in combat; the cast's target name is secret there)
    lua, ns = game
    L = ns.Layers
    db = ns.db
    saved_nodes = db.nodes
    lua.execute("""
      AGPS_SECRET_T = setmetatable({}, { __tostring = function() return "<secret>" end })
      AGPS_WAS_SECRET = AGPS_NS.IsSecret
      AGPS_NS.IsSecret = function(v) return v ~= nil and v == AGPS_SECRET_T end
      -- the game's own rule: a table indexed with a secret key is an error
      local i = 1
      while true do
        local n, v = debug.getupvalue(AGPS_NS.Layers.NodeKind, i)
        if not n then break end
        if n == "nodeKind" then
          setmetatable(v, { __index = function(_, k)
            if k == AGPS_SECRET_T then error("attempted to index a table that cannot be indexed with secret keys") end
          end })
        end
        i = i + 1
      end
    """)
    try:
        db.nodes = lua.eval("{}")
        ev = L.frame._scripts.OnEvent
        secret = lua.eval("AGPS_SECRET_T")
        assert L.NodeKind(secret) is None
        assert L.GatherKind(2366, secret) is None
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", secret, "cast-s1", 133)
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", secret, secret, secret)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", secret, secret)
        assert db.nodes[0] is None
        # out of combat again: herbs still saved
        ev(L.frame, "UNIT_SPELLCAST_SENT", "player", "Peacebloom", "cast-s2", 2366)
        ev(L.frame, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-s2", 2366)
        assert [str(n[3]) for n in db.nodes[0].values()] == ["Peacebloom"]
    finally:
        db.nodes = saved_nodes
        lua.execute("""
          local i = 1
          while true do
            local n, v = debug.getupvalue(AGPS_NS.Layers.NodeKind, i)
            if not n then break end
            if n == "nodeKind" then setmetatable(v, nil) end
            i = i + 1
          end
          AGPS_NS.IsSecret, AGPS_WAS_SECRET, AGPS_SECRET_T = AGPS_WAS_SECRET, nil, nil
        """)


def test_the_no_spoiler_maps_explored_parts_hold_steady(game):
    # (reported 2026-11-17: "When the spoiler-free map is enabled, display errors occur. It flickers, pops out": the
    # game's list asked again in another order, or empty for a moment, mustn't reshuffle or drop the explored parts)
    lua, ns = game
    G = ns.GPS
    lua.execute("""
      AGPS_EXP_ORDER, AGPS_EXP_EMPTY = 1, false
      C_MapExplorationInfo = C_MapExplorationInfo or {}
      AGPS_EXP_SV = C_MapExplorationInfo.GetExploredMapTextures
      C_MapExplorationInfo.GetExploredMapTextures = function(id)
        if AGPS_EXP_EMPTY then return {} end
        local a = { textureWidth = 300, textureHeight = 200, offsetX = 10, offsetY = 20, fileDataIDs = { 101, 102 } }
        local b = { textureWidth = 128, textureHeight = 128, offsetX = 500, offsetY = 5, fileDataIDs = { 201 } }
        local hover = { textureWidth = 64, textureHeight = 64, offsetX = 0, offsetY = 0, fileDataIDs = { 301 },
          isShownByMouseOver = true }
        if AGPS_EXP_ORDER == 1 then return { a, b, hover } end
        return { hover, b, a }
      end
    """)
    try:
        t = float(lua.eval("AGPS_T"))
        lua.globals().AGPS_T = t + 1000
        first = G.ExploredOverlays(987654)
        fids = [first[i][1] for i in range(1, len(first) + 1)]
        assert sorted(fids) == [101, 102, 201]  # (the mouse-over one left out)
        lua.globals().AGPS_EXP_ORDER = 2
        lua.globals().AGPS_T = t + 1000 + G.EXPLORED_TTL + 1
        again = G.ExploredOverlays(987654)
        assert lua.eval("function(a, b) return a == b end")(first, again)  # (the same list, untouched)
        lua.globals().AGPS_EXP_EMPTY = True
        lua.globals().AGPS_T = t + 1000 + 2 * (G.EXPLORED_TTL + 1)
        assert lua.eval("function(a, b) return a == b end")(first, G.ExploredOverlays(987654))
    finally:
        lua.globals().AGPS_T = t
        lua.execute("C_MapExplorationInfo.GetExploredMapTextures = AGPS_EXP_SV")

def test_a_walk_recorded_with_no_floor_picked_takes_the_floors_of_the_roads_it_joins(game):
    # (2026-11-17, Stormwind's bank: a walk recorded to the counter with no floor picked (Shift + wheel) was on no
    # floor, and the stop, with the counter's height, took the city road at that height and a 45 yd line through the
    # bank's walls. "can the difference be assumed to gradually increase over that drawn distance rather than flat":
    # a road with no heights takes its ends' roads' floors, rising evenly between, R.RampHeights)
    lua, ns = game
    R = ns.Router
    walk = lua.table_from([-8876.6, 644.9, -8879.0, 643.7, -8881.0, 642.8, -8882.9, 641.8, -8884.8, 640.9, -8886.9, 639.9, -8888.8, 638.7, -8890.0, 636.9, -8892.0, 636.0, -8894.2, 635.0, -8894.9, 634.6, -8897.0, 633.6, -8899.0, 632.6, -8901.1, 631.6, -8903.0, 630.7, -8905.0, 629.7, -8907.8, 628.5, -8909.7, 627.7, -8913.6, 627.2, -8915.9, 627.5, -8917.4, 628.9, -8919.6, 629.1, -8921.7, 629.1, -8923.9, 629.0, -8926.1, 628.6, -8928.1, 627.9, -8930.0, 626.9, -8931.4, 625.5, -8931.8, 623.5, -8933.4, 622.0, -8935.0, 620.8])
    was = ns.db.tracks
    lua.globals().AGPS_WALK = walk
    # (the walk on to the counter has shipped since, as FloorTracks' time 1794929103, with heights of its own: left
    # out here, this is about a walk with none)
    lua.execute("""AGPS_FT_WAS = AGPS_NS.FloorTracks[0]
      local keep = {}
      for _, t in ipairs(AGPS_FT_WAS) do if t.time ~= 1794929103 then keep[#keep + 1] = t end end
      AGPS_NS.FloorTracks[0] = keep""")
    lua.execute("""AGPS_NS.db.tracks = { { op = 'add', drawn = true, recorded = true, continent = 0,
      zone = 'Stormwind City', time = 1795000123, pts = AGPS_WALK } }""")
    lua.execute("AGPS_UFG = UnitFactionGroup UnitFactionGroup = function() return 'Alliance', 'Alliance' end")
    try:
        R.Reset()
        bank = (-8935.24374, 612.6575)
        r = R.Route(0, -8860.0, 700.0, bank[0], bank[1], lua.table_from({"tz": 99.6}))
        n = len(r.pts) // 2
        pts = [(r.pts[2 * i - 1], r.pts[2 * i]) for i in range(1, n + 1)]
        assert math.dist(pts[-2], pts[-1]) < 15  # (the walk's end by the counter, not 45 yd across the walls)
        assert min(math.dist(p, (-8948.0, 570.0)) for p in pts) > 20  # (not by the city road south of the bank)
    finally:
        lua.execute("AGPS_NS.FloorTracks[0] = AGPS_FT_WAS")
        ns.db.tracks = was
        lua.execute("UnitFactionGroup = AGPS_UFG")
        R.Reset()


def test_ramp_heights_rise_evenly_between_the_ends_floors(game):
    lua, ns = game
    R = ns.Router
    pts = lua.table_from([0, 0, 10, 0, 30, 0])
    h = R.RampHeights(pts, 100, 105)
    assert [round(h[i], 2) for i in (1, 2, 3)] == [100, 101.67, 105]
    one = R.RampHeights(pts, None, 104)
    assert [one[i] for i in (1, 2, 3)] == [104, 104, 104]  # (one end's floor alone: flat at it)
    assert R.RampHeights(pts, None, None) is None  # (none: as before, the land's)


def test_the_mage_trainer_route_goes_up_the_wizards_sanctum_and_through_its_portal(game):
    # (asked 2026-11-17: "Path here says below but the trainer is actually at the top of the tower through a portal",
    # issue #565) from the Mage Quarter's street: to the portal at the top of the tower, through it, straight to the
    # trainer in the room under the city; no "Below you, 76 yd down", and not arrived on the street over them
    lua, ns = game
    N = ns.Nav
    lua.execute("AGPS_UFG = UnitFactionGroup UnitFactionGroup = function() return 'Alliance', 'Alliance' end")
    was_pos = lua.eval("{ AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] }")
    try:
        N.roomIn = None
        was_faction = ns.CharDB().faction
        ns.CharDB().faction = 'Alliance'
        lua.execute("AGPS_POS = { -8990.0, 830.0, 0 }")
        N.SetStops(lua.eval("{ { x = -8990.0, y = 862.9, cont = 0, z = 29.6, name = 'Stormwind Mage Trainer' } }"), False,
                   "red")
        for t in range(6):
            lua.execute(f"AGPS_T = {900000 + t * 2}")
            _redraw(lua, ns)
            N.Status(-8990.0, 830.0, 0)
        steps = str(N.StepsText(9))
        assert "Take the teleporter to Wizard's Sanctum" in steps, steps
        assert N.HeightText(-8990.0, 830.0, 0) is None
        last = N.route.parts[len(N.route.parts)]
        n = len(last.pts) // 2
        yd = sum(math.dist((last.pts[2 * k - 1], last.pts[2 * k]), (last.pts[2 * k + 1], last.pts[2 * k + 2]))
                 for k in range(1, n))
        assert yd < 60  # (in the room: straight to the trainer, not round the streets over it)
        # standing on the street over the trainer: not there
        lua.execute("AGPS_POS = { -8990.5, 862.5, 0 }")
        assert "Arrived" not in str(N.Status(-8990.5, 862.5, 0) or "")
    finally:
        N.Clear()
        N.roomIn = None
        if "was_faction" in locals():
            ns.CharDB().faction = was_faction
        lua.globals().AGPS_POS = was_pos
        lua.execute("UnitFactionGroup = AGPS_UFG")


def test_the_mage_trainer_route_climbs_the_walk_recorded_up_the_wizards_sanctum(game):
    # (asked 2026-11-17: "The mage tower path doesn't follow my route I saved, spiraling around the tower on the way up
    # to the portal": a street's end cut at the stairs' foot was joined onto the turn 22 yd over it, the room under the
    # city was linked to the stairs by the map's distance, and the walk's floors dropped into the room halfway up)
    lua, ns = game
    N = ns.Nav
    lua.execute("AGPS_UFG = UnitFactionGroup UnitFactionGroup = function() return 'Alliance', 'Alliance' end")
    was_pos = lua.eval("{ AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] }")
    try:
        N.roomIn = None
        was_faction = ns.CharDB().faction
        ns.CharDB().faction = 'Alliance'
        lua.execute("AGPS_POS = { -8990.0, 830.0, 0 }")
        N.SetStops(lua.eval("{ { x = -8990.0, y = 862.9, cont = 0, z = 29.6, name = 'Stormwind Mage Trainer' } }"), False,
                   "red")
        for t in range(6):
            lua.execute(f"AGPS_T = {900000 + t * 2}")
            _redraw(lua, ns)
            N.Status(-8990.0, 830.0, 0)
        first = N.route.parts[1]
        pts = [(first.pts[k], first.pts[k + 1]) for k in range(1, len(first.pts), 2)]
        fz = [first.fz[k] for k in range(1, len(first.fz) + 1)]
        # (in at the stairs' foot by the door, round both turns of the walk, to the portal at the top)
        assert min(math.dist(p, (-9010.2, 853.7)) for p in pts) < 1.5
        for spot in [(-8999.8, 889.0), (-8980.7, 874.5), (-9007.0, 877.9), (-9017.0, 876.6)]:
            assert min(math.dist(p, spot) for p in pts) < 1.5, spot
        # (climbing all the way: never a floor's jump between two points, never down into the room)
        assert max(abs(b - a) for a, b in zip(fz, fz[1:])) < 5
        assert min(fz) > 100 and fz[-1] > 140
    finally:
        N.Clear()
        N.roomIn = None
        if "was_faction" in locals():
            ns.CharDB().faction = was_faction
        lua.globals().AGPS_POS = was_pos
        lua.execute("UnitFactionGroup = AGPS_UFG")


def test_at_the_wizards_sanctum_portal_it_says_the_portal_and_through_it_youve_arrived(game):
    # (2026-11-17, in game: in front of the portal "Take the stairs up", the walk to it 2 yd off the stairs' last turn;
    # then through it, still "Take the teleporter": put 1.4 yd off the server's landing and running on, the landing's
    # exact spot and facing were never seen. "Also once going through the portal technically the player has arrived")
    lua, ns = game
    N = ns.Nav
    lua.execute("AGPS_UFG = UnitFactionGroup UnitFactionGroup = function() return 'Alliance', 'Alliance' end")
    was_pos = lua.eval("{ AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] }")
    was_time = lua.eval("GetTime")
    clock = [900000.0]
    try:
        N.roomIn = None
        was_faction = ns.CharDB().faction
        ns.CharDB().faction = 'Alliance'

        def at(x, y, dt=0.25, frames=1):
            for _ in range(frames):
                clock[0] += dt
                lua.execute(f"AGPS_NOW = {clock[0]} AGPS_T = {clock[0]} AGPS_POS = {{ {x}, {y}, 0 }}")
                _redraw(lua, ns)
                N.Status(x, y, 0)

        lua.execute("GetTime = function() return AGPS_NOW end")
        at(-8990.0, 830.0, frames=1)
        N.SetStops(lua.eval("{ { x = -8990.0, y = 862.9, cont = 0, z = 29.6, name = 'Stormwind Mage Trainer' } }"), False,
                   "red")
        at(-8990.0, 830.0, dt=2, frames=6)
        # (up the walk as drawn, to the top, on the way from the stairs to the portal: the portal, not stairs)
        first = N.route.parts[1]
        walk = [(first.pts[k], first.pts[k + 1]) for k in range(1, len(first.pts), 2)]
        for x, y in walk[:next(i for i, p in enumerate(walk) if math.dist(p, (-9014.6, 873.0)) < 0.5) + 1]:
            at(x, y, dt=0.5)
        at(-9014.6, 873.0, dt=0.5, frames=2)
        _path, man = ns.Turns.Ahead(N.route, "stop")
        assert man[1].kind == "board", man[1].text
        # (through it: 9 yd on in a quarter of a second, 1.4 yd from the landing, the facing anything; arrived)
        at(-9017.0, 876.6, frames=2)
        at(-9016.1, 886.0)
        assert N.roomIn is not None
        assert N.dest is None or N.arrivedAt, str(N.StepsText(9))
        # (walking by the landing at the same pace isn't a hop: on foot over the street's same spot)
        N.roomIn = None
        at(-9016.1, 880.0, frames=1)
        at(-9016.1, 886.0, dt=1.0)
        assert N.roomIn is None
    finally:
        N.Clear()
        N.roomIn = None
        lua.globals().GetTime = was_time
        if "was_faction" in locals():
            ns.CharDB().faction = was_faction
        lua.globals().AGPS_POS = was_pos
        lua.execute("UnitFactionGroup = AGPS_UFG")


def _arrow_route(lua, ns, t0):
    # (a route the arrow window shows: set, drawn, "keep this route?" answered)
    N, G = ns.Nav, ns.GPS
    N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    for k in range(2):
        lua.execute(f"AGPS_T = {t0 + k * 0.5}")
        G.Update()
        if N.RedAsking():
            G.confirmBox.yes._scripts.OnClick(G.confirmBox.yes)
    assert N.route and not N.RedAsking()


def test_the_arrow_off_hides_the_arrow_and_keeps_the_directions(game):
    # (asked 2026-11-17: "add a fifth option that is 'Hide' that hides the arrow"; its own check since 2026-11-24,
    # `arrowShown`, the old Hide carried over to it) the arrow's panel unseen and
    # click-through, the directions as ever (their own clamp, no arrow column); a hearthstone to use at the route's start
    # brings the panel back for its button; with the directions hidden too the arrow shows (never an empty window)
    lua, ns = game
    A, N, G, st = ns.Arrow, ns.Nav, ns.GPS, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections
    lua.execute("""AzerothGPSArrow.EnableMouse = function(s, v) s._mouse = v end
      AzerothGPSDirections.EnableMouse = function(s, v) s._mouse = v end""")
    saved = _arrow_settings(st)
    real = N.UseNow
    try:
        st.arrowLocked = st.dirLocked = False
        _arrow_route(lua, ns, 1200)
        A.Apply()
        af._scripts.OnUpdate(af, 1)
        assert af._alpha > 0 and af._mouse and dirf._alpha > 0  # (as before: both seen)
        st.arrowShown = False
        A.Apply()
        lua.execute("AGPS_T = 1201")
        af._scripts.OnUpdate(af, 1)
        assert A.Hidden() and af._shown and af._alpha == 0 and not af._mouse  # (shown: its OnUpdate runs the text)
        assert dirf._shown and dirf._alpha > 0 and dirf._mouse
        assert tuple(dirf._clamp.values()) == (0, 0, 0, 0)
        # the route starts with the hearthstone: its icon and button where the arrow was, the panel seen for it
        hearth = lua.eval("{ 0, 2254, 293, 0, -8900, -160, 10, 'your Hearthstone', '', 'Northshire Valley', 'your Hearthstone', use = true, item = 6948 }")
        N.UseNow = lua.eval("function(t) return function() return t end end")(hearth)
        lua.execute("AGPS_T = 1202")
        af._scripts.OnUpdate(af, 1)
        assert lua.globals().AzerothGPSArrowUseButton._shown and af._alpha > 0 and af._mouse
        N.UseNow = real
        lua.execute("AGPS_T = 1203")
        af._scripts.OnUpdate(af, 1)
        assert af._alpha == 0
        # the text hidden too: the arrow shows after all
        st.dirShown = False
        A.Apply()
        lua.execute("AGPS_T = 1204")
        af._scripts.OnUpdate(af, 1)
        assert not A.Hidden() and af._alpha > 0 and not dirf._shown
    finally:
        N.UseNow = real
        lua.execute("AzerothGPSArrow.EnableMouse = nil AzerothGPSDirections.EnableMouse = nil")
        N.Clear()
        _arrow_restore(ns, saved)


def test_the_directions_text_hidden_leaves_the_arrow(game):
    # (asked 2026-11-17: "hide the text separately and only show the arrow": dirShown, Options > Directions > Show the
    # directions text) the directions' panel hidden, the arrow seen on its own with its route
    lua, ns = game
    A, N, st = ns.Arrow, ns.Nav, ns.settings.gps
    af, dirf = lua.globals().AzerothGPSArrow, lua.globals().AzerothGPSDirections
    saved = _arrow_settings(st)
    try:
        _arrow_route(lua, ns, 1300)
        st.dirShown = False
        A.Apply()
        lua.execute("AGPS_T = 1301")
        af._scripts.OnUpdate(af, 1)
        assert not dirf._shown and af._shown and af._alpha > 0 and A.arrowTex._shown
        # Hide picked with the text hidden (a saved setting, a slash command): the arrow still shows
        st.arrowSide = "hide"
        A.Apply()
        lua.execute("AGPS_T = 1302")
        af._scripts.OnUpdate(af, 1)
        assert not dirf._shown and af._alpha > 0 and A.arrowTex._shown
    finally:
        N.Clear()
        _arrow_restore(ns, saved)


def test_a_glowing_resume_button_shows_on_the_minimap_square_while_paused(minimap):
    # (1.3.9, asked 2026-11-18 with a red circle just right of the square's logo: "(enabled by default) I'd like the
    # unpause button to also show in the minimap glowing here") replaceMinimapResume on (the default): while routing is
    # paused, however it was, a glowing Resume Routing button right of the logo; a click resumes; off, or not paused, or
    # the map opened out of the square (the quick bar's glowing button there): none
    lua, ns = minimap
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    assert ns.DEFAULTS.gps.replaceMinimapResume is True and st.replaceMinimapResume is not False
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
        assert G.MinimapMode()
        r = G.mmResume
        assert r is not None and not r._shown  # (routing on: none)
        for why in ("manual", "auto", "perf"):
            N.SetPaused(True, why)
            assert r._shown and r.glow._shown, why
            N.SetPaused(False)
            assert not r._shown, why
        N.SetPaused(True, "auto")
        # (the Pause Routing button's icon; just right of the logo, clear of it, inside the square's bottom)
        assert "spell_nature_timestop" in str(r.icon._tex).lower()  # (drawn at its size: Media\Icons, G.RoundArt)
        b = G.mmButton
        size = b.logoSize
        p = r._pts.BOTTOMLEFT
        assert p[3] == "BOTTOMLEFT" and p[4] >= size * (G.MINIMAP_LOGO_IN + 0.5) and p[5] > 0
        assert r._w < size and r._w >= G.MINIMAP_RESUME_MIN  # (smaller than the logo, which it follows)
        # (its tooltip: Resume Routing and why it was paused)
        lua.execute("AGPS_TIP = {} AGPS_AL = GameTooltip.AddLine GameTooltip.AddLine = function(_, t) AGPS_TIP[#AGPS_TIP + 1] = t end")
        try:
            r._scripts.OnEnter(r)
            assert str(lua.eval("GameTooltip._text")) == "Resume Routing"
            assert any("not following the route" in str(t) for t in lua.eval("AGPS_TIP").values())
        finally:
            lua.execute("GameTooltip.AddLine = AGPS_AL")
        # (the glow pulses as the quick buttons' does)
        lua.execute("AGPS_T = AGPS_T + 0.1")
        r._scripts.OnUpdate(r, 0.1)
        assert abs(r.glow._alpha - G.GlowAlpha()) < 1e-9
        # a click resumes
        r._scripts.OnClick(r, "LeftButton")
        assert N.paused is None and not r._shown
        # the option off: none; on again: back
        N.SetPaused(True, "manual")
        assert r._shown
        st.replaceMinimapResume = False
        G.RefreshMinimapResume()
        assert not r._shown
        st.replaceMinimapResume = True
        G.RefreshMinimapResume()
        assert r._shown
        # (a smaller square: the logo and the button shrink together)
        st.replaceMinimapSize = "large"
        G.ApplySettings()
        big = r._w
        st.replaceMinimapSize = "small"
        G.ApplySettings()
        assert r._shown and r._w < big
        # opened out of the square (the square not kept): the window's quick bar has the glowing button instead
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        assert not r._shown
        G.SetMinimapExpanded(False)
        _tick(lua, ns)
        assert r._shown
        # the route cleared while paused: gone
        N.Clear()
        assert not r._shown
    finally:
        st.replaceMinimapResume = True
        N.SetPaused(False)
        N.Clear()


def test_the_route_can_be_left_off_the_minimap_square(minimap):
    # (asked 2026-11-17: "add option to not show the route on our minimap replacement") replaceMinimapRoute off: no route
    # line on the square; on (the default): drawn; the map opened out of the square keeps its route either way
    lua, ns = minimap
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    blue = "0.05,0.28,0.85"

    def route_drawn(t):
        for k in range(2):
            lua.execute(f"AGPS_T = {t + k * 0.5}")
            G.Update()
            if N.RedAsking():
                G.confirmBox.yes._scripts.OnClick(G.confirmBox.yes)
        return blue in _colors(_lines(lua))
    assert ns.DEFAULTS.gps.replaceMinimapRoute is True
    try:
        st.replaceMinimap = True
        G.ApplySettings()
        N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
        assert G.MinimapMode() and route_drawn(1400)
        st.replaceMinimapRoute = False
        G.ApplySettings()
        assert not route_drawn(1402) and N.route
        G.SetMinimapExpanded(True)  # (opened out of the square: the usual map, its route)
        _tick(lua, ns)
        assert not G.MinimapMode() and route_drawn(1404)
        G.SetMinimapExpanded(False)
        _tick(lua, ns)
        assert G.MinimapMode() and not route_drawn(1406)
        st.replaceMinimapRoute = True
        G.ApplySettings()
        assert route_drawn(1408)
    finally:
        st.replaceMinimapRoute = True
        N.Clear()


def test_the_leg_to_the_next_stop_is_drawn_over_the_later_legs(game):
    # (asked 2026-11-19: following the leg to the next stop, the next leg drawn back the same way covered it) with
    # several stops the leg to the next stop is on a higher draw sublevel (G.ROUTE_TOP_SUB) than the later legs, its
    # lines too; with one stop every line stays on sublevel 0, as before
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    N.Clear()
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")

    def route_subs():
        for t in range(3):
            lua.execute("AGPS_T = AGPS_T + 1")
            _redraw(lua, ns)
        segs, n = G.DrawnSegs()
        # (the route's segments: kept while moving; their color, a table with several stops, else an index)
        def col(c):
            return tuple(c[k] for k in (1, 2, 3)) if lua.eval("type")(c) == "table" else c
        return [(segs[i][10], col(segs[i][5])) for i in range(1, n + 1) if segs[i][8]]

    try:
        # there and back: Two is next to where the player stands, so its leg goes back over the leg to One
        N.SetStops(lua.eval("{ { x = 2290, y = 293, cont = 0, name = 'One' }, { x = 2256, y = 293, cont = 0, name = 'Two' } }"),
                   False, "red")
        subs = route_subs()
        top = [c for s, c in subs if s == G.ROUTE_TOP_SUB]
        rest = [c for s, c in subs if s == 0]
        assert top and rest, subs
        assert not set(top) & set(rest)  # (One's leg up top in its color, Two's under it in its own)
        assert all(s in (0, G.ROUTE_TOP_SUB) for s, _ in subs)
        lines = _shown(lua, lambda w: getattr(w, "_sub", None) == G.ROUTE_TOP_SUB and w._layer == "OVERLAY" and w._kind == "Line")
        assert lines  # (and the lines themselves set to it)
        # one stop: nothing raised, and the lines reused go back to sublevel 0
        N.SetStops(lua.eval("{ { x = 2290, y = 293, cont = 0, name = 'One' } }"), False, "red")
        subs = route_subs()
        assert subs and all(s == 0 for s, _ in subs)
        assert not _shown(lua, lambda w: getattr(w, "_sub", None) == G.ROUTE_TOP_SUB and w._layer == "OVERLAY"
                          and w._kind == "Line")
    finally:
        N.Clear()


def test_the_map_window_goes_over_the_games_windows_with_our_popups_over_it(minimap):
    # (Kooki3z, for 1.3.14: "make the GPS map outside of minimap pop out also go over UI elements like the pop out one
    # does, options still go on top of it just like the pop out one") the map in its own window at the grown-out
    # map's strata, over the game's windows; our popups (ns.Window, the options) lifted over it while it shows, back to
    # their own when it closes or is the minimap square again; the square under them all as before
    lua, ns = minimap
    G, st = ns.GPS, ns.settings.gps
    _expand_setup(lua)
    frame = lua.eval("AzerothGPSFrame")
    st.replaceMinimap, st.useWorldMap, st.shown = False, False, True
    frame._shown = True
    G.ApplySettings()
    assert frame._strata == G.MINIMAP_EXPANDED_STRATA and ns.popupsOver
    f = ns.Window("AzerothGPSTestPopup", 200, 100, "Test")
    own = str(f.GetFrameStrata(f))
    f._shown = True
    f._scripts.OnShow(f)
    assert f._strata == ns.POPUP_OVER_STRATA  # (over the map)
    ns.Options.Toggle()
    opts = lua.eval("AzerothGPSOptions")
    frame._scripts.OnUpdate(frame, 0.01)  # (the map's next frame: a popup whose own OnShow went past the hook, lifted)
    assert opts._shown and opts._strata == ns.POPUP_OVER_STRATA
    ns.Options.Toggle()
    # the map closed: back to their own strata
    frame._shown = False
    frame._scripts.OnHide(frame)
    assert not ns.popupsOver and f._strata == own
    # shown again: over it again (and one shown since, lifted on the map's next frame)
    frame._shown = True
    frame._scripts.OnShow(frame)
    assert ns.popupsOver and f._strata == ns.POPUP_OVER_STRATA
    # the map as the minimap square: under the game's windows, our popups back
    st.replaceMinimap = True
    G.ApplySettings()
    assert G.MinimapMode() and frame._strata == "BACKGROUND" and not ns.popupsOver and f._strata == own
    G.SetMinimapExpanded(True)  # (grown out of it: over them again, as before)
    _tick(lua, ns)
    assert frame._strata == G.MINIMAP_EXPANDED_STRATA and f._strata == ns.POPUP_OVER_STRATA
    G.SetMinimapExpanded(False)
    _tick(lua, ns)
    st.replaceMinimap = False
    G.ApplySettings()
    f._shown = False


def test_the_route_tour_waits_for_the_route_before_zooming(game):
    # (Kooki3z, 2026-11-23: "The zoom in when setting a route shouldn't happen until a route is actually displayed")
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    try:
        N.Clear()
        G.Follow()
        G.AddStopAt(2400.0, 400.0, "Somewhere near Brill")
        G.ConfirmRoute()  # (skips the hold: zooms out as soon as there's a route)
        assert G.TourPhase() == "hold"
        for _ in range(20):  # (the route worked out in the frame's update, not left over from the test before)
            if N.route:
                break
            G.Update()
        real = N.route
        assert real and G.TourPhase() == "hold"
        N.route = None  # (still being worked out)
        t = lua.eval("GetTime")()
        for k in range(1, 40):
            G.TourStep(t + k * 0.5)
            assert G.TourPhase() == "hold"  # (no zoom over nothing)
        N.route = real
        G.TourStep(t + 20.5)
        assert G.TourPhase() == "out"  # (the route shown: the tour goes on)
        # (item 29: the world grid's stand-in, its faded line while it works, is waited out too; fit once, on settling)
        G.ConfirmRoute()
        assert G.TourPhase() == "hold"
        wg_was = ns.settings.gps.worldGrid
        ns.settings.gps.worldGrid = True
        ns.WorldGrid.Set(True)
        stand_in = lua.table(pending=True, parts=real.parts, legs=real.legs)
        N.route = stand_in
        assert N.StandIn()
        for k in range(1, 40):
            G.TourStep(t + 30 + k * 0.5)
            assert G.TourPhase() == "hold"  # (no zoom to the line)
        N.route = real
        G.TourStep(t + 60.5)
        assert G.TourPhase() == "out"
        ns.settings.gps.worldGrid = wg_was
        ns.WorldGrid.Set(bool(wg_was))
    finally:
        N.Clear()
        G.Follow()
