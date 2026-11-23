"""Import From GatherMate2 (1.3.10, asked 2026-11-19: "a way for players to import GatherMate2 data for herbs/mines ...
detects if the user has that addon installed, and if so add a button to the herbs menu ... once per startup check for
new GatherMate2 data to be imported; if so make the button glow. If they haven't imported it, the button glows as
well"). The button is in the map menu's Herbs, Ore and Farming group, only with GatherMate2 loaded; the import goes into
the player's own herbs and ore (unconfirmed until gathered), in slices; the startup check is in slices too."""

import pytest

FRAME_MS = 40  # (test_frame_budget's: the longest a slice of background work may run)
TIRISFAL = 1420

PRE = """
  AGPS_GM2 = true
  AGPS_GM2DATA = "none" -- GatherMate2_Data: "none", "demand" (installed, load on demand), "loaded"
  AGPS_GM2DATA_LOADS = 0
  C_AddOns.IsAddOnLoaded = function(name)
    if name == "GatherMate2_Data" then return AGPS_GM2DATA == "loaded" end
    return AGPS_GM2 and name == "GatherMate2"
  end
  IsAddOnLoaded = C_AddOns.IsAddOnLoaded
  C_AddOns.GetAddOnInfo = function(name)
    if name ~= "GatherMate2_Data" or AGPS_GM2DATA == "none" then return name, nil, nil, false, "MISSING" end
    return name, "GatherMate2Data", "", true, AGPS_GM2DATA == "demand" and "DEMAND_LOADED" or nil
  end
  local meta = C_AddOns.GetAddOnMetadata
  C_AddOns.GetAddOnMetadata = function(name, field)
    if name == "GatherMate2_Data" and field == "Version" then return AGPS_GM2DATA_VERSION or "v42.0" end
    return meta(name, field)
  end
  C_AddOns.LoadAddOn = function(name)
    if name ~= "GatherMate2_Data" or AGPS_GM2DATA ~= "demand" then return false, "MISSING" end
    AGPS_GM2DATA, AGPS_GM2DATA_LOADS = "loaded", AGPS_GM2DATA_LOADS + 1
    GatherMateData2HerbDB, GatherMateData2MineDB = AGPS_GM2DATA_HERBS, AGPS_GM2DATA_MINES
    return true
  end
"""


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(pre=PRE)
    return lua, ns


def _coord(x, y):
    return int(x * 10000 + 0.5) * 1000000 + int(y * 10000 + 0.5) * 100


def _table(d):
    rows = []
    for zone, nodes in (d or {}).items():
        rows.append(f"[{zone}] = {{ " + ", ".join(f"[{_coord(x, y)}] = {i}" for x, y, i in nodes) + " }")
    return "{ " + ", ".join(rows) + " }"


def _gm2(lua, herbs=None, mines=None):
    """GatherMate2's saved variables: { [uiMapID] = { [coord] = nodeID } } from { map: [(x, y, id), ...] }."""
    lua.execute(f"GatherMate2HerbDB = {_table(herbs)}; GatherMate2MineDB = {_table(mines)}")


def _gm2data(lua, herbs=None, mines=None, state="demand"):
    """GatherMate2_Data installed, its WoW Forever tables (GatherMateData2HerbDB / MineDB) set when it loads."""
    lua.execute(f"AGPS_GM2DATA = '{state}'; AGPS_GM2DATA_HERBS = {_table(herbs)}; AGPS_GM2DATA_MINES = {_table(mines)}")
    if state == "loaded":
        lua.execute("GatherMateData2HerbDB, GatherMateData2MineDB = AGPS_GM2DATA_HERBS, AGPS_GM2DATA_MINES")


@pytest.fixture(autouse=True)
def fresh(game):
    lua, ns = game
    lua.execute("AGPS_GM2 = true; AGPS_GM2DATA = 'none'; AGPS_GM2DATA_LOADS = 0; AGPS_GM2DATA_VERSION = nil; AGPS_GM2DATA_HERBS = nil; "
                "AGPS_GM2DATA_MINES = nil; GatherMateData2HerbDB, GatherMateData2MineDB = nil, nil")
    ns.db.nodes = lua.table()
    ns.db.gm2 = None
    lua.execute("for k in pairs(AGPS_NS.Layers.gm2) do AGPS_NS.Layers.gm2[k] = nil end")
    _gm2(lua)
    yield
    lua.execute("GatherMate2HerbDB, GatherMate2MineDB = nil, nil")


