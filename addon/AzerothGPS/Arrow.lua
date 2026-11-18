-- The direction arrow (TomTom style), two panels (asked 2026-10-30): the arrow (AzerothGPSArrow, a big arrow along the
-- route) and the directions (AzerothGPSDirections: the next maneuver, "Turn left in 120 yd", "toward Razor Hill", the
-- stop it leads to with its distance and ETA, the maneuver after and the later stops; or the stops alone,
-- `dirStopsOnly`). Snapped (`arrowSnap`) the arrow sits on a side of the directions (`arrowSide`) and the two move as
-- one; apart, each is placed on its own (`arrowFreePoint`, `dirPoint`). Dragged, the arrow comes off the directions, and
-- dropped against a side of them it snaps there (A.SnapSide; asked 2026-10-30: "support snapping and detaching").
-- Sizes: `arrowPx`, `dirTextScale`. Toggle: gps.arrow (both panels). The arrow alone hidden: `arrowSide` "hide" (asked
-- 2026-11-17), only while the directions show (A.Hidden); the directions alone hidden: `dirShown` false.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format
local Geo = ns.Geo

local A = {}
ns.Arrow = A

local ARROW_ATLAS = "ui-hud-minimap-arrow-questtracking-2x"
local ARROW_FILE = "Interface\\Minimap\\MinimapArrow"
local TEXT_EVERY = 0.25 -- seconds between text updates (the arrow itself turns every frame)

local frame, dir, arrow, slot, bang, dist, line1, line2, line3, line4, grip, stale
-- the route's first step a hearthstone or teleport: its icon where the arrow is, glowing (pulsing like
-- the quest route's remake button), and over it its button, clear (GPSFrame's NewUseButton: a click uses it)
local useBtn, useIcon, useGlow
local SPRINT_ICON = "Interface\\Icons\\Ability_Rogue_Sprint" -- the quest route button's
local QUEST_ICON = "Interface\\GossipFrame\\AvailableQuestIcon" -- the "!" in a quest area
local rows = {} -- the later stops, as many as fit the directions' height
local rowsUnder -- the text line the rows go under (line4; line1 with the stops alone)
local ROW_H = 14 -- a row's height at text size 100%
local path, maneuvers, textWait = nil, nil, 0
local lastSet = {} -- (the rotation, color and jump icon as last set: not set again while unchanged)
A.SET_ROT = 0.005 -- radians the facing turns before the arrow is set again (about a third of a degree)
local jumpIcon

A.ARROW_PX = 58 -- the arrow's size by default (arrowPx; Options > Directions, ARROW_PX_MIN to ARROW_PX_MAX)
A.ARROW_PX_MIN, A.ARROW_PX_MAX = 32, 128
A.PAD = 8 -- the arrow panel's margin round the arrow
A.SIDES = { left = true, right = true, top = true, bottom = true }
-- (the one window before the two panels, 1.1.9: its arrow column, 8 + 58 + 8, left of the text)
A.OLD_COLUMN = 74

local function S() return ns.settings.gps end
-- opacity: full, or the combat setting in combat
local function Alpha()
  return ns.inCombat and (S().arrowCombatAlpha or 1) or 1
end
local function Px() return math.max(A.ARROW_PX_MIN, math.min(A.ARROW_PX_MAX, S().arrowPx or A.ARROW_PX)) end
local function K(n) return n * Px() / A.ARROW_PX end -- (a size in the arrow panel at the default arrow, scaled)
local function TextScale() return math.max(0.5, math.min(2, S().dirTextScale or 1)) end
local function RowH() return ROW_H * TextScale() end
local function IconPx(n) return math.floor(n * TextScale() + 0.5) end
local function Side()
  local s = S().arrowSide
  return A.SIDES[s] and s or "left"
end
-- snapped: with the directions hidden, the arrow is placed on its own
local function Snapped() return S().arrowSnap ~= false and S().dirShown ~= false end
A.Snapped = Snapped
-- The arrow hidden, the directions alone (Arrow side "Hide", asked 2026-11-17: "a fifth option that is 'Hide' that
-- hides the arrow"). Only while the directions show: with them hidden too the arrow shows, never an empty window (the
-- whole of it off is "Show direction arrow"). Its panel stays shown (its OnUpdate keeps the text going) at alpha 0 and
-- click-through, and shows anyway while the route's first step is a hearthstone or teleport: its button is there.
local function Hidden() return S().arrowSide == "hide" and S().dirShown ~= false end
A.Hidden = Hidden
-- The directions' least height: snapped on its left or right, the arrow's column
local function MinHeight()
  local side = Side()
  return (Snapped() and not Hidden() and (side == "left" or side == "right")) and Px() + 2 * A.PAD or 40
end

local function PointOf(f)
  local p, rel, rp, x, y = f:GetPoint(1)
  return { p, rel and rel:GetName() or "UIParent", rp, x, y }
end
local function SavePositions()
  S().dirPoint = PointOf(dir)
  if not Snapped() then S().arrowFreePoint = PointOf(frame) end
end

-- The side of the directions the arrow was dropped against: within SNAP_PX of it and beside it along that side; nil
-- for none. a, d: { left, right, top, bottom } of the arrow and the directions on the screen (y up).
A.SNAP_PX = 24
function A.SnapSide(a, d)
  local best, gap = nil, A.SNAP_PX
  local beside = a.bottom < d.top and a.top > d.bottom -- (overlapping up and down: left or right of it)
  local over = a.left < d.right and a.right > d.left -- (overlapping across: above or below it)
  for _, c in ipairs({ { "left", a.right - d.left, beside }, { "right", a.left - d.right, beside },
    { "top", a.bottom - d.top, over }, { "bottom", a.top - d.bottom, over } }) do
    if c[3] and math.abs(c[2]) <= gap then best, gap = c[1], math.abs(c[2]) end
  end
  return best
