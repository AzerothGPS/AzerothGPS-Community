"""The first-run setup's card pictures (`agps setup-art`): Media/Setup/<art>.tga from Kooki3z's in-game screenshots
(2026-11-19, all at the same spot in Hillsbrad Foothills; the PNGs aren't in the repo, by default read from
~/Downloads).

Each picture is Setup.lua's S.IMAGE_PX for a 2-card page (300 x 180), in the top left of a power-of-two canvas
(512 x 256) with the rest clear, like the CornerLogo files: uncompressed 32-bit TGAs with alpha (media.on_canvas's
way). The addon shows it pixel for pixel, never filtered above LINEAR; a new file needs a full relog (not a /reload).

Kooki3z, 2026-11-19: "clean up those screenshots: remove background, subtle gold glow". Each shot is cut out of the
game world behind it by a mask made of shapes in the screenshot's own pixels (`SHOTS[art]["keep"]`: the minimap's
square frame or round ring, the zone bar, the buttons, the coordinates' bright text; the windows' frame rect), the
windows' corner logo cut by the alpha of our own CornerLogo<px>.tga at the spot it's drawn (found by matching:
pixel for pixel). The map window and the world map are first cut to 5:3 (`crop`). The cut-out is fitted whole
inside the picture, `MARGIN` px in (Lanczos, premultiplied alpha), with a soft gold glow round it (`GLOW_*`)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 300, 180  # Setup.lua's S.IMAGE_PX[2]
MARGIN = 6  # px left round the cut-out for its glow
GLOW_COLOR = (255, 209, 0)  # the UI's gold (#FFD100)
GLOW_ALPHA = 0.55  # its strongest, next to the cut-out
GLOW_GROW = 1  # px the glow starts out from the cut-out's edge ...
GLOW_BLUR = 2.5  # ... and how soft it fades (Gaussian radius, px of the picture)
SS = 4  # the masks drawn this many times bigger, for smooth edges
TEXT_MIN = 150  # the coordinates' text: a pixel this bright (0-255) is text, with a pixel round it (its outline)

# art name -> the screenshot, its size, the 5:3 crop (None: all of it), and what's kept of it (screenshot pixels):
#   ("rect", x0, y0, x1, y1, corner radius), ("circle", cx, cy, r), ("poly", [(x, y), ...]),
#   ("text", x0, y0, x1, y1): the bright text in the box and its outline, ("logo", px, x, y): CornerLogo<px>.tga's
#   alpha with its top left at x, y (the logo the addon drew there, pixel for pixel).
SHOTS = {
    # the GPS square in the screen's corner: the frame, the zone bar, its buttons, the coordinates, the logo button
    "gpsMinimap": {"file": "Screenshot 2026-11-19 201527.png", "size": (391, 437), "crop": None, "keep": [
        ("rect", 16, 64, 370, 418, 2),  # the square and its frame
        ("rect", 155, 1, 182, 25, 3),  # the search button
        ("rect", 180, 1, 342, 25, 3),  # the zone and clock bar
        ("rect", 340, 1, 364, 25, 3),  # the calendar
        ("rect", 343, 27, 363, 44, 3),  # the tracking button
        ("circle", 246, 60, 14),  # the AzerothGPS button
        ("circle", 365, 67, 19.5),  # the time of day
        ("text", 158, 422, 224, 437),  # the coordinates
        ("logo", 56, 4, 382),  # the square's corner logo button
    ]},
    # the game's round minimap: the ring, its north mark, the zone bar, the buttons, the coordinates
    "gameMinimap": {"file": "Screenshot 2026-11-19 201616.png", "size": (265, 309), "crop": None, "keep": [
        ("circle", 139.5, 170, 116),  # the map and its ring
        ("poly", [(139.5, 45), (123, 67), (156, 67)]),  # the north mark
        ("rect", 34, 1, 58, 25, 3),  # the search button
        ("rect", 57, 1, 220, 25, 3),  # the zone and clock bar
        ("rect", 219, 1, 243, 25, 3),  # the calendar
        ("rect", 221, 27, 242, 44, 3),  # the tracking button
        ("circle", 173, 63, 14),  # the AzerothGPS button
        ("circle", 200, 78, 19.5),  # the time of day
        ("text", 106, 290, 170, 305),  # the coordinates
    ]},
    # the map window: its whole width from the top (the title bar and the corner logo), 5:3; the window from x 10, y 16
    "window": {"file": "Screenshot 2026-11-19 201711.png", "size": (816, 627), "crop": (0, 0, 816, 490), "keep": [
        ("rect", 10, 16, 816, 627, 3),
        ("logo", 72, -1, -3),
    ]},
    # inside the game's world map: its title and breadcrumbs, the map, a strip of the quest log, 5:3; the window from
    # x 6, y 5 to its bottom edge, its round book portrait over the top-left corner
    "worldMap": {"file": "Screenshot 2026-11-19 201739.png", "size": (1155, 605), "crop": (0, 0, 1000, 600), "keep": [
        ("rect", 6, 5, 1155, 600, 3),
        ("circle", 35, 35, 34),
    ]},
}


def _logo_alpha(media: Path, px: int) -> Image.Image:
    return Image.open(media / f"CornerLogo{px}.tga").convert("RGBA").crop((0, 0, px, px)).getchannel("A")


def mask(im: Image.Image, keep, media: Path) -> Image.Image:
    """What's kept of screenshot `im` (L, 255 kept): the union of the `keep` shapes."""
    big = Image.new("L", (im.width * SS, im.height * SS), 0)
    d = ImageDraw.Draw(big)
    for s in keep:
        if s[0] == "rect":
            _, x0, y0, x1, y1, r = s
            d.rounded_rectangle((x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1), radius=r * SS, fill=255)
        elif s[0] == "circle":
            _, cx, cy, r = s
            d.ellipse(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), fill=255)
        elif s[0] == "poly":
            d.polygon([(x * SS, y * SS) for x, y in s[1]], fill=255)
    out = big.resize(im.size, Image.LANCZOS)
    for s in keep:
        if s[0] == "text":
            _, x0, y0, x1, y1 = s
            lum = im.convert("L").crop((x0, y0, x1, y1)).point(lambda v: 255 if v >= TEXT_MIN else 0)
            out.paste(ImageChops.lighter(out.crop((x0, y0, x1, y1)), lum.filter(ImageFilter.MaxFilter(3))), (x0, y0))
        elif s[0] == "logo":
            _, px, x, y = s
            layer = Image.new("L", im.size, 0)
            layer.paste(_logo_alpha(media, px), (x, y))
            out = ImageChops.lighter(out, layer)
    return out


