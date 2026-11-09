#!/usr/bin/env python3
"""2CPC — generate interactive plans viewable in the browser.

  cpc.py new [FILE | "Title"] [--id ID] [--file F] [--check] [--no-open] [--root DIR]
      (DSL from FILE/--file, or stdin)
  cpc.py open [ID] [--v N]
  cpc.py list
  cpc.py path ID [--v N]
  cpc.py rebuild [ID] [--v N] [--all]
  cpc.py list [--all] [--archived]
  cpc.py todo ID [KEY ...] [--undo]   ·   cpc.py status ID draft|active|done|archived
  cpc.py gc [ID] [--keep N] [--yes]   (dry run by default)
  cpc.py answers [ID] [--save] [--file F] [--v N]   (save pasted answers / print the last saved)
  cpc.py patch ID [FILE] [--check] [--no-open]       (@replace/@after/@before/@delete/@append/@meta -> vN+1)

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

from cpc.answers import decision_rows, header as answers_header, is_delta, merge as merge_answers  # noqa: E402
from cpc.dashboard import write_dashboard  # noqa: E402
from cpc.parser import parse, slug  # noqa: E402
from cpc.patch import PatchError, apply as apply_patch, diff_sections  # noqa: E402
from cpc.render import render_page  # noqa: E402
from cpc.skill import render_skill  # noqa: E402

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


def load_state(root, pid):
    """Agent-side state of a plan (.2cpc/<id>/state.json): {"todo": {"<todo id>.<key>": "YYYY-MM-DD"}}."""
    f = store(root) / pid / "state.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def save_state(root, pid, st):
    (store(root) / pid / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


STATUS = {"draft": "draft", "brouillon": "draft", "active": "active", "actif": "active", "en-cours": "active",
          "done": "done", "fait": "done", "termine": "done", "archived": "archived", "archive": "archived"}


def norm_status(s):
    return STATUS.get(slug(s or "", 20)) if s else None


def storage_key(root, pid, v):
    h = hashlib.sha1(str(root).lower().encode()).hexdigest()[:6]
    return f"2cpc:{slug(root.name, 24)}-{h}:{pid}:v{v}"


def normalize_eol(text):
    """CRLF, CR, CRCRLF (CRLF re-written in text mode on Windows) -> LF."""
    return re.sub(r"\r+\n?", "\n", text)


def read_input(args):
    if args.file:
        data = Path(args.file).read_bytes()
    else:
        if sys.stdin is None or sys.stdin.isatty():
            die("no input: pipe the plan DSL on stdin (heredoc) or use --file")
        data = sys.stdin.buffer.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return normalize_eol(data.decode(enc))
        except UnicodeDecodeError:
            continue
    return normalize_eol(data.decode("utf-8", errors="replace"))


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

def read_text(path):
    return Path(path).read_bytes().decode("utf-8-sig")


def walk_blocks(blocks):
    for b in blocks:
        yield b
        if b["t"] == "cols":
            for c in b["cols"]:
                yield from walk_blocks(c)
        elif b["t"] == "tabs":
            for tb in b["tabs"]:
                yield from walk_blocks(tb["blocks"])
        elif b["t"] == "details":
            yield from walk_blocks(b["blocks"])


Q_SHAPE = ("qt", "label", "opts", "labels", "rows", "cols", "items", "min", "max")


def decisions_for(pdir, plan, v, lang):
    """{version: rows | None} for every !decisions block of the plan (default: previous version)."""
    out = {}
    for b in walk_blocks(plan.blocks):
        if b["t"] != "decisions":
            continue
        dv = b["v"] or v - 1
        if dv < 1 or dv in out:
            continue
        ans, src = pdir / f"v{dv}" / "answers.txt", pdir / f"v{dv}" / "plan.txt"
        if not (ans.is_file() and src.is_file()):
            out[dv] = None
            continue
        p = parse(read_text(src))
        secs = [b2["text"] for b2 in p.blocks if b2["t"] == "h" and b2["level"] <= 2]
        other = "Other" if (p.meta.get("lang") or lang) == "en" else "Autre"
        out[dv] = decision_rows(p.questions, read_text(ans), secs, other)
    return out


def build_version(root, pid, v, entry, text=None):
    """Render v of plan pid. If text is given it is written as plan.txt first.
    -> (page path, warnings, changes vs v-1 as (changed ids, new ids, removed titles) or None)."""
    pdir = store(root) / pid
    vdir = pdir / f"v{v}"
    vdir.mkdir(parents=True, exist_ok=True)
    src = vdir / "plan.txt"
    if text is not None:
        src.write_text(normalize_eol(text), encoding="utf-8", newline="\n")
    cur_text = read_text(src)
    plan = parse(cur_text)
    vinfo = entry["versions"][str(v)]
    new_ids = set()
    prev_key = None
    changes, prev_q = None, {}
    if v > 1:
        psrc = pdir / f"v{v - 1}" / "plan.txt"
        if psrc.is_file():
            prev_text = read_text(psrc)
            pq = {q["id"]: q for q in parse(prev_text).questions}
            new_ids = {q["id"] for q in plan.questions} - set(pq)
            changes = diff_sections(prev_text, cur_text)
            prev_q = {q["id"]: pq[q["id"]] for q in plan.questions if q["id"] in pq and
                      any(q.get(k) != pq[q["id"]].get(k) for k in Q_SHAPE)}
        prev_key = storage_key(root, pid, v - 1)
    done = load_state(root, pid).get("todo", {})
    for q in plan.questions:
        if q["qt"] == "todo":
            q["agent"] = [lab for k, lab in zip(q["keys"], q["items"]) if f"{q['id']}.{k}" in done]
    versions = sorted(int(k) for k in entry["versions"])
    info = {
        "id": pid, "v": v, "title": vinfo["title"],
        "intro": plan.meta.get("intro", ""), "date": vinfo["date"],
        "project": str(root), "plan_path": str(src),
        "tool": str(HERE / "cpc.py"),
        "key": storage_key(root, pid, v), "prev_key": prev_key,
        "versions": versions,
        "gone": [k for k in versions if k != v and not (pdir / f"v{k}" / "index.html").is_file()],
        "status": entry.get("status"),
        "editor": plan.meta.get("editor") or load_config().get("editor"),
        "changes": changes, "prev_q": prev_q,
        "decisions": decisions_for(pdir, plan, v, plan.meta.get("lang", "")),
    }
    warnings = plan.warnings + render_page(plan, info, root, vdir, new_ids)
    return vdir / "index.html", warnings, changes


def changes_line(changes, v):
    if not changes:
        return ""
    c, n, r = changes
    ids = lambda xs: (" (" + " ".join(xs[:6]) + (" …" if len(xs) > 6 else "") + ")") if xs else ""
    return f"changes vs v{v - 1}: {len(c)} modified{ids(c)} · {len(n)} new{ids(n)} · {len(r)} removed"


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
    line2 = f"ids: {ids}" if ids else ""
    if plan.next is not None:
        line2 += (" · " if line2 else "") + "next: " + " ".join(plan.next["opts"])
    return (f"{secs} sections · {len(plan.questions)} questions" + (f" ({types})" if types else ""), line2)


def asset_warnings(blocks, root):
    out = []

    def walk(bl):
        for b in bl:
            t = b["t"]
            srcs = [b["src"]] if t in ("img", "audio", "video", "html") else [b["a"], b["b"]] if t == "compare" else []
            for src in srcs:
                if not re.match(r"^(https?:)?//|^data:", src, re.I):
                    p = Path(src)
                    if not (p if p.is_absolute() else root / p).is_file():
                        out.append(f"missing asset: {src}")
            if t == "link" and not re.match(r"^[a-z][a-z0-9+.-]*:|^#", b["href"], re.I):
                p = Path(re.sub(r":\d+(:\d+)?$", "", b["href"]))
                if not (p if p.is_absolute() else root / p).exists():
                    out.append(f"missing link target: {b['href']}")
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
    if args.check:
        check_report(root, parsed)
        return
    publish(root, text, parsed, args.id, args.title, args.no_open)


def check_report(root, parsed, extra=()):
    line1, line2 = summary(parsed)
    warns = parsed.warnings + asset_warnings(parsed.blocks, root)
    print(f"CHECK {'ok' if not warns else 'warn'} · {line1}")
    for ln in (line2, *extra):
        if ln:
            print(ln)
    for w in warns[:30]:
        print(f"WARN {w}")


def publish(root, text, parsed, pid_arg=None, title_arg=None, no_open=False, prefix=""):
    """Write a new plan (or version vN+1 of pid_arg), render it, print the OK report."""
    meta = parsed.meta
    title = title_arg or meta.get("title") or "Plan"
    idx = load_index(root)
    plans = idx["plans"]
    if pid_arg:
        pid = slug(pid_arg, 40)
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
    st_warn = ""
    if meta.get("status"):
        st = norm_status(meta["status"])
        if st:
            entry["status"] = st
        else:
            st_warn = f"bad status '{meta['status']}' (draft|active|done|archived)"
    plans[pid] = entry
    page, warnings, changes = build_version(root, pid, v, entry, text)
    for old in range(1, v):  # refresh version links on older pages
        if str(old) in entry["versions"] and (store(root) / pid / f"v{old}" / "index.html").is_file():
            build_version(root, pid, old, entry)
    save_index(root, idx)
    register(root)
    refresh_dashboard(root)
    if st_warn:
        warnings.append(st_warn)
    line1, line2 = summary(parsed)
    print(f"OK {pid} v{v} · {prefix}{line1}")
    for ln in (line2, changes_line(changes, v)):
        if ln:
            print(ln)
    for w in warnings[:30]:
        print(f"WARN {w}")
    sw = skill_warning()
    if sw:
        print(sw)
    if not no_open:
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


def cpc_home():
    return Path(os.environ.get("CPC_HOME") or (Path.home() / ".2cpc"))


def load_config():
    """~/.2cpc/config.json, e.g. {"editor": "vscode" | "cursor" | "idea" | "rider" | "none" | "<url with {path} {line} {col}>"}."""
    f = cpc_home() / "config.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            print(f"WARN invalid {f}")
    return {}


def load_registry():
    f = cpc_home() / "registry.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"projects": {}}


def register(root):
    """Remember this project in ~/.2cpc/registry.json (for `list --all` / `rebuild --all`)."""
    try:
        reg = load_registry()
        reg["projects"][str(root)] = {"name": root.name, "updated": dt.datetime.now().isoformat(timespec="seconds")}
        cpc_home().mkdir(parents=True, exist_ok=True)
        (cpc_home() / "registry.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:  # pragma: no cover
        print(f"WARN registry not updated: {e}")


def registry_roots():
    """Registered projects that still have a .2cpc/index.json."""
    return [Path(p) for p in sorted(load_registry()["projects"]) if (Path(p) / ".2cpc" / "index.json").is_file()]


def refresh_dashboard(root):
    try:
        write_dashboard(root, load_index(root), load_state, storage_key)
    except OSError as e:  # pragma: no cover
        print(f"WARN dashboard not written: {e}")


def skill_warning():
    """WARN line if the installed skill differs from skill/SKILL.md (run install.py)."""
    installed = Path(os.environ.get("CPC_SKILL_FILE") or (Path.home() / ".claude" / "skills" / "2cpc" / "SKILL.md"))
    if not installed.is_file():
        return ""
    try:
        if installed.read_text(encoding="utf-8") != render_skill(HERE):
            return f'WARN skill outdated: python "{(HERE / "install.py").as_posix()}"'
    except OSError:
        pass
    return ""


def plan_lines(root, pid, e, prefix=""):
    st = e.get("status") or "active"
    return f"{prefix}{pid} v{e['v']} {e.get('updated', '')[:10]} [{st}] {e['title']}"


def cmd_list(args):
    roots = registry_roots() if args.all else [project_root(args.root)]
    shown = 0
    for root in roots:
        plans = load_index(root)["plans"]
        hidden = 0
        for pid, e in sorted(plans.items(), key=lambda kv: kv[1].get("updated", ""), reverse=True):
            if e.get("status") == "archived" and not args.archived:
                hidden += 1
                continue
            print(plan_lines(root, pid, e, f"{root.name}/" if args.all else ""))
            shown += 1
        if hidden and not args.all:
            print(f"({hidden} archived: list --archived)")
    if not shown and not args.all:
        print(f"(none in {store(roots[0])})")
    elif not roots:
        print("(no registered project)")


def rebuild_root(root, pid=None, only_v=None):
    idx = load_index(root)
    n = 0
    for p, e in idx["plans"].items():
        if pid and p != pid:
            continue
        for v in sorted(int(k) for k in e["versions"]):
            vdir = store(root) / p / f"v{v}"
            if only_v and v != only_v:
                continue
            # versions removed by gc stay removed, except the latest one or when asked with --v
            if (vdir / "plan.txt").is_file() and ((vdir / "index.html").is_file() or v == e["v"] or only_v):
                build_version(root, p, v, e)
                n += 1
    refresh_dashboard(root)
    return n


def cmd_rebuild(args):
    if args.all:
        total = 0
        for root in registry_roots():
            n = rebuild_root(root)
            total += n
            print(f"OK {root} · {n}")
        print(f"OK rebuilt {total}")
        return
    root = project_root(args.root)
    print(f"OK rebuilt {rebuild_root(root, args.id, args.v)}")


def latest_plan(root, pid):
    pid, v, vdir = resolve(root, pid, None)
    return pid, v, parse(read_text(vdir / "plan.txt"))


def cmd_todo(args):
    """Mark todo items as done by the agent (state.json), or list them."""
    root = project_root(args.root)
    pid, v, plan = latest_plan(root, args.id)
    items = [(q["id"], k, lab) for q in plan.questions if q["qt"] == "todo" for k, lab in zip(q["keys"], q["items"])]
    st = load_state(root, pid)
    done = st.setdefault("todo", {})
    if not args.keys:
        for qid, k, lab in items:
            print(f"{'x' if f'{qid}.{k}' in done else ' '} {qid}.{k}" + (f"  {lab}" if lab != k else ""))
        return
    targets = []
    for a in args.keys:
        hits = [it for it in items if f"{it[0]}.{it[1]}" == a] or [it for it in items if a in (it[1], it[2])]
        if len(hits) != 1:
            known = " ".join(f"{q}.{k}" for q, k, _ in items) or "(no !todo)"
            die(f"{'ambiguous' if hits else 'unknown'} todo '{a}' · known: {known}")
        targets.append(f"{hits[0][0]}.{hits[0][1]}")
    for t in targets:
        if args.undo:
            done.pop(t, None)
        else:
            done.setdefault(t, dt.date.today().isoformat())
    save_state(root, pid, st)
    build_version(root, pid, v, load_index(root)["plans"][pid])
    refresh_dashboard(root)
    n = sum(1 for q, k, _ in items if f"{q}.{k}" in done)
    print(f"OK todo {pid} v{v} · {n}/{len(items)} done · {'undo' if args.undo else 'done'}: {' '.join(targets)}")


def cmd_status(args):
    root = project_root(args.root)
    idx = load_index(root)
    if args.id not in idx["plans"]:
        die(f"unknown plan '{args.id}' (see: cpc.py list)")
    st = norm_status(args.value)
    if not st:
        die(f"bad status '{args.value}' (draft|active|done|archived, or brouillon|actif|fait|archivé)")
    e = idx["plans"][args.id]
    e["status"] = st
    save_index(root, idx)
    if (store(root) / args.id / f"v{e['v']}" / "plan.txt").is_file():
        build_version(root, args.id, e["v"], e)
    refresh_dashboard(root)
    print(f"OK {args.id} [{st}]")


def cmd_gc(args):
    """Remove old pages (keep plan.txt / answers.txt) and unreferenced assets. Dry run unless --yes."""
    root = project_root(args.root)
    idx = load_index(root)
    victims = []
    for pid, e in idx["plans"].items():
        if args.id and pid != args.id:
            continue
        pdir = store(root) / pid
        versions = sorted(int(k) for k in e["versions"])
        keep = set(versions[-max(1, args.keep):])
        for v in versions:
            vdir = pdir / f"v{v}"
            if v not in keep and (vdir / "index.html").is_file():
                victims.append(vdir / "index.html")
        pages = [pdir / f"v{v}" / "index.html" for v in versions]
        alive = [p for p in pages if p.is_file() and p not in victims]
        html = "".join(p.read_text(encoding="utf-8") for p in alive)
        for v in versions:  # legacy per-version assets (before shared assets)
            legacy = pdir / f"v{v}" / "assets"
            page = pdir / f"v{v}" / "index.html"
            if legacy.is_dir() and (page in victims or not page.is_file() or
                                    not re.search(r'(src|href)="assets/', page.read_text(encoding="utf-8"))):
                victims += [f for f in legacy.rglob("*") if f.is_file()]
        if (pdir / "assets").is_dir():
            victims += [f for f in (pdir / "assets").iterdir() if f.is_file() and f"../assets/{f.name}" not in html]
    size = sum(f.stat().st_size for f in victims)
    for f in victims:
        print(f"{'DEL' if args.yes else 'would delete'} {f.relative_to(store(root)).as_posix()}")
    if args.yes:
        for f in victims:
            f.unlink()
        for d in sorted({f.parent for f in victims}, key=lambda p: len(p.parts), reverse=True):
            if d.name == "assets" and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        for pid, e in idx["plans"].items():  # version links -> "removed"
            if not args.id or pid == args.id:
                for v in sorted(int(k) for k in e["versions"]):
                    if (store(root) / pid / f"v{v}" / "index.html").is_file():
                        build_version(root, pid, v, e)
        refresh_dashboard(root)
        print(f"OK gc · {len(victims)} file(s) · {size / 1e6:.1f} MB freed")
    else:
        print(f"DRY RUN · {len(victims)} file(s) · {size / 1e6:.1f} MB · run again with --yes to delete")


def cmd_answers(args):
    """--save: store pasted answers in vN/answers.txt (vN from the `2CPC id vN` header). Else print the last saved."""
    root = project_root(args.root)
    if args.save:
        text = read_input(args).strip()
        if not text:
            die("empty answers")
        hid, hv = answers_header(text)
        if not args.id and not hid:
            die("plan id unknown: pass it (cpc.py answers <id> --save)")
        if args.id and hid and slug(hid, 40) != slug(args.id, 40):
            die(f"answers are for '{hid}', not '{args.id}'")
        pid, v, vdir = resolve(root, args.id or hid, args.v or hv)
        dest = vdir / "answers.txt"
        if is_delta(text):  # "What's new": merge into the saved answers of this version
            text = merge_answers(read_text(dest) if dest.is_file() else "", text)
            print(f"OK merged Δ into {pid} v{v}")
        dest.write_text(text + "\n", encoding="utf-8", newline="\n")
        n = sum(1 for ln in text.splitlines()[1:] if "=" in ln and not ln.startswith(("Intro :", "Projet :")))
        print(f"OK saved {pid} v{v} · {n} line(s) · {vdir / 'answers.txt'}")
        entry = load_index(root)["plans"][pid]
        for later in sorted(int(k) for k in entry["versions"] if int(k) > v):  # refresh !decisions
            src = store(root) / pid / f"v{later}" / "plan.txt"
            if src.is_file() and re.search(r"^\s*!decisions\b", read_text(src), re.M):
                build_version(root, pid, later, entry)
                print(f"OK rebuilt v{later} (!decisions)")
        refresh_dashboard(root)
        return
    pid, v, _ = resolve(root, args.id, args.v)
    for k in ([v] if args.v else range(v, 0, -1)):
        f = store(root) / pid / f"v{k}" / "answers.txt"
        if f.is_file():
            print(f"# {f}")
            print(read_text(f).rstrip())
            return
    die(f"no saved answers for '{pid}' (cpc.py answers {pid} --save)")


def cmd_patch(args):
    """Apply @replace/@after/@before/@delete/@append/@meta operations to the last version -> vN+1."""
    root = project_root(args.root)
    pid, v, vdir = resolve(root, args.id, None)
    if not args.id:
        die("plan id required: cpc.py patch <id> <file>")
    if args.patchfile and not args.file:
        args.file = args.patchfile
    try:
        text, n = apply_patch(read_text(vdir / "plan.txt"), read_input(args))
    except PatchError as e:
        die(f"patch: {e} (nothing written)")
    parsed = parse(text)
    if args.check:
        check_report(root, parsed, (f"patch: {n} op(s) OK on v{v}",
                                    changes_line(diff_sections(read_text(vdir / "plan.txt"), text), v + 1)))
        return
    publish(root, text, parsed, pid, None, args.no_open, prefix=f"patch {n} op(s) · ")


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
    p = sub.add_parser("answers", help="save pasted answers (--save, stdin/--file) or print the last saved")
    p.add_argument("id", nargs="?")
    p.add_argument("--v", type=int)
    p.add_argument("--save", action="store_true")
    p.add_argument("--file", "-f")
    p.set_defaults(fn=cmd_answers)
    p = sub.add_parser("patch", help="apply @operations to the last version -> new version")
    p.add_argument("id", nargs="?")
    p.add_argument("patchfile", nargs="?")
    p.add_argument("--file", "-f")
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--check", action="store_true", help="validate only: no write, no browser")
    p.set_defaults(fn=cmd_patch)
    p = sub.add_parser("list", help="plans of the project (--all: every registered project)")
    p.add_argument("--all", action="store_true")
    p.add_argument("--archived", action="store_true")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("rebuild", help="re-render pages (--all: every registered project)")
    p.add_argument("id", nargs="?")
    p.add_argument("--v", type=int)
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_rebuild)
    p = sub.add_parser("todo", help="mark !todo items done by the agent (no key: list them)")
    p.add_argument("id")
    p.add_argument("keys", nargs="*")
    p.add_argument("--undo", action="store_true")
    p.set_defaults(fn=cmd_todo)
    p = sub.add_parser("status", help="set a plan status: draft|active|done|archived")
    p.add_argument("id")
    p.add_argument("value")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("gc", help="remove old pages + unused assets (dry run unless --yes)")
    p.add_argument("id", nargs="?")
    p.add_argument("--keep", type=int, default=3)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_gc)
    # allow --root after the subcommand too
    for sp in sub.choices.values():
        sp.add_argument("--root", dest="root_sub", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    args.root = getattr(args, "root_sub", None) or args.root
    args.fn(args)


if __name__ == "__main__":
    main()
