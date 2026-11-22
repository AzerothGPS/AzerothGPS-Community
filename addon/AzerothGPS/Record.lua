-- The player's road fixes: roads drawn on the map where the road data misses one, and
-- stretches erased where it has one that isn't there (the road tools: "Draw a road" and
-- "Erase a road" on the map's buttons, or /agps draw). Saved in ns.db.tracks: routes use
-- them at once (Router.WithTracks), `agps roads` takes them into the road data, and they're
-- kept for sharing if the player opted in (Feedback). Once the addon's road data has one
-- (ns.RoadTracksIn, by its time), it moves to an archive (R.Archive): kept for good, never used.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local R = {}
ns.Record = R

local function Tracks()
  ns.db.tracks = ns.db.tracks or {}
  return ns.db.tracks
end
R.Tracks = Tracks

-- The fixes the road data has, kept for good (asked 2026-10-06, keep data forever): ns.db.tracksShipped, each as it
-- was with its points packed (`pk`, `zk`: ns.PackNumbers), never used by routes (the data's copy is) nor by Undo.
function R.Archive()
  ns.db.tracksShipped = ns.db.tracksShipped or {}
  return ns.db.tracksShipped
end
-- A copy of track `t` with its points packed, as the archive keeps it (Core.lua's ns.PackNumbers' format).
local function Pack(list)
  if ns.PackNumbers then return ns.PackNumbers(list) end
  local out = {}
  for i, v in ipairs(list) do out[i] = v == false and "-" or tostring(v) end
  return table.concat(out, " ")
end
function R.Packed(t)
  local c = {}
  for k, v in pairs(t) do c[k] = v end
  if type(c.pts) == "table" then c.pk, c.pts = Pack(c.pts), nil end
  if type(c.zs) == "table" then c.zk, c.zs = Pack(c.zs), nil end
  return c
end

-- At login: the fixes the road data now has go to the archive (R.Archive), out of the list routes and Undo go by.
-- (They were deleted before: a stroke set aside on purpose, or drawn in the same second as a shipped one, was lost.)
function R.Prune()
  local shipped = ns.RoadTracksIn
  if not shipped or not ns.db then return end
  local n = 0
  local archive = R.Archive()
  local have = {}
  for _, a in ipairs(archive) do have[tostring(a.time) .. ":" .. tostring(a.continent) .. ":" .. tostring(a.pk)] = true end
  local function prune(list, count)
    local moved = {}
    for i = #(list or {}), 1, -1 do
      if list[i].time and shipped[list[i].time] then
        table.insert(moved, 1, table.remove(list, i))
        if count then n = n + 1 end
      end
    end
    for _, t in ipairs(moved) do
      local c = R.Packed(t)
      local key = tostring(c.time) .. ":" .. tostring(c.continent) .. ":" .. tostring(c.pk)
      if not have[key] then -- (an older version's second copy of one: once)
        have[key] = true
        archive[#archive + 1] = c
      end
    end
  end
  prune(ns.db.tracks, true)
  -- (strokes saved on a city's level though drawn elsewhere, looking at another zone from down
  -- in the city: back on the continent)
  local P = ns.Passability
  for _, t in ipairs(ns.db.tracks or {}) do
    local lvl = ns.CityLevels and ns.CityLevels[t.continent]
    if lvl and P and P.InGrid and t.pts and t.pts[1] and not P.InGrid(t.continent, t.pts[1], t.pts[2]) then
      t.continent = lvl.base
    end
  end
  -- (and the copies kept for sharing: the data has them, nothing to share)
  prune(ns.db.feedback and ns.db.feedback.roads)
  if n > 0 then ns.Print(L["%d of your drawn roads and walls are in the map data now (kept in your saved data)"]:format(n)) end
end

-- Tracks changed: the walls at once, and the road network (it includes them) and the route rebuilt, after every
-- edit, the road and wall tools on or not (asked 2026-11-11: "make the route update immediately after a road or wall
-- is drawn, not after the tool is turned off"; until then the network waited for the tools to be turned off). The
-- network is rebuilt in the background; the map shows the edits over the roads as they were meanwhile (GPSFrame's
-- LayoutRoads).
function R.Changed()
  if ns.Passability and ns.Passability.RefreshWalls then ns.Passability.RefreshWalls() end
  if ns.GPS and ns.GPS.ClearEdges then ns.GPS.ClearEdges() end
  R.Apply()
end

-- The edits into the road network and the route.
function R.Apply()
  R.pending = nil
  if ns.Router and ns.Router.Reset then ns.Router.Reset() end
  if ns.Nav and ns.Nav.Invalidate then ns.Nav.Invalidate(true, true) end
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end

-- The tracks made this session (since the last /reload or login), the only ones Undo takes back (asked 2026-11-17:
-- "I accidently hit undo too many times and erased the path fix to stormwind bank, Undo on recorder should only be for
-- the current session reloaded"). By the track itself, never saved: a /reload starts it empty.
R.thisSession = setmetatable({}, { __mode = "k" })

-- A drawn road (op "add") or erased one ("remove"): saved; its number.
function R.Save(track)
  -- (the tutorial's practice, Tutorial.lua: R.practice = { list = {} } while its road section runs. A stroke or a
  -- recorded walk goes on that list, in memory only: never the saved tracks, the shared roads or the unsaved count)
  if R.practice then
    local list = R.practice.list
    list[#list + 1] = track
    if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    return #list
  end
  local t = Tracks()
  -- (a time of its own: it's the track's key)
  local used = {}
  for _, o in ipairs(t) do if o.time then used[o.time] = true end end
  while used[track.time] or (ns.RoadTracksIn and ns.RoadTracksIn[track.time]) do track.time = track.time + 1 end
  t[#t + 1] = track
  R.thisSession[track] = true
  if ns.Feedback then ns.Feedback.RoadRecorded(track) end
  if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(track.time), "add") end
  R.Changed()
  return #t
end

-- Roads and walls someone shared, taken into the player's own (the dev tools' import of a Copy Map Data
-- text): kept with their times (their keys: one here already, or in the data, is left out), so routes use
-- them at once, Undo takes them back, and the road watcher puts them into the data as it does drawn ones.
-- `imported` (a player's import in the Import and Share window, asked 2026-10-06): marked `imported`, not `shared`,
-- and the road watcher leaves them out: the player's own data, never the addon's.
-- Each { op = "add"|"remove"|"wall"|"unwall", continent, time, pts, area, z, indoors, down, zs (a height per point),
-- stair, gz (the ground's heights from the map's data) }. How many added, how many were here already or in the data.
function R.AddShared(list, imported)
  local t = Tracks()
  local have = {}
  for _, o in ipairs(t) do
    if o.time then have[o.time] = true end
  end
  local n, had = 0, 0
  for _, s in ipairs(list or {}) do
    if s.time and not have[s.time] and not (ns.RoadTracksIn and ns.RoadTracksIn[s.time]) and s.pts and #s.pts >= 4 then
      t[#t + 1] = { op = s.op, drawn = true, shared = not imported or nil, imported = imported or nil,
        continent = s.continent, zone = s.zone or (imported and "imported" or "shared"), time = s.time, pts = s.pts,
        area = s.area or nil, z = s.z, indoors = s.indoors, down = s.down,
        zs = type(s.zs) == "table" and #s.zs == #s.pts / 2 and s.zs or nil, stair = s.stair or nil,
        gz = type(s.gz) == "table" and #s.gz == #s.pts / 2 and s.gz or nil }
      R.thisSession[t[#t]] = true
      have[s.time] = true
      n = n + 1
      -- (a player's import: one unsaved change for all of it, the caller's)
      if ns.MarkUnsaved and not imported then ns.MarkUnsaved("track:" .. tostring(s.time), "add") end
    elseif s.time then
      had = had + 1
    end
  end
  if n > 0 then R.Changed() end
  return n, had
end

function R.Delete(i)
  local t = Tracks()
  if not (i and t[i]) then
    ns.Print(string.format(L["no drawn road #%s"], tostring(i)))
    return
  end
  local tr = table.remove(t, i)
  if ns.Feedback and ns.Feedback.RoadRemoved then ns.Feedback.RoadRemoved(tr) end
  local what = { remove = L["erased road"], wall = L["wall"], unwall = L["erased wall"] }
  ns.Print(L["took back #%d (%s)"]:format(i, what[tr.op] or L["drawn road"]))
  if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(tr.time), "remove") end
  R.Changed()
end

-- The last one taken back: roads and walls (and their erasings) are one list, in the order drawn, so
-- Undo takes back whichever came last.
function R.Undo()
  if R.practice then -- (the tutorial's practice: its own last stroke, never a saved one)
    table.remove(R.practice.list)
    if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    return
  end
  if R.UndoRestore() then return end -- (a restore the last change: put back)
  local t = Tracks()
  local n = #t
  if n == 0 then
    ns.Print(L["no drawn road or wall to take back"])
    return
  end
  if not R.thisSession[t[n]] then -- (one from before this session: kept, R.thisSession)
    ns.Print(L["Undo takes back only what you changed since your last /reload or login. Older roads and walls stay: erase them with the road or wall tools instead."])
    return
  end
  R.Delete(n)
end

function R.List()
  local t = Tracks()
  if #t == 0 then ns.Print(L["no drawn roads waiting for the road data"]) end
  for i, tr in ipairs(t) do
    local what = { remove = L["erased road"], wall = L["wall"], unwall = L["erased wall"], add = L["road"] }
    ns.Print(Format(L["#%d %s %s, %d points, %s"], i, what[tr.op] or tr.op, tr.zone or "?",
      #tr.pts / 2, date("%Y-%m-%d %H:%M", tr.time)))
  end
end

-- Editing a road afterwards (asked 2026-11-18 for 1.3.10, issue #640: "Couldn't be provide tooling to change the drawn
-- data line by specifying the information afterwards? ... pick the floor level that would be on"). The road tools' Edit
-- Road picks a drawn or recorded road (R.TrackAt) and sets what it is: its floor or height, its kind (Router.TRACK_KINDS:
-- ground, floor, bridge, stairs, lift) and a stairs stretch on part of it. Saved as a new track (R.EditTrack) with the
-- same points and its `zs`, `kind`, `stairs`, that `replaces` the one edited (its time; `rpart`, a piece of a recorded
-- walk or an edit the data has): routes leave the old one out at once (Router.ExpandTracks), Undo takes the edit back,
-- and the road watcher ships it in the old one's place.
R.EDIT_PICK_YD = 12 -- yards: a click this near a road picks it

-- The roads that can be edited on `cont`: the player's own (drawn, recorded, those the data has from them: the archive)
-- and the data's with their heights (ns.FloorTracks), less those an edit replaced. Each { t, shipped, archived }.
function R.Editable(cont)
  local Rt = ns.Router
  local all, out = {}, {}
  local shipped = ns.RoadTracksIn or {}
  local function add(t, how)
    if t and t.continent == cont and (t.op == nil or t.op == "add") then all[#all + 1] = { t = t, how = how } end
  end
  for _, t in ipairs(Tracks()) do
    if not shipped[t.time or -1] then add(t, "own") end
  end
  for _, a in ipairs(R.Archive()) do
    if a.continent == cont and (a.op == nil or a.op == "add") and type(a.pk) == "string" and ns.UnpackNumbers then
      add({ op = "add", continent = a.continent, time = a.time, zone = a.zone, recorded = a.recorded,
        pts = ns.UnpackNumbers(a.pk), zs = type(a.zk) == "string" and ns.UnpackNumbers(a.zk) or nil, stair = a.stair,
        kind = a.kind }, "archived")
    end
  end
  for _, t in ipairs(ns.FloorTracks and ns.FloorTracks[cont] or {}) do
    if t.op == nil or t.op == "add" then
      local c = {}
      for k, v in pairs(t) do c[k] = v end
      c.continent = cont
      add(c, "shipped")
    end
  end
  local list = {}
  for _, a in ipairs(all) do list[#list + 1] = a.t end
  local gone = Rt and Rt.ReplacedSet and Rt.ReplacedSet(list) or {}
  local shippedTimes = {}
  for _, a in ipairs(all) do if a.how == "shipped" then shippedTimes[a.t.time or -1] = true end end
  for _, a in ipairs(all) do
    local t = a.t
    -- (an archived one the data ships with its heights: the data's copy, its pieces, not this one)
    local dup = a.how == "archived" and shippedTimes[t.time or -1]
    if not dup and not (Rt and Rt.Replaced and Rt.Replaced(gone, t)) and t.pts and #t.pts >= 4 then
      out[#out + 1] = { t = t, shipped = a.how == "shipped", archived = a.how == "archived" }
    end
  end
  return out
end

-- The editable road nearest (x, y) on `cont` within `reach` (EDIT_PICK_YD): { t, shipped, archived, d, i (its point
-- nearest), part }, or nil.
-- (never a road erased there since: gone from the map and the routes, it was picked all the same and Delete took out
-- that one, not the road shown; Kooki3z 2026-11-20, "cant delete stairs here, also seems like I can select phantom
-- roads that aren't shown with the road tool")
function R.TrackAt(cont, x, y, reach)
  reach = reach or R.EDIT_PICK_YD
  local best
  local G = ns.GPS
  local erases = G and G.PendingErases and G.PendingErases(cont)
  if erases and #erases == 0 then erases = nil end
  for _, c in ipairs(R.Editable(cont)) do
    local p = c.t.pts
    for k = 1, #p - 3, 2 do
      local ax, ay, bx, by = p[k], p[k + 1], p[k + 2], p[k + 3]
      local vx, vy = bx - ax, by - ay
      local L2 = vx * vx + vy * vy
      local f = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
      local qx, qy = ax + vx * f, ay + vy * f
      local d = math.sqrt((qx - x) ^ 2 + (qy - y) ^ 2)
      if d <= reach and (not best or d < best.d)
          and not (erases and G.UnderErase(erases, qx, qy, c.t.time)) then
        best = { t = c.t, shipped = c.shipped, archived = c.archived, d = d, i = f < 0.5 and (k + 1) / 2 or (k + 3) / 2,
          part = c.t.part }
      end
    end
  end
  return best
end

-- The point of track `t` nearest (x, y): its number (1 ..).
function R.NearestPoint(t, x, y)
  local best, bi = math.huge, 1
  for k = 1, #t.pts - 1, 2 do
    local d = (t.pts[k] - x) ^ 2 + (t.pts[k + 1] - y) ^ 2
    if d < best then best, bi = d, (k + 1) / 2 end
  end
  return bi
end

-- The heights for an edit of `n` points `pts`: `kind` (ground: none unless `z` given; stairs: from `z1` at the first
-- point to `z2` at the last; else `z` at every point, or the track's own `old` zs when no `z`), a stairs stretch
-- `stairs` = { i, j, z1, z2 } rising evenly by the yards along from i to j, the points before at z1, after at z2 (or
-- `base`'s there, a height or false per point: Set Heights keeps the rest of the road's own).
function R.EditHeights(pts, kind, z, old, stairs, z1, z2, base)
  local n = #pts / 2
  local Rt = ns.Router
  local function ramp(a, b, za, zb, out)
    local sub = {}
    for k = a, b do sub[#sub + 1], sub[#sub + 2] = pts[2 * k - 1], pts[2 * k] end
    local hs = Rt.RampHeights(sub, za, zb)
    for k = a, b do out[k] = hs[k - a + 1] end
  end
  if stairs then
    local i, j, a, b = stairs[1], stairs[2], tonumber(stairs[3]), tonumber(stairs[4])
    if not (i and j and a and b and i >= 1 and j <= n and j > i) then return nil end
    local out = {}
    for k = 1, n do out[k] = (type(base) == "table" and tonumber(base[k])) or (k < i and a or b) end
    ramp(i, j, a, b, out)
    return out
  end
  if kind == "stairs" or kind == "lift" then
    z1, z2 = tonumber(z1), tonumber(z2)
    if not (z1 and z2) then return nil end
    local out = {}
    ramp(1, n, z1, z2, out)
    return out
  end
  z = tonumber(z)
  if z then
    local out = {}
    for k = 1, n do out[k] = z end
    return out
  end
  if kind == "ground" then return nil end
  if type(old) == "table" and #old == n then
    local out = {}
    for k = 1, n do out[k] = old[k] end
    return out
  end
  return nil
end

-- Edit Wall (the wall tools, 1.3.10, issue #685): a wall the player drew (not in the data yet) made a cliff on a
-- section of it, with the ground's height on each side (Passability.CliffSection: open where they're level, walked down
-- only where the drop is safe, else a wall both ways), or a plain wall again. Saved as a new wall that `replaces` the
-- old one (its time): Undo takes it back, and the road watcher ships it in its place.
R.WALL_PICK_YD = 12
-- The sides filled in (Record.WallSides): the ground read along the perpendicular on each side, every CLIFF_SIDE_STEP
-- yards from CLIFF_SIDE_NEAR out to CLIFF_SIDE_REACH. (Read only next to the wall, CLIFF_SIDE_YD off, both sides came
-- out nearly the same: the map's grid is ~16.7 yd a cell and bilinear, so a ledge is a smooth slope there; Kooki3z
-- 2026-11-20, a Stonetalon ledge whose top is ~70-75 and its foot ~22-25 filled in "Left 70.0, Right 69.7", made a
-- level, open cliff that blocked nothing. The grid there takes ~60 yd from the top (~73) to the foot (~25), with a
-- shelf and bumps of a few yards on the way down.)
R.CLIFF_SIDE_YD = 5 -- (the ground's height this far either side, when the ground's level across it)
R.CLIFF_SIDE_NEAR, R.CLIFF_SIDE_STEP, R.CLIFF_SIDE_REACH = 3, 2, 60
R.CLIFF_SIDE_TURN = 5 -- yards: past the top (the foot), ground this far below (above) it again ends that side's read
-- (the next valley or rise: not this ledge's; a bump or a shelf on the way down less than this does not)
-- The player's own walls on `cont` (not in the data yet), less those an edit replaced and those an erase took out since:
-- the ones the map draws and the routes use (Passability.WallLines). (Kooki3z 2026-11-20: a wall deleted with an erase
-- stayed pickable, though gone from the map and the routes, so the wall shown next to it could never be clicked and
-- deleted: every click picked the erased one again.)
function R.EditableWalls(cont)
  local shipped = ns.RoadTracksIn or {}
  local P = ns.Passability
  local out = {}
  if P and P.WallLines and P.WallTrack then
    for _, w in ipairs(P.WallLines(cont)) do
      local t = P.WallTrack(w)
      if t and t.op == "wall" and t.pts and #t.pts >= 4 and not shipped[t.time or -1] then out[#out + 1] = t end
    end
    return out
  end
  local gone = {}
  for _, t in ipairs(Tracks()) do
    if t.op == "wall" and t.replaces then gone[t.replaces] = true end
  end
  for _, t in ipairs(Tracks()) do
    if t.op == "wall" and t.continent == cont and t.pts and #t.pts >= 4 and not shipped[t.time or -1]
        and not gone[t.time or -1] then out[#out + 1] = t end
  end
  return out
end
-- The editable wall nearest (x, y) on `cont` within `reach`: { t, d, i (the section's first point) }, or nil.
function R.WallAt(cont, x, y, reach)
  reach = reach or R.WALL_PICK_YD
  local best
  for _, t in ipairs(R.EditableWalls(cont)) do
    local p = t.pts
    for k = 1, #p - 3, 2 do
      local ax, ay, bx, by = p[k], p[k + 1], p[k + 2], p[k + 3]
      local vx, vy = bx - ax, by - ay
      local L2 = vx * vx + vy * vy
      local f = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
      local d = math.sqrt((ax + vx * f - x) ^ 2 + (ay + vy * f - y) ^ 2)
      if d <= reach and (not best or d < best.d) then best = { t = t, d = d, i = (k + 1) / 2 } end
    end
  end
  return best
end
-- The ground's height on each side of wall `t`'s points i .. j (its left and its right as drawn; ns.Ground): zl, zr
-- (either nil with no ground data there). For each section, at its middle, the ground is read out along the
-- perpendicular on both sides (R.CLIFF_SIDE_NEAR .. R.CLIFF_SIDE_REACH); the higher side's height is its top (the
-- highest it reaches before the ground falls away again: a ledge's plateau, not the next valley), the lower side's
-- its foot (the lowest before it rises again), so the sides are the ledge's top and its foot, not two heights from
-- its smoothed edge (Kooki3z 2026-11-20). Level ground (the two sides' reads alike): the heights R.CLIFF_SIDE_YD off.
-- The sections' values averaged.
function R.WallSides(level, t, i, j)
  local GD = ns.Ground
  if not GD then return nil, nil end
  local sl, nl, sr, nr = 0, 0, 0, 0
  local p = t.pts
  -- (side `sg` of the section at (mx, my), its left unit (ux, uy): the heights out along it, nearest first)
  local function profile(mx, my, ux, uy, sg)
    local out = {}
    local d = R.CLIFF_SIDE_NEAR
    while d <= R.CLIFF_SIDE_REACH do
      local h = GD.At(level, mx + ux * d * sg, my + uy * d * sg)
      if not h then break end -- (off the grid, over a hole: as far as it reads)
      out[#out + 1] = h
      d = d + R.CLIFF_SIDE_STEP
    end
    return out
  end
  local function top(hs) -- (the highest before the ground falls CLIFF_SIDE_TURN below it again)
    local best = hs[1]
    for k = 2, #hs do
      if hs[k] > best then best = hs[k] elseif hs[k] < best - R.CLIFF_SIDE_TURN then break end
    end
    return best
  end
  local function foot(hs) -- (the lowest before the ground rises CLIFF_SIDE_TURN over it again)
    local best = hs[1]
    for k = 2, #hs do
      if hs[k] < best then best = hs[k] elseif hs[k] > best + R.CLIFF_SIDE_TURN then break end
    end
    return best
  end
  local function mean(hs)
    local sum = 0
    for k = 1, #hs do sum = sum + hs[k] end
    return sum / #hs
  end
  for k = i, math.max(i, j - 1) do
    local ax, ay, bx, by = p[2 * k - 1], p[2 * k], p[2 * k + 1], p[2 * k + 2]
    if bx then
      local ex, ey = bx - ax, by - ay
      local L = math.sqrt(ex * ex + ey * ey)
      if L > 0 then
        local mx, my, ux, uy = (ax + bx) / 2, (ay + by) / 2, -ey / L, ex / L
        local pl, pr = profile(mx, my, ux, uy, 1), profile(mx, my, ux, uy, -1)
        local hl, hr
        if #pl > 0 and #pr > 0 then
          local ml, mr = mean(pl), mean(pr)
          if ml >= mr then hl, hr = top(pl), foot(pr) else hl, hr = foot(pl), top(pr) end
          -- (level across it, the top and foot within a step: the ground right by it, as it is)
          if math.abs(hl - hr) <= (ns.Passability and ns.Passability.CLIFF_STEP or 2) then hl, hr = nil, nil end
        end
        local d = R.CLIFF_SIDE_YD
        hl = hl or GD.At(level, mx + ux * d, my + uy * d)
        hr = hr or GD.At(level, mx - ux * d, my - uy * d)
        if hl then sl, nl = sl + hl, nl + 1 end
        if hr then sr, nr = sr + hr, nr + 1 end
      end
    end
  end
  local function r1(v) return math.floor(v * 10 + 0.5) / 10 end
  return nl > 0 and r1(sl / nl) or nil, nr > 0 and r1(sr / nr) or nil
end
-- Save an edit of the wall picked (`sel`, R.WallAt's): { kind ("cliff" or "wall"), i, j (the section's points), zl, zr
-- (a cliff's sides) }. The rest keeps its own sides. Its number in the drawn roads, or nil and why.
function R.EditWall(sel, edit)
  local t = sel and sel.t
  if not (t and t.pts and #t.pts >= 4 and edit) then return nil, "nothing" end
  local n = #t.pts / 2
  local i, j = tonumber(edit.i) or 1, tonumber(edit.j) or n
  if j < i then i, j = j, i end
  i, j = math.max(1, i), math.min(n, j)
  if i == j then return nil, "section" end
  local zl, zr = tonumber(edit.zl), tonumber(edit.zr)
  if edit.kind == "cliff" and not (zl and zr) then return nil, "height" end
  local cl, cr = {}, {}
  for k = 1, n do
    cl[k] = type(t.cl) == "table" and tonumber(t.cl[k]) or false
    cr[k] = type(t.cr) == "table" and tonumber(t.cr[k]) or false
  end
  for k = i, j do
    if edit.kind == "cliff" then cl[k], cr[k] = zl, zr else cl[k], cr[k] = false, false end
  end
  local any = false
  for k = 1, n do any = any or (cl[k] and cr[k]) and true or false end
  local pts = {}
  for k = 1, #t.pts do pts[k] = t.pts[k] end
  local w = { op = "wall", drawn = true, edit = true, continent = t.continent, zone = t.zone or "?", time = time(),
    pts = pts, z = t.z, indoors = t.indoors, down = t.down, replaces = t.time,
    kind = any and "cliff" or nil, cl = any and cl or nil, cr = any and cr or nil }
  return R.Save(w)
end

-- Set Heights (Edit Road, 1.3.10, issue #685): the heights the rest of road `t` keeps around a stretch, a height or
-- false per point: its own (`zs`), else the ground's it was drawn on (`gz`), else the map's grid there (ns.Ground).
function R.StretchBase(t, level)
  local n = #t.pts / 2
  local out = {}
  local GD = ns.Ground
  for k = 1, n do
    local own = type(t.zs) == "table" and tonumber(t.zs[k])
    local gz = type(t.gz) == "table" and tonumber(t.gz[k])
    out[k] = own or gz or (GD and level and GD.PointHeight(level, t.pts[2 * k - 1], t.pts[2 * k])) or false
  end
  return out
end

-- Save an edit of the road picked (`sel`, R.TrackAt's): { kind, z (its height), z1, z2 (a stairs' or lift's foot and
-- top), stairs = { i, j, z1, z2 } (a stairs stretch), base (the rest's heights, R.StretchBase), skind ("ramp": the
-- stretch a ramp, not stairs), split (false: the stretch's heights only, no piece of its own) }. Its number in the drawn
-- roads, or nil and why.
function R.EditTrack(sel, edit)
  local t = sel and sel.t
  if not (t and t.pts and #t.pts >= 4 and edit) then return nil, "nothing" end
  local kind = edit.kind
  local known = false
  for _, k in ipairs(ns.Router and ns.Router.TRACK_KINDS or {}) do known = known or k == kind end
  if not known then return nil, "kind" end
  local function r1(v) return math.floor(v * 10 + 0.5) / 10 end
  -- (`reverse`: its points the other way round: a lift with no heights turned round, Flip Lift)
  local src, old = t.pts, t.zs
  if edit.reverse then
    src, old = {}, type(t.zs) == "table" and {} or nil
    local n = #t.pts / 2
    for k = n, 1, -1 do
      src[#src + 1], src[#src + 2] = t.pts[2 * k - 1], t.pts[2 * k]
      if old then old[#old + 1] = t.zs[k] end
    end
  end
  local zs = R.EditHeights(src, kind, edit.z, old, edit.stairs, edit.z1, edit.z2, edit.base)
  -- (a bridge: raised with or without; a lift: a lift ride with or without, its way round by its points)
  if not zs and kind ~= "ground" and kind ~= "bridge" and kind ~= "lift" then return nil, "height" end
  if zs then for k = 1, #zs do zs[k] = r1(zs[k]) end end
  local pts = {}
  for k = 1, #src do pts[k] = src[k] end
  local track = { op = "add", drawn = true, edit = true, continent = t.continent, zone = t.zone or "?", time = time(),
    pts = pts, zs = zs, z = zs and zs[1] or nil, kind = kind, replaces = t.time,
    rpart = sel.shipped and t.part or nil, -- (a piece of a walk or an edit the data has: that piece; else all of it)
    stair = kind == "stairs" and zs ~= nil or nil,
    stairs = edit.split ~= false and edit.stairs and { edit.stairs[1], edit.stairs[2] } or nil,
    skind = edit.split ~= false and edit.stairs and edit.skind == "ramp" and "ramp" or nil }
  return R.Save(track)
end

-- Delete (asked 2026-11-19 for 1.3.10): Edit Road's and Edit Wall's Delete button takes out exactly the stretch the
-- window shows highlighted. The player's own road or wall (on the drawn list, not an edit of another) comes off the
-- list (R.TakeOut; a wall's section: the rest saved as its own walls); the map's own, or an edit, gets an erase saved
-- as Shift + right-drag saves one ("remove" along the road, "unwall" at the wall), so it's kept, shared and imported
-- like any erase, and Undo puts it back. An erase's ends stay R.DELETE_TRIM_YD off the roads it meets (the cut's reach
-- would take their ends too: the stub left goes, Router.TRACK_STUB); a wall's is a yard at its point furthest from the
-- other walls (an erase takes out every wall it comes near, whole).
R.DELETE_TRIM_YD = 13 -- (Router.TRACK_REMOVE_YD and a yard)
R.DELETE_ALONG_YD = 3 -- (a road with every point this near the stretch is a piece of it, not another road)

-- Track number `i` taken off the drawn list (and the shared copies): routes leave it out at once. The track.
function R.TakeOut(i)
  local tr = table.remove(Tracks(), i)
  if not tr then return nil end
  if ns.Feedback and ns.Feedback.RoadRemoved then ns.Feedback.RoadRemoved(tr) end
  if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(tr.time), "remove") end
  R.Changed()
  return tr
end

-- How far (x, y) is from the line `pts` (flat x, y list; index `first` on, a graph road's 5).
function R.LineDist(pts, x, y, first)
  first = first or 1
  if #pts - first < 3 then return math.sqrt((pts[first] - x) ^ 2 + (pts[first + 1] - y) ^ 2) end
  local best = math.huge
  for k = first, #pts - 3, 2 do
    local ax, ay, bx, by = pts[k], pts[k + 1], pts[k + 2], pts[k + 3]
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local f = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
    local d = math.sqrt((ax + vx * f - x) ^ 2 + (ay + vy * f - y) ^ 2)
    if d < best then best = d end
  end
  return best
end

-- Whether a road other than the stretch `pts` (one not along it) comes within an erase's reach of (x, y) on `level`:
-- the roads as routed now (only when they're built: Router.DebugGraph).
function R.OtherRoadNear(level, x, y, pts)
  local Rt = ns.Router
  local g = Rt and Rt.DebugGraph and Rt.DebugGraph(level)
  if not (g and Rt.NearestEdges) then return false end
  local reach = (Rt.TRACK_REMOVE_YD or 12) + 1
  for _, c in ipairs(Rt.NearestEdges(level, x, y)) do
    local ed = g.e[c.edge]
    if ed and c.dist and c.dist <= reach then
      for k = 5, #ed - 1, 2 do
        if R.LineDist(pts, ed[k], ed[k + 1]) > R.DELETE_ALONG_YD then return true end
      end
    end
  end
  return false
end

-- `pts` (and its heights `zs`, or nil) less its first `yd` yards (straight from its start): new lists, or nil when
-- all of it is that near.
local function TrimStart(pts, zs, yd)
  local x0, y0 = pts[1], pts[2]
  local n = #pts / 2
  for k = 2, n do
    local bx, by = pts[2 * k - 1], pts[2 * k]
    if (bx - x0) ^ 2 + (by - y0) ^ 2 >= yd * yd then
      local ax, ay = pts[2 * k - 3], pts[2 * k - 2]
      local lo, hi = 0, 1
      for _ = 1, 24 do
        local m = (lo + hi) / 2
        if (ax + (bx - ax) * m - x0) ^ 2 + (ay + (by - ay) * m - y0) ^ 2 >= yd * yd then hi = m else lo = m end
      end
      local op = { ax + (bx - ax) * hi, ay + (by - ay) * hi }
      local oz = zs and { zs[k - 1] + (zs[k] - zs[k - 1]) * hi } or nil
      for j = k, n do
        op[#op + 1], op[#op + 2] = pts[2 * j - 1], pts[2 * j]
        if oz then oz[#oz + 1] = zs[j] end
      end
      return op, oz
    end
  end
  return nil
end
local function Reversed(pts, zs)
  local op, oz = {}, zs and {} or nil
  local n = #pts / 2
  for k = n, 1, -1 do
    op[#op + 1], op[#op + 2] = pts[2 * k - 1], pts[2 * k]
    if oz then oz[#oz + 1] = zs[k] end
  end
  return op, oz
end
local function Length(pts)
  local len = 0
  for k = 1, #pts - 3, 2 do len = len + math.sqrt((pts[k + 2] - pts[k]) ^ 2 + (pts[k + 3] - pts[k + 1]) ^ 2) end
  return len
end
-- The spot `d` yards along `pts`: x, y and its height (nil with no `zs`).
local function Along(pts, zs, d)
  for k = 1, #pts - 3, 2 do
    local L = math.sqrt((pts[k + 2] - pts[k]) ^ 2 + (pts[k + 3] - pts[k + 1]) ^ 2)
    if d <= L or k + 3 >= #pts then
      local f = L > 0 and math.max(0, math.min(1, d / L)) or 0
      local i = (k + 1) / 2
      return pts[k] + (pts[k + 2] - pts[k]) * f, pts[k + 1] + (pts[k + 3] - pts[k + 1]) * f,
        zs and zs[i] + (zs[i + 1] - zs[i]) * f or nil
    end
    d = d - L
  end
  return pts[1], pts[2], zs and zs[1] or nil
end

-- The erase that takes out road `pts` (heights `zs`, or nil) on `level` and no road it meets: its points and heights.
function R.DeleteStroke(level, pts, zs)
  local yd = R.DELETE_TRIM_YD
  local out, oz = pts, zs
  if R.OtherRoadNear(level, pts[1], pts[2], pts) then out, oz = TrimStart(out, oz, yd) end
  if out and R.OtherRoadNear(level, pts[#pts - 1], pts[#pts], pts) then
    local rp, rz = Reversed(out, oz)
    rp, rz = TrimStart(rp, rz, yd)
    if rp then out, oz = Reversed(rp, rz) else out = nil end
  end
  if not out or Length(out) < 1 then -- (shorter than its two ends' room: its middle)
    local half = Length(pts) / 2
    local ax, ay, az = Along(pts, zs, math.max(0, half - 0.5))
    local bx, by, bz = Along(pts, zs, half + 0.5)
    out, oz = { ax, ay, bx, by }, zs and { az, bz } or nil
  end
  local function r1(v) return math.floor(v * 10 + 0.5) / 10 end
  for k = 1, #out do out[k] = r1(out[k]) end
  if oz then for k = 1, #oz do oz[k] = r1(oz[k]) end end
  return out, oz
end

-- Delete the road picked (`sel`, R.TrackAt's or the map's own road shown read-only, `sel.t.zs` its heights when it has
-- them) on `level`. `floor`: { z, indoors, down, zone } for an erase with no heights (the floor being edited). "own"
-- (taken off the list) or the erase's number; nil when there's nothing to delete.
function R.DeleteRoad(level, sel, floor)
  local t = sel and sel.t
  if not (level and t and type(t.pts) == "table" and #t.pts >= 4) then return nil end
  floor = floor or {}
  if not (sel.readOnly or sel.shipped or sel.archived or t.replaces) then
    for i, o in ipairs(Tracks()) do
      if o == t then
        R.TakeOut(i)
        return "own"
      end
    end
  end
  local zs = type(t.zs) == "table" and #t.zs == #t.pts / 2 and t.zs or nil
  for k = 1, zs and #zs or 0 do
    if type(zs[k]) ~= "number" then zs = nil break end
  end
  local pts, hs = R.DeleteStroke(level, t.pts, zs)
  return R.Save({ op = "remove", drawn = true, continent = level, zone = floor.zone or t.zone or "?", time = time(),
    pts = pts, zs = hs, z = hs and hs[1] or floor.z, indoors = not hs and floor.indoors or nil,
    down = not hs and floor.down or nil })
end

-- Wall `t` (an edit: it `replaces` another) and the walls it replaced, back to the one first drawn, when every one of
-- them is the player's own on the drawn list (not in the data) and no other wall replaces any of them: taken out
-- together they leave nothing behind. A list, `t` first; nil otherwise (the data has one of them, or another wall
-- would lose the one it replaced).
function R.OwnWallChain(t)
  local shipped = ns.RoadTracksIn or {}
  if shipped[t.time or -1] then return nil end
  local list, cur, seen = { t }, t, { [t] = true }
  while cur.replaces do
    local found
    for _, o in ipairs(Tracks()) do
      if o.op == "wall" and o.time == cur.replaces and o ~= cur then
        if found then return nil end -- (two walls of that time: not sure which)
        found = o
      end
    end
    if not found or seen[found] or shipped[found.time or -1] then return nil end
    seen[found] = true
    list[#list + 1] = found
    cur = found
  end
  for _, o in ipairs(Tracks()) do
    if o.op == "wall" and o.replaces and not seen[o] then
      for _, c in ipairs(list) do
        if o.replaces == c.time then return nil end
      end
    end
  end
  return list
end

-- Delete the section `i` .. `j` of the wall picked (`sel`, R.WallAt's or the map's own wall shown read-only; `sel.fl`
-- its floor) on `level`. "own" (the player's own wall off the list, the rest of it kept) or the erase's number.
function R.DeleteWall(level, sel, i, j, zone)
  local t = sel and sel.t
  if not (level and t and type(t.pts) == "table" and #t.pts >= 4) then return nil end
  local n = #t.pts / 2
  i, j = tonumber(i) or 1, tonumber(j) or n
  if j < i then i, j = j, i end
  i, j = math.max(1, i), math.min(n, j)
  local idx
  if not sel.readOnly then
    for k, o in ipairs(Tracks()) do
      if o == t and o.op == "wall" then idx = k end
    end
  end
  -- (an edit of the player's own wall, the whole of it: off the list with the walls it replaced, when they're the
  -- player's own too and nothing else depends on them; an erase there takes out any other wall near that point too and
  -- opens the ground round it. Kooki3z 2026-11-20: Delete removes the one clicked)
  local chain = idx and i == 1 and j == n and t.replaces and R.OwnWallChain(t)
  if chain then
    for _, o in ipairs(chain) do
      for k, c in ipairs(Tracks()) do
        if c == o then R.TakeOut(k) break end
      end
    end
    return "own"
  end
  if idx and (i > 1 or j < n or not t.replaces) then
    R.TakeOut(idx)
    for _, ab in ipairs({ { 1, i }, { j, n } }) do
      local a, b = ab[1], ab[2]
      if b > a then
        local pts, cl, cr, any = {}, {}, {}, false
        for k = a, b do
          pts[#pts + 1], pts[#pts + 2] = t.pts[2 * k - 1], t.pts[2 * k]
          cl[#cl + 1] = type(t.cl) == "table" and tonumber(t.cl[k]) or false
          cr[#cr + 1] = type(t.cr) == "table" and tonumber(t.cr[k]) or false
          any = any or (cl[#cl] and cr[#cr]) and true or false
        end
        any = any and t.kind == "cliff"
        R.Save({ op = "wall", drawn = true, edit = t.edit, continent = t.continent, zone = t.zone or "?",
          time = time(), pts = pts, z = t.z, indoors = t.indoors, down = t.down, replaces = t.replaces,
          kind = any and "cliff" or nil, cl = any and cl or nil, cr = any and cr or nil })
      end
    end
    return "own"
  end
  -- (the map's own, or an edit: an erase at its point furthest from every other wall's)
  local P = ns.Passability
  local others = {}
  for _, w in ipairs(P and P.WallLines and P.WallLines(level) or {}) do
    local same = true
    for k = 1, #w - 1, 2 do
      if R.LineDist(t.pts, w[k], w[k + 1]) > 0.5 then same = false break end
    end
    if not same then others[#others + 1] = w end
  end
  local best, bk = -1, i
  for k = i, j do
    local x, y = t.pts[2 * k - 1], t.pts[2 * k]
    local near = math.huge
    for _, w in ipairs(others) do
      for m = 1, #w - 1, 2 do
        local d = (w[m] - x) ^ 2 + (w[m + 1] - y) ^ 2
        if d < near then near = d end
      end
    end
    if near > best then best, bk = near, k end
  end
  local x, y = t.pts[2 * bk - 1], t.pts[2 * bk]
  local o = bk < n and bk + 1 or bk - 1
  local dx, dy = t.pts[2 * o - 1] - x, t.pts[2 * o] - y
  local d = math.sqrt(dx * dx + dy * dy)
  if d > 0 then dx, dy = dx / d, dy / d else dx, dy = 1, 0 end
  local function r1(v) return math.floor(v * 10 + 0.5) / 10 end
  local fl = sel.fl or { z = t.z, indoors = t.indoors, down = t.down }
  return R.Save({ op = "unwall", drawn = true, continent = level, zone = zone or t.zone or "?", time = time(),
    pts = { r1(x), r1(y), r1(x + dx), r1(y + dy) }, z = fl.z, indoors = fl.indoors, down = fl.down })
end

-- Restoring the map's own data (asked 2026-11-14: "a magic eraser ... that can be used to restore original road and
-- wall data", a zone's, a continent's): the player's own edits of one kind (the road tools': drawn roads, erased roads,
-- stairs, recorded walks; the wall tools': walls and wall erasers) taken out where they lie, so the data's roads and
-- walls are as shipped there again. A stroke that runs on past the area is cut there, the rest of it kept (as new
-- strokes, its parts); an erased area (a loop) or stairs the area touches go whole. Undo puts it all back.
R.RESTORE_OPS = { road = { add = true, remove = true }, wall = { wall = true, unwall = true } }
R.restores = {} -- (Undo's: each restore's tracks taken out and parts put in, the last on top; this session only)

-- Track `t`'s points, with points put in along a stretch longer than `step` that goes through the area (`inside`)
-- between two points outside it: { x, y, ... } and their heights (nil when it has none), and its own points' places.
local function Densified(t, inside, step)
  local pts, zs = t.pts, t.zs
  if not step or t.recorded then return pts, zs end -- (a recorded walk's points are 2 yd apart: as they are)
  local out, oz, n = {}, zs and {} or nil, #pts / 2
  for i = 1, n do
    local x, y = pts[2 * i - 1], pts[2 * i]
    out[#out + 1], out[#out + 2] = x, y
    if oz then oz[#oz + 1] = zs[i] end
    if i < n then
      local x2, y2 = pts[2 * i + 1], pts[2 * i + 2]
      local d = math.sqrt((x2 - x) ^ 2 + (y2 - y) ^ 2)
      local m = math.ceil(d / step)
      if m > 1 then
        local hit = false
        for k = 1, m - 1 do
          if inside(x + (x2 - x) * k / m, y + (y2 - y) * k / m) then hit = true break end
        end
        if hit then
          for k = 1, m - 1 do
            out[#out + 1], out[#out + 2] = x + (x2 - x) * k / m, y + (y2 - y) * k / m
            if oz then oz[#oz + 1] = k * 2 <= m and zs[i] or zs[i + 1] end
          end
        end
      end
    end
  end
  return out, oz
end

-- A part of track `t` (points `a` to `b` of `pts`/`zs`): a copy of it with those points; a recorded walk's notes
-- (indoors or not, the times, the rooms' names, the floors picked, its stairs marks) cut to them too.
local function Part(t, pts, zs, a, b)
  local c = {}
  for k, v in pairs(t) do c[k] = v end
  c.pts = {}
  for i = a, b do c.pts[#c.pts + 1], c.pts[#c.pts + 2] = pts[2 * i - 1], pts[2 * i] end
  if zs then
    c.zs = {}
    for i = a, b do c.zs[#c.zs + 1] = zs[i] end
    c.z = c.zs[1] or t.z
  end
  c.stairs = nil
  if t.recorded and type(t.rec) == "table" then -- (a recorded walk's points are its own: not densified)
    local r = t.rec
    local rec = {}
    if type(r.ind) == "string" then rec.ind = r.ind:sub(a, b) end
    if type(r.ts) == "string" then
      local ts = {}
      for v in r.ts:gmatch("[^,]+") do ts[#ts + 1] = v end
      local part = {}
      for i = a, b do part[#part + 1] = ts[i] or "0" end
      rec.ts = table.concat(part, ",")
    end
    -- ({ point, value, ... }: those in the part, numbered from its start; the one in effect at its start first)
    local function marks(list)
      if type(list) ~= "table" then return nil end
      local out, before = {}, nil
      for i = 1, #list - 1, 2 do
        local p = list[i]
        if p < a then before = list[i + 1]
        elseif p <= b then
          if p > a and before ~= nil and #out == 0 then out[1], out[2] = 1, before end
          out[#out + 1], out[#out + 2] = p - a + 1, list[i + 1]
        end
      end
      if #out == 0 and before ~= nil then out[1], out[2] = 1, before end
      return #out > 0 and out or nil
    end
    rec.zt, rec.pk = marks(r.zt), marks(r.pk)
    c.rec = rec
    if type(t.stairs) == "table" then
      local st = {}
      for i = 1, #t.stairs - 1, 2 do
        local s, e = t.stairs[i], t.stairs[i + 1]
        if s >= a and e <= b then st[#st + 1], st[#st + 2] = s - a + 1, e - a + 1 end
      end
      c.stairs = #st > 0 and st or nil
    end
  end
  return c
end

-- Track `t` restored where `inside(x, y)`: nil when it isn't there; else the parts of it left ({} for none).
-- `step`: the yards apart its points are looked at along a long stretch (nil: only at its points).
function R.CutTrack(t, inside, step)
  if type(t.pts) ~= "table" or #t.pts < 2 then return nil end
  local pts, zs = Densified(t, inside, step)
  local n = #pts / 2
  local inn, any = {}, false
  for i = 1, n do
    inn[i] = inside(pts[2 * i - 1], pts[2 * i]) and true or false
    any = any or inn[i]
  end
  if not any then return nil end
  if t.area or t.stair then return {} end -- (an erased area, stairs: whole)
  local parts, a = {}, nil
  for i = 1, n + 1 do
    if i <= n and not inn[i] then
      a = a or i
    elseif a then
      if i - 1 > a then parts[#parts + 1] = Part(t, pts, zs, a, i - 1) end
      a = nil
    end
  end
  return parts
end

-- Restores the data where `inside(x, y)` on continent `cont` (its city levels with it) for the `kind` of edits ("road"
-- or "wall"); `box` (minX, minY, maxX, maxY) the area's bounds, to skip strokes nowhere near (nil: any); `step` as
-- R.CutTrack's. How many edits went whole, how many were cut, how many parts were kept.
function R.Restore(kind, cont, inside, box, step)
  local ops = R.RESTORE_OPS[kind]
  if not ops then return 0, 0, 0 end
  if R.practice then -- (the tutorial's practice: its own strokes)
    local list = R.practice.list
    for i = #list, 1, -1 do
      local parts = ops[list[i].op] and R.CutTrack(list[i], inside, step)
      if parts then table.remove(list, i) end
    end
    if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    return 0, 0, 0
  end
  local Geo = ns.Geo
  local base = Geo and Geo.Base(cont) or cont
  local t = Tracks()
  local removed, added, whole, cut = {}, {}, 0, 0
  for i = 1, #t do
    local tr = t[i]
    local on = ops[tr.op] and tr.continent and (Geo and Geo.Base(tr.continent) or tr.continent) == base
    if on and box and type(tr.pts) == "table" then
      local x1, y1, x2, y2 = math.huge, math.huge, -math.huge, -math.huge
      for k = 1, #tr.pts - 1, 2 do
        local x, y = tr.pts[k], tr.pts[k + 1]
        if x < x1 then x1 = x end
        if x > x2 then x2 = x end
        if y < y1 then y1 = y end
        if y > y2 then y2 = y end
      end
      on = not (x2 < box[1] or x1 > box[3] or y2 < box[2] or y1 > box[4])
    end
    local parts = on and R.CutTrack(tr, inside, step)
    if parts then
      removed[#removed + 1] = { i = i, t = tr }
      if #parts == 0 then whole = whole + 1 else cut = cut + 1 end
      for _, p in ipairs(parts) do added[#added + 1] = p end
    end
  end
  if #removed == 0 then return 0, 0, 0 end
  for k = #removed, 1, -1 do
    local tr = table.remove(t, removed[k].i)
    if ns.Feedback and ns.Feedback.RoadRemoved then ns.Feedback.RoadRemoved(tr) end
    if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(tr.time), "remove") end
  end
  -- (the parts kept: strokes of their own, each a time (its key) of its own)
  local used = {}
  for _, o in ipairs(t) do if o.time then used[o.time] = true end end
  for _, r in ipairs(removed) do if r.t.time then used[r.t.time] = true end end
  for _, p in ipairs(added) do
    p.time = (p.time or time()) + 1
    while used[p.time] or (ns.RoadTracksIn and ns.RoadTracksIn[p.time]) do p.time = p.time + 1 end
    used[p.time] = true
    t[#t + 1] = p
    if ns.Feedback then ns.Feedback.RoadRecorded(p) end
    if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(p.time), "add") end
  end
  R.restores[#R.restores + 1] = { removed = removed, added = added, count = #t }
  R.Changed()
  return whole, cut, #added
end

-- Undo of the last restore, when it's the last change (nothing drawn since, or what was is taken back): true if so.
function R.UndoRestore()
  local t = Tracks()
  while #R.restores > 0 do
    local e = R.restores[#R.restores]
    if #t > e.count then return false end -- (something drawn since: that first)
    local ok = #t == e.count
    for k = 1, #e.added do
      if t[#t - #e.added + k] ~= e.added[k] then ok = false break end
    end
    table.remove(R.restores)
    if ok then
      for _ = 1, #e.added do
        local p = table.remove(t)
        if ns.Feedback and ns.Feedback.RoadRemoved then ns.Feedback.RoadRemoved(p) end
        if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(p.time), "remove") end
      end
      for _, r in ipairs(e.removed) do
        table.insert(t, math.min(r.i, #t + 1), r.t)
        if ns.Feedback then ns.Feedback.RoadRecorded(r.t) end
        if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(r.t.time), "add") end
      end
      ns.Print(Format(L["put back what was restored (%d of your changes)"], #e.removed))
      R.Changed()
      return true
    end
  end
  return false
end

-- The edits of `kind` on `cont` (its city levels too), and in the zone `zone` there when given (any of their points).
function R.CountEdits(kind, cont, zone)
  local ops = R.RESTORE_OPS[kind]
  local Geo, Ro = ns.Geo, ns.Router
  local base = Geo and Geo.Base(cont) or cont
  local n = 0
  for _, tr in ipairs(Tracks()) do
    if ops and ops[tr.op] and tr.continent and (Geo and Geo.Base(tr.continent) or tr.continent) == base then
      local hit = not zone
      if zone and type(tr.pts) == "table" then
        for k = 1, #tr.pts - 1, 2 do
          if Ro.ZoneAt(base, tr.pts[k], tr.pts[k + 1]) == zone then hit = true break end
        end
      end
      if hit then n = n + 1 end
    end
  end
  return n
end

-- Record (the road tools' pop-out, asked 2026-10-06: "a record button (pop out from road drawing tool) that will
-- capture this data automatically"): the player walks a road and it's saved as a drawn road (`recorded`), with what the
-- game tells of where they walked: a point every REC_STEP_YD and at the corners, indoors or not at each (`rec.ind`,
-- "1"/"0"/"?"), the minimap's zone text where it changed (`rec.zt` = { point, text, ... }: a building's or a cave's
-- rooms name themselves there), the tenths of a second between points (`rec.ts`), the floor picked with Shift + wheel
-- (`zs`, as a stroke's, for routes now; `rec.pk` = { point, height or false, ... } where the pick changed, for the
-- watcher), and their own Stairs Start / Stairs End marks (`stairs` = { first point, last point, ... }).
-- The game gives no height: the road watcher works each point's floor out (roads/recorded.py, the best path over the
-- floors under the whole walk). A new walk at a loading screen, a jump, a level change and REC_MAX_POINTS; paused in
-- combat, on a flight, a boat or a zeppelin, while dead, while the dev tools' simulated player is on, and where the game
-- hides the position (R.PauseReason). Kept going over a /reload (`recordOn`), not a logout.
R.REC_TICK = 0.1 -- seconds between samples
R.REC_STEP_YD = 2 -- a point at least this far from the last
R.REC_TURN = math.rad(25) -- and at a corner: the way turning this much there (its sample REC_TURN_MIN_YD on, at least)
R.REC_TURN_MIN_YD = 1
R.REC_JUMP_YD = 30 -- moved this far between two samples: a new walk (a teleport)
-- ... and a shorter hop onto where a portal puts you (ns.Transports' `land1`/`land2`): Stormwind's Wizard's Sanctum, the
-- tower's top and the trainers' room 9 yd apart on the map (2026-11-17: one walk, and its floors dropped into the room
-- halfway up the stairs)
R.REC_PORTAL_YD = 5
R.REC_PORTAL_LAND_YD = 4

-- Whether a hop of a sample from (ax, ay) to (x, y) on `level` was a portal's (R.REC_PORTAL_YD).
function R.PortalHop(level, ax, ay, x, y)
  if (x - ax) ^ 2 + (y - ay) ^ 2 < R.REC_PORTAL_YD ^ 2 then return false end
  local r2 = R.REC_PORTAL_LAND_YD ^ 2
  for _, t in pairs(ns.Transports or {}) do
    if type(t) == "table" and t[8] == "teleporter" then
      for side, l in ipairs({ t.land1 or false, t.land2 or false }) do
        if l and t[side == 1 and 1 or 4] == level and (x - l[1]) ^ 2 + (y - l[2]) ^ 2 <= r2 then return true end
      end
    end
  end
  return false
end
R.REC_RESUME_YD = 3 -- moved this far while paused: a new walk on going on (else the same one)
R.REC_MIN_YD = 8 -- a walk shorter than this isn't saved (as a stroke)
R.REC_MAX_POINTS = 1000 -- a walk this long is saved, and the next goes on from its last point

-- The road type being recorded (Kooki3z 2026-11-20: "recorder should support all road types as well and just get the
-- correct Z height automatically"; "I should be able to toggle the road type being recorded"): the Record window's kind
-- buttons, R.SetRecordKind. Changed while walking, the walk so far is saved as its own road of the kind it was, and the
-- walk goes on from that point as the new kind. A walk of a kind (not ground) is saved with it, and with its heights
-- worked out from the map (R.AutoHeights): the game gives no player height in WoW Forever.
R.REC_KINDS = { "ground", "floor", "bridge", "stairs", "lift" }
R.REC_KIND_MIN_YD = 1 -- (a walk of a kind this long at least is saved: a lift moves little across)
-- A bridge's ends this far apart in height: one of them stands on something (a lift's tower) over lower ground, and the
-- bridge is level at the higher (Kooki3z 2026-11-20: a recorded rope bridge from a mesa's top to a lift's tower came out
-- sloping 87 to -36, the canyon floor under the tower). A lift's ends closer than LIFT_APART_Z: its top isn't on the map's
-- ground (a tower), so no heights (Edit Road's Foot and Top set them).
R.AUTO_BRIDGE_LEVEL_Z = 6
R.AUTO_LIFT_APART_Z = 8
R.recKind = "ground" -- (the kind picked, kept for the next recording too)
-- A walk's heights from the map, the game giving no player height: a floor at the floor near its start (the floors the
-- tools know, else the ground); a bridge, stairs or a lift from the ground's height where it starts to where it ends
-- (where it meets the land: a lift's foot and the mesa's top, a bridge's two ends), evenly between. nil: none known (the
-- road watcher's import works them out).
function R.AutoHeights(kind, level, pts)
  if not kind or kind == "ground" then return nil end
  local GD, G, Rt = ns.Ground, ns.GPS, ns.Router
  local n = #pts / 2
  local function ground(k)
    if not (GD and GD.PointHeight) then return nil end
    local was = GD.force
    GD.force = true -- (the map's ground data, the road tools open or not)
    local ok, h = pcall(GD.PointHeight, level, pts[2 * k - 1], pts[2 * k])
    GD.force = was
    return ok and h or nil
  end
  local function floorNear(k)
    if not (G and G.StairHeights) then return nil end
    local ok, hs = pcall(G.StairHeights, level, pts[2 * k - 1], pts[2 * k])
    return ok and type(hs) == "table" and hs[1] or nil
  end
  local function r1(v) return math.floor(v * 10 + 0.5) / 10 end
  if kind == "floor" then
    local h = floorNear(1) or ground(1) or floorNear(n) or ground(n)
    if not h then return nil end
    local out = {}
    for k = 1, n do out[k] = r1(h) end
    return out
  end
  local za, zb = ground(1) or floorNear(1), ground(n) or floorNear(n)
  if not (za or zb) then return nil end
  za, zb = za or zb, zb or za
  if kind == "bridge" and math.abs(za - zb) > R.AUTO_BRIDGE_LEVEL_Z then za, zb = math.max(za, zb), math.max(za, zb) end
  if kind == "lift" and math.abs(za - zb) < R.AUTO_LIFT_APART_Z then return nil end
  -- (stairs walked up or down: which way from the heights where they begin and end, not the way walked; Kooki3z
  -- 2026-11-20, "stairs shouldn't need to start at the bottom". Both ends on about the same floor, as indoors with no
  -- ground under them: no heights to tell, the road watcher's import works the floors out)
  if kind == "stairs" and math.abs(za - zb) < 1 then return nil end
  local hs = Rt and Rt.RampHeights and Rt.RampHeights(pts, za, zb)
  if not hs then return nil end
  local out = {}
  for k = 1, n do out[k] = r1(hs[k]) end
  return out
end
-- The road type recorded from now on: the walk so far saved as its own road of the kind it was (R.FinishWalk), going
-- on from that point. Not recording: the kind the next recording starts with.
function R.SetRecordKind(kind)
  local known = false
  for _, k in ipairs(R.REC_KINDS) do known = known or k == kind end
  if not known then return false end
  local r = R.rec
  if r and (r.kind or "ground") ~= kind then
    if not r.paused and GetTime then R.RecordTick(GetTime(), true) end -- (a point where it changed)
    if #r.pts / 2 >= 2 then R.FinishWalk(true) end
    r.kind = kind
    local G = ns.GPS
    ns.Print(Format(L["recording: %s from here (the walk so far saved as its own road)"],
      G and G.EDIT_KIND_NAMES and G.EDIT_KIND_NAMES[kind] or kind))
  end
  R.recKind = kind
  R.RefreshWindow()
  return true
end
local function NewWalk(r)
  r.pts, r.ind, r.ts, r.zs, r.zt, r.stairs, r.pk = {}, {}, {}, {}, {}, {}, {}
  r.yd, r.lastT, r.lastZt, r.lastPk, r.cand, r.t0, r.g0 = 0, nil, nil, false, nil, nil, nil
end

-- The map's name where the player is (a walk's `zone`, as a stroke's).
local function ZoneName()
  local ok, info = pcall(function()
    local id = C_Map.GetBestMapForUnit("player")
    return id and C_Map.GetMapInfo(id)
  end)
  return ok and info and info.name or "?"
end

-- Why recording waits right now, or nil.
function R.PauseReason()
  local Geo = ns.Geo
  if Geo and Geo.Simulated and Geo.Simulated() then return "the simulated player is on" end
  if UnitIsDeadOrGhost and UnitIsDeadOrGhost("player") then return "dead" end
  if ns.inCombat or (UnitAffectingCombat and UnitAffectingCombat("player")) then return "in combat" end
  if UnitOnTaxi and UnitOnTaxi("player") then return "on a flight" end
  if ns.Taxi and ns.Taxi.Riding and ns.Taxi.Riding() then return "on a boat or zeppelin" end
  if not (Geo and Geo.RealPlayerWorld and Geo.RealPlayerWorld()) then return "no position here" end
  return nil
end

-- A sample kept as the walk's next point: s = { x, y, now, indoors, zone text, picked floor }.
local function AddPoint(r, s)
  local n = #r.pts / 2 + 1
  local x, y = math.floor(s[1] * 10 + 0.5) / 10, math.floor(s[2] * 10 + 0.5) / 10
  if n > 1 then
    local lx, ly = r.pts[#r.pts - 1], r.pts[#r.pts]
    if lx == x and ly == y then return end
    r.yd = r.yd + math.sqrt((x - lx) ^ 2 + (y - ly) ^ 2)
  end
  r.g0 = r.g0 or s[3]
  r.t0 = r.t0 or time()
  r.zone = n == 1 and ZoneName() or r.zone
  r.pts[#r.pts + 1], r.pts[#r.pts + 2] = x, y
  r.ind[n] = s[4] == true and "1" or s[4] == false and "0" or "?"
  local t = math.floor((s[3] - r.g0) * 10 + 0.5)
  r.ts[n] = math.max(0, t - (r.lastT or t))
  r.lastT = t
  r.zs[n] = s[6] or false
  -- (and where the floor picked changed, `rec.pk`: the watcher weighs what was picked, not `zs` filled in for routes)
  if (s[6] or false) ~= r.lastPk then
    r.pk[#r.pk + 1], r.pk[#r.pk + 2] = n, s[6] or false
    r.lastPk = s[6] or false
  end
  if s[5] ~= r.lastZt then
    r.zt[#r.zt + 1], r.zt[#r.zt + 2] = n, s[5] or ""
    r.lastZt = s[5]
  end
end

-- A walk's time (its key, and its place among the edits: an erase or a delete takes out roads older than it): when it
-- began, or just after the newest erase or delete saved since (Kooki3z 2026-11-20: stairs deleted and recorded again
-- while recording were older than the delete, hidden under it, "things are hidden until clicked").
function R.WalkTime(t0)
  t0 = t0 or time()
  for _, o in ipairs(Tracks()) do
    if (o.op == "remove" or o.op == "unwall") and tonumber(o.time) and o.time >= t0 then t0 = o.time + 1 end
  end
  return t0
end
-- The walk so far saved (two points and REC_MIN_YD at least) as a drawn road; `goOn`: the next walk starts at its
-- last point (REC_MAX_POINTS, an open stairs mark carried on). Its number in the drawn roads, or nil.
function R.FinishWalk(goOn)
  local r = R.rec
  if not r then return nil end
  local n = #r.pts / 2
  local saved
  local stairs = {}
  for _, v in ipairs(r.stairs) do stairs[#stairs + 1] = v end
  if r.stairOpen and n > r.stairOpen then stairs[#stairs + 1], stairs[#stairs + 2] = r.stairOpen, n end
  local kind = r.kind ~= "ground" and r.kind or nil
  if n >= 2 and r.yd >= (kind and R.REC_KIND_MIN_YD or R.REC_MIN_YD) then
    R.NotePicks(r) -- (before it's saved: the floors there as the player had them, the roads not yet rebuilt)
    local G = ns.GPS
    local zs = G and G.StrokeHeights and G.StrokeHeights(r.zs, n) or nil
    -- (a kind: its heights from the map when no floor was picked, R.AutoHeights)
    if kind and not zs then zs = R.AutoHeights(kind, r.level, r.pts) end
    saved = R.Save({ op = "add", drawn = true, recorded = true, continent = r.level, zone = r.zone or "?",
      time = R.WalkTime(r.t0), pts = r.pts, zs = zs, z = zs and zs[1] or nil, kind = kind,
      stair = kind == "stairs" and zs ~= nil or nil,
      rec = { ind = table.concat(r.ind), ts = table.concat(r.ts, ","), zt = r.zt, pk = #r.pk > 0 and r.pk or nil },
      stairs = #stairs > 0 and stairs or nil })
    r.saved = (r.saved or 0) + 1
    R.lastPiece = { kind = kind or "ground", yd = r.yd } -- (the window's "Last:")
    if kind == "stairs" then r.stairRoads = (r.stairRoads or 0) + 1 end
  end
  r.recYd = (r.recYd or 0) + (r.yd or 0) -- (the recording's yards before the next walk: the summary's "from 80 yd")
  local last
  if n > 0 then
    local indoors -- (as sampled: true, false, or nil when unknown)
    if r.ind[n] == "1" then indoors = true elseif r.ind[n] == "0" then indoors = false end
    last = { r.pts[2 * n - 1], r.pts[2 * n], r.g0 and (r.g0 + (r.lastT or 0) / 10) or 0, indoors, r.lastZt, r.zs[n] }
  end
  NewWalk(r)
  if goOn and last then
    AddPoint(r, last)
    r.stairOpen = r.stairOpen and 1 or nil
  else
    r.stairOpen = nil
  end
  return saved
end

-- A sample at (x, y) of `level` at `now` (GetTime), indoors or not (nil: unknown), the minimap's zone text, the floor
-- picked (or false): a point every REC_STEP_YD, the corner when the way turns, a new walk after a jump or onto another
-- level. `force`: a point here whatever (a stairs mark's).
function R.RecordSample(x, y, level, now, indoors, zt, fz, force)
  local r = R.rec
  if not (r and x and y) then return end
  local pts = r.pts
  local n = #pts / 2
  local s = { x, y, now, indoors, zt, fz }
  if n > 0 then
    local c = r.cand or { pts[2 * n - 1], pts[2 * n] }
    if level ~= r.level or (x - c[1]) ^ 2 + (y - c[2]) ^ 2 > R.REC_JUMP_YD ^ 2 or R.PortalHop(level, c[1], c[2], x, y) then
      R.FinishWalk()
      n = 0
    end
  end
  if n == 0 then
    r.level = level
    AddPoint(r, s)
    r.cand = nil
    return
  end
  local lx, ly = pts[2 * n - 1], pts[2 * n]
  local c = r.cand
  if c then
    -- (a corner: from the last point to the latest sample, then on to this one, the way turned)
    local ax, ay, bx, by = c[1] - lx, c[2] - ly, x - c[1], y - c[2]
    local la, lb = math.sqrt(ax * ax + ay * ay), math.sqrt(bx * bx + by * by)
    if la >= R.REC_TURN_MIN_YD and lb >= 0.3 and (ax * bx + ay * by) / (la * lb) < math.cos(R.REC_TURN) then
      AddPoint(r, c)
      lx, ly = c[1], c[2]
    end
  end
  if force or (x - lx) ^ 2 + (y - ly) ^ 2 >= R.REC_STEP_YD ^ 2 then
    AddPoint(r, s)
    r.cand = nil
  else
    r.cand = s
  end
  if #r.pts / 2 >= R.REC_MAX_POINTS then R.FinishWalk(true) end
end

-- A sample from the game now (R.REC_TICK apart while recording), or the pause it's in. `force`: a point here.
function R.RecordTick(now, force)
  local r = R.rec
  if not r then return end
  local why = r.userPaused and "paused" or R.PauseReason()
  if why then
    r.paused = why
    return
  end
  local Geo = ns.Geo
  local x, y, cont = Geo.RealPlayerWorld()
  local level = ns.Nav and ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont) or cont
  if r.paused then
    -- (going on: the same walk while still where it stopped, else a new one)
    local n = #r.pts / 2
    if n > 0 and (level ~= r.level or (x - r.pts[2 * n - 1]) ^ 2 + (y - r.pts[2 * n]) ^ 2 > R.REC_RESUME_YD ^ 2) then
      R.FinishWalk()
    end
    r.paused, r.cand = nil, nil
  end
  local indoors
  if IsIndoors then
    local ok, v = pcall(IsIndoors)
    if ok and not (ns.IsSecret and ns.IsSecret(v)) then indoors = v and true or false end
  end
  local zt
  if GetMinimapZoneText then
    local ok, v = pcall(GetMinimapZoneText)
    if ok and type(v) == "string" and not (ns.IsSecret and ns.IsSecret(v)) then zt = v end
  end
  local G = ns.GPS
  local fz = G and G.editFloor and G.editFloor.z or false
  R.RecordSample(x, y, level, now, indoors, zt, fz, force)
end

-- The floor picked, in the Record window (Kooki3z 2026-11-21: Shift + wheel with the road tools on was the only way to
-- pick one, and Record never said which floor it took you to be on). The game gives no height: the pick (G.editFloor,
-- the road tools' too) is a hint the walk carries (`rec.pk`), and the road watcher's import works each point's floor
-- out with it. The window's Floor line says it at the player's own spot: "Auto" (no pick), "Floor 2 of 3 (counting
-- up)", worked out again only when the player moved FLOOR_LINE_YD, the pick changed, or FLOOR_LINE_MAX_S went by.
R.FLOOR_LINE_YD = 3
R.FLOOR_LINE_MAX_S = 2
R.FLOOR_LINE_SECONDS = 0.25 -- (the window's own refresh while not recording; recording refreshes it every REC_TICK)
-- The player's level and spot (nil where the game hides it).
function R.PlayerSpot()
  local Geo, N = ns.Geo, ns.Nav
  local x, y, cont
  if Geo and Geo.RealPlayerWorld then x, y, cont = Geo.RealPlayerWorld() end
  if not x then return nil end
  return N and N.PlayerLevel and N.PlayerLevel(cont) or cont, x, y
end
-- The floors with heights at (x, y) of `level`, bottom up (the road tools' G.EditFloors; over a cave's floor with no
-- heights, none: a walk carries heights only).
function R.HeightFloorsAt(level, x, y)
  local G = ns.GPS
  if not (G and G.EditFloors and level and x) then return {} end
  local ok, floors = pcall(G.EditFloors, level, x, y)
  local out = {}
  for _, f in ipairs(ok and floors or {}) do
    if f.z then out[#out + 1] = f end
  end
  return out
end
-- Height `z`'s floor at (x, y) of `level`: its number counting up (0: not one there) and how many there are.
function R.FloorNumberAt(level, x, y, z)
  local floors = R.HeightFloorsAt(level, x, y)
  local G = ns.GPS
  local i = (z and G and G.FloorIndex) and G.FloorIndex(floors, { z = z }) or 0
  return i, #floors
end
-- The Floor line now: { text, note, n (the floors here), i, z (false: Auto) }; `force`: worked out again whatever.
function R.FloorState(force)
  local G = ns.GPS
  local z = G and G.editFloor and G.editFloor.z or false
  local level, x, y = R.PlayerSpot()
  local now = GetTime and GetTime() or 0
  local c = R.floorState
  if not force and c and x and c.x and c.level == level and c.z == z and now - c.t < R.FLOOR_LINE_MAX_S
      and (x - c.x) ^ 2 + (y - c.y) ^ 2 < R.FLOOR_LINE_YD ^ 2 then
    return c
  end
  local i, n = 0, 0
  if level then i, n = R.FloorNumberAt(level, x, y, z) end
  local text
  if not z then
    text = L["Floor: Auto"]
  elseif i > 0 then
    text = Format(L["Floor %d of %d (counting up)"], i, n)
  else
    text = L["Floor: the one picked (none here)"]
  end
  local note
  if n < 2 then
    note = L["One floor here."]
  elseif not z then
    note = L["Auto: the import works your floor out. Up and Down pick it."]
  else
    note = L["The pick goes with the walk to the import."]
  end
  c = { level = level, x = x, y = y, z = z, t = now, i = i, n = n, text = text, note = note }
  R.floorState = c
  return c
end
-- Up (delta > 0) or Down: the floor picked stepped at the player's spot (Auto past the top and the bottom, as the road
-- tools' Shift + wheel: G.StepFloorAt). Whether there were floors to step.
function R.StepFloor(delta)
  local G = ns.GPS
  local level, x, y = R.PlayerSpot()
  if not (G and G.StepFloorAt and level) or #R.HeightFloorsAt(level, x, y) < 2 then return false end
  local ok = G.StepFloorAt(level, x, y, delta)
  R.RefreshWindow(true)
  return ok
end
-- Auto: no floor picked (the import works it out).
function R.AutoFloor()
  local G = ns.GPS
  if G and G.editFloor then
    G.editFloor, G.floorLine = nil, nil
    if G.floorBuilding and G.floorPicks then G.floorPicks[G.floorBuilding.key] = false end
    if G.Redraw then G.Redraw() end
    if G.RoadHint and (G.roadMode or G.wallMode) then G.RoadHint() end
  end
  R.RefreshWindow(true)
end
-- A saved walk's floor picks (its `rec.pk`) kept for the summary at Stop & Save: where along the recording each pick
-- began (yards) and its number there; the same pick carried on into the next walk counted once.
function R.NotePicks(r)
  local pk = r.pk
  if not (pk and #pk > 0) then return end
  r.picks = r.picks or {}
  local pts, along, k = r.pts, 0, 1
  for j = 1, #pk - 1, 2 do
    local i, z = pk[j], pk[j + 1]
    while k < i and pts[2 * k + 2] do
      along = along + math.sqrt((pts[2 * k + 1] - pts[2 * k - 1]) ^ 2 + (pts[2 * k + 2] - pts[2 * k]) ^ 2)
      k = k + 1
    end
    if z ~= (r.sumPk or false) then
      r.sumPk = z
      local fi, fn = 0, 0
      if z and pts[2 * i] then fi, fn = R.FloorNumberAt(r.level, pts[2 * i - 1], pts[2 * i], z) end
      r.picks[#r.picks + 1] = { yd = (r.recYd or 0) + along, z = z, i = fi, n = fn }
    end
  end
end
-- What a recording's walks carry for the import, one line: the floors picked along it and the Stairs roads.
function R.PickSummary(r)
  local parts, any = {}, false
  for _, p in ipairs(r.picks or {}) do
    any = any or p.z ~= false
    local what = not p.z and L["Auto"] or (p.i or 0) > 0 and Format(L["%d of %d"], p.i, p.n) or L["a height not there"]
    parts[#parts + 1] = p.yd < 1 and Format(L["%s at the start"], what)
      or Format(L["%s from %s"], what, ns.Nav.FormatDistance(p.yd))
  end
  local stairs = r.stairRoads or 0
  if not any then return Format(L["No floor picked: worked out when imported. Stairs roads: %d."], stairs) end
  return Format(L["Floors picked: %s. Stairs roads: %d. The import works out the floors from these."],
    table.concat(parts, ", "), stairs)
end

-- Recording on: samples every REC_TICK (a frame of its own, shown only while recording).
function R.StartRecording(quiet)
  if R.rec then return end
  R.lastSummary = nil
  R.rec = { saved = 0, kind = R.recKind or "ground", recYd = 0, picks = {}, sumPk = false, stairRoads = 0 }
  NewWalk(R.rec)
  if not R.recFrame and CreateFrame then
    local f = CreateFrame("Frame")
    local acc = 0
    f:SetScript("OnUpdate", function(_, elapsed)
      acc = acc + (elapsed or 0)
      if acc < R.REC_TICK then return end
      acc = 0
      R.RecordTick(GetTime())
      R.RefreshWindow()
    end)
    if ns.TimeScript then ns.TimeScript(f, "OnUpdate", "recording") end
    R.recFrame = f
  end
  if R.recFrame then R.recFrame:Show() end
  R.RecordTick(GetTime())
  if not quiet then ns.Print(L["recording: walk the road, switching the road type as you go (Stairs too), then Stop & Save"]) end
  R.RefreshWindow()
  if ns.GPS and ns.GPS.RefreshQuick then ns.GPS.RefreshQuick() end
end

-- Recording off: the walk so far saved.
function R.StopRecording()
  local r = R.rec
  if not r then return end
  R.FinishWalk()
  R.rec = nil
  if R.recFrame then R.recFrame:Hide() end
  if R.practice then -- (the tutorial's practice walk: R.Save kept it in memory only)
    ns.Print(L["Practice: nothing was saved."])
  else
    ns.Print((r.saved or 0) == 1 and L["recording stopped: 1 walk saved as a drawn road (Undo takes the last back)"]
      or L["recording stopped: %d walks saved as drawn roads (Undo takes the last back)"]:format(r.saved or 0))
    -- (the game gives no height: a walk up stairs looks flat until it's imported, 2026-11-18)
    if (r.saved or 0) > 0 then ns.Print(L["Recorded walks show flat until they're added to the road data, which works out their heights and stairs."]) end
    R.lastSaved = r.saved
    R.lastSummary = (r.saved or 0) > 0 and R.PickSummary(r) or nil -- (the window's line on what the walks carry)
  end
  R.RefreshWindow()
  if ns.GPS and ns.GPS.RefreshQuick then ns.GPS.RefreshQuick() end
end

-- Pause (or go on), the player's own.
function R.TogglePause()
  local r = R.rec
  if not r then return end
  r.userPaused = not r.userPaused or nil
  R.RecordTick(GetTime())
  R.RefreshWindow()
end

-- The stairs key (its binding, AZEROTHGPS_RECORD_STAIRS): the Stairs road type on, and back to the type before off
-- (Kooki3z 2026-11-20: "remove the Stairs Start button and just use the top stairs button"; the marks are gone, old
-- walks with them still load). Whether it switched.
function R.MarkStairs()
  local r = R.rec
  if not r then
    ns.Print(L["Record isn't on (the road tools' Record button)"])
    return false
  end
  if r.kind == "stairs" then
    return R.SetRecordKind(r.beforeStairs or "ground")
  end
  r.beforeStairs = r.kind or "ground"
  return R.SetRecordKind("stairs")
end

-- A loading screen (PLAYER_ENTERING_WORLD): the walk so far is one walk. After a /reload, recording that was on goes on.
function R.OnEnteringWorld(isInitialLogin, isReloadingUi)
  local cdb = ns.CharDB and ns.CharDB()
  if R.rec then
    R.FinishWalk()
  elseif cdb and cdb.recordOn and isReloadingUi then
    R.StartRecording(true)
    ns.Print(L["still recording (the road tools' Record window)"])
    R.ShowWindow()
  end
  if cdb then cdb.recordOn = nil end
end

-- A /reload or logout (PLAYER_LOGOUT): the walk so far saved; recording goes on after a /reload.
function R.OnLogout()
  if R.practice then R.rec = nil end -- (the tutorial's practice walk: let go, not gone on with after a /reload)
  if not R.rec then return end
  R.FinishWalk()
  local cdb = ns.CharDB and ns.CharDB()
  if cdb then cdb.recordOn = true end
end

-- The Record window (an ns.Window): what's recorded, and Record / Pause, Stop, Stairs Start / End and Undo.
-- (the walks saved, a sentence of its own after the status)
-- The Record window (redone 2026-11-20, Kooki3z: "redo the recorder UI, its difficult to understand what is happening
-- during the recording"): the state in color with a dot (gray not recording, red recording and the road type, yellow
-- paused and why), the road type buttons, this road so far (type, length, points, indoors, the rooms' name), the stairs
-- mark, what's saved this time and the last one, and what to do next.
R.STATE_COLORS = { idle = { 0.6, 0.6, 0.6 }, rec = { 1, 0.2, 0.2 }, paused = { 1, 0.82, 0 } }
local function KindName(kind)
  local G = ns.GPS
  return G and G.EDIT_KIND_NAMES and G.EDIT_KIND_NAMES[kind or "ground"] or kind or "ground"
end
-- The window's lines now: { state, color key, road, saved, hint }.
function R.WindowLines()
  local r = R.rec
  local out = {}
  if not r then
    out.state, out.color = L["Not recording"], "idle"
    out.road = Format(L["Road type: %s"], KindName(R.recKind))
    out.hint = L["Pick the road type, press Record, then walk along the road. A road is saved each time you switch type, and at Stop & Save."]
  else
    local n = #r.pts / 2
    if r.paused then
      local why = { ["the simulated player is on"] = L["the simulated player is on"], dead = L["dead"],
        ["in combat"] = L["in combat"], ["on a flight"] = L["on a flight"],
        ["on a boat or zeppelin"] = L["on a boat or zeppelin"], ["no position here"] = L["no position here"] }
      out.state = r.paused == "paused" and L["Paused."] or L["Paused: %s."]:format(why[r.paused] or r.paused)
      out.color = "paused"
      out.hint = r.paused == "paused"
        and L["Press Resume where you stopped. Moved more than 3 yd away, a new road starts there."]
        or L["It waits by itself and goes on when it can."]
    else
      out.state, out.color = Format(L["Recording: %s"], KindName(r.kind)), "rec"
      out.hint = L["Walk along the road. Switch the type as you step onto or off a bridge, a lift or stairs: the road so far is saved then."]
    end
    local road = Format(L["This road: %s, %s, %s"], KindName(r.kind), ns.Nav.FormatDistance(r.yd or 0),
      n == 1 and L["1 point"] or L["%d points"]:format(n))
    if n > 0 and r.ind[n] == "1" then road = road .. ", " .. L["indoors"] end
    if r.lastZt and r.lastZt ~= "" then road = road .. ", " .. r.lastZt end
    out.road = road
  end
  local saved = r and r.saved or R.lastSaved or 0
  if saved > 0 and R.lastPiece then
    out.saved = Format(L["Saved this time: %d. Last: %s, %s."], saved, KindName(R.lastPiece.kind),
      ns.Nav.FormatDistance(R.lastPiece.yd or 0))
  else
    out.saved = L["Nothing saved yet this time."]
  end
  return out
end
-- (kept for what reads it: the window's state line)
function R.RecordStatus()
  local w = R.WindowLines()
  return w.state
end

function R.RefreshWindow(force)
  local f = R.window
  if not (f and f:IsShown()) then return end
  local w = R.WindowLines()
  local c = R.STATE_COLORS[w.color] or R.STATE_COLORS.idle
  f.status:SetText(w.state)
  f.status:SetTextColor(c[1], c[2], c[3])
  f.dot:SetColorTexture(c[1], c[2], c[3], 1)
  f.road:SetText(w.road)
  f.saved:SetText(w.saved)
  f.hint:SetText(w.hint)
  local r = R.rec
  -- the floor picked at the player's spot, and after Stop & Save what the walks carry for the import
  local fs = R.FloorState(force)
  f.floor:SetText(fs.text)
  f.floorNote:SetText(fs.note)
  f.up:SetEnabled(fs.n >= 2)
  f.down:SetEnabled(fs.n >= 2)
  f.auto:SetEnabled(fs.z ~= false)
  f.summary:SetText(not r and R.lastSummary or "")
  f.rec:SetText(not r and L["Record"] or r.userPaused and L["Resume"] or L["Pause"])
  f.stop:SetEnabled(r ~= nil)
  local kind = r and r.kind or R.recKind or "ground"
  for _, b in ipairs(f.kinds or {}) do
    b.picked = b.kind == kind
    if b.picked then
      if b.LockHighlight then b:LockHighlight() end
    elseif b.UnlockHighlight then
      b:UnlockHighlight()
    end
  end
end

function R.ShowWindow()
  local f = R.window
  if not f then
    f = ns.Window("AzerothGPSRecord", 420, 312, L["Record"])
    local function Text(font, x, y)
      local t = f:CreateFontString(nil, "ARTWORK", font)
      t:SetPoint("TOPLEFT", x, f.top - y)
      t:SetPoint("RIGHT", -14, 0)
      t:SetJustifyH("LEFT")
      return t
    end
    -- the state: a dot and a line in its color
    local dot = f:CreateTexture(nil, "ARTWORK")
    dot:SetSize(10, 10)
    dot:SetPoint("TOPLEFT", 16, f.top - 13)
    f.dot = dot
    f.status = Text("GameFontNormalLarge", 34, 8)
    -- the road type
    local label = Text("GameFontNormalSmall", 14, 38)
    label:SetText(L["Road type:"])
    f.kinds = {}
    local G = ns.GPS
    for k, kind in ipairs(R.REC_KINDS) do
      local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
      b:SetSize(68, 22)
      b:SetPoint("TOPLEFT", 12 + (k - 1) * 72, f.top - 54)
      b:SetText(KindName(kind))
      b.kind = kind
      if G and G.KindSwatch then G.KindSwatch(b, kind) end
      b:SetScript("OnClick", function() R.SetRecordKind(kind) end)
      f.kinds[k] = b
    end
    -- the floor picked at the player's spot, with Up / Down / Auto beside it (R.FloorState)
    f.floor = Text("GameFontHighlight", 14, 88)
    f.floor:SetPoint("RIGHT", -162, 0)
    local function Small(label, w, x, fn)
      local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
      b:SetSize(w, 22)
      b:SetPoint("TOPRIGHT", x, f.top - 83)
      b:SetText(label)
      b:SetScript("OnClick", fn)
      return b
    end
    f.auto = Small(L["Auto"], 46, -12, function() R.AutoFloor() end)
    f.down = Small(L["Down"], 50, -62, function() R.StepFloor(-1) end)
    f.up = Small(L["Up"], 44, -116, function() R.StepFloor(1) end)
    f.floorNote = Text("GameFontDisableSmall", 14, 108)
    -- this road, what's saved, what the walks carry for the import, what to do
    f.road = Text("GameFontHighlight", 14, 128)
    f.saved = Text("GameFontHighlightSmall", 14, 150)
    f.saved:SetTextColor(0.45, 1, 0.45)
    f.summary = Text("GameFontHighlightSmall", 14, 168)
    f.hint = Text("GameFontDisableSmall", 14, 198)
    -- (the Floor line kept up to date while the window shows and nothing records: recording refreshes it itself)
    local acc = 0
    f:SetScript("OnUpdate", function(_, elapsed)
      acc = acc + (elapsed or 0)
      if acc < R.FLOOR_LINE_SECONDS or R.rec then return end
      acc = 0
      R.RefreshWindow()
    end)
    if ns.TimeScript then ns.TimeScript(f, "OnUpdate", "record window") end
    local function Button(label, w, x, fn)
      local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
      b:SetSize(w, 22)
      b:SetPoint("BOTTOMLEFT", x, 10)
      b:SetText(label)
      b:SetScript("OnClick", fn)
      return b
    end
    f.rec = Button(L["Record"], 88, 12, function()
      if R.rec then R.TogglePause() else R.StartRecording() end
      R.RefreshWindow()
    end)
    f.stop = Button(L["Stop & Save"], 104, 104, function()
      R.StopRecording()
      R.RefreshWindow()
    end)
    f.undo = Button(L["Undo"], 60, 212, function()
      R.Undo()
      R.RefreshWindow()
    end)
    R.window = f
  end
  f:Show()
  R.RefreshWindow()
  return f
end

function R.ToggleWindow()
  if R.window and R.window:IsShown() then
    R.window:Hide()
  else
    R.ShowWindow()
  end
end
