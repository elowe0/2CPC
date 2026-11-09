"""Block tree -> standalone HTML page."""
import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from . import charts, draw
from .i18n import NEXT_DEFAULT, STRINGS
from .markdown import esc, inline
from .parser import first_paragraph, opts_parse, slug

TPL = Path(__file__).parent / "template"
SEL = ' aria-selected="true"'
CUR = ' aria-current="page"'
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"


EDITORS = {  # !link to a local file -> editor URL ({path} absolute posix, {line}, {col})
    "vscode": "vscode://file/{path}:{line}:{col}",
    "cursor": "cursor://file/{path}:{line}:{col}",
    "windsurf": "windsurf://file/{path}:{line}:{col}",
    "idea": "idea://open?file={path}&line={line}",
    "rider": "rider://open?file={path}&line={line}",
    "none": "",
}


def is_url(s):
    return bool(re.match(r"^(https?:)?//", s, re.I)) or s.startswith("data:")


class Ctx:
    def __init__(self, root, vdir, new_ids):
        self.root = Path(root)
        self.vdir = Path(vdir)
        self.new_ids = new_ids or set()
        self.copied = {}
        self.warnings = []
        self.toc = []
        self.sections = []
        self.mermaid = False
        self.lang = "fr"
        self.decisions = {}   # version -> rows [label, value] (or None: no saved answers)
        self.default_dec_v = None
        self.sec_status = {}  # section id -> "chg" | "new" (only for v > 1)
        self.editor = "vscode"

    def asset(self, src):
        """Copy a local asset once per plan into <plan>/assets/<sha8>-<name>, return its URL from vN/ (or None).

        Same content -> same file for every version. If the source is gone, the legacy per-version copy
        (vN/assets/<name>, before shared assets) is reused."""
        if is_url(src):
            return src
        p = Path(src)
        if not p.is_absolute():
            p = self.root / p
        p = p.resolve()
        if p in self.copied:
            return self.copied[p]
        if not p.is_file():
            legacy = self.vdir / "assets" / p.name
            if not legacy.is_file():
                self.warnings.append(f"missing asset: {src}")
                return None
            p = legacy
        data = p.read_bytes()
        name = f"{hashlib.sha1(data).hexdigest()[:8]}-{slug(p.stem, 40)}{p.suffix.lower()}"
        dest = self.vdir.parent / "assets" / name
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        url = f"../assets/{name}"
        self.copied[p] = url
        return url


def missing(src):
    return f'<div class="missing"><span data-i18n="missingAsset"></span> : <code>{esc(src)}</code></div>'


def caption(c):
    return f"<figcaption>{inline(c)}</figcaption>" if c else ""


def video_embed(src):
    u = urlparse(src if not src.startswith("//") else "https:" + src)
    host = (u.netloc or "").lower().replace("www.", "")
    vid = None
    if host in ("youtube.com", "m.youtube.com"):
        vid = parse_qs(u.query).get("v", [None])[0] or (u.path.split("/")[-1] if "/embed/" in u.path or "/shorts/" in u.path else None)
        if vid:
            return f"https://www.youtube-nocookie.com/embed/{vid}"
    if host == "youtu.be":
        return f"https://www.youtube-nocookie.com/embed/{u.path.strip('/')}"
    if host == "vimeo.com" and u.path.strip("/").isdigit():
        return f"https://player.vimeo.com/video/{u.path.strip('/')}"
    return None


# ---------- questions ----------

def q_head(b, ctx):
    badges = ""
    if b["req"]:
        badges += '<span class="badge req" data-i18n="required"></span>'
    if b["id"] in ctx.new_ids:
        badges += '<span class="badge new" data-i18n="isNew"></span>'
    badges += '<span class="badge reused" hidden></span>'
    label = inline(b["label"]) if b["label"] else ""
    return f'<div class="q-label">{label}{badges}</div>'


def opt_label(b, k):
    """Label HTML for option key k (with optional key chip and detail line)."""
    label = b.get("labels", {}).get(k, k)
    chip = f'<code class="key">{esc(k)}</code> ' if b.get("keyed") and k != label else ""
    det = b.get("details", {}).get(k)
    det = f'<small class="dt">{inline(det)}</small>' if det else ""
    return f'<span class="ol"><span class="lt">{chip}{inline(label)}</span>{det}</span>'