def _shrink(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    return im.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def picture(src: Path, shot: dict, media: Path) -> Image.Image:
    """The card picture (W x H): the cut-out fitted whole MARGIN px in, a gold glow round it, the rest clear."""
    im = Image.open(src).convert("RGBA")
    im.putalpha(mask(im, shot["keep"], media))
    if shot["crop"]:
        im = im.crop(shot["crop"])
    im = im.crop(im.getchannel("A").getbbox())
    k = min((W - 2 * MARGIN) / im.width, (H - 2 * MARGIN) / im.height)
    cut = _shrink(im, (max(1, round(im.width * k)), max(1, round(im.height * k))))
    at = ((W - cut.width) // 2, (H - cut.height) // 2)
    shape = Image.new("L", (W, H), 0)
    shape.paste(cut.getchannel("A"), at)
    halo = shape.filter(ImageFilter.MaxFilter(2 * GLOW_GROW + 1)) if GLOW_GROW else shape
    halo = halo.filter(ImageFilter.GaussianBlur(GLOW_BLUR)).point(lambda v: round(v * GLOW_ALPHA))
    out = Image.new("RGBA", (W, H), GLOW_COLOR + (0,))
    out.putalpha(halo)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(cut, at)
    return Image.alpha_composite(out, layer)


def on_canvas(img: Image.Image) -> Image.Image:
    """`img` in the top left of the smallest power-of-two canvas holding it (each side its own), the rest clear."""
    pw, ph = 1, 1
    while pw < img.width:
        pw *= 2
    while ph < img.height:
        ph *= 2
    canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    canvas.paste(img, (0, 0))
    return canvas


def sheet(pics: list[Image.Image], gray=(128, 128, 128)) -> Image.Image:
    """The pictures 2 x 2 on mid-gray (to see the clear parts and the glow)."""
    gap = 12
    out = Image.new("RGBA", (2 * W + 3 * gap, 2 * H + 3 * gap), gray + (255,))
    for i, p in enumerate(pics):
        out.alpha_composite(p, (gap + (i % 2) * (W + gap), gap + (i // 2) * (H + gap)))
    return out


def make(media: Path, src_dir: Path, preview: Path | None = None) -> list[Path]:
    """Media/Setup/<art>.tga for every SHOTS entry (and <art>.png W x H previews and all.png in `preview`). `media`
    is the addon's Media folder (CornerLogo<px>.tga read from it). Returns the files written."""
    out, pics = [], []
    setup = media / "Setup"
    setup.mkdir(parents=True, exist_ok=True)
    for art, shot in SHOTS.items():
        src = src_dir / shot["file"]
        with Image.open(src) as probe:
            if probe.size != shot["size"]:
                raise SystemExit(f"{src}: {probe.size}, expected {shot['size']} (another screenshot? check the shapes)")
        pic = picture(src, shot, media)
        g = setup / f"{art}.tga"
        on_canvas(pic).save(g)
        out.append(g)
        pics.append(pic)
        if preview:
            preview.mkdir(parents=True, exist_ok=True)
            pic.save(preview / f"{art}.png")
    if preview:
        sheet(pics).save(preview / "all.png")
    return out
