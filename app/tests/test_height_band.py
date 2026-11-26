"""The height band from range checks (item 104, 1.4.1; HeightBand.lua): the game checks ranges in 3D, so an NPC standing
still at its one spawn nearby (Data/Npcs.lua, ns.NpcsStill) bounds the player's height. Extra evidence for the floor
followed (Nav.TrackCityZ, Nav.TrackGridZ, CityGrid.TrackFloor): floors out of the band are dropped, never the only source,
and with no NPC in reach nothing changes.

The range checks here are a small make-believe world (`_RangeWorld`): the player's true height, the NPCs the unit tokens
name, and the client's answers from the 3D distance to them."""

import math

import pytest

from test_map_redraw import game  # noqa: F401

# (shipped NPCs: level, x, y, z; all standing still, ns.NpcsStill)
GRIZZLE = (10001, 1331.9, 334.7, -63.6)  # Undercity, Grizzle Halfmane (347): the roads there at -65 and -35 overhead
RENEE = (0, 2269.5, 244.9, 34.3)  # Brill's inn, Innkeeper Renee (5688)
MARION = (0, 2271.0, 243.0, 41.2)  # upstairs, Marion Call (2130)
MARAUDON = (1, -1244.0, 2896.0)  # Maraudon's outer cave: passages over passages under the hill (74, 88, 128)

_SETUP = """
AGPS_RW = { units = {}, spellR = {}, interact = { [2] = 11.11, [3] = 9.9, [4] = 28 }, calls = 0, p = { 0, 0, 0 } }
AGPS_RW_SAVED = { C_Spell = rawget(_G, 'C_Spell'), UnitExists = rawget(_G, 'UnitExists'),
  IsPlayerSpell = rawget(_G, 'IsPlayerSpell'), CheckInteractDistance = rawget(_G, 'CheckInteractDistance'),
  AGPS_GUIDS = rawget(_G, 'AGPS_GUIDS'), InCombatLockdown = InCombatLockdown }
local function D(n)
  local p = AGPS_RW.p
  return math.sqrt((n.x - p[1]) ^ 2 + (n.y - p[2]) ^ 2 + (n.z - p[3]) ^ 2)
end
UnitExists = function(u) return AGPS_RW.units[u] ~= nil end
IsPlayerSpell = function(id) return AGPS_RW.spellR[id] ~= nil end
C_Spell = {
  GetSpellInfo = function(id) local r = AGPS_RW.spellR[id] return r and { name = 'Spell', maxRange = r, minRange = 0 } end,
  IsSpellInRange = function(id, u)
    AGPS_RW.calls = AGPS_RW.calls + 1
    local n, r = AGPS_RW.units[u], AGPS_RW.spellR[id]
    if not (n and r) then return nil end
    return D(n) <= r
  end,
}
CheckInteractDistance = function(u, i)
  AGPS_RW.calls = AGPS_RW.calls + 1
  local n, r = AGPS_RW.units[u], AGPS_RW.interact[i]
  if not (n and r) then return false end
  return D(n) <= r
end
AGPS_GUIDS = {}
"""
_TEARDOWN = """
C_Spell, UnitExists, IsPlayerSpell = AGPS_RW_SAVED.C_Spell, AGPS_RW_SAVED.UnitExists, AGPS_RW_SAVED.IsPlayerSpell
CheckInteractDistance, AGPS_GUIDS = AGPS_RW_SAVED.CheckInteractDistance, AGPS_RW_SAVED.AGPS_GUIDS
InCombatLockdown = AGPS_RW_SAVED.InCombatLockdown
"""


