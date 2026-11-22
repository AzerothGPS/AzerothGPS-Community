"""The in-game tutorial (Tutorial.lua, 1.2.0; asked 2026-11-09): when it's offered, every section run from start to
finish with the player's actions simulated (and with every step skipped), in English, German and Chinese; leaving at
any step puts everything back exactly as the player had it; a /reload in the middle restores from the saved snapshot;
the example herbs and ore, the practice roads, walls and recorded walks never reach the saved variables; combat hides
it and it goes on after; "Keep the GPS map as your minimap?" Yes keeps only that; Options > Help lists every section
and Play starts it; docs/tutorial-1.2.0.md has every step's text."""

from pathlib import Path

import pytest

from test_map_redraw import MM_SETUP

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = ["minimap", "route", "quests", "arrow", "gather", "pins", "search", "dungeon", "window"]  # (roads: gone, 1.3.14)

# The player's side of the test, in Lua: a canonical text of any table (to compare before and after), the saved
# variables as the game would write them, and what the player does at each step that waits for them.
SETUP = MM_SETUP + r"""
  AzerothGPSFrame.SetFrameStrata = function(s, v) s._strata = v end
  Minimap.SetAlpha = function(s, a) s._alpha = a end
  IsPlayerMoving = function() return AGPS_MOVING == true end
  AGPS_PRINTS = {}
  AGPS_REAL_PRINT = AGPS_NS.Print
  AGPS_NS.Print = function(...) AGPS_PRINTS[#AGPS_PRINTS + 1] = tostring((...)) end
  -- (an empty table, or one of empty tables, is as good as none: the addon makes its lists as it first looks at them)
  local function Empty(x)
    if type(x) ~= "table" then return false end
    for _, v in pairs(x) do
      if not Empty(v) then return false end
    end
    return true
  end
  local function Text(v, skip, depth)
    local t = type(v)
    if t ~= "table" then return t == "string" and string.format("%q", v) or tostring(v) end
    local keys = {}
    for k, x in pairs(v) do
      if not Empty(x) and not (depth == 0 and skip and skip[k]) then keys[#keys + 1] = k end
    end
    table.sort(keys, function(a, b) return type(a) .. tostring(a) < type(b) .. tostring(b) end)
    local out = {}
    for _, k in ipairs(keys) do out[#out + 1] = "[" .. Text(k, nil, 1) .. "]=" .. Text(v[k], nil, 1) end
    return "{" .. table.concat(out, ",") .. "}"
  end
  function AGPS_DUMP(v, skip) return Text(v, skip, 0) end
  -- the saved variables, all but the tutorial's own record
  function AGPS_DB() return Text(AzerothGPSDB, { tutorial = true }, 0) end
  -- what's live and not saved: the route, the stops waiting, the view, the minimap, the tools, the demo things
  function AGPS_LIVE()
    local ns = AGPS_NS
    local G, N, R, T = ns.GPS, ns.Nav, ns.Record, ns.Tutorial
    local v = G.SaveView()
    if v then v.t = nil end
    local stops = {}
    for i, d in ipairs(N.stops) do
      stops[i] = { d.x, d.y, d.cont, d.name, d.icon, d.tex, d.z, d.quest }
    end
    local quick = {} -- (the quick buttons: which show, and where each is put)
    for _, t in ipairs(G.QUICK) do
      if t.button then quick[t.id] = tostring(t.button:IsShown()) .. " " .. tostring(G.QuickPlace(t.id)) end
    end
    return Text({ stops = stops, loop = N.loop, pending = G.PendingStops(), view = v or false,
      mmOn = G.mmState.on, mmExpanded = G.mmState.expanded or false, mmHold = G.mmHold or false,
      road = G.roadMode or false, wall = G.wallMode or false, draw = G.drawMode or false,
      rec = R.rec ~= nil, practice = R.practice ~= nil, demo = ns.Layers.demoNodes ~= nil,
      overlay = G.overlays[T.OVERLAY] ~= nil, search = G.searchPanel:IsShown(), quick = quick,
      frame = { AzerothGPSFrame._w, AzerothGPSFrame._h, AzerothGPSFrame._shown } }, nil, 0)
  end
  function AGPS_SAVED()
    local function Lit(v)
      local t = type(v)
      if t == "string" then return string.format("%q", v) end
      if t == "number" then
        if v == math.floor(v) and math.abs(v) < 1e15 then return string.format("%d", v) end
        return string.format("%.17g", v)
      end
      if t ~= "table" then return tostring(v) end
      local out = {}
      for k, x in pairs(v) do out[#out + 1] = "[" .. Lit(k) .. "]=" .. Lit(x) end
      return "{" .. table.concat(out, ",") .. "}"
    end
    return "AzerothGPSDB = " .. Lit(AzerothGPSDB)
  end

  local function Click(b, button)
    local fn = b:GetScript("OnClick")
    assert(fn, "nothing to click")
    fn(b, button or "LeftButton")
  end
  AGPS_CLICK = Click
  local function Quick(id)
    local grp = AGPS_NS.GPS.groupOf and AGPS_NS.GPS.groupOf[id]
    if grp then return grp.button end
    for _, t in ipairs(AGPS_NS.GPS.QUICK) do
      if t.id == id then return t.button end
    end
  end
  local function Stroke(wall)
    local ns = AGPS_NS
    local x, y, level = ns.Tutorial.Here()
    ns.GPS.FinishRoad({ cont = level, pts = { x + 10, y, x + 40, y + 5, x + 70, y + 10 } }, false, wall)
  end
  -- (the action for the step showing)
  function AGPS_ACT_FOR(sec, si, title)
    local acts = AGPS_ACT[sec]
    if not acts then return nil end
    if acts.byTitle then
      for k, fn in pairs(acts.byTitle) do
        if AGPS_NS.L[k] == title then return fn end
      end
      return nil
    end
    return acts[si]
  end
  -- what the player does at a step that waits: [section][step]
  AGPS_ACT = {
    minimap = {
      [2] = function(ns) Click(ns.GPS.mmButton) end,
      [3] = function(ns) -- (left alone: it goes back by itself; or its arrow, the same call)
        ns.GPS.MinimapTick(1)
        ns.GPS.SetMinimapExpanded(false)
      end,
      [7] = function(ns) ns.GPS.OpenOptions() end, -- (the logo's right-click)
      [4] = function(ns)
        ns.GPS.MinimapTick(1) -- (opened out: the animation over, standing still)
        AGPS_MOVING = true
        ns.GPS.MinimapTick(0.1)
        ns.GPS.MinimapTick(1)
        AGPS_MOVING = nil
      end,
    },
    route = {
      [1] = function(ns) ns.GPS.Update() ns.GPS.AddPending(40, 30) end,
      [2] = function(ns) Click(ns.GPS.routeButton) end,
      [3] = function(ns)
        ns.GPS.Update()
        ns.GPS.AddPending(-60, 20)
        ns.GPS.AddPending(10, -70)
      end,
      [4] = function(ns) ns.Nav.RemoveStop(1) end, -- (a stop's marker right-clicked)
      [6] = function(ns) Click(ns.GPS.navCancel) end, -- (the directions' X)
    },
    gather = {
      [3] = function(ns) Click(Quick("farm")) end,
      [4] = function(ns)
        local G = ns.GPS
        local x, y, level = ns.Tutorial.Here()
        G.lasso = { cont = level, pts = { x + 150, y + 150, x + 150, y - 150, x - 150, y - 150, x - 150, y + 150 } }
        G.FinishDrawing()
      end,
    },
    pins = {
      [1] = function(ns) -- (Shift + click on the map, then its Create Pin button: the pin's window for that spot)
        local x, y, level = ns.Tutorial.Here()
        ns.Pins.OpenEditor({ level = level, x = x + 50, y = y + 50, floors = {}, pick = 0 })
      end,
      [2] = function(ns)
        AzerothGPSPinDialog.name:SetText("Fishing spot")
        ns.Pins.Confirm()
      end,
      [3] = function(ns) ns.GPS.Update() ns.GPS.AddPending(50, 50) end, -- (the pin double-clicked)
      [4] = function(ns)
        local box = ns.GPS.searchPanel.box
        box:SetText("fishing spot")
        box:GetScript("OnTextChanged")(box, true)
      end,
    },
    search = {
      [1] = function(ns) Click(ns.GPS.searchButton) end,
      [2] = function(ns)
        local box = ns.GPS.searchPanel.box
        box:SetText(ns.L["class trainer"])
        box:GetScript("OnTextChanged")(box, true)
      end,
      [3] = function(ns)
        local box = ns.GPS.searchPanel.box
        box:GetScript("OnEnterPressed")(box)
      end,
    },
    arrow = {
      [2] = function(ns)
        local st = ns.settings.gps
        local p = st.dirPoint
        st.dirPoint = { p[1], p[2], p[3], (p[4] or 0) + 37, (p[5] or 0) - 12 } -- (as its OnDragStop saves it)
        ns.Arrow.Apply()
      end,
      [3] = function(ns)
        local f = ns.Arrow.frame
        f:GetScript("OnDragStart")(f)
        f:GetScript("OnDragStop")(f)
      end,
    },
    -- (by the step's English title: "Bring it back" is left out with the map as the minimap, so their numbers move)
    window = { byTitle = {
      ["Hide the map"] = function(ns) ns.GPS.SetMinimized(true) end, -- (the logo's double-click)
      ["Bring it back"] = function(ns)
        local b = ns.GPS.miniIcon
        b:GetScript("OnDoubleClick")(b, "LeftButton")
      end,
      ["Resize it"] = function(ns) -- (the corner dragged: as its OnUpdate sets it)
        local st = ns.settings.gps
        st.size = st.size + 40
        ns.GPS.ApplySettings()
      end,
      ["Any shape"] = function(ns)
        local st = ns.settings.gps
        st.width = st.size + 120
        ns.GPS.ApplySettings()
      end,
    } },
    roads = {
      [2] = function(ns)
        Click(Quick("mapEdit"))
        Click(Quick("roadTools"))
      end,
      [3] = function(ns) Stroke(false) end,
      [4] = function(ns) -- (the magic eraser over the practice road)
        Click(Quick("magicEraser"))
        local _, _, level = ns.Tutorial.Here()
        ns.Record.Restore("road", level, function() return true end)
      end,
      [5] = function(ns)
        Click(Quick("wallTools"))
        Stroke(true)
      end,
      [6] = function(ns)
        local R = ns.Record
        Click(Quick("roadRecord"))
        Click(R.window.rec)
        for _ = 1, 6 do
          AGPS_POS[1] = AGPS_POS[1] + 1.5
          AGPS_T = AGPS_T + 0.2
          R.RecordTick(AGPS_T)
        end
      end,
      [7] = function(ns) Click(ns.Record.window.stop) end,
    },
  }
"""


