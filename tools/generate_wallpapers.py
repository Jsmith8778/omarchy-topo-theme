#!/usr/bin/env python3
"""Generate six original Topo terrains using only NumPy and Pillow.

Run: python3 tools/generate_wallpapers.py
Optional: --only 1-topo-dark-ridge (one exact output stem).

Each scalar field is evaluated on the complete 3840 x 2160 pixel grid. Rotated
Gaussians form the land; four octaves of quintic-interpolated value noise add
broad, smooth irregularity. Marching squares uses shared integer edge IDs and
an asymptotic saddle decider to stitch continuous contours. Ramer-Douglas-
Peucker simplification, two Chaikin passes, and a final simplification yield
compact polylines. The very same rounded coordinates feed SVG and Pillow.
Every fifth elevation is an index contour. No external artwork is used.

Seeds, terrain parameters, noise interpolation and levels are fixed here.
No image metadata, timestamps or machine information are embedded. Pixel
output is deterministic with the same NumPy and Pillow versions. PNGs use
lossless 8-bit luminance (dark) or an exact 256-entry colour ramp (light).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 3840, 2160
SCALE = 2
SVG_NAMESPACE = "http://www&#46;w3&#46;org/2000/svg"


@dataclass(frozen=True)
class Design:
    stem: str
    seed: int
    terrain: str
    levels: int
    light: bool = False


DESIGNS = (
    Design("1-topo-dark-ridge", 2701, "ridge", 52),
    Design("2-topo-dark-peaks", 2702, "peaks", 43),
    Design("3-topo-dark-basin", 2703, "basin", 60),
    Design("4-topo-light-ridge", 2704, "ridge", 47, True),
    Design("5-topo-light-peaks", 2705, "peaks", 56, True),
    Design("6-topo-light-basin", 2706, "basin", 50, True),
)


def value_noise(rng: np.random.Generator, columns: int, rows: int) -> np.ndarray:
    """Quintic interpolation of a coarse random lattice over the full grid."""
    lattice = rng.uniform(-1, 1, (rows + 1, columns + 1)).astype(np.float32)
    x = np.linspace(0, columns, WIDTH, endpoint=False, dtype=np.float32)
    y = np.linspace(0, rows, HEIGHT, endpoint=False, dtype=np.float32)
    ix, iy = x.astype(np.int32), y.astype(np.int32)
    fx, fy = x - ix, y - iy
    fx = (fx ** 3 * (fx * (fx * 6 - 15) + 10)).astype(np.float32)
    fy = (fy ** 3 * (fy * (fy * 6 - 15) + 10)).astype(np.float32)
    top = lattice[iy[:, None], ix] * (1 - fx) + lattice[iy[:, None], ix + 1] * fx
    bottom = lattice[iy[:, None] + 1, ix] * (1 - fx) + lattice[iy[:, None] + 1, ix + 1] * fx
    return top * (1 - fy[:, None]) + bottom * fy[:, None]


def terrain_field(design: Design) -> np.ndarray:
    """Coordinates span screen aspect ratio, so Gaussian dimensions are isotropic."""
    aspect = WIDTH / HEIGHT
    x = np.linspace(-aspect, aspect, WIDTH, dtype=np.float32)[None, :]
    y = np.linspace(-1, 1, HEIGHT, dtype=np.float32)[:, None]
    if design.terrain == "ridge":
        hills = [
            (1.10, -1.10, .48, 1.08, .39, -.52),
            (.95, .20, -.10, .94, .42, -.62),
            (.90, 1.25, -.68, .80, .34, -.40),
            (-.45, -.75, -.92, .65, .40, .15),
            (-.35, 1.30, .85, .65, .49, -.2),
        ]
    elif design.terrain == "peaks":
        hills = [
            (1.15, -1.05, -.48, .55, .42, .30),
            (.92, .18, .58, .52, .38, -.45),
            (1.30, 1.17, -.42, .59, .46, -.52),
            (.57, -1.55, .98, .65, .40, -.25),
            (-.38, -.04, -.65, .48, .52, .15),
            (-.20, 1.65, .95, .51, .50, 0),
        ]
    else:
        hills = [
            (-1.60, .28, .03, 1.13, .65, -.30),
            (.85, -1.62, -.83, .83, .52, -.45),
            (.72, 1.60, .90, .85, .43, -.50),
            (.43, -.65, 1.20, .65, .45, .30),
            (.38, .80, -1.10, .65, .42, -.40),
        ]
    field = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    for amplitude, cx, cy, sx, sy, angle in hills:
        # Light variants have different terrain as well as different noise.
        if design.light:
            cx = -cx + .13
            cy = cy - .09
            angle = -angle + .12
        cosine, sine = np.cos(angle), np.sin(angle)
        rx = (x - cx) * cosine + (y - cy) * sine
        ry = -(x - cx) * sine + (y - cy) * cosine
        field += (amplitude * np.exp(-.5 * ((rx / sx) ** 2 + (ry / sy) ** 2))).astype(np.float32)
    rng = np.random.default_rng(design.seed)
    for columns, rows, amplitude in [(5, 3, .115), (10, 6, .052), (20, 12, .018), (40, 24, .005)]:
        field += amplitude * value_noise(rng, columns, rows)
    field -= field.min()
    field /= field.max()
    return field


def marching_squares(field: np.ndarray, level: float) -> list[np.ndarray]:
    """Vectorized cell classification, exact shared edges, then graph traversal.

    Corner bits: TL=1, TR=2, BR=4, BL=8. Edges: top=0, right=1,
    bottom=2, left=3. Saddle connectivity follows the bilinear determinant.
    """
    high = field >= level
    cases = (high[:-1, :-1].astype(np.uint8)
             | (high[:-1, 1:].astype(np.uint8) << 1)
             | (high[1:, 1:].astype(np.uint8) << 2)
             | (high[1:, :-1].astype(np.uint8) << 3))
    yy, xx = np.nonzero((cases != 0) & (cases != 15))
    kind = cases[yy, xx]
    del high, cases
    if not len(xx):
        return []
    lookup = np.array([
        [-1, -1], [0, 3], [0, 1], [1, 3], [1, 2], [0, 1], [0, 2], [2, 3],
        [2, 3], [0, 2], [0, 1], [1, 2], [1, 3], [0, 1], [0, 3], [-1, -1]
    ], dtype=np.int8)
    pairs = lookup[kind]
    saddle = np.flatnonzero((kind == 5) | (kind == 10))
    if len(saddle):
        sy, sx = yy[saddle], xx[saddle]
        q = ((field[sy, sx] - level) * (field[sy + 1, sx + 1] - level)
             - (field[sy, sx + 1] - level) * (field[sy + 1, sx] - level))
        positive = q >= 0
        pairs[saddle] = np.where(positive[:, None], [0, 1], [0, 3])
        second = np.where(positive[:, None], [2, 3], [1, 2])
        xx = np.concatenate((xx, sx))
        yy = np.concatenate((yy, sy))
        pairs = np.concatenate((pairs, second))
    edge = pairs.ravel()
    xx = np.repeat(xx, 2)
    yy = np.repeat(yy, 2)
    horizontal = (edge == 0) | (edge == 2)
    ex = xx + (edge == 1)
    ey = yy + (edge == 2)
    ids = np.where(horizontal, ey * (WIDTH - 1) + ex,
                   HEIGHT * (WIDTH - 1) + ey * WIDTH + ex)
    ax, ay = ex, ey
    bx = ex + horizontal
    by = ey + ~horizontal
    a = field[ay, ax].astype(np.float64)
    b = field[by, bx].astype(np.float64)
    fraction = (level - a) / (b - a)
    vertices = np.column_stack((ex + horizontal * fraction, ey + ~horizontal * fraction))
    # Every endpoint is shared by its integer grid edge, never by float rounding.
    unique, first, inverse = np.unique(ids, return_index=True, return_inverse=True)
    coordinates = vertices[first]
    adjacency: dict[int, list[int]] = defaultdict(list)
    for a_id, b_id in inverse.reshape(-1, 2).tolist():
        adjacency[a_id].append(b_id)
        adjacency[b_id].append(a_id)
    visited = np.zeros(len(unique), dtype=bool)
    paths = []
    starts = [key for key, neighbors in adjacency.items() if len(neighbors) == 1]
    starts.extend(adjacency)
    for start in starts:
        if visited[start]:
            continue
        indices = [start]
        previous, current = -1, start
        while True:
            visited[current] = True
            following = [v for v in adjacency[current] if v != previous]
            if not following:
                break
            nxt = following[0]
            if nxt == start:
                indices.append(start)
                break
            if visited[nxt]:
                break
            indices.append(nxt)
            previous, current = current, nxt
        if len(indices) >= 4:
            paths.append(coordinates[indices])
    return paths


def simplify(points: np.ndarray, epsilon: float) -> np.ndarray:
    """Iterative Ramer-Douglas-Peucker using distances to finite segments."""
    keep = np.zeros(len(points), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(points) - 1)]
    tolerance = epsilon * epsilon
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        delta = points[last] - points[first]
        inner = points[first + 1:last] - points[first]
        length = np.dot(delta, delta)
        if length:
            projection = np.clip(inner @ delta / length, 0, 1)
            residual = inner - projection[:, None] * delta
        else:
            residual = inner
        distances = np.sum(residual * residual, axis=1)
        furthest = int(np.argmax(distances))
        if distances[furthest] > tolerance:
            pivot = first + 1 + furthest
            keep[pivot] = True
            stack.extend([(first, pivot), (pivot, last)])
    return points[keep]


def chaikin(points: np.ndarray, closed: bool) -> np.ndarray:
    if closed:
        base = points[:-1]
        following = np.roll(base, -1, axis=0)
    else:
        base, following = points[:-1], points[1:]
    refined = np.empty((len(base) * 2, 2), dtype=np.float64)
    refined[0::2] = .75 * base + .25 * following
    refined[1::2] = .25 * base + .75 * following
    if closed:
        return np.vstack((refined, refined[0]))
    return np.vstack((points[0], refined, points[-1]))


def contours(design: Design) -> dict[str, list[np.ndarray]]:
    field = terrain_field(design)
    result: dict[str, list[np.ndarray]] = {"minor": [], "index": []}
    # Fixed absolute elevations; omit the tiny rings at the very extrema.
    for number, level in enumerate(np.linspace(.025, .975, design.levels), start=1):
        group = "index" if number % 5 == 0 else "minor"
        for raw in marching_squares(field, float(level)):
            if np.ptp(raw, axis=0).max() < 8:
                continue
            closed = np.array_equal(raw[0], raw[-1])
            path = simplify(raw, .60)
            for _ in range(2):
                path = chaikin(path, closed)
            path = np.round(simplify(path, .22), 1)
            if len(path) >= 3:
                result[group].append(path)
    return result


def render(design: Design, paths: dict[str, list[np.ndarray]]) -> None:
    background_dir, source_dir = ROOT / "backgrounds", ROOT / "src"
    background_dir.mkdir(exist_ok=True)
    source_dir.mkdir(exist_ok=True)
    if design.light:
        background, minor, index = "#ecebe8", "#b1b0ae", "#858482"
        # Shade is coverage along a near-neutral ramp, preserving warm paper.
        shades = {"minor": 90, "index": 158}
        canvas = Image.new("L", (WIDTH * SCALE, HEIGHT * SCALE), 0)
    else:
        background, minor, index = "#101010", "#3d3d3d", "#858585"
        shades = {"minor": 61, "index": 133}
        canvas = Image.new("L", (WIDTH * SCALE, HEIGHT * SCALE), 16)
    widths = {"minor": 1.0, "index": 2.0}
    draw = ImageDraw.Draw(canvas)
    svg = [f'<svg xmlns="{SVG_NAMESPACE}" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
           f'<title>Topo / {design.terrain} / {"light" if design.light else "dark"}</title>',
           '<desc>Original procedural Gaussian terrain with smooth value noise; every fifth contour is an index line.</desc>',
           f'<style>.minor{{stroke:{minor};stroke-width:1}}.index{{stroke:{index};stroke-width:2}}</style>',
           f'<path fill="{background}" d="M0 0H{WIDTH}V{HEIGHT}H0Z"/>',
           '<g fill="none" stroke-linecap="round" stroke-linejoin="round">']
    for group in ["minor", "index"]:
        commands = []
        for points in paths[group]:
            scaled = [(float(x * SCALE), float(y * SCALE)) for x, y in points]
            draw.line(scaled, fill=shades[group], width=round(widths[group] * SCALE), joint="curve")
            closed = np.array_equal(points[0], points[-1])
            vertices = points[:-1] if closed else points
            commands.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in vertices) + ("Z" if closed else ""))
        svg.append(f'<g class="{group}"><path d="{"".join(commands)}"/></g>')
    svg.extend(['</g>', '</svg>', ''])
    (source_dir / f"{design.stem}.svg").write_text("\n".join(svg), encoding="utf-8")
    reduced = canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    if design.light:
        # Encode all 256 coverage shades without quantization or dithering.
        # Entries 0 / 90 / 158 match the SVG background / minor / index exactly.
        lookup = []
        for shade in range(256):
            if shade <= 90:
                a, b, fraction = (236, 235, 232), (177, 176, 174), shade / 90
            else:
                a, b, fraction = (177, 176, 174), (133, 132, 130), (shade - 90) / 68
            lookup.extend(max(0, min(255, round(start + (end - start) * fraction))) for start, end in zip(a, b))
        indexed = Image.frombytes("P", reduced.size, reduced.tobytes())
        indexed.putpalette(lookup)
        reduced = indexed
    reduced.save(background_dir / f"{design.stem}.png", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=[d.stem for d in DESIGNS], help="Regenerate one design")
    args = parser.parse_args()
    for design in DESIGNS:
        if args.only and design.stem != args.only:
            continue
        started = time.monotonic()
        lines = contours(design)
        render(design, lines)
        count = sum(len(paths) for paths in lines.values())
        points = sum(len(p) for paths in lines.values() for p in paths)
        png_size = (ROOT / "backgrounds" / f"{design.stem}.png").stat().st_size
        svg_size = (ROOT / "src" / f"{design.stem}.svg").stat().st_size
        print(f"{design.stem}: {count} lines, {points:,} points; PNG {png_size:,} B; SVG {svg_size:,} B; {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
