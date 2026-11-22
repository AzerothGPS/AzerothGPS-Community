"""The Quest Route button's right-click menu: toggles that stay on or off, the player's saved Quest Route options (1.3.14;
the whole addon, gameharness).

Kooki3z 2026-11-22: "lets extend the quest route button with a sub menu to route in different ways like by level, turn
ins only, tracked quest only, etc"; then "make these quick buttons that can be toggled on/off. If any of them conflict
with another auto turn it on/off like picking turn-ins only and tracked quests only for example, only 1 should be on
at a time or both off."

- Left-click: the quest route by the saved Quest Route options. Right-click: our own menu (never the game's menus:
  issue #887) with Fastest order, Lowest level first, About to turn gray first, Turn-ins only, Objectives only, Tracked
  quests only, This zone only (each a check box) and Quest Route options...
- Each toggle is a saved setting (QuestWays.lua): Options > Routing > Quest Route is its home, the menu a second
  control; one changes the other. Groups: the level order (Fastest order = neither), and turn-ins only / objectives
  only / tracked quests only, at most one on; this zone only combines with anything.
- A toggle on a quest route makes it again at once; on any other route (or none) it's only saved. The menu stays open
  after a toggle; a click elsewhere, the button again or Escape (the menu only) shuts it.
- It opens beside the button wherever the button is: the column going up, the row going right, the world map, the map
  grown out of the minimap square.

The quest log is test_quest_route_choices.py's stub: its quests around Brill on Tirisfal Glades' map.
"""

import pytest

from test_map_redraw import MM_SETUP, MM_TEARDOWN, _expand_setup, _tick
from test_quest_route_choices import BRILL, _names, _order, game, quests  # noqa: F401

WAYS = ["fastest", "low", "gray", "turnins", "objectives", "tracked", "zone"]
ALL4 = ["Boars", "Spiders", "Turn in: Letter", "Wolves"]


def _qr(ns):
    return ns.GPS.questRouteButton


def _right_click(ns):
    b = _qr(ns)
    b._scripts.OnClick(b, "RightButton")


def _left_click(ns):
    b = _qr(ns)
    b._scripts.OnClick(b, "LeftButton")


def _rows(ns):
    m = ns.GPS.questWays
    return [(str(r.id), str(r.text._text)) for r in m.rows.values() if r._shown]


def _row(ns, way):
    m = ns.GPS.questWays
    (row,) = [r for r in m.rows.values() if r._shown and r.id == way]
    return row


def _pick(ns, way):
    row = _row(ns, way)
    row._scripts.OnClick(row, "LeftButton")


def _checked(ns):
    """The ids whose check box shows on, as the menu draws them."""
    m = ns.GPS.questWays
    return [str(r.id) for r in m.rows.values() if r._shown and r.check._shown]


def _on(ns):
    """The toggles on by the saved options."""
    return [w for w in WAYS if ns.GPS.QuestToggleOn(w)]


def _saved(st):
    return (st.questLevelOrder, st.questZoneOnly, st.questTrackedOnly, st.questTurninsOnly, st.questObjectivesOnly)


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


def test_right_click_opens_the_toggles_and_left_click_is_the_route_by_them(menu):
    lua, ns = menu
    G, N = ns.GPS, ns.Nav
    b = _qr(ns)
    assert b is not None and lua.eval("rawequal")(b, next(t.button for t in G.QUICK.values() if t.id == "questRoute"))
    _right_click(ns)
    assert G.QuestWaysOpen() and len(N.stops) == 0  # (the menu only: no route yet)
    assert [i for i, _ in _rows(ns)] == WAYS + ["options"]
    texts = dict(_rows(ns))
    assert texts["fastest"] == "Fastest order" and texts["turnins"] == "Turn-ins only"
    assert texts["options"] == "Quest Route options..."
    assert not any("(default)" in t for t in texts.values())
    # the saved options as check boxes: by default only Fastest order; Quest Route options... has none
    assert _checked(ns) == ["fastest"]
    assert all(_row(ns, w).box._shown for w in WAYS) and not _row(ns, "options").box._shown
    # right-click again: shut; a click anywhere else shuts it too
    _right_click(ns)
    assert not G.QuestWaysOpen()
    _right_click(ns)
    G.questWays.catch._scripts.OnClick(G.questWays.catch, "LeftButton")
    assert not G.QuestWaysOpen()
    # left-click: the quest route by the saved options (every quest), the menu shut
    _right_click(ns)
    _left_click(ns)
    assert not G.QuestWaysOpen()
    assert _names(ns) == ALL4
    # with a toggle on, a left-click routes by it
    ns.settings.gps.questTurninsOnly = True
    N.Clear()
    _left_click(ns)
    assert _names(ns) == ["Turn in: Letter"]


