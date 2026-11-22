"""The quest route's choices stick, and it can be ordered by level (1.3.13; the whole addon, gameharness).

Players' requests, relayed by Kooki3z 2026-11-21:
"Quest route to be able to go through tracked quests only. Would solve a lot of other stuff, for example when a quest is
excluded via the popup, it comes up again every time the route regenerates."
"Be able to prioritize quests by level (i.e. prefer lower level or quests that are about to turn grey)"

- A quest left out (Leave Out on the group quest question, or its stop removed from a quest route) stays out of every
  later quest route: made again by hand, by itself (questAutoReroute), by the Sprint icon, after a /reload, with no route
  in between; the question isn't asked again. Saved per character (Nav.SaveQuestChoices), let go only when the quest
  leaves the log. Put back from the directions (Put Back) or Options > Routing > Quest Route (Put Back All).
- "Only tracked quests" (questTrackedOnly, there since 1.3.10) holds on a reroute too, and a finished untracked quest
  doesn't ask for one.
- questLevelOrder: "low" (lowest level first) and "gray" (about to turn gray first) put the stops in level bands, each
  in the fastest order (Nav.QuestBands); a quest's turn-in always after its objectives.

The quest log here is a stub (C_QuestLog), its quests around Brill on Tirisfal Glades' map (1420), where the harness
player stands; Layers.QuestStops reads it as in game.
"""

import pytest

BRILL = (2254.0, 293.0)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("""
      AGPS_QL = {}
      AGPS_OLD_QL = C_QuestLog
      local function find(id) for _, q in ipairs(AGPS_QL) do if q.id == id then return q end end end
      AGPS_QL_STUB = setmetatable({
        GetNumQuestLogEntries = function() return #AGPS_QL, #AGPS_QL end,
        GetInfo = function(i) local q = AGPS_QL[i] return q and { questID = q.id, level = q.level } end,
        IsComplete = function(id) local q = find(id) return q and q.done or false end,
        IsOnQuest = function(id) return find(id) ~= nil end,
        GetTitleForQuestID = function(id) local q = find(id) return q and q.title end,
        GetQuestsOnMap = function(m)
          local out = {}
          if m ~= 1420 then return out end
          for _, q in ipairs(AGPS_QL) do if q.u then out[#out + 1] = { questID = q.id, x = q.u, y = q.v } end end
          return out
        end,
        GetNextWaypoint = function() end,
        GetQuestWatchType = function(id) local q = find(id) if q and q.tracked then return 0 end end,
        GetQuestDifficultyLevel = function(id) local q = find(id) return q and q.level end,
        GetQuestTagInfo = function(id)
          local q = find(id)
          if q and q.elite then return { isElite = true, tagName = "Elite" } end
        end,
        GetLogIndexForQuestID = function(id) for i, q in ipairs(AGPS_QL) do if q.id == id then return i end end end,
        GetQuestObjectives = function() return {} end,
      }, { __index = AGPS_OLD_QL })
    """)
    return lua, ns


def _uv(ns, x, y):
    b = ns.Maps[1420].bounds
    return (b[4] - y) / (b[4] - b[2]), (b[3] - x) / (b[3] - b[1])


@pytest.fixture
def quests(game):
    """quests(*q): the quest log, each q a dict: id, title, dx/dy (yards from Brill; none: no place), level, done,
    tracked, elite. Chat is kept (quests.said()); every choice and setting put back afterward."""
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    was = (st.questTrackedOnly, st.questAutoReroute, st.questLevelOrder, st.questZoneOnly, ns.db.questAutoAsked, ns.Print,
           st.questTurninsOnly, st.questObjectivesOnly)
    lua.execute("C_QuestLog = AGPS_QL_STUB AGPS_SAID = {}")
    ns.Print = lua.eval("function(m) AGPS_SAID[#AGPS_SAID + 1] = m end")
    st.questTrackedOnly = st.questAutoReroute = st.questZoneOnly = st.questTurninsOnly = st.questObjectivesOnly = False
    st.questLevelOrder = "off"
    N.Clear()
    G.groupChoice = lua.eval("{}")
    N.questDropped = lua.eval("{}")

    def set_log(*qs):
        rows = []
        for q in qs:
            fields = [f"id = {q['id']}", f"title = {q['title']!r}", f"level = {q.get('level', 12)}"]
            if "dx" in q:
                u, v = _uv(ns, BRILL[0] + q["dx"], BRILL[1] + q.get("dy", 0))
                fields += [f"u = {u}", f"v = {v}"]
            for k in ("done", "tracked", "elite"):
                if q.get(k):
                    fields.append(f"{k} = true")
            rows.append("{ " + ", ".join(fields) + " }")
        lua.execute("AGPS_QL = { " + ", ".join(rows) + " }")

    set_log.said = lambda: [str(m) for m in lua.eval("AGPS_SAID").values()]
    yield set_log
    lua.execute("C_QuestLog = AGPS_OLD_QL AGPS_QL = {}")
    (st.questTrackedOnly, st.questAutoReroute, st.questLevelOrder, st.questZoneOnly, ns.db.questAutoAsked,
     ns.Print, st.questTurninsOnly, st.questObjectivesOnly) = was
    N.Clear()
    G.groupChoice = lua.eval("{}")
    N.questDropped = lua.eval("{}")
    N.SaveQuestChoices()
    G.groupQuests = lua.eval("{}")
    if G.askBox is not None:  # (made by the first question: a test run alone may have asked none)
        G.askBox._shown = False
    G.autoQuestPending, N.questRouteStale = None, None