def q_opts(b, kind):
    name = f"q-{b['id']}"
    out = []
    for o in b.get("opts", []):
        rec = '<span class="badge rec" data-i18n="recommended"></span>' if o in b.get("rec", []) else ""
        out.append(f'<label class="opt"><input type="{kind}" name="{esc(name)}" value="{esc(o)}">'
                   f'{opt_label(b, o)}{rec}</label>')
    if b.get("other"):
        out.append(f'<label class="opt other"><input type="{kind}" name="{esc(name)}" value="__other" '
                   f'data-i18n-title="other"><input type="text" class="other-txt" data-i18n-ph="otherPh"></label>')
    return f'<div class="opts">{"".join(out)}</div>'


def question(b, ctx):
    qt, qid = b["qt"], b["id"]
    name = esc(f"q-{qid}")
    if qt in ("choice", "pick"):
        body = q_opts(b, "radio")
    elif qt == "multi":
        body = q_opts(b, "checkbox")
    elif qt == "yesno":
        body = (f'<div class="opts row"><label class="opt"><input type="radio" name="{name}" value="yes">'
                f'<span data-i18n="yes"></span></label><label class="opt"><input type="radio" name="{name}" value="no">'
                f'<span data-i18n="no"></span></label></div>')
    elif qt == "scale":
        cells = "".join(f'<label><input type="radio" name="{name}" value="{v}"><span>{v}</span></label>'
                        for v in range(b["min"], b["max"] + 1))
        body = f'<div class="scale">{cells}</div>'
    elif qt == "text":
        body = f'<textarea rows="4" data-i18n-ph="textPh"></textarea>'
    elif qt == "line":
        body = f'<input type="text" data-i18n-ph="textPh">'
    elif qt == "number":
        rng = "".join(f' {a}="{b[a]:g}"' for a in ("min", "max") if b.get(a) is not None)
        hint = (f'<span class="hint">{b["min"]:g} – {b["max"]:g}</span>' if b.get("min") is not None else "")
        body = f'<input type="number" step="any"{rng}> {hint}'
    elif qt == "date":
        body = '<input type="date">'
    elif qt == "rank":
        items = "".join(
            f'<li draggable="true" data-val="{esc(o)}"><span class="grip" aria-hidden="true">⋮⋮</span>'
            f'<span class="rk"></span><span class="lbl">{opt_label(b, o)}</span>'
            f'<button type="button" class="up" data-i18n-title="up">↑</button>'
            f'<button type="button" class="down" data-i18n-title="down">↓</button></li>'
            for o in b["opts"])
        body = f'<ol class="rank">{items}</ol><p class="hint" data-i18n="dragHint"></p>'
    elif qt == "approve":
        rows = []
        for k, o in enumerate(b["opts"]):
            n = esc(f"q-{qid}-{k}")
            rows.append(
                f'<div class="ap" data-item="{esc(o)}"><span class="lbl">{opt_label(b, o)}</span><span class="ap-btns">'
                f'<label class="y"><input type="radio" name="{n}" value="y"><span data-i18n-title="approveY">✓</span></label>'
                f'<label class="n"><input type="radio" name="{n}" value="n"><span data-i18n-title="approveN">✗</span></label>'
                f'<label class="m"><input type="radio" name="{n}" value="?"><span data-i18n-title="approveQ">?</span></label>'
                f'</span><input type="text" class="note" data-i18n-ph="notePh"></div>')
        body = f'<div class="approve">{"".join(rows)}</div>'
    elif qt == "matrix":
        head = "".join(f"<th>{inline(c)}</th>" for c in b["cols"])
        trs = []
        for r_i, r in enumerate(b["rows"]):
            n = esc(f"q-{qid}-{r_i}")
            tds = "".join(f'<td><label><input type="radio" name="{n}" value="{esc(c)}" aria-label="{esc(r)} {esc(c)}"></label></td>'
                          for c in b["cols"])
            trs.append(f'<tr data-row="{esc(r)}"><th scope="row">{inline(r)}</th>{tds}</tr>')
        body = f'<div class="tbl"><table class="matrix"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
    elif qt == "todo":
        done = set(b.get("agent") or ())
        items = "".join(
            f'<label class="opt{" agent" if o in done else ""}"><input type="checkbox" value="{k}"'
            f'{" checked disabled" if o in done else ""}><span>{inline(o)}</span>'
            + ('<span class="badge agent" data-i18n="agentDone"></span>' if o in done else "") + '</label>'
            for k, o in enumerate(b["items"]))
        body = f'<div class="opts todo">{items}</div>'
    else:
        body = ""
    return (f'<div class="q q-{qt}" id="q-{esc(qid)}" data-q="{esc(qid)}" data-qt="{qt}">'
            f'{q_head(b, ctx)}{body}</div>')


