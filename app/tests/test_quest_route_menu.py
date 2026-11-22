"""The Quest Route button's right-click menu: other ways to make the quest route, for that route only (1.3.14; the whole
addon, gameharness).

Kooki3z 2026-11-22: "lets extend the quest route button with a sub menu to route in different ways like by level, turn
ins only, tracked quest only, etc".

- Left-click: the quest route by the saved Quest Route options, as before. Right-click: our own menu (never the game's
  menus: issue #887) with Fastest order (all quests), Lowest level first, About to turn gray first, Turn-ins only,
  Objectives only, Tracked quests only, This zone only and Quest Route options...; the entries the saved options give
  marked "(default)".
- Each way sets only its own part (QuestWays.lua): the rest is the saved options, quests left out stay out, and the
  saved options are never changed. The way is the route's (Nav.questWay): its remakes and reorders keep it, a /reload
  too; a left-click goes back to the saved options.
- It opens beside the button wherever the button is: the column going up, the row going right, the world map, the map
  grown out of the minimap square.

The quest log is test_quest_route_choices.py's stub: its quests around Brill on Tirisfal Glades' map.
"""

import pytest

from test_map_redraw import MM_SETUP, MM_TEARDOWN, _expand_setup, _tick
from test_quest_route_choices import _names, _order, game, quests  # noqa: F401

WAYS = ["fastest", "low", "gray", "turnins", "objectives", "tracked", "zone"]


def _qr(ns):
    return ns.GPS.questRouteButton


def _right_click(ns):
    b = _qr(ns)
    b._scripts.OnClick(b, "RightButton")


def _rows(ns):
    m = ns.GPS.questWays
    return [(str(r.id), str(r.text._text)) for r in m.rows.values() if r._shown]


def _pick(ns, way):
    m = ns.GPS.questWays
    (row,) = [r for r in m.rows.values() if r._shown and r.id == way]
    row._scripts.OnClick(row, "LeftButton")


def _saved(st):
    return (st.questLevelOrder, st.questZoneOnly, st.questTrackedOnly)


def _log(quests):
    # near: a tracked level 10 quest, a finished level 14 one (its turn-in), an untracked level 14 one, a level 11 one
    quests({"id": 601, "title": "Wolves", "dx": 60, "level": 10, "tracked": True},
           {"id": 602, "title": "Letter", "dx": 120, "level": 14, "done": True},
           {"id": 603, "title": "Boars", "dx": 180, "level": 14},
           {"id": 604, "title": "Spiders", "dx": 240, "level": 11, "tracked": True})


@pytest.fixture
def menu(game, quests):
    lua, ns = game
    _log(quests)
    if ns.GPS.askBox is None:  # (the quests fixture puts its question box back after: made once, as a question does)
        ns.GPS.Ask("AzerothGPSGroupQuest", "?", "Keep", "Leave Out", lua.eval("function() end"), lua.eval("function() end"))
        ns.GPS.askBox._shown = False
    yield lua, ns
    ns.GPS.CloseQuestWays()


def test_right_click_opens_the_menu_and_left_click_is_the_saved_route(menu):
    lua, ns = menu
    G, N = ns.GPS, ns.Nav
    b = _qr(ns)
    assert b is not None and lua.eval("rawequal")(b, next(t.button for t in G.QUICK.values() if t.id == "questRoute"))
    _right_click(ns)
    assert G.QuestWaysOpen() and len(N.stops) == 0  # (the menu only: no route yet)
    ids = [i for i, _ in _rows(ns)]
    assert ids == WAYS + ["options"]
    texts = dict(_rows(ns))
    assert texts["turnins"] == "Turn-ins only" and texts["options"] == "Quest Route options..."
    assert texts["low"] == "Lowest level first" and texts["fastest"].startswith("Fastest order (all quests)")
    # right-click again: shut; a click anywhere else shuts it too
    _right_click(ns)
    assert not G.QuestWaysOpen()
    _right_click(ns)
    G.questWays.catch._scripts.OnClick(G.questWays.catch, "LeftButton")
    assert not G.QuestWaysOpen()
    # left-click: the quest route by the saved options, as before (every quest), the menu shut
    _right_click(ns)
    b._scripts.OnClick(b, "LeftButton")
    assert not G.QuestWaysOpen()
    assert _names(ns) == ["Boars", "Spiders", "Turn in: Letter", "Wolves"] and N.questWay is None


