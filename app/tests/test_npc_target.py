"""The Target button (1.3.14, asked by Kooki3z): the route's next stop an NPC picked in the search (or a pin made from
its row) and the player near it, a "Target <name>" button under the directions panel, and a key for it (Bindings.xml).
The player's own click only: a secure button whose macro is "/targetexact <name>"; AzerothGPS never calls TargetUnit
or any other protected function itself (wowmock.lua's AGPS_PROTECTED lists any call). Set only out of combat, hidden as
combat starts. The same click marks the NPC with the stop's route marker (asked 2026-11-22) when the options allow it
(solo on, party or raid off; a raid with lead or assist only): the macro "/click"s a second secure button whose action
is the game's own "raidtarget" one. Not "/tm": this client runs it as an ordinary, tainted slash command and its
SetRaidTarget refuses that, so 1.3.14's "/tm" line marked nothing ("raid marking isn't working", 2026-11-23).
AzerothGPS never marks or clears a mark itself (SetRaidTarget is restricted in this client)."""

import re
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
NPC_ID = 6741  # (Innkeeper Renee, Brill)
NPC_GUID = f"Creature-0-1-0-1-{NPC_ID}-0000ABCDEF"
TARGET_ONLY = "/targetexact Innkeeper Renee"
# (the target cleared first and "[@target,exists]": with the NPC not found, nothing else is marked. The marker button
# it clicks does the marking, with the stop's icon: its "set-unmarked" leaves a unit with any mark alone, ours from a
# click before included, so a second click never toggles it off)
MARKED = "/cleartarget\n/targetexact Innkeeper Renee\n/click [@target,exists] AzerothGPSTargetMarkButton"
MARK_BTN = "AzerothGPSTargetMarkButton"


def _marker(lua):
    return lua.eval(MARK_BTN)


def _marks_with(lua, icon):
    # (the marker button set to mark the target with raid icon `icon`, never toggling; None: set to do nothing)
    m = _marker(lua)
    if icon is None:
        return m._attr["type"] is None
    return (m._attr["type"] == "raidtarget" and m._attr["marker"] == icon and m._attr["unit"] == "target"
            and m._attr["action"] == "set-unmarked")


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def _at(lua, x, y):
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0")


def _npc_route(lua, ns, x=2264.0, y=300.0, npc=True):
    extra = f", npcId = {NPC_ID}, npcName = 'Innkeeper Renee'" if npc else ""
    ns.Nav.SetStops(lua.eval(f"{{ {{ x = {x}, y = {y}, cont = 0, name = 'Innkeeper Renee'{extra} }} }}"), False, "red")


def _update(lua, ns, t, arrow=False):
    G = ns.GPS
    lua.execute(f"AGPS_T = {t}")
    G.Update()
    G.navPanel.Show(G.navPanel)  # (the map's directions panel up, as with a route worked out)
    if not arrow:
        ns.Arrow.dir.Hide(ns.Arrow.dir)  # (the arrow's directions closed: in the map's panel)
    G.UpdateTargetButton()
    return G.targetBtn


@pytest.fixture()
def clean(game):
    lua, ns = game
    yield lua, ns
    lua.execute("AGPS_GUIDS = nil InCombatLockdown = function() return false end IsInGroup, IsInRaid = nil, nil "
                "UnitIsGroupLeader, UnitIsGroupAssistant = nil, nil")
    ns.settings.gps.targetNpcMarkSolo, ns.settings.gps.targetNpcMarkGroup = True, False
    _at(lua, 2254.0, 293.0)
    ns.settings.gps.targetNpcButton = True
    ns.Nav.Clear()
    ns.GPS.UpdateTargetButton()
    assert not list(lua.eval("AGPS_PROTECTED").values())


