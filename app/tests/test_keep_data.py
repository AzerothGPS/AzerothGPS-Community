"""Keep data forever (asked 2026-10-06, the user's standing rule: "all data should be kept forever by default"): nothing
the player builds up is capped or pruned by itself. A saved file of the old format loads and loses nothing, the
points go into the saved file packed (one string a road or a trace: WoW's Lua loads a file of at most 262,143
distinct values), and back; NPCs keep every place they were met; the file's fullness is said, never acted on but by
refusing an import past a safe share. Run with the whole addon (gameharness)."""

import re

import pytest

from azerothgps.paths import ADDON_DIR

# (WoW's own way of writing a saved variable, near enough: every key in brackets, numbers in full)
SERIALIZE = r"""
AGPS_SERIALIZE = function(name, v)
  local function key(k)
    if type(k) == "number" then return "[" .. string.format("%.17g", k) .. "]" end
    return "[" .. string.format("%q", k) .. "]"
  end
  local function val(x, indent)
    local t = type(x)
    if t == "number" then return string.format("%.17g", x)
    elseif t == "string" then return string.format("%q", x)
    elseif t == "boolean" then return tostring(x)
    elseif t == "table" then
      local parts = {}
      for k, y in pairs(x) do
        local ty = type(y)
        if ty ~= "function" and ty ~= "userdata" and ty ~= "thread" then
          parts[#parts + 1] = indent .. "\t" .. key(k) .. " = " .. val(y, indent .. "\t") .. ","
        end
      end
      table.sort(parts)
      return "{\n" .. table.concat(parts, "\n") .. "\n" .. indent .. "}"
    end
    return "nil"
  end
  return name .. " = " .. val(v, "") .. "\n"
end
"""


def _shipped_time() -> int:
    """A drawn road's time the road data has (Data/Roads.lua's ns.RoadTracksIn)."""
    text = (ADDON_DIR / "Data" / "Roads.lua").read_text(encoding="utf-8")
    block = text[text.find("ns.RoadTracksIn"):]
    return int(re.search(r"\[(\d+)\]\s*=\s*true", block).group(1))


def _old_file(shipped: int) -> str:
    """A saved file as 1.1.5 wrote it: points as lists, more than 100 faster trips, an NPC marked common, years-old
    inbox acknowledgments, a pin removal, a stand-in character from before its name was known."""
    trips = ",\n".join(
        f'{{ ["continent"] = 0, ["time"] = {1700000000 + i}, ["estimate"] = 90, ["actual"] = 60, '
        f'["pts"] = {{ {-9000 - i}, 600, {-9010 - i}, 610, {-9020 - i}, 625 }} }}' for i in range(120))
    acks = ",\n".join(f'[{made}] = {{ ["at"] = {1000 + made}, ["had"] = 0, ["rejected"] = 0 }}' for made in range(1, 151))
    return f"""AzerothGPSDB = {{
  ["version"] = 2,
  ["settings"] = {{ ["gps"] = {{ }} }},
  ["tracks"] = {{
    {{ ["op"] = "add", ["drawn"] = true, ["continent"] = 0, ["zone"] = "Tirisfal Glades", ["time"] = {shipped},
      ["pts"] = {{ 2200.5, 300, 2210, 300.1, 2220, 305 }} }},
    {{ ["op"] = "add", ["drawn"] = true, ["continent"] = 0, ["zone"] = "Elwynn Forest", ["time"] = 1,
      ["pts"] = {{ -9400, 60, -9410, 62.5, -9420, 70 }}, ["zs"] = {{ 58.4, 58.4, 58.5 }}, ["z"] = 58.4 }},
  }},
  ["feedback"] = {{ ["roads"] = {{ }}, ["trips"] = {{ {trips} }} }},
  ["npcs"] = {{
    [1234] = {{ ["name"] = "Stormwind Guard", ["cont"] = 0, ["x"] = -8900, ["y"] = 600, ["common"] = true }},
    [5678] = {{ ["name"] = "Innkeeper Renee", ["title"] = "Innkeeper", ["place"] = "Brill", ["cont"] = 0,
      ["x"] = 2254, ["y"] = 293 }},
  }},
  ["importInbox"] = {{ {acks} }},
  ["pinsRemoved"] = {{ [1790000000] = "shared" }},
  ["pins"] = {{ {{ ["level"] = 0, ["x"] = 1, ["y"] = 2, ["name"] = "Mine", ["time"] = 1790000001, ["icon"] = 134400 }} }},
  ["chars"] = {{ ["Somerealm-Unknown"] = {{ ["flights"] = {{ ["a:b"] = 99 }} }} }},
}}
"""


