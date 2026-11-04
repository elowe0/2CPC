"""Dependency-free SVG charts: bar, hbar, line, pie, donut.

Colors come from CSS classes (.s1..s8 / .stroke-s1) so light/dark themes apply.
Hover = native <title> tooltips on enlarged hit targets.
"""
import math
from .markdown import esc

W, H = 600, 260


def fmt(v):
    if abs(v) >= 1000 and v == int(v):
        return f"{int(v):,}".replace(",", " ")
    return f"{v:g}"


def nice_ticks(lo, hi, count=4):
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    a = math.floor(lo / step) * step
    b = math.ceil(hi / step) * step
    ticks, t = [], a
    while t <= b + step / 1e6:
        ticks.append(round(t, 10))
        t += step
    return ticks


def _top_rounded(x, y, w, h, r=4):
    r = min(r, w / 2, h)
    if h <= 0:
        return ""
    return (f"M{x:.1f},{y + h:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}"
            f"H{x + w - r:.1f}Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}V{y + h:.1f}Z")


def _right_rounded(x, y, w, h, r=4):
    r = min(r, h / 2, w)
    if w <= 0:
        return ""
    return (f"M{x:.1f},{y:.1f}H{x + w - r:.1f}Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}"
            f"V{y + h - r:.1f}Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f}H{x:.1f}Z")


def bar(data):
    pl, pr, pt, pb = 44, 12, 18, 34
    vals = [v for _, v in data]
    ticks = nice_ticks(min(0, min(vals)), max(0, max(vals)))
    lo, hi = ticks[0], ticks[-1]
    ph = H - pt - pb
    y = lambda v: pt + ph * (hi - v) / (hi - lo)
    out = []
    for t in ticks:
        out.append(f'<line class="grid" x1="{pl}" x2="{W - pr}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text class="ax" x="{pl - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{fmt(t)}</text>')
    slot = (W - pl - pr) / len(data)
    bw = min(56, slot * 0.62)
    for i, (k, v) in enumerate(data):
        x = pl + slot * i + (slot - bw) / 2
        y0, y1 = y(max(v, 0)), y(min(v, 0))
        path = _top_rounded(x, y0, bw, y1 - y0) if v >= 0 else f"M{x:.1f},{y0:.1f}h{bw:.1f}v{y1 - y0:.1f}h{-bw:.1f}Z"
        out.append(f'<g class="mk"><title>{esc(k)} : {fmt(v)}</title>'
                   f'<rect class="hit" x="{pl + slot * i:.1f}" y="{pt}" width="{slot:.1f}" height="{ph}"/>'
                   f'<path class="s1" d="{path}"/>'
                   f'<text class="val" x="{x + bw / 2:.1f}" y="{y0 - 5:.1f}" text-anchor="middle">{fmt(v)}</text>'
                   f'<text class="ax" x="{x + bw / 2:.1f}" y="{H - pb + 18}" text-anchor="middle">{esc(k)}</text></g>')
    out.append(f'<line class="base" x1="{pl}" x2="{W - pr}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    return W, H, "".join(out)


def hbar(data):
    lw = min(180, 14 + 7 * max(len(k) for k, _ in data))
    pr, pt, rowh = 48, 6, 30
    h = pt * 2 + rowh * len(data)
    hi = max(0.0, max(v for _, v in data)) or 1
    pw = W - lw - pr
    out = []
    for i, (k, v) in enumerate(data):
        yy = pt + rowh * i
        bw = pw * max(v, 0) / hi
        out.append(f'<g class="mk"><title>{esc(k)} : {fmt(v)}</title>'
                   f'<rect class="hit" x="0" y="{yy}" width="{W}" height="{rowh}"/>'
                   f'<text class="ax" x="{lw - 8}" y="{yy + rowh / 2 + 4:.1f}" text-anchor="end">{esc(k)}</text>'
                   f'<path class="s1" d="{_right_rounded(lw, yy + 5, bw, rowh - 10)}"/>'
                   f'<text class="val" x="{lw + bw + 6:.1f}" y="{yy + rowh / 2 + 4:.1f}">{fmt(v)}</text></g>')
    out.append(f'<line class="base" x1="{lw}" x2="{lw}" y1="{pt}" y2="{h - pt}"/>')
    return W, h, "".join(out)


def line(data):
    pl, pr, pt, pb = 44, 16, 18, 34
    vals = [v for _, v in data]
    ticks = nice_ticks(min(0, min(vals)), max(vals))
    lo, hi = ticks[0], ticks[-1]
    ph = H - pt - pb
    y = lambda v: pt + ph * (hi - v) / (hi - lo)
    n = len(data)
    x = lambda i: pl + (W - pl - pr) * (i / (n - 1) if n > 1 else 0.5)
    out = []
    for t in ticks:
        out.append(f'<line class="grid" x1="{pl}" x2="{W - pr}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text class="ax" x="{pl - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{fmt(t)}</text>')
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(data))
    out.append(f'<polyline class="ln stroke-s1" points="{pts}"/>')
    slot = (W - pl - pr) / max(n, 1)
    imax = vals.index(max(vals))
    for i, (k, v) in enumerate(data):
        anc = "start" if i == 0 and n > 1 else "end" if i == n - 1 and n > 1 else "middle"
        dx = 6 if anc == "start" else -6 if anc == "end" else 0
        label = (f'<text class="val" x="{x(i) + dx:.1f}" y="{y(v) - 10:.1f}" text-anchor="{anc}">{fmt(v)}</text>'
                 if i in (0, n - 1, imax) else "")
        out.append(f'<g class="mk"><title>{esc(k)} : {fmt(v)}</title>'
                   f'<rect class="hit" x="{x(i) - slot / 2:.1f}" y="{pt}" width="{slot:.1f}" height="{ph}"/>'
                   f'<circle class="dot s1" cx="{x(i):.1f}" cy="{y(v):.1f}" r="4"/>{label}'
                   f'<text class="ax" x="{x(i):.1f}" y="{H - pb + 18}" text-anchor="middle">{esc(k)}</text></g>')
    out.append(f'<line class="base" x1="{pl}" x2="{W - pr}" y1="{y(lo):.1f}" y2="{y(lo):.1f}"/>')
    return W, H, "".join(out)


