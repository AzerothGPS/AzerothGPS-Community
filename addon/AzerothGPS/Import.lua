-- Import waypoints written for TomTom ("/way Elwynn Forest 43.2 65.1 First Stop"), as
-- route stops: a window opened from the GPS's "+" button, and /way itself when TomTom
-- isn't installed. The parsing is pure Lua (unit-tested).
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format
local Geo = ns.Geo

local I = {}
ns.Import = I

local function Trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

-- The uiMap named `name` (any case; a unique beginning of a name also works, e.g. "elwynn"): MapText's.
function I.FindMap(name) return ns.MapText.FindMap(name) end

-- One line: { mapID, x, y (0-100), name } or nil, error message (MapText.ParseWay).
-- Accepts "/way [zone] x y [text]", "/way #mapID x y [text]", with or without "/way".
function I.ParseLine(line, currentMap) return ns.MapText.ParseWay(line, currentMap) end

-- A waypoint as a stop: { x, y, cont, name } in world coordinates, or nil, error. One with no name of its own is
-- named by its zone and spot, and marked `unnamed` (not a herb's or an NPC's name).
function I.ToStop(w)
  local m = ns.Maps and ns.Maps[w.mapID]
  local b = m and m.bounds
  if not b then return nil, L["no map data for that zone"] end
  local u, v = w.x / 100, w.y / 100
  local name = w.name or string.format("%s %.1f, %.1f", m.name or "?", w.x, w.y)
  return { x = b[3] - v * (b[3] - b[1]), y = b[4] - u * (b[4] - b[2]), cont = Geo.MapCont(w.mapID), name = name,
    unnamed = not w.name or nil }
end