def _clock(lua):
    return lua.eval("function() return os.clock() * 1000 end")


def _run(lua, ns, slice_ms=3):
    """Pump the check or import to its end; the longest slice in ms and how many slices."""
    Lay = ns.Layers
    clock = _clock(lua)
    worst, n = 0.0, 0
    more = True
    while more:
        a = clock()
        more = Lay.GM2Pump(a + slice_ms, clock)
        worst = max(worst, clock() - a)
        n += 1
        assert n < 100000
    return worst, n


def _world(ns, x, y, zone=TIRISFAL):
    wx, wy, cont = ns.Layers.MapToWorld(zone, x, y)
    return wx, wy, cont


def _nodes(ns, cont):
    lst = ns.db.nodes[cont]
    return [] if lst is None else [lst[i] for i in range(1, len(lst) + 1)]


def _member_shown(lua, ns, qid):
    G, gps = ns.GPS, ns.settings.gps
    was = gps.quick
    gps.quick = lua.eval("{ gather = 'barUp' }")  # (on the bar: shown without opening the map menu)
    G.LayoutQuick()
    grp = G.groupOf.gather
    if G.OpenGroupSlot() is not None:
        G.CloseOpenGroup()
    try:
        assert grp.button._shown
        G.ToggleGroup(grp)
        t = next(m for m in grp.members.values() if str(m.id) == qid)
        shown = bool(t.button._shown)
        if shown:
            # (laid out with no gap: the group's shown members one step apart)
            xs = sorted(m.button._pts.LEFT[4] for m in grp.members.values() if m.button._shown)
            assert all(abs((b - a) - G.QUICK_STEP_BAR) < 1e-6 for a, b in zip(xs, xs[1:])), xs
        return shown
    finally:
        G.CloseOpenGroup()
        gps.quick = was
        G.LayoutQuick()



# -- the button -----------------------------------------------------------------------------------------------------


def test_no_button_without_gathermate2(game):
    lua, ns = game
    lua.execute("AGPS_GM2 = false")
    Lay = ns.Layers
    assert not Lay.GM2Loaded()
    assert not _member_shown(lua, ns, "gm2Import")
    assert _member_shown(lua, ns, "nodeFind")  # (the group's others as before)
    assert not Lay.GM2StartCheck() and not Lay.GM2Import()  # (no check at startup, no import)
    assert not Lay.GM2Glow() and not ns.GPS.GlowingIds()["gm2Import"]


def test_the_button_is_in_the_herbs_group_with_gathermate2(game):
    lua, ns = game
    assert ns.Layers.GM2Loaded()
    assert _member_shown(lua, ns, "gm2Import")
    t = next(m for m in ns.GPS.groupOf.gather.members.values() if str(m.id) == "gm2Import")
    assert str(t.label) == "Import From GatherMate2"


def test_the_button_is_there_in_world_map_mode_too(game):
    from test_world_map_host import SETUP
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    was = (st.useWorldMap, st.shown, st.minimized)
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        assert _member_shown(lua, ns, "gm2Import")
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        st.useWorldMap, st.shown, st.minimized = was
        G.ApplySettings()


# -- the import -----------------------------------------------------------------------------------------------------


def test_the_import_converts_to_world_spots_and_dedupes(game):
    lua, ns = game
    Lay = ns.Layers
    a, b, c = (0.40, 0.50), (0.45, 0.55), (0.60, 0.30)
    ax, ay, cont = _world(ns, *a)
    # (one the player gathered already, at a: known once)
    assert Lay.AddNode(cont, ax + 3, ay - 2, "Peacebloom", "herb")
    _gm2(lua,
         herbs={TIRISFAL: [(a[0], a[1], 401), (b[0], b[1], 402), (b[0] + 0.0002, b[1], 402), (0.7, 0.7, 432)]},
         mines={TIRISFAL: [(c[0], c[1], 201)]})
    said = []
    old = ns.Print
    ns.Print = lambda msg: said.append(str(msg))
    try:
        assert Lay.GM2Import()
        _run(lua, ns)
    finally:
        ns.Print = old
    nodes = _nodes(ns, cont)
    by = {str(n[3]): n for n in nodes}
    assert sorted(by) == ["Copper Vein", "Peacebloom", "Silverleaf"] and len(nodes) == 3
    bx, by_, _ = _world(ns, *b)
    cx, cy, _ = _world(ns, *c)
    s = by["Silverleaf"]
    assert abs(s[1] - bx) < 2 and abs(s[2] - by_) < 2 and str(s[4]) == "herb" and s[6] is True  # (unconfirmed)
    v = by["Copper Vein"]
    assert abs(v[1] - cx) < 0.2 and abs(v[2] - cy) < 0.2 and str(v[4]) == "ore" and v[6] is True
    assert by["Peacebloom"][6] is None  # (the player's own, gathered: as it was)
    # (two Silverleafs a yard or so apart: one, either; Felweed, 432, a later expansion's: not a herb here)
    assert said == ["Imported 1 herbs and 1 mines, 2 already known."]
    assert str(Lay.gm2.result) == said[0]