def test_the_target_button_shows_near_an_npc_stop_and_targets_it_by_name(clean):
    lua, ns = clean
    _npc_route(lua, ns)
    b = _update(lua, ns, 1000)
    assert b._name == "AzerothGPSTargetButton" and b._parent._name == "UIParent"  # (not the map's: it may hide in combat)
    assert b._shown
    # (solo, the default: marked too, with the stop's route marker, its raid icon: the first stop's is the square, 6)
    assert ns.Nav.stops[1].icon == 6
    assert b._attr["type"] == "macro" and b._attr["macrotext"] == MARKED and _marks_with(lua, 6)
    # (an icon, Hunter's Mark's, the Sprint icon's size; no text)
    assert b.icon._tex in (ns.SpellIcon(ns.GPS.TARGET_NPC_SPELL), ns.GPS.TARGET_NPC_ICON_FILE)
    assert (b._w, b._h) == (ns.GPS.TARGET_NPC_PX, ns.GPS.TARGET_NPC_PX)
    # (this client's secure buttons act on the key's down; an up-only one does nothing)
    assert set(b._clicks.values()) == {"AnyUp", "AnyDown"}
    # (in the map's directions panel: its bottom right corner)
    assert lua.eval("AzerothGPSTargetButton._pts.BOTTOMRIGHT[2] == AGPS_NS.GPS.navPanel")
    # (the stop saved with the route keeps its NPC: the button again after a /reload)
    saved = ns.CharDB().stops[1]
    assert saved.npcId == NPC_ID and saved.npcName == "Innkeeper Renee"


def test_the_target_button_hides_away_from_the_npc_and_without_an_npc_stop(clean):
    lua, ns = clean
    _npc_route(lua, ns)
    G = ns.GPS
    _at(lua, 2264.0 - G.TARGET_NPC_YD - 5, 300.0)  # (45 yd off: never shown from here)
    b = _update(lua, ns, 1100)
    assert not b._shown and b._attr["type"] is None and b._attr["macrotext"] is None
    _at(lua, 2264.0 - 20, 300.0)
    assert _update(lua, ns, 1101)._shown
    _at(lua, 2264.0 - G.TARGET_NPC_YD - 5, 300.0)  # (shown: kept till LEAVE_YD)
    assert _update(lua, ns, 1102)._shown
    _at(lua, 2264.0 - G.TARGET_NPC_LEAVE_YD - 5, 300.0)
    b = _update(lua, ns, 1103)
    assert not b._shown and b._attr["type"] is None  # (no macro: its key does nothing)
    # (a plain stop, not an NPC's: none)
    _at(lua, 2254.0, 293.0)
    _npc_route(lua, ns, npc=False)
    b = _update(lua, ns, 1104)
    assert not b._shown and b._attr["type"] is None
    # (no route: none)
    ns.Nav.Clear()
    ns.GPS.UpdateTargetButton()
    assert not b._shown and b._attr["type"] is None


def test_the_target_button_hides_with_the_npc_targeted_the_panel_hidden_or_the_option_off(clean):
    lua, ns = clean
    _npc_route(lua, ns)
    G, st = ns.GPS, ns.settings.gps
    assert _update(lua, ns, 1200)._shown
    lua.execute(f"AGPS_GUIDS = {{ target = '{NPC_GUID}' }}")  # (targeted already)
    assert not _update(lua, ns, 1201)._shown
    lua.execute("AGPS_GUIDS = { target = 'Creature-0-1-0-1-1234-0000ABCDEF' }")  # (another NPC targeted)
    assert _update(lua, ns, 1202)._shown
    lua.execute("AGPS_GUIDS = { target = AGPS_SECRET }")  # (a hidden GUID: not known to be it)
    assert _update(lua, ns, 1203)._shown
    lua.execute("AGPS_GUIDS = nil")
    G.navPanel.Hide(G.navPanel)  # (the map's directions panel closed: under the arrow's directions instead)
    A = ns.Arrow
    A.dir.Show(A.dir)
    G.UpdateTargetButton()
    assert G.targetBtn._shown and lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.Arrow.dir")
    A.dir.Hide(A.dir)  # (neither shows: hidden, its key still set)
    G.UpdateTargetButton()
    assert not G.targetBtn._shown and G.targetBtn._attr["type"] == "macro"
    st.targetNpcButton = False
    b = _update(lua, ns, 1204)
    assert not b._shown and b._attr["type"] is None


