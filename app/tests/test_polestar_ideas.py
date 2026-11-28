"""Item 135 b-e (1.4.2): ideas taken from Polestar's design (GPL-3: the ideas only, our own code).

(b) A road through a zone too high for the player costs Router.LEVEL_ROAD_FACTOR a yard (about 3x) instead of the full
    LEVEL_FACTOR, for zones at most LEVEL_ROAD_MAX (about 20) levels over the player's; off the roads as before.
(c) A walk that starts or ends inside the other faction's town is priced there as if the player had no faction in the
    terrain search too (Passability.FindPath's `townEnds`), as the Router's legs and the world grid already price it.
(d) More floor evidence folded into the height band (HeightBand.Extras): the place name's rooms where floors stack and
    the flight master's floor after a landing; never the only source.
(e) As a ghost, the corpse run against the Spirit Healer (Nav.CorpseNote): the time saved, the sickness and durability.
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401

DARKSHIRE = (-10515.0, -1261.0)
SWAMP_WEST = (-10450.0, -2850.0)  # (Swamp of Sorrows, west: the road there runs through Deadwind Pass, 55-60)
DEADWIND = 1430
SOUTHSHORE_IN = (-845.0, -540.0)  # (inside Southshore, the Alliance's town in Hillsbrad)
SOUTHSHORE_OUT = (-620.0, -760.0)  # (out on the Hillsbrad fields, east of it)
STORMWIND_FM = (0, -8835.8, 490.1, 109.7)  # (Dungar Longdrink on the Stormwind gryphon tower)
GRIZZLE = (10001, 1331.9, 334.7)  # (Undercity's Trade Quarter, Grizzle Halfmane)
ELWYNN_HEALER = (0, -9341.0, 165.0, 61.6)  # (a Spirit Healer's spawn, Data/Npcs.lua)


def _pts(r):
    flat = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


def _zone_yards(R, cont, r, zone):
    pts = _pts(r)
    return sum(dict(R.ZoneYards(cont, *pts[i], *pts[i + 1]).items()).get(zone, 0) for i in range(len(pts) - 1))


@pytest.fixture
def alliance(game):  # noqa: F811
    lua, ns = game
    cdb, st = ns.CharDB(), ns.settings.gps
    was = (cdb.faction, st.avoidHighZones, st.avoidHostile)
    lua.execute('AGPS_FAC_SAVED = UnitFactionGroup UnitFactionGroup = function() return "Alliance", "Alliance" end')
    cdb.faction = "Alliance"
    st.avoidHighZones = True
    yield lua, ns
    lua.execute("UnitFactionGroup = AGPS_FAC_SAVED AGPS_LEVEL = nil")
    cdb.faction, st.avoidHighZones, st.avoidHostile = was
    ns.Router.Reset()


@pytest.fixture
def horde(game):  # noqa: F811
    lua, ns = game
    cdb, st = ns.CharDB(), ns.settings.gps
    was = (cdb.faction, st.avoidHostile, st.avoidElites)
    lua.execute('AGPS_FAC_SAVED = UnitFactionGroup UnitFactionGroup = function() return "Horde", "Horde" end')
    cdb.faction = "Horde"
    st.avoidHostile, st.avoidElites = True, False
    ns.Router.HostileChanged()
    yield lua, ns
    lua.execute("UnitFactionGroup = AGPS_FAC_SAVED")
    cdb.faction, st.avoidHostile, st.avoidElites = was
    ns.Router.HostileChanged()


# --- (b) roads through zones too high ---------------------------------------------------------------------------------

def test_a_road_through_a_zone_too_high_costs_the_road_factor_up_to_its_level_limit(alliance):
    lua, ns = alliance
    R = ns.Router
    assert (R.LEVEL_ROAD_FACTOR, R.LEVEL_ROAD_MAX, R.LEVEL_FACTOR) == (3, 20, 4)
    red = lua.eval("{ [1] = 20, [2] = 21, [3] = true }")
    assert R.RedFactor(red, 1, True) == 3 and R.RedFactor(red, 1, False) == 4  # (off the roads: as before)
    assert R.RedFactor(red, 2, True) == 4  # (more than LEVEL_ROAD_MAX over: roads too)
    assert R.RedFactor(red, 3, True) == 4 and R.RedFactor(red, 9, True) == 1
    # (the set says how far over each zone is: Deadwind Pass, 55-60, is 20 over a level 35)
    lua.execute("AGPS_LEVEL = 35")
    assert R.RedZones()[DEADWIND] == 20
    lua.execute("AGPS_LEVEL = 34")
    assert R.RedZones()[DEADWIND] == 21


def test_the_road_through_deadwind_pass_is_taken_within_20_levels_and_avoided_past_them(alliance):
    # Darkshire to the Swamp of Sorrows: the road through Deadwind Pass (about 800 yd of it) or the way round by
    # Redridge, 6.7k yd. LEVEL_FACTOR raised to 8 here so the full avoidance clearly wins: at level 35 (Deadwind 20 over)
    # its road costs LEVEL_ROAD_FACTOR and is taken; at 34 (21 over) it costs the full factor and the way round wins; and
    # at 35 with roads priced as the open ground (the old way) the way round wins too.
    lua, ns = alliance
    R = ns.Router
    was = (R.LEVEL_FACTOR, R.LEVEL_ROAD_FACTOR)

    def route(level):
        lua.execute(f"AGPS_LEVEL = {level}")
        R.Reset()
        return R.Route(0, *DARKSHIRE, *SWAMP_WEST, lua.table(offroad=False))

    try:
        R.LEVEL_FACTOR = 8
        through = route(35)
        assert through.length < 2500 and _zone_yards(R, 0, through, DEADWIND) > 500, through.length
        round_ = route(34)
        assert round_.length > 5000 and _zone_yards(R, 0, round_, DEADWIND) < 50, round_.length
        R.LEVEL_ROAD_FACTOR = 8
        old = route(35)
        assert old.length > 5000, old.length
    finally:
        R.LEVEL_FACTOR, R.LEVEL_ROAD_FACTOR = was
        R.Reset()


def test_the_world_grid_prices_road_ground_in_a_zone_too_high_at_the_road_factor(alliance):
    lua, ns = alliance
    R, WG = ns.Router, ns.WorldGrid
    # (a point in Deadwind Pass on the line from Darkshire to the swamp)
    spot = next((DARKSHIRE[0] + (SWAMP_WEST[0] - DARKSHIRE[0]) * t / 100, DARKSHIRE[1] + (SWAMP_WEST[1] - DARKSHIRE[1]) * t / 100)
                for t in range(100) if R.ZoneAt(0, DARKSHIRE[0] + (SWAMP_WEST[0] - DARKSHIRE[0]) * t / 100,
                                                 DARKSHIRE[1] + (SWAMP_WEST[1] - DARKSHIRE[1]) * t / 100) == DEADWIND)
    for over, less in ((20, 1), (21, 0)):
        x = lua.eval(f"{{ cont = 0, f = {{}}, red = {{ [{DEADWIND}] = {over} }}, redExempt = {{}} }}")
        assert WG.Extra(x, 7, *spot) == R.LEVEL_FACTOR - 1  # (off the roads: as before)
        assert WG.RoadLess(x, 7) == less  # (along road ground: LEVEL_ROAD_FACTOR within 20 levels)


# --- (c) a walk out of or into the other faction's town ---------------------------------------------------------------

def test_a_walk_out_of_an_enemy_town_the_trip_starts_in_is_priced_as_if_no_faction(horde):
    lua, ns = horde
    R, P = ns.Router, ns.Passability
    side = R.HostileSide()
    assert side and R.HostileTownsNear(0, side, *SOUTHSHORE_IN)
    sx, sy, tx, ty = *SOUTHSHORE_IN, *SOUTHSHORE_OUT
    assert R.WalkTownEnds(0, sx, sy, tx, ty, sx, sy, tx, ty) == "s"
    assert R.WalkTownEnds(0, sx, sy, tx, ty, sx, sy, -700.0, -600.0) == "s"  # (a walk from the start onto a road)
    assert R.WalkTownEnds(0, sx, sy, tx, ty, -700.0, -600.0, tx, ty) is None  # (neither end the trip's)
    assert R.WalkTownEnds(0, tx, ty, sx, sy, tx, ty, sx, sy) == "t"
    priced = P.FindPath(0, sx, sy, tx, ty, False, False)
    free = P.FindPath(0, sx, sy, tx, ty, False, False, "s")
    assert priced and free
    c_priced, c_free = priced[0], free[0]
    straight = math.dist(SOUTHSHORE_IN, SOUTHSHORE_OUT)
    # (the guards' cells at HOSTILE_FACTOR before; free now: about the walk's own yards)
    assert c_free < c_priced and c_free < straight * 1.6, (c_free, c_priced, straight)


def test_a_walk_from_open_ground_is_priced_as_ever(horde):
    lua, ns = horde
    R, P = ns.Router, ns.Passability
    side = R.HostileSide()
    # (a walk that starts in open ground: "s" names no town there, the walk priced as ever)
    a = P.FindPath(0, *SOUTHSHORE_OUT, *SOUTHSHORE_IN, False, False)
    b = P.FindPath(0, *SOUTHSHORE_OUT, *SOUTHSHORE_IN, False, False, "s")
    assert a and b and abs(a[0] - b[0]) < 1e-6
    assert not R.HostileTownsNear(0, side, *SOUTHSHORE_OUT)


# --- (d) the place name and a landing as floor evidence ---------------------------------------------------------------

@pytest.fixture
def band(game):  # noqa: F811
    lua, ns = game
    HB = ns.HeightBand
    lua.execute("""AGPS_ZT_SAVED = { GetMinimapZoneText, GetSubZoneText, IsIndoors }""")
    HB.Reset()
    yield lua, ns
    lua.execute("GetMinimapZoneText, GetSubZoneText, IsIndoors = AGPS_ZT_SAVED[1], AGPS_ZT_SAVED[2], AGPS_ZT_SAVED[3]")
    HB.Reset()


def test_the_flight_masters_are_read_from_the_shipped_npcs(band):
    lua, ns = band
    HB = ns.HeightBand
    sp = HB.ServiceSpawns("f")
    spots = [(sp[i], round(sp[i + 1], 1), round(sp[i + 2], 1), round(sp[i + 3], 1)) for i in range(1, len(sp) + 1, 4)]
    assert STORMWIND_FM in spots and len(spots) >= 60
    x, y, z, d = HB.NearestService("f", 0, -8838.0, 486.0, 40)
    assert round(z, 1) == 109.7 and d < 5
    assert HB.NearestService("f", 0, -8838.0, 286.0, 40) is None


def test_a_landing_puts_the_band_on_the_flight_masters_floor_for_a_while(band):
    lua, ns = band
    HB, N = ns.HeightBand, ns.Nav
    assert round(HB.Landed(0, -8838.0, 486.0), 1) == 109.7
    b = HB.Here(0, -8838.0, 486.0)
    assert b and b[1][1] >= 109.7 - HB.LAND_Z - 0.01 and b[len(b)][2] <= 109.7 + HB.LAND_Z + 0.01
    assert "landing" in list(HB.last.extras.values())
    # (the roads there: the street under the tower and the tower's top; the band picks the top, as the range checks do)
    hs = lua.eval("{ { z = 94.0, d = 2, flat = true, edge = 1 }, { z = 109.5, d = 3, flat = true, edge = 2 } }")
    assert round(N.BandFloor(0, -8838.0, 486.0, hs, None)[0], 1) == 109.5
    # (walked off the landing, or later: nothing)
    assert HB.Here(0, -8838.0 + HB.LAND_YD + 5, 486.0) is None
    lua.execute(f"AGPS_T = AGPS_T + {HB.LAND_SECONDS + 1}")
    assert HB.Here(0, -8838.0, 486.0) is None


def test_a_landing_never_overrules_the_range_checks(band):
    lua, ns = band
    HB = ns.HeightBand
    HB.Landed(0, -8838.0, 486.0)
    # (the range checks say 80-100: the landing's 106.7-112.7 would leave nothing, so it's left out)
    b = HB.WithExtras(lua.eval("{ { 80, 100 } }"), 0, -8838.0, 486.0)[0]
    assert [(b[i][1], b[i][2]) for i in range(1, len(b) + 1)] == [(80, 100)]
    # (and where they overlap, both)
    b = HB.WithExtras(lua.eval("{ { 100, 111 } }"), 0, -8838.0, 486.0)[0]
    assert round(b[1][1], 1) == round(109.7 - HB.LAND_Z, 1) and b[1][2] == 111


def test_the_place_name_gives_the_floor_its_rooms_span_where_floors_stack(band):
    lua, ns = band
    HB, G = ns.HeightBand, ns.GPS
    level, x, y = GRIZZLE
    lua.execute('GetMinimapZoneText = function() return "Trade Quarter" end GetSubZoneText = function() return "" end')
    lo, hi = HB.RoomBand(level, x, y, "Trade Quarter")
    wmo = ns.CityLevels[level].wmo
    assert (lo, hi) == tuple(G.ZoneTextBand(0, x, y, "Trade Quarter", wmo))  # (the minimap's band the start used)
    got = HB.ZoneTextBand(level, x, y)  # (down in a city's level: Undercity says outdoors)
    assert got[0] == lo and got[1] == hi and str(got[2]) == "Trade Quarter"
    b = HB.Here(level, x, y)
    assert b and b[1][1] >= lo - 0.01 and b[len(b)][2] <= hi + 0.01
    # (a name no room has: nothing; the subzone's name next)
    HB.Reset()
    lua.execute('GetMinimapZoneText = function() return "Nowhere" end GetSubZoneText = function() return "Trade Quarter" end')
    assert HB.ZoneTextBand(level, x, y)[0] == lo
    lua.execute('GetSubZoneText = function() return "Nowhere" end')
    HB.Reset()
    assert HB.ZoneTextBand(level, x, y)[0] is None and HB.Here(level, x, y) is None


def test_out_on_the_land_the_place_name_counts_only_indoors(band):
    lua, ns = band
    HB = ns.HeightBand
    # (Stormwind's Slaughtered Lamb, its rooms down under the Mage Quarter: outdoors over it the name isn't a floor)
    sp = None
    for cont in (0,):
        for p in ns.Interiors[cont].values():
            w = ns.WMOs[p[1]]
            if w and any(str(g.n) == "The Slaughtered Lamb" for g in w.groups.values()):
                sp = ((p[6] + p[8]) / 2, (p[7] + p[9]) / 2)
                break
    assert sp
    lua.execute('GetMinimapZoneText = function() return "The Slaughtered Lamb" end IsIndoors = function() return false end')
    assert HB.ZoneTextBand(0, *sp) is None  # (outdoors: not even looked at, one nil)
    HB.Reset()
    lua.execute("IsIndoors = function() return true end")
    lo, hi, name = HB.ZoneTextBand(0, *sp)
    assert lo < hi and str(name) == "The Slaughtered Lamb"


# --- (e) the corpse run against the Spirit Healer ---------------------------------------------------------------------

@pytest.fixture
def ghost(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    lua.execute("""AGPS_GH_SAVED = { stops = AGPS_NS.Nav.stops, route = AGPS_NS.Nav.route, dest = AGPS_NS.Nav.dest,
      corpse = AGPS_NS.Nav.corpse, GetResSicknessDuration = rawget(_G, 'GetResSicknessDuration'),
      pos = { AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] } }""")
    yield lua, ns
    lua.execute("""local s = AGPS_GH_SAVED
      AGPS_NS.Nav.stops, AGPS_NS.Nav.route, AGPS_NS.Nav.dest, AGPS_NS.Nav.corpse = s.stops, s.route, s.dest, s.corpse
      GetResSicknessDuration = s.GetResSicknessDuration
      AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = s.pos[1], s.pos[2], s.pos[3] AGPS_LEVEL = nil""")
    N.ResetSpeeds()


def _dead(lua, ns, walk_yd, next_stop=None):
    """The ghost at the Elwynn Spirit Healer, its body `walk_yd` along the route away."""
    _, hx, hy, _ = ELWYNN_HEALER
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {hx + 3}, {hy}, 0")
    stops = f"{{ x = {hx - 900}, y = {hy}, cont = 0, corpse = true, name = 'Your body' }}"
    if next_stop:
        stops += f", {{ x = {next_stop[0]}, y = {next_stop[1]}, cont = 0, name = 'next' }}"
    lua.execute(f"""local N = AGPS_NS.Nav
      N.stops = {{ {stops} }}
      N.dest, N.corpse = N.stops[1], true
      N.route = {{ walkYards = {walk_yd}, length = {walk_yd}, swimYards = 0, pts = {{}}, kinds = {{}} }}""")


def test_the_spirit_healers_cost_by_level_as_the_client_says(ghost):
    lua, ns = ghost
    N = ns.Nav
    lua.execute("GetResSicknessDuration = nil")
    assert str(N.HealerCost(5)) == "no penalty"
    assert str(N.HealerCost(10)) == "10% durability"
    assert str(N.HealerCost(15)) == "sickness 5 min, 25% durability"
    assert str(N.HealerCost(42)) == "sickness 10 min, 25% durability"
    # (the game's own time when it says one; none: no sickness, 10%)
    lua.execute('GetResSicknessDuration = function() return "7 Min" end')
    assert str(N.HealerCost(30)) == "sickness 7 Min, 25% durability"
    lua.execute("GetResSicknessDuration = function() return nil end")
    assert str(N.HealerCost(30)) == "10% durability"
    assert str(N.FormatClock(130)) == "2:10" and str(N.FormatClock(3725)) == "1:02:05"


def test_a_ghost_by_the_spirit_healer_sees_what_it_saves(ghost):
    lua, ns = ghost
    N = ns.Nav
    lua.execute("AGPS_LEVEL = 42 GetResSicknessDuration = nil")
    _dead(lua, ns, 1050)  # (150 s at the ghost's 7 yd/s)
    run, corpse, healer = N.CorpseRunSecs(N.route, ELWYNN_HEALER[1] + 3, ELWYNN_HEALER[2], 0)
    assert round(run) == 150 and round(corpse) == 150 and healer < 2
    note = str(N.CorpseNote())
    assert note == "|cffbfbfbfCorpse 2:30 · Spirit Healer saves 2:30 (sickness 10 min, 25% durability)|r", note


def test_with_a_stop_after_the_body_the_walk_on_counts(ghost):
    lua, ns = ghost
    N = ns.Nav
    lua.execute("AGPS_LEVEL = 42 GetResSicknessDuration = nil")
    # (the next stop just past the body: the Spirit Healer's walk on to it is longer by about what the run saves)
    _, hx, hy, _ = ELWYNN_HEALER
    _dead(lua, ns, 1050, next_stop=(hx - 950, hy))
    run, corpse, healer = N.CorpseRunSecs(N.route, hx + 3, hy, 0)
    assert corpse > run and healer > 100 and corpse - healer < 60
    note = str(N.CorpseNote())
    assert ("saves" in note) == (corpse - healer >= N.HEALER_GAIN)
    # (the next stop back by the Spirit Healer: it saves the run there and back)
    _dead(lua, ns, 1050, next_stop=(hx + 20, hy))
    run, corpse, healer = N.CorpseRunSecs(N.route, hx + 3, hy, 0)
    assert corpse - healer > 250


def test_no_note_alive_or_far_from_any_spirit_healer(ghost):
    lua, ns = ghost
    N = ns.Nav
    _dead(lua, ns, 1050)
    N.corpse = None
    assert N.CorpseNote() is None
    _dead(lua, ns, 20)
    assert "no faster" in str(N.CorpseNote())  # (the body right here: run back)
