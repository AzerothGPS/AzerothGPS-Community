"""Travel extras (item 109, SPF parity, Kooki3z 2026-11-26: "match or have the advantage over SPF in all aspects").

Checked against WoW Forever's own client data (the file headers in Teleports.lua and Nav.lua's Frequent Flier):
- WoW Forever's second "Hearthstone" item, 284163 (spell 1315212, home, the same 1 h cooldown category as 6948's).
- The bind point learned where the player stands when they bind (HEARTHSTONE_BOUND), not only after a hearth.
- A party mage's portals (option usePartyPortals, off): by the mage's level against the client's SpellLevels, the
  player's faction's cities, only from where the player stands and with the mage near.
- Frequent Flier (spell 1225490, aura 388: the taxi +20%): flight estimates 1.2 times as fast, recorded times scaled.
- Water walking can be turned off (option useWaterWalking, on).
- The teleports' landings are the server's (Moonglade's had been 180 yd off)."""

import pytest

from test_addon_lua import env, load, nav_env  # noqa: F401 (fixtures)

pytest.importorskip("lupa")

DUROTAR = (300.0, -4700.0)  # (Kalimdor, far from Orgrimmar's middle)


def _teleports(lua, ns, **gps):
    load(lua, ns, "Data/Pois.lua", "Teleports.lua")
    lua.execute("""
      AGPS_ITEMS = {}
      GetItemCount = function(id) return AGPS_ITEMS[id] or 0 end
      GetItemCooldown = function() return 0, 0, 1 end
      GetBindLocation = function() return "Brill" end
      IsPlayerSpell = function() return false end
      UnitFactionGroup = function() return "Horde" end
      UnitPosition = function(unit)
        if unit == "player" then return AGPS_PX, AGPS_PY, 0, 1 end
        local m = AGPS_MATES and AGPS_MATES[unit]
        if m then return m.x, m.y, 0, m.cont or 1 end
      end
      AGPS_PX, AGPS_PY = 300.0, -4700.0
    """)
    settings = {"useHearthstone": True, "useTeleports": True}
    settings.update(gps)
    body = ", ".join(f"{k} = {'true' if v else 'false'}" for k, v in settings.items())
    ns.settings = lua.eval(f"{{ gps = {{ {body} }} }}")
    ns.Teleports.Changed()
    return ns.Teleports


def _names(rows):
    return [rows[i][8] for i in range(1, len(rows) + 1)]


def test_forevers_own_hearthstone_counts_as_the_hearthstone(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns)
    lua.execute("AGPS_ITEMS = { [284163] = 1 }")
    T.Changed()
    rows = T.Available(1, *DUROTAR)
    assert _names(rows) == ["your Hearthstone"] and rows[1].item == 284163 and rows[1][10] == "Brill"
    # (both in the bags: the first ready one; the classic one first)
    lua.execute("AGPS_ITEMS = { [284163] = 1, [6948] = 1 }")
    T.Changed()
    rows = T.Available(1, *DUROTAR)
    assert _names(rows) == ["your Hearthstone"] and rows[1].item == 6948
    # (a hearth with the new one is recorded as one: its spell is a home spell)
    assert T.HOME_SPELLS[1315212] and T.HOME_SPELLS[8690] and T.HOME_SPELLS[556]


def test_the_bind_point_is_where_the_player_stands_when_they_bind(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns)
    cdb = ns.CharDB()
    # (bound in Brill's inn, standing by the innkeeper: the subzone isn't the bind's name, LearnHome took nothing)
    lua.execute("AGPS_PX, AGPS_PY = 2269.0, 244.0 UnitPosition = function() return AGPS_PX, AGPS_PY, 0, 0 end "
                "GetSubZoneText = function() return 'Gallows\\' End Tavern' end")
    T.LearnHome()
    assert cdb.bind is None
    T.LearnBind()
    assert cdb.bind.name == "Brill" and cdb.bind.cont == 0 and abs(cdb.bind.x - 2269.0) < 0.1
    home = T.Home()
    assert abs(home.x - 2269.0) < 0.1 and abs(home.y - 244.0) < 0.1


def _party(lua, mates, raid=False):
    """mates: { unit: (class, level, x, y) }"""
    rows = ", ".join(f'["{u}"] = {{ class = "{c}", level = {lv}, x = {x}, y = {y}, name = "{u.title()}Mage" }}'
                     for u, (c, lv, x, y) in mates.items())
    lua.execute(f"""
      AGPS_MATES = {{ {rows} }}
      IsInGroup = function() return true end
      IsInRaid = function() return {'true' if raid else 'false'} end
      GetNumGroupMembers = function() local n = 0 for _ in pairs(AGPS_MATES) do n = n + 1 end return n + 1 end
      UnitExists = function(u) return AGPS_MATES[u] ~= nil end
      UnitIsUnit = function(a, b) return a == b end
      UnitIsConnected = function() return true end
      UnitClass = function(u) local m = AGPS_MATES[u] if m then return m.class, m.class end return "Warrior", "WARRIOR" end
      UnitLevel = function(u) local m = AGPS_MATES[u] return m and m.level or 30 end
      UnitName = function(u) local m = AGPS_MATES[u] return m and m.name or "Tester" end
    """)


