-- Custom searches (asked 2026-11-16 for 1.3.5: "a custom map menu button feature that effectively will auto search and
-- pick the top result and set a destination. Players create these, any icon and name with description (enforce letter
-- limits) ... account wide ... like the search field is "repair" and it'd function like the repair one under quick find
-- menu. Players can choose this to be a button on map menu or it can be under the quick find menu. Allow them to
-- add/remove the current quick find buttons in this section as well").
--
-- One list for the whole account (AzerothGPSDB.searches): Quick Find's own entries (GPS.QUICK_FIND, `builtin` its kind:
-- seeded, editable, removable, back with Restore Defaults) and the player's. Each: a name, a description (its tooltip),
-- an icon (a file id or an Interface\Icons path), the words searched and where it goes: in Quick Find's flyout, or a
-- button of its own in the map menu (GPS.QuickPlace: always shown or in the menu, going up or right). Clicked: the
-- search the search box would run, from where the player stands now (the nearest of a kind, "repair"), its top result
-- the destination, as Quick Find's own do.
local _, ns = ...
local L = ns.L
local Format = string.format
local S = {}
ns.Searches = S

S.NAME_MAX = 24 -- letters
S.DESC_MAX = 120
S.TEXT_MAX = 40
S.TEXT_MIN = 2 -- (the search's own least: shorter finds nothing)
S.MAX = 20 -- searches in the list
S.DEFAULT_ICON = "Interface\\Icons\\INV_Misc_QuestionMark"
S.PLACES = { "quickFind", "menuUp", "menuRight", "barUp", "barRight" } -- (a map menu one: GPS.QUICK_PLACES')

-- Letters (UTF-8 characters, not bytes: an accented name is as long as it looks).
function S.Len(s)
  local n = 0
  for _ in tostring(s or ""):gmatch("[%z\1-\127\194-\244][\128-\191]*") do n = n + 1 end
  return n
end
-- `s` cut to `max` letters.
function S.Cut(s, max)
  s = tostring(s or "")
  if S.Len(s) <= max then return s end
  local out, n = {}, 0
  for ch in s:gmatch("[%z\1-\127\194-\244][\128-\191]*") do
    n = n + 1
    if n > max then break end
    out[n] = ch
  end
  return table.concat(out)
end
local function Trim(s) return (tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", "")) end

-- An icon as typed: a file id ("136243"), a path, or an icon's name under Interface\Icons ("INV_Misc_Bag_08"). Nil:
-- nothing typed.
function S.IconFrom(v)
  if type(v) == "number" then return v end
  v = Trim(v)
  if v == "" then return nil end
  local n = tonumber(v)
  if n then return math.floor(n) end
  if not v:find("[\\/]") then v = "Interface\\Icons\\" .. v end
  return v
end

local function DB()
  local db = ns.db
  if not db then return nil end
  if type(db.searches) ~= "table" then
    -- (first time, or a version before 1.3.5: Quick Find's own, as they were)
    db.searches = {}
    db.searchesRemoved = db.searchesRemoved or {}
    for _, e in ipairs(ns.GPS and ns.GPS.QUICK_FIND or {}) do
      db.searches[#db.searches + 1] = { id = "b:" .. e.kind, builtin = e.kind, place = "quickFind" }
    end
  else
    -- (a built-in added since, not removed by the player: in its place among them)
    db.searchesRemoved = db.searchesRemoved or {}
    local have = {}
    for _, r in ipairs(db.searches) do if r.builtin then have[r.builtin] = true end end
    for i, e in ipairs(ns.GPS and ns.GPS.QUICK_FIND or {}) do
      if not have[e.kind] and not db.searchesRemoved[e.kind] then
        table.insert(db.searches, math.min(i, #db.searches + 1), { id = "b:" .. e.kind, builtin = e.kind, place = "quickFind" })
      end
    end
  end
  return db
end

local function Builtin(r)
  if not r.builtin then return nil end
  for _, e in ipairs(ns.GPS and ns.GPS.QUICK_FIND or {}) do
    if e.kind == r.builtin then return e end
  end
  return nil
end
S.Builtin = Builtin

-- The list (rows as saved; empty without the saved variables).
function S.List()
  local db = DB()
  return db and db.searches or {}
end
function S.Get(id)
  for i, r in ipairs(S.List()) do
    if r.id == id then return r, i end
  end
  return nil
end

-- A row's name, description, icon (a texture) and words searched: its own, else its built-in's.
function S.Name(r)
  local b = Builtin(r)
  return r.name or (b and b.label) or "?"
end
function S.Desc(r)
  if r.desc then return r.desc end
  local b = Builtin(r)
  if b and b.sub then return L["Click for arrows or bullets. Right-click: the search, nearest first."] end
  return L["Click: a stop at the nearest. Right-click: the search, nearest first."]
end
function S.Icon(r)
  if r.icon then return r.icon end
  local b = Builtin(r)
  if b and ns.GPS and ns.GPS.QuickFindIcon then return ns.GPS.QuickFindIcon(b) end
  return S.DEFAULT_ICON
end
function S.Text(r)
  if r.text then return r.text end
  local b = Builtin(r)
  return b and b.kind or ""
end
-- Shown for this character: a built-in for one class (a hunter's Stable Master, Ammo) only for it.
function S.Shown(r)
  local b = Builtin(r)
  if not (b and b.class) then return true end
  local class = UnitClass and select(2, UnitClass("player"))
  return b.class == class
end
-- Where it goes: "quickFind", or its place in the map menu (GPS.QUICK_PLACES').
function S.Place(r)
  local p = r.place or "quickFind"
  for _, q in ipairs(S.PLACES) do
    if q == p then return p end
  end
  return "quickFind"
end
-- The map menu button's id (GPS's quick buttons): "cs:" and the row's.
function S.QuickId(r) return "cs:" .. r.id end
function S.FromQuickId(id)
  local rid = type(id) == "string" and id:match("^cs:(.+)$")
  return rid and S.Get(rid) or nil
end

-- Fields checked and cut to their limits: { name, desc, icon, text, place }, or nil and why.
function S.Clean(f)
  local name = S.Cut(Trim(f.name), S.NAME_MAX)
  if name == "" then return nil, L["Give it a name."] end
  local text = S.Cut(Trim(f.text), S.TEXT_MAX)
  if S.Len(text) < S.TEXT_MIN then return nil, Format(L["Type at least %d letters to search for."], S.TEXT_MIN) end
  local desc = S.Cut(Trim(f.desc), S.DESC_MAX)
  return { name = name, desc = desc ~= "" and desc or nil, icon = S.IconFrom(f.icon) or S.DEFAULT_ICON, text = text,
    place = f.place or "quickFind" }
end

local function Changed()
  if ns.GPS and ns.GPS.SyncCustomQuick then ns.GPS.SyncCustomQuick() end
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
end
S.Changed = Changed

-- A new one (at the end): its row, or nil and why.
function S.Add(f)
  local db = DB()
  if not db then return nil, "no saved variables" end
  if #db.searches >= S.MAX then return nil, Format(L["At most %d searches: remove one first."], S.MAX) end
  local c, why = S.Clean(f)
  if not c then return nil, why end
  db.searchesNext = (db.searchesNext or 0) + 1
  c.id = "c" .. db.searchesNext
  db.searches[#db.searches + 1] = c
  Changed()
  return c
end
-- Changed: a built-in keeps its kind (and Ammo its own flyout), its fields the player's now.
function S.Update(id, f)
  local r = S.Get(id)
  if not r then return nil, "not found" end
  local c, why = S.Clean(f)
  if not c then return nil, why end
  for k, v in pairs(c) do r[k] = v end
  if r.icon == S.DEFAULT_ICON and r.builtin and not S.IconFrom(f.icon) then r.icon = nil end
  Changed()
  return r
end
function S.SetPlace(id, place)
  local r = S.Get(id)
  if not r then return false end
  r.place = place
  Changed()
  return true
end
function S.Remove(id)
  local db = DB()
  local r, i = S.Get(id)
  if not (db and r) then return false end
  table.remove(db.searches, i)
  if r.builtin then db.searchesRemoved[r.builtin] = true end
  Changed()
  return true
end
-- Quick Find's own back as they were (in their order, first), the player's kept after them.
function S.RestoreDefaults()
  local db = DB()
  if not db then return end
  local mine = {}
  for _, r in ipairs(db.searches) do
    if not r.builtin then mine[#mine + 1] = r end
  end
  db.searches, db.searchesRemoved = {}, {}
  for _, e in ipairs(ns.GPS and ns.GPS.QUICK_FIND or {}) do
    db.searches[#db.searches + 1] = { id = "b:" .. e.kind, builtin = e.kind, place = "quickFind" }
  end
  for _, r in ipairs(mine) do
    if #db.searches < S.MAX then db.searches[#db.searches + 1] = r end
  end
  Changed()
end

-- The search's top result for `text`, from where the player is: a common kind typed ("repair", "flight master") the
-- nearest of it (Quick Find's own way), else the search box's first. Nil: nothing found.
function S.Top(text)
  local G = ns.GPS
  if not (G and G.SearchPlacesPlain) then return nil end
  local words = {}
  for w in G.SearchLower(text):gmatch("%S+") do words[#words + 1] = w end
  for _, k in ipairs(G.GENERIC_KINDS or {}) do
    if G.KindTyped(words, k) then
      local found = G.QuickFindNearest(text)
      if found then return found end
      break
    end
  end
  for _, e in ipairs(G.SearchPlacesPlain(text, 50)) do
    if e.x and e.cont then return e end
  end
  return nil
end
-- Clicked: its top result the destination (as picking it in the search); said in chat when there's none.
function S.Run(r)
  local G = ns.GPS
  if not G or G.Held() then return nil end
  local found = S.Top(S.Text(r))
  if not found then
    ns.Print(Format(L["Quick Find: nothing found for %s."], S.Name(r)))
    return nil
  end
  if G.PickSearchEntry then G.PickSearchEntry(found) end
  return found
end

-- The places a search can go, in the order its dropdowns list them, and their names (the long ones in the lists, the
-- short ones on a closed dropdown in Options' rows).
S.PLACE_NAMES = {
  quickFind = L["In Quick Find"], menuUp = L["Map menu: in the menu, up"], menuRight = L["Map menu: in the menu, right"],
  barUp = L["Map menu: always shown, up"], barRight = L["Map menu: always shown, right"],
}
S.PLACE_SHORT = {
  quickFind = L["Quick Find"], menuUp = L["Menu, up"], menuRight = L["Menu, right"],
  barUp = L["Always shown, up"], barRight = L["Always shown, right"],
}
-- The dropdowns' list (Options' O.PadDropdown: { value, text, short }).
function S.PlaceOptions()
  local out = {}
  for _, p in ipairs(S.PLACES) do out[#out + 1] = { value = p, text = S.PLACE_NAMES[p], short = S.PLACE_SHORT[p] } end
  return out
end

-- An icon's name as shown: the file's name ("INV_Misc_Bag_08"), "File id 136243", an atlas's name.
function S.IconLabel(icon)
  if type(icon) == "number" then return Format(L["File id %d"], icon) end
  icon = tostring(icon or "")
  return icon:match("^atlas:(.+)$") or icon:match("([^\\/]+)$") or icon
end

-- The icons to pick from (asked 2026-11-16: "make the icon selection another popup like how custom pin works, allow
-- the icon search field in that pop up"): the custom pin dialog's (Pins.Icons: the game's macro icons, file ids on
-- this client), after the ones the addon names itself (Quick Find's, the search's pins', Pins' own few), so a name
-- typed finds those. Worked out once.
function S.PickerIcons()
  if S.pickerIcons then return S.pickerIcons end
  local out, seen = {}, {}
  local function add(v)
    if v == nil then return end
    if type(v) == "string" and not v:find("[\\/]") and not v:find("^atlas:") then v = "Interface\\Icons\\" .. v end
    local key = type(v) == "string" and v:lower() or v
    if seen[key] then return end
    seen[key] = true
    out[#out + 1] = v
  end
  local G, P = ns.GPS, ns.Pins
  for _, e in ipairs(G and G.QUICK_FIND or {}) do
    local icon = G.QuickFindIcon and G.QuickFindIcon(e)
    if type(icon) == "string" and not icon:find("^atlas:") then add(icon) end
  end
  if P then
    local names = {}
    for _, v in pairs(P.NPC_ICONS or {}) do names[#names + 1] = v end
    table.sort(names)
    for _, v in ipairs(names) do add(v) end
    for _, v in ipairs(P.FALLBACK_ICONS or {}) do add(v) end
    for _, v in ipairs(P.Icons and P.Icons() or {}) do add(v) end
  end
  S.pickerIcons = out
  return out
end

-- The icons matching `text` (every word in an icon's file name; digits also in a file id), and the icon typed itself
-- first (a name or a file id: Searches.IconFrom) when it isn't among them and the game has that file.
function S.FilterIcons(text, probe)
  local all = S.PickerIcons()
  local raw = Trim(text)
  text = raw:lower()
  if text == "" then return all end
  local words = {}
  for w in text:gmatch("%S+") do words[#words + 1] = w end
  local digits = text:match("^%d+$")
  local out = {}
  local typed = S.IconFrom(raw)
  local typedKey = type(typed) == "string" and typed:lower() or typed
  local hasTyped = false
  for _, v in ipairs(all) do
    local ok
    if type(v) == "number" then
      ok = digits and tostring(v):find(digits, 1, true) ~= nil
    else
      local name = S.IconLabel(v):lower()
      ok = true
      for _, w in ipairs(words) do
        if not name:find(w, 1, true) then ok = false break end
      end
    end
    if ok then
      out[#out + 1] = v
      if (type(v) == "string" and v:lower() or v) == typedKey then hasTyped = true end
    end
  end
  if typed and not hasTyped then
    local real = true
    if probe then -- (a file the game hasn't: no file id once set)
      probe:SetTexture(typed)
      if probe.GetTextureFileID then
        local okId, id = pcall(probe.GetTextureFileID, probe)
        real = okId and id ~= nil
      end
    end
    if real then table.insert(out, 1, typed) end
  end
  return out
end

-- The icon picker: a popup of its own (the custom pin dialog's grid: Pins.COLS x Pins.ROWS, scrolled with the mouse
-- wheel or the bar beside it) with a search box over it that filters the icons as they're typed. An icon clicked is
-- the editor's and the picker closes.
function S.Picker()
  local f = S.picker
  if f then return f end
  local P = ns.Pins
  local COLS, ROWS, CELL = P.COLS, P.ROWS, P.CELL
  f = ns.Window("AzerothGPSIconPicker", COLS * CELL + 64, ROWS * CELL + 150, L["Choose Icon"])
  S.picker = f
  f.top0 = 0
  local top = f.top
  local label = f:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
  label:SetPoint("TOPLEFT", 20, top - 10)
  label:SetWidth(COLS * CELL + 20)
  label:SetJustifyH("LEFT")
  label:SetWordWrap(false)
  label:SetText(L["Search icons: part of a name, or a file id"])
  f.label = label
  local box = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
  box:SetSize(COLS * CELL + 14, 20)
  box:SetPoint("TOPLEFT", 26, top - 26)
  box:SetAutoFocus(false)
  box:SetMaxLetters(80)
  box:SetScript("OnTextChanged", function() S.FilterPicker() end)
  box:SetScript("OnEnterPressed", function()
    local first = f.list and f.list[1]
    if first ~= nil then S.PickIcon(first) end
  end)
  box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  f.search = box
  f.probe = f:CreateTexture(nil, "BACKGROUND")
  f.probe:SetSize(1, 1)
  f.probe:SetPoint("TOPLEFT")
  f.probe:SetAlpha(0)
  local grid = CreateFrame("Frame", nil, f)
  grid:SetSize(COLS * CELL, ROWS * CELL)
  grid:SetPoint("TOPLEFT", 20, top - 54)
  grid:EnableMouseWheel(true)
  grid:SetScript("OnMouseWheel", function(_, delta) S.ScrollPicker(delta > 0 and -1 or 1) end)
  local sel = grid:CreateTexture(nil, "BACKGROUND")
  sel:SetSize(CELL, CELL)
  sel:SetColorTexture(1, 0.82, 0, 0.75)
  f.sel = sel
  f.cells = {}
  for r = 1, ROWS do
    for c = 1, COLS do
      local b = CreateFrame("Button", nil, grid)
      b:SetSize(CELL - 4, CELL - 4)
      b:SetPoint("TOPLEFT", (c - 1) * CELL + 2, -((r - 1) * CELL + 2))
      b.icon = b:CreateTexture(nil, "ARTWORK")
      b.icon:SetAllPoints()
      local hl = b:CreateTexture(nil, "HIGHLIGHT")
      hl:SetAllPoints()
      hl:SetColorTexture(1, 1, 1, 0.25)
      b:SetScript("OnClick", function(self)
        if self.value ~= nil then S.PickIcon(self.value) end
      end)
      b:SetScript("OnEnter", function(self)
        if self.value == nil then return end
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(S.IconLabel(self.value), 1, 1, 1)
        GameTooltip:Show()
      end)
      b:SetScript("OnLeave", GameTooltip_Hide)
      f.cells[#f.cells + 1] = b
    end
  end
  local bar = CreateFrame("Slider", nil, f)
  bar:SetOrientation("VERTICAL")
  bar:SetSize(14, ROWS * CELL)
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
    if f.syncing then return end
    f.top0 = math.floor(v + 0.5)
    S.RefreshPicker()
  end)
  f.bar = bar
  f.count = f:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  f.count:SetPoint("TOPLEFT", grid, "BOTTOMLEFT", 0, -4)
  f.count:SetWidth(COLS * CELL)
  f.count:SetJustifyH("LEFT")
  local cancel = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  cancel:SetSize(90, 22)
  cancel:SetPoint("BOTTOMRIGHT", -20, 14)
  cancel:SetText(L["Cancel"])
  cancel:SetScript("OnClick", function() f:Hide() end)
  f.cancel = cancel
  return f
end

function S.ScrollPicker(rows)
  local f = S.picker
  if not f then return end
  f.top0 = (f.top0 or 0) + rows
  S.RefreshPicker()
end

-- The search box's text: the icons matching it, from the top.
function S.FilterPicker()
  local f = S.picker
  if not f then return end
  f.list = S.FilterIcons(f.search:GetText(), f.probe)
  f.top0 = 0
  S.RefreshPicker()
end

function S.RefreshPicker()
  local f = S.picker
  if not f then return end
  local P = ns.Pins
  local list = f.list or S.PickerIcons()
  local rows = math.ceil(#list / P.COLS)
  local maxTop = math.max(0, rows - P.ROWS)
  f.top0 = math.max(0, math.min(f.top0 or 0, maxTop))
  local cur = f.current
  local curKey = type(cur) == "string" and cur:lower() or cur
  f.sel:Hide()
  for i, b in ipairs(f.cells) do
    local v = list[f.top0 * P.COLS + i]
    b.value = v
    if v ~= nil then
      ns.SetIcon(b.icon, v, S.DEFAULT_ICON)
      b:Show()
      if curKey ~= nil and (type(v) == "string" and v:lower() or v) == curKey then
        f.sel:ClearAllPoints()
        f.sel:SetPoint("CENTER", b, "CENTER")
        f.sel:Show()
      end
    else
      b:Hide()
    end
  end
  if #list == 0 then
    f.count:SetText(L["No icons match."])
  else
    local first = f.top0 * P.COLS + 1
    f.count:SetText(Format(L["Icons %d-%d of %d (mouse wheel scrolls)"], first,
      math.min(first + P.COLS * P.ROWS - 1, #list), #list))
  end
  f.syncing = true
  f.bar:SetMinMaxValues(0, maxTop)
  f.bar:SetValue(f.top0)
  f.syncing = false
end

-- Open the picker beside the editor, the editor's icon marked (and in view).
function S.OpenPicker()
  local f = S.Picker()
  local ed = S.editor
  f.current = ed and (ed.iconValue or ed.iconShown) or nil
  f.search:SetText("")
  f.list = S.PickerIcons()
  f.top0 = 0
  if f.current ~= nil then
    local key = type(f.current) == "string" and f.current:lower() or f.current
    for i, v in ipairs(f.list) do
      if (type(v) == "string" and v:lower() or v) == key then
        f.top0 = math.floor((i - 1) / ns.Pins.COLS)
        break
      end
    end
  end
  if ed then
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", ed, "TOPRIGHT", 8, 0)
  end
  S.RefreshPicker()
  f:Show()
  f.search:SetFocus()
  return f
end

-- An icon picked: the editor's, and the picker closed.
function S.PickIcon(v)
  local ed = S.editor
  if ed then
    ed.iconValue = v
    ed.ShowIcon()
  end
  if S.picker then S.picker:Hide() end
end

-- Add (no `id`) or change one: a popup with its name, the words searched, its description (each box under its label,
-- holding no more letters than the limits; Save checks and cuts them again: Searches.Clean), its icon (a button
-- showing it: clicked, the icon picker) and where it goes (a dropdown).
S.EDIT_W = 380
function S.Edit(id)
  local r = id and S.Get(id) or nil
  local f = S.editor
  local W = S.EDIT_W
  if not f then
    f = ns.Window("AzerothGPSSearchEdit", W, 0, L["Search Button"])
    S.editor = f
    f.labels = {}
    local y = f.top - 8
    local function Label(text)
      local fs = f:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
      fs:SetPoint("TOPLEFT", 20, y)
      fs:SetWidth(W - 40)
      fs:SetJustifyH("LEFT")
      fs:SetWordWrap(false)
      fs:SetText(text)
      fs.room = W - 40
      f.labels[#f.labels + 1] = fs
      y = y - 16
      return fs
    end
    local function Box(max)
      local box = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
      box:SetSize(W - 48, 20)
      box:SetPoint("TOPLEFT", 26, y)
      box:SetAutoFocus(false)
      box:SetMaxLetters(max)
      box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
      y = y - 30
      return box
    end
    Label(Format(L["Name (up to %d letters)"], S.NAME_MAX))
    f.name = Box(S.NAME_MAX)
    Label(Format(L["Search for (up to %d)"], S.TEXT_MAX))
    f.text = Box(S.TEXT_MAX)
    Label(Format(L["Description (up to %d)"], S.DESC_MAX))
    f.desc = Box(S.DESC_MAX)
    -- (the icon: a button showing it, its name beside it, Choose Icon at the right; either opens the picker)
    Label(L["Icon"])
    f.iconBtn = CreateFrame("Button", nil, f)
    f.iconBtn:SetSize(36, 36)
    f.iconBtn:SetPoint("TOPLEFT", 20, y - 2)
    f.preview = f.iconBtn:CreateTexture(nil, "ARTWORK")
    f.preview:SetAllPoints()
    local hl = f.iconBtn:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetColorTexture(1, 1, 1, 0.25)
    f.iconBtn:SetScript("OnClick", function() S.OpenPicker() end)
    f.iconBtn:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(L["Choose Icon"], 1, 1, 1)
      GameTooltip:AddLine(L["Click to choose another icon."], nil, nil, nil, true)
      GameTooltip:Show()
    end)
    f.iconBtn:SetScript("OnLeave", GameTooltip_Hide)
    f.choose = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    f.choose:SetText(L["Choose Icon"])
    local cw = math.max(110, (f.choose.GetTextWidth and f.choose:GetTextWidth() or 0) + 24)
    f.choose:SetSize(cw, 22)
    f.choose:SetPoint("TOPRIGHT", f, "TOPRIGHT", -20, y - 9)
    f.choose:SetScript("OnClick", function() S.OpenPicker() end)
    f.iconName = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    f.iconName:SetPoint("LEFT", f.iconBtn, "RIGHT", 10, 0)
    f.iconName:SetWidth(W - 20 - 36 - 10 - 8 - cw - 20)
    f.iconName:SetJustifyH("LEFT")
    f.iconName:SetWordWrap(false)
    y = y - 46
    -- (the icon shown: the one picked, else the row's own (a built-in's Quick Find icon), else the question mark)
    function f.ShowIcon()
      local v = f.iconValue
      if v == nil then v = f.defaultIcon or S.DEFAULT_ICON end
      f.iconShown = v
      ns.SetIcon(f.preview, v, S.DEFAULT_ICON)
      f.iconName:SetText(S.IconLabel(v))
    end
    Label(L["Where"])
    local DD = ns.Options and ns.Options.PadDropdown
    if DD then
      f.placeDD = DD(f, W - 40, S.PlaceOptions, function() return f.place end, function(v)
        f.place = v
        f.placeDD:Update(true)
      end)
      f.placeDD:SetPoint("TOPLEFT", 20, y)
    end
    y = y - 34
    f.err = f:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
    f.err:SetPoint("TOPLEFT", 20, y)
    f.err:SetWidth(W - 40)
    f.err:SetJustifyH("LEFT")
    f.err:SetTextColor(1, 0.25, 0.25)
    y = y - 18
    f.save = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    f.save:SetSize(100, 22)
    f.save:SetPoint("TOPRIGHT", f, "TOPRIGHT", -126, y)
    f.save:SetText(L["Save"])
    f.save:SetScript("OnClick", function()
      local fields = { name = f.name:GetText(), text = f.text:GetText(), desc = f.desc:GetText(),
        icon = f.iconValue, place = f.place }
      local ok, why
      if f.editing then ok, why = S.Update(f.editing, fields) else ok, why = S.Add(fields) end
      if ok then f:Hide() else f.err:SetText(why or "") end
    end)
    local cancel = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    cancel:SetSize(100, 22)
    cancel:SetPoint("LEFT", f.save, "RIGHT", 6, 0)
    cancel:SetText(L["Cancel"])
    cancel:SetScript("OnClick", function() f:Hide() end)
    y = y - 34
    f:SetHeight(-y + 4)
    f:HookScript("OnHide", function() if S.picker then S.picker:Hide() end end)
  end
  f.editing = r and r.id or nil
  f.name:SetText(r and S.Name(r) or "")
  f.text:SetText(r and S.Text(r) or "")
  f.desc:SetText(r and r.desc or "")
  f.iconValue = r and r.icon or nil
  f.defaultIcon = r and not r.icon and S.Icon(r) or nil
  f.ShowIcon()
  f.place = r and S.Place(r) or "quickFind"
  if f.placeDD then f.placeDD:Update(true) end
  f.err:SetText("")
  if S.picker then S.picker:Hide() end
  f:Show()
  return f
end