def test_importing_again_adds_nothing_new(game):
    lua, ns = game
    Lay = ns.Layers
    _gm2(lua, herbs={TIRISFAL: [(0.4, 0.5, 401), (0.5, 0.5, 403)]})
    Lay.GM2Import()
    _run(lua, ns)
    _, _, cont = _world(ns, 0.4, 0.5)
    n = len(_nodes(ns, cont))
    Lay.GM2Import()
    _run(lua, ns)
    assert len(_nodes(ns, cont)) == n == 2
    assert str(Lay.gm2.result) == "Imported 0 herbs and 0 mines, 2 already known."


def test_big_counts_are_written_with_separators(game):
    lua, ns = game
    T = ns.Layers.GM2Thousands
    assert str(T(1234)) == "1,234" and str(T(567)) == "567" and str(T(1234567)) == "1,234,567"


# -- the glow -------------------------------------------------------------------------------------------------------


def _glow(lua, ns):
    on = bool(ns.Layers.GM2Glow())
    assert on == bool(ns.GPS.GlowingIds()["gm2Import"])
    assert on == bool(ns.GPS.GlowingIds()["gather"])  # (the group's button glows for it, as for Find Herbs and Ore)
    return on


def _check(lua, ns):
    assert ns.Layers.GM2StartCheck()
    _run(lua, ns)


def test_it_glows_when_never_imported(game):
    lua, ns = game
    _gm2(lua, herbs={TIRISFAL: [(0.4, 0.5, 401)]})
    assert not _glow(lua, ns)  # (until the startup check has looked)
    _check(lua, ns)
    assert _glow(lua, ns)
    assert "haven't imported" in str(ns.Layers.GM2Status())


def test_no_glow_after_the_import(game):
    lua, ns = game
    _gm2(lua, herbs={TIRISFAL: [(0.4, 0.5, 401)]}, mines={TIRISFAL: [(0.6, 0.3, 201)]})
    _check(lua, ns)
    assert _glow(lua, ns)
    ns.Layers.GM2Import()
    assert not _glow(lua, ns)  # (not while importing either)
    _run(lua, ns)
    assert not _glow(lua, ns)
    _check(lua, ns)  # (the next startup's check: nothing new)
    assert not _glow(lua, ns)


def test_it_glows_when_gathermate2_has_new_data(game):
    lua, ns = game
    _gm2(lua, herbs={TIRISFAL: [(0.4, 0.5, 401)]})
    ns.Layers.GM2Import()
    _run(lua, ns)
    _check(lua, ns)
    assert not _glow(lua, ns)
    _gm2(lua, herbs={TIRISFAL: [(0.4, 0.5, 401), (0.42, 0.52, 404)]})  # (gathered since with GatherMate2)
    _check(lua, ns)
    assert _glow(lua, ns)


def test_no_glow_with_nothing_to_import(game):
    lua, ns = game
    _check(lua, ns)
    assert not _glow(lua, ns)


def test_the_startup_check_waits_and_does_nothing_without_gathermate2(game):
    lua, ns = game
    Lay = ns.Layers
    lua.execute("AGPS_AFTER = {}; C_Timer.After = function(s, fn) AGPS_AFTER[#AGPS_AFTER + 1] = { s, fn } end")
    try:
        Lay.GM2OnLogin()
        waits = lua.eval("AGPS_AFTER")
        assert len(waits) == 1 and waits[1][1] == Lay.GM2_CHECK_WAIT > 0
        assert Lay.gm2.phase is None  # (nothing read at login itself)
        waits[1][2]()
        assert str(Lay.gm2.phase) == "check"
        _run(lua, ns)
        lua.execute("AGPS_GM2 = false; AGPS_AFTER = {}")
        Lay.GM2OnLogin()
        assert len(lua.eval("AGPS_AFTER")) == 0
    finally:
        lua.execute("C_Timer.After = function() end")