# ---------- content blocks ----------

def block(b, ctx, top=False):
    t = b["t"]
    if t == "h":
        lvl = b["level"]
        badge, attr = "", ""
        if top:
            ctx.toc.append((lvl, b["text"], b["id"]))
            if lvl <= 2 and ctx.sec_status:
                st = ctx.sec_status.get(b["id"], "same")
                attr = f' data-sec="{st}"'
                if st != "same":
                    badge = f' <span class="badge {st}" data-i18n="{"isNew" if st == "new" else "changed"}"></span>'
        return f'<h{lvl + 1} id="{esc(b["id"])}"{attr}>{inline(b["text"])}{badge}</h{lvl + 1}>'
    if t == "decisions":
        v = b["v"] or ctx.default_dec_v
        S = STRINGS.get(ctx.lang) or STRINGS["fr"]
        rows = ctx.decisions.get(v) if v else None
        cap = caption(b["title"]) if b["title"] else ""
        if not rows:
            ctx.warnings.append(f"!decisions: no saved answers for v{v} (cpc.py answers <id> --save)" if v
                                else "!decisions: no previous version")
            msg = S["decNone"].replace("{v}", str(v or "?"))
            return f'<div class="callout warn"><span class="ic">⚠</span><div>{inline(msg)}</div></div>'
        body = "".join(f"<tr><td>{inline(q)}</td><td>{inline(a)}</td></tr>" for q, a in rows)
        return (f'<figure class="decisions"><div class="tbl"><table><thead><tr><th>{esc(S["decQ"])}</th>'
                f'<th>{esc(S["decA"].replace("{v}", str(v)))}</th></tr></thead><tbody>{body}</tbody></table></div>{cap}</figure>')
    if t == "p":
        return f"<p>{inline(b['text'])}</p>"
    if t in ("ul", "ol"):
        return f"<{t}>{''.join(f'<li>{inline(x)}</li>' for x in b['items'])}</{t}>"
    if t == "quote":
        return f"<blockquote>{inline(b['text'])}</blockquote>"
    if t == "callout":
        icon = {"note": "ℹ", "tip": "✦", "warn": "⚠", "danger": "⛔"}[b["kind"]]
        return f'<div class="callout {b["kind"]}"><span class="ic">{icon}</span><div>{inline(b["text"])}</div></div>'
    if t == "hr":
        return "<hr>"
    if t == "img":
        url = ctx.asset(b["src"])
        if not url:
            return missing(b["src"])
        return (f'<figure class="img"><a href="{esc(url)}" target="_blank" rel="noopener">'
                f'<img src="{esc(url)}" alt="{esc(b["caption"])}" loading="lazy"></a>'
                f'{caption(b["caption"])}</figure>')
    if t == "audio":
        url = ctx.asset(b["src"])
        if not url:
            return missing(b["src"])
        return f'<figure class="audio"><audio controls preload="metadata" src="{esc(url)}"></audio>{caption(b["caption"])}</figure>'
    if t == "video":
        if is_url(b["src"]):
            emb = video_embed(b["src"])
            if emb:
                return (f'<figure class="video"><div class="embed"><iframe src="{esc(emb)}" allowfullscreen '
                        f'loading="lazy" title="{esc(b["caption"])}"></iframe></div>{caption(b["caption"])}</figure>')
        url = ctx.asset(b["src"])
        if not url:
            return missing(b["src"])
        return f'<figure class="video"><video controls preload="metadata" src="{esc(url)}"></video>{caption(b["caption"])}</figure>'
    if t == "chart":
        return charts.render(b)
    if t == "draw":
        return f'<figure class="draw">{draw.render(b)}{caption(b["caption"])}</figure>'
    if t == "kpi":
        tiles = "".join(f'<div class="tile"><div class="kv">{inline(v)}</div><div class="kk">{inline(k)}</div></div>'
                        for k, v in b["items"])
        return f'<div class="kpi">{tiles}</div>'
    if t == "progress":
        v = b["value"]
        return (f'<div class="progress"><div class="pl"><span>{inline(b["label"])}</span><b>{v:g}%</b></div>'
                f'<div class="pb" role="progressbar" aria-valuenow="{v:g}" aria-valuemin="0" aria-valuemax="100">'
                f'<i style="width:{v:g}%"></i></div></div>')
    if t == "table":
        head = "".join(f"<th>{inline(c)}</th>" for c in b["head"])
        rows = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in b["rows"])
        return f'<div class="tbl"><table>{f"<thead><tr>{head}</tr></thead>" if head else ""}<tbody>{rows}</tbody></table></div>'
    if t == "code":
        return f'<pre class="code" data-lang="{esc(b["lang"])}"><code>{esc(b["text"])}</code></pre>'
    if t == "mermaid":
        ctx.mermaid = True
        return (f'<figure class="mermaid-wrap"><pre class="mermaid">{esc(b["text"])}</pre>'
                f'<figcaption class="mm-off" data-i18n="mermaidOffline" hidden></figcaption></figure>')
    if t == "steps":
        items = "".join(f'<li><span class="n">{k + 1}</span><span class="s">{inline(x)}</span></li>'
                        for k, x in enumerate(b["items"]))
        return f'<ol class="steps">{items}</ol>'
    if t == "gantt":
        rows = b["rows"]
        if not rows:
            return ""
        lo, hi = min(r["a"] for r in rows), max(r["b"] for r in rows)
        span = hi - lo + 1
        unit = next((r["unit"] for r in rows if r["unit"]), "")
        head = "".join(f"<span>{esc(unit)}{k}</span>" for k in range(lo, hi + 1))
        body = "".join(
            f'<div class="gr"><span class="gn">{inline(r["name"])}</span><div class="gt" style="--n:{span}">'
            f'<i class="s{k % 8 + 1}" style="grid-column:{r["a"] - lo + 1}/{r["b"] - lo + 2}" '
            f'title="{esc(r["name"])} : {esc(unit)}{r["a"]}–{esc(unit)}{r["b"]}"></i></div></div>'
            for k, r in enumerate(rows))
        return (f'<div class="gantt"><div class="gr gh"><span class="gn"></span>'
                f'<div class="gt" style="--n:{span}">{head}</div></div>{body}</div>')
    if t == "cards":
        pick = b.get("pick")
        cards = []
        for c in b["cards"]:
            pros = "".join(f'<li class="pro">{inline(x)}</li>' for x in c["pros"])
            cons = "".join(f'<li class="con">{inline(x)}</li>' for x in c["cons"])
            lst = f'<ul class="pc">{pros}{cons}</ul>' if pros or cons else ""
            btn = (f'<button type="button" class="pick-btn" data-i18n="choose"></button>' if pick else "")
            cards.append(f'<div class="card" data-val="{esc(c["title"])}"><h4>{inline(c["title"])}</h4>'
                         f'<p>{inline(c["desc"])}</p>{lst}{btn}</div>')
        attr = f' data-pick="{esc(pick)}"' if pick else ""
        return f'<div class="cards"{attr}>{"".join(cards)}</div>'
    if t == "cols":
        cols = "".join(f'<div class="col">{blocks(c, ctx)}</div>' for c in b["cols"])
        return f'<div class="cols" style="--n:{len(b["cols"])}">{cols}</div>'
    if t == "tabs":
        heads = "".join(f'<button type="button" role="tab" data-tab="{k}"{SEL if k == 0 else ""}>{inline(tb["name"])}</button>'
                        for k, tb in enumerate(b["tabs"]))
        panes = "".join(f'<div class="pane" role="tabpanel"{"" if k == 0 else " hidden"}>{blocks(tb["blocks"], ctx)}</div>'
                        for k, tb in enumerate(b["tabs"]))
        return f'<div class="tabs"><div class="tabbar" role="tablist">{heads}</div>{panes}</div>'
    if t == "details":
        return f'<details class="det"><summary>{inline(b["title"])}</summary><div>{blocks(b["blocks"], ctx)}</div></details>'
    if t == "link":
        href, alt = b["href"], ""
        if not is_url(href) and not href.startswith(("mailto:", "#")):
            m = re.match(r"^(.*?)(?::(\d+))?(?::(\d+))?$", href)
            p = Path(m.group(1))
            p = (p if p.is_absolute() else ctx.root / p).resolve()
            if not p.exists():
                ctx.warnings.append(f"missing link target: {href}")
            href = p.as_uri()
            tpl = EDITORS.get(ctx.editor, ctx.editor if "{path}" in (ctx.editor or "") else "")
            if tpl and p.is_file():  # source file -> open in the editor (at the line), file:// as a fallback
                alt = (f' <a class="alt" href="{esc(href)}" target="_blank" rel="noopener" '
                       f'data-i18n-title="fileOpen">📄</a>')
                href = tpl.format(path=p.as_posix(), line=m.group(2) or 1, col=m.group(3) or 1)
                return (f'<p class="link"><a href="{esc(href)}" data-i18n-title="editorOpen">✎ {inline(b["label"])}</a>'
                        f'<code class="lk">{esc(b["href"])}</code>{alt}</p>')
        return f'<p class="link"><a href="{esc(href)}" target="_blank" rel="noopener">🔗 {inline(b["label"])}</a></p>'
    if t == "compare":
        a, c = ctx.asset(b["a"]), ctx.asset(b["b"])
        if not a or not c:
            return missing(b["a"] if not a else b["b"])
        return (f'<figure class="cmp"><div class="cmp-box" style="--pos:50%">'
                f'<img src="{esc(a)}" alt="" loading="lazy"><img class="after" src="{esc(c)}" alt="" loading="lazy">'
                f'<span class="cmp-l" data-i18n="cmpBefore"></span><span class="cmp-r" data-i18n="cmpAfter"></span>'
                f'<input type="range" min="0" max="100" value="50" aria-label="before / after"></div>'
                f'{caption(b["caption"])}</figure>')
    if t == "html":
        url = ctx.asset(b["src"])
        if not url:
            return missing(b["src"])
        return (f'<figure class="htmlfr"><iframe src="{esc(url)}" sandbox="allow-scripts" loading="lazy" '
                f'style="height:{b["height"]}px" title="{esc(b["caption"] or b["src"])}"></iframe>'
                f'<figcaption>{inline(b["caption"])} <a href="{esc(url)}" target="_blank" rel="noopener">↗</a>'
                f'</figcaption></figure>')
    if t == "q":
        return question(b, ctx)
    return ""