def test_the_target_button_is_hidden_as_combat_starts_and_left_alone_in_it(clean):
    lua, ns = clean
    _npc_route(lua, ns)
    b = _update(lua, ns, 1300)
    assert b._shown
    lua.eval("AGPS_FIRE")("PLAYER_REGEN_DISABLED")
    assert not b._shown and not lua.eval("next(AzerothGPSTargetButton._pts)")  # (anchored to nothing of ours)
    lua.execute("InCombatLockdown = function() return true end AGPS_SET = 0 "
                "AGPS_SA = AzerothGPSTargetButton.SetAttribute "
                "AzerothGPSTargetButton.SetAttribute = function(...) AGPS_SET = AGPS_SET + 1 return AGPS_SA(...) end")
    try:
        _npc_route(lua, ns, x=2270.0)  # (another NPC stop in the fight: nothing set or shown till it's over)
        ns.GPS.UpdateTargetButton()
        lua.eval("AzerothGPSTargetButton")._scripts.OnEnter  # (still a button)
        assert lua.eval("AGPS_SET") == 0 and not b._shown
    finally:
        lua.execute("AzerothGPSTargetButton.SetAttribute = AGPS_SA InCombatLockdown = function() return false end")
    assert _update(lua, ns, 1301)._shown


def test_the_target_button_works_the_same_with_the_controller_ui_and_touches_no_game_panel(clean):
    lua, ns = clean
    lua.execute("""AGPS_PANEL_CALLS = {}
      for _, f in ipairs({ "ShowUIPanel", "HideUIPanel", "ToggleWorldMap", "OpenWorldMap" }) do
        AGPS_OLD_PANEL = AGPS_OLD_PANEL or {}
        AGPS_OLD_PANEL[f] = rawget(_G, f)
        _G[f] = function() AGPS_PANEL_CALLS[#AGPS_PANEL_CALLS + 1] = f end
      end
      AGPS_OLD_IIS = rawget(_G, "C_InputInterfaceStyle")
      C_InputInterfaceStyle = { GetCurrentStyle = function() return Enum.InputDeviceInterfaceType.Gamepad end }""")
    try:
        assert ns.GPS.ControllerUI()
        _npc_route(lua, ns)
        b = _update(lua, ns, 1400)
        assert b._shown and b._attr["macrotext"] == MARKED
        b._scripts.OnEnter(b)
        b._scripts.OnLeave(b)
        lua.execute(f"AGPS_GUIDS = {{ target = '{NPC_GUID}' }}")
        assert not _update(lua, ns, 1401)._shown
        assert not list(lua.eval("AGPS_PANEL_CALLS").values())
    finally:
        lua.execute("""for f, v in pairs(AGPS_OLD_PANEL) do _G[f] = v end
          C_InputInterfaceStyle = AGPS_OLD_IIS""")


def test_an_npc_picked_in_the_search_is_a_stop_carrying_its_npc(clean):
    lua, ns = clean
    G, N = ns.GPS, ns.Nav
    _npc_route(lua, ns, npc=False)  # (a route already: the pick goes straight onto it)
    e = lua.eval(f"""{{ name = 'Innkeeper Renee', sub = 'Innkeeper', npc = true, id = {NPC_ID}, cont = 0,
      x = 2264, y = 300, z = 0 }}""")
    G.PickSearchEntry(e)
    got = [d for d in N.stops.values() if d.npcId == NPC_ID]
    assert len(got) == 1 and got[0].npcName == "Innkeeper Renee"
    # (a pin made from its row: picked from the search, the same)
    N.Clear()
    _npc_route(lua, ns, npc=False)
    e = lua.eval(f"""{{ name = 'Innkeeper Renee <Innkeeper>', sub = 'Pin', pin = true, npcId = {NPC_ID},
      npcName = 'Innkeeper Renee', cont = 0, x = 2264, y = 300, z = 0 }}""")
    G.PickSearchEntry(e)
    got = [d for d in N.stops.values() if d.npcId == NPC_ID]
    assert len(got) == 1 and got[0].npcName == "Innkeeper Renee"


def test_the_target_buttons_macro_is_one_line_in_the_games_language(clean):
    lua, ns = clean
    G = ns.GPS
    d = lua.eval(f"{{ npcId = {NPC_ID}, npcName = 'Bad;Name\\nTwo' }}")
    assert G.TargetNpcMacro(d) == "/targetexact Bad Name Two"
    assert G.TargetNpcMacro(lua.eval("{ npcId = 1, npcName = '  ' }")) is None


def test_the_target_key_is_bound_and_named():
    xml = (ADDON / "Bindings.xml").read_text(encoding="utf-8")
    assert 'name="CLICK AzerothGPSTargetButton:LeftButton"' in xml
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert '_G["BINDING_NAME_CLICK AzerothGPSTargetButton:LeftButton"]' in core


