"""Immunities an Expert jumper lands with (1.4.1, item 102, Kooki3z: "more Expert jumper spells ... spells that survive
the landing"): Divine Shield, Divine Protection, Blessing of Protection (on the player) and Ice Block, each its own
option under Expert jumper (on by default). From WoW Forever's own client data (FallSpells.lua's header): physical school
immunity (SpellEffect aura 39, misc 1), which the server's fall damage checks; their ranks' durations, 5 min cooldowns,
Divine Shield and Divine Protection sharing category 37, Forbearance (25771, 60 s) stopping the paladin's three.

Each is planned as the fall spells are: only when known, off its cooldown, not blocked, its option on and Expert jumper
on; cast at the ledge when it still lasts through the plain fall (the game's gravity), else "Jump, then cast ... just
before you land" (Ice Block always: it stuns), the cue IMMUNE_CUE_S before the landing, the use button casting it.
"""

import pytest

from test_map_redraw import game  # noqa: F401
from test_spell_jumping import DEEP, TWO, autos, drops, trip  # noqa: F401

pytest.importorskip("lupa")

FMT = "function(v) return v end"
KEYS = ("jumpDivineShield", "jumpDivineProtection", "jumpBlessingOfProtection", "jumpIceBlock")


def knows(*ids):
    return "IsPlayerSpell = function(id) return " + " or ".join(f"id == {i}" for i in ids) + " end"


def no_feathers():
    return "GetItemCount = function() return 0 end"


def cooldown(id_, left):
    return (f"GetSpellCooldown = function(id) if id == {id_} then return AGPS_T - 1, {left + 1}, 1 end "
            "return 0, 0, 1 end")


@pytest.fixture
def expert(game, trip):  # noqa: F811
    """The trip fixture with Expert jumper on, the immunities' options and the auras put back after."""
    lua, ns = game
    st = ns.settings.gps
    saved = {k: st[k] for k in KEYS + ("expertJumper", "useClassSpells")}
    lua.execute("AGPS_IJ_AURAS = C_UnitAuras")
    st.expertJumper, st.useClassSpells = True, True
    try:
        yield trip
    finally:
        for k, v in saved.items():
            st[k] = v
        lua.execute("C_UnitAuras = AGPS_IJ_AURAS")
        ns.FallSpells.Refresh()


def row(ns, name):
    for r in ns.FallSpells.SPELLS.values():
        if r.name == name and r.immune:
            return r
    raise KeyError(name)


def test_the_rows_are_the_client_s_own_data(game):  # noqa: F811
    lua, ns = game
    FS = ns.FallSpells
    ds, dp, bop, ib = (row(ns, n) for n in ("Divine Shield", "Divine Protection", "Blessing of Protection", "Ice Block"))
    assert list(ds.ids.values()) == [1020, 642] and ds.durations[1020] == 12 and ds.durations[642] == 10
    assert list(dp.ids.values()) == [5573, 498] and dp.durations[5573] == 8 and dp.durations[498] == 6
    assert list(bop.ids.values()) == [10278, 5599, 1022] and bop.selfCast
    assert list(ib.ids.values()) == [11958, 27619] and ib.duration == 10 and ib.castInAir
    for r in (ds, dp, bop, ib):
        assert r.cd == 300 and r.endsOnLanding and r.immune and r.option in KEYS
        assert ns.DEFAULTS.gps[r.option] is True  # (on by default)
    assert ds.cat == dp.cat == 37 and ds.catCd == 300  # (one bubble's cooldown is the other's)
    for r in (ds, dp, bop):
        assert list(r.blockedBy.values()) == [FS.FORBEARANCE] and r.lock == "forbearance" and r.lockCd == 60
    # (cast at the ledge: the plain fall within the duration less the margin)
    lua.execute(knows(1020))
    FS.KnownId(ds)
    assert ds.duration == 12 and FS.RowReach(ds) == pytest.approx(min(FS.DROP_CAP, FS.FallDist(10)))
    assert FS.FallTime(FS.FallDist(7.5)) == pytest.approx(7.5) and FS.FallTime(FS.FallDist(2)) == pytest.approx(2)
    assert FS.RowReach(ib) == 0  # (Ice Block stuns: only in the air)
    lua.execute("IsPlayerSpell = function() return false end")


