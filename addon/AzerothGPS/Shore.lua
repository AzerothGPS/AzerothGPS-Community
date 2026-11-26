-- The way out of the water (item 116a, Kooki3z 2026-11-26's grid ideas): while the player swims (Nav.Swimming, the
-- game's IsSwimming) with no route, the nearest shore they can walk up onto, by the world grid (WorldGrid.lua): its
-- water's surfaces link to the land's only where the land is within the grid's SHORE_Z of the water's top
-- (worldgrid.py), so a steep bank has no link and is never picked. Pointed at with a wavy line on the map (a swim's
-- look, G.WaveLines; the GPS map and the world map's, one redraw) and the arrow, with its yards ("Swim to the shore").
-- With a route the route's own way out wins: it starts in the water too (WorldGrid's Ends, `swimming`) and goes on
-- from the shore it picks, so nothing of this is shown then. Allow swimming off doesn't matter here: the player is in
-- the water already.
local _, ns = ...
local S = {}
ns.Shore = S
local L = ns.L

local sqrt, max = math.sqrt, math.max

S.EVERY = 0.5 -- seconds between looks while swimming ...
S.MOVE_YD = 4 -- ... when the player has moved this far since the last (else the last one kept)
S.MAX_NODES = 5000 -- water surfaces looked at, at most (8.33 yd cells: about 330 yd round the player)
S.LAND_CELLS = 25 -- a way out goes on to this many land surfaces at least, walked without swimming (not a rock in the
-- water, nor a strip of beach under a cliff)
S.COLOR = { 0.35, 0.75, 1 } -- (the line's: a swim's light blue)
S.LABEL_PX = 8 -- (the label this far over the line's end)

local F_SWIM, F_REACH = 1, 4
local function Bit(v, b) return math.floor(v / b) % 2 == 1 end
local function Dist(x1, y1, x2, y2) return sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) end
local function Id(key, s) return key * 1048576 + s end -- (a surface's own number here: its tile and index)

-- Each surface linked from surface `s` of cell `ci` in tile `key`: fn(nkey, nci, s2, nt) for each.
local function EachLink(WG, c, t, key, ci, s, fn)
  for d = 1, 8 do
    local kk = WG.Link(t, s, d)
    if kk > 0 then
      local nkey, nci = WG.Step(c, key, ci, d)
      local nt = nkey and WG.Tile(c, nkey)
      if nt then fn(nkey, nci, WG.First(nt, nci) + kk - 1, nt) end
    end
  end
end

-- Whether the land surface (key, ci, s) leads on: LAND_CELLS land surfaces reached from it without swimming.
local function LeadsOn(WG, c, key, ci, s, seen)
  local id0 = Id(key, s)
  if seen[id0] ~= nil then return seen[id0] end
  local done, queue, n = { [id0] = true }, { { key, ci, s } }, 1
  local head = 1
  while queue[head] and n < S.LAND_CELLS do
    local q = queue[head]
    head = head + 1
    local t = WG.Tile(c, q[1])
    if t then
      EachLink(WG, c, t, q[1], q[2], q[3], function(nkey, nci, s2, nt)
        local id = Id(nkey, s2)
        if not done[id] and not Bit(WG.Flags(nt, s2), F_SWIM) then
          done[id] = true
          n = n + 1
          queue[#queue + 1] = { nkey, nci, s2 }
        end
      end)
    end
  end
  local ok = n >= S.LAND_CELLS
  seen[id0] = ok
  return ok
end

-- The nearest shore to (x, y) on continent `cont` the player swimming there can walk up onto, by the swim to it:
-- { x, y, z, yd (swum to it) }, or nil (not over the grid's water, no grid, none in reach).
function S.Find(cont, x, y)
  local WG = ns.WorldGrid
  local c = WG and WG.Cont and WG.Cont(cont)
  if not (c and WG.Ends) then return nil end
  local hk, hv = {}, {}
  local g, node = {}, {}
  for _, f in ipairs(WG.Ends(c, x, y, nil, true) or {}) do
    if Bit(f.f or 0, F_SWIM) then
      local id = Id(f.key, f.s)
      local cost = Dist(x, y, f.x, f.y)
      if not g[id] or cost < g[id] then
        g[id], node[id] = cost, { f.key, f.ci, f.s, f.x, f.y, f.z, false }
        WG.HeapPush(hk, hv, cost, id)
      end
    end
  end
  local closed, seen, n = {}, {}, 0
  while hk[1] do
    local cost, id = WG.HeapPop(hk, hv)
    if not closed[id] then
      closed[id] = true
      n = n + 1
      if n > S.MAX_NODES then break end
      local nd = node[id]
      if nd[7] then -- (a shore's land surface: out here if it leads on)
        if LeadsOn(WG, c, nd[1], nd[2], nd[3], seen) then
          return { x = nd[4], y = nd[5], z = nd[6], yd = cost, cont = cont }
        end
      else
        local t = WG.Tile(c, nd[1])
        if t then
          EachLink(WG, c, t, nd[1], nd[2], nd[3], function(nkey, nci, s2, nt)
            local id2 = Id(nkey, s2)
            if closed[id2] then return end
            local fl = WG.Flags(nt, s2)
            local land = not Bit(fl, F_SWIM)
            if land and not Bit(fl, F_REACH) then return end -- (a rock's top or a roof cut off from the land)
            local px, py = WG.Pt(c, nt, s2, nci)
            local c2 = cost + Dist(nd[4], nd[5], px, py)
            if not g[id2] or c2 < g[id2] then
              g[id2], node[id2] = c2, { nkey, nci, s2, px, py, WG.Z(c, nt, s2), land }
              WG.HeapPush(hk, hv, c2, id2)
            end
          end)
        end
      end
    end
  end
  return nil
end

-- The shore to point to now: { x, y, z, yd, cont, px, py, dist (straight from the player) }, or nil: not swimming, a
-- route set (its own way out), not on a continent's open-world grid. Looked for again every EVERY seconds once the
-- player has moved MOVE_YD.
function S.Current()
  local N, Geo, WG = ns.Nav, ns.Geo, ns.WorldGrid
  if not (N and Geo and WG and WG.On and WG.On()) then return nil end
  if #(N.stops or {}) > 0 or N.dest then S.last = nil return nil end -- (a route: its own way out)
  if not (N.Swimming and N.Swimming()) then S.last = nil return nil end
  local px, py, cont = Geo.PlayerWorld()
  if not (px and cont) or Geo.Base(cont) ~= cont then S.last = nil return nil end
  if N.InGridBox and N.InGridBox(cont, px, py) then S.last = nil return nil end -- (a capital's canal: the city's grid)
  local now = GetTime and GetTime() or 0
  local last = S.last
  if not last or last.cont ~= cont or (now - last.at >= S.EVERY and Dist(px, py, last.fx, last.fy) >= S.MOVE_YD) then
    local e = S.Find(cont, px, py) or false
    last = { e = e, at = now, fx = px, fy = py, cont = cont }
    S.last = last
  end
  local e = last.e
  if not e then return nil end
  e.px, e.py, e.dist = px, py, Dist(px, py, e.x, e.y)
  return e
end

-- The words for it: "Swim to the shore  |cffffffff23 yd|r".
function S.Text(e)
  return string.format("%s  |cffffffff%s|r", L["Swim to the shore"], ns.Nav.FormatDistance(e.dist or e.yd))
end

-- Drawn on the map (GPSFrame's redraw, after its route): a wavy line from the player to the shore and its yards there.
-- (cx, cy) the view's middle, `rot` and `s` its turn and scale, `viewCont` its continent.
function S.Draw(cx, cy, rot, s, viewCont)
  local G, Geo = ns.GPS, ns.Geo
  local e = S.Current()
  local layer = G and G.markLayer
  if not (e and e.cont == viewCont and layer and G.AddSeg) then
    if S.label then S.label:Hide() end
    return
  end
  local function Screen(x, y)
    local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
    return Geo.Rotate(dx * s, dy * s, rot)
  end
  local ax, ay = Screen(e.px, e.py)
  local bx, by = Screen(e.x, e.y)
  local total = Dist(ax, ay, bx, by)
  local col = S.COLOR
  local function Line(x1, y1, x2, y2) G.AddSeg(x1, y1, x2, y2, col, 2, 0.9, true) end
  if G.WaveLines and total > 1 then
    G.waveLeft = max(G.waveLeft or 0, G.SWIM_WAVE_MAX or 0) -- (no route drawn: its budget is this line's)
    G.WaveLines(ax, ay, bx, by, 2, (G.SWIM_WAVE_PX or 12) + 4, 0, total, Line)
  else
    Line(ax, ay, bx, by)
  end
  if not S.label then
    S.label = layer:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    S.label:SetTextColor(col[1], col[2], col[3])
  end
  local half = layer:GetWidth() / 2
  if math.abs(bx) > half or math.abs(by) > half then
    S.label:Hide()
    return
  end
  S.label:ClearAllPoints()
  S.label:SetPoint("BOTTOM", layer, "CENTER", bx, by + S.LABEL_PX)
  S.label:SetText(ns.Format(L["Shore %s"], ns.Nav.FormatDistance(e.dist)))
  S.label:Show()
end