def _start(locale=None, saved=None):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale=locale, saved=saved)
    ns.Nav.FUN = False
    lua.execute(SETUP)
    ns.Tutorial.DONE_PAUSE = 0  # (the next step at once, not after "Done!")
    # (1.3.10: the setup, once for everyone, comes before the offer, Setup.lua; taken as seen here: the order is
    # test_setup.py's)
    ns.db.setup.shown = ns.Setup.VERSION
    return lua, ns


@pytest.fixture(scope="module")
def game():
    return _start()


@pytest.fixture
def tut(game):
    """(lua, ns) with no tutorial running and none ever offered; the same again after."""
    lua, ns = game
    _reset(lua, ns)
    yield lua, ns
    _reset(lua, ns)


def _reset(lua, ns):
    T = ns.Tutorial
    lua.execute("InCombatLockdown = function() return false end AGPS_NS.inCombat = false AGPS_MOVING = nil")
    if T.run:
        T.Exit()
    if T.prompt:
        T.answered = True
        T.prompt.Hide(T.prompt)
    lua.execute("""
      local ns = AGPS_NS
      local T = ns.Tutorial
      T.run, T.prompted, T.resume, T.panelMoved = nil, nil, nil, nil
      ns.db.tutorial = { seen = {}, ask = true, declined = 0, fresh = true }
      -- (1.3.10: a first install's tips in the route panel stand in for the offer, Setup.lua; off here, the offer's
      -- own tests: test_setup.py has the first install's path)
      ns.db.tips = {}
      ns.db.setup.shown = ns.Setup.VERSION
      ns.Nav.Clear()
      ns.GPS.PendingStops({})
      ns.GPS.Follow()
      AGPS_POS = { 2254.0, 293.0, 0 }
      AGPS_PRINTS = {}
    """)
    T.DONE_PAUSE = 0


def _ok(result):
    """T.Start's first value (true alone, or false with why)."""
    return result[0] if isinstance(result, tuple) else result


def _state(lua):
    lua.execute("AGPS_T = AGPS_T + 1")
    return lua.eval("AGPS_DB()"), lua.eval("AGPS_LIVE()")


def _diff(a, b):
    """Where two canonical texts first differ (for a failed comparison's message)."""
    if a == b:
        return None
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return f"...{a[max(0, i - 150):i + 100]}...  !=  ...{b[max(0, i - 150):i + 100]}..."


def _where(ns):
    run = ns.Tutorial.run
    if not run:
        return None
    if run.card:
        return "card"
    return run.section.id, run.si


def _step(lua, ns, act=True):
    """One step taken: the player's action where the step waits for one (`act`), else Skip Step / Next. The map drawn
    with it, nothing failing."""
    T = ns.Tutorial
    run = T.run
    sec, si = run.section.id, run.si
    assert run.error is None, (sec, si, run.error)
    ns.GPS.Update()
    T.Tick()
    assert _where(ns) == (sec, si), f"{sec} {si} went on by itself"
    did = lua.eval("AGPS_ACT_FOR")(sec, si, run.step.title)
    waits = bool(T.Waits(run))
    if act and did and not run.blocked:
        assert waits, (sec, si)
        did(ns)
        ns.GPS.Update()
        T.Tick()
        assert _where(ns) != (sec, si), f"{sec} {si}: the player's action wasn't noticed"
    else:
        assert str(T.panel.next._text) == str(ns.L["Skip Step"] if waits else ns.L["Next"])
        T.NextClicked()
        assert _where(ns) != (sec, si)
    return sec, si, waits


def _play(lua, ns, act=True):
    """The tutorial running played to its closing card; the steps taken."""
    taken = []
    for _ in range(200):
        if _where(ns) == "card":
            return taken
        taken.append(_step(lua, ns, act))
    raise AssertionError("the tutorial never ended")


# ---------------------------------------------------------------- when it's offered

def test_a_first_install_is_offered_the_whole_tutorial(tut):
    lua, ns = tut
    T = ns.Tutorial
    assert [s.id for s in T.SECTIONS.values()] == SECTIONS
    assert all(s.version == "1.2.0" for s in T.SECTIONS.values()) and T.Newest() == "1.2.0"
    due, ids = T.PromptDue()
    assert due is True and list(ids.values()) == SECTIONS
    assert T.MaybePrompt() is True
    f = T.prompt
    assert f._shown and f._text == "" and str(f.text._text).startswith("Take a short tutorial?")
    assert [str(b._text) for b in (f.start, f.later, f.never)] == ["Start Tutorial", "Not Now", "Don't Ask Again"]
    assert T.MaybePrompt() is False  # (once a session)
    lua.globals().AGPS_CLICK(f.start)
    assert f._shown is False and _where(ns) == ("minimap", 1) and list(T.run.queue.values()) == SECTIONS
    assert ns.db.tutorial.offered == "1.2.0"
    T.Exit()
    T.prompted = None
    assert T.PromptDue() is False and T.MaybePrompt() is False  # (taken up: not offered again)


