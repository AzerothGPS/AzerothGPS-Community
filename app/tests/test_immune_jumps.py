"""Immunities an Expert jumper lands with (1.4.1, item 102, Kooki3z: "more Expert jumper spells ... spells that survive
the landing"): Divine Shield, Divine Protection, Blessing of Protection (on the player) and Ice Block, each its own
option under Expert jumper (off by default, item 125b: nil is off, a saved value kept). From WoW Forever's own client data (FallSpells.lua's header): physical school
immunity (SpellEffect aura 39, misc 1), which the server's fall damage checks; their ranks' durations, 5 min cooldowns,
Divine Shield and Divine Protection sharing category 37, Forbearance (25771, 60 s) stopping the paladin's three.

Each is planned as the fall spells are: only when known, off its cooldown, not blocked, its option on and Expert jumper
on; cast at the ledge when it still lasts through the plain fall (the game's gravity), else "Jump, then cast ... just
before you land" (Ice Block always: it stuns), the cue IMMUNE_CUE_S before the landing, the use button casting it.
"""

import pytest

from test_map_redraw import game  # noqa: F401
from test_spell_jumping import DEEP, TWO, autos, drops, trip, world_grid  # noqa: F401

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
    """The trip fixture with Expert jumper and the immunities' options on (off by default), all put back after, the
    auras too."""
    lua, ns = game
    st = ns.settings.gps
    saved = {k: st[k] for k in KEYS + ("expertJumper", "useClassSpells")}
    lua.execute("AGPS_IJ_AURAS = C_UnitAuras")
    st.expertJumper, st.useClassSpells = True, True
    for k in KEYS:
        st[k] = True
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
        assert ns.DEFAULTS.gps[r.option] is False  # (off by default, item 125b)
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


@pytest.mark.parametrize("name,ids,step,cast", CASES, ids=[c[0] for c in CASES])
def test_a_fresh_character_plans_no_immunity_till_its_toggle_is_on(game, trip, name, ids, step, cast):  # noqa: F811
    """Item 125b (Kooki3z: "Immunity toggles ... off by default"): nothing saved, the four are off, so an Expert jumper's
    big drop takes no immunity, nil (an option missing from the saved data) off too; turned on, it does."""
    lua, ns = game
    FS = ns.FallSpells
    st = ns.settings.gps
    key = row(ns, name).option
    saved = {k: st[k] for k in KEYS + ("expertJumper", "useClassSpells")}
    lua.execute("AGPS_IJ_AURAS = C_UnitAuras")
    try:
        assert all(st[k] is False for k in KEYS)  # (the defaults: nothing saved but them)
        st.expertJumper, st.useClassSpells = True, True
        r = trip(DEEP, knows(*ids), no_feathers())
        assert drops(ns, r) == 0 and FS.Current() is None
        st[key] = None
        r = trip(DEEP, knows(*ids), no_feathers())
        assert drops(ns, r) == 0 and FS.Current() is None
        # (its toggle turned on: the drop is taken with it)
        st[key] = True
        r = trip(DEEP, knows(*ids), no_feathers())
        assert drops(ns, r) == 1
        c = FS.Current()
        assert c and c.row.name == name and c.id == cast
    finally:
        for k, v in saved.items():
            st[k] = v
        lua.execute("C_UnitAuras = AGPS_IJ_AURAS")
        FS.Refresh()


# --- Item 125c (Kooki3z 2026-11-27): "On a mage if slow fall reagents are available then this should be the priority
# spell to jump with, immunities are fallbacks". A normal fall spell castable now is the step's and the trip's
# (FallSpells.Prefer, Budget's ties); an immunity only with none: no reagent, not known, on its cooldown. The Barrens'
# hills north of the Crossroads' south road (test_world_grid's BARRENS_A, B: `.go xyz -2241 -1917 95 1`, then
# `/way 1 -2743.5 -2892.9`), whose way down is a spell jump of 85 yd and more, on the world grid.

BARRENS_TOP, BARRENS_FOOT = (-2241.0, -1916.9), (-2743.5, -2892.9)
WALK_ON_AIR = 1259416


def feathers(n):
    return f"GetItemCount = function(id) return id == 17056 and {n} or 0 end"


def barrens(expert, *setup):
    return expert("{}", *setup, a=BARRENS_TOP, b=BARRENS_FOOT)


def big_jumps(ns, r):
    js = ns.Nav.SpellJumps(r)
    return [js[i].dz for i in range(1, len(js) + 1)]


def drop_step(lua, ns, dz):
    """The step and the use button at the top of a drop of dz yards, 5 yd ahead."""
    m = lua.table(kind="drop", dist=5, dropYd=dz)
    return str(ns.Turns.NowText(m, lua.eval(FMT))), ns.FallSpells.CastFor(m)


