"""The seamless map's coastline (issue #73): the terrain fades into the world art along the coast, not the tiles'
squares. coast.py works the sea out from the shipped terrain grid; GPSFrame draws the coastal tiles through their
masks."""

from __future__ import annotations

import re

import numpy as np
import pytest

from azerothgps import coast
from azerothgps.paths import ADDON_DIR

from test_atlas import COASTS, _laid, _seamless

CELL = coast.TILE / coast.MASK_PX


def _world(h=200, w=200):
    """A synthetic grid: no terrain west of column 20 (the void), the open sea to column 80, land east of it."""
    cells = np.zeros((h, w), np.uint8)
    cells[:, :80] = 1
    tiled = np.ones((h, w), bool)
    tiled[:, :20] = False
    return cells, tiled


def test_the_sea_is_the_open_water_joined_to_where_there_is_no_terrain():
    cells, tiled = _world()
    cells[100:103, 80:180] = 1  # a river (3 cells, 25 yd wide) out to the sea
    cells[20:60, 120:160] = 1  # a lake inland, wide but joined to nothing
    cells[150:190, 40:44] = 2  # the seabed's steep ridge out in the sea (cut the coast off it, off Westfall)
    cells[10:40, 80:86] = 2  # a cliff on the shore, land behind it
    cells[60:63, 50:53] = 0  # a rock out in the sea
    cells[120:140, 40:60] = 0  # an island
    sea = coast.sea(cells, tiled)
    assert sea[:, :20].all()  # (the void)
    assert sea[50, 60] and sea[170, 60]  # the open sea, and past the ridge
    assert sea[170, 42]  # the ridge is the sea's
    assert not sea[101, 150]  # the river is the land's
    assert not sea[40, 140]  # the lake too
    assert not sea[20, 83]  # the cliff on the shore
    assert sea[61, 51]  # the rock, a speck, the sea's
    assert not sea[130, 50]  # the island isn't


def test_the_fade_runs_from_the_shore_out_over_the_feather_yards():
    cells, tiled = _world()
    a = coast.alpha(coast.sea(cells, tiled)).astype(int)
    assert (a[:, 80:] == 255).all()  # the land, sharp
    row = a[100, 20:80][::-1]  # from the shore out
    assert row[0] > 240 and (np.diff(row) <= 0).all()  # fading out, never back
    out = int(np.ceil(coast.FEATHER_YD / CELL)) + 1
    assert (row[out:] == 0).all()  # past the feather: the sea, the art alone
    assert 0 < row[out // 2] < 255


def test_the_feather_is_the_maps_own():
    src = (ADDON_DIR / "GPSFrame.lua").read_text(encoding="utf-8")
    yd = float(re.search(r"^G\.EDGE_FEATHER_YD = ([\d.]+)", src, re.M).group(1))
    assert yd == coast.FEATHER_YD


def test_tile_masks_and_their_boxes():
    cells, tiled = _world(128, 192)
    tiles = {tx * 64 + ty for tx in (1, 2) for ty in (0, 1)}  # (a grid of 3 x 2 tiles; tile column 0 the void's)
    cells[:, :140] = 1  # (the sea out to the middle of tile column 2)
    masks = coast.tile_masks(0, 0, cells, tiles)
    assert isinstance(masks[1 * 64 + 0], int) and masks[1 * 64 + 0] == 0  # all sea: the shore past its feather
    m = masks[2 * 64 + 0]  # the coast: columns 140.., 12.. in it
    assert m.shape == (64, 64) and m[:, 12:].min() == 255 and m[:, :4].max() == 0
    cells[:, :] = 0
    assert coast.tile_masks(0, 0, cells, tiles) == {}  # all land (the void west of it the sea, but past the feather)
    box = coast.sea_box(m)
    assert box[0] == 0 and box[1] == 0 and box[3] == 63 and box[2] < 36
    lua, ns = _seamless()
    u0, v0, u1, v1 = ns.GPS.CoastBox(coast.code(box))
    assert (u0, v0, u1, v1) == pytest.approx((box[0] / 64, box[1] / 64, (box[2] + 1) / 64, (box[3] + 1) / 64))


def test_the_shipped_masks_are_up_to_date_and_white():
    masks = coast.build(log=lambda *_: None)
    assert (ADDON_DIR / "Data" / "Coast.lua").read_text(encoding="utf-8") == coast.lua(masks), \
        "stale: run agps coast --write"
    want = set()
    for cont, m in masks.items():
        for k, v in m.items():
            if isinstance(v, int):
                continue
            tx, ty = divmod(k, 64)
            p = coast.MEDIA / f"{cont}_{tx}_{ty}.tga"
            want.add(p.name)
            data = p.read_bytes()
            assert data == coast.tga(v), p.name
            rgb, a = coast.read_tga_alpha(data)
            assert (rgb == 255).all() and (a == v).all()  # (white: only its alpha, no picture in it)
    assert {p.name for p in coast.MEDIA.iterdir()} == want
    assert masks[0] and masks[1]  # (both continents have their coasts)


def test_the_edge_blend_turns_on_only_with_the_sea_in_view():
    lua, ns = _seamless()
    G, Geo = ns.GPS, ns.Geo
    TILE = Geo.TILE
    # one coastal tile (10, 10) among land tiles, its sea in its eastern quarter
    lua.execute("""
      local t = {}
      for tx = 8, 12 do for ty = 8, 12 do t[tx * 64 + ty] = 111 end end
      AGPS_NS.MinimapTiles[77] = t
      AGPS_NS.Coast = { [77] = { [10 * 64 + 10] = 1 + 48 + 64 * (0 + 64 * (63 + 64 * 63)) } }""")
    x = (32 - 10.5) * TILE  # (the tile's middle row: x north)
    y_west, y_east = (32 - 10.2) * TILE, (32 - 10.95) * TILE
    assert not G.EdgeInView(77, x, y_west, 50)  # its land only in view
    assert G.EdgeInView(77, x, y_east, 50)  # its sea
    assert G.CoastAt(77, 10, 10) == G.COAST_MEDIA + "77_10_10" and G.CoastAt(77, 9, 10) is None
    lua.execute("AGPS_NS.Coast[77][10 * 64 + 10] = 0")
    assert G.EdgeInView(77, x, y_west, 50) and G.CoastAt(77, 10, 10) == 0
    # laid with the edge blend: the tile all sea left out; without it, drawn as always
    q = ns.GPS.LayoutMinimap(x, (32 - 10.5) * TILE, 77, 0, 600, 300, True)
    fids = [q[i][1] for i in range(1, len(q) + 1) if not q[i].color and not q[i].grad]
    assert len(fids) == 24
    q = ns.GPS.LayoutMinimap(x, (32 - 10.5) * TILE, 77, 0, 600, 300, False)
    assert len(q) == 25 and not any(q[i].mask for i in range(1, 26))


@pytest.mark.parametrize("cont,x,y", COASTS)
def test_a_texture_reused_off_the_coast_loses_its_mask(cont, x, y):
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}")
    ns.settings.gps.zoom = 400
    G.Update()
    assert any(t.mask for t in _laid(lua)[0])
    lua.execute("AGPS_POS = { -4.0, -788.0, 1 }")  # (inland: the Barrens)
    G.Update()
    assert not G.shownView.edge
    lua.execute("""AGPS_D = 0
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._shown and w._parent == AGPS_NS.GPS.quadLayer and (w.agpsMaskOn or #(w._masks or {}) > 0) then
          AGPS_D = AGPS_D + 1
        end
      end""")
    assert lua.eval("AGPS_D") == 0


