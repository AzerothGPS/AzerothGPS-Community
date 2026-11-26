-- The FAQ window (item 48, Kooki3z 2026-11-24): Options > Help's FAQ button and `/agps faq`. AzerothGPS's popup style
-- (ns.Window: the GPS map's frame, its corner logo), each question a heading with its short answer under it, scrolling,
-- Close at the bottom right; over the world map too (ns.POPUP_OVER_STRATA). Every answer is what this version does:
-- checked against the code when written (item 48's rule: nothing not true yet).
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })

local F = {}
ns.Faq = F
F.W, F.H = 520, 460
F.GAP, F.PAD = 10, 16

-- { question, answer } in order
F.ITEMS = {
  { L["Why are there so many \"AzerothGPS map data\" entries in my AddOn List?"],
    L["They're part of AzerothGPS: the map's own ground that routes walk, split into one folder per region so only the regions near you load and memory stays low. Keep them installed and turned on; updating AzerothGPS updates them all. With one turned off, routes there use the older routing (AzerothGPS says so once)."] },
  { L["Why does it say \"Working out the route...\"?"],
    L["Routes are worked out in the background, a little each frame, so your game stays smooth. Short trips settle almost at once; long trips across zones can take a few seconds. The route shows faded meanwhile."] },
  { L["What does \"No way found yet\" mean?"],
    L["AzerothGPS knows no walking way to that spot yet (inside some caves and buildings, for example). Pick a stop nearby. To report the spot, see the last question."] },
  { L["What are the coiled and wavy lines on the route?"],
    L["A coil is a jump down a ledge or across a gap; a wavy line is a swim. Right-click a jump to avoid jumps for that stop, or right-click a swim and click Remove? to go around by land."] },
  { L["Why does it tell me to cast Slow Fall, Levitate or another fall spell?"],
    L["Spell jumping (Options > Routing > Use class spells): with a fall spell or item ready, routes may jump down drops too high to survive without it. The directions say when to cast, and a button beside them casts it. With Expert jumper, off any ledge: cast just before you land."] },
  { L["What is Safe drop?"],
    L["How far routes may drop without a fall spell (Options > Routing). Above about 39 yd a fall can kill a low-level character."] },
  { L["Why does the route cut across open ground instead of following the road?"],
    L["That's Roads or shortcuts (Options > Routing): to the left, routes keep to the roads more; to the right, they cut across open ground more."] },
  { L["Why does the route go around a town, a camp or a zone?"],
    L["Avoid the other faction's towns and Avoid zones too high for your level (Options > Routing): routes go around them when there's a reasonable way. A stop inside one is still reached; if the only way passes the other faction's guards, you're asked \"Take it?\" first."] },
  { L["Why doesn't it always know which floor I'm on?"],
    L["The game doesn't tell addons your height, so AzerothGPS follows you from floor to floor as you walk. Targeting or pointing at an NPC near you helps it tell."] },
  { L["Why doesn't the route use a flight path?"],
    L["It only uses flight masters this character knows (Options > Routing > Use flight paths), and it learns which ones from the flight map: open it once at any flight master. Your hearthstone and class teleports have options of their own."] },
  { L["Will it slow my game down?"],
    L["It shouldn't. If you see stutters, Options > Performance has presets for a slower PC, Gentle background work (smaller slices of each frame) and an option to pause routing when it makes the game stutter."] },
  { L["How do I import /way lines or share a route?"],
    L["The map's + button opens Import: paste /way lines such as \"/way Elwynn Forest 43.2 65.1 First Stop\" (or /way #mapID x y). Typing /way in chat works too when TomTom isn't installed. In a group, Share under the directions links your route in party chat."] },
  { L["How do I report a wrong route?"],
    L["Options > Help > Debugging: tick Debug log, do what goes wrong, then click Export Debug Log... and paste it, with what went wrong, on the website's feedback page or in the Discord. The addresses are on the Help page."] },
  { L["It was following my leveling guide, now it isn't?"],
    L["With RestedXP, Zygor, Polestar or Questify loaded, its button on the map's menu (RestedXP Route, Zygor Route and so on) makes each step of the guide your next stop. Picking another route (a stop of your own, a search, Quest Route) or clearing the route turns it off, and the chat says so: click the guide's button again to follow it. A step with no place to go shows no stop until the next one that has, and reaching a stop doesn't finish the step: the guide checks it off."] }, -- (item 68)
}

local function InCombat() return (ns.inCombat or (InCombatLockdown and InCombatLockdown())) and true or false end

function F.Window()
  if F.window then return F.window end
  local f = ns.Window("AzerothGPSFaq", F.W, F.H, L["Frequently asked questions"], ns.POPUP_OVER_STRATA or "DIALOG")
  local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", F.PAD, (f.top or -30) - 6)
  scroll:SetPoint("BOTTOMRIGHT", -F.PAD - 18, 46)
  local child = CreateFrame("Frame", nil, scroll)
  local w = F.W - 2 * F.PAD - 24
  child:SetSize(w, 10)
  scroll:SetScrollChild(child)
  f.scroll, f.child, f.lines = scroll, child, {}
  local y = 0
  for _, it in ipairs(F.ITEMS) do
    local q = child:CreateFontString(nil, "ARTWORK", "GameFontNormal")
    q:SetPoint("TOPLEFT", 0, -y)
    q:SetWidth(w)
    q:SetJustifyH("LEFT")
    q:SetText(it[1])
    y = y + (q:GetStringHeight() or 14) + 4
    local a = child:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    a:SetPoint("TOPLEFT", 0, -y)
    a:SetWidth(w)
    a:SetJustifyH("LEFT")
    a:SetText(it[2])
    y = y + (a:GetStringHeight() or 12) + F.GAP + 4
    f.lines[#f.lines + 1] = { q, a }
  end
  child:SetHeight(math.max(10, y))
  local ok, b = pcall(CreateFrame, "Button", nil, f, "UIPanelButtonTemplate")
  if not ok or not b then b = CreateFrame("Button", nil, f) end
  b:SetHeight(22)
  b:SetText(L["Close"])
  b:SetWidth(math.max(90, (b.GetTextWidth and b:GetTextWidth() or 0) + 24))
  b:SetScript("OnClick", function() f:Hide() end)
  b:SetPoint("BOTTOMRIGHT", -16, 14)
  f.close = b
  F.window = f
  return f
end

function F.Open()
  if InCombat() then
    ns.Print(L["The FAQ can't open in combat. Try again after the fight."])
    return false
  end
  local f = F.Window()
  f:ClearAllPoints()
  f:SetPoint("CENTER", 0, 40)
  f:Show()
  if f.Raise then f:Raise() end
  return true
end
function F.Shown() return (F.window and F.window:IsShown()) and true or false end
