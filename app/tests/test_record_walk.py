"""The road tools' Record (1.1.6): a road walked in game saved as a drawn road, with what the game tells of where the
player was (indoors, the minimap's zone text), its corners, the player's stairs marks, split and paused as it should be.
Run with the whole addon (gameharness), the player in Brill."""

import math

import pytest

X0, Y0 = 2254.0, 293.0  # (Brill, the harness's start)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    lua.execute("""
      AGPS_NS_PRINT = AGPS_NS.Print
      AGPS_INDOORS, AGPS_ZONE, AGPS_COMBAT = false, "Brill", false
      IsIndoors = function() return AGPS_INDOORS end
      GetMinimapZoneText = function() return AGPS_ZONE end
      UnitAffectingCombat = function() return AGPS_COMBAT end
    """)
    return lua, ns


@pytest.fixture()
def rec(game):
    lua, ns = game
    ns.db.tracks = lua.eval("{}")
    lua.execute(f"AGPS_POS = {{ {X0}, {Y0}, 0 }}; AGPS_INDOORS, AGPS_ZONE, AGPS_COMBAT = false, 'Brill', false")
    yield lua, ns
    R = ns.Record
    if R.rec is not None:
        R.rec = None
    R.REC_MAX_POINTS = 1000
    ns.inCombat = False
    ns.Geo.SetOverride(None)
    ns.db.tracks = lua.eval("{}")


class Walker:
    """The player walking at `speed` yd/s, a Record sample every 0.1 s as the game's frames give them."""

    def __init__(self, lua, ns, speed=7.0):
        self.lua, self.ns, self.speed = lua, ns, speed
        self.x, self.y = X0, Y0
        self.t = float(lua.eval("AGPS_T"))

    def put(self, x, y):
        self.x, self.y = x, y
        self.lua.execute(f"AGPS_POS = {{ {x}, {y}, 0 }}")

    def tick(self):
        self.t += 0.1
        self.lua.execute(f"AGPS_T = {self.t}")
        self.ns.Record.RecordTick(self.t)

    def walk(self, dx, dy):
        """Walk (dx, dy) yards from where the player is, sampled on the way."""
        d = math.hypot(dx, dy)
        steps = max(1, math.ceil(d / (self.speed * 0.1)))
        x, y = self.x, self.y
        for k in range(1, steps + 1):
            self.put(x + dx * k / steps, y + dy * k / steps)
            self.tick()


def tracks(lua, ns):
    return [ns.db.tracks[i] for i in range(1, len(ns.db.tracks) + 1)]


def points(t):
    return [(t.pts[i], t.pts[i + 1]) for i in range(1, len(t.pts), 2)]


def test_a_walk_is_saved_with_its_corner_and_what_the_game_said(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    R.StartRecording(True)
    w.walk(12, 0)
    lua.execute("AGPS_INDOORS, AGPS_ZONE = true, 'Gallows\\' End Tavern'")
    w.walk(0, 12)
    said, ns.Print = [], lambda *m: said.append(str(m[0]))
    try:
        R.StopRecording()
    finally:
        ns.Print = lua.eval("AGPS_NS_PRINT")
    # (the game gives no height: said that the walk shows flat until the road data has it, 2026-11-18)
    assert said[-1].startswith("Recorded walks show flat until"), said
    (t,) = tracks(lua, ns)
    assert t.recorded and t.op == "add" and t.continent == 0
    pts = points(t)
    # (a point every 2 yd or so, and one at the corner)
    assert 10 <= len(pts) <= 16
    assert min(math.hypot(x - (X0 + 12), y - Y0) for x, y in pts) < 0.8
    assert max(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])) < 2.8
    # (indoors per point, the zone text where it changed, the time between points)
    ind = str(t.rec.ind)
    assert len(ind) == len(pts) and ind.startswith("0") and ind.endswith("1")
    zt = [t.rec.zt[i] for i in range(1, len(t.rec.zt) + 1)]
    assert zt[0] == 1 and zt[1] == "Brill" and zt[3] == "Gallows' End Tavern"
    assert len(str(t.rec.ts).split(",")) == len(pts)
    assert t.zs is None  # (no floor picked: a plain drawn road until the watcher works its heights out)


def test_a_floor_picked_while_walking_is_kept_as_a_strokes(rec):
    lua, ns = rec
    R, w, G = ns.Record, Walker(*rec), ns.GPS
    R.StartRecording(True)
    w.walk(6, 0)
    G.editFloor = lua.eval("{ z = 63.5 }")
    try:
        w.walk(6, 0)
    finally:
        G.editFloor = None
    R.StopRecording()
    (t,) = tracks(lua, ns)
    zs = [t.zs[i] for i in range(1, len(t.zs) + 1)]
    assert len(zs) == len(t.pts) // 2 and set(zs) == {63.5}  # (filled in, for routes now)
    # (and only where it was picked, for the watcher: where the pick changed)
    pk = [t.rec.pk[i] for i in range(1, len(t.rec.pk) + 1)]
    assert len(pk) == 2 and pk[1] == 63.5 and 3 <= pk[0] <= len(zs)