def test_the_round_icons_rings_are_our_own_and_up_to_date():
    """Media/IconRing<n>.tga (the round map icons' ring at each size it's shown at, GPSFrame's G.RING_SIZES; asked
    2026-11-14: "these icon borders seem poorly downscaled"), made by coast.ring(n) (`agps coast --write`): gray levels
    only (the tint is the ring's color), clear in its middle and past its corners, its gold band opaque."""
    import re as _re
    shipped = sorted(int(_re.fullmatch(r"IconRing(\d+)\.tga", p.name).group(1))
                     for p in coast.RING_DIR.glob("IconRing*.tga"))
    assert shipped == sorted(coast.RING_SIZES)
    for n in coast.RING_SIZES:
        data = coast.ring_file(n).read_bytes()
        assert data == coast.tga_rgba(coast.ring(n)), n
        rgb, a = coast.read_tga_alpha(data)
        assert (rgb[..., 0] == rgb[..., 1]).all() and (rgb[..., 1] == rgb[..., 2]).all()
        assert a[n // 2, n // 2] == 0 and a[0, 0] == 0
        # (along the middle row from the left edge: the black edge, then the gold, lit)
        row = a[n // 2]
        assert row.max() == 255 and rgb[n // 2, :, 0].max() >= 200, n


def test_the_interiors_feather_is_our_own_and_up_to_date():
    """Media/Feather.tga (issue #85, the interiors' edge blend): white, only its alpha varies, made by coast.feather()
    (`agps coast --write`): opaque in its middle half, clear at its corners, the same cut GPSFrame slices it by."""
    data = coast.FEATHER_FILE.read_bytes()
    assert data == coast.tga(coast.feather())
    rgb, a = coast.read_tga_alpha(data)
    assert (rgb == 255).all()
    n, k = coast.FEATHER_PX, int(coast.FEATHER_PX * coast.FEATHER_CUT)
    assert (a[k:n - k, k:n - k] == 255).all() and a[0, 0] == 0 and a[n // 2, 0] < 10
    assert (np.diff(a[n // 2, :k].astype(int)) >= 0).all()  # (rising to the middle)
    lua = (ADDON_DIR / "GPSFrame.lua").read_text(encoding="utf-8")
    assert re.search(r"G\.INTERIOR_FEATHER_CUT = ([\d.]+)", lua).group(1) == f"{coast.FEATHER_CUT:g}"
