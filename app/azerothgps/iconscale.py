"""The map's game icons drawn at each size they're shown at (asked 2026-11-16: "for all map icons and borders ... render
the icons to scale like we did for icon rings to look better"; the user chose shipping scaled copies of the game's
icons). The game shrinks a 64 px icon to 16 px on the screen by its LINEAR filter alone (nothing above LINEAR: it
crashes WoW Forever), and it breaks up, as the one 64 px ring did; so each icon the map draws is drawn here at each of
coast.RING_SIZES from its full-size art, and GPSFrame's G.ScaledIcon picks the nearest to its size on the screen.

What's drawn (`sources`):
- the Interface\\Icons the addon's Lua names (Layers' city places and layers, Pins' NPC icons and its fallback list,
  the map's round buttons': GPSFrame's G.FitRoundButton), and the herbs' and veins' item icons (Layers.NODE_ITEMS,
  by the client's Item table);
  opaque: JPG (WoW Forever loads it as it is, any size), each also cut round (`r`: its border cropped by
  GPSFrame's G.ROUND_CROP, for the round icons' mask);
- a few other textures the map draws as icons (the quest marks, the NPC dots): TGA, their alpha kept;
- the classes' icons (atlas classicon-<class>, the party's) and the Search button's magnifier (ATLASES): TGA cut from
  their atlas.
Written to Media/Icons/, and Data/IconSizes.lua: { sizes, files = { [key] = "j" | "t" }, ids = { [file id] = key } };
a key is the texture's lowercased path under Interface\\ ("icons/inv_misc_book_09"), or "atlas:<name>".
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image

from .coast import RING_SIZES, tga_rgba

ROUND_CROP = 0.07  # (GPSFrame's G.ROUND_CROP: the round icons' border cropped)
JPG_QUALITY = 92
MEDIA_PATH = "Interface\\AddOns\\AzerothGPS\\Media\\Icons\\"
# other textures the map draws as icons, by their path under Interface\ (Layers.ICON's, GPSFrame's NPC dots)
EXTRA = ("gossipframe/activequesticon", "gossipframe/availablequesticon", "raidframe/readycheck-waiting",
         "common/indicator-gray", "common/indicator-yellow")
CLASSES = ("warrior", "paladin", "hunter", "rogue", "priest", "shaman", "mage", "warlock", "druid")
# atlas art drawn as icons: the classes' (the party's), and the map's Search button's magnifier (1.3.9: the map's round
# buttons drawn sharp, GPSFrame's G.FitRoundButton)
ATLASES = tuple(f"classicon-{c}" for c in CLASSES) + ("common-search-magnifyingglass",)
_BS = chr(92)
ICON_RE = re.compile("Interface" + _BS * 4 + "Icons" + _BS * 4 + "([A-Za-z0-9_]+)")
FALLBACK_RE = re.compile(r"P\.FALLBACK_ICONS = \{(.*?)\}", re.S)
NODE_ITEMS_RE = re.compile(r"Lay\.NODE_ITEMS = \{(.*?)\n\}", re.S)


def base_name(key: str) -> str:
    """The files' name for `key`: its path's or atlas' characters other than letters, digits and _ as _."""
    return re.sub(r"[^a-z0-9_]", "_", key.replace("atlas:", "atlas_"))


def icon_names(addon_dir: Path) -> set[str]:
    """The Interface\\Icons the addon's Lua names, lowercased."""
    names = set()
    for f in sorted(addon_dir.glob("*.lua")) + sorted((addon_dir / "Data").glob("*.lua")):
        text = f.read_text(encoding="utf-8", errors="replace")
        names.update(m.group(1).lower() for m in ICON_RE.finditer(text))
        m = FALLBACK_RE.search(text)
        if m and f.name == "Pins.lua":
            names.update(n.lower() for n in re.findall(r'"([A-Za-z0-9_]+)"', m.group(1)))
    return names


def node_items(addon_dir: Path) -> set[int]:
    m = NODE_ITEMS_RE.search((addon_dir / "Layers.lua").read_text(encoding="utf-8"))
    return {int(v) for v in re.findall(r"=\s*(\d+)", m.group(1))} if m else set()


def _blp(cd, fid: int) -> Image.Image:
    data = cd.casc.read(fid)
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        img = _blp_raw(data)
        if img is None:
            raise
        return img


def _blp_raw(data: bytes) -> Image.Image | None:
    """A BLP2 of uncompressed BGRA pixels (its encoding 3, which Pillow doesn't read: the Search button's magnifier's
    atlas), its first mip; None for any other."""
    import struct

    if data[:4] != b"BLP2" or data[8] != 3:
        return None
    w, h = struct.unpack_from("<II", data, 12)
    off = struct.unpack_from("<I", data, 20)[0]
    px = data[off:off + w * h * 4]
    if len(px) < w * h * 4:
        return None
    b, g, r, a = Image.frombytes("RGBA", (w, h), px).split()
    return Image.merge("RGBA", (r, g, b, a))