end
local function Rect(f)
  local l, r, t, b = f:GetLeft(), f:GetRight(), f:GetTop(), f:GetBottom()
  if not (l and r and t and b) then return nil end
  return { left = l, right = r, top = t, bottom = b }
end
local function RefreshOptions()
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
end

-- The old one window's place and size (arrowPoint, arrowSize) as the directions panel's: the text's part of it, so the
-- two snapped on the left are where the window was.
function A.FromOld(point, size)
  local p = type(point) == "table" and point or { "CENTER", "UIParent", "CENTER", 0, 0 }
  local w = type(size) == "table" and tonumber(size[1]) or 250
  local h = type(size) == "table" and tonumber(size[2]) or 86
  local at = tostring(p[1] or "CENTER")
  local shift = at:find("LEFT") and A.OLD_COLUMN or at:find("RIGHT") and 0 or A.OLD_COLUMN / 2
  return { p[1] or "CENTER", p[2] or "UIParent", p[3] or p[1] or "CENTER", (p[4] or 0) + shift, p[5] or 0 },
    { math.max(120, w - A.OLD_COLUMN), h }
end

-- A font string's size times k (its own size kept from the first time). SetTextScale where the client has it: SetFont
-- with the font object's file loses the font family's other alphabets, and Korean, Chinese and Russian text showed as
-- squares on an English client (the languages' screenshots, 2026-11-09).
local function ScaleText(fs, k)
  if fs.SetTextScale then
    fs:SetTextScale(k)
    return
  end
  if not fs.agpsFont then fs.agpsFont = { fs:GetFont() } end
  local f = fs.agpsFont
  if f[1] and f[2] then fs:SetFont(f[1], f[2] * k, f[3] or "") end
end

local function StopLabel(d, count)
  local icon = string.format("|T%s:%d|t ", ns.Nav.StopIcon(d), IconPx(14))
  if d.name then return icon .. d.name end
  return icon .. (count > 1 and string.format(L["stop %d"], 1) or L["destination"])
end

local function Colored(l)
  if type(l) == "string" then return l end
  return string.format("|cff%02x%02x%02x%s|r", math.floor(l[2] * 255), math.floor(l[3] * 255), math.floor(l[4] * 255), l[1])
end

-- Make room for `want` rows under the text: the directions grow down past their saved size while needed (quest
-- objectives), and go back to it after. Kept in place by the top left corner meanwhile.
local function FitRows(want)
  -- (not while the player sizes it: set back to the saved height 4 times a second, the corner stuck, asked 2026-10-30)
  if A.sizing then return end
  local base = math.max((S().dirSize or { 296, 97 })[2], MinHeight())
  local top, lb = dir:GetTop(), rowsUnder:GetBottom()
  if not top or not lb then return end
  local h = want > 0 and math.max(base, (top - lb) + 8 + want * RowH()) or base
  if math.abs(dir:GetHeight() - h) < 0.5 then return end
  local p = dir:GetPoint(1)
  if p ~= "TOPLEFT" then
    local left = dir:GetLeft()
    dir:ClearAllPoints()
    dir:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left, top)
  end
  dir:SetHeight(h)
end

local function PlaceRow(i)
  local row = rows[i]
  row:ClearAllPoints()
  row:SetPoint("TOPLEFT", rowsUnder, "BOTTOMLEFT", 0, -4 - (i - 1) * RowH())
  row:SetPoint("RIGHT", dir, "RIGHT", -18, 0)
end
local function SetRowsUnder(fs)
  if rowsUnder == fs then return end
  rowsUnder = fs
  for i in ipairs(rows) do PlaceRow(i) end
end
local function Row(i)
  local row = rows[i]
  if not row then
    row = dir:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row:SetJustifyH("LEFT")
    row:SetWordWrap(false)
    ScaleText(row, TextScale())
    rows[i] = row
    PlaceRow(i)
  end
  row:Show()
  return row
end

local function MoreStops(k)
  return string.format(k > 1 and L["|cff9d9d9d... %d more stops|r"] or L["|cff9d9d9d... %d more stop|r"], k)
end