def _start(saved):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start(saved=saved)
    lua.execute(SERIALIZE)
    return lua, ns


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else None


def test_an_old_saved_file_loads_and_loses_nothing(tmp_path):
    # (asked 2026-10-06: a migration from the current formats, with a test that loads an old file and loses nothing)
    shipped = _shipped_time()
    lua, ns = _start(_old_file(shipped))
    db = ns.db
    # the drawn road the data has: archived (packed), not deleted; the other as it was
    (arch,) = _list(db.tracksShipped)
    assert arch.time == shipped and arch.pk == "2200.5 300 2210 300.1 2220 305" and arch.pts is None
    (t,) = _list(db.tracks)
    assert t.time == 1 and _list(t.pts) == [-9400, 60, -9410, 62.5, -9420, 70] and _list(t.zs) == [58.4, 58.4, 58.5]
    # every faster trip (120, past the old cap of 100), every inbox acknowledgment, the pin and its removal, both NPCs
    assert len(db.feedback.trips) == 120
    ns.Import.CheckInbox()
    assert len(list(db.importInbox.keys())) == 150
    assert db.pinsRemoved[1790000000] == "shared" and len(db.pins) == 1
    assert db.npcs[1234].common and db.npcs[5678].name == "Innkeeper Renee"
    # the stand-in from before a name was known: kept, unclaimed
    (u,) = _list(db.unclaimed)
    assert u.key == "Somerealm-Unknown" and u.data.flights["a:b"] == 99
    # a /reload: the points saved packed, one string a road and a trip
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.eval("AGPS_SERIALIZE")("AzerothGPSDB", lua.globals().AzerothGPSDB)
    assert '["pk"] = "-9400 60 -9410 62.5 -9420 70"' in text and '["zk"] = "58.4 58.4 58.5"' in text
    assert '["pts"]' not in text
    # loaded again: all of it back, as lists
    lua2, ns2 = _start(text)
    db2 = ns2.db
    (t2,) = _list(db2.tracks)
    assert _list(t2.pts) == [-9400, 60, -9410, 62.5, -9420, 70] and _list(t2.zs) == [58.4, 58.4, 58.5]
    trips = _list(db2.feedback.trips)
    assert len(trips) == 120 and _list(trips[119].pts) == [-9119, 600, -9129, 610, -9139, 625]
    assert db2.tracksShipped[1].pk == arch.pk and len(db2.tracksShipped) == 1  # (archived once, not again)
    assert len(list(db2.importInbox.keys())) == 150 and db2.unclaimed[1].data.flights["a:b"] == 99
    # and the road watcher reads the packed file
    from azerothgps.roads.tracks import read_tracks

    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text(text, encoding="utf-8")
    (r,) = [r for r in read_tracks(tmp_path / "WTF") if r["time"] == 1]
    assert r["coords"] == [[-9400, 60], [-9410, 62.5], [-9420, 70]] and r["zs"] == [58.4, 58.4, 58.5]


def test_npcs_keep_every_place_met_and_common_ones_are_searched_with_the_option():
    # (asked 2026-10-06) met in another place far apart: that place kept too (it was thrown away), the NPC one of many,
    # left out of the search unless the option's on, then found at the place nearest the player
    lua, ns = _start(None)
    L, st = ns.Layers, ns.settings.gps
    lua.execute("AGPS_POS = { 2254.0, 293.0, 0 }")
    assert L.NoteNpc(77, "Wandering Vendor", "Supplies", 0, 2250.0, 290.0, "Brill")
    assert not L.NoteNpc(77, "Wandering Vendor", "Supplies", 0, 2270.0, 300.0, "Brill")  # (the same place)
    assert not ns.db.npcs[77].common
    assert not L.NoteNpc(77, "Wandering Vendor", "Supplies", 0, -9460.0, 30.0, "Goldshire")
    n = ns.db.npcs[77]
    assert n.common and len(n.spots) == 1 and n.spots[1].place == "Goldshire" and n.x == 2250.0  # (both kept)
    names = lambda: [str(k.name) for k in _list(L.KnownNpcs())]
    assert "Wandering Vendor" not in names()
    st.searchCommonNpcs = True
    try:
        (v,) = [k for k in _list(L.KnownNpcs()) if k.name == "Wandering Vendor"]
        assert (v.x, v.y, v.place) == (2250.0, 290.0, "Brill")  # (the place nearest the player)
        lua.execute("AGPS_POS = { -9450.0, 40.0, 0 }")
        # (the nearest of the spots on the player's side: Goldshire's is the Alliance's, 2026-10-07's faction rule)
        cdb, faction = ns.CharDB(), ns.CharDB().faction
        cdb.faction = "Alliance"
        (v,) = [k for k in _list(L.KnownNpcs()) if k.name == "Wandering Vendor"]
        assert v.place == "Goldshire"
        cdb.faction = "Horde"
        (v,) = [k for k in _list(L.KnownNpcs()) if k.name == "Wandering Vendor"]
        assert v.place == "Brill"  # (a Horde player in Goldshire: Brill's, not the Alliance town's)
        cdb.faction = faction
    finally:
        st.searchCommonNpcs = False
        lua.execute("AGPS_POS = { 2254.0, 293.0, 0 }")