def test_a_jump_a_loading_screen_and_another_level_start_a_new_walk(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    R.StartRecording(True)
    w.walk(12, 0)
    w.put(w.x + 60, w.y)  # (a teleport)
    w.tick()
    w.walk(12, 0)
    lua.eval("AGPS_FIRE")("PLAYER_ENTERING_WORLD", False, False)  # (a loading screen)
    w.walk(12, 0)
    R.StopRecording()
    ts = tracks(lua, ns)
    assert len(ts) == 3
    assert all(t.recorded for t in ts)
    # (no line across the jump)
    assert max(x for x, _y in points(ts[0])) < X0 + 13 and min(x for x, _y in points(ts[1])) > X0 + 70


def test_recording_waits_in_combat_and_goes_on_where_it_stopped(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    R.StartRecording(True)
    w.walk(10, 0)
    n = len(R.rec.pts)
    lua.execute("AGPS_COMBAT = true")
    w.walk(1, 0)  # (a step in the fight: not recorded)
    assert R.rec.paused == "in combat" and len(R.rec.pts) == n
    lua.execute("AGPS_COMBAT = false")
    w.walk(10, 0)
    assert R.rec.paused is None
    # (paused by the player, then walked away: a new walk on going on)
    R.TogglePause()
    w.walk(0, 20)
    assert R.rec.paused == "paused"
    R.TogglePause()
    w.walk(10, 0)
    R.StopRecording()
    ts = tracks(lua, ns)
    assert len(ts) == 2
    assert len(points(ts[0])) >= 10  # (the fight didn't split the first)


def test_nothing_is_recorded_from_the_simulated_player_or_on_a_flight(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    R.StartRecording(True)
    ns.Geo.SetOverride(lua.eval(f"{{ x = {X0 + 100}, y = {Y0}, cont = 0 }}"))
    w.walk(12, 0)
    assert R.rec.paused == "the simulated player is on"
    ns.Geo.SetOverride(None)
    lua.execute("UnitOnTaxi = function() return true end")
    try:
        w.walk(12, 0)
        assert R.rec.paused == "on a flight"
    finally:
        lua.execute("UnitOnTaxi = function() return false end")
    R.StopRecording()
    assert len(tracks(lua, ns)) == 0


def test_stairs_marks_are_kept_with_the_walk(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    R.StartRecording(True)
    w.walk(6, 0)
    assert R.MarkStairs()
    foot = (w.x, w.y)
    w.walk(8, 0)
    lua.eval("AzerothGPS_RecordStairs")()  # (the key binding's)
    top = (w.x, w.y)
    w.walk(6, 0)
    assert R.MarkStairs()  # (stairs again: still open at Stop, closed at the walk's end)
    w.walk(4, 0)
    R.StopRecording()
    (t,) = tracks(lua, ns)
    st = [t.stairs[i] for i in range(1, len(t.stairs) + 1)]
    pts = points(t)
    assert len(st) == 4 and st[0] < st[1] < st[2] < st[3] == len(pts)
    assert math.dist(pts[st[0] - 1], foot) < 0.2 and math.dist(pts[st[1] - 1], top) < 0.2


def test_a_long_walk_is_saved_in_pieces_that_join(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    R.REC_MAX_POINTS = 10
    R.StartRecording(True)
    w.walk(50, 0)
    R.StopRecording()
    ts = tracks(lua, ns)
    assert len(ts) >= 2
    for a, b in zip(ts, ts[1:]):
        assert points(a)[-1] == points(b)[0]
    assert len({t.time for t in ts}) == len(ts)  # (each its own key)


def test_the_walk_draws_as_it_goes_and_a_short_one_isnt_saved(rec):
    lua, ns = rec
    R, w, G = ns.Record, Walker(*rec), ns.GPS
    R.StartRecording(True)
    w.walk(5, 0)
    assert G.DrawRecording(X0, Y0, 0, 2, 0) >= 2
    assert G.DrawRecording(X0, Y0, 0, 2, 1) == 0  # (another level in view)
    G.Update()  # (the redraw with it: no error)
    R.StopRecording()
    assert len(tracks(lua, ns)) == 0


def test_a_long_walk_draws_only_what_shows(rec):
    # (a walk is up to REC_MAX_POINTS: a line a point zoomed out cost a redraw what 2500 lines of another addon's do)
    lua, ns = rec
    R, w, G = ns.Record, Walker(*rec, speed=20.0), ns.GPS
    R.StartRecording(True)
    for _ in range(9):
        w.walk(200, 0)
        w.walk(0, 6)
    n = len(R.rec.pts) // 2
    assert n > 900
    # (zoomed out, a tenth of a pixel a yard: points under 2 px apart drawn as one)
    assert G.DrawRecording(X0 + 900, Y0, 0, 0.1, 0, 200) < 120
    # (zoomed in at its start: only the lines in view)
    assert G.DrawRecording(X0, Y0, 0, 4, 0, 200) < 60
    R.StopRecording()


def test_recording_goes_on_after_a_reload_not_after_a_logout(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    fire = lua.eval("AGPS_FIRE")
    R.StartRecording(True)
    w.walk(12, 0)
    fire("PLAYER_LOGOUT")
    assert len(tracks(lua, ns)) == 1 and ns.CharDB().recordOn
    R.rec = None  # (the next session)
    fire("PLAYER_ENTERING_WORLD", False, True)  # (a /reload)
    assert R.rec is not None and not ns.CharDB().recordOn
    w.walk(12, 0)
    fire("PLAYER_LOGOUT")
    R.rec = None
    fire("PLAYER_ENTERING_WORLD", True, False)  # (logged in again)
    assert R.rec is None and not ns.CharDB().recordOn
    assert len(tracks(lua, ns)) == 2
    R.window.Hide(R.window)


def test_the_record_window_and_its_buttons(rec):
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    f = R.ShowWindow()
    assert str(f.rec.GetText(f.rec)) == "Record" and str(f.stairs.GetText(f.stairs)) == "Stairs Start"
    f.rec._scripts.OnClick(f.rec)  # (Record)
    w.walk(4, 0)
    R.RefreshWindow()
    assert str(f.rec.GetText(f.rec)) == "Pause" and "Recording" in str(f.status.GetText(f.status))
    f.stairs._scripts.OnClick(f.stairs)
    R.RefreshWindow()
    assert str(f.stairs.GetText(f.stairs)) == "Stairs End"
    f.rec._scripts.OnClick(f.rec)  # (Pause)
    assert str(f.rec.GetText(f.rec)) == "Resume"
    f.stop._scripts.OnClick(f.stop)
    assert R.rec is None and str(f.rec.GetText(f.rec)) == "Record"
    R.ToggleWindow()
    assert not f.IsShown(f)


def test_the_record_button_sits_with_the_road_tools(game):
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    st.devTools = True
    try:
        ids = [str(m.id) for m in G.groupOf["mapEdit"].members.values()]  # (in the Map Editing menu, 1.3.0)
        assert ids.index("roadRecord") == ids.index("roadStairs") + 1
    finally:
        st.devTools = False
    from azerothgps.paths import ADDON_DIR

    assert "AZEROTHGPS_RECORD_STAIRS" in (ADDON_DIR / "Bindings.xml").read_text(encoding="utf-8")
    assert lua.eval("BINDING_NAME_AZEROTHGPS_RECORD_STAIRS")


def test_a_portals_short_hop_starts_a_new_walk(rec):
    # (Stormwind's Wizard's Sanctum, 2026-11-17: the tower's top and the trainers' room 9 yd apart on the map, under
    # REC_JUMP_YD; recorded as one walk, its floors dropped into the room halfway up the stairs). A hop onto where a
    # portal puts you is a new walk; walking over that spot isn't.
    lua, ns = rec
    R, w = ns.Record, Walker(*rec)
    T = ns.Transports
    key = "agps_test_portal"
    T[key] = lua.eval(f"""{{ 0, {X0 + 30}, {Y0}, 0, {X0 + 50}, {Y0}, 5, "teleporter", "A", "B", "teleporter",
                             land1 = {{ {X0 + 40}, {Y0 + 20} }}, land2 = {{ {X0 + 21}, {Y0} }} }}""")
    try:
        R.StartRecording(True)
        w.walk(12, 0)
        w.put(w.x + 9, w.y)  # (through the portal: onto land2, 9 yd on)
        w.tick()
        w.walk(12, 0)
        w.walk(-14, 0)  # (and back on foot over land2's spot: the same walk)
        R.StopRecording()
        ts = tracks(lua, ns)
        assert len(ts) == 2
        assert max(x for x, _y in points(ts[0])) < X0 + 13 and min(x for x, _y in points(ts[1])) > X0 + 19
        assert not R.PortalHop(0, X0 + 18, Y0, X0 + 21, Y0)  # (a step onto it: no hop)
        assert R.PortalHop(0, X0 + 12, Y0, X0 + 21, Y0) and not R.PortalHop(1, X0 + 12, Y0, X0 + 21, Y0)
    finally:
        T[key] = None
