#!/usr/bin/env python3
"""Validate Topo offline against a local Omarchy checkout.

Uses the standard library and Pillow. The deny list is parsed as literal data.
Only the color resolver and unchanged upstream look checker are executed. Privacy checks inspect text and
decoded image metadata, not compressed pixels. Python checks cover comments and
string literals, avoiding attribute-expression false positives.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import configparser
import io
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tokenize
import tomllib
import xml.etree.ElementTree as ET

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
THEME = "topo"
EXPECTED_MODE = "dark"
UPSTREAM_SHA = "cbd7139ac67b8ef421cf828507ac6f59e02c7c9b"
SKIP_DIRS = {".git", ".agents", ".codex", ".aws", "__pycache__"}
HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
ANSI_KEYS = (
    "background", "red", "green", "yellow", "blue", "magenta", "cyan",
    "foreground", "muted", "bright_red", "bright_green", "bright_yellow",
    "bright_blue", "bright_magenta", "bright_cyan", "bright_foreground",
)
BASE_KEYS = {
    "mode", "accent", "selection", "muted", "background", "dark_background",
    "darker_background", "lighter_background", "foreground", "dark_foreground",
    "light_foreground", "bright_foreground", "red", "yellow", "orange", "green",
    "cyan", "blue", "magenta", "brown", "bright_red", "bright_yellow",
    "bright_green", "bright_cyan", "bright_blue", "bright_magenta",
    "selection_foreground", "selection_background",
}
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w-])")
HOST = re.compile(r"(?<![\w.-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?![\w.-])")
URL = re.compile(r"https?://[^\s<>\"'\x60\)\]]+")
FILE_SUFFIXES = {
    "py", "pyc", "toml", "ini", "css", "conf", "json", "lua", "theme", "rgb",
    "png", "jpg", "jpeg", "webp", "svg", "md", "txt", "ttf", "otf", "tpl",
    "sh", "bash", "gitignore", "npy", "npz", "log", "xml", "yaml", "yml", "mode",
}
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
REMOVED_KEYS = {"active_border_color", "active_tab_background", "hyprland_active_border", "icon_mark"}
GITHUB_PREFIX = "https://" + "github" + ".com/"
MACHINE_PATHS = tuple("/" + part for part in ("workspace", "home", "tmp"))


class Report:
    def __init__(self, upstream: Path) -> None:
        self.failures = 0
        self.passes = 0
        self.paths = [(str(upstream), "<upstream>"), (str(ROOT), "<repo>")]

    def clean(self, message: str) -> str:
        for path, replacement in sorted(self.paths, key=lambda pair: len(pair[0]), reverse=True):
            message = message.replace(path, replacement)
        return message

    def check(self, ok: bool, message: str) -> bool:
        print(f"{'PASS' if ok else 'FAIL'} {self.clean(message)}")
        self.passes += bool(ok)
        self.failures += not ok
        return ok

    def info(self, message: str) -> None:
        print(f"INFO {self.clean(message)}")


def repo_files(root: Path) -> list[Path]:
    """List publishable files without traversing metadata or symlinks."""
    found = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        found.extend(Path(directory) / name for name in dirs if name not in SKIP_DIRS and (Path(directory) / name).is_symlink())
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix != ".pyc":
                found.append(path)
    return sorted(found)


def read_denied(upstream: Path) -> set[str]:
    source = (upstream / "bin/omarchy-theme-set").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^\s*INSTALLED_THEME_DENIED\s*=\s*\((.*?)\)", source)
    if not match:
        raise ValueError("cannot find literal INSTALLED_THEME_DENIED array")
    values = shlex.split(match.group(1), comments=True, posix=True)
    if not values or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in values):
        raise ValueError("deny list is not a nonempty literal filename array")
    return set(values)


def is_denied(name: str, denied: set[str]) -> bool:
    return name in denied or name.endswith(".lua")


def check_upstream(upstream: Path, files: list[Path], report: Report) -> set[str]:
    """Inspect bundled inventories; these are not a theme-copy allowlist."""
    try:
        result = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10, check=True)
        report.check(result.stdout.strip() == UPSTREAM_SHA, f"upstream HEAD matches pinned {UPSTREAM_SHA}")
    except (OSError, subprocess.SubprocessError) as exc:
        report.check(False, f"cannot verify pinned upstream HEAD: {exc}")
    try:
        denied = read_denied(upstream)
    except (OSError, ValueError) as exc:
        report.check(False, f"upstream deny-list parsing: {exc}")
        denied = set()
    else:
        report.check(True, "parsed upstream INSTALLED_THEME_DENIED: " + ", ".join(sorted(denied)))
    report.info("All top-level *.lua files are also denied; upstream recursively copies other non-symlink entries, including source, previews and tools.")
    forbidden = [str(p.relative_to(ROOT)) for p in files if p.parent == ROOT and is_denied(p.name, denied)]
    report.check(not forbidden, "denied top-level files absent" + (": " + ", ".join(forbidden) if forbidden else ""))
    themes_path = upstream / "themes"
    themes = sorted(p for p in themes_path.iterdir() if p.is_dir()) if themes_path.is_dir() else []
    if not report.check(bool(themes), f"bundled upstream themes discovered: {len(themes)}"):
        return set()
    counts: Counter[str] = Counter()
    dropped: Counter[str] = Counter()
    keys = set()
    print("Bundled themes: " + ", ".join(theme.name for theme in themes))
    for theme in themes:
        for path in repo_files(theme):
            relative = path.relative_to(theme).as_posix()
            (dropped if path.parent == theme and is_denied(path.name, denied) else counts)[relative] += 1
        try:
            keys.update(tomllib.loads((theme / "colors.toml").read_text(encoding="utf-8")))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            report.check(False, f"reference palette {theme.name}: {exc}")
    print("\nBundled upstream inventory (observation, not a copy allowlist):")
    print(f"| File | Bundles | Requirement | {THEME} |")
    print("| --- | ---: | --- | --- |")
    missing = []
    for relative, count in sorted(counts.items()):
        required = count == len(themes)
        present = (ROOT / relative).is_file()
        print(f"| {relative} | {count}/{len(themes)} | {'required' if required else 'optional'} | {'present' if present else 'absent'} |")
        if required and not present:
            missing.append(relative)
    report.check(not missing, "all universally bundled non-denied files present" + (": missing " + ", ".join(missing) if missing else ""))
    print("Dropped upstream files (excluded from requirements):")
    for relative, count in sorted(dropped.items()):
        print(f"  {relative}: {count}/{len(themes)} bundles; prohibited")
    if "starship" in {p.name for p in themes}:
        report.info("The starship bundle lacks unlock and unlock-preview assets; this validator checks those separately below.")
    return keys - REMOVED_KEYS


def check_css(text: str) -> None:
    """Basic lexical CSS check: comments, strings, braces, and declarations."""
    cleaned = []
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("unclosed CSS comment")
            cleaned.append(" ")
            index = end + 2
        elif text.startswith("*/", index):
            raise ValueError("stray CSS comment terminator")
        elif text[index] in "\"'":
            quote = text[index]
            index += 1
            while index < len(text) and text[index] != quote:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] in "\r\n":
                    raise ValueError("unescaped newline in CSS string")
                index += 1
            if index >= len(text):
                raise ValueError("unclosed CSS string")
            index += 1
            cleaned.append("STRING")
        else:
            cleaned.append(text[index])
            index += 1
    text = "".join(cleaned)
    if re.search(r"[\x00-\x08\x0b\x0e-\x1f\x60\\]", text):
        raise ValueError("stray CSS character")
    brackets, blocks = [], []
    fragment = ""

    def declaration(value: str, in_block: bool) -> None:
        value = value.strip()
        if not value:
            return
        if value.startswith("@"):
            if not re.fullmatch(r"@[\w-]+(?:\s+[^{};]+)?", value):
                raise ValueError("invalid CSS at-rule")
        elif not in_block or not re.fullmatch(r"(?:--)?[A-Za-z_][\w-]*\s*:\s*[^{};]+", value):
            raise ValueError(f"stray CSS text or invalid declaration: {value[:60]}")

    for char in text:
        if char in "([":
            brackets.append(char)
        elif char in ")]":
            if not brackets or brackets.pop() != {')': '(', ']': '['}[char]:
                raise ValueError("unbalanced CSS parentheses or brackets")
        if char == "{" and not brackets:
            selector = fragment.strip()
            if not selector or not re.fullmatch(r"[\w\s#.:*>+~,\[\]|=^$%()_'\"/@&-]+", selector):
                raise ValueError("missing selector or stray CSS selector character")
            blocks.append(selector)
            fragment = ""
        elif char == "}" and not brackets:
            if not blocks:
                raise ValueError("unbalanced CSS closing brace")
            declaration(fragment, True)
            blocks.pop()
            fragment = ""
        elif char == ";" and not brackets:
            declaration(fragment, bool(blocks))
            fragment = ""
        else:
            fragment += char
    if brackets or blocks:
        raise ValueError("unclosed CSS brace, bracket, or parenthesis")
    if fragment.strip():
        raise ValueError("stray CSS text after last rule")


def check_configs(files: list[Path], reference_keys: set[str], report: Report) -> dict[str, str]:
    counts = Counter()
    palette = {}
    for path in files:
        kind = path.suffix.lower()
        if kind not in {".toml", ".css", ".ini"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if kind == ".toml":
                parsed = tomllib.loads(text)
                if path == ROOT / "colors.toml":
                    palette = parsed
            elif kind == ".ini":
                parser = configparser.ConfigParser(interpolation=None, strict=True)
                parser.read_string(text)
            else:
                check_css(text)
            counts[kind] += 1
        except (OSError, UnicodeError, ValueError, configparser.Error) as exc:
            report.check(False, f"parse {path.relative_to(ROOT)}: {exc}")
    report.check(True, "configuration syntax checked: " + ", ".join(f"{counts[suffix]} {suffix}" for suffix in (".toml", ".css", ".ini")))
    if not report.check(bool(palette), "colors.toml parsed"):
        return {}
    missing = (BASE_KEYS | reference_keys) - palette.keys()
    report.check(not missing, f"palette includes all {len(reference_keys)} supported bundled-theme keys and explicit selection roles" + (": missing " + ", ".join(sorted(missing)) if missing else ""))
    removed = REMOVED_KEYS & palette.keys()
    report.check(not removed, "dead, redundant, and derived palette overrides absent" + (": " + ", ".join(sorted(removed)) if removed else ""))
    invalid = [key for key, value in palette.items() if key != "mode" and (not isinstance(value, str) or not HEX.fullmatch(value))]
    report.check(not invalid, "every palette color is #rrggbb" + (": invalid " + ", ".join(invalid) if invalid else ""))
    report.check(palette.get("mode") == EXPECTED_MODE, f'palette mode = "{EXPECTED_MODE}"')
    try:
        text = (ROOT / "chromium.theme").read_text(encoding="utf-8")
        values = text.strip().split(",")
        valid = len(text.splitlines()) == 1 and len(values) == 3 and all(re.fullmatch(r"\d{1,3}", v) and 0 <= int(v) <= 255 for v in values)
        report.check(valid, "chromium.theme contains one RGB triplet")
        if valid and HEX.fullmatch(palette.get("background", "")):
            expected = [int(palette["background"][i:i + 2], 16) for i in (1, 3, 5)]
            report.check([int(value) for value in values] == expected, "chromium.theme matches background RGB")
    except OSError as exc:
        report.check(False, f"chromium.theme: {exc}")
    return palette


def fallback_palette(raw: dict[str, str]) -> dict[str, str]:
    """Resolve the explicit semantic Topo palette without Bash."""
    palette = dict(raw)
    for number, key in enumerate(ANSI_KEYS):
        palette[f"color{number}"] = raw.get(f"color{number}", raw.get(key, ""))
    palette["bg"] = raw.get("background", raw.get("color0", ""))
    palette["fg"] = raw.get("foreground", raw.get("color7", ""))
    palette["color0"] = palette["bg"]
    palette["color7"] = palette["fg"]
    palette.setdefault("selection_background", raw.get("selection", ""))
    palette.setdefault("selection_foreground", raw.get("bright_foreground", ""))
    return palette


def resolve_palette(raw: dict[str, str], upstream: Path, report: Report) -> dict[str, str]:
    script = upstream / "bin/omarchy-theme-color"
    bash = shutil.which("bash")
    if not bash or not script.is_file():
        report.info("Bash or upstream color resolver unavailable; contrast uses explicit semantic palette fallback.")
        return fallback_palette(raw)
    environment = os.environ.copy()
    environment["OMARCHY_PATH"] = str(upstream)
    try:
        result = subprocess.run(
            [bash, str(script), "--file", str(ROOT / "colors.toml"), "--all"],
            env=environment, text=True, capture_output=True, timeout=30, check=True,
        )
        resolved = dict(line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)
        expected = {"fg", "bg", "muted", "accent", "selection_foreground", "selection_background"} | {f"color{i}" for i in range(16)}
        invalid = [key for key in sorted(expected) if not HEX.fullmatch(resolved.get(key, ""))]
        if invalid:
            raise ValueError("missing or invalid resolved colors: " + ", ".join(invalid))
        if result.stderr.strip():
            raise ValueError("resolver reported diagnostics")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report.check(False, f"upstream color resolver failed: {exc}")
        report.info("Raw semantic palette used only to complete the diagnostic contrast table.")
        return fallback_palette(raw)
    report.check(True, "contrast uses upstream omarchy-theme-color --all (resolved ANSI, fg, bg, muted)")
    return resolved


def luminance(color: str) -> float:
    components = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in components]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(foreground: str, background: str) -> float:
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def check_contrast(palette: dict[str, str], report: Report) -> None:
    rows = [("fg", "fg", "bg", 7.0), ("muted", "muted", "bg", 4.5),
            ("selection fg", "selection_foreground", "selection_background", 4.5),
            ("fg on selection", "fg", "selection", 4.5),
            ("muted on selection", "muted", "selection_background", 4.5),
            ("accent", "accent", "bg", 3.0),
            ("dark_foreground", "dark_foreground", "bg", 3.0)]
    if "hyprland_inactive_border" in palette:
        rows.append(("inactive border", "hyprland_inactive_border", "bg", 3.0))
    rows += [(f"ANSI {i} ({ANSI_KEYS[i]})", f"color{i}", "bg", 0 if i == 0 else 4.5) for i in range(16)]
    print("\n| Role | Foreground | Background | Contrast | Minimum | Result |")
    print("| --- | --- | --- | ---: | ---: | --- |")
    failed = []
    for label, key, bg_key, minimum in rows:
        fg, bg = palette.get(key, ""), palette.get(bg_key, "")
        if not isinstance(fg, str) or not isinstance(bg, str) or not HEX.fullmatch(fg) or not HEX.fullmatch(bg):
            failed.append(label)
            print(f"| {label} | {fg or 'missing'} | {bg or 'missing'} | n/a | {minimum:.1f}:1 | FAIL |")
        elif not minimum:
            print(f"| {label} | {fg} | {bg} | n/a | n/a | background |")
        else:
            ratio = contrast(fg, bg)
            ok = ratio >= minimum
            if not ok:
                failed.append(label)
            print(f"| {label} | {fg} | {bg} | {ratio:.2f}:1 | {minimum:.1f}:1 | {'PASS' if ok else 'FAIL'} |")
    report.check(not failed, "contrast thresholds: fg 7:1; muted, selection text and ANSI 1–15 4.5:1; accent, dark_foreground and inactive border 3:1" + (": " + ", ".join(failed) if failed else ""))


def lab(color: str) -> tuple[float, float, float]:
    """CIELAB D65, sRGB transfer function and the standard 2-degree observer."""
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    xyz = ((0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047,
           0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
           (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883)
    delta = 6 / 29
    x, y, z = [v ** (1 / 3) if v > delta ** 3 else v / (3 * delta ** 2) + 4 / 29 for v in xyz]
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def check_chroma(palette: dict[str, str], report: Report) -> None:
    print("\nCIELAB D65 chroma and relative luminance:")
    print("| Role | Hex | L* | C* | Relative luminance | Minimum C* | Result |")
    print("| --- | --- | ---: | ---: | ---: | ---: | --- |")
    failed = []
    roles = ("red", "green", "cyan", "yellow", "blue", "magenta",
             "bright_red", "bright_green", "bright_cyan", "bright_yellow", "bright_blue", "bright_magenta", "orange", "brown")
    for key in roles:
        color = palette.get(key, "")
        minimum = 25 if key.removeprefix("bright_") in {"red", "green"} else 20 if key.removeprefix("bright_") == "cyan" else 0
        if not HEX.fullmatch(color):
            failed.append(key)
            print(f"| {key} | missing/invalid | n/a | n/a | n/a | {minimum or 'diagnostic'} | FAIL |")
            continue
        lightness, a, b = lab(color)
        chroma = math.hypot(a, b)
        ok = chroma >= minimum
        if not ok:
            failed.append(key)
        print(f"| {key} | {color} | {lightness:.2f} | {chroma:.2f} | {luminance(color):.4f} | {minimum or 'diagnostic'} | {'PASS' if ok else 'FAIL'} |")
    report.check(not failed, "red/green C* >=25 and cyan C* >=20, normal and bright" + (": " + ", ".join(failed) if failed else ""))
    minimum = 1.4 if EXPECTED_MODE == "dark" else 1.3
    print("\n| Red/green pair | Green / red luminance | Minimum | Result |")
    print("| --- | ---: | ---: | --- |")
    separation = []
    for prefix in ("", "bright_"):
        red, green = palette.get(prefix + "red", ""), palette.get(prefix + "green", "")
        valid = bool(HEX.fullmatch(red) and HEX.fullmatch(green))
        ratio = luminance(green) / max(luminance(red), 1e-12) if valid else 0
        ok = valid and ratio >= minimum
        label = "bright" if prefix else "normal"
        print(f"| {label} | {ratio:.3f} | {minimum:.1f} | {'PASS' if ok else 'FAIL'} |")
        separation.append((ok, label))
    for ok, label in separation:
        report.check(ok, f"{label} red/green luminance separation >= {minimum:.1f}")
    print("\n| Distinctness diagnostic | Delta E76 |")
    print("| --- | ---: |")
    for first, second in [(key, "bright_" + key) for key in ("red", "green", "yellow", "blue", "magenta", "cyan")] + [("orange", "brown")]:
        if HEX.fullmatch(palette.get(first, "")) and HEX.fullmatch(palette.get(second, "")):
            distance = math.dist(lab(palette[first]), lab(palette[second]))
            print(f"| {first} / {second} | {distance:.2f} |")


def check_image_size(path: Path, expected: tuple[int, int] | None, report: Report) -> None:
    try:
        with Image.open(path) as image:
            image.load()
            size = image.size
        report.check(expected is None or size == expected, f"{path.relative_to(ROOT)}: {size[0]}x{size[1]}" + (f" (expected {expected[0]}x{expected[1]})" if expected else ""))
    except (OSError, ValueError) as exc:
        report.check(False, f"image {path.relative_to(ROOT)}: {exc}")


def check_images(report: Report) -> None:
    backgrounds = sorted(p for p in (ROOT / "backgrounds").glob("*") if p.is_file())
    stems = {f"{number}-topo-{EXPECTED_MODE}-{design}" for number, design in enumerate(("ridge", "peaks", "basin"), 1)}
    report.check({path.name for path in backgrounds} == {stem + ".png" for stem in stems}, f"exactly three {EXPECTED_MODE} wallpapers present: {len(backgrounds)}")
    for path in backgrounds:
        relative = path.relative_to(ROOT)
        try:
            with Image.open(path) as image:
                image.load()
                size = image.size
                stats = ImageStat.Stat(image.convert("RGB"))
                mean = sum(stats.mean) / 3 / 255
                variance = sum(value * value for value in stats.rms) / 3 / 255 ** 2 - mean ** 2
                stddev = math.sqrt(max(0, variance))
            length = path.stat().st_size
            report.check(size[0] >= 3840 and size[1] >= 2160 and length < 5_000_000,
                         f"{relative}: {size[0]}x{size[1]}, {length:,} bytes (minimum 4K, below 5 MB)")
            report.info(f"{relative}: normalized RGB mean {mean:.6f}, standard deviation {stddev:.6f}")
        except (OSError, ValueError) as exc:
            report.check(False, f"wallpaper {relative}: {exc}")
        source = ROOT / "src" / (path.stem + ".svg")
        report.check(source.is_file(), f"matching source {source.relative_to(ROOT)}")
        thumbnail = ROOT / "previews" / (path.stem + ".jpg")
        if not thumbnail.exists():
            thumbnail = thumbnail.with_suffix(".png")
        check_image_size(thumbnail, (960, 540), report)
    sources = sorted((ROOT / "src").glob("*.svg"))
    report.check({path.stem for path in sources} == stems, f"exactly three matching SVG sources present: {len(sources)}")
    thumbnails = sorted((ROOT / "previews").glob("*.jpg"))
    report.check({path.stem for path in thumbnails} == stems, f"exactly three matching JPG thumbnails present: {len(thumbnails)}")
    for path in sources:
        try:
            tree = ET.parse(path)
            valid = tree.getroot().tag == "{" + SVG_NAMESPACE + "}svg" and f'xmlns="{SVG_NAMESPACE}"' in path.read_text(encoding="utf-8")
            report.check(valid, f"SVG XML parsed: {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")
            if path.stat().st_size >= 1_500_000:
                report.info(f"{path.name} exceeds the 1.5 MB optimization target.")
        except (OSError, ET.ParseError) as exc:
            report.check(False, f"SVG XML {path.relative_to(ROOT)}: {exc}")
    check_image_size(ROOT / "preview.png", (2560, 1440), report)
    check_image_size(ROOT / "preview-unlock.png", (1920, 1080), report)
    check_image_size(ROOT / "previews/palette.png", (960, 540), report)
    try:
        with Image.open(ROOT / "unlock.png") as image:
            image.load()
            valid = image.size == (800, 188) and image.mode == "RGBA"
            transparent = image.mode == "RGBA" and image.getextrema()[3][0] == 0
            report.check(valid and transparent, f"unlock.png: {image.width}x{image.height} {image.mode}, transparent background")
    except (OSError, ValueError) as exc:
        report.check(False, f"unlock.png: {exc}")


def privacy_texts(path: Path) -> list[str]:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        with Image.open(path) as image:
            metadata = list(image.info.values()) + list(image.getexif().values())
        return [value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value) for value in metadata]
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [chunk.decode("ascii") for chunk in re.findall(rb"[\x20-\x7e]{8,}", data)]
    if path.suffix == ".py" or path.name == "magick":
        parts = []
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in {tokenize.COMMENT, getattr(tokenize, "FSTRING_MIDDLE", -1)}:
                parts.append(token.string)
            elif token.type == tokenize.STRING:
                try:
                    value = ast.literal_eval(token.string)
                    parts.append(value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value))
                except (ValueError, SyntaxError):
                    parts.append(token.string)
        return parts
    return [text]


def check_privacy(files: list[Path], report: Report) -> None:
    findings = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.is_symlink():
            findings.append(f"{relative}: symbolic link")
            continue
        try:
            for text in [relative, *privacy_texts(path)]:
                if EMAIL.search(text):
                    findings.append(f"{relative}: email-like string")
                if any(re.search(re.escape(prefix) + r"(?:/|\b)", text) for prefix in MACHINE_PATHS):
                    findings.append(f"{relative}: absolute machine path")

                def approved_url(match: re.Match[str]) -> str:
                    url = match.group(0).rstrip(".,:;")
                    if url == SVG_NAMESPACE:
                        return ""
                    if path.suffix.lower() == ".md" and url.startswith(GITHUB_PREFIX):
                        tail = url[len(GITHUB_PREFIX):]
                        if re.fullmatch(r"(?:Jsmith8778(?:/[A-Za-z0-9_.~/#-]*)?|basecamp/omarchy(?:\.git)?(?:/[A-Za-z0-9_.~/#-]*)?)", tail):
                            return ""
                    findings.append(f"{relative}: unapproved URL")
                    return match.group(0)

                text = URL.sub(approved_url, text)
                for match in HOST.finditer(text):
                    if match.group(0).rsplit(".", 1)[-1].lower() not in FILE_SUFFIXES:
                        findings.append(f"{relative}: hostname-like string")
                        break
        except (OSError, ValueError, SyntaxError, tokenize.TokenError) as exc:
            findings.append(f"{relative}: cannot inspect ({type(exc).__name__})")
    report.check(not findings, f"privacy scan of {len(files)} publishable files" + (": " + "; ".join(sorted(set(findings))) if findings else ": no email, unapproved hostname, or absolute machine path"))
    report.info("Privacy scope: filenames, text, Python comments/string literals, and decoded image metadata; excludes git/environment/cache metadata and recognized file suffixes. URL exceptions: exact W3C SVG namespace; GitHub owner and upstream repository links in Markdown docs only.")


def check_look(upstream: Path, report: Report) -> None:
    """Run the pinned upstream checker unchanged, with a limited Pillow fallback."""
    environment = os.environ.copy()
    magick = shutil.which("magick")
    shim = ROOT / "tools/magick_shim/magick"
    using_shim = not magick or Path(magick).resolve() == shim.resolve()
    if using_shim:
        if not report.check(shim.is_file() and os.access(shim, os.X_OK), "Pillow magick shim is executable"):
            return
        environment["PATH"] = str(shim.parent) + os.pathsep + environment.get("PATH", "")
        report.info("look-check magick: Pillow shim (tools/magick_shim/magick); RGB image statistics and background crop only; drawing operations ignored.")
    else:
        report.info("look-check magick: real ImageMagick found on PATH; full upstream preview rendering.")
    script = upstream / "bin/omarchy-agent-look-theme"
    with tempfile.TemporaryDirectory(prefix=THEME + "-look-") as directory:
        output = Path(directory) / "look.png"
        report.paths.extend([(str(output), "<tempfile>"), (directory, "<temporary-directory>")])
        try:
            result = subprocess.run([sys.executable, str(script), str(ROOT), "--out", str(output)],
                                    env=environment, capture_output=True, text=True, timeout=180)
            print("\nUpstream look-check output:")
            print(report.clean(result.stdout.rstrip()))
            if result.stderr.strip():
                report.info("look-check stderr: " + result.stderr.strip())
            report.check(result.returncode == 0 and "problems: none" in result.stdout.splitlines(),
                         f"unmodified upstream look check: exit {result.returncode}, problems: " + ("none" if "problems: none" in result.stdout.splitlines() else "reported"))
            try:
                with Image.open(output) as image:
                    image.load()
                    report.check(image.size == (1280, 720), "upstream look-check output image: 1280x720")
            except (OSError, ValueError) as exc:
                report.check(False, f"upstream look-check output image: {exc}")
        except (OSError, subprocess.SubprocessError) as exc:
            report.check(False, f"upstream look check could not run: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True, help="read-only local Omarchy checkout")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    report = Report(upstream)
    print(f"{THEME} validation (offline)\n")
    files = repo_files(ROOT)
    symlinks = [str(path.relative_to(ROOT)) for path in files if path.is_symlink()]
    report.check(not symlinks, "publishable files are regular files" + (": symlinks " + ", ".join(symlinks) if symlinks else ""))
    reference_keys = check_upstream(upstream, files, report)
    raw = check_configs(files, reference_keys, report)
    if raw:
        resolved = resolve_palette(raw, upstream, report)
        check_contrast(resolved, report)
        check_chroma(resolved, report)
        if "hyprland_inactive_border" in raw:
            try:
                template = (upstream / "default/themed/hyprland.lua.tpl").read_text(encoding="utf-8")
                report.check("{{ hypr_gradient hyprland_inactive_border " in template, "retained hyprland_inactive_border is consumed by upstream template")
            except OSError as exc:
                report.check(False, f"inactive-border consumer: {exc}")
    check_images(report)
    check_look(upstream, report)
    check_privacy(files, report)
    print(f"\n{'FAIL' if report.failures else 'PASS'} {THEME} validation: {report.passes} checks passed, {report.failures} failed.")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
