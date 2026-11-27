#!/usr/bin/env python3
"""Build Topo's deterministic Pillow previews and transparent Plymouth mark.

Run from any directory: python3 tools/generate_previews.py
Requires Pillow, the generated wallpapers, and colors.toml. System fonts are
selected in a fixed order; no font files are bundled. Pixel-identical text is
expected on the same Pillow/font versions. All screen content is illustrative.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
import subprocess
import tomllib

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LANCZOS = Image.Resampling.LANCZOS
ANSI_KEYS = (
    "background", "red", "green", "yellow", "blue", "magenta", "cyan",
    "foreground", "muted", "bright_red", "bright_green", "bright_yellow",
    "bright_blue", "bright_magenta", "bright_cyan", "bright_foreground",
)
FONT_PATTERNS = {
    "sans": "sans-serif",
    "mono": "monospace",
    "bold": "sans-serif:weight=bold",
}


@lru_cache(maxsize=None)
def font_path(style: str) -> str | None:
    """Ask Fontconfig for local fonts without assuming a filesystem layout."""
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}\n", FONT_PATTERNS[style]],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return next((line for line in result.stdout.splitlines() if Path(line).is_file()), None)
    except (OSError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=None)
def font(size: int, style: str = "sans") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = font_path(style)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Older Pillow versions lack scalable default fonts.
        return ImageFont.load_default()


def theme_name(palette: dict[str, str]) -> str:
    return "topo-light" if palette.get("mode") == "light" else "topo"


def theme_title(palette: dict[str, str]) -> str:
    return "Topo Light" if palette.get("mode") == "light" else "Topo"


def rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def luminance(value: str) -> float:
    channels = [x / 255 for x in rgb(value)]
    linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
              for x in channels]
    return sum(x * w for x, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], content: str,
         fill: str, size: int, style: str = "sans", anchor: str = "lt") -> None:
    draw.text(xy, content, fill=fill, font=font(size, style), anchor=anchor)


def emblem(draw: ImageDraw.ImageDraw, center: tuple[float, float], radius: float,
           color: str, width: float = 1.0) -> None:
    """An original six-ring mark, with smooth harmonics shared by each ring."""
    cx, cy = center
    for ring in range(6):
        r = radius * (0.29 + ring * 0.135)
        points = []
        for step in range(241):
            a = step / 240 * math.tau
            wobble = (1 + 0.08 * math.sin(3 * a + 0.6)
                      + 0.045 * math.cos(5 * a - 0.7))
            points.append((cx + r * wobble * math.cos(a),
                           cy + r * wobble * math.sin(a) * 0.91))
        draw.line(points, fill=color, width=max(1, round(width * (1.7 if ring == 4 else 1))),
                  joint="curve")


def save_png(image: Image.Image, path: Path) -> None:
    image.save(path, optimize=True)
    print(f"{path.relative_to(ROOT)}: {image.width}x{image.height}, {path.stat().st_size:,} bytes")


def make_unlock(palette: dict[str, str]) -> Image.Image:
    # Match upstream's shorter 800x188 Plymouth convention. Work at 2x for
    # smooth transparent edges, with generous empty space around the mark.
    scale = 2
    image = Image.new("RGBA", (800 * scale, 188 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    light = palette.get("mode") == "light"
    # Plymouth copies the logo unchanged; only its other assets are tinted.
    # Use dark-gray pixels for both parts of the mark on a light boot screen.
    emblem(draw, ((202 if light else 287) * scale, 95 * scale), 64 * scale,
           palette["foreground"] if light else palette["accent"], width=1.45 * scale)
    text(draw, ((288 if light else 374) * scale, (56 if light else 42) * scale),
         theme_name(palette), palette["foreground"], (74 if light else 99) * scale, "sans")
    image = image.resize((800, 188), LANCZOS)
    save_png(image, ROOT / "unlock.png")
    return image


def make_palette(palette: dict[str, str]) -> None:
    image = Image.new("RGB", (960, 540), palette["background"])
    draw = ImageDraw.Draw(image)
    text(draw, (28, 22), theme_title(palette) + " / palette", palette["foreground"], 30, "bold")
    text(draw, (28, 64), "NEUTRAL SURFACES / READABLE SIGNALS", palette["muted"], 13, "mono")
    surfaces = (
        ("background", "background"), ("dark_background", "dark bg"),
        ("darker_background", "darker bg"), ("lighter_background", "lighter bg"),
        ("foreground", "foreground"), ("muted", "muted"),
        ("accent", "accent"), ("selection", "selection"),
    )
    for index, (key, label) in enumerate(surfaces):
        x = 28 + index * 114
        draw.rounded_rectangle((x, 100, x + 106, 136), radius=3,
                               fill=palette[key], outline=palette["muted"])
        text(draw, (x, 147), label, palette["foreground"], 12, "mono")
        text(draw, (x, 166), palette[key], palette["muted"], 12, "mono")
    draw.line((28, 200, 932, 200), fill=palette["muted"], width=1)
    text(draw, (28, 215), "Terminal / ANSI 0–15", palette["foreground"], 20, "bold")
    text(draw, (932, 220), "Contrast on " + palette["background"],
         palette["muted"], 13, "mono", "rt")
    for index, key in enumerate(ANSI_KEYS):
        x = 28 + index % 4 * 228
        y = 257 + index // 4 * 66
        ratio = "n/a" if index == 0 else f"{contrast(palette[key], palette['background']):.2f}:1"
        text(draw, (x, y), f"{index:02d} {key}", palette["foreground"], 13, "mono")
        draw.rounded_rectangle((x, y + 24, x + 30, y + 43), radius=2,
                               fill=palette[key], outline=palette["muted"])
        text(draw, (x + 40, y + 26), palette[key], palette["muted"], 12, "mono")
        text(draw, (x + 206, y + 26), ratio, palette["foreground"], 12, "mono", "rt")
    save_png(image, ROOT / "previews" / "palette.png")


def wallpaper(size: tuple[int, int]) -> Image.Image:
    paths = sorted((ROOT / "backgrounds").glob("1-*.png"))
    if len(paths) != 1:
        raise SystemExit("Generate wallpapers first: python3 tools/generate_wallpapers.py")
    with Image.open(paths[0]) as source:
        return source.convert("RGB").resize(size, LANCZOS)


def make_desktop(palette: dict[str, str]) -> None:
    image = wallpaper((2560, 1440))
    draw = ImageDraw.Draw(image)
    light = palette.get("mode") == "light"
    divider = palette["darker_background"] if light else "#333333"
    # A compact Hyprland-inspired bar. These are drawn previews, never configs.
    draw.rectangle((0, 0, 2560, 67), fill=palette["dark_background"])
    draw.line((0, 67, 2560, 67), fill=divider, width=1)
    emblem(draw, (42, 33), 20, palette["accent"], 0.8)
    text(draw, (81, 18), theme_name(palette), palette["foreground"], 28)
    for index in range(4):
        x = (284 if light else 218) + index * 54
        if index == 0:
            draw.rounded_rectangle((x - 10, 13, x + 31, 54), radius=6,
                                   fill=palette["selection"])
        text(draw, (x + 10, 22), str(index + 1),
             palette.get("selection_foreground", palette["foreground"]) if index == 0 else palette["muted"], 22,
             "mono", "mt")
    text(draw, (1280, 23), "FRI 27 NOV  /  09:41", palette["foreground"], 21, "mono", "mt")
    text(draw, (2518, 23), "NETWORK  ·  AUDIO  ·  100%", palette["muted"], 21, "mono", "rt")

    # Frame stays quiet, with a fine border and a little ambient shadow.
    box = (480, 315, 2080, 1140)
    draw.rounded_rectangle((492, 331, 2092, 1156), radius=14,
                           fill=palette["darker_background"] if light else "#090909")
    draw.rounded_rectangle(box, radius=13, fill=palette["background"],
                           outline=palette["hyprland_inactive_border"], width=2)
    draw.rounded_rectangle((482, 317, 2078, 381), radius=11,
                           fill=palette["lighter_background"])
    draw.rectangle((482, 351, 2078, 381), fill=palette["lighter_background"])
    text(draw, (1280, 336), theme_name(palette) + " / terminal", palette["foreground"], 22, "mono", "mt")
    for x in (1987, 2014, 2041):
        draw.ellipse((x, 340, x + 8, 348), fill=palette["muted"])
    draw.line((482, 382, 2078, 382), fill=divider, width=1)
    text(draw, (542, 432), "$ cat theme.txt", palette["green"], 28, "mono")
    emblem(draw, (752, 688), 130, palette["accent"], 2.0)
    text(draw, (976, 540), theme_title(palette), palette["bright_foreground"], 91, "sans")
    text(draw, (980, 651), "GREYSCALE TOPOGRAPHY", palette["muted"], 23, "mono")
    pairs = (
        ("palette", "neutral surfaces / clear signals", "cyan"),
        ("terrain", "ridge / peaks / basin", "blue"),
        ("source", "original procedural contours", "magenta"),
        ("status", "ready", "green"),
    )
    for index, (label, value, key) in enumerate(pairs):
        y = 718 + index * 48
        text(draw, (980, y), label, palette[key], 24, "mono")
        text(draw, (1134, y), value, palette["foreground"], 24, "mono")
    draw.line((542, 953, 2018, 953), fill=divider, width=1)
    text(draw, (542, 984), "ANSI", palette["muted"], 19, "mono")
    for index, key in enumerate(ANSI_KEYS):
        x = 652 + index * 80
        draw.rounded_rectangle((x, 982, x + 58, 1007), radius=3,
                               fill=palette[key], outline=palette["muted"])
    text(draw, (542, 1055), "$", palette["green"], 28, "mono")
    draw.rectangle((580, 1053, 594, 1080), fill=palette["foreground"])
    text(draw, (64, 1354), theme_name(palette).upper(), palette["foreground"], 23, "mono")
    text(draw, (64, 1391), "01 / LIGHT RIDGE" if light else "01 / DARK RIDGE", palette["muted"], 18, "mono")
    text(draw, (2496, 1391), "Original contours · 3840 × 2160", palette["muted"],
         18, "mono", "rt")
    save_png(image, ROOT / "preview.png")


def make_lock(palette: dict[str, str], logo: Image.Image) -> None:
    image = wallpaper((1920, 1080)).convert("RGBA")
    light = palette.get("mode") == "light"
    shade = Image.new("RGBA", image.size, (236, 235, 232, 104) if light else (0, 0, 0, 72))
    image = Image.alpha_composite(image, shade)
    draw = ImageDraw.Draw(image)
    text(draw, (960, 140), "09:41", palette["bright_foreground"], 122, "sans", "mt")
    text(draw, (960, 292), "FRIDAY / 27 NOVEMBER", palette["muted"], 20, "mono", "mt")
    image.alpha_composite(logo, (560, 403))
    draw = ImageDraw.Draw(image)
    text(draw, (960, 625), "Enter passphrase to unlock", palette["foreground"], 25, "sans", "mt")
    draw.rounded_rectangle((704, 683, 1216, 752), radius=10,
                           fill=palette["dark_background"], outline=palette["hyprland_inactive_border"], width=2)
    for x in (922, 947, 972, 997):
        draw.ellipse((x, 711, x + 8, 719), fill=palette["accent"])
    # Small boot indicator shows how the same transparent wordmark can sit
    # above Plymouth's progress feedback without copying upstream artwork.
    draw.line((864, 920, 1056, 920), fill=palette["darker_background"], width=2)
    draw.line((864, 920, 989, 920), fill=palette["accent"], width=2)
    text(draw, (960, 944), "Ready for the desktop", palette["muted"], 17, "mono", "mt")
    text(draw, (48, 1024), theme_name(palette).upper() + " / UNLOCK", palette["muted"], 17, "mono")
    text(draw, (1872, 1024), "CONTOUR STUDY 01", palette["muted"], 17, "mono", "rt")
    save_png(image.convert("RGB"), ROOT / "preview-unlock.png")


def make_wallpaper_previews() -> None:
    for path in sorted((ROOT / "backgrounds").glob("*.png")):
        with Image.open(path) as source:
            thumbnail = source.convert("RGB").resize((960, 540), LANCZOS)
        destination = ROOT / "previews" / (path.stem + ".jpg")
        thumbnail.save(destination, quality=88, subsampling=0, optimize=True)
        print(f"{destination.relative_to(ROOT)}: 960x540, {destination.stat().st_size:,} bytes")


def main() -> None:
    with (ROOT / "colors.toml").open("rb") as source:
        palette = tomllib.load(source)
    (ROOT / "previews").mkdir(exist_ok=True)
    make_palette(palette)
    logo = make_unlock(palette)
    make_wallpaper_previews()
    make_desktop(palette)
    make_lock(palette, logo)


if __name__ == "__main__":
    main()
