"""The Quest Route button's right-click: toggle icons that pop out of it as Quick Find's do, the player's saved Quest Route
options (1.3.14; the whole addon, gameharness).

Kooki3z 2026-11-22: "lets extend the quest route button with a sub menu to route in different ways like by level, turn
ins only, tracked quest only, etc"; then "make these quick buttons that can be toggled on/off. If any of them conflict
with another auto turn it on/off like picking turn-ins only and tracked quests only for example, only 1 should be on
at a time or both off"; then, of the text menu that was: "this still isn't sub menu buttons, should be like the ammo
button, expand into more icons with on/off toggles".

- Left-click: the quest route by the saved Quest Route options. Right-click: round icon buttons (Quick Find's,
  G.NewRoundButton; never the game's menus: issue #887) out from the button the way Quick Find's go, one each for
  Fastest order, Lowest level first, About to turn gray first, Turn-ins only, Objectives only, Tracked quests only,
  This zone only, and Quest Route options. On: full color in a lit gold ring; off: gray and dimmed. A tooltip each: its
  name, what it does, On or Off.
- Each toggle is a saved setting (QuestWays.lua): Options > Routing > Quest Route is its home, the icons a second
  control; one changes the other. Groups: the level order (Fastest order = neither), and turn-ins only / objectives
  only / tracked quests only, at most one on; this zone only combines with anything.
- A toggle on a quest route makes it again at once; on any other route (or none) it's only saved. The icons stay out
  after a toggle; a click elsewhere, the button again, Escape (the icons only), the button gone, or GROUP_IDLE
  untouched (as Quick Find) puts them away.
- They come out wherever the button is: the column going up, the row going right, the world map, the map grown out of
  the minimap square.

The quest log is test_quest_route_choices.py's stub: its quests around Brill on Tirisfal Glades' map.
"""

import pytest

from test_map_redraw import MM_SETUP, MM_TEARDOWN, _expand_setup, _tick
from test_quest_route_choices import BRILL, _names, _order, game, quests  # noqa: F401

WAYS = ["fastest", "low", "gray", "turnins", "objectives", "tracked", "zone"]
ALL4 = ["Boars", "Spiders", "Turn in: Letter", "Wolves"]
ICONS = {
    "fastest": "Interface\\Icons\\INV_Boots_02",
    "low": "Interface\\Icons\\Spell_ChargePositive",
    "gray": "Interface\\Icons\\INV_Misc_Bone_HumanSkull_01",
    "turnins": "Interface\\GossipFrame\\ActiveQuestIcon",
    "objectives": "Interface\\GossipFrame\\AvailableQuestIcon",
    "tracked": "Interface\\Icons\\INV_Misc_Eye_01",
    "zone": "Interface\\Icons\\INV_Misc_Map_01",
    "options": "Interface\\Icons\\INV_Misc_Gear_01",
}


def _qr(ns):
    return ns.GPS.questRouteButton


def _right_click(ns):
    b = _qr(ns)
    b._scripts.OnClick(b, "RightButton")


def _left_click(ns):
    b = _qr(ns)
    b._scripts.OnClick(b, "LeftButton")


def _icons(ns):
    """The icons out, in their order from the button."""
    b = ns.GPS.QuestWaysButtons()
    return [b[i] for i in range(1, len(b) + 1)]


def _icon(ns, way):
    (b,) = [b for b in _icons(ns) if b.id == way]
    return b


def _pick(ns, way):
    b = _icon(ns, way)
    b._scripts.OnClick(b, "LeftButton")


def _lit(b):
    """How an icon looks: True on (full color, the gold ring lit), False off (gray, dimmed, no ring), None neither."""
    ring, tex = bool(b.ring._shown), b.iconTex
    if ring and not tex._desat and tex._alpha == 1:
        return True
    if not ring and tex._desat and tex._alpha < 0.6:
        return False
    return None


def _checked(ns):
    """The ids whose icon shows on, as drawn (each toggle's icon on or off, never in between)."""
    out = []
    for b in _icons(ns):
        if b.id == "options":
            assert not b.ring._shown and not b.iconTex._desat
            continue
        look = _lit(b)
        assert look is not None, b.id
        if look:
            out.append(str(b.id))
    return out


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