class _RangeWorld:
    def __init__(self, lua, ns):
        self.lua, self.ns = lua, ns

    def __enter__(self):
        self.lua.execute(_SETUP)
        HB = self.ns.HeightBand
        HB.Reset()
        HB.ResetLadders()
        return self

    def __exit__(self, *exc):
        self.lua.execute(_TEARDOWN)
        HB = self.ns.HeightBand
        HB.Reset()
        HB.ResetLadders()
        HB.ResetSpawns()
        HB.ResetStill()

    def player(self, x, y, z):
        self.lua.execute(f"AGPS_RW.p = {{ {x}, {y}, {z} }}")

    def name(self, unit, npc_id, spot):
        """The unit token `unit` names NPC `npc_id` standing at `spot` (level, x, y, z)."""
        _, x, y, z = spot
        self.lua.execute(f"AGPS_RW.units['{unit}'] = {{ x = {x}, y = {y}, z = {z} }}"
                         f" AGPS_GUIDS['{unit}'] = 'Creature-0-1-0-1-{npc_id}-0000000001'")

    def forget(self):
        self.lua.execute("AGPS_RW.units = {} AGPS_GUIDS = {}")

    def spell(self, spell_id, r):
        self.lua.execute(f"AGPS_RW.spellR[{spell_id}] = {r}")
        self.ns.HeightBand.ResetLadders()

    @property
    def calls(self):
        return int(self.lua.eval("AGPS_RW.calls"))


@pytest.fixture(params=[True, False], ids=["grids", "roads"])
def grids(request, game):  # noqa: F811
    """With the grids on (the capitals' floor from CityGrid.TrackFloor) and off (the roads', Nav.TrackCityZ)."""
    st = game[1].settings.gps
    was = (st.cityGrid, st.worldGrid)
    st.cityGrid = st.worldGrid = request.param
    yield request.param
    st.cityGrid, st.worldGrid = was


def _tick(lua, s=1.0):
    lua.execute(f"AGPS_T = AGPS_T + {s}")


def _teleported(lua, ns):
    """A teleport, a hearth, a login: nothing followed, a while later."""
    ns.Nav.ResetCityTrack()
    ns.Nav.ResetTrack()
    _tick(lua, 30)


# --- the data -----------------------------------------------------------------------------------------------------------

def test_only_npcs_that_stand_still_at_one_spawn_near_count(game):  # noqa: F811
    lua, ns = game
    HB = ns.HeightBand
    assert HB.Still(347) and HB.Still(5688)
    sp = HB.Spawns(5688)
    assert [sp[1], round(sp[2], 1), round(sp[3], 1), round(sp[4], 1)] == [0, 2269.5, 244.9, 34.3]
    x, y, z = HB.SpawnOf(5688, 0, 2266.0, 241.0)
    assert (round(x, 1), round(y, 1), round(z, 1)) == (2269.5, 244.9, 34.3)
    assert HB.SpawnOf(5688, 0, 2266.0, 541.0) is None  # (none near)
    assert HB.SpawnOf(5688, 1, 2266.0, 241.0) is None  # (another level)
    # (an NPC that wanders or patrols somewhere: never; and one the data hasn't)
    packed = str(ns.NpcsPacked)
    moving = next(int(line.split("|")[0]) for line in packed.split("\n")
                  if line and not HB.Still(int(line.split("|")[0])))
    assert HB.SpawnOf(moving, 0, 0, 0) is None
    assert HB.Spawns(99999999) is None


def test_the_band_from_in_and_out_of_range(game):  # noqa: F811
    lua, ns = game
    HB = ns.HeightBand
    rd = lua.eval("function(rows) return rows end")
    slack = HB.RANGE_SLACK + HB.WANDER_YD
    band = HB.Band(rd(lua.table(lua.table(x=0, y=0, z=10, r=9.9, inside=True))), 0, 0)
    assert band[1][1] == pytest.approx(10 - 9.9 - slack) and band[1][2] == pytest.approx(10 + 9.9 + slack)
    band = HB.Band(rd(lua.table(lua.table(x=0, y=0, z=10, r=28, inside=False))), 0, 0)
    h = math.sqrt(28 ** 2 - HB.WANDER_YD ** 2)
    assert len(band) == 2 and band[1][2] == pytest.approx(10 - h) and band[2][1] == pytest.approx(10 + h)
    assert HB.InBand(band, 10 + h + 0.5) and not HB.InBand(band, 10)
    assert HB.InBand(None, 1234)  # (no band: every height)
    kept = HB.Keep(band, lua.table(lua.table(z=10), lua.table(z=60)), "z")
    assert len(kept) == 1 and kept[1].z == 60
    assert HB.Keep(band, lua.table(lua.table(z=10)), "z") is None  # (it leaves none: it says nothing)


