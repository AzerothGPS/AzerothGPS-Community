-- The addon's own text in the game's language (GetLocale()). `ns.L` is keyed by the English text: L["Quest Route"].
-- A key a language doesn't have (and every key on an English client, enUS/enGB) reads as the English itself.
-- Each Locales\<locale>.lua fills ns.L only when it is the client's language (ns.NewLocale), so only one is kept.
-- Names the game gives (zones, NPCs, items, spells) come already in the client's language and are never keys here.
-- Formatted text is one whole sentence per key ("%d stops added to the route (%d in all)"); a language that needs
-- its values in another order writes them "%2$s ... %1$s", and that key is formatted with ns.Format.
local _, ns = ...

ns.L = ns.L or setmetatable({}, { __index = function(_, key) return key end })
-- The languages there's text for; a player can pick one of them over the game's (`/agps language`, kept in
-- AzerothGPSDB.language: read here, as the files load, by the toc's LoadSavedVariablesFirst; a /reload applies it).
ns.LOCALES = { enUS = true, deDE = true, esES = true, esMX = true, frFR = true, itIT = true, koKR = true, ptBR = true,
  ruRU = true, zhCN = true, zhTW = true }
local picked = type(AzerothGPSDB) == "table" and AzerothGPSDB.language
ns.loadedLanguage = type(picked) == "string" and picked or "auto" -- (what a /reload would change: Options > General)
ns.LOCALE = (picked and ns.LOCALES[picked] and picked) or (GetLocale and GetLocale()) or "enUS"

-- The table to fill for `locale`, or nil when the client is in another language.
function ns.NewLocale(locale)
  if ns.LOCALE ~= locale then return nil end
  return ns.L
end

-- string.format that also takes positional values ("%2$s ... %1$s"), as some translations need.
function ns.Format(fmt, ...)
  if not fmt:find("%%%d+%$") then return string.format(fmt, ...) end
  local args, ordered, n = { ... }, {}, 0
  local plain = fmt:gsub("%%(%%?)(%d*)(%$?)", function(pct, num, dollar)
    if pct == "%" then return "%%" .. num .. dollar end
    n = n + 1
    ordered[n] = args[dollar == "$" and tonumber(num) or n]
    return dollar == "$" and "%" or ("%" .. num)
  end)
  return string.format(plain, (unpack or table.unpack)(ordered, 1, n))
end

-- Names in the game's language (a German player, 1.3.6: "dann in 20 m nach Menethil Harbor, Wetlands fliegen"). The
-- shipped data's names are the client's English ones; each is looked up in the game by its id, the English only the
-- fallback (a name the game hasn't given). On an English client nothing is looked up: the data's names are the game's.
-- Every name shown goes through these; logic (saved keys, matching) keeps the English. The search finds both.
ns.names = { zone = {}, area = {}, poi = {}, item = {}, instance = {}, taxi = nil, taxiVer = 0, byEnglish = nil }
function ns.GameLocalized()
  local n = ns.names
  if n.localized == nil then
    local ok, loc = pcall(GetLocale or error)
    n.localized = ok and type(loc) == "string" and loc ~= "enUS" and loc ~= "enGB" or false
  end
  return n.localized
end
local function Cached(cache, id, look)
  if not id then return nil end
  local v = cache[id]
  if v == nil then
    local ok, name = pcall(look, id)
    v = ok and type(name) == "string" and name ~= "" and name or false
    cache[id] = v
  end
  return v or nil
end
-- A zone's or city's name (its uiMap, Data/Maps.lua), else `english`.
function ns.ZoneName(mapID, english)
  if not ns.GameLocalized() then return english end
  return Cached(ns.names.zone, mapID, function(id) return C_Map.GetMapInfo(id).name end) or english
end
-- An area's name (its AreaTable id: a town's, a subzone's), else `english`.
function ns.AreaName(areaID, english)
  if not ns.GameLocalized() then return english end
  return Cached(ns.names.area, areaID, function(id) return C_Map.GetAreaInfo(id) end) or english
end
-- A map point of interest's name (its AreaPOI id), else `english`.
function ns.AreaPoiName(poiID, english)
  if not ns.GameLocalized() then return english end
  return Cached(ns.names.poi, poiID, function(id) return C_AreaPoiInfo.GetAreaPOIInfo(nil, id).name end) or english
end
-- The flight masters' names as the game gives them, by node (Taxi.lua saves them from C_TaxiMap: the flight map, and
-- the continents' maps at login). Made again when Taxi saves new ones (`ns.TaxiNamesChanged`).
function ns.TaxiNamesChanged()
  ns.names.taxi = nil
  ns.names.taxiVer = ns.names.taxiVer + 1
end
function ns.TaxiName(node, english)
  if not (node and ns.GameLocalized()) then return english end
  local n = ns.names
  if not n.taxi then
    n.taxi = {}
    local ok, cdb = pcall(ns.CharDB)
    for _, entry in pairs(ok and cdb and cdb.taxiNodes or {}) do
      for _, t in ipairs(type(entry) == "table" and entry.nodes or {}) do
        if t.nodeID and type(t.name) == "string" and t.name ~= "" then n.taxi[t.nodeID] = t.name end
      end
    end
  end
  return n.taxi[node] or english
end
-- A Data/Pois.lua row's name: a flight master's by its node, a map point's by its AreaPOI id, a place label's by its
-- area (their 6th value, since 1.3.8's data).
function ns.PoiName(p)
  if not (p and ns.GameLocalized()) then return p and p[4] end
  if p[1] == 1 then return ns.TaxiName(p[5], p[4]) end
  if p[1] == 2 and p[6] then return ns.AreaPoiName(p[6], p[4]) end
  if p[1] == 3 and p[6] then return ns.AreaName(p[6], p[4]) end
  return p[4]
end
-- A name from the data with no id of its own (the capitals' district labels, ns.CityLabels): by the place label of the
-- same English name (Data/Pois.lua kind 3), else as it is.
function ns.PlaceName(english)
  if not (english and ns.GameLocalized()) then return english end
  local n = ns.names
  if not n.byEnglish then
    n.byEnglish = {}
    for _, list in pairs(ns.Pois or {}) do
      for _, p in ipairs(list) do
        if p[1] == 3 and p[6] and p[4] and not n.byEnglish[p[4]] then n.byEnglish[p[4]] = p[6] end
      end
    end
  end
  local id = n.byEnglish[english]
  return id and ns.AreaName(id, english) or english
end
-- A zone's or city's name from its English one alone (a dungeon's way in names its zone so: Data/Instances.lua's
-- portals), by the uiMap of that name (Data/Maps.lua's zones and cities), else `english`.
function ns.ZoneNameByEnglish(english)
  if not (english and ns.GameLocalized()) then return english end
  local n = ns.names
  if not n.zoneByEnglish then
    n.zoneByEnglish = {}
    for id, m in pairs(ns.Maps or {}) do
      if m.name and (m.type == 3 or m.type == 4) then
        local have = n.zoneByEnglish[m.name]
        if not have or id < have then n.zoneByEnglish[m.name] = id end
      end
    end
  end
  local id = n.zoneByEnglish[english]
  return id and ns.ZoneName(id, english) or english
end
-- A dungeon's or raid's name (Data/Instances.lua's level `lvl`): GetRealZoneText by its map id (Map.db's name, the
-- data's English; WoW Forever's API docs: ZoneScript's GetRealZoneText(mapID)), else the English. With `wing` (its
-- English: "Library"), "Scarlet Monastery: Library", the wing by its dungeon map floor of that name (a uiMap, the
-- Scarlet Monastery's four) else as it is; `door` its door's, "(...)", as it is.
function ns.InstanceName(lvl, wing, door)
  local info = lvl and ns.Instances and ns.Instances[lvl]
  local english = info and info.name or (ns.CityLevels and ns.CityLevels[lvl] and ns.CityLevels[lvl].name)
  local name = english
  if english and ns.GameLocalized() then
    local map = info and info.map or (ns.CityLevels[lvl] and ns.CityLevels[lvl].base)
    name = Cached(ns.names.instance, map, function(id) return GetRealZoneText(id) end) or english
  end
  if not (name and wing) then return name end
  return name .. ": " .. ns.WingName(lvl, wing) .. (door and (" (" .. door .. ")") or "")
end
-- A dungeon's wing's name (Data/Instances.lua's `wings`, English), by the dungeon map floor (Data/DungeonMaps.lua's
-- uiMap) of that name; the others ("Front Entrance", "East": the data's own words, no id in the game) as they are.
function ns.WingName(lvl, wing)
  if not (wing and ns.GameLocalized()) then return wing end
  local dm = ns.DungeonMaps and ns.DungeonMaps[lvl]
  for _, f in ipairs(dm and dm.floors or {}) do
    if f.name == wing and f.ui then return ns.ZoneName(f.ui, wing) end
  end
  return wing
end
-- A transport row's end (`side` 1 or 2: Data/Transports.lua's name1 / name2): its town by area (`area1`) and its zone
-- by uiMap (`map1`), "Town, Zone" as the English is; a flight's (Nav's rows) are the game's names already.
function ns.RideEndName(t, side)
  local english = t and t[side == 1 and 9 or 10]
  if not (english and ns.GameLocalized()) or t.from then return english end
  if t[8] == "portal" then -- (a dungeon's way in, Data/Instances.lua: the dungeon's end by its map, the zone's by name)
    local lvl = side == 1 and t[1] or t[4]
    local info = ns.Instances and ns.Instances[lvl]
    if info then
      local base = info.name or ""
      local wing = english:sub(1, #base + 2) == base .. ": " and english:sub(#base + 3) or nil
      return ns.InstanceName(lvl, wing)
    end
    return ns.ZoneNameByEnglish(english)
  end
  local area, map = t["area" .. side], t["map" .. side]
  if not (area or map) then return english end
  local town = area and ns.AreaName(area)
  local zone = map and ns.ZoneName(map)
  if area and not town or map and not zone then return english end -- (half in each language: the English)
  if town and zone and town ~= zone then return town .. ", " .. zone end
  return town or zone
end
-- An item's name (GetItemInfo: once the game has it cached; else asked for, and the English meanwhile).
function ns.ItemName(id, english)
  if not (id and ns.GameLocalized()) then return english end
  local cache = ns.names.item
  local v = cache[id]
  if v then return v end
  local ok, name = pcall(function()
    if C_Item and C_Item.GetItemNameByID then return C_Item.GetItemNameByID(id) end
    return (GetItemInfo(id))
  end)
  if ok and type(name) == "string" and name ~= "" then
    cache[id] = name
    return name
  end
  return english
end
-- The shipped NPCs' names and titles in the client's language (Data/NpcNames/<locale>.lua, AzerothCore's; asked
-- 2026-11-17, "All players should be able to search for NPCs they haven't met yet"): only the client's own file sets
-- ns.NpcNamesLoc. Read at the first ask: { [id] = name }, { [id] = title }, only those that differ from the English.
function ns.ShippedNpcNames()
  local n = ns.names
  if n.shippedNpcs then return n.shippedNpcs, n.shippedTitles end
  local names, titles = {}, {}
  local packed, list = ns.NpcNamesLoc, ns.NpcTitlesLoc or {}
  local ok, loc = pcall(GetLocale)
  if type(packed) == "string" and ok and loc == ns.NpcNamesLocale then
    for line in packed:gmatch("[^\n]+") do
      local id, name, t = line:match("^(%d+)|([^|]*)|(%d*)$")
      id = tonumber(id)
      if id and name ~= "" then names[id] = name end
      if id and t ~= "" then titles[id] = list[tonumber(t)] end
    end
  end
  n.shippedNpcs, n.shippedTitles = names, titles
  return names, titles
end
-- An NPC's name (its creature id): as the game showed it (UnitName by the creature id in its GUID: targeted, under the
-- mouse, a window opened; per client language, account-wide, ns.db.npcNames[locale][id]), else the shipped one in the
-- client's language (ns.ShippedNpcNames), else the English.
function ns.NpcName(id, english)
  if not (id and ns.GameLocalized()) then return english end
  id = tonumber(id)
  local ok, loc = pcall(GetLocale)
  local learned = ok and ns.db and ns.db.npcNames and ns.db.npcNames[loc]
  return learned and learned[id] or ns.ShippedNpcNames()[id] or english
end
-- An NPC's title ("Weaponsmith") in the client's language, shipped (ns.ShippedNpcNames), else the English.
function ns.NpcTitle(id, english)
  if not (id and english and ns.GameLocalized()) then return english end
  local _, titles = ns.ShippedNpcNames()
  return titles[tonumber(id)] or english
end
function ns.CreatureId(guid)
  if type(guid) ~= "string" or (ns.IsSecret and ns.IsSecret(guid)) then return nil end
  local kind, id = guid:match("^(%a+)%-%d+%-%d+%-%d+%-%d+%-(%d+)%-")
  if kind == "Creature" or kind == "Vehicle" then return tonumber(id) end
end
ns.NPC_NAME_MAX = 100 -- (bytes: a name longer than this isn't kept)
function ns.LearnNpcName(unit)
  if not (ns.db and ns.GameLocalized()) then return end
  local ok, guid, name, loc = pcall(function() return UnitGUID(unit), UnitName(unit), GetLocale() end)
  if not ok or not name or (ns.IsSecret and ns.IsSecret(name)) or type(name) ~= "string" then return end
  local id = ns.CreatureId(guid)
  if not id or name == "" or #name > ns.NPC_NAME_MAX or name:find("|", 1, true) then return end
  ns.db.npcNames = ns.db.npcNames or {}
  local names = ns.db.npcNames[loc] or {}
  ns.db.npcNames[loc] = names
  if names[id] ~= name then
    names[id] = name
    ns.npcNamesVer = (ns.npcNamesVer or 0) + 1
  end
end