def test_right_click_pops_out_the_toggle_icons_and_left_click_is_the_route_by_them(menu):
    lua, ns = menu
    G, N = ns.GPS, ns.Nav
    same = lua.eval("rawequal")
    b = _qr(ns)
    assert b is not None and same(b, next(t.button for t in G.QUICK.values() if t.id == "questRoute"))
    _right_click(ns)
    assert G.QuestWaysOpen() and len(N.stops) == 0  # (the icons only: no route yet)
    icons = _icons(ns)
    assert [str(i.id) for i in icons] == WAYS + ["options"]
    for i in icons:
        # Quick Find's round buttons: the round frame and a round icon, on the button's own parent, its picture each
        assert i.agpsArt is not None and i.agpsArt.units == 26 and i.agpsArt.mask is not None
        assert same(i.GetParent(i), b.GetParent(b))
        assert str(i.iconTex.agpsSrc) == ICONS[str(i.id)], i.id  # (drawn at its size where shipped so)
    texts = {str(i.id): str(i.text) for i in icons}
    assert texts["fastest"] == "Fastest order" and texts["turnins"] == "Turn-ins only"
    assert texts["options"] == "Quest Route options..."
    # the saved options as lit icons: by default only Fastest order; Quest Route options is neither
    assert _checked(ns) == ["fastest"]
    # right-click again: in; a click anywhere else puts them in too
    _right_click(ns)
    assert not G.QuestWaysOpen() and not any(i._shown for i in icons)
    _right_click(ns)
    G.questWays.catch._scripts.OnClick(G.questWays.catch, "LeftButton")
    assert not G.QuestWaysOpen() and len(N.stops) == 0
    # left-click: the quest route by the saved options (every quest), the icons in
    _right_click(ns)
    _left_click(ns)
    assert not G.QuestWaysOpen()
    assert _names(ns) == ALL4
    # with a toggle on, a left-click routes by it
    ns.settings.gps.questTurninsOnly = True
    N.Clear()
    _left_click(ns)
    assert _names(ns) == ["Turn in: Letter"]


def test_no_text_menu_is_left():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "QuestWays.lua").read_text(encoding="utf-8")
    code = "\n".join(line.split("--")[0] for line in src.splitlines())
    for gone in ("CreateFontString", "QUEST_WAYS_ROW", "QuestWayRows", "SetColorTexture"):
        assert gone not in code, gone
    assert "G.NewRoundButton(" in code


def test_a_click_on_the_button_itself_while_out_routes(menu):
    # (the click-catcher lies over the Quest Route button too: a left-click there is still its left-click)
    lua, ns = menu
    G = ns.GPS
    _right_click(ns)
    lua.execute("AGPS_NS.GPS.questRouteButton.IsMouseOver = function() return true end")
    try:
        G.questWays.catch._scripts.OnClick(G.questWays.catch, "LeftButton")
        assert not G.QuestWaysOpen() and _names(ns) == ALL4
        ns.Nav.Clear()
        _right_click(ns)
        G.questWays.catch._scripts.OnClick(G.questWays.catch, "RightButton")  # (right: in, as the button's toggle)
        assert not G.QuestWaysOpen() and len(ns.Nav.stops) == 0
    finally:
        lua.execute("AGPS_NS.GPS.questRouteButton.IsMouseOver = nil")


def test_the_tooltips_name_say_what_and_on_or_off(menu):
    lua, ns = menu
    G = ns.GPS
    lines = []
    lua.execute("AGPS_OLD_TIP = { S = GameTooltip.SetText, A = GameTooltip.AddLine }")
    lua.globals().GameTooltip.SetText = lambda self, text, *a: lines.append(("title", str(text)))
    lua.globals().GameTooltip.AddLine = lambda self, text, *a: lines.append(("line", str(text)))
    try:
        b = _qr(ns)
        b._scripts.OnEnter(b)
        assert ("line", "Right-click to choose how it routes.") in lines
        _right_click(ns)
        for way, name, on in (("fastest", "Fastest order", True), ("turnins", "Turn-ins only", False)):
            lines.clear()
            i = _icon(ns, way)
            i._scripts.OnEnter(i)
            assert lines[0] == ("title", name) and len(lines) == 3, lines
            assert lines[2] == ("line", "On" if on else "Off")
            tip = lua.globals().GameTooltip
            assert lua.eval("rawequal")(tip.GetOwner(tip), i)
        lines.clear()
        i = _icon(ns, "fastest")
        i._scripts.OnEnter(i)
        assert lines[1] == ("line", "Your quests in the fastest order, whatever their level. Turns off the level orders.")
        # clicked: its tooltip says so at once
        lines.clear()
        t = _icon(ns, "turnins")
        t._scripts.OnEnter(t)
        lines.clear()
        _pick(ns, "turnins")
        assert ("line", "On") in lines
        # Quest Route options: no On or Off
        lines.clear()
        o = _icon(ns, "options")
        o._scripts.OnEnter(o)
        assert lines[0] == ("title", "Quest Route options...") and ("line", "On") not in lines
        assert ("line", "Off") not in lines and "Options > Routing > Quest Route" in lines[1][1]
    finally:
        lua.execute("GameTooltip.SetText, GameTooltip.AddLine = AGPS_OLD_TIP.S, AGPS_OLD_TIP.A")