# -- the frame budget -----------------------------------------------------------------------------------------------


def _big(lua, n_zones=12, per=4000):
    """A large GatherMate2 file: n_zones * per herbs and as many mines, on real maps."""
    zones = [1411, 1412, 1413, 1416, 1417, 1418, 1419, 1420, 1421, 1422, 1423, 1424, 1425, 1426, 1427, 1428, 1429,
             1430, 1431, 1432, 1433, 1434, 1436, 1437, 1438, 1439, 1440, 1441, 1442, 1443, 1444, 1445, 1446, 1447,
             1448, 1449, 1450, 1451, 1452][:n_zones]
    lua.execute(f"""
      local herbs, mines = {{}}, {{}}
      local zones = {{ {', '.join(map(str, zones))} }}
      for zi, z in ipairs(zones) do
        local h, m = {{}}, {{}}
        for i = 1, {per} do
          local x, y = (i % 97) / 100 + 0.005, math.floor(i / 97) % 97 / 100 + 0.005
          local c = math.floor(x * 10000 + 0.5) * 1000000 + math.floor(y * 10000 + 0.5) * 100
          h[c + 1] = 401 + (i % 28)
          m[c + 2] = 201 + (i % 20)
        end
        herbs[z], mines[z] = h, m
      end
      GatherMate2HerbDB, GatherMate2MineDB = herbs, mines
    """)
    return 2 * n_zones * per


@pytest.mark.timing
def test_the_startup_check_stays_within_the_frame_budget(game):
    lua, ns = game
    total = _big(lua)
    clock = _clock(lua)
    a = clock()
    assert ns.Layers.GM2StartCheck()
    assert clock() - a < FRAME_MS
    worst, n = _run(lua, ns)
    assert worst < FRAME_MS, f"a slice of the check ran {worst:.0f} ms"
    assert n > 1  # (spread over frames)
    assert ns.Layers.gm2.herbs + ns.Layers.gm2.mines == total


@pytest.mark.timing
def test_the_import_stays_within_the_frame_budget_with_progress(game):
    lua, ns = game
    Lay, G = ns.Layers, ns.GPS
    _big(lua)
    clock = _clock(lua)
    a = clock()
    assert Lay.GM2Import()  # (the click itself)
    assert clock() - a < FRAME_MS, f"the click ran {clock() - a:.0f} ms"
    t = next(m for m in G.groupOf.gather.members.values() if str(m.id) == "gm2Import")
    a = clock()
    assert Lay.GM2Pump(a + 3, clock)
    assert t.progressText is not None and t.progressText._shown and "%" in str(t.progressText._text)
    assert 0 < Lay.gm2.progress < 1
    worst, n = _run(lua, ns)
    assert worst < FRAME_MS, f"a slice of the import ran {worst:.0f} ms"
    assert n > 1 and not t.progressText._shown
    assert Lay.gm2.phase is None and ns.db.gm2 is not None and not Lay.GM2Glow()
    added = sum(len(_nodes(ns, c)) for c in (0, 1))
    assert added > 0


# -- removing what was imported (asked 2026-11-19: "provide a way to remove this data from an import as well in options.
# So this would wipe unverified nodes from the local data. Require confirmation.") ------------------------------------


def test_removing_unconfirmed_asks_first_and_keeps_gathered_ones(game):
    lua, ns = game
    Lay, O = ns.Layers, ns.Options
    a = (0.40, 0.50)
    ax, ay, cont = _world(ns, *a)
    assert Lay.AddNode(cont, ax, ay, "Peacebloom", "herb")  # (gathered: stays)
    _gm2(lua, herbs={TIRISFAL: [(a[0], a[1], 401), (0.45, 0.55, 402)]}, mines={TIRISFAL: [(0.6, 0.3, 201)]})
    Lay.GM2Import()
    _run(lua, ns)
    assert Lay.UnconfirmedCount() == 2 and len(_nodes(ns, cont)) == 3
    O.Show()
    b = O.removeUnconfirmedButton
    assert str(b._text) == "Remove Unconfirmed Herbs and Ore"
    O.Refresh()
    assert b._enabled is not False
    b._scripts.OnClick(b)
    ask = O.removeAsk
    assert ask is not None and ask._shown and "Remove 2 unconfirmed herbs and ore?" in str(ask.text._text)
    assert Lay.UnconfirmedCount() == 2  # (the click alone removed nothing)
    ask.no._scripts.OnClick(ask.no)
    assert Lay.UnconfirmedCount() == 2 and len(_nodes(ns, cont)) == 3
    said = []
    old = ns.Print
    ns.Print = lambda msg: said.append(str(msg))
    try:
        b._scripts.OnClick(b)
        ask = O.removeAsk
        ask.yes._scripts.OnClick(ask.yes)
    finally:
        ns.Print = old
    nodes = _nodes(ns, cont)
    assert Lay.UnconfirmedCount() == 0 and len(nodes) == 1 and str(nodes[0][3]) == "Peacebloom" and nodes[0][6] is None
    assert said == ["Removed 2 unconfirmed herbs and ore."]
    O.Refresh()
    assert b._enabled is False  # (nothing left to remove)
    # (GatherMate2's import undone: its button glows again after the check)
    assert ns.db.gm2 is None
    _check(lua, ns)
    assert _glow(lua, ns)


