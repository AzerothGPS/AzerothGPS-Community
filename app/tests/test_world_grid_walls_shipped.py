"""The shipped world grid never links across a model's wall the walk mesh lost (item 72e, Kooki3z: "a CI test that
fails if a new bake has links crossing collision geometry, so it can't come back"). data/wall_cut_links.json: a sample
of the links the 72 bake cut (worldgrid.cut_wall_links, from the client's models: Red Cloud Mesa, Goldshire, Zephras
Isle's towns, Stormwind, Orgrimmar...), each a surface's point and height, the way to its neighbor cell and the
neighbor's height. A bake made without the cut (its models missing, the cut undone) links them again: this fails."""

import json
from pathlib import Path

from test_map_redraw import game  # noqa: F401

FIXTURE = Path(__file__).parent / "data" / "wall_cut_links.json"

CHECK = """
return function(cont, ax, ay, az, dx, dy, bz)
  local WG = AGPS_NS.WorldGrid
  local c = WG.Cont(cont)
  if not c then return "no grid" end
  local DX = { 1, 0, -1, 0, 1, -1, -1, 1 }
  local DY = { 0, 1, 0, -1, 1, 1, -1, -1 }
  local d
  for k = 1, 8 do if DX[k] == dx and DY[k] == dy then d = k end end
  local here
  for _, s in ipairs(WG.SurfacesAt(c, ax, ay, az)) do
    if math.abs(s.z - az) <= 1 and math.floor(s.x / c.cell) == math.floor(ax / c.cell)
      and math.floor(s.y / c.cell) == math.floor(ay / c.cell) then here = s break end
  end
  if not here then return "gone" end -- (the surface not kept: a piece left out, nothing linked)
  local t = WG.Tile(c, here.key)
  local kk = WG.Link(t, here.s, d)
  if kk == 0 then return "cut" end
  local nkey, nci = WG.Step(c, here.key, here.ci, d)
  local nt = WG.Tile(c, nkey)
  local z = WG.Z(c, nt, WG.First(nt, nci) + kk - 1)
  if math.abs(z - bz) <= 1 then return "linked" end
  return "cut"
end
"""


def test_no_shipped_link_crosses_a_wall_the_mesh_lost(game):
    lua, ns = game
    ns.WorldGrid.Set(True)
    check = lua.execute(CHECK)
    links = json.loads(FIXTURE.read_text(encoding="utf-8"))["links"]
    assert len(links) >= 50
    bad, seen = [], 0
    for ln in links:
        a, b, (dx, dy) = ln["a"], ln["b"], ln["dir"]
        got = str(check(ln["cont"], a[0], a[1], a[2], dx, dy, b[2]))
        assert got != "no grid", ln
        seen += got != "gone"
        if got == "linked":
            bad.append(ln)
    assert not bad, f"{len(bad)} of {len(links)} links across a model's wall are in the shipped grid: {bad[:3]}"
    assert seen >= len(links) // 2  # (most of their surfaces kept: the check checked something)
