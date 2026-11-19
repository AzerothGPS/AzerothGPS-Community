"""Herbs and veins gathered on a client in another language than English are saved (reported 2026-11-19 from a German
client: no herb or vein ever saved). Lay.AddNode takes only a name it knows: KNOWN_NODES are the English names ("Copper
Vein", not "Kupfervorkommen"), and a name was learned from a world object's tooltip only when its profession line said
"Mining" or "Herbalism". The profession's line in the client's language teaches it too: its gathering spell's name,
"Bergbau", "Kräuterkunde" (this client's spells are named as the professions). The cast alone still teaches nothing:
it may name the unit targeted (test_map_redraw's Dark Enforcer)."""

import pytest

pytest.importorskip("lupa.lua51")


@pytest.fixture
def german():
    from azerothgps.gameharness import start
    lua, ns = start(locale="deDE")
    lua.execute("AGPS_NS.SpellName = function(id) return ({ [2575] = 'Bergbau', [2366] = 'Kräuterkunde' })[id] end")
    return lua, ns


def _saved(ns):
    out = []
    for c in (0, 1):
        lst = ns.db.nodes[c]
        out += [] if lst is None else [(lst[i][3], lst[i][4]) for i in range(1, len(lst) + 1)]
    return out


def _gather(lua, name, guid, spell):
    lua.execute(f"""
      AGPS_FIRE("UNIT_SPELLCAST_SENT", "player", "{name}", "{guid}", {spell})
      AGPS_FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "{guid}", {spell})
    """)


def test_a_vein_and_a_herb_hovered_then_gathered_on_a_german_client_are_saved(german):
    lua, ns = german
    L = ns.Layers
    # (the mouse over each first, as a right-click on it: its tooltip, the name and the profession's line)
    assert L.LearnNode("Kupfervorkommen", "Bergbau") == "ore"
    assert L.LearnNode("Friedensblume", "Kräuterkunde") == "herb"
    _gather(lua, "Kupfervorkommen", "Cast-1", 2575)
    _gather(lua, "Friedensblume", "Cast-2", 2366)
    saved = _saved(ns)
    assert ("Kupfervorkommen", "ore") in saved and ("Friedensblume", "herb") in saved


def test_the_cast_alone_teaches_nothing(german):
    lua, ns = german
    _gather(lua, "Dunkler Vollstrecker", "Cast-3", 2366)  # (the unit targeted, not what was gathered)
    assert ns.Layers.NodeKind("Dunkler Vollstrecker") is None and _saved(ns) == []


def test_only_the_professions_line_teaches(german):
    L = german[1].Layers
    assert L.LearnNode("Bergbau", "Bergbau") is None  # (the profession's own line is no node)
    assert L.LearnNode("Gnoll", "Stufe 10") is None
    assert L.LearnNode("Copper Vein", "Mining") == "ore"  # (and the English, as before)


def test_right_clicked_without_the_profession_on_a_german_client(german):
    L = german[1].Layers
    assert L.LearnNode("Zinnader", "Bergbau") == "ore"
    L.NoteWorldObject("Zinnader", 10.0)
    assert L.OnGatherError("Benötigt Bergbau", 11.0, 300.0, 200.0, 1)
    assert _saved(german[1])[-1] == ("Zinnader", "ore")