def blocks(lst, ctx):
    return "".join(block(b, ctx) for b in lst)


def comment_box(sec):
    return (f'<details class="sec-comment" data-c="{esc(sec["id"])}"><summary data-i18n="comment"></summary>'
            f'<textarea rows="3" data-i18n-ph="commentPh"></textarea></details>')


def body_html(plan, ctx, comments=True):
    out, cur = [], None
    for b in plan.blocks:
        if b["t"] == "h" and b["level"] <= 2:
            if cur and comments:
                out.append(comment_box(cur))
            cur = {"id": b["id"], "text": b["text"]}
            ctx.sections.append(cur)
        out.append(block(b, ctx, top=True))
    if cur and comments:
        out.append(comment_box(cur))
    return "".join(out)


def next_opts(plan, lang):
    """'What next?' options: the plan's !next, else defaults; None if `next: off`."""
    if plan.meta.get("next", "on").lower() in ("off", "no", "0", "false"):
        return None
    if plan.next is not None:
        return plan.next
    nb = {"qt": "next", "id": "next"}
    opts_parse(nb, NEXT_DEFAULT.get(lang or "fr", NEXT_DEFAULT["fr"]), lambda m: None)
    return nb


def next_li(b, k):
    return (f'<li draggable="true" data-k="{esc(k)}"><span class="grip" aria-hidden="true">⋮⋮</span>'
            f'<input type="checkbox" aria-label="{esc(b["labels"].get(k, k))}"><span class="rk"></span>'
            f'<span class="lbl">{opt_label(dict(b, keyed=False), k)}</span>'
            f'<button type="button" class="up" data-i18n-title="up">↑</button>'
            f'<button type="button" class="down" data-i18n-title="down">↓</button></li>')


