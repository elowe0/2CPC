"""2CPC DSL -> block tree.

Each block is a dict with a "t" (type) key. Containers (cols, tabs, details)
hold child block lists. Questions have t="q" and a "qt" (question type).
"""
import re

from . import draw

HEADER_KEYS = ("title", "lang", "intro", "comments", "other")
CALLOUTS = ("note", "tip", "warn", "danger")
QTYPES = ("choice", "multi", "text", "line", "number", "date", "scale",
          "yesno", "rank", "approve", "matrix", "pick")
RAW = ("code", "mermaid", "cards", "draw")
CONTAINERS = ("cols", "tabs", "details")

_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_KEY = re.compile(r"^([A-Za-z0-9_.-]{1,40})=(?!=)(.*)$")
_NUM = r"-?\d+(?:\.\d+)?"
OPT_TYPES = ("choice", "multi", "rank", "approve")
REC_TYPES = ("choice", "multi")
# max number of |-fields per question type (id | label | ...)
QFIELDS = {"choice": 3, "multi": 3, "rank": 3, "approve": 3, "text": 3, "line": 3,
           "date": 3, "yesno": 3, "number": 4, "scale": 4, "matrix": 4, "pick": 2}
E_SEMI, E_PIPE = "\x01", "\x02"   # placeholders for \; and \|


def _unesc(o):
    if isinstance(o, str):
        return o.replace(E_SEMI, ";").replace(E_PIPE, "|")
    if isinstance(o, list):
        return [_unesc(x) for x in o]
    if isinstance(o, tuple):
        return tuple(_unesc(x) for x in o)
    if isinstance(o, dict):
        return {_unesc(k): _unesc(v) for k, v in o.items()}
    return o


def _reesc(s):
    return s.replace(E_SEMI, "\\;").replace(E_PIPE, "\\|")


def slug(s, n=48):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:n].strip("-") or "x"


def split(s, sep):
    return [p.strip() for p in s.split(sep)] if s.strip() else []


def pipes(s):
    return [p.strip() for p in s.split("|")]


class Plan:
    def __init__(self):
        self.meta = {}
        self.blocks = []
        self.questions = []   # flat list of question blocks, in order
        self.warnings = []