-- All lines: stops, and { "Line n: error", ... } for the ones that couldn't be read (lines numbered as seen, blank
-- ones too).
function I.Parse(text, currentMap)
  local stops, errors = {}, {}
  for n, line in ipairs(ns.MapText.SplitLines(text)) do
    local w, err = I.ParseLine(line, currentMap)
    local stop
    if w then stop, err = I.ToStop(w) end
    if stop then
      stops[#stops + 1] = stop
    elseif err then
      errors[#errors + 1] = string.format(L["Line %d: %s"], n, err)
    end
  end
  return stops, errors
end

-- A map pin link from chat ("worldmap:<uiMapID>:<x>:<y>", x and y in 1/10000 of the
-- map): { cont, x, y, name } in world coordinates, or nil.
function I.ParseMapPin(link)
  local mapID, u, v = link:match("^worldmap:(%d+):(%d+):(%d+)")
  mapID, u, v = tonumber(mapID), tonumber(u), tonumber(v)
  local m = mapID and ns.Maps and ns.Maps[mapID]
  local b = m and m.bounds
  if not (b and u and v) then return nil end
  u, v = u / 10000, v / 10000
  if u < 0 or u > 1 or v < 0 or v > 1 then return nil end
  return { cont = Geo.MapCont(mapID), x = b[3] - v * (b[3] - b[1]), y = b[4] - u * (b[4] - b[2]),
    name = string.format(L["Map pin (%s %.1f, %.1f)"], m.name or "?", u * 100, v * 100) }
end

-- The chat box being typed in, or nil.
function I.ChatBox()
  local box = (ChatEdit_GetActiveWindow and ChatEdit_GetActiveWindow())
    or (ChatFrameUtil and ChatFrameUtil.GetActiveWindow and ChatFrameUtil.GetActiveWindow())
  return box or nil
end

-- The map pin (asked 2026-10-01: as the game's world map does it): one diamond on the map, the game's own
-- waypoint (C_Map's user waypoint) where the client has one. Ctrl + left-click on the map puts it there,
-- Shift + left-click on it links it in chat, Ctrl + left-click on it takes it away. Not a custom pin: never
-- in the shared map data. Kept per character (cdb.mapPin: { cont, x, y }, world), so it lasts over reloads
-- and logouts, and put back as the game's waypoint at login when the game has none. The game's waypoint
-- set or cleared elsewhere (its world map, a link clicked) moves the pin with it.
local syncing -- (our own change of the game's waypoint: not taken back in from its event)

function I.MapPin()
  local cdb = ns.db and ns.CharDB and ns.CharDB()
  return cdb and cdb.mapPin or nil
end

local function Redraw()
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end

-- The spot as the game's map point: uiMapID, x, y (0-1), on a zone's (or city's) map; not in a dungeon's.
local function MapPoint(cont, x, y)
  local G = ns.GPS
  if not (cont and cont < 20000 and G and G.LocateWorld) then return nil end
  local mapID, _, u, v = G.LocateWorld(Geo.Base(cont), x, y)
  return mapID, u, v
end

function I.SetMapPin(cont, x, y)
  if not (cont and cont < 20000) then return false end
  ns.CharDB().mapPin = { cont = Geo.Base(cont), x = x, y = y }
  local mapID, u, v = MapPoint(cont, x, y)
  if mapID and C_Map and C_Map.SetUserWaypoint and UiMapPoint then
    syncing = true
    pcall(C_Map.SetUserWaypoint, UiMapPoint.CreateFromCoordinates(mapID, u, v))
    syncing = false
  end
  Redraw()
  return true
end

function I.ClearMapPin()
  ns.CharDB().mapPin = nil
  if C_Map and C_Map.ClearUserWaypoint then
    syncing = true
    pcall(C_Map.ClearUserWaypoint)
    syncing = false
  end
  Redraw()
end

-- The pin's chat link ("[Map Pin Location]"): the game's for its waypoint, else made the same way.
function I.MapPinLink()
  local p = I.MapPin()
  if not p then return nil end
  if C_Map and C_Map.HasUserWaypoint and C_Map.GetUserWaypointHyperlink then
    local ok, has = pcall(C_Map.HasUserWaypoint)
    if ok and has then
      local okL, link = pcall(C_Map.GetUserWaypointHyperlink)
      if okL and link then return link end
    end
  end
  return I.PointLink(p.cont, p.x, p.y)
end
-- The game's map pin link ("[Map Pin Location]", worldmap:<uiMapID>:<x>:<y>) for a spot: the zone map it's on, as
-- the game makes them; nil off any zone map (a dungeon's).
function I.PointLink(cont, x, y)
  local mapID, u, v = MapPoint(cont, x, y)
  if not mapID then return nil end
  return string.format("|cffffff00|Hworldmap:%d:%d:%d|h[%s]|h|r", mapID,
    math.floor(u * 10000 + 0.5), math.floor(v * 10000 + 0.5), L["Map Pin Location"])
end

-- Shift + left-click on the pin: its link in the chat box being typed in, else a chat box opened with it.
function I.LinkMapPin()
  return I.InsertLink(I.MapPinLink())
end
-- A link in the chat box being typed in, else a chat box opened with it.
function I.InsertLink(link)
  if not link then return false end
  if I.ChatBox() then
    if ChatFrameUtil and ChatFrameUtil.InsertLink then
      ChatFrameUtil.InsertLink(link)
    elseif ChatEdit_InsertLink then
      ChatEdit_InsertLink(link)
    else
      I.ChatBox():Insert(link)
    end
  elseif ChatFrameUtil and ChatFrameUtil.OpenChat then
    ChatFrameUtil.OpenChat(link)
  elseif ChatFrame_OpenChat then
    ChatFrame_OpenChat(link)
  else
    return false
  end
  return true
end

-- The game's waypoint changed (USER_WAYPOINT_UPDATED): the pin follows it.
function I.OnUserWaypoint()
  if syncing or not (C_Map and C_Map.HasUserWaypoint and ns.db) then return end
  local cdb = ns.CharDB()
  local ok, has = pcall(C_Map.HasUserWaypoint)
  if not ok then return end
  if has then
    local okW, wp = pcall(C_Map.GetUserWaypoint)
    local pos = okW and wp and wp.position
    local x, y, cont
    if pos and ns.Layers and ns.Layers.MapToWorld then x, y, cont = ns.Layers.MapToWorld(wp.uiMapID, pos.x, pos.y) end
    if x and cont then cdb.mapPin = { cont = Geo.Base(cont), x = x, y = y } end
  else
    cdb.mapPin = nil
  end
  Redraw()
end

-- At login: the saved pin back as the game's waypoint, when the game has none.
function I.RestoreMapPin()
  local p = I.MapPin()
  if not (p and C_Map and C_Map.HasUserWaypoint) then return end
  local ok, has = pcall(C_Map.HasUserWaypoint)
  if ok and not has then I.SetMapPin(p.cont, p.x, p.y) end
end

-- A map pin link clicked in chat (hooked on SetItemRef): a stop there (option acceptMapPins; asked
-- 2026-10-01: a plain click, it used to take Shift), but not a Shift-click with a chat box open, which is
-- the game's "put it in the chat". Whether `link` was a map pin.
function I.OnMapPinLink(link)
  local pin = type(link) == "string" and I.ParseMapPin(link)
  if not pin then return false end
  local relink = IsModifiedClick and IsModifiedClick("CHATLINK") and I.ChatBox()
  local st = ns.settings and ns.settings.gps
  if not relink and not (st and st.acceptMapPins == false) then I.AddMapPin(pin) end
  return true
end

-- A shared map pin as a stop: added to the route (or a new route), with the route tour on
-- an open map (see GPS.RouteChanged).
function I.AddMapPin(pin)
  local N = ns.Nav
  local stop = { cont = pin.cont, x = pin.x, y = pin.y, name = pin.name, tex = pin.tex, z = pin.z }
  if #N.stops > 0 then
    local ok, asked = N.AddStop(stop, ns.settings and ns.settings.gps.fastestOrder)
    if not ok then
      if not asked then ns.Print(string.format(L["Map pin: the route is full (%d stops at most)."], N.MAX_STOPS)) end
      return
    end
  elseif N.SetStops({ stop }) == false then
    return -- (held off, or asked first: a zone too high for the character)
  end
  ns.Print(string.format(L["%s added to your route."], pin.name))
  if ns.GPS and ns.GPS.RouteChanged then ns.GPS.RouteChanged() end
end

-- Make them the route (or add them to it). Returns how many stops were set. Every list of stops brought in goes
-- through here: the window's Import, /way lines (typed, or several pasted in chat) and a route another player sent.
-- With "Route in the listed order" (gps.importKeepOrder; asked for 1.3.9) they go in the order listed, never the
-- fastest (Nav.keepOrder: nor reordered on the way); added to a route already in its listed order, at its end too.
function I.KeepsOrder(add)
  local st = ns.settings and ns.settings.gps
  local N = ns.Nav
  return (st and st.importKeepOrder) and true or (add and N.keepOrder and #N.stops > 0) or false
end

function I.Apply(stops, add)
  local N = ns.Nav
  local keep = I.KeepsOrder(add)
  local list = {}
  if add then
    for _, d in ipairs(N.stops) do list[#list + 1] = d end
  end
  local max = N.MAX_STOPS
  for _, d in ipairs(stops) do
    if #list >= max then break end
    d.icon = N.NextMarker(list)
    list[#list + 1] = d
  end
  N.SetStops(list, ns.settings and ns.settings.gps.fastestOrder and not keep, nil, keep)
  if keep and I.TellOrder then I.TellOrder() end
  return #list
end

---------------------------------------------------------------------------
-- Export and share
---------------------------------------------------------------------------

-- A stop as a TomTom line, "/way Durotar 52.3 41.8 Razor Hill": the zone by name, or as
-- "#mapID" when that name would pick another map. nil when no zone map covers it.
function I.WayLine(d)
  local id, name, mx, my = ns.GPS.LocateWorld(Geo.Base(d.cont), d.x, d.y) -- (a city level: its continent's maps)
  if not id then return nil end
  local zone = I.FindMap(name) == id and name or ("#" .. id)
  local line = string.format("/way %s %.1f %.1f", zone, mx * 100, my * 100)
  if d.name then line = line .. " " .. d.name:gsub("[\r\n]", " ") end
  return line
end

-- One line of text (a stop's /way line, GPS.CopyStopWay) in a small window, selected: Ctrl+C copies it, then
-- "Copied!" in green and the window closes (asked 2026-11-09: copied at once; an addon can't: CopyToClipboard is
-- HasRestrictions in this client's API docs, OsDocumentation, forbidden to addons). Escape or the close button too.
I.COPIED_CLOSE = 0.7 -- seconds "Copied!" shows before the window closes
local copyLine
function I.ShowCopyLine(text)
  if not copyLine then
    local f = ns.Window("AzerothGPSCopyLine", 440, 104, L["Copy /way Line"], "FULLSCREEN_DIALOG")
    local edit = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
    edit:SetPoint("TOPLEFT", 22, f.top - 10)
    edit:SetPoint("TOPRIGHT", -18, f.top - 10)
    edit:SetHeight(22)
    edit:SetAutoFocus(false)
    edit:SetFontObject(ChatFontNormal)
    edit:SetScript("OnEscapePressed", function() f:Hide() end)
    edit:SetScript("OnEnterPressed", function() f:Hide() end)
    -- (read only: typing puts the text back; a click selects it all again)
    edit:SetScript("OnTextChanged", function(self, user)
      if user then
        self:SetText(f.text or "")
        self:HighlightText()
      end
    end)
    edit:SetScript("OnMouseUp", function(self) self:HighlightText() end)
    edit:SetScript("OnKeyDown", function(_, key) -- (Ctrl+C: the game copies it; then "Copied!" and closed)
      if key == "C" and IsControlKeyDown and IsControlKeyDown() then I.CopiedLine() end
    end)
    local hint = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    hint:SetPoint("TOPLEFT", edit, "BOTTOMLEFT", -4, -8)
    hint:SetText(L["Press |cffffd100Ctrl+C|r to copy it (it's all selected), then paste it anywhere."])
    local copied = f:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
    copied:SetPoint("TOPLEFT", edit, "BOTTOMLEFT", -4, -6)
    copied:SetTextColor(0.2, 1, 0.2)
    copied:SetText(L["Copied!"])
    copied:Hide()
    f.edit, f.hint, f.copied = edit, hint, copied
    copyLine = f
  end
  copyLine.text = text
  copyLine.copiedAt = nil
  copyLine.hint:Show()
  copyLine.copied:Hide()
  copyLine:Show()
  copyLine:Raise()
  copyLine.edit:SetText(text)
  copyLine.edit:SetFocus()
  copyLine.edit:HighlightText()
  copyLine.edit:SetCursorPosition(0)
  copyLine.edit:HighlightText()
  return copyLine
end

-- Ctrl+C pressed in the copy box: "Copied!" in green, then the window closes (unless another line was shown since).
function I.CopiedLine()
  local f = copyLine
  if not f then return end
  f.hint:Hide()
  f.copied:Show()
  local at = GetTime()
  f.copiedAt = at
  local function Close() if f.copiedAt == at then f:Hide() end end
  if C_Timer and C_Timer.After then C_Timer.After(I.COPIED_CLOSE, Close) else Close() end
end

-- The stops as /way lines (one per line), and how many couldn't be written.
function I.ExportText(stops)
  local lines, skipped = {}, 0
  for _, d in ipairs(stops) do
    local line = I.WayLine(d)
    if line then lines[#lines + 1] = line else skipped = skipped + 1 end
  end
  return table.concat(lines, "\n"), skipped
end

-- In game, to other AzerothGPS users, as a link (asked 2026-10-02: like a map pin's, so nothing pops up
-- unasked and nobody's navigation is interrupted). Sharing puts a short line in your chat box,
-- "[AzerothGPS Route 1a2b3c: 3 stops]", sent when you press Enter: plain text for players without
-- AzerothGPS, a link for those with it. Clicking the link asks you for the route (an addon whisper,
-- "?\tid"), and only then are its stops sent, to that player alone: one addon message per stop,
-- "version \t id \t i \t n \t cont \t x \t y \t name". Stops nobody asked for are ignored, and nothing
-- is used until they accept.
-- Asking a group member for their route (asked 2026-10-06; a right-click on their icon on the map): an addon whisper
-- "!\troute?"; they're asked whether to send it, and their stops come as above (any route id, the first one), else
-- "!\tno" (not sent) or "!\tnone" (no route). Only from players in your group, once in ROUTE_ASK_GAP seconds each.
I.PREFIX = "AzerothGPS"
I.SHARE_TIMEOUT = 30 -- seconds to wait for a route's remaining stops
I.ROUTE_ASK_GAP = 10
I.ASK_TIMEOUT = 30 -- seconds a clicked link's route is waited for
I.POSTED_MAX = 5 -- routes linked lately that are still answered for
I.POSTED_TTL = 3600 -- (an hour each)
I.ANSWER_GAP = 5 -- seconds before the same player gets the same route again
local SHARE_VERSION = "1"
-- Stops sent in game (the next ones): addon messages are rate limited, and the other
-- player's popup lists them all. Copy as /way has no limit.
I.MAX_SHARE = 8

function I.ShareMessages(stops, id)
  local msgs, n = {}, math.min(#stops, I.MAX_SHARE)
  for i = 1, n do
    local d = stops[i]
    local name = (d.name or ""):gsub("[\t\r\n|]", " "):sub(1, 120)
    msgs[i] = string.format("%s\t%s\t%d\t%d\t%d\t%.1f\t%.1f\t%s", SHARE_VERSION, id, i, n, d.cont, d.x, d.y, name)
  end
  return msgs
end

local function KnownContinent(cont) return ns.MapText.KnownLevel(cont) end

local incoming = {} -- [sender] = { id, n, got, stops, t }

-- One received message: the whole route ({ stops }) once all its stops are in, else nil.
-- Anything malformed is ignored.
function I.Receive(text, sender, now)
  local v, id, i, n, cont, x, y, name =
    (text or ""):match("^(%d+)\t(%w+)\t(%d+)\t(%d+)\t(%-?%d+)\t(%-?[%d%.]+)\t(%-?[%d%.]+)\t(.*)$")
  if v ~= SHARE_VERSION then return nil end
  i, n, cont, x, y = tonumber(i), tonumber(n), tonumber(cont), tonumber(x), tonumber(y)
  if not (i and n and cont and x and y) or n < 1 or n > I.MAX_SHARE or i < 1 or i > n
      or math.abs(x) > 30000 or math.abs(y) > 30000 or not KnownContinent(cont) then
    return nil
  end
  local r = incoming[sender]
  if not r or r.id ~= id or r.n ~= n or now - r.t > I.SHARE_TIMEOUT then
    r = { id = id, n = n, got = 0, stops = {}, t = now }
    incoming[sender] = r
  end
  if not r.stops[i] then r.got = r.got + 1 end
  r.stops[i] = { x = x, y = y, cont = cont, name = name ~= "" and name or nil }
  r.t = now
  if r.got < n then return nil end
  incoming[sender] = nil
  return r.stops
end

-- The one way out to other players: `I.io.send(prefix, msg, channel, target)`, the game's addon
-- message. (A developer hook: a private dev addon swaps it to test sharing
-- without anything going over the network; see AzerothGPS_Extend in Core.lua.)
I.io = {}
function I.io.send(prefix, msg, channel, target)
  local send = C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
  return send(prefix, msg, channel, target)
end

-- The game throttles addon messages per prefix: 10 in a burst, then 1 a second (whispers outside instances
-- excepted), and drops what's over it (result 3; 8 is the server's throttle, 11 an encounter's lockdown). Several
-- raid members clicking a route link at once in an instance lost their routes' ends (from StreetView's own
-- findings, 2026-10-02). So every message goes through this queue: whispers outside instances at once, the rest
-- SEND_BURST at once and then SEND_PER_SECOND, in order; a refused one is tried again a moment later.
I.SEND_BURST, I.SEND_PER_SECOND = 8, 1
I.RETRY_RESULTS = { [3] = true, [8] = true, [11] = true }
local sendQueue, sendTokens, sendAt, pumping = {}, I.SEND_BURST, nil, false

local function Paced(channel)
  if channel ~= "WHISPER" then return true end
  local inside = IsInInstance and IsInInstance()
  return inside and true or false
end

-- Send what the throttle allows now; the rest after a moment. How many are left waiting.
function I.Pump()
  local now = GetTime()
  sendTokens = math.min(I.SEND_BURST, sendTokens + (now - (sendAt or now)) * I.SEND_PER_SECOND)
  sendAt = now
  while sendQueue[1] do
    local q = sendQueue[1]
    local paced = Paced(q[3])
    if paced and sendTokens < 1 then break end
    local result = I.io.send(q[1], q[2], q[3], q[4])
    if I.RETRY_RESULTS[result] then -- (the game's own count is full: wait, then the same one again)
      sendTokens = 0
      break
    end
    table.remove(sendQueue, 1)
    if paced then sendTokens = sendTokens - 1 end
  end
  if sendQueue[1] and not pumping and C_Timer and C_Timer.After then
    pumping = true
    C_Timer.After(1 / I.SEND_PER_SECOND, function()
      pumping = false
      I.Pump()
    end)
  end
  return #sendQueue
end

function I.Queue(prefix, msg, channel, target)
  sendQueue[#sendQueue + 1] = { prefix, msg, channel, target }
  return I.Pump()
end

-- The chat box opened with `text` for `channel` ("WHISPER" to `target`, "PARTY", "RAID"; nil: the chat box
-- being typed in, else a new one), for the player to send. Nothing is sent here. Whether a box took it.
local function InsertInChat(text)
  local box = I.ChatBox()
  if box then
    if ChatFrameUtil and ChatFrameUtil.InsertLink then
      ChatFrameUtil.InsertLink(text)
    elseif ChatEdit_InsertLink then
      ChatEdit_InsertLink(text)
    else
      box:Insert(text)
    end
    return true
  end
  local open = ChatFrameUtil and ChatFrameUtil.OpenChat or ChatFrame_OpenChat
  if not open then return false end
  open(text)
  return true
end

-- `text` into the chat box being typed in, else a new one, for the player to send (a dock's times,
-- GPSFrame's Shift-click). Nothing is sent. Whether a box took it.
function I.PasteInChat(text)
  return InsertInChat(text)
end

function I.io.chat(text, channel, target)
  local slash
  if channel == "WHISPER" and target then
    slash = (SLASH_WHISPER1 or "/w") .. " " .. target .. " "
  elseif channel == "PARTY" then
    slash = (SLASH_PARTY1 or "/p") .. " "
  elseif channel == "RAID" then
    slash = (SLASH_RAID1 or "/raid") .. " "
  end
  if not slash then return InsertInChat(text) end
  local open = ChatFrameUtil and ChatFrameUtil.OpenChat or ChatFrame_OpenChat
  if not open then return false end
  open(slash .. text) -- (as the game's own "Whisper" does: the box parses the slash command)
  return true
end

-- A route's line in chat: "[AzerothGPS Route 1a2b3c: 3 stops]" (I.LinkifyRoutes makes it a link).
function I.RouteTag(id, n)
  return string.format("[AzerothGPS Route %s: %d stop%s]", id, n, n == 1 and "" or "s")
end
local TAG_PATTERN = "%[AzerothGPS Route (%x+): (%d+) stops?%]"

local posted, postedOrder = {}, {} -- [id] = { msgs, t }: the routes you linked lately, as they were then
I.posted = posted

function I.Post(id, msgs, now)
  posted[id] = { msgs = msgs, t = now or GetTime() }
  postedOrder[#postedOrder + 1] = id
  while #postedOrder > I.POSTED_MAX do posted[table.remove(postedOrder, 1)] = nil end
end

-- Link the route in chat: channel "WHISPER" (to `target`), "PARTY" or "RAID", or nil (the chat box
-- being typed in). Nothing is sent: the chat box opens with the link, for you to send. Returns the
-- number of stops it carries and its id, or nil and why not.
function I.Send(channel, target)
  local stops = ns.Nav.stops
  if #stops == 0 then return nil, L["No route to share."] end
  local id = string.format("%x", math.random(0x100000, 0xFFFFFF))
  local msgs = I.ShareMessages(stops, id)
  if not I.io.chat(I.RouteTag(id, #msgs), channel, target) then return nil, L["Couldn't open a chat box."] end
  I.Post(id, msgs)
  return #msgs, id
end

function I.AcceptShared()
  return not ns.settings or ns.settings.gps.acceptShared ~= false
end

-- A player's name to compare by: without the realm, lower case.
local function Who(name)
  return ((name or ""):match("^[^-]*")):lower()
end

local function IsMe(name)
  local me = UnitName and UnitName("player")
  return me ~= nil and Who(name) == Who(me)
end

local answered = {} -- [who \t id] = when

-- Someone clicked your route's link and asks for it: its stops, to them only (a route you linked in
-- the last hour; once in ANSWER_GAP seconds each). How many messages went.
function I.Answer(sender, id, now)
  local p = posted[id]
  if not p or now - p.t > I.POSTED_TTL then return 0 end
  local key = Who(sender) .. "\t" .. id
  if answered[key] and now - answered[key] < I.ANSWER_GAP then return 0 end
  answered[key] = now
  for _, m in ipairs(p.msgs) do I.Queue(I.PREFIX, m, "WHISPER", sender) end
  return #p.msgs
end

local askedFor = {} -- [who] = { id, t }: the route last asked for from each player (its link clicked)

-- A route `sender`'s stops are taken in for (I.Expect: the dev addon's fake players answer through it).
function I.Expect(sender, id, now)
  askedFor[Who(sender)] = { id = id, t = now or GetTime() }
end

function I.Request(sender, id)
  I.Expect(sender, id)
  I.Queue(I.PREFIX, "?\t" .. id, "WHISPER", sender)
  local name = Ambiguate and Ambiguate(sender, "none") or sender
  if C_Timer and C_Timer.After then
    C_Timer.After(I.ASK_TIMEOUT, function()
      local a = askedFor[Who(sender)]
      if a and a.id == id then
        askedFor[Who(sender)] = nil
        ns.Print(string.format(L["No route from %s: the link may be over an hour old, or they're offline."], name))
      end
    end)
  end
  ns.Print(string.format(L["Asking %s for the route..."], name))
end

-- "[AzerothGPS Route id: n stops]" in a chat line from `author`: a link that asks them for it.
function I.LinkifyRoutes(msg, author)
  if type(msg) ~= "string" or not I.AcceptShared() then return msg end
  if msg:find("[AzerothGPS Pin: ", 1, true) then msg = I.LinkifyPins(msg) end
  if not msg:find("[AzerothGPS Route ", 1, true) then return msg end
  author = (author or ""):gsub("[:|]", "")
  if author == "" then return msg end
  return (msg:gsub(TAG_PATTERN, function(id, n)
    -- (the tag in chat stays English, as AzerothGPS reads it on any client; the link is shown in this client's language)
    local shown = n == "1" and L["[AzerothGPS Route: 1 stop]"] or string.format(L["[AzerothGPS Route: %s stops]"], n)
    return string.format("|cff33ff99|Haddon:AzerothGPS:route:%s:%s|h%s|h|r", id, author, shown)
  end))
end

-- A pin as a line in chat (asked 2026-10-06: Shift-click a pin to share it): readable, and in AzerothGPS users' chat
-- a link that adds it to their map (after asking): "[AzerothGPS Pin: Old Tree (Elwynn Forest) @0:-9465.2,63.1 #134400]".
-- Its level and world spot exactly, ",z<height>" and ",down" when it has them, "#<icon>" a file id or icon path; the
-- place in brackets is only for reading. Carried whole: no addon message, the one who shared it needn't be online.
local function IconToken(icon)
  if type(icon) == "number" then return tostring(math.floor(icon)) end
  if type(icon) == "string" and icon:match("^[%w_\\/%.%-]+$") then return icon end
  return nil
end
function I.PinTag(pin, place)
  local name = (ns.Pins and ns.Pins.CleanName(pin.name) or tostring(pin.name or "Pin")):gsub("[%[%]]", "")
  local spot = string.format("@%d:%.1f,%.1f", pin.level or 0, pin.x, pin.y)
  if pin.z then spot = spot .. string.format(",z%.1f", pin.z) end
  if pin.down then spot = spot .. ",down" end
  local icon = IconToken(pin.icon)
  place = type(place) == "string" and place:gsub("[%[%]()]", "") or nil
  return string.format("[AzerothGPS Pin: %s%s %s%s]", name, (place and place ~= "") and (" (" .. place .. ")") or "",
    spot, icon and (" #" .. icon) or "")
end
-- The pin in a tag's text (what's between "[AzerothGPS Pin: " and "]"), checked: { level, x, y, z, down, icon,
-- name, place }, or nil (MapText.ParsePinTag). `wholeName`: the text before " @" is all name (a link's).
function I.ParsePin(inner, wholeName) return ns.MapText.ParsePinTag(inner, wholeName) end
-- Pin tags in a chat line as links (the data in the link: level, x, y, z, down, icon, then the name).
function I.LinkifyPins(msg)
  return (msg:gsub("%[AzerothGPS Pin: ([^%]]+)%]", function(inner)
    local p = I.ParsePin(inner)
    if not p then return nil end
    return string.format("|cff33ff99|Haddon:AzerothGPS:pin:%d:%.1f:%.1f:%s:%s:%s:%s|h%s|h|r",
      p.level, p.x, p.y, p.z and string.format("%.1f", p.z) or "", p.down and "1" or "0", p.icon and tostring(p.icon) or "",
      p.name, string.format(L["[AzerothGPS Pin: %s]"], p.name))
  end))
end
-- A pin link clicked: asked whether to add it to your map. Whether `link` was one.
function I.OnPinLink(link)
  if type(link) ~= "string" then return false end
  local level, x, y, z, down, icon, name =
    link:match("^addon:AzerothGPS:pin:(%-?%d+):(%-?[%d%.]+):(%-?[%d%.]+):(%-?[%d%.]*):([01]):([^:]*):(.*)$")
  if not level then return false end
  local tag = string.format("%s @%s:%s,%s%s%s%s", name, level, x, y, z ~= "" and (",z" .. z) or "",
    down == "1" and ",down" or "", icon ~= "" and (" #" .. icon) or "")
  local pin = I.ParsePin(tag, true)
  if pin then I.OfferPin(pin) end
  return true
end
-- "Add the pin X to your map?": the pin, yours from then on (as one you made). One you have already isn't added again.
function I.OfferPin(pin)
  for _, p in ipairs(ns.Pins.Own()) do
    if p.level == pin.level and p.name == pin.name and (p.x - pin.x) ^ 2 + (p.y - pin.y) ^ 2 < 4 then
      ns.Print(string.format(L["You have the pin %s already."], pin.name))
      return false
    end
  end
  local Ask = ns.GPS and ns.GPS.Ask or ns.Ask
  local question = pin.place and Format(L["Add the pin |cffffd100%s|r (%s) to your map?"], pin.name, pin.place)
    or string.format(L["Add the pin |cffffd100%s|r to your map?"], pin.name)
  I.pinBox = Ask("AzerothGPSSharedPin", question, L["Add Pin"], L["Cancel"], function()
      ns.Pins.Add(pin)
      ns.Print(string.format(L["pin added: %s"], pin.name))
      if ns.GPS then ns.GPS.Redraw() end
    end, nil, { timeout = 60 })
  return true
end

-- A route link clicked (I.LinkifyRoutes): its author is asked for it. Whether `link` was one.
function I.OnRouteLink(link)
  if type(link) ~= "string" then return false end
  local id, who = link:match("^addon:AzerothGPS:route:(%x+):(.+)$")
  if not id then return false end
  if IsMe(who) then
    ns.Print(L["That's your route's link: AzerothGPS users who click it are sent your route."])
  elseif not I.AcceptShared() then
    ns.Print(L["Routes from other players are turned off (AzerothGPS options: Accept routes shared by players)."])
  else
    I.Request(who, id)
  end
  return true
end

-- A route you asked for (its link clicked): ask before using it. (I.Offer: the dev addon's checks swap
-- it to see what would be offered without the popup.)
function I.Offer(sender, stops)
  local who = Ambiguate and Ambiguate(sender, "none") or sender
  local names = {}
  for i, d in ipairs(stops) do names[i] = string.format("%d. %s", i, d.name or string.format(L["stop %d"], i)) end
  -- (AzerothGPS's popup without a title bar, over the map while it shows: GPS.Ask; gone unanswered after a minute)
  I.offered = { stops = stops, who = who }
  local Ask = ns.GPS and ns.GPS.Ask or ns.Ask
  I.offerBox = Ask("AzerothGPSSharedRoute",
    Format(L["%s's route (AzerothGPS):\n\n%s\n\nUse it as your route?"], who, table.concat(names, "\n")),
    L["Use Route"], L["Ignore"], function()
      local n = I.Apply(stops, false)
      ns.Print(n > 1 and Format(L["route from %s: %d stops"], who, n) or string.format(L["route from %s: 1 stop"], who))
      if ns.GPS then
        ns.GPS.Follow()
        ns.GPS.Redraw()
      end
    end, nil, { timeout = 60 })
end

local SHARE_CHANNELS = { WHISPER = true, PARTY = true, RAID = true, INSTANCE_CHAT = true }

-- The chat a route's line becomes a link in.
I.LINK_EVENTS = { "CHAT_MSG_WHISPER", "CHAT_MSG_WHISPER_INFORM", "CHAT_MSG_PARTY", "CHAT_MSG_PARTY_LEADER",
  "CHAT_MSG_RAID", "CHAT_MSG_RAID_LEADER", "CHAT_MSG_RAID_WARNING", "CHAT_MSG_INSTANCE_CHAT",
  "CHAT_MSG_INSTANCE_CHAT_LEADER", "CHAT_MSG_GUILD", "CHAT_MSG_OFFICER", "CHAT_MSG_SAY", "CHAT_MSG_YELL",
  "CHAT_MSG_CHANNEL" }

-- An addon message received (CHAT_MSG_ADDON): someone asking for a route you linked (answered), or a
-- stop of a route you asked for, offered once all its stops are in; any other route is ignored.
-- (I.OnAddonMessage: the dev addon feeds it fake players' messages.)
function I.OnAddonMessage(prefix, text, channel, sender)
  if prefix ~= I.PREFIX or not SHARE_CHANNELS[channel] or type(text) ~= "string" or IsMe(sender) then return end
  local now = GetTime()
  local want = text:match("^%?\t(%x+)$")
  if want then
    if channel == "WHISPER" then I.Answer(sender, want, now) end
    return
  end
  local bang = text:match("^!\t(%S+)$")
  if bang then
    if channel == "WHISPER" then I.OnRouteAsk(sender, bang, now) end
    return
  end
  if not I.AcceptShared() then return end
  local a = askedFor[Who(sender)]
  local tid = text:match("^%d+\t(%w+)\t")
  if a and a.id == "*" and tid and now - a.t <= I.ASK_TIMEOUT then a.id = tid end -- (asked a group member: theirs)
  if not (a and tid == a.id and now - a.t <= I.ASK_TIMEOUT) then return end
  local stops = I.Receive(text, sender, now)
  if stops then
    askedFor[Who(sender)] = nil
    I.Offer(sender, stops)
  end
end

-- The players in your group (names as the game gives them, the realm where it does); the dev addon may swap it.
function I.io.groupNames()
  local out = {}
  local raid = IsInRaid and IsInRaid()
  local n = raid and (GetNumGroupMembers and GetNumGroupMembers() or 0) or 4
  for i = 1, n do
    local unit = raid and ("raid" .. i) or ("party" .. i)
    if UnitExists and UnitExists(unit) then
      local name, realm = UnitName(unit)
      if name and not (ns.IsSecret and ns.IsSecret(name)) then
        out[#out + 1] = (realm and realm ~= "") and (name .. "-" .. realm) or name
      end
    end
  end
  return out
end
function I.InGroup(name)
  for _, n in ipairs(I.io.groupNames()) do
    if Who(n) == Who(name) then return true end
  end
  return false
end

-- Ask group member `name` for their route (asked 2026-10-06: request a route in a party). Their answer comes as
-- stops (offered as any shared route), or "no" / "none". False (and why) when it can't be asked.
function I.AskForRoute(name)
  if not name or IsMe(name) then return false, L["That's you."] end
  if not I.InGroup(name) then return false, L["Only players in your group can be asked for their route."] end
  if not I.AcceptShared() then
    return false, L["Routes from other players are turned off (AzerothGPS options: Accept routes shared by players)."]
  end
  I.Expect(name, "*")
  I.Queue(I.PREFIX, "!\troute?", "WHISPER", name)
  local who = Ambiguate and Ambiguate(name, "none") or name
  if C_Timer and C_Timer.After then
    C_Timer.After(I.ASK_TIMEOUT, function()
      local a = askedFor[Who(name)]
      if a and a.id == "*" then
        askedFor[Who(name)] = nil
        ns.Print(string.format(L["No answer from %s (they may not have AzerothGPS)."], who))
      end
    end)
  end
  ns.Print(string.format(L["Asking %s for their route..."], who))
  return true
end

local routeAsks = {} -- [who] = when they last asked you
-- A "!" message from `sender`: a group member asking for your route ("route?": you're asked whether to send it), or
-- their answer to yours ("no", "none").
function I.OnRouteAsk(sender, what, now)
  local who = Ambiguate and Ambiguate(sender, "none") or sender
  if what == "route?" then
    if not I.InGroup(sender) then return end -- (only your group)
    local last = routeAsks[Who(sender)]
    if last and now - last < I.ROUTE_ASK_GAP then return end
    routeAsks[Who(sender)] = now
    local stops = ns.Nav.stops
    if #stops == 0 then
      I.Queue(I.PREFIX, "!\tnone", "WHISPER", sender)
      ns.Print(string.format(L["%s asked for your route; you have none right now."], who))
      return
    end
    local Ask = ns.GPS and ns.GPS.Ask or ns.Ask
    I.routeAskBox = Ask("AzerothGPSRouteAsk",
      #stops == 1 and string.format(L["|cffffd100%s|r asks for your route (1 stop).\n\nSend it to them?"], who)
        or Format(L["|cffffd100%s|r asks for your route (%d stops).\n\nSend it to them?"], who, #stops),
      L["Send"], L["Don't Send"], function()
        local id = string.format("%x", math.random(0x100000, 0xFFFFFF))
        local msgs = I.ShareMessages(ns.Nav.stops, id)
        for _, m in ipairs(msgs) do I.Queue(I.PREFIX, m, "WHISPER", sender) end
        ns.Print(#msgs == 1 and string.format(L["Your route (1 stop) went to %s."], who)
          or Format(L["Your route (%d stops) went to %s."], #msgs, who))
      end, function()
        I.Queue(I.PREFIX, "!\tno", "WHISPER", sender)
      end, { timeout = 60 })
    return
  end
  local a = askedFor[Who(sender)]
  if not (a and a.id == "*") then return end -- (an answer to nothing you asked)
  askedFor[Who(sender)] = nil
  if what == "none" then
    ns.Print(string.format(L["%s has no route right now."], who))
  elseif what == "no" then
    ns.Print(string.format(L["%s didn't send their route."], who))
  end
end

---------------------------------------------------------------------------
-- Map data in and out (asked 2026-10-06: herbs, ore, NPCs, pins, roads and walls imported and exported in game)
---------------------------------------------------------------------------

-- Text pasted in the Import and Share window, taken into the player's own data, never the addon's: MapText's lines
-- (roads and walls with the ones they drew, marked imported: Record.AddShared; pins as their own: Pins.AddImported;
-- herbs and ore unconfirmed until gathered: Layers.AddNodes; NPCs until talked to: Layers.AddImportedNpc), and /way
-- lines as `ways` says: "stops" (the route; `addToRoute`: after its stops), "nodes", "npcs" or "none" (rejected: an
-- import inbox's). One unsaved change for
-- all of it (Save Now). Returns { added = { roads, walls, pins, herbs, ore, npcs }, had (known already), stops (the
-- /way stops read, or nil), wanted and fit (the route's stops asked for and after), rejected = { "Line n: why", ... },
-- skipped (known lines not imported here) }.
-- About how many values an import brings to the saved file (ns.SavedValues): a road or wall (its points one string,
-- ns.PackSaved) ~4, a pin ~6, a herb or ore ~3, an NPC ~5, a /way line ~5.
function I.ImportValues(d)
  return 4 * (#d.roads + #d.walls) + 6 * #d.pins + 3 * (#d.herbs + #d.ore) + 5 * #d.npcs + 5 * #d.ways
end

function I.ImportText(text, ways, addToRoute)
  local M, Lay = ns.MapText, ns.Layers
  local d = M.Parse(text, C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player"))
  local res = { added = { roads = 0, walls = 0, pins = 0, herbs = 0, ore = 0, npcs = 0 }, had = 0, rejected = {},
    skipped = d.skipped }
  local A = res.added
  -- (the saved file's limit, asked 2026-10-06: an import that would bring it past SAVED_IMPORT_SHARE of what WoW can
  -- load is refused whole; nothing taken in, nothing of the player's deleted)
  local cost = I.ImportValues(d)
  if cost > 0 and ns.SavedValues and AzerothGPSDB then
    local share = (ns.SavedValues(AzerothGPSDB) + cost) / ns.SAVED_LIMIT
    if share > ns.SAVED_IMPORT_SHARE then
      res.refused = Format(L["Not imported: it would bring your saved AzerothGPS data to %d%% of what WoW can load (%d%% at most for an import). Nothing was added or deleted."], math.floor(share * 100 + 0.5),
        math.floor(ns.SAVED_IMPORT_SHARE * 100 + 0.5))
      return res
    end
  end
  local function reject(line, why) res.rejected[#res.rejected + 1] = { line = line, why = why } end
  for _, r in ipairs(d.rejected) do reject(r.line, r.why) end
  -- roads and walls (apart, for their counts)
  for _, kind in ipairs({ "roads", "walls" }) do
    local tracks = {}
    for _, e in ipairs(d[kind]) do
      tracks[#tracks + 1] = { op = e.op, continent = e.level, time = e.time, pts = e.pts, area = e.area, z = e.z,
        indoors = e.indoors, down = e.down }
    end
    if #tracks > 0 and ns.Record then
      local n, had = ns.Record.AddShared(tracks, true)
      A[kind], res.had = n, res.had + had
    end
  end
  -- herbs, ore and NPCs, with /way lines taken as them
  local herbs, ore, npcs, stops = {}, {}, {}, {}
  for _, e in ipairs(d.herbs) do herbs[#herbs + 1] = { level = e.level, x = e.x, y = e.y, name = e.name, kind = "herb" } end
  for _, e in ipairs(d.ore) do ore[#ore + 1] = { level = e.level, x = e.x, y = e.y, name = e.name, kind = "ore" } end
  for _, e in ipairs(d.npcs) do npcs[#npcs + 1] = e end
  for _, w in ipairs(d.ways) do
    local stop, why = I.ToStop(w)
    if not stop then
      reject(w.line, why)
    elseif ways == "nodes" then
      local kind = not stop.unnamed and Lay and Lay.NodeKind(stop.name) -- (no name: its zone's isn't the node's)
      if not kind then
        reject(w.line, stop.unnamed and L["a herb or ore needs its name"]
          or string.format(L["'%s' isn't a herb or ore name"], stop.name))
      else
        local list = kind == "ore" and ore or herbs
        list[#list + 1] = { level = stop.cont, x = stop.x, y = stop.y, name = stop.name, kind = kind }
      end
    elseif ways == "none" then
      reject(w.line, L["a /way line: paste it in the Import and Share window"])
    elseif ways == "npcs" then
      if stop.unnamed then
        reject(w.line, L["an NPC needs its name"])
      else
        npcs[#npcs + 1] = { level = stop.cont, x = stop.x, y = stop.y, name = stop.name }
      end
    else
      stops[#stops + 1] = stop
    end
  end
  if Lay then
    local n, had = Lay.AddNodes(herbs)
    A.herbs, res.had = n, res.had + had
    n, had = Lay.AddNodes(ore)
    A.ore, res.had = n, res.had + had
    local known = #npcs > 0 and Lay.TalkedToNames()
    for _, e in ipairs(npcs) do
      if Lay.AddImportedNpc(e.level, e.x, e.y, e.name, e.title, known) then A.npcs = A.npcs + 1 else res.had = res.had + 1 end
    end
  end
  if #d.pins > 0 and ns.Pins then
    local n, had = ns.Pins.AddImported(d.pins)
    A.pins, res.had = n, res.had + had
  end
  local any = 0
  for _, n in pairs(A) do any = any + n end
  if any > 0 and ns.MarkUnsaved then ns.MarkUnsaved("import:" .. (time and time() or 0), "add") end
  if #stops > 0 then
    res.stops = #stops
    res.wanted = #stops + (addToRoute and #ns.Nav.stops or 0)
    res.fit = I.Apply(stops, addToRoute)
  end
  table.sort(res.rejected, function(a, b) return a.line < b.line end)
  for i, r in ipairs(res.rejected) do res.rejected[i] = M.Why(r) end
  return res
end

-- What an import did, for the window and the chat: "Added 2 roads, 3 pins. 5 you had already. ..." (rejected lines:
-- the first SHOW_REJECTED of them).
I.SHOW_REJECTED = 4
I.KIND_WORDS = { { "roads", L["1 road"], L["%d roads"] }, { "walls", L["1 wall"], L["%d walls"] },
  { "pins", L["1 pin"], L["%d pins"] }, { "herbs", L["1 herb"], L["%d herbs"] }, { "ore", L["1 ore"], L["%d ore"] },
  { "npcs", L["1 NPC"], L["%d NPCs"] } }
function I.ImportSummary(res)
  local any = res.stops or res.had > 0 or #res.rejected > 0
  for _, n in pairs(res.added) do any = any or n > 0 end
  if res.refused and not any then return "|cffff6060" .. res.refused .. "|r" end
  local out, parts = {}, {}
  for _, k in ipairs(I.KIND_WORDS) do
    local n = res.added[k[1]]
    if n > 0 then parts[#parts + 1] = n == 1 and k[2] or string.format(k[3], n) end
  end
  if res.stops then
    out[#out + 1] = res.fit == 1 and L["Route: 1 stop."] or string.format(L["Route: %d stops."], res.fit)
    if res.wanted > res.fit then
      out[#out + 1] = Format(L["Only %d fit (%d stops at most)."], res.fit, ns.Nav.MAX_STOPS)
    end
  end
  if #parts > 0 then
    out[#out + 1] = string.format(L["Added %s."], table.concat(parts, L[", "]))
  elseif not res.stops then
    out[#out + 1] = L["Nothing new added."]
  end
  if res.had > 0 then out[#out + 1] = string.format(L["%d you had already."], res.had) end
  if res.skipped > 0 then
    out[#out + 1] = res.skipped == 1 and L["1 line not imported here (faster trips, dungeons' ways in)."]
      or string.format(L["%d lines not imported here (faster trips, dungeons' ways in)."], res.skipped)
  end
  local n = #res.rejected
  if n > 0 then
    local shown = {}
    for i = 1, math.min(n, I.SHOW_REJECTED) do shown[i] = res.rejected[i] end
    local list = table.concat(shown, "; ")
    if n > I.SHOW_REJECTED then list = Format(L["%s; and %d more"], list, n - I.SHOW_REJECTED) end
    out[#out + 1] = n == 1 and string.format(L["|cffff60601 line rejected:|r %s"], list)
      or Format(L["|cffff6060%d lines rejected:|r %s"], n, list)
  end
  if res.refused then out[#out + 1] = "|cffff6060" .. res.refused .. "|r" end
  return table.concat(out, " ")
end

-- The player's own map data as text to share (the window's Copy My Map Data; MapText's lines, its header first): of
-- the kinds in `kinds` ({ herbs = true, ore, npcs, pins, roads, walls }), the herbs and ore they gathered and the NPCs
-- they talked to (their own finds: not imported ones, nor NPCs found in several places), their pins, and the roads
-- and walls they drew or imported that the addon's data hasn't got. Returns the text ("" when there's nothing) and
-- how many lines.
function I.MapDataText(kinds)
  local M = ns.MapText
  local lines, finds = {}, {}
  for cont, list in pairs(ns.db and ns.db.nodes or {}) do
    for _, n in ipairs(list) do
      if not n[6] and ((n[4] == "herb" and kinds.herbs) or (n[4] == "ore" and kinds.ore)) and ns.Layers.IsNode(n) then
        finds[#finds + 1] = M.NodeLine(n[4], cont, n[1], n[2], n[3])
      end
    end
  end
  if kinds.npcs then
    for _, n in pairs(ns.db and ns.db.npcs or {}) do
      if n.name and n.x and n.cont and not n.imported and not n.common then
        finds[#finds + 1] = M.NpcLine(n.cont, n.x, n.y, n.name, n.title)
      end
    end
  end
  table.sort(finds) -- (the same finds, the same text)
  for _, l in ipairs(finds) do lines[#lines + 1] = l end
  if kinds.pins and ns.Pins then
    for _, p in ipairs(ns.Pins.Own()) do
      if p.time and p.x and p.y then lines[#lines + 1] = M.PinLine(p, ns.Pins.DEFAULT_ICON) end
    end
  end
  if (kinds.roads or kinds.walls) and ns.Feedback then
    local all = ns.Feedback.Lines()
    for _, kind in ipairs({ "roads", "walls" }) do
      if kinds[kind] then
        for _, l in ipairs(all[kind]) do lines[#lines + 1] = l end
      end
    end
  end
  if #lines == 0 then return "", 0 end
  table.insert(lines, 1, M.HEADER)
  return table.concat(lines, "\n"), #lines - 1
end

---------------------------------------------------------------------------
-- An import inbox (asked 2026-10-06): map data a tool on the player's PC leaves for AzerothGPS, in a global any
-- loaded file may define:
--   AzerothGPS_ImportInbox = { { made = <a whole number, its own>, text = "<MapText's lines>" }, ... }
-- Read once every addon is loaded (I.Init, at PLAYER_LOGIN, a /reload too: the file defining it may load after
-- AzerothGPS), as data only: entries with a whole number `made` and a string `text`, INBOX_MAX of them at most, each
-- text through MapText's limits; anything else is passed over. The entries not handled yet are offered once, with
-- their counts; Yes takes them in as the window's Import does (the player's own data, never the addon's), No declines
-- them; unanswered (Escape, the time out), they're offered again at the next login or /reload. Each one handled is
-- acknowledged in ns.db.importInbox[made] = { at, added = { roads, walls, pins, herbs, ore, npcs }, had, rejected,
-- declined } (an unsaved change: Save Now), which whoever made the inbox reads back from the saved file. /way lines
-- aren't taken from an inbox (it never changes the route): they count as rejected.
---------------------------------------------------------------------------
I.INBOX_MAX = 50
I.INBOX_TEXT_MAX = 2 * 1024 * 1024 -- bytes of an entry's text
-- (the acknowledgments are kept for good, asked 2026-10-06: keep data forever; about two values each in the saved file)
I.INBOX_DELAY = 3 -- seconds after login before asking (the map and the windows made)
I.INBOX_TIMEOUT = 120

-- The inbox's entries not handled yet (`acks`: ns.db.importInbox), read as data: { { made, text }, ... } by `made`.
function I.InboxEntries(inbox, acks)
  local out, seen = {}, {}
  if type(inbox) ~= "table" then return out end
  for i = 1, I.INBOX_MAX do
    local e = rawget(inbox, i)
    if e == nil then break end
    if type(e) == "table" then
      local made, text = rawget(e, "made"), rawget(e, "text")
      if type(made) == "number" and made >= 1 and made < 2 ^ 53 and made % 1 == 0 and type(text) == "string"
          and #text <= I.INBOX_TEXT_MAX and not (acks and acks[made]) and not seen[made] then
        seen[made] = true
        out[#out + 1] = { made = made, text = text }
      end
    end
  end
  table.sort(out, function(a, b) return a.made < b.made end)
  return out
end

-- What an inbox's entries hold, for the question: "12 herbs, 3 pins, 1 road", and how many lines can't be taken.
local function InboxCounts(entries)
  local counts = { roads = 0, walls = 0, pins = 0, herbs = 0, ore = 0, npcs = 0 }
  local bad = 0
  for _, e in ipairs(entries) do
    local d = ns.MapText.Parse(e.text)
    for kind in pairs(counts) do counts[kind] = counts[kind] + #d[kind] end
    bad = bad + #d.rejected + #d.ways
  end
  local parts = {}
  for _, k in ipairs(I.KIND_WORDS) do
    local n = counts[k[1]]
    if n > 0 then parts[#parts + 1] = n == 1 and k[2] or string.format(k[3], n) end
  end
  return parts, bad
end

-- The inbox looked at: the entries not handled yet offered (true), or nothing to ask (false).
function I.CheckInbox()
  local db = ns.db
  if not db then return false end
  if type(db.importInbox) ~= "table" then db.importInbox = {} end
  local acks = db.importInbox
  local entries = I.InboxEntries(rawget(_G, "AzerothGPS_ImportInbox"), acks)
  if #entries == 0 then return false end
  local now = time and time() or 0
  local function Ack(e, a)
    a.at = now
    acks[e.made] = a
    if ns.MarkUnsaved then ns.MarkUnsaved("importInbox:" .. e.made, "add") end
  end
  local parts, bad = InboxCounts(entries)
  if #parts == 0 then -- (nothing in them AzerothGPS can take: said, not asked)
    for _, e in ipairs(entries) do Ack(e, { added = {}, had = 0, rejected = bad }) end
    ns.Print(bad == 1 and L["An import inbox had nothing AzerothGPS could read (1 line)."]
      or string.format(L["An import inbox had nothing AzerothGPS could read (%d lines)."], bad))
    return false
  end
  local what = table.concat(parts, L[", "])
  local text = bad == 0 and string.format(L["Map data is waiting in an import inbox: |cffffd100%s|r.\n\nAdd it to your map?"], what)
    or bad == 1 and string.format(L["Map data is waiting in an import inbox: |cffffd100%s|r. (1 line can't be read.)\n\nAdd it to your map?"], what)
    or Format(L["Map data is waiting in an import inbox: |cffffd100%s|r. (%d lines can't be read.)\n\nAdd it to your map?"], what, bad)
  local function Yes()
    local total = { added = { roads = 0, walls = 0, pins = 0, herbs = 0, ore = 0, npcs = 0 }, had = 0, rejected = {},
      skipped = 0 }
    for _, e in ipairs(entries) do
      local res = I.ImportText(e.text, "none", false)
      local added = {}
      for kind, n in pairs(res.added) do
        added[kind] = n
        total.added[kind] = total.added[kind] + n
      end
      total.had, total.skipped = total.had + res.had, total.skipped + res.skipped
      for _, r in ipairs(res.rejected) do total.rejected[#total.rejected + 1] = r end
      total.refused = total.refused or res.refused
      Ack(e, { added = added, had = res.had, rejected = #res.rejected, refused = res.refused and true or nil })
    end
    ns.Print(string.format(L["From an import inbox: %s"], I.ImportSummary(total)))
    if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
  end
  local function No(clicked)
    if not clicked then return end -- (unanswered: asked again next time)
    for _, e in ipairs(entries) do Ack(e, { declined = true }) end
  end
  local Ask = ns.GPS and ns.GPS.Ask or ns.Ask
  I.inboxBox = Ask("AzerothGPSImportInbox", text, L["Add It"], L["Not This"], Yes, No, { timeout = I.INBOX_TIMEOUT })
  return true
end

---------------------------------------------------------------------------
-- Window
---------------------------------------------------------------------------

local win

-- (the window's tooltips)
local function Tip(frame, title, text)
  frame:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(title, 1, 1, 1)
    GameTooltip:AddLine(text, nil, nil, nil, true)
    GameTooltip:Show()
  end)
  frame:SetScript("OnLeave", GameTooltip_Hide)
end
-- (a small checkbox, its label after it: `label`)
local function Check(f, text)
  local c = CreateFrame("CheckButton", nil, f, "UICheckButtonTemplate")
  c:SetSize(22, 22)
  local t = c:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  t:SetPoint("LEFT", c, "RIGHT", 1, 0)
  t:SetText(text)
  c.label = t
  -- (its words tick it too: a click on "/way as herb/ore nodes" left the box unticked, and the /way line became a
  -- stop, the 1.1.5 test pass)
  if c.SetHitRectInsets then c:SetHitRectInsets(0, -(t:GetStringWidth() + 2), 0, 0) end
  return c
end

-- A button as wide as its text needs (other languages' words are longer: the languages' screenshots, 2026-11-09), at
-- least `w`.
local function FitButton(b, w)
  local need = b.GetTextWidth and (b:GetTextWidth() or 0) + 24 or 0
  b:SetWidth(math.max(w, math.ceil(need)))
end
I.FitButton = FitButton

-- The kinds Copy My Map Data writes (the window's checkboxes): { key, label }.
I.EXPORT_KINDS = { { "herbs", L["Herbs"] }, { "ore", L["Ore"] }, { "npcs", L["NPCs"] }, { "pins", L["Pins"] },
  { "roads", L["Roads"] }, { "walls", L["Walls"] } }

local function Build()
  -- the map window's frame without the logo, as every popup (ns.Window)
  local f = ns.Window("AzerothGPSImport", 520, 460, L["Import and Share"])
  local TOP = -f.top -- where the content starts, below the title
  local hint = f:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  hint:SetPoint("TOPLEFT", 12, -TOP)
  hint:SetPoint("RIGHT", -12, 0) -- (wrapped in the window: it ran past its edge, in English too)
  hint:SetJustifyH("LEFT")
  hint:SetWordWrap(true)
  hint:SetText(L["Paste TomTom /way lines or AzerothGPS map data, one per line:  /way Elwynn Forest 43.2 65.1 First Stop"])

  local scroll = CreateFrame("ScrollFrame", "AzerothGPSImportScroll", f, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", hint, "BOTTOMLEFT", 0, -9) -- (its box drawn 4 above it: the hint's line clear of it)
  scroll:SetPoint("BOTTOMRIGHT", -32, 196)
  local bg = f:CreateTexture(nil, "BACKGROUND", nil, 1)
  bg:SetPoint("TOPLEFT", scroll, -4, 4)
  bg:SetPoint("BOTTOMRIGHT", scroll, 4, -4)
  bg:SetColorTexture(0, 0, 0, 0.5)
  local edit = CreateFrame("EditBox", nil, scroll)
  edit:SetMultiLine(true)
  edit:SetAutoFocus(false)
  edit:SetFontObject(ChatFontNormal)
  edit:SetWidth(460)
  edit:SetScript("OnEscapePressed", function() f:Hide() end)
  scroll:SetScrollChild(edit)
  scroll:SetScript("OnMouseDown", function() edit:SetFocus() end)
  f.edit = edit

  local status = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  status:SetPoint("BOTTOMLEFT", 12, 130)
  status:SetPoint("RIGHT", -12, 0)
  status:SetJustifyH("LEFT")
  status:SetWordWrap(true)
  f.status = status

  -- Share the current route: as /way text to copy anywhere, or sent in game.
  local copy = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  copy:SetSize(150, 22)
  copy:SetPoint("BOTTOMLEFT", 12, 98)
  copy:SetText(L["Copy Route as /way"])
  FitButton(copy, 150)
  copy:SetScript("OnClick", function()
    local text, skipped = I.ExportText(ns.Nav.stops)
    if text == "" then
      status:SetText(L["|cffff6060No route to copy.|r Set one first (double-click the map)."])
      return
    end
    edit:SetText(text)
    edit:SetFocus()
    edit:HighlightText()
    status:SetText(L["Selected above: press Ctrl+C, then paste it anywhere (Discord, a guide, chat). AzerothGPS and TomTom users can paste it to get the same stops."]
      .. (skipped == 1 and L[" |cffff60601 stop outside any zone left out.|r"]
        or skipped > 1 and string.format(L[" |cffff6060%d stops outside any zone left out.|r"], skipped) or ""))
  end)
  Tip(copy, L["Copy Route as /way"], L["Writes your route's stops as TomTom /way lines in the box, selected for copying."])

  local sendLabel = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  sendLabel:SetPoint("LEFT", copy, "RIGHT", 12, 0)
  sendLabel:SetText(L["Link To"])
  local who = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
  who:SetSize(100, 20)
  who:SetPoint("LEFT", sendLabel, "RIGHT", 10, 0)
  who:SetAutoFocus(false)
  who:SetMaxLetters(60)
  who:SetScript("OnEscapePressed", function() f:Hide() end)
  f.who = who
  Tip(who, L["Link To"], L["A player's name (Name or Name-Realm). Shift+click a name in chat to fill it in, or target the player before opening this window."])
  local function Sent(n, err, to)
    if n then
      local total = #ns.Nav.stops
      status:SetText(total > n and Format(L["A link to your route (%d stops (the next %d; use Copy route as /way for all %d)) is in the chat box to %s: press Enter to send it. AzerothGPS users click it to get the route; others only see the short line."], n, n, total, to)
        or n == 1 and string.format(L["A link to your route (1 stop) is in the chat box to %s: press Enter to send it. AzerothGPS users click it to get the route; others only see the short line."], to)
        or Format(L["A link to your route (%d stops) is in the chat box to %s: press Enter to send it. AzerothGPS users click it to get the route; others only see the short line."], n, to))
    else
      status:SetText("|cffff6060" .. err .. "|r")
    end
  end
  local whisper = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  whisper:SetSize(70, 22)
  whisper:SetPoint("LEFT", who, "RIGHT", 6, 0)
  whisper:SetText(L["Player"])
  FitButton(whisper, 70)
  whisper:SetScript("OnClick", function()
    local name = Trim(who:GetText() or "")
    if name == "" then
      status:SetText(L["|cffff6060Type a player's name|r (or target them first)."])
      return
    end
    local n, err = I.Send("WHISPER", name)
    Sent(n, err, name)
  end)
  local group = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  group:SetSize(64, 22)
  group:SetPoint("LEFT", whisper, "RIGHT", 4, 0)
  group:SetText(L["Group"])
  FitButton(group, 64)
  group:SetScript("OnClick", function()
    local channel = IsInRaid and IsInRaid() and "RAID" or (IsInGroup and IsInGroup() and "PARTY")
    if not channel then
      status:SetText(L["|cffff6060You're not in a group.|r"])
      return
    end
    local n, err = I.Send(channel, nil)
    Sent(n, err, channel == "RAID" and L["your raid"] or L["your party"])
  end)
  local linkTip = L["Puts a link to your route in the chat box (a whisper, or party or raid chat) for you to send. AzerothGPS users who click it get your route's stops, and are asked before it replaces theirs. Nothing is sent until you press Enter."]
  Tip(whisper, L["Link to a player"], linkTip)
  Tip(group, L["Link to your group"], linkTip)

  -- Share your own map data (asked 2026-10-06): as MapText's lines, the kinds ticked, for other players to import.
  local mine = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  mine:SetSize(124, 22)
  mine:SetPoint("BOTTOMLEFT", 12, 68)
  mine:SetText(L["Copy My Map Data"])
  FitButton(mine, 124)
  f.mine = mine
  f.kinds = {}
  local prev
  for _, k in ipairs(I.EXPORT_KINDS) do
    local c = Check(f, k[2])
    if prev then c:SetPoint("LEFT", prev.label, "RIGHT", 8, 0) else c:SetPoint("LEFT", mine, "RIGHT", 6, 0) end
    c:SetChecked(true)
    f.kinds[k[1]] = c
    prev = c
  end
  mine:SetScript("OnClick", function()
    local want = {}
    for key, c in pairs(f.kinds) do want[key] = c:GetChecked() and true or nil end
    local text, n = I.MapDataText(want)
    if n == 0 then
      status:SetText(L["|cffff6060Nothing of yours to copy|r for what's ticked: the herbs and ore you gathered, the NPCs you talked to, your pins, and the roads and walls you drew go here."])
      return
    end
    edit:SetText(text)
    edit:SetFocus()
    edit:HighlightText()
    status:SetText(n == 1 and L["1 line selected above: press Ctrl+C, then paste it anywhere. Players with AzerothGPS paste it here and press Import to add it to their map."]
      or string.format(L["%d lines selected above: press Ctrl+C, then paste it anywhere. Players with AzerothGPS paste it here and press Import to add it to their map."], n))
  end)
  Tip(mine, L["Copy My Map Data"], L["Writes your own map data in the box, selected for copying: the herbs and ore you gathered, the NPCs you talked to, your pins, and the roads and walls you drew. Tick what to include. Players with AzerothGPS paste it here and press Import to add it to their own map."])

  local add = Check(f, L["Add to the current route"])
  add:SetPoint("BOTTOMLEFT", 10, 38)
  f.add = add
  -- or: /way lines as herb and ore nodes for the map (unconfirmed until gathered)
  local asNodes = Check(f, L["/way as herb/ore nodes"])
  asNodes:SetPoint("LEFT", add.label, "RIGHT", 16, 0)
  Tip(asNodes, L["/way as herb/ore nodes"], L["Each /way line is a gathering node for the map instead of a stop, e.g. /way Elwynn Forest 43.2 65.1 Copper Vein. The name must say what it is (a herb or ore name). They show faded until you gather there. Circle them with \"Draw a farming area\" (map menu) to route through them."])
  f.asNodes = asNodes
  -- or: NPCs for the search (asked 2026-10-05: as herbs and ore are imported; unconfirmed until talked to)
  local asNpcs = Check(f, L["/way as NPCs"])
  asNpcs:SetPoint("LEFT", asNodes.label, "RIGHT", 16, 0)
  Tip(asNpcs, L["/way as NPCs"], L["Each /way line is an NPC for Search Places instead of a stop, e.g. /way Elwynn Forest 43.8 65.8 Innkeeper Farley. They're not drawn on the map: search for one to make it a stop. Talking to the NPC confirms where it is."])
  f.asNpcs = asNpcs
  -- (one or the other)
  asNodes:SetScript("OnClick", function(self) if self:GetChecked() then asNpcs:SetChecked(false) end end)
  asNpcs:SetScript("OnClick", function(self) if self:GetChecked() then asNodes:SetChecked(false) end end)

  -- the stops in the order they're listed, not the fastest (asked for 1.3.9; remembered: gps.importKeepOrder, also in
  -- Options > Routing)
  local keep = Check(f, L["Route in the listed order"])
  keep:SetPoint("BOTTOMLEFT", 10, 10)
  keep:SetScript("OnClick", function(self)
    if ns.settings then ns.settings.gps.importKeepOrder = self:GetChecked() and true or false end
    if ns.db then ns.db.importOrderTold = true end -- (chosen: no need to be told)
  end)
  Tip(keep, L["Route in the listed order"], L["Stops you import (pasted in Import and Share, /way lines, or a route another player sends) are visited in the order they're listed, not the fastest order. Stops added to that route later go at the end."])
  f.keep = keep

  local go = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  go:SetSize(90, 22)
  go:SetPoint("BOTTOMRIGHT", -12, 10)
  go:SetText(L["Import"])
  FitButton(go, 90)
  go:SetScript("OnClick", function()
    local ways = asNodes:GetChecked() and "nodes" or asNpcs:GetChecked() and "npcs" or "stops"
    local res = I.ImportText(edit:GetText(), ways, add:GetChecked())
    local msg = I.ImportSummary(res)
    ns.Print(msg)
    status:SetText(msg)
    -- (only a route, all of it in: done; else what happened stays in view)
    local done = res.stops and #res.rejected == 0 and res.wanted <= res.fit and res.had == 0 and res.skipped == 0
      and not I.orderTold -- (the one-time notice up: the window stays, its box glowing)
    for _, n in pairs(res.added) do done = done and n == 0 end
    if done then f:Hide() end
    if ns.GPS then
      if res.stops then ns.GPS.Follow() end
      ns.GPS.Redraw()
    end
  end)
  Tip(go, L["Import"], L["Takes in what's pasted above: /way lines as your route's stops (or, with the boxes beside, as herb and ore nodes or NPCs), and AzerothGPS map data (pins, roads, walls, herbs, ore and NPCs other players copied) into your own map. Here it says what was added, what you had already, and which lines couldn't be read."])
  f.go = go
  local cancel = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  cancel:SetSize(90, 22)
  cancel:SetPoint("RIGHT", go, "LEFT", -6, 0)
  cancel:SetText(L["Cancel"])
  FitButton(cancel, 90)
  cancel:SetScript("OnClick", function() f:Hide() end)

  -- (the window as wide as its longest row of buttons and boxes needs: a long language's ran past its edge)
  local function Row(...)
    local w = 0
    for i = 1, select("#", ...) do
      local x = select(i, ...)
      w = w + (type(x) == "number" and x or x.label and (x:GetWidth() + 1 + x.label:GetStringWidth())
        or x.GetStringWidth and x:GetStringWidth() or x:GetWidth())
    end
    return w
  end
  local boxes = { mine, 6 }
  for _, k in ipairs(I.EXPORT_KINDS) do boxes[#boxes + 1] = f.kinds[k[1]]; boxes[#boxes + 1] = 8 end
  local need = 24 + math.max(Row(copy, 12, sendLabel, 10, who, 6, whisper, 4, group), Row(unpack(boxes)),
    Row(add, 16, asNodes, 16, asNpcs), Row(keep, 16, cancel, 6, go))
  f.needWidth = need
  if need > f:GetWidth() then
    f:SetWidth(math.ceil(need))
    edit:SetWidth(math.ceil(need) - 60)
  end

  f:SetScript("OnShow", function()
    status:SetText(L["|cff9d9d9dTip: Shift+click a player's name in chat to put it in \"Link to\".|r"])
    add:SetChecked(false)
    add:SetEnabled(#ns.Nav.stops > 0)
    keep:SetChecked(ns.settings and ns.settings.gps.importKeepOrder and true or false)
    -- your target, if it's another player, is the default recipient
    if UnitIsPlayer("target") and not UnitIsUnit("target", "player") then
      local name, realm = UnitName("target")
      f.who:SetText(realm and realm ~= "" and (name .. "-" .. realm) or name)
    end
    edit:SetFocus()
  end)
  f:HookScript("OnHide", function()
    if ns.Tutorial and ns.Tutorial.StopPointing then ns.Tutorial.StopPointing(keep) end
  end)
  f:Hide()
  return f
end

-- Told once for the account (`db.importOrderTold`; asked for 1.3.9 with the listed order on by default): the first
-- import that keeps its listed order says so and where to change it, the stops already routed. A player who ticked or
-- unticked the box (or the option) is never told. The box glows while it shows (the tutorial's glow), when the Import
-- and Share window is open; an import from /way or a shared route doesn't open it. Returns the popup.
function I.TellOrder()
  local db = ns.db
  local st = ns.settings and ns.settings.gps
  if not db or db.importOrderTold or not (st and st.importKeepOrder) then return nil end
  local Ask = ns.GPS and ns.GPS.Ask or ns.Ask
  if not Ask then return nil end
  db.importOrderTold = true
  local box = win and win:IsShown() and win.keep or nil
  local T = ns.Tutorial
  if box and T and T.PointAt then T.PointAt(box, box.label) end
  local function Done()
    I.orderTold = nil
    if box and T and T.StopPointing then T.StopPointing(box) end
  end
  I.orderTold = Ask("AzerothGPSImportOrder", L["Imported stops are now routed in the order they're listed. For the fastest order instead, untick \"Route in the listed order\" in the Import and Share window (or Options > Routing). Your choice is remembered."],
    L["Got It"], nil, Done, Done, { single = true })
  return I.orderTold
end

function I.Toggle()
  win = win or Build()
  win:SetShown(not win:IsShown())
end

-- Text with one or more "/way ..." commands (typed, or several lines pasted into the chat
-- box, possibly run together on one line): each one's waypoint. Returns stops, errors.
function I.ParseWays(text, currentMap)
  -- every "/way" or "/tway" starts a new waypoint
  local lines = (text or ""):gsub("/[tT]?[wW][aA][yY]%s", "\n")
  return I.Parse(lines, currentMap)
end

function I.Enabled()
  return not ns.settings or ns.settings.gps.acceptWay ~= false
end

-- Add the waypoints in `text` to the route; tell the player what happened.
function I.AddWays(text)
  if not I.Enabled() then return end
  local stops, errors = I.ParseWays(text, C_Map.GetBestMapForUnit("player"))
  for _, e in ipairs(errors) do ns.Print("/way: " .. e) end
  if #stops == 0 then
    if #errors == 0 then ns.Print(L["/way: usage: /way [zone] x y [description]"]) end
    return
  end
  local before = #ns.Nav.stops
  local n = I.Apply(stops, true)
  local added = n - before
  if added < #stops then ns.Print(Format(L["/way: only %d stops fit (%d at most)"], added, ns.Nav.MAX_STOPS)) end
  if added == 1 then
    ns.Print(Format(L["stop %d: %s"], n, stops[1].name))
  elseif added > 1 then
    ns.Print(Format(L["%d stops added to the route (%d in all)"], added, n))
  end
  if ns.GPS then ns.GPS.Redraw() end
end

-- Questie's "Set TomTom Target" (its tracker's right-click menu, and Ctrl + click on a tracked quest; asked
-- 2026-11-09): the target becomes a route stop, TomTom installed or not (with it, TomTom's arrow is set too). Each
-- target is added to the current route (the user: added, not replacing the last one). Questie's TrackerUtils:SetTomTomTarget(title,
-- areaId, x, y), x and y in percent; its areaId a uiMap by its ZoneDB. Off with "Accept TomTom /way commands".
function I.QuestieTarget(title, areaId, x, y)
  if not I.Enabled() then return end
  local mods = QuestieLoader and QuestieLoader._modules
  local zdb = mods and mods.ZoneDB
  local ok, ui = pcall(function() return zdb and zdb:GetUiMapIdByAreaId(areaId) end)
  ui = ok and ui or nil
  local stop = ui and type(x) == "number" and type(y) == "number"
    and I.ToStop({ mapID = ui, x = x, y = y, name = title ~= "" and title or nil })
  if not stop then
    ns.Print(L["Questie: no map for that target"])
    return
  end
  stop.questie = true
  local N = ns.Nav
  for _, d in ipairs(N.stops) do -- (the same spot twice: once)
    if d.name == stop.name and d.cont == stop.cont and math.abs(d.x - stop.x) < 1 and math.abs(d.y - stop.y) < 1 then
      ns.Print(string.format(L["%s is already on your route."], stop.name))
      return
    end
  end
  local added, asked = N.AddStop(stop, ns.settings and ns.settings.gps.fastestOrder)
  if added then
    ns.Print(string.format(L["%s added to your route."], stop.name))
  elseif not asked then
    ns.Print(string.format(L["Questie: %s can't be added (the route is full or held)"], stop.name))
  end
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end

-- Questie's TrackerUtils (when Questie is loaded): its SetTomTomTarget goes to I.QuestieTarget first. Every caller
-- looks the method up on the module when it runs, so wrapping it here covers the menu and the Ctrl + click.
function I.HookQuestie()
  local mods = QuestieLoader and QuestieLoader._modules
  local tu = mods and mods.TrackerUtils
  if not tu or type(tu.SetTomTomTarget) ~= "function" or tu.agpsHooked then return false end
  local orig = tu.SetTomTomTarget
  tu.SetTomTomTarget = function(self, title, zone, x, y, ...)
    local ok, err = pcall(I.QuestieTarget, title, zone, x, y)
    if not ok and ns.Debug then ns.Debug("Questie target: " .. tostring(err)) end
    return orig(self, title, zone, x, y, ...)
  end
  tu.agpsHooked = true
  return true
end

-- "/way ..." typed in chat (our own command when TomTom isn't installed).
function I.SlashWay(msg)
  if not I.Enabled() then
    ns.Print(L["/way is turned off (AzerothGPS options: Accept TomTom /way commands)"])

    return
  end
  I.AddWays("/way " .. (msg or ""))
end

-- Several /way lines pasted into a chat box at once: take them all right away (the chat box
-- would only run the first) and empty the box.
local function OnChatText(box, userInput)
  if not userInput or not I.Enabled() then return end
  local text = box:GetText() or ""
  local _, count = text:gsub("/[tT]?[wW][aA][yY]%s", "")
  if count < 2 then return end
  box:SetText("")
  I.AddWays(text)
  if ChatEdit_DeactivateChat then pcall(ChatEdit_DeactivateChat, box) else box:ClearFocus() end
end

function I.Init()
  -- an import inbox (I.CheckInbox): every addon is loaded by now; asked a moment later
  if C_Timer and C_Timer.After then C_Timer.After(I.INBOX_DELAY, function() pcall(I.CheckInbox) end) end
  local loaded = C_AddOns and C_AddOns.IsAddOnLoaded and C_AddOns.IsAddOnLoaded("TomTom")
    or IsAddOnLoaded and IsAddOnLoaded("TomTom")
  -- whoever owns /way already (TomTom): also add its waypoints to our route
  local owner
  for key in pairs(SlashCmdList) do
    for i = 1, 9 do
      local cmd = _G["SLASH_" .. key .. i]
      if not cmd then break end
      if cmd:lower() == "/way" then owner = key end
    end
  end
  if owner then
    hooksecurefunc(SlashCmdList, owner, function(msg) if I.Enabled() then I.AddWays("/way " .. (msg or "")) end end)
  elseif not loaded then
    SLASH_AZEROTHGPSWAY1 = "/way"
    SLASH_AZEROTHGPSWAY2 = "/tway"
    SlashCmdList.AZEROTHGPSWAY = I.SlashWay
  end
  I.HookQuestie() -- (Questie's "Set TomTom Target": a stop)
  -- pasted lines in any chat box
  for i = 1, (NUM_CHAT_WINDOWS or 10) do
    local box = _G["ChatFrame" .. i .. "EditBox"]
    if box then box:HookScript("OnTextChanged", OnChatText) end
  end
  -- route lines in chat as links (I.LinkifyRoutes); a click on one asks its author for the route (the game
  -- hands "addon:" links to EventRegistry's "SetItemRef"; SetItemRef's hook as well: one ask per click)
  local addFilter = ChatFrameUtil and ChatFrameUtil.AddMessageEventFilter or ChatFrame_AddMessageEventFilter
  if addFilter then
    local function Filter(_, event, msg, author, ...)
      if event == "CHAT_MSG_WHISPER_INFORM" or event == "CHAT_MSG_BN_WHISPER_INFORM" then author = UnitName("player") end
      local out = I.LinkifyRoutes(msg, author)
      if out ~= msg then return false, out, author, ... end
    end
    for _, e in ipairs(I.LINK_EVENTS) do addFilter(e, Filter) end
  end
  local lastLink, lastAt
  local function RouteClick(link)
    if type(link) ~= "string" or not (link:find("^addon:AzerothGPS:route:") or link:find("^addon:AzerothGPS:pin:")) then
      return false
    end
    if link == lastLink and GetTime() - lastAt < 0.5 then return true end
    lastLink, lastAt = link, GetTime()
    if link:find("^addon:AzerothGPS:pin:") then return I.OnPinLink(link) end -- (a pin someone shared: add it?)
    return I.OnRouteLink(link)
  end
  if EventRegistry and EventRegistry.RegisterCallback then
    EventRegistry:RegisterCallback("SetItemRef", function(_, link) RouteClick(link) end, I)
  end
  hooksecurefunc("SetItemRef", function(link)
    if RouteClick(link) then return end
    -- a click on a map pin someone shared in chat: it becomes a stop
    if I.OnMapPinLink(link) then return end
    if type(link) ~= "string" or not IsModifiedClick("CHATLINK") then return end
    -- Shift+click on a player's name in chat, with this window open: fills in "Link to"
    if not win or not win:IsShown() then return end
    local name = link:match("^player:([^:]+)")
    if name and name ~= "" then
      win.who:SetText(name)
      win.who:SetCursorPosition(0)
    end
  end)
  -- the map pin: put back as the game's waypoint, then following the game's (I.MapPin)
  local function Waypoints()
    pcall(I.RestoreMapPin)
    local wf = CreateFrame("Frame")
    if pcall(wf.RegisterEvent, wf, "USER_WAYPOINT_UPDATED") then
      wf:SetScript("OnEvent", function() pcall(I.OnUserWaypoint) end)
    end
  end
  if C_Timer and C_Timer.After then C_Timer.After(3, Waypoints) else Waypoints() end
  -- routes shared by other players
  local register = C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix or RegisterAddonMessagePrefix
  if register then
    register(I.PREFIX)
    local ev = CreateFrame("Frame")
    ev:RegisterEvent("CHAT_MSG_ADDON")
    ev:SetScript("OnEvent", function(_, _, prefix, text, channel, sender) I.OnAddonMessage(prefix, text, channel, sender) end)
    if ns.TimeScript then ns.TimeScript(ev, "OnEvent", "events (sharing)") end
  end
end
