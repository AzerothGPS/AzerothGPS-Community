"""Herbs and veins by the character's skill (asked 2026-11-19): a node their Herbalism or Mining is too low for says so
in red in its tooltip ("Requires Mining 125"); Find Herbs and Ore's Available toggle shows only those they can gather,
kept up to date as the skill goes up; the finder's search box clear of the text above it."""

import pytest

TIRISFAL = 1420

PRE = """
  AGPS_HERB, AGPS_MINE, AGPS_PROFS_READY = 100, 0, true
  -- (WoW Forever's own: retail's GetProfessions / GetProfessionInfo, the skill line 7th; no classic skill lines)
  GetProfessions = function()
    if not AGPS_PROFS_READY then return nil, nil, nil, nil, nil end
    return 1, AGPS_MINE > 0 and 2 or nil, nil, nil, 3 -- (Herbalism, Mining, -, -, Cooking)
  end
  GetProfessionInfo = function(i)
    if i == 1 then return "Herbalism", 136246, AGPS_HERB, 300, 2, 0, 182 end
    if i == 2 then return "Mining", 136248, AGPS_MINE, 300, 2, 0, 186 end
    return "Cooking", 133971, 50, 75, 1, 0, 185
  end
  GetNumSkillLines = function() return 0 end
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
    lua.execute("AGPS_HERB, AGPS_MINE, AGPS_PROFS_READY = 100, 0, true")
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


def test_the_skill_is_read_from_retails_profession_api_by_skill_line(game):
    # (Kooki3z, 2026-11-19: "my mining isn't 0": WoW Forever gives its professions by GetProfessions, not the classic
    # skill lines; by skill line, whatever the client's language)
    lua, ns = game
    lua.execute("AGPS_HERB, AGPS_MINE = 120, 175")
    lua.execute("AGPS_GPI = GetProfessionInfo; GetProfessionInfo = function(i) "
                "local a, b, c, d, e, f, g = AGPS_GPI(i) return (g == 186 and 'Bergbau' or g == 182 and 'Kräuterkunde' "
                "or a), b, c, d, e, f, g end")
    try:
        ns.Layers.OnSkillChanged()
        r = ns.Layers.SkillRanks()
        assert (r.herb, r.ore) == (120, 175)
        assert ns.Layers.Professions().ore and ns.Layers.Professions().herb
    finally:
        lua.execute("GetProfessionInfo = AGPS_GPI")


def test_the_classic_skill_lines_still_count(game):
    lua, ns = game
    lua.execute("""AGPS_GP, AGPS_GNSL, AGPS_GSLI = GetProfessions, GetNumSkillLines, GetSkillLineInfo
      GetProfessions = nil
      GetNumSkillLines = function() return 2 end
      GetSkillLineInfo = function(i)
        if i == 1 then return "Professions", true end
        return "Mining", false, nil, 140
      end""")
    try:
        ns.Layers.OnSkillChanged()
        r = ns.Layers.SkillRanks()
        assert (r.herb, r.ore) == (0, 140)
    finally:
        lua.execute("GetProfessions, GetNumSkillLines, GetSkillLineInfo = AGPS_GP, AGPS_GNSL, AGPS_GSLI")


def test_professions_not_given_yet_at_login_are_read_again(game):
    # (read before the game has them: none found is kept only a few seconds, not until the next skill-up)
    lua, ns = game
    Lay = ns.Layers
    lua.execute("AGPS_PROFS_READY = false")
    Lay.OnSkillChanged()
    assert Lay.SkillRanks().herb == 0
    lua.execute(f"AGPS_PROFS_READY = true; AGPS_T = AGPS_T + {Lay.RANK_EMPTY_SECONDS + 1}")
    assert Lay.SkillRanks().herb == 100


def _rows(f):
    """The finder's rows shown: (name, ticked)."""
    out = []
    for r in f.rows.values():
        if r._shown and r.entry:
            out.append((str(r.entry.name), bool(r.check._shown)))
    return out


