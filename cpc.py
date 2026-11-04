#!/usr/bin/env python3
"""2CPC — generate interactive plans viewable in the browser.

  cpc.py new [FILE | "Title"] [--id ID] [--file F] [--check] [--no-open] [--root DIR]
      (DSL from FILE/--file, or stdin)
  cpc.py open [ID] [--v N]
  cpc.py list
  cpc.py path ID [--v N]
  cpc.py rebuild [ID]

Plans are stored in <project>/.2cpc/<id>/v<N>/. Format reference: docs/DSL.md
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cpc.parser import parse, slug  # noqa: E402
from cpc.render import render_page  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def die(msg):
    print(f"ERR {msg}")
    sys.exit(1)


# ---------- project / storage ----------

def project_root(arg):
    if arg:
        return Path(arg).resolve()
    cwd = Path.cwd().resolve()
    for p in (cwd, *cwd.parents):
        if (p / ".git").exists():
            return p
    return cwd


def store(root):
    return root / ".2cpc"


def load_index(root):
    f = store(root) / "index.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"plans": {}}


def save_index(root, idx):
    d = store(root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def storage_key(root, pid, v):
    h = hashlib.sha1(str(root).lower().encode()).hexdigest()[:6]
    return f"2cpc:{slug(root.name, 24)}-{h}:{pid}:v{v}"


def read_input(args):
    if args.file:
        data = Path(args.file).read_bytes()
    else:
        if sys.stdin is None or sys.stdin.isatty():
            die("no input: pipe the plan DSL on stdin (heredoc) or use --file")
        data = sys.stdin.buffer.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def open_file(path):
    try:
        if os.name == "nt":
            os.startfile(str(path))  # default browser for .html
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            webbrowser.open(Path(path).as_uri())
    except Exception as e:  # pragma: no cover
        print(f"WARN cannot open browser: {e}")


# ---------- build ----------

def build_version(root, pid, v, entry, text=None):
    """Render v of plan pid. If text is given it is written as plan.txt first."""
    pdir = store(root) / pid
    vdir = pdir / f"v{v}"
    vdir.mkdir(parents=True, exist_ok=True)
    src = vdir / "plan.txt"
    if text is not None:
        src.write_text(text, encoding="utf-8")
    plan = parse(src.read_text(encoding="utf-8"))
    vinfo = entry["versions"][str(v)]
    new_ids = set()
    prev_key = None
    if v > 1:
        psrc = pdir / f"v{v - 1}" / "plan.txt"
        if psrc.is_file():
            prev_ids = {q["id"] for q in parse(psrc.read_text(encoding="utf-8")).questions}
            new_ids = {q["id"] for q in plan.questions} - prev_ids
        prev_key = storage_key(root, pid, v - 1)
    info = {
        "id": pid, "v": v, "title": vinfo["title"],
        "intro": plan.meta.get("intro", ""), "date": vinfo["date"],
        "project": str(root), "plan_path": str(src),
        "tool": str(HERE / "cpc.py"),
        "key": storage_key(root, pid, v), "prev_key": prev_key,
        "versions": sorted(int(k) for k in entry["versions"]),
    }
    warnings = plan.warnings + render_page(plan, info, root, vdir, new_ids)
    return vdir / "index.html", warnings


def summary(plan):
    from collections import Counter
    secs = 0
    stack = list(plan.blocks)
    while stack:
        b = stack.pop()
        if b["t"] == "h" and b["level"] <= 2:
            secs += 1
    c = Counter(q["qt"] for q in plan.questions)
    types = ", ".join(f"{k} {v}" for k, v in c.most_common())
    ids = " ".join(q["id"] for q in plan.questions)
    return (f"{secs} sections · {len(plan.questions)} questions" + (f" ({types})" if types else ""),
            f"ids: {ids}" if ids else "")


def asset_warnings(blocks, root):
    out = []

    def walk(bl):
        for b in bl:
            t = b["t"]
            if t in ("img", "audio", "video") and not re.match(r"^(https?:)?//|^data:", b["src"], re.I):
                p = Path(b["src"])
                if not (p if p.is_absolute() else root / p).is_file():
                    out.append(f"missing asset: {b['src']}")
            elif t == "cols":
                for c in b["cols"]:
                    walk(c)
            elif t == "tabs":
                for tb in b["tabs"]:
                    walk(tb["blocks"])
            elif t == "details":
                walk(b["blocks"])
    walk(blocks)
    return out


def cmd_new(args):
    if args.title and not args.file and Path(args.title).is_file():
        args.file, args.title = args.title, None
    root = project_root(args.root)
    text = read_input(args)
    if not text.strip():
        die("empty plan")
    parsed = parse(text)
    meta = parsed.meta
    if args.check:
        line1, line2 = summary(parsed)
        warns = parsed.warnings + asset_warnings(parsed.blocks, root)
        print(f"CHECK {'ok' if not warns else 'warn'} · {line1}")
        if line2:
            print(line2)
        for w in warns[:30]:
            print(f"WARN {w}")
        return
    title = args.title or meta.get("title") or "Plan"
    idx = load_index(root)
    plans = idx["plans"]
    if args.id:
        pid = slug(args.id, 40)
    else:
        base = slug(title, 40)
        pid, k = base, 1
        while pid in plans or (store(root) / pid).exists():
            k += 1
            pid = f"{base}-{k}"
    entry = plans.get(pid) or {"title": title, "v": 0, "versions": {}}
    v = entry["v"] + 1
    today = dt.date.today().isoformat()
    entry["versions"][str(v)] = {"title": title, "date": today}
    entry.update(title=title, v=v, updated=dt.datetime.now().isoformat(timespec="seconds"))
    plans[pid] = entry
    page, warnings = build_version(root, pid, v, entry, text)
    for old in range(1, v):  # refresh version links on older pages
        if str(old) in entry["versions"] and (store(root) / pid / f"v{old}" / "plan.txt").is_file():
            build_version(root, pid, old, entry)
    save_index(root, idx)
    line1, line2 = summary(parsed)
    print(f"OK {pid} v{v} · {line1}")
    if line2:
        print(line2)
    for w in warnings[:30]:
        print(f"WARN {w}")
    if not args.no_open:
        open_file(page)


def resolve(root, pid, v):
    idx = load_index(root)
    plans = idx["plans"]
    if not plans:
        die(f"no plans in {store(root)}")
    if not pid:
        pid = max(plans, key=lambda k: plans[k].get("updated", ""))
    if pid not in plans:
        die(f"unknown plan '{pid}' (see: cpc.py list)")
    v = v or plans[pid]["v"]
    vdir = store(root) / pid / f"v{v}"
    if not vdir.is_dir():
        die(f"no version v{v} for '{pid}'")
    return pid, v, vdir


def cmd_open(args):
    root = project_root(args.root)
    pid, v, vdir = resolve(root, args.id, args.v)
    open_file(vdir / "index.html")
    print(f"OK {pid} v{v}")


def cmd_path(args):
    root = project_root(args.root)
    _, _, vdir = resolve(root, args.id, args.v)
    print(vdir / "plan.txt")


def cmd_list(args):
    root = project_root(args.root)
    plans = load_index(root)["plans"]
    if not plans:
        print(f"(none in {store(root)})")
        return
    for pid, e in sorted(plans.items(), key=lambda kv: kv[1].get("updated", ""), reverse=True):
        print(f"{pid} v{e['v']} {e.get('updated', '')[:10]} {e['title']}")


def cmd_rebuild(args):
    root = project_root(args.root)
    idx = load_index(root)
    n = 0
    for pid, e in idx["plans"].items():
        if args.id and pid != args.id:
            continue
        for v in sorted(int(k) for k in e["versions"]):
            if (store(root) / pid / f"v{v}" / "plan.txt").is_file():
                build_version(root, pid, v, e)
                n += 1
    print(f"OK rebuilt {n}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cpc.py", description="2CPC interactive plans")
    ap.add_argument("--root", help="project root (default: git root or cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="create a plan (or a new version with --id); DSL on stdin")
    p.add_argument("title", nargs="?")
    p.add_argument("--id")
    p.add_argument("--file", "-f")
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--check", action="store_true", help="validate only: no write, no browser")
    p.set_defaults(fn=cmd_new)
    for name, fn in (("open", cmd_open), ("path", cmd_path)):
        p = sub.add_parser(name)
        p.add_argument("id", nargs="?")
        p.add_argument("--v", type=int)
        p.set_defaults(fn=fn)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("rebuild")
    p.add_argument("id", nargs="?")
    p.set_defaults(fn=cmd_rebuild)
    # allow --root after the subcommand too
    for sp in sub.choices.values():
        sp.add_argument("--root", dest="root_sub", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    args.root = getattr(args, "root_sub", None) or args.root
    args.fn(args)


if __name__ == "__main__":
    main()
