"""AzerothGPS's yes / no questions on the map (1.4.0 blockers, Kooki3z on e96d80ee).

Item 93/93b: the too-high-zone question, shown again later in a session (after an earlier question closed with the map
and the map's mode switched), had Yes and No as plain text that took no clicks; after a /reload they worked. The
question on the map is now held by a frame of its own over everything (G.askHolder), not in the map's frames, its
strata and its buttons' levels set again each time it's shown, with Enter / Escape answering it.

Item 85: with the GPS map as the minimap, a question shows only on the map (opened out, or the world map), never loose
mid-screen nor by the directions; with the map closed only the glowing "?" over the logo. Without it, as before.

Item 87: "Take it?" -> No with no way round the guards (Horde 60 at Gol'Bolar Quarry, Dun Morogh 64.8, 54.3, to the
Wetlands past Dun Algaz, Dun Morogh ~78.9, 34.0): within Nav.REFUSED_SECONDS the searches stop and the player is asked
whether to take the way past them; never minutes of "Routing..."."""

from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP


def _setup(lua, ns):
    lua.execute(SETUP)
    st = ns.settings.gps
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized", "windowFrame",
                              "replaceMinimapKeepSquare")}
    st.shown, st.minimized, st.replaceMinimapKeepSquare = True, None, False
    return was


def _teardown(lua, ns, was):
    lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil InCombatLockdown = function() return false end")
    st = ns.settings.gps
    for k, v in was.items():
        st[k] = v
    ns.GPS.WorldMapChanged()
    ns.GPS.ApplySettings()
    ns.Nav.Clear()


def _shown_up(lua, f):
    return bool(lua.eval("function(f) return AGPS_NS.GPS.ShownUp(f) end")(f))


def _same(lua, a, b):
    return bool(lua.eval("function(a, b) return rawequal(a, b) end")(a, b))


def _in_map_tree(lua, box):
    return bool(lua.eval("""function(box)
      for _, e in ipairs(AGPS_NS.GPS.LevelOffsets()) do if e[1] == box then return true end end
      return false end""")(box))


def _check_clickable(lua, ns, box):
    """On screen over everything, out of the map's own frames, its buttons over its art and enabled."""
    G = ns.GPS
    assert _same(lua, box._parent, G.askHolder) and not _in_map_tree(lua, box)
    assert _shown_up(lua, box) and box._shown and not box.answered
    assert G.askHolder._strata == ns.POPUP_OVER_STRATA and box._strata == ns.POPUP_OVER_STRATA
    for b in (box.yes, box.no):
        assert b._shown and b._strata == box._strata
        assert b._level == box.GetFrameLevel(box) + ns.ASK_BUTTON_LEVELS
        assert b.IsEnabled(b)
    assert box._keyboard is True