def test_the_window_says_welcome_at_a_first_install_and_whats_new_after_an_update():
    # a first install: no saved variables at all; an update: saved variables from before the tutorial
    lua, ns = _start()
    assert ns.db.tutorial.fresh is True and ns.db.tutorial.ask is True and ns.db.tutorial.declined == 0
    ns.Tutorial.ShowPrompt(ns.Tutorial.NewSections())
    title = lua.eval("AGPS_NS.Tutorial.prompt.chrome and 'chrome' or 'plain'")
    texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text]
    assert "Welcome to AzerothGPS" in texts, title
    lua, ns = _start(saved='AzerothGPSDB = { settings = { gps = { size = 400 } }, chars = {} }')
    T = ns.Tutorial
    assert ns.db.tutorial.fresh is None and ns.settings.gps.size == 400  # (older saved data: loads as it was)
    due, ids = T.PromptDue()
    assert due is True and list(ids.values()) == SECTIONS  # (for 1.2.0 every section is new)
    T.ShowPrompt(ids)
    texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text]
    assert "What's new in 1.2.0" in texts and "Welcome to AzerothGPS" not in texts
    assert str(T.prompt.text._text).startswith("Take a short tutorial of the new features?")
    # (the addon's logo and name on it: "nothing tells the player this is for AGPS", 2026-11-10)
    # (the headline with the minimap's section offered, asked 2026-11-10; without it, the addon's name)
    assert str(T.prompt.name._text) == "AzerothGPS can now replace your minimap!"
    T.ShowPrompt(lua.eval("{ 'route' }"))
    assert str(T.prompt.name._text) == "AzerothGPS"


def test_not_now_asks_again_next_login_three_times_at_most(tut):
    lua, ns = tut
    T = ns.Tutorial
    for n in range(1, T.MAX_ASKS + 1):
        T.prompted = None  # (the next login)
        assert T.MaybePrompt() is True, n
        lua.globals().AGPS_CLICK(T.prompt.later)
        assert ns.db.tutorial.declined == (n if n < T.MAX_ASKS else 0) and T.run is None
    T.prompted = None
    assert T.MaybePrompt() is False and ns.db.tutorial.offered == "1.2.0"
    # closed without an answer (Escape, the X) counts as Not Now
    _reset(lua, ns)
    assert T.MaybePrompt() is True
    T.prompt.Hide(T.prompt)
    T.prompt._scripts.OnHide(T.prompt)
    assert ns.db.tutorial.declined == 1


def test_dont_ask_again_turns_the_offer_off(tut):
    lua, ns = tut
    T = ns.Tutorial
    assert T.MaybePrompt() is True
    lua.globals().AGPS_CLICK(T.prompt.never)
    assert ns.db.tutorial.ask is False and T.run is None
    T.prompted = None
    assert T.MaybePrompt() is False
    ns.db.tutorial.offered = None  # (an update with new sections: still not asked)
    assert T.PromptDue() is False


def test_an_update_offers_only_the_sections_it_added(tut):
    lua, ns = tut
    T = ns.Tutorial
    ns.db.tutorial.offered, ns.db.tutorial.fresh = "1.2.0", None
    assert T.PromptDue() is False  # (nothing new for a seen version)
    lua.execute("""
      local T = AGPS_NS.Tutorial
      AGPS_EXTRA = { id = "later", version = "1.3.0", title = "A later feature", steps = { { title = "t", text = "x" } } }
      table.insert(T.SECTIONS, AGPS_EXTRA)
      T.byId.later = AGPS_EXTRA
    """)
    try:
        ns.db.tutorial.declined = 2  # (Not Now twice for 1.2.0's: the count starts again for the new ones)
        due, ids = T.PromptDue()
        assert due is True and list(ids.values()) == ["later"] and ns.db.tutorial.declined == 0
        assert T.MaybePrompt() is True
        texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text]
        assert "What's new in 1.3.0" in texts
        lua.globals().AGPS_CLICK(T.prompt.start)
        assert _where(ns) == ("later", 1) and list(T.run.queue.values()) == ["later"]
        T.NextClicked()
        assert _where(ns) == "card" and ns.db.tutorial.seen.later == "1.3.0" and ns.db.tutorial.offered == "1.3.0"
    finally:
        lua.execute("table.remove(AGPS_NS.Tutorial.SECTIONS) AGPS_NS.Tutorial.byId.later = nil")


def test_no_offer_and_no_start_in_combat_dead_on_a_flight_in_a_dungeon_or_during_a_game(tut):
    lua, ns = tut
    T, G = ns.Tutorial, ns.GPS
    cases = {
        "combat": ("InCombatLockdown = function() return true end", "InCombatLockdown = function() return false end"),
        "dead": ("UnitIsDeadOrGhost = function() return true end", "UnitIsDeadOrGhost = function() return false end"),
        "flight": ("UnitOnTaxi = function() return true end", "UnitOnTaxi = function() return false end"),
        "dungeon": ("IsInInstance = function() return true, 'party' end",
                    "IsInInstance = function() return false, 'none' end"),
        "recording": ("AGPS_NS.Record.rec = { saved = 0 }", "AGPS_NS.Record.rec = nil"),
    }
    for name, (on, off) in cases.items():
        lua.execute(on)
        try:
            assert T.MaybePrompt() is False and T.prompted is None, name  # (asked the next time instead)
            ok, why = T.Start()
            assert ok is False and "can't start" in str(why) and T.run is None, name
        finally:
            lua.execute(off)
    # a companion's game on the map (API.HoldMap) and a dungeon's boss route hold it off too
    G.SetHolder("a game", lua.eval("{ click = function() end }"))
    try:
        ok, why = T.Start()
        assert ok is False and str(why) == "not during a game on the map"
    finally:
        G.SetHolder("a game", None)
    lua.execute("AGPS_OLD_LOCKED = AGPS_NS.Nav.DungeonLocked AGPS_NS.Nav.DungeonLocked = function() return true end")
    try:
        assert _ok(T.Start()) is False
    finally:
        lua.execute("AGPS_NS.Nav.DungeonLocked = AGPS_OLD_LOCKED")
    # and one can't start while one runs
    assert _ok(T.Start()) is True
    ok, why = T.Start()
    assert ok is False and str(why) == "The tutorial is already running."
    # a game starting on the map while one runs: the tutorial gets out of its way, everything back
    G.SetHolder("a game", lua.eval("{ click = function() end }"))
    try:
        T.Tick()
        assert T.run is None and T.panel._shown is False and ns.settings.gps.replaceMinimap is False
    finally:
        G.SetHolder("a game", None)


# ---------------------------------------------------------------- every section, start to finish

def _run_all(lua, ns, act):
    T = ns.Tutorial
    before = _state(lua)
    assert _ok(T.Start()) is True
    taken = _play(lua, ns, act)
    assert [s for s, i, w in taken if i == 1] == SECTIONS
    # each section in a few short steps (2 to 8), and every step that waits has the player's action tested
    count = {s: max(i for sec, i, w in taken if sec == s) for s in SECTIONS}
    assert all(2 <= n <= 8 for n in count.values()), count
    acts = lua.eval("AGPS_ACT")
    for sec, si, waits in taken:
        if waits and act:
            assert acts[sec] and (acts[sec].byTitle or acts[sec][si]), f"{sec} {si} waits for the player: no action tested"
    # (each at the release it was played as: a section changed since it was added, its `updated`)
    assert dict(ns.db.tutorial.seen.items()) == {s.id: s.updated or s.version for s in T.SECTIONS.values()}
    assert T.panel._shown and str(T.panel.title._text) == str(ns.L["That's the tour"])
    assert str(T.panel.next._text) == str(ns.L["Close"])
    after = _state(lua)  # (everything back as the closing card says, before it's closed)
    assert _diff(before[0], after[0]) is None and _diff(before[1], after[1]) is None
    T.NextClicked()
    assert T.run is None and T.panel._shown is False and T.glow._shown is False and T.ticker._shown is False
    assert ns.db.tutorial.run is None
    return taken


def test_every_section_runs_start_to_finish_with_the_players_actions(tut):
    lua, ns = tut
    taken = _run_all(lua, ns, True)
    waits = [(s, i) for s, i, w in taken if w]
    assert len(waits) >= 20  # (the player does most of it)
    assert ("minimap", 2) in waits and ("route", 1) in waits


def test_every_section_runs_start_to_finish_with_every_step_skipped(tut):
    lua, ns = tut
    _run_all(lua, ns, False)


@pytest.mark.parametrize("locale", ["deDE", "zhCN"])
def test_the_tutorial_runs_in_the_games_language(locale):
    lua, ns = _start(locale=locale)
    T = ns.Tutorial
    assert ns.LOCALE == locale and str(T.SECTIONS[1].title) != "The GPS map as your minimap"
    _run_all(lua, ns, True)
    _run_all(lua, ns, False)
    # every text of it is translated
    for sec in T.SECTIONS.values():
        for step in sec.steps.values():
            assert str(step.title) != "" and step.text is not None
    texts = _script(lua, ns)
    english = _script(*_english())
    same = [a for a, b in zip(texts, english) if a == b and a not in ("Quest Route",)]
    assert not same, same


