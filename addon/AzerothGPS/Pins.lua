-- Pins: places the player marks on the map. With pinning on (Options > Tools, `pinning`, on by default),
-- Shift + left-click on the map asks "Create Pin" (GPSFrame's G.AskCreatePin); then a name, an icon from
-- the game's icons (the ones a macro can have) and, where floors lie over each other, the floor (a
-- dungeon's floors, Undercity's, the floor under a cave's or capital's ground: GPSFrame's G.PinFloors).
-- Shown on the map (Options > Show on the map, `showCustomPins`) like a city location: double-click for a stop there
-- (with its height: its floor), right-click to remove it.
-- Kept account-wide (ns.db.pins) and shared with the map data like roads and walls ("Copy Map Data...":
-- the "P" lines, Feedback.RoadsText, unless unticked there): `agps import-shared` (or `agps pins`, from the
-- saved variables; not the road watcher: the player's pins are theirs until shared) puts them in
-- overrides/pins.json and Data/Pins.lua (ns.SharedPins, shown to everyone; ns.PinsIn, their times: the
-- player's own copies of those are dropped at login).
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local P = {}
ns.Pins = P

P.NAME_MAX = 40 -- letters
P.DEFAULT_ICON = "Interface\\Icons\\INV_Misc_QuestionMark"
P.COLS, P.ROWS, P.CELL = 10, 6, 34 -- the icon grid: columns, rows shown, pixels a cell
-- (if the game gives no icon list: a few of its own)
P.FALLBACK_ICONS = { "INV_Misc_QuestionMark", "INV_Misc_Map02", "INV_Misc_Bag_08", "INV_Misc_Coin_01",
  "INV_Misc_Herb_07", "INV_Ore_Copper_01", "INV_Pick_02", "INV_Sword_04", "INV_Shield_06", "INV_Helmet_03",
  "INV_Misc_Bone_HumanSkull_01", "INV_Misc_Note_02", "INV_Misc_Spyglass_02", "INV_Misc_Rune_01",
  "INV_Misc_PocketWatch_01", "Ability_Warrior_ShieldWall", "Ability_DualWield" }

function P.Own()
  ns.db.pins = ns.db.pins or {}
  return ns.db.pins
end

-- A pin's icon as a texture: a file id, a path, or an icon's name (under Interface\Icons).
function P.IconTexture(icon)
  if type(icon) == "number" then return icon end
  if type(icon) ~= "string" or icon == "" then return P.DEFAULT_ICON end
  if icon:find("[\\/]") then return icon end
  return "Interface\\Icons\\" .. icon
end

-- A name as kept and shared: one line, no escape codes ("|"), "Pin" when empty (MapText.CleanName).
function P.CleanName(s)
  s = ns.MapText.CleanName(s)
  return s ~= "" and s or L["Pin"]
end

-- Every pin to show: the player's own and the shared ones (Data/Pins.lua) they haven't removed. Each:
-- { level, x, y, z, down, icon, name, time, shipped }.
function P.All()
  local out, mine = {}, {}
  for _, p in ipairs(P.Own()) do
    out[#out + 1] = p
    if p.time then mine[p.time] = true end
  end
  local gone = ns.db.pinsRemoved or {}
  for _, p in ipairs(ns.SharedPins or {}) do
    if not gone[p.time] and not mine[p.time] then out[#out + 1] = p end -- (one the player keeps too: theirs, once)
  end
  return out
end

-- Where a pin is, for the search (asked 2026-10-03: "Auction House  Stormwind City"): its dungeon's or raid's name,
-- else the city or zone at it. Kept on the player's own pins (`place`, set when made; older ones get it the first time
-- it's asked), worked out each time for the shared ones (the shipped data isn't changed).
function P.PlaceName(pin)
  if pin.place then return pin.place end
  local name
  local lvl = pin.level
  if lvl and lvl >= 20000 and ns.Instances and ns.Instances[lvl] then
    name = ns.Instances[lvl].name
  elseif lvl and ns.GPS and ns.GPS.LocateWorld then
    local _, n = ns.GPS.LocateWorld(ns.Geo.Base(lvl), pin.x, pin.y)
    name = n
  end
  if name then
    for _, own in ipairs(P.Own()) do
      if own == pin then pin.place = name break end
    end
  end
  return name
end

-- A pin made where the player stands (within HERE_YD): what the game tells of where they are, kept on the pin (asked
-- 2026-10-03: track the floor as well as we can). Whether they were indoors, the subzone ("The Great Forge"), and
-- their height when the game gives it (WoW Forever doesn't: UnitPosition's height is always 0, so the floor itself
-- is the Create Pin dialog's, `z`/`down`). Not in a dungeon: the game hides the position there.
P.HERE_YD = 30
function P.NoteHere(p)
  local Geo = ns.Geo
  local px, py, pc = Geo.RealPlayerWorld() -- (what the game says of where the player really is)
  if not (px and p.level and p.x) or Geo.Base(pc) ~= Geo.Base(p.level) then return end
  if (px - p.x) ^ 2 + (py - p.y) ^ 2 > P.HERE_YD ^ 2 then return end
  p.indoors = IsIndoors and IsIndoors() and true or nil
  local sub = GetMinimapZoneText and GetMinimapZoneText()
  p.subzone = sub and sub ~= "" and sub or nil
  local z = ns.Nav and ns.Nav.PlayerZ and ns.Nav.PlayerZ()
  p.playerZ = z or nil
end

-- A new pin { level, x, y, z, down, icon, name }: kept, and returned. Its time is its id (one no other
-- pin has, the shared ones' included).
function P.Add(pin)
  local t = time and time() or 0
  local used = {}
  for _, p in ipairs(P.All()) do
    if p.time then used[p.time] = true end
  end
  for k in pairs(ns.PinsIn or {}) do used[k] = true end
  while used[t] do t = t + 1 end
  local p = { level = pin.level, x = pin.x, y = pin.y, z = pin.z, down = pin.down, icon = pin.icon or P.DEFAULT_ICON,
    name = P.CleanName(pin.name), time = t }
  -- (a pin from an NPC's search row: its creature id and plain name, for another addon's Shift-click, API 20)
  if tonumber(pin.npc) then p.npc, p.npcName = tonumber(pin.npc), pin.npcName and P.CleanName(pin.npcName) or nil end
  local own = P.Own()
  own[#own + 1] = p
  P.PlaceName(p) -- (where it was made: the search shows it)
  P.NoteHere(p) -- (and, made where the player stands: indoors, the subzone, their height if given)
  if ns.MarkUnsaved then ns.MarkUnsaved("pin:" .. t, "add") end
  P.Changed()
  return p
end

-- A pin from the search (asked 2026-11-14: "add an option beside searched NPCs to a custom pin for its location
-- permanently. Pick the best icon that makes sense for this"): the search list's Pin button (GPSFrame's
-- G.PinSearchEntry). An NPC's icon by what it does, the game's own icons as the city places' (Layers.CITY_ICONS):
-- a trainer its class's or profession's (else a book), a flight master the city places' wyvern, an innkeeper the
-- hearthstone, a banker the bank's bag, an auctioneer a coin, a stable master the beast taming one, a battlemaster the
-- rune, one who repairs an anvil (blacksmithing), a vendor a bag, a quest giver the "!", anyone else a head.
P.NPC_ICONS = {
  trainer = "Interface\\Icons\\INV_Misc_Book_09", weapon = "Interface\\Icons\\INV_Sword_04",
  flight = "Interface\\Icons\\Ability_Mount_Wyvern_01", inn = "Interface\\Icons\\INV_Misc_Rune_01",
  bank = "Interface\\Icons\\INV_Misc_Bag_10_Blue", auction = "Interface\\Icons\\INV_Misc_Coin_02",
  stable = "Interface\\Icons\\Ability_Hunter_BeastTaming", battle = "Interface\\Icons\\INV_Misc_Rune_07",
  repair = "Interface\\Icons\\Trade_BlackSmithing", vendor = "Interface\\Icons\\INV_Misc_Bag_10",
  quest = "Interface\\GossipFrame\\AvailableQuestIcon", npc = "Interface\\Icons\\INV_Misc_Head_Human_01",
  -- (Quick Find's Ammo, asked 2026-11-14)
  ammo = "Interface\\Icons\\INV_Ammo_Arrow_01", arrows = "Interface\\Icons\\INV_Ammo_Arrow_02",
  bullets = "Interface\\Icons\\INV_Ammo_Bullet_02",
}
-- The icon for search entry `e` of an NPC: a shipped one's by its services (`e.shipped`: svc, trainer), one talked to
-- by its title and what its window was (`vendor`, `repair`).
function P.NpcIcon(e)
  local I, Lay = P.NPC_ICONS, ns.Layers
  local function city(word) -- (a class's or profession's own, as the city places': nil when it has none)
    local icon = Lay and Lay.CityIcon and Lay.CityIcon(word)
    return icon ~= (Lay and Lay.CITY_DEFAULT_ICON) and icon or nil
  end
  local s = e.shipped
  if s then
    local has = function(c) return Lay.NpcOffers(s, c) end
    if s.trainer == "Weapon" then return I.weapon end
    if has("t") then return (s.trainer and city(s.trainer)) or I.trainer end
    if has("f") then return I.flight end
    if has("i") then return I.inn end
    if has("b") then return I.bank end
    if has("a") then return I.auction end
    if has("s") then return I.stable end
    if has("m") then return I.battle end
    if has("r") then return I.repair end
    if has("v") then return I.vendor end
    if has("q") then return I.quest end
    return I.npc
  end
  local t = (e.title or ""):lower()
  if t:find("weapon master", 1, true) then return I.weapon end
  if t:find("trainer", 1, true) then return city(t) or I.trainer end
  for _, w in ipairs({ { "flight master", I.flight }, { "gryphon", I.flight }, { "wind rider", I.flight },
    { "hippogryph", I.flight }, { "bat handler", I.flight }, { "innkeeper", I.inn }, { "banker", I.bank },
    { "auctioneer", I.auction }, { "stable", I.stable }, { "battlemaster", I.battle } }) do
    if t:find(w[1], 1, true) then return w[2] end
  end
  if e.repair then return I.repair end
  if e.vendor then return I.vendor end
  if t:find("quest", 1, true) then return I.quest end
  return I.npc
end
-- One of the pins (the player's or shared) on `level` within SAME_YD of (x, y), or nil: the search's Pin button says
-- it's pinned already instead of making another.
P.SAME_YD = 3
function P.PinnedAt(level, x, y)
  for _, p in ipairs(P.All()) do
    if p.level == level and p.x and (p.x - x) ^ 2 + (p.y - y) ^ 2 <= P.SAME_YD ^ 2 then return p end
  end
  return nil
end
-- A search entry's pin name: an NPC's name and title, "Innkeeper Farley <Innkeeper>" (its name alone when that's
-- longer than a pin's name may be); a city place's full name ("Ironforge Inn").
function P.SearchPinName(e)
  if e.place then return e.place end
  if e.title and #e.name + #e.title + 3 <= P.NAME_MAX then return e.name .. " <" .. e.title .. ">" end
  return e.name
end
-- Pin search entry `e` (an NPC, shipped or talked to, or a city place) for good: at its spot, on its level and floor
-- (`z`; `down`, under a cave's or capital's ground), named and with an icon as above. Returns the new pin, or nil and
-- the one there already.
function P.AddFromSearch(e, down)
  if not (e and e.x and e.y and e.cont) then return nil end
  local have = P.PinnedAt(e.cont, e.x, e.y)
  if have then return nil, have end
  local icon = e.npc and P.NpcIcon(e) or e.tex or P.DEFAULT_ICON
  return P.Add({ level = e.cont, x = e.x, y = e.y, z = e.z, down = down, icon = icon, name = P.SearchPinName(e),
    npc = e.npc and e.id or nil, npcName = e.npc and e.name or nil })
end

-- Take pin `p` off the map: the player's own is gone; a shared one is hidden here, and its removal
-- shared with the map data. (Its time is kept as removed either way, for good: one of the player's in the data is
-- shared by then.)
function P.Remove(p)
  if p.time then
    ns.db.pinsRemoved = ns.db.pinsRemoved or {}
    ns.db.pinsRemoved[p.time] = true
  end
  local own = P.Own()
  for i = #own, 1, -1 do
    if own[i] == p then table.remove(own, i) end
  end
  if ns.MarkUnsaved then ns.MarkUnsaved("pin:" .. tostring(p.time), "remove") end
  P.Changed()
end

function P.Changed()
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end

-- Pins someone shared, taken in (the dev tools' import of a Copy Map Data text): an added one kept with its
-- time (left out: one here already, or in the data), marked `shared`; a removal of one the data has hides
-- it here, marked "shared". The road watcher takes in those marked so (`agps watch-roads`), never the
-- player's own. Each { add = true, level, x, y, z, down, icon, name, time } or { remove = true, time }.
-- Returns how many added, removed.
function P.AddShared(list)
  local own, shipped = P.Own(), ns.PinsIn or {}
  local have = {}
  for _, p in ipairs(own) do
    if p.time then have[p.time] = true end
  end
  local added, removed = 0, 0
  for _, s in ipairs(list or {}) do
    if s.remove and s.time then
      if shipped[s.time] and not (ns.db.pinsRemoved and ns.db.pinsRemoved[s.time]) then
        ns.db.pinsRemoved = ns.db.pinsRemoved or {}
        ns.db.pinsRemoved[s.time] = "shared"
        removed = removed + 1
      end
    elseif s.time and s.x and s.y and not have[s.time] and not shipped[s.time] then
      own[#own + 1] = { level = s.level, x = s.x, y = s.y, z = s.z, down = s.down, icon = s.icon or P.DEFAULT_ICON,
        name = P.CleanName(s.name), time = s.time, shared = true }
      have[s.time] = true
      added = added + 1
    end
  end
  if added + removed > 0 then P.Changed() end
  return added, removed
end

-- Pins a player imported (the Import and Share window: MapText's pin lines and chat tags; asked 2026-10-06), as their
-- own and marked `imported` (never `shared`: the road watcher takes only those, and pins never ship): one they have
-- already (the same name on its level within 2 yd, or its time) left out; a pin's time kept as its id when no other
-- pin has it, else a new one. Each { level, x, y, z, down, icon, name, time }. Returns how many added, had already.
function P.AddImported(list)
  local own = P.Own()
  local used = {}
  for _, p in ipairs(P.All()) do
    if p.time then used[p.time] = true end
  end
  for k in pairs(ns.PinsIn or {}) do used[k] = true end
  -- (the player's pins by level and 2-yd cell: an import of thousands, not each against all of them)
  local near = {}
  local function cell(level, x, y) return level .. ":" .. math.floor(x / 2) .. ":" .. math.floor(y / 2) end
  local function index(p)
    local k = cell(p.level or 0, p.x, p.y)
    near[k] = near[k] or {}
    near[k][#near[k] + 1] = p
  end
  for _, p in ipairs(own) do
    if p.x and p.y then index(p) end
  end
  local added, had = 0, 0
  local now = time and time() or 0
  for _, s in ipairs(list or {}) do
    local name = P.CleanName(s.name)
    local dup = false -- (the same pin: on its level within 2 yd, by its name or its time)
    local cx, cy = math.floor(s.x / 2), math.floor(s.y / 2)
    for dx = -1, 1 do
      for dy = -1, 1 do
        for _, p in ipairs(near[s.level .. ":" .. (cx + dx) .. ":" .. (cy + dy)] or {}) do
          if (p.x - s.x) ^ 2 + (p.y - s.y) ^ 2 < 4 and (p.name == name or (s.time and p.time == s.time)) then dup = true end
        end
      end
    end
    if dup then
      had = had + 1
    else
      local t = s.time
      if not t or used[t] then
        t = now
        while used[t] do t = t + 1 end
      end
      used[t] = true
      local p = { level = s.level, x = s.x, y = s.y, z = s.z, down = s.down, icon = s.icon or P.DEFAULT_ICON, name = name,
        time = t, imported = true }
      own[#own + 1] = p
      index(p)
      added = added + 1 -- (the import counts as one unsaved change: its caller's)
    end
  end
  if added > 0 then P.Changed() end
  return added, had
end

-- (Nothing of the player's pins is dropped at login any more, asked 2026-10-06: keep data forever. Pins never ship,
-- Data/Pins.lua stays empty; one that did would show once, the player's own copy, P.All.)

-- The pins to share ("Copy Map Data...", Feedback.RoadsText): the player's not in the data yet, and the
-- shared ones they removed. `agps import-shared` reads them back:
--   P add <level> <time> <x,y> [z=<height>] [down=1|0] icon=<file id or path> name=<the rest of the line>
--   P remove <time>
function P.ShareLines()
  local lines = {}
  local shipped = ns.PinsIn or {}
  for _, p in ipairs(P.Own()) do
    if p.time and p.x and p.y and not shipped[p.time] then lines[#lines + 1] = ns.MapText.PinLine(p, P.DEFAULT_ICON) end
  end
  local gone = {}
  for t in pairs(ns.db.pinsRemoved or {}) do
    if shipped[t] then gone[#gone + 1] = t end
  end
  table.sort(gone)
  for _, t in ipairs(gone) do lines[#lines + 1] = "P remove " .. t end
  return lines
end

-- The icons to pick from: the game's list for macros (file ids, or names), worked out once.
local icons
function P.Icons()
  if icons then return icons end
  icons = {}
  local seen = {}
  local function take(fn)
    if type(fn) ~= "function" then return end
    local list = {}
    local ok, r = pcall(fn, list)
    if ok and type(r) == "table" and r ~= list then list = r end -- (a client that returns it instead)
    for _, v in ipairs(list) do
      if v and not seen[v] then
        seen[v] = true
        icons[#icons + 1] = v
      end
    end
  end
  take(GetLooseMacroIcons)
  take(GetLooseMacroItemIcons)
  take(GetMacroIcons)
  take(GetMacroItemIcons)
  if #icons == 0 then
    for _, n in ipairs(P.FALLBACK_ICONS) do icons[#icons + 1] = n end
  end
  return icons
end

-- The dialog: a name, the icon grid (scrolled with the mouse wheel or the bar beside it), the floor.
local dlg
P.selected, P.top = 1, 0 -- the icon picked (kept for the next pin), the grid's first row
local function Button(parent, text, w)
  local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(w, 22)
  b:SetText(text)
  return b
end
local function Dialog()
  if dlg then return dlg end
  -- (the map window's frame without the logo, as every popup: ns.Window)
  local f = ns.Window("AzerothGPSPinDialog", P.COLS * P.CELL + 64, P.ROWS * P.CELL + 160, L["Create Pin"])
  local top = f.top

  local label = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  label:SetPoint("TOPLEFT", 20, top - 18)
  label:SetText(L["Name"])
  local name = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
  name:SetSize(220, 20)
  name:SetPoint("LEFT", label, "RIGHT", 12, 0)
  name:SetAutoFocus(false)
  name:SetMaxLetters(P.NAME_MAX)
  name:SetScript("OnEnterPressed", function() P.Confirm() end)
  name:SetScript("OnEscapePressed", function() f:Hide() end)
  f.name = name
  local preview = f:CreateTexture(nil, "ARTWORK")
  preview:SetSize(36, 36)
  preview:SetPoint("TOPRIGHT", -24, top - 8)
  f.preview = preview

  local pick = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  pick:SetPoint("TOPLEFT", 20, top - 50)
  pick:SetText(L["Choose an icon:"])
  local grid = CreateFrame("Frame", nil, f)
  grid:SetSize(P.COLS * P.CELL, P.ROWS * P.CELL)
  grid:SetPoint("TOPLEFT", 20, top - 66)
  grid:EnableMouseWheel(true)
  grid:SetScript("OnMouseWheel", function(_, delta) P.Scroll(delta > 0 and -1 or 1) end)
  local sel = grid:CreateTexture(nil, "BACKGROUND")
  sel:SetSize(P.CELL, P.CELL)
  sel:SetColorTexture(1, 0.82, 0, 0.75)
  f.sel = sel
  f.cells = {}
  for r = 1, P.ROWS do
    for c = 1, P.COLS do
      local b = CreateFrame("Button", nil, grid)
      b:SetSize(P.CELL - 4, P.CELL - 4)
      b:SetPoint("TOPLEFT", (c - 1) * P.CELL + 2, -((r - 1) * P.CELL + 2))
      b.icon = b:CreateTexture(nil, "ARTWORK")
      b.icon:SetAllPoints()
      local hl = b:CreateTexture(nil, "HIGHLIGHT")
      hl:SetAllPoints()
      hl:SetColorTexture(1, 1, 1, 0.25)
      b:SetScript("OnClick", function(self)
        P.selected = self.index
        P.Refresh()
      end)
      b:SetScript("OnDoubleClick", function(self)
        P.selected = self.index
        P.Confirm()
      end)
      f.cells[#f.cells + 1] = b
    end
  end
  local bar = CreateFrame("Slider", nil, f)
  bar:SetOrientation("VERTICAL")
  bar:SetSize(14, P.ROWS * P.CELL)
  bar:SetPoint("TOPLEFT", grid, "TOPRIGHT", 6, 0)
  local barBg = bar:CreateTexture(nil, "BACKGROUND")
  barBg:SetAllPoints()
  barBg:SetColorTexture(0.15, 0.15, 0.15, 0.9)
  local thumb = bar:CreateTexture(nil, "OVERLAY")
  thumb:SetColorTexture(0.7, 0.7, 0.7, 1)
  thumb:SetSize(14, 28)
  bar:SetThumbTexture(thumb)
  bar:SetValueStep(1)
  if bar.SetObeyStepOnDrag then bar:SetObeyStepOnDrag(true) end
  bar:SetScript("OnValueChanged", function(_, v)
    if P.syncing then return end
    P.top = math.floor(v + 0.5)
    P.Refresh()
  end)
  f.bar = bar
  local count = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  count:SetPoint("TOPLEFT", grid, "BOTTOMLEFT", 0, -4)
  f.count = count

  -- the floor, where floors lie over each other there
  local floorText = f:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  floorText:SetPoint("BOTTOMLEFT", 20, 50)
  f.floorText = floorText
  local nextF = Button(f, ">", 26)
  nextF:SetPoint("BOTTOMRIGHT", -20, 46)
  nextF:SetScript("OnClick", function() P.StepFloor(1) end)
  local prevF = Button(f, "<", 26)
  prevF:SetPoint("RIGHT", nextF, "LEFT", -4, 0)
  prevF:SetScript("OnClick", function() P.StepFloor(-1) end)
  f.floorButtons = { prevF, nextF }

  local ok = Button(f, L["Create Pin"], 110)
  ok:SetPoint("BOTTOMRIGHT", -20, 14)
  ok:SetScript("OnClick", function() P.Confirm() end)
  local cancel = Button(f, L["Cancel"], 90)
  cancel:SetPoint("RIGHT", ok, "LEFT", -8, 0)
  cancel:SetScript("OnClick", function() f:Hide() end)
  f.ok = ok
  -- (asked 2026-10-04: a pin is kept when the game saves, at logout or a /reload; a crash before then loses it)
  local note = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  note:SetPoint("BOTTOMLEFT", 20, 18)
  note:SetPoint("RIGHT", cancel, "LEFT", -8, 0)
  note:SetJustifyH("LEFT")
  note:SetText(L["Saved at logout or /reload"])
  f.saveNote = note
  dlg = f
  return f
end

-- Scroll the icon grid `rows` rows (down: positive).
function P.Scroll(rows)
  P.top = (P.top or 0) + rows
  P.Refresh()
end

-- Step the pin's floor: through the floors there, and "every floor" past either end.
function P.StepFloor(d)
  local e = P.editing
  if not e or #e.floors == 0 then return end
  e.floor = (e.floor + d) % (#e.floors + 1)
  P.Refresh()
end

-- The floor's line in the dialog.
function P.FloorLine(e)
  local fl = e and e.floors[e.floor]
  return fl and string.format(L["Floor: %s"], fl.label) or L["Floor: every floor here"]
end

function P.Refresh()
  local f = dlg
  if not f then return end
  local list = P.Icons()
  local rows = math.ceil(#list / P.COLS)
  local maxTop = math.max(0, rows - P.ROWS)
  P.top = math.max(0, math.min(P.top or 0, maxTop))
  P.selected = math.max(1, math.min(P.selected or 1, #list))
  f.sel:Hide()
  for i, b in ipairs(f.cells) do
    local k = P.top * P.COLS + i
    local icon = list[k]
    b.index = k
    if icon then
      b.icon:SetTexture(P.IconTexture(icon))
      b:Show()
      if k == P.selected then
        f.sel:ClearAllPoints()
        f.sel:SetPoint("CENTER", b, "CENTER")
        f.sel:Show()
      end
    else
      b:Hide()
    end
  end
  f.preview:SetTexture(P.IconTexture(list[P.selected]))
  local first = P.top * P.COLS + 1
  f.count:SetText(string.format(L["Icons %d-%d of %d (mouse wheel scrolls)"], math.min(first, #list),
    math.min(first + P.COLS * P.ROWS - 1, #list), #list))
  P.syncing = true
  f.bar:SetMinMaxValues(0, maxTop)
  f.bar:SetValue(P.top)
  P.syncing = false
  local e = P.editing
  local floors = e and #e.floors > 0
  f.floorText:SetShown(floors and true or false)
  for _, b in ipairs(f.floorButtons) do b:SetShown(floors and true or false) end
  if floors then f.floorText:SetText(P.FloorLine(e)) end
end

-- Open the dialog for a pin at `spot`: { level, x, y, floors = { { label, z, down }, ... } (bottom up),
-- pick = the floor picked (0: every floor) }.
function P.OpenEditor(spot)
  local f = Dialog()
  P.editing = { level = spot.level, x = spot.x, y = spot.y, floors = spot.floors or {}, floor = spot.pick or 0 }
  f.name:SetText("")
  P.top = math.floor(((P.selected or 1) - 1) / P.COLS) -- (the icon picked last in view)
  P.Refresh()
  f:Show()
  f.name:SetFocus()
end

-- "Create Pin" in the dialog: the pin, with the name, icon and floor picked.
function P.Confirm()
  local e = P.editing
  if not (e and dlg) then return nil end
  local fl = e.floors[e.floor]
  local p = P.Add({ level = e.level, x = e.x, y = e.y, z = fl and fl.z or nil, down = fl and fl.down,
    icon = P.Icons()[P.selected] or P.DEFAULT_ICON, name = dlg.name:GetText() })
  P.editing = nil
  dlg.name:ClearFocus()
  dlg:Hide()
  if ns.Print then ns.Print(string.format(L["pinned %s (double-click it for a stop, right-click to remove it)"], p.name)) end

  return p
end