def sources(cd, addon_dir: Path) -> list[dict]:
    """Each texture to draw: { key, fid (or None), image (RGBA, full size), opaque, round }."""
    out, seen = [], set()

    def add(key, fid, img, opaque, round_):
        if key in seen:
            return
        seen.add(key)
        out.append({"key": key, "fid": fid, "image": img, "opaque": opaque, "round": round_})

    paths = {f"icons/{n}" for n in icon_names(addon_dir)}
    items = {r["ID"]: r["IconFileDataID"] for r in cd.table("Item")}
    by_item = {}
    for item in sorted(node_items(addon_dir)):
        fid = items.get(item)
        name = fid and cd.name(fid)
        if isinstance(name, str) and name.startswith("interface/icons/"):
            by_item[name[len("interface/"):-len(".blp")]] = fid
    for key in sorted(paths | set(by_item)):
        fid = by_item.get(key) or cd.listfile.id(f"interface/{key}.blp")
        if not fid:
            continue
        add(key, fid, _blp(cd, fid), True, True)
    for key in EXTRA:
        fid = cd.listfile.id(f"interface/{key}.blp")
        if fid:
            img = _blp(cd, fid)
            add(key, fid, img, img.getextrema()[3][0] == 255, False)
    members = {str(r.get("CommittedName") or "").lower(): r for r in cd.table("UiTextureAtlasMember")}
    atlases = {r["ID"]: r for r in cd.table("UiTextureAtlas")}
    sheets = {}
    for name in ATLASES:
        m = members.get(name)
        if not m:
            continue
        a = atlases[m["UiTextureAtlasID"]]
        sheet = sheets.get(a["FileDataID"]) or sheets.setdefault(a["FileDataID"], _blp(cd, a["FileDataID"]))
        sx, sy = sheet.width / a["AtlasWidth"], sheet.height / a["AtlasHeight"]
        box = (round(m["CommittedLeft"] * sx), round(m["CommittedTop"] * sy), round(m["CommittedRight"] * sx),
               round(m["CommittedBottom"] * sy))
        add(f"atlas:{name}", None, sheet.crop(box), False, False)
    return out


def scaled(img: Image.Image, n: int, crop: float = 0.0) -> Image.Image:
    """`img` (its border cropped by `crop` of each side) shrunk to n x n from its full size (Lanczos, colors weighted
    by their alpha so clear edges don't darken)."""
    if crop:
        w, h = img.size
        img = img.crop((round(w * crop), round(h * crop), round(w * (1 - crop)), round(h * (1 - crop))))
    pre = img.convert("RGBa")  # (premultiplied)
    return pre.resize((n, n), Image.LANCZOS, reducing_gap=None).convert("RGBA")


def sizes_for(src: dict) -> list[int]:
    """The sizes drawn for a source: those under its own art's size (at its size the game's file is it, pixel for
    pixel: a 64 px icon at 64 px)."""
    return [n for n in RING_SIZES if n < min(src["image"].size)]


def files_for(src: dict) -> dict[str, bytes]:
    """{ file name: its bytes } for one source: each size, square, and round (`r`) for an opaque game icon."""
    out = {}
    base = base_name(src["key"])
    for n in sizes_for(src):
        variants = [("", 0.0)] + ([("r", ROUND_CROP)] if src["round"] else [])
        for suffix, crop in variants:
            img = scaled(src["image"], n, crop)
            if src["opaque"]:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=JPG_QUALITY, subsampling=0)
                out[f"{base}_{n}{suffix}.jpg"] = buf.getvalue()
            else:
                import numpy as np

                out[f"{base}_{n}{suffix}.tga"] = tga_rgba(np.asarray(img))
    return out


def lua_text(srcs: list[dict], version: str = "") -> str:
    lines = [f"-- GENERATED by `agps gen-addon-data`{' from client ' + version if version else ''}. Do not edit by hand.",
             "-- The map's game icons drawn at each size (app/azerothgps/iconscale.py; GPSFrame's G.ScaledIcon): files,",
             "-- a texture's key (its lowercased path under Interface\\, or atlas:<name>) -> j (JPG, square and round",
             "-- `r` files) or t (TGA), and the largest size drawn (bigger: the game's own file); ids, a file id -> its",
             "-- key.",
             "local _, ns = ...",
             "ns.IconSizes = {",
             f"  path = \"{MEDIA_PATH.replace(_BS, _BS * 2)}\",",
             "  sizes = { " + ", ".join(str(n) for n in RING_SIZES) + " },",
             "  files = {"]
    for s in sorted(srcs, key=lambda s: s["key"]):
        lines.append(f"    [\"{s['key']}\"] = \"{'j' if s['opaque'] else 't'}{max(sizes_for(s), default=0)}\",")
    lines += ["  },", "  ids = {"]
    for s in sorted((s for s in srcs if s["fid"]), key=lambda s: s["fid"]):
        lines.append(f"    [{s['fid']}] = \"{s['key']}\",")
    lines += ["  },", "}", ""]
    return "\n".join(lines)


def write(cd, addon_dir: Path, log=print) -> list[Path]:
    """Media/Icons/* and Data/IconSizes.lua, the files no longer made removed."""
    srcs = sources(cd, addon_dir)
    media = addon_dir / "Media" / "Icons"
    media.mkdir(parents=True, exist_ok=True)
    keep, total = set(), 0
    for s in srcs:
        for name, data in files_for(s).items():
            f = media / name
            keep.add(name)
            total += len(data)
            if not f.exists() or f.read_bytes() != data:
                f.write_bytes(data)
    for f in media.iterdir():
        if f.name not in keep:
            f.unlink()
    p = addon_dir / "Data" / "IconSizes.lua"
    p.write_text(lua_text(srcs, getattr(getattr(cd, "casc", None), "version", "")), encoding="utf-8", newline="\n")
    log(f"icons to scale: {len(srcs)} textures, {len(keep)} files, {total / 1e6:.2f} MB")
    return [p, media]