_EN = []


def _english():
    if not _EN:
        _EN.append(_start())
    return _EN[0]


def _script(lua, ns):
    """Every step's title and text as shown (a text made at run time with the tutorial's own snapshot)."""
    lua.execute("""
      function AGPS_SCRIPT()
        local ns = AGPS_NS
        local T, out = ns.Tutorial, {}
        local run = { snapshot = { gps = {} }, mark = { has = true } }
        local real = T.OtherAddons
        T.OtherAddons = function() return "RestedXP Route, Zygor Route, and Questie" end -- (as with those loaded)
        for _, sec in ipairs(T.SECTIONS) do
          out[#out + 1] = sec.title
          for _, step in ipairs(sec.steps) do
            out[#out + 1] = step.title
            local text = step.text
            if type(text) == "function" then text = text(run) end
            out[#out + 1] = text
          end
        end
        T.OtherAddons = real
        return out
      end
    """)
    return [str(t) for t in lua.eval("AGPS_SCRIPT()").values()]


def test_the_quest_route_step_waits_for_the_button_when_there_are_quests(tut):
    lua, ns = tut
    T = ns.Tutorial
    lua.execute("""
      AGPS_OLD_QS = AGPS_NS.Layers.QuestStops
      AGPS_NS.Layers.QuestStops = function()
        return { { x = 2300, y = 350, cont = 0, name = "A quest", questRoute = true } },
          { todo = 1, turnin = 0, missing = {}, elsewhere = 0 }
      end
    """)
    try:
        assert _ok(T.Start(lua.eval("{ 'quests' }"))) is True
        run = T.run
        assert run.mark.has is True and T.Waits(run) and str(T.panel.body._text) == "Click Quest Route in the map menu."
        assert len(list(ns.Nav.stops.values())) == 0
        qr = next(t.button for t in ns.GPS.QUICK.values() if t.id == "questRoute")
        lua.globals().AGPS_CLICK(qr)
        T.Tick()
        assert _where(ns) == ("quests", 2)
    finally:
        lua.execute("AGPS_NS.Layers.QuestStops = AGPS_OLD_QS")
    # without quests the stops are examples, kept out of the quest log's own handling
    T.Exit()
    assert _ok(T.Start(lua.eval("{ 'quests' }"))) is True
    assert T.run.mark.has is False and not T.Waits(T.run)
    names = [str(d.name) for d in ns.Nav.stops.values()]
    assert sorted(names) == ["Example quest 1", "Example quest 2", "Example quest 3"]
    assert all(d.quest is None for d in ns.Nav.stops.values())
    # the other addons' line only with one of them loaded
    assert len(list(T.run.steps.values())) == 2 and T.OtherAddons() is None
    T.Exit()
    lua.execute("RXPG_ARROW = {} C_AddOns.IsAddOnLoaded = function(n) return n == 'TomTom' end")
    try:
        assert _ok(T.Start(lua.eval("{ 'quests' }"))) is True
        assert len(list(T.run.steps.values())) == 3 and str(T.OtherAddons()) == "RestedXP Route and TomTom /way"
    finally:
        lua.execute("RXPG_ARROW = nil C_AddOns.IsAddOnLoaded = function() return false end")


# ---------------------------------------------------------------- everything back as it was

OWN = """
  local ns = AGPS_NS
  local st = ns.settings.gps
  -- the player's own setup: not the defaults
  st.size, st.freeSize, st.width, st.zoom = 380, true, 520, 300
  st.arrowLocked, st.arrowSnap, st.arrowFreePoint = true, false, { "TOPLEFT", "UIParent", "BOTTOMLEFT", 300, 700 }
  st.layerHerbs, st.layerOre, st.nodeFilter = false, true, { Peacebloom = true }
  st.devTools, st.wallTools, st.stepsCollapsed, st.avoidHighZones = false, false, true, true
  st.replaceMinimapSize, st.replaceMinimapCollapseOnMove = "medium", false
  st.quick = { search = "barRight", questRoute = "hidden", gather = "menuRight" } -- (their quick buttons, moved about)
  ns.GPS.LayoutQuick()
  ns.GPS.ApplySettings()
  ns.Arrow.Apply()
  ns.Nav.SetStops({ { x = 2000, y = 400, cont = 0, name = "Mine" }, { x = 2400, y = 100, cont = 0 } }, false, "red")
  ns.GPS.LookAt(0, 2100, 350, 400)
"""


def test_leaving_at_any_step_of_any_section_puts_everything_back_exactly(tut):
    lua, ns = tut
    T = ns.Tutorial
    saved = lua.eval("AGPS_NS.Tutorial.Copy(AGPS_NS.settings.gps)")
    try:
        lua.execute(OWN)
        before = _state(lua)
        left = 0
        for sec in SECTIONS:
            steps = len(list(T.byId[sec].steps.values()))
            for upto in range(1, steps + 1):
                for act in (True, False):
                    assert _ok(T.Start(lua.eval("{ '%s' }" % sec))) is True
                    while _where(ns) not in ("card", None) and T.run.si < upto:
                        _step(lua, ns, act)
                    if _where(ns) == "card":  # (a step left out here, the other addons': the section's end)
                        T.NextClicked()
                        continue
                    ns.GPS.Update()
                    T.Exit()
                    assert T.run is None and T.panel._shown is False and T.glow._shown is False
                    after = _state(lua)
                    assert _diff(before[0], after[0]) is None, (sec, upto, act, _diff(before[0], after[0]))
                    assert _diff(before[1], after[1]) is None, (sec, upto, act, _diff(before[1], after[1]))
                    left += 1
        assert left >= 80
        assert any("everything is back as you had it" in str(p) for p in lua.eval("AGPS_PRINTS").values())
    finally:
        lua.globals().AGPS_KEEP = saved
        lua.execute("""
          local st = AGPS_NS.settings.gps
          for k in pairs(st) do st[k] = nil end
          for k, v in pairs(AGPS_KEEP) do st[k] = v end
          AGPS_NS.GPS.ApplySettings()
          AGPS_NS.GPS.LayoutQuick()
          AGPS_NS.Arrow.Apply()
        """)


def test_the_sections_are_jumped_between_and_each_starts_from_the_players_own_state(tut):
    lua, ns = tut
    T, G = ns.Tutorial, ns.GPS
    before = _state(lua)
    assert _ok(T.Start()) is True
    T.Jump("gather")
    assert _where(ns) == ("gather", 1) and ns.Layers.demoNodes is not None
    T.NextClicked()
    T.Back()
    assert _where(ns) == ("gather", 1)
    assert T.panel.back._enabled is False  # (nothing before a section's first step)
    T.Jump("window")
    assert _where(ns) == ("window", 1) and ns.Layers.demoNodes is None  # (the examples gone with their section)
    # the list of sections, from the panel: a click jumps, the done ones marked
    ns.db.tutorial.seen.route = "1.2.0"
    lua.globals().AGPS_CLICK(T.panel.list)
    rows = [str(b._text) for b in T.list.rows.values()]
    assert T.list._shown and rows[1] == "Set a route (done)" and rows[2] == "Quest Route" and len(rows) == 9
    lua.globals().AGPS_CLICK(T.list.rows[4])
    assert _where(ns) == ("arrow", 1) and T.list._shown is False
    # played on from there to the end: the sections after it, in order
    taken = _play(lua, ns, False)
    assert [s for s, i, w in taken if i == 1] == SECTIONS[SECTIONS.index("arrow"):]
    T.NextClicked()
    after = _state(lua)
    assert _diff(before[0], after[0]) is None and _diff(before[1], after[1]) is None
    # one section played alone from Options > Help, jumped out of: that one alone
    assert _ok(T.Start(lua.eval("{ 'search' }"))) is True
    T.Jump("dungeon")
    assert _where(ns) == ("dungeon", 1) and list(T.run.queue.values()) == ["dungeon"]
    lvl = T.Dungeon()[0]
    assert lvl == 20389 and G.BrowseState()[1].instance == lvl  # (Ragefire Chasm's map shown from outside)
    assert "Ragefire Chasm" in str(T.panel.body._text)
    G.Update()
    assert G.ViewInstance()[0] == lvl


