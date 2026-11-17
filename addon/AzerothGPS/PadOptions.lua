-- A controller in the Options window (asked 2026-11-16, Blizzard's settings with Gamepad UI on shown: "can we do this in
-- our options?"). Nothing of Blizzard's gamepad focus (protected; touching its panels taints): override bindings of our
-- own owner frame, set while Options is open with a controller active and out of combat (cleared as a fight begins),
-- a highlight bar and a gold arrow of our own textures, and each control pressed through its own scripts.
--
-- The buttons are fixed (not Options > Controller's map controls): the D-pad moves (up and down through the page list
-- or the page's rows, left and right along a row; on a slider a step, on a dropdown the choice before or after), A
-- presses (a checkbox ticked, a button clicked, a dropdown's list opened: the D-pad through it, A picks, B closes it;
-- an edit box takes the keyboard), LB and RB the page before and after, B backs out (a list, a question, a popup) and
-- then closes Options. A question up (ns.Ask): A is Yes, B No, as on the map. A popup over Options (ns.Window: a
-- search button's editor): the D-pad goes through its controls.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })
local Pad = ns.Pad
local PO = {}
local Owner -- (the bindings' owner frame: made below)
Pad.Opt = PO

PO.OWNER = "AzerothGPSPadOptOwner"
PO.KEYS = { PADDUP = "up", PADDDOWN = "down", PADDLEFT = "left", PADDRIGHT = "right", PAD1 = "a", PAD2 = "b",
  PADLSHOULDER = "lb", PADRSHOULDER = "rb" }
PO.REPEAT_WAIT, PO.REPEAT_EVERY = 0.4, 0.12 -- a D-pad held: again after this, then this often
PO.LIST_ROWS, PO.LIST_ROW = 12, 18 -- a dropdown's list: rows shown, their height
-- the frames a pad can act on, by their kind
PO.KINDS = { Button = true, CheckButton = true, Slider = true, EditBox = true, DropdownButton = true }

local function Window() return rawget(_G, "AzerothGPSOptions") end
local function Locked() return InCombatLockdown and InCombatLockdown() and true or false end
local function InCombat() return (ns.inCombat or Locked()) and true or false end
local function Call(f, script, ...)
  local fn = f and f.GetScript and f:GetScript(script)
  if fn then return pcall(fn, f, ...) end
  return false
end

-- Wanted: a controller active (Options > Controller's support on), Options open, out of combat.
function PO.Wanted()
  local w = Window()
  return (Pad.Active() and w and w:IsShown() and not InCombat()) and true or false
end
function PO.Open() local w = Window() return (w and w:IsShown()) and true or false end

---------------------------------------------------------------------------
-- What there is to move through
---------------------------------------------------------------------------

local function Enabled(f)
  if f.agpsOn == false then return false end
  if f.IsEnabled then
    local ok, on = pcall(f.IsEnabled, f)
    if ok and not on then return false end
  end
  return true
end
local function IsScrollBar(f)
  local p = f:GetParent()
  return p and (p.ScrollBar == f or p.scrollBar == f) or false
end
-- the frames under `root` a pad can act on, shown and enabled, in the order they were made (top to bottom as laid out)
function PO.Collect(root, out)
  out = out or {}
  local kids = { root:GetChildren() }
  for _, c in ipairs(kids) do
    if c:IsShown() and not c.agpsNoPad and not IsScrollBar(c) then
      local kind = c.GetObjectType and c:GetObjectType()
      if PO.KINDS[kind] then
        if Enabled(c) then out[#out + 1] = c end
      else
        PO.Collect(c, out)
      end
    end
  end
  return out
end
-- A frame's row on its page: the nearest frame laid out with a place of its own (Options' `place`: padY), or what it
-- hangs on (`also`: padRow); and its height from the page's top, summed up the frames it's laid out in.
-- Where the rows are now: the search's results while they show (asked 2026-11-16, "when using the search bar in
-- Options and results popup I can't move to them with the controller"), else the page showing. Its frame of rows,
-- its scroll and the field each row's place is in (padResY: the results' places, Options' O.Search).
function PO.Area()
  local O = ns.Options
  local s = O.search
  if s and s.results and s.results:IsShown() then return s.resultsChild, s.results, "padResY" end
  local info = s and s.pages and s.pages[O.CurrentPage()]
  if not info or not (info.scroll and info.scroll:IsShown()) then return nil end
  return info.child, info.scroll, "padY"
end
local function RowOf(f, top, key)
  key = key or "padY"
  local a = f
  while a and a ~= top do
    if a[key] then return a.padRow or a end
    a = a:GetParent()
  end
  return nil
end
local function YOf(f, top, key)
  key = key or "padY"
  local y, a = 0, f
  if f.padRow then a = f.padRow end
  local any = false
  while a and a ~= top do
    if a[key] then y, any = y + a[key], true end
    a = a:GetParent()
  end
  return any and y or nil
end
-- The current page's rows: { { items..., y = , h = , key = }, ... } top to bottom.
function PO.Rows()
  local O = ns.Options
  local top, _, field = PO.Area()
  if not top then return {} end
  local rows, byKey, lastY = {}, {}, 0
  for seq, f in ipairs(PO.Collect(top)) do
    local key = RowOf(f, top, field)
    local r = key and byKey[key]
    if not r then
      local y = key and YOf(key, top, field) or lastY
      r = { key = key or f, y = y, h = key and key.padH or 26, seq = seq }
      rows[#rows + 1] = r
      if key then byKey[key] = r end
    end
    lastY = r.y
    r[#r + 1] = f
  end
  table.sort(rows, function(a, b)
    if a.y ~= b.y then return a.y > b.y end
    return a.seq < b.seq
  end)
  return rows
end
-- the page list: its entries (the pages' names) and then Options' own footer button
function PO.ListItems()
  local O = ns.Options
  local out = {}
  for _, t in ipairs(O.tabs or {}) do
    if t:IsShown() then out[#out + 1] = t end
  end
  if O.footerReset and O.footerReset:IsShown() then out[#out + 1] = O.footerReset end
  return out
end
-- a popup over Options (ns.Window: ns.RegisterPopup's), the one shown last
function PO.Popup()
  local best, at
  for f in pairs(ns.popups or {}) do
    if f ~= Window() and f:IsShown() and f ~= ns.lastAsk and not f.agpsNoPad then
      local t = f.agpsShownAt or 0
      if not best or t > at then best, at = f, t end
    end
  end
  return best
end

---------------------------------------------------------------------------
-- The look: a bright bar along the focused row, an outline on the control, a gold arrow on the page showing
---------------------------------------------------------------------------

local bar, outline, arrow, hint, list
local function Gold(t, a) t:SetColorTexture(1, 0.82, 0, a) end
local function Bar()
  local w = Window()
  if bar or not w then return bar end
  bar = CreateFrame("Frame", nil, w)
  bar:SetFrameStrata("FULLSCREEN_DIALOG")
  bar.fill = bar:CreateTexture(nil, "BACKGROUND")
  bar.fill:SetAllPoints()
  Gold(bar.fill, 0.16)
  bar.edge = bar:CreateTexture(nil, "ARTWORK")
  bar.edge:SetPoint("TOPLEFT")
  bar.edge:SetPoint("BOTTOMLEFT")
  bar.edge:SetWidth(3)
  Gold(bar.edge, 0.95)
  bar:Hide()
  outline = CreateFrame("Frame", nil, w)
  outline:SetFrameStrata("FULLSCREEN_DIALOG")
  outline.lines = {}
  for i, p in ipairs({ { "TOPLEFT", "TOPRIGHT" }, { "BOTTOMLEFT", "BOTTOMRIGHT" }, { "TOPLEFT", "BOTTOMLEFT" },
    { "TOPRIGHT", "BOTTOMRIGHT" } }) do
    local t = outline:CreateTexture(nil, "OVERLAY")
    t:SetPoint(p[1])
    t:SetPoint(p[2])
    if i <= 2 then t:SetHeight(1) else t:SetWidth(1) end
    Gold(t, 1)
    outline.lines[i] = t
  end
  outline:Hide()
  PO.bar, PO.outline = bar, outline
  return bar
end
-- the gold arrow on the page showing (">", two bars of our own)
local function Arrow(tab)
  if not arrow then
    arrow = CreateFrame("Frame", nil, tab)
    arrow:SetSize(10, 12)
    for i, a in ipairs({ -math.pi / 4, math.pi / 4 }) do
      local t = arrow:CreateTexture(nil, "OVERLAY")
      t:SetSize(8, 2)
      Gold(t, 1)
      t:SetPoint("CENTER", arrow, "CENTER", 0, i == 1 and 2.5 or -2.5)
      pcall(t.SetRotation, t, a)
    end
    PO.arrow = arrow
  end
  if not tab then arrow:Hide() return end
  arrow:SetParent(tab)
  arrow:ClearAllPoints()
  arrow:SetPoint("LEFT", tab, "LEFT", -1, 0)
  arrow:SetFrameLevel((tab:GetFrameLevel() or 1) + 3)
  arrow.agpsOn = true
  arrow:SetShown(PO.LookOn())
end
-- The focus on `f` (nil: none): the bar along its row (`row`: the frame the row is; else `f`), the outline on it, its
-- tooltip as on hover.
function PO.SetFocus(f, row)
  local old = PO.focus
  if old and old ~= f then Call(old, "OnLeave") if PO.tipOwner and PO.tipOwner ~= old then Call(PO.tipOwner, "OnLeave") end end
  PO.focus, PO.tipOwner = f, nil
  Bar()
  if not f then
    if bar then bar:Hide() outline:Hide() end
    return
  end
  local r = (row and row.GetObjectType and row ~= f) and row or f
  -- (on the window the focus is in, at its strata over its own frames: a button's window open, the bar and outline
  -- left on Options' showed through it; asked 2026-11-16, "the highlight from the window behind it is on top")
  local top = f
  while top.GetParent and top:GetParent() and top:GetParent() ~= UIParent do top = top:GetParent() end
  for _, x in ipairs({ bar, outline }) do
    if x:GetParent() ~= top then x:SetParent(top) end
    x:SetFrameStrata(top.GetFrameStrata and top:GetFrameStrata() or "DIALOG")
    x:SetFrameLevel(math.min((top.GetFrameLevel and top:GetFrameLevel() or 0) + 150, 9000))
  end
  bar:ClearAllPoints()
  bar:SetPoint("TOPLEFT", r, "TOPLEFT", -6, 3)
  bar:SetPoint("BOTTOMLEFT", r, "BOTTOMLEFT", -6, -3)
  local _, scroll = PO.Area()
  local edge = (PO.side == "page" and scroll) or r
  bar:SetPoint("RIGHT", edge, "RIGHT", -2, 0)
  bar:SetShown(PO.LookOn())
  outline:ClearAllPoints()
  outline:SetPoint("TOPLEFT", f, "TOPLEFT", -2, 2)
  outline:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", 2, -2)
  outline:SetShown(PO.LookOn())
  -- (its tooltip: its own, else its row's: a search button's, a group's in the quick buttons' order)
  if old ~= f and PO.LookOn() then -- (its tooltip: the controller in use only)
    if f:GetScript("OnEnter") then
      Call(f, "OnEnter")
      PO.tipOwner = f
    elseif r ~= f and r.GetScript and r:GetScript("OnEnter") then
      Call(r, "OnEnter")
      PO.tipOwner = r
    end
    local kind = f:GetObjectType()
    if kind == "EditBox" and GameTooltip then -- (typed in: a keyboard's)
      if not PO.tipOwner then
        GameTooltip:SetOwner(f, "ANCHOR_RIGHT")
        GameTooltip:SetText(L["Text box"], 1, 1, 1)
      end
      GameTooltip:AddLine(L["Needs a keyboard: A puts the cursor in it, B takes it out."], 1, 0.82, 0, true)
      GameTooltip:Show()
      PO.tipOwner = PO.tipOwner or f
    end
  end
end

-- The hint at Options' bottom: the buttons it takes.
function PO.HintText()
  local K = Pad.KeyLabel
  if PO.listOpen then
    return string.format(L["%s: Move   %s: Pick   %s: Close"], L["D-pad"], K("PAD1"), K("PAD2"))
  end
  return string.format(L["%s: Move   %s: Select   %s: Back   %s/%s: Page"], L["D-pad"], K("PAD1"), K("PAD2"),
    K("PADLSHOULDER"), K("PADRSHOULDER"))
end
-- The look (the bar, the outline, the page's arrow, the hint at the bottom): only while a controller is in use, as
-- the map's marks (Pad.used: its input seen, the mouse not used since; none connected, none). Asked 2026-11-16: "If
-- controller support is on but one isn't connected we shouldn't still show controller highlights on options page or
-- the controls at the bottom".
function PO.LookOn()
  return PO.bound and Pad.used and true or false
end
local ShowHint
function PO.UpdateLook()
  local on = PO.LookOn()
  if bar then bar:SetShown(on and PO.focus ~= nil) end
  if outline then outline:SetShown(on and PO.focus ~= nil) end
  if arrow then arrow:SetShown(on and arrow.agpsOn or false) end
  if not on and PO.tipOwner then Call(PO.tipOwner, "OnLeave") PO.tipOwner = nil end
  ShowHint(on)
end
function ShowHint(on)
  local w = Window()
  if on and w and not hint then
    -- (where the version is: that hidden while it shows, clear of Reset to defaults on the right)
    hint = w:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    hint:SetPoint("BOTTOMLEFT", w, "BOTTOMLEFT", 14, 18)
    hint:SetPoint("RIGHT", w, "RIGHT", -184, 0)
    hint:SetJustifyH("LEFT")
    PO.hint = hint
  end
  if hint then
    if on then hint:SetText(PO.HintText()) end
    hint:SetShown(on and true or false)
    local v = ns.Options.versionText
    if v then v:SetShown(not on) end
  end
end

---------------------------------------------------------------------------
-- Moving
---------------------------------------------------------------------------

PO.side = "list"
local function Tabs() return ns.Options.tabs or {} end
-- the list's focus on entry `i` (clamped)
local function ListFocus(i)
  local items = PO.ListItems()
  if #items == 0 then return PO.SetFocus(nil) end
  i = math.max(1, math.min(#items, i or 1))
  PO.side, PO.listAt = "list", i
  PO.SetFocus(items[i])
  -- (scrolled into view: the list as the page's own scroll does it)
  local t = items[i]
  local ls = ns.Options.listScroll
  if t.listY and ls and ls.ScrollBar and ls.ScrollBar:IsShown() then
    local topY, h = -t.listY, ls:GetHeight() or 0
    local cur = ls:GetVerticalScroll() or 0
    if topY < cur then ls:SetVerticalScroll(math.max(0, topY - 6))
    elseif topY + 24 > cur + h then ls:SetVerticalScroll(math.max(0, topY + 30 - h)) end
  end
end
-- the page scrolled so row `r` shows (its top and bottom in the window)
function PO.ScrollTo(r)
  local _, sf = PO.Area()
  if not (sf and r and r.y) then return end
  local h = sf:GetHeight() or 0
  local topY, bottom = -r.y - 4, -r.y + (r.h or 26) + 4
  local cur = sf:GetVerticalScroll() or 0
  local rows = PO.Rows()
  local last = rows[#rows]
  local full = last and (-last.y + (last.h or 26) + 16) or 0
  local range = math.max(0, full - h)
  if topY < cur then
    sf:SetVerticalScroll(math.max(0, topY))
  elseif bottom > cur + h then
    sf:SetVerticalScroll(math.min(range, bottom - h))
  end
end
-- the page's focus on row `ri`, its item `ci` (clamped)
local function PageFocus(ri, ci)
  local rows = PO.Rows()
  if #rows == 0 then return false end
  ri = math.max(1, math.min(#rows, ri or 1))
  local r = rows[ri]
  ci = math.max(1, math.min(#r, ci or 1))
  PO.side, PO.row, PO.col = "page", ri, ci
  PO.ScrollTo(r)
  PO.SetFocus(r[ci], r.key)
  return true
end
-- the focus on control `f` of the page showing (false: not there)
function PO.FocusOn(f)
  for ri, r in ipairs(PO.Rows()) do
    for ci, x in ipairs(r) do
      if x == f then return PageFocus(ri, ci) end
    end
  end
  return false
end
-- where the focus is on the page now (it may have moved: rows shown or hidden since)
local function Where()
  local rows = PO.Rows()
  for ri, r in ipairs(rows) do
    for ci, f in ipairs(r) do
      if f == PO.focus then return ri, ci, rows end
    end
  end
  return nil, nil, rows
end
-- the page showing: page `n` (by the list's order), the list's entry with it
function PO.ShowPage(n)
  local tabs = Tabs()
  if #tabs == 0 then return false end
  n = ((n - 1) % #tabs) + 1
  local t = tabs[n]
  Call(t, "OnClick", "LeftButton")
  Arrow(t)
  return true
end

-- A dropdown (Options' own or the game's): its choices, the one picked, picking one
local function DropOf(f)
  if f and f.options and f.padSet and f.padGet then return f end
  return nil
end
local function DropIndex(d)
  local v = d.padGet()
  for i, o in ipairs(d.options) do
    if o.value == v then return i end
  end
  return 1
end
local function DropPick(d, i)
  local o = d.options[i]
  if o and not o.off then d.padSet(o.value) end
end
-- the list of a dropdown's choices, ours (never the game's menu): opened on the one picked
local function FillList()
  local d = list.drop
  local n = #d.options
  list.top = math.max(0, math.min(n - #list.rows, list.top))
  if list.at <= list.top then list.top = list.at - 1 end
  if list.at > list.top + #list.rows then list.top = list.at - #list.rows end
  local v = d.padGet()
  for r, row in ipairs(list.rows) do
    local o = d.options[list.top + r]
    row:SetShown(o ~= nil)
    if o then
      row.text:SetText(o.text or tostring(o.value))
      row.text:SetFontObject(o.off and "GameFontDisableSmall" or "GameFontHighlightSmall")
      row.mark:SetShown(o.value == v)
      row.hl:SetShown(list.top + r == list.at)
    end
  end
end
function PO.OpenList(d)
  local w = Window()
  if not w then return false end
  if not list then
    -- (on the screen, not Options: Options lifted over the opened-out map, ns.LiftPopup, takes its children's strata
    -- with it, and the list went under a button's window again; asked 2026-11-16, "menu behind")
    list = CreateFrame("Frame", nil, UIParent)
    list:SetFrameStrata("FULLSCREEN_DIALOG")
    list:SetFrameLevel(40)
    list:SetWidth(220)
    local edge = list:CreateTexture(nil, "BACKGROUND", nil, -1)
    edge:SetPoint("TOPLEFT", -1, 1)
    edge:SetPoint("BOTTOMRIGHT", 1, -1)
    Gold(edge, 0.8)
    local bg = list:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetColorTexture(0.04, 0.04, 0.04, 0.97)
    list.rows = {}
    -- (the mouse's too: with the game's controller UI on, the button window's dropdowns are this list, never the
    -- game's menu, whose controller code is blocked as it shows and hides: AzerothGPS's own forbiddenLog, 2026-11-16,
    -- SetPreferredGamepadInteractTarget from Blizzard_GamepadSmartNavigation's FrameShown / FrameHidden)
    list:EnableMouseWheel(true)
    list:SetScript("OnMouseWheel", function(_, delta)
      list.top = math.max(0, (list.top or 0) - delta)
      list.at = math.max(list.top + 1, math.min(list.at, list.top + #list.rows))
      FillList()
    end)
    for r = 1, PO.LIST_ROWS do
      local row = CreateFrame("Button", nil, list)
      row:SetSize(218, PO.LIST_ROW)
      row.r = r
      row:SetScript("OnEnter", function(self)
        local d = list.drop
        local o = d and d.options[list.top + self.r]
        if not o then return end
        list.at = list.top + self.r
        FillList()
        if o.tip and GameTooltip then
          GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
          GameTooltip:SetText(o.text or tostring(o.value), 1, 0.82, 0)
          for _, line in ipairs(type(o.tip) == "table" and o.tip or { o.tip }) do GameTooltip:AddLine(line, 1, 1, 1, true) end
          GameTooltip:Show()
        end
      end)
      row:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
      row:SetScript("OnClick", function(self)
        local d = list.drop
        local o = d and d.options[list.top + self.r]
        if not o or o.off then return end
        DropPick(d, list.top + self.r)
        PO.CloseList()
      end)
      row:SetPoint("TOPLEFT", 1, -1 - (r - 1) * PO.LIST_ROW)
      row.hl = row:CreateTexture(nil, "BACKGROUND")
      row.hl:SetAllPoints()
      Gold(row.hl, 0.3)
      row.mark = row:CreateTexture(nil, "ARTWORK")
      row.mark:SetSize(6, 6)
      row.mark:SetPoint("LEFT", 7, 0)
      Gold(row.mark, 1)
      row.text = row:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
      row.text:SetPoint("LEFT", 19, 0)
      row.text:SetPoint("RIGHT", -4, 0)
      row.text:SetJustifyH("LEFT")
      list.rows[r] = row
    end
    PO.list = list
  end
  list.drop, list.at, list.top = d, DropIndex(d), 0
  local n = math.min(#d.options, PO.LIST_ROWS)
  local w = math.max(120, d.GetWidth and d:GetWidth() or 220)
  list:SetWidth(w)
  for r, row in ipairs(list.rows) do
    row:SetShown(r <= n)
    row:SetWidth(w - 2)
  end
  list:SetHeight(n * PO.LIST_ROW + 2)
  list:ClearAllPoints()
  list:SetPoint("TOPLEFT", d, "BOTTOMLEFT", 0, -2)
  -- (over whatever window the dropdown is on: a button's window over Options went over it, asked 2026-11-16
  -- "dropdown goes behind window")
  -- (a child of the window its dropdown is on, over that window's own: raised with it when it's clicked, asked
  -- 2026-11-16 "menu is behind the popup"; its strata, not TOOLTIP, so the game's tooltip for an entry shows over it)
  local top = d
  while top.GetParent and top:GetParent() and top:GetParent() ~= UIParent do top = top:GetParent() end
  if list:GetParent() ~= top then list:SetParent(top) end
  -- (and a strata above it: at the window's own its border and buttons drew over the list, asked 2026-11-16 "with
  -- controller, cuts through frame")
  local order = { "BACKGROUND", "LOW", "MEDIUM", "HIGH", "DIALOG", "FULLSCREEN", "FULLSCREEN_DIALOG", "TOOLTIP" }
  local own = top.GetFrameStrata and top:GetFrameStrata() or "DIALOG"
  local above = "TOOLTIP"
  for i, n in ipairs(order) do if n == own and order[i + 1] then above = order[i + 1] end end
  list:SetFrameStrata(above)
  list:SetFrameLevel(math.min((top.GetFrameLevel and top:GetFrameLevel() or 0) + 200, 9000))
  if list.Raise then list:Raise() end
  FillList()
  list:Show()
  PO.listOpen = true
  ShowHint(PO.LookOn())
  return true
end
function PO.CloseList()
  if list then list:Hide() end
  PO.listOpen = nil
  ShowHint(PO.bound)
  return true
end

-- A control pressed (A): as a click on it.
function PO.Press(f)
  if not f then return false end
  local kind = f:GetObjectType()
  local d = DropOf(f)
  if d then return PO.OpenList(d) end
  if kind == "EditBox" then
    if f.SetFocus then f:SetFocus() end
    PO.typing = f
    return true
  end
  if kind == "Slider" then return false end
  if kind == "CheckButton" then
    if f.SetChecked then f:SetChecked(not f:GetChecked()) end
  end
  local before = PO.Popup()
  Call(f, "OnClick", "LeftButton", false)
  -- (a window opened by it: the focus on its first control, not left on the page behind)
  local pop = PO.Popup()
  if pop and pop ~= before then
    local items = PO.Collect(pop)
    if items[1] then PO.side = "popup" PO.SetFocus(items[1]) end
  end
  return true
end
-- left or right on a control: a slider's step, a dropdown's choice; else nil (the move along the row)
local function Adjust(f, dir)
  if not f then return nil end
  local d = DropOf(f)
  if d then
    local i = DropIndex(d) + dir
    if i >= 1 and i <= #d.options then DropPick(d, i) end
    return true
  end
  if f:GetObjectType() == "Slider" and f.padStep then
    f.padStep(dir)
    return true
  end
  return nil
end

-- The pad's button `what` ("up", "down", "left", "right", "a", "b", "lb", "rb") pressed while Options is open.
function PO.Do(what)
  if not PO.bound then return false end
  if Pad.Capturing() then return true end -- (Change waiting for a button: B held cancels it there, Pad.CaptureTick)
  -- a question up: Yes and No
  local q = Pad.Question()
  if q then
    if what == "a" then Call(q.yes, "OnClick", "LeftButton") return true end
    if what == "b" then Call(q.no, "OnClick", "LeftButton") return true end
    return true
  end
  -- a dropdown's list open
  if PO.listOpen and list and list.drop then
    local n = #list.drop.options
    if what == "up" or what == "left" then list.at = math.max(1, list.at - 1) FillList()
    elseif what == "down" or what == "right" then list.at = math.min(n, list.at + 1) FillList()
    elseif what == "a" then DropPick(list.drop, list.at) PO.CloseList()
    elseif what == "b" then PO.CloseList() end
    return true
  end
  if PO.typing then
    if what == "b" or what ~= "a" then
      if PO.typing.ClearFocus then PO.typing:ClearFocus() end
      PO.typing = nil
      if what == "b" then return true end
    end
  end
  -- a popup over Options: its controls one after another
  local pop = PO.Popup()
  if pop then
    local items = PO.Collect(pop)
    local at
    for i, f in ipairs(items) do
      if f == PO.focus then at = i end
    end
    if what == "b" then pop:Hide() PO.SetFocus(nil) PO.Refocus() return true end
    if #items == 0 then return true end
    if what == "a" then
      if at then PO.Press(items[at]) else PO.side = "popup" PO.SetFocus(items[1]) end
      return true
    end
    local step = (what == "down" or what == "right") and 1 or (what == "up" or what == "left") and -1 or 0
    if step ~= 0 then
      PO.side = "popup"
      PO.SetFocus(items[at and ((at - 1 + step) % #items) + 1 or 1])
    end
    return true
  end
  if PO.side == "popup" then PO.Refocus() end
  if what == "b" then
    local w = Window()
    if w then w:Hide() end
    PO.Apply()
    return true
  end
  if what == "lb" or what == "rb" then
    PO.ShowPage((ns.Options.CurrentPage() or 1) + (what == "rb" and 1 or -1))
    if PO.side == "page" then
      if not PageFocus(1, 1) then ListFocus(ns.Options.CurrentPage()) end
    else
      ListFocus(ns.Options.CurrentPage())
    end
    return true
  end
  -- the search box over the pages (asked 2026-11-16: "pressing up on the d pad from here id expect the search bar to
  -- be selectable"): up from a page's first row; A types in it, down goes back to the page, left to the list
  if PO.side == "search" then
    local box = PO.SearchBox()
    if what == "a" and box then PO.Press(box)
    elseif what == "down" and PO.searchFrom == "list" then ListFocus(1)
    elseif what == "down" then
      if not PageFocus(1, 1) then ListFocus(ns.Options.CurrentPage()) end
    elseif what == "left" then ListFocus(ns.Options.CurrentPage())
    elseif what == "right" then
      if not PageFocus(1, 1) then ListFocus(ns.Options.CurrentPage()) end
    end
    return true
  end
  if PO.side == "list" then
    local items = PO.ListItems()
    local i = PO.listAt or ns.Options.CurrentPage() or 1
    -- (up from the list's first page too: asked 2026-11-16, "still can't highlight search in options pane yet")
    if what == "up" and i <= 1 and PO.SearchBox() then PO.FocusSearch("list")
    elseif what == "up" then ListFocus(i - 1)
    elseif what == "down" then ListFocus(i + 1)
    elseif what == "right" then
      if items[i] and items[i] ~= ns.Options.footerReset and i ~= ns.Options.CurrentPage() then PO.ShowPage(i) end
      PageFocus(1, 1)
    elseif what == "a" then
      local t = items[i]
      if t == ns.Options.footerReset then PO.Press(t)
      elseif t then PO.ShowPage(i) ListFocus(i) end
    end
    return true
  end
  -- on the page
  local ri, ci, rows = Where()
  if not ri then
    if not PageFocus(1, 1) then ListFocus(ns.Options.CurrentPage()) end
    return true
  end
  local f = rows[ri][ci]
  if what == "up" and ri == 1 and PO.SearchBox() then PO.FocusSearch("page")
  elseif what == "up" then PageFocus(ri - 1, ci)
  elseif what == "down" then PageFocus(ri + 1, ci)
  elseif what == "left" or what == "right" then
    local dir = what == "right" and 1 or -1
    if not Adjust(f, dir) then
      if dir < 0 and ci == 1 then ListFocus(ns.Options.CurrentPage())
      elseif rows[ri][ci + dir] then PageFocus(ri, ci + dir) end
    end
  elseif what == "a" then
    PO.Press(f)
    -- (the page may have changed under it: shown or hidden rows)
    if PO.side == "page" and not PO.listOpen then
      local r2, c2 = Where()
      if r2 then PageFocus(r2, c2) else PageFocus(ri, ci) end
    end
  end
  return true
end
-- Options' search box, shown
function PO.SearchBox()
  local O = ns.Options
  local box = O.search and O.search.box
  return (box and box.IsShown and box:IsShown()) and box or nil
end
function PO.FocusSearch(from)
  local box = PO.SearchBox()
  if not box then return false end
  PO.side, PO.searchFrom = "search", from
  PO.SetFocus(box)
  return true
end
-- the focus back where it belongs (a popup gone, the window opened): the page's entry in the list, or the page's row
function PO.Refocus()
  if PO.side == "page" and PO.row then
    if PageFocus(PO.row, PO.col) then return end
  end
  ListFocus(ns.Options.CurrentPage())
end

---------------------------------------------------------------------------
-- The bindings
---------------------------------------------------------------------------

local owner
local buttons = {}
Owner = function()
  if not owner then
    owner = CreateFrame("Frame", PO.OWNER, UIParent)
    owner:Hide()
  end
  return owner
end
local repeater
local function KeyButton(key)
  local b = buttons[key]
  if b then return b end
  b = CreateFrame("Button", "AzerothGPSPadOpt_" .. key, Owner())
  b:RegisterForClicks("AnyDown", "AnyUp")
  b:SetScript("OnClick", function(_, _, down)
    local what = PO.KEYS[key]
    if down == false then
      if PO.held == key then PO.held = nil end
      return
    end
    Pad.SawInput(true) -- (the controller in use: its look on Options, PO.UpdateLook)
    local ok, err = pcall(PO.Do, what)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("controller", err) end
    if what == "up" or what == "down" or what == "left" or what == "right" then
      PO.held, PO.heldWait = key, PO.REPEAT_WAIT
      if repeater then repeater:Show() end
    end
  end)
  buttons[key] = b
  return b
end
PO.bound = false
function PO.Apply()
  local w = Window()
  if w and not w.agpsPadHooked then
    w.agpsPadHooked = true
    w:HookScript("OnShow", function() w.agpsShownAt = GetTime and GetTime() or 0 Pad.Apply() end)
    w:HookScript("OnHide", function() PO.CloseList() Pad.Apply() end)
  end
  if Locked() then
    if PO.bound then PO.Unmark() end
    return false
  end
  local want = PO.Wanted()
  if want == PO.bound then return want end
  local o = Owner()
  if want then
    for key in pairs(PO.KEYS) do
      KeyButton(key)
      pcall(SetOverrideBindingClick, o, true, key, "AzerothGPSPadOpt_" .. key, "LeftButton")
    end
    PO.bound = true
    PO.side = "list"
    ListFocus(ns.Options.CurrentPage())
    Arrow(Tabs()[ns.Options.CurrentPage()])
    ShowHint(PO.LookOn())
    if not repeater then
      repeater = CreateFrame("Frame", nil, UIParent)
      repeater:SetScript("OnUpdate", function(self, dt)
        if not (PO.bound and PO.held) then self:Hide() return end
        PO.heldWait = (PO.heldWait or 0) - (dt or 0)
        if PO.heldWait <= 0 then
          local down = Pad.KeysDown and Pad.KeysDown() or {}
          if next(down) ~= nil and not down[PO.held] then PO.held = nil self:Hide() return end
          PO.heldWait = PO.REPEAT_EVERY
          pcall(PO.Do, PO.KEYS[PO.held])
        end
      end)
      repeater:Hide()
      PO.repeater = repeater
    end
  else
    pcall(ClearOverrideBindings, o)
    PO.Unmark()
  end
  return want
end
-- the bindings gone (a fight, Options closed): the look with them
function PO.Unmark()
  PO.bound, PO.held, PO.typing = false, nil, nil
  PO.CloseList()
  PO.SetFocus(nil)
  if arrow then arrow.agpsOn = nil arrow:Hide() end
  ShowHint(false)
end
function PO.Clear()
  if owner and not Locked() then pcall(ClearOverrideBindings, owner) end
  PO.Unmark()
end