def test_the_tooltip_says_right_click_to_choose(menu):
    lua, ns = menu
    b = _qr(ns)
    lines = []
    lua.execute("AGPS_OLD_ADD = GameTooltip.AddLine")
    lua.globals().GameTooltip.AddLine = lambda self, text, *a: lines.append(str(text))
    try:
        b._scripts.OnEnter(b)
    finally:
        lua.execute("GameTooltip.AddLine = AGPS_OLD_ADD")
    assert "Right-click to choose how it routes." in lines


def test_a_toggle_is_saved_and_the_menu_stays_open(menu):
    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    _right_click(ns)
    _pick(ns, "turnins")
    assert G.QuestWaysOpen() and st.questTurninsOnly is True and "turnins" in _checked(ns)
    _pick(ns, "zone")
    assert G.QuestWaysOpen() and st.questZoneOnly is True and _checked(ns) == ["fastest", "turnins", "zone"]
    # shut and opened again: as saved
    G.CloseQuestWays()
    _right_click(ns)
    assert _checked(ns) == ["fastest", "turnins", "zone"]
    # clicked again: off
    _pick(ns, "turnins")
    _pick(ns, "zone")
    assert st.questTurninsOnly is False and st.questZoneOnly is False and _checked(ns) == ["fastest"]


def test_whats_routed_is_one_at_most(menu):
    lua, ns = menu
    st = ns.settings.gps
    _right_click(ns)
    what = ["turnins", "objectives", "tracked"]
    for a in what:
        for b in what:
            _pick(ns, a)
            if not ns.GPS.QuestToggleOn(a):
                _pick(ns, a)
            assert [w for w in what if w in _on(ns)] == [a]
            if b != a:
                _pick(ns, b)  # (turning another on turns this one off)
                assert [w for w in what if w in _on(ns)] == [b] and [w for w in what if w in _checked(ns)] == [b]
            _pick(ns, b)  # (and off: none on)
            assert not [w for w in what if w in _on(ns)]
    # Kooki3z's example: turn-ins only, then tracked quests only
    _pick(ns, "turnins")
    _pick(ns, "tracked")
    assert st.questTrackedOnly is True and st.questTurninsOnly is False and st.questObjectivesOnly is False


def test_the_level_order_and_fastest(menu):
    lua, ns = menu
    st = ns.settings.gps
    _right_click(ns)
    order = ["fastest", "low", "gray"]
    assert [w for w in order if w in _checked(ns)] == ["fastest"]
    # Fastest order clicked while on: stays on, nothing changes
    _pick(ns, "fastest")
    assert st.questLevelOrder == "off" and [w for w in order if w in _checked(ns)] == ["fastest"]
    # a level order on: Fastest off; the other level order turns it off
    _pick(ns, "low")
    assert st.questLevelOrder == "low" and [w for w in order if w in _checked(ns)] == ["low"]
    _pick(ns, "gray")
    assert st.questLevelOrder == "gray" and [w for w in order if w in _checked(ns)] == ["gray"]
    # Fastest order on: both level orders off
    _pick(ns, "fastest")
    assert st.questLevelOrder == "off" and [w for w in order if w in _checked(ns)] == ["fastest"]
    # a level order turned off by itself: Fastest again
    _pick(ns, "gray")
    _pick(ns, "gray")
    assert st.questLevelOrder == "off" and [w for w in order if w in _checked(ns)] == ["fastest"]


def test_this_zone_only_combines_with_anything(menu):
    lua, ns = menu
    _right_click(ns)
    _pick(ns, "zone")
    for w in ("low", "turnins", "gray", "objectives", "tracked", "fastest"):
        _pick(ns, w)
        assert "zone" in _on(ns) and w in _on(ns), w
    assert _on(ns) == ["fastest", "tracked", "zone"]


