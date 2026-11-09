"""Answers pasted back by the user (`2CPC <id> vN` + key=value lines): parsing, and the `!decisions` table."""
import json
import re

HEAD = re.compile(r"^2CPC\s+(\S+)\s+v(\d+)\b")
CTX_HEAD = re.compile(r"^\[2CPC\].*\(v(\d+),")


def header(text):
    """-> (plan id or None, version or None)."""
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        m = HEAD.match(s)
        if m:
            return m.group(1), int(m.group(2))
        m = CTX_HEAD.match(s)
        if m:
            return None, int(m.group(1))
        break
    return None, None


DELTA = re.compile(r"^2CPC\s+\S+\s+v\d+\s+Δ\s*$")


def is_delta(text):
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return bool(DELTA.match(first))


def merge(old_text, delta_text):
    """Apply a "What's new" answer (header `2CPC id vN Δ`) to the saved one: changed lines replace, `key=` removes."""
    def key(s):  # labels "(…)" dropped, so compact and "+ Context" answers share keys
        if s.startswith("#"):
            i = s.find('="')
            return s[:i] if i >= 0 else s.rstrip("=")
        return _split_kv(s)[0]

    def body(text):
        out = {}
        for ln in text.splitlines():
            s = ln.strip()
            if s and not HEAD.match(s) and not s.startswith("[2CPC]") and key(s):
                out[key(s)] = s
        return out
    head = re.sub(r"\s+Δ\s*$", "", next(ln.strip() for ln in delta_text.splitlines() if ln.strip()))
    merged = body(old_text) if old_text else {}
    for k, ln in body(delta_text).items():
        if ln.endswith("=") and key(ln) + "=" == ln:  # `key=` -> answer cleared
            merged.pop(k, None)
        else:
            merged[k] = ln
    return "\n".join([head] + list(merged.values()))


def _split_kv(line):
    """'id(Label (x))=value' -> ('id', 'value'): first '=' outside parentheses; labels in () are dropped."""
    depth = 0
    for k, c in enumerate(line):
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        elif c == "=" and depth == 0:
            key, out, d = line[:k], [], 0
            for ch in key:
                if ch == "(":
                    d += 1
                elif ch == ")":
                    d = max(0, d - 1)
                elif d == 0:
                    out.append(ch)
            return "".join(out).strip(), line[k + 1:]
    return None, None


def parse(text, questions=()):
    """-> {"answers": {qid: raw}, "approve": {qid: {key: raw}}, "comments": {section: text}, "next": raw}."""
    qs = {q["id"]: q for q in questions}
    res = {"answers": {}, "approve": {}, "comments": {}, "next": None}
    lines = text.splitlines()
    if lines and lines[0].startswith("[2CPC]"):  # "Answer + Context": skip the header up to '---'
        lines = lines[lines.index("---") + 1:] if "---" in lines else lines[1:]
    for ln in lines:
        s = ln.strip()
        if not s or HEAD.match(s):
            continue
        if s.startswith("#"):
            m = re.match(r'^#(.*?)=(".*")$', s)
            if m:
                res["comments"][m.group(1).strip()] = _json(m.group(2))
            continue
        key, val = _split_kv(s)
        if not key:
            continue
        if key in qs or (not qs and "." not in key and not key.startswith("next")):
            res["answers"][key] = val
        elif key == "next":
            res["next"] = val
        elif key.startswith("next."):
            continue
        else:
            qid = max((i for i in qs if key.startswith(i + ".") and qs[i]["qt"] == "approve"), key=len, default=None)
            if qid is None and not qs and "." in key:
                qid = key.split(".", 1)[0]
            if qid is not None:
                res["approve"].setdefault(qid, {})[key[len(qid) + 1:]] = val
    return res


def _json(s):
    try:
        return json.loads(s)
    except ValueError:
        return s.strip('"')


def split_top(raw, seps):
    """Split on the first separator of `seps` present outside "quoted" parts."""
    for sep in seps:
        parts, cur, q, k = [], "", False, 0
        found = False
        while k < len(raw):
            c = raw[k]
            if c == '"' and (k == 0 or raw[k - 1] != "\\"):
                q = not q
            if not q and raw.startswith(sep, k):
                parts.append(cur)
                cur, k, found = "", k + len(sep), True
                continue
            cur += c
            k += 1
        parts.append(cur)
        if found:
            return [p.strip() for p in parts]
    return [raw.strip()] if raw.strip() else []


def _opt(q, raw, other_word):
    raw = raw.strip()
    if raw.startswith('"'):
        return f"*{other_word} :* {_json(raw)}"
    return (q.get("labels") or {}).get(raw, raw)


def human(q, raw, approve=None, other_word="Autre"):
    """Readable value of one answer for the decisions table (markdown inline)."""
    qt = q["qt"]
    if qt == "approve":
        groups = {"✓": [], "✗": [], "?": [], "": []}
        for k, v in (approve or {}).items():
            v = v.strip()
            sym = v[:1] if v[:1] in ("✓", "✗", "?") else ""
            note = v[1:].strip() if sym else v
            label = (q.get("labels") or {}).get(k, k)
            groups[sym].append(label + (f" (« {_json(note)} »)" if note else ""))
        return " · ".join(f"{s} " + ", ".join(v) if s else ", ".join(v) for s, v in groups.items() if v)
    if raw is None:
        return ""
    if qt in ("choice", "pick"):
        return _opt(q, raw, other_word)
    if qt == "multi":
        return ", ".join(_opt(q, x, other_word) for x in split_top(raw, (" ; ", ",")))
    if qt == "rank":
        return " › ".join(f"{n}. {_opt(q, x, other_word)}" for n, x in enumerate(split_top(raw, (" ; ", ">")), 1))
    if qt in ("text", "line"):
        return _json(raw.strip())
    return raw.strip()


def decision_rows(questions, text, sections=(), other_word="Autre"):
    """Rows [label, value] for every answered question (todos skipped) + section comments."""
    res = parse(text, questions)
    rows = []
    for q in questions:
        if q["qt"] == "todo":
            continue
        if q["qt"] == "approve":
            if q["id"] not in res["approve"]:
                continue
            val = human(q, None, res["approve"][q["id"]], other_word)
        elif q["id"] in res["answers"]:
            val = human(q, res["answers"][q["id"]], other_word=other_word)
        else:
            continue
        rows.append([q.get("label") or q["id"], val])
    titles = {}
    for s in sections:
        titles.setdefault(_short(s), s)
    for name, c in res["comments"].items():
        rows.append([f"💬 {titles.get(name, name)}", c])
    return rows


def _short(s, n=30):
    s = re.sub(r"\s+", " ", re.sub(r"[*`_\[\]]", "", s)).strip()
    s = re.sub(r"\s*[?:]+$", "", s)
    return s if len(s) <= n else s[:n - 1].strip() + "…"
