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

-- Where each teleport lands (world yards, approximate): { spell, cont, x, y, name, needsRune }
T.SPELLS = {
  { 3567, 1, 1469.9, -4221.5, "Orgrimmar", true }, -- Teleport: Orgrimmar
  { 3563, 0, 1773.5, 61.1, "Undercity", true }, -- Teleport: Undercity
  { 3566, 1, -965.0, 283.4, "Thunder Bluff", true }, -- Teleport: Thunder Bluff
  { 3561, 0, -9003.5, 869.0, "Stormwind", true }, -- Teleport: Stormwind
  { 3562, 0, -4613.6, -915.4, "Ironforge", true }, -- Teleport: Ironforge
  { 3565, 1, 9660.8, 2513.6, "Darnassus", true }, -- Teleport: Darnassus
  { 18960, 1, 7980.0, -2501.0, "Moonglade", false }, -- Teleport: Moonglade (druid)
}

-- Teleport items: { item, cont, x, y, name, the engineering specialization it needs (spell), item name }
T.ITEMS = {
  { 18984, 1, 6723.5, -4662.5, "Everlook", 20222, "Dimensional Ripper - Everlook" }, -- Goblin Engineer
  { 18986, 1, -7139.1, -3752.1, "Gadgetzan", 20219, "Ultrasafe Transporter: Gadgetzan" }, -- Gnomish Engineer
}
T.HEARTHSTONE_ITEM, T.ASTRAL_RECALL = HEARTHSTONE_ITEM, ASTRAL_RECALL

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
-- the town of the inn (GetBindLocation) found among the place names.
function T.Home()
  local cdb = ns.CharDB and ns.CharDB()
  local bind = GetBindLocation and GetBindLocation()
  local rec = cdb and cdb.bind
  if rec and rec.name == bind then return rec end
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
  return { cont, px, py, dest.cont, dest.x, dest.y, T.CAST_SECONDS, c[1], "", dest.name, c[1], use = true,
    item = c.item, spell = c.spell }
end

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
  if not hearth and not teleports then return {} end
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
      -- (a shaman's Astral Recall first: it goes home as fast, and keeps the hearthstone for later; the
      -- route takes the first of equals. Asked, 2026-10-01)
      if SpellKnown(ASTRAL_RECALL) then
        Add(SpellReady(ASTRAL_RECALL), ns.SpellName and ns.SpellName(ASTRAL_RECALL) or "Astral Recall", home, nil, ASTRAL_RECALL)
      end
      if ItemCount(HEARTHSTONE_ITEM) > 0 then Add(ItemReady(HEARTHSTONE_ITEM), L["your Hearthstone"], home, HEARTHSTONE_ITEM) end
    end
    for _, it in ipairs(teleports and T.ITEMS or {}) do -- (an engineer's teleporter: its specialization to use it)
      if SpellKnown(it[6]) and ItemCount(it[1]) > 0 then
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
    ItemCount(HEARTHSTONE_ITEM), tostring(ItemReady(HEARTHSTONE_ITEM)), #list > 0 and table.concat(list, ", ") or "none",
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
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(T.TICK_SECONDS, T.Tick) end
  ev:SetScript("OnEvent", function(_, event, unit, _, spell)
    cache = nil
    if event ~= "UNIT_SPELLCAST_SUCCEEDED" then
      C_Timer.After(1, T.LearnHome)
      return
    end
    if event == "UNIT_SPELLCAST_SUCCEEDED" and unit == "player" and (spell == HEARTHSTONE_SPELL or spell == ASTRAL_RECALL) then
      C_Timer.After(4, function()
        local x, y, cont = Geo.PlayerWorld()
        local cdb = ns.CharDB and ns.CharDB()
        if x and cdb then cdb.bind = { cont = cont, x = x, y = y, name = GetBindLocation and GetBindLocation() } end
        -- (in an inn with its inside: the floor followed from the innkeeper's, Nav.Hearthed)
        if x and ns.Nav and ns.Nav.Hearthed and spell == HEARTHSTONE_SPELL then
          ns.Nav.Hearthed(ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont) or cont, x, y)
        end
        if ns.Nav then ns.Nav.Invalidate(true) end
      end)
    end
  end)
  if ns.TimeScript then ns.TimeScript(ev, "OnEvent", "events (teleports)") end
end