def test_keep_the_gps_map_as_your_minimap_yes_keeps_only_that(tut):
    lua, ns = tut
    T, G, st = ns.Tutorial, ns.GPS, ns.settings.gps
    before = _state(lua)
    assert st.replaceMinimap is False and st.replaceMinimapSize == "small"
    assert _ok(T.Start()) is True
    while _where(ns) != ("minimap", 6):
        _step(lua, ns, True)
    assert st.replaceMinimap is True and G.MinimapMode()  # (really on for the demo)
    sizes = T.panel.choices
    assert [str(sizes[i]._text) for i in (1, 2, 3)] == ["Small", "Medium", "Large"]
    lua.globals().AGPS_CLICK(sizes[3])
    assert st.replaceMinimapSize == "large" and lua.eval("AzerothGPSFrame._w") == G.MINIMAP_SIDES.large
    while _where(ns) != ("minimap", 8):
        _step(lua, ns, True)
    assert str(T.panel.title._text) == "Keep the GPS map as your minimap?"
    yes, no = T.panel.choices[1], T.panel.choices[2]
    assert (str(yes._text), str(no._text), yes._shown, no._shown) == ("Yes", "No", True, True)
    lua.globals().AGPS_CLICK(yes)
    # the sections after it run on the whole map, opened out of the square and held out
    assert _where(ns) == ("route", 1) and st.replaceMinimap is True and G.mmState.expanded and G.mmHold == "tutorial"
    lua.execute("AGPS_T = AGPS_T + 60")
    G.MinimapTick(1)
    G.MinimapTick(1)
    assert G.mmState.expanded  # (not back after 5 quiet seconds)
    G.SetMinimapExpanded(False)  # (sent back by its button: out again, the step needs it)
    G.MinimapTick(1)
    T.Tick()
    assert G.mmState.expanded
    # with the map as the minimap, the window section says why the logo doesn't minimize
    T.Jump("window")
    assert "sends the map back to its corner" in str(T.panel.body._text) and not T.Waits(T.run)
    assert str(T.panel.next._text) == "Next"
    _play(lua, ns, True)
    T.NextClicked()
    after = _state(lua)
    assert st.replaceMinimap is True and st.replaceMinimapSize == "large" and G.MinimapMode() and G.mmHold is None
    zoom = st.zoom
    lua.execute("AGPS_NS.settings.gps.replaceMinimap, AGPS_NS.settings.gps.replaceMinimapSize = false, 'small'")
    G.ApplySettings()
    # (this test's own going back to the small map rescales the zoom, as any resize does: put back as it was. With the
    # window section last, since 1.3.14's roads section went, the tutorial ends on the bigger window)
    st.zoom = zoom
    G.ApplySettings()
    back = _state(lua)
    assert _diff(before[0], back[0]) is None and _diff(before[1], back[1]) is None  # (nothing else was kept)
    assert before[0] != after[0]
    # No, or no answer: as the player had it
    for answer in (2, None):
        assert _ok(T.Start(lua.eval("{ 'minimap' }"))) is True
        while _where(ns) != ("minimap", 8):
            _step(lua, ns, False)
        if answer:
            lua.globals().AGPS_CLICK(T.panel.choices[answer])
        else:
            T.NextClicked()
        T.NextClicked()
        assert st.replaceMinimap is False and not G.mmState.on
        assert _diff(before[0], _state(lua)[0]) is None
    # a player who has it on already isn't asked: it stays on
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        assert _ok(T.Start(lua.eval("{ 'minimap' }"))) is True
        while _where(ns) != ("minimap", 8):
            _step(lua, ns, False)
        assert "stays on" in str(T.panel.body._text) and not (T.panel.choices[1] and T.panel.choices[1]._shown)
        T.NextClicked()
        T.NextClicked()
        assert st.replaceMinimap is True and G.MinimapMode()
    finally:
        st.replaceMinimap = False
        G.ApplySettings()


def test_a_reload_in_the_middle_restores_from_the_saved_snapshot_and_offers_to_go_on():
    lua, ns = _start()
    T = ns.Tutorial
    lua.execute(OWN)
    lua.execute("AGPS_NS.GPS.Follow()")
    gps = lua.eval("AGPS_DUMP(AGPS_NS.settings.gps)")
    stops = lua.eval("AGPS_DUMP(AGPS_NS.CharDB().stops)")
    assert _ok(T.Start()) is True
    while _where(ns) != ("minimap", 8):
        _step(lua, ns, True)
    lua.globals().AGPS_CLICK(T.panel.choices[1])  # (Keep the GPS map as your minimap? Yes)
    while _where(ns) != ("gather", 4):
        _step(lua, ns, True)
    # the tutorial's own settings and route are in the saved variables now, with the snapshot beside them
    assert lua.eval("AGPS_DUMP(AGPS_NS.settings.gps)") != gps and ns.db.tutorial.run.snapshot is not None
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")  # (a /reload: the game writes the saved variables)
    saved = lua.eval("AGPS_SAVED()")
    assert "Peacebloom" in saved  # (the player's own filter, in the snapshot; no example node is saved: below)

    lua2, ns2 = _start(saved=saved + "\n" + MM_SETUP)
    T2, st2 = ns2.Tutorial, ns2.settings.gps
    assert ns2.db.tutorial.run is None and T2.run is None
    assert st2.replaceMinimap is True  # (the answer given before the /reload)
    st2.replaceMinimap = False
    assert _diff(gps, lua2.eval("AGPS_DUMP(AGPS_NS.settings.gps)")) is None
    assert _diff(stops, lua2.eval("AGPS_DUMP(AGPS_NS.CharDB().stops)")) is None
    assert [str(d.name) for d in ns2.Nav.stops.values()][0] == "Mine" and len(list(ns2.Nav.stops.values())) == 2
    assert ns2.Layers.demoNodes is None and ns2.Record.practice is None and ns2.Record.rec is None
    assert lua2.eval("AGPS_NS.CharDB().recordOn") is None
    # offered again from the section it was in
    assert T2.resume.qi == SECTIONS.index("gather") + 1 and T2.MaybePrompt() is True
    ask = next(w for w in lua2.eval("AGPS_WIDGETS").values()
               if w._text and str(w._text).startswith("The tutorial was cut short"))
    yes = ask._parent.yes
    yes._scripts.OnClick(yes)
    assert _where(ns2) == ("gather", 1) and list(T2.run.queue.values()) == SECTIONS


def test_a_tutorial_left_saved_by_a_crash_restores_whoever_logs_in(tut):
    # the snapshot is the account's settings and the character's route: put back at the next login, the saved record
    # gone, whatever it holds
    lua, ns = tut
    T = ns.Tutorial
    gps = lua.eval("AGPS_DUMP(AGPS_NS.settings.gps)")
    assert _ok(T.Start(lua.eval("{ 'window' }"))) is True
    for _ in range(4):
        _step(lua, ns, True)
    assert lua.eval("AGPS_DUMP(AGPS_NS.settings.gps)") != gps
    run = ns.db.tutorial.run
    lua.execute("AGPS_NS.Tutorial.run = nil")  # (the session gone)
    T.RestoreSaved()
    assert ns.db.tutorial.run is None and _diff(gps, lua.eval("AGPS_DUMP(AGPS_NS.settings.gps)")) is None
    assert T.resume.qi == 1 and list(T.resume.queue.values()) == ["window"]
    # a record that makes no sense is dropped without an error
    lua.execute("AGPS_NS.db.tutorial.run = { snapshot = 5, queue = 'x' }")
    T.RestoreSaved()
    assert ns.db.tutorial.run is None
    lua.execute("AGPS_NS.Tutorial.Ticker():Hide()")
    ns.GPS.ApplySettings()
    assert run is not None


# ---------------------------------------------------------------- the player's data is never written