# --- Undercity: two floors 30 yd apart, after a teleport --------------------------------------------------------------

def test_after_a_teleport_by_an_npc_the_band_picks_the_floor_under_or_over_it(game, grids):  # noqa: F811
    """With the grids (the city grid's floor, CityGrid.TrackFloor) and without (the roads' floor, Nav.TrackCityZ)."""
    lua, ns = game
    N = ns.Nav
    lv, x, y = GRIZZLE[0], GRIZZLE[1], GRIZZLE[2] - 4.0
    with _RangeWorld(lua, ns) as w:
        # (no NPC named: the roads near are on both floors, -65 and -35; can't tell)
        _teleported(lua, ns)
        assert N.TrackCityZ(lv, x, y) is None
        # (down by Grizzle, his floor: in reach of him)
        w.name("mouseover", 347, GRIZZLE)
        w.player(x, y, -65.0)
        _teleported(lua, ns)
        z = N.TrackCityZ(lv, x, y)
        assert z is not None and abs(z - -65) < 2, z
        # (on the walkway over him: out of reach of him)
        w.player(x, y, -35.0)
        _teleported(lua, ns)
        ns.HeightBand.Reset()
        z = N.TrackCityZ(lv, x, y)
        assert z is not None and abs(z - -35) < 2, z
        assert str(ns.HeightBand.last.pick.by) == ("city grid" if grids else "band")


def test_a_floor_followed_wrong_is_put_right_by_the_band(game, grids):  # noqa: F811
    """Followed up on the walkway (a lift ridden, a drop, a guess gone wrong), the band by Grizzle says his floor."""
    lua, ns = game
    N = ns.Nav
    lv, x, y = GRIZZLE[0], GRIZZLE[1], GRIZZLE[2] - 4.0
    with _RangeWorld(lua, ns) as w:
        _teleported(lua, ns)
        N.SetTrackForTests(lv, x, y, -35.0)
        _tick(lua, 0.3)
        assert abs(N.TrackCityZ(lv, x + 0.5, y) - -35) < 2  # (no NPC named: the floor followed kept)
        w.name("target", 347, GRIZZLE)
        w.player(x + 1, y, -65.0)
        _tick(lua, 0.3)
        z = N.TrackCityZ(lv, x + 1, y)
        assert abs(z - -65) < 2, z
        assert str(ns.HeightBand.last.pick.by) == ("city grid" if grids else "band: not the floor followed")


# --- Brill's inn: floors 7 yd apart, no NPC in reach -------------------------------------------------------------------

