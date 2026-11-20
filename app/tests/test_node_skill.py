"""Herbs and veins by the character's skill (asked 2026-11-19): a node their Herbalism or Mining is too low for says so
in red in its tooltip ("Requires Mining 125"); Find Herbs and Ore's Available toggle shows only those they can gather,
kept up to date as the skill goes up; the finder's search box clear of the text above it."""

import pytest

TIRISFAL = 1420

PRE = """
  AGPS_HERB, AGPS_MINE = 100, 0
  GetNumSkillLines = function() return 3 end
  GetSkillLineInfo = function(i)
    if i == 1 then return "Professions", true end
    if i == 2 then return "Herbalism", false, nil, AGPS_HERB end
    if AGPS_MINE > 0 then return "Mining", false, nil, AGPS_MINE end
    return "Cooking", false, nil, 50
  end
"""


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(pre=PRE)
    return lua, ns


@pytest.fixture(autouse=True)
def fresh(game):
    lua, ns = game
    st = ns.settings.gps
    st.nodeAvailable, st.layerHerbs, st.layerOre = False, True, True
    st.nodeFilter = lua.eval("{}")
    ns.db.nodes = lua.table()
    lua.execute("AGPS_HERB, AGPS_MINE = 100, 0")
    ns.Layers.OnSkillChanged()
    yield
    if ns.Layers.finder:
        ns.Layers.finder.Hide(ns.Layers.finder)


def _spot(ns, u, v):
    return ns.Layers.MapToWorld(TIRISFAL, u, v)


def _add(ns):
    """A Peacebloom (1), a Kingsblood (125) and an Iron Deposit (125) near each other in Tirisfal."""
    Lay = ns.Layers
    x, y, cont = _spot(ns, 0.4, 0.5)
    assert Lay.AddNode(cont, x, y, "Peacebloom", "herb")
    assert Lay.AddNode(cont, x + 60, y, "Kingsblood", "herb")
    assert Lay.AddNode(cont, x, y + 60, "Iron Deposit", "ore")
    return x, y, cont


def _marks(lua, ns, x, y, cont):
    ns.Layers.version = ns.Layers.version + 1
    ms = ns.Layers.Marks(cont, x, y, 400, lua.table(), cont)
    return {str(m[4]): str(m[5]) for m in ms.values()}


def test_a_node_the_skill_is_too_low_for_says_so_in_red(game):
    lua, ns = game
    x, y, cont = _add(ns)
    m = _marks(lua, ns, x, y, cont)
    assert "Requires" not in m["Peacebloom"]
    assert "|cffff3030Requires Herbalism 125|r" in m["Kingsblood"]
    assert "|cffff3030Requires Mining 125|r" in m["Iron Deposit"]  # (no Mining at all)
    lua.execute("AGPS_HERB = 125")
    ns.Layers.OnSkillChanged()
    assert "Requires" not in _marks(lua, ns, x, y, cont)["Kingsblood"]


def test_available_shows_only_what_the_skill_gathers_and_follows_it(game):
    lua, ns = game
    Lay = ns.Layers
    x, y, cont = _add(ns)
    f = Lay.ShowNodeFinder()
    b = f.available
    assert str(b._text) == "Available"
    assert str(f.availableState._text) == "|cffff4040off|r"
    assert sorted(_marks(lua, ns, x, y, cont)) == ["Iron Deposit", "Kingsblood", "Peacebloom"]
    b._scripts.OnClick(b)
    assert ns.settings.gps.nodeAvailable is True
    assert str(f.availableState._text) == "|cff40ff40on|r"
    assert sorted(_marks(lua, ns, x, y, cont)) == ["Peacebloom"]
    # (a farming area takes only those too)
    poly = lua.eval(f"{{ {x - 200}, {y - 200}, {x + 200}, {y - 200}, {x + 200}, {y + 200}, {x - 200}, {y + 200} }}")
    inside = Lay.NodesInPolygon(cont, poly)
    assert sorted(str(n.name) for n in inside.values()) == ["Peacebloom"]
    # (Herbalism up to 125, the game's event: Kingsblood now)
    lua.execute("AGPS_HERB = 125")
    Lay.frame._scripts.OnEvent(Lay.frame, "SKILL_LINES_CHANGED")
    assert sorted(_marks(lua, ns, x, y, cont)) == ["Kingsblood", "Peacebloom"]
    lua.execute("AGPS_MINE = 130")
    Lay.frame._scripts.OnEvent(Lay.frame, "CHAT_MSG_SKILL", "Your skill in Mining has increased to 130.")
    assert sorted(_marks(lua, ns, x, y, cont)) == ["Iron Deposit", "Kingsblood", "Peacebloom"]
    # (Find Herbs and Ore's quick button glows and says why while it's on)
    G = ns.GPS
    assert G.GlowingIds()["nodeFind"]
    t = next(t for t in G.QUICK.values() if str(t.id) == "nodeFind")
    assert "Available is on" in str(t.warn())
    b._scripts.OnClick(b)
    assert ns.settings.gps.nodeAvailable is False and not G.GlowingIds()["nodeFind"]
    assert str(f.availableState._text) == "|cffff4040off|r"


def test_the_available_button_explains_itself(game):
    lua, ns = game
    f = ns.Layers.ShowNodeFinder()
    b = f.available
    lines = []
    lua.globals().GameTooltip.AddLine = lambda self, text, *a: lines.append(str(text))
    b._scripts.OnEnter(b)
    assert any("On: only the herbs and veins" in s for s in lines)
    assert "Your skill: Herbalism 100, Mining 0" in lines


def test_the_search_box_is_clear_of_the_text_above_it(game):
    lua, ns = game
    Lay = ns.Layers
    f = Lay.ShowNodeFinder()
    hint_top = f.hint._pts.TOPLEFT[3]  # (SetPoint("TOPLEFT", x, y): its y)
    box_y = f.box._pts.TOPLEFT[3]
    hint_h = f.hint.GetStringHeight(f.hint)
    # (the box's top at least FINDER_GAP under the hint's bottom; before, 18 under its top with a two-line hint)
    assert box_y <= hint_top - hint_h - Lay.FINDER_GAP
    assert f.available._shown and f.showAll._shown