def test_a_toggle_is_saved_and_the_icons_stay_out(menu):
    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    _right_click(ns)
    _pick(ns, "turnins")
    assert G.QuestWaysOpen() and st.questTurninsOnly is True and "turnins" in _checked(ns)
    _pick(ns, "zone")
    assert G.QuestWaysOpen() and st.questZoneOnly is True and _checked(ns) == ["fastest", "turnins", "zone"]
    # in and out again: as saved
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
                _pick(ns, b)  # (turning another on turns this one off, its icon gray at once)
                assert [w for w in what if w in _on(ns)] == [b] and [w for w in what if w in _checked(ns)] == [b]
            _pick(ns, b)  # (and off: none on)
            assert not [w for w in what if w in _on(ns)] and not [w for w in what if w in _checked(ns)]
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
    assert _on(ns) == ["fastest", "tracked", "zone"] and _checked(ns) == ["fastest", "tracked", "zone"]


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
    assert G.QuestWaysOpen()  # (out the whole time)


def test_a_toggle_doesnt_touch_another_route(menu):
    lua, ns = menu
    N = ns.Nav
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


def test_the_options_page_and_the_icons_stay_in_sync(menu):
    lua, ns = menu
    O, st = ns.Options, ns.settings.gps
    O.Show()
    try:
        ctl = {c.key: c.control for c in O.settingControls.values() if not c.mirror}

        def click(key, on):
            cb = ctl[key]
            cb.SetChecked(cb, on)
            cb._scripts.OnClick(cb)

        _right_click(ns)
        # the options' check box: the icons show it at once, the others of its group off
        click("questTrackedOnly", True)
        assert "tracked" in _checked(ns)
        click("questTurninsOnly", True)
        assert st.questTurninsOnly is True and st.questTrackedOnly is False
        assert [w for w in ("turnins", "objectives", "tracked") if w in _checked(ns)] == ["turnins"]
        assert ctl["questTrackedOnly"].GetChecked(ctl["questTrackedOnly"]) is False
        click("questObjectivesOnly", True)
        assert st.questTurninsOnly is False and [w for w in ("turnins", "objectives") if w in _checked(ns)] == ["objectives"]
        # an icon: the options' check boxes follow
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


def test_escape_puts_in_only_the_icons(menu):
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


def test_they_go_in_as_quick_finds_do_untouched(menu):
    lua, ns = menu
    G = ns.GPS
    was = _qr(ns)._shown
    _qr(ns)._shown = True  # (the button on screen)
    try:
        _idle(lua, ns)
    finally:
        _qr(ns)._shown = was


def _idle(lua, ns):
    G = ns.GPS
    _right_click(ns)
    m = G.questWays
    m._scripts.OnUpdate(m, G.GROUP_IDLE - 1)
    assert G.QuestWaysOpen()
    # the mouse over one: the clock starts again
    i = _icon(ns, "zone")
    lua.execute("AGPS_OVER = true")
    i.IsMouseOver = lua.eval("function() return AGPS_OVER end")
    try:
        m._scripts.OnUpdate(m, G.GROUP_IDLE - 1)
        assert G.QuestWaysOpen() and m.idle == 0
    finally:
        i.IsMouseOver = None
    m._scripts.OnUpdate(m, G.GROUP_IDLE - 1)
    assert G.QuestWaysOpen()
    m._scripts.OnUpdate(m, 1.5)
    assert not G.QuestWaysOpen() and not any(b._shown for b in m.buttons.values())


def test_one_flyout_out_at_a_time(menu):
    lua, ns = menu
    G = ns.GPS
    G.SetQuickFindOpen(True)
    _right_click(ns)
    assert G.QuestWaysOpen() and not G.quickFindOpen
    G.SetQuickFindOpen(True)
    assert not G.QuestWaysOpen()
    G.SetQuickFindOpen(False)


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