def test_nothing_in_the_addon_calls_a_protected_targeting_or_marking_function():
    # (display only: the Target button's macro, run by the game on the player's click, does the targeting)
    calls = re.compile(r"(?<![\w.:\"'])(TargetUnit|FocusUnit|AssistUnit|InteractUnit|SetRaidTarget|ClearRaidMarker|"
                       r"PlaceRaidMarker|RunMacroText|TargetNearest\w*)\s*\(")
    found = []
    for p in ADDON.rglob("*.lua"):
        if "Data" in p.parts:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("--", 1)[0]
            if calls.search(code):
                found.append(f"{p.name}:{i}: {line.strip()}")
    assert not found, found


def _group(lua, raid=False, lead=False, assist=False, secret=False):
    v = "AGPS_SECRET" if secret else None
    lua.execute(f"""IsInGroup = function() return true end
      IsInRaid = function() return {str(raid).lower()} end
      UnitIsGroupLeader = function() return {v or str(lead).lower()} end
      UnitIsGroupAssistant = function() return {v or str(assist).lower()} end""")


def test_the_click_marks_the_npc_solo_and_in_a_group_only_when_allowed(clean):
    lua, ns = clean
    G, st = ns.GPS, ns.settings.gps
    _npc_route(lua, ns)
    assert _update(lua, ns, 1500)._attr["macrotext"] == MARKED  # (solo, on by default)
    st.targetNpcMarkSolo = False
    assert _update(lua, ns, 1501)._attr["macrotext"] == TARGET_ONLY
    st.targetNpcMarkSolo = True
    # (a party: off by default; the group's change makes the macro again at once, its events)
    _group(lua)
    lua.eval("AGPS_FIRE")("GROUP_ROSTER_UPDATE")
    assert G.targetBtn._attr["macrotext"] == TARGET_ONLY
    st.targetNpcMarkGroup = True
    lua.eval("AGPS_FIRE")("PARTY_LEADER_CHANGED")
    assert G.targetBtn._attr["macrotext"] == MARKED
    # (a raid: only with lead or assist; unreadable, no)
    _group(lua, raid=True)
    assert _update(lua, ns, 1502)._attr["macrotext"] == TARGET_ONLY
    _group(lua, raid=True, assist=True)
    assert _update(lua, ns, 1503)._attr["macrotext"] == MARKED
    _group(lua, raid=True, lead=True)
    assert _update(lua, ns, 1504)._attr["macrotext"] == MARKED
    _group(lua, raid=True, secret=True)
    assert _update(lua, ns, 1505)._attr["macrotext"] == TARGET_ONLY
    st.targetNpcMarkGroup = False
    _group(lua, raid=True, lead=True)
    assert _update(lua, ns, 1506)._attr["macrotext"] == TARGET_ONLY


@pytest.mark.parametrize("icon", range(1, 9))
def test_the_mark_is_the_stops_route_marker(clean, icon):
    # (Nav.MARKER_COLORS are in raid icon order: 1 star yellow ... 8 skull white; the stop's `icon` is that number)
    lua, ns = clean
    ns.Nav.SetStops(lua.eval(f"""{{ {{ x = 2264, y = 300, cont = 0, name = 'Innkeeper Renee', npcId = {NPC_ID},
      npcName = 'Innkeeper Renee', icon = {icon} }} }}"""), False, "red")
    assert ns.Nav.dest.icon == icon
    assert _update(lua, ns, 1600 + icon)._attr["macrotext"] == MARKED and _marks_with(lua, icon)


def test_a_stop_without_a_raid_marker_is_targeted_only(clean):
    lua, ns = clean
    G = ns.GPS
    assert G.TargetNpcMacro(lua.eval(f"{{ npcId = {NPC_ID}, npcName = 'Innkeeper Renee' }}")) == TARGET_ONLY
    assert G.TargetNpcMacro(lua.eval(f"{{ npcId = {NPC_ID}, npcName = 'Innkeeper Renee', icon = 9 }}")) == TARGET_ONLY


def test_after_the_click_the_button_hides_and_comes_back_only_once_the_target_changes(clean):
    # (the click: the NPC targeted and marked by the game. The button hides then, so no second click from it; with
    # another target it shows again, and a click then leaves the mark as it is: "set-unmarked", any mark kept)
    lua, ns = clean
    _npc_route(lua, ns)
    b = _update(lua, ns, 1700)
    assert b._shown
    lua.execute(f"AGPS_GUIDS = {{ target = '{NPC_GUID}' }}")
    assert not _update(lua, ns, 1701)._shown
    lua.execute("AGPS_GUIDS = { target = 'Creature-0-1-0-1-1234-0000ABCDEF' }")
    b = _update(lua, ns, 1702)
    assert b._shown and b._attr["macrotext"] == MARKED and _marks_with(lua, 6)


