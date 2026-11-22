"""The Target button (1.3.14, asked by Kooki3z): the route's next stop an NPC picked in the search (or a pin made from
its row) and the player near it, a "Target <name>" button under the directions panel, and a key for it (Bindings.xml).
The player's own click only: a secure button whose macro is "/targetexact <name>"; AzerothGPS never calls TargetUnit
or any other protected function itself (wowmock.lua's AGPS_PROTECTED lists any call). Set only out of combat, hidden as
combat starts. The same click marks the NPC with the stop's route marker ("/tm", asked 2026-11-22) when the options
allow it (solo on, party or raid off; a raid with lead or assist only); AzerothGPS never marks or clears a mark itself
(SetRaidTarget is restricted in this client)."""

import re
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
NPC_ID = 6741  # (Innkeeper Renee, Brill)
NPC_GUID = f"Creature-0-1-0-1-{NPC_ID}-0000ABCDEF"
TARGET_ONLY = "/targetexact Innkeeper Renee"
# (the target cleared first and "[@target,exists]": with the NPC not found, nothing else is marked; "~": a unit with
# any mark already, ours from a click before included, is left alone, so a second click never toggles it off)
MARKED = "/cleartarget\n/targetexact Innkeeper Renee\n/tm [@target,exists] ~{}"


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


def _update(lua, ns, t):
    G = ns.GPS
    lua.execute(f"AGPS_T = {t}")
    G.Update()
    G.navPanel.Show(G.navPanel)  # (the directions panel up, as with a route worked out)
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
    assert b._attr["type"] == "macro" and b._attr["macrotext"] == MARKED.format(6)
    assert str(b._text) == "Target Innkeeper Renee"
    # (this client's secure buttons act on the key's down; an up-only one does nothing)
    assert set(b._clicks.values()) == {"AnyUp", "AnyDown"}
    assert lua.eval("AzerothGPSTargetButton._pts.TOPRIGHT[2] == AGPS_NS.GPS.navPanel")  # (under the directions panel)
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
    G.navPanel.Hide(G.navPanel)  # (the directions panel closed: hidden, its key still set)
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
        assert b._shown and b._attr["macrotext"] == MARKED.format(6)
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
    assert _update(lua, ns, 1500)._attr["macrotext"] == MARKED.format(6)  # (solo, on by default)
    st.targetNpcMarkSolo = False
    assert _update(lua, ns, 1501)._attr["macrotext"] == TARGET_ONLY
    st.targetNpcMarkSolo = True
    # (a party: off by default; the group's change makes the macro again at once, its events)
    _group(lua)
    lua.eval("AGPS_FIRE")("GROUP_ROSTER_UPDATE")
    assert G.targetBtn._attr["macrotext"] == TARGET_ONLY
    st.targetNpcMarkGroup = True
    lua.eval("AGPS_FIRE")("PARTY_LEADER_CHANGED")
    assert G.targetBtn._attr["macrotext"] == MARKED.format(6)
    # (a raid: only with lead or assist; unreadable, no)
    _group(lua, raid=True)
    assert _update(lua, ns, 1502)._attr["macrotext"] == TARGET_ONLY
    _group(lua, raid=True, assist=True)
    assert _update(lua, ns, 1503)._attr["macrotext"] == MARKED.format(6)
    _group(lua, raid=True, lead=True)
    assert _update(lua, ns, 1504)._attr["macrotext"] == MARKED.format(6)
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
    assert _update(lua, ns, 1600 + icon)._attr["macrotext"] == MARKED.format(icon)


def test_a_stop_without_a_raid_marker_is_targeted_only(clean):
    lua, ns = clean
    G = ns.GPS
    assert G.TargetNpcMacro(lua.eval(f"{{ npcId = {NPC_ID}, npcName = 'Innkeeper Renee' }}")) == TARGET_ONLY
    assert G.TargetNpcMacro(lua.eval(f"{{ npcId = {NPC_ID}, npcName = 'Innkeeper Renee', icon = 9 }}")) == TARGET_ONLY


def test_after_the_click_the_button_hides_and_comes_back_only_once_the_target_changes(clean):
    # (the click: the NPC targeted and marked by the game. The button hides then, so no second click from it; with
    # another target it shows again, and a click then leaves the mark as it is: "~", any mark kept)
    lua, ns = clean
    _npc_route(lua, ns)
    b = _update(lua, ns, 1700)
    assert b._shown
    lua.execute(f"AGPS_GUIDS = {{ target = '{NPC_GUID}' }}")
    assert not _update(lua, ns, 1701)._shown
    lua.execute("AGPS_GUIDS = { target = 'Creature-0-1-0-1-1234-0000ABCDEF' }")
    b = _update(lua, ns, 1702)
    assert b._shown and "~6" in b._attr["macrotext"] and "/tm 6" not in b._attr["macrotext"]
