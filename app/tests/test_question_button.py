"""A question waiting: a glowing "?" by the minimap's logo (item 54, Kooki3z 2026-11-24): the enemy ground's "Take it?"
asked on the map with the map closed wasn't seen. Shown while AzerothGPS waits on an answer, with the logo's gold glow;
a click opens the map and brings the question up; both go once it's answered."""

from test_map_redraw import game, minimap  # noqa: F401


def test_an_enemy_ground_question_raises_the_button_and_answering_clears_it(minimap):  # noqa: F811
    lua, ns = minimap
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    st.replaceMinimap = True
    G.ApplySettings()
    N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
    assert G.MinimapMode()
    r, watch = G.mmAsk, G.mmAskWatch
    assert r is not None and not r._shown
    answered = []
    try:
        # (asked with the map out, then the map back in the square: the question on it, hidden with it)
        G.SetMinimapExpanded(True)
        G.ConfirmHostile(lua.table("Kharanos"), "H", lambda *a: answered.append("yes"), lambda *a: answered.append("no"))
        G.SetMinimapExpanded(False)
        assert G.PendingQuestion() is not None
        watch._scripts.OnUpdate(watch, 1)
        assert r._shown and r.glow._shown and G.mmButton.agpsAskGlow._shown
        lua.execute("AGPS_T = AGPS_T + 0.1")
        watch._scripts.OnUpdate(watch, 0.01)
        assert abs(r.glow._alpha - G.GlowAlpha()) < 1e-9  # (pulsing as the Resume button's)
        r._scripts.OnEnter(r)
        assert str(lua.eval("GameTooltip._text")) == "A question is waiting: click to answer"
        # (above the logo, its top middle: item 58)
        p = r._pts.BOTTOM
        assert p[3] == "TOP" and p[4] == 0 and p[5] < 0
        # (a click: the map out of the square, the question with it; showing: no "?", no glow, item 58)
        r._scripts.OnClick(r, "LeftButton")
        assert G.mmState.expanded
        watch._scripts.OnUpdate(watch, 1)
        assert not r._shown and not G.mmButton.agpsAskGlow._shown
        # (closed again unanswered: back, glowing)
        G.SetMinimapExpanded(False)
        watch._scripts.OnUpdate(watch, 1)
        assert r._shown and r.glow._shown and G.mmButton.agpsAskGlow._shown
        G.SetMinimapExpanded(True)
        box = G.PendingQuestion()
        box.yes._scripts.OnClick(box.yes, "LeftButton")
        assert answered == ["yes"] and G.PendingQuestion() is None
        watch._scripts.OnUpdate(watch, 1)
        assert not r._shown and not G.mmButton.agpsAskGlow._shown
    finally:
        if G.mmState.expanded:
            G.SetMinimapExpanded(False)
        N.Clear()


# The game sends OnHide to a shown frame's shown children as it hides (and OnShow as it shows): the stand-in's frames
# don't, so the question's holder is made to here.
_GAME_HIDE = """function(h)
  local function Each(f, script)
    for _, k in ipairs(f._kids or {}) do
      if k._shown then
        local s = k._scripts[script]
        if s then s(k) end
        Each(k, script)
      end
    end
  end
  local function Set(s, on)
    on = on and true or false
    if s._shown == on then return end
    s._shown = on
    Each(s, on and "OnShow" or "OnHide")
  end
  h.SetShown = Set
  h.Hide = function(s) Set(s, false) end
  h.Show = function(s) Set(s, true) end
end"""


def _ask_kinds(lua, G):
    return [
        ("Take it?", lambda yes, no: G.ConfirmHostile(lua.table("Kharanos"), "H", yes, no)),
        ("a zone too high", lambda yes, no: G.ConfirmRedZone(lua.eval("{ { 'Dustwallow Marsh', 35, 45 } }"),
                                                              lua.eval("{ { name = 'That stop' } }"), yes)),
        ("Keep this route?", lambda yes, no: G.Confirm("Keep this route?", yes, no)),
        ("no way around the guards", lambda yes, no: G.ConfirmNoWayRound("Dun Algaz", yes, no)),
    ]


def test_every_question_on_the_map_closed_unanswered_keeps_waiting_with_the_question_mark(minimap):  # noqa: F811
    """Kooki3z on 6195a75c: "Routing paused: no way around the guards found" with no "?" over the logo. The question was
    on the map; the map closed, the game hid it with its holder (OnHide), which let it go as unanswered."""
    lua, ns = minimap
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    st.replaceMinimap = True
    G.ApplySettings()
    N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
    assert G.MinimapMode()
    lua.eval(_GAME_HIDE)(G.AskHolder())
    r, watch = G.mmAsk, G.mmAskWatch
    try:
        for what, ask in _ask_kinds(lua, G):
            answers = []
            G.SetMinimapExpanded(True)
            ask(lambda *a: answers.append("yes"), lambda *a: answers.append(("no",) + tuple(a)))
            box = G.PendingQuestion()
            assert type(box) is not bool and G.ShownUp(box), what
            # (the map closed unanswered: the question kept, not taken as No; the "?" and the logo's glow)
            G.SetMinimapExpanded(False)
            G.SyncAskHolder()
            assert not G.askHolder._shown and answers == [] and not box.answered, what
            assert lua.eval("rawequal")(G.PendingQuestion(), box) and G.AskWanted(), what
            watch._scripts.OnUpdate(watch, 1)
            assert r._shown and G.mmButton.agpsAskGlow._shown, what
            # (the "?" clicked: the map open, the question on it; answered, both gone)
            r._scripts.OnClick(r, "LeftButton")
            assert G.mmState.expanded and G.ShownUp(box), what
            box.yes._scripts.OnClick(box.yes, "LeftButton")
            assert answers == ["yes"] and G.PendingQuestion() is None, what
            G.SetMinimapExpanded(False)
            watch._scripts.OnUpdate(watch, 1)
            assert not r._shown and not G.mmButton.agpsAskGlow._shown, what
    finally:
        if G.mmState.expanded:
            G.SetMinimapExpanded(False)
        N.Clear()


def test_paused_for_the_guards_with_the_question_let_go_shows_the_question_mark_and_asks_again(minimap):  # noqa: F811
    """Routing paused ("no way around the guards found") with its question closed by its close button: the "?" still
    glows over the logo, and a click opens the map and asks again."""
    lua, ns = minimap
    G, st, N = ns.GPS, ns.settings.gps, ns.Nav
    st.replaceMinimap = True
    G.ApplySettings()
    N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0, name = 'stop' } }"), False, "red")
    r, watch = G.mmAsk, G.mmAskWatch
    try:
        assert G.MinimapMode() and G.PendingQuestion() is None
        N.SetPaused(True, "guards")
        assert G.AskWanted()
        watch._scripts.OnUpdate(watch, 1)
        assert r._shown and G.mmButton.agpsAskGlow._shown
        r._scripts.OnClick(r, "LeftButton")
        box = G.PendingQuestion()
        assert G.mmState.expanded and type(box) is not bool and G.ShownUp(box)
        assert "Take the way past them?" in str(box.text._text) and N.guardsAsking is not None
        # (No: the route cleared, nothing waiting)
        box.no._scripts.OnClick(box.no, "LeftButton")
        assert N.dest is None and N.paused is None and G.PendingQuestion() is None
    finally:
        if G.mmState.expanded:
            G.SetMinimapExpanded(False)
        N.SetPaused(False)
        N.Clear()