def test_a_toggle_remakes_the_quest_route_at_once(menu):
    lua, ns = menu
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    st.fastestOrder = True
    _left_click(ns)
    assert _names(ns) == ALL4
    _right_click(ns)
    turnin = lambda: [bool(N.stops[i].turnin) for i in range(1, len(N.stops) + 1)]  # noqa: E731
    _pick(ns, "turnins")
    assert _names(ns) == ["Turn in: Letter"] and all(turnin())
    assert not N.QuestRouteTakesNew() and N.QuestRouteTakes(603)
    _pick(ns, "objectives")
    assert _names(ns) == ["Boars", "Spiders", "Wolves"] and not any(turnin())
    assert not N.QuestRouteTakes(603) and N.QuestRouteTakesNew()
    _pick(ns, "tracked")
    assert _names(ns) == ["Spiders", "Wolves"]
    _pick(ns, "tracked")
    assert _names(ns) == ALL4 and N.QuestRouteTakes(603)
    # by level: lowest first, levels 10-12 (Wolves, Spiders) before 13-15 (Boars, the Letter's turn-in)
    _pick(ns, "low")
    assert N.QuestLevelOrder() == "low" and N.QuestBands(N.stops) is not None
    assert sorted(_order(ns)[:2]) == ["Spiders", "Wolves"]
    _pick(ns, "fastest")
    assert N.QuestLevelOrder() is None
    assert G.QuestWaysOpen()  # (open the whole time)


def test_a_toggle_doesnt_touch_another_route(menu):
    lua, ns = menu
    G, N = ns.GPS, ns.Nav
    # no route: only saved
    _right_click(ns)
    _pick(ns, "turnins")
    assert len(N.stops) == 0 and ns.settings.gps.questTurninsOnly is True
    # a route of the player's own stops: kept as it is
    N.SetStops(lua.eval(f"{{ {{ x = {BRILL[0] + 300}, y = {BRILL[1]}, cont = 0, name = 'Mine' }} }}"), True)
    assert _order(ns) == ["Mine"] and not N.OnQuestRoute()
    _pick(ns, "objectives")
    _pick(ns, "low")
    assert _order(ns) == ["Mine"] and ns.settings.gps.questObjectivesOnly is True


def test_turn_ins_only_with_nothing_finished_says_so(menu, quests):
    lua, ns = menu
    N = ns.Nav
    quests({"id": 611, "title": "Wolves", "dx": 60})
    _right_click(ns)
    _pick(ns, "turnins")
    _left_click(ns)
    assert len(N.stops) == 0
    assert any("none of your quests are finished yet" in m for m in quests.said())


def test_left_out_quests_stay_out_whichever_toggle(menu):
    lua, ns = menu
    G = ns.GPS
    G.groupChoice[603] = "leave"
    _left_click(ns)
    _right_click(ns)
    for way in ("objectives", "low", "zone"):
        _pick(ns, way)
        assert "Boars" not in _names(ns) and len(_names(ns)) > 0, way


def test_the_options_page_and_the_menu_stay_in_sync(menu):
    lua, ns = menu
    G, O, st = ns.GPS, ns.Options, ns.settings.gps
    O.Show()
    try:
        ctl = {c.key: c.control for c in O.settingControls.values() if not c.mirror}

        def click(key, on):
            cb = ctl[key]
            cb.SetChecked(cb, on)
            cb._scripts.OnClick(cb)

        _right_click(ns)
        # the options' check box: the menu shows it at once, the others of its group off
        click("questTrackedOnly", True)
        assert "tracked" in _checked(ns)
        click("questTurninsOnly", True)
        assert st.questTurninsOnly is True and st.questTrackedOnly is False
        assert [w for w in ("turnins", "objectives", "tracked") if w in _checked(ns)] == ["turnins"]
        assert ctl["questTrackedOnly"].GetChecked(ctl["questTrackedOnly"]) is False
        click("questObjectivesOnly", True)
        assert st.questTurninsOnly is False and [w for w in ("turnins", "objectives") if w in _checked(ns)] == ["objectives"]
        # the menu's toggle: the options' check boxes follow
        _pick(ns, "tracked")
        assert ctl["questTrackedOnly"].GetChecked(ctl["questTrackedOnly"]) is True
        assert ctl["questObjectivesOnly"].GetChecked(ctl["questObjectivesOnly"]) is False
        _pick(ns, "zone")
        assert ctl["questZoneOnly"].GetChecked(ctl["questZoneOnly"]) is True
        click("questZoneOnly", False)
        assert "zone" not in _checked(ns)
        # the level order's choice, both ways
        _pick(ns, "gray")
        radios = ctl["questLevelOrder"]
        assert [bool(radios[i].GetChecked(radios[i])) for i in range(1, len(radios) + 1)] == [False, False, True]
        r = radios[2]  # (Lowest level first)
        r._scripts.OnClick(r)
        assert st.questLevelOrder == "low" and [w for w in ("fastest", "low", "gray") if w in _checked(ns)] == ["low"]
    finally:
        lua.execute("if AzerothGPSOptions then AzerothGPSOptions:Hide() end")


