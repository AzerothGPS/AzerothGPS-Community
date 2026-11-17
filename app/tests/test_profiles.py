"""Profiles (1.2.2, asked 2026-11-11: "save/load profiles that are character specific and/or account wide ... for all
option settings"; each character picks the one it uses)."""
import pytest

pytest.importorskip("lupa.lua51")


def test_a_character_picks_its_profile_and_changes_are_saved_into_it():
    from azerothgps.gameharness import start
    lua, ns = start()
    O = ns.Options
    same = lua.eval("function() return AGPS_NS.settings == AGPS_NS.db.settings end")
    # every character on Default until another is picked: the options as they always were
    assert ns.ProfileName() is None and same() and list(ns.ProfileNames().values()) == []
    ns.settings.gps.replaceMinimapIdle = 7
    ns.settings.minimap.angle = 10
    # a new one: a copy of the options as they are, this character on it
    assert O.NewProfile("  Healer ") is True
    assert ns.ProfileName() == "Healer" and not same()
    assert list(ns.ProfileNames().values()) == ["Healer"]
    assert ns.settings.gps.replaceMinimapIdle == 7 and ns.settings.minimap.angle == 10
    # a change is saved into the profile in use, not the others
    ns.settings.gps.replaceMinimapIdle = 0
    ns.settings.minimap.angle = 200
    assert ns.db.settings.gps.replaceMinimapIdle == 7 and ns.db.settings.minimap.angle == 10
    # a name taken, Default's own, an empty one: no
    assert O.NewProfile("Healer") is False and O.NewProfile("Default") is False and O.NewProfile("  ") is False
    # back on Default, and to it again
    assert ns.UseProfile(None) is True and same() and ns.ProfileName() is None
    assert ns.settings.gps.replaceMinimapIdle == 7
    assert ns.UseProfile("Nobody") is False and same()
    # Copy from: asked first, then every option of the other in this one
    ask = O.AskCopyProfile("Healer")
    assert ask._shown is True and ns.settings.gps.replaceMinimapIdle == 7
    ask.yes._scripts.OnClick(ask.yes)
    assert same() and ns.settings.gps.replaceMinimapIdle == 0 and ns.settings.minimap.angle == 200
    assert ns.db.profiles.Healer.gps.replaceMinimapIdle == 0  # (a copy: the other still its own)
    ns.settings.gps.replaceMinimapIdle = 9
    assert ns.db.profiles.Healer.gps.replaceMinimapIdle == 0
    # Delete: asked first, the one in use, never Default; the character goes back to Default
    assert O.AskDeleteProfile() is None
    ns.UseProfile("Healer")
    ask = O.AskDeleteProfile()
    ask.no._scripts.OnClick(ask.no)
    assert ns.ProfileName() == "Healer"
    ask = O.AskDeleteProfile()
    ask.yes._scripts.OnClick(ask.yes)
    assert ns.ProfileName() is None and same() and ns.db.profiles.Healer is None
    assert ns.settings.gps.replaceMinimapIdle == 9


def test_the_profile_is_the_characters_at_login_and_gets_the_options_added_since():
    from azerothgps.gameharness import start
    lua, ns = start()
    key = ns.CharKey()
    saved = """AzerothGPSDB = {
      settings = { gps = { replaceMinimapIdle = 30 } },
      profiles = { Healer = { gps = { replaceMinimapIdle = 0 } } },
      chars = { [%s] = { profile = %s } },
    }"""
    quote = lambda s: '"' + s.replace('"', '\\"') + '"'  # noqa: E731
    lua, ns = start(saved=saved % (quote(key), quote("Healer")))
    assert ns.ProfileName() == "Healer"
    assert ns.settings.gps.replaceMinimapIdle == 0 and ns.db.settings.gps.replaceMinimapIdle == 30
    # (an option it never had: its default; the minimap button's part too)
    assert ns.settings.gps.size == ns.DEFAULTS.gps.size and ns.settings.minimap.angle == ns.DEFAULTS.minimap.angle
    # a pick whose profile is gone (deleted on another character): Default, and the pick let go
    lua, ns = start(saved=saved % (quote(key), quote("Gone")))
    assert ns.ProfileName() is None and ns.settings.gps.replaceMinimapIdle == 30
    assert ns.CharDB().profile is None
    # another character: Default
    lua, ns = start(saved=saved % (quote("Elsewhere-Someone"), quote("Healer")))
    assert ns.ProfileName() is None and ns.settings.gps.replaceMinimapIdle == 30


def test_the_options_list_the_profiles_and_hold_them_while_the_tutorial_runs():
    from azerothgps.gameharness import start
    lua, ns = start()
    O = ns.Options
    O.Show()
    names = lambda: [o.text for o in O.profileOptions.values()]  # noqa: E731
    assert O.profileList is not None and O.profileCopy is not None and len(names()) == 1
    assert O.NewProfile("Tank") is True
    assert names()[1:] == ["Tank"]
    # typed in the box, Enter: made, the box emptied
    O.profileBox.SetText(O.profileBox, "Alt")
    O.profileBox._scripts.OnEnterPressed(O.profileBox)
    assert ns.ProfileName() == "Alt" and names()[1:] == ["Alt", "Tank"] and O.profileBox.GetText(O.profileBox) == ""
    # the tutorial running: it holds the options it found, so no other profile meanwhile
    lua.execute("AGPS_RUN = AGPS_NS.Tutorial.run AGPS_NS.Tutorial.run = {}")
    try:
        assert O.ProfilesHeld() and O.NewProfile("Later") is False
        assert O.AskDeleteProfile() is None and O.AskCopyProfile("Tank") is None
    finally:
        lua.execute("AGPS_NS.Tutorial.run = AGPS_RUN AGPS_RUN = nil")
    assert not O.ProfilesHeld()