def test_trips_past_a_hundred_are_kept():
    lua, ns = _start(None)
    F = ns.Feedback
    trips = lua.table_from([lua.table_from({"continent": 0, "time": 1800000000 + i, "estimate": 90, "actual": 60,
                                            "pts": lua.table_from([0, i, 10, i, 20, i])}) for i in range(150)])
    F.AddShared(trips, None)
    assert len(ns.db.feedback.trips) == 150


def test_the_saved_files_fullness_is_said_and_an_import_past_its_budget_refused():
    lua, ns = _start(None)
    I = ns.Import
    n = ns.SavedValues(lua.globals().AzerothGPSDB)
    assert 0 < n < ns.SAVED_LIMIT * 0.25
    # (packed when saved: a road's points count as one value)
    ns.db.tracks = lua.eval("{ { op = 'add', continent = 0, time = 5, pts = { 1.5, 2.5, 3.5, 4.5, 5.5, 6.5 } } }")
    assert ns.SavedValues(lua.globals().AzerothGPSDB) - n <= 6
    lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    limit, share = ns.SAVED_LIMIT, ns.SAVED_IMPORT_SHARE
    try:
        assert ns.SavedNotice() < 0.25 and len(lua.eval("AGPS_PRINTS")) == 0  # (nothing to say)
        ns.SAVED_LIMIT = 100  # (a file near its limit)
        assert ns.SavedNotice() > 1 and "Nothing is ever deleted" in str(lua.eval("AGPS_PRINTS")[1])
        ns.SAVED_LIMIT = n + 30
        ns.SAVED_IMPORT_SHARE = 1.0
        res = I.ImportText("H 0 100.0,200.0 name=Peacebloom\n" * 12, "none", False)  # (~36 values: past it)
        assert res.refused and res.added.herbs == 0 and "Nothing was added or deleted" in str(I.ImportSummary(res))
        res = I.ImportText("H 0 100.0,200.0 name=Peacebloom\n", "none", False)  # (a few: in)
        assert not res.refused and res.added.herbs == 1
    finally:
        ns.SAVED_LIMIT, ns.SAVED_IMPORT_SHARE = limit, share
        ns.db.tracks = lua.eval("{}")


def test_herbs_ore_and_guard_places_count_as_unsaved():
    # (Save Now: a crash lost them; marked as pins are)
    lua, ns = _start(None)
    L = ns.Layers
    ns.ResetUnsaved()
    L.AddCityPoi(0, 2260.0, 280.0, "Brill Inn", 0)
    assert ns.unsaved == 1
    L.AddCityPoi(0, 2260.0, 280.0, "Brill Inn", 0)  # (the same, unchanged: nothing new)
    assert ns.unsaved == 1
    lua.execute("AGPS_NS.Layers.NoteWorldObject('Peacebloom', 100)")
    lua.execute("GetSpellInfo = GetSpellInfo or function() return nil end")
    L.OnGatherError("Requires Herbalism", 101, 2250.0, 290.0, 0)
    assert ns.unsaved == 2
    ns.ResetUnsaved()


def test_early_name_data_merges_entry_by_entry():
    # (a flight time learned before the character's name was known: kept, not dropped for the one table it had)
    lua, ns = _start(None)
    own = lua.eval("{ flights = { ['x:y'] = 10 }, faction = 'Horde' }")
    tmp = lua.eval("{ flights = { ['a:b'] = 99, ['x:y'] = 1 }, taxiNodes = { 5 } }")
    ns.MergeInto(own, tmp)
    assert own.flights["a:b"] == 99 and own.flights["x:y"] == 10 and own.taxiNodes[1] == 5 and own.faction == "Horde"