def test_the_example_nodes_never_reach_the_saved_variables(tut):
    lua, ns = tut
    T, G, R, Lay = ns.Tutorial, ns.GPS, ns.Record, ns.Layers
    before = lua.eval("AGPS_DB()")
    tracks = lua.eval("#(AGPS_NS.db.tracks or {})")
    nodes = lua.eval("AGPS_DUMP(AGPS_NS.db.nodes or {})")

    def untouched():
        assert lua.eval("#(AGPS_NS.db.tracks or {})") == tracks and ns.unsaved == 0
        assert lua.eval("AGPS_DUMP(AGPS_NS.db.nodes or {})") == nodes
        assert ns.Record.pending is None and lua.eval("AGPS_NS.CharDB().recordOn") is None

    # herbs and ore: on the map and in a farming area, from memory only
    assert _ok(T.Start(lua.eval("{ 'gather' }"))) is True
    demo = lua.eval("AGPS_NS.Layers.demoNodes[0]")
    assert len(list(demo.values())) == 6
    lua.execute("AGPS_T = AGPS_T + 2")
    G.Update()
    marks = Lay.Marks(0, 2254, 293, 300, lua.eval("{}"), 0)
    example = [m for m in marks.values() if str(m[5]) == "Example for the tutorial"]
    assert len(example) == 6 and {str(m[4]) for m in example} >= {"Peacebloom", "Copper Vein", "Tin Vein"}
    for _ in range(4):
        _step(lua, ns, True)
    assert _where(ns) == ("gather", 5) and ns.Nav.loop is True and len(list(ns.Nav.stops.values())) == 6
    untouched()
    T.Exit()
    assert Lay.demoNodes is None and len(list(ns.Nav.stops.values())) == 0
    assert len([m for m in Lay.Marks(0, 2254, 293, 300, lua.eval("{}"), 0).values()
                if str(m[5]) == "Example for the tutorial"]) == 0

    untouched()
    assert _diff(before, lua.eval("AGPS_DB()")) is None
    # (the roads section, its practice roads, walls and walks, went with the map editor in 1.3.14)
    assert "roads" not in [str(s.id) for s in T.SECTIONS.values()] and T.PracticeCount is None


def test_combat_hides_the_tutorial_and_it_goes_on_after(tut):
    lua, ns = tut
    T, G = ns.Tutorial, ns.GPS
    fire = lua.eval("AGPS_FIRE")
    assert _ok(T.Start(lua.eval("{ 'route' }"))) is True
    _step(lua, ns, True)
    assert _where(ns) == ("route", 2) and T.panel._shown and T.glow._shown
    assert lua.eval("AGPS_NS.Tutorial.target == AGPS_NS.GPS.routeButton")
    lua.execute("InCombatLockdown = function() return true end")
    fire("PLAYER_REGEN_DISABLED")
    assert T.run.paused is True and T.panel._shown is False and T.glow._shown is False
    lua.globals().AGPS_CLICK(G.routeButton)  # (what the step waits for, done mid-fight: looked at after)
    T.Tick()
    assert _where(ns) == ("route", 2) and T.panel._shown is False
    lua.execute("InCombatLockdown = function() return false end")
    fire("PLAYER_REGEN_ENABLED")
    assert T.run.paused is None and T.panel._shown and _where(ns) == ("route", 2)
    T.Tick()
    assert _where(ns) == ("route", 3)
    # left during a fight (/agps tutorial exit): still everything back
    lua.execute("InCombatLockdown = function() return true end")
    fire("PLAYER_REGEN_DISABLED")
    lua.eval("SlashCmdList.AZEROTHGPS")("tutorial exit")
    assert T.run is None and len(list(ns.Nav.stops.values())) == 0
    lua.execute("InCombatLockdown = function() return false end")
    fire("PLAYER_REGEN_ENABLED")


def test_the_panel_says_where_it_is_and_points_at_the_control(tut):
    lua, ns = tut
    T, G = ns.Tutorial, ns.GPS
    assert _ok(T.Start(lua.eval("{ 'route', 'search' }"))) is True
    p = T.panel
    assert str(p.progress._text) == "Set a route: step 1 of 6" and str(p.title._text) == "Place a stop"
    assert str(p.body._text) == "Double-click anywhere on the map to place a stop."
    assert [str(b._text) for b in (p.back, p.list, p.exit, p.next)] == ["Back", "Sections", "Exit Tutorial", "Skip Step"]
    assert p._strata == "FULLSCREEN_DIALOG" and T.glow._strata == "FULLSCREEN_DIALOG"  # (over the map opened out)
    assert "AzerothGPSTutorialPanel" not in list(lua.eval("UISpecialFrames").values())  # (Escape doesn't leave it)
    assert lua.eval("AGPS_NS.Tutorial.target == AzerothGPSFrame") and T.glow._shown
    assert lua.eval("AGPS_NS.Tutorial.glow._pts.TOPLEFT[2] == AzerothGPSFrame")
    # out of the way of what it points at: the map is mid-screen left of the middle here, the panel to the right
    assert lua.eval("AGPS_NS.Tutorial.panel._pt[4]") == pytest.approx(1920 * 0.72)
    # a step that only shows has Next; a quick button in the closed menu is pointed at by the menu's own button
    T.Jump("search")
    assert lua.eval("AGPS_NS.Tutorial.target == AGPS_NS.GPS.mapButton or AGPS_NS.Tutorial.target == AGPS_NS.GPS.searchButton")
    T.NextClicked()
    T.NextClicked()
    T.NextClicked()
    assert _where(ns) == ("search", 4) and str(p.next._text) == "Next"
    # a step that fails to set up says so and is skipped, never a dead end
    lua.execute("AGPS_OLD_SHOW = AGPS_NS.GPS.ShowInstance AGPS_NS.GPS.ShowInstance = function() error('boom') end")
    try:
        T.Jump("dungeon")
        assert T.run.blocked and str(p.body._text) == "This step can't be done here right now. Skip it to go on."
        assert "boom" in str(T.run.error) and T.glow._shown is False and str(p.next._text) == "Next"
        T.NextClicked()
        assert _where(ns) == ("dungeon", 2)
    finally:
        lua.execute("AGPS_NS.GPS.ShowInstance = AGPS_OLD_SHOW")
    # the X leaves the tutorial, as Exit Tutorial
    close = (p.chrome and p.chrome.CloseButton) or p.closeButton
    close._scripts.OnClick(close)
    assert T.run is None and p._shown is False


def test_the_quick_buttons_are_in_their_usual_places_while_it_runs(tut):
    # the steps say "in the map menu" and "on the map": true whatever the player did with their quick buttons
    lua, ns = tut
    T, G, st = ns.Tutorial, ns.GPS, ns.settings.gps
    st.quick = lua.eval("{ search = 'hidden', gather = 'barRight' }")
    G.LayoutQuick()
    try:
        assert G.QuickPlace("search") == "hidden" and G.QuickPlace("gather") == "barRight"
        assert _ok(T.Start(lua.eval("{ 'search' }"))) is True
        assert G.QuickPlace("search") == "menuUp" and G.QuickPlace("gather") == "menuUp"
        assert lua.eval("AGPS_NS.Tutorial.target == AGPS_NS.GPS.mapButton")  # (the menu's button, the menu closed)
        G.searchButton.Show(G.searchButton)  # (the menu opened, its drawer slid out: the search button itself)
        T.Tick()
        assert lua.eval("AGPS_NS.Tutorial.target == AGPS_NS.GPS.searchButton")
        assert lua.eval("AGPS_NS.Tutorial.glow._pts.TOPLEFT[2] == AGPS_NS.GPS.searchButton")
        T.Exit()
        assert G.QuickPlace("search") == "hidden" and G.QuickPlace("gather") == "barRight"
        assert G.searchButton._shown is False
    finally:
        st.quick = None
        G.LayoutQuick()


def test_the_panel_stays_where_the_player_drags_it(tut):
    lua, ns = tut
    T = ns.Tutorial
    assert _ok(T.Start(lua.eval("{ 'route' }"))) is True
    p = T.panel
    p._scripts.OnDragStop(p)
    lua.execute("AGPS_NS.Tutorial.panel._pt = { 'CENTER', UIParent, 'BOTTOMLEFT', 111, 222 }")
    T.NextClicked()
    assert lua.eval("AGPS_NS.Tutorial.panel._pt[4]") == 111