def test_escape_shuts_only_the_menu(menu):
    lua, ns = menu
    G = ns.GPS
    lua.execute("AGPS_NS.settings.gps.shown = true")
    _right_click(ns)
    m = G.questWays
    assert m._keyboard is True and m._propagate is True  # (other keys go on to the game)
    m._scripts.OnKeyDown(m, "W")
    assert G.QuestWaysOpen() and m._propagate is True
    m._scripts.OnKeyDown(m, "ESCAPE")
    assert not G.QuestWaysOpen() and m._propagate is False  # (taken: not the game's menu, nor the map)
    # in combat the keys can't be taken: none are, so none are kept from the game
    lua.execute("AGPS_OLD_ICL = InCombatLockdown InCombatLockdown = function() return true end")
    try:
        _right_click(ns)
        assert m._keyboard is False
        m._scripts.OnKeyDown(m, "ESCAPE")
        assert not G.QuestWaysOpen()
    finally:
        lua.execute("InCombatLockdown = AGPS_OLD_ICL")


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
        _left_click(ns)
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
        _left_click(ns)
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
        _left_click(ns)
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


def test_the_slash_command_sets_a_toggle_and_routes(menu, quests):
    lua, ns = menu
    st = ns.settings.gps
    run = lua.eval("function(m) SlashCmdList.AZEROTHGPS(m) end")
    run("questroute turnins")  # (no route before: one made)
    assert st.questTurninsOnly is True and _names(ns) == ["Turn in: Letter"]
    run("questroute turnins")  # (set, not flipped: the same each time)
    assert st.questTurninsOnly is True and _names(ns) == ["Turn in: Letter"]
    run("questroute tracked")  # (its group: turn-ins only off)
    assert st.questTrackedOnly is True and st.questTurninsOnly is False and _names(ns) == ["Spiders", "Wolves"]
    run("questroute tracked off")
    assert st.questTrackedOnly is False and _names(ns) == ALL4
    run("questroute grey")
    assert st.questLevelOrder == "gray"
    run("questroute fastest")
    assert st.questLevelOrder == "off"
    run("questroute sideways")
    assert any("Quest Route ways:" in m for m in quests.said()) and _names(ns) == ALL4
    ns.Nav.Clear()
    run("questroute")
    assert _names(ns) == ALL4


def test_the_toggles_survive_a_reload(game):
    # toggled in one session; its saved variables (the game writes AzerothGPSDB out) read by the next one
    from azerothgps.gameharness import start

    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    was = _saved(st)
    try:
        for k, v in (("questLevelOrder", "off"), ("questZoneOnly", False), ("questTrackedOnly", False),
                     ("questTurninsOnly", False), ("questObjectivesOnly", False)):
            st[k] = v
        _right_click(ns)
        _pick(ns, "objectives")
        _pick(ns, "gray")
        _pick(ns, "zone")
        G.CloseQuestWays()
        # (the saved variable's settings, written out as plain values)
        saved = lua.eval("""function()
          local out = {}
          for k, v in pairs(AzerothGPSDB.settings.gps) do
            if type(v) == "boolean" or type(v) == "number" then out[#out + 1] = k .. " = " .. tostring(v)
            elseif type(v) == "string" then out[#out + 1] = k .. " = " .. string.format("%q", v) end
          end
          return "AzerothGPSDB = { settings = { gps = { " .. table.concat(out, ", ") .. " } } }"
        end""")()
        assert "questObjectivesOnly = true" in saved and 'questLevelOrder = "gray"' in saved
        lua2, ns2 = start(saved=saved)
        assert [w for w in WAYS if ns2.GPS.QuestToggleOn(w)] == ["gray", "objectives", "zone"]
        _right_click(ns2)
        assert _checked(ns2) == ["gray", "objectives", "zone"]
    finally:
        (st.questLevelOrder, st.questZoneOnly, st.questTrackedOnly, st.questTurninsOnly, st.questObjectivesOnly) = was