def test_nothing_is_removed_while_importing(game):
    lua, ns = game
    Lay = ns.Layers
    _gm2(lua, herbs={TIRISFAL: [(0.4, 0.5, 401)]})
    Lay.GM2Import()
    assert Lay.RemoveUnconfirmed() is None
    _run(lua, ns)
    assert Lay.UnconfirmedCount() == 1


# -- GatherMate2_Data (asked 2026-11-19: "the 1 button should handle both data, either from player collected or from the
# additional data addon") -----------------------------------------------------------------------------------------------


def test_one_click_imports_the_players_own_and_gathermate2_datas(game):
    lua, ns = game
    Lay = ns.Layers
    _gm2(lua, herbs={TIRISFAL: [(0.40, 0.50, 401)]})  # (the player's own, collected)
    # (the data addon's: one the same Peacebloom, a Silverleaf and a vein elsewhere; a later expansion's node)
    _gm2data(lua, herbs={TIRISFAL: [(0.40, 0.50, 401), (0.45, 0.55, 402), (0.7, 0.7, 432)]},
             mines={TIRISFAL: [(0.60, 0.30, 201)]})
    assert lua.eval("AGPS_GM2DATA_LOADS") == 0
    assert Lay.GM2Import()
    assert lua.eval("AGPS_GM2DATA_LOADS") == 1  # (loaded by the click, on demand)
    _run(lua, ns)
    _, _, cont = _world(ns, 0.4, 0.5)
    names = sorted(str(n[3]) for n in _nodes(ns, cont))
    assert names == ["Copper Vein", "Peacebloom", "Silverleaf"]
    assert all(n[6] is True for n in _nodes(ns, cont))  # (unconfirmed until gathered)
    assert str(Lay.gm2.result) == "Imported 2 herbs and 1 mines, 1 already known."
    assert not Lay.GM2Glow()


def test_gathermate2_data_alone_glows_until_imported(game):
    lua, ns = game
    Lay = ns.Layers
    _gm2data(lua, herbs={TIRISFAL: [(0.45, 0.55, 402)]})  # (nothing collected with GatherMate2 yet)
    _check(lua, ns)
    assert lua.eval("AGPS_GM2DATA_LOADS") == 0  # (the startup check never loads it)
    assert _glow(lua, ns)
    Lay.GM2Import()
    _run(lua, ns)
    assert Lay.UnconfirmedCount() == 1 and not _glow(lua, ns)
    # (the next startup: GatherMate2_Data loaded or not, the same signature: no glow)
    for state in ("loaded", "demand"):
        lua.execute(f"AGPS_GM2DATA = '{state}'")
        _check(lua, ns)
        assert not _glow(lua, ns), state
    # (a new GatherMate2_Data version: glows again)
    lua.execute("AGPS_GM2DATA_VERSION = 'v43.0'")
    _check(lua, ns)
    assert _glow(lua, ns)


@pytest.mark.timing
def test_a_large_gathermate2_data_import_stays_within_the_frame_budget(game):
    lua, ns = game
    Lay = ns.Layers
    _big(lua)
    lua.execute("AGPS_GM2DATA = 'demand'; AGPS_GM2DATA_HERBS, AGPS_GM2DATA_MINES = GatherMate2HerbDB, GatherMate2MineDB; "
                "GatherMate2HerbDB, GatherMate2MineDB = {}, {}")
    assert Lay.GM2Import()
    worst, n = _run(lua, ns)
    assert worst < FRAME_MS, f"a slice of the import ran {worst:.0f} ms"
    assert n > 1 and Lay.UnconfirmedCount() > 0