# ---------------------------------------------------------------- Options > Help and the slash command

def test_options_help_lists_every_section_and_play_starts_it(tut):
    lua, ns = tut
    T, O = ns.Tutorial, ns.Options
    O.Show()
    assert O.ShowPage("Help") is True
    assert [str(e.id) for e in O.helpSections.values()] == ["tutorial"] and O.help.host._shown is True
    rows = list(T.helpRows.values())
    assert [str(r.id) for r in rows] == SECTIONS
    assert [str(r.label._text) for r in rows][:2] == ["The GPS map as your minimap", "Set a route"]
    assert all(str(r.button._text) == "Play" for r in rows)
    ws = lua.eval("AGPS_WIDGETS")
    assert any(w._kind == "Button" and w._text == "Play All" and w._shown for w in ws.values())
    # Play starts that section alone, the options out of the way; done, it's marked on the page
    lua.globals().AGPS_CLICK(rows[SECTIONS.index("dungeon")].button)
    assert _where(ns) == ("dungeon", 1) and list(T.run.queue.values()) == ["dungeon"]
    assert lua.eval("AzerothGPSOptions._shown") is False
    _play(lua, ns, True)
    T.NextClicked()
    assert dict(ns.db.tutorial.seen.items()) == {"dungeon": "1.2.0"}
    O.Show()
    assert str(list(T.helpRows.values())[SECTIONS.index("dungeon")].label._text) == "Dungeon maps (done)"
    assert str(list(T.helpRows.values())[0].label._text) == "The GPS map as your minimap"
    # Play All: every section
    play_all = next(w for w in reversed(list(ws.values())) if w._kind == "Button" and w._text == "Play All")
    lua.globals().AGPS_CLICK(play_all)
    assert _where(ns) == ("minimap", 1) and list(T.run.queue.values()) == SECTIONS
    T.Exit()
    # the offer's switch: Don't Ask Again, and back
    cb = T.helpCheck
    assert ns.db.tutorial.ask is True
    O.Refresh()
    assert cb._checked is True
    ns.db.tutorial.ask = False
    O.Refresh()
    assert cb._checked is False
    cb._checked = True
    cb._scripts.OnClick(cb)
    assert ns.db.tutorial.ask is True
    lua.execute("AzerothGPSOptions:Hide()")


def test_the_slash_command_plays_the_tutorial_a_section_or_leaves_it(tut):
    lua, ns = tut
    T = ns.Tutorial
    slash = lua.eval("SlashCmdList.AZEROTHGPS")
    ns.settings.gps.arrowLocked = True  # (the player's own: locked; unlocked is the default since 1.2.2)
    slash("tutorial arrow")
    assert _where(ns) == ("arrow", 1) and list(T.run.queue.values()) == ["arrow"]
    assert ns.Arrow.AskLock() is None  # (no lock question in the tutorial: it puts the player's setting back after)
    assert ns.settings.gps.arrowLocked is False  # (unlocked for the demo)
    slash("tutorial exit")
    assert T.run is None and ns.settings.gps.arrowLocked is True
    ns.settings.gps.arrowLocked = ns.DEFAULTS.gps.arrowLocked
    slash("tutorial nonsense")
    assert T.run is None and "Tutorial sections: minimap route quests" in str(lua.eval("AGPS_PRINTS[#AGPS_PRINTS]"))
    slash("tutorial")
    assert _where(ns) == ("minimap", 1) and list(T.run.queue.values()) == SECTIONS
    slash("tutorial exit")
    slash("tutorial exit")
    assert str(lua.eval("AGPS_PRINTS[#AGPS_PRINTS]")) == "The tutorial isn't running."
    help_lines = (ROOT / "addon" / "AzerothGPS" / "Config.lua").read_text(encoding="utf-8")
    assert "/agps tutorial [section|exit]" in help_lines


def test_the_route_across_the_sea_takes_a_boat_or_zeppelin(tut):
    lua, ns = tut
    T, N = ns.Tutorial, ns.Nav
    assert _ok(T.Start(lua.eval("{ 'route' }"))) is True
    while _where(ns) != ("route", 5):
        _step(lua, ns, False)
    assert T.run.error is None and len(list(N.stops.values())) == 1 and N.stops[1].cont == 1  # (Kalimdor, from Brill)
    for t in range(8):
        lua.execute("AGPS_T = AGPS_T + 1")
        ns.GPS.Update()
    assert N.route is not None and "eppelin" in str(N.StepsText(9))
    assert ns.settings.gps.stepsCollapsed is False  # (the steps listed for it)
    T.NextClicked()
    # (the route is the player's to end there, with the directions' X: asked 2026-11-10)
    assert _where(ns) == ("route", 6) and len(list(N.stops.values())) == 1 and T.Waits(T.run)
    assert lua.eval("rawequal")(T.run.step.target(), ns.GPS.navCancel)
    lua.globals().AGPS_CLICK(ns.GPS.navCancel)
    assert len(list(N.stops.values())) == 0
    T.Exit()
    assert ns.settings.gps.stepsCollapsed is True


# ---------------------------------------------------------------- the script, for whoever reads it

def test_the_docs_have_every_steps_text(game):
    lua, ns = game
    doc = (ROOT / "docs" / "tutorial-1.2.0.md").read_text(encoding="utf-8")
    missing = [t for t in _script(lua, ns) if t not in doc]
    assert not missing, missing
    for sec in ns.Tutorial.SECTIONS.values():
        assert f"`{sec.id}`" in doc
        for step in sec.steps.values():  # (a short tutorial: a sentence or two a step)
            text = step.text
            if not isinstance(text, str):
                continue
            assert len(text) <= 190, text


def test_the_minimap_steps_that_wait_go_on_when_the_player_does_them(tut):
    # (seen in game 2026-11-10: "It goes back by itself" was held open and never went on after the map was closed;
    # "Options on the logo" didn't go on when the options opened)
    lua, ns = tut
    T, G = ns.Tutorial, ns.GPS
    assert _ok(T.Start()) is True
    while _where(ns) != ("minimap", 3):
        _step(lua, ns, True)
    assert T.Waits(T.run) and G.mmState.expanded and G.mmHold is None  # (not held open: it can go back)
    assert _step(lua, ns, True) == ("minimap", 3, True)
    while _where(ns) != ("minimap", 7):
        _step(lua, ns, True)
    assert T.Waits(T.run) and not lua.eval("AzerothGPSOptions and AzerothGPSOptions:IsShown()")
    assert _step(lua, ns, True) == ("minimap", 7, True)
    T.Exit()


def test_the_back_to_the_minimap_options_are_offered_in_the_tutorial_and_kept(tut):
    # (asked 2026-11-10: "offer the player to check the box here as well to enable it")
    lua, ns = tut
    T, st = ns.Tutorial, ns.settings.gps
    assert not st.replaceMinimapCollapseOnMove and not st.replaceMinimapCollapseOnCombat
    assert _ok(T.Start()) is True
    while _where(ns) != ("minimap", 5):
        _step(lua, ns, True)
    boxes = [T.panel.checks[i] for i in (1, 2)]
    assert [str(b.label._text) for b in boxes] == ["Back to the minimap when you move", "Back to the minimap when combat starts"]
    assert all(b._shown for b in boxes) and not st.replaceMinimapCollapseOnMove  # (the demo's setting isn't left on)
    boxes[1]._checked = True
    boxes[1].GetChecked = lua.eval("function() return true end")
    boxes[1]._scripts.OnClick(boxes[1])
    assert st.replaceMinimapCollapseOnCombat is True
    _step(lua, ns, True)
    assert not any(T.panel.checks[i]._shown for i in (1, 2))  # (the next step has none)
    T.Exit()
    assert st.replaceMinimapCollapseOnCombat is True and not st.replaceMinimapCollapseOnMove  # (kept; the rest put back)
    assert st.replaceMinimap is False
    st.replaceMinimapCollapseOnCombat = False


def test_the_show_hide_key_opens_and_closes_the_map_as_the_minimap(tut):
    # (asked 2026-11-10: "hotkey when in minimap mode should still work and just expand/contract the map")
    lua, ns = tut
    G, st = ns.GPS, ns.settings.gps
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        assert G.mmState.on and not G.mmState.expanded
        lua.globals().AzerothGPS_ToggleMap()
        assert G.mmState.expanded and st.shown
        lua.globals().AzerothGPS_ToggleMap()
        assert not G.mmState.expanded and st.shown  # (never hidden by the key there)
    finally:
        st.replaceMinimap = False
        G.ApplySettings()