def test_a_question_shown_again_after_the_map_closed_and_its_mode_switched_takes_clicks(game):  # noqa: F811
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    was = _setup(lua, ns)
    try:
        st.replaceMinimap, st.useWorldMap = True, False
        G.ApplySettings()
        N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
        assert G.MinimapMode()
        answers = []
        # (1. "Take it?" asked with the map out of the square)
        G.SetMinimapExpanded(True)
        G.ConfirmHostile(lua.table("Kharanos"), "H", lambda *a: answers.append("yes1"), lambda *a: answers.append("no1"))
        box = G.PendingQuestion()
        # (the game's real level for this box: what it was set to; the stand-in's is a constant)
        lua.eval("function(b) b.GetFrameLevel = function(s) return s._level or 5 end end")(box)
        assert _shown_up(lua, box)
        # (2. the map closed unanswered: hidden with it, the "?" glowing; no answer)
        G.SetMinimapExpanded(False)
        assert _same(lua, G.PendingQuestion(), box) and not _shown_up(lua, box) and G.AskWanted() and answers == []
        # (3. the "?" clicked: the map out, the question back; Escape is No)
        G.mmAsk._scripts.OnClick(G.mmAsk, "LeftButton")
        assert G.mmState.expanded and _shown_up(lua, box)
        _check_clickable(lua, ns, box)
        assert box._scripts.OnKeyDown(box, "ESCAPE") and answers == ["no1"] and G.PendingQuestion() is None
        G.SetMinimapExpanded(False)
        # (4. the map's mode switched: the world map with the GPS map in it, opened)
        st.useWorldMap = True
        G.ApplySettings()
        lua.execute("ToggleWorldMap()")
        assert G.WorldMapHosted()
        # (5. the too-high zone's question: the same window, clickable over the world map)
        again = []
        G.ConfirmRedZone(lua.eval("{ { 'Dustwallow Marsh', 35, 45 } }"), lua.eval("{ { name = 'That stop' } }"),
                         lambda *a: again.append(True))
        box2 = G.PendingQuestion()
        assert _same(lua, box2, box) and "Dustwallow Marsh" in str(box2.text._text)
        _check_clickable(lua, ns, box2)
        # (the world map closed and opened again: hidden with it, then back and still clickable)
        lua.execute("ToggleWorldMap()")
        assert not _shown_up(lua, box2) and G.AskWanted()
        lua.execute("ToggleWorldMap()")
        assert G.WorldMapHosted() and _shown_up(lua, box2)
        _check_clickable(lua, ns, box2)
        box2.yes._scripts.OnClick(box2.yes, "LeftButton")
        assert again == [True] and G.PendingQuestion() is None
        # (Enter answers Yes; other keys go on to the game)
        G.Confirm("Keep this route?", lambda *a: answers.append("yes3"), lambda *a: answers.append("no3"))
        box3 = G.PendingQuestion()
        assert not box3._scripts.OnKeyDown(box3, "W") and box3._propagate is True and answers == ["no1"]
        assert box3._scripts.OnKeyDown(box3, "ENTER") and answers == ["no1", "yes3"]
        # (in combat the keys aren't taken: they go on to the game)
        lua.execute("InCombatLockdown = function() return true end")
        G.Confirm("Keep this route?", lambda *a: answers.append("yes4"), lambda *a: answers.append("no4"))
        box4 = G.PendingQuestion()
        assert box4._keyboard is False and not box4._scripts.OnKeyDown(box4, "ENTER")
        box4.no._scripts.OnClick(box4.no, "LeftButton")
        assert answers[-1] == "no4"
    finally:
        _teardown(lua, ns, was)


def test_with_the_minimap_replaced_a_question_is_only_on_the_map(game):  # noqa: F811
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    was = _setup(lua, ns)
    try:
        st.replaceMinimap, st.useWorldMap = True, False
        G.ApplySettings()
        N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
        assert G.MinimapMode() and not G.mmState.expanded
        # (the directions showing: still not by them, and never mid-screen)
        lua.execute("AGPS_DIR_WAS = AGPS_NS.Arrow.dir AGPS_NS.Arrow.dir = NewWidget('Frame') AGPS_NS.Arrow.dir:Show()")
        try:
            G.ConfirmHostile(lua.table("Kharanos"), "H", lambda *a: None, lambda *a: None)
        finally:
            lua.execute("AGPS_NS.Arrow.dir = AGPS_DIR_WAS")
        box = G.PendingQuestion()
        assert box.onMap and not box.byDirections and _same(lua, box._parent, G.askHolder)
        assert not _shown_up(lua, box) and G.AskWanted()  # (only the "?")
        G.mmAskWatch._scripts.OnUpdate(G.mmAskWatch, 1)
        assert G.mmAsk._shown
        G.BringUpQuestion()
        assert G.mmState.expanded and _shown_up(lua, box) and not G.AskWanted()
        # (anchored to the map's middle)
        assert G.askHolder._pts.CENTER[1] == "CENTER"
        box.yes._scripts.OnClick(box.yes, "LeftButton")
        G.SetMinimapExpanded(False)
        # (without the minimap replaced and the map window closed: mid-screen, as before)
        st.replaceMinimap = False
        st.shown = False
        G.ApplySettings()
        G.Confirm("Keep this route?", lambda *a: None, lambda *a: None)
        box2 = G.PendingQuestion()
        assert not box2.onMap and not _same(lua, box2._parent, G.askHolder) and _shown_up(lua, box2)
        box2.no._scripts.OnClick(box2.no, "LeftButton")
    finally:
        _teardown(lua, ns, was)