-- Rows under the text line `under`: lines[from] on, as many as fit. `grow`: the directions grow to fit them all (quest
-- objectives); else they fill the height it has, the last saying how many more there are (`more(k)`).
local function FillRows(lines, from, under, grow, more)
  SetRowsUnder(under)
  FitRows(grow and math.max(0, #lines - from + 1) or 0)
  local lb, fb = under:GetBottom(), dir:GetBottom()
  local fit = (lb and fb) and math.max(0, math.floor((lb - fb - 6) / RowH())) or 0
  local n = 0
  for i = from, #lines do
    if n >= fit then break end
    n = n + 1
    local left = #lines - i + 1
    Row(n):SetText(more and n == fit and left > 1 and more(left) or Colored(lines[i]))
  end
  for k = n + 1, #rows do rows[k]:Hide() end
  return true
end

-- Lines { { text, r, g, b }, ... } into the four text lines, then rows below (the directions grow to fit them).
local function RenderLines(lines)
  for i, fs in ipairs({ line1, line2, line3, line4 }) do
    fs:SetText(lines[i] and Colored(lines[i]) or "")
  end
  return FillRows(lines, 5, line4, true)
end

-- The stops after the first, each with its distance and time from the stop before it
local function LaterStops(r, speed)
  local N, out = ns.Nav, {}
  for i = 2, #N.stops do
    local d, st = N.stops[i], r.stretches and r.stretches[i]
    local label = string.format("|T%s:%d|t %s", N.StopIcon(d), IconPx(12), d.name or string.format(L["stop %d"], i))
    out[#out + 1] = st and string.format("%d. %s  |cffffffff%s|r  |cffffd100%s|r", i, label, N.FormatDistance(st.walk),
      N.FormatTime(st.walk / speed + st.ride)) or string.format("%d. %s", i, label)
  end
  return out
end

-- In the stop's quest area (Nav's questing): a "!" and the objectives, one per line. Until
-- the stop's spot is reached the arrow still leads there (the "!" small beside it, the
-- distance small under it); after that just a big "!".
local function QuestText(px, py, cont)
  local N = ns.Nav
  local paused, r, d = N.QuestPaused(), N.route, N.dest
  local lines = N.QuestLines()
  for _, l in ipairs(N.areaQuests and N.QuestLines(N.areaQuests) or {}) do lines[#lines + 1] = l end
  -- where to after this: the next stop, with its distance from this one
  local nxt, st = N.stops[2], r and r.stretches and r.stretches[2]
  if nxt then
    local label = string.format("|T%s:%d|t %s", N.StopIcon(nxt), IconPx(12), nxt.name or string.format(L["stop %d"], 2))
    lines[#lines + 1] = { st and Format(L["Then: |cffffffff%s|r  %s"], N.FormatDistance(st.walk), label)
      or Format(L["Then: %s"], label), 0.75, 0.75, 0.75 }
  end
  bang:ClearAllPoints()
  bang:Show()
  bang:SetAlpha(1)
  if paused or not r or r.flying then
    -- (the spot reached, the route waiting: the small faded "!" at the arrow's top right, as with no route; asked
    -- 2026-11-15, "still shows a large one as well")
    path, maneuvers = nil, nil
    arrow:Hide()
    dist:Hide()
    bang:SetSize(K(22), K(22))
    bang:SetPoint("CENTER", arrow, "TOPRIGHT", -K(4), -K(4))
    bang:SetAlpha(0.5)
  else
    -- still leading to the spot: a smaller, fainter arrow (a little higher), "In quest
    -- area" and the yards to the spot under it; the "!" goes by the quest's title instead
    path = ns.Turns.Path(r)
    arrow:Show()
    arrow:SetSize(Px() / 2, Px() / 2)
    arrow:SetAlpha(0.5)
    arrow:ClearAllPoints()
    arrow:SetPoint("CENTER", slot, "CENTER", 0, K(10))
    dist:SetText(L["|cffbfbfbfIn quest area|r"] .. "\n" .. N.FormatDistance(r.walkYards))
    dist:Show()
    bang:Hide()
    if lines[1] then lines[1][1] = string.format("|T%s:%d|t %s", QUEST_ICON, IconPx(14), lines[1][1]) end
  end
  return RenderLines(lines)
end

-- (the arrow's use button, in the arrow's place: anchored to the arrow panel itself, as the map's to its panel,
-- not to the texture there: in the game it wasn't over the icon to click, 2026-10-01)
A.USE_PX = 28
local function PlaceUse(b)
  b:SetSize(A.USE_PX, A.USE_PX)
  b:SetPoint("CENTER", frame, "CENTER") -- (the slot's middle)
end
local function SetUse(t)
  local G = ns.GPS
  if useBtn and G and G.SetUseButton then G.SetUseButton(useBtn, t, PlaceUse) end
end
A.SetUse = SetUse

local function UpdateText(px, py, cont)
  local N = ns.Nav
  ns.Nav.Status(px, py, cont) -- keeps the route current and advances stops, even with the GPS hidden
  -- the route starting with a hearthstone or teleport from here (its step 1): said as that, with its
  -- button where the arrow is (asked, 2026-10-01: the turns of the walk after it were shown instead,
  -- out of step with the steps), the walk after it next
  local use = N.route and N.dest and not N.route.flying and not (N.questing and N.dest) and N.UseNow and N.UseNow() or nil
  SetUse(use)
  if not use then
    useIcon:Hide()
    useGlow:Hide()
  end
  if N.questing and N.dest then return QuestText(px, py, cont) end
  arrow:SetSize(Px(), Px())
  arrow:SetAlpha(1)
  bang:SetAlpha(1)
  arrow:ClearAllPoints()
  arrow:SetPoint("CENTER", slot, "CENTER")
  arrow:Show()
  useIcon:Hide()
  useGlow:Hide()
  bang:Hide()
  dist:Hide()
  local r, d = N.route, N.dest
  if d and N.paused then
    -- routing paused (Nav.SetPaused): the arrow as on a flight, up and blue, no turns; "Routing is paused" (or why it
    -- was paused) and how to resume, then the stop as the crow flies
    path, maneuvers = nil, {}
    arrow:SetRotation(0)
    arrow:SetVertexColor(0.6, 0.8, 1)
    lastSet.rot, lastSet.color = nil, nil
    line1:SetText(N.paused == "auto" and L["|cffffd100Routing paused: you're not following the route|r"]
      or L["|cffffd100Routing is paused|r"])
    line2:SetText(L["|cff9d9d9dResume Routing in the map menu, or /agps pause|r"])
    local dd = d.cont == cont and math.sqrt((d.x - px) ^ 2 + (d.y - py) ^ 2) or nil
    line3:SetText(dd and string.format("%s  |cffffffff%s|r", StopLabel(d, #N.stops), N.FormatDistance(dd))
      or StopLabel(d, #N.stops))
    line4:SetText("")
    for _, row in ipairs(rows) do row:Hide() end
    return true
  end
  if r and N.RedAsking and N.RedAsking() then r = nil end -- (asked "keep this route?": not followed yet)
  if not d and N.areaQuests then
    -- no route, in a quest's area: its objectives, with the small "!" at the arrow's top right, as beside the arrow on
    -- a route (asked 2026-11-15: "change it to the same one we show when there is an arrow, the small one in the top
    -- right only"), no arrow
    path, maneuvers = nil, nil
    arrow:Hide()
    bang:ClearAllPoints()
    bang:SetSize(K(22), K(22))
    bang:SetPoint("CENTER", arrow, "TOPRIGHT", -K(4), -K(4))
    bang:SetAlpha(0.5) -- (faded, as the arrow in a quest's area on the way there; asked 2026-11-15)
    bang:Show()
    return RenderLines(N.QuestLines(N.areaQuests))
  end
  if not r or not d then
    path, maneuvers = nil, nil
    return false
  end
  if r.flying or use then -- in the air: where it lands and when; turns resume after landing (or the teleport)
    path, maneuvers = nil, {}
  else
    path, maneuvers = ns.Turns.Ahead(r, StopLabel(d, #N.stops)) -- (the next ones, once per route as it is now)
  end
  local m = maneuvers[1]
  local stopsOnly = S().dirStopsOnly
  local cur, walk, mount, mounted = N.Speeds()
  if N.areaQuests and not r.flying then
    -- in a quest's area on the way (not the stop's): its objectives first with a small
    -- "!" by the arrow, then the next turn and the stop, the arrow still leading on
    bang:ClearAllPoints()
    bang:SetSize(K(22), K(22))
    bang:SetPoint("CENTER", arrow, "TOPRIGHT", -K(4), -K(4))
    bang:Show()
    local speed = (cur and cur > 0.5) and cur or (mounted and mount or walk)
    local lines = N.QuestLines(N.areaQuests)
    if m and not stopsOnly then lines[#lines + 1] = { string.format("%s  |cffffffff%s|r", m.text, N.FormatDistance(m.dist)), 1, 0.82, 0 } end
    lines[#lines + 1] = { string.format("%s  |cffffffff%s|r  |cffffd100%s|r", StopLabel(d, #N.stops),
      N.FormatDistance(r.walkYards), N.FormatTime(r.walkYards / speed + r.rideSeconds)), 1, 1, 1 }
    return RenderLines(lines)
  end
  if r.flying then
    arrow:SetRotation(0)
    arrow:SetVertexColor(0.6, 0.8, 1)
  elseif use then
    arrow:Hide() -- (its icon there instead, glowing: click it)
    useIcon:SetTexture(ns.GPS and ns.GPS.UseTexture and ns.GPS.UseTexture(use) or 134400)
    useIcon:Show()
    useGlow:Show()
  end
  -- the stop: its marker and name, distance and ETA
  local speed = (cur and cur > 0.5 and not r.flying) and cur or (mounted and mount or walk)
  local yards, eta = N.FormatDistance(r.walkYards), N.FormatTime(r.walkYards / speed + r.rideSeconds)
  if stopsOnly then
    -- (dirStopsOnly, asked 2026-10-30: the stops alone, no turns) the first on the top line, the later ones under it
    line1:SetText(string.format("%s%s  |cffffffff%s|r  |cffffd100%s|r", #N.stops > 1 and "1. " or "", StopLabel(d, #N.stops),
      yards, eta))
    line2:SetText("")
    line3:SetText("")
    line4:SetText("")
    return FillRows(LaterStops(r, speed), 1, line1, false, MoreStops)
  end
  if r.flying then
    line1:SetText(N.RidingText(r.flying.kind, r.flying.to))
    line2:SetText(N.RidingWhen(r.flying.kind, r.flying.seconds))
  elseif use then
    line1:SetText(Format(L["Use %s"], tostring(use[8])))
    line2:SetText(use[10] and use[10] ~= "" and Format(L["to %s"], use[10]) or "")
  elseif m then
    -- what to do now, then the maneuver: "Continue straight, then slight right in 13 yd" (shorter when
    -- the panel is too narrow for it on one line)
    local function yd(v) return "|cffffffff" .. N.FormatDistance(v) .. "|r" end
    line1:SetText(ns.Turns.NowText(m, yd))
    if line1:GetStringWidth() > line1:GetWidth() + 1 then line1:SetText(ns.Turns.NowText(m, yd, true)) end
    -- (and the stop's height against yours, in a city: "Below you, 12 yd down")
    local hint = N.HeightText(px, py, cont)
    local toward = m.toward and Format(L["toward %s"], m.toward) or ""
    line2:SetText(hint and (toward ~= "" and toward .. "  " .. hint or hint) or toward)
  else
    line1:SetText("")
    line2:SetText("")
  end
  line3:SetText(string.format("%s  |cffffffff%s|r  |cffffd100%s|r%s", StopLabel(d, #N.stops), yards, eta,
    #N.stops > 1 and string.format("  |cff9d9d9d(1/%d)|r", #N.stops) or ""))
  local nxt = maneuvers[2]
  line4:SetText(nxt and Format(L["Then: %s in %s"], nxt.text, N.FormatDistance(nxt.dist - (m and m.dist or 0))) or "")
  if use then -- (then the steps' second: the walk from where it lands)
    local steps = N.Steps()
    line4:SetText(steps[2] and Format(L["Then: %s"], steps[2]) or "")
  end
  -- the later stops, each with its distance and time from the stop before it
  return FillRows(LaterStops(r, speed), 1, line4, false, MoreStops)
end

-- The corner let go: the size it was left at is the directions' own
local function EndSizing()
  dir:StopMovingOrSizing()
  A.sizing = nil
  S().dirSize = { math.floor(dir:GetWidth() + 0.5), math.floor(dir:GetHeight() + 0.5) }
  SavePositions()
  textWait = 0 -- relist the stops for the new size
end

local function Update(dt)
  -- (the mouse let go where the corner didn't hear it: hidden meanwhile)
  if A.sizing and IsMouseButtonDown and not IsMouseButtonDown("LeftButton") then EndSizing() end
  local px, py, cont = Geo.PlayerWorld()
  -- (the player and their facing as at the last look, nothing pulsing: OnUpdate's idle rate, A.IDLE_HZ)
  local facing = Geo.Facing()
  A.still = px ~= nil and px == A.lastX and py == A.lastY and facing == A.lastFacing and not A.sizing
  A.lastX, A.lastY, A.lastFacing = px, py, facing
  -- a quest picked up or finished since the quest route was made: the Sprint icon pulses in the corner
  local N = ns.Nav
  if N.questRouteStale and not N.OnQuestRoute() then N.questRouteStale = nil end
  if N.questRouteStale then
    stale:SetAlpha(0.55 + 0.45 * math.sin(GetTime() * 4))
    stale:Show()
    A.still = false
  else
    stale:Hide()
  end
  if useIcon:IsShown() then -- (the hearthstone's icon in the arrow's place: glowing, as the remake button pulses)
    local a = 0.55 + 0.45 * math.sin(GetTime() * 4)
    useIcon:SetAlpha(0.75 + 0.25 * a)
    useGlow:SetAlpha(a)
    A.still = false
  end
  textWait = textWait - dt
  if textWait <= 0 then
    textWait = TEXT_EVERY
    local active = px and UpdateText(px, py, cont)
    -- no route: hidden and click-through (kept shown so this keeps checking), except while unlocked (to place and
    -- size them)
    local placing = not active and not S().arrowLocked
    if placing then
      line1:SetText(L["|cff9d9d9dNo route|r"])
      line2:SetText(L["Set one on the map: double-click a spot, or pan and Confirm Route."])
      line3:SetText(L["|cff9d9d9dDrag to move, corner to resize, right-click to lock.|r"])
      line4:SetText("")
      for _, row in ipairs(rows) do row:Hide() end
      arrow:SetRotation(0)
      arrow:SetVertexColor(0.5, 0.5, 0.5)
      lastSet.rot = nil -- (set outside the cache: the next route sets the arrow again)
    end
    local show = active or placing
    -- (the arrow hidden: its panel unseen and click-through, but for a hearthstone's or teleport's button there)
    local arrowShow = show and (not Hidden() or useIcon:IsShown())
    -- click-through (options): in combat, and/or while moving
    local st = S()
    local moving = ns.GPS and ns.GPS.PlayerMoving and ns.GPS.PlayerMoving()
    -- locked: always click-through (nothing to click on it then; unlocked it's dragged)
    local through = st.arrowLocked or (st.clickThroughCombat and ns.inCombat) or (st.clickThroughMoving and moving)
    for _, f in ipairs({ frame, dir }) do
      local on = f == dir and show or f == frame and arrowShow
      f:SetAlpha(on and Alpha() or 0)
      f:EnableMouse(on and not through)
    end
    grip:SetShown(show and not st.arrowLocked)
    if not active then return end
  end
  if not px or not path or Hidden() then return end
  local tx, ty = ns.Turns.Target(path, px, py)
  if not tx then return end
  local rel = ns.Turns.RelativeAngle(px, py, Geo.Facing(), tx, ty)
  -- green when heading the right way, gold for a turn, red when it's behind you; orange at a
  -- drop off a ledge coming up: jump down there
  local a = math.abs(rel)
  local m1 = maneuvers and maneuvers[1]
  local drop = m1 and m1.kind == "drop" and m1.dist <= 12
  local jump = (m1 and m1.kind == "drop" and m1.dist <= 15) and true or false
  local color = drop and 4 or a < math.rad(20) and 1 or a < math.rad(100) and 2 or 3
  -- (running straight, nothing changes: the rotation, color and jump icon aren't set again every
  -- frame — they were most of the arrow's cost with arrowHz 0, the 2026-10-07 idle profile)
  if math.abs(rel - (lastSet.rot or 99)) > A.SET_ROT or color ~= lastSet.color or jump ~= lastSet.jump then
    arrow:SetRotation(rel)
    if color == 1 then arrow:SetVertexColor(0.45, 1, 0.45)
    elseif color == 2 then arrow:SetVertexColor(1, 1, 1)
    elseif color == 3 then arrow:SetVertexColor(1, 0.45, 0.35)
    else arrow:SetVertexColor(1, 0.55, 0.1) end
    jumpIcon:SetShown(jump)
    lastSet.rot, lastSet.color, lastSet.jump = rel, color, jump
  end
  if jump then
    jumpIcon:SetAlpha(0.55 + 0.45 * math.sin(GetTime() * 7))
    A.still = false
  end
end

-- Errors are reported once (else the window would just stay invisible).
local sinceUpdate = 0
A.IDLE_HZ, A.IDLE_HZ_LIMITED = 10, 5
local function OnUpdate(_, dt)
  -- (the route's background searches are pumped by the map's OnUpdate, or its pump frame while it's
  -- hidden — not here: hidden frames get no OnUpdate, and with the arrow off nothing pumped, 2026-10-07)
  -- (Options > Performance: the arrow turned at most arrowHz times a second; 0: every frame)
  sinceUpdate = sinceUpdate + dt
  local hz = S().arrowHz or 0
  if hz > 0 and sinceUpdate < 1 / hz then return end
  -- (standing still, facing the same way, nothing pulsing: A.IDLE_HZ, A.IDLE_HZ_LIMITED with arrowHz set; issue #191:
  -- the arrow was most of a still player's cost. A turn or a step is looked at at once: two of the game's calls)
  if A.still and sinceUpdate < 1 / (hz > 0 and A.IDLE_HZ_LIMITED or A.IDLE_HZ) then
    local px, py = Geo.PlayerWorld()
    if px == A.lastX and py == A.lastY and Geo.Facing() == A.lastFacing then return end
  end
  dt, sinceUpdate = sinceUpdate, 0
  local t0 = ns.PerfStart and ns.PerfStart()
  local ok, err = pcall(Update, dt)
  if t0 then ns.PerfEnd("arrow window", t0) end
  if not ok then
    A.lastError = tostring(err)
    if not A.errorShown then
      A.errorShown = true
      ns.Print(string.format(L["direction arrow error: %s"], tostring(A.lastError)))
    end
  end
end

function A.Describe()
  if not frame then return "not created" end
  return string.format("shown=%s visible=%s alpha=%.2f route=%s arrow=%.0fx%.0f directions=%s %.0fx%.0f snap=%s%s",
    tostring(frame:IsShown()), tostring(frame:IsVisible()), frame:GetAlpha(), tostring(ns.Nav.route ~= nil),
    frame:GetWidth(), frame:GetHeight(), tostring(dir:IsShown()), dir:GetWidth(), dir:GetHeight(),
    Snapped() and Side() or "off", A.lastError and (" error: " .. A.lastError) or "")
end

-- The arrow panel's size and place: snapped, against the directions' side (as tall as them on the left or right, as
-- wide above or below), the two kept on the screen as one; apart, a box round the arrow at its own spot.
local function Layout()
  local st, px = S(), Px()
  local col = px + 2 * A.PAD
  slot:SetSize(px, px)
  arrow:SetSize(px, px) -- (questing, half that: from the next text update)
  jumpIcon:SetSize(K(24), K(24))
  jumpIcon:ClearAllPoints()
  jumpIcon:SetPoint("CENTER", arrow, "BOTTOMLEFT", K(6), K(6))
  dist:SetWidth(px + 12) -- (within the arrow's column: wraps there)
  if Snapped() then
    st.arrowFreePoint = nil -- (unsnapped again, it starts where it is then)
    local side = Side()
    frame:ClearAllPoints()
    if side == "left" or side == "right" then
      local a, b = side == "left" and "RIGHT" or "LEFT", side == "left" and "LEFT" or "RIGHT"
      frame:SetPoint("TOP" .. a, dir, "TOP" .. b)
      frame:SetPoint("BOTTOM" .. a, dir, "BOTTOM" .. b)
      frame:SetWidth(col)
    else
      local a, b = side == "top" and "BOTTOM" or "TOP", side == "top" and "TOP" or "BOTTOM"
      frame:SetPoint(a .. "LEFT", dir, b .. "LEFT")
      frame:SetPoint(a .. "RIGHT", dir, b .. "RIGHT")
      frame:SetHeight(col)
    end
    frame:SetClampedToScreen(false)
    if Hidden() then col = 0 end -- (no arrow to keep on the screen with them)
    dir:SetClampRectInsets(side == "left" and -col or 0, side == "right" and col or 0, side == "top" and col or 0,
      side == "bottom" and -col or 0)
  else
    local p = st.arrowFreePoint
    if type(p) ~= "table" then -- (just unsnapped: where it is now)
      local left, top = frame:GetLeft(), frame:GetTop()
      p = left and top and { "TOPLEFT", "UIParent", "BOTTOMLEFT", left, top } or { "CENTER", "UIParent", "CENTER", 0, 200 }
      st.arrowFreePoint = p
    end
    frame:ClearAllPoints()
    frame:SetPoint(p[1], _G[p[2]] or UIParent, p[3], p[4], p[5])
    frame:SetSize(col, col)
    frame:SetClampedToScreen(true)
    dir:SetClampRectInsets(0, 0, 0, 0)
  end
end

function A.Apply()
  if not frame then return end
  local st = S()
  if type(st.dirPoint) ~= "table" then st.dirPoint, st.dirSize = A.FromOld(st.arrowPoint, st.arrowSize) end
  local p = st.dirPoint
  dir:ClearAllPoints()
  dir:SetPoint(p[1], _G[p[2]] or UIParent, p[3], p[4], p[5])
  local minH = MinHeight()
  if dir.SetResizeBounds then dir:SetResizeBounds(120, minH, 900, 700)
  elseif dir.SetMinResize then dir:SetMinResize(120, minH) end
  local size = st.dirSize or { 296, 97 }
  dir:SetSize(size[1], math.max(size[2], minH))
  frame:SetMovable(not st.arrowLocked)
  dir:SetMovable(not st.arrowLocked)
  -- (each its own background, asked 2026-10-30: the directions' is the arrow's until it's set)
  frame:SetBackdropColor(0, 0, 0, st.arrowBg or 0.55)
  dir:SetBackdropColor(0, 0, 0, st.dirBg or st.arrowBg or 0.55)
  dir:SetResizable(not st.arrowLocked)
  Layout()
  local k = TextScale()
  for _, fs in ipairs({ line1, line2, line3, line4, dist }) do ScaleText(fs, k) end
  for i, row in ipairs(rows) do
    ScaleText(row, k)
    PlaceRow(i)
  end
  grip:SetShown(not st.arrowLocked)
  -- (none in a battleground or an arena: asked 2026-11-10, GPSFrame.lua's ns.InBattleground)
  local on = st.arrow and not (ns.inCombat and st.combatHideArrow) and not (ns.InBattleground and ns.InBattleground())
  frame:SetShown(on)
  dir:SetShown(on and st.dirShown ~= false)
  lastSet.rot = nil -- (its size may have changed: set again)
  textWait = 0 -- refresh now
end

-- A right-click on the arrow or the directions, unlocked (asked 2026-11-11: "support right clicking either one with a
-- popup next to the mouse to confirm locking its position, then after locking it another popup telling them where in
-- options to unlock it in the future"): "Lock ... here?" by the mouse, then where the lock is. Not in the tutorial,
-- which unlocks them for its own steps and puts the player's setting back after.
local function ByMouse(f)
  local x, y = 0, 0
  if GetCursorPosition then x, y = GetCursorPosition() end
  local s = UIParent and UIParent.GetEffectiveScale and UIParent:GetEffectiveScale() or 1
  if not s or s <= 0 then s = 1 end
  f:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", (x or 0) / s + 12, (y or 0) / s + 12)
end
function A.Lock()
  S().arrowLocked = true
  A.Apply()
  RefreshOptions()
  if ns.Ask then
    A.lockTold = ns.Ask("AzerothGPSArrowLock", L["Locked. To unlock them later: Options > Directions > Lock arrow position."], OKAY or "OK", nil, nil, nil,
      { place = ByMouse, single = true, strata = "DIALOG" })
  end
end
function A.AskLock()
  if S().arrowLocked or (ns.Tutorial and ns.Tutorial.run) or not ns.Ask then return nil end
  A.lockAsk = ns.Ask("AzerothGPSArrowLock", L["Lock the arrow and the directions in place here?"], nil, nil, A.Lock, nil, { place = ByMouse, strata = "DIALOG" })
  return A.lockAsk
end

-- Told once, to a player who had them locked before unlocked became the default (asked 2026-11-11: "One time pop up
-- for existing users to ask if they want to unlock the arrow and directions and how they can lock it back", then
-- "preemptively set them to unlocked ... [Leave Unlocked] [Lock]"): they're unlocked first, then the popup says so
-- and how to lock them again; Lock puts the lock back, anything else leaves them unlocked. A few seconds after
-- login. A new install, or a player who has them unlocked already: never. Put off to a later login while the
-- tutorial runs, in a fight, or with the arrow turned off. Once for the account (db.arrowUnlockOffered).
A.UNLOCK_OFFER_WAIT = 6
function A.OfferUnlock()
  local db = ns.db
  if not db or db.arrowUnlockOffered or not ns.Ask then return nil end
  local st = S()
  if not st.arrowLocked then
    db.arrowUnlockOffered = true
    return nil
  end
  if not st.arrow or (ns.Tutorial and ns.Tutorial.run) or ns.inCombat then return nil end
  db.arrowUnlockOffered = true
  st.arrowLocked = false
  A.Apply()
  RefreshOptions()
  A.unlockAsk = ns.Ask("AzerothGPSArrowUnlock", L["Directions and the arrow are now unlocked by default. You can move them now if you wish.\n\nTo lock them again: right-click either one, or Options > Directions > Lock arrow position."], L["Leave Unlocked"], L["Lock"], nil, function(clicked)
    if not clicked then return end -- (Escape, the close button: left unlocked)
    S().arrowLocked = true
    A.Apply()
    RefreshOptions()
  end, { strata = "DIALOG" })
  return A.unlockAsk
end

-- A panel: dragged while unlocked. The directions snapped carry the arrow; the arrow dragged comes off them (from where
-- it is), and dropped against a side of them snaps there.
local function Panel(name)
  local f = CreateFrame("Frame", name, UIParent, "BackdropTemplate")
  f:SetFrameStrata("MEDIUM")
  f:SetClampedToScreen(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", function(self)
    local st = S()
    if st.arrowLocked then return end
    if self == frame and Snapped() then
      local left, top = frame:GetLeft(), frame:GetTop()
      st.arrowSnap = false
      st.arrowFreePoint = left and top and { "TOPLEFT", "UIParent", "BOTTOMLEFT", left, top } or nil
      A.Apply()
      RefreshOptions()
    end
    A.moving = self
    self:StartMoving()
  end)
  f:SetScript("OnDragStop", function(self)
    if A.moving then A.moving:StopMovingOrSizing() end
    A.moving = nil
    SavePositions()
    if self == frame and not Snapped() and S().dirShown ~= false then
      local a, d = Rect(frame), Rect(dir)
      local side = a and d and A.SnapSide(a, d)
      if side then
        S().arrowSnap, S().arrowSide = true, side
        A.Apply()
        RefreshOptions()
      end
    end
  end)
  f:SetScript("OnMouseUp", function(_, button)
    if button == "RightButton" and not A.moving then A.AskLock() end
  end)
  f:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8" })
  f:SetBackdropColor(0, 0, 0, 0.55)
  return f
end

function A.Init()
  if frame then return end
  dir = Panel("AzerothGPSDirections")
  dir:SetSize(296, 97)
  frame = Panel("AzerothGPSArrow")
  frame:SetSize(A.ARROW_PX + 2 * A.PAD, A.ARROW_PX + 2 * A.PAD)
  A.frame, A.dir = frame, dir -- (the tests)

  -- the quest route is missing a new quest (see Update): click it to remake the route. Its
  -- own button, so it takes clicks even while the panel is click-through (locked)
  stale = CreateFrame("Button", nil, dir)
  stale:SetSize(18, 18)
  stale:SetPoint("TOPRIGHT", -3, -3)
  stale:SetFrameLevel(dir:GetFrameLevel() + 5)
  local sicon = stale:CreateTexture(nil, "ARTWORK")
  sicon:SetAllPoints()
  sicon:SetTexture(SPRINT_ICON)
  sicon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
  local shl = stale:CreateTexture(nil, "HIGHLIGHT")
  shl:SetAllPoints()
  shl:SetColorTexture(1, 1, 1, 0.25)
  stale:SetScript("OnClick", function()
    if ns.GPS and ns.GPS.QuestRerouteClick then ns.GPS.QuestRerouteClick() end
  end)
  stale:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText(L["Quest Route"], 1, 1, 1)
    GameTooltip:AddLine(L["You picked up or finished a quest since this quest route was made. Click to make it again with new quests and turn-ins."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  stale:SetScript("OnLeave", GameTooltip_Hide)
  stale:Hide()

  -- resize grip (the directions' bottom-right), while unlocked
  grip = CreateFrame("Button", nil, dir)
  grip:SetSize(14, 14)
  grip:SetPoint("BOTTOMRIGHT", -2, 2)
  grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
  grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
  grip:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
  grip:SetScript("OnMouseDown", function()
    if S().arrowLocked then return end
    A.sizing = true
    dir:StartSizing("BOTTOMRIGHT")
  end)
  grip:SetScript("OnMouseUp", function() if A.sizing then EndSizing() end end)
  A.grip = grip

  -- the arrow's spot: fixed in the middle of its panel, so a smaller arrow (questing) stays centered in it
  slot = frame:CreateTexture(nil, "BACKGROUND")
  slot:SetSize(A.ARROW_PX, A.ARROW_PX)
  slot:SetPoint("CENTER")
  arrow = frame:CreateTexture(nil, "ARTWORK")
  arrow:SetSize(A.ARROW_PX, A.ARROW_PX)
  arrow:SetPoint("CENTER", slot, "CENTER")
  ns.SetIcon(arrow, "atlas:" .. ARROW_ATLAS, ARROW_FILE)
  A.arrowTex = arrow -- (the tests: the unchanged-skip counts its Sets)
  -- a drop off a ledge coming up: a flashing jump icon by the arrow
  jumpIcon = frame:CreateTexture(nil, "OVERLAY")
  jumpIcon:SetTexture("Interface\\Icons\\Spell_Magic_FeatherFall")
  jumpIcon:Hide()
  -- (the route's first step a hearthstone or teleport: its icon in the arrow's place, glowing, and its
  -- button over it: the panel's own texture shows it whatever the secure button does)
  useIcon = frame:CreateTexture(nil, "ARTWORK")
  useIcon:SetSize(A.USE_PX, A.USE_PX)
  useIcon:SetPoint("CENTER", slot, "CENTER")
  useIcon:Hide()
  useGlow = frame:CreateTexture(nil, "OVERLAY")
  useGlow:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
  useGlow:SetBlendMode("ADD")
  useGlow:SetVertexColor(1, 0.85, 0.3)
  useGlow:SetSize(A.USE_PX * 1.9, A.USE_PX * 1.9)
  useGlow:SetPoint("CENTER", useIcon, "CENTER")
  useGlow:Hide()
  if ns.GPS and ns.GPS.NewUseButton then
    useBtn = ns.GPS.NewUseButton("AzerothGPSArrowUseButton", frame, A.USE_PX)
    if useBtn then useBtn.icon:SetAlpha(0) end -- (clear: the icon under it is the panel's)
  end
  bang = frame:CreateTexture(nil, "ARTWORK")
  bang:SetSize(40, 40)
  bang:SetPoint("CENTER", arrow, "CENTER")
  bang:SetTexture(QUEST_ICON)
  bang:Hide()
  dist = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall") -- questing: yards to the spot
  dist:SetPoint("TOP", arrow, "BOTTOM", 0, -2)
  dist:SetJustifyH("CENTER")
  dist:Hide()

  line1 = dir:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  line1:SetPoint("TOPLEFT", 8, -8)
  line1:SetPoint("RIGHT", -8, 0)
  line1:SetJustifyH("LEFT")
  line2 = dir:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  line2:SetPoint("TOPLEFT", line1, "BOTTOMLEFT", 0, -2)
  line2:SetPoint("RIGHT", -8, 0)
  line2:SetJustifyH("LEFT")
  line3 = dir:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  line3:SetPoint("TOPLEFT", line2, "BOTTOMLEFT", 0, -4)
  line3:SetPoint("RIGHT", -8, 0)
  line3:SetJustifyH("LEFT")
  line4 = dir:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  line4:SetPoint("TOPLEFT", line3, "BOTTOMLEFT", 0, -3)
  line4:SetPoint("RIGHT", -8, 0)
  line4:SetJustifyH("LEFT")
  rowsUnder = line4

  frame:SetScript("OnUpdate", OnUpdate)
  for _, f in ipairs({ frame, dir }) do
    f:SetAlpha(0)
    f:EnableMouse(false)
  end
  A.Apply()
end