def _names(ns):
    N = ns.Nav
    return sorted(str(N.stops[i].name) for i in range(1, len(N.stops) + 1))


def _order(ns):
    N = ns.Nav
    return [str(N.stops[i].name) for i in range(1, len(N.stops) + 1)]


def _reroute_every_way(lua, ns):
    """The quest route made again each way there is: the button, by itself (the option on), the Sprint icon. Yields
    the stops after each."""
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    G.QuestRoute()
    yield "button"
    st.questAutoReroute = True
    N.MarkQuestRouteStale()
    G.autoQuestPending = None
    G.AutoQuestTick()
    yield "by itself"
    st.questAutoReroute = False
    ns.db.questAutoAsked = True
    G.QuestRerouteClick()
    yield "Sprint icon"


def _reload(lua, ns):
    """A /reload: the session's memory gone, the saved character's read back."""
    G, N = ns.GPS, ns.Nav
    G.groupChoice = lua.eval("{}")
    N.questDropped = lua.eval("{}")
    N.Restore()


def _directions_rows(lua, ns):
    G = ns.GPS
    G.Follow()
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Redraw()
    G.Update()
    return [(str(r.text._text), str(r.button.label._text), r.button)
            for r in (G.groupRows or lua.table()).values() if r._shown]


def test_a_quest_left_out_on_the_question_stays_out_until_put_back(game, quests):
    lua, ns = game
    G, N, O = ns.GPS, ns.Nav, ns.Options
    quests({"id": 501, "title": "Wolves", "dx": 60}, {"id": 502, "title": "Ogre Mound", "dx": 120, "elite": True})
    G.QuestRoute()
    assert G.askBox._shown and "Ogre Mound" in G.askBox.text._text
    G.askBox.no._scripts.OnClick(G.askBox.no)  # (Leave Out)
    assert _names(ns) == ["Wolves"]
    # every way the quest route is made again: not asked, still out
    for how in _reroute_every_way(lua, ns):
        assert not G.askBox._shown, how
        assert _names(ns) == ["Wolves"], how
    # saved per character, with or without a route; a /reload keeps it
    assert ns.CharDB().groupChoice[502] == "leave"
    N.Clear()
    assert ns.CharDB().groupChoice[502] == "leave"
    _reload(lua, ns)
    assert G.groupChoice[502] == "leave"
    G.QuestRoute()
    assert not G.askBox._shown and _names(ns) == ["Wolves"]
    # Options > Routing > Quest Route lists it; Put Back All puts it back, kept and not asked again
    ns.Options.Show()
    O.Refresh()
    assert "Ogre Mound" in str(O.questLeftOutText._text) and O.questPutBackAll._enabled is not False
    O.questPutBackAll._scripts.OnClick(O.questPutBackAll)
    O.Refresh()
    assert "No quests are left out" in str(O.questLeftOutText._text)
    assert G.groupChoice[502] == "keep"
    G.QuestRoute()
    assert not G.askBox._shown and _names(ns) == ["Ogre Mound", "Wolves"]
    _reload(lua, ns)
    G.QuestRoute()
    assert not G.askBox._shown and _names(ns) == ["Ogre Mound", "Wolves"]  # (kept: asked once per quest)