def test_a_countdown_shows_on_the_map_while_it_waits_to_go_back(tut):
    # (asked 2026-11-10: "add a countdown in the GPS window ... if player does activity change the numbers to Active!")
    lua, ns = tut
    T, G = ns.Tutorial, ns.GPS
    assert _ok(T.Start()) is True
    assert T.CountdownText(lua.eval("AGPS_T")) is None  # (not this step's)
    while _where(ns) != ("minimap", 3):
        _step(lua, ns, True)
    G.MinimapTick(1)  # (opened out: the animation over)
    m = G.mmState
    now = lua.eval("AGPS_T")
    m.activeAt = now
    assert "Active!" in str(T.CountdownText(now))
    assert T.CountdownText(now + 1) == "4" and T.CountdownText(now + 4.5) == "1"
    lua.execute("AGPS_T = AGPS_T + 2")
    T.Tick()
    assert T.countdown._shown and str(T.countdown.text._text) == "3"
    _step(lua, ns, True)  # (it went back: the next step, no countdown)
    assert not T.countdown._shown
    T.Exit()


def test_the_arrow_section_leaves_the_map_as_the_minimap_in_its_corner(tut):
    # (seen in game 2026-11-10: the whole map was forced open over the arrow it was showing)
    lua, ns = tut
    T, G, st = ns.Tutorial, ns.GPS, ns.settings.gps
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        assert _ok(T.Start(lua.eval("{ 'route', 'arrow' }"))) is True
        assert G.mmState.expanded and G.mmHold == "tutorial"  # (the route section: on the whole map)
        while _where(ns)[0] == "route":
            _step(lua, ns, True)
        assert _where(ns) == ("arrow", 1) and G.mmState.on and not G.mmState.expanded and G.mmHold is None
        for _ in range(3):
            G.Update()
            T.Tick()
        assert not G.mmState.expanded  # (and it isn't opened again while the section runs)
        T.Exit()
    finally:
        st.replaceMinimap = False
        G.ApplySettings()


def test_the_any_shape_step_really_turns_any_shape_on_and_offers_it(tut):
    # (seen in game 2026-11-10: "this step didn't actually enable the any size option to test it")
    lua, ns = tut
    T, G, st = ns.Tutorial, ns.GPS, ns.settings.gps
    assert not st.freeSize and st.width is None
    size = st.size
    assert _ok(T.Start(lua.eval("{ 'window' }"))) is True
    while _where(ns) != ("window", 4):
        _step(lua, ns, True)
    assert G.FreeSize() and st.width is not None  # (the corner sets the width and the height apart)
    box = T.panel.checks[1]
    assert str(box.label._text) == "Any shape" and box._shown
    box.GetChecked = lua.eval("function() return true end")
    box._scripts.OnClick(box)
    T.Exit()
    assert st.freeSize is True and st.size == size and st.width == size  # (kept, from the player's own size)
    st.freeSize, st.width = False, None
    G.ApplySettings()


def test_the_hide_the_map_step_leaves_the_map_in_its_corner_as_the_minimap(tut):
    # (seen in game 2026-11-10: "this step automatically opens the map back up after collapsing it")
    lua, ns = tut
    T, G, st = ns.Tutorial, ns.GPS, ns.settings.gps
    st.replaceMinimap = True
    G.ApplySettings()
    try:
        assert _ok(T.Start(lua.eval("{ 'window' }"))) is True
        assert _where(ns) == ("window", 1) and G.mmState.expanded
        G.MinimapTick(1)
        G.SetMinimized(True)  # (the logo's double-click: back to its corner there)
        for _ in range(4):
            G.MinimapTick(1)
            T.Tick()
        assert not G.mmState.expanded  # (left there)
        T.NextClicked()
        T.NextClicked()
        assert _where(ns) == ("window", 3)
        G.MinimapTick(1)
        assert G.mmState.expanded  # (opened again for the step that needs it)
        T.Exit()
    finally:
        st.replaceMinimap = False
        G.ApplySettings()


def test_the_loop_route_step_says_why_only_the_next_paths_are_drawn(tut):
    # (asked 2026-11-10: "explain that only the first X routes are drawn to save on performance but all stops are in
    # the route and once the first destination is reached the next position's path is drawn")
    lua, ns = tut
    T, st = ns.Tutorial, ns.settings.gps
    was = st.stopsAhead
    st.stopsAhead = 4
    try:
        assert _ok(T.Start(lua.eval("{ 'gather' }"))) is True
        while _where(ns) != ("gather", 5):
            _step(lua, ns, True)
        text = str(T.panel.body._text)
        assert "(4 at a time)" in text and "Every stop is still in the route" in text
        assert "Options > Performance" in text
        T.Exit()
    finally:
        st.stopsAhead = was


def test_the_countdown_is_drawn_by_the_maps_size_and_the_addons_read_as_a_list(tut):
    # (asked 2026-11-10: "Make this number/word much larger on the map relative to user map size"; and the other
    # addons as "RestedXP Route, Zygor, and Questie")
    lua, ns = tut
    T = ns.Tutorial
    small, big = T.CountdownScale(140, 140), T.CountdownScale(800, 600)
    assert small == T.COUNTDOWN_MIN  # (never smaller than twice the huge font)
    assert big == pytest.approx(600 * 0.2 / 20) and big > 2 * small  # (by the smaller side)
    assert T.CountdownScale(4000, 4000) == T.COUNTDOWN_MAX and T.CountdownScale(None, None) == T.COUNTDOWN_MIN
    lua.execute("""
      AGPS_NS.RestedXP = AGPS_NS.RestedXP or {}
      AGPS_RX, AGPS_ZY = AGPS_NS.RestedXP.Available, AGPS_NS.Zygor and AGPS_NS.Zygor.Available
      AGPS_NS.Zygor = AGPS_NS.Zygor or {}
      AGPS_NS.RestedXP.Available = function() return true end
      AGPS_NS.Zygor.Available = function() return true end
      AGPS_LOADED = IsAddOnLoaded
      AGPS_CA = C_AddOns and C_AddOns.IsAddOnLoaded
      IsAddOnLoaded = function(n) return n == "Questie" end
      if C_AddOns then C_AddOns.IsAddOnLoaded = IsAddOnLoaded end
    """)
    try:
        assert str(T.OtherAddons()) == "RestedXP Route, Zygor Route, and Questie"
    finally:
        lua.execute("""
          AGPS_NS.RestedXP.Available, AGPS_NS.Zygor.Available = AGPS_RX, AGPS_ZY
          IsAddOnLoaded = AGPS_LOADED
          if C_AddOns then C_AddOns.IsAddOnLoaded = AGPS_CA end
        """)


def test_the_section_list_marks_done_updated_and_new(tut):
    # (asked 2026-11-14: "if the player has done the tutorial we mark it (done) but if we update or add a new one we
    # should show (new) or (updated)")
    lua, ns = tut
    T = ns.Tutorial
    sec = lambda v, u=None: lua.eval(  # noqa: E731
        "function(v, u) return { id = 'x', title = 'X', version = v, updated = u } end")(v, u)
    seen = lua.eval("{ route = '1.2.0', x = '1.2.0' }")
    assert T.SectionLabel(sec("1.2.0"), seen) == "X (done)"
    assert T.SectionLabel(sec("1.2.0", "1.2.9"), seen) == "X (updated)"  # (changed since it was played)
    assert T.SectionLabel(sec("1.2.0", "1.2.9"), lua.eval("{ x = '1.2.9' }")) == "X (done)"  # (played as it is now)
    assert T.SectionLabel(sec("1.3.0"), lua.eval("{ route = '1.2.0' }")) == "X (new)"  # (added after the newest played)
    assert T.SectionLabel(sec("1.2.0"), lua.eval("{ route = '1.2.0' }")) == "X"  # (as old, not played: no mark)
    assert T.SectionLabel(sec("1.3.0"), lua.eval("{}")) == "X"  # (none played: nothing is new to them)
