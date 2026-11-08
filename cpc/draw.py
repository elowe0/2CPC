"""!draw: tiny vector sketch language -> static inline SVG (no JS, works offline).

One shape per line: `cmd coords [.flags] [label]`. Coordinates are `x,y` (y goes down),
in any unit; the viewBox is fitted automatically, so only relative positions matter.

    box x,y w,h        circle x,y r       line x,y x,y ...    arrow x,y x,y ...
    poly x,y x,y x,y   dot x,y            text x,y Label      grid [step]

Flags: colors (.blue .orange .green .yellow .pink .purple .red .gray), .dash, .thick,
.empty (no fill), .solid (opaque fill), .curve (smooth line/arrow/poly), .both (2 arrowheads).
"""
import math
import re

from .markdown import esc

COLORS = {"blue": "s1", "orange": "s2", "green": "s3", "yellow": "s4", "pink": "s5",
          "purple": "s7", "red": "s8", "gray": "gr", "grey": "gr"}
FLAGS = {"dash", "thick", "empty", "solid", "curve", "both"}
ALIASES = {"rect": "box", "circ": "circle", "pt": "dot", "label": "text", "polygon": "poly"}
# cmd -> (min points, max points, needs a number, needs a label)
SPEC = {"box": (2, 2, False, False), "circle": (1, 1, True, False), "line": (2, 99, False, False),
        "arrow": (2, 99, False, False), "poly": (3, 99, False, False), "dot": (1, 1, False, False),
        "text": (1, 1, False, True), "grid": (0, 0, False, False)}
_PT = re.compile(r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")

MAX_W, MAX_H = 680, 440        # target size in px
FS, SW = 13, 1.6               # font size / stroke width in px


def parse(lines, warn):
    """-> {"shapes": [...], "grid": step|None}. warn(msg) for bad lines."""
    shapes, grid = [], None
    for raw in lines:
        for ln in re.split(r"(?<!\\);", raw):
            ln = ln.strip().replace("\\;", ";")
            if not ln or ln.startswith("//"):
                continue
            toks = ln.split()
            cmd = ALIASES.get(toks[0].lower(), toks[0].lower())
            if cmd not in SPEC:
                warn(f"!draw: unknown shape '{toks[0]}' (box circle line arrow poly dot text grid)")
                continue
            lo, hi, need_num, need_label = SPEC[cmd]
            pts, num, flags, color, k = [], None, set(), None, 1
            while k < len(toks):
                tk = toks[k]
                m = _PT.match(tk)
                if m and len(pts) < hi and num is None:
                    pts.append((float(m.group(1)), float(m.group(2))))
                elif _NUM.match(tk) and num is None and (need_num or cmd == "grid") and len(pts) >= lo:
                    num = float(tk)
                elif tk.startswith(".") and tk[1:].lower() in FLAGS:
                    flags.add(tk[1:].lower())
                elif tk.startswith(".") and tk[1:].lower() in COLORS:
                    color = COLORS[tk[1:].lower()]
                else:
                    break
                k += 1
            label = " ".join(toks[k:])
            if cmd == "grid":
                grid = num if num and num > 0 else 1.0
                continue
            if len(pts) < lo:
                warn(f"!draw {cmd}: needs {lo} point(s) x,y — got '{ln}'")
                continue
            if need_num and not num:
                warn(f"!draw circle: needs a radius after the center — got '{ln}'")
                continue
            if need_label and not label:
                warn(f"!draw text: empty label")
                continue
            shapes.append({"cmd": cmd, "pts": pts, "r": abs(num or 0), "flags": sorted(flags),
                           "color": color, "label": label})
    if not shapes:
        warn("!draw: no shapes")
    return {"shapes": shapes, "grid": grid}


def _f(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _catmull(pts, closed=False):
    """Smooth path through points (Catmull-Rom -> cubic Bezier). Returns (d, last control point)."""
    P = list(pts)
    n = len(P)
    if closed:
        get = lambda i: P[i % n]
        segs = range(n)
    else:
        get = lambda i: P[max(0, min(n - 1, i))]
        segs = range(n - 1)
    d = f"M{_f(P[0][0])},{_f(P[0][1])}"
    c2, samples = P[0], [P[0]]
    for i in segs:
        p0, p1, p2, p3 = get(i - 1), get(i), get(i + 1), get(i + 2)
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{_f(c1[0])},{_f(c1[1])} {_f(c2[0])},{_f(c2[1])} {_f(p2[0])},{_f(p2[1])}"
        for k in range(1, 13):
            t = k / 12
            a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
            samples.append((a * p1[0] + b * c1[0] + c * c2[0] + e * p2[0],
                            a * p1[1] + b * c1[1] + c * c2[1] + e * p2[1]))
    return d + ("Z" if closed else ""), c2, samples


def _head(tip, frm, size):
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    w = size * 0.45
    pts = [tip, (bx - uy * w, by + ux * w), (bx + uy * w, by - ux * w)]
    return "<polygon class=\"hd\" points=\"" + " ".join(f"{_f(x)},{_f(y)}" for x, y in pts) + "\"/>"


def _mid(pts):
    """Point at half the length of a polyline + direction of that segment."""
    segs = [(a, b, math.hypot(b[0] - a[0], b[1] - a[1])) for a, b in zip(pts, pts[1:])]
    half = sum(s[2] for s in segs) / 2
    for a, b, L in segs:
        if half <= L and L:
            t = half / L
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), (b[0] - a[0], b[1] - a[1])
        half -= L
    return pts[0], (1, 0)


def _bounds(shapes, grid):
    xs, ys = [], []
    for s in shapes:
        if s["cmd"] == "circle":
            (x, y), r = s["pts"][0], s["r"]
            xs += [x - r, x + r]
            ys += [y - r, y + r]
        elif s["cmd"] == "box":
            (x, y), (w, h) = s["pts"]
            xs += [x, x + w]
            ys += [y, y + h]
        else:
            xs += [p[0] for p in s["pts"]]
            ys += [p[1] for p in s["pts"]]
    if grid and xs:
        xs = [math.floor(min(xs) / grid) * grid, math.ceil(max(xs) / grid) * grid]
        ys = [math.floor(min(ys) / grid) * grid, math.ceil(max(ys) / grid) * grid]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1, 1)