# (each spell: the ids known, the step at the 250 yd cliff's top, the button's spell)
CASES = [
    ("Divine Shield", (1020, 642), "Cast Divine Shield, then jump down", 1020),  # (12 s: lasts the 6.8 s fall)
    ("Divine Protection", (498,), "Jump, then cast Divine Protection just before you land", 498),  # (6 s: not)
    ("Blessing of Protection", (1022,), "Jump, then cast Blessing of Protection just before you land", 1022),
    ("Ice Block", (11958,), "Jump, then cast Ice Block just before you land", 11958),
]


@pytest.mark.parametrize("name,ids,step,cast", CASES, ids=[c[0] for c in CASES])
def test_each_immunity_takes_a_big_drop_when_ready(game, expert, name, ids, step, cast):  # noqa: F811
    lua, ns = game
    FS = ns.FallSpells
    r = expert(DEEP, knows(*ids), no_feathers())
    assert drops(ns, r) == 1, r.length
    c = FS.Current()
    assert c and c.row.name == name and c.id == cast and c.drop == FS.EXPERT_DROP
    m = lua.table(kind="drop", dist=5, dropYd=250)
    assert str(ns.Turns.NowText(m, lua.eval(FMT))) == step
    t = FS.CastFor(m)
    assert t.spell == cast and t.fall
    assert bool(t.early) == step.startswith("Jump")  # (dimmed till the cue when cast in the air)
    assert (t.unit == "player") == (name == "Blessing of Protection")  # (on the player, whatever's targeted)
    # (the jump's coil tooltip says the same)
    tip = ns.GPS.JumpTip(lua.table(kind="drop", dz=250))
    lines = [str(tip.lines[i]) for i in range(1, len(tip.lines) + 1)]
    assert (step if step.startswith("Jump") else f"Cast {name} at the edge, then jump") in lines


@pytest.mark.parametrize("name,ids,step,cast", CASES, ids=[c[0] for c in CASES])
def test_each_immunity_is_not_planned_when_off_on_cooldown_or_not_expert(game, expert, name, ids, step, cast):  # noqa: F811
    lua, ns = game
    FS = ns.FallSpells
    st = ns.settings.gps
    key = row(ns, name).option
    # (its own option off)
    st[key] = False
    r = expert(DEEP, knows(*ids), no_feathers())
    assert drops(ns, r) == 0 and FS.Current() is None
    st[key] = True
    # (on its cooldown, minutes left)
    r = expert(DEEP, knows(*ids), no_feathers(), cooldown(cast, 200))
    assert drops(ns, r) == 0 and FS.Current() is None
    lua.execute("GetSpellCooldown = function() return 0, 0, 1 end")
    # (not known)
    r = expert(DEEP, "IsPlayerSpell = function() return false end", no_feathers())
    assert drops(ns, r) == 0
    # (Expert jumper off: an immunity is an Expert jumper's only)
    st.expertJumper = False
    r = expert(DEEP, knows(*ids), no_feathers())
    assert drops(ns, r) == 0 and FS.Current() is None
    # (ready again, every condition met)
    st.expertJumper = True
    r = expert(DEEP, knows(*ids), no_feathers())
    assert drops(ns, r) == 1


def test_the_fall_s_cue_comes_just_before_the_landing(game, expert):  # noqa: F811
    lua, ns = game
    FS = ns.FallSpells
    expert(DEEP, knows(11958), no_feathers())
    m = lua.table(kind="drop", dist=5, dropYd=250)
    assert str(ns.Turns.NowText(m, lua.eval(FMT))) == "Jump, then cast Ice Block just before you land"
    lua.execute("IsFalling = function() return true end")
    FS.WatchFall()
    f = FS.fall
    land = FS.FallTime(250)
    assert f is not None and f.landAt - f.start == pytest.approx(land)
    assert f.landAt - f.cueAt == pytest.approx(FS.IMMUNE_CUE_S)  # (Ice Block's 10 s more than covers it)
    assert FS.FallCue() is None and FS.CastNow().early
    lua.execute(f"AGPS_T = AGPS_T + {land - FS.IMMUNE_CUE_S + 0.1}")
    assert str(FS.FallCue()) == "Cast Ice Block now!"
    t = FS.CastNow()
    assert t.spell == 11958 and not t.early
    lua.execute("IsFalling = function() return false end")
    FS.WatchFall()
    assert FS.fall is None