# Dun Morogh (uiMap 1426) 64.8, 54.3 and 78.9, 34.0 in world yards (Lay.MapToWorld)
START, STOP = (-5659.9, -1389.3), (-5193.4, -2083.7)


def _no_way_round(game, answer):  # noqa: F811
    lua, ns = game
    R, N, WG, st = ns.Router, ns.Nav, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.cityGrid, st.avoidHostile)
    st.worldGrid, st.cityGrid, st.avoidHostile = True, True, True
    WG.Set(True)
    lua.execute("AGPS_87 = UnitFactionGroup; AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    now = lua.eval("function() return os.clock() * 1000 end")
    R.Reset()
    R.SYNC_WALKS = False
    clock = [2000.0]

    def tick():
        clock[0] += 0.5
        lua.execute(f"AGPS_T = {clock[0]}")
        r = N.Route(START[0], START[1], 0)
        N.Tick()
        t1 = now()
        while R.HasWork() and now() - t1 < 15:
            res = R.Pump(now() + 4, now)
            done, fixed = res if isinstance(res, tuple) else (res, None)
            if done:
                N.SearchDone(fixed)
        return r

    lua.execute("""
      AGPS_ASKED, AGPS_NOWAY = nil, nil
      AGPS_CH, AGPS_CN = AGPS_NS.GPS.ConfirmHostile, AGPS_NS.GPS.ConfirmNoWayRound
      AGPS_NS.GPS.ConfirmHostile = function(names, side, yes, no) AGPS_ASKED = { no = no } return true end
      AGPS_NS.GPS.ConfirmNoWayRound = function(towns, yes, no)
        AGPS_NOWAY = { towns = towns, yes = yes, no = no, at = AGPS_T } return true end""")
    try:
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {START[0]}, {START[1]}, 0 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {STOP[0]}, y = {STOP[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        for _ in range(400):
            r = tick()
            if lua.eval("AGPS_ASKED"):
                break
        asked = lua.eval("AGPS_ASKED")
        assert asked is not None  # ("goes through ... (Alliance guards). Take it?")
        asked.no(True)
        no_at = clock[0]
        assert N.RiskAnswer(N.dest) is False
        for _ in range(int(2 * (N.REFUSED_SECONDS + 5))):
            tick()
            if lua.eval("AGPS_NOWAY"):
                break
        noway = lua.eval("AGPS_NOWAY")
        # (within the cap: no guard-free walk here, so asked whether to take the way past them; its searches stopped)
        assert noway is not None, "still routing %.0f s after No" % (clock[0] - no_at)
        assert noway.at - no_at <= N.REFUSED_SECONDS + 1
        assert N.paused == "guards" and not N.RideChecking() and N.guardsAsking is not None
        assert "no way around the guards" in str(N.PausedHead())
        if answer:
            noway.yes()
            assert N.paused is None and N.RiskAnswer(N.dest) is True and N.guardsAsking is None
            r = None
            for _ in range(400):
                r = tick()
                if r and not r.pending:
                    break
            assert r is not None and not r.pending and N.RouteThroughGuards(r)
            assert lua.eval("AGPS_NOWAY").at == noway.at  # (not asked again)
        else:
            noway.no(True)
            assert len(N.stops) == 0 and N.dest is None and N.paused is None
    finally:
        lua.execute("AGPS_NS.GPS.ConfirmHostile, AGPS_NS.GPS.ConfirmNoWayRound = AGPS_CH, AGPS_CN")
        N.Clear()
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        lua.execute("UnitFactionGroup = AGPS_87; AGPS_LEVEL = nil")
        st.worldGrid, st.cityGrid, st.avoidHostile = saved
        WG.Set(bool(saved[0]))


def test_no_to_take_it_with_no_way_round_asks_again_and_yes_takes_the_way_past(game):  # noqa: F811
    _no_way_round(game, True)


def test_no_to_take_it_with_no_way_round_and_no_again_clears_the_route(game):  # noqa: F811
    _no_way_round(game, False)
