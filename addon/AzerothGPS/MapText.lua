-- Map data as text, a line each (asked 2026-10-06: herbs, ore, NPCs, pins, roads and walls imported and exported in
-- game, in the Import and Share window): read strictly as data (patterns; never run), within limits, and written the
-- same way. Pure Lua with no game calls, so it loads outside the game too (`chunk("AzerothGPS", ns)`; /way lines need
-- Data/Maps.lua's ns.Maps first):
--   R <add|remove|area> <level> <time> [z=<h>] [indoors=1|0] [down=1] [zs=<h>,<h>,...] <x,y> <x,y> ...
--                                        a road drawn or erased; `zs`: a height per point (1.1.6's road tools)
--   ... [gz=<h|->,<h|->,...] ...         a drawn road's ground heights from the map's data, "-" for none (1.3.10)
--   R stair <level> <time> zs=<h>,<h>,... <x,y> <x,y> ...   stairs (1.1.6): their heights, foot and top at least
--   R <wall|unwall|unwallarea> ...                                                       a wall drawn or erased
--   P add <level> <time> <x,y> [z=<h>] [down=1|0] icon=<file id or path> name=<the rest>  a pin
--   [AzerothGPS Pin: Name (Place) @<level>:<x>,<y>[,z<h>][,down] #<icon>]   a pin's chat tag, anywhere in a line
--   H <level> <x,y> name=<name>          a herb
--   O <level> <x,y> name=<name>          ore
--   N <level> <x,y> name=<name>[ <title>]   an NPC (the title as the game shows it: "<Innkeeper>")
--   /way [zone] <x> <y> [name]           a TomTom waypoint (in zone percent): a stop, a node or an NPC, as the window says
--   T ..., E ..., P remove <time>        Copy Map Data's faster trips, dungeons' ways in and a shared pin's removal:
--                                        known, not imported here (`skipped`)
-- `level`: AzerothGPS's (0 the Eastern Kingdoms, 1 Kalimdor, 2991 Zephras Isle, 10001 Undercity, 20000 + a dungeon's
-- map id); positions in world yards. Header lines ("AzerothGPS map data 1", Copy Map Data's "AzerothGPS roads 1 ...")
-- and blank lines are passed over. Lines are numbered as the player sees them, blank ones too.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local M = {}
ns.MapText = M

M.HEADER = "AzerothGPS map data 1"
M.MAX_LINES = 5000
M.MAX_LINE_BYTES = 65536
M.MAX_POINTS = 2000 -- a road's or a wall's
M.MAX_COORD = 30000 -- yards, either way
M.MAX_Z = 10000
M.NAME_MAX = 160 -- bytes (Pins' NAME_MAX letters, four bytes each at most)
M.ICON_MAX = 200 -- bytes of an icon's path
M.TIME_MAX = 4102444800 -- (seconds: the year 2100; a time past that isn't one)

local function Trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
M.Trim = Trim

-- A plain decimal ("43.2", "-9465", "12."): the number, or nil (no exponent, hex, "inf" or "nan").
local function Num(s)
  if type(s) ~= "string" or not s:match("^%-?%d+%.?%d*$") then return nil end
  return tonumber(s)
end
-- A whole number, or nil.
local function Int(s)
  if type(s) ~= "string" or not s:match("^%-?%d+$") then return nil end
  return tonumber(s)
end
-- "x,y" in world yards, within MAX_COORD: x, y; or nil.
local function XY(s)
  local a, b = (s or ""):match("^([^,]+),([^,]+)$")
  local x, y = Num(a), Num(b)
  if not (x and y) or math.abs(x) > M.MAX_COORD or math.abs(y) > M.MAX_COORD then return nil end
  return x, y
end
local function Words(s)
  local w = {}
  for p in s:gmatch("%S+") do w[#w + 1] = p end
  return w
end
-- (a bit of what was read, for a message)
local function Short(s)
  s = tostring(s or ""):gsub("|", "")
  return #s > 24 and (s:sub(1, 24) .. "...") or s
end

-- A name as kept and shared: one line, no escape codes ("|"), trimmed, at most NAME_MAX bytes (not cut in the middle
-- of a letter); "" when nothing's left.
function M.CleanName(s)
  s = Trim(tostring(s or ""):gsub("|", ""):gsub("%c", " "))
  if #s > M.NAME_MAX then
    s = s:sub(1, M.NAME_MAX)
    local i = #s -- (a letter cut short at the end: left out)
    while i > 0 and s:byte(i) >= 128 and s:byte(i) < 192 do i = i - 1 end
    if i > 0 then
      local b = s:byte(i)
      local need = b >= 240 and 4 or b >= 224 and 3 or b >= 192 and 2 or 1
      if #s - i + 1 < need then s = s:sub(1, i - 1) end
    end
    s = Trim(s)
  end
  return s
end

-- An icon as shared: a file id (a whole number), or a path of letters, digits and _ - . \ /; else nil.
function M.Icon(v)
  if type(v) == "number" then return (v >= 1 and v < 2 ^ 31 and v % 1 == 0) and v or nil end
  if type(v) ~= "string" then return nil end
  local n = Int(v)
  if n then return M.Icon(n) end
  if #v > M.ICON_MAX or v:match("^[%d%.%-]+$") or not v:match("^[%w_%-%.\\/]+$") then return nil end
  return v
end

-- Whether `level` is one AzerothGPS has: an underground city's or a dungeon's (ns.CityLevels), or a continent
-- (ns.Maps). Outside the game without that data: the levels it ships.
local conts, contsOf -- (the continents in ns.Maps, worked out once per Maps table)
function M.KnownLevel(level)
  if type(level) ~= "number" or level % 1 ~= 0 then return false end
  if ns.CityLevels then
    if ns.CityLevels[level] then return true end
  elseif level == 10001 or (level > 20000 and level < 30000) then
    return true
  end
  if ns.Maps then
    if contsOf ~= ns.Maps then
      conts, contsOf = {}, ns.Maps
      -- (a continent's map, or a zone's: Zephras Isle (2991) has zones only, no continent map, and a player's own
      -- herbs there were "unknown level '2991'" when pasted back in, 2026-10-06)
      for _, m in pairs(ns.Maps) do
        if (m.type == 2 or m.type == 3) and m.continent then conts[m.continent] = true end
      end
    end
    return conts[level] == true
  end
  return level == 0 or level == 1 or level == 2991
end

-- The lines of `text` as the player sees them (blank ones too; "\r\n", "\r" or "\n" between them).
function M.SplitLines(text)
  local out = {}
  text = tostring(text or ""):gsub("\r\n?", "\n")
  for line in (text .. "\n"):gmatch("([^\n]*)\n") do out[#out + 1] = line end
  if out[#out] == "" then out[#out] = nil end -- (text ending in a line break: no line after it)
  return out
end

-- The uiMap named `name` (any case; a unique beginning of a name also works, e.g. "elwynn"). Several maps can share
-- a name: the one with art and bounds, most detailed.
function M.FindMap(name)
  local want = Trim(name):lower()
  if want == "" then return nil end
  local exact, prefix = {}, {}
  for id, m in pairs(ns.Maps or {}) do
    if m.bounds and m.name then
      local n = m.name:lower()
      if n == want then exact[#exact + 1] = id
      elseif n:sub(1, #want) == want then prefix[#prefix + 1] = id end
    end
  end
  local function best(list)
    table.sort(list, function(a, b)
      local ma, mb = ns.Maps[a], ns.Maps[b]
      if (ma.tiles ~= nil) ~= (mb.tiles ~= nil) then return ma.tiles ~= nil end
      if (ma.type or 0) ~= (mb.type or 0) then return (ma.type or 0) > (mb.type or 0) end
      return a < b
    end)
    return list[1]
  end
  if #exact > 0 then return best(exact) end
  -- a beginning that names one place only
  local names = {}
  for _, id in ipairs(prefix) do names[ns.Maps[id].name] = true end
  local count = 0
  for _ in pairs(names) do count = count + 1 end
  if count == 1 then return best(prefix) end
  return nil
end

-- A number token of a /way line ("43.2", "43.2,", ",65.1"): the number, or nil.
local function WayNum(tok)
  if not tok then return nil end
  return Num((tok:gsub("^,", ""):gsub(",$", "")))
end
-- A TomTom waypoint line ("/way [zone] x y [text]", "/way #mapID x y [text]", with or without "/way"):
-- { mapID, x, y (0-100), name }, nil (a blank line), or nil and why.
function M.ParseWay(line, currentMap)
  local s = Trim(line or "")
  s = s:gsub("^/[tT]?[wW][aA][yY]%s*", "")
  if s == "" then return nil end
  local toks = Words(s)
  -- the coordinates: the first two numbers in a row
  local at
  for i = 1, #toks - 1 do
    if WayNum(toks[i]) and WayNum(toks[i + 1]) then
      at = i
      break
    end
  end
  if not at then return nil, L["no coordinates"] end
  local x, y = WayNum(toks[at]), WayNum(toks[at + 1])
  local zone = Trim(table.concat(toks, " ", 1, at - 1)):gsub(",$", "")
  local text = Trim(table.concat(toks, " ", at + 2))
  local mapID
  if zone == "" then
    mapID = currentMap
    if not mapID then return nil, L["no zone, and your current zone is unknown"] end
  elseif zone:match("^#%d+$") then
    mapID = tonumber(zone:sub(2))
  else
    mapID = M.FindMap(zone)
    if not mapID then return nil, string.format(L["unknown zone '%s'"], Short(zone)) end
  end
  if x < 0 or x > 100 or y < 0 or y > 100 then return nil, L["coordinates must be 0-100"] end
  return { mapID = mapID, x = x, y = y, name = text ~= "" and text or nil }
end

-- A pin's chat tag's text (between "[AzerothGPS Pin: " and "]", Import.PinTag's), checked: { level, x, y, z, down,
-- icon, name, place }, or nil. `wholeName`: the text before " @" is all name (a link's: no place in brackets after it).
function M.ParsePinTag(inner, wholeName)
  if type(inner) ~= "string" or #inner > M.MAX_LINE_BYTES then return nil end
  local head, level, x, y, rest = inner:match("^(.-) @(%-?%d+):(%-?[%d%.]+),(%-?[%d%.]+)(.*)$")
  if not head then return nil end
  level, x, y = Int(level), Num(x), Num(y)
  if not (level and x and y) or math.abs(x) > M.MAX_COORD or math.abs(y) > M.MAX_COORD or not M.KnownLevel(level) then
    return nil
  end
  local z = Num(rest:match(",z(%-?[%d%.]+)"))
  if z and math.abs(z) > M.MAX_Z then return nil end
  local down = rest:find(",down", 1, true) ~= nil
  local icon = M.Icon(rest:match("#(%S+)%s*$"))
  local place = not wholeName and head:match(" %(([^()]*)%)$") or nil
  local name = wholeName and head or head:gsub(" %([^()]*%)$", "")
  name = M.CleanName(name)
  place = place and M.CleanName(place) or nil
  return { level = level, x = x, y = y, z = z, down = down or nil, icon = icon, name = name ~= "" and name or L["Pin"],
    place = place ~= "" and place or nil }
end

-- The level and time words of an R or P line, checked: level, time; or nil and why.
local function LevelTime(lw, tw)
  local level, t = Int(lw), Int(tw)
  if not level or not M.KnownLevel(level) then return nil, string.format(L["unknown level '%s'"], Short(lw)) end
  if not t or t < 1 or t > M.TIME_MAX then return nil, string.format(L["not a time '%s'"], Short(tw)) end
  return level, t
end

local ROAD_OPS = { add = "add", remove = "remove", area = "remove", wall = "wall", unwall = "unwall", unwallarea = "unwall",
  stair = "add" }
-- One line: its kind ("road", "wall", "pin", "herb", "ore", "npc", "way") and what it holds; "skip" (known, not
-- imported here); nil (blank, a header); or false and why it can't be read.
function M.ParseLine(line, currentMap)
  if type(line) ~= "string" then return nil end
  if #line > M.MAX_LINE_BYTES then return false, L["longer than AzerothGPS reads"] end
  line = Trim(line)
  if line == "" or line:find("^AzerothGPS map data") or line:find("^AzerothGPS roads") then return nil end
  local w = Words(line)
  local k = w[1]
  if k == "R" then
    local op = ROAD_OPS[w[2] or ""]
    if not op then return false, L["not a road or wall"] end
    local level, t = LevelTime(w[3], w[4])
    if not level then return false, t end
    local e = { op = op, area = (w[2] == "area" or w[2] == "unwallarea") or nil, stair = w[2] == "stair" or nil,
      level = level, time = t, pts = {} }
    for i = 5, #w do
      local key, v = w[i]:match("^(%a+)=(.*)$")
      if key == "zs" then -- (a height per point)
        e.zs = {}
        for h in (v .. ","):gmatch("([^,]*),") do
          local z = Num(h)
          if not z or math.abs(z) > M.MAX_Z or #e.zs >= M.MAX_POINTS then return false, L["not a list of heights"] end
          e.zs[#e.zs + 1] = z
        end
      elseif key == "gz" then -- (the ground's heights from the map's data: "-" for none)
        e.gz = {}
        for h in (v .. ","):gmatch("([^,]*),") do
          local z = h == "-" and false or Num(h)
          if z == nil or (z and math.abs(z) > M.MAX_Z) or #e.gz >= M.MAX_POINTS then return false, L["not a list of heights"] end
          e.gz[#e.gz + 1] = z
        end
      elseif key == "z" then
        e.z = Num(v)
        if not e.z or math.abs(e.z) > M.MAX_Z then return false, L["not a height"] end
      elseif key == "indoors" then
        e.indoors = v == "1"
      elseif key == "down" then
        e.down = v == "1" or nil
      elseif not key then -- (other keys: a newer version's, passed over)
        if #e.pts >= M.MAX_POINTS * 2 then return false, string.format(L["more than %d points"], M.MAX_POINTS) end
        local x, y = XY(w[i])
        if not x then return false, string.format(L["not a point '%s'"], Short(w[i])) end
        e.pts[#e.pts + 1], e.pts[#e.pts + 2] = x, y
      end
    end
    if #e.pts < 4 then return false, L["fewer than 2 points"] end
    if e.zs and #e.zs ~= #e.pts / 2 then return false, L["its heights don't match its points"] end
    if e.gz and #e.gz ~= #e.pts / 2 then e.gz = nil end -- (the ground's: only a help, left out when off)
    if e.stair and not e.zs then return false, L["stairs need their heights"] end
    return (op == "wall" or op == "unwall") and "wall" or "road", e
  elseif k == "P" then
    if w[2] == "remove" then return "skip" end -- (a shared pin taken off: the addon's data has none to take)
    if w[2] ~= "add" then return false, L["not a pin"] end
    local head, name = line:match("^(.-) name=(.*)$")
    local hw = Words(head or line)
    local level, t = LevelTime(hw[3], hw[4])
    if not level then return false, t end
    local x, y = XY(hw[5])
    if not x then return false, L["no position"] end
    local p = { level = level, time = t, x = x, y = y }
    for i = 6, #hw do
      local key, v = hw[i]:match("^(%a+)=(.*)$")
      if key == "z" then
        p.z = Num(v)
        if not p.z or math.abs(p.z) > M.MAX_Z then return false, L["not a height"] end
      elseif key == "down" then
        p.down = v == "1"
      elseif key == "icon" then
        p.icon = M.Icon(v) -- (not one: the default icon)
      end
    end
    name = M.CleanName(name)
    p.name = name ~= "" and name or L["Pin"]
    return "pin", p
  elseif k == "H" or k == "O" or k == "N" then
    local head, name = line:match("^(.-) name=(.*)$")
    if not head then return false, L["no name"] end
    local hw = Words(head)
    if #hw ~= 3 then return false, string.format(L["not '%s <level> <x,y> name=...'"], k) end
    local level = Int(hw[2])
    if not level or not M.KnownLevel(level) then return false, string.format(L["unknown level '%s'"], Short(hw[2])) end
    local x, y = XY(hw[3])
    if not x then return false, L["no position"] end
    local title
    if k == "N" then
      local n, tt = name:match("^(.-)%s*<([^<>]*)>%s*$")
      if n then
        name, title = n, M.CleanName(tt)
        if title == "" then title = nil end
      end
    end
    name = M.CleanName(name)
    if name == "" then return false, L["no name"] end
    return k == "H" and "herb" or k == "O" and "ore" or "npc", { level = level, x = x, y = y, name = name, title = title }
  elseif k == "T" or k == "E" then
    return "skip" -- (a faster trip or a dungeon's way in: for the developer's tools, not imported here)
  end
  local wp, why = M.ParseWay(line, currentMap)
  if wp then return "way", wp end
  if not line:find("^/[tT]?[wW][aA][yY]") and why == L["no coordinates"] then why = nil end -- (not a waypoint at all)
  return false, why or L["not a line AzerothGPS reads"]
end

-- The lines' kinds' lists in M.Parse's result.
M.LISTS = { road = "roads", wall = "walls", pin = "pins", herb = "herbs", ore = "ore", npc = "npcs", way = "ways" }
-- All of `text`: { roads, walls, pins, herbs, ore, npcs, ways (lists of what each line holds, with its `line`),
-- rejected = { { line = n, why = "..." }, ... }, skipped = the lines known but not imported here (T, E, P remove; not
-- blank or header lines), lines = how many were read }. Past MAX_LINES the rest is left out (rejected once).
function M.Parse(text, currentMap)
  local out = { roads = {}, walls = {}, pins = {}, herbs = {}, ore = {}, npcs = {}, ways = {}, rejected = {}, skipped = 0,
    lines = 0 }
  for n, line in ipairs(M.SplitLines(text)) do
    if n > M.MAX_LINES then
      if Trim(line) ~= "" then
        out.rejected[#out.rejected + 1] = { line = n, why = string.format(L["past %d lines: the rest left out"], M.MAX_LINES) }
        break
      end
    else
      out.lines = n
      local tags = 0
      for inner in line:gmatch("%[AzerothGPS Pin: ([^%]]+)%]") do -- (pins' chat tags, a line from chat)
        tags = tags + 1
        local p = M.ParsePinTag(inner)
        if p then
          p.line = n
          out.pins[#out.pins + 1] = p
        else
          out.rejected[#out.rejected + 1] = { line = n, why = L["a pin AzerothGPS can't read"] }
        end
      end
      if tags == 0 then
        local kind, rec = M.ParseLine(line, currentMap)
        if kind == false then
          out.rejected[#out.rejected + 1] = { line = n, why = rec }
        elseif kind == "skip" then
          out.skipped = out.skipped + 1
        elseif kind then
          rec.line = n
          local list = out[M.LISTS[kind]]
          list[#list + 1] = rec
        end
      end
    end
  end
  return out
end
-- A rejected line as the window says it.
function M.Why(r) return string.format(L["Line %d: %s"], r.line, r.why) end


-- Lines out (what Copy Map Data and the window's Copy My Map Data write: the same lines M.Parse reads).
-- A road or wall drawn or erased (Record's: op, continent, time, pts, area, z, indoors, down).
function M.RoadLine(t)
  local op = t.op == "remove" and (t.area and "area" or "remove")
    or t.op == "wall" and "wall" or t.op == "unwall" and (t.area and "unwallarea" or "unwall") or t.stair and "stair" or "add"
  local line = { "R", op, tostring(t.continent or 0), tostring(t.time or 0) }
  -- (its floor, where floors lie over each other: "z=<height>", "indoors=1|0", "down=1")
  if t.z then line[#line + 1] = string.format("z=%.1f", t.z) end
  if t.indoors ~= nil then line[#line + 1] = t.indoors and "indoors=1" or "indoors=0" end
  if t.down then line[#line + 1] = "down=1" end
  if type(t.zs) == "table" and #t.zs == #t.pts / 2 then
    local hs = {}
    for i, h in ipairs(t.zs) do hs[i] = string.format("%.1f", h) end
    line[#line + 1] = "zs=" .. table.concat(hs, ",")
  end
  -- (a drawn road's ground heights from the map's data, 1.3.10: "-" where it had none)
  if type(t.gz) == "table" and #t.gz == #t.pts / 2 then
    local hs = {}
    for i, h in ipairs(t.gz) do hs[i] = type(h) == "number" and string.format("%.1f", h) or "-" end
    line[#line + 1] = "gz=" .. table.concat(hs, ",")
  end
  for i = 1, #t.pts - 1, 2 do line[#line + 1] = string.format("%.1f,%.1f", t.pts[i], t.pts[i + 1]) end
  return table.concat(line, " ")
end
-- A pin (level, time, x, y, z, down, icon, name); `defaultIcon` for one with none.
function M.PinLine(p, defaultIcon)
  local out = { "P", "add", tostring(p.level or 0), tostring(p.time), string.format("%.1f,%.1f", p.x, p.y) }
  if p.z then out[#out + 1] = string.format("z=%.1f", p.z) end
  if p.down ~= nil then out[#out + 1] = p.down and "down=1" or "down=0" end
  out[#out + 1] = "icon=" .. (tostring(p.icon or defaultIcon or ""):gsub("%s", ""))
  local name = M.CleanName(p.name)
  out[#out + 1] = "name=" .. (name ~= "" and name or "Pin")
  return table.concat(out, " ")
end
-- A herb or ore node (`kind` "herb" or "ore") at (x, y) on `level`.
function M.NodeLine(kind, level, x, y, name)
  return string.format("%s %d %.1f,%.1f name=%s", kind == "ore" and "O" or "H", level, x, y, M.CleanName(name))
end
-- An NPC at (x, y) on `level`, its title (or nil).
function M.NpcLine(level, x, y, name, title)
  local n = (M.CleanName(name):gsub("[<>]", ""))
  local t = title and (M.CleanName(title):gsub("[<>]", "")) or ""
  return string.format("N %d %.1f,%.1f name=%s%s", level, x, y, n, t ~= "" and (" <" .. t .. ">") or "")
end