def test_the_tooltip_says_right_click(menu):
    lua, ns = menu
    b = _qr(ns)
    lines = []
    lua.execute("AGPS_OLD_ADD = GameTooltip.AddLine")
    lua.globals().GameTooltip.AddLine = lambda self, text, *a: lines.append(str(text))
    try:
        b._scripts.OnEnter(b)
    finally:
        lua.execute("GameTooltip.AddLine = AGPS_OLD_ADD")
    assert "Right-click for other ways." in lines


@pytest.mark.parametrize("saved_level", ["off", "low"])
def test_each_way_makes_its_stops_and_leaves_the_options_alone(menu, saved_level):
    lua, ns = menu
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    st.questLevelOrder = saved_level
    was = _saved(st)
    calls = []
    real = ns.Layers.QuestStops
    note = lambda zone, tracked: calls.append((bool(zone), bool(tracked)))  # noqa: E731
    ns.Layers.QuestStops = lua.eval("function(real, note) return function(z, t) note(z, t) return real(z, t) end end")(
        real, note)
    try:
        made = {}
        for way in WAYS:
            _right_click(ns)
            _pick(ns, way)
            assert not G.QuestWaysOpen()
            assert _saved(st) == was, way  # (the saved options untouched)
            made[way] = (_names(ns), calls[-1], N.QuestLevelOrder(), [bool(N.stops[i].turnin) for i in
                                                                      range(1, len(N.stops) + 1)])
    finally:
        ns.Layers.QuestStops = real
    # turn-ins only: the finished quest's turn-in alone; objectives only: no turn-in
    assert made["turnins"][0] == ["Turn in: Letter"] and all(made["turnins"][3])
    assert made["objectives"][0] == ["Boars", "Spiders", "Wolves"] and not any(made["objectives"][3])
    # tracked only: the tracked quests; this zone only: the zone's (asked of the quest log so)
    assert made["tracked"][0] == ["Spiders", "Wolves"] and made["tracked"][1] == (False, True)
    assert made["zone"][1] == (True, False)
    # fastest order, all quests: no level order, whatever is saved; every quest
    assert made["fastest"][2] is None and made["fastest"][1] == (False, False) and len(made["fastest"][0]) == 4
    # by level: its order for this route; the other ways keep the saved one
    assert made["low"][2] == "low" and made["gray"][2] == "gray"
    assert made["tracked"][2] == (None if saved_level == "off" else "low")


def test_lowest_level_first_puts_the_low_quests_first(menu):
    lua, ns = menu
    N, st = ns.Nav, ns.settings.gps
    st.fastestOrder = True
    _right_click(ns)
    _pick(ns, "low")
    # levels 10-12 (Wolves, Spiders) before 13-15 (Boars, the Letter's turn-in), each band the fastest order
    assert sorted(_order(ns)[:2]) == ["Spiders", "Wolves"]
    bands = N.QuestBands(N.stops)
    assert bands is not None
    assert st.questLevelOrder == "off"


