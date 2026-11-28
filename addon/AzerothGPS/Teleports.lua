-- Teleports the route may start with (options "Use hearthstone", "Use class teleports and
-- teleport items"): the Hearthstone, Astral Recall, the mage's own teleports, Teleport:
-- Moonglade and the engineers' teleporters, when the character has them ready right now. The
-- directions say "Use your Hearthstone", with a button beside them that uses it (the player's
-- click: GPSFrame's use button); the addon never casts or uses anything by itself.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Geo = ns.Geo

local T = {}
ns.Teleports = T

T.CAST_SECONDS = 25 -- casting (10 s) plus the loading screen, roughly
local HEARTHSTONE_ITEM, RUNE_OF_TELEPORTATION = 6948, 17031
local HEARTHSTONE_SPELL, ASTRAL_RECALL = 8690, 556
-- The hearthstones, from this client's own data (item 109, read 2026-11-26: ItemEffect/ItemXItemEffect, SpellEffect,
-- SpellCooldowns, SpellCategories): 6948 (spell 8690) and WoW Forever's own "Hearthstone" 284163 (spell 1315212), both a
-- teleport to the bind point (SpellEffect 252, target 9 "home"), a 10 s cast, a 1 h cooldown in the same category (89):
-- one hearth spends both. The first in the bags is the one used.
T.HEARTHSTONE_ITEMS = { HEARTHSTONE_ITEM, 284163 }
T.HOME_SPELLS = { [HEARTHSTONE_SPELL] = true, [1315212] = true, [ASTRAL_RECALL] = true }

-- Where each teleport lands (world yards): { spell, cont, x, y, name, needsRune }. The landing is the server's
-- spell_target_position for the spell (the CMaNGOS dump; item 109 put Darnassus's and Moonglade's there: Moonglade's had
-- been 180 yd off). Reagents (Rune of Teleportation, 17031; Moonglade none) from the client's SpellReagents.
T.SPELLS = {
  { 3567, 1, 1469.9, -4221.5, "Orgrimmar", true }, -- Teleport: Orgrimmar
  { 3563, 0, 1773.5, 61.1, "Undercity", true }, -- Teleport: Undercity
  { 3566, 1, -965.0, 283.4, "Thunder Bluff", true }, -- Teleport: Thunder Bluff
  { 3561, 0, -9003.5, 870.0, "Stormwind", true }, -- Teleport: Stormwind
  { 3562, 0, -4613.6, -915.4, "Ironforge", true }, -- Teleport: Ironforge
  { 3565, 1, 9664.1, 2526.4, "Darnassus", true }, -- Teleport: Darnassus
  { 18960, 1, 7991.9, -2679.8, "Moonglade", false }, -- Teleport: Moonglade (druid)
}

-- Teleport items: { item, cont, x, y, name, the engineering specialization it needs (spell), item name, worn = }.
-- Landings: the server's spell_target_position for Everlook Transporter (23442) and Gadgetzan Transporter (23441, the
-- Gnomish Transporter's success). 260820 (item 109): WoW Forever's own item with the Everlook Transporter's spell (the
-- client's ItemEffect, 3 charges, the same 4 h cooldown category 68003), a trinket: used worn, and only when the game
-- says it's usable (IsUsableItem: its skill and charges), since its own requirements aren't in the client's readable data.
T.ITEMS = {
  { 18984, 1, 6755.3, -4658.1, "Everlook", 20222, "Dimensional Ripper - Everlook" }, -- Goblin Engineer
  { 18986, 1, -7109.1, -3825.2, "Gadgetzan", 20219, "Ultrasafe Transporter: Gadgetzan" }, -- Gnomish Engineer
  { 260820, 1, 6755.3, -4658.1, "Everlook", nil, "Everlook Transporter", worn = true },
}
T.HEARTHSTONE_ITEM, T.ASTRAL_RECALL = HEARTHSTONE_ITEM, ASTRAL_RECALL

-- A party mage's portals (item 109, option `usePartyPortals`, Options > Routing, off: the route then asks another player
-- for something). The client says nothing of another player's spells, so what a mage in the group can open is told by
-- their level against the client's SpellLevels (read 2026-11-26): Portal: Stormwind 10059, Ironforge 11416, Orgrimmar
-- 11417 and Undercity 11418 at 40, Darnassus 11419 and Thunder Bluff 11420 at 50, each a Rune of Portals (17032,
-- SpellReagents), the player's own faction's cities only. Only from where the player stands, with the mage within
-- PARTY_MAGE_YD (UnitPosition gives party members' positions here): a stop further on can't count on the mage being
-- there. Landings: the server's portal effects (17334, 17607-17611). No use button: the portal is the mage's to cast,
-- the player clicks it themselves. { spell, cont, x, y, name, level, side }
T.PARTY_PORTALS = {
  { 10059, 0, -9003.5, 870.0, "Stormwind", 40, "Alliance" },
  { 11416, 0, -4613.6, -915.4, "Ironforge", 40, "Alliance" },
  { 11419, 1, 9660.8, 2513.6, "Darnassus", 50, "Alliance" },
  { 11417, 1, 1469.9, -4221.5, "Orgrimmar", 40, "Horde" },
  { 11418, 0, 1773.5, 61.1, "Undercity", 40, "Horde" },
  { 11420, 1, -965.0, 283.4, "Thunder Bluff", 50, "Horde" },
}
T.PARTY_MAGE_YD = 60 -- the mage this near: they can open a portal here
T.PARTY_HERE_YD = 30 -- a route starting this near the player (not from a later stop)
T.PARTY_SECONDS = 45 -- asking, the mage's 10 s cast, stepping in and the loading screen

local function S() return ns.settings and ns.settings.gps end

-- Seconds left on a cooldown (0: ready; the global cooldown's 1.5 s counts as ready).
-- The game keeps some cooldowns secret from addons at times (a "secret number value": comparing one is an error,
-- which stopped the map's redraw, in the saved errors 2026-11-06). Then the cooldown last read for that item or spell
-- (`key`) stands; none read yet: ready.
local seen = {}
local function Secret(v) return ns.IsSecret ~= nil and ns.IsSecret(v) end
local function Left(key, start, duration)
  if Secret(start) or Secret(duration) then
    local s = seen[key]
    if not s then return 0 end
    start, duration = s[1], s[2]
  else
    start = start or 0
    seen[key] = { start, duration }
  end
  if start == 0 or (duration or 0) <= 1.5 then return 0 end
  return math.max(0, start + duration - GetTime())
end

-- Items: C_Item in newer clients, the old globals in older ones.
local function ItemCount(item)
  local get = (C_Item and C_Item.GetItemCount) or GetItemCount
  if not get then return 0 end
  local ok, n = pcall(get, item)
  return ok and n or 0
end

local function ItemLeft(item)
  local get = (C_Container and C_Container.GetItemCooldown) or (C_Item and C_Item.GetItemCooldown) or GetItemCooldown
  if not get then return 0 end
  local ok, start, duration = pcall(get, item)
  if not ok then return 0 end
  if not Secret(start) and type(start) == "table" then return Left("i" .. item, start.startTime, start.duration) end
  return Left("i" .. item, start, duration)
end

local function ItemReady(item)
  if ItemCount(item) == 0 then return false end
  return ItemLeft(item) <= 0
end

local function SpellKnown(spell)
  if IsPlayerSpell then return IsPlayerSpell(spell) end
  return IsSpellKnown and IsSpellKnown(spell) or false
end

local function Worn(item)
  local f = (C_Item and C_Item.IsEquippedItem) or IsEquippedItem
  if not f then return false end
  local ok, v = pcall(f, item)
  return ok and v == true
end

-- Whether the game lets the player use an item now (its skill, its charges); true when the client can't say.
local function Usable(item)
  local f = (C_Item and C_Item.IsUsableItem) or IsUsableItem
  if not f then return true end
  local ok, v = pcall(f, item)
  if not ok or (ns.IsSecret and ns.IsSecret(v)) then return true end
  return v and true or false
end

-- The hearthstone in the bags: the first ready one, else the first had (on its cooldown); nil with none.
local function Hearthstone()
  local had
  for _, item in ipairs(T.HEARTHSTONE_ITEMS) do
    if ItemCount(item) > 0 then
      if ItemLeft(item) <= 0 then return item, true end
      had = had or item
    end
  end
  return had, false
end
T.Hearthstone = Hearthstone

-- Another mage in the group, near the player (T.PARTY_MAGE_YD): their name and level, else nil.
function T.PartyMage()
  local inGroup = IsInGroup and IsInGroup()
  if not inGroup then return nil end
  local raid = IsInRaid and IsInRaid()
  local x, y, cont = Geo.PlayerWorld()
  if not x then return nil end
  local n = GetNumGroupMembers and GetNumGroupMembers() or 0
  if ns.IsSecret and ns.IsSecret(n) then return nil end
  for i = 1, math.min(n, 40) do
    local unit = raid and ("raid" .. i) or ("party" .. i)
    local ok, mine = pcall(UnitIsUnit, unit, "player")
    if not (ok and mine) and UnitExists and UnitExists(unit) then
      local _, class = UnitClass(unit)
      local level = UnitLevel(unit)
      local okp, ux, uy, _, inst = pcall(UnitPosition, unit)
      local readable = not (ns.IsSecret and (ns.IsSecret(class) or ns.IsSecret(level) or ns.IsSecret(ux)))
      local on = not UnitIsConnected or UnitIsConnected(unit)
      if readable and on and class == "MAGE" and okp and ux and Geo.Base(inst) == Geo.Base(cont)
          and (ux - x) ^ 2 + (uy - y) ^ 2 <= T.PARTY_MAGE_YD ^ 2 then
        local name = UnitName(unit)
        if name and not (ns.IsSecret and ns.IsSecret(name)) then return name, level end
      end
    end
  end
  return nil
end

-- The portals a party mage near the player can open for them: { name, dest, ask = the mage's name, spell }.
local function PartyPortals()
  local st = S()
  if not st or not st.usePartyPortals then return {} end
  local mage, level = T.PartyMage()
  if not mage then return {} end
  local side = UnitFactionGroup and UnitFactionGroup("player")
  local out = {}
  for _, p in ipairs(T.PARTY_PORTALS) do
    if p[7] == side and (level or 0) >= p[6] then
      out[#out + 1] = { string.format(L["%s's portal"], mage), { cont = p[2], x = p[3], y = p[4], name = p[5] },
        ask = mage, portal = p[1] }
    end
  end
  return out
end

local function SpellLeft(spell)
  local get = (C_Spell and C_Spell.GetSpellCooldown) or GetSpellCooldown
  if not get then return 0 end
  local ok, a, b = pcall(get, spell)
  if not ok then return 0 end
  if not Secret(a) and type(a) == "table" then return Left("s" .. spell, a.startTime, a.duration) end
  return Left("s" .. spell, a, b)
end

local function SpellReady(spell) return SpellLeft(spell) <= 0 end

-- Seconds left on the cooldown of a teleport row's item or spell (`t.item` / `t.spell`): 0 when ready.
-- (What the use button shows while it waits.)
function T.CooldownLeft(t)
  if not t then return 0 end
  if t.item then return ItemLeft(t.item) end
  if t.spell then return SpellLeft(t.spell) end
  return 0
end

-- A cooldown as the player reads it: "4:30" from a minute up, "45.3" under it.
function T.FormatCooldown(sec)
  sec = math.max(0, sec or 0)
  if sec >= 60 then
    local s = math.floor(sec)
    return string.format("%d:%02d", math.floor(s / 60), s % 60)
  end
  return string.format("%.1f", math.floor(sec * 10) / 10)
end

-- The hearthstone's destination: the spot recorded after the last hearth (exact), else
-- the town of the inn (GetBindLocation) found among the place names. (A recorded spot far from where the bind's name
-- says, another continent or past HOME_CHECK_YD, isn't taken: item 51b, Kooki3z 2026-11-24, "Use your Hearthstone (to
-- Valley of Trials)" and the route on from Undercity: the spot had been read before the teleport, the player still in
-- Undercity, and kept under the new bind's name.)
T.HOME_CHECK_YD = 600
T.HOME_MOVED_YD, T.HOME_WAIT_SECONDS = 200, 20
local NamedHome
function T.Home()
  local cdb = ns.CharDB and ns.CharDB()
  local bind = GetBindLocation and GetBindLocation()
  local rec = cdb and cdb.bind
  if rec and rec.name == bind then
    local named = NamedHome(bind)
    if not named or (Geo.Base(named.cont) == Geo.Base(rec.cont)
        and (named.x - rec.x) ^ 2 + (named.y - rec.y) ^ 2 <= T.HOME_CHECK_YD ^ 2) then
      return rec
    end
    cdb.bind = nil -- (not that inn's: forgotten, the next hearth records it again)
    return named
  end
  return NamedHome(bind)
end
function NamedHome(bind)
  if not bind or bind == "" then return nil end
  -- the inn's building (bind locations are often an inn's own name), then a place name
  -- (towns, villages), then any point of interest, then a zone or city map's middle
  -- (the bind location is the client's language, "Gasthaus Zur Höhle des Löwen", the data's names the English ones:
  -- the spots by Data/PlaceNames, the places and maps by their names in the game's language too)
  for en in pairs(ns.PlaceEnglishNames(bind)) do
    local spot = ns.AreaSpots and ns.AreaSpots[en]
    if spot then return { cont = spot[1], x = spot[2], y = spot[3], name = bind } end
  end
  for _, kind in ipairs({ 3, 2, 1 }) do
    for cont, list in pairs(ns.Pois or {}) do
      for _, p in ipairs(list) do
        local shown = ns.PoiName and ns.PoiName(p) or p[4]
        if p[1] == kind and (p[4] == bind or shown == bind
            or (kind == 1 and (p[4]:find(bind, 1, true) == 1 or shown:find(bind, 1, true) == 1))) then
          return { cont = cont, x = p[2], y = p[3], name = bind }
        end
      end
    end
  end
  for id, m in pairs(ns.Maps or {}) do
    if (m.name == bind or ns.ZoneName and ns.ZoneName(id, m.name) == bind) and m.bounds and m.continent
        and m.continent >= 0 then
      local b = m.bounds
      return { cont = Geo.MapCont(id), x = (b[1] + b[3]) / 2, y = (b[2] + b[4]) / 2, name = bind }
    end
  end
  return nil
end

-- A teleport as a transport row (Nav's format, used from where the player stands):
-- { cont, x, y, cont2, x2, y2, seconds, what, "", to, what, use = true, item = id | spell = id }
-- (item or spell: what the use button uses).
local function Row(c, cont, px, py)
  local dest = c[2]
  return { cont, px, py, dest.cont, dest.x, dest.y, (c.ask and T.PARTY_SECONDS or T.CAST_SECONDS) + (c.spare or 0), c[1], "", dest.name,
    c[1], use = true, item = c.item, spell = c.spell, ask = c.ask }
end

-- Astral Recall's name in the game's language. Whether the character knows it (a shaman from level 30): the directions,
-- the use button and the map menu's hearth button name it then (GPSFrame's G.SyncHearthQuick).
function T.RecallName() return ns.SpellName and ns.SpellName(ASTRAL_RECALL) or "Astral Recall" end
function T.RecallKnown() return SpellKnown(ASTRAL_RECALL) and true or false end
-- (seconds added to the hearthstone's row while Astral Recall is ready: T.Available)
T.RECALL_FIRST_SECONDS = 1

local cache, cacheAt = nil, -100
-- The teleports the character has that were on their cooldown as the list was built: { name, item = | spell = }.
-- Looked at every second (T.Tick): the game sends no event as a cooldown runs out.
local waiting = {}
T.TICK_SECONDS = 1

-- What's ready now, from (px, py) on `cont`. Cached for a few seconds (bags and cooldowns
-- don't change often; a teleport used goes on cooldown and drops out).
function T.Available(cont, px, py)
  local st = S()
  local hearth = not st or st.useHearthstone ~= false
  local teleports = not st or st.useTeleports ~= false
  local party = st and st.usePartyPortals
  if not hearth and not teleports and not party then return {} end
  local now = GetTime()
  if not cache or now - cacheAt > 3 then
    cacheAt = now
    cache, waiting = {}, {}
    -- (ready: a row; had but on its cooldown: waited for)
    local function Add(ready, name, dest, item, spell)
      if ready then cache[#cache + 1] = { name, dest, item = item, spell = spell }
      else waiting[#waiting + 1] = { name, item = item, spell = spell } end
    end
    local home = hearth and T.Home()
    if home then
      -- (a shaman's Astral Recall first: it goes home as fast, and keeps the hearthstone for later. Asked, 2026-10-01;
      -- again 2026-11-27, Kooki3z: "When you are on a Shaman ... recommend Astral Recall". The plan doesn't take the
      -- first of equals: Nav.Plan's next place is the nearest by `pairs`, whose order is the table's own, so with both
      -- ready the hearthstone was taken about as often. With Astral Recall ready, the hearthstone costs RECALL_FIRST_SECONDS
      -- more: never the one picked, still there for a later stretch. On its cooldown: the hearthstone, as before)
      local recall = SpellKnown(ASTRAL_RECALL) and SpellReady(ASTRAL_RECALL)
      if SpellKnown(ASTRAL_RECALL) then
        Add(recall, T.RecallName(), home, nil, ASTRAL_RECALL)
      end
      local stone, ready = Hearthstone()
      if stone then
        Add(ready, L["your Hearthstone"], home, stone)
        if ready and recall then cache[#cache].spare = T.RECALL_FIRST_SECONDS end
      end
    end
    for _, it in ipairs(teleports and T.ITEMS or {}) do -- (an engineer's teleporter: its specialization to use it)
      if (not it[6] or SpellKnown(it[6])) and ItemCount(it[1]) > 0 and (not it.worn or Worn(it[1])) and Usable(it[1]) then
        local name = GetItemInfo and GetItemInfo(it[1]) or it[7]
        Add(ItemReady(it[1]), name, { cont = it[2], x = it[3], y = it[4], name = it[5] }, it[1])
      end
    end
    local rune = ItemCount(RUNE_OF_TELEPORTATION) > 0
    for _, s in ipairs(teleports and T.SPELLS or {}) do
      if SpellKnown(s[1]) and (rune or not s[6]) then
        local name = ns.SpellName(s[1]) or string.format(L["Teleport: %s"], s[5])
        Add(SpellReady(s[1]), name, { cont = s[2], x = s[3], y = s[4], name = s[5] }, nil, s[1])
      end
    end
  end
  local out = {}
  for _, c in ipairs(cache) do out[#out + 1] = Row(c, cont, px, py) end
  -- (a party mage's portals: from where the player stands only, looked at each time: the mage moves)
  if party then
    local x, y, pc = Geo.PlayerWorld()
    if x and px and Geo.Base(pc) == Geo.Base(cont) and (px - x) ^ 2 + (py - y) ^ 2 <= T.PARTY_HERE_YD ^ 2 then
      for _, c in ipairs(PartyPortals()) do out[#out + 1] = Row(c, cont, px, py) end
    end
  end
  return out
end

function T.Changed() cache = nil end

-- Every second: a teleport the last list had on its cooldown and now ready. The list is built again, and with a
-- stop set the route is worked out again (the hearthstone ready halfway may be quicker; the recalculation keeps
-- the route it has unless the new one is clearly shorter), said in the chat. Returns the names now ready.
function T.Tick()
  if #waiting == 0 then return nil end
  local ready, still = {}, {}
  for _, w in ipairs(waiting) do
    if T.CooldownLeft(w) <= 0 then ready[#ready + 1] = w[1] else still[#still + 1] = w end
  end
  if #ready == 0 then return nil end
  waiting = still
  cache = nil
  local N = ns.Nav
  if N and N.dest and N.Invalidate then
    N.Invalidate(true)
    if ns.Print then
      local names = table.concat(ready, ", ")
      ns.Print(string.format(L["%s ready again: the route is worked out again with it."], (names:gsub("^%l", string.upper))))
    end
  end
  return ready
end

-- The names waiting on their cooldown (for the tests and /agps debug).
function T.Waiting()
  local out = {}
  for _, w in ipairs(waiting) do out[#out + 1] = w[1] end
  return out
end

-- In the inn you're bound to: remember exactly where it is.
function T.LearnHome()
  local bind = GetBindLocation and GetBindLocation()
  local sub = GetSubZoneText and GetSubZoneText()
  if not bind or bind == "" or sub ~= bind then return end
  local x, y, cont = Geo.PlayerWorld()
  local cdb = ns.CharDB and ns.CharDB()
  if not x or not cdb then return end
  local b = cdb.bind
  if b and b.name == bind and b.cont == cont and (b.x - x) ^ 2 + (b.y - y) ^ 2 < 900 then return end
  cdb.bind = { cont = cont, x = x, y = y, name = bind }
  cache = nil
  if ns.Nav then ns.Nav.Invalidate(true, true) end
end

-- Just bound at an innkeeper (HEARTHSTONE_BOUND, item 109): the player stands by the innkeeper, so that's home, whatever
-- the bind's name says (the client gives only the name; an inn whose name isn't the subzone's was learned only after the
-- first hearth). Kept in the character's own db (CharDB().bind) at runtime, never written to a file by hand.
function T.LearnBind()
  local bind = GetBindLocation and GetBindLocation()
  local x, y, cont = Geo.PlayerWorld()
  local cdb = ns.CharDB and ns.CharDB()
  if not bind or bind == "" or not x or not cdb then return end
  cdb.bind = { cont = cont, x = x, y = y, name = bind }
  cache = nil
  if ns.Nav then ns.Nav.Invalidate(true, true) end
end

-- For /agps debug: what the addon sees.
function T.Describe()
  local home = T.Home()
  local list = {}
  local x, y, cont = Geo.PlayerWorld()
  if x then
    for _, r in ipairs(T.Available(cont, x, y)) do list[#list + 1] = r[8] .. " -> " .. r[10] end
  end
  local wait = T.Waiting()
  return string.format("bind=%s home=%s hearthstones=%d ready=%s available: %s waiting: %s",
    tostring(GetBindLocation and GetBindLocation()), home and string.format("%s (%d, %.0f, %.0f)", home.name, home.cont, home.x, home.y) or "unknown",
    ItemCount(HEARTHSTONE_ITEM) + ItemCount(T.HEARTHSTONE_ITEMS[2]), tostring(select(2, Hearthstone())), #list > 0 and table.concat(list, ", ") or "none",
    #wait > 0 and table.concat(wait, ", ") or "none")
end

-- After a hearth: remember exactly where it lands (for the next route).
function T.Init()
  local ev = CreateFrame("Frame")
  ev:RegisterEvent("UNIT_SPELLCAST_SUCCEEDED")
  ev:RegisterEvent("BAG_UPDATE_COOLDOWN")
  ev:RegisterEvent("SPELLS_CHANGED")
  -- standing in the inn you're bound to (or binding there): that's exactly home
  ev:RegisterEvent("ZONE_CHANGED")
  ev:RegisterEvent("ZONE_CHANGED_INDOORS")
  ev:RegisterEvent("PLAYER_ENTERING_WORLD")
  ev:RegisterEvent("HEARTHSTONE_BOUND")
  ev:RegisterEvent("GROUP_ROSTER_UPDATE") -- (a party mage joined or left: usePartyPortals)
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(T.TICK_SECONDS, T.Tick) end
  ev:SetScript("OnEvent", function(_, event, unit, _, spell)
    cache = nil
    if event == "GROUP_ROSTER_UPDATE" then
      local st = S()
      if st and st.usePartyPortals and ns.Nav and ns.Nav.dest and ns.Nav.Invalidate then ns.Nav.Invalidate(true) end
      return
    end
    if event == "HEARTHSTONE_BOUND" then
      C_Timer.After(1, T.LearnBind)
      return
    end
    if event == "SPELLS_CHANGED" and ns.GPS and ns.GPS.SyncHearthQuick then ns.GPS.SyncHearthQuick() end -- (Astral Recall learned)
    if event ~= "UNIT_SPELLCAST_SUCCEEDED" then
      C_Timer.After(1, T.LearnHome)
      return
    end
    if event == "UNIT_SPELLCAST_SUCCEEDED" and unit == "player" and T.HOME_SPELLS[spell] then
      -- (recorded once the player is there: moved HOME_MOVED_YD or more, or onto another continent, looked at each second
      -- up to HOME_WAIT_SECONDS; the loading screen can outlast a fixed wait, item 51b)
      local fx, fy, fcont = Geo.PlayerWorld()
      local tries = 0
      local function Arrived()
        tries = tries + 1
        local x, y, cont = Geo.PlayerWorld()
        local moved = x and fx and (Geo.Base(cont) ~= Geo.Base(fcont) or (x - fx) ^ 2 + (y - fy) ^ 2 >= T.HOME_MOVED_YD ^ 2)
        if not moved then
          if tries < T.HOME_WAIT_SECONDS then C_Timer.After(1, Arrived) end
          return
        end
        local cdb = ns.CharDB and ns.CharDB()
        if x and cdb then cdb.bind = { cont = cont, x = x, y = y, name = GetBindLocation and GetBindLocation() } end
        -- (in an inn with its inside: the floor followed from the innkeeper's, Nav.Hearthed)
        if x and ns.Nav and ns.Nav.Hearthed and spell ~= ASTRAL_RECALL then
          ns.Nav.Hearthed(ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont) or cont, x, y)
        end
        if ns.Nav then ns.Nav.Invalidate(true) end
      end
      C_Timer.After(4, Arrived)
    end
  end)
  if ns.TimeScript then ns.TimeScript(ev, "OnEvent", "events (teleports)") end
end