def test_with_the_map_as_the_minimap_the_button_hangs_under_the_arrows_directions(clean):
    # (Kooki3z, 2026-11-22: the GPS map as the minimap, its own directions panel never shows; the arrow's do)
    lua, ns = clean
    G, A = ns.GPS, ns.Arrow
    _npc_route(lua, ns)
    lua.execute("AGPS_OLD_MM = AGPS_NS.GPS.MinimapMode AGPS_NS.GPS.MinimapMode = function() return true end")
    try:
        A.dir.Show(A.dir)
        b = _update(lua, ns, 1800, arrow=True)
        assert b._shown and lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.Arrow.dir")
        A.dir.Hide(A.dir)
        G.UpdateTargetButton()
        assert not b._shown
    finally:
        lua.execute("AGPS_NS.GPS.MinimapMode = AGPS_OLD_MM")
    b = _update(lua, ns, 1801)  # (the map's panel showing again, the arrow's closed: in it)
    assert b._shown and lua.eval("AzerothGPSTargetButton._pts.BOTTOMRIGHT[2] == AGPS_NS.GPS.navPanel")


def test_in_the_arrows_directions_it_goes_left_of_the_quest_route_icon_or_in_its_spot(clean):
    # (Kooki3z, 2026-11-22: "to the left of it if quest route button in there, otherwise use the quest route spot")
    lua, ns = clean
    A = ns.Arrow
    _npc_route(lua, ns)
    A.dir.Show(A.dir)
    A.stale.Hide(A.stale)
    b = _update(lua, ns, 1900, arrow=True)
    pt = lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT")
    own = lua.eval("AGPS_NS.Arrow.stale._pts.TOPRIGHT")
    assert b._shown and lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.Arrow.dir")
    assert (pt[4], pt[5]) == (own[2], own[3])  # (the Sprint icon's own spot)
    A.stale.Show(A.stale)  # (the quest route's Sprint icon up: just left of it)
    _update(lua, ns, 1901, arrow=True)
    pt = lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT")
    assert lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.Arrow.stale") and pt[3] == "TOPLEFT"
    A.stale.Hide(A.stale)
    _update(lua, ns, 1902, arrow=True)
    assert lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.Arrow.dir")


def test_in_the_maps_panel_it_stays_in_the_column_the_text_keeps_clear(clean):
    # (the steps' text ends stepsR from the right (G.NavTextInsets): the icon within it, over the use button when shown)
    lua, ns = clean
    G = ns.GPS
    _npc_route(lua, ns)
    _, steps_r = G.NavTextInsets()
    for use in (False, True):
        (G.useBtn.Show if use else G.useBtn.Hide)(G.useBtn)
        try:
            b = _update(lua, ns, 1950 + use)
            pt = lua.eval("AzerothGPSTargetButton._pts.BOTTOMRIGHT")
        finally:
            G.useBtn.Hide(G.useBtn)
        assert b._shown and lua.eval("AzerothGPSTargetButton._pts.BOTTOMRIGHT[2] == AGPS_NS.GPS.navPanel")
        left = pt[4] - G.TARGET_NPC_PX
        assert left >= -steps_r and pt[4] <= 0
        assert pt[5] >= (5 + 24 if use else 0)  # (over the use button, never on it)


def _icon_left(lua, ns):
    # (the icon's left edge, from the panel's right: the arrow's directions' top right corner)
    G, A = ns.GPS, ns.Arrow
    pt = lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT")
    if lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.Arrow.stale"):
        sp = lua.eval("AGPS_NS.Arrow.stale._pts.TOPRIGHT")
        return sp[2] - A.stale._w + pt[4] - G.TARGET_NPC_PX
    return pt[4] - G.TARGET_NPC_PX