def test_the_way_holds_on_a_remake_and_a_left_click_goes_back(menu):
    lua, ns = menu
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    _right_click(ns)
    _pick(ns, "turnins")
    assert _names(ns) == ["Turn in: Letter"] and str(N.questWay.id) == "turnins"
    # remade by the Sprint icon, by itself, a /reload: still turn-ins only
    ns.db.questAutoAsked = True
    G.QuestRerouteClick()
    assert _names(ns) == ["Turn in: Letter"]
    st.questAutoReroute = True
    N.MarkQuestRouteStale()
    G.autoQuestPending = None
    G.AutoQuestTick()
    assert _names(ns) == ["Turn in: Letter"]
    N.questWay = None
    N.Restore()
    assert str(N.questWay.id) == "turnins" and str(G.QuestWayNow()) == "turnins"
    # a quest picked up: nothing for a turn-ins only route to add; a quest finished: its turn-in wanted
    assert not N.QuestRouteTakesNew() and N.QuestRouteTakes(603)
    # objectives only: a finished quest's turn-in isn't wanted
    _right_click(ns)
    _pick(ns, "objectives")
    assert not N.QuestRouteTakes(603) and N.QuestRouteTakesNew()
    # a left-click: the saved options again
    b = _qr(ns)
    b._scripts.OnClick(b, "LeftButton")
    assert N.questWay is None and len(_names(ns)) == 4 and N.QuestRouteTakes(603)
    N.Restore()
    assert N.questWay is None


def test_turn_ins_only_with_nothing_finished_says_so(menu, quests):
    lua, ns = menu
    G, N = ns.GPS, ns.Nav
    quests({"id": 611, "title": "Wolves", "dx": 60})
    _right_click(ns)
    _pick(ns, "turnins")
    assert len(N.stops) == 0
    assert any("none of your quests are finished yet" in m for m in quests.said())


def test_left_out_quests_stay_out_whichever_way(menu):
    lua, ns = menu
    G, N = ns.GPS, ns.Nav
    G.groupChoice[603] = "leave"
    for way in ("fastest", "objectives", "low"):
        _right_click(ns)
        _pick(ns, way)
        assert "Boars" not in _names(ns), way


def test_the_default_is_marked(menu):
    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    _right_click(ns)
    marked = [i for i, t in _rows(ns) if t.endswith("(default)|r")]
    assert marked == ["fastest"]
    G.CloseQuestWays()
    st.questLevelOrder, st.questTrackedOnly = "gray", True
    _right_click(ns)
    marked = [i for i, t in _rows(ns) if t.endswith("(default)|r")]
    assert marked == ["gray", "tracked"]


def test_quest_route_options_opens_routing_at_the_quest_route_section(menu):
    lua, ns = menu
    O = ns.Options
    _right_click(ns)
    _pick(ns, "options")
    try:
        assert O.IsShown()
        assert O.CurrentPage() == O.pages.Routing.index
        assert not ns.GPS.QuestWaysOpen() and len(ns.Nav.stops) == 0
    finally:
        lua.execute("if AzerothGPSOptions then AzerothGPSOptions:Hide() end")


def test_with_the_controller_ui_the_menu_is_our_own(menu):
    # (issue #887: the game's menus with an addon's entries got AzerothGPS blocked with the controller UI on)
    lua, ns = menu
    G = ns.GPS
    lua.execute("""
      AGPS_STYLE = { C = C_InputInterfaceStyle, E = Enum.InputDeviceInterfaceType }
      Enum.InputDeviceInterfaceType = { KeyboardAndMouse = 0, Gamepad = 1 }
      C_InputInterfaceStyle = { GetCurrentStyle = function() return 1 end }
      AGPS_GAME_MENUS = 0
      AGPS_OLD_MENU = MenuUtil
      MenuUtil = setmetatable({}, { __index = function() return function() AGPS_GAME_MENUS = AGPS_GAME_MENUS + 1 end end })
      AGPS_OLD_CF = CreateFrame
      CreateFrame = function(kind, name, parent, template)
        if kind == "DropdownButton" or (template and tostring(template):find("Dropdown")) then
          AGPS_GAME_MENUS = AGPS_GAME_MENUS + 1
        end
        return AGPS_OLD_CF(kind, name, parent, template)
      end
    """)
    try:
        assert G.ControllerUI()
        G.questWays = None  # (made afresh under the controller UI)
        _right_click(ns)
        assert G.QuestWaysOpen() and lua.eval("AGPS_GAME_MENUS") == 0
        _pick(ns, "tracked")
        assert _names(ns) == ["Spiders", "Wolves"] and lua.eval("AGPS_GAME_MENUS") == 0
    finally:
        lua.execute("""
          CreateFrame = AGPS_OLD_CF
          MenuUtil = AGPS_OLD_MENU
          C_InputInterfaceStyle, Enum.InputDeviceInterfaceType = AGPS_STYLE.C, AGPS_STYLE.E
        """)


