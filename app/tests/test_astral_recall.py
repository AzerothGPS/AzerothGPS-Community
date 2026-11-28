"""A shaman's Astral Recall before the hearthstone (Kooki3z 2026-11-27: "When you are on a Shaman, when the GPS gives
instruction to use the Hearthstone, could you have it instead recommend Astral Recall").

Teleports.Available listed Astral Recall first and both cost the same, but Nav.Plan's next place is the nearest by
`pairs`, whose order is the table's own: with both ready the route took the hearthstone about as often. Now, with
Astral Recall ready, the hearthstone's row costs Teleports.RECALL_FIRST_SECONDS more; on Astral Recall's cooldown the
hearthstone is taken as before. The map menu's hearth button names Astral Recall for a shaman who knows it."""

import pytest

from test_addon_lua import env, load, nav_env  # noqa: F401 (fixtures)

BRILL_STOP = (2250.0, 250.0, 0)  # (home is Brill; the player in Durotar, across the sea)
DUROTAR = (300.0, -4700.0, 1)

SHAMAN = """
  GetItemCount = nil
  AGPS_STONES = { [6948] = 1 }
  C_Item = { GetItemCount = function(id) return AGPS_STONES[id] or 0 end }
  C_Container = { GetItemCooldown = function() return 0, 0, 1 end }
  GetBindLocation = function() return "Brill" end
  AGPS_KNOWN = { [556] = true }
  IsPlayerSpell = function(id) return AGPS_KNOWN[id] or false end
  AGPS_RECALL_CD = 0
  C_Spell = { GetSpellCooldown = function(id)
    local cd = id == 556 and AGPS_RECALL_CD or 0
    return { startTime = cd > 0 and 1 or 0, duration = cd }
  end }
"""


def _teleports(lua, ns):
    load(lua, ns, "Data/Pois.lua", "Teleports.lua")
    lua.execute(SHAMAN)
    ns.settings = lua.eval("{ gps = { useHearthstone = true, useTeleports = true } }")
    ns.Teleports.Changed()
    return ns.Teleports


def _rows(T):
    T.Changed()
    rows = T.Available(*DUROTAR[2:], *DUROTAR[:2])
    return [rows[i] for i in range(1, len(rows) + 1)]


def _route(lua, ns):
    N = ns.Nav
    ns.Teleports.Changed()
    N.SetDestination(BRILL_STOP[0], BRILL_STOP[1], BRILL_STOP[2], "Brill inn")
    r = N.Route(DUROTAR[0], DUROTAR[1], DUROTAR[2])
    return r, r.legs[1].ride


def test_with_both_ready_the_hearthstone_costs_more(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns)
    rows = _rows(T)
    assert [r[8] for r in rows] == ["Astral Recall", "your Hearthstone"]
    recall, stone = rows
    assert recall.spell == 556 and recall[7] == T.CAST_SECONDS
    assert stone.item == 6948 and stone[7] == T.CAST_SECONDS + T.RECALL_FIRST_SECONDS > recall[7]


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_the_plan_takes_astral_recall_whatever_the_rows_order(nav_env, order):  # noqa: F811
    # (the tie was broken by `pairs`: the rows' order alone mustn't decide it)
    lua, ns = nav_env
    T = _teleports(lua, ns)
    rows = _rows(T)
    listed = lua.table(*(rows[i] for i in order))
    stop = lua.eval("function(x, y, c) return { x = x, y = y, cont = c } end")(*BRILL_STOP)
    legs, _ = ns.Nav.Plan(DUROTAR[2], DUROTAR[0], DUROTAR[1], 7.0, stop, listed)
    assert legs[1].ride and legs[1].ride.spell == 556


def test_a_shaman_is_told_to_use_astral_recall(nav_env):  # noqa: F811
    # the directions, the steps and the use button beside them: Astral Recall, the hearthstone kept
    lua, ns = nav_env
    _teleports(lua, ns)
    r, ride = _route(lua, ns)
    assert ride and ride.use and ride.spell == 556 and ride.item is None
    assert "Use Astral Recall (to Brill)" in ns.Nav.StepsText(3)
    assert "Use your Hearthstone" not in ns.Nav.StepsText(9)
    assert ns.GPS.UseKey(ns.Nav.UseNow()) == "spell:556"


def test_astral_recall_without_a_hearthstone_in_the_bags(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns)
    lua.execute("AGPS_STONES = {}")
    assert [r[8] for r in _rows(T)] == ["Astral Recall"]
    _, ride = _route(lua, ns)
    assert ride and ride.spell == 556


def test_on_astral_recalls_cooldown_the_hearthstone(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns)
    lua.execute("AGPS_RECALL_CD = 900")  # (its 15 minutes, the client's SpellCooldowns)
    rows = _rows(T)
    assert [r[8] for r in rows] == ["your Hearthstone"] and rows[0][7] == T.CAST_SECONDS
    assert list(T.Waiting().values()) == ["Astral Recall"]
    _, ride = _route(lua, ns)
    assert ride and ride.item == 6948 and ride.spell is None
    assert "Use your Hearthstone (to Brill)" in ns.Nav.StepsText(3)
    assert ns.GPS.UseKey(ns.Nav.UseNow()) == "item:6948"


def test_another_class_is_told_to_use_the_hearthstone_as_before(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns)
    lua.execute("AGPS_KNOWN = {}")
    rows = _rows(T)
    assert [r[8] for r in rows] == ["your Hearthstone"] and rows[0][7] == T.CAST_SECONDS
    assert not T.RecallKnown()
    _, ride = _route(lua, ns)
    assert ride and ride.item == 6948
    assert "Use your Hearthstone (to Brill)" in ns.Nav.StepsText(3)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def test_the_map_menus_hearth_button_names_astral_recall_for_a_shaman(game):
    lua, ns = game
    G = ns.GPS
    hearth = next(t for t in G.QUICK.values() if t.id == "hearth")
    real_name, real_known = ns.SpellName, lua.globals().IsPlayerSpell
    try:
        ns.SpellName = lua.eval("function(real) return function(id) if id == 556 then return 'Astral Recall' end "
                                "return real(id) end end")(real_name)
        lua.execute("IsPlayerSpell = function(id) return id == 556 end")
        G.RefreshQuick()
        assert hearth.label == "Use Astral Recall" and hearth.key == "useHearthstone"
        assert hearth.icon == G.RECALL_ICON and "Astral Recall" in hearth.tip and "Hearthstone" in hearth.tip
        assert hearth.iconTex.agpsSrc == G.RECALL_ICON
        # (the scaled copies of its icon are shipped: Data/IconSizes.lua lists it)
        assert ns.IconSizes.files["icons/spell_nature_astralrecal"] and ns.IconSizes.ids[136010]
        # (another class: the hearthstone's, as before)
        lua.execute("IsPlayerSpell = function() return false end")
        G.RefreshQuick()
        assert hearth.label == "Use Hearthstone" and hearth.icon == G.HEARTH_ICON
        assert hearth.iconTex.agpsSrc == G.HEARTH_ICON
    finally:
        ns.SpellName = real_name
        lua.globals().IsPlayerSpell = real_known
        G.RefreshQuick()