def test_forbearance_blocks_the_second_paladin_bubble(game, expert):  # noqa: F811
    """A paladin with Divine Shield and Blessing of Protection, two big drops 20 s apart: the first takes Divine
    Shield, the second can't take Blessing of Protection till Forbearance is gone (60 s), nor Divine Protection (its
    category's 5 min). Forbearance already up: the bubble waits for it."""
    lua, ns = game
    FS = ns.FallSpells
    expert(DEEP, knows(1020, 642, 10278, 5599, 1022), no_feathers())
    jumps = lua.eval("{ { t = 0, dz = 250, key = 'a' }, { t = 20, dz = 250, key = 'b' } }")
    plain = ns.Nav.PlainSafeDrop()
    k, wait = FS.Budget(jumps, plain)
    assert k == 2 and wait == pytest.approx(40, abs=0.5)
    # (waited for there: both taken, 40 s waited)
    k, waited = FS.Budget(jumps, plain, lua.eval("{ b = true }"))
    assert k is None and waited == pytest.approx(40, abs=0.5)
    # (Divine Protection instead of the blessing: the shared category, 5 min)
    expert(DEEP, knows(1020, 642, 5573, 498), no_feathers())
    k, wait = FS.Budget(jumps, plain)
    assert k == 2 and wait == pytest.approx(280, abs=0.5)
    # (a mage's Ice Block and a paladin's bubble aren't both anyone's; two Ice Blocks: its own 5 min cooldown)
    expert(DEEP, knows(11958), no_feathers())
    k, wait = FS.Budget(jumps, plain)
    assert k == 2 and wait == pytest.approx(280, abs=0.5)
    # Forbearance on the player now (a Blessing of Protection from another paladin): 45 s before a bubble
    expert(DEEP, knows(1020, 642), no_feathers(), """C_UnitAuras = { GetPlayerAuraBySpellID = function(id)
        if id == 25771 then return { expirationTime = AGPS_T + 45 } end end }""")
    ds = row(ns, "Divine Shield")
    assert FS.RowCooldown(ds) == pytest.approx(45, abs=0.1)
    m = lua.table(kind="drop", dist=3, dropYd=250)
    text = str(ns.Turns.NowText(m, lua.eval(FMT)))
    assert text.startswith("Wait ") and "Divine Shield" in text, text
    k, wait = FS.Budget(lua.eval("{ { t = 0, dz = 250, key = 'a' } }"), plain)
    assert k == 1 and wait == pytest.approx(45, abs=0.5)


def test_a_fall_spell_is_still_picked_first(game, expert):  # noqa: F811
    """A mage with Slow Fall and its feathers and Ice Block: Slow Fall (no cooldown) is the step's, Ice Block kept."""
    lua, ns = game
    FS = ns.FallSpells
    expert(DEEP, knows(130, 11958), "GetItemCount = function(id) return id == 17056 and 5 or 0 end")
    assert FS.Current().row.name == "Slow Fall"
    jumps = lua.eval("{ { t = 0, dz = 250, key = 'a' } }")
    assert FS.Budget(jumps, ns.Nav.PlainSafeDrop())[0] is None


def test_the_blessing_s_button_casts_it_on_the_player(game, expert):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    expert(DEEP, knows(1022), no_feathers(), a=(-1500.0, -1945.0))
    t = ns.FallSpells.CastNow()
    assert t is not None and t.spell == 1022 and t.unit == "player"
    b = G.useBtn
    b.key = None
    G.SetUseButton(b, t, lua.eval("function(b) end"))
    assert b._attr["type"] == "spell" and b._attr["unit"] == "player"
    # (another spell after it: no unit left on the button)
    lua.execute("IsPlayerSpell = function(id) return id == 11958 end")
    ns.FallSpells.Refresh()
    t = ns.FallSpells.CastNow()
    assert t is not None and t.spell == 11958 and t.unit is None
    G.SetUseButton(b, t, lua.eval("function(b) end"))
    assert b._attr.unit is None