def test_a_quest_whose_stop_was_removed_stays_out_and_comes_back_with_put_back(game, quests):
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    quests({"id": 511, "title": "Wolves", "dx": 60}, {"id": 512, "title": "Boars", "dx": 120})
    G.QuestRoute()
    assert _names(ns) == ["Boars", "Wolves"]
    i = next(k for k in range(1, len(N.stops) + 1) if N.stops[k].quest == 512)
    N.RemoveStop(i)
    assert any("Boars stays out of your quest routes" in m and "Options > Routing > Quest Route" in m
               for m in quests.said())
    for how in _reroute_every_way(lua, ns):
        assert _names(ns) == ["Wolves"], how
    # its spot moved on (its next objective, elsewhere): still out
    lua.execute("AGPS_QL[2].u, AGPS_QL[2].v = AGPS_QL[1].u + 0.01, AGPS_QL[1].v")
    N.Clear()
    _reload(lua, ns)
    G.QuestRoute()
    assert _names(ns) == ["Wolves"]
    # the directions: a row for it with Put Back
    rows = _directions_rows(lua, ns)
    (row,) = [r for r in rows if "Boars" in r[0]]
    assert "Left out:" in row[0] and row[1] == "Put Back"
    row[2]._scripts.OnClick(row[2])
    assert _names(ns) == ["Boars", "Wolves"] and not N.QuestLeftOut(512)


def test_a_choice_is_let_go_once_its_quest_leaves_the_log(game, quests):
    # (keep data forever: nothing the player chose is pruned by itself; a choice about a quest no longer in the log is
    # moot, and the quest picked up again is asked about afresh)
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    quests({"id": 521, "title": "Wolves", "dx": 60}, {"id": 522, "title": "Ogre Mound", "dx": 120, "elite": True},
           {"id": 523, "title": "Boars", "dx": 180})
    G.groupChoice[522] = "leave"
    N.questDropped = lua.eval("{ { quest = 523, name = 'Boars' } }")
    N.SaveQuestChoices()
    # turned in (QUEST_TURNED_IN / QUEST_REMOVED)
    N.OnQuestGone(523, "Boars")
    assert not N.QuestLeftOut(523) and ns.CharDB().questDropped is None
    # abandoned while not watched: gone from the log at the next quest route
    lua.execute("table.remove(AGPS_QL, 2)")
    G.QuestRoute()
    assert G.groupChoice[522] is None and ns.CharDB().groupChoice is None
    # an empty log (not sent yet at login) isn't taken as every quest gone
    G.groupChoice[521] = "leave"
    N.ForgetGoneQuests(lua.eval("{}"))
    assert G.groupChoice[521] == "leave"


def test_only_tracked_quests_holds_on_a_reroute(game, quests):
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    st.questTrackedOnly = True
    quests({"id": 531, "title": "Wolves", "dx": 60, "tracked": True}, {"id": 532, "title": "Boars", "dx": 120})
    G.QuestRoute()
    assert _names(ns) == ["Wolves"]
    # a tracked quest picked up: in on every remake; the untracked one never
    lua.execute("AGPS_QL[3] = { id = 533, title = 'Spiders', level = 12, tracked = true, u = AGPS_QL[1].u, "
                "v = AGPS_QL[1].v + 0.005 }")
    for how in _reroute_every_way(lua, ns):
        assert _names(ns) == ["Spiders", "Wolves"], how
    # an untracked quest finished: no reroute asked for (its turn-in wouldn't be taken)
    N.questRouteStale = None
    N.CheckQuestsDone(lua.eval("{ 531, 532, 533 }"), True)
    lua.execute("AGPS_QL[2].done = true")
    assert N.CheckQuestsDone(lua.eval("{ 531, 532, 533 }")) is None and not N.questRouteStale
    # a tracked one finished: asked for
    lua.execute("AGPS_QL[1].done = true")
    assert N.CheckQuestsDone(lua.eval("{ 531, 532, 533 }")) == 531 and N.questRouteStale


def _stops(lua, *qs):
    """Quest route stops along a line north of Brill: each (name, quest, yards out, turnin)."""
    rows = []
    for name, q, yd, turnin in qs:
        rows.append(f"{{ x = {BRILL[0] + yd}, y = {BRILL[1]}, cont = 0, name = {name!r}, questRoute = true, "
                    f"quest = {q}{', turnin = true' if turnin else ''} }}")
    return lua.eval("{ " + ", ".join(rows) + " }")