def pie(data, donut=False):
    data = [(k, v) for k, v in data if v > 0]
    total = sum(v for _, v in data) or 1
    cx, cy, r = 120, 120, 104
    ri = 62 if donut else 0
    out, legend, a = [], [], -math.pi / 2
    for i, (k, v) in enumerate(data):
        cls = f"s{i % 8 + 1}"
        da = 2 * math.pi * v / total
        pct = f"{100 * v / total:.0f}%"
        if len(data) == 1:
            shape = (f'<circle class="{cls} seg" cx="{cx}" cy="{cy}" r="{r}"/>' +
                     (f'<circle class="surf" cx="{cx}" cy="{cy}" r="{ri}"/>' if ri else ""))
        else:
            b = a + da
            large = 1 if da > math.pi else 0
            p0 = (cx + r * math.cos(a), cy + r * math.sin(a))
            p1 = (cx + r * math.cos(b), cy + r * math.sin(b))
            if ri:
                q0 = (cx + ri * math.cos(b), cy + ri * math.sin(b))
                q1 = (cx + ri * math.cos(a), cy + ri * math.sin(a))
                d = (f"M{p0[0]:.1f},{p0[1]:.1f}A{r},{r} 0 {large} 1 {p1[0]:.1f},{p1[1]:.1f}"
                     f"L{q0[0]:.1f},{q0[1]:.1f}A{ri},{ri} 0 {large} 0 {q1[0]:.1f},{q1[1]:.1f}Z")
            else:
                d = (f"M{cx},{cy}L{p0[0]:.1f},{p0[1]:.1f}"
                     f"A{r},{r} 0 {large} 1 {p1[0]:.1f},{p1[1]:.1f}Z")
            shape = f'<path class="{cls} seg" d="{d}"/>'
            a = b
        out.append(f'<g class="mk"><title>{esc(k)} : {fmt(v)} ({pct})</title>{shape}</g>')
        legend.append(f'<li><i class="sw {cls}"></i><span>{esc(k)}</span><b>{fmt(v)}</b><em>{pct}</em></li>')
    if donut:
        out.append(f'<text class="val big" x="{cx}" y="{cy + 7}" text-anchor="middle">{fmt(total)}</text>')
    return 240, 240, "".join(out), "".join(legend)


def render(block):
    data = block["data"]
    title = esc(block.get("title", ""))
    if not data:
        return f'<figure class="chart empty"><figcaption>{title}</figcaption><p>∅</p></figure>'
    kind = block["kind"]
    legend = ""
    if kind in ("pie", "donut"):
        w, h, body, legend = pie(data, kind == "donut")
        legend = f'<ul class="legend">{legend}</ul>'
    else:
        w, h, body = {"bar": bar, "hbar": hbar, "line": line}[kind](data)
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{title}" '
           f'class="c-{kind}" preserveAspectRatio="xMidYMid meet">{body}</svg>')
    rows = "".join(f"<tr><td>{esc(k)}</td><td>{fmt(v)}</td></tr>" for k, v in data)
    table = f'<details class="data"><summary data-i18n="data"></summary><table>{rows}</table></details>'
    return (f'<figure class="chart chart-{kind}">'
            f'{f"<figcaption>{title}</figcaption>" if title else ""}'
            f'<div class="chart-body">{svg}{legend}</div>{table}</figure>')