def test_the_arrows_first_line_never_runs_under_the_icons(clean):
    # (Kooki3z, 2026-11-22: the icon covered "yd" of "Continue straight, then make a U-turn in 40 yd")
    lua, ns = clean
    A = ns.Arrow
    _npc_route(lua, ns)
    A.dir.Show(A.dir)
    for sprint in (False, True):
        (A.stale.Show if sprint else A.stale.Hide)(A.stale)
        A.ReserveCorner()
        b = _update(lua, ns, 1960 + sprint, arrow=True)
        assert b._shown
        right = lua.eval("AGPS_NS.Arrow.line1._pts.RIGHT")[2]  # (the line's right end, from the panel's)
        assert right <= _icon_left(lua, ns) - 1, (sprint, right, _icon_left(lua, ns))
    # (the icon gone: the line its full width back; the Sprint icon alone still kept clear)
    A.stale.Hide(A.stale)
    ns.Nav.Clear()
    ns.GPS.UpdateTargetButton()
    assert lua.eval("AGPS_NS.Arrow.line1._pts.RIGHT")[2] == -A.LINE_RIGHT
    A.stale.Show(A.stale)
    A.ReserveCorner()
    assert lua.eval("AGPS_NS.Arrow.line1._pts.RIGHT")[2] <= -(3 + A.stale._w) - 1
    A.stale.Hide(A.stale)
    A.ReserveCorner()


def test_it_pulses_as_the_quest_route_icon_does_and_says_when_it_marks(clean):
    lua, ns = clean
    G = ns.GPS
    _npc_route(lua, ns)
    b = _update(lua, ns, 2000)
    pulses = {round(G.TargetNpcPulse(t), 3) for t in (2000.0, 2000.2, 2000.4, 2000.6)}
    assert len(pulses) > 1 and all(0.1 <= a <= 1 for a in pulses)
    assert abs(b._alpha - G.TargetNpcPulse(2000)) < 1e-6  # (shown: at the pulse's alpha)
    assert b.marks  # (solo: marks too; its tooltip says so)
    b._scripts.OnEnter(b)
    ns.settings.gps.targetNpcMarkSolo = False
    b = _update(lua, ns, 2001)
    assert not b.marks and b._attr["macrotext"] == TARGET_ONLY and _marks_with(lua, None)
    b._scripts.OnEnter(b)
    b._scripts.OnLeave(b)


def test_it_is_still_a_secure_button_made_once():
    src = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    assert 'CreateFrame, "Button", "AzerothGPSTargetButton", UIParent, "SecureActionButtonTemplate")' in src


def test_the_mark_is_made_by_the_games_secure_raidtarget_action_not_tm(clean):
    # (Kooki3z, 2026-11-23: "raid marking isn't working". This client's /tm is an ordinary slash command, run tainted
    # from a macro, and SetRaidTarget refuses tainted code: the NPC was targeted, never marked. /click is a secure
    # command, and the clicked button's raidtarget action runs in the template's secure code)
    lua, ns = clean
    _npc_route(lua, ns)
    b = _update(lua, ns, 2100)
    assert "/tm" not in b._attr["macrotext"] and b._attr["macrotext"].endswith("/click [@target,exists] " + MARK_BTN)
    m = _marker(lua)
    assert m._name == MARK_BTN and m._parent._name == "UIParent" and not m._shown
    # (it acts on the up, which is what /click sends: with "cast on key down" on (the default) it would do nothing)
    assert m._attr["useOnKeyDown"] is False
    assert _marks_with(lua, 6)
    # (only the icon changed, the macro the same: the marker's icon follows)
    ns.Nav.dest.icon = 3
    assert _update(lua, ns, 2101)._attr["macrotext"] == MARKED and _marks_with(lua, 3)
    # (marking off, or no NPC stop: the marker does nothing)
    ns.settings.gps.targetNpcMarkSolo = False
    assert _update(lua, ns, 2102)._attr["macrotext"] == TARGET_ONLY and _marks_with(lua, None)
    ns.settings.gps.targetNpcMarkSolo = True
    assert _update(lua, ns, 2103)._attr["macrotext"] == MARKED and _marks_with(lua, 3)
    ns.Nav.Clear()
    ns.GPS.UpdateTargetButton()
    assert b._attr["type"] is None and _marks_with(lua, None)


def test_the_marker_button_is_a_secure_raidtarget_button_that_never_toggles():
    src = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    assert 'CreateFrame, "Button", G.TARGET_NPC_MARK_BTN, UIParent, "SecureActionButtonTemplate")' in src
    assert 'G.TARGET_NPC_MARK_BTN = "AzerothGPSTargetMarkButton"' in src
    assert 'm:SetAttribute("action", "set-unmarked")' in src  # (never "toggle", the template's default)