def next_panel(b):
    if not b:
        return ""
    items = "".join(next_li(b, k) for k in b["opts"])
    return (f'<section class="next" id="next" aria-labelledby="next-t">'
            f'<h2 id="next-t" data-i18n="nextTitle"></h2><p class="hint" data-i18n="nextHint"></p>'
            f'<ol class="rank next-list">{items}</ol>'
            f'<div class="next-add"><input type="text" class="next-new" data-i18n-ph="nextAddPh">'
            f'<button type="button" class="btn" data-i18n="nextAdd"></button></div>'
            f'<p class="hint next-none" data-i18n="nextNone" hidden></p>'
            f'<label class="opt next-pause"><input type="checkbox"><span data-i18n="nextPause"></span></label>'
            f'<textarea class="next-note" rows="2" data-i18n-ph="nextNotePh"></textarea></section>')


def q_meta(b):
    keep = ("id", "qt", "label", "req", "opts", "labels", "keyed", "rows", "cols", "items", "keys", "agent",
            "min", "max", "def", "other")
    return {k: b[k] for k in keep if k in b}


def render_page(plan, info, root, vdir, new_ids):
    """info: id, v, title, intro, date, project, plan_path, tool, key, prev_key, versions."""
    ctx = Ctx(root, vdir, new_ids)
    lang = plan.meta.get("lang", "").lower()
    lang = lang if lang in STRINGS else ""
    ctx.lang = lang or "fr"
    ctx.editor = info.get("editor") or "vscode"
    ctx.decisions = info.get("decisions") or {}
    ctx.default_dec_v = info["v"] - 1 if info["v"] > 1 else None
    chg = info.get("changes")  # (changed ids, new ids, removed titles) vs the previous version
    if chg:
        ctx.sec_status = {k: "chg" for k in chg[0]}
        ctx.sec_status.update({k: "new" for k in chg[1]})
        ctx.sec_status["__any"] = "same"  # non-empty -> headings get data-sec
    comments = plan.meta.get("comments", "on").lower() not in ("off", "no", "0", "false")
    body = body_html(plan, ctx, comments)
    changes = ""
    if chg and (chg[0] or chg[1] or chg[2]):
        changes = (f'<div id="chgBar" class="callout tip" data-c="{len(chg[0])}" data-n="{len(chg[1])}" '
                   f'data-pv="{info["v"] - 1}"><span class="ic">Δ</span><div><span class="chg-txt"></span>'
                   + (f' <span class="chg-del"><span data-i18n="chgDel"></span> '
                      f'{" · ".join(inline(x) for x in chg[2])}</span>' if chg[2] else "")
                   + ' <button type="button" class="btn sm" id="chgOnly" data-i18n="chgOnly"></button></div></div>')
    nxt = next_opts(plan, lang)
    toc = "".join(f'<li class="l{lvl}"><a href="#{esc(hid)}">{inline(txt)}</a></li>' for lvl, txt, hid in ctx.toc)
    meta = {
        "id": info["id"], "v": info["v"], "title": info["title"],
        "intro": info["intro"] or first_paragraph(plan.blocks),
        "date": info["date"], "project": info["project"], "planPath": info["plan_path"],
        "tool": info["tool"], "lang": lang, "key": info["key"], "prevKey": info.get("prev_key"),
        "versions": info["versions"],
        "questions": [q_meta(q) for q in plan.questions],
        "sections": [{"id": s["id"], "text": s["text"]} for s in ctx.sections] if comments else [],
        "next": {k: nxt[k] for k in ("opts", "labels", "keyed", "rec") if k in nxt} if nxt else None,
        "prevQ": {k: q_meta(q) for k, q in (info.get("prev_q") or {}).items()},
    }
    js_json = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    gone = set(info.get("gone") or ())
    versions = "".join(
        f'<span class="gone" data-i18n-title="gcGone">v{v}</span>' if v in gone and v != info["v"] else
        f'<a href="../v{v}/index.html"{CUR if v == info["v"] else ""}>v{v}</a>'
        for v in info["versions"])
    status = info.get("status")
    st_txt = (STRINGS.get(lang) or STRINGS["fr"]).get(f"st_{status}", status) if status else ""
    page = (TPL / "page.html").read_text(encoding="utf-8")
    repl = {
        "{{LANG}}": lang or "fr",
        "{{TITLE}}": esc(info["title"]),
        "{{CSS}}": (TPL / "style.css").read_text(encoding="utf-8"),
        "{{ANSWERS_JS}}": (TPL / "answers.js").read_text(encoding="utf-8"),
        "{{JS}}": (TPL / "app.js").read_text(encoding="utf-8"),
        "{{CHANGES}}": changes,
        "{{BODY}}": body,
        "{{TOC}}": toc + ('<li class="l1"><a href="#next" data-i18n="nextTitle"></a></li>' if nxt else ""),
        "{{NEXT}}": next_panel(nxt),
        "{{VERSIONS}}": versions,
        "{{META_LINE}}": esc(f"v{info['v']} · {Path(info['project']).name} · {info['date']}")
                         + (f' · <span class="st st-{esc(status)}">{esc(st_txt)}</span>' if status else ""),
        "{{PLAN}}": js_json(meta),
        "{{I18N}}": js_json(STRINGS),
        "{{MERMAID}}": (f'<script src="{MERMAID}" defer onerror="window.__mmFail=1"></script>' if ctx.mermaid else ""),
    }
    for k, v in repl.items():
        page = page.replace(k, v)
    (Path(vdir) / "index.html").write_text(page, encoding="utf-8")
    return ctx.warnings
