-- Map layers on the GPS, from what the game tells addons (display only):
--  * Quests: objectives and turn-ins of your quests (C_QuestLog.GetQuestsOnMap). Clients
--    without that API: the quest pins the world map showed when you opened it. (Quests to
--    pick up aren't shown: this client only draws them on its own minimap, where addons
--    can't read them.)
--  * Gathering nodes (like GatherMate): herbs and ore you gathered, plus nodes you hover on
--    the minimap (its tooltip names them; the cursor gives the spot). The game doesn't give
--    addons the minimap's icons themselves, so nodes are only known once seen this way.
--    Saved account-wide; shown only for professions the character has.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local Geo = ns.Geo

local Lay = {}
ns.Layers = Lay
Lay.version = 0 -- bumped when there's something new to draw (the GPS redraws on change)

Lay.QUEST_TTL = 5 -- seconds a map's quest list is reused
Lay.NODE_MERGE_YD = 20 -- the same node seen again within this distance is the same node
Lay.MAX_MARKS = 120
-- Minimap width in yards per zoom level (index 1 = zoom 0), outdoors and indoors.
Lay.MINIMAP_OUTDOOR = { 1400 / 3, 400, 1000 / 3, 800 / 3, 200, 400 / 3 }
Lay.MINIMAP_INDOOR = { 300, 240, 180, 120, 80, 50 }

Lay.ICON = {
  objective = "atlas:SideInProgressQuestIcon", -- the world map's in-progress quest (circle, three dots)
  objectiveFallback = "Interface\\RaidFrame\\ReadyCheck-Waiting",
  turnin = "Interface\\GossipFrame\\ActiveQuestIcon",
  available = "Interface\\GossipFrame\\AvailableQuestIcon",
}

-- The herbs and ore veins there are (enUS names): only these are ever saved, whatever was gathered, hovered or
-- imported, and those whose tooltip shows the profession (L.LearnNode). (Asked 2026-11-05: collecting a quest's
-- ground pickups with a Dark Enforcer targeted saved "Dark Enforcer" as a herb, and pickups like "Doom Weed" passed
-- for herbs by their words. The client's cache: these have the gathering locks, 29 and up for herbs and 38 for veins;
-- the pickups have others, 43 and 259. WoW Forever's own: Poor Copper Vein, Stunted Silverleaf.)
Lay.KNOWN_NODES = {
  ore = { "Copper Vein", "Poor Copper Vein", "Tin Vein", "Silver Vein", "Iron Deposit", "Gold Vein", "Mithril Deposit",
    "Truesilver Deposit", "Small Thorium Vein", "Rich Thorium Vein", "Dark Iron Deposit",
    "Incendicite Mineral Vein", "Lesser Bloodstone Deposit", "Indurium Mineral Vein",
    "Ooze Covered Silver Vein", "Ooze Covered Gold Vein", "Ooze Covered Truesilver Deposit",
    "Ooze Covered Mithril Deposit", "Ooze Covered Thorium Vein", "Ooze Covered Rich Thorium Vein",
    "Hakkari Thorium Vein", "Small Obsidian Chunk", "Large Obsidian Chunk" },
  herb = { "Peacebloom", "Silverleaf", "Earthroot", "Mageroyal", "Briarthorn", "Stranglekelp",
    "Bruiseweed", "Wild Steelbloom", "Grave Moss", "Kingsblood", "Liferoot", "Fadeleaf", "Goldthorn",
    "Khadgar's Whisker", "Wintersbite", "Firebloom", "Purple Lotus", "Arthas' Tears", "Sungrass",
    "Blindweed", "Ghost Mushroom", "Gromsblood", "Golden Sansam", "Dreamfoil", "Mountain Silversage",
    "Plaguebloom", "Icecap", "Black Lotus", "Stunted Silverleaf" },
}
-- What gathering each gives (asked 2026-11-06: each node on the map shows the bag icon of its item, not the gathering
-- spell's for all): the item's ID, its icon read at runtime (C_Item.GetItemIconByID, no item cache needed). From the
-- CMaNGOS classic dump's loot (gameobject_loot_template, the 100% item). WoW Forever's own (Stunted Silverleaf, Poor
-- Copper Vein, those learned by their tooltips) aren't here: their icon is learned from the loot (L.OnGatherLoot).
Lay.NODE_ITEMS = {
  ["Peacebloom"] = 2447, ["Silverleaf"] = 765, ["Earthroot"] = 2449, ["Mageroyal"] = 785, ["Briarthorn"] = 2450,
  ["Stranglekelp"] = 3820, ["Bruiseweed"] = 2453, ["Wild Steelbloom"] = 3355, ["Grave Moss"] = 3369,
  ["Kingsblood"] = 3356, ["Liferoot"] = 3357, ["Fadeleaf"] = 3818, ["Goldthorn"] = 3821, ["Khadgar's Whisker"] = 3358,
  ["Wintersbite"] = 3819, ["Firebloom"] = 4625, ["Purple Lotus"] = 8831, ["Arthas' Tears"] = 8836, ["Sungrass"] = 8838,
  ["Blindweed"] = 8839, ["Ghost Mushroom"] = 8845, ["Gromsblood"] = 8846, ["Golden Sansam"] = 13464,
  ["Dreamfoil"] = 13463, ["Mountain Silversage"] = 13465, ["Plaguebloom"] = 13466, ["Icecap"] = 13467,
  ["Black Lotus"] = 13468,
  ["Copper Vein"] = 2770, ["Tin Vein"] = 2771, ["Silver Vein"] = 2775, ["Iron Deposit"] = 2772, ["Gold Vein"] = 2776,
  ["Mithril Deposit"] = 3858, ["Truesilver Deposit"] = 7911, ["Small Thorium Vein"] = 10620,
  ["Rich Thorium Vein"] = 10620, ["Dark Iron Deposit"] = 11370, ["Incendicite Mineral Vein"] = 3340,
  ["Lesser Bloodstone Deposit"] = 4278, ["Indurium Mineral Vein"] = 5833, ["Ooze Covered Silver Vein"] = 2775,
  ["Ooze Covered Gold Vein"] = 2776, ["Ooze Covered Truesilver Deposit"] = 7911, ["Ooze Covered Mithril Deposit"] = 3858,
  ["Ooze Covered Thorium Vein"] = 10620, ["Ooze Covered Rich Thorium Vein"] = 10620, ["Hakkari Thorium Vein"] = 10620,
  ["Small Obsidian Chunk"] = 22202, ["Large Obsidian Chunk"] = 22203,
}
Lay.LOOT_AFTER_GATHER = 5 -- seconds after a gathering cast its loot window is that node's
local function SpellName(id) return ns.SpellName and ns.SpellName(id) end -- Core.lua
local function SpellIcon(id) return ns.SpellIcon and ns.SpellIcon(id) end
Lay.GATHER_SPELLS = { ore = 2575, herb = 2366 } -- Mining, Herb Gathering (apprentice)
-- every rank's gathering spell (a higher rank casts a different spell ID)
Lay.GATHER_IDS = {
  [2575] = "ore", [2576] = "ore", [3564] = "ore", [10248] = "ore", [29354] = "ore", [50310] = "ore",
  [2366] = "herb", [2368] = "herb", [3570] = "herb", [11993] = "herb", [28695] = "herb", [50300] = "herb",
}
Lay.PROFESSION = { ore = "Mining", herb = "Herbalism" } -- skill line names (enUS; localized below)

local nodeKind = {} -- node name -> "ore" / "herb"
for kind, names in pairs(Lay.KNOWN_NODES) do
  for _, n in ipairs(names) do nodeKind[n] = kind end
end

---------------------------------------------------------------------------
-- Coordinates
---------------------------------------------------------------------------

-- World position (continent x, y) of a normalized position on uiMap `mapID`.
function Lay.MapToWorld(mapID, u, v)
  local m = ns.Maps and ns.Maps[mapID]
  local b = m and m.bounds
  if not b or not u or not v then return nil end
  return b[3] - v * (b[3] - b[1]), b[4] - u * (b[4] - b[2]), Geo.MapCont(mapID)
end

-- World offset of a point `dx`, `dy` UI units right/up of the minimap center: minimap
-- `width` UI units showing `yards` yards; `facing` when the minimap turns with the player.
function Lay.MinimapOffset(dx, dy, width, yards, facing)
  local k = yards / width
  dx, dy = dx * k, dy * k
  local f = facing or 0
  -- forward = (cos f, sin f) in (X north, Y west); right = (sin f, -cos f)
  return dy * math.cos(f) + dx * math.sin(f), dy * math.sin(f) - dx * math.cos(f)
end

---------------------------------------------------------------------------
-- Gathering nodes
---------------------------------------------------------------------------

local function DB()
  local db = ns.db
  if not db then return nil end
  db.nodes = db.nodes or {}
  return db.nodes
end

-- Nodes: { x, y, name, kind, times seen, unconfirmed? } per continent. Imported nodes are
-- unconfirmed (drawn faded) until the player gathers there.

-- Names learned from the game's tooltips (account-wide): { [name] = "herb" / "ore" }.
local function Learned()
  local db = ns.db
  if not db then return nil end
  db.nodeNames = db.nodeNames or {}
  return db.nodeNames
end

-- A node's kind from its name ("herb" / "ore"), or nil: not a herb or vein (KNOWN_NODES, or learned).
function Lay.NodeKind(name)
  -- (a secret name, a cast's target in combat, can't be a table key: a player's report 2026-11-16, an error on every
  -- cast in combat in Blackfathom Deeps)
  if not name or (ns.IsSecret and ns.IsSecret(name)) then return nil end
  local learned = nodeKind[name] == nil and Learned()
  return nodeKind[name] or (learned and learned[name]) or nil
end

-- A world object's tooltip: its name, then the profession that gathers it ("Herbalism", "Mining") when it's a herb
-- or vein; units, items and quest pickups have no such line. (2026-11-06: WoW Forever's Stunted Silverleaf in
-- Teldrassil wasn't in KNOWN_NODES and its gathering wasn't saved.) Returns the kind learned, or nil.
function Lay.LearnNode(name, line2)
  if not name or name == "" or not line2 then return nil end
  for kind, prof in pairs(Lay.PROFESSION) do
    if line2 == prof and name ~= prof then
      local learned = Learned()
      if learned and not nodeKind[name] then learned[name] = kind end
      return kind
    end
  end
  return nil
end

-- A saved node that is a herb or vein, as its name says (one saved before 2026-11-05 may be a unit or a pickup).
function Lay.IsNode(n) return Lay.NodeKind(n[3]) == n[4] end

-- Add a node sighting (merging with one already known nearby). Returns true if new. Only a herb or vein, of
-- `kind` when given (KNOWN_NODES).
-- `imported`: from a list, not seen here yet (unconfirmed until gathered).
function Lay.AddNode(cont, x, y, name, kind, imported)
  local db = DB()
  if not db or not cont or not name then return false end
  local real = Lay.NodeKind(name)
  if not real or (kind and kind ~= real) then return false end
  kind = real
  local list = db[cont]
  if not list then
    list = {}
    db[cont] = list
  end
  local r2 = Lay.NODE_MERGE_YD * Lay.NODE_MERGE_YD
  for _, n in ipairs(list) do
    -- the same node: the same name nearby (or an imported one of the same kind)
    if (n[3] == name or (n[6] and n[4] == kind)) and (n[1] - x) ^ 2 + (n[2] - y) ^ 2 <= r2 then
      if not imported then
        n[5] = (n[5] or 1) + 1
        if n[6] then n[3], n[6] = name, nil end -- gathered here: confirmed
      end
      return false
    end
  end
  list[#list + 1] = { math.floor(x * 10 + 0.5) / 10, math.floor(y * 10 + 0.5) / 10, name, kind, 1, imported or nil }
  return true
end

-- Imported nodes in one go ({ { level, x, y, name, kind }, ... }; unconfirmed until gathered): as L.AddNode, but the
-- nodes near each looked up by a grid of NODE_MERGE_YD (an import of thousands: not each against every node known).
-- Returns how many were added, how many were known already.
function Lay.AddNodes(list)
  local db = DB()
  if not db then return 0, 0 end
  local C = Lay.NODE_MERGE_YD
  local grids = {}
  local function cell(x, y) return math.floor(x / C) * 65536 + math.floor(y / C) end
  local function grid(cont)
    local g = grids[cont]
    if not g then
      g = {}
      for _, n in ipairs(db[cont] or {}) do
        local k = cell(n[1], n[2])
        g[k] = g[k] or {}
        g[k][#g[k] + 1] = n
      end
      grids[cont] = g
    end
    return g
  end
  local added, had = 0, 0
  for _, s in ipairs(list or {}) do
    local kind = Lay.NodeKind(s.name)
    if kind and (not s.kind or s.kind == kind) and s.level and s.x and s.y then
      local g = grid(s.level)
      local cx, cy = math.floor(s.x / C), math.floor(s.y / C)
      local same = false
      for dx = -1, 1 do
        for dy = -1, 1 do
          for _, n in ipairs(g[(cx + dx) * 65536 + cy + dy] or {}) do
            -- (the same node: the same name nearby, or an imported one of the same kind; as L.AddNode)
            if (n[3] == s.name or (n[6] and n[4] == kind)) and (n[1] - s.x) ^ 2 + (n[2] - s.y) ^ 2 <= C * C then same = true end
          end
        end
      end
      if same then
        had = had + 1
      else
        local nodes = db[s.level] or {}
        db[s.level] = nodes
        local n = { math.floor(s.x * 10 + 0.5) / 10, math.floor(s.y * 10 + 0.5) / 10, s.name, kind, 1, true }
        nodes[#nodes + 1] = n
        local k = cell(n[1], n[2])
        g[k] = g[k] or {}
        g[k][#g[k] + 1] = n
        added = added + 1
      end
    end
  end
  return added, had
end

-- Import nodes from text: lines like TomTom's "/way Elwynn Forest 43.2 65.1 Copper Vein"
-- (see Import.lua). The name says what it is ("Copper Vein", "Peacebloom": KNOWN_NODES).
-- Returns added, skipped (already known), errors.
function Lay.ImportNodes(text)
  local stops, errors = ns.Import.Parse(text, C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player"))
  local list = {}
  for _, d in ipairs(stops) do
    local kind = not d.unnamed and Lay.NodeKind(d.name) -- (a line with no name: its zone's isn't the node's)
    if d.unnamed then
      errors[#errors + 1] = L["a line with no herb or ore name"]
    elseif not kind then
      errors[#errors + 1] = string.format(L["'%s': not a herb or ore name"], d.name or "?")
    else
      list[#list + 1] = { level = d.cont, x = d.x, y = d.y, name = d.name, kind = kind }
    end
  end
  local added, skipped = Lay.AddNodes(list)
  return added, skipped, errors
end

-- Is world (x, y) inside the polygon { x1, y1, x2, y2, ... } (even-odd rule)?
function Lay.InPolygon(x, y, poly)
  local inside, n = false, #poly / 2
  local j = n
  for i = 1, n do
    local xi, yi, xj, yj = poly[2 * i - 1], poly[2 * i], poly[2 * j - 1], poly[2 * j]
    if (yi > y) ~= (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi then inside = not inside end
    j = i
  end
  return inside
end

-- The known nodes inside a drawn area on continent `cont`, of the kinds in `kinds`
-- ({ ore = true, herb = true }; nil: all) and the names in `names` ({ [name] = true }; nil: any; L.NodeFilter):
-- { { x, y, cont, name }, ... }.
function Lay.NodesInPolygon(cont, poly, kinds, names)
  local out = {}
  local db = DB()
  for _, n in ipairs(db and db[cont] or {}) do
    if (not kinds or kinds[n[4]]) and (not names or names[n[3]]) and Lay.IsNode(n) and Lay.InPolygon(n[1], n[2], poly) then
      out[#out + 1] = { x = n[1], y = n[2], cont = cont, name = n[3], tex = Lay.NodeIcon(n[4], n[3]) }
    end
  end
  -- (the tutorial's example herbs and ore, Tutorial.lua: Lay.demoNodes[cont] = { { x, y, name, kind }, ... }, in
  -- memory only, never the saved nodes)
  for _, n in ipairs(Lay.demoNodes and Lay.demoNodes[cont] or {}) do
    if (not kinds or kinds[n[4]]) and Lay.InPolygon(n[1], n[2], poly) then
      out[#out + 1] = { x = n[1], y = n[2], cont = cont, name = n[3], tex = Lay.NodeIcon(n[4], n[3]) }
    end
  end
  return out
end

-- Profession skill lines the character has (by kind).
local profCache, profAt = nil, -100
local function Professions()
  if profCache and GetTime() - profAt < 10 then return profCache end
  local have = {}
  profCache, profAt = have, GetTime()
  pcall(function()
    local want = {}
    for kind, spell in pairs(Lay.GATHER_SPELLS) do
      want[Lay.PROFESSION[kind]] = kind
      local sname = SpellName(spell)
      if sname then want[sname] = kind end -- e.g. localized "Mining"
    end
    for i = 1, GetNumSkillLines() do
      local name, isHeader = GetSkillLineInfo(i)
      if not isHeader and want[name] then have[want[name]] = true end
    end
  end)
  return have
end
Lay.Professions = Professions

-- The node kinds shown on the map (the Herbs and Ore layers), which a farming area uses too.
function Lay.VisibleKinds(st)
  st = st or ns.settings.gps
  return { herb = st.layerHerbs ~= false, ore = st.layerOre ~= false }
end

-- The herbs and veins picked in Find Herbs and Ore (asked 2026-11-06: search for particular herbs or veins, only
-- theirs on the map): { [name] = true }, or nil when none are picked (every one shown). `gps.nodeFilter`.
function Lay.NodeFilter(st)
  st = st or ns.settings.gps
  local f = st and st.nodeFilter
  if type(f) ~= "table" or next(f) == nil then return nil end
  return f
end

-- Whether a node of `kind` named `name` shows on the map: its layer on (Herbs, Ore) and, with some picked, one of them.
function Lay.NodeShown(name, kind, st, kinds, filter)
  st = st or ns.settings.gps
  kinds = kinds or Lay.VisibleKinds(st)
  if not kinds[kind] then return false end
  filter = filter or Lay.NodeFilter(st)
  return not filter or filter[name] == true
end

-- Pick a herb or vein to show (`on`), or put it back; `name` nil with `on` false: none picked, every one shown. A pick
-- turns its kind's layer on (only it would show otherwise: nothing). The map is drawn again at once.
function Lay.SetNodeFilter(name, on)
  local st = ns.settings.gps
  if type(st.nodeFilter) ~= "table" then st.nodeFilter = {} end
  if name == nil then
    if not on then st.nodeFilter = {} end
  else
    st.nodeFilter[name] = on and true or nil
    local kind = on and Lay.NodeKind(name)
    if kind == "herb" then st.layerHerbs = true elseif kind == "ore" then st.layerOre = true end
  end
  Lay.version = Lay.version + 1
  local G = ns.GPS
  if G and G.Redraw then G.Redraw() end
  if G and G.RefreshQuick then G.RefreshQuick() end
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
  if Lay.finder and Lay.finder:IsShown() and Lay.finder.Refresh then Lay.finder.Refresh() end
end

-- Every herb and vein name there is (KNOWN_NODES, the learned ones, any saved), for Find Herbs and Ore: matching
-- `query` (any case; "" or nil: all), { { name, kind, count = nodes known, picked, icon }, ... }: picked first, then
-- those with nodes known, then names starting with the query, then by name.
function Lay.NodeNames(query)
  local q = (query or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
  local counts, kinds = {}, {}
  for name, kind in pairs(nodeKind) do kinds[name] = kind end
  for name, kind in pairs(Learned() or {}) do kinds[name] = kinds[name] or kind end
  for _, list in pairs(DB() or {}) do
    for _, n in ipairs(list) do
      if Lay.IsNode(n) then counts[n[3]] = (counts[n[3]] or 0) + 1 end
    end
  end
  local filter = Lay.NodeFilter() or {}
  local out = {}
  for name, kind in pairs(kinds) do
    local i = q == "" and 1 or name:lower():find(q, 1, true)
    if i then
      out[#out + 1] = { name = name, kind = kind, count = counts[name] or 0, picked = filter[name] == true,
        icon = Lay.NodeIcon(kind, name), starts = i == 1 }
    end
  end
  table.sort(out, function(a, b)
    if a.picked ~= b.picked then return a.picked end
    if (a.count > 0) ~= (b.count > 0) then return a.count > 0 end
    if a.starts ~= b.starts then return a.starts end
    return a.name < b.name
  end)
  return out
end

---------------------------------------------------------------------------
-- Quests
---------------------------------------------------------------------------

local questCache = {} -- [mapID] = { t, marks }
local seenPins = {} -- [mapID] = { { kind, u, v, name }, ... } from the world map, this session

-- (each quest's title as last read: a quest turned in may have none from the game any more)
local titles = {}
local function QuestTitle(id)
  local Q = C_QuestLog
  local t
  if Q.GetTitleForQuestID then t = Q.GetTitleForQuestID(id) elseif Q.GetQuestInfo then t = Q.GetQuestInfo(id) end
  if type(t) == "string" and t ~= "" and not (ns.IsSecret and ns.IsSecret(t)) then titles[id] = t end
  return t or titles[id]
end
Lay.QuestTitle = QuestTitle

-- A quest for a group (asked 2026-10-06: the quest route asks before keeping one): { size = players suggested,
-- elite = true/false, tag = its tag's name ("Elite", "Group", "Dungeon") }, or nil for a quest to do alone.
Lay.GROUP_TAGS = { elite = true, group = true, dungeon = true, raid = true }
function Lay.QuestGroup(id)
  local Q = C_QuestLog
  if not (Q and id) then return nil end
  local function known(v) return v ~= nil and not (ns.IsSecret and ns.IsSecret(v)) end
  local size = 0
  if Q.GetSuggestedGroupSize then
    local ok, n = pcall(Q.GetSuggestedGroupSize, id)
    if ok and known(n) then size = tonumber(n) or 0 end
  end
  if size <= 1 and Q.GetLogIndexForQuestID and Q.GetInfo then -- (the log's own field)
    local ok, i = pcall(Q.GetLogIndexForQuestID, id)
    local info = ok and known(i) and i and Q.GetInfo(i)
    if type(info) == "table" and known(info.suggestedGroup) then size = math.max(size, tonumber(info.suggestedGroup) or 0) end
  end
  local elite, tagName = false, nil
  if Q.GetQuestTagInfo then
    local ok, tag = pcall(Q.GetQuestTagInfo, id)
    if ok and type(tag) == "table" then
      if known(tag.isElite) and tag.isElite then elite = true end
      if known(tag.tagName) and type(tag.tagName) == "string" then tagName = tag.tagName end
    end
  end
  local grouped = tagName and Lay.GROUP_TAGS[tagName:lower()]
  if tagName and tagName:lower() == "elite" then elite = true end
  if size > 1 or elite or grouped then return { size = size, elite = elite, tag = tagName } end
  return nil
end

-- A red quest (asked 2026-11-07: "do the same for red quests to offer leaving them out of the route", as the group
-- quests): its level at least QUEST_RED_LEVELS over the player's, as the quest log colors it red. Its level, or nil.
Lay.QUEST_RED_LEVELS = 5
function Lay.QuestRed(id)
  local Q = C_QuestLog
  if not (Q and id) then return nil end
  local function known(v) return type(v) == "number" and not (ns.IsSecret and ns.IsSecret(v)) end
  local lvl
  if Q.GetQuestDifficultyLevel then
    local ok, n = pcall(Q.GetQuestDifficultyLevel, id)
    if ok and known(n) and n > 0 then lvl = n end
  end
  if not lvl and Q.GetLogIndexForQuestID and Q.GetInfo then
    local ok, i = pcall(Q.GetLogIndexForQuestID, id)
    local info = ok and i and not (ns.IsSecret and ns.IsSecret(i)) and Q.GetInfo(i)
    if type(info) == "table" and known(info.level) and info.level > 0 then lvl = info.level end
  end
  local ok, me = pcall(UnitLevel or error, "player")
  if not (lvl and ok and known(me) and me > 0) then return nil end
  return lvl - me >= Lay.QUEST_RED_LEVELS and lvl or nil
end

-- Quest marks on uiMap `mapID`: { { x, y, cont, kind, name }, ... }
local function QuestMarks(mapID, st)
  local c = questCache[mapID]
  local now = GetTime()
  if c and now - c.t < Lay.QUEST_TTL then return c.marks end
  local marks = {}
  local function add(u, v, kind, name, questID)
    local x, y, cont = Lay.MapToWorld(mapID, u, v)
    if x then marks[#marks + 1] = { x, y, cont, kind, name, questID } end
  end
  local direct = false
  local Q = C_QuestLog
  if Q and Q.GetQuestsOnMap then
    direct = true
    for _, q in ipairs(Q.GetQuestsOnMap(mapID) or {}) do
      local complete = Q.IsComplete and Q.IsComplete(q.questID)
      add(q.x, q.y, complete and "turnin" or "objective", QuestTitle(q.questID), q.questID)
    end
  end
  if not direct then
    for _, p in ipairs(seenPins[mapID] or {}) do add(p[2], p[3], p[1], p[4]) end
  end
  questCache[mapID] = { t = now, marks = marks }
  return marks
end

-- Fallback for clients without the quest APIs: remember the quest pins the world map
-- shows (read-only), per map, for this session.
local function ScrapeWorldMap()
  local wm = WorldMapFrame
  if not (wm and wm.EnumerateAllPins and wm.GetMapID) then return end
  local mapID = wm:GetMapID()
  if not mapID then return end
  local list = {}
  for pin in wm:EnumerateAllPins() do
    local tmpl = pin.pinTemplate or ""
    if tmpl:find("Quest") and pin.GetPosition then
      local u, v = pin:GetPosition()
      if u and v then
        if not tmpl:find("Offer") then -- your quests only
          list[#list + 1] = { pin.isComplete and "turnin" or "objective", u, v, pin.questID and QuestTitle(pin.questID) or nil }
        end
      end
    end
  end
  seenPins[mapID] = list
  questCache[mapID] = nil
  Lay.lastTemplates = Lay.lastTemplates or {}
  for pin in wm:EnumerateAllPins() do Lay.lastTemplates[pin.pinTemplate or "?"] = true end
end

---------------------------------------------------------------------------
-- Quest objective areas (the shapes the minimap and world map outline)
---------------------------------------------------------------------------
-- The game gives no outline data, but it can say whether a point on a map is inside a
-- quest's area (C_Minimap.IsInsideQuestBlob, or the world map's QuestPOIFrame widget).
-- Each area is traced once in the background: a coarse grid over the zone finds it, a
-- finer grid over its box gives the shape, marching squares turn that into an outline.
-- Cached per quest until its objectives change.

Lay.AREA_COARSE = 72 -- samples across the whole zone (finding the areas)
Lay.AREA_PAD = 2 -- coarse cells added around what was found, for the fine pass
Lay.AREA_STEP_YD = 5 -- fine sampling step
Lay.AREA_FINE_MIN, Lay.AREA_FINE_MAX = 40, 200 -- fine samples per side
Lay.AREA_SMOOTH = 2 -- rounds of corner cutting on the traced outline
Lay.AREA_SIMPLIFY = 0.35 -- grid cells: points closer than this to the line are dropped
Lay.AREA_BUDGET_MS = 2 -- tracing time per frame

-- Outline of a sampled shape: inside(i, j) for i = 0..nu-1, j = 0..nv-1 (outside the grid
-- counts as outside). Returns segments { i1, j1, i2, j2, ... } in grid units (edge midpoints).
function Lay.Outline(inside, nu, nv)
  local out = {}
  local function at(i, j)
    if i < 0 or j < 0 or i >= nu or j >= nv then return false end
    return inside(i, j) and true or false
  end
  for i = -1, nu - 1 do
    for j = -1, nv - 1 do
      -- corners a (i, j), b (i+1, j), c (i+1, j+1), d (i, j+1); crossing points on the
      -- edges whose two corners differ, in order ab, bc, cd, da
      local a, b, c, d = at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)
      local pts = {}
      if a ~= b then pts[#pts + 1] = { i + 0.5, j } end
      if b ~= c then pts[#pts + 1] = { i + 1, j + 0.5 } end
      if c ~= d then pts[#pts + 1] = { i + 0.5, j + 1 } end
      if d ~= a then pts[#pts + 1] = { i, j + 0.5 } end
      for k = 1, #pts - 1, 2 do
        local p, q = pts[k], pts[k + 1]
        out[#out + 1], out[#out + 2], out[#out + 3], out[#out + 4] = p[1], p[2], q[1], q[2]
      end
    end
  end
  return out
end

-- The inside of a sampled shape as world rectangles (asked 2026-10-08: a faint fill in each quest area, so being inside
-- one shows at any zoom): each row's runs of inside samples, a run carried on down the rows while it stays the same
-- (few rectangles: a circle 40 samples across is about 40). inside(i, j) as for Outline; toWorld(u, v) gives the world
-- (x, y) of grid point (u, v) (sample i spans u = i .. i + 1). Flat { x1, y1, x2, y2, ... } (each rectangle's two
-- corners, x1 <= x2, y1 <= y2), or nil when empty.
function Lay.FillRects(inside, nu, nv, toWorld)
  local out, open = {}, {} -- (open: [i0 .. ":" .. i1] = { i0, i1, j0 } still going)
  local function close(r, j1)
    local xa, ya = toWorld(r[1], r[3])
    local xb, yb = toWorld(r[2] + 1, j1)
    if xa and xb then
      out[#out + 1], out[#out + 2] = math.min(xa, xb), math.min(ya, yb)
      out[#out + 1], out[#out + 2] = math.max(xa, xb), math.max(ya, yb)
    end
  end
  for j = 0, nv do
    local now = {}
    if j < nv then
      local i = 0
      while i < nu do
        if inside(i, j) then
          local i0 = i
          while i + 1 < nu and inside(i + 1, j) do i = i + 1 end
          now[i0 .. ":" .. i] = { i0, i }
        end
        i = i + 1
      end
    end
    for k, r in pairs(open) do
      if not now[k] then
        close(r, j)
        open[k] = nil
      end
    end
    for k, r in pairs(now) do
      if not open[k] then open[k] = { r[1], r[2], j } end
    end
  end
  return #out > 0 and out or nil
end

-- Douglas-Peucker: the points of polyline `pts` needed to stay within `eps` of it.
local function Simplify(pts, eps)
  local n = #pts
  if n < 3 then return pts end
  local keep = { [1] = true, [n] = true }
  local stack = { { 1, n } }
  while #stack > 0 do
    local seg = table.remove(stack)
    local i0, i1 = seg[1], seg[2]
    local a, b = pts[i0], pts[i1]
    local vx, vy = b[1] - a[1], b[2] - a[2]
    local L2 = vx * vx + vy * vy
    local best, bi = -1, nil
    for i = i0 + 1, i1 - 1 do
      local p = pts[i]
      local d
      if L2 == 0 then
        d = (p[1] - a[1]) ^ 2 + (p[2] - a[2]) ^ 2
      else
        local cross = (p[1] - a[1]) * vy - (p[2] - a[2]) * vx
        d = cross * cross / L2
      end
      if d > best then best, bi = d, i end
    end
    if bi and best > eps * eps then
      keep[bi] = true
      stack[#stack + 1] = { i0, bi }
      stack[#stack + 1] = { bi, i1 }
    end
  end
  local out = {}
  for i = 1, n do if keep[i] then out[#out + 1] = pts[i] end end
  return out
end

-- Join outline segments into loops and round them off (Chaikin corner cutting, `rounds`
-- times), so a grid-traced outline doesn't look like stairs. Returns segments again.
function Lay.Smooth(segs, rounds)
  local function key(x, y) return string.format("%.3f,%.3f", x, y) end
  local nbr, pos = {}, {}
  for k = 1, #segs - 3, 4 do
    local a, b = key(segs[k], segs[k + 1]), key(segs[k + 2], segs[k + 3])
    pos[a], pos[b] = { segs[k], segs[k + 1] }, { segs[k + 2], segs[k + 3] }
    nbr[a] = nbr[a] or {}
    nbr[b] = nbr[b] or {}
    table.insert(nbr[a], b)
    table.insert(nbr[b], a)
  end
  local used, out = {}, {}
  local function edgeKey(a, b) return a < b and (a .. "|" .. b) or (b .. "|" .. a) end
  for start in pairs(nbr) do
    for _, first in ipairs(nbr[start]) do
      if not used[edgeKey(start, first)] then
        -- walk a loop (or an open chain) from start
        local chain, prev, cur = { pos[start] }, start, first
        used[edgeKey(start, first)] = true
        local closed = false
        while true do
          chain[#chain + 1] = pos[cur]
          if cur == start then
            closed = true
            break
          end
          local nxt
          for _, n in ipairs(nbr[cur]) do
            if not used[edgeKey(cur, n)] then nxt = n break end
          end
          if not nxt then break end
          used[edgeKey(cur, nxt)] = true
          prev, cur = cur, nxt
        end
        local pts = chain
        if closed then table.remove(pts) end -- last == first
        for _ = 1, rounds do
          local n = #pts
          if n < 3 then break end
          local nxtPts = {}
          local last = closed and n or n - 1
          if not closed then nxtPts[1] = pts[1] end
          for i = 1, last do
            local p, q = pts[i], pts[i % n + 1]
            nxtPts[#nxtPts + 1] = { 0.75 * p[1] + 0.25 * q[1], 0.75 * p[2] + 0.25 * q[2] }
            nxtPts[#nxtPts + 1] = { 0.25 * p[1] + 0.75 * q[1], 0.25 * p[2] + 0.75 * q[2] }
          end
          if not closed then nxtPts[#nxtPts + 1] = pts[n] end
          pts = nxtPts
        end
        -- drop points that barely bend the line (keeps drawing cheap)
        if closed and #pts > 3 then pts[#pts + 1] = pts[1] end -- simplify as an open chain
        pts = Simplify(pts, Lay.AREA_SIMPLIFY)
        if closed and #pts > 3 then table.remove(pts) end
        local n = #pts
        for i = 1, closed and n or n - 1 do
          local p, q = pts[i], pts[i % n + 1]
          out[#out + 1], out[#out + 2], out[#out + 3], out[#out + 4] = p[1], p[2], q[1], q[2]
        end
      end
    end
  end
  return out
end

local poiFrame
local function POIHit(mapID, questID, u, v)
  if not poiFrame then
    poiFrame = CreateFrame("QuestPOIFrame", nil, UIParent)
    poiFrame:SetSize(2048, 2048) -- the shape may be rasterised at the frame's size
    poiFrame:SetPoint("CENTER")
    poiFrame:SetAlpha(0)
    if poiFrame.SetFillAlpha then poiFrame:SetFillAlpha(0) end
    if poiFrame.SetBorderAlpha then poiFrame:SetBorderAlpha(0) end
    poiFrame:EnableMouse(false)
  end
  if poiFrame.map ~= mapID then
    poiFrame:SetMapID(mapID)
    poiFrame.map, poiFrame.drawn = mapID, nil
  end
  if poiFrame.drawn ~= questID then
    poiFrame:DrawNone()
    poiFrame:DrawBlob(questID, true)
    poiFrame.drawn = questID
  end
  local r = poiFrame:UpdateMouseOverTooltip(u, v)
  return r == questID or r == true
end

-- Ways to ask "is (u, v) on map `mapID` inside quest `q`'s area?"; the first that answers
-- sensibly (inside at a quest's map icon, outside far away) is used.
local HITTERS = {
  { "IsInsideQuestBlob(q, u, v)", function(m, q, u, v) return C_Minimap.IsInsideQuestBlob(q, u, v) end },
  { "IsInsideQuestBlob(q, x, y)", function(m, q, u, v)
    local x, y = Lay.MapToWorld(m, u, v)
    return x and C_Minimap.IsInsideQuestBlob(q, x, y)
  end },
  { "QuestPOIFrame", POIHit },
}
local hitter -- chosen HITTERS entry (retried every 30 s until one works)
Lay.hitterName = nil

-- Inside: true, false, or nil when the game hides the answer (a secret value, in combat): no answer, not "outside"
-- (read as outside, a trace then came out empty or with holes, and stayed so: an area that didn't draw in the live
-- game, 2026-10-08)
local function Hit(h, m, q, u, v)
  local ok, r = pcall(h[2], m, q, u, v)
  if ok and ns.IsSecret and ns.IsSecret(r) then return nil end
  return ok and r and true or false
end
Lay.HIDDEN_WAIT = 1 -- seconds: tracing waits this long after a hidden answer

-- In combat the game hides what the hit tests return (secret values): every spot would
-- read as outside, and areas traced then would come out empty. Tracing (and choosing the
-- hit test) waits until combat ends; areas already traced keep working (QuestsAt uses the
-- outlines, not the game).
local function InCombat()
  return InCombatLockdown and InCombatLockdown() or false
end

-- The game only loads quest area shapes for "the map the quest POIs are for" (what the
-- world map last showed). Tracing points it at the job's map (not while the world map is
-- open on another map) and puts it back when the queue is done: switching it is not cheap,
-- so it happens once per job, not every frame.
local poiPrev -- the map to restore, while switched
local function UsePOIMap(mapID)
  local Q = C_QuestLog
  if not (Q.SetMapForQuestPOIs and Q.GetMapForQuestPOIs) then return true end
  local cur = Q.GetMapForQuestPOIs()
  if cur == mapID then return true end
  if WorldMapFrame and WorldMapFrame:IsShown() then return false end -- don't fight the open map
  if poiPrev == nil then poiPrev = cur or false end
  Q.SetMapForQuestPOIs(mapID)
  return true
end

local function RestorePOIMap()
  if poiPrev ~= nil then
    if poiPrev and C_QuestLog.SetMapForQuestPOIs then C_QuestLog.SetMapForQuestPOIs(poiPrev) end
    poiPrev = nil
  end
end

local function WithPOIMap(mapID, fn, ...)
  UsePOIMap(mapID)
  local ok, a, b = pcall(fn, ...)
  RestorePOIMap()
  if not ok then error(a, 0) end
  return a, b
end

-- The quests in the log (not headers): { questID, ... }.
function Lay.LogQuests()
  local Q, out = C_QuestLog, {}
  if not (Q and Q.GetNumQuestLogEntries and Q.GetInfo) then return out end
  for i = 1, (Q.GetNumQuestLogEntries()) or 0 do
    local info = Q.GetInfo(i)
    if info and not info.isHeader and info.questID and info.questID > 0 then out[#out + 1] = info.questID end
  end
  return out
end

-- A way that answers sensibly: inside somewhere on the map for one of the quests (at its
-- icon, or anywhere on a rough grid: an icon needn't be inside its area), and outside at
-- the far corner from there. L.hitterNote says what was tried (for /agps debug).
Lay.HITTER_GRID = 16
Lay.HITTER_QUESTS = 8
-- Stops for the quest log (the quest route button): each open quest's objective spot and
-- each finished quest's turn-in, from the maps' quest pins (the map you're on first, then
-- every zone), else the quest's next waypoint. Returns stops { x, y, cont, name } and
-- { todo = n, turnin = n, missing = { title, ... } }.
-- The zone a map is in (a city's: the zone around it), for "only this zone".
function Lay.ZoneOf(id)
  local m = id and ns.Maps and ns.Maps[id]
  if m and m.zoneParent then return m.zoneParent end
  return id
end

-- `onlyZone`: just the quests whose spot is in the zone the player is in (counts.elsewhere:
-- how many were left out).
function Lay.QuestStops(onlyZone)
  local Q = C_QuestLog
  local out, placed = {}, {}
  local counts = { todo = 0, turnin = 0, missing = {}, elsewhere = 0 }
  local myZone = onlyZone and Lay.ZoneOf(C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player"))
  if not Q then return out, counts end
  local wanted = {}
  for _, id in ipairs(Lay.LogQuests()) do wanted[id] = true end
  local function secret(v) return ns.IsSecret and ns.IsSecret(v) end
  -- (the city levels' own maps: a pin there is down in the city)
  local cityMap = {}
  for lc, l in pairs(ns.CityLevels or {}) do if l.map then cityMap[l.map] = lc end end
  local function add(id, mapID, u, v)
    local x, y, cont = Lay.MapToWorld(mapID, u, v)
    if not x or secret(x) then return end
    if cityMap[mapID] and Lay.CityLevelAt(cont, x, y) == cityMap[mapID] then cont = cityMap[mapID] end
    if myZone then
      -- (the zone the ground there is in, Data/Zones.lua; zones' map outlines overlap: by them a
      -- Tirisfal spot by its eastern edge could be in Western Plaguelands)
      local R = ns.Router
      local at = R and R.ZoneAt and R.ZoneAt(Geo.Base(cont), x, y) or 0
      if at == 0 then at = ns.GPS and ns.GPS.LocateWorld and ns.GPS.LocateWorld(Geo.Base(cont), x, y) end
      if Lay.ZoneOf(at) ~= myZone then
        placed[id] = true -- (found, just not here)
        counts.elsewhere = counts.elsewhere + 1
        return
      end
    end
    local complete = Q.IsComplete and Q.IsComplete(id)
    if secret(complete) then complete = false end
    local title = QuestTitle(id) or string.format(L["Quest %d"], id)
    -- (its quest, asked 2026-10-06: done by the quest, not by getting there; Nav.QuestStopDone)
    out[#out + 1] = { x = x, y = y, cont = cont, name = complete and string.format(L["Turn in: %s"], title) or title, questRoute = true,
      quest = id, turnin = complete and true or nil, z = (ns.Nav and ns.Nav.SpawnZ and ns.Nav.SpawnZ(cont, x, y)) or Lay.QuestNpcZ(id, cont, x, y), -- (its NPC's floor, if known)
      parts = not complete and Lay.QuestAreaSpots(id) or nil } -- (its area's other parts: Nav.OrderStops picks one)
    placed[id] = true
    if complete then counts.turnin = counts.turnin + 1 else counts.todo = counts.todo + 1 end
  end
  local maps = {}
  local here = C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
  for id, m in pairs(ns.Maps or {}) do
    if m.type == 3 and m.bounds and id ~= here then maps[#maps + 1] = id end
  end
  -- (the map you're on first, then cities' own maps: a quest in a city is found there
  -- before on the zone around it, which can't tell the city from the ground above it)
  table.sort(maps, function(a, b)
    local ca, cb = cityMap[a] and 0 or 1, cityMap[b] and 0 or 1
    if ca ~= cb then return ca < cb end
    return a < b
  end)
  -- (the map you're on next, after the cities' own; asked 2026-10-06: up in Tirisfal, Undercity's quests were found on
  -- Tirisfal's map first, their stops up on the surface over the NPCs, and the route led there, outside the city)
  if here and ns.Maps and ns.Maps[here] and not cityMap[here] then
    local at = 1
    while maps[at] and cityMap[maps[at]] do at = at + 1 end
    table.insert(maps, at, here)
  elseif here and cityMap[here] then
    table.insert(maps, 1, here) -- (in a city: its own map first, as before)
  end
  if Q.GetQuestsOnMap then
    for _, mapID in ipairs(maps) do
      UsePOIMap(mapID)
      for _, q in ipairs(Q.GetQuestsOnMap(mapID) or {}) do
        if wanted[q.questID] and not placed[q.questID] and q.x and not secret(q.x) then add(q.questID, mapID, q.x, q.y) end
      end
    end
    RestorePOIMap()
  end
  for _, id in ipairs(Lay.LogQuests()) do
    if not placed[id] and Q.GetNextWaypoint then
      local mapID, u, v = Q.GetNextWaypoint(id)
      if mapID and u and v and ns.Maps and ns.Maps[mapID] then add(id, mapID, u, v) end
    end
    if not placed[id] then counts.missing[#counts.missing + 1] = QuestTitle(id) or string.format(L["Quest %d"], id) end
  end
  return out, counts
end

local function ChooseHitter(mapID, quests)
  return WithPOIMap(mapID, function()
    local G = Lay.HITTER_GRID
    for _, h in ipairs(HITTERS) do
      for n, q in ipairs(quests) do
        if n > Lay.HITTER_QUESTS then break end
        local spots = {}
        if q.x then spots[1] = { q.x, q.y } end
        for k = 0, G * G - 1 do spots[#spots + 1] = { (k % G + 0.5) / G, (math.floor(k / G) + 0.5) / G } end
        for _, sp in ipairs(spots) do
          local u, v = sp[1], sp[2]
          if Hit(h, mapID, q.questID, u, v) then
            if not Hit(h, mapID, q.questID, u > 0.5 and 0.01 or 0.99, v > 0.5 and 0.01 or 0.99) then
              Lay.hitterName = h[1]
              Lay.hitterNote = string.format("chosen on map %d with quest %d", mapID, q.questID)
              return h
            end
            break -- inside everywhere: not a real answer, next quest
          end
        end
      end
    end
    Lay.hitterNote = string.format("none answered on map %d (%d quests, %s)", mapID, #quests,
      InCombat() and "in combat" or "out of combat")
  end)
end

Lay.AREA_VERSION = 3 -- bump to retrace cached areas after changing the tracer
-- Small areas (a circle of a few dozen yards) can fall between the coarse samples: then
-- the ground around the quest's map icon and around the player is sampled closely, and a
-- quest with no area found is looked for again around the player every AREA_EMPTY_RETRY s.
Lay.AREA_LOCAL_CELLS = 3 -- coarse cells each way around the icon / the player
Lay.AREA_LOCAL_SUB = 5 -- samples per coarse cell there
Lay.AREA_EMPTY_RETRY = 60

-- The player's spot on uiMap `mapID` (u, v in 0..1), or nil when not on it.
local function PlayerUV(mapID)
  local pos = C_Map.GetPlayerMapPosition and C_Map.GetPlayerMapPosition(mapID, "player")
  if not pos then return nil end
  local u, v
  if pos.GetXY then u, v = pos:GetXY() else u, v = pos.x, pos.y end
  if u and v and u > 0 and u < 1 and v > 0 and v < 1 then return u, v end
end
Lay.PlayerUV = PlayerUV
local areas = {} -- ["map:quest"] = { sig, cont, segs = { x1, y1, x2, y2, ... } world } (segs nil while tracing)
local jobs = {} -- queue of { key, map, quest, sig, phase, ... }

local function ObjectivesSig(questID)
  local parts = { Lay.AREA_VERSION }
  local list = C_QuestLog.GetQuestObjectives and C_QuestLog.GetQuestObjectives(questID)
  for _, o in ipairs(list or {}) do parts[#parts + 1] = o.finished and "1" or "0" end
  return table.concat(parts)
end

-- One step of the current tracing job, within the time budget. Returns true while busy.
local function TraceStep(deadline, now)
  local job = jobs[1]
  if not job then return false end
  local h = hitter
  local function done(segs, cont, fill)
    -- bounding box, so areas out of view are skipped without looking at their segments
    local bb
    for k = 1, #segs - 1, 2 do
      local x, y = segs[k], segs[k + 1]
      if not bb then bb = { x, y, x, y } else
        bb[1], bb[2], bb[3], bb[4] = math.min(bb[1], x), math.min(bb[2], y), math.max(bb[3], x), math.max(bb[4], y)
      end
    end
    areas[job.key] = { sig = job.sig, cont = cont, segs = segs, bbox = bb, fill = fill,
      emptyAt = #segs == 0 and GetTime() or nil }
    Lay.version = Lay.version + 1 -- something new to draw
    table.remove(jobs, 1)
  end
  -- the fine grid: the found box plus a margin, sampled every AREA_STEP_YD
  local function Fine()
    local N = Lay.AREA_COARSE
    local P = Lay.AREA_PAD
    job.fu0, job.fu1 = math.max(0, (job.u0 - P) / N), math.min(1, (job.u1 + 1 + P) / N)
    job.fv0, job.fv1 = math.max(0, (job.v0 - P) / N), math.min(1, (job.v1 + 1 + P) / N)
    local b = ns.Maps[job.map].bounds
    local function count(span, yards)
      return math.max(Lay.AREA_FINE_MIN, math.min(Lay.AREA_FINE_MAX, math.ceil(span * yards / Lay.AREA_STEP_YD)))
    end
    job.mu = count(job.fu1 - job.fu0, b[4] - b[2]) -- u runs east-west (world Y)
    job.mv = count(job.fv1 - job.fv0, b[3] - b[1]) -- v runs north-south (world X)
    job.phase, job.k, job.grid = "fine", 0, {}
  end
  -- close look around the icon and the player (small areas the coarse pass stepped over)
  if job.phase == "local" then
    local N = Lay.AREA_COARSE
    local M = 2 * Lay.AREA_LOCAL_CELLS * Lay.AREA_LOCAL_SUB
    if not job.centers then
      job.centers = {}
      if job.px and not job.nearPlayerOnly then job.centers[#job.centers + 1] = { job.px, job.py } end
      local pu, pv = PlayerUV(job.map)
      if pu then job.centers[#job.centers + 1] = { pu, pv } end
      job.k = 0
    end
    while job.k < #job.centers * M * M do
      local c = job.centers[math.floor(job.k / (M * M)) + 1]
      local r = job.k % (M * M)
      local u = c[1] + ((r % M + 0.5) / M * 2 - 1) * Lay.AREA_LOCAL_CELLS / N
      local v = c[2] + ((math.floor(r / M) + 0.5) / M * 2 - 1) * Lay.AREA_LOCAL_CELLS / N
      local hit = u > 0 and u < 1 and v > 0 and v < 1 and Hit(h, job.map, job.quest, u, v)
      if hit == nil then return "hidden" end -- (asked again later, this sample too)
      job.k = job.k + 1
      if hit then
        local ci, cj = math.floor(u * N), math.floor(v * N)
        job.u0, job.u1, job.v0, job.v1 = ci, ci, cj, cj
        Fine()
        return true
      end
      if now() > deadline then return true end
    end
    done({}, nil)
    return true
  end
  if job.phase == "coarse" then
    local N = Lay.AREA_COARSE
    while job.k < N * N do
      local i, j = job.k % N, math.floor(job.k / N)
      local hit = Hit(h, job.map, job.quest, (i + 0.5) / N, (j + 0.5) / N)
      if hit == nil then return "hidden" end
      if hit then
        job.u0, job.u1 = math.min(job.u0 or i, i), math.max(job.u1 or i, i)
        job.v0, job.v1 = math.min(job.v0 or j, j), math.max(job.v1 or j, j)
      end
      job.k = job.k + 1
      if now() > deadline then return true end
    end
    if not job.u0 then
      -- too small for the coarse grid? look closely around the quest's icon and the player
      local hit = job.px and Hit(h, job.map, job.quest, job.px, job.py)
      if hit == nil and job.px then return "hidden" end
      if hit then
        local ci, cj = math.floor(job.px * N), math.floor(job.py * N)
        job.u0, job.u1, job.v0, job.v1 = ci, ci, cj, cj
      else
        job.phase = "local"
        return true
      end
    end
    Fine()
    return true
  end
  local MU, MV = job.mu, job.mv
  local du, dv = (job.fu1 - job.fu0) / MU, (job.fv1 - job.fv0) / MV
  while job.k < MU * MV do
    local i, j = job.k % MU, math.floor(job.k / MU)
    local hit = Hit(h, job.map, job.quest, job.fu0 + (i + 0.5) * du, job.fv0 + (j + 0.5) * dv)
    if hit == nil then return "hidden" end
    job.grid[job.k] = hit
    job.k = job.k + 1
    if now() > deadline then return true end
  end
  local g = job.grid
  local raw = Lay.Smooth(Lay.Outline(function(i, j) return g[j * MU + i] end, MU, MV), Lay.AREA_SMOOTH)
  local segs, cont = {}, nil
  for k = 1, #raw, 2 do
    local x, y, c = Lay.MapToWorld(job.map, job.fu0 + (raw[k] + 0.5) * du, job.fv0 + (raw[k + 1] + 0.5) * dv)
    segs[k], segs[k + 1], cont = x, y, c
  end
  done(segs, cont, Lay.FillRects(function(i, j) return g[j * MU + i] end, MU, MV, function(u, v)
    return Lay.MapToWorld(job.map, job.fu0 + u * du, job.fv0 + v * dv)
  end))
  return true
end

-- Finish every queued trace now (tests, /agps debug).
function Lay.TraceAll()
  if not hitter then return end
  while jobs[1] do
    UsePOIMap(jobs[1].map)
    if TraceStep(math.huge, function() return 0 end) == "hidden" then break end
  end
  RestorePOIMap()
end

-- Called every frame (Init): trace in the background, a couple of milliseconds a frame.
local function OnUpdate()
  if not hitter or not jobs[1] then
    RestorePOIMap()
    return
  end
  if InCombat() then return end -- see InCombat
  if Lay.hiddenAt and GetTime() - Lay.hiddenAt < Lay.HIDDEN_WAIT then return end -- (hidden still: a moment)
  if not UsePOIMap(jobs[1].map) then return end -- wait until the world map closes
  local now = debugprofilestop
  local t0 = now()
  local deadline = t0 + Lay.AREA_BUDGET_MS
  while jobs[1] and now() < deadline do
    local map = jobs[1].map
    if TraceStep(deadline, now) == "hidden" then
      Lay.hiddenAt = GetTime()
      break
    end
    if jobs[1] and jobs[1].map ~= map and not UsePOIMap(jobs[1].map) then break end
  end
  if ns.PerfEnd then ns.PerfEnd("quest area tracing", t0) end
end

-- Whether (x, y) is inside a traced outline (flat segments x1, y1, x2, y2, ...): even-odd
-- rule, counting the outline's crossings of a ray going +Y from the point.
function Lay.InsideOutline(segs, x, y)
  local inside = false
  for k = 1, #segs - 3, 4 do
    local x1, y1, x2, y2 = segs[k], segs[k + 1], segs[k + 2], segs[k + 3]
    if (x1 > x) ~= (x2 > x) then
      local yc = y1 + (x - x1) / (x2 - x1) * (y2 - y1)
      if yc > y then inside = not inside end
    end
  end
  return inside
end

-- Whether quest `questID`'s traced area contains (x, y) on continent `cont`.
function Lay.AreaContains(questID, cont, x, y)
  local a = areas["q:" .. questID]
  if not (a and a.segs and a.cont and #a.segs > 0) then return false end
  local qx, qy = Geo.ToContinent(cont, x, y, a.cont)
  return qx ~= nil and Lay.InsideOutline(a.segs, qx, qy)
end

-- A quest's area in separate parts (asked 2026-11-07: Quest Route led to the north one while the same quest's area
-- was also by another quest's stop, the better way round): a spot inside each part, the parts at least AREA_PART_GAP
-- yards apart (from the traced areas' fill rectangles: those touching, or closer than that, are one part; the spot
-- the middle of the part's largest rectangle, so inside it). { { x, y, cont }, ... } biggest part first; nil for an
-- area in one part, or none traced yet.
Lay.AREA_PART_GAP = 40
function Lay.QuestAreaSpots(questID)
  local rects = {}
  for key, a in pairs(areas) do
    if a.fill and a.cont and key:match(":(%d+)$") == tostring(questID) then
      for k = 1, #a.fill - 3, 4 do
        rects[#rects + 1] = { a.fill[k], a.fill[k + 1], a.fill[k + 2], a.fill[k + 3], a.cont }
      end
    end
  end
  return Lay.AreaParts(rects)
end
-- The parts of an area from its fill rectangles { { x1, y1, x2, y2, cont }, ... }, as QuestAreaSpots
function Lay.AreaParts(rects)
  if #rects < 2 then return nil end
  local g = Lay.AREA_PART_GAP
  local part, n = {}, 0
  for i = 1, #rects do
    if not part[i] then
      n = n + 1
      part[i] = n
      local stack = { i }
      while #stack > 0 do
        local a = rects[table.remove(stack)]
        for j = 1, #rects do
          local b = rects[j]
          if not part[j] and b[5] == a[5] and b[1] <= a[3] + g and a[1] <= b[3] + g and b[2] <= a[4] + g
            and a[2] <= b[4] + g then
            part[j] = n
            stack[#stack + 1] = j
          end
        end
      end
    end
  end
  if n < 2 then return nil end
  local best, size = {}, {}
  for i, r in ipairs(rects) do
    local p, area = part[i], (r[3] - r[1]) * (r[4] - r[2])
    size[p] = (size[p] or 0) + area
    if not best[p] or area > best[p][2] then best[p] = { r, area } end
  end
  local out = {}
  for p = 1, n do
    local r = best[p][1]
    out[#out + 1] = { x = (r[1] + r[3]) / 2, y = (r[2] + r[4]) / 2, cont = r[5], size = size[p] }
  end
  table.sort(out, function(a, b) return a.size > b.size end)
  return out
end

-- Quests whose traced area contains (x, y) on continent `cont` (the maps' areas as
-- drawn): { questID, ... }. Uses the outlines, so it costs no game calls.
function Lay.QuestsAt(cont, x, y)
  local out, seen = {}, {}
  for key, a in pairs(areas) do
    if a.segs and a.cont and #a.segs > 0 then
      local qx, qy = Geo.ToContinent(cont, x, y, a.cont)
      local questID = tonumber(key:match(":(%d+)$"))
      local Q = C_QuestLog
      local active = questID and not (Q.IsComplete and Q.IsComplete(questID))
        and not (Q.IsOnQuest and not Q.IsOnQuest(questID)) -- finished or abandoned: not drawn either
      if qx and active and not seen[questID] and Lay.InsideOutline(a.segs, qx, qy) then
        seen[questID] = true
        out[#out + 1] = questID
      end
    end
  end
  return out
end

-- A quest's title and objectives: title, { { text, finished }, ... } (text as the quest
-- log shows it, e.g. "Vile Familiar slain: 3/8").
function Lay.QuestObjectives(questID)
  local out = {}
  local list = C_QuestLog.GetQuestObjectives and C_QuestLog.GetQuestObjectives(questID)
  for _, o in ipairs(list or {}) do
    if o.text and o.text ~= "" then out[#out + 1] = { text = o.text, finished = o.finished and true or false } end
  end
  return QuestTitle(questID), out
end

-- Add a quest to a tooltip like the minimap does: title, then its objectives.
function Lay.AddQuestToTooltip(tip, questID)
  tip:AddLine(QuestTitle(questID) or string.format(L["Quest %d"], questID), 1, 0.82, 0)
  local list = C_QuestLog.GetQuestObjectives and C_QuestLog.GetQuestObjectives(questID)
  for _, o in ipairs(list or {}) do
    if o.text and o.text ~= "" then
      if o.finished then tip:AddLine("- " .. o.text, 0.5, 0.5, 0.5) else tip:AddLine("- " .. o.text, 1, 1, 1) end
    end
  end
end

Lay.AREA_LIST_TTL = 2 -- seconds
local areaLists = {} -- [mapID] = { t, quests } (cleared on quest log changes)

-- Quest area outlines near (cx, cy) on `cont`: flat { x1, y1, x2, y2, ... } in `cont`
-- coordinates. Starts tracing areas not known yet.
function Lay.Areas(cont, cx, cy, reach, mapIDs)
  local out = {}
  Lay.EachArea(cont, cx, cy, reach, mapIDs, function(x1, y1, x2, y2)
    out[#out + 1], out[#out + 2], out[#out + 3], out[#out + 4] = x1, y1, x2, y2
  end)
  return out
end

-- Same, calling fn(x1, y1, x2, y2) per outline segment (no tables: called every redraw), and `fillFn(x1, y1, x2, y2)`,
-- when given, per rectangle of each area's inside (L.FillRects: two opposite corners) near the view.
function Lay.EachArea(cont, cx, cy, reach, mapIDs, fn, fillFn)
  local Q = C_QuestLog
  if not (Q and Q.GetQuestsOnMap) then return end
  local seenMap = {}
  for _, mapID in ipairs(mapIDs) do
    if mapID and not seenMap[mapID] and ns.Maps and ns.Maps[mapID] then
      seenMap[mapID] = true
      -- the map's open quests and their objective state, refreshed every AREA_LIST_TTL
      local c = areaLists[mapID]
      if not c or GetTime() - c.t > Lay.AREA_LIST_TTL then
        c = { t = GetTime(), quests = {} }
        local listed = {}
        for _, q in ipairs(Q.GetQuestsOnMap(mapID) or {}) do
          listed[q.questID] = true
          if not (Q.IsComplete and Q.IsComplete(q.questID)) then
            q.sig = ObjectivesSig(q.questID)
            c.quests[#c.quests + 1] = q
          end
        end
        -- the log's other open quests too: an area can be on this map without the quest's
        -- icon being here (e.g. "enter the Dead Fields"); no icon, so they're looked for
        -- over the whole map, then closely around the player
        for _, id in ipairs(Lay.LogQuests()) do
          if not listed[id] and not (Q.IsComplete and Q.IsComplete(id)) then
            c.quests[#c.quests + 1] = { questID = id, sig = ObjectivesSig(id) }
          end
        end
        areaLists[mapID] = c
      end
      local quests = c.quests
      if not hitter and #quests > 0 and GetTime() - (Lay.hitterTried or -100) > 30 and not InCombat() then
        Lay.hitterTried = GetTime()
        hitter = ChooseHitter(mapID, quests)
      end
      if hitter then
        for _, q in ipairs(quests) do
          -- per quest, not per map: outlines are in world coordinates, so one traced on
          -- another map (the zone, a city) is drawn right away here too
          local key = "q:" .. q.questID
          local sig = q.sig
          local a = areas[key]
          local retry = a and a.emptyAt and not a.tracing and GetTime() - a.emptyAt > Lay.AREA_EMPTY_RETRY
          if retry then
            -- none found yet: look again around where the player is now (close look only)
            a.tracing = true
            jobs[#jobs + 1] = { key = key, map = mapID, quest = q.questID, sig = sig, phase = "local", k = 0,
              nearPlayerOnly = true }
          elseif not a or a.sig ~= sig then
            if not (a and a.tracing) then
              -- re-traced in the background: the old outline stays drawn until then (all of it,
              -- its bounding box too, or it wouldn't be drawn at all)
              areas[key] = { sig = sig, tracing = true, segs = a and a.segs, cont = a and a.cont, bbox = a and a.bbox,
                fill = a and a.fill }
              jobs[#jobs + 1] = { key = key, map = mapID, quest = q.questID, sig = sig, phase = "coarse", k = 0,
                px = q.x, py = q.y }
            end
          end
          a = areas[key]
          local segs, bb = a and a.segs, a and a.bbox
          local fill = fillFn and a and a.fill
          if fill and a.cont then
            for k = 1, #fill - 3, 4 do
              local x1, y1, x2, y2 = fill[k], fill[k + 1], fill[k + 2], fill[k + 3]
              if a.cont ~= cont then
                x1, y1 = Geo.ToContinent(a.cont, x1, y1, cont)
                x2, y2 = Geo.ToContinent(a.cont, x2, y2, cont)
              end
              if x1 and x2 and x2 >= cx - reach and x1 <= cx + reach and y2 >= cy - reach and y1 <= cy + reach then
                fillFn(x1, y1, x2, y2)
              end
            end
          end
          if segs and a.cont and bb then
            if a.cont == cont then
              -- the usual case: no conversion; skip the whole area when it's out of view
              if bb[3] >= cx - reach and bb[1] <= cx + reach and bb[4] >= cy - reach and bb[2] <= cy + reach then
                for k = 1, #segs - 3, 4 do
                  local x1, y1 = segs[k], segs[k + 1]
                  if math.abs(x1 - cx) <= reach and math.abs(y1 - cy) <= reach then
                    fn(x1, y1, segs[k + 2], segs[k + 3])
                  end
                end
              end
            else
              for k = 1, #segs - 3, 4 do
                local x1, y1 = Geo.ToContinent(a.cont, segs[k], segs[k + 1], cont)
                local x2, y2 = Geo.ToContinent(a.cont, segs[k + 2], segs[k + 3], cont)
                if x1 and x2 and math.abs(x1 - cx) <= reach and math.abs(y1 - cy) <= reach then fn(x1, y1, x2, y2) end
              end
            end
          end
        end
      end
    end
  end
end

---------------------------------------------------------------------------
-- What to draw
---------------------------------------------------------------------------

local nodeIcons = {} -- kind -> gathering spell icon
Lay.itemIcons = {} -- node name -> its item's icon (L.NODE_ITEMS), once the game gave it

-- The icons learned from what gathering gave (account-wide): { [node name] = { icon = file id or path, item = name } }.
local function LootIcons()
  local db = ns.db
  if not db then return nil end
  db.nodeItems = db.nodeItems or {}
  return db.nodeItems
end

-- A node's item icon (asked 2026-11-06): its item's bag icon (L.NODE_ITEMS), else the one learned from its loot, else
-- nil.
function Lay.NodeItemIcon(name)
  if not name then return nil end
  local icon = Lay.itemIcons[name]
  if icon then return icon end
  local id = Lay.NODE_ITEMS[name]
  if id then
    icon = (C_Item and C_Item.GetItemIconByID and C_Item.GetItemIconByID(id)) or (GetItemIcon and GetItemIcon(id))
    if icon then
      Lay.itemIcons[name] = icon
      return icon
    end
  end
  local learned = LootIcons()
  local e = learned and learned[name]
  return e and e.icon or nil
end

-- A node's icon: what gathering it gives (L.NodeItemIcon), else its kind's (the gathering spell's), or nil.
function Lay.NodeIcon(kind, name)
  local item = Lay.NodeItemIcon(name)
  if item then return item end
  local icon = nodeIcons[kind]
  if icon == nil then
    icon = SpellIcon(Lay.GATHER_SPELLS[kind]) or false
    nodeIcons[kind] = icon
  end
  return icon or nil
end

-- The loot window just after a gathering cast on node `name`: the first item in it is what that node gives, its icon
-- the node's on the map from now (account-wide, kept; for a node with no item in L.NODE_ITEMS: WoW Forever's own).
-- `slots` = { { icon, item name, quest item? }, ... } in the loot's order. Returns the icon learned, or nil.
function Lay.OnGatherLoot(name, slots)
  if not name or not Lay.NodeKind(name) or Lay.NODE_ITEMS[name] then return nil end
  local learned = LootIcons()
  if not learned or learned[name] then return nil end
  for _, s in ipairs(slots or {}) do
    local icon, item = s[1], s[2]
    if icon and not s[3] and (type(icon) == "number" or type(icon) == "string") then
      learned[name] = { icon = icon, item = type(item) == "string" and item or nil }
      Lay.version = Lay.version + 1
      if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
      return icon
    end
  end
  return nil
end

-- Marks near (cx, cy) on continent `cont`, within `reach` yards: { { x, y, icon, name, note,
-- size, r, g, b }, ... } in `cont` coordinates. mapIDs: uiMaps to ask for quests.
-- `level`: the player's level when the view is theirs (a city's own places, down in it,
-- show only while on that city's level). `questsOnly`: the quests' marks alone (the seamless map's world stage).
-- `shown` (optional): { quests, city, herbs, ore = false } leaves that kind out (GPSFrame's G.IconKinds: past the zoom it
-- shows out to, asked 2026-11-14)
function Lay.Marks(cont, cx, cy, reach, mapIDs, level, questsOnly, shown)
  local st = ns.settings.gps
  shown = shown or {}
  local out = {}
  local function near(x, y) return math.abs(x - cx) <= reach and math.abs(y - cy) <= reach end
  -- (`level`: the level a stop made from it is on: a city's places are down in it, wherever the
  -- floor data under them has a gap: a trainer's booth)
  -- (`z`: its height, the game's: a city place's, from its NPC; the floor, where they lie over each other)
  -- (`exact`: a game icon drawn at its exact size, GPSFrame's G.ICON_PX: the nodes' items)
  local function put(x, y, icon, name, note, size, r, g, b, questID, preview, level, z, city, exact)
    if #out < Lay.MAX_MARKS and near(x, y) then
      out[#out + 1] = { x, y, icon, name, note, size, r, g, b, questID, preview, level, z, city, exact }
    end
  end
  if st.layerQuests and shown.quests ~= false then
    local seen = {}
    for _, id in ipairs(mapIDs) do
      if id and not seen[id] then
        seen[id] = true
        for _, m in ipairs(QuestMarks(id, st)) do
          local x, y = Geo.ToContinent(m[3], m[1], m[2], cont)
          local kind = m[4]
          if x then
            if kind == "objective" and st.layerQuests then
              put(x, y, Lay.ICON.objective, m[5] or L["Quest objective"], L["Quest objective"], 16, nil, nil, nil, m[6])
            elseif kind == "turnin" and st.layerQuests then
              put(x, y, Lay.ICON.turnin, m[5] or L["Quest"], L["Ready to turn in"], 16, nil, nil, nil, m[6])
            end
          end
        end
      end
    end
  end
  if questsOnly then return out end
  -- (city locations on the terrain view only, not on the world map styles)
  if st.layerCity and shown.city ~= false and not (ns.GPS and ns.GPS.IsMapStyle and ns.GPS.IsMapStyle(ns.GPS.Style and ns.GPS.Style() or st.style)) then
    -- (and those down in its underground cities, saved on their levels, drawn here too)
    local saved = {}
    for lc, list in pairs(Lay.CityDB()) do
      if lc == cont or (lc == level and Geo.Base(lc) == cont) then
        for _, c in ipairs(list) do
          if not Lay.InHiddenCity(lc, c[1], c[2]) then -- (one in the other faction's city: not for this character)
            put(c[1], c[2], c[4] or Lay.CITY_DEFAULT_ICON, c[3], L["City location (a guard pointed it out)"], 16,
              nil, nil, nil, nil, nil, lc, Lay.PlaceZ(lc, c[1], c[2], c[3]), true)
            saved[#saved + 1] = c
          end
        end
      end
    end
    -- a city's other places, once a guard there has been talked to (not a stop until a
    -- guard is asked for it)
    for _, p in ipairs(Lay.RevealedPlaces(cont)) do
      local dup = p.cont ~= cont and p.cont ~= level -- (down in a city, the player elsewhere)
      for _, c in ipairs(saved) do
        if c[3] == p[3] or (c[1] - p[1]) ^ 2 + (c[2] - p[2]) ^ 2 <= Lay.CITY_SAME_YD ^ 2 then dup = true break end
      end
      if not dup then
        put(p[1], p[2], Lay.CityIcon(p[3]) or Lay.CITY_DEFAULT_ICON, Lay.PlaceLabel(p[3]), L["City location"], 16, nil, nil,
          nil, nil, true, p.cont, p.z, true)
      end
    end
  end
  local kinds = Lay.VisibleKinds(st)
  if shown.herbs == false or shown.ore == false then
    kinds = { herb = kinds.herb and shown.herbs ~= false, ore = kinds.ore and shown.ore ~= false }
  end
  if kinds.herb or kinds.ore then
    local db = DB()
    local filter = Lay.NodeFilter(st) -- (Find Herbs and Ore: only those picked)
    for _, n in ipairs(db and db[cont] or {}) do
      if Lay.NodeShown(n[3], n[4], st, kinds, filter) and Lay.IsNode(n) and near(n[1], n[2]) then
        -- (the item gathering it gives, else the gathering spell's: game icons, drawn at their exact size)
        local icon = Lay.NodeIcon(n[4], n[3])
        local ore = n[4] == "ore"
        if n[6] then
          put(n[1], n[2], icon or "Interface\\Icons\\INV_Misc_QuestionMark", n[3],
            ore and L["Mining node (imported, not confirmed yet: gather it to confirm)"]
              or L["Herb (imported, not confirmed yet: gather it to confirm)"], 16, 0.55, 0.55, 0.55, nil, nil, nil, nil, nil, true)
        else
          put(n[1], n[2], icon or "Interface\\Icons\\INV_Misc_QuestionMark", n[3], ore and L["Mining node"] or L["Herb"], 16, nil, nil, nil, nil, nil, nil, nil,
            nil, true)
        end
      end
    end
    for _, n in ipairs(Lay.demoNodes and Lay.demoNodes[cont] or {}) do -- (the tutorial's examples: in memory only)
      if kinds[n[4]] and near(n[1], n[2]) then
        put(n[1], n[2], Lay.NodeIcon(n[4], n[3]) or "Interface\\Icons\\INV_Misc_QuestionMark", n[3], L["Example for the tutorial"],
          16, nil, nil, nil, nil, nil, nil, nil, nil, true)
      end
    end
  end
  return out
end

---------------------------------------------------------------------------
-- City locations: what a guard points out when asked for directions ("Alchemy
-- Trainer", "Bank"): the game marks it on the map (a gossip point of interest). Each is
-- saved for all characters, drawn with a matching icon (layerCity), and made a stop.
---------------------------------------------------------------------------

Lay.CITY_DEFAULT_ICON = "Interface\\Icons\\INV_Misc_Map_01"
Lay.CITY_ICONS = { -- words in the name -> icon (the first that matches)
  { "alchem", "Interface\\Icons\\Trade_Alchemy" },
  { "blacksmith", "Interface\\Icons\\Trade_BlackSmithing" },
  { "cook", "Interface\\Icons\\INV_Misc_Food_15" },
  { "enchant", "Interface\\Icons\\Trade_Engraving" },
  { "engineer", "Interface\\Icons\\Trade_Engineering" },
  { "first aid", "Interface\\Icons\\Spell_Holy_SealOfSacrifice" },
  { "fish", "Interface\\Icons\\Trade_Fishing" },
  { "herbalis", "Interface\\Icons\\Trade_Herbalism" },
  { "leatherwork", "Interface\\Icons\\Trade_LeatherWorking" },
  { "mining", "Interface\\Icons\\Trade_Mining" },
  { "skinning", "Interface\\Icons\\INV_Misc_Pelt_Wolf_01" },
  { "tailor", "Interface\\Icons\\Trade_Tailoring" },
  { "bank", "Interface\\Icons\\INV_Misc_Bag_10_Blue" },
  { "auction", "Interface\\Icons\\INV_Misc_Coin_02" },
  { "mail", "Interface\\Icons\\INV_Letter_15" },
  { "inn", "Interface\\Icons\\INV_Drink_05" },
  { "flight", "Interface\\Icons\\Ability_Mount_Wyvern_01" },
  { "gryphon", "Interface\\Icons\\Ability_Mount_Wyvern_01" },
  { "wind rider", "Interface\\Icons\\Ability_Mount_Wyvern_01" },
  { "bat handler", "Interface\\Icons\\Ability_Mount_Wyvern_01" },
  { "hippogryph", "Interface\\Icons\\Ability_Mount_Wyvern_01" },
  { "stable", "Interface\\Icons\\Ability_Hunter_BeastTaming" },
  { "weapon", "Interface\\Icons\\INV_Sword_04" },
  { "battlemaster", "Interface\\Icons\\INV_Misc_Rune_07" },
  { "warrior", "Interface\\Icons\\INV_Sword_27" },
  { "paladin", "Interface\\Icons\\Spell_Holy_HolyBolt" },
  { "hunter", "Interface\\Icons\\INV_Weapon_Bow_07" },
  { "rogue", "Interface\\Icons\\INV_ThrowingKnife_04" },
  { "priest", "Interface\\Icons\\INV_Staff_30" },
  { "shaman", "Interface\\Icons\\Spell_Nature_BloodLust" },
  { "mage", "Interface\\Icons\\INV_Staff_13" },
  { "warlock", "Interface\\Icons\\Spell_Shadow_DeathCoil" },
  { "druid", "Interface\\Icons\\Ability_Druid_Maul" },
}
Lay.CITY_SAME_YD = 15 -- the same place again (same name, this close): updated, not added

function Lay.CityIcon(name)
  local n = (name or ""):lower()
  for _, e in ipairs(Lay.CITY_ICONS) do
    if n:find(e[1], 1, true) then return e[2] end
  end
  return Lay.CITY_DEFAULT_ICON
end

-- Saved city locations, for all characters: [cont] = { { x, y, name, icon }, ... }.
-- A city's places (Data/CityPlaces.lua) show once any character has talked to a guard in
-- that city (saved for the account). { {x, y, name}, ... } on `cont` (or its city levels).
local placeCache = {}
-- A shipped place's name as the map shows it, in the addon's language (GPS.PlaceName; asked 2026-11-12 for the
-- search): "Orgrimmar Mining Trainer" is "Bergbaulehrer, Orgrimmar" in German, as it is in English.
function Lay.PlaceLabel(name)
  local G = ns.GPS
  if not (G and G.PlaceName) then return name end
  local shown, before = G.PlaceName(name)
  if shown == name then return name end
  return before and (shown .. ", " .. before) or shown
end

function Lay.RevealedPlaces(cont)
  local db = ns.db
  local out = {}
  if not (db and db.cityRevealed and ns.CityPlaces) then return out end
  for ui in pairs(db.cityRevealed) do
    local list = placeCache[ui]
    if list == nil then
      list = {}
      local c = ns.CityPlaces[ui]
      for _, p in ipairs(c or {}) do
        local x, y, pc = Lay.MapToWorld(ui, p[1] / 100, p[2] / 100)
        if x then
          pc = Lay.CityLevelAt(pc, x, y) or pc
          list[#list + 1] = { x, y, p[3], cont = pc, z = p[4] }
        end
      end
      -- (a starting zone's town: its places in world yards, ns.TownPlaces)
      local t = ns.TownPlaces and ns.TownPlaces[ui]
      for _, p in ipairs(t or {}) do list[#list + 1] = { p.x, p.y, p[1], cont = t.cont, z = p.z } end
      placeCache[ui] = list
    end
    local hidden = Lay.HiddenCity(ui) -- (the other faction's city: its places not shown to this character)
    for _, p in ipairs(list) do
      if not hidden and (p.cont == cont or Geo.Base(p.cont) == cont) then out[#out + 1] = p end
    end
  end
  return out
end
-- The cities and towns each faction's guards give directions in (CityPlaces' and TownPlaces' uiMaps): a character of
-- the other faction doesn't see the places learned there by one of this one (cityRevealed is account-wide), nor the
-- guards' places saved there (asked 2026-11-14: "If player has opposing faction character just hide the city guard
-- locations that get marked"; the NPCs inside the buildings there still show).
Lay.GUARD_CITY_SIDE = { [1453] = "A", [1455] = "A", [1457] = "A", [1429] = "A", [1426] = "A", [1438] = "A",
  [1454] = "H", [1456] = "H", [1458] = "H", [1420] = "H", [1412] = "H", [1411] = "H" }
Lay.GUARD_CITY_REACH = 120 -- yards past a hidden city's places a saved guard's place counts as in it
function Lay.HiddenCity(ui)
  local mine = ns.Nav and ns.Nav.Faction and ns.Nav.Faction()
  local side = Lay.GUARD_CITY_SIDE[ui]
  return mine ~= nil and side ~= nil and side ~= mine
end
-- whether (x, y) on level `cont` is in a city or town of the other faction (its places' box, GUARD_CITY_REACH round it)
function Lay.InHiddenCity(cont, x, y)
  local mine = ns.Nav and ns.Nav.Faction and ns.Nav.Faction()
  if not (mine and ns.CityPlaces) then return false end
  Lay.guardBoxes = Lay.guardBoxes or {}
  for ui, side in pairs(Lay.GUARD_CITY_SIDE) do
    if side ~= mine then
      local box = Lay.guardBoxes[ui]
      if box == nil then
        box = false
        local pts = {}
        for _, p in ipairs(ns.CityPlaces[ui] or {}) do
          local px, py, pc = Lay.MapToWorld(ui, p[1] / 100, p[2] / 100)
          if px then pts[#pts + 1] = { px, py, pc } end
        end
        local t = ns.TownPlaces and ns.TownPlaces[ui]
        for _, p in ipairs(t or {}) do pts[#pts + 1] = { p.x, p.y, t.cont } end
        for _, p in ipairs(pts) do
          if not box then box = { Geo.Base(p[3]), p[1], p[2], p[1], p[2] } end
          if Geo.Base(p[3]) == box[1] then
            box[2], box[3] = math.min(box[2], p[1]), math.min(box[3], p[2])
            box[4], box[5] = math.max(box[4], p[1]), math.max(box[5], p[2])
          end
        end
        Lay.guardBoxes[ui] = box
      end
      local r = Lay.GUARD_CITY_REACH
      if box and box[1] == Geo.Base(cont) and x >= box[2] - r and x <= box[4] + r and y >= box[3] - r
          and y <= box[5] + r then
        return true
      end
    end
  end
  return false
end

-- The capitals' factions (Data/CityPlaces.lua's uiMaps), for the search: only the player's own (asked 2026-10-03).
Lay.CITY_FACTION = { [1454] = "Horde", [1456] = "Horde", [1458] = "Horde",
  [1453] = "Alliance", [1455] = "Alliance", [1457] = "Alliance" }

-- The city places the player knows, for the search (asked 2026-10-03: "Inn Ir" finds Ironforge's inn): every place of
-- a city a guard there was talked to (L.RevealedPlaces), and the spots guards pointed out (L.CityDB), in the
-- player's faction's capitals. Each: { name ("Inn"), full ("Ironforge Inn", the stop's name), city, x, y, cont, z, icon }.
-- `all`: every capital's and town's places of their faction, guards talked to or not (the search, asked 2026-10-30:
-- "Rogue Trainer", "Skinning Trainer" without talking to a guard first; the map still shows them once one was).
function Lay.KnownPlaces(all)
  local side = UnitFactionGroup and UnitFactionGroup("player")
  local out, seen = {}, {}
  local function add(full, city, x, y, cont, z, icon, ui, faction)
    local f = faction or (ui and Lay.CITY_FACTION[ui])
    if f and side and f ~= side then return end
    local key = full:lower() .. ":" .. math.floor(x / 30) .. ":" .. math.floor(y / 30)
    if seen[key] then return end
    seen[key] = true
    local short = city and full:sub(1, #city + 1):lower() == (city .. " "):lower() and full:sub(#city + 2) or full
    out[#out + 1] = { name = short, full = full, city = city, x = x, y = y, cont = cont, z = z,
      icon = icon or Lay.CityIcon(full) or Lay.CITY_DEFAULT_ICON }
  end
  local db = ns.db
  local cities = db and db.cityRevealed or {}
  if all then
    cities = {}
    for ui in pairs(ns.CityPlaces or {}) do cities[ui] = true end
    for ui in pairs(ns.TownPlaces or {}) do cities[ui] = true end
  end
  for ui in pairs(cities) do
    local c = ns.CityPlaces and ns.CityPlaces[ui]
    for _, p in ipairs(c or {}) do
      local x, y, pc = Lay.MapToWorld(ui, p[1] / 100, p[2] / 100)
      if x then add(p[3], c.city, x, y, Lay.CityLevelAt(pc, x, y) or pc, p[4], nil, ui) end
    end
    local t = ns.TownPlaces and ns.TownPlaces[ui]
    for _, p in ipairs(t or {}) do add(p[1], t.town, p.x, p.y, t.cont, p.z, nil, ui, t.faction) end
  end
  for lc, list in pairs(Lay.CityDB()) do
    for _, c in ipairs(list) do
      local ui, city
      if ns.GPS and ns.GPS.CityMapAt then
        ui = ns.GPS.CityMapAt(Geo.Base(lc), c[1], c[2])
        local cp = ui and ns.CityPlaces and ns.CityPlaces[ui]
        city = cp and cp.city or (ui and ns.Maps and ns.Maps[ui] and ns.Maps[ui].name)
      end
      add(c[3], city, c[1], c[2], lc, nil, c[4], ui)
    end
  end
  return out
end

-- The city (Data/CityPlaces.lua uiMap) the player is in: their map or one it's inside; outside the capitals, a
-- starting zone with a town whose guards give directions (ns.TownPlaces: Dolanaar's in Teldrassil, asked 2026-10-04).
function Lay.CityHere()
  local id = C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
  for _ = 1, 4 do
    if not id then return nil end
    if (ns.CityPlaces and ns.CityPlaces[id]) or (ns.TownPlaces and ns.TownPlaces[id]) then return id end
    local m = ns.Maps and ns.Maps[id]
    id = m and m.parent
  end
  return nil
end

-- Talked to a guard here: this city's places show from now on.
function Lay.RevealCity()
  local ui = Lay.CityHere()
  local db = ns.db
  if not (ui and db) then return end
  db.cityRevealed = db.cityRevealed or {}
  if not db.cityRevealed[ui] then
    db.cityRevealed[ui] = true
    Lay.version = Lay.version + 1
    if ns.MarkUnsaved then ns.MarkUnsaved("cityRevealed:" .. tostring(ui), "add") end
  end
end

-- A guard's directions menu: a capital's offers the bank and the inn or the auction house; a town's (Dolanaar,
-- Razor Hill: no bank) the inn, the stable master and trainers. So: the bank or the inn, and three places at least.
Lay.GUARD_WORDS = { "bank", "inn", "auction", "stable", "trainer", "master", "mailbox", "zeppelin", "boat", "tram" }
function Lay.IsGuardMenu(options)
  local anchor, places = false, 0
  for _, o in ipairs(options or {}) do
    local t = (o.name or ""):lower()
    if t:find("bank", 1, true) or t:find("the inn", 1, true) or t == "inn" then anchor = true end
    for _, w in ipairs(Lay.GUARD_WORDS) do
      if t:find(w, 1, true) then
        places = places + 1
        break
      end
    end
  end
  return anchor and places >= 3
end

-- NPCs the player has talked to (asked 2026-10-05): the game doesn't tell addons where NPCs are, but a window of
-- theirs opening (gossip, a vendor, a trainer, a quest, a flight master, the bank...) means the player stands by
-- them, so the player's spot is theirs. Searchable (G.SearchPlaces) and a stop when picked; never drawn on the map.
-- Every spot an NPC (its creature id) was talked to at is kept (asked 2026-10-06, keep data forever): the first in its
-- record, the others in `spots` (one within NPC_SAME_YD of another is that one). In two places far apart it's a
-- `common` one (a guard, a vendor in every town): left out of the search unless the option `searchCommonNpcs` is on,
-- then found at its spot nearest the player (L.KnownNpcs); a guard's directions menu isn't kept. Saved account-wide in
-- ns.db.npcs: { [id] = { name, title, place, cont, x, y, common, vendor, repair, spots = { { cont, x, y, place }, ... } },
-- ["imp:<name>"] = { ..., imported } }.
-- Imported ones (the import window's "Import as NPCs", /way lines as herbs and ore) are unconfirmed until the
-- player talks to one of that name nearby (NPC_CONFIRM_YD), which replaces it.
Lay.NPC_SAME_YD = 50
Lay.NPC_CONFIRM_YD = 150
-- The events of an NPC's window, with the kind said when it has no title of its own.
Lay.NPC_EVENTS = {
  GOSSIP_SHOW = "NPC", MERCHANT_SHOW = L["Vendor"], TRAINER_SHOW = L["Trainer"], TAXIMAP_OPENED = L["Flight master"],
  BANKFRAME_OPENED = L["Banker"], AUCTION_HOUSE_SHOW = L["Auctioneer"], QUEST_GREETING = L["Quest giver"],
  QUEST_DETAIL = L["Quest giver"], QUEST_PROGRESS = L["Quest giver"], QUEST_COMPLETE = L["Quest giver"],
  PET_STABLE_SHOW = L["Stable master"], -- (translated: saved as the NPC's title, as the game's own titles are)
}
local function NpcDB()
  if not ns.db then return nil end
  ns.db.npcs = ns.db.npcs or {}
  return ns.db.npcs
end
-- The title under an NPC's name ("<Weapon Merchant>"), from its tooltip's second line; nil when it has none.
function Lay.NpcTitle(unit)
  if not (C_TooltipInfo and C_TooltipInfo.GetUnit) then return nil end
  local ok, info = pcall(C_TooltipInfo.GetUnit, unit)
  local line = ok and info and info.lines and info.lines[2]
  local text = line and line.leftText
  if type(text) ~= "string" or ns.IsSecret(text) then return nil end
  return text:match("^<(.+)>$")
end
-- Note the NPC `id` (`name`, `title`) talked to with the player at (x, y) on level `cont`, in `place` (the subzone). Returns true when it's
-- new (or moved from an import), false when known or left out.
-- `z`: the floor the player was followed on there (Nav.FollowedZ: in a building with its inside, down in Undercity, in
-- a capital; asked 2026-10-06, "learn NPC floors"), else nil: the record's (or the spot's) `z`, learned only, never
-- shipped; a route to the NPC goes to it (the stop's height), and a quest stop for one of its quests (L.QuestNpcZ).
function Lay.NoteNpc(id, name, title, cont, x, y, place, z)
  local db = NpcDB()
  if not (db and id and name and cont and x) then return false end
  z = z and math.floor(z * 10 + 0.5) / 10 or nil
  local n = db[id]
  if n then
    local spot = Lay.NpcSpotNear(n, cont, x, y)
    if not spot then -- (another place: kept too, and it's one of many)
      n.spots = n.spots or {}
      n.spots[#n.spots + 1] = { cont = cont, x = math.floor(x * 10 + 0.5) / 10, y = math.floor(y * 10 + 0.5) / 10,
        place = place, z = z }
      n.common = true
      ns.MarkUnsaved("npc:" .. id .. ":" .. #n.spots, "add")
    elseif z and spot.z == nil then -- (its floor learned: talked to again, followed there this time)
      spot.z = z
      ns.MarkUnsaved("npc:" .. id .. ":z", "add")
    end
    return false
  end
  -- an imported one of that name near here: talked to now, confirmed
  local imp = db["imp:" .. name:lower()]
  if imp and Geo.Base(imp.cont) == Geo.Base(cont) and (imp.x - x) ^ 2 + (imp.y - y) ^ 2 <= Lay.NPC_CONFIRM_YD ^ 2 then
    db["imp:" .. name:lower()] = nil
  end
  db[id] = { name = name, title = title, place = place, cont = cont, x = math.floor(x * 10 + 0.5) / 10,
    y = math.floor(y * 10 + 0.5) / 10, z = z }
  ns.MarkUnsaved("npc:" .. id, "add")
  return true
end
-- The quests the NPC in the open window gives or takes in (asked 2026-10-06: a quest stop goes to its NPC's floor): the
-- gossip's lists (C_GossipInfo.GetActiveQuests / GetAvailableQuests, in this client's own API docs), else the quest
-- window's own (GetQuestID). Their ids.
function Lay.WindowQuests(event)
  local out = {}
  local function take(id)
    if type(id) == "number" and not ns.IsSecret(id) and id > 0 then out[#out + 1] = id end
  end
  local G = C_GossipInfo
  if event == "GOSSIP_SHOW" and G then
    for _, fn in ipairs({ G.GetActiveQuests or false, G.GetAvailableQuests or false }) do
      local ok, list = false, nil
      if fn then ok, list = pcall(fn) end
      if ok and type(list) == "table" then
        for _, q in ipairs(list) do take(type(q) == "table" and q.questID) end
      end
    end
  elseif (event == "QUEST_DETAIL" or event == "QUEST_PROGRESS" or event == "QUEST_COMPLETE") and GetQuestID then
    local ok, id = pcall(GetQuestID)
    if ok then take(id) end
  end
  return out
end
-- NPC `id`'s quests (L.WindowQuests'), kept with it (`quests` = { [quest id] = true }). Whether any was new.
function Lay.NoteNpcQuests(id, quests)
  local n = NpcDB() and NpcDB()[id]
  if not (n and quests and quests[1]) then return false end
  n.quests = n.quests or {}
  local new = false
  for _, q in ipairs(quests) do
    if not n.quests[q] then n.quests[q], new = true, true end
  end
  if new then ns.MarkUnsaved("npc:" .. id .. ":quests", "add") end
  return new
end
-- The floor (height) of quest `qid`'s NPC near (x, y) on level `cont`: one talked to whose window had that quest (its
-- giver, or the one who takes it in), its floor known, within QUEST_NPC_YD, the nearest. Nil when none.
Lay.QUEST_NPC_YD = 40
function Lay.QuestNpcZ(qid, cont, x, y)
  local best, bd
  for _, n in pairs(NpcDB() or {}) do
    if type(n) == "table" and n.quests and n.quests[qid] and not n.imported then
      local spots = { n }
      for _, s in ipairs(n.spots or {}) do spots[#spots + 1] = s end
      for _, s in ipairs(spots) do
        if s.z and s.cont == cont and s.x then
          local d = (s.x - x) ^ 2 + (s.y - y) ^ 2
          if d <= Lay.QUEST_NPC_YD ^ 2 and (not bd or d < bd) then best, bd = s.z, d end
        end
      end
    end
  end
  return best
end
-- The window of an NPC opening (L.NPC_EVENTS): who it is and where the player stands. `options`: the gossip's.
function Lay.OnNpcWindow(event, options)
  local kind = Lay.NPC_EVENTS[event]
  if not kind or not UnitGUID then return false end
  if event == "GOSSIP_SHOW" and Lay.IsGuardMenu(options) then return false end -- (a guard's directions)
  local guid, name = UnitGUID("npc"), UnitName("npc")
  if ns.IsSecret(guid) or ns.IsSecret(name) or not name then return false end
  local id = ns.Nav and ns.Nav.NpcOf(guid)
  if not id then return false end -- (an object's: a quest from a board, a chest)
  if Geo.Simulated() then return false end -- (the dev tools' simulated player: not where the NPC is)
  local px, py, cont = Geo.PlayerWorld()
  if not px then return false end -- (in a dungeon: no position)
  if ns.Nav.InstanceLevel and ns.Nav.InstanceLevel(cont) then return false end
  local level = ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont) or cont -- (down in Undercity: its level)
  local place = GetSubZoneText and GetSubZoneText()
  if ns.IsSecret(place) or place == "" then place = GetZoneText and GetZoneText() end
  if ns.IsSecret(place) or place == "" then place = nil end
  local z = ns.Nav.FollowedZ and ns.Nav.FollowedZ(level) -- (the floor followed: in a building, a city)
  -- (down in a city's level or in a capital, the NPC's own height where it's shipped: the player's floor, followed from
  -- there, and the one learned; the floor followed can be a walkway over them, Undercity 2026-11-14)
  local sz = ((ns.CityLevels and ns.CityLevels[level]) or (ns.Nav.InCapital and ns.Nav.InCapital(level, px, py)))
    and Lay.ShippedSpawnZ(id, name, level, px, py)
  if sz and ns.Nav.AnchorFloor and ns.Nav.AnchorFloor(level, px, py, sz) then z = sz end
  local new = Lay.NoteNpc(id, name, Lay.NpcTitle("npc") or (kind ~= "NPC" and kind or nil), level, px, py, place, z)
  Lay.NoteNpcQuests(id, Lay.WindowQuests(event))
  -- (its faction, for the search: L.NpcFaction. "Neutral": the goblins' towns, and anyone the game gives none)
  local f = UnitFactionGroup and UnitFactionGroup("npc")
  local rec = NpcDB() and NpcDB()[id]
  if rec and not ns.IsSecret(f) then
    rec.faction = (f == "Alliance" or f == "Horde") and f or "Neutral"
  end
  if event == "MERCHANT_SHOW" then
    Lay.NoteMerchant(id)
    Lay.NoteMerchantItems(id)
  end
  return new
end
-- A vendor's window open (asked 2026-11-14: "repair" and "vendor" in the search, nearest first): NPC `id` is a vendor
-- (`vendor`), and whether it repairs (`repair`: CanMerchantRepair, the merchant window's own; left unknown, nil, when
-- the client doesn't give it or hides it). Older records have neither: a vendor by its title (L.NpcIsVendor).
function Lay.NoteMerchant(id)
  local n = NpcDB() and NpcDB()[id]
  if not n then return false end
  local changed = not n.vendor
  n.vendor = true
  if CanMerchantRepair then
    local ok, can = pcall(CanMerchantRepair)
    if ok and not ns.IsSecret(can) then
      can = (can and can ~= 0) and true or false -- (1/nil in the old API, a boolean in the new)
      if n.repair ~= can then n.repair, changed = can, true end
    end
  end
  if changed then ns.MarkUnsaved("npc:" .. id .. ":vendor", "add") end
  return changed
end
-- What the open vendor sells (asked 2026-11-15, the user's "Both": the shipped lists, Data/VendorItems.lua, and each
-- vendor's real stock learned here, which wins): every item its window lists, kept with NPC `id` as `sells` =
-- { [item id] = { name = the client's, kind = "a" arrows / "b" bullets / nil } }. Added to, never taken from (keep data
-- forever: an item sold out comes back). Again on MERCHANT_UPDATE (names the client hadn't loaded yet). Whether any
-- was new; then L.sellsVersion goes up (the search's index made again).
Lay.sellsVersion = 0
function Lay.NoteMerchantItems(id)
  local n = NpcDB() and NpcDB()[id]
  if not (n and GetMerchantNumItems) then return false end
  local ok, count = pcall(GetMerchantNumItems)
  if not ok or type(count) ~= "number" or ns.IsSecret(count) then return false end
  local changed = false
  for i = 1, count do
    local item, name, kind = Lay.MerchantItem(i)
    if item then
      n.sells = n.sells or {}
      local had = n.sells[item]
      if not had then
        n.sells[item], changed = { name = name, kind = kind }, true
      elseif (name and had.name ~= name) or (kind and had.kind ~= kind) then
        had.name, had.kind, changed = name or had.name, kind or had.kind, true
      end
    end
  end
  if changed then
    Lay.sellsVersion = Lay.sellsVersion + 1
    ns.MarkUnsaved("npc:" .. id .. ":sells", "add")
  end
  return changed
end
-- The open vendor's item `i`: its item id, name (nil when not loaded yet) and kind ("a" arrows, "b" bullets, nil), or nil.
function Lay.MerchantItem(i)
  local function safe(fn, ...)
    if not fn then return nil end
    local ok, a = pcall(fn, ...)
    if ok and not ns.IsSecret(a) then return a end
    return nil
  end
  local id = safe(GetMerchantItemID, i)
  if type(id) ~= "number" then
    local link = safe(GetMerchantItemLink, i)
    id = type(link) == "string" and tonumber(link:match("item:(%d+)")) or nil
  end
  if not id then return nil end
  local info = C_MerchantFrame and safe(C_MerchantFrame.GetItemInfo, i)
  local name = type(info) == "table" and info.name or safe(GetMerchantItemInfo, i)
  if type(name) ~= "string" or ns.IsSecret(name) or name == "" then name = nil end
  local kind
  local instant = GetItemInfoInstant or (C_Item and C_Item.GetItemInfoInstant)
  if instant then
    local ok, _, _, _, _, _, class, sub = pcall(instant, id)
    if ok and class == 6 and not ns.IsSecret(sub) then kind = sub == 2 and "a" or sub == 3 and "b" or nil end
  end
  return id, name, kind
end
-- The vendor window's list changing (its items' names loaded): the open vendor's stock noted again.
function Lay.OnMerchantUpdate()
  if not UnitGUID then return false end
  local guid = UnitGUID("npc")
  if ns.IsSecret(guid) or not guid then return false end
  local id = ns.Nav and ns.Nav.NpcOf(guid)
  return id and Lay.NoteMerchantItems(id) or false
end
-- Whether NPC record `n` sells (its window was a vendor's: `vendor`; an older record by its title, the window's kind
-- when it had none of its own).
function Lay.NpcIsVendor(n)
  return n.vendor == true or (n.title ~= nil and (n.title == L["Vendor"] or n.title == "Vendor"))
end
-- NPC record `n`'s spot within NPC_SAME_YD of (x, y) on level `cont` (the record itself for its first), or nil.
function Lay.NpcSpotNear(n, cont, x, y)
  local function near(c, sx, sy)
    return c and sx and Geo.Base(c) == Geo.Base(cont) and (sx - x) ^ 2 + (sy - y) ^ 2 <= Lay.NPC_SAME_YD ^ 2
  end
  if near(n.cont, n.x, n.y) then return n end
  for _, s in ipairs(n.spots or {}) do
    if near(s.cont, s.x, s.y) then return s end
  end
  return nil
end
-- NPC record `n` at its spot nearest the player (on their continent first): a copy with that spot's cont, x, y, place.
-- `allow(spot)`: only those spots (none allowed: nil).
function Lay.NearestNpcSpot(n, allow)
  local px, py, pc = Geo.PlayerWorld()
  local best, bd = { n.cont, n.x, n.y, n.place, n.z }, math.huge
  local spots = { { cont = n.cont, x = n.x, y = n.y, place = n.place, z = n.z } }
  for _, s in ipairs(n.spots or {}) do spots[#spots + 1] = s end
  local any = false
  for _, s in ipairs(spots) do
    if s.cont and s.x and (not allow or allow(s)) then
      any = true
      local d = (px and pc and Geo.Base(s.cont) == Geo.Base(pc)) and (s.x - px) ^ 2 + (s.y - py) ^ 2 or 1e30
      if d < bd then best, bd = { s.cont, s.x, s.y, s.place, s.z }, d end
    end
  end
  if allow and not any then return nil end
  return { name = n.name, title = n.title, imported = n.imported, common = n.common, vendor = Lay.NpcIsVendor(n) or nil,
    repair = n.repair, cont = best[1], x = best[2], y = best[3], place = best[4], z = best[5] }
end
-- The NPCs to search: { { name, title, cont, x, y, imported }, ... }; common ones only with the option (asked
-- 2026-10-06), at their spot nearest the player.
-- An NPC's side for the search (the user's 1.1.6 test pass, 2026-10-07: "routing to an opposing faction NPC
-- shouldn't show up in the list"; the NPCs met are account-wide, so the other faction's character's were offered):
-- "A", "H" or "N" (neutral). Talked to since, as the game gave it (`faction`, L.OnNpcWindow); else (met before, or
-- imported) by where `spot` (default: its own) stands for a player of side `mine`: within the other faction's guards'
-- reach (Data/Hostile.lua, the circles routes keep out of) is theirs, anywhere else neutral (offered).
function Lay.NpcFaction(n, mine, spot)
  local f = n.faction
  if f == "Alliance" then return "A" elseif f == "Horde" then return "H" elseif f == "Neutral" then return "N" end
  spot = spot or n
  local cont = spot.cont and Geo.Base(spot.cont)
  local list = (mine == "A" or mine == "H") and cont and ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][mine]
  if not (list and spot.x and spot.y) then return "N" end
  for i = 1, #list - 2, 3 do
    if (list[i] - spot.x) ^ 2 + (list[i + 1] - spot.y) ^ 2 <= list[i + 2] ^ 2 then return mine == "A" and "H" or "A" end
  end
  return "N"
end
-- `allCommon`: the common ones too, with the option off (the search's generic words: "repair", "vendor"; asked
-- 2026-11-14); each has `common` set, so the search can tell them.
function Lay.KnownNpcs(allCommon)
  return (Lay.KnownNpcsWithIds(allCommon))
end
-- L.KnownNpcs' list, and each one's creature id by its place in it (the search merges it with the shipped NPC).
function Lay.KnownNpcsWithIds(allCommon)
  local out = {}
  local s = ns.settings and ns.settings.gps
  local withCommon = allCommon or (s and s.searchCommonNpcs)
  local mine = ns.Nav and ns.Nav.Faction and ns.Nav.Faction()
  local theirs = mine == "A" and "H" or mine == "H" and "A" or nil
  local function ours(n, spot) return not (theirs and Lay.NpcFaction(n, mine, spot) == theirs) end
  local ids = {}
  for id, n in pairs(NpcDB() or {}) do
    if n.name and n.x then
      if not n.common then
        if ours(n, n) then out[#out + 1] = n ids[#out] = id end
      elseif withCommon then -- (met in many places: the nearest of those on the player's side)
        local spot = Lay.NearestNpcSpot(n, function(s) return ours(n, s) end)
        if spot then out[#out + 1] = spot ids[#out] = id end
      end
    end
  end
  return out, ids
end

-- Every friendly NPC, shipped (Data/Npcs.lua, `agps npcs`; asked 2026-11-14: "the search function for
-- repairs/trainers/etc should always show for any NPC", the user's choice "Ship all NPCs"): read from its one string at
-- the first search, not at login. Each { id, name, title, svc (the services' letters: "v" vendor, "r" repairs, "t"
-- trainer, "f" flight master, "i" innkeeper, "b" banker, "a" auctioneer, "s" stable master, "q" quests...), trainer
-- ("MAGE", "Mining", "Weapon", "Riding", "Pet" or nil), side ("A", "H", "B"), spawns = { level, x, y, z, ... } }; and
-- { [id] = that }, and { [its name, lower case] = { those of that name } }. Read again when the string changes (the
-- tests' own).
function Lay.ShippedNpcs()
  local packed = ns.NpcsPacked
  if Lay.shippedFrom == packed and Lay.shippedNpcs then return Lay.shippedNpcs, Lay.shippedById, Lay.shippedByName end
  local out, byId, byName = {}, {}, {}
  if type(packed) == "string" then
    for line in packed:gmatch("[^\n]+") do
      local id, name, title, svc, trainer, side, spawns =
        line:match("^(%d+)|([^|]*)|([^|]*)|([^|]*)|([^|]*)|([^|]*)|(.*)$")
      id = tonumber(id)
      if id and name ~= "" then
        local sp = {}
        for lv, x, y, z in spawns:gmatch("(%-?%d+) (%-?[%d%.]+) (%-?[%d%.]+) (%-?[%d%.]+)") do
          local k = #sp
          sp[k + 1], sp[k + 2], sp[k + 3], sp[k + 4] = tonumber(lv), tonumber(x), tonumber(y), tonumber(z)
        end
        if sp[1] then
          local n = { id = id, name = name, title = title ~= "" and title or nil, svc = svc,
            trainer = trainer ~= "" and trainer or nil, side = side, spawns = sp }
          out[#out + 1], byId[id] = n, n
          local key = name:lower()
          byName[key] = byName[key] or {}
          byName[key][#byName[key] + 1] = n
        end
      end
    end
  end
  Lay.shippedFrom, Lay.shippedNpcs, Lay.shippedById, Lay.shippedByName = packed, out, byId, byName
  return out, byId, byName
end
-- The shipped NPC that NPC record `n` (talked to: ns.db.npcs[id]) is: by its creature id, else one of its name with a
-- spawn within NPC_SAME_YD of its spot (a creature id the data does not have: the same NPC). Nil when none.
function Lay.ShippedFor(id, n)
  local _, byId, byName = Lay.ShippedNpcs()
  if id and byId[id] then return byId[id] end -- (the game's own ids: its name may be in the client's language)
  if not (n and n.name and n.cont and n.x) then return nil end
  local base = Geo.Base(n.cont)
  for _, s in ipairs(byName[n.name:lower()] or {}) do
    local sp = s.spawns
    for i = 1, #sp - 3, 4 do
      if Geo.Base(sp[i]) == base and (sp[i + 1] - n.x) ^ 2 + (sp[i + 2] - n.y) ^ 2 <= Lay.NPC_SAME_YD ^ 2 then return s end
    end
  end
  return nil
end
-- The height of shipped NPC `id` (else the one named `name` there: L.ShippedFor) at its spawn within NPC_FLOOR_YD of
-- (x, y) on level `level`, the game's, or nil: its window open, the player stands by it (L.OnNpcWindow).
Lay.NPC_FLOOR_YD = 8
function Lay.ShippedSpawnZ(id, name, level, x, y)
  local n = Lay.ShippedFor(id, { name = name, cont = level, x = x, y = y })
  local sp = n and n.spawns
  local best, bd = nil, Lay.NPC_FLOOR_YD ^ 2
  for i = 1, sp and #sp - 3 or 0, 4 do
    local d = (sp[i + 1] - x) ^ 2 + (sp[i + 2] - y) ^ 2
    if sp[i] == level and d <= bd then best, bd = sp[i + 3], d end
  end
  return best
end
-- What the shipped vendors sell (Data/VendorItems.lua, `agps vendors`; asked 2026-11-15: "arrows" or "sharp arrow"
-- should send the player to the closest vendor that sells them): read from its one string at the first search. Items
-- { [item id] = { name (English), kind ("a" arrows, "b" bullets, or nil) } }, and { [npc id] = { item ids } } (a list
-- several vendors share is one table). An emulator's lists: the stock learned (L.NoteMerchantItems) wins.
function Lay.VendorItems()
  local packed = ns.VendorItemsPacked
  if Lay.vendorFrom == packed and Lay.vendorItems then return Lay.vendorItems, Lay.vendorSells end
  local items, sells, order, inItems = {}, {}, {}, true
  if type(packed) == "string" then
    for line in packed:gmatch("[^\n]+") do
      if line == "#" then
        inItems = false
      elseif inItems then
        local id, kind, name = line:match("^(%d+)|(%a?)|(.+)$")
        id = tonumber(id)
        if id then
          order[#order + 1] = id
          items[id] = { name = name, kind = kind ~= "" and kind or nil }
        end
      else
        local npc, rest = line:match("^(%d+)|(.+)$")
        npc = tonumber(npc)
        if npc then
          local same = tonumber(rest:match("^=(%d+)$") or "")
          if same then
            sells[npc] = sells[same]
          else
            local list = {}
            for k in rest:gmatch("[^,]+") do list[#list + 1] = order[(tonumber(k, 36) or -1) + 1] end
            sells[npc] = list
          end
        end
      end
    end
  end
  Lay.vendorFrom, Lay.vendorItems, Lay.vendorSells = packed, items, sells
  return items, sells
end
-- Whether shipped NPC `n` offers service `letter` (L.ShippedNpcs' `svc`).
function Lay.NpcOffers(n, letter)
  return n.svc ~= nil and n.svc:find(letter, 1, true) ~= nil
end
-- Shipped NPC `n`'s spawn nearest (x, y) on the player's continent `cont` (any level over it: Undercity's too), else
-- its first: level, x, y, z.
function Lay.NearestSpawn(n, x, y, cont)
  local sp = n.spawns
  local base = cont and Geo.Base(cont)
  local bi, bd = 1, math.huge
  for i = 1, #sp - 3, 4 do
    if x and base and Geo.Base(sp[i]) == base then
      local d = (sp[i + 1] - x) ^ 2 + (sp[i + 2] - y) ^ 2
      if d < bd then bi, bd = i, d end
    end
  end
  return sp[bi], sp[bi + 1], sp[bi + 2], sp[bi + 3]
end
-- The floor (z) learned for NPC record `n` (talked to: L.NoteNpc) at a spot within LEARNED_Z_YD of (x, y) on level
-- `level`, or nil: the search's stop at a shipped NPC takes the learned floor first (where the player was followed
-- there), else the spawn's own height.
Lay.LEARNED_Z_YD = 15
function Lay.LearnedZ(n, level, x, y)
  if not n then return nil end
  local function at(s)
    return s.z and s.cont == level and s.x and (s.x - x) ^ 2 + (s.y - y) ^ 2 <= Lay.LEARNED_Z_YD ^ 2
  end
  if at(n) then return n.z end
  for _, s in ipairs(n.spots or {}) do
    if at(s) then return s.z end
  end
  return nil
end
-- Import NPCs from /way lines ("/way Elwynn Forest 42.1 65.9 Innkeeper Farley"): unconfirmed until talked to.
-- Returns added, skipped (known by that name), errors.
function Lay.ImportNpcs(text)
  local stops, errors = ns.Import.Parse(text, C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player"))
  local added, skipped = 0, 0
  if not NpcDB() then return 0, 0, errors end
  local known = Lay.TalkedToNames()
  for _, d in ipairs(stops) do
    if d.unnamed then -- (no name: Parse's "Zone x, y")
      errors[#errors + 1] = L["a line with no NPC name"]
    elseif Lay.AddImportedNpc(d.cont, d.x, d.y, d.name, nil, known) then
      added = added + 1
    else
      skipped = skipped + 1
    end
  end
  if added > 0 then ns.MarkUnsaved("import:npcs:" .. (time and time() or 0), "add") end -- (one change for them all)
  return added, skipped, errors
end
-- The names (lowercase) of the NPCs talked to: { [name] = true }.
function Lay.TalkedToNames()
  local known = {}
  for _, n in pairs(NpcDB() or {}) do
    if n.name and not n.imported then known[n.name:lower()] = true end
  end
  return known
end
-- An imported NPC (`name`, `title` or nil, at (x, y) on level `cont`): kept unconfirmed until talked to, unless one of
-- that name is known already (talked to: `known`, L.TalkedToNames(), made once for a whole import; or imported).
-- Whether it was added.
function Lay.AddImportedNpc(cont, x, y, name, title, known)
  local db = NpcDB()
  name = name and ns.MapText.CleanName(name)
  if not (db and cont and x and y and name and name ~= "") then return false end
  local key = "imp:" .. name:lower()
  if db[key] or (known or Lay.TalkedToNames())[name:lower()] then return false end
  db[key] = { name = name, title = title, cont = cont, x = x, y = y, imported = true }
  return true -- (the import counts as one unsaved change: its caller's)
end

-- The underground city level a place on `cont` is down in (on its floors), or nil. A guard
-- may mark it on the continent's map (asked up top, say), but city places are down there.
function Lay.CityLevelAt(cont, x, y)
  -- (any floor of its there: a trainer's booth or a counter is blocked, but down there)
  local P, N = ns.Passability, ns.Nav
  for id, l in pairs(ns.CityLevels or {}) do
    if l.base == cont and ((N and N.CityHeight and N.CityHeight(id, x, y)) or (P and P.IsOpen(id, x, y))) then return id end
  end
  return nil
end

-- The height (the game's) of the city place named `name` near (x, y) on `cont` (a guard's
-- directions to it, a spot a guard pointed out), from Data/CityPlaces.lua; nil when none.
Lay.PLACE_Z_YD = 25
function Lay.PlaceZ(cont, x, y, name)
  if not (name and ns.CityPlaces) then return nil end
  local want = name:lower()
  for ui, c in pairs(ns.CityPlaces) do
    for _, p in ipairs(c) do
      if p[4] and p[3]:lower() == want then
        local px, py, pc = Lay.MapToWorld(ui, p[1] / 100, p[2] / 100)
        if px and Geo.Base(pc) == Geo.Base(cont) and (px - x) ^ 2 + (py - y) ^ 2 <= Lay.PLACE_Z_YD ^ 2 then return p[4] end
      end
    end
  end
  for _, t in pairs(ns.TownPlaces or {}) do
    for _, p in ipairs(t) do
      if p.z and t.cont == Geo.Base(cont) and p[1]:lower() == want and (p.x - x) ^ 2 + (p.y - y) ^ 2 <= Lay.PLACE_Z_YD ^ 2 then
        return p.z
      end
    end
  end
  return nil
end

local cityDbChecked
function Lay.CityDB()
  local db = ns.db
  if not db then return {} end
  db.cityPois = db.cityPois or {}
  if not cityDbChecked and ns.CityLevels then
    -- (saved on the continent before its cities had levels: moved down to theirs)
    cityDbChecked = true
    for cont, list in pairs(db.cityPois) do
      if not ns.CityLevels[cont] then
        for i = #list, 1, -1 do
          local c = list[i]
          local lvl = Lay.CityLevelAt(cont, c[1], c[2])
          if lvl then
            table.remove(list, i)
            db.cityPois[lvl] = db.cityPois[lvl] or {}
            table.insert(db.cityPois[lvl], c)
          end
        end
      end
    end
  end
  return db.cityPois
end

-- Save a city location (or update it: the same name close by). Returns the entry.
function Lay.AddCityPoi(cont, x, y, name, icon)
  local db = Lay.CityDB()
  db[cont] = db[cont] or {}
  for _, c in ipairs(db[cont]) do
    if c[3] == name and (c[1] - x) ^ 2 + (c[2] - y) ^ 2 <= Lay.CITY_SAME_YD ^ 2 then
      if c[1] ~= x or c[2] ~= y or c[4] ~= icon then
        c[1], c[2], c[4] = x, y, icon
        if ns.MarkUnsaved then ns.MarkUnsaved(("city:%s:%s"):format(tostring(cont), name), "add") end
      end
      return c
    end
  end
  local c = { x, y, name, icon }
  db[cont][#db[cont] + 1] = c
  Lay.version = Lay.version + 1
  -- (a guard's place counts as made, as a pin: Save Now, asked 2026-10-06; a crash lost it)
  if ns.MarkUnsaved then ns.MarkUnsaved(("city:%s:%s"):format(tostring(cont), name), "add") end
  return c
end

local lastGossipPoi, lastGossipAt -- "name:x:y" of the last one made a stop, and when (the event repeats)
Lay.GOSSIP_REPEAT_SECONDS = 3

-- A guard marked something on the map: save it, and make it a stop (again too, when asked
-- again for a place already known: `asked`, the player picked the guard's answer).
function Lay.OnGossipPoi(asked)
  local G = C_GossipInfo
  if not (G and G.GetPoiForUiMapID and G.GetPoiInfo and C_Map and C_Map.GetBestMapForUnit) then return end
  local mapID = C_Map.GetBestMapForUnit("player")
  local maps = { mapID }
  local info, onMap
  for _, id in ipairs(maps) do
    local poi = id and G.GetPoiForUiMapID(id)
    if poi and not (ns.IsSecret and ns.IsSecret(poi)) then
      info, onMap = G.GetPoiInfo(id, poi), id
      if info then break end
    end
  end
  if not (info and info.position and info.name) then return end
  local u, v
  if info.position.GetXY then u, v = info.position:GetXY() else u, v = info.position.x, info.position.y end
  local x, y, cont = Lay.MapToWorld(onMap, u, v)
  if not x then return end
  cont = Lay.CityLevelAt(cont, x, y) or cont
  local icon = Lay.CityIcon(info.name)
  Lay.AddCityPoi(cont, x, y, info.name, icon)
  local key = string.format("%s:%.0f:%.0f", info.name, x, y)
  local now = GetTime()
  if key == lastGossipPoi and now - (lastGossipAt or 0) < Lay.GOSSIP_REPEAT_SECONDS then return end
  if key == lastGossipPoi and not asked then return end -- (the same marker, not asked for again)
  lastGossipPoi, lastGossipAt = key, now
  -- as a stop (unless it's one already)
  for _, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.name == info.name and d.cont == cont and (d.x - x) ^ 2 + (d.y - y) ^ 2 <= Lay.CITY_SAME_YD ^ 2 then return end
  end
  if ns.Import and ns.Import.AddMapPin then
    ns.Import.AddMapPin({ cont = cont, x = x, y = y, name = info.name, tex = icon, z = Lay.PlaceZ(cont, x, y, info.name) })
  end
end

---------------------------------------------------------------------------
-- Events: gathering, minimap tooltips, world map
---------------------------------------------------------------------------

local pendingCast -- { guid, name, kind, x, y, cont }
local lastGather -- { name, at }: the node a gathering cast just finished on (its loot window is next)

-- The loot window open: right after a gathering cast, what the node gave (L.OnGatherLoot). `now`: GetTime().
function Lay.OnLootOpened(now)
  local g = lastGather or (pendingCast and { name = pendingCast.name, at = pendingCast.at or -math.huge })
  if not g or now - g.at > Lay.LOOT_AFTER_GATHER or not GetNumLootItems or not GetLootSlotInfo then return nil end
  lastGather = nil
  local slots = {}
  for i = 1, GetNumLootItems() or 0 do
    local item = not GetLootSlotType or GetLootSlotType(i) == 1 -- (LOOT_SLOT_ITEM: not money)
    local icon, name, _, _, _, _, isQuest = GetLootSlotInfo(i)
    if item and icon and not ns.IsSecret(icon) and not ns.IsSecret(name) then
      slots[#slots + 1] = { icon, name, isQuest and true or nil }
    end
  end
  return Lay.OnGatherLoot(g.name, slots)
end

-- Gathering from a spell cast on a target: by the spell (any rank, or its name matching
-- Mining / Herb Gathering), or by the target being a known node name.
function Lay.GatherKind(spellID, target)
  if ns.IsSecret and (ns.IsSecret(spellID) or ns.IsSecret(target)) then return nil end
  if Lay.GATHER_IDS[spellID] then return Lay.GATHER_IDS[spellID] end
  local name = spellID and SpellName(spellID)
  if name then
    for kind, id in pairs(Lay.GATHER_SPELLS) do
      if name == SpellName(id) then return kind end
    end
  end
  return Lay.NodeKind(target)
end
local GatherKind = Lay.GatherKind

-- Whether the minimap is in its indoor (smaller) scale: each mode keeps its zoom in its own
-- CVar and the active one follows Minimap:GetZoom().
local indoorsAt, indoorsCached = -100, false
local MinimapIndoors
-- The game's minimap across, in yards (its zoom, indoors or out), for drawing on it (GPS.UpdateMinimapRoute).
function Lay.MinimapYards()
  if not (Minimap and Minimap.GetZoom) then return nil end
  local ok, indoors = pcall(MinimapIndoors)
  local sizes = (ok and indoors) and Lay.MINIMAP_INDOOR or Lay.MINIMAP_OUTDOOR
  return sizes[(tonumber(Minimap:GetZoom()) or 0) + 1] or sizes[1]
end
function MinimapIndoors()
  if GetTime() - indoorsAt < 5 then return indoorsCached end
  indoorsAt = GetTime()
  local z = Minimap:GetZoom()
  if GetCVar("minimapZoom") == GetCVar("minimapInsideZoom") then
    Minimap:SetZoom(z < 2 and z + 1 or z - 1)
    indoorsCached = tonumber(GetCVar("minimapZoom")) ~= Minimap:GetZoom()
    Minimap:SetZoom(z)
  else
    indoorsCached = tonumber(GetCVar("minimapZoom")) ~= z
  end
  return indoorsCached
end

-- The minimap's tooltip names what's under the cursor: remember gathering nodes there.
-- The last thing in the world the mouse was over (not a unit), from the tooltip: its name.
local worldName, worldAt = nil, -100

function Lay.NoteWorldObject(name, now) worldName, worldAt = name, now end

-- Right-clicking a herb or ore without the profession: the game says "Requires Herbalism"
-- (or Mining). The node is right next to the player then: save it (account-wide) for a
-- character that has the profession. Its name comes from the tooltip just shown.
function Lay.OnGatherError(message, now, px, py, cont)
  if not message or not worldName or now - worldAt > 3 or not px then return false end
  local kind
  for k, prof in pairs(Lay.PROFESSION) do
    local local_name = SpellName(Lay.GATHER_SPELLS[k])
    if message:find(prof, 1, true) or (local_name and message:find(local_name, 1, true)) then kind = k end
  end
  if not kind then return false end
  local added = Lay.AddNode(cont, px, py, worldName, kind)
  if added and ns.Print then ns.Print(string.format(L["saved %s on the map for later (all your characters)"], worldName)) end
  if added and ns.MarkUnsaved then
    ns.MarkUnsaved(("node:%s:%.0f:%.0f"):format(tostring(cont), px, py), "add") -- (Save Now, as a pin: asked 2026-10-06)
  end
  return added
end

-- Whether the tooltip is the minimap's blips under the mouse. This client's Minimap_OnUpdate shows them with
-- GameTooltip:SetOwner(UIParent, "ANCHOR_CURSOR") (Blizzard_Minimap/Mainline/Minimap.lua), not owned by the Minimap:
-- an owner check alone saved no herb or ore hovered (reported 2026-11-13).
function Lay.IsMinimapTip(tip)
  local owner = tip:GetOwner()
  if not Minimap then return false end
  if owner == Minimap then return true end
  if owner ~= UIParent then return false end
  if not (Minimap.IsVisible and Minimap:IsVisible()) then return false end
  if Minimap.GetEffectiveAlpha and (Minimap:GetEffectiveAlpha() or 1) <= 0 then return false end
  if Minimap.IsMouseOver and Minimap:IsMouseOver() then return true end
  return Lay.CursorOnMinimap()
end
-- The cursor inside the Minimap's square, worked out (the GPS square: the mouse is on the map's own frame over it, and
-- Minimap:IsMouseOver() says false while the game still shows its blips' tooltip, the hover log 2026-11-13).
function Lay.CursorOnMinimap()
  if not (Minimap.GetCenter and Minimap.GetWidth and GetCursorPosition) then return false end
  local mx, my = Minimap:GetCenter()
  if not mx then return false end
  local sc = Minimap:GetEffectiveScale() or 1
  local cx, cy = GetCursorPosition()
  if not cx or sc <= 0 then return false end
  local w, h = Minimap:GetWidth() or 0, (Minimap.GetHeight and Minimap:GetHeight()) or Minimap:GetWidth() or 0
  return math.abs(cx / sc - mx) <= w / 2 and math.abs(cy / sc - my) <= h / 2
end

-- The minimap across, in yards, for a hover: the game's own view radius (the square's Minimap is bigger than the
-- usual one: the zoom table's yards are the usual one's), else the zoom table's.
function Lay.HoverYards()
  local C = C_Minimap
  if C and C.GetViewRadius then
    local ok, r = pcall(C.GetViewRadius)
    if ok and not ns.IsSecret(r) and type(r) == "number" and r > 0 then return 2 * r end
  end
  local sizes = MinimapIndoors() and Lay.MINIMAP_INDOOR or Lay.MINIMAP_OUTDOOR
  return sizes[Minimap:GetZoom() + 1]
end

-- The debug log's notes (ns.Debug, Options > Help > Debugging; nothing while it's off). Tooltips naming a herb or vein:
-- what the hover reader saw (2026-11-13: a vein hovered on the GPS square wasn't saved), each once (its text changing or
-- 2 s); the player's gathering casts: which of their values the game hid and what they were taken for.
local function Debugging() return ns.Debug and ns.Debug.on end
function Lay.NoteCast(what, unit, target, guid, spell)
  if not Debugging() or unit ~= "player" then return end
  local secret = (ns.IsSecret(target) and "t" or "") .. (ns.IsSecret(guid) and "g" or "") .. (ns.IsSecret(spell) and "s" or "")
  local name = not ns.IsSecret(target) and target or nil
  local spellName = not ns.IsSecret(spell) and SpellName and SpellName(spell) or nil
  local gather = false
  for _, id in pairs(Lay.GATHER_SPELLS or {}) do
    if spellName and spellName == SpellName(id) then gather = true end
  end
  if what == "sent" and not gather and not (name and Lay.NodeKind(name)) then return end
  ns.Debug.Log("cast " .. what, { secret = secret, target = name or false, spell = spellName or false,
    kind = name and Lay.NodeKind(name) or false })
end
-- A gather's spot and whether it was new; the map's next few icon gathers say whether its icon was placed
-- (Lay.drawWatch, GPSFrame's AddMarks: 2026-11-13, a vein mined that never showed, Find Herbs and Ore's pick).
function Lay.NoteGather(p, added)
  if not Debugging() then return end
  ns.Debug.Log("gathered", { name = p.name, cont = p.cont, x = p.x, y = p.y, added = added and true or false,
    shown = Lay.NodeShown(p.name, p.kind) })
  Lay.drawWatch = { name = p.name, x = p.x, y = p.y, left = 6 }
end
function Lay.NoteDraw(entry)
  local w = Lay.drawWatch
  if not w then return end
  w.left = w.left - 1
  if w.left <= 0 then Lay.drawWatch = nil end
  if Debugging() then ns.Debug.Log("icons after the gather", entry) end
end
function Lay.NoteHover(tip)
  if not Debugging() then return end
  local lines, node = {}, false
  for i = 1, math.min(tip:NumLines() or 0, 6) do
    local fs = _G[tip:GetName() .. "TextLeft" .. i]
    local text = fs and fs:GetText()
    if ns.IsSecret(text) then
      lines[#lines + 1] = "<secret>"
    elseif text then
      lines[#lines + 1] = text
      for line in text:gmatch("[^\n]+") do
        if Lay.NodeKind(strtrim((line:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", "")))) then node = true end
      end
    end
  end
  if not node then return end
  local key = table.concat(lines, "/")
  local now = GetTime()
  if Lay.lastHover == key and now - (Lay.lastHoverAt or 0) < 2 then return end
  Lay.lastHover, Lay.lastHoverAt = key, now
  local owner = tip:GetOwner()
  local function name(f) return f and (f.GetName and f:GetName() or tostring(f)) or "nil" end
  ns.Debug.Log("tooltip", { lines = key, owner = name(owner), minimapTip = Lay.IsMinimapTip(tip),
    mouseOver = Minimap and Minimap:IsMouseOver() or false, cursorOn = Lay.CursorOnMinimap(),
    square = ns.GPS and ns.GPS.MinimapTaken and ns.GPS.MinimapTaken() or false })
end

-- A herb or vein just gathered that the map doesn't show (its layer off, or Find Herbs and Ore showing others only):
-- said once a session for each name, so it doesn't look unsaved (2026-11-13: a Copper Vein mined with only Tin Vein
-- picked).
local hiddenSaid = {}
function Lay.SayIfHidden(name, kind)
  if not name or hiddenSaid[name] or Lay.NodeShown(name, kind) then return false end
  hiddenSaid[name] = true
  local st = ns.settings.gps
  if not Lay.VisibleKinds(st)[kind] then
    ns.Print(Format(kind == "herb" and L["%s saved, but the map hides herbs: turn the Herbs layer on to see them."]
      or L["%s saved, but the map hides ore: turn the Ore layer on to see it."], name))
  else
    ns.Print(Format(L["%s saved, but hidden: Find Herbs and Ore shows only the ones you picked."], name))
  end
  return true
end

local function OnTooltip(tip)
  if not Lay.IsMinimapTip(tip) then
    -- the world: remember what's under the mouse (for OnGatherError); units don't count
    if tip.GetUnit and tip:GetUnit() then return end
    local fs = _G[tip:GetName() .. "TextLeft1"]
    local text = fs and fs:GetText()
    if ns.IsSecret(text) then return end -- (hidden from addons: in a dungeon, in combat)
    if text and text ~= "" then
      Lay.NoteWorldObject(strtrim(text), GetTime())
      if not (tip.GetItem and tip:GetItem()) and not (tip.GetSpell and tip:GetSpell()) then
        local fs2 = _G[tip:GetName() .. "TextLeft2"]
        local line2 = fs2 and fs2:GetText()
        if line2 and not ns.IsSecret(line2) then Lay.LearnNode(strtrim(text), strtrim(line2)) end
      end
    end
    return
  end
  local px, py, cont = Geo.RealPlayerWorld() -- (the minimap is round the real player, simulated or not)
  if not px then return end
  local names = {}
  for i = 1, tip:NumLines() do
    local fs = _G[tip:GetName() .. "TextLeft" .. i]
    local text = fs and fs:GetText()
    if text and not ns.IsSecret(text) then
      for line in text:gmatch("[^\n]+") do
        local name = line:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", "")
        name = strtrim(name)
        if Lay.NodeKind(name) then names[#names + 1] = name end
      end
    end
  end
  if #names == 0 then return end
  local mx, my = Minimap:GetCenter()
  local cx, cy = GetCursorPosition()
  local sc = Minimap:GetEffectiveScale()
  local yards = Lay.HoverYards()
  local facing = GetCVar("rotateMinimap") == "1" and Geo.RealFacing() or 0
  local ox, oy = Lay.MinimapOffset(cx / sc - mx, cy / sc - my, Minimap:GetWidth(), yards, facing)
  local any = false
  for _, name in ipairs(names) do any = Lay.AddNode(cont, px + ox, py + oy, name) or any end
  -- (one change for every node seen on the minimap, not one each: the Save button doesn't flicker as the mouse moves)
  if any and ns.MarkUnsaved then ns.MarkUnsaved("nodes:minimap", "add") end
end
Lay.OnTooltip = OnTooltip

function Lay.Init()
  if Lay.frame then return end
  local f = CreateFrame("Frame")
  Lay.frame = f
  f:RegisterEvent("UNIT_SPELLCAST_SENT")
  f:RegisterEvent("UNIT_SPELLCAST_SUCCEEDED")
  f:RegisterEvent("QUEST_LOG_UPDATE")
  f:RegisterEvent("QUEST_ACCEPTED")
  -- (a quest turned in or dropped: its route stops are done, asked 2026-10-06)
  pcall(f.RegisterEvent, f, "QUEST_TURNED_IN")
  pcall(f.RegisterEvent, f, "QUEST_REMOVED")
  pcall(f.RegisterEvent, f, "DYNAMIC_GOSSIP_POI_UPDATED") -- a guard's directions
  -- Asked again for a place the guard already marked: the marker doesn't change, so no
  -- event. A pick that ends the talk (the answer: no more choices, or the window closes)
  -- checks the marker again.
  -- (only with those who have given directions: "Undercity Guardian" and the like)
  local pickedAt = -math.huge
  local guides = {} -- NPC names that marked a place
  if hooksecurefunc and C_GossipInfo then
    for _, fn in ipairs({ "SelectOption", "SelectOptionByIndex" }) do
      if C_GossipInfo[fn] then
        hooksecurefunc(C_GossipInfo, fn, function()
          local npc = UnitName("npc")
          pickedAt = npc and guides[npc] and GetTime() or -math.huge
        end)
      end
    end
  end
  pcall(f.RegisterEvent, f, "GOSSIP_SHOW")
  pcall(f.RegisterEvent, f, "GOSSIP_CLOSED")
  for e in pairs(Lay.NPC_EVENTS) do pcall(f.RegisterEvent, f, e) end -- (NPCs talked to: L.OnNpcWindow)
  pcall(f.RegisterEvent, f, "MERCHANT_UPDATE") -- (a vendor's stock: L.OnMerchantUpdate)
  Lay.gossipPicked = function(event)
    if GetTime() - pickedAt > 2 then return end
    if event == "GOSSIP_SHOW" then
      local opts = C_GossipInfo.GetOptions and C_GossipInfo.GetOptions()
      if opts and #opts > 0 then return end -- (a list of places: not the answer yet)
    end
    pickedAt = -math.huge
    C_Timer.After(0.3, function() Lay.OnGossipPoi(true) end)
  end
  f:RegisterEvent("UI_ERROR_MESSAGE")
  pcall(f.RegisterEvent, f, "LOOT_OPENED") -- (what a node gave: its icon, L.OnLootOpened)
  pcall(f.RegisterEvent, f, "LOOT_READY")
  f:SetScript("OnUpdate", OnUpdate)
  if ns.TimeScript then ns.TimeScript(f, "OnUpdate", "quest areas' frame") end
  f:SetScript("OnEvent", function(_, event, unit, a, b, c)
    if event == "QUEST_TURNED_IN" or event == "QUEST_REMOVED" then -- (questID, ...)
      local id = tonumber(unit)
      if id and ns.Nav and ns.Nav.OnQuestGone then ns.Nav.OnQuestGone(id, QuestTitle(id)) end
      questCache, areaLists = {}, {}
    elseif event == "QUEST_LOG_UPDATE" then
      questCache = {}
      areaLists = {}
      local ids = Lay.LogQuests()
      for _, id in ipairs(ids) do QuestTitle(id) end -- (each title kept, for after it's turned in)
      -- (a quest finished on a quest route without its turn-in: the Sprint icon pulses, Nav's N.CheckQuestsDone)
      if ns.Nav and ns.Nav.CheckQuestsDone then ns.Nav.CheckQuestsDone(ids) end
    elseif event == "DYNAMIC_GOSSIP_POI_UPDATED" then
      local npc = UnitName("npc")
      if npc then guides[npc] = true end
      Lay.RevealCity()
      Lay.OnGossipPoi()
    elseif event == "GOSSIP_SHOW" or event == "GOSSIP_CLOSED" then
      if event == "GOSSIP_SHOW" and C_GossipInfo and C_GossipInfo.GetOptions then
        local ok, opts = pcall(C_GossipInfo.GetOptions)
        if ok and Lay.IsGuardMenu(opts) then Lay.RevealCity() end
        pcall(Lay.OnNpcWindow, event, ok and opts or nil)
      end
      Lay.gossipPicked(event)
    elseif Lay.NPC_EVENTS[event] then
      pcall(Lay.OnNpcWindow, event)
    elseif event == "MERCHANT_UPDATE" then
      pcall(Lay.OnMerchantUpdate)
    elseif event == "QUEST_ACCEPTED" then
      -- on a quest route: it doesn't have the new quest yet
      questCache, areaLists = {}, {}
      if ns.Nav and ns.Nav.OnQuestRoute and ns.Nav.OnQuestRoute() then
        -- (the arrow window shows the Sprint icon until rebuilt; or rebuilt by itself, the option on)
        ns.Nav.MarkQuestRouteStale()
        if not ns.Nav.QuestAutoReroute() then
          ns.Print(L["New quest: click the quest route button (Sprint) again to add it to your route."])
        end
      end
    elseif event == "LOOT_OPENED" or event == "LOOT_READY" then
      pcall(Lay.OnLootOpened, GetTime())
    elseif event == "UI_ERROR_MESSAGE" then -- (errorType, message)
      local px, py, cont = Geo.RealPlayerWorld() -- (where the player really gathers, simulated or not)
      Lay.OnGatherError(a, GetTime(), px, py, cont)
    elseif unit ~= "player" then
      return
    elseif event == "UNIT_SPELLCAST_SENT" then
      -- unit, target name, castGUID, spellID (secret in combat: no gathering then, nothing looked up)
      pcall(Lay.NoteCast, "sent", unit, a, b, c)
      local secret = ns.IsSecret and (ns.IsSecret(a) or ns.IsSecret(b) or ns.IsSecret(c))
      local kind = not secret and GatherKind(c, a) or nil
      local px, py, cont = Geo.RealPlayerWorld()
      pendingCast = kind and px and a and a ~= "" and { guid = b, name = a, kind = kind, x = px, y = py, cont = cont, at = GetTime() } or nil
    elseif event == "UNIT_SPELLCAST_SUCCEEDED" and pendingCast and not (ns.IsSecret and ns.IsSecret(a))
        and a == pendingCast.guid then
      pcall(Lay.NoteCast, "done", unit, pendingCast.name, a, b)
      local p = pendingCast
      pendingCast = nil
      local added = Lay.AddNode(p.cont, p.x, p.y, p.name, p.kind)
      pcall(Lay.NoteGather, p, added)
      pcall(Lay.SayIfHidden, p.name, p.kind)
      lastGather = { name = p.name, at = GetTime() }
      if ns.MarkUnsaved then ns.MarkUnsaved(("node:%s:%.0f:%.0f"):format(tostring(p.cont), p.x, p.y), "add") end
    end
  end)
  if ns.TimeScript then ns.TimeScript(f, "OnEvent", "events (quests, NPCs, herbs and ore)") end
  -- (a tooltip the game hides values of, or anything else odd in it: never an error each frame)
  local function Watch(tip)
    pcall(Lay.NoteHover, tip)
    local ok, err = pcall(OnTooltip, tip)
    if not ok and not Lay.hoverErrorSaid and ns.GPS and ns.GPS.LogError then
      Lay.hoverErrorSaid = true -- (once a session: it runs four times a second)
      ns.GPS.LogError("minimap hover", err)
    end
  end
  GameTooltip:HookScript("OnShow", Watch)
  -- moving across blips changes the tooltip's text without showing it again
  local since = 0
  GameTooltip:HookScript("OnUpdate", function(tip, dt)
    since = since + dt
    if since >= 0.25 then
      since = 0
      Watch(tip)
    end
  end)
  if WorldMapFrame then
    WorldMapFrame:HookScript("OnShow", function() C_Timer.After(0.2, ScrapeWorldMap) end)
    if WorldMapFrame.OnMapChanged then
      hooksecurefunc(WorldMapFrame, "OnMapChanged", function() C_Timer.After(0.2, ScrapeWorldMap) end)
    end
  end
end

---------------------------------------------------------------------------
-- Find Herbs and Ore (asked 2026-11-06): search the herbs and veins by name and pick those to show on the map, the
-- others hidden until Show All. The map menu's "Herbs, Ore and Farming" group has its button (GPSFrame's QUICK).
---------------------------------------------------------------------------

Lay.FINDER_ROWS = 12
Lay.FINDER_ROW_H = 20

-- What the finder's last line says: "Showing all herbs and ore" or the names picked.
function Lay.FilterText()
  local f = Lay.NodeFilter()
  if not f then return L["Showing all herbs and ore you know."] end
  local names = {}
  for name in pairs(f) do names[#names + 1] = name end
  table.sort(names)
  return string.format(L["Showing only: %s"], table.concat(names, ", "))
end

function Lay.ToggleNodeFinder()
  local f = Lay.finder
  if f and f:IsShown() then
    f:Hide()
    return f
  end
  return Lay.ShowNodeFinder()
end

function Lay.ShowNodeFinder()
  local f = Lay.finder
  if not f then
    local W = 300
    f = ns.Window("AzerothGPSNodeFinder", W, 0, L["Find Herbs and Ore"])
    Lay.finder = f
    local hint = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    hint:SetPoint("TOPLEFT", 14, f.top - 4)
    hint:SetPoint("RIGHT", -14, 0)
    hint:SetJustifyH("LEFT")
    hint:SetText(L["Type a name, then click herbs or veins to show only those on the map."])
    local box = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
    box:SetSize(W - 34, 20)
    box:SetPoint("TOPLEFT", 20, f.top - 22)
    box:SetAutoFocus(false)
    box:SetMaxLetters(40)
    f.box = box
    local rows, list, offset = {}, {}, 0
    f.rows = rows
    local listTop = f.top - 48
    for i = 1, Lay.FINDER_ROWS do
      local r = CreateFrame("Button", nil, f)
      r:SetSize(W - 28, Lay.FINDER_ROW_H)
      r:SetPoint("TOPLEFT", 14, listTop - (i - 1) * Lay.FINDER_ROW_H)
      local hl = r:CreateTexture(nil, "HIGHLIGHT")
      hl:SetAllPoints()
      hl:SetColorTexture(1, 1, 1, 0.1)
      r.check = r:CreateTexture(nil, "ARTWORK")
      r.check:SetSize(16, 16)
      r.check:SetPoint("LEFT", 2, 0)
      r.check:SetTexture("Interface\\Buttons\\UI-CheckBox-Check")
      r.icon = r:CreateTexture(nil, "ARTWORK")
      r.icon:SetSize(16, 16) -- (a game icon at its exact size: never a filter above LINEAR)
      r.icon:SetPoint("LEFT", 22, 0)
      r.text = r:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
      r.text:SetPoint("LEFT", r.icon, "RIGHT", 6, 0)
      r.text:SetPoint("RIGHT", -4, 0)
      r.text:SetJustifyH("LEFT")
      r.text:SetWordWrap(false)
      r:SetScript("OnClick", function(self)
        if self.entry then Lay.SetNodeFilter(self.entry.name, not self.entry.picked) end
      end)
      rows[i] = r
    end
    local status = f:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
    status:SetPoint("TOPLEFT", 14, listTop - Lay.FINDER_ROWS * Lay.FINDER_ROW_H - 6)
    status:SetPoint("RIGHT", -14, 0)
    status:SetJustifyH("LEFT")
    status:SetWordWrap(true)
    f.status = status
    local all = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    all:SetSize(100, 22)
    all:SetPoint("BOTTOMRIGHT", -12, 10)
    all:SetText(L["Show All"])
    all:SetScript("OnClick", function() Lay.SetNodeFilter(nil, false) end)
    f.showAll = all
    f:SetHeight(-listTop + Lay.FINDER_ROWS * Lay.FINDER_ROW_H + 74)
    function f.Refresh()
      list = Lay.NodeNames(box:GetText())
      offset = math.max(0, math.min(offset, #list - Lay.FINDER_ROWS))
      for i, r in ipairs(rows) do
        local e = list[offset + i]
        r.entry = e
        if e then
          ns.SetIcon(r.icon, e.icon, "Interface\\Icons\\INV_Misc_QuestionMark")
          r.check:SetShown(e.picked)
          local ore = e.kind == "ore"
          if e.count == 0 then
            r.text:SetText(string.format(ore and L["%s  |cff9d9d9dore, none known|r"] or L["%s  |cff9d9d9dherb, none known|r"], e.name))
          elseif e.count == 1 then
            r.text:SetText(string.format(ore and L["%s  |cff9d9d9dore, 1 known|r"] or L["%s  |cff9d9d9dherb, 1 known|r"], e.name))
          else
            r.text:SetText(Format(ore and L["%s  |cff9d9d9dore, %d known|r"] or L["%s  |cff9d9d9dherb, %d known|r"], e.name, e.count))
          end
          r:Show()
        else
          r:Hide()
        end
      end
      local more = #list > Lay.FINDER_ROWS and string.format(L["  |cff9d9d9d(%d-%d of %d: scroll for more)|r"], offset + 1,
        math.min(#list, offset + Lay.FINDER_ROWS), #list) or ""
      status:SetText((#list == 0 and L["|cff9d9d9dNo herb or vein by that name.|r\n"] or "") .. Lay.FilterText() .. more)
      all:SetEnabled(Lay.NodeFilter() ~= nil)
    end
    f:EnableMouseWheel(true)
    f:SetScript("OnMouseWheel", function(_, delta)
      offset = math.max(0, offset - delta * 3)
      f.Refresh()
    end)
    box:SetScript("OnTextChanged", function()
      offset = 0
      f.Refresh()
    end)
    -- (Enter: the first one picked, or put back)
    box:SetScript("OnEnterPressed", function()
      local e = list[1]
      if e and box:GetText() ~= "" then Lay.SetNodeFilter(e.name, not e.picked) end
    end)
    box:SetScript("OnEscapePressed", function() box:ClearFocus() f:Hide() end)
    local function Quick() if ns.GPS and ns.GPS.RefreshQuick then ns.GPS.RefreshQuick() end end -- (its button lit)
    f:SetScript("OnShow", function() f.Refresh() Quick() end)
    f:SetScript("OnHide", Quick)
    -- (over the map's middle while it shows, the first time)
    local map = _G.AzerothGPSFrame
    if map and map.IsShown and map:IsShown() then
      f:ClearAllPoints()
      f:SetPoint("CENTER", map, "CENTER", 0, 0)
    end
  end
  f:Show()
  f.Refresh()
  f.box:SetFocus()
  return f
end

-- For /agps debug layers.
function Lay.Describe()
  local Q, QL = C_QuestLog, C_QuestLine
  local db = DB() or {}
  local n = 0
  for _, list in pairs(db) do n = n + #list end
  local tmpl = {}
  for t in pairs(Lay.lastTemplates or {}) do tmpl[#tmpl + 1] = t end
  table.sort(tmpl)
  local prof = {}
  for k in pairs(Professions()) do prof[#prof + 1] = k end
  local nAreas = 0
  for _, a in pairs(areas) do if a.segs and #a.segs > 0 then nAreas = nAreas + 1 end end
  local nEmpty, nTracing = 0, 0
  for _, a in pairs(areas) do
    if a.tracing then nTracing = nTracing + 1 elseif a.segs and #a.segs == 0 then nEmpty = nEmpty + 1 end
  end
  local job = jobs[1]
  local here = C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
  local list = here and areaLists[here]
  return string.format("areas: hit test=%s (%s, tried %s s ago) traced=%d empty=%d tracing=%d queued=%d%s"
      .. " combat=%s map=%s quests listed=%d log=%d | ",
    tostring(Lay.hitterName), tostring(Lay.hitterNote), Lay.hitterTried and string.format("%.0f", GetTime() - Lay.hitterTried) or "never",
    nAreas, nEmpty, nTracing, #jobs,
    job and string.format(" (first: quest %d map %d %s %d)", job.quest, job.map, job.phase, job.k or 0) or "",
    tostring(InCombat()), tostring(here), list and #list.quests or -1, #Lay.LogQuests())
    .. string.format("GetQuestsOnMap=%s GetAvailableQuestLines=%s IsQuestTrivial=%s nodes=%d professions=%s worldmap pins=%s",
    tostring(Q and Q.GetQuestsOnMap ~= nil), tostring(QL and QL.GetAvailableQuestLines ~= nil),
    tostring(Q and Q.IsQuestTrivial ~= nil), n, table.concat(prof, ","), table.concat(tmpl, ","))
end