def test_a_mage_with_light_feathers_jumps_with_slow_fall_not_ice_block(game, expert, world_grid):  # noqa: F811
    lua, ns = game
    FS = ns.FallSpells
    r = barrens(expert, knows(130, 11958), feathers(20))
    dzs = big_jumps(ns, r)
    assert dzs and max(dzs) >= 80, dzs  # (down the hillside, a spell jump)
    c = FS.Current()
    assert c and c.row.name == "Slow Fall" and c.id == 130
    assert FS.Budget(ns.Nav.SpellJumps(r), ns.Nav.PlainSafeDrop())[0] is None
    for dz in dzs:
        text, t = drop_step(lua, ns, dz)
        assert "Slow Fall" in text and "Ice Block" not in text, text
        assert t.spell == 130
    # (the jump's coil tooltip names it too)
    tip = ns.GPS.JumpTip(lua.table(kind="drop", dz=max(dzs)))
    lines = [str(tip.lines[i]) for i in range(1, len(tip.lines) + 1)]
    assert any("Slow Fall" in s for s in lines) and not any("Ice Block" in s for s in lines), lines


def test_the_same_mage_with_no_feathers_jumps_with_ice_block(game, expert, world_grid):  # noqa: F811
    lua, ns = game
    FS = ns.FallSpells
    r = barrens(expert, knows(130, 11958), feathers(0))
    dzs = big_jumps(ns, r)
    assert dzs and max(dzs) >= 80, dzs
    c = FS.Current()
    assert c and c.row.name == "Ice Block" and c.id == 11958
    text, t = drop_step(lua, ns, max(dzs))
    assert text == "Jump, then cast Ice Block just before you land" and t.spell == 11958


def test_ice_block_off_and_no_feathers_the_route_goes_round(game, expert, world_grid):  # noqa: F811
    lua, ns = game
    FS, N = ns.FallSpells, ns.Nav
    jumped = barrens(expert, knows(130, 11958), feathers(0)).totalYards
    ns.settings.gps.jumpIceBlock = False
    r = barrens(expert, knows(130, 11958), feathers(0))
    assert FS.Current() is None and big_jumps(ns, r) == []
    R = ns.Router
    for p in range(1, len(r.parts) + 1):
        part = r.parts[p]
        for i in range(1, len(part.pts) // 2):
            if part.kinds[i] == R.KIND_DROP and (i == 1 or part.kinds[i - 1] != R.KIND_DROP):
                dz = R.DropFall(part.pts, part.kinds, i)
                dz = dz[0] if isinstance(dz, tuple) else dz
                assert not dz or dz <= N.PlainSafeDrop() + 0.5, dz
    assert r.totalYards > jumped  # (the way round the hills)


def test_a_paladin_still_lands_with_divine_shield(game, expert, world_grid):  # noqa: F811
    # (a paladin has no normal fall spell: the immunity it has on is the one, feathers in the bags or not)
    lua, ns = game
    FS = ns.FallSpells
    r = barrens(expert, knows(1020, 642), feathers(20))
    dzs = big_jumps(ns, r)
    assert dzs and max(dzs) >= 80, dzs
    c = FS.Current()
    assert c and c.row.name == "Divine Shield" and c.id == 1020
    text, t = drop_step(lua, ns, max(dzs))
    assert "Divine Shield" in text and t.spell == 1020, text


def test_a_normal_fall_spell_on_its_cooldown_leaves_the_jump_to_the_immunity(game, expert):  # noqa: F811
    """Walk on Air (a racial, 2 min) and Ice Block both ready: Walk on Air. On its cooldown (30 s left) with Ice Block
    castable now: Ice Block. Picked on the trip (Nav.PickFallSpell), an immunity still doesn't beat a normal one ready,
    in the step or the trip's plan (FallSpells.Budget's ties)."""
    lua, ns = game
    FS, N = ns.FallSpells, ns.Nav
    expert(DEEP, knows(WALK_ON_AIR, 11958), feathers(0))
    assert FS.Current().row.name == "Walk on Air"
    lua.execute(cooldown(WALK_ON_AIR, 30))
    FS.Refresh()
    assert FS.Current().row.name == "Ice Block"
    lua.execute("GetSpellCooldown = function() return 0, 0, 1 end")
    FS.Refresh()
    assert FS.Current().row.name == "Walk on Air"
    # (the trip's pick an immunity: the normal one still first, here and in the plan)
    N.fallPick = "Ice Block"
    try:
        FS.Refresh()
        assert FS.Current().row.name == "Walk on Air"
        jumps = lua.eval("{ { t = 0, dz = 250, key = 'a' }, { t = 20, dz = 250, key = 'b' } }")
        # (two jumps 20 s apart: Walk on Air the first, its 2 min cooldown leaves the second to Ice Block)
        assert FS.Budget(jumps, N.PlainSafeDrop())[0] is None
        # (Ice Block on its cooldown too: the second jump has no source in time)
        lua.execute(cooldown(11958, 200))
        assert FS.Budget(jumps, N.PlainSafeDrop())[0] == 2
    finally:
        N.fallPick = None
        lua.execute("GetSpellCooldown = function() return 0, 0, 1 end")
        FS.Refresh()