def test_available_lists_only_what_shows_ticked_and_show_all_turns_it_off(game):
    # (asked 2026-11-19: "If available is on, auto filter the list to show what would be selected, then if Show All
    # is clicked this turns Available to off and deselects the filtered ones")
    lua, ns = game
    Lay = ns.Layers
    st = ns.settings.gps
    lua.execute("AGPS_HERB, AGPS_MINE = 60, 0")  # (Peacebloom, Silverleaf, Earthroot, Mageroyal; no Mining)
    Lay.OnSkillChanged()
    f = Lay.ShowNodeFinder()
    every = len(Lay.NodeNames(""))
    assert every > 40 and not any(t for _, t in _rows(f))  # (off: every name, none ticked)
    assert not f.showAll._enabled
    f.available._scripts.OnClick(f.available)
    f.box.SetText(f.box, "")
    f.Refresh()
    rows = _rows(f)
    assert sorted(n for n, _ in rows) == ["Earthroot", "Mageroyal", "Peacebloom", "Silverleaf", "Stunted Silverleaf"]
    assert all(t for _, t in rows)  # (each shown on the map: ticked)
    assert "skill can gather" in str(f.status._text)
    assert f.showAll._enabled is not False
    # (one unticked: the others the skill gathers stay, only it hidden)
    row = next(r for r in f.rows.values() if r._shown and str(r.entry.name) == "Mageroyal")
    row._scripts.OnClick(row)
    ticks = dict(_rows(f))
    assert ticks["Mageroyal"] is False and ticks["Peacebloom"] is True and ticks["Earthroot"] is True
    assert st.nodeFilter["Mageroyal"] is None and st.nodeFilter["Peacebloom"] is True
    # (Show All: Available off, nothing picked, every name back unticked)
    f.showAll._scripts.OnClick(f.showAll)
    assert st.nodeAvailable is False and Lay.NodeFilter() is None
    assert len(Lay.NodeNames("")) == every and not any(t for _, t in _rows(f))
    assert str(f.availableState._text) == "|cffff4040off|r"


def test_a_name_the_skill_is_too_low_for_shows_the_skill_needed_in_red(game):
    # (asked 2026-11-19: "for items they don't have the skill level to gather for, beside the name put the number
    # needed in red")
    lua, ns = game
    Lay = ns.Layers
    f = Lay.ShowNodeFinder()
    f.box.SetText(f.box, "kingsblood")
    f.Refresh()
    r = next(r for r in f.rows.values() if r._shown and str(r.entry.name) == "Kingsblood")
    assert str(r.text._text).startswith("Kingsblood |cffff3030125|r")
    f.box.SetText(f.box, "peacebloom")
    f.Refresh()
    r = next(r for r in f.rows.values() if r._shown and str(r.entry.name) == "Peacebloom")
    assert "|cffff3030" not in str(r.text._text)
    f.box.SetText(f.box, "")


def test_the_herbs_and_ore_buttons_narrow_the_list(game):
    # (asked 2026-11-19: "round icons at the top right of the window, one is a copper ore and the other a peacebloom.
    # clicking 1 or the other will filter to just ore or herbs. Clicking it again takes the filter off, so does
    # selecting the other type")
    lua, ns = game
    Lay = ns.Layers
    f = Lay.ShowNodeFinder()
    ore, herb = f.kindButtons["ore"], f.kindButtons["herb"]
    assert ore._shown and herb._shown and str(ore._pt[1]) == "TOPRIGHT"
    assert ore.agpsArt is not None  # (the map menu's round button, drawn at whole pixels)

    def kinds():
        return {str(e.kind) for e in Lay.NodeNames("", Lay.finderKind).values()}

    try:
        assert kinds() == {"herb", "ore"}
        ore._scripts.OnClick(ore)
        assert Lay.finderKind == "ore" and kinds() == {"ore"}
        assert all(str(r.entry.kind) == "ore" for r in f.rows.values() if r._shown)
        assert ore.glow._shown and herb.iconTex._desat
        herb._scripts.OnClick(herb)  # (the other type: herbs only)
        assert Lay.finderKind == "herb" and kinds() == {"herb"}
        herb._scripts.OnClick(herb)  # (again: off)
        assert Lay.finderKind is None and kinds() == {"herb", "ore"}
        assert not ore.iconTex._desat and not herb.iconTex._desat
    finally:
        Lay.SetFinderKind(None)