def parse(text):
    plan = Plan()
    text = text.replace("\\;", E_SEMI).replace("\\|", E_PIPE)
    lines = re.sub(r"\r+\n?", "\n", text).split("\n")
    i, n = 0, len(lines)

    # header keys (only before any content)
    while i < n:
        ln = lines[i].strip()
        if not ln:
            i += 1
            continue
        m = re.match(r"^(%s):\s*(.*)$" % "|".join(HEADER_KEYS), ln)
        if not m:
            break
        plan.meta[m.group(1)] = m.group(2).strip()
        i += 1

    other_on = plan.meta.get("other", "on").lower() not in ("off", "no", "0", "false")
    root = []
    stack = []  # entries: dict(block=..., target=list)
    target = root
    para, lst, quote = [], None, []
    ids = set()
    auto = {"todo": 0}
    last_cards = [None]
    heads = {}

    def warn(msg):
        plan.warnings.append(f"l{i + 1}: {msg}")

    def flush():
        nonlocal para, lst, quote
        if para:
            target.append({"t": "p", "text": " ".join(para)})
            para = []
        if lst:
            target.append(lst)
            lst = None
        if quote:
            target.append({"t": "quote", "text": " ".join(quote)})
            quote = []

    def add_q(b):
        qid = b["id"]
        if qid in ids:
            warn(f"duplicate id '{qid}'")
            k = 2
            while f"{qid}{k}" in ids:
                k += 1
            b["id"] = qid = f"{qid}{k}"
        ids.add(qid)
        target.append(b)
        plan.questions.append(b)

    def raw_until_end(start, kind):
        out, j = [], start
        while j < n and lines[j].strip() != "!end":
            out.append(lines[j] if kind == "cards" else _reesc(lines[j]))
            j += 1
        if j >= n:
            plan.warnings.append(f"l{start}: missing !end")
        return out, j + 1

    while i < n:
        line = lines[i]
        s = line.strip()

        if not s:
            flush()
            i += 1
            continue

        # headings
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            flush()
            text = m.group(2).strip()
            hid = slug(text)
            heads[hid] = heads.get(hid, 0) + 1
            if heads[hid] > 1:
                hid = f"{hid}-{heads[hid]}"
            target.append({"t": "h", "level": len(m.group(1)), "text": text, "id": hid})
            i += 1
            continue

        if re.match(r"^-{3,}$", s):
            flush()
            target.append({"t": "hr"})
            i += 1
            continue

        # quotes / callouts
        if s.startswith(">"):
            body = s[1:].strip()
            m = re.match(r"^(%s):\s*(.*)$" % "|".join(CALLOUTS), body, re.I)
            if m:
                flush()
                target.append({"t": "callout", "kind": m.group(1).lower(), "text": m.group(2)})
            else:
                if para or lst:
                    flush()
                quote.append(body)
            i += 1
            continue

        # lists
        m = re.match(r"^([-*]|\d+[.)])\s+(.*)$", s)
        if m and not s.startswith("**"):
            kind = "ol" if m.group(1)[0].isdigit() else "ul"
            if para or quote:
                flush()
            if lst and lst["t"] != kind:
                flush()
            if not lst:
                lst = {"t": kind, "items": []}
            lst["items"].append(m.group(2))
            i += 1
            continue

        # directives
        if s.startswith("!") and len(s) > 1 and s[1].isalpha():
            flush()
            m = re.match(r"^!(\w+)\s*(.*)$", s)
            name, arg = m.group(1).lower(), m.group(2).strip()
            i += 1

            if name == "end":
                if stack:
                    stack.pop()
                    target = stack[-1]["target"] if stack else root
                else:
                    warn("stray !end")
                continue
            if name == "col":
                if stack and stack[-1]["block"]["t"] == "cols":
                    blk = stack[-1]["block"]
                    blk["cols"].append([])
                    target = stack[-1]["target"] = blk["cols"][-1]
                else:
                    warn("!col outside !cols")
                continue
            if name == "tab":
                if stack and stack[-1]["block"]["t"] == "tabs":
                    blk = stack[-1]["block"]
                    blk["tabs"].append({"name": arg or f"#{len(blk['tabs']) + 1}", "blocks": []})
                    target = stack[-1]["target"] = blk["tabs"][-1]["blocks"]
                else:
                    warn("!tab outside !tabs")
                continue
            if name in CONTAINERS:
                if name == "cols":
                    blk = {"t": "cols", "cols": [[]]}
                    inner = blk["cols"][0]
                elif name == "tabs":
                    blk = {"t": "tabs", "tabs": [{"name": arg or "#1", "blocks": []}]}
                    inner = blk["tabs"][0]["blocks"]
                else:
                    blk = {"t": "details", "title": arg or "…", "blocks": []}
                    inner = blk["blocks"]
                target.append(blk)
                stack.append({"block": blk, "target": inner})
                target = inner
                continue
            if name in RAW:
                body, i = raw_until_end(i, name)
                if name == "code":
                    target.append({"t": "code", "lang": arg, "text": "\n".join(body)})
                elif name == "mermaid":
                    target.append({"t": "mermaid", "text": "\n".join(body)})
                elif name == "draw":
                    d = draw.parse(body, warn)
                    d.update({"t": "draw", "caption": arg})
                    target.append(d)
                else:
                    cards = []
                    for b in body:
                        if not b.strip():
                            continue
                        p = pipes(b)
                        pros, cons = [], []
                        for it in split(p[2] if len(p) > 2 else "", ";"):
                            (cons if it.startswith("-") else pros).append(it.lstrip("+-").strip())
                        cards.append({"title": p[0], "desc": p[1] if len(p) > 1 else "",
                                      "pros": pros, "cons": cons})
                    blk = {"t": "cards", "cards": cards, "pick": None}
                    last_cards[0] = blk
                    target.append(blk)
                continue

            p = pipes(arg)
            if name in ("img", "audio", "video"):
                target.append({"t": name, "src": p[0], "caption": p[1] if len(p) > 1 else ""})
            elif name == "chart":
                ctype = (p[0] or "bar").lower()
                if ctype not in ("bar", "hbar", "line", "pie", "donut"):
                    warn(f"unknown chart '{ctype}', using bar")
                    ctype = "bar"
                data = []
                for kv in split(p[2] if len(p) > 2 else "", ","):
                    k, _, v = kv.partition("=")
                    try:
                        data.append((k.strip(), float(v.replace(" ", ""))))
                    except ValueError:
                        warn(f"bad chart value '{kv}'")
                target.append({"t": "chart", "kind": ctype,
                               "title": p[1] if len(p) > 1 else "", "data": data})
            elif name == "kpi":
                items = []
                for kv in split(arg, ";"):
                    k, _, v = kv.partition("=")
                    items.append((k.strip(), v.strip()))
                target.append({"t": "kpi", "items": items})
            elif name == "progress":
                try:
                    val = float(p[1].rstrip("%")) if len(p) > 1 else 0
                except ValueError:
                    val = 0
                target.append({"t": "progress", "label": p[0], "value": max(0, min(100, val))})
            elif name == "table":
                head = pipes(arg.strip("|")) if arg.strip("|").strip() else []
                rows = []
                while i < n and lines[i].strip().startswith("|"):
                    rows.append(pipes(lines[i].strip().strip("|")))
                    i += 1
                target.append({"t": "table", "head": head, "rows": rows})
            elif name == "steps":
                target.append({"t": "steps", "items": split(arg, ";")})
            elif name == "gantt":
                rows = []
                for kv in split(arg, ";"):
                    k, _, v = kv.partition("=")
                    mm = re.match(r"^([^\d-]*)(\d+)\s*(?:-\s*[^\d]*(\d+))?$", v.strip())
                    if not mm:
                        warn(f"bad gantt '{kv}'")
                        continue
                    a = int(mm.group(2))
                    b = int(mm.group(3) or a)
                    rows.append({"name": k.strip(), "a": min(a, b), "b": max(a, b), "unit": mm.group(1).strip()})
                target.append({"t": "gantt", "rows": rows})
            elif name == "link":
                target.append({"t": "link", "label": p[0], "href": p[1] if len(p) > 1 else p[0]})
            elif name == "todo":
                if len(p) > 1 and _ID.match(p[0]):
                    qid, items = p[0], split(p[1], ";")
                else:
                    auto["todo"] += 1
                    qid = "todo" if auto["todo"] == 1 else f"todo{auto['todo']}"
                    items = split(arg, ";")
                if any(not x for x in items):
                    warn(f"!todo {qid}: empty item")
                    items = [x for x in items if x]
                add_q({"t": "q", "qt": "todo", "id": qid, "label": "", "req": False, "items": items})
            else:
                warn(f"unknown directive !{name}")
                target.append({"t": "p", "text": s})
            continue

        # questions
        m = re.match(r"^\?(\w+)\s+(.*)$", s)
        if m and m.group(1).lower() not in QTYPES and m.group(2).count("|"):
            warn(f"unknown question type ?{m.group(1)}")
        if m and m.group(1).lower() in QTYPES:
            flush()
            qt = m.group(1).lower()
            p = pipes(m.group(2))
            qid = p[0]
            req = qid.endswith("!")
            qid = qid.rstrip("!")
            if not _ID.match(qid):
                warn(f"bad question id '{qid}'")
                qid = slug(qid, 20)
            if len(p) > QFIELDS[qt]:
                warn(f"?{qt} {qid}: {len(p) - QFIELDS[qt]} extra '|' field(s) ignored (escape as \\|)")
            b = {"t": "q", "qt": qt, "id": qid, "req": req, "label": p[1] if len(p) > 1 else qid}
            rest = p[2] if len(p) > 2 else ""
            f3 = p[3] if len(p) > 3 else ""
            if qt in OPT_TYPES:
                opts_parse(b, rest, warn)
            elif qt in ("scale", "number"):
                mm = re.match(r"^(%s)\s*(?:-|\.\.)\s*(%s)$" % (_NUM, _NUM), rest)
                if qt == "number" and rest and not mm and re.match("^%s$" % _NUM, rest) and not f3:
                    f3 = rest  # ?number id | Q | default
                elif rest and not mm:
                    warn(f"?{qt} {qid}: bad range '{rest}' (use min-max)")
                lo, hi = (float(mm.group(1)), float(mm.group(2))) if mm else (None, None)
                if qt == "scale":
                    lo, hi = (int(lo), int(hi)) if mm else (1, 5)
                    if hi - lo > 20 or hi <= lo:
                        warn(f"?scale {qid}: range must be 2..21 steps, using 1-5")
                        lo, hi = 1, 5
                    b["min"], b["max"] = lo, hi
                elif mm:
                    b["min"], b["max"] = min(lo, hi), max(lo, hi)
                if f3:
                    try:
                        d = float(f3)
                        if b.get("min") is not None and not (b["min"] <= d <= b["max"]):
                            warn(f"?{qt} {qid}: default {f3} out of range")
                        else:
                            b["def"] = f"{d:g}"
                    except ValueError:
                        warn(f"?{qt} {qid}: bad default '{f3}'")
            elif qt == "yesno":
                if rest:
                    v = rest.lower()
                    if v in ("yes", "oui", "y", "o", "true", "1"):
                        b["def"] = "yes"
                    elif v in ("no", "non", "n", "false", "0"):
                        b["def"] = "no"
                    else:
                        warn(f"?yesno {qid}: bad default '{rest}' (oui|non)")
            elif qt in ("text", "line", "date"):
                if rest:
                    b["def"] = rest
            elif qt == "matrix":
                b["rows"] = split(rest, ";")
                b["cols"] = split(f3, ";")
                if not b["rows"] or not b["cols"]:
                    warn(f"?matrix {qid}: needs rows | cols")
            elif qt == "pick":
                cb = last_cards[0]
                if cb is None:
                    warn(f"?pick {qid}: no !cards before")
                    b["opts"] = []
                else:
                    b["opts"] = [c["title"] for c in cb["cards"]]
                    cb["pick"] = qid
            if qt in ("choice", "multi", "pick"):
                b["other"] = other_on
            add_q(b)
            i += 1
            continue

        # plain text
        if lst or quote:
            flush()
        para.append(s)
        i += 1

    flush()
    if stack:
        plan.warnings.append("unclosed container (missing !end)")
    plan.blocks = _unesc(root)
    plan.questions = [q for q in _iter_q(plan.blocks)]
    plan.meta = _unesc(plan.meta)
    return plan


