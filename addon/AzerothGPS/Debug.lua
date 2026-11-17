-- The debug log (Options > Help > Debugging, asked 2026-11-13): a player with a problem ticks Debug log, does what goes
-- wrong, and clicks Export Debug Log...: a text to copy and send. No /reload: the log is in memory only (this session's,
-- never saved), so it's there to export at once. It holds what the addon's own checks note while it's on (herbs and ore
-- hovered and gathered, the map's icons after a gather, errors, the addon's work each second), with where the player is,
-- the settings and the addon's timings since login at export.
-- No character or realm names in it.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })

local D = {}
ns.Debug = D

D.MAX = 2000 -- entries kept (the oldest dropped): a session's log, never saved
D.on = false
D.log = {}

function D.On() return D.on end

-- Turned on: a new log from now. Off: the log stays, to export.
function D.SetOn(on)
  on = on and true or false
  if on and not D.on then
    D.log = {}
    D.t0 = GetTime and GetTime() or 0
    D.on = true
    D.Log("debug log on")
    D.StartSeconds()
  elseif not on and D.on then
    D.Log("debug log off")
    D.on = false
    if D.frame then D.frame:Hide() end
  end
end

-- While on, a line a second: the addon's work in that second (ms: 10 ms a second is 1% of a CPU core), the frame
-- rate, and the timings that took most of it (ns.perf's top ones, Core.lua). For CPU spikes (asked 2026-11-13).
D.SECOND_TOP = 3
local last -- { total, by = { [name] = total } } at the last second
local function Snapshot()
  local by, total = {}, 0
  for _, k in ipairs(ns.PERF_TOP or {}) do
    local p = ns.perf and ns.perf[k]
    if p then by[k] = p.total; total = total + p.total end
  end
  return { total = total, by = by }
end
function D.Second()
  local now = Snapshot()
  local prev = last
  last = now
  if not prev or now.total < prev.total then return end -- (the first, or the timings started over: /agps debug perf)
  local parts = {}
  for k, v in pairs(now.by) do
    local d = v - (prev.by[k] or 0)
    if d > 0.05 then parts[#parts + 1] = { k, d } end
  end
  table.sort(parts, function(a, b) return a[2] > b[2] end)
  local top = {}
  for i = 1, math.min(D.SECOND_TOP, #parts) do top[i] = string.format("%s %.1f", parts[i][1], parts[i][2]) end
  D.Log("second", { ms = string.format("%.1f", now.total - prev.total), fps = GetFramerate and GetFramerate() or false,
    top = #top > 0 and table.concat(top, ", ") or false })
end
function D.StartSeconds()
  last = Snapshot()
  if not CreateFrame then return end
  if not D.frame then
    D.frame = CreateFrame("Frame")
    local since = 0
    D.frame:SetScript("OnUpdate", function(_, dt)
      since = since + (dt or 0)
      if since >= 1 then
        since = since - 1
        if since > 1 then since = 0 end -- (a long hitch: one line for it, not a run of them)
        D.Second()
      end
    end)
  end
  D.frame:Show()
end

-- An entry: `what` happened, `fields` ({ name = value }) about it. Nothing while the log is off.
function D.Log(what, fields)
  if not D.on then return end
  local log = D.log
  log[#log + 1] = { t = (GetTime and GetTime() or 0) - (D.t0 or 0), what = what, fields = fields }
  while #log > D.MAX do table.remove(log, 1) end
end

-- An entry kept from login whether the log is on or not (and in the log too while it's on): the few things a
-- problem right after a /reload needs, before anyone could tick Debug log (the world map's first open, 2026-11-13).
-- Taken only now and then (the world map opening or closing, and its next redraws): the last KEEP_MAX.
D.KEEP_MAX = 60
D.loadedAt = GetTime and GetTime() or 0 -- (the addon loaded: the login or /reload)
D.kept = {}
function D.Keep(what, fields)
  local kept = D.kept
  kept[#kept + 1] = { t = GetTime and GetTime() or 0, what = what, fields = fields }
  while #kept > D.KEEP_MAX do table.remove(kept, 1) end
  D.Log(what, fields)
end

-- A value as text: a hidden (secret) one said so, numbers short.
local function Val(v)
  if ns.IsSecret and ns.IsSecret(v) then return "<secret>" end
  if type(v) == "number" then
    if v ~= math.floor(v) then return string.format("%.1f", v) end
    return string.format("%d", v)
  end
  if type(v) == "table" then
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = tostring(k) end
    table.sort(keys)
    return "{" .. table.concat(keys, ",") .. "}"
  end
  return tostring(v)
end
D.Val = Val

local function Fields(t)
  if type(t) ~= "table" then return t ~= nil and Val(t) or "" end
  local keys = {}
  for k in pairs(t) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  local out = {}
  for _, k in ipairs(keys) do out[#out + 1] = tostring(k) .. "=" .. Val(t[k]) end
  return table.concat(out, " ")
end

-- The text to send: the addon and game, where the player is, the settings, the errors kept, then the log.
function D.Text()
  local lines = {}
  local function add(s) lines[#lines + 1] = s end
  local build, num = "?", "?"
  if GetBuildInfo then build, num = GetBuildInfo() end
  add("AzerothGPS debug log")
  add(Fields({ version = ns.VERSION or "?", game = tostring(build) .. "." .. tostring(num),
    locale = GetLocale and GetLocale() or "?", date = date and date("%Y-%m-%d %H:%M:%S") or "?" }))
  local Geo = ns.Geo
  local ok, x, y, cont = pcall(function() return Geo.RealPlayerWorld() end)
  local okMap, map = pcall(function() return Geo.PlayerMap() end)
  local GPS = ns.GPS
  add("where: " .. Fields({ cont = ok and cont or false, x = ok and x or false, y = ok and y or false,
    map = okMap and map or false,
    square = GPS and GPS.MinimapTaken and GPS.MinimapTaken() and true or false,
    level = UnitLevel and UnitLevel("player") or false,
    class = UnitClassBase and UnitClassBase("player") or false,
    stops = ns.Nav and ns.Nav.stops and #ns.Nav.stops or 0,
    route = ns.Nav and ns.Nav.route and true or false }))
  local st = ns.settings and ns.settings.gps
  if type(st) == "table" then
    local keys = {}
    for k, v in pairs(st) do
      if type(v) ~= "table" or k == "nodeFilter" then keys[#keys + 1] = k end
    end
    table.sort(keys)
    local out = {}
    for _, k in ipairs(keys) do out[#out + 1] = k .. "=" .. Val(st[k]) end
    add("settings: " .. table.concat(out, " "))
  end
  -- the addon's timings since login (or /agps debug perf): ms a second, and its longest runs
  local span = math.max(0.001, (GetTime and GetTime() or 0) - (ns.perfSince or 0))
  local names = {}
  for k in pairs(ns.perf or {}) do names[#names + 1] = k end
  table.sort(names, function(a, b) return ns.perf[a].total > ns.perf[b].total end)
  add(string.format("performance (%.0f s, all: %.2f ms/s, %d fps):", span, (ns.PerfTotal and ns.PerfTotal() or 0) / span,
    GetFramerate and GetFramerate() or 0))
  for _, k in ipairs(names) do
    local p = ns.perf[k]
    add(string.format("  %s: %.2f ms/s, avg %.2f ms, max %.1f ms, %.1f runs/s, %d over 16 ms", k, p.total / span,
      p.total / math.max(1, p.n), p.max, p.n / span, p.slow))
  end
  local errors = ns.db and ns.db.errors or {}
  add(string.format("errors (%d):", #errors))
  for _, e in ipairs(errors) do
    add("  " .. Fields({ what = e.what, time = e.time }) .. " " .. tostring(e.err))
    if e.stack then add("    " .. tostring(e.stack):gsub("\n", "\n    ")) end
  end
  add(string.format("since login (%d, s after login):", #D.kept))
  for _, e in ipairs(D.kept) do
    add(string.format("  %7.2f %s %s", e.t - D.loadedAt, e.what, Fields(e.fields)))
  end
  add(string.format("log (%d, %s):", #D.log, D.on and "on" or "off"))
  for _, e in ipairs(D.log) do
    add(string.format("  %7.2f %s %s", e.t, e.what, Fields(e.fields)))
  end
  return table.concat(lines, "\n")
end

-- The window with the text, selected, to copy (Ctrl+C).
local win
function D.ShowExport()
  if not win then
    local f = ns.Window("AzerothGPSDebugExport", 520, 400, L["Debug Log"], "FULLSCREEN_DIALOG")
    local top = f.top
    local hint = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    hint:SetPoint("TOPLEFT", 14, top - 8)
    hint:SetPoint("RIGHT", -14, 0)
    hint:SetJustifyH("LEFT")
    hint:SetText(L["Press |cffffd100Ctrl+C|r to copy it, then paste it in the AzerothGPS Discord or the website's report form, with what went wrong."])
    local scroll = CreateFrame("ScrollFrame", "AzerothGPSDebugExportScroll", f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 14, top - 40)
    scroll:SetPoint("BOTTOMRIGHT", -34, 14)
    local bg = f:CreateTexture(nil, "BACKGROUND", nil, 1)
    bg:SetPoint("TOPLEFT", scroll, -4, 4)
    bg:SetPoint("BOTTOMRIGHT", scroll, 4, -4)
    bg:SetColorTexture(0, 0, 0, 1)
    local edit = CreateFrame("EditBox", nil, scroll)
    edit:SetMultiLine(true)
    edit:SetAutoFocus(false)
    edit:SetFontObject(ChatFontNormal)
    edit:SetWidth(460)
    edit:SetScript("OnEscapePressed", function() f:Hide() end)
    -- (read only: typing puts the text back; a click selects it all again)
    edit:SetScript("OnTextChanged", function(self, user)
      if user then
        self:SetText(f.text or "")
        self:HighlightText()
      end
    end)
    edit:SetScript("OnMouseUp", function(self) self:HighlightText() end)
    scroll:SetScrollChild(edit)
    scroll:SetScript("OnMouseDown", function() edit:SetFocus() end)
    f.edit = edit
    -- (closed: the log off, its box unticked; what it holds stays, to export again. Asked 2026-11-13)
    f:HookScript("OnHide", function()
      D.SetOn(false)
      if ns.Options and ns.Options.Refresh then pcall(ns.Options.Refresh) end
    end)
    win = f
  end
  win.text = D.Text()
  win.edit:SetText(win.text)
  win:Show()
  win:Raise()
  win.edit:SetFocus()
  win.edit:HighlightText()
  return win
end
