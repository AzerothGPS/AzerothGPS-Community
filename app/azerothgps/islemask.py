"""The seamless map's isles' land masks (issue #90, #87): addon/AzerothGPS/Atlas/Media/Textures/MapIsle/<map>.tga.

An isle on a map of its own (Zephras Isle, uiMap 2521 on continent 2991) isn't on Azeroth's map art, so the stitched
map lays its own zone map over its frame (Atlas.lua A.DrawIsles). That art is a whole parchment page round the island
(clouds, towers, the page's frame): drawn as it is, the isle sat on a light square with hard edges out in the world's
sea. Its mask here is the island alone: the gray coastline band the map paints round it, found by its colour (bluish
or gray, against the yellow parchment and the brown land), closed over its gaps, filled, and its largest piece kept (not the clouds');
1 on the island and its coastline, fading out over FEATHER_PX of the art past it, 0 on the page.

The mask is made from the game's map art, so it ships in the Atlas folder only (CLAUDE.md: the one exception; white,
only its alpha varies). Needs the client: `agps isle-mask --write`.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np

from .paths import ADDON_DIR

MEDIA = ADDON_DIR / "Atlas" / "Media" / "Textures" / "MapIsle"
ISLES = (2521,)  # the isles drawn on a map of their own (GPSFrame's G.WORLD_INSETS)
MASK_PX = 512  # the mask's side (stretched over the map's rectangle, as the engine's MapLand masks are)
FEATHER_PX = 14  # the art's px past the coastline over which the island fades out (about 75 yd on Zephras Isle)
CLOSE_PX = 18  # gaps in the coastline band up to about twice this are closed (its south lobe's is gray-brown)


def map_tiles(map_id: int, path: Path | None = None) -> tuple[int, int, list]:
    """Data/Maps.lua's art for uiMap `map_id`: (artW, artH, [(file, x, y, w, h, texW, texH)])."""
    text = (path or ADDON_DIR / "Data" / "Maps.lua").read_text(encoding="utf-8")
    m = re.search(r"^  \[%d\] = \{.*?artW = (\d+), artH = (\d+),\s*tiles = \{(.*?)\},\s*$" % map_id, text, re.S | re.M)
    if not m:
        raise SystemExit(f"no art for uiMap {map_id} in Data/Maps.lua")
    tiles = [tuple(int(v) for v in t.split(",")) for t in re.findall(r"\{([\d,]+)\}", m.group(3))]
    return int(m.group(1)), int(m.group(2)), tiles


def compose(read, map_id: int) -> np.ndarray:
    """The map's art (artH, artW, 3) from its tiles; `read(file id)` gives a BLP's bytes."""
    from PIL import Image

    w, h, tiles = map_tiles(map_id)
    canvas = Image.new("RGB", (max(t[1] + t[5] for t in tiles), max(t[2] + t[6] for t in tiles)))
    for fid, x, y, *_ in tiles:
        canvas.paste(Image.open(io.BytesIO(read(fid))).convert("RGB"), (x, y))
    return np.asarray(canvas.crop((0, 0, w, h))).astype(float)


def land(art: np.ndarray) -> np.ndarray:
    """(h, w) bool: the island and its coastline band."""
    from scipy import ndimage as nd

    r, b = art[..., 0], art[..., 2]
    mx = art.max(-1)
    sat = (mx - art.min(-1)) / np.maximum(mx, 1)
    line = ((b - r > -40) & (mx > 90)) | ((sat < 0.2) & (mx > 70))  # the coastline band and the lakes: bluish or gray
    shape = nd.binary_fill_holes(nd.binary_dilation(line, iterations=CLOSE_PX))
    shape = nd.binary_erosion(shape, iterations=CLOSE_PX)
    lab, n = nd.label(shape)
    if not n:
        raise SystemExit("no island found in the map's art")
    return lab == int(np.argmax(nd.sum(shape, lab, range(1, n + 1)))) + 1


def mask(art: np.ndarray) -> np.ndarray:
    """(MASK_PX, MASK_PX, 4) uint8: white, alpha 255 on the island fading to 0 over FEATHER_PX past it."""
    from PIL import Image
    from scipy import ndimage as nd

    d = nd.distance_transform_edt(~land(art))  # (art px from the island; 0 on it)
    t = np.clip(1 - d / FEATHER_PX, 0, 1)
    a = t * t * (3 - 2 * t)
    alpha = Image.fromarray((a * 255 + 0.5).astype(np.uint8)).resize((MASK_PX, MASK_PX), Image.LANCZOS)
    out = np.full((MASK_PX, MASK_PX, 4), 255, np.uint8)
    out[..., 3] = np.asarray(alpha)
    out[0, :, 3] = out[-1, :, 3] = out[:, 0, 3] = out[:, -1, 3] = 0  # (clamped: never a line along the frame's edge)
    return out


def write(read, isles=ISLES) -> list[Path]:
    from PIL import Image

    MEDIA.mkdir(parents=True, exist_ok=True)
    out = []
    for map_id in isles:
        m = mask(compose(read, map_id))
        p = MEDIA / f"{map_id}.tga"
        Image.fromarray(m, "RGBA").save(p)
        out.append(p)
        print(f"wrote {p} (island {np.mean(m[..., 3] > 127):.1%} of the page)")
    return out