def test_with_no_npc_in_reach_nothing_changes(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    with _RangeWorld(lua, ns) as w:
        # (by the innkeeper, the roads near on every floor: can't tell, with or without the band, as before)
        _teleported(lua, ns)
        assert N.TrackCityZ(0, 2266.0, 241.0) is None
        assert w.calls == 0
        # (the innkeeper named: her floor and upstairs are 7 yd apart, closer than the range checks can tell; still
        # unknown, never a guess)
        w.name("target", 5688, RENEE)
        w.name("mouseover", 2130, MARION)
        w.player(2266.0, 241.0, 34.3)
        _teleported(lua, ns)
        assert N.TrackCityZ(0, 2266.0, 241.0) is None
        assert w.calls > 0
        # (followed in by the door: the floor followed kept, the band allowing it)
        _teleported(lua, ns)
        N.SetTrackForTests(0, 2266.0, 241.0, 34.3)
        _tick(lua, 0.3)
        assert abs(N.TrackCityZ(0, 2266.5, 241.0) - 34.3) < 1
        # (an NPC named far off (a spawn not near): no reading)
        w.forget()
        ns.HeightBand.Reset()
        w.name("target", 347, GRIZZLE)
        _tick(lua, 0.3)
        assert abs(N.TrackCityZ(0, 2267.0, 241.0) - 34.3) < 1
        assert ns.HeightBand.readings[1] is None


def test_the_hearthstone_into_brills_inn_still_lands_on_the_innkeepers_floor(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    with _RangeWorld(lua, ns) as w:
        w.name("softinteract", 5688, RENEE)
        w.player(2266.0, 241.0, 34.3)
        _teleported(lua, ns)
        N.Hearthed(0, 2266.0, 241.0)
        _tick(lua, 1)
        assert abs(N.TrackCityZ(0, 2266.0, 241.0) - 34.5) < 1


# --- a cave under a hill (the world grid's stacked surfaces) ----------------------------------------------------------

def test_in_a_cave_under_a_hill_the_band_picks_the_passage(game):  # noqa: F811
    lua, ns = game
    N, WG, HB, st = ns.Nav, ns.WorldGrid, ns.HeightBand, ns.settings.gps
    was = st.worldGrid
    st.worldGrid = True
    WG.Set(True)
    old_still = ns.NpcsStill
    lx, ly = MARAUDON[1], MARAUDON[2]
    try:
        c = WG.Cont(1)
        zs = sorted(e.z for e in WG.SurfacesAt(c, lx, ly).values())
        assert len(zs) >= 3, zs
        low, mid = zs[0], zs[1]
        # (an NPC standing still in the passage over the low one, a few yards off: a made-up one, Maraudon has no
        # friendly NPC)
        npc = (1, lx + 3.0, ly, mid)
        ns.NpcsStill = str(old_still) + " 99999991"
        HB.ResetStill()
        lua.execute(f"AGPS_NS.NpcsPacked = '99999991|Test|||||1 {npc[1]} {npc[2]} {npc[3]}\\n' .. AGPS_NS.NpcsPacked")
        HB.ResetSpawns()
        lua.execute("AGPS_T = AGPS_T + 1000; IsIndoors = function() return true end")
        with _RangeWorld(lua, ns) as w:
            # (nothing named: indoors, the highest surface under the hill's ground, as before)
            N.ResetTrack()
            lua.execute("AGPS_T = AGPS_T + 100")
            before = N.TrackGridZ(1, lx, ly)
            assert before is not None and abs(before - low) > 5, (before, zs)
            # (named, but out of the short checks' reach of the NPC in the passage overhead: not its passage, nor the
            # hill's top over it; the low one)
            w.name("target", 99999991, npc)
            w.player(lx, ly, low)
            lua.execute("AGPS_T = AGPS_T + 100")
            z = N.TrackGridZ(1, lx, ly)
            assert z is not None and abs(z - low) < 1, (z, zs)
    finally:
        lua.execute("IsIndoors = function() return false end")
        lua.execute("AGPS_NS.NpcsPacked = AGPS_NS.NpcsPacked:gsub('^99999991|[^\\n]*\\n', '')")
        ns.NpcsStill = old_still
        HB.ResetStill()
        HB.ResetSpawns()
        st.worldGrid = was
        WG.Set(bool(was))


# --- cost and safety ---------------------------------------------------------------------------------------------------

def test_the_client_is_asked_at_most_every_quarter_second_and_never_in_combat(game):  # noqa: F811
    lua, ns = game
    HB = ns.HeightBand
    lv, x, y = GRIZZLE[0], GRIZZLE[1], GRIZZLE[2] - 4.0
    with _RangeWorld(lua, ns) as w:
        w.spell(2050, 40)
        w.name("target", 347, GRIZZLE)
        w.player(x, y, -65.0)
        _tick(lua, 10)
        HB.Here(lv, x, y)
        n = w.calls
        assert n > 0 and n <= 2 * HB.RANGES + 3
        assert any(str(r.src) == "spell2050" for r in HB.readings.values())
        for _ in range(20):  # (twenty frames in the same quarter second: no more asking)
            lua.execute("AGPS_T = AGPS_T + 0.01")
            HB.Here(lv, x, y)
        assert w.calls == n
        # (in combat: nothing asked, and an error in a check is caught)
        lua.execute("InCombatLockdown = function() return true end")
        _tick(lua, 1)
        HB.Here(lv, x, y)
        assert w.calls == n
        lua.execute("InCombatLockdown = AGPS_RW_SAVED.InCombatLockdown")
        lua.execute("C_Spell.IsSpellInRange = function() error('boom') end")
        _tick(lua, 1)
        HB.Here(lv, x, y)
