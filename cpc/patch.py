"""Sections of a plan's DSL text: extents (for `patch`) and hashes (for "changed since vN-1")."""
import hashlib
import re

from .parser import HEADER_KEYS, parse, slug

_NEXT = re.compile(r"^\s*!next\b")
_OP = re.compile(r"^@(replace|after|before|delete|append|meta|next)\b[ \t]*(.*)$")
_HEAD = re.compile(r"^\s*(#{1,3})\s+(.*)$")
_ANCHOR = re.compile(r"\{#([A-Za-z0-9_.-]+)\}\s*$")


class PatchError(Exception):
    pass


def lines_of(text):
    return re.sub(r"\r+\n?", "\n", text).split("\n")


def sections(text, max_level=3):
    """Top-level headings (level <= max_level) with their line extent [start, end).

    A section ends at the next top-level heading of the same or a higher level, at a `!next` line, or at EOF.
    """
    lines = lines_of(text)
    heads = [b for b in parse(text).blocks if b["t"] == "h"]
    nxt = [k for k, ln in enumerate(lines) if _NEXT.match(ln)]
    out = []
    for k, h in enumerate(heads):
        if h["level"] > max_level:
            continue
        end = len(lines)
        for h2 in heads[k + 1:]:
            if h2["level"] <= h["level"]:
                end = h2["line"]
                break
        end = min([end] + [x for x in nxt if x > h["line"]])
        anchor = _ANCHOR.search(lines[h["line"]])
        out.append({"id": h["id"], "text": h["text"], "level": h["level"], "start": h["line"], "end": end,
                    "anchor": anchor.group(1) if anchor else None})
    return out


def section_hashes(text):
    """{section id: (text, hash)} for the sections that get a comment box (levels 1-2).

    A level-2 section stops at the next level-1 or level-2 heading."""
    lines = lines_of(text)
    secs = sections(text, max_level=2)
    out = {}
    for k, s in enumerate(secs):
        end = min(s["end"], secs[k + 1]["start"]) if k + 1 < len(secs) else s["end"]
        body = "\n".join(ln.rstrip() for ln in lines[s["start"]:end]).strip()
        out[s["id"]] = (s["text"], hashlib.sha1(body.encode("utf-8")).hexdigest()[:12])
    return out


def diff_sections(old_text, new_text):
    """-> (changed ids, new ids, removed titles)."""
    old, new = section_hashes(old_text), section_hashes(new_text)
    changed = [k for k in new if k in old and new[k][1] != old[k][1]]
    added = [k for k in new if k not in old]
    removed = [old[k][0] for k in old if k not in new]
    return changed, added, removed


def find(secs, target):
    """target: '## Title' (exact text, else unique prefix; level must match) or '{#id}' / '#id' (anchor or slug)."""
    t = target.strip()
    m = re.match(r"^\{?#([A-Za-z0-9_.-]+)\}?$", t)
    if m and not t.startswith("# "):
        hits = [s for s in secs if s["anchor"] == m.group(1)] or [s for s in secs if s["id"] == m.group(1)]
    else:
        m = re.match(r"^(#{1,3})\s+(.*)$", t)
        if not m:
            raise PatchError(f"bad target '{target}' (use '## Title' or '{{#id}}')")
        lvl, txt = len(m.group(1)), _ANCHOR.sub("", m.group(2)).strip()
        same = [s for s in secs if s["level"] == lvl]
        hits = [s for s in same if s["text"] == txt]
        if not hits:
            low = txt.lower()
            hits = [s for s in same if s["text"].lower().startswith(low)] or \
                   [s for s in same if slug(s["text"]) == slug(txt)]
    if not hits:
        raise PatchError(f"target not found: {target}")
    if len(hits) > 1:
        raise PatchError(f"ambiguous target '{target}': " + " · ".join(f"l{s['start'] + 1} {s['text']}" for s in hits))
    return hits[0]


def parse_ops(patch_text):
    ops, cur = [], None
    for ln in lines_of(patch_text):
        m = _OP.match(ln)
        if m:
            cur = {"op": m.group(1), "arg": m.group(2).strip(), "body": []}
            ops.append(cur)
        elif cur is not None:
            cur["body"].append(ln)
        elif ln.strip():
            raise PatchError(f"text before the first @operation: {ln.strip()[:60]}")
    for o in ops:
        while o["body"] and not o["body"][-1].strip():
            o["body"].pop()
        while o["body"] and not o["body"][0].strip():
            o["body"].pop(0)
        if o["op"] in ("replace", "after", "before", "delete") and not o["arg"]:
            raise PatchError(f"@{o['op']} needs a target")
        if o["op"] in ("replace", "after", "before", "append") and not o["body"]:
            raise PatchError(f"@{o['op']} {o['arg']}: empty content")
    if not ops:
        raise PatchError("no @operation found")
    return ops


def _set_meta(lines, key, value):
    if key not in HEADER_KEYS:
        raise PatchError(f"unknown header key '{key}'")
    k = 0
    while k < len(lines):  # header block = leading `key: value` / blank lines
        s = lines[k].strip()
        if s and not re.match(r"^(%s):" % "|".join(HEADER_KEYS), s):
            break
        if s.startswith(key + ":"):
            lines[k] = f"{key}: {value}"
            return lines
        k += 1
    last = max([j for j in range(k) if lines[j].strip()], default=-1)
    return lines[:last + 1] + [f"{key}: {value}"] + lines[last + 1:]


def apply(text, patch_text):
    """Apply @operations to a plan's DSL text -> (new text, n ops). Raises PatchError (nothing applied)."""
    lines = lines_of(text)
    for o in parse_ops(patch_text):
        op, body = o["op"], o["body"]
        if op == "meta":
            m = re.match(r"^(\w+):\s*(.*)$", o["arg"])
            if not m:
                raise PatchError(f"@meta expects 'key: value', got '{o['arg']}'")
            lines = _set_meta(lines, m.group(1), m.group(2))
            continue
        if op == "next":  # replace the !next line (or add one at the end)
            if not o["arg"]:
                raise PatchError("@next needs the options (same syntax as !next)")
            nx = [k for k, ln in enumerate(lines) if _NEXT.match(ln)]
            if nx:
                lines[nx[0]] = "!next " + o["arg"]
            else:
                while lines and not lines[-1].strip():
                    lines.pop()
                lines += ["", "!next " + o["arg"], ""]
            continue
        if op == "append":
            nx = [k for k, ln in enumerate(lines) if _NEXT.match(ln)]
            at = nx[0] if nx else len(lines)
            while at > 0 and not lines[at - 1].strip():
                at -= 1
            lines = lines[:at] + [""] + body + [""] + lines[at:]
            continue
        s = find(sections("\n".join(lines)), o["arg"])
        a, b = s["start"], s["end"]
        while b > a + 1 and not lines[b - 1].strip():  # keep the blank lines between sections
            b -= 1
        if op == "delete":
            lines = lines[:a] + lines[b:]
            while a < len(lines) and a > 0 and not lines[a].strip() and not lines[a - 1].strip():
                del lines[a]
        elif op == "replace":
            if not _HEAD.match(body[0]):  # content without heading: keep the original one
                body = [lines[a]] + body
            lines = lines[:a] + body + ([""] if b < len(lines) and lines[b].strip() else []) + lines[b:]
        elif op == "after":
            lines = lines[:b] + [""] + body + ([""] if b < len(lines) and lines[b].strip() else []) + lines[b:]
        elif op == "before":
            lines = lines[:a] + body + [""] + lines[a:]
    return "\n".join(lines), len(parse_ops(patch_text))