def _iter_q(blocks):
    for b in blocks:
        if b["t"] == "q":
            yield b
        elif b["t"] == "cols":
            for c in b["cols"]:
                yield from _iter_q(c)
        elif b["t"] == "tabs":
            for tb in b["tabs"]:
                yield from _iter_q(tb["blocks"])
        elif b["t"] == "details":
            yield from _iter_q(b["blocks"])


def opts_parse(b, rest, warn):
    """Options 'KEY=Label :: detail*' separated by ';'. KEY optional (defaults to label)."""
    qt, qid = b["qt"], b["id"]
    raw = [x.strip() for x in rest.split(";")] if rest.strip() else []
    opts, labels, details, rec, keyed = [], {}, {}, [], False
    for k, o in enumerate(raw):
        if not o:
            warn(f"?{qt} {qid}: empty item #{k + 1}")
            continue
        star = o.endswith("*")
        if star:
            o = o[:-1].rstrip()
        m = _KEY.match(o)
        if m:
            key, label = m.group(1), m.group(2).strip()
            keyed = True
        else:
            key = label = o
        detail = ""
        if " :: " in label or label.endswith(" ::"):
            label, _, detail = label.partition("::")
            label, detail = label.strip(), detail.strip()
            if not m:
                key = label
        if key in labels:
            warn(f"?{qt} {qid}: duplicate item '{key}'")
            continue
        if star:
            if qt in REC_TYPES:
                rec.append(key)
            else:
                warn(f"?{qt} {qid}: '*' ignored (only ?choice/?multi)")
        opts.append(key)
        labels[key] = label or key
        if detail:
            details[key] = detail
    if not opts:
        warn(f"?{qt} {qid}: no options")
    b["opts"], b["labels"], b["rec"], b["keyed"] = opts, labels, rec, keyed
    if details:
        b["details"] = details


def first_paragraph(blocks):
    for b in blocks:
        if b["t"] == "p":
            return b["text"]
    return ""