def test_a_party_mage_near_the_player_opens_portals_to_the_cities_their_level_allows(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns, usePartyPortals=True)
    _party(lua, {"party1": ("MAGE", 45, DUROTAR[0] + 10, DUROTAR[1])})
    rows = T.Available(1, *DUROTAR)
    dests = sorted(rows[i][10] for i in range(1, len(rows) + 1))
    assert dests == ["Orgrimmar", "Undercity"]  # (Thunder Bluff's at 50; the Alliance's cities never)
    r = rows[1]
    assert r.ask == "Party1Mage" and r.use and not r.item and not r.spell and r[7] == T.PARTY_SECONDS
    # (level 50: Thunder Bluff too)
    lua.execute("AGPS_MATES.party1.level = 50")
    assert len(T.Available(1, *DUROTAR)) == 3
    # (from a stop further on: none; the mage far off: none; not a mage: none)
    assert len(T.Available(1, DUROTAR[0] + 500, DUROTAR[1])) == 0
    lua.execute("AGPS_MATES.party1.x = AGPS_PX + 200")
    assert len(T.Available(1, *DUROTAR)) == 0
    lua.execute("AGPS_MATES.party1.x = AGPS_PX + 5; AGPS_MATES.party1.class = 'PRIEST'")
    assert len(T.Available(1, *DUROTAR)) == 0
    # (off by default: the option off, nothing)
    lua.execute("AGPS_MATES.party1.class = 'MAGE'")
    ns.settings.gps.usePartyPortals = False
    assert len(T.Available(1, *DUROTAR)) == 0


def test_the_route_asks_the_party_mage_for_a_portal_when_its_faster(nav_env):  # noqa: F811
    lua, ns = nav_env
    load(lua, ns, "Turns.lua")
    T = _teleports(lua, ns, usePartyPortals=True)
    _party(lua, {"party1": ("MAGE", 60, DUROTAR[0] + 10, DUROTAR[1])})
    # (Durotar to Undercity: the portal, not the walk and the zeppelin)
    stop = lua.eval("{ x = 1600.0, y = 240.0, cont = 0 }")
    legs, _ = ns.Nav.Plan(1, DUROTAR[0], DUROTAR[1], 7.0, stop, T.Available(1, *DUROTAR))
    first = legs[1].ride
    assert first and first.ask == "Party1Mage" and first[10] == "Undercity"
    ns.Nav.SetDestination(1600.0, 240.0, 0, "Undercity")
    ns.Nav.Route(DUROTAR[0], DUROTAR[1], 1)
    assert "Ask Party1Mage for a portal (to Undercity)" in str(ns.Nav.StepsText(5))


def test_frequent_flier_makes_flights_faster_and_scales_recorded_times(nav_env):  # noqa: F811
    lua, ns = nav_env
    N = ns.Nav
    lua.execute("AGPS_FF = false IsPlayerSpell = function(id) return id == 1225490 and AGPS_FF end")
    N.ForgetFlightSpeed()
    assert N.FlightSpeedFactor() == 1
    lua.execute("AGPS_FF = true")
    N.ForgetFlightSpeed()
    assert N.FlightSpeedFactor() == pytest.approx(1.2)
    # (a time recorded without the perk is flown faster now; one recorded with it as it is; an old one, no speed, as is)
    assert N.RecordedFlightSecs(lua.eval("{ seconds = 120, speed = 1 }")) == pytest.approx(100)
    assert N.RecordedFlightSecs(lua.eval("{ seconds = 120, speed = 1.2 }")) == pytest.approx(120)
    assert N.RecordedFlightSecs(lua.eval("{ seconds = 120 }")) == pytest.approx(120)
    lua.execute("AGPS_FF = false")
    N.ForgetFlightSpeed()
    assert N.RecordedFlightSecs(lua.eval("{ seconds = 100, speed = 1.2 }")) == pytest.approx(120)


def test_water_walking_can_be_turned_off(nav_env):  # noqa: F811
    lua, ns = nav_env
    N = ns.Nav
    lua.execute("IsPlayerSpell = function(id) return id == 1066 end")  # (Aquatic Form: no reagent)
    ns.settings = lua.eval("{ gps = {} }")
    N.ForgetWaterFast()
    assert N.WaterFast() is not None
    ns.settings.gps.useWaterWalking = False
    N.ForgetWaterFast()
    assert N.WaterFast() is None


def test_the_teleports_land_where_the_server_puts_you(nav_env):  # noqa: F811
    # (the server's spell_target_position, the CMaNGOS dump: Moonglade's was 180 yd off, Darnassus's the portal's)
    lua, ns = nav_env
    T = _teleports(lua, ns)
    spots = {T.SPELLS[i][1]: (T.SPELLS[i][3], T.SPELLS[i][4]) for i in range(1, len(T.SPELLS) + 1)}
    assert spots[18960] == pytest.approx((7991.9, -2679.8), abs=0.2)
    assert spots[3565] == pytest.approx((9664.1, 2526.4), abs=0.2)
    items = {T.ITEMS[i][1]: (T.ITEMS[i][3], T.ITEMS[i][4]) for i in range(1, len(T.ITEMS) + 1)}
    assert items[18984] == pytest.approx((6755.3, -4658.1), abs=0.2)
    assert items[18986] == pytest.approx((-7109.1, -3825.2), abs=0.2)


def test_forevers_everlook_trinket_only_worn_and_usable(nav_env):  # noqa: F811
    lua, ns = nav_env
    T = _teleports(lua, ns)
    lua.execute("""
      AGPS_ITEMS = { [260820] = 1 }
      AGPS_WORN, AGPS_USABLE = false, true
      IsEquippedItem = function(id) return AGPS_WORN end
      IsUsableItem = function(id) return AGPS_USABLE end
    """)
    T.Changed()
    assert len(T.Available(1, *DUROTAR)) == 0
    lua.execute("AGPS_WORN = true")
    T.Changed()
    rows = T.Available(1, *DUROTAR)
    assert len(rows) == 1 and rows[1].item == 260820 and rows[1][10] == "Everlook"
    lua.execute("AGPS_USABLE = false")
    T.Changed()
    assert len(T.Available(1, *DUROTAR)) == 0
