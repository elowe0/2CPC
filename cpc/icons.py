"""Plan icons: 64x64 pixel-art PNG, stdlib only.

The motif is picked from the plan's title + intro by keywords (cpc/motifs.py, FR/EN); colors and background
pattern come from a hash of the plan id, so two plans with the same motif still look different.
No keyword match -> a symmetric "creature" generated from the hash. Cost for the agent: zero tokens.
"""
import colorsys
import hashlib
import re
import struct
import unicodedata
import zlib
from pathlib import Path

from .motifs import MOTIFS

N = 16      # grid size
SCALE = 4   # -> 64 px


# ---------- PNG ----------

def png_bytes(px, w, h):
    raw = b"".join(b"\x00" + bytes(c for p in px[y * w:(y + 1) * w] for c in p) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# ---------- colors ----------

def _rgb(h, s, v):
    return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(h % 1, max(0, min(1, s)), max(0, min(1, v)))) + (255,)


def palette(seed):
    hue = seed[0] / 255
    return {
        "o": _rgb(hue + .7, .45, .16),          # outline
        "1": _rgb(hue, .62, .86),               # fill
        "2": _rgb(hue + .03, .72, .62),         # shade
        "3": _rgb(hue - .03, .32, .99),         # light
        "+": _rgb(hue + .45, .7, .92),          # accent
        "@": _rgb(hue + .7, .45, .16),          # dark detail
        "*": (250, 250, 245, 255),              # white
        "bg": _rgb(hue + .5, .16, .88),
        "bg2": _rgb(hue + .5, .2, .82),
    }


# ---------- grids ----------

def _cells(rows):
    rows = [r.ljust(N, ".")[:N] for r in rows] + ["." * N] * (N - len(rows))
    return [list(r) for r in rows[:N]]


def shade(rows):
    """Motif rows ('#' fill, '+' accent, '@' dark, '*' white, '.' empty) -> rows with outline and shading."""
    g = _cells(rows)
    on = lambda x, y: 0 <= x < N and 0 <= y < N and g[y][x] != "."
    solid = lambda x, y: 0 <= x < N and 0 <= y < N and g[y][x] in "#+*"  # '@' strokes get no halo
    out = [["." for _ in range(N)] for _ in range(N)]
    for y in range(N):
        for x in range(N):
            c = g[y][x]
            if c == ".":
                if any(solid(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    out[y][x] = "o"
            elif c == "#":
                if not on(x, y - 1) or not on(x - 1, y):
                    out[y][x] = "3"
                elif not on(x, y + 1) or not on(x + 1, y):
                    out[y][x] = "2"
                else:
                    out[y][x] = "1"
            else:
                out[y][x] = c
    return ["".join(r) for r in out]


def creature(seed):
    """Symmetric creature from the hash (fallback when no motif matches)."""
    bits = int.from_bytes(seed[1:9], "big")
    m = [["."] * N for _ in range(N)]
    k = 0
    for y in range(2, 14):
        for x in range(2, 8):
            dens = .9 if 4 <= y <= 11 and x >= 4 else .5 if 3 <= y <= 12 and x >= 3 else .2
            v = ((bits >> (k % 64)) ^ (bits >> ((k * 7) % 64))) & 0xff
            if (v / 255) < dens or (x == 7 and 4 <= y <= 11):
                m[y][x] = m[y][15 - x] = "#"
            k += 3
    ey, ex = 5 + seed[9] % 3, 5 + seed[10] % 2
    for x in (ex, 15 - ex):
        if m[ey][x] == "#":
            m[ey][x] = "*"
            m[ey + 1][x] = "@"
    return ["".join(r) for r in m]


def render(rows, pal, seed):
    """16x16 shaded rows -> 64x64 RGBA pixels on a rounded tile with a hash pattern."""
    pat = [[(seed[11 + y] >> x) & 1 for x in range(8)] for y in range(8)]
    px = []
    S = N * SCALE
    for y in range(S):
        for x in range(S):
            gx, gy = x // SCALE, y // SCALE
            c = rows[gy][gx]
            if c != ".":
                px.append(pal[c])
            elif (x < 3 or x > S - 4) and (y < 3 or y > S - 4) and (min(x, S - 1 - x) + min(y, S - 1 - y) < 3):
                px.append((0, 0, 0, 0))  # rounded corners
            else:
                px.append(pal["bg2"] if pat[(gy // 2) % 8][(gx // 2) % 8] else pal["bg"])
    return px


# ---------- motif choice ----------

def fold(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _match(kw, w):
    return w == kw if len(kw) < 4 else w.startswith(kw)


def _score(m, text):
    """Each word counts once per motif (even if several keywords match it), plus multi-word phrases."""
    words = text.split()
    single = [k for k in m["kw"] if " " not in k]
    s = sum(1 for w in words if any(_match(k, w) for k in single))
    return s + sum(f" {text} ".count(f" {k} ") for k in m["kw"] if " " in k)


def choose(title, intro=""):
    """-> (motif name, score) or (None, 0). Title words weigh 3, intro words 1; ties: library order."""
    t, i = fold(title), fold(intro)
    best, score = None, 0
    for name, m in MOTIFS.items():
        s = 3 * _score(m, t) + _score(m, i)
        if s > score:
            best, score = name, s
    return best, score


RENDER_VERSION = 2  # bump when the drawing changes (not the motif choice): frozen icons are redrawn


def center(rows):
    """Shift the drawing (outline included) to the middle of the 16x16 grid."""
    g = _cells(rows)
    pts = [(x, y) for y in range(N) for x in range(N) if g[y][x] != "."]
    if not pts:
        return rows
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    dx, dy = (N - (x1 - x0 + 1)) // 2 - x0, (N - (y1 - y0 + 1)) // 2 - y0
    out = [["." for _ in range(N)] for _ in range(N)]
    for x, y in pts:
        out[y + dy][x + dx] = g[y][x]
    return ["".join(r) for r in out]


def icon_rows(pid, title, intro="", motif=None):
    """-> (motif name, shaded + centered rows, seed). `motif` forces the motif (frozen choice)."""
    seed = hashlib.sha1(pid.encode("utf-8")).digest()
    name = motif if motif in MOTIFS or motif == "creature" else choose(title, intro)[0]
    rows = MOTIFS[name]["px"] if name in MOTIFS else creature(seed)
    return (name or "creature"), center(shade(rows)), seed


def icon_png(pid, title, intro="", motif=None):
    name, rows, seed = icon_rows(pid, title, intro, motif)
    return name, png_bytes(render(rows, palette(seed), seed), N * SCALE, N * SCALE)


def make_icon(path, pid, title, intro="", motif=None):
    """Write the 64x64 PNG; -> motif name ('creature' when no keyword matched)."""
    name, data = icon_png(pid, title, intro, motif)
    Path(path).write_bytes(data)
    return name


def sheet(path, items, cols=10, label=None):
    """Contact sheet of (pid, rows) pairs, 72 px per cell (tests / previews)."""
    cell = N * SCALE + 8
    rws = (len(items) + cols - 1) // cols
    W, H = cols * cell, rws * cell
    px = [(255, 255, 255, 0)] * (W * H)
    for k, (pid, rows) in enumerate(items):
        seed = hashlib.sha1(pid.encode("utf-8")).digest()
        img = render(rows, palette(seed), seed)
        ox, oy = (k % cols) * cell + 4, (k // cols) * cell + 4
        for y in range(N * SCALE):
            px[(oy + y) * W + ox:(oy + y) * W + ox + N * SCALE] = img[y * N * SCALE:(y + 1) * N * SCALE]
    Path(path).write_bytes(png_bytes(px, W, H))