def _label_box(s, fs):
    """Approximate extent of a shape's label, for viewBox fitting."""
    if not s["label"]:
        return None
    w = len(s["label"]) * fs * 0.58
    if s["cmd"] == "dot":
        x, y = s["pts"][0]
        return (x, y - fs, x + fs * 0.6 + w, y + fs)
    if s["cmd"] in ("line", "arrow"):
        (x, y), _ = _mid(s["pts"])
        return (x - w / 2, y - fs * 1.6, x + w / 2, y + fs * 0.5)
    if s["cmd"] == "text":
        x, y = s["pts"][0]
        return (x - w / 2, y - fs, x + w / 2, y + fs)
    return None   # centered inside closed shapes: assumed to fit


def _fit(shapes, grid):
    x0, y0, x1, y1 = _bounds(shapes, grid)
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    k = min(MAX_W / w, MAX_H / h)
    for _ in range(2):          # labels grow the box, which shrinks the scale: iterate
        fs = FS / k
        bx = [x0, x1]
        by = [y0, y1]
        for s in shapes:
            lb = _label_box(s, fs)
            if lb:
                bx += [lb[0], lb[2]]
                by += [lb[1], lb[3]]
        pad = fs * (2.2 if grid else 0.9)
        X0, Y0, X1, Y1 = min(bx) - pad, min(by) - pad, max(bx) + pad, max(by) + pad
        k = min(MAX_W / (X1 - X0), MAX_H / (Y1 - Y0))
    return (X0, Y0, X1 - X0, Y1 - Y0), k


def _txt(x, y, s, cls="lb", anchor="middle"):
    return (f'<text class="{cls}" x="{_f(x)}" y="{_f(y)}" text-anchor="{anchor}" '
            f'dominant-baseline="central">{esc(s)}</text>')