def test_with_the_controller_ui_the_icons_are_our_own(menu):
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
    keep = G.questWays
    try:
        assert G.ControllerUI()
        G.questWays = None  # (made afresh under the controller UI)
        _left_click(ns)
        _right_click(ns)
        assert G.QuestWaysOpen() and lua.eval("AGPS_GAME_MENUS") == 0 and len(_icons(ns)) == 8
        _pick(ns, "tracked")
        assert _names(ns) == ["Spiders", "Wolves"] and lua.eval("AGPS_GAME_MENUS") == 0
        assert "tracked" in _checked(ns)
    finally:
        G.CloseQuestWays()
        G.questWays = keep
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


def _point(b):
    """(point, the frame it's on, its point, x, y) of a button placed by one point."""
    (p,) = [v for v in b._pts.values()]
    return str(p[1]), p[2], str(p[3]), p[4], p[5]


@pytest.mark.parametrize("where", ["menuUp", "barUp", "menuRight", "barRight"])
def test_they_come_out_as_quick_finds_wherever_the_button_is(menu, where):
    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    same = lua.eval("rawequal")
    quick = st.quick
    lua.execute("AGPS_NS.settings.gps.quick = {}")
    st.quick.questRoute = where
    st.quick.quickFind = where
    try:
        G.LayoutQuick()
        t = next(t for t in G.QUICK.values() if t.id == "questRoute")
        f = next(t for t in G.QUICK.values() if t.id == "quickFind")
        was_f = f.button._shown
        assert str(t.where) == where and str(f.where) == where
        if G.mapMenu:
            G.mapMenu.Show(G.mapMenu)
        t.button._shown = f.button._shown = True  # (the map's buttons as on screen)
        # Quick Find's flyout from its button, for the way and the spacing
        G.SetQuickFindOpen(True)
        qf = G.QuickFindEntries()
        qf = [G.quickFindButtons[qf[i].kind] for i in range(1, len(qf) + 1)]
        want = [(p, r, x, y) for p, _, r, x, y in map(_point, qf)]
        _right_click(ns)
        assert G.QuestWaysOpen() and not G.quickFindOpen
        icons = _icons(ns)
        got = [_point(i) for i in icons]
        assert all(same(g[1], _qr(ns)) for g in got)
        got = [(p, r, x, y) for p, _, r, x, y in got]
        assert got[:len(want)] == want
        sideways = where.endswith("Up")
        step = G.QUICK_STEP_BAR if sideways else G.QUICK_STEP_MENU
        for j, (p, r, x, y) in enumerate(got):
            assert (p, r) == (("LEFT", "RIGHT") if sideways else ("BOTTOM", "TOP"))
            assert (x if sideways else y) == 4 + j * step and (y if sideways else x) == 0
        # over the click-catcher, which lies over everything else
        for i in icons:
            assert i._strata == G.questWays.catch._strata == "FULLSCREEN_DIALOG" and i._level > G.questWays.catch._level
        # its button gone (the map menu shut, the map closed): the icons with it
        _qr(ns)._shown = False
        G.questWays._scripts.OnUpdate(G.questWays, 0.1)
        assert not G.QuestWaysOpen()
    finally:
        _qr(ns)._shown = True
        f.button._shown = was_f
        G.SetQuickFindOpen(False)
        st.quick = quick
        G.LayoutQuick()


def test_it_works_in_world_map_mode(menu):
    from test_world_map_host import SETUP

    lua, ns = menu
    G, st = ns.GPS, ns.settings.gps
    same = lua.eval("rawequal")
    lua.execute(SETUP)
    was = (st.useWorldMap, st.shown, st.minimized)
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        _left_click(ns)
        _right_click(ns)
        assert G.QuestWaysOpen() and len(_icons(ns)) == 8
        assert all(same(i.GetParent(i), _qr(ns).GetParent(_qr(ns))) for i in _icons(ns))
        _pick(ns, "tracked")
        assert _names(ns) == ["Spiders", "Wolves"] and "tracked" in _checked(ns)
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
        assert G.QuestWaysOpen() and len(_icons(ns)) == 8
        _pick(ns, "turnins")
        assert _names(ns) == ["Turn in: Letter"] and "turnins" in _checked(ns)
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