def test_lowest_level_first_puts_the_low_quests_first_in_bands(game, quests):
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    quests({"id": 541, "title": "A", "level": 10}, {"id": 542, "title": "B", "level": 14},
           {"id": 543, "title": "C", "level": 14}, {"id": 544, "title": "D", "level": 11})
    stops = lambda: _stops(lua, ("B", 542, 60, False), ("C", 543, 120, False), ("A", 541, 240, False),
                           ("D", 544, 300, False))
    # off: the fastest order, nearest first
    N.SetStops(stops(), True)
    assert _order(ns)[:2] == ["B", "C"]
    # lowest first: levels 10-12 (A, D) before 13-15 (B, C), each band in the fastest order
    st.questLevelOrder = "low"
    N.SetStops(stops(), True)
    assert _order(ns) == ["A", "D", "C", "B"]
    assert ns.Nav.QuestBands(N.stops) is not None


def test_about_to_turn_gray_first(game, quests):
    lua, ns = game
    N, st, L = ns.Nav, ns.settings.gps, ns.Layers
    lua.execute("AGPS_LEVEL = 14")  # (gray at 8 and below: Classic's green range at 14 is 5)
    try:
        assert L.QuestGrayLevel() == 8
        lua.execute("GetQuestGreenRange = function() return 4 end")
        assert L.QuestGrayLevel() == 9
        lua.execute("GetQuestGreenRange = nil")
        quests({"id": 551, "title": "Gray", "level": 8}, {"id": 552, "title": "Yellow", "level": 14},
               {"id": 553, "title": "Soon", "level": 10}, {"id": 554, "title": "Sooner", "level": 9})
        st.questLevelOrder = "gray"
        N.SetStops(_stops(lua, ("Gray", 551, 60, False), ("Yellow", 552, 120, False), ("Soon", 553, 240, False),
                          ("Sooner", 554, 300, False)), True)
        # the two turning gray within two levels first; the gray one and the yellow one after, fastest
        assert sorted(_order(ns)[:2]) == ["Soon", "Sooner"]
    finally:
        lua.execute("AGPS_LEVEL = nil GetQuestGreenRange = nil")


def test_a_level_up_sorts_a_quest_route_by_level_again(game, quests):
    """Kooki3z 2026-11-21: on a level-up the quest route by level is put in order again (the gray bands move)."""
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    was_fastest = st.fastestOrder
    lua.execute("AGPS_LEVEL = 14")
    try:
        st.fastestOrder = True
        quests({"id": 571, "title": "Gray", "level": 8}, {"id": 572, "title": "Yellow", "level": 14},
               {"id": 573, "title": "Soon", "level": 10}, {"id": 574, "title": "Sooner", "level": 9})
        stops = lambda: _stops(lua, ("Gray", 571, 60, False), ("Yellow", 572, 120, False),
                               ("Soon", 573, 240, False), ("Sooner", 574, 300, False))
        # off: a level-up changes nothing
        N.SetStops(stops(), True)
        N.reorderDue = None
        assert not N.OnLevelUp() and not N.reorderDue
        st.questLevelOrder = "gray"
        N.SetStops(stops(), True)
        assert sorted(_order(ns)[:2]) == ["Soon", "Sooner"]
        # level 18: gray at 12 and below, so the level 14 quest turns gray within two levels now and goes first
        lua.execute("AGPS_LEVEL = 18")
        N.reorderDue = None
        assert N.OnLevelUp() and N.reorderDue
        N.MaybeReorder(BRILL[0], BRILL[1], 0)
        assert _order(ns)[0] == "Yellow"
    finally:
        st.fastestOrder = was_fastest
        lua.execute("AGPS_LEVEL = nil")


@pytest.mark.parametrize("mode", ["off", "low"])
def test_a_quests_turn_in_comes_after_its_objectives(game, quests, mode):
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    st.questLevelOrder = mode
    quests({"id": 561, "title": "Letter", "level": 12}, {"id": 562, "title": "Wolves", "level": 12})
    N.SetStops(_stops(lua, ("Turn in: Letter", 561, 40, True), ("Wolves", 562, 120, False),
                      ("Letter", 561, 300, False)), True)
    order = _order(ns)
    assert order.index("Letter") < order.index("Turn in: Letter")


def test_the_quest_route_buttons_tooltip_says_where_its_options_are(game):
    lua, ns = game
    L = lua.globals().AGPS_NS.L
    key = "Only tracked quests, lowest level first, quests left out: Options > Routing > Quest Route."
    src = (__import__("pathlib").Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "GPSFrame.lua")
    assert key in src.read_text(encoding="utf-8") and L[key] == key