def render(b):
    shapes, grid = b["shapes"], b.get("grid")
    if not shapes:
        return ""
    (vx, vy, vw, vh), k = _fit(shapes, grid)
    u = 1 / k
    fs, sw = FS * u, SW * u
    out = []
    if grid:
        gx0, gy0, gx1, gy1 = _bounds(shapes, grid)
        step = grid
        while (gx1 - gx0) / step > 40 or (gy1 - gy0) / step > 40:
            step *= 2
        lab = []
        n = int(round((gx1 - gx0) / step))
        for i in range(n + 1):
            x = gx0 + i * step
            out.append(f'<line class="gl" x1="{_f(x)}" y1="{_f(gy0)}" x2="{_f(x)}" y2="{_f(gy1)}" stroke-width="{_f(u)}"/>')
            if n <= 24 or i % 2 == 0:
                lab.append(_txt(x, gy0 - fs * 0.9, f"{x:g}", "gt"))
        n = int(round((gy1 - gy0) / step))
        for i in range(n + 1):
            y = gy0 + i * step
            out.append(f'<line class="gl" x1="{_f(gx0)}" y1="{_f(y)}" x2="{_f(gx1)}" y2="{_f(y)}" stroke-width="{_f(u)}"/>')
            if n <= 24 or i % 2 == 0:
                lab.append(_txt(gx0 - fs * 0.5, y, f"{y:g}", "gt", "end"))
        out += lab
    labels = []
    for s in shapes:
        cmd, pts, fl = s["cmd"], s["pts"], s["flags"]
        cls = ["sh", s["color"] or ("gr" if cmd in ("box", "circle", "poly") else "fg")]
        cls += [f for f in fl if f in ("dash", "empty", "solid")]
        w = sw * (2 if "thick" in fl else 1)
        attrs = f'class="{" ".join(cls)}" stroke-width="{_f(w)}"'
        if "dash" in fl:
            attrs += f' stroke-dasharray="{_f(6 * u)} {_f(4 * u)}"'
        lb = s["label"]
        if cmd == "box":
            (x, y), (bw, bh) = pts
            x, bw = (x + bw, -bw) if bw < 0 else (x, bw)
            y, bh = (y + bh, -bh) if bh < 0 else (y, bh)
            out.append(f'<rect {attrs} x="{_f(x)}" y="{_f(y)}" width="{_f(bw)}" height="{_f(bh)}" rx="{_f(2 * u)}"/>')
            if lb:
                labels.append(_txt(x + bw / 2, y + bh / 2, lb))
        elif cmd == "circle":
            (x, y), r = pts[0], s["r"]
            out.append(f'<circle {attrs} cx="{_f(x)}" cy="{_f(y)}" r="{_f(r)}"/>')
            if lb:
                labels.append(_txt(x, y, lb))
        elif cmd == "poly":
            if "curve" in fl:
                d, _, _ = _catmull(pts, closed=True)
                out.append(f'<path {attrs} d="{d}"/>')
            else:
                out.append(f'<polygon {attrs} points="{" ".join(f"{_f(a)},{_f(c)}" for a, c in pts)}"/>')
            if lb:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                labels.append(_txt(cx, cy, lb))
        elif cmd in ("line", "arrow"):
            hs = 9 * u * (1.3 if "thick" in fl else 1)
            path_pts = pts
            if "curve" in fl and len(pts) > 2:
                d, end_from, path_pts = _catmull(pts)
                start_to = _catmull(pts[::-1])[1]
            else:
                d = "M" + " L".join(f"{_f(a)},{_f(c)}" for a, c in pts)
                end_from, start_to = pts[-2], pts[1]
            g = f'<path {attrs} fill="none" d="{d}"/>'
            if cmd == "arrow":
                g += _head(pts[-1], end_from, hs)
                if "both" in fl:
                    g += _head(pts[0], start_to, hs)
                g = f'<g class="{cls[1]}">{g}</g>'
            out.append(g)
            if lb:
                (mx, my), (dx, dy) = _mid(path_pts)
                L = math.hypot(dx, dy) or 1
                nx, ny = dy / L, -dx / L          # normal pointing "up" for left-to-right lines
                if ny > 0:
                    nx, ny = -nx, -ny
                off = fs * 0.85
                labels.append(_txt(mx + nx * off, my + ny * off, lb))
        elif cmd == "dot":
            x, y = pts[0]
            out.append(f'<circle class="dt {cls[1]}" cx="{_f(x)}" cy="{_f(y)}" r="{_f(4 * u)}"/>')
            if lb:
                labels.append(_txt(x + fs * 0.6, y, lb, anchor="start"))
        elif cmd == "text":
            x, y = pts[0]
            labels.append(_txt(x, y, lb, f"lb tx {s['color'] or ''}".strip()))
    cap = b.get("caption", "")
    vb = f"{_f(vx)} {_f(vy)} {_f(vw)} {_f(vh)}"
    svg = (f'<svg viewBox="{vb}" width="{vw * k:.0f}" height="{vh * k:.0f}" role="img" '
           f'aria-label="{esc(cap)}" font-size="{_f(fs)}" stroke-width="{_f(sw * 2.6)}">'
           f'{"".join(out)}{"".join(labels)}</svg>')
    return svg
