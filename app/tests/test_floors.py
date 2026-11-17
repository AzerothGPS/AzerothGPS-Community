"""The floors report's rules (app/azerothgps/floors.py, `agps floors`)."""

from azerothgps import floors as F


def test_an_npc_s_roles_come_from_the_classic_flags():
    # (1.12's NpcFlags: 2 quests, 4 vendor, 16 trainer, 128 innkeeper; gossip alone offers nothing)
    assert F._roles(2 | 16, False) == ["quests", "trainer"]
    assert F._roles(4 | 128, True) == ["innkeeper", "quests", "vendor"]
    assert F._roles(1, False) == []
    assert F._roles(0, True) == ["quests"]


def test_undercity_is_counted_apart():
    # (its own level: its floors are known already)
    assert F._in_undercity(0, 1595.3, 224.7, -62.0)
    assert not F._in_undercity(0, 1595.3, 224.7, 61.0)  # (up in the Ruins)
    assert not F._in_undercity(1, 1595.3, 224.7, -62.0)