def test_no_game_menu_in_the_code():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "QuestWays.lua").read_text(encoding="utf-8")
    code = "\n".join(line.split("--")[0] for line in src.splitlines())
    for name in ("MenuUtil", "DropdownButton", "SetupMenu", "EasyMenu", "UIDropDownMenu", "StaticPopup"):
        assert name not in code, name


@pytest.mark.parametrize("where,point,rel", [("menuUp", "BOTTOMLEFT", "BOTTOMRIGHT"),
                                             ("barUp", "BOTTOMLEFT", "BOTTOMRIGHT"),
                                             ("menuRight", "BOTTOMLEFT", "TOPLEFT"),
                                             ("barRight", "BOTTOMLEFT", "TOPLEFT")])
def test_it_opens_beside_the_button_wherever_it_is(menu, where, point, rel):
    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    quick = st.quick
    lua.execute("AGPS_NS.settings.gps.quick = {}")
    st.quick.questRoute = where
    try:
        G.LayoutQuick()
        t = next(t for t in G.QUICK.values() if t.id == "questRoute")
        assert str(t.where) == where
        if G.mapMenu:
            G.mapMenu.Show(G.mapMenu)
        _right_click(ns)
        m = G.questWays
        assert G.QuestWaysOpen()
        p = m._pts[point]
        assert lua.eval("rawequal")(p[2], _qr(ns)) and p[3] == rel
        # its button gone (the map menu shut, the map closed): the menu with it
        _qr(ns)._shown = False
        m._scripts.OnUpdate(m, 0.1)
        assert not G.QuestWaysOpen()
    finally:
        _qr(ns)._shown = True
        st.quick = quick
        G.LayoutQuick()


def test_it_works_in_world_map_mode(menu):
    from test_world_map_host import SETUP

    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    was = (st.useWorldMap, st.shown, st.minimized)
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        _right_click(ns)
        assert G.QuestWaysOpen()
        _pick(ns, "tracked")
        assert _names(ns) == ["Spiders", "Wolves"]
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        st.useWorldMap, st.shown, st.minimized = was
        G.ApplySettings()


def test_it_works_on_the_map_grown_out_of_the_minimap_square(menu):
    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    lua.execute(MM_SETUP)
    keep = st.replaceMinimapKeepSquare
    st.replaceMinimapKeepSquare = False
    try:
        _expand_setup(lua)
        st.replaceMinimap = True
        G.ApplySettings()
        G.SetMinimapExpanded(True)
        _tick(lua, ns)
        assert G.mmState.expanded
        _right_click(ns)
        assert G.QuestWaysOpen()
        _pick(ns, "turnins")
        assert _names(ns) == ["Turn in: Letter"]
    finally:
        st.replaceMinimap = False
        G.ApplySettings()
        st.replaceMinimapKeepSquare = keep
        lua.execute(MM_TEARDOWN)
        G.ApplySettings()


def test_the_slash_command_takes_a_way(menu, quests):
    lua, ns = menu
    N = ns.Nav
    run = lua.eval("function(m) SlashCmdList.AZEROTHGPS(m) end")
    run("questroute turnins")
    assert _names(ns) == ["Turn in: Letter"]
    run("questroute tracked")
    assert _names(ns) == ["Spiders", "Wolves"]
    run("questroute sideways")
    assert any("Quest Route ways:" in m for m in quests.said()) and _names(ns) == ["Spiders", "Wolves"]
    run("questroute")
    assert len(_names(ns)) == 4 and N.questWay is None
