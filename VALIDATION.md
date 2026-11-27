# Topo validation report

**PASS — 44 checks passed, 0 failed.** Generated and checked offline against Omarchy commit `ecd8a5324ae5668695d4b8cd3a0bd4fe8c7bdf23`.

First clone Omarchy into `../omarchy` using the [README setup command](README.md#validate), then run:

```sh
python3 tools/generate_wallpapers.py
python3 tools/generate_previews.py
python3 tools/validate.py --upstream ../omarchy
```

Python 3.13.5, NumPy 2.5.5, Pillow 12.3.0. A second complete generation run produced identical SHA-256 hashes for all **22 generated assets**: six PNG wallpapers, six SVG sources, six JPEG thumbnails, the palette preview, the desktop preview, the unlock preview, and the transparent logo.

All six wallpapers and the desktop, unlock, and palette mockups were visually inspected. The Python sources compile successfully. Additional temporary fixtures exercised 17 repository scenarios and 10 CSS lexical cases: low contrast, missing palette keys, denied files, invalid TOML/INI/CSS, missing or malformed artwork, and email/hostname patterns (including Python f-string literals and URL domains resembling file suffixes). Expected failures were detected; temporary fixtures were removed. An independent review confirmed the CSS and privacy fixes.

## File inventory

Exact byte sizes, including this report. Git internals, environment-owned metadata directories, and ignored Python caches are not published assets.

**31 files, 7,066,193 bytes total.**

| File | Bytes |
| --- | ---: |
| [.gitignore](.gitignore) | 23 |
| [LICENSE](LICENSE) | 1,067 |
| [README.md](README.md) | 10,999 |
| [VALIDATION.md](VALIDATION.md) | 12,188 |
| [backgrounds/1-topo-dark-ridge.png](backgrounds/1-topo-dark-ridge.png) | 732,383 |
| [backgrounds/2-topo-dark-peaks.png](backgrounds/2-topo-dark-peaks.png) | 835,321 |
| [backgrounds/3-topo-dark-basin.png](backgrounds/3-topo-dark-basin.png) | 713,276 |
| [backgrounds/4-topo-light-ridge.png](backgrounds/4-topo-light-ridge.png) | 560,695 |
| [backgrounds/5-topo-light-peaks.png](backgrounds/5-topo-light-peaks.png) | 733,132 |
| [backgrounds/6-topo-light-basin.png](backgrounds/6-topo-light-basin.png) | 518,627 |
| [chromium.theme](chromium.theme) | 9 |
| [colors.toml](colors.toml) | 951 |
| [preview-unlock.png](preview-unlock.png) | 661,394 |
| [preview.png](preview.png) | 758,336 |
| [previews/1-topo-dark-ridge.jpg](previews/1-topo-dark-ridge.jpg) | 89,909 |
| [previews/2-topo-dark-peaks.jpg](previews/2-topo-dark-peaks.jpg) | 85,332 |
| [previews/3-topo-dark-basin.jpg](previews/3-topo-dark-basin.jpg) | 85,688 |
| [previews/4-topo-light-ridge.jpg](previews/4-topo-light-ridge.jpg) | 95,843 |
| [previews/5-topo-light-peaks.jpg](previews/5-topo-light-peaks.jpg) | 102,548 |
| [previews/6-topo-light-basin.jpg](previews/6-topo-light-basin.jpg) | 90,775 |
| [previews/palette.png](previews/palette.png) | 145,866 |
| [src/1-topo-dark-ridge.svg](src/1-topo-dark-ridge.svg) | 121,530 |
| [src/2-topo-dark-peaks.svg](src/2-topo-dark-peaks.svg) | 137,996 |
| [src/3-topo-dark-basin.svg](src/3-topo-dark-basin.svg) | 118,502 |
| [src/4-topo-light-ridge.svg](src/4-topo-light-ridge.svg) | 106,468 |
| [src/5-topo-light-peaks.svg](src/5-topo-light-peaks.svg) | 165,671 |
| [src/6-topo-light-basin.svg](src/6-topo-light-basin.svg) | 98,654 |
| [tools/generate_previews.py](tools/generate_previews.py) | 11,630 |
| [tools/generate_wallpapers.py](tools/generate_wallpapers.py) | 14,058 |
| [tools/validate.py](tools/validate.py) | 22,122 |
| [unlock.png](unlock.png) | 35,200 |

## Judgment calls and limits

- The upstream intersection is smaller than the initial assumption: 23/23 bundles ship `colors.toml` and `preview.png`; 22/23 ship `preview-unlock.png` and `unlock.png`, with `starship` the exception. Topo includes every requested asset regardless of that exception.
- Five optional palette roles found across bundled themes are included as neutral hex values. Explicit selection colours are supported and achieve 9.36:1. Muted/ANSI 8 is 6.43:1; the minimum among coloured ANSI entries is 7.04:1.
- A custom `btop.theme` would duplicate upstream templating, so none is shipped. `chromium.theme` is the requested single-line frame colour, `16,16,16`.
- The transparent logo uses the supported 800 × 188 convention. Both screen previews are illustrative Pillow mockups with synthetic content. Actual Plymouth uses a solid background plus the logo.
- Light wallpapers retain the requested warm off-white paper colour while the application palette stays dark. Fixed seeds and changed terrain parameters make all six designs distinct.
- SVG namespace dots are serialized as XML character references. XML parsers resolve the standard SVG namespace; published source text contains no literal external hostname. The privacy scan covers filenames, text and image metadata, with documented exceptions for code syntax/file suffixes, README URLs and the designated repository URL. It is a simple pattern check.
- Compatibility was checked from the supplied source and its colour resolver. A running Hyprland/Plymouth installation was not available for an end-to-end desktop test.
- All work stayed local. No package installation, network access, git write, commit, or push was performed. Artwork and source are original and MIT-licensed.

## Contrast table

| Role | Foreground | Background | Contrast | Minimum | Result |
| --- | --- | --- | ---: | ---: | --- |
| fg | #dedede | #101010 | 14.14:1 | 12.0:1 | PASS |
| muted | #969696 | #101010 | 6.43:1 | 4.5:1 | PASS |
| selection | #f5f5f5 | #414141 | 9.36:1 | 7.0:1 | PASS |
| accent | #dedede | #101010 | 14.14:1 | 4.5:1 | PASS |
| ANSI 0 (background) | #101010 | #101010 | n/a | n/a | background |
| ANSI 1 (red) | #b89595 | #101010 | 7.04:1 | 4.5:1 | PASS |
| ANSI 2 (green) | #9eaf99 | #101010 | 8.20:1 | 4.5:1 | PASS |
| ANSI 3 (yellow) | #b7ac8c | #101010 | 8.42:1 | 4.5:1 | PASS |
| ANSI 4 (blue) | #98a8bf | #101010 | 7.87:1 | 4.5:1 | PASS |
| ANSI 5 (magenta) | #b09db5 | #101010 | 7.55:1 | 4.5:1 | PASS |
| ANSI 6 (cyan) | #96b0b0 | #101010 | 8.28:1 | 4.5:1 | PASS |
| ANSI 7 (foreground) | #dedede | #101010 | 14.14:1 | 4.5:1 | PASS |
| ANSI 8 (muted) | #969696 | #101010 | 6.43:1 | 4.5:1 | PASS |
| ANSI 9 (bright_red) | #d0b0b0 | #101010 | 9.53:1 | 4.5:1 | PASS |
| ANSI 10 (bright_green) | #b8c9b2 | #101010 | 10.91:1 | 4.5:1 | PASS |
| ANSI 11 (bright_yellow) | #d0c5a7 | #101010 | 11.08:1 | 4.5:1 | PASS |
| ANSI 12 (bright_blue) | #b2c2d8 | #101010 | 10.51:1 | 4.5:1 | PASS |
| ANSI 13 (bright_magenta) | #cbb7d0 | #101010 | 10.17:1 | 4.5:1 | PASS |
| ANSI 14 (bright_cyan) | #b1caca | #101010 | 11.03:1 | 4.5:1 | PASS |
| ANSI 15 (bright_foreground) | #f5f5f5 | #101010 | 17.45:1 | 4.5:1 | PASS |

## Complete validator output

```text
Topo validation (offline)

PASS publishable files are regular files
PASS parsed upstream INSTALLED_THEME_DENIED: alacritty.toml, foot.ini, ghostty.conf, kitty.conf, vscode.json
INFO All *.lua files are also prohibited by the git-installed-theme rule.
PASS denied files absent
PASS bundled upstream themes discovered: 23
Bundled themes: catppuccin, catppuccin-latte, ethereal, everforest, flexoki-light, gruvbox, hackerman, jade-horse, kanagawa, last-horizon, lumon, lupine, matte-black, miasma, nord, retro-82, ristretto, rose-pine, solitude, starship, tokyo-night, vantablack, white

Allowed upstream file union:
| File | Bundles | Requirement | Topo |
| --- | ---: | --- | --- |
| btop.theme | 4/23 | optional | absent |
| chromium.theme | 5/23 | optional | present |
| colors.toml | 23/23 | required | present |
| keyboard.rgb | 2/23 | optional | absent |
| preview-unlock.png | 22/23 | optional | present |
| preview.png | 23/23 | required | present |
| shell.lock.toml | 1/23 | optional | absent |
| unlock.png | 22/23 | optional | present |
PASS all universally bundled allowed files present
Dropped upstream files (excluded from requirements):
  hyprland.lua: 5/23 bundles; prohibited
  neovim.lua: 14/23 bundles; prohibited
  vscode.json: 15/23 bundles; prohibited
INFO The starship bundle lacks unlock and unlock-preview assets; Topo checks those separately below.
PASS configuration syntax checked: 1 .toml, 0 .css, 0 .ini
PASS colors.toml parsed
PASS palette includes all 31 bundled-theme keys and explicit selection roles
PASS every palette color is #rrggbb
PASS palette mode = "dark"
PASS chromium.theme contains one RGB triplet
PASS contrast uses upstream omarchy-theme-color --all (resolved ANSI, fg, bg, muted)

| Role | Foreground | Background | Contrast | Minimum | Result |
| --- | --- | --- | ---: | ---: | --- |
| fg | #dedede | #101010 | 14.14:1 | 12.0:1 | PASS |
| muted | #969696 | #101010 | 6.43:1 | 4.5:1 | PASS |
| selection | #f5f5f5 | #414141 | 9.36:1 | 7.0:1 | PASS |
| accent | #dedede | #101010 | 14.14:1 | 4.5:1 | PASS |
| ANSI 0 (background) | #101010 | #101010 | n/a | n/a | background |
| ANSI 1 (red) | #b89595 | #101010 | 7.04:1 | 4.5:1 | PASS |
| ANSI 2 (green) | #9eaf99 | #101010 | 8.20:1 | 4.5:1 | PASS |
| ANSI 3 (yellow) | #b7ac8c | #101010 | 8.42:1 | 4.5:1 | PASS |
| ANSI 4 (blue) | #98a8bf | #101010 | 7.87:1 | 4.5:1 | PASS |
| ANSI 5 (magenta) | #b09db5 | #101010 | 7.55:1 | 4.5:1 | PASS |
| ANSI 6 (cyan) | #96b0b0 | #101010 | 8.28:1 | 4.5:1 | PASS |
| ANSI 7 (foreground) | #dedede | #101010 | 14.14:1 | 4.5:1 | PASS |
| ANSI 8 (muted) | #969696 | #101010 | 6.43:1 | 4.5:1 | PASS |
| ANSI 9 (bright_red) | #d0b0b0 | #101010 | 9.53:1 | 4.5:1 | PASS |
| ANSI 10 (bright_green) | #b8c9b2 | #101010 | 10.91:1 | 4.5:1 | PASS |
| ANSI 11 (bright_yellow) | #d0c5a7 | #101010 | 11.08:1 | 4.5:1 | PASS |
| ANSI 12 (bright_blue) | #b2c2d8 | #101010 | 10.51:1 | 4.5:1 | PASS |
| ANSI 13 (bright_magenta) | #cbb7d0 | #101010 | 10.17:1 | 4.5:1 | PASS |
| ANSI 14 (bright_cyan) | #b1caca | #101010 | 11.03:1 | 4.5:1 | PASS |
| ANSI 15 (bright_foreground) | #f5f5f5 | #101010 | 17.45:1 | 4.5:1 | PASS |
PASS contrast thresholds: fg 12:1, selection 7:1, muted/accent/ANSI 1–15 4.5:1
PASS six wallpapers present: 6
PASS backgrounds/1-topo-dark-ridge.png: 3840x2160, 732,383 bytes (minimum 4K, below 5 MB)
PASS matching source src/1-topo-dark-ridge.svg
PASS previews/1-topo-dark-ridge.jpg: 960x540 (expected 960x540)
PASS backgrounds/2-topo-dark-peaks.png: 3840x2160, 835,321 bytes (minimum 4K, below 5 MB)
PASS matching source src/2-topo-dark-peaks.svg
PASS previews/2-topo-dark-peaks.jpg: 960x540 (expected 960x540)
PASS backgrounds/3-topo-dark-basin.png: 3840x2160, 713,276 bytes (minimum 4K, below 5 MB)
PASS matching source src/3-topo-dark-basin.svg
PASS previews/3-topo-dark-basin.jpg: 960x540 (expected 960x540)
PASS backgrounds/4-topo-light-ridge.png: 3840x2160, 560,695 bytes (minimum 4K, below 5 MB)
PASS matching source src/4-topo-light-ridge.svg
PASS previews/4-topo-light-ridge.jpg: 960x540 (expected 960x540)
PASS backgrounds/5-topo-light-peaks.png: 3840x2160, 733,132 bytes (minimum 4K, below 5 MB)
PASS matching source src/5-topo-light-peaks.svg
PASS previews/5-topo-light-peaks.jpg: 960x540 (expected 960x540)
PASS backgrounds/6-topo-light-basin.png: 3840x2160, 518,627 bytes (minimum 4K, below 5 MB)
PASS matching source src/6-topo-light-basin.svg
PASS previews/6-topo-light-basin.jpg: 960x540 (expected 960x540)
PASS SVG sources present: 6
PASS SVG XML parsed: src/1-topo-dark-ridge.svg (121,530 bytes)
PASS SVG XML parsed: src/2-topo-dark-peaks.svg (137,996 bytes)
PASS SVG XML parsed: src/3-topo-dark-basin.svg (118,502 bytes)
PASS SVG XML parsed: src/4-topo-light-ridge.svg (106,468 bytes)
PASS SVG XML parsed: src/5-topo-light-peaks.svg (165,671 bytes)
PASS SVG XML parsed: src/6-topo-light-basin.svg (98,654 bytes)
PASS preview.png: 2560x1440 (expected 2560x1440)
PASS preview-unlock.png: 1920x1080 (expected 1920x1080)
PASS previews/palette.png: 1920x1510
PASS unlock.png: 800x188 RGBA, transparent background
PASS privacy scan of 31 publishable files: no email or hostname-like strings
INFO Privacy scope: filenames, text, Python comments/string literals, and decoded image metadata; excludes git/environment/cache metadata, recognized file suffixes, README URLs, and approved repository URL. SVG namespace dots are XML character references.

PASS Topo validation: 44 checks passed, 0 failed.
```
